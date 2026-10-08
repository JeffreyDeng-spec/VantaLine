"""Comparison work-budget and evidence selection share the explicit media owner."""
from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.codex_compare import worker
from local_inspection_service.codex_compare.media import MediaStore
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable

class ComparisonMediaOwnerTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.task={'owner_user_id':'alice','id':'task','attempt_id':'attempt'}
    def test_budget_and_evidence_follow_each_selected_owner(self):
        events=[]
        for index,runtime in enumerate(self.runtimes):
            media=MediaStore(self.root/'codex_comparisons'/'media',runtime_provider=lambda runtime=runtime:runtime)
            data=('evidence-'+str(index)).encode();sha=media.put('alice',data)
            budget=SimpleNamespace(preallocated=True, scratch_roots={'work':self.root}, limits={'work':100*1024*1024}, workspace=Mock())
            selected_runtime=SimpleNamespace(key=runtime.key,mode=runtime.mode,store=SimpleNamespace(
                budget=budget,locations=runtime.store.locations,read_bytes=runtime.store.read_bytes))
            media.runtime_provider=lambda:selected_runtime
            @contextmanager
            def workspace(kind,size):
                events.append((index,'reserve',kind,size))
                try:yield self.root/('work-'+str(index))
                finally:events.append((index,'release'))
            def execute(task,token,config,selected):
                self.assertIs(selected,media);self.assertEqual(selected.read('alice',sha),data)
                self.assertEqual(config['work_root'],str(self.root/('work-'+str(index))))
                self.assertTrue(config['bounded_artifacts']);events.append((index,'execute'));return index
            with patch.object(budget,'preallocated',True),patch.object(budget,'scratch_roots',{'work':self.root}),patch.object(budget,'limits',{'work':100*1024*1024}),patch.object(budget,'workspace',side_effect=workspace),patch.object(worker.shutil,'disk_usage',return_value=SimpleNamespace(free=80*1024*1024)),patch.object(worker,'_execute',side_effect=execute):
                self.assertEqual(worker.execute(self.task,'token',{'work_root':'ignored'},media),index)
        self.assertEqual(events,[(0,'reserve','work',64*1024*1024),(0,'execute'),(0,'release'),(1,'reserve','work',64*1024*1024),(1,'execute'),(1,'release')])
    def test_reservation_failure_settles_once_before_execution(self):
        runtime=self.runtimes[0];media=MediaStore(self.root,runtime_provider=lambda:runtime)
        budget=runtime.store.budget;failure=ArtifactUnavailable('synthetic');context=Mock();context.__enter__=Mock(side_effect=failure);context.__exit__=Mock();repo=Mock()
        with patch.object(budget,'preallocated',True),patch.object(budget,'scratch_roots',{'work':self.root}),patch.object(budget,'workspace',return_value=context),patch.object(worker,'with_repo',side_effect=lambda fn:fn(repo)),patch.object(worker,'_execute') as execute:
            with self.assertRaises(ArtifactUnavailable) as caught:worker.execute(self.task,'token',{},media)
        self.assertIs(caught.exception,failure);execute.assert_not_called();context.__exit__.assert_not_called()
        self.assertEqual(repo.settle.call_count,1);self.assertEqual(repo.settle.call_args.args[:4],('alice','task','attempt','failed'))
    def test_body_failure_releases_selected_reservation_without_retry(self):
        runtime=self.runtimes[1];media=MediaStore(self.root,runtime_provider=lambda:runtime);budget=runtime.store.budget
        context=Mock();context.__enter__=Mock(return_value=self.root/'work');context.__exit__=Mock();error=ValueError('synthetic')
        with patch.object(budget,'preallocated',True),patch.object(budget,'scratch_roots',{'work':self.root}),patch.object(budget,'workspace',return_value=context),patch.object(worker,'_execute',side_effect=error) as execute:
            with self.assertRaises(ValueError) as caught:worker.execute(self.task,'token',{},media)
        self.assertIs(caught.exception,error);execute.assert_called_once();context.__exit__.assert_called_once_with(None,None,None)
    def test_local_provider_and_provider_failure_precede_execution(self):
        media=MediaStore(self.root,runtime_provider=lambda:None);config={'work_root':'synthetic'}
        with patch.object(worker,'_execute',return_value='local') as execute:
            self.assertEqual(worker.execute(self.task,'token',config,media),'local');execute.assert_called_once_with(self.task,'token',config,media)
        error=ArtifactUnavailable('unavailable');media.runtime_provider=Mock(side_effect=error)
        with patch.object(worker,'_execute') as execute,patch.object(worker,'with_repo') as repository:
            with self.assertRaises(ArtifactUnavailable) as caught:worker.execute(self.task,'token',config,media)
        self.assertIs(caught.exception,error);execute.assert_not_called();repository.assert_not_called()
    def test_required_provider_and_unbounded_remote_rejection(self):
        with self.assertRaises(TypeError):MediaStore(self.root)
        with self.assertRaises(TypeError):MediaStore(self.root,runtime_provider=None)
        class Falsey:
            def __bool__(self):raise AssertionError('truthiness')
            def __call__(self):return None
        provider=Falsey();self.assertIs(MediaStore(self.root,runtime_provider=provider).runtime_provider,provider)
        media=MediaStore(self.root,runtime_provider=lambda:self.runtimes[0])
        with patch.object(worker,'_execute') as execute:
            with self.assertRaisesRegex(RuntimeError,'kernel-limited'):worker.execute(self.task,'token',{},media)
        execute.assert_not_called()

if __name__=='__main__':unittest.main()
