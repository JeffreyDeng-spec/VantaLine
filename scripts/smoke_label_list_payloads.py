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
            ('safe-old', 'alice', 'safe-task', 10, dict(id='safe-old', kind='run', task_id='safe-task',
                created_at=10, status='failed', decision='DIFFERENCES', profile_snapshot={'blob': heavy})),
            ('safe-new', 'alice', 'safe-task', 11, dict(id='safe-new', kind='run', task_id='safe-task',
                created_at=11, status='succeeded', decision='MATCH', model=heavy)),
            ('tie-z', 'alice', 'tie-task', 2, dict(id='tie-z', kind='run', task_id='tie-task',
                created_at=20, status='failed', decision='DIFFERENCES')),
            ('tie-a', 'alice', 'tie-task', 30, dict(id='tie-a', kind='run', task_id='tie-task',
                created_at=20, status='succeeded', decision='MATCH')),
            ('null-fields', 'alice', 'field-task', 33, dict(id='null-fields', kind='run',
                task_id='field-task', created_at=33.25, status=None, decision=None)),
            ('missing-fields', 'alice', 'field-task', 34, dict(id='missing-fields', kind='run',
                task_id='field-task', created_at=34.5)),
            ('id-mismatch', 'alice', 'id-task', 31, dict(id='json-id', kind='run', task_id='id-task',
                created_at=21, status='succeeded')),
            ('fraction-only', 'alice', 'fraction-task', 32, dict(id='fraction-only', kind='run', task_id='fraction-task',
                created_at=22.5, status='succeeded')),
            ('missing-time-old', 'alice', 'missing-time-task', 14, dict(id='missing-time-old',
                kind='run', task_id='missing-time-task', status='failed')),
            ('valid-time-new', 'alice', 'missing-time-task', 15, dict(id='valid-time-new',
                kind='run', task_id='missing-time-task', created_at=15, status='succeeded')),
            ('bad-import', 'alice', 'bad-task', 12, dict(id='bad-import', kind='run', task_id='bad-task',
                created_at=12, status='failed', **{'import': []})),
            ('good-new', 'alice', 'bad-task', 13, dict(id='good-new', kind='run', task_id='bad-task',
                created_at=13, status='succeeded')),
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
        huge = ('{"id":"huge-old","kind":"run","task_id":"huge-task",'
                '"created_at":1,"status":"failed","x":' + '9' * 5000 + '}')
        with writer.tx() as cursor:
            cursor.execute(
                f'INSERT INTO {table} (id,owner_user_id,task_id,kind,status,created_at,updated_at,idempotency_key,raw_json) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                ('huge-old', 'alice', 'huge-task', 'run', 'failed', 1, 1, 'key-huge', huge),
            )
            cursor.execute(
                f'INSERT INTO {table} (id,owner_user_id,task_id,kind,status,created_at,updated_at,idempotency_key,raw_json) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                ('huge-new', 'alice', 'huge-task', 'run', 'succeeded', 2, 2, 'key-new',
                 json.dumps({'id': 'huge-new', 'kind': 'run', 'task_id': 'huge-task',
                             'created_at': 2, 'status': 'succeeded'})),
            )
        decode_outcomes = []
        for reader_fn in (reader.list_run_payloads_for_tasks, reader.native_run_summaries_for_tasks):
            try:
                result = reader_fn('alice', ['huge-task'])
            except ValueError as exc:
                decode_outcomes.append((type(exc), str(exc)))
            else:
                decode_outcomes.append(result['huge-task'])
        if isinstance(decode_outcomes[0], tuple):
            assert decode_outcomes[0] == decode_outcomes[1], decode_outcomes
        else:
            assert decode_outcomes[1]['safe'] is False
            assert decode_outcomes[1]['runs'] == decode_outcomes[0], decode_outcomes
        deep = {'id': 'deep-old', 'kind': 'run', 'task_id': 'deep-task',
                'created_at': 1, 'status': 'failed', 'evidence': []}
        nested = deep['evidence']
        for _ in range(80):
            child = []
            nested.append(child)
            nested = child
        with writer.tx() as cursor:
            cursor.execute(
                f'INSERT INTO {table} (id,owner_user_id,task_id,kind,status,created_at,updated_at,idempotency_key,raw_json) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                ('deep-old', 'alice', 'deep-task', 'run', 'failed', 1, 1, 'key-deep',
                 json.dumps(deep)),
            )
        deep_group = reader.native_run_summaries_for_tasks('alice', ['deep-task'])['deep-task']
        assert deep_group['safe'] is False
        assert deep_group['runs'] == reader.list_run_payloads_for_tasks('alice', ['deep-task'])['deep-task']
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
        summaries = reader.native_run_summaries_for_tasks('alice', ['safe-task', 'bad-task', 'task', 'missing'])
        assert summaries['safe-task']['safe'] is True
        assert summaries['safe-task']['count'] == 2
        assert [run['id'] for run in summaries['safe-task']['runs']] == ['safe-new', 'safe-old']
        assert all('model' not in run and 'profile_snapshot' not in run
                   for run in summaries['safe-task']['runs'])
        assert [run['id'] for run in sorted(
            [public(row) for row in summaries['safe-task']['runs']],
            key=lambda row: (row['created_at'], row['id']), reverse=True
        )] == ['safe-new', 'safe-old']
        missing_time = reader.native_run_summaries_for_tasks('alice', ['missing-time-task'])['missing-time-task']
        assert missing_time['safe'] is False
        assert missing_time['runs'] == reader.list_run_payloads_for_tasks('alice', ['missing-time-task'])['missing-time-task']
        assert summaries['bad-task']['safe'] is False
        assert summaries['bad-task']['runs'] == reader.list_run_payloads_for_tasks('alice', ['bad-task'])['bad-task']
        assert summaries['task']['safe'] is False
        assert summaries['task']['runs'] == light['task']
        assert summaries['missing'] == {'safe': True, 'count': 0, 'runs': []}
        more = reader.native_run_summaries_for_tasks('alice', ['tie-task', 'id-task', 'fraction-task'])
        assert more['tie-task']['safe'] is True
        assert [row['id'] for row in sorted(more['tie-task']['runs'], key=lambda row: (row['created_at'], row['id']), reverse=True)] == ['tie-z', 'tie-a']
        assert more['id-task']['safe'] is False and more['id-task']['runs'][0]['id'] == 'json-id'
        assert more['fraction-task']['safe'] is True and more['fraction-task']['runs'][0]['created_at'] == 22.5
        fields = reader.native_run_summaries_for_tasks('alice', ['field-task'])['field-task']
        assert fields['safe'] is True and fields['count'] == 2
        by_id = {row['id']: row for row in fields['runs']}
        assert by_id['null-fields']['status'] is None and by_id['null-fields']['decision'] is None
        assert 'status' not in by_id['missing-fields'] and 'decision' not in by_id['missing-fields']
        assert reader.native_run_summaries_for_tasks('bob', ['safe-task'])['safe-task']['count'] == 0
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with writer.tx() as cursor:
                cursor.execute(f'UPDATE {table} SET raw_json=%s::jsonb WHERE id=%s',
                    (json.dumps({**next(value for identity, _, _, _, value in rows if identity == 'safe-new'), 'status': 'changed'}), 'safe-new'))
                future = pool.submit(reader.native_run_summaries_for_tasks, 'alice', ['safe-task'])
                pending_summary = future.result(timeout=3)['safe-task']
                assert pending_summary['safe'] is True
                assert pending_summary['runs'][0]['status'] == 'succeeded'
        committed_summary = reader.native_run_summaries_for_tasks('alice', ['safe-task'])['safe-task']
        assert committed_summary['runs'][0]['status'] == 'changed'

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
            with patch.object(PostgresRuntimeRepository, '_row_to_dict', fail_decode):
                try:
                    reader.native_run_summaries_for_tasks('alice', ['safe-task'])
                except RuntimeError as exc:
                    assert exc is marker
                else:
                    raise AssertionError('summary decoder error disappeared')
            assert opened[-1].closed
            assert reader_runtime.connection.info.transaction_status == TransactionStatus.IDLE
            assert reader.native_run_summaries_for_tasks('alice', ['safe-task'])
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
