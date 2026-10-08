"""Text storage ownership through independent HTTP apps and native threads."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from local_inspection_service.runtime.json_records import read_json_list, write_json_list
from local_inspection_service.storage.runtime_records import (
    incoming_text_reference_row, incoming_text_inspection_row, audit_event_row, row_raw_json_list,
)
from local_inspection_service.text_inspection.incoming_store import IncomingPaths, IncomingRows
from local_inspection_service.text_inspection.record_store import TEXT_INSPECTION_TABLES
from local_inspection_service.text_inspection.storage_composition import TextStorage, TextStoragePaths, TextStorageJSON


def build(directory, repository=lambda: None):
    return TextStorage(
        repository=repository,
        paths=TextStoragePaths(lambda: directory/'records', IncomingPaths(
            lambda: directory/'references.json', lambda: directory/'inspections.json', lambda: directory/'audit.json')),
        rows=IncomingRows(incoming_text_reference_row, incoming_text_inspection_row, audit_event_row, lambda: row_raw_json_list),
        json_io=TextStorageJSON(lambda: read_json_list, lambda: write_json_list),
        tables=lambda: TEXT_INSPECTION_TABLES,
    )


def row(owner):
    return dict(id='same', owner_user_id=owner, task_id='task', version_label='v1',
                standard_id='standard', comparison_id='comparison', status='completed')


class CompositionContracts(unittest.TestCase):
    def test_every_supplier_remains_unevaluated_during_construction(self):
        forbidden=Mock(side_effect=AssertionError('constructor supplier call'))
        owner=TextStorage(repository=forbidden,
            paths=TextStoragePaths(forbidden,IncomingPaths(forbidden,forbidden,forbidden)),
            rows=IncomingRows(forbidden,forbidden,forbidden,forbidden),
            json_io=TextStorageJSON(forbidden,forbidden), tables=forbidden)
        forbidden.assert_not_called()
        self.assertIs(owner.records.dependencies.guard(),owner.lock)
        self.assertIs(owner.incoming.guard(),owner.lock)
        with self.assertRaises(AttributeError):owner.lock=threading.RLock()
        forbidden.assert_not_called()

    def test_construction_is_inert_and_repository_is_selected_on_calling_thread(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)/'absent'
            calls=[]
            def repository():
                calls.append(threading.get_ident())
                return None
            owner=build(directory, repository)
            self.assertEqual(calls, [])
            self.assertFalse(directory.exists())
            self.assertIs(owner.records.dependencies.guard(), owner.lock)
            self.assertIs(owner.incoming.guard(), owner.lock)
            def read():
                identity=threading.get_ident()
                self.assertEqual(owner.records.load('records'), [])
                self.assertIsNone(owner.incoming.load_incoming_text_reference('missing'))
                return identity
            with ThreadPoolExecutor(max_workers=1) as pool:
                identity=pool.submit(read).result(timeout=5)
            self.assertEqual(calls, [identity, identity, identity])
            self.assertNotEqual(identity, threading.get_ident())

    def test_two_http_apps_persist_identical_ids_without_crossing_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            first, second=build(root/'first'), build(root/'second')
            self.assertIsNot(first.lock, second.lock)
            self.assertIsNot(first.records, second.records)
            self.assertIsNot(first.incoming, second.incoming)
            def client_for(storage, identity):
                app=FastAPI()
                @app.post('/record')
                def write():
                    value=row(identity)
                    storage.records.save('records', value)
                    storage.incoming.save_incoming_text_reference(value)
                    return {'record':storage.records.load('records')[0],
                            'reference':storage.incoming.load_incoming_text_reference('same')}
                return TestClient(app)
            with client_for(first, 'alice') as a, client_for(second, 'bob') as b:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results=[pool.submit(client.post, '/record') for client in (a,b)]
                    for future, identity in zip(results, ('alice','bob')):
                        response=future.result(timeout=10)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json(), {'record':row(identity),'reference':row(identity)})
                with patch.object(first.incoming, 'read_json', side_effect=OSError('first unavailable')):
                    with self.assertRaisesRegex(OSError, 'first unavailable'):
                        first.incoming.load_incoming_text_reference('same')
                    self.assertEqual(b.post('/record').json()['reference'], row('bob'))
            self.assertEqual(first.records.load('records'), [row('alice')])
            self.assertEqual(second.records.load('records'), [row('bob')])

    def test_one_domain_write_lock_does_not_block_another_domain(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second=build(Path(folder)/'first'), build(Path(folder)/'second')
            entered=threading.Event()
            original=first.incoming.repository
            def repository():
                entered.set()
                return original()
            first.incoming.repository=repository
            with ThreadPoolExecutor(max_workers=2) as pool:
                with first.lock:
                    blocked=pool.submit(first.incoming.save_incoming_text_reference, row('alice'))
                    self.assertTrue(entered.wait(5))
                    other=pool.submit(second.records.save, 'records', row('bob'))
                    self.assertTrue(other.result(timeout=5))
                    self.assertFalse(blocked.done())
                self.assertTrue(blocked.result(timeout=5))
            self.assertEqual(first.incoming.load_incoming_text_reference('same'), row('alice'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
