#!/usr/bin/env python3
"""Real PostgreSQL contract for the model-profile admin display read."""
from __future__ import annotations

import concurrent.futures
import copy
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
from local_inspection_service.model_profiles.dependencies import ProfileDependencies
from local_inspection_service.model_profiles.repository import Repository
from local_inspection_service.model_profiles.service import Service, PURPOSES, DEFAULTS
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl


def main():
    dsn = os.environ['VANTALINE_POSTGRES_DSN']
    schema = 'profile_public_' + uuid.uuid4().hex
    connections = []
    secret_reads = []
    with psycopg.connect(dsn) as setup:
        setup.execute(postgres_ddl(schema))

    def make():
        conn = psycopg.connect(dsn)
        conn.execute("SET lock_timeout = '6000ms'")
        conn.execute("SET statement_timeout = '8000ms'")
        conn.commit()
        connections.append(conn)
        runtime = PostgresRuntimeRepository(conn, 'test', schema)
        sources = [
            ('alpha', dict(provider='qwen', model='qwen3-vl-flash', api_key='hidden-alpha',
                base_url='https://example.invalid/v1', enabled=True), ['label']),
            ('beta', dict(provider='gemini', model='gemini-2.5-flash', api_key='hidden-beta',
                base_url='https://example.invalid/v2', enabled=True), ['pipeline']),
        ]
        deps = ProfileDependencies(runtime_repository=lambda: runtime,
            write_secret=lambda ref, value: None,
            read_secret=lambda ref: secret_reads.append(ref) or 'unexpected',
            legacy_sources=lambda: sources, validate_model=lambda value: None,
            validate_base_url=lambda value: None, mask_secret=lambda value: '****')
        return Service(deps), Repository(runtime), runtime

    try:
        writer_service, writer, _ = make()
        initial = writer_service.public()
        assert initial['revision'] == 1
        assert {p['name'] for p in initial['profiles']} == {'alpha', 'beta'}
        order_ids = [p['id'] for p in initial['profiles']]
        assert set(initial['bindings']) == set(PURPOSES)
        assert [p['id'] for p in initial['providers']] == list(DEFAULTS)
        alpha = next(p for p in initial['profiles'] if p['name'] == 'alpha')
        beta = next(p for p in initial['profiles'] if p['name'] == 'beta')
        assert alpha['used_by'] == ['label'] and beta['used_by'] == ['pipeline']
        assert all(p['connection_status'] == 'not_tested' for p in initial['profiles'])
        assert 'hidden-alpha' not in json.dumps(initial)
        assert 'hidden-beta' not in json.dumps(initial)
        assert 'secret_ref' not in json.dumps(initial)
        assert not secret_reads
        with writer.transaction() as cursor:
            writer.put(cursor, f"test:{alpha['id']}:1", 'test', {'ok': False, 'at': 1})
        baseline = writer_service.public()
        assert [p['id'] for p in baseline['profiles']] == order_ids
        baseline_by_id = {p['id']: p for p in baseline['profiles']}
        assert baseline_by_id[alpha['id']]['connection_status'] == 'failed'
        assert baseline_by_id[beta['id']]['connection_status'] == 'not_tested'
        reader_service, _, reader_runtime = make()
        assert reader_service.public() == baseline

        # State, immutable versions, and test rows remain on the committed
        # view while a writer holds the advisory lock with pending changes.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with writer.transaction() as cursor:
                state = copy.deepcopy(writer.state(cursor))
                profile = copy.deepcopy(writer.get(cursor, f"{alpha['id']}:1"))
                profile.update(version=2, name='alpha rotated', secret_ref='still-hidden')
                writer.put(cursor, f"{alpha['id']}:2", 'profile', profile)
                writer.put(cursor, f"test:{alpha['id']}:2", 'test', {'ok': True, 'at': 2})
                state['heads'][alpha['id']] = 2
                state['revision'] += 1
                writer.put(cursor, 'state', 'state', state, replace=True)
                future = pool.submit(reader_service.public)
                assert future.result(timeout=3) == baseline
        updated = reader_service.public()
        assert updated['revision'] == 2
        assert [p['id'] for p in updated['profiles']] == order_ids
        updated_by_id = {p['id']: p for p in updated['profiles']}
        assert (updated_by_id[alpha['id']]['name'], updated_by_id[alpha['id']]['version'],
            updated_by_id[alpha['id']]['connection_status']) == ('alpha rotated', 2, 'connected')
        assert (updated_by_id[beta['id']]['name'], updated_by_id[beta['id']]['version'],
            updated_by_id[beta['id']]['connection_status']) == ('beta', 1, 'not_tested')
        assert updated_by_id[alpha['id']]['used_by'] == ['label']
        assert updated['bindings'] == baseline['bindings']
        assert 'secret_ref' not in json.dumps(updated) and 'still-hidden' not in json.dumps(updated)
        assert not secret_reads

        # A slow state-row decoder cannot hold the global write fence.
        decode_service, _, decode_runtime = make()
        entered = threading.Event()
        release = threading.Event()
        original_decode = PostgresRuntimeRepository._row_to_dict
        def pause_decode(self, cursor, row):
            if self is decode_runtime and not entered.is_set():
                entered.set()
                assert release.wait(3), 'admin decoder did not resume'
            return original_decode(self, cursor, row)
        with patch.object(decode_service, 'initialize', return_value=None):
            with patch.object(PostgresRuntimeRepository, '_row_to_dict', pause_decode):
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(decode_service.public)
                    try:
                        assert entered.wait(3), 'admin read did not decode a row'
                        with writer.transaction() as cursor:
                            cursor.execute('SELECT 1')
                    finally:
                        release.set()
                    assert future.result(timeout=3) == updated

        # A state, profile, or mutable test-row decode error is raised as-is,
        # rolls back, closes the cursor, and leaves the connection reusable.
        original_cursor = PostgresRuntimeRepository._cursor
        for fail_on in (1, 2, 4):
            service, _, runtime = make()
            opened = []
            decoded = []
            queried = []
            marker = RuntimeError(f'admin decode {fail_on}')
            original_get = Repository.get
            def track_get(self, cursor, identity):
                if self.runtime is runtime:
                    queried.append(identity)
                return original_get(self, cursor, identity)
            def track_cursor(self):
                cursor = original_cursor(self)
                if self is runtime:
                    opened.append(cursor)
                return cursor
            def fail_decode(self, cursor, row):
                if self is runtime:
                    decoded.append(1)
                    if len(decoded) == fail_on:
                        assert runtime.connection.info.transaction_status == TransactionStatus.INTRANS
                        raise marker
                return original_decode(self, cursor, row)
            with patch.object(service, 'initialize', return_value=None):
                with patch.object(PostgresRuntimeRepository, '_cursor', track_cursor):
                    with patch.object(Repository, 'get', track_get):
                        with patch.object(PostgresRuntimeRepository, '_row_to_dict', fail_decode):
                            try:
                                service.public()
                            except RuntimeError as exc:
                                assert exc is marker
                            else:
                                raise AssertionError('admin decode failure was swallowed')
                    if fail_on == 4:
                        assert queried[-1] == f"test:{alpha['id']}:2"
                    assert len(opened) == 1 and opened[0].closed
                    assert runtime.connection.info.transaction_status == TransactionStatus.IDLE
                    assert service.public() == updated
                    assert opened[-1].closed
                    assert runtime.connection.info.transaction_status == TransactionStatus.IDLE
        # Versions are materialized before any profile projection or mutable
        # test lookup. A later version decode error takes precedence over a
        # missing field in an earlier version's display projection.
        priority_service, _, priority_runtime = make()
        original_get = Repository.get
        marker = RuntimeError('later version decode failed')
        versions = {alpha['id']: 2, beta['id']: 1}
        first_version = f"{order_ids[0]}:{versions[order_ids[0]]}"
        second_version = f"{order_ids[1]}:{versions[order_ids[1]]}"
        queried = []
        def priority_get(self, cursor, identity):
            if self.runtime is priority_runtime:
                queried.append(identity)
                if identity == first_version:
                    p = copy.deepcopy(original_get(self, cursor, identity))
                    p.pop('name')
                    return p
                if identity == second_version:
                    raise marker
            return original_get(self, cursor, identity)
        with patch.object(priority_service, 'initialize', return_value=None):
            with patch.object(Repository, 'get', priority_get):
                try:
                    priority_service.public()
                except RuntimeError as exc:
                    assert exc is marker
                else:
                    raise AssertionError('version read order changed')
        assert queried == ['state', first_version, second_version]
        assert priority_runtime.connection.info.transaction_status == TransactionStatus.IDLE

        # State is captured first. A subsequent head/binding commit cannot
        # change the versions or used_by projection in this in-flight call.
        mid_service, _, mid_runtime = make()
        original_state = Repository.state
        state_read = threading.Event()
        continue_read = threading.Event()
        def pause_after_state(self, cursor):
            result = original_state(self, cursor)
            if self.runtime is mid_runtime and not state_read.is_set():
                state_read.set()
                assert continue_read.wait(3), 'admin state reader did not resume'
            return result
        with patch.object(mid_service, 'initialize', return_value=None):
            with patch.object(Repository, 'state', pause_after_state):
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(mid_service.public)
                    try:
                        assert state_read.wait(3), 'admin display did not read state'
                        with writer.transaction() as cursor:
                            next_state = copy.deepcopy(writer.state(cursor))
                            next_profile = copy.deepcopy(writer.get(cursor, f"{alpha['id']}:2"))
                            next_profile.update(version=3, name='alpha third')
                            writer.put(cursor, f"{alpha['id']}:3", 'profile', next_profile)
                            next_state['heads'][alpha['id']] = 3
                            next_state['bindings']['label'] = beta['id']
                            next_state['revision'] += 1
                            writer.put(cursor, 'state', 'state', next_state, replace=True)
                    finally:
                        continue_read.set()
                    assert future.result(timeout=3) == updated
        latest = reader_service.public()
        assert latest['revision'] == 3
        assert [p['id'] for p in latest['profiles']] == order_ids
        latest_by_id = {p['id']: p for p in latest['profiles']}
        assert latest_by_id[alpha['id']]['name'] == 'alpha third'
        assert latest_by_id[beta['id']]['name'] == 'beta'
        assert latest_by_id[alpha['id']]['used_by'] == []
        assert latest_by_id[beta['id']]['used_by'] == [k for k, v in latest['bindings'].items() if v == beta['id']]
        assert latest_by_id[alpha['id']]['connection_status'] == 'not_tested'
        # Connection-test rows are mutable. A commit after the first test
        # SELECT may be visible to the second SELECT, while each key stays
        # bound to the profile version captured from the state row.
        version_by_id = {alpha['id']: 3, beta['id']: 1}
        first_test = f"test:{order_ids[0]}:{version_by_id[order_ids[0]]}"
        second_test = f"test:{order_ids[1]}:{version_by_id[order_ids[1]]}"
        with writer.transaction() as cursor:
            writer.put(cursor, first_test, 'test', {'ok': False, 'at': 10}, replace=True)
            writer.put(cursor, second_test, 'test', {'ok': False, 'at': 10}, replace=True)
        mixed_service, _, mixed_runtime = make()
        test_selected = threading.Event()
        continue_test = threading.Event()
        test_queries = []
        original_get = Repository.get
        def pause_after_first_test(self, cursor, identity):
            value = original_get(self, cursor, identity)
            if self.runtime is mixed_runtime and identity.startswith('test:'):
                test_queries.append(identity)
                if identity == first_test and not test_selected.is_set():
                    test_selected.set()
                    assert continue_test.wait(3), 'test-row reader did not resume'
            return value
        with patch.object(mixed_service, 'initialize', return_value=None):
            with patch.object(Repository, 'get', pause_after_first_test):
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(mixed_service.public)
                    try:
                        assert test_selected.wait(3), 'first test row not selected'
                        with writer.transaction() as cursor:
                            writer.put(cursor, first_test, 'test', {'ok': True, 'at': 11}, replace=True)
                            writer.put(cursor, second_test, 'test', {'ok': True, 'at': 11}, replace=True)
                    finally:
                        continue_test.set()
                    mixed = future.result(timeout=3)
        assert test_queries == [first_test, second_test]
        mixed_by_id = {p['id']: p for p in mixed['profiles']}
        assert mixed_by_id[order_ids[0]]['connection_status'] == 'failed'
        assert mixed_by_id[order_ids[1]]['connection_status'] == 'connected'
        assert all(p['connection_status'] == 'connected' for p in reader_service.public()['profiles'])
        assert not secret_reads
        print('PASS model public read: committed projection, order/status, no secrets/fence, rollback/IDLE')
    finally:
        for conn in connections:
            conn.close()
        with psycopg.connect(dsn) as cleanup:
            cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')


if __name__ == '__main__':
    main()
