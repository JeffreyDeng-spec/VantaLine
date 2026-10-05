"""Repository selection/probe errors and connection ownership with fake stores."""
import ast
import hashlib
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock
from fastapi import HTTPException
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.storage.runtime_selector import RuntimeStoreConfigError, RuntimeStoreConnectionError
BASELINE = os.environ.get('VANTALINE_REPOSITORY_ACCESS_BASELINE_SOURCE')
NAMES = {'runtime_repository_selection', 'runtime_postgres_repository_or_none',
         'runtime_repository_connection_probe_id', 'runtime_store_probe_payload'}


def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body
                 if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 4
        ns = dict(bindings, Any=Any, HTTPException=HTTPException, os=os, threading=threading,
                  hashlib=hashlib, RuntimeStoreConfigError=RuntimeStoreConfigError,
                  RuntimeStoreConnectionError=RuntimeStoreConnectionError)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), ns)
        return SimpleNamespace(**{n: ns[n] for n in NAMES}), ns
    from local_inspection_service.runtime.repository_access import RuntimeRepositoryAccess, runtime_repository_connection_probe_id
    service = RuntimeRepositoryAccess(factory=lambda: bindings['_runtime_repositories'],
        selection=lambda: bindings['runtime_repository_selection'],
        probe_id=lambda: bindings['runtime_repository_connection_probe_id'],
        postgres_store=lambda: bindings['POSTGRES_STORE'])
    bindings.update(runtime_repository_selection=service.runtime_repository_selection,
                    runtime_repository_connection_probe_id=runtime_repository_connection_probe_id)
    return SimpleNamespace(**{n: getattr(service, n) for n in NAMES if n != 'runtime_repository_connection_probe_id'},
                           runtime_repository_connection_probe_id=runtime_repository_connection_probe_id), bindings


class Contracts(unittest.TestCase):
    def setUp(self):
        self.connection = object()
        self.repository = SimpleNamespace(kind='postgres', connection=self.connection, count_rows=Mock(return_value={'schema_migrations': 4}))
        self.selection = SimpleNamespace(store='postgres', repository=self.repository)
        self.factory = SimpleNamespace(selection=Mock(return_value=self.selection))
        self.service, self.bindings = create({'_runtime_repositories': self.factory, 'POSTGRES_STORE': 'postgres'})

    def test_selection_and_postgres_return_same_objects_without_close(self):
        self.assertIs(self.service.runtime_repository_selection(), self.selection)
        self.assertIs(self.service.runtime_postgres_repository_or_none(), self.repository)
        self.assertEqual(self.factory.selection.call_count, 2)

    def test_json_and_other_store_return_none(self):
        for store in ('json', 'other'):
            self.selection.store = store
            self.assertIsNone(self.service.runtime_postgres_repository_or_none())

    def test_selector_errors_have_existing_status_detail_and_suppressed_cause(self):
        for error, code in [(RuntimeStoreConfigError('config'), 'runtime_store_config_error'),
                            (RuntimeStoreConnectionError('connect'), 'runtime_store_connection_error')]:
            self.factory.selection.side_effect = error
            with self.assertRaises(HTTPException) as caught: self.service.runtime_repository_selection()
            self.assertEqual(caught.exception.status_code, 503)
            self.assertEqual(caught.exception.detail, {'code': code, 'message': str(error), 'json_fallback_used': False})
            self.assertTrue(caught.exception.__suppress_context__)
        unexpected = ValueError('unexpected'); self.factory.selection.side_effect = unexpected
        with self.assertRaises(ValueError) as caught: self.service.runtime_repository_selection()
        self.assertIs(caught.exception, unexpected)

    def test_probe_json_does_not_query_or_fingerprint(self):
        self.selection.store = 'json'; self.repository.kind = 'json'
        self.bindings['runtime_repository_connection_probe_id'] = Mock(side_effect=AssertionError('probe'))
        self.assertEqual(self.service.runtime_store_probe_payload(), {'store': 'json', 'repository_kind': 'json',
            'json_fallback_used': False, 'repository_connection_id': None, 'repository_connection_scope': None,
            'postgres_count_probe': None})
        self.repository.count_rows.assert_not_called()

    def test_probe_postgres_count_then_fingerprint(self):
        events = []
        self.repository.count_rows.side_effect = lambda tables: events.append(('count', tables)) or {'schema_migrations': 3}
        self.bindings['runtime_repository_connection_probe_id'] = lambda repo: events.append(('id', repo)) or 'fixture'
        result = self.service.runtime_store_probe_payload()
        self.assertEqual(result['postgres_count_probe'], {'schema_migrations': 3})
        self.assertEqual(result['repository_connection_scope'], 'thread-local')
        self.assertEqual(result['repository_connection_id'], 'fixture')
        self.assertEqual(events, [('count', ('schema_migrations',)), ('id', self.repository)])
        self.repository.count_rows.side_effect = None; self.repository.count_rows.return_value = {}
        self.assertEqual(self.service.runtime_store_probe_payload()['postgres_count_probe'], {'schema_migrations': 0})

    def test_probe_redacts_query_failure_but_not_unrelated_errors(self):
        error = RuntimeError('private connection material')
        self.repository.count_rows.side_effect = error
        with self.assertRaises(HTTPException) as caught: self.service.runtime_store_probe_payload()
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, {'code': 'runtime_store_probe_error', 'message': 'RuntimeError', 'json_fallback_used': False})
        self.repository.count_rows.side_effect = None; self.repository.count_rows.return_value = None
        with self.assertRaises(AttributeError): self.service.runtime_store_probe_payload()
        self.repository.count_rows.return_value = {}
        self.bindings['runtime_repository_connection_probe_id'] = Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught: self.service.runtime_store_probe_payload()
        self.assertIs(caught.exception, error)

    def test_selection_and_fingerprint_suppliers_are_live(self):
        replacement = SimpleNamespace(store='json', repository=SimpleNamespace(kind='replacement'))
        self.bindings['runtime_repository_selection'] = lambda: replacement
        self.assertEqual(self.service.runtime_store_probe_payload()['repository_kind'], 'replacement')
        self.bindings['_runtime_repositories'] = SimpleNamespace(selection=lambda: replacement)
        self.assertIs(self.service.runtime_repository_selection(), replacement)

    def test_fingerprint_exact_material_and_absent_connection(self):
        material = f'{os.getpid()}:{threading.get_ident()}:{id(self.connection)}'
        self.assertEqual(self.service.runtime_repository_connection_probe_id(self.repository), hashlib.sha256(material.encode()).hexdigest()[:16])
        self.assertEqual(self.service.runtime_repository_connection_probe_id(SimpleNamespace()), '')
        self.assertEqual(self.service.runtime_repository_connection_probe_id(SimpleNamespace(connection=None)), '')

    def test_shared_service_uses_factory_thread_scope_without_owning_connection(self):
        from concurrent.futures import ThreadPoolExecutor
        from local_inspection_service.runtime.connections import ThreadRepositoryFactory
        connections = []
        barrier = threading.Barrier(2, timeout=5)
        def build():
            connection = SimpleNamespace(closed=False, owner=threading.get_ident())
            def close():
                self.assertEqual(connection.owner, threading.get_ident())
                connection.closed = True
            connection.close = close; connections.append(connection)
            return SimpleNamespace(store='postgres', repository=SimpleNamespace(kind='postgres', connection=connection))
        factory = ThreadRepositoryFactory(build, lambda: 'fixture')
        self.bindings['_runtime_repositories'] = factory
        def worker():
            with factory.thread_scope():
                repository = self.service.runtime_postgres_repository_or_none()
                barrier.wait()
                self.assertIs(self.service.runtime_postgres_repository_or_none(), repository)
                self.assertFalse(repository.connection.closed)
                return repository.connection.owner
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(worker), pool.submit(worker)
            self.assertNotEqual(first.result(timeout=10), second.result(timeout=10))
        self.assertEqual(len(connections), 2)
        self.assertTrue(all(c.closed for c in connections))

    def test_selection_failure_precedes_probe_projection(self):
        sentinel = ValueError('selection')
        self.bindings['runtime_repository_selection'] = Mock(side_effect=sentinel)
        with self.assertRaises(ValueError) as caught: self.service.runtime_store_probe_payload()
        self.assertIs(caught.exception, sentinel); self.repository.count_rows.assert_not_called()


if __name__ == '__main__': unittest.main()
