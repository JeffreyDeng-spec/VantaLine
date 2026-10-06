"""Owned training storage and snapshot/failure ordering using synthetic stores."""
import ast
from contextlib import contextmanager
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from smoke_training_runner import Fixture
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.training.runner import TrainingRunner,TrainingRunnerRecords,TrainingRunnerPaths,TrainingDatasetExecution,TrainingLocalExecution

def compose(f,files):
    return TrainingRunner(TrainingRunnerRecords(f.find,f.path,lambda:f.load,lambda:f.update,f.sync),
        TrainingRunnerPaths(lambda:f.resolve,lambda:f.root,lambda:f.root/'app',lambda:f.output),
        TrainingDatasetExecution(f.mode,f.generate,f.runpod,f.remote),
        TrainingLocalExecution(f.base,f.device,f.cli,lambda:f.popen,f.progress,lambda:f.warmup),
        lambda:f.resolver,files=files)

class RunnerFileTests(unittest.TestCase):
    def setUp(self):fixtures.DetectionArtifactPortsTests.setUp(self)
    def graph(self,index):
        f=Fixture(self.root/'training_tasks');f.mode.side_effect=None;f.mode.return_value='runpod'
        f.task.update(action='train_model',dataset_yaml=str(self.root/'outputs/training_datasets/shared/dataset.yaml'))
        files=BusinessFiles(lambda:self.runtimes[index]);return f,files,compose(f,files)
    def test_same_dataset_path_isolated_and_original_snapshot_used(self):
        a,af,ar=self.graph(0);b,bf,br=self.graph(1);path=Path(a.task['dataset_yaml']);af.write_text(path,'synthetic',encoding='utf-8')
        a.resolver.version=99;b.binding['model_profiles']['pipeline']['version']=88
        ar.run_training_task('job');br.run_training_task('job')
        a.generate.assert_not_called();b.generate.assert_called_once_with(b.task)
        a.runpod.assert_called_once();b.runpod.assert_called_once()
        self.assertEqual(a.runpod.call_args.args[2]['dataset_yaml'],str(path))
        self.assertEqual(b.runpod.call_args.args[2],b.dataset)
        self.assertEqual(a.resolver.scopes[-1],a.binding['model_profiles'])
        self.assertEqual(b.resolver.scopes[-1]['pipeline']['version'],88)
        self.assertIsNone(a.resolver.current_snapshot());self.assertFalse(path.exists())
    def test_cos_rejects_local_before_path_resolution_or_process_start(self):
        f,files,runner=self.graph(0);f.mode.return_value='local';runner.run_training_task('job')
        self.assertEqual([u['status'] for u in f.updates],['running','failed'])
        self.assertIn('COS training requires RunPod',f.updates[-1]['error'])
        f.resolve.assert_not_called();f.generate.assert_not_called();f.popen.assert_not_called();f.runpod.assert_not_called();f.sync.assert_called_once()
    def test_failure_preserves_running_update_and_does_not_retry(self):
        f,files,runner=self.graph(0);failure=ArtifactUnavailable('synthetic selection unavailable')
        with patch.object(files,'runtime_provider',side_effect=failure) as provider:runner.run_training_task('job')
        provider.assert_called_once();self.assertEqual([u['status'] for u in f.updates],['running','failed'])
        self.assertEqual(f.updates[-1]['error'],str(failure));f.resolve.assert_not_called();f.sync.assert_called_once()
        self.assertIsNone(f.resolver.current_snapshot())
    def test_generation_reservation_released_before_unknown_submission_failure(self):
        f,files,runner=self.graph(0);events=[]
        @contextmanager
        def reserve(kind,amount):
            events.append(('enter',kind,amount))
            try:yield
            finally:events.append(('exit',))
        f.generate.side_effect=lambda task:events.append(('generate',)) or f.dataset
        def submit(*args):events.append(('submit',));raise RuntimeError('unknown remote result')
        f.runpod.side_effect=submit
        with patch.object(self.runtimes[0].store.budget,'reserve',side_effect=reserve):runner.run_training_task('job')
        self.assertEqual(events,[('enter','work',1),('generate',),('exit',),('submit',)])
        f.runpod.assert_called_once();f.remote.assert_not_called();f.popen.assert_not_called()
        self.assertEqual(f.updates[-1]['error'],'unknown remote result');f.sync.assert_called_once()
    def test_required_files_and_root_composition(self):
        class Falsey:
            def __bool__(self):raise AssertionError('files truthiness')
        kwargs={k:Mock() for k in inspect.signature(TrainingRunner).parameters if k!='files'}
        with self.assertRaises(TypeError):TrainingRunner(**kwargs)
        with self.assertRaises(TypeError):TrainingRunner(**kwargs,files=None)
        files=Falsey();self.assertIs(TrainingRunner(**kwargs,files=files).files,files)
        tree=ast.parse((Path(__file__).resolve().parents[1]/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='TrainingRunner')
        self.assertEqual(ast.dump(next(k.value for k in call.keywords if k.arg=='files')),ast.dump(ast.parse('_business_files',mode='eval').body))

if __name__=='__main__':unittest.main()
