"""Real artifact-store isolation for training metadata with synthetic rendering."""
import ast
from concurrent.futures import ThreadPoolExecutor
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from fastapi import HTTPException
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from smoke_training_dataset import DatasetFixture
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.schemas.training import TrainingStartRequest
from local_inspection_service.training import dataset_input, dataset_generation, preview_cache, preview_artifacts, preview_approval
from local_inspection_service.training.dataset_input import TrainingDatasetInput
from local_inspection_service.training.dataset_generation import DatasetGenerator, DatasetRecords, DatasetPlanning, DatasetRendering
from local_inspection_service.training.preview_cache import TrainingPreviewCache, SpriteVersionInputs
from local_inspection_service.training.preview_artifacts import PreviewArtifactStore
from local_inspection_service.training.preview_approval import TrainingPreviewApproval


class TrainingFilePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('implicit training storage'))
        for module in (dataset_input, dataset_generation, preview_cache, preview_artifacts, preview_approval):
            p = patch.object(module, 'BusinessFiles', self.default, create=True)
            p.start(); self.addCleanup(p.stop)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index])
        directory = self.root / 'outputs/training_datasets/same'
        jobs = self.root / 'training_jobs'
        selected = [{'id': 'same', 'name': 'store-' + str(index)}]
        inputs = TrainingDatasetInput(lambda identifier, **kwargs: (directory, {'owner_user_id': str(index)}),
            lambda record, user: self.assertEqual(record['owner_user_id'], user['id']), lambda: lambda rows: rows, files=files)
        cache = TrainingPreviewCache(SpriteVersionInputs(lambda item: [{'path': str(directory / 'sprite.png')}],
            lambda item: item['id'], lambda item: 'object', lambda item: 'solid'), lambda: 'schema', lambda: Path,
            lambda item: cache.accessory_sprite_version(item), files=files)
        approval = TrainingPreviewApproval(lambda: jobs, lambda: lambda value, user: 'background', cache.preview_cache_key, files=files)
        plans = PreviewArtifactStore(lambda kind: self.root / kind, lambda: jobs, files=files)
        return files, directory, selected, inputs, cache, approval, plans

    def test_two_stores_keep_dataset_plan_and_stat_cache_separate_at_identical_paths(self):
        def run(index):
            files, directory, selected, inputs, cache, approval, plans = self.graph(index)
            files.write_text(directory / 'manifest.json', json.dumps({'samples': [index], 'display_name': str(index)}), encoding='utf-8')
            files.write_text(directory / 'dataset.yaml', 'synthetic', encoding='utf-8')
            files.write_bytes(directory / 'sprite.png', b'synthetic sprite' * (index + 1))
            key = cache.preview_cache_key(selected)
            plans.write_plan('same', {'selected_accessories': selected, 'background_set_id': 'background', 'preview_cache_key': key})
            self.assertEqual(inputs.dataset_for_training('same', {'id': str(index)})['display_name'], str(index))
            approval.validate_approved_preview({'training': {}}, TrainingStartRequest(selected_accessory_ids=['same'], approved_preview_id='same'), selected)
            self.assertFalse((directory / 'manifest.json').exists())
            return key
        with ThreadPoolExecutor(max_workers=2) as pool: keys = list(pool.map(run, range(2)))
        self.assertNotEqual(*keys); self.default.assert_not_called()

    def test_stale_approval_mutates_only_its_config_after_same_store_sprite_changes(self):
        files, directory, selected, inputs, cache, approval, plans = self.graph(0)
        files.write_bytes(directory / 'sprite.png', b'before')
        plans.write_plan('same', {'selected_accessories': selected, 'background_set_id': 'background', 'preview_cache_key': cache.preview_cache_key(selected)})
        files.write_bytes(directory / 'sprite.png', b'after changed content')
        state = {'training': {'preview_urls': ['old'], 'previews': ['old']}}
        with self.assertRaises(HTTPException) as caught:
            approval.validate_approved_preview(state, TrainingStartRequest(selected_accessory_ids=['same'], approved_preview_id='same'), selected)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(state['training']['preview_stale_reason'], 'clean_sprite_version_changed')
        self.assertEqual(state['training']['preview_urls'], [])
        self.assertFalse(BusinessFiles(lambda: self.runtimes[1]).exists(self.root / 'training_jobs/same.json'))

    def test_remote_read_failure_is_not_reinterpreted_as_missing_or_unreadable_metadata(self):
        files, directory, selected, inputs, cache, approval, plans = self.graph(0)
        for path in (directory / 'manifest.json', directory / 'dataset.yaml', self.root / 'training_jobs/same.json'):
            files.write_text(path, '{}', encoding='utf-8')
        failure = ArtifactUnavailable('synthetic object read failure')
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=failure) as opened:
            for action in (lambda: inputs.dataset_for_training('same'), lambda: approval.validate_approved_preview(
                    {'training': {}}, TrainingStartRequest(selected_accessory_ids=['same'], approved_preview_id='same'), selected)):
                with self.assertRaises(ArtifactUnavailable) as caught: action()
                self.assertIs(caught.exception, failure)
            self.assertEqual(opened.call_count, 2)
        self.default.assert_not_called()

    def generator(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); fixture = DatasetFixture(self.root)
        fixture.task.update(job_id='same', owner_user_id=str(index), sample_count=1)
        fixture.plan = fixture.plan[:1]
        fixture.output.side_effect = lambda *args: self.root / 'outputs/training_datasets'
        def draw(selected, path, **kwargs):
            files.write_bytes(path, ('image-' + str(index)).encode())
            return {'labels': [], 'url': '/synthetic/image'}
        generator = DatasetGenerator(DatasetRecords(fixture.load, fixture.save, fixture.ensure, fixture.select, fixture.ocr),
            DatasetPlanning(lambda: fixture.pose, lambda: fixture.background, fixture.planner),
            DatasetRendering(lambda: draw, lambda: Mock(), lambda: lambda *args: '/synthetic/annotation',
                lambda path, directory, names: files.write_text(path, str(index), encoding='utf-8'), lambda: 0.5, lambda: 33),
            lambda: fixture.output, lambda: fixture.update, files=files)
        return files, fixture, generator

    def test_generation_writes_labels_and_manifest_in_the_selected_store(self):
        def run(index):
            files, fixture, generator = self.generator(index)
            result = generator.generate_training_dataset(fixture.task)
            manifest = json.loads(files.read_text(Path(result['manifest_path']), encoding='utf-8'))
            self.assertEqual(manifest['owner_user_id'], str(index))
            self.assertEqual(files.read_bytes(self.root / 'outputs/training_datasets/same/images/train/sample_000001.png'), ('image-' + str(index)).encode())
            self.assertEqual(files.read_text(self.root / 'outputs/training_datasets/same/labels/train/sample_000001.txt', encoding='utf-8'), '')
            self.assertFalse(Path(result['manifest_path']).exists())
        with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(run, range(2)))
        self.default.assert_not_called()

    def test_label_publication_failure_preserves_image_but_prevents_progress_yaml_and_manifest(self):
        files, fixture, generator = self.generator(0)
        store = self.runtimes[0].store; original = store.put_bytes
        failure = ArtifactUnavailable('synthetic label publication failure')
        def publish(key, data, **kwargs):
            if '/labels/' in key: raise failure
            return original(key, data, **kwargs)
        with patch.object(store, 'put_bytes', side_effect=publish) as writes:
            with self.assertRaises(ArtifactUnavailable) as caught: generator.generate_training_dataset(fixture.task)
        self.assertIs(caught.exception, failure); self.assertEqual(writes.call_count, 2)
        self.assertTrue(files.exists(self.root / 'outputs/training_datasets/same/images/train/sample_000001.png'))
        for name in ('dataset.yaml', 'manifest.json'): self.assertFalse(files.exists(self.root / 'outputs/training_datasets/same' / name))
        fixture.update.assert_not_called()

    def test_missing_none_falsey_dependencies_and_root_bindings(self):
        classes = (TrainingDatasetInput, DatasetGenerator, TrainingPreviewCache, PreviewArtifactStore, TrainingPreviewApproval)
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        for cls in classes:
            args = {name: Mock() for name in inspect.signature(cls).parameters if name != 'files'}
            with self.assertRaises(TypeError): cls(**args)
            with self.assertRaises(TypeError): cls(**args, files=None)
            port = Falsey(); self.assertIs(cls(**args, files=port).files, port)
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        names = {cls.__name__ for cls in classes}; found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names:
                ports = [kw.value for kw in node.keywords if kw.arg == 'files']; self.assertEqual(len(ports), 1)
                self.assertEqual(ast.dump(ports[0]), ast.dump(ast.parse('_business_files', mode='eval').body)); found.append(node.func.id)
        self.assertCountEqual(found, names)


if __name__ == '__main__': unittest.main()
