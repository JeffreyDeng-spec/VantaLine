"""Retired task settlement and read-only public refresh with all remote capabilities forbidden."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class PoisonValue:
    def __bool__(self):raise AssertionError('unexpected truthiness')
    def __str__(self):raise AssertionError('unexpected stringify')
    def __iter__(self):raise AssertionError('unexpected iteration')
    def __contains__(self,item):raise AssertionError('unexpected membership')
    def get(self,*args,**kwargs):raise AssertionError('unexpected task read')


class RetiredFlowFixture:
    def __init__(self):
        self.events=[];self.task={'job_id':'job','owner_user_id':'owner','nested':[]};self.dataset={'dataset_yaml':'fixture'}
        self.clock_value=123.9;self.update_value={'ignored':True};self.public_value={'status':'running','nested':[]}
        self.clock=Mock(side_effect=lambda:self.event('clock') or self.clock_value)
        self.update=Mock(side_effect=lambda *args,**kwargs:self.event('update') or self.update_value)
        self.public=Mock(side_effect=lambda task:self.event('public') or self.public_value);self.hidden=[]
    def event(self,name):self.events.append(name)
    def bind(self,api,stack):
        stack.enter_context(patch.object(api,'update_training_task',self.update));stack.enter_context(patch.object(api,'public_training_task',self.public));stack.enter_context(patch('time.time',self.clock))
        for name in ['windows_worker_base_url','masked_url_for_status','windows_worker_request_with_retry','worker_training_payload','post_worker_training_bundle',
                     'public_path_sanitized','windows_worker_request','_start_transfer_progress_thread','windows_worker_get_json_streamed','worker_training_upload_timeout_seconds',
                     'worker_training_artifact_summary','import_worker_training_artifacts']:
            self.hidden.append(stack.enter_context(patch.object(api,name,side_effect=AssertionError('unreachable historical capability'))))
        stack.enter_context(patch.object(api,'IMAGE_JOB_ACTIVE_STATUSES',PoisonValue()))


class TrainingRetiredWorkerFlowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start();cls.runtime=tempfile.TemporaryDirectory(prefix='retired-flow-root-')
        root=Path(cls.runtime.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.f=self.fixture()
        for target in ['requests.request','requests.get','requests.post','time.sleep','subprocess.Popen','os.kill','threading.Thread','threading.Event']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
    def fixture(self):f=RetiredFlowFixture();f.bind(self.api,self.stack);return f
    def settle(self,kind,job_id=' job ',task=None,dataset=None):
        task=self.f.task if task is None else task
        if kind=='dataset':return self.api.run_worker_dataset_generation_task(job_id,task)
        return self.api.run_worker_training_task(job_id,task,dataset)
    def refresh(self,**kwargs):return self.api.refresh_worker_training_task(self.f.task,**kwargs)
    def assert_hidden(self,f):
        for port in f.hidden:port.assert_not_called()
    def test_task_settlement_exact_fields_order_and_ignored_update_results(self):
        for kind,error in [('dataset','Windows Worker dataset generation is retired. Production training uses RunPod.'),('training','Windows Worker training is retired. Production training uses RunPod.')]:
            for returned in [False,None,{'replacement':True}]:
                self.f=self.fixture();f=self.f;f.update_value=returned;task_before=copy.deepcopy(f.task);dataset_before=copy.deepcopy(f.dataset)
                self.assertIsNone(self.settle(kind,dataset=f.dataset));self.assertEqual(f.events,['clock','update'])
                f.update.assert_called_once_with(' job ',status='failed',progress=100,completed_at=123,training_executor='runpod',error=error,note='Windows Worker 已退役；请使用 RunPod 训练链路。')
                f.clock.assert_called_once_with();f.public.assert_not_called();self.assert_hidden(f);self.assertEqual(f.task,task_before);self.assertEqual(f.dataset,dataset_before)
    def test_task_and_dataset_and_job_id_are_not_interpreted(self):
        for kind in ['dataset','training']:
            self.f=self.fixture();f=self.f;value=PoisonValue();self.assertIsNone(self.settle(kind,job_id=value,task=value,dataset=value));self.assertIs(f.update.call_args.args[0],value);self.assert_hidden(f)
        self.f=self.fixture();f=self.f
        self.assertIsNone(self.api.run_worker_training_task('job',PoisonValue()));self.assertIsNone(self.api.run_worker_training_task('job',PoisonValue(),None));self.assertEqual(f.update.call_count,2);self.assert_hidden(f)
    def test_clock_conversion_and_failure_precede_update_without_retry(self):
        for kind in ['dataset','training']:
            for value,expected in [(0,0),(-1.9,-1),(123.9,123),('45',45)]:
                self.f=self.fixture();f=self.f;f.clock_value=value;self.settle(kind);self.assertEqual(f.update.call_args.kwargs['completed_at'],expected);f.clock.assert_called_once()
            for value,error_type in [(None,TypeError),('bad',ValueError),(float('inf'),OverflowError),(float('nan'),ValueError)]:
                self.f=self.fixture();f=self.f;f.clock_value=value
                with self.assertRaises(error_type):self.settle(kind)
                f.clock.assert_called_once();f.update.assert_not_called();self.assert_hidden(f)
            self.f=self.fixture();f=self.f;error=OSError('clock');f.clock.side_effect=[error,123]
            with self.assertRaises(OSError) as caught:self.settle(kind)
            self.assertIs(caught.exception,error);f.clock.assert_called_once();f.update.assert_not_called();self.assert_hidden(f)
    def test_settlement_captures_current_updater_before_reading_clock(self):
        for kind in ['dataset','training']:
            self.f=self.fixture();f=self.f;replacement=Mock(return_value=False)
            def clock():self.api.update_training_task=replacement;return 77.9
            f.clock.side_effect=clock;self.settle(kind);f.update.assert_called_once();replacement.assert_not_called();self.assertEqual(f.update.call_args.kwargs['completed_at'],77)
            self.settle(kind);f.update.assert_called_once();replacement.assert_called_once();self.assertEqual(replacement.call_args.kwargs['completed_at'],77);self.assert_hidden(f)
    def test_update_failure_propagates_once_after_clock(self):
        for kind in ['dataset','training']:
            for error_type in [OSError,RuntimeError,KeyboardInterrupt]:
                self.f=self.fixture();f=self.f;error=error_type('update');f.update.side_effect=[error,{}]
                with self.assertRaises(error_type) as caught:self.settle(kind)
                self.assertIs(caught.exception,error);f.clock.assert_called_once();f.update.assert_called_once();f.public.assert_not_called();self.assert_hidden(f)
    def test_refresh_preserves_projection_identity_nested_aliases_and_existing_notes(self):
        default_note='历史 Windows-worker 训练记录仅保留只读展示；生产训练执行已切换为 RunPod。'
        for note in [None,'',0,PoisonValue(),'kept']:
            self.f=self.fixture();f=self.f;f.public_value.update(executor_retired=False,remote_refresh_retired=0,note=note);nested=f.public_value['nested'];before=copy.deepcopy(f.task)
            result=self.refresh(include_artifacts=PoisonValue());self.assertIs(result,f.public_value);self.assertIs(result['note'],note);self.assertIs(result['nested'],nested)
            self.assertIs(result['executor_retired'],True);self.assertIs(result['remote_refresh_retired'],True);f.public.assert_called_once_with(f.task);self.assertEqual(f.task,before)
            f.clock.assert_not_called();f.update.assert_not_called();self.assert_hidden(f)
        self.f=self.fixture();f=self.f;value=PoisonValue();f.task=value;result=self.refresh();self.assertIs(result,f.public_value);self.assertEqual(result['note'],default_note);self.assertIs(f.public.call_args.args[0],value)
    def test_refresh_mutation_order_and_partial_failures_are_not_retried(self):
        for failure in [None,'executor_retired','remote_refresh_retired','setdefault']:
            self.f=self.fixture();f=self.f;error=OSError(str(failure));events=[];hits=[]
            class Projection(dict):
                def __setitem__(self,key,value):
                    events.append(key)
                    if key==failure:
                        hits.append(True)
                        if len(hits)==1:raise error
                    return super().__setitem__(key,value)
                def setdefault(self,key,value):
                    events.append('setdefault')
                    if failure=='setdefault':
                        hits.append(True)
                        if len(hits)==1:raise error
                    return super().setdefault(key,value)
            f.public_value=Projection(existing='keep')
            if failure is None:self.assertIs(self.refresh(),f.public_value)
            else:
                with self.assertRaises(OSError) as caught:self.refresh()
                self.assertIs(caught.exception,error);self.assertEqual(len(hits),1)
            expected=['executor_retired','remote_refresh_retired','setdefault'];self.assertEqual(events,expected if failure is None else expected[:expected.index(failure)+1])
            self.assertEqual(f.public_value.get('executor_retired'),None if failure=='executor_retired' else True)
            self.assertEqual(f.public_value.get('remote_refresh_retired'),True if failure in [None,'setdefault'] else None)
            self.assertEqual('note' in f.public_value,failure is None);f.public.assert_called_once();f.clock.assert_not_called();f.update.assert_not_called();self.assert_hidden(f)
    def test_public_projection_errors_and_non_mapping_result_are_not_normalized(self):
        self.f=self.fixture();f=self.f;error=ValueError('projection');f.public.side_effect=[error,{}]
        with self.assertRaises(ValueError) as caught:self.refresh()
        self.assertIs(caught.exception,error);f.public.assert_called_once();f.clock.assert_not_called();f.update.assert_not_called();self.assert_hidden(f)
        for value in [None,[],False,'invalid']:
            self.f=self.fixture();f=self.f;f.public_value=value
            with self.assertRaises(TypeError):self.refresh()
            f.public.assert_called_once();f.clock.assert_not_called();f.update.assert_not_called();self.assert_hidden(f)
    def test_refresh_does_not_copy_a_projection_that_aliases_its_input(self):
        f=self.f;f.public.side_effect=lambda task:task;result=self.refresh(include_artifacts=True)
        self.assertIs(result,f.task);self.assertIs(f.task['executor_retired'],True);self.assertIs(f.task['remote_refresh_retired'],True);f.clock.assert_not_called();f.update.assert_not_called();self.assert_hidden(f)


    def test_independent_task_and_refresh_services_capture_updater_and_keep_projection_aliases(self):
        from local_inspection_service.training.legacy_worker_tasks import LegacyWorkerTaskPorts, LegacyWorkerTasks
        from local_inspection_service.training.legacy_worker_refresh import LegacyRefreshRecords, LegacyRefreshTransfer, LegacyRefreshArtifacts, LegacyWorkerRefresh
        instances=[]
        for index,owner in enumerate(['alice','bob']):
            f=RetiredFlowFixture();f.task['owner_user_id']=owner;f.public_value={'owner':owner,'nested':[]}
            if owner=='bob':f.public_value['note']=None
            replacement=Mock(return_value=False);active=[f.update];provider=Mock(side_effect=lambda active=active:active[0])
            def clock(active=active,replacement=replacement,index=index):active[0]=replacement;return 200.9+index
            f.clock.side_effect=clock;forbidden=[Mock(side_effect=AssertionError('unreachable '+owner+' capability')) for unused in range(14)]
            tasks=LegacyWorkerTasks(provider,f.clock,LegacyWorkerTaskPorts(*forbidden[:6]))
            refresh=LegacyWorkerRefresh(LegacyRefreshRecords(f.public,provider,forbidden[6],forbidden[7]),LegacyRefreshTransfer(*forbidden[8:12]),LegacyRefreshArtifacts(*forbidden[12:14]),f.clock)
            for callback in [f.update,replacement,provider,f.public,f.clock,*forbidden]:callback.assert_not_called()
            self.assertEqual(f.events,[]);instances.append((owner,f,replacement,provider,forbidden,tasks,refresh))
        for name in ['run_worker_dataset_generation_task','run_worker_training_task','refresh_worker_training_task','update_training_task','public_training_task']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected root dependency')))
        self.stack.enter_context(patch('time.time',side_effect=AssertionError('unexpected global clock')));counts=[0,0]
        for index in [1,0,1,0]:
            owner,f,replacement,provider,forbidden,tasks,refresh=instances[index];before=copy.deepcopy(f.task);nested=f.public_value['nested']
            if counts[index]==0:
                self.assertIsNone(tasks.run_worker_dataset_generation_task(owner,PoisonValue()));f.update.assert_called_once();replacement.assert_not_called()
            else:
                self.assertIsNone(tasks.run_worker_training_task(owner,PoisonValue(),PoisonValue()));f.update.assert_called_once();replacement.assert_called_once()
            writer=f.update if counts[index]==0 else replacement;self.assertEqual(writer.call_args.args,(owner,));self.assertEqual(writer.call_args.kwargs['completed_at'],200+index)
            self.assertEqual(writer.call_args.kwargs['status'],'failed');counts[index]+=1
            result=refresh.refresh_worker_training_task(f.task,include_artifacts=PoisonValue());self.assertIs(result,f.public_value);self.assertIs(result['nested'],nested);self.assertEqual(result['owner'],owner)
            self.assertIs(result['executor_retired'],True);self.assertIs(result['remote_refresh_retired'],True);self.assertEqual(f.task,before)
            if owner=='bob':self.assertIsNone(result['note'])
            for callback in forbidden:callback.assert_not_called()
        for owner,f,replacement,provider,forbidden,tasks,refresh in instances:
            self.assertEqual(provider.call_count,2);self.assertEqual(f.clock.call_count,2);self.assertEqual(f.public.call_count,2);self.assertEqual(f.update.call_count,1);self.assertEqual(replacement.call_count,1)


    def test_settlement_provider_failure_precedes_clock_and_is_not_retried(self):
        from local_inspection_service.training.legacy_worker_tasks import LegacyWorkerTaskPorts,LegacyWorkerTasks
        for kind in ['dataset','training']:
            with self.subTest(kind=kind):
                f=RetiredFlowFixture();error=OSError('provider');hits=[]
                def provider():
                    hits.append(1)
                    if len(hits)==1:raise error
                    return f.update
                forbidden=[Mock(side_effect=AssertionError('retired')) for unused in range(6)]
                service=LegacyWorkerTasks(provider,f.clock,LegacyWorkerTaskPorts(*forbidden))
                with self.assertRaises(BaseException) as caught:
                    if kind=='dataset':service.run_worker_dataset_generation_task('job',PoisonValue())
                    else:service.run_worker_training_task('job',PoisonValue(),PoisonValue())
                self.assertIs(caught.exception,error);self.assertEqual(hits,[1]);f.clock.assert_not_called();f.update.assert_not_called()
                for callback in forbidden:callback.assert_not_called()

    def test_noncallable_settlement_target_still_evaluates_clock_before_failure(self):
        for kind in ['dataset','training']:
            with self.subTest(kind=kind):
                self.f=self.fixture();f=self.f;later=Mock();self.api.update_training_task=None
                def clock():self.api.update_training_task=later;return 42.9
                f.clock.side_effect=clock
                with self.assertRaises(TypeError):self.settle(kind)
                f.clock.assert_called_once();later.assert_not_called();f.update.assert_not_called();self.assert_hidden(f)


if __name__=='__main__':unittest.main()
