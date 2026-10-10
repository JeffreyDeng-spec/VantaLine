"""Training mutations, archive reads and digests use the selected synthetic store."""
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactConflict, ArtifactUnavailable
from local_inspection_service.schemas.training import TrainingResourceUpdateRequest
from local_inspection_service.training import resource_mutations, task_background_store, dataset_archives
from local_inspection_service.training.resource_mutations import TrainingResourceMutations, ResourceWriteAccess, ResourceWriteCatalog, ResourceRetirement
from local_inspection_service.training.task_background_store import TaskBackgroundStore, TaskBackgroundIdentity, TaskBackgroundPaths, TaskBackgroundRecords
from local_inspection_service.training.dataset_archives import DatasetArchives, file_sha256


class TrainingResourcePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('implicit training resource storage'))
        for module in (resource_mutations, task_background_store, dataset_archives):
            p = patch.object(module, 'BusinessFiles', self.default, create=True); p.start(); self.addCleanup(p.stop)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); directory = self.root / 'outputs/datasets/same'
        user = {'id': str(index)}; record = {'id': 'same', 'owner_user_id': str(index)}
        payload = Mock(return_value={'owner': str(index)})
        access = ResourceWriteAccess(lambda: user, Mock(), lambda row: row['owner_user_id'], lambda: Mock(), lambda: Mock())
        catalog = ResourceWriteCatalog(lambda *args, **kwargs: (directory, record), lambda: [], lambda: Path, payload)
        service = TrainingResourceMutations(access, catalog, Mock(spec=ResourceRetirement), files=files)
        return files, directory, user, record, payload, service

    def test_two_stores_update_and_remove_only_the_selected_dataset(self):
        graphs = [self.graph(i) for i in range(2)]
        for index, (files, directory, *_) in enumerate(graphs):
            files.write_json(directory / 'manifest.json', {'owner': index}, indent=2)
            files.write_bytes(directory / 'images/train/sample.png', ('image-' + str(index)).encode())
        def update(index):
            files, directory, user, record, payload, service = graphs[index]
            self.assertEqual(service.update_training_dataset('same', TrainingResourceUpdateRequest(display_name='name-' + str(index)))['owner'], str(index))
            return files.read_json(directory / 'manifest.json')['display_name']
        with ThreadPoolExecutor(max_workers=2) as pool: self.assertEqual(list(pool.map(update, range(2))), ['name-0', 'name-1'])
        files, directory, user, record, payload, service = graphs[0]
        self.assertIs(service.delete_training_dataset_resource('same', user), record)
        self.assertFalse(files.exists(directory)); self.assertTrue(graphs[1][0].exists(directory)); self.default.assert_not_called()

    def test_manifest_generation_conflict_preserves_concurrent_update_without_retry(self):
        files, directory, user, record, payload, service = self.graph(0)
        path = directory / 'manifest.json'; files.write_json(path, {'display_name': 'old'}, indent=2)
        def concurrent(*args, **kwargs):
            value = files.read_json(path); value['display_name'] = 'newer'; files.write_json(path, value, indent=2)
        service.access = ResourceWriteAccess(lambda: user, Mock(), lambda row: user['id'], lambda: concurrent, lambda: Mock())
        with patch.object(self.runtimes[0].store, 'put_bytes', wraps=self.runtimes[0].store.put_bytes) as puts:
            with self.assertRaises(ArtifactConflict): service.update_training_dataset('same', TrainingResourceUpdateRequest(display_name='loser'))
            self.assertEqual(puts.call_count, 2)
        self.assertEqual(files.read_json(path)['display_name'], 'newer'); payload.assert_not_called()

    def test_sample_deletion_failure_preserves_original_partial_deletion_and_manifest(self):
        files, directory, user, record, payload, service = self.graph(0)
        image = directory / 'images/train/sample.png'; label = directory / 'labels/train/sample.txt'
        files.write_bytes(image, b'image'); files.write_bytes(label, b'label')
        manifest = {'samples': [{'image': str(image)}]}; files.write_json(directory / 'manifest.json', manifest, indent=2)
        original = files.unlink; failure = ArtifactUnavailable('synthetic delete failure')
        def unlink(path):
            if path == label: raise failure
            return original(path)
        with patch.object(files, 'unlink', side_effect=unlink) as deletes:
            with self.assertRaises(ArtifactUnavailable) as caught: service.delete_training_dataset_sample('same', 'sample.png')
            self.assertIs(caught.exception, failure); self.assertEqual(deletes.call_count, 2)
        self.assertFalse(files.exists(image)); self.assertTrue(files.exists(label))
        self.assertEqual(dict(files.read_json(directory / 'manifest.json')), manifest); payload.assert_not_called()

    def test_task_background_replacement_and_source_copy_are_store_local(self):
        graphs = [self.graph(i) for i in range(2)]; source = self.root / 'uploads/source.png'; directory = self.root / 'backgrounds/task_env_same'
        for index, (files, *_) in enumerate(graphs):
            files.write_bytes(source, ('source-' + str(index)).encode()); files.write_bytes(directory / 'old.png', b'old')
        files = graphs[0][0]; update = Mock(side_effect=lambda identifier, **meta: meta)
        service = TaskBackgroundStore(TaskBackgroundIdentity(lambda value: value, lambda value: value, lambda: str, lambda: 'legacy'),
            TaskBackgroundPaths(lambda: self.root / 'backgrounds', lambda: {'.png'}),
            TaskBackgroundRecords(lambda: update, lambda identifier, meta: meta), lambda *args, **kwargs: None,
            lambda path: list(files.iterdir(path)), lambda: 123, files=files)
        result = service.save_task_environment_background_set('same', source, {'id': '0'})
        self.assertEqual(result['status'], 'ready'); self.assertEqual(files.read_bytes(directory / 'source.png'), b'source-0')
        self.assertFalse(files.exists(directory / 'old.png')); self.assertTrue(graphs[1][0].exists(directory / 'old.png'))
        self.assertFalse(graphs[1][0].exists(directory / 'source.png')); update.assert_called_once()

    def test_remote_archives_and_digest_read_only_their_selected_store(self):
        for fixture in self.stores:
            fixture.budget.limits['work'] = 4 * 1024 * 1024
            fixture.budget.free_bytes = lambda: 20 * 1024 * 1024
        def run(index):
            files, directory, *_ = self.graph(index); contents = ('archive source ' + str(index)).encode()
            source = directory / 'images/train/sample.png'; files.write_bytes(source, contents)
            files.write_bytes(directory / 'previews/preview.png', b'preview')
            archives = DatasetArchives(str, lambda: {'previews'}, lambda: 90, lambda path: file_sha256(path, files=files), runtime_provider=lambda: self.runtimes[index])
            self.assertEqual(file_sha256(source, files=files), hashlib.sha256(contents).hexdigest())
            for worker in (False, True):
                temporary, archive = (archives.build_worker_training_bundle if worker else archives.package_training_dataset)(directory, 'same')
                try:
                    with zipfile.ZipFile(archive) as zipped:
                        self.assertEqual(zipped.read('images/train/sample.png'), contents)
                        self.assertEqual('previews/preview.png' in zipped.namelist(), not worker)
                finally: temporary.cleanup()
            self.assertFalse(source.exists())
        with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(run, range(2)))
        self.default.assert_not_called()

    def test_missing_none_falsey_capabilities_and_root_bindings(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
            def __call__(self): return None
        for cls, field in ((TrainingResourceMutations, 'files'), (TaskBackgroundStore, 'files'), (DatasetArchives, 'runtime_provider')):
            args = {k: Mock() for k in inspect.signature(cls).parameters if k != field}
            with self.assertRaises(TypeError): cls(**args)
            with self.assertRaises(TypeError): cls(**args, **{field: None})
            port = Falsey(); self.assertIs(getattr(cls(**args, **{field: port}), field), port)
        with self.assertRaises(TypeError): file_sha256(Path('unused'))
        with self.assertRaises(TypeError): file_sha256(Path('unused'), files=None)
        root = Path(__file__).resolve().parents[1]; tree = ast.parse(read_checked_application_source(root / 'local_inspection_service/server.py', encoding='utf-8')); found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'TrainingResourceMutations', 'TaskBackgroundStore', 'DatasetArchives'}:
                field = 'runtime_provider' if node.func.id == 'DatasetArchives' else 'files'
                expected = 'lambda: _business_files.runtime_provider()' if field == 'runtime_provider' else '_business_files'
                values = [kw.value for kw in node.keywords if kw.arg == field]; self.assertEqual(len(values), 1)
                self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse(expected, mode='eval').body)); found.append(node.func.id)
        self.assertCountEqual(found, ['TrainingResourceMutations', 'TaskBackgroundStore', 'DatasetArchives'])


if __name__ == '__main__': unittest.main()
