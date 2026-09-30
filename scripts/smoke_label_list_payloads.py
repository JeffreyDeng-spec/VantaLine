#!/usr/bin/env python3
"""Isolated PostgreSQL contract for list-only label run payload trimming."""
from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import sys
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg.pq import TransactionStatus
from local_inspection_service.label_inspection.api import public
from local_inspection_service.storage.label_inspection import LabelRepository, RUN_BATCH_SIZE
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl

DISCARDED = {'model', 'prompt_hash', 'layout', 'transformations', 'profile_snapshot'}


def main():
    dsn = os.environ['VANTALINE_POSTGRES_DSN']
    schema = 'label_payload_' + uuid.uuid4().hex
    connections = []
    created = False

    def make():
        conn = psycopg.connect(dsn)
        connections.append(conn)
        conn.execute("SET lock_timeout = '6000ms'")
        conn.execute("SET statement_timeout = '8000ms'")
        conn.commit()
        runtime = PostgresRuntimeRepository(conn, 'test', schema)
        return LabelRepository(runtime), runtime

    try:
        with psycopg.connect(dsn) as setup:
            setup.execute(postgres_ddl(schema))
        created = True
        writer, _ = make()
        reader, reader_runtime = make()
        table = writer.table
        heavy = 'synthetic-' + 'x' * 8192
        rows = [
            ('first', 'alice', 'task', 1, dict(id='first', kind='run', task_id='task',
                created_at=1.75, status='succeeded', decision='MATCH',
                model=heavy, prompt_hash=heavy, layout={'blob': heavy},
                transformations=[heavy], profile_snapshot={'secret_ref': heavy},
                quality={'score': 1}, **{'import': {'version': 'v1', 'ignored': heavy}})),
            ('earlier', 'alice', 'task', 1, dict(id='earlier', kind='run', task_id='task',
                created_at=1.25, status='failed', decision='DIFFERENCES',
                profile_snapshot={'secret_ref': heavy})),
            ('mismatch', 'alice', 'task', 2, dict(id='mismatch', kind='run', task_id='other',
                created_at=2.5, status='succeeded', decision='MATCH')),
            ('other-kind', 'alice', 'task', 3, dict(id='other-kind', kind='task', task_id='task',
                created_at=3, status='ready', model=heavy)),
            ('scalar', 'alice', 'task', 4, 'scalar-json'),
            ('neighbor', 'bob', 'task', 5, dict(id='neighbor', kind='run', task_id='task',
                created_at=5, status='succeeded', model=heavy)),
        ]
        with writer.tx() as cursor:
            for identity, owner, task, row_created, value in rows:
                cursor.execute(
                    f'INSERT INTO {table} (id,owner_user_id,task_id,kind,status,created_at,updated_at,idempotency_key,raw_json) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                    (identity, owner, task, 'run', 'succeeded', row_created, row_created,
                     'key-' + identity, json.dumps(value)),
                )
        assert reader.list_run_payloads_for_tasks('alice', []) == {}
        try:
            reader.list_run_payloads_for_tasks('alice', ['task'] * (RUN_BATCH_SIZE + 1))
        except ValueError as exc:
            assert str(exc) == 'run batch exceeds limit'
        else:
            raise AssertionError('oversized payload batch accepted')
        assert reader.list_run_payloads_for_tasks('bob', ['other']) == {'other': []}
        full = reader.runs_for_tasks('alice', ['task', 'other'])
        light = reader.list_run_payloads_for_tasks('alice', ['task', 'other'])
        assert set(full) == set(light) == {'task', 'other'}
        for task_id in full:
            assert len(full[task_id]) == len(light[task_id])
            for old, new in zip(full[task_id], light[task_id]):
                if isinstance(old, dict) and old.get('kind') == 'run':
                    assert new == {k: v for k, v in old.items() if k not in DISCARDED}
                    assert public(old) == public(new)
                else:
                    assert new == old
        assert [row['id'] if isinstance(row, dict) else row for row in light['task']] == [
            'scalar-json', 'other-kind', 'mismatch', 'first', 'earlier']
        assert light['task'][2]['task_id'] == 'other'  # grouping uses SQL task_id
        assert light['task'][3]['created_at'] == 1.75  # JSON fraction retained
        assert 'model' in light['task'][1]  # JSON kind != run is not trimmed
        assert 'model' not in light['task'][3]
        assert len(json.dumps(light)) < len(json.dumps(full)) // 2
        assert reader_runtime.connection.info.transaction_status == TransactionStatus.IDLE

        # A pending writer does not block a list read or leak uncommitted JSON.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with writer.tx() as cursor:
                cursor.execute(f'UPDATE {table} SET raw_json=%s::jsonb WHERE id=%s',
                    (json.dumps({**rows[0][4], 'status': 'changed'}), 'first'))
                future = pool.submit(reader.list_run_payloads_for_tasks, 'alice', ['task'])
                pending = future.result(timeout=3)
                assert next(x for x in pending['task'] if isinstance(x, dict) and x.get('id') == 'first')['status'] == 'succeeded'
        committed = reader.list_run_payloads_for_tasks('alice', ['task'])
        assert next(x for x in committed['task'] if isinstance(x, dict) and x.get('id') == 'first')['status'] == 'changed'

        opened = []
        original_cursor = PostgresRuntimeRepository._cursor
        original_decode = PostgresRuntimeRepository._row_to_dict
        marker = RuntimeError('payload decode failure')
        def track_cursor(self):
            cursor = original_cursor(self)
            if self is reader_runtime:
                opened.append(cursor)
            return cursor
        def fail_decode(self, cursor, row):
            if self is reader_runtime:
                assert self.connection.info.transaction_status == TransactionStatus.INTRANS
                raise marker
            return original_decode(self, cursor, row)
        with patch.object(PostgresRuntimeRepository, '_cursor', track_cursor):
            with patch.object(PostgresRuntimeRepository, '_row_to_dict', fail_decode):
                try:
                    reader.list_run_payloads_for_tasks('alice', ['task'])
                except RuntimeError as exc:
                    assert exc is marker
                else:
                    raise AssertionError('payload decoder error disappeared')
            assert opened[-1].closed
            assert reader_runtime.connection.info.transaction_status == TransactionStatus.IDLE
            assert reader.list_run_payloads_for_tasks('alice', ['task'])
            assert opened[-1].closed
        print('PASS label list payloads: exact projection, owner/SQL grouping, committed view, no fence, rollback/IDLE')
    finally:
        pending = sys.exc_info()[0] is not None
        cleanup_error = None
        for conn in connections:
            try:
                conn.close()
            except Exception as exc:
                cleanup_error = cleanup_error or exc
        if created:
            try:
                with psycopg.connect(dsn) as cleanup:
                    cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')
            except Exception as exc:
                cleanup_error = cleanup_error or exc
        if cleanup_error is not None and not pending:
            raise cleanup_error


if __name__ == '__main__':
    main()
