"""Explicit training catalog owners preserve indexed catalog separation."""
import ast
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.training.dataset_catalog import DatasetCatalog, DatasetPaths, DatasetAudit, DatasetAccess
from local_inspection_service.training.resource_queries import TrainingResources, ResourceDatasets, ResourceRecords, ResourceConfiguration, ResourceAccess
from local_inspection_service.training.model_catalog import TrainedModelCatalog, TrainingFiles, TrainingAccessories, TrainingPipeline, TrainingAccess


class TrainingCatalogFilePortsTests(unittest.TestCase):
    def setUp(self): fixtures.DetectionArtifactPortsTests.setUp(self)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); output = self.root/'outputs'; datasets = output/'training_datasets'; runs = output/'training_runs'; dataset = datasets/'same'; run = runs/'same'
        name = 'synthetic-' + str(index); audit = {'created_at': index+1, 'updated_at': index+2, 'owner_user_id': name, 'owner_username': name}
        files.write_bytes(dataset/'manifest.json', json.dumps({'display_name':name,'samples':[{'image':str(dataset/'sample.png')}]}).encode())
        files.write_bytes(dataset/'sample.png', b'synthetic sample'); files.write_bytes(run/'weights/best.pt', b'synthetic model')
        files.write_bytes(run/'library_metadata.json', json.dumps({'display_name':name}).encode())
        catalog = None
        catalog = DatasetCatalog(DatasetPaths(lambda: output, lambda: Path, lambda: [datasets], str), files.read_json,
            DatasetAudit(lambda *args: audit, lambda: lambda *args: index+1, lambda: lambda *args: index+2),
            DatasetAccess(lambda *args: True, lambda *args: True), lambda path, **kw: catalog.dataset_resource_item(path, **kw), files=files)
        models = TrainedModelCatalog(lambda: {}, TrainingFiles(lambda: [runs], lambda: lambda path: {'action':'train_model'}, lambda: lambda identifier: Path(identifier), files.read_json, lambda: output, lambda: Path),
            TrainingAccessories(str, lambda item: item, lambda: lambda item: False, lambda: lambda *args: {}),
            TrainingPipeline(lambda: [], lambda: lambda *args: {}, lambda: str), TrainingAccess(lambda: None, lambda *args: True, lambda: lambda *args: audit), lambda spec, config: spec, business_files=files)
        resources = TrainingResources(ResourceDatasets(lambda: [datasets], catalog.dataset_resource_item, catalog.training_task_dataset_resource_id),
            ResourceRecords(lambda **kw: [], models.list_trained_model_specs, lambda: []), ResourceConfiguration(lambda: {}, lambda: lambda config, *args: config, lambda task, config: task),
            ResourceAccess(lambda *args: True, lambda record: name, lambda: name, lambda value: value), lambda: Path, lambda: output, files=files)
        return files, catalog, models, resources, dataset, run, name

    def test_same_path_dataset_model_and_resource_payloads_keep_their_owner(self):
        graphs = [self.graph(i) for i in range(2)]
        for files, catalog, models, resources, dataset, run, name in graphs:
            item = catalog.dataset_resource_item(dataset); self.assertEqual(item['display_name'], name); self.assertEqual(item['sample_count'], 1)
            found, item = catalog.find_dataset_resource('same'); self.assertEqual(found, dataset); self.assertEqual(item['owner_user_id'], name)
            specs = models.list_trained_model_specs(); self.assertEqual(len(specs), 1); self.assertEqual(specs[0]['label'], name)
            result = resources.training_resources_payload(include_samples=True); self.assertEqual(result['datasets'][0]['display_name'], name)
            self.assertTrue(result['models'][0]['exists']); self.assertEqual(result['models'][0]['owner_user_id'], name)
            self.assertFalse((run/'weights/best.pt').exists())

    def test_missing_manifest_and_weight_change_only_one_catalog(self):
        graphs = [self.graph(i) for i in range(2)]
        files, catalog, models, resources, dataset, run, name = graphs[0]; files.unlink(dataset/'manifest.json'); files.unlink(run/'weights/best.pt')
        self.assertIsNone(catalog.dataset_resource_item(dataset)); self.assertIsNotNone(graphs[1][1].dataset_resource_item(dataset))
        # Independent metadata reader retains its original missing-file exception.
        with self.assertRaises(FileNotFoundError): models.list_trained_model_specs()
        self.assertTrue(graphs[1][3].training_resources_payload()['models'][0]['exists'])

    def test_runtime_failure_precedes_catalog_reads_and_has_no_fallback(self):
        files, catalog, models, resources, dataset, run, name = self.graph(0); failure = ArtifactUnavailable('synthetic catalog mode')
        with patch.object(files, 'runtime_provider', side_effect=failure):
            for method, args in [(catalog.dataset_resource_item, (dataset,)), (catalog.find_dataset_resource, ('same',)), (catalog.training_dataset_roots, ()), (catalog.training_run_roots, ()), (models.list_trained_model_specs, ()), (resources.training_resources_payload, ())]:
                with self.assertRaises(ArtifactUnavailable) as caught: method(*args)
                self.assertIs(caught.exception, failure)

    def test_required_falsey_adapters_and_root_bindings(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        for cls, key in [(DatasetCatalog,'files'),(TrainingResources,'files'),(TrainedModelCatalog,'business_files')]:
            args = {name: Mock() for name in inspect.signature(cls).parameters if name != key}
            with self.assertRaises(TypeError): cls(**args)
            with self.assertRaises(TypeError): cls(**args, **{key:None})
            owner = Falsey(); self.assertIs(getattr(cls(**args, **{key:owner}),key),owner)
        tree = ast.parse(read_checked_application_source(Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py', encoding='utf-8'))
        calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('DatasetCatalog','TrainingResources','TrainedModelCatalog')]
        # ModelCatalog now owns the actual TrainedModelCatalog constructor.
        domain=ast.parse((Path(__file__).resolve().parents[1]/'local_inspection_service/training/catalog_composition.py').read_text(encoding='utf-8'))
        owned=[n for n in ast.walk(domain) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='TrainedModelCatalog']
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(owned), 1)
        self.assertEqual(ast.dump(next(k.value for k in owned[0].keywords if k.arg=='business_files')),ast.dump(ast.parse('files',mode='eval').body))
        builders=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='ModelCatalog']
        self.assertEqual(len(builders),1)
        self.assertEqual(ast.dump(next(k.value for k in builders[0].keywords if k.arg=='files')),ast.dump(ast.parse('_business_files',mode='eval').body))
        for call in calls:
            key = 'business_files' if call.func.id == 'TrainedModelCatalog' else 'files'
            self.assertEqual(ast.dump(next(k.value for k in call.keywords if k.arg==key)), ast.dump(ast.parse('_business_files',mode='eval').body))


if __name__ == '__main__': unittest.main()
