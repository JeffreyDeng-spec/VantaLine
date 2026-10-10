"""Pipeline availability reads are isolated by explicit artifact ownership."""
import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.pipeline.resource_status import PipelineResourceStatus
from local_inspection_service.pipeline.resource_status_ports import PipelineResourceStatusLinks
from application_integration_source_contract import restore_plc_domain_root


class PipelineStatusFilePortsTests(unittest.TestCase):
    def setUp(self): fixtures.DetectionArtifactPortsTests.setUp(self)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); dataset = self.root/'outputs/training_datasets/same'; model = self.root/'outputs/training_runs/same.pt'
        files.write_bytes(dataset/'image.png', b'synthetic'); files.write_bytes(model, b'synthetic model')
        links = PipelineResourceStatusLinks(lambda: lambda identifier: (dataset, None), lambda: lambda: [{'id': 'ai'}], lambda: lambda: [{'run_id': 'same', 'path': str(model)}])
        return PipelineResourceStatus(links, files=files), files, dataset, model

    def test_identical_paths_have_independent_availability(self):
        graphs = [self.graph(i) for i in range(2)]
        graphs[0][1].rmtree(graphs[0][2]); graphs[0][1].unlink(graphs[0][3])
        for index, (service, files, dataset, model) in enumerate(graphs):
            expected = 'available' if index else 'missing'
            self.assertEqual(service.pipeline_task_dataset_status({'dataset_id': 'same'}), expected)
            self.assertEqual(service.pipeline_task_model_status({'model_run_id': 'same'}), expected)
            self.assertFalse(model.exists()); self.assertEqual(service.pipeline_task_model_status({'ai_task_id': 'ai', 'detection_method': 'ai'}), 'available')

    def test_storage_errors_are_not_missing_and_early_branches_do_not_read(self):
        service, files, dataset, model = self.graph(0); failure = ArtifactUnavailable('synthetic existence failure')
        with patch.object(files, 'exists', side_effect=failure) as exists:
            self.assertEqual(service.pipeline_task_dataset_status({'dataset_id': 'same', 'dataset_status': 'deleted'}), 'deleted')
            self.assertEqual(service.pipeline_task_model_status({'model_status': 'deleted'}), 'deleted')
            self.assertEqual(service.pipeline_task_model_status({'ai_task_id': 'ai', 'detection_method': 'ai'}), 'available')
            exists.assert_not_called()
            for method, task in [(service.pipeline_task_dataset_status, {'dataset_id': 'same', 'stage': 'samples', 'status': 'running'}), (service.pipeline_task_model_status, {'model_run_id': 'same', 'stage': 'training', 'status': 'running'})]:
                with self.assertRaises(ArtifactUnavailable) as caught: method(task)
                self.assertIs(caught.exception, failure)

    def test_required_falsey_reader_and_root_binding(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        with self.assertRaises(TypeError): PipelineResourceStatus(Mock())
        with self.assertRaises(TypeError): PipelineResourceStatus(Mock(), files=None)
        files = Falsey(); self.assertIs(PipelineResourceStatus(Mock(), files=files).files, files)
        tree = ast.parse(restore_plc_domain_root(read_checked_application_source(Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py', encoding='utf-8')))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_PipelineResourceStatus']
        self.assertEqual(len(calls), 1); self.assertEqual(ast.dump(next(k.value for k in calls[0].keywords if k.arg == 'files')), ast.dump(ast.parse('_business_files', mode='eval').body))


if __name__ == '__main__': unittest.main()
