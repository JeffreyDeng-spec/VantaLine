"""Retained coordination contracts; synthetic heartbeats and isolated PostgreSQL only."""
import ast
from concurrent.futures import ThreadPoolExecutor
import copy
import os
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace
from typing import Any, Callable
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE = os.environ.get('VANTALINE_PLC_COORDINATION_BASELINE_SOURCE')
NAMES = {'mutate_plc_runtime_coordination', 'plc_completed_capture_receipt',
         '_mutate_plc_runtime_rows', 'plc_claim_or_renew_io_owner', 'plc_current_process_owns_io'}


def build():
    source = Path(BASELINE) if BASELINE else ROOT / 'local_inspection_service/server.py'
    nodes = []
    text = read_checked_application_source(source, encoding='utf-8-sig')
    if not BASELINE:
        from application_integration_source_contract import restore_plc_domain_root
        text = restore_plc_domain_root(text)
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.ImportFrom) and node.module == 'plc.legacy_coordination':
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in NAMES | {'_legacy_plc_coordination'} for t in node.targets
        ):
            nodes.append(node)
    target = ModuleType('local_inspection_service._coordination_contract')
    target.__package__ = 'local_inspection_service'
    target.__dict__.update(Any=Any, Callable=Callable, copy=copy)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), target.__dict__)
    return target


class CoordinationContract(unittest.TestCase):
    def setUp(self):
        self.api = build()
        self.config = {'outside': {'kept': True}}
        self.api.runtime_postgres_repository_or_none = lambda: None
        self.api.load_config = lambda: self.config
        self.api.PLC_RUNTIME_COORDINATION_KEY = 'runtime'
        self.api.PLC_CAPTURE_RESULTS_KEY = 'receipts'
        self.api._plc_process_owner_id = 'process-a'
        self.api.PLC_IO_OWNER_LEASE_SECONDS = 10
        self.api.PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS = 5
        self.api.time = SimpleNamespace(time=lambda: 100.5)
        self.api.plc_start_owner_heartbeat = Mock()
        def mutate(callback):
            working = copy.deepcopy(self.config)
            callback(working)
            self.config.clear()
            self.config.update(working)
            return working
        self.api.mutate_app_config_atomically = mutate

    def test_json_state_copy_namespace_and_failed_mutator(self):
        original = {'nested': {'value': 1}}
        self.config['runtime'] = original
        result = self.api.mutate_plc_runtime_coordination(lambda state: state['nested'].__setitem__('value', 2))
        self.assertEqual(original, {'nested': {'value': 1}})
        result['nested']['value'] = 99
        self.assertEqual(self.config['runtime']['nested']['value'], 2)
        self.assertEqual(self.config['outside'], {'kept': True})
        error = RuntimeError('mutator failed')
        before = copy.deepcopy(self.config)
        def fail(state):
            state['nested']['value'] = 88
            raise error
        with self.assertRaises(RuntimeError) as caught:
            self.api.mutate_plc_runtime_coordination(fail)
        self.assertIs(caught.exception, error)
        self.assertEqual(self.config, before)
        self.config['runtime'] = []
        self.assertEqual(self.api.mutate_plc_runtime_coordination(lambda state: state.update(count=1)), {'count': 1})

    def test_pg_narrow_namespace_falsey_repository_and_deep_copy(self):
        rows = {'runtime': {'nested': {'value': 1}}, 'other': 'untouched'}
        calls = []
        class Repository:
            def __bool__(self):
                raise AssertionError('repository truthiness')
            def mutate_app_config_namespace(self, keys, callback, *, updated_at):
                calls.append((keys, updated_at))
                callback(rows)
                return rows
        self.api.runtime_postgres_repository_or_none = Repository
        self.api.mutate_app_config_atomically = Mock(side_effect=AssertionError('JSON fallback'))
        result = self.api.mutate_plc_runtime_coordination(lambda state: state['nested'].__setitem__('value', 3))
        self.assertEqual(calls, [(('runtime',), 100)])
        self.assertEqual(rows['other'], 'untouched')
        result['nested']['value'] = 4
        self.assertEqual(rows['runtime']['nested']['value'], 3)
        error = RuntimeError('repository failed')
        self.api.runtime_postgres_repository_or_none = Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:
            self.api.mutate_plc_runtime_coordination(lambda _: self.fail('mutator must not run'))
        self.assertIs(caught.exception, error)
        self.api.runtime_postgres_repository_or_none.assert_called_once()

    def test_receipt_shapes_and_deep_copy(self):
        for receipts in (None, [], {'id': None}, {'id': []}):
            self.config['receipts'] = receipts
            self.assertIsNone(self.api.plc_completed_capture_receipt('id'))
        self.config['receipts'] = {'id': {'nested': {'value': 1}}}
        receipt = self.api.plc_completed_capture_receipt('id')
        receipt['nested']['value'] = 2
        self.assertEqual(self.config['receipts']['id']['nested']['value'], 1)

    def test_claim_renewal_takeover_deadlines_and_epoch(self):
        cases = [({}, 1), ({'owner_id': 'process-a', 'epoch': 7, 'expires_at': 999, 'quarantine_until': 999}, 7),
                 ({'owner_id': 'process-a', 'epoch': 0}, 1),
                 ({'owner_id': 'other', 'epoch': 3, 'expires_at': 100.5, 'quarantine_until': 100.5}, 4),
                 ({'owner_id': 'other', 'expires_at': 101}, None),
                 ({'owner_id': 'other', 'expires_at': 0, 'quarantine_until': 101}, None)]
        for owner, expected in cases:
            with self.subTest(owner=owner):
                self.config['runtime'] = {'io_owner': copy.deepcopy(owner), 'kept': 1}
                result = self.api.plc_claim_or_renew_io_owner()
                if expected is None:
                    self.assertIsNone(result)
                    self.assertEqual(self.config['runtime']['io_owner'], owner)
                else:
                    self.assertEqual(result, {'owner_id': 'process-a', 'epoch': expected, 'heartbeat_at': 100.5,
                                             'expires_at': 110.5, 'quarantine_until': 115.5})
                    result['epoch'] = 999
                    self.assertEqual(self.config['runtime']['io_owner']['epoch'], expected)
                self.assertEqual(self.config['runtime']['kept'], 1)
        self.api.plc_start_owner_heartbeat.assert_not_called()
        self.config['runtime'] = {'io_owner': {'owner_id': 'process-a', 'epoch': 'invalid'}}
        before = copy.deepcopy(self.config)
        with self.assertRaises(ValueError):
            self.api.plc_claim_or_renew_io_owner()
        self.assertEqual(self.config, before)

    def test_ownership_short_circuit_exact_expiry_and_epoch(self):
        clock = Mock(return_value=100.5)
        self.api.time.time = clock
        self.assertFalse(self.api.plc_current_process_owns_io())
        clock.assert_not_called()
        self.config['runtime'] = {'io_owner': {'owner_id': 'process-a', 'expires_at': 100.5, 'epoch': 2}}
        self.assertFalse(self.api.plc_current_process_owns_io())
        self.config['runtime']['io_owner']['expires_at'] = 101
        self.assertTrue(self.api.plc_current_process_owns_io())
        self.assertTrue(self.api.plc_current_process_owns_io(2))
        self.assertFalse(self.api.plc_current_process_owns_io(3))
        self.config['runtime']['io_owner']['epoch'] = 'malformed'
        self.assertTrue(self.api.plc_current_process_owns_io())
        with self.assertRaises(ValueError):
            self.api.plc_current_process_owns_io(2)

    def test_commit_then_repository_and_heartbeat_reselection_no_replay(self):
        original = self.api.mutate_plc_runtime_coordination
        heartbeat = Mock(side_effect=RuntimeError('heartbeat start failed'))
        def commit(callback):
            original(callback)
            self.api.runtime_postgres_repository_or_none = lambda: False
            self.api.plc_start_owner_heartbeat = heartbeat
        self.api.mutate_plc_runtime_coordination = Mock(side_effect=commit)
        with self.assertRaisesRegex(RuntimeError, 'heartbeat start failed'):
            self.api.plc_claim_or_renew_io_owner()
        self.api.mutate_plc_runtime_coordination.assert_called_once()
        heartbeat.assert_called_once_with(1)
        self.assertEqual(self.config['runtime']['io_owner']['epoch'], 1)

    @unittest.skipUnless(os.environ.get('VANTALINE_POSTGRES_DSN'), 'isolated PostgreSQL DSN required')
    def test_real_postgres_absent_owner_race_and_mutation_rollback(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.runtime.connections import ThreadRepositoryFactory
        dsn = os.environ['VANTALINE_POSTGRES_DSN']
        schema = 'coordination_' + uuid.uuid4().hex
        connections = []
        def connect():
            connection = psycopg.connect(dsn)
            connections.append(connection)
            return SimpleNamespace(repository=PostgresRuntimeRepository(connection, 'fixture', schema), store='postgres')
        factory = ThreadRepositoryFactory(connect, lambda: schema)
        first = self.api
        self.setUp()
        second = self.api
        second._plc_process_owner_id = 'process-b'
        for api in (first, second):
            api.runtime_postgres_repository_or_none = lambda: factory.selection().repository
        with psycopg.connect(dsn, autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                with factory.thread_scope():
                    factory.selection().repository.mutate_app_config_namespace(('unrelated',), lambda rows: rows.update(unrelated={'kept': 1}), updated_at=1)
                barrier = threading.Barrier(2)
                def claim(api):
                    with factory.thread_scope():
                        barrier.wait(timeout=5)
                        return api.plc_claim_or_renew_io_owner()
                with ThreadPoolExecutor(2) as pool:
                    futures = [pool.submit(claim, api) for api in (first, second)]
                    results = [future.result(timeout=20) for future in futures]
                self.assertEqual(sum(result is not None for result in results), 1)
                self.assertEqual(first.plc_start_owner_heartbeat.call_count + second.plc_start_owner_heartbeat.call_count, 1)
                with factory.thread_scope():
                    repo = factory.selection().repository
                    before = repo.fetch_all('app_config')
                    error = RuntimeError('before write')
                    def fail(state):
                        state['io_owner']['epoch'] = 999
                        raise error
                    with self.assertRaises(RuntimeError) as caught:
                        first.mutate_plc_runtime_coordination(fail)
                    self.assertIs(caught.exception, error)
                    self.assertEqual(repo.fetch_all('app_config'), before)
                    error = RuntimeError('SQL publish failure')
                    with patch.object(PostgresRuntimeRepository, '_upsert_sql_params', side_effect=error):
                        with self.assertRaises(RuntimeError) as caught:
                            first.mutate_plc_runtime_coordination(lambda state: state.update(extra=1))
                    self.assertIs(caught.exception, error)
                    self.assertEqual(repo.fetch_all('app_config'), before)
                    # A subsequent transaction still succeeds after rollback.
                    result = first.mutate_plc_runtime_coordination(lambda state: state.update(extra=2))
                    self.assertEqual(result['extra'], 2)
                    rows = repo.fetch_all('app_config')
                    self.assertEqual(next(row['config_value_json'] for row in rows if row['config_key'] == 'unrelated'), {'kept': 1})
                self.assertTrue(all(connection.closed for connection in connections))
            finally:
                factory.clear()
                control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    @unittest.skipIf(BASELINE, 'candidate owner binding')
    def test_root_binding_no_constructor_io_and_dormant_startup(self):
        for name in NAMES:
            self.assertIs(getattr(self.api, name).__self__, self.api._legacy_plc_coordination)
        self.assertIsNot(build()._legacy_plc_coordination, self.api._legacy_plc_coordination)
        tree = ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py'))
        startup = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'start_plc_runtime_workers')
        self.assertEqual(ast.dump(startup.body[0]), ast.dump(ast.Return(value=ast.Constant(value=None))))
        self.assertEqual(len(startup.body), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
