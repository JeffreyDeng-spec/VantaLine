#!/usr/bin/env python3
"""Isolated PostgreSQL contract for fixed model-profile and call-list reads."""
from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import sys
import threading
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg.pq import TransactionStatus
from fastapi import HTTPException
from local_inspection_service.model_profiles.dependencies import ProfileDependencies
from local_inspection_service.model_profiles.repository import Repository
from local_inspection_service.model_profiles.service import Service
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl


def main():
    dsn = os.environ['VANTALINE_POSTGRES_DSN']
    schema = 'model_reads_' + uuid.uuid4().hex
    connections = []
    secrets = {'old-key': 'secret-old', 'new-key': 'secret-new', 'proxy': 'https://proxy.example'}
    with psycopg.connect(dsn) as setup:
        setup.execute(postgres_ddl(schema))

    def make():
        conn = psycopg.connect(dsn)
        conn.execute("SET lock_timeout = '6000ms'")
        conn.execute("SET statement_timeout = '8000ms'")
        conn.commit()
        runtime = PostgresRuntimeRepository(conn, 'test', schema)
        connections.append(conn)
        reads = []

        def read_secret(ref):
            assert conn.info.transaction_status == TransactionStatus.IDLE
            reads.append(ref)
            return secrets[ref]

        deps = ProfileDependencies(runtime_repository=lambda: runtime,
            write_secret=lambda k, v: None, read_secret=read_secret,
            legacy_sources=lambda: [], validate_model=lambda v: None,
            validate_base_url=lambda v: None, mask_secret=lambda v: '****')
        return Service(deps), Repository(runtime), runtime, reads

    try:
        writer_service, writer, _, _ = make()
        profile = dict(id='mp_fixed', version=1, name='original', provider='qwen',
            model='qwen3-vl-flash', base_url='https://example.invalid/v1',
            timeout_seconds=30, enabled=True, secret_ref='old-key',
            masked_key='****', proxy_ref='proxy', operational={})
        newer = {**profile, 'version': 2, 'name': 'rotated', 'secret_ref': 'new-key'}
        reference = {'id': 'mp_fixed', 'version': 1}
        with writer.transaction() as cursor:
            writer.put(cursor, 'mp_fixed:1', 'profile', profile)
            writer.put(cursor, 'mp_fixed:2', 'profile', newer)
            writer.put(cursor, 'test:mp_fixed:1', 'test', {'ok': False, 'at': 1})
            writer.put(cursor, 'call-base', 'call', {'marker': 'base'})
        reader_service, _, reader_runtime, secret_reads = make()
        with patch.object(reader_service, 'initialize', side_effect=AssertionError('fixed ref initialized')):
            original = reader_service.resolve('label', reference)
        assert original['api_key'] == 'secret-old'
        assert original['proxy_url_raw'] == 'https://proxy.example'
        assert original['connection_status'] == 'failed'
        assert secret_reads == ['old-key', 'proxy']
        assert reader_service.calls() == [{'marker': 'base'}]

        next_call = {'marker': 'new'}
        call_reader, _, _, _ = make()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            with writer.transaction() as cursor:
                writer.put(cursor, 'test:mp_fixed:1', 'test', {'ok': True, 'at': 2}, replace=True)
                writer.put(cursor, 'call-next', 'call', next_call)
                resolved = pool.submit(reader_service.resolve, 'label', reference)
                calls = pool.submit(call_reader.calls)
                assert resolved.result(timeout=3)['connection_status'] == 'failed'
                assert calls.result(timeout=3) == [{'marker': 'base'}]
        assert reader_service.resolve('label', reference)['connection_status'] == 'connected'
        assert reader_service.resolve('label', reference)['api_key'] == 'secret-old'
        assert {row['marker'] for row in reader_service.calls()} == {'base', 'new'}
        assert reader_service.resolve('label', {'id': 'mp_fixed', 'version': 2})['api_key'] == 'secret-new'

        original_decode = PostgresRuntimeRepository._row_to_dict
        for method in ('resolve', 'calls'):
            service, _, runtime, _ = make()
            entered = threading.Event()
            release = threading.Event()

            def pause_decode(self, cursor, row):
                if self is runtime and not entered.is_set():
                    entered.set()
                    assert release.wait(3), 'read decoder did not resume'
                return original_decode(self, cursor, row)

            with patch.object(PostgresRuntimeRepository, '_row_to_dict', pause_decode):
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(service.resolve, 'label', reference) if method == 'resolve' else pool.submit(service.calls)
                    try:
                        assert entered.wait(3), f'{method} did not decode a row'
                        _, independent_writer, _, _ = make()
                        independent_writer.runtime.connection.execute("SET lock_timeout = '750ms'")
                        with independent_writer.transaction() as cursor:
                            cursor.execute('SELECT 1')
                    finally:
                        release.set()
                    assert future.result(timeout=3)

        for method in ('resolve', 'calls'):
            service, _, runtime, _ = make()
            original_cursor = PostgresRuntimeRepository._cursor
            opened = []
            marker = RuntimeError(method + ' synthetic decode failure')

            def track_cursor(self):
                cursor = original_cursor(self)
                if self is runtime:
                    opened.append(cursor)
                return cursor

            def fail_decode(self, cursor, row):
                if self is runtime:
                    raise marker
                return original_decode(self, cursor, row)

            with patch.object(PostgresRuntimeRepository, '_cursor', track_cursor):
                with patch.object(PostgresRuntimeRepository, '_row_to_dict', fail_decode):
                    try:
                        service.resolve('label', reference) if method == 'resolve' else service.calls()
                    except RuntimeError as exc:
                        assert exc is marker
                    else:
                        raise AssertionError(method + ' swallowed decode failure')
                assert opened[-1].closed
                assert runtime.connection.info.transaction_status == TransactionStatus.IDLE
                assert service.resolve('label', reference) if method == 'resolve' else service.calls()
                assert opened[-1].closed
                assert runtime.connection.info.transaction_status == TransactionStatus.IDLE

        missing_service, _, missing_runtime, missing_reads = make()
        original_get = Repository.get
        queried = []

        def track_get(self, cursor, identity):
            if self.runtime is missing_runtime:
                queried.append(identity)
            return original_get(self, cursor, identity)

        with patch.object(Repository, 'get', track_get):
            try:
                missing_service.resolve('label', {'id': 'absent', 'version': 7})
            except HTTPException as exc:
                assert exc.status_code == 503 and exc.detail == '任务引用的模型配置版本不存在'
            else:
                raise AssertionError('missing fixed version did not fail closed')
        assert queried == ['absent:7', 'test:absent:7']
        assert missing_reads == []
        assert missing_runtime.connection.info.transaction_status == TransactionStatus.IDLE

        no_database = Service(ProfileDependencies(runtime_repository=lambda: (_ for _ in ()).throw(AssertionError('database used')),
            write_secret=lambda k, v: None, read_secret=lambda ref: '', legacy_sources=lambda: [],
            validate_model=lambda v: None, validate_base_url=lambda v: None, mask_secret=lambda v: ''))
        assert no_database.resolve('label', None)['status'] == 'unconfigured'

        service, _, runtime, _ = make()
        original_cursor = PostgresRuntimeRepository._cursor
        opened = []

        def track_cursor(self):
            cursor = original_cursor(self)
            if self is runtime:
                opened.append(cursor)
            return cursor

        def invalid_json(self, cursor, row):
            if self is runtime:
                return {'raw_json': '{'}
            return original_decode(self, cursor, row)

        original_loads = json.loads

        def decode_after_commit(value, *args, **kwargs):
            if value == '{':
                assert runtime.connection.info.transaction_status == TransactionStatus.IDLE
                assert opened[-1].closed
            return original_loads(value, *args, **kwargs)

        with patch.object(PostgresRuntimeRepository, '_cursor', track_cursor):
            with patch.object(PostgresRuntimeRepository, '_row_to_dict', invalid_json):
                with patch.object(json, 'loads', decode_after_commit):
                    try:
                        service.calls()
                    except json.JSONDecodeError:
                        pass
                    else:
                        raise AssertionError('post-commit JSON error disappeared')
            assert opened[-1].closed
            assert runtime.connection.info.transaction_status == TransactionStatus.IDLE
            assert service.calls()

        with writer.transaction() as cursor:
            cursor.execute(f"INSERT INTO {writer.table}(id,kind,created_at,raw_json) "
                "SELECT 'bulk-' || lpad(n::text,4,'0'),'call',2000000000,jsonb_build_object('n',n) "
                "FROM generate_series(0,501) AS n")
        bulk = reader_service.calls()
        assert len(bulk) == 500
        assert [row['n'] for row in bulk] == list(range(501, 1, -1))
        print('PASS model fixed reads: committed view, no read fence, snapshot keys, rollback/IDLE, error order, call order/limit')
    finally:
        for conn in connections:
            conn.close()
        with psycopg.connect(dsn) as cleanup:
            cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')


if __name__ == '__main__':
    main()
