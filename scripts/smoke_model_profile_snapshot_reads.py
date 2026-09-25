#!/usr/bin/env python3
"""Real PostgreSQL contract for model-profile task snapshot reads."""
from __future__ import annotations

import concurrent.futures
import copy
import os
from pathlib import Path
import sys
import threading
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
    schema = 'profile_snapshots_' + uuid.uuid4().hex
    connections = []
    secret_reads = []
    secret_writes = []
    source = dict(provider='qwen', model='qwen3-vl-flash', api_key='legacy-secret',
        base_url='https://example.invalid/v1', enabled=True)
    with psycopg.connect(dsn) as setup:
        setup.execute(postgres_ddl(schema))

    def make():
        conn = psycopg.connect(dsn)
        conn.execute("SET lock_timeout = '6000ms'")
        conn.execute("SET statement_timeout = '8000ms'")
        conn.commit()
        connections.append(conn)
        runtime = PostgresRuntimeRepository(conn, 'test', schema)
        deps = ProfileDependencies(runtime_repository=lambda: runtime,
            write_secret=lambda ref, value: secret_writes.append((ref, value)),
            read_secret=lambda ref: secret_reads.append(ref) or 'legacy-secret',
            legacy_sources=lambda: [('legacy', source, ['label'])],
            validate_model=lambda value: None, validate_base_url=lambda value: None,
            mask_secret=lambda value: '****')
        return Service(deps), Repository(runtime), runtime

    try:
        writer_service, writer, _ = make()
        old = writer_service.snapshot()
        assert old['label']['version'] == 1 and old['label']['model'] == source['model']
        profile_id = old['label']['id']
        assert len(secret_writes) == 1 and not secret_reads
        reader_service, _, reader_runtime = make()
        assert reader_service.snapshot() == old
        assert reader_service.snapshot_for_record({'created_at': 1}) == old

        # A snapshot sees the committed binding while a writer owns the old
        # advisory lock and has an uncommitted new profile version.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with writer.transaction() as cursor:
                state = copy.deepcopy(writer.state(cursor))
                profile = copy.deepcopy(writer.get(cursor, f'{profile_id}:1'))
                profile.update(version=2, model='qwen3-vl-new')
                writer.put(cursor, f'{profile_id}:2', 'profile', profile)
                state['heads'][profile_id] = 2
                writer.put(cursor, 'state', 'state', state, replace=True)
                read = pool.submit(reader_service.snapshot)
                current_record = pool.submit(reader_service.snapshot_for_record,
                    {'created_at': state['migrated_at'] + 1})
                assert read.result(timeout=3) == old
                assert current_record.result(timeout=3) == old
        updated = reader_service.snapshot()
        assert updated['label']['version'] == 2
        assert updated['label']['model'] == 'qwen3-vl-new'
        assert reader_service.snapshot_for_record({'created_at': state['migrated_at'] + 1}) == updated
        historical = reader_service.snapshot_for_record({'created_at': 1})
        assert historical == old
        historical['label']['model'] = 'local mutation'
        assert reader_service.snapshot_for_record({'created_at': 1}) == old
        assert reader_service.snapshot_for_record({'created_at': 0}) == updated
        assert reader_service.snapshot_for_record({}) == updated
        assert not secret_reads
        with reader_service.scope(old):
            assert reader_service.current_snapshot() == old
        assert reader_service.current_snapshot() is None
        with reader_service.scope({}):
            assert reader_service.resolve('label')['status'] == 'unconfigured'
        assert not secret_reads

        # Slow row decoding cannot keep the global write fence held.
        decode_service, _, decode_runtime = make()
        entered = threading.Event()
        release = threading.Event()
        original_decode = PostgresRuntimeRepository._row_to_dict

        def pause_decode(self, cursor, row):
            if self is decode_runtime and not entered.is_set():
                entered.set()
                assert release.wait(3), 'snapshot decoder did not resume'
            return original_decode(self, cursor, row)

        with patch.object(decode_service, 'initialize', return_value=None):
            with patch.object(PostgresRuntimeRepository, '_row_to_dict', pause_decode):
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(decode_service.snapshot)
                    try:
                        assert entered.wait(3), 'snapshot did not decode a row'
                        with writer.transaction() as cursor:
                            cursor.execute('SELECT 1')
                    finally:
                        release.set()
                    assert future.result(timeout=3) == updated

        # The state/head pair is captured before profile lookup. A concurrent
        # committed head rotation must not mix the old state with a new profile.
        staged_service, staged_repo, staged_runtime = make()
        original_state = Repository.state
        state_read = threading.Event()
        continue_read = threading.Event()
        def pause_after_state(self, cursor):
            result = original_state(self, cursor)
            if self.runtime is staged_runtime and not state_read.is_set():
                state_read.set()
                assert continue_read.wait(3), 'state reader did not resume'
            return result
        with patch.object(staged_service, 'initialize', return_value=None):
            with patch.object(Repository, 'state', pause_after_state):
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(staged_service.snapshot)
                    try:
                        assert state_read.wait(3), 'snapshot did not read state'
                        with writer.transaction() as cursor:
                            next_state = copy.deepcopy(writer.state(cursor))
                            next_profile = copy.deepcopy(writer.get(cursor, f'{profile_id}:2'))
                            next_profile.update(version=3, model='qwen3-vl-third')
                            writer.put(cursor, f'{profile_id}:3', 'profile', next_profile)
                            next_state['heads'][profile_id] = 3
                            writer.put(cursor, 'state', 'state', next_state, replace=True)
                    finally:
                        continue_read.set()
                    assert future.result(timeout=3) == updated
        newest = reader_service.snapshot()
        assert newest['label']['version'] == 3

        # The nonhistorical path closes its first cursor before snapshot().
        # A binding committed in between is visible to the second read.
        fallback_service, _, fallback_runtime = make()
        original_snapshot = fallback_service.snapshot
        original_cursor = PostgresRuntimeRepository._cursor
        opened = []
        def track_fallback_cursor(self):
            cursor = original_cursor(self)
            if self is fallback_runtime:
                opened.append(cursor)
            return cursor
        def after_first_read():
            assert len(opened) == 1 and opened[0].closed
            assert fallback_runtime.connection.info.transaction_status == TransactionStatus.IDLE
            with writer.transaction() as cursor:
                bound_state = copy.deepcopy(writer.state(cursor))
                other = copy.deepcopy(writer.get(cursor, f'{profile_id}:3'))
                other.update(id='mp_other', version=1, name='other binding')
                writer.put(cursor, 'mp_other:1', 'profile', other)
                bound_state['heads']['mp_other'] = 1
                bound_state['bindings']['label'] = 'mp_other'
                writer.put(cursor, 'state', 'state', bound_state, replace=True)
            return original_snapshot()
        with patch.object(fallback_service, 'initialize', return_value=None):
            with patch.object(PostgresRuntimeRepository, '_cursor', track_fallback_cursor):
                with patch.object(fallback_service, 'snapshot', after_first_read):
                    rebound = fallback_service.snapshot_for_record({})
        assert len(opened) == 2 and all(cursor.closed for cursor in opened)
        latest = reader_service.snapshot()
        assert latest['label']['id'] == 'mp_other' and rebound == latest
        assert fallback_service.snapshot_for_record({'created_at': str(next_state['migrated_at'])}) == latest
        assert fallback_service.snapshot_for_record({'created_at': '0'}) == old
        try:
            fallback_service.snapshot_for_record({'created_at': 'bad time'})
        except ValueError:
            pass
        else:
            raise AssertionError('invalid task timestamp was silently changed')
        assert fallback_runtime.connection.info.transaction_status == TransactionStatus.IDLE

        # Exceptions in either snapshot reader roll back and close their
        # cursors; the same connection can serve the next request.
        original_cursor = PostgresRuntimeRepository._cursor
        for method in ('snapshot', 'snapshot_for_record'):
            service, _, runtime = make()
            opened = []
            marker = RuntimeError(method + ' synthetic decode failure')
            decoded = []

            def track_cursor(self):
                cursor = original_cursor(self)
                if self is runtime:
                    opened.append(cursor)
                return cursor

            def fail_decode(self, cursor, row):
                if self is runtime:
                    decoded.append(1)
                    if len(decoded) == (2 if method == 'snapshot' else 1):
                        assert runtime.connection.info.transaction_status == TransactionStatus.INTRANS
                        raise marker
                return original_decode(self, cursor, row)

            with patch.object(service, 'initialize', return_value=None):
                with patch.object(PostgresRuntimeRepository, '_cursor', track_cursor):
                    with patch.object(PostgresRuntimeRepository, '_row_to_dict', fail_decode):
                        try:
                            service.snapshot() if method == 'snapshot' else service.snapshot_for_record({'created_at': 1})
                        except RuntimeError as exc:
                            assert exc is marker
                        else:
                            raise AssertionError(method + ' swallowed decode failure')
                    assert len(opened) == 1 and opened[-1].closed
                    assert runtime.connection.info.transaction_status == TransactionStatus.IDLE
                    assert (service.snapshot() if method == 'snapshot' else service.snapshot_for_record({'created_at': 1})) == (latest if method == 'snapshot' else old)
                    assert opened[-1].closed
                    assert runtime.connection.info.transaction_status == TransactionStatus.IDLE
        print('PASS model snapshots: committed bindings, old tasks, scope, no read fence, rollback/IDLE')
    finally:
        for conn in connections:
            conn.close()
        with psycopg.connect(dsn) as cleanup:
            cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')


if __name__ == '__main__':
    main()
