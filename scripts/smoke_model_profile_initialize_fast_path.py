#!/usr/bin/env python3
"""Real PostgreSQL contract for the model registry's warm initialization read."""
from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg.pq import TransactionStatus
from local_inspection_service.model_profiles.dependencies import ProfileDependencies
from local_inspection_service.model_profiles.repository import Repository
from local_inspection_service.model_profiles.service import Service
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl


def main():
    dsn = os.environ['VANTALINE_POSTGRES_DSN']
    schemas = []
    connections = []
    secret_writes = []

    def schema():
        name = 'profile_init_' + uuid.uuid4().hex
        with psycopg.connect(dsn) as conn:
            conn.execute(postgres_ddl(name))
        schemas.append(name)
        return name

    def make(name, sources=lambda: []):
        conn = psycopg.connect(dsn)
        conn.execute("SET lock_timeout = '6000ms'")
        conn.execute("SET statement_timeout = '8000ms'")
        conn.commit()
        connections.append(conn)
        runtime = PostgresRuntimeRepository(conn, 'test', name)
        deps = ProfileDependencies(runtime_repository=lambda: runtime,
            write_secret=lambda ref, key: secret_writes.append((ref, key)),
            read_secret=lambda ref: '', legacy_sources=sources,
            validate_model=lambda model: None, validate_base_url=lambda url: None,
            mask_secret=lambda key: '****')
        return Service(deps), Repository(runtime), runtime

    def wait_for_advisory(pid):
        with psycopg.connect(dsn) as monitor:
            for _ in range(100):
                state = monitor.execute('SELECT wait_event_type, wait_event FROM pg_stat_activity WHERE pid=%s',
                    (pid,)).fetchone()
                monitor.commit()
                if state == ('Lock', 'advisory'):
                    return
                time.sleep(0.05)
        raise AssertionError('expected the cold initializer to wait on the original advisory lock')

    try:
        warm_schema = schema()
        source_calls = []
        def warm_sources():
            source_calls.append(1)
            return []
        warm_service, warm_repo, _ = make(warm_schema, warm_sources)
        warm_service.initialize()
        assert source_calls == [1] and not secret_writes
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with warm_repo.transaction() as cursor:
                cursor.execute('SELECT 1')
                reader_service, _, reader_runtime = make(warm_schema, warm_sources)
                future = pool.submit(reader_service.initialize)
                assert future.result(timeout=3) is None
                assert reader_runtime.connection.info.transaction_status == TransactionStatus.IDLE
        assert source_calls == [1] and not secret_writes

        cold_schema = schema()
        entered = threading.Event()
        release = threading.Event()
        first_calls = []
        second_calls = []
        legacy = dict(provider='qwen', model='qwen3-vl-flash', api_key='synthetic-key',
            base_url='https://example.invalid/v1', enabled=True)

        def first_sources():
            first_calls.append(1)
            entered.set()
            assert release.wait(12), 'first cold initializer did not resume'
            return [('legacy', legacy, ['label'])]

        def second_sources():
            second_calls.append(1)
            return [('legacy', legacy, ['label'])]

        first_service, first_repo, _ = make(cold_schema, first_sources)
        second_service, second_repo, second_runtime = make(cold_schema, second_sources)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(first_service.initialize)
            try:
                assert entered.wait(3), 'first initializer did not enter migration'
                second = pool.submit(second_service.initialize)
                wait_for_advisory(second_runtime.connection.info.backend_pid)
                assert not second.done()
            finally:
                release.set()
            assert first.result(timeout=8) is None
            assert second.result(timeout=8) is None
        assert first_calls == [1] and second_calls == []
        assert len(secret_writes) == 1
        with first_repo.read_tx() as cursor:
            state = first_repo.state(cursor)
            rows = cursor.execute(f'SELECT kind,count(*) FROM {first_repo.table} GROUP BY kind').fetchall()
        assert state['bindings']['label'] in state['heads']
        assert dict(rows) == {'state': 1, 'profile': 1, 'audit': 1}
        assert second_repo.runtime.connection.info.transaction_status == TransactionStatus.IDLE

        failure_schema = schema()
        failed_service, failed_repo, failed_runtime = make(failure_schema,
            lambda: [('legacy', legacy, ['label'])])
        original_put = Repository.put
        marker = RuntimeError('synthetic migration failure after external secret write')

        def fail_profile(self, cursor, identity, kind, value, **kwargs):
            result = original_put(self, cursor, identity, kind, value, **kwargs)
            if self.runtime is failed_runtime and kind == 'profile':
                assert failed_runtime.connection.info.transaction_status == TransactionStatus.INTRANS
                raise marker
            return result

        with patch.object(Repository, 'put', fail_profile):
            try:
                failed_service.initialize()
            except RuntimeError as exc:
                assert exc is marker
            else:
                raise AssertionError('migration failure was swallowed')
        assert failed_runtime.connection.info.transaction_status == TransactionStatus.IDLE
        with failed_repo.read_tx() as cursor:
            assert failed_repo.state(cursor) is None
            assert cursor.execute(f'SELECT count(*) FROM {failed_repo.table}').fetchone()[0] == 0
        assert len(secret_writes) == 2  # External secret writing predates the failed DB insert.
        recovery_service, recovery_repo, _ = make(failure_schema,
            lambda: [('legacy', legacy, ['label'])])
        recovery_service.initialize()
        with recovery_repo.read_tx() as cursor:
            assert recovery_repo.state(cursor)['bindings']['label']
            assert cursor.execute(f"SELECT count(*) FROM {recovery_repo.table} WHERE kind='audit'").fetchone()[0] == 1
        assert len(secret_writes) == 3

        error_service, _, error_runtime = make(warm_schema)
        original_cursor = PostgresRuntimeRepository._cursor
        original_decode = PostgresRuntimeRepository._row_to_dict
        opened = []
        decode_marker = RuntimeError('synthetic state decode failure')

        def track_cursor(self):
            cursor = original_cursor(self)
            if self is error_runtime:
                opened.append(cursor)
            return cursor

        def fail_decode(self, cursor, row):
            if self is error_runtime:
                assert error_runtime.connection.info.transaction_status == TransactionStatus.INTRANS
                raise decode_marker
            return original_decode(self, cursor, row)

        with patch.object(PostgresRuntimeRepository, '_cursor', track_cursor):
            with patch.object(PostgresRuntimeRepository, '_row_to_dict', fail_decode):
                try:
                    error_service.initialize()
                except RuntimeError as exc:
                    assert exc is decode_marker
                else:
                    raise AssertionError('state read failure was swallowed')
            assert opened[-1].closed
            assert error_runtime.connection.info.transaction_status == TransactionStatus.IDLE
            error_service.initialize()
            assert opened[-1].closed
            assert error_runtime.connection.info.transaction_status == TransactionStatus.IDLE

        false_schema = schema()
        false_service, false_repo, false_runtime = make(false_schema)
        with false_repo.transaction() as cursor:
            false_repo.put(cursor, 'state', 'state', {})
        try:
            false_service.initialize()
        except psycopg.errors.UniqueViolation:
            pass
        else:
            raise AssertionError('falsey state bypassed the original cold migration')
        assert false_runtime.connection.info.transaction_status == TransactionStatus.IDLE
        with false_repo.read_tx() as cursor:
            assert false_repo.state(cursor) == {}
        print('PASS model init read: warm no fence, cold advisory recheck, one migration, rollback/retry, falsey/error cleanup')
    finally:
        for conn in connections:
            conn.close()
        for name in schemas:
            with psycopg.connect(dsn) as cleanup:
                cleanup.execute(f'DROP SCHEMA "{name}" CASCADE')


if __name__ == '__main__':
    main()
