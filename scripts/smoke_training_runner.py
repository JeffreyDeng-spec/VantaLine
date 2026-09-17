"""Offline training runner and submission contracts; no real processes, models or requests."""
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.model_profiles.snapshots import freeze_record


class Resolver:
    def __init__(self):
        self.version=1;self.value=ContextVar('runner-snapshot',default=None);self.scopes=[];self.records=[]
    def current_snapshot(self):return self.value.get()
    def snapshot_for_record(self,record):self.records.append(record);return {'pipeline':{'version':self.version}}
    @contextmanager
    def scope(self,value=None):
        self.scopes.append(copy.deepcopy(value));token=self.value.set(value)
        try:yield
        finally:self.value.reset(token)


class Fixture:
    def __init__(self,root):
        self.root=Path(root);self.resolver=Resolver();self.events=[];self.updates=[];self.saved=[];self.threads={}
        self.binding={'job_id':'binding-object','model_profiles':{'pipeline':{'version':7,'secret_ref':'fixture-ref','prompt_version':'historical'}}}
        self.task={'job_id':'job','action':'generate_samples','owner_user_id':'alice','epochs':3,'image_size':640}
        self.dataset={'dataset_dir':str(self.root/'generated'),'dataset_yaml':str(self.root/'generated/dataset.yaml'),'manifest_path':'synthetic-manifest'}
        self.find=Mock(side_effect=lambda job:self.event('find',job) or self.binding)
        self.path=Mock(side_effect=lambda job:self.event('path',job) or self.root/(job+'.json'))
        self.load=Mock(side_effect=lambda path:self.event('load',path) or self.task)
        self.update=Mock(side_effect=self.updated)
        self.sync=Mock(side_effect=lambda job:self.event('sync',job))
        self.mode=Mock(side_effect=lambda:self.event('mode') or 'local')
        self.resolve=Mock(side_effect=lambda value:self.event('resolve',value) or (Path(value) if value else self.root/'missing.yaml'))
        self.generate=Mock(side_effect=lambda task:self.event('generate',task) or self.dataset)
        self.runpod=Mock(side_effect=lambda *args:self.event('runpod',*args))
        self.remote=Mock(side_effect=lambda *args:self.event('remote',*args))
        self.output=Mock(side_effect=lambda *args:self.event('output',*args) or self.root/'runs')
        self.base=Mock(side_effect=lambda:self.event('base') or self.root/'base.pt')
        self.device=Mock(return_value='cpu');self.cli=Mock(return_value='fake-yolo')
        self.progress=Mock(side_effect=lambda *args:self.event('parse',*args))
        self.process=Mock(pid=123,returncode=0);self.process.poll.return_value=0
        self.popen=Mock(side_effect=lambda *args,**kwargs:self.event('popen',args,kwargs) or self.process)
        self.sleep=Mock(side_effect=lambda delay:self.event('sleep',delay));self.warmup=Mock(side_effect=lambda *args:self.event('warmup',*args))
        self.save=Mock(side_effect=self.save_record);self.public=Mock(side_effect=lambda task:self.event('public',task) or {'public_id':task['job_id']})
        self.estimate=Mock(side_effect=lambda *args,**kwargs:self.event('estimate',args,kwargs) or {'estimated_seconds':1})
        self.ocr=Mock(side_effect=lambda item:bool(item.get('ocr')))
        self.background=Mock(side_effect=lambda *args:self.event('background',*args) or 'background')
        self.thread=Mock();self.thread.start.side_effect=lambda:self.event('start',dict(self.threads))
        self.thread_factory=Mock(side_effect=lambda *args,**kwargs:self.event('thread',args,kwargs) or self.thread)
    def event(self,name,*args):self.events.append((name,args,copy.deepcopy(self.resolver.current_snapshot())))
    def updated(self,job,**values):self.event('update',job,values);self.updates.append(values);return {'job_id':job,**values}
    def save_record(self,task):self.event('save',task);freeze_record(lambda:self.resolver,task);self.saved.append(task)
    def bind(self,api,stack):
        values={'model_profile_service':self.resolver,'find_training_task':self.find,'training_task_path':self.path,'load_training_task':self.load,
            'update_training_task':self.update,'sync_training_state_from_task':self.sync,'training_executor_mode':self.mode,'resolve_service_path':self.resolve,
            'generate_training_dataset':self.generate,'run_runpod_training_task':self.runpod,'run_remote_training_task':self.remote,
            'output_write_dir_for_owner':self.output,'detect_base_model':self.base,'yolo_inference_device':self.device,'yolo_cli_command':self.cli,
            'parse_yolo_epoch_progress':self.progress,'start_yolo_warmup':self.warmup,'TRAINING_TASKS_DIR':self.root,'APP_DIR':self.root/'app',
            'save_training_task':self.save,'public_training_task':self.public,'training_estimate':self.estimate,'accessory_uses_ocr':self.ocr,
            'selected_background_set_id':self.background,'_training_task_threads':self.threads}
        for name,value in values.items():stack.enter_context(patch.object(api,name,value))
        stack.enter_context(patch.object(subprocess,'Popen',self.popen));stack.enter_context(patch('time.sleep',self.sleep))


class TrainingRunnerContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start()
        cls.runtime=tempfile.TemporaryDirectory(prefix='training-runner-root-');root=Path(cls.runtime.name)
        (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server;cls.original_progress=staticmethod(server.parse_yolo_epoch_progress);cls.original_cli=staticmethod(server.yolo_cli_command)
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.f=Fixture(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-runner-')));self.f.bind(self.api,self.stack)
        token=self.api._request_user.set(None);self.addCleanup(self.api._request_user.reset,token)
        self.stack.enter_context(patch('requests.request',side_effect=AssertionError('unexpected network')))
        self.stack.enter_context(patch('os.kill',side_effect=AssertionError('unexpected process signal')))

    def test_binding_and_task_load_are_distinct_snapshot_preserved_and_keyword_call(self):
        api=self.api;f=self.f;original=copy.deepcopy(f.binding);f.resolver.version=99
        api.run_training_task(job_id='job')
        self.assertEqual([e[0] for e in f.events[:3]],['find','path','load']);f.find.assert_called_once_with('job')
        f.path.assert_called_once_with('job');f.load.assert_called_once_with(f.root/'job.json');f.generate.assert_called_once_with(f.task)
        self.assertEqual(f.resolver.scopes,[original['model_profiles']]);self.assertEqual(f.binding,original);self.assertEqual(f.resolver.records,[])
        self.assertTrue(all(e[2]==original['model_profiles'] for e in f.events[1:]));self.assertIsNone(f.resolver.current_snapshot())
        self.assertEqual([u['status'] for u in f.updates],['running','completed']);f.sync.assert_called_once_with('job')
        f.popen.assert_not_called();f.runpod.assert_not_called();f.remote.assert_not_called()

    def test_missing_resolver_find_and_load_fail_before_failure_updates(self):
        api=self.api;f=self.f
        with patch.object(api,'model_profile_service',None):
            with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'):api.run_training_task('job')
        f.find.assert_not_called();f.load.assert_not_called();f.update.assert_not_called()
        f.find.side_effect=RuntimeError('find')
        with self.assertRaisesRegex(RuntimeError,'find'):api.run_training_task('job')
        f.load.assert_not_called();f.update.assert_not_called();self.assertEqual(f.resolver.scopes,[])
        f.find.side_effect=lambda job:f.binding;f.load.side_effect=RuntimeError('load')
        with self.assertRaisesRegex(RuntimeError,'load'):api.run_training_task('job')
        f.update.assert_not_called();f.sync.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())
        f.load.side_effect=None;f.load.return_value=None;api.run_training_task('job');f.update.assert_not_called()

    def test_empty_none_and_ambient_snapshots_restore_after_run(self):
        api=self.api;f=self.f
        f.binding={'model_profiles':{}};api.run_training_task('job');self.assertEqual(f.resolver.scopes,[{}]);self.assertEqual(f.resolver.records,[])
        f.binding={'model_profiles':None};ambient={'pipeline':{'version':20}}
        with f.resolver.scope(ambient):
            api.run_training_task('job');self.assertIs(f.resolver.current_snapshot(),ambient)
        self.assertEqual(f.resolver.scopes[-1],ambient)
        f.resolver.version=30;api.run_training_task('job');self.assertEqual(f.resolver.scopes[-1],{'pipeline':{'version':30}})
        self.assertIs(f.resolver.records[-1],f.binding);self.assertIsNone(f.resolver.current_snapshot())

    def test_dataset_exists_twice_and_generation_precedes_executor_dispatch(self):
        api=self.api;f=self.f;yaml=f.root/'selected/dataset.yaml';yaml.parent.mkdir();yaml.write_text('synthetic')
        f.task.update(dataset_yaml=str(yaml),manifest_path='raw-manifest');f.mode.side_effect=None;f.mode.return_value='runpod'
        api.run_training_task('job');f.generate.assert_not_called();f.runpod.assert_not_called();f.remote.assert_not_called()
        self.assertEqual(f.updates[1]['dataset_dir'],str(yaml.parent));self.assertEqual(f.updates[1]['progress'],74)
        self.assertEqual(f.updates[-1]['manifest_path'],'raw-manifest')
        changing=Mock();changing.exists.side_effect=[True,False];f.resolve.side_effect=None;f.resolve.return_value=changing
        f.generate.reset_mock();api.run_training_task('job');self.assertEqual(changing.exists.call_count,2);f.generate.assert_called_once_with(f.task)

    def test_executor_first_runpod_and_second_remote_read(self):
        api=self.api;f=self.f;f.task['action']='train_model';f.mode.side_effect=['runpod']
        api.run_training_task('job');f.mode.assert_called_once();f.runpod.assert_called_once_with('job',f.task,f.dataset)
        f.sync.assert_not_called();f.popen.assert_not_called()
        f.mode.reset_mock();f.mode.side_effect=['local','remote'];api.run_training_task('job')
        self.assertEqual(f.mode.call_count,2);f.remote.assert_called_once_with('job',f.task,f.dataset);f.popen.assert_not_called()

    def test_generation_and_executors_unknown_outcome_never_retry_or_fall_through(self):
        for failing, modes in [('generate',['local']),('runpod',['runpod']),('remote',['local','remote'])]:
            with self.subTest(failing=failing), ExitStack() as stack:
                f=Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='training-no-retry-')))
                f.bind(self.api,stack);f.task['action']='train_model';f.mode.side_effect=modes
                # A retry would succeed, so terminal failure alone cannot hide a second call.
                getattr(f,failing).side_effect=[RuntimeError('unknown outcome'),f.dataset]
                self.api.run_training_task('job')
                f.generate.assert_called_once_with(f.task)
                for name in ('runpod','remote'):
                    executor=getattr(f,name)
                    if name==failing:executor.assert_called_once_with('job',f.task,f.dataset)
                    else:executor.assert_not_called()
                self.assertEqual(f.mode.call_count,len(modes))
                self.assertEqual([u['status'] for u in f.updates],['running','failed'])
                self.assertEqual(f.updates[-1]['error'],'unknown outcome')
                self.assertEqual(f.update.call_count,2);f.sync.assert_called_once_with('job')
                for local in (f.output,f.base,f.device,f.cli,f.popen,f.progress,f.sleep,f.warmup):local.assert_not_called()
                self.assertEqual(f.resolver.scopes,[f.binding['model_profiles']])
                settlements=[e for e in f.events if e[0] in {'update','sync'}]
                self.assertEqual([e[0] for e in settlements],['update','update','sync'])
                self.assertTrue(all(e[2]==f.binding['model_profiles'] for e in settlements))
                self.assertIsNone(f.resolver.current_snapshot())

    def test_local_cpu_gpu_command_exact_process_and_terminal_state(self):
        api=self.api;f=self.f;f.task.update(action='train_model',epochs=900,image_size=100,model_variant='yolo_ocr')
        for device,code,cpu in [(' CPU ',0,True),('0',3,False)]:
            f.device.return_value=device;f.process.returncode=code;f.popen.reset_mock();f.warmup.reset_mock();f.progress.reset_mock();f.updates.clear()
            api.run_training_task('job');f.popen.assert_called_once();args,kwargs=f.popen.call_args
            self.assertEqual(args[0],['fake-yolo','detect','train',f'model={f.root / "base.pt"}',f'data={f.dataset["dataset_yaml"]}',
                'imgsz=320','epochs=500','batch=1' if cpu else 'batch=0.72',f'device={device}','cache=False' if cpu else 'cache=ram','workers=0',
                'amp=False' if cpu else 'amp=True','patience=25','optimizer=auto','mosaic=0.0','mixup=0.0','copy_paste=0.0',
                'plots=False' if cpu else 'plots=True',f'project={f.root / "runs"}','name=job','exist_ok=True'])
            self.assertEqual(kwargs['cwd'],str(f.root/'app'));self.assertEqual(kwargs['stderr'],subprocess.STDOUT);self.assertTrue(kwargs['text'])
            self.assertTrue(kwargs['stdout'].closed);self.assertEqual(kwargs['stdout'].name,str(f.root/'job.log'))
            self.assertEqual(f.updates[-1]['status'],'completed' if code==0 else 'failed');self.assertEqual(f.updates[-1]['return_code'],code)
            self.assertEqual(f.updates[-1]['current_epoch'],500 if code==0 else 0);f.progress.assert_called_once_with(f.root/'job.log',500)
            if code==0:f.warmup.assert_called_once_with('training_completed',['trained_job__yolo_ocr'])
            else:f.warmup.assert_not_called()
        f.process.terminate.assert_not_called();f.process.kill.assert_not_called();f.sleep.assert_not_called()

    def test_poll_parse_sleep_order_duplicate_epochs_and_last_failure_epoch(self):
        api=self.api;f=self.f;f.task.update(action='train_model',epochs=10);f.process.poll.side_effect=[None,None,0];f.process.returncode=2
        values=iter([(2,10),(2,10),(3,10)])
        f.progress.side_effect=lambda *args:f.event('parse',*args) or next(values)
        def poll():f.event('poll');return next(polls)
        polls=iter([None,None,0]);f.process.poll.side_effect=poll;api.run_training_task('job')
        self.assertEqual([e[0] for e in f.events if e[0] in {'poll','parse','sleep'}],['poll','parse','sleep','poll','parse','sleep','poll','parse'])
        self.assertEqual([u['current_epoch'] for u in f.updates if 'current_epoch' in u],[0,2,3])
        self.assertEqual(f.updates[-2]['progress'],85);self.assertEqual(f.updates[-1]['status'],'failed')
        self.assertEqual(f.sleep.call_args_list,[((5,),),((5,),)])

    def test_failures_after_success_sync_and_warmup_keep_original_settlement(self):
        api=self.api;f=self.f;f.task['action']='train_model';f.sync.side_effect=[RuntimeError('sync failed'),None]
        api.run_training_task('job');self.assertEqual([u['status'] for u in f.updates if 'status' in u][-2:],['completed','failed'])
        self.assertEqual(f.updates[-1]['error'],'sync failed');self.assertEqual(f.sync.call_count,2);f.warmup.assert_not_called()
        f.sync.side_effect=None;f.sync.reset_mock();f.warmup.side_effect=RuntimeError('warmup failed');api.run_training_task('job')
        self.assertEqual(f.updates[-1]['error'],'warmup failed');self.assertEqual(f.sync.call_count,2)
        f.generate.side_effect=RuntimeError('generation failed');f.update.side_effect=lambda job,**values:(_ for _ in ()).throw(ValueError('failed write')) if values.get('status')=='failed' else f.updated(job,**values)
        with self.assertRaisesRegex(ValueError,'failed write'):api.run_training_task('job')
        self.assertIsNone(f.resolver.current_snapshot());f.process.terminate.assert_not_called();f.process.kill.assert_not_called()



    def test_submission_fields_order_duplicate_ids_and_frozen_binding(self):
        api=self.api;f=self.f
        request=api.TrainingStartRequest(selected_accessory_ids=['ignored'],sample_count=0,epochs=999,image_size=1,train_mode='yolo_ocr',
            approved_preview_id='approved',pipeline_task_id=' '+('p'*140)+' ',pipeline_task_name=' '+('n'*170)+' ')
        selected=[{'id':1,'ocr':True},{'id':'1','ocr':False}]
        api._request_user.set({'id':'alice','username':'Alice'})
        with patch.object(threading,'Thread',f.thread_factory),patch('uuid.uuid4',return_value=SimpleNamespace(hex='abcdef1234')),patch('time.time',side_effect=[10.9,11.9]):
            result=api.enqueue_training_task(request,selected,'generate_samples')
        job='samples_10_abcdef';task=f.saved[0]
        self.assertEqual(result,{'public_id':job});self.assertIs(f.public.call_args.args[0],task)
        self.assertEqual([e[0] for e in f.events],['estimate','background','save','thread','start','public'])
        f.estimate.assert_called_once_with(1,include_training=False,include_generation=True,epochs=500,image_size=320,selected_count=2,train_mode='yolo_ocr')
        self.assertEqual(task['created_at'],11);self.assertEqual(task['selected_accessory_ids'],[1,'1'])
        self.assertEqual(task['required_accessory_counts'],{'1':1});self.assertEqual(task['accessory_class_map'],{'0':'1','1':'1'})
        self.assertEqual(task['class_accessory_map'],{'1':1});self.assertEqual(task['ocr_accessory_ids'],['1'])
        self.assertEqual((task['owner_user_id'],task['owner_username']),('alice','Alice'))
        self.assertEqual(task['pipeline_task_id'],'p'*128);self.assertEqual(task['pipeline_task_name'],'n'*160)
        self.assertEqual((task['background_set_id'],task['approved_preview_id'],task['preview_pose_family_policy']),('background','approved','auto'))
        f.thread_factory.assert_called_once_with(target=api.run_training_task,args=(job,),name='training-task-'+job,daemon=True)
        self.assertIs(f.threads[job],f.thread);self.assertIs(next(e for e in f.events if e[0]=='start')[1][0][job],f.thread)
        f.thread.start.assert_called_once();self.assertEqual(task['model_profiles'],{'pipeline':{'version':1}})
        f.binding=task;f.task=task;f.resolver.version=200
        f.thread_factory.call_args.kwargs['target'](*f.thread_factory.call_args.kwargs['args'])
        self.assertEqual(f.resolver.scopes[-1],{'pipeline':{'version':1}});self.assertEqual(task['model_profiles'],{'pipeline':{'version':1}})

    def test_submission_dataset_merge_late_owner_and_late_target(self):
        api=self.api;f=self.f;request=api.TrainingStartRequest(selected_accessory_ids=[],sample_count=5,epochs=2,image_size=480)
        first=Mock();replacement=Mock();api._request_user.set({'id':'alice','username':'Alice'})
        def background(value,user):
            self.assertEqual(user['id'],'alice');api._request_user.set({'id':'bob','username':'Bob'});return 'selected'
        f.background.side_effect=background
        def save(task):f.save_record(task);api.run_training_task=first;return {'replacement':'ignored'}
        f.save.side_effect=save
        def thread_factory(*args,**kwargs):
            self.assertIs(kwargs['target'],first);api.run_training_task=replacement;return f.thread
        f.thread_factory.side_effect=thread_factory
        dataset={'id':'dataset','sample_count':40000,'dataset_dir':'dir','dataset_yaml':'yaml','manifest_path':'manifest','display_name':'name'}
        with patch.object(api,'run_training_task',Mock()),patch.object(threading,'Thread',f.thread_factory):
            api.enqueue_training_task(request,[],'train_model',dataset)
            self.assertIs(f.thread_factory.call_args.kwargs['target'],first);self.assertIs(api.run_training_task,replacement)
        task=f.saved[0];self.assertEqual(task['owner_user_id'],'bob');self.assertEqual(task['sample_count'],20000)
        self.assertEqual((task['source_dataset_id'],task['dataset_yaml'],task['label'],task['candidate_name']),('dataset','yaml','name','name'))
        f.estimate.assert_called_once_with(20000,include_training=True,include_generation=False,epochs=2,image_size=480,selected_count=0,train_mode='yolo_ocr')
        self.assertNotIn('replacement',task);first.assert_not_called();replacement.assert_not_called()
        with self.assertRaises(TypeError):api.enqueue_training_task(request,[],'train_model',{'id':'bad'})

    def test_submission_failure_residue_and_no_retry(self):
        api=self.api;f=self.f;request=api.TrainingStartRequest(selected_accessory_ids=[])
        for stage in ('save','thread','start','public'):
            f.saved.clear();f.threads.clear()
            for callback in (f.save,f.thread_factory,f.thread.start,f.public):callback.reset_mock();callback.side_effect=None
            f.save.side_effect=f.save_record;f.thread_factory.return_value=f.thread;f.public.return_value={}
            target={'save':f.save,'thread':f.thread_factory,'start':f.thread.start,'public':f.public}[stage]
            target.side_effect=RuntimeError(stage)
            with patch.object(threading,'Thread',f.thread_factory),patch('uuid.uuid4',return_value=SimpleNamespace(hex='abcdef')),patch('time.time',return_value=10):
                with self.assertRaisesRegex(RuntimeError,stage):api.enqueue_training_task(request,[],'train_model')
            f.save.assert_called_once()
            self.assertEqual(len(f.saved),0 if stage=='save' else 1)
            self.assertEqual(f.thread_factory.call_count,0 if stage=='save' else 1)
            self.assertEqual(f.thread.start.call_count,0 if stage in {'save','thread'} else 1)
            self.assertEqual(f.public.call_count,1 if stage=='public' else 0)
            self.assertEqual(list(f.threads),['train_10_abcdef'] if stage in {'start','public'} else [])

    def test_process_creation_and_progress_errors_do_not_restart_or_terminate(self):
        api=self.api;f=self.f;f.task['action']='train_model'
        f.popen.side_effect=RuntimeError('process-start');api.run_training_task('job')
        self.assertEqual(f.updates[-1]['error'],'process-start');f.popen.assert_called_once();f.sync.assert_called_once()
        f.popen.reset_mock();f.popen.side_effect=None;f.popen.return_value=f.process;f.progress.side_effect=RuntimeError('progress')
        api.run_training_task('job');self.assertEqual(f.updates[-1]['error'],'progress');f.popen.assert_called_once()
        f.process.terminate.assert_not_called();f.process.kill.assert_not_called()
        f.generate.side_effect=RuntimeError('generate');f.sync.side_effect=ValueError('failure-sync')
        with self.assertRaisesRegex(ValueError,'failure-sync'):api.run_training_task('job')
        self.assertIsNone(f.resolver.current_snapshot())

    def test_snapshot_isolation_across_async_threads(self):
        import asyncio
        api=self.api;f=self.f;barrier=threading.Barrier(2);observed=[]
        bindings={name:{'model_profiles':{'pipeline':{'version':version}}} for name,version in [('alice',10),('bob',20)]}
        tasks={name:{'job_id':name,'action':'generate_samples'} for name in bindings}
        f.find.side_effect=lambda job:bindings[job];f.load.side_effect=lambda path:tasks[path.stem]
        def generate(task):
            barrier.wait(timeout=10);observed.append((task['job_id'],f.resolver.current_snapshot()['pipeline']['version']));return f.dataset
        f.generate.side_effect=generate
        async def worker(name):
            token=api._request_user.set({'id':name})
            try:
                with f.resolver.scope({'pipeline':{'version':'ambient-'+name}}):
                    await asyncio.to_thread(api.run_training_task,name)
                    self.assertEqual(f.resolver.current_snapshot()['pipeline']['version'],'ambient-'+name)
                    self.assertEqual(api._request_user.get(),{'id':name})
            finally:api._request_user.reset(token)
        async def check():await asyncio.gather(worker('alice'),worker('bob'))
        asyncio.run(check());self.assertEqual(sorted(observed),[('alice',10),('bob',20)])
        self.assertIsNone(f.resolver.current_snapshot());self.assertIsNone(api._request_user.get());f.popen.assert_not_called()

    def test_progress_parser_tail_window_regex_and_exception_boundaries(self):
        path=self.f.root/'progress.log';read=self.original_progress
        self.assertIsNone(read(path,10))
        path.write_bytes(b'bad \xff\n1/10 done\n2/20 other\n2/10 done\n3/10')
        self.assertEqual(read(path,10),(2,10))
        path.write_bytes(b'15/10 done\n10000/10 ignored\n0/10 ignored\n1/0 ignored\n')
        self.assertEqual(read(path,10),(15,10));self.assertIsNone(read(path,20))
        path.write_bytes(b'8/10 old '+b'x'*131072);self.assertIsNone(read(path,10))
        with path.open('ab') as stream:stream.write(b'\n9/10 latest\n')
        self.assertEqual(read(path,0),(9,10))
        with patch.object(Path,'exists',side_effect=OSError('exists')):
            with self.assertRaisesRegex(OSError,'exists'):read(path,10)
        with patch.object(Path,'open',side_effect=PermissionError('open')):self.assertIsNone(read(path,10))

    def test_cli_resolution_precedence_and_fallback_paths(self):
        import shutil
        fn=self.original_cli
        with patch.dict(os.environ,{},clear=True),patch.object(shutil,'which',return_value='discovered') as which:
            os.environ['INSPECTION_YOLO_COMMAND']=' custom cli ';self.assertEqual(fn(),'custom cli');which.assert_not_called()
            os.environ['INSPECTION_YOLO_COMMAND']=' ';self.assertEqual(fn(),'discovered');which.assert_called_once_with('yolo')
            which.return_value=None;os.environ['VIRTUAL_ENV']=str(self.f.root/'virtual');paths=[]
            def exists(path):paths.append(path);return len(paths)==2
            with patch.object(Path,'exists',exists):self.assertEqual(fn(),str(Path(sys.executable).parent/'yolo'))
            self.assertEqual(paths,[self.f.root/'virtual/bin/yolo',Path(sys.executable).parent/'yolo'])
            with patch.object(Path,'exists',return_value=False):self.assertEqual(fn(),'yolo')
            which.side_effect=RuntimeError('which')
            with self.assertRaisesRegex(RuntimeError,'which'):fn()

    def test_independent_runners_submission_and_zero_call_construction(self):
        from local_inspection_service.training.runner import TrainingRunner,TrainingRunnerRecords,TrainingRunnerPaths,TrainingDatasetExecution,TrainingLocalExecution
        from local_inspection_service.training.submission import TrainingSubmission,TrainingSubmissionPolicy,TrainingSubmissionIdentity,TrainingSubmissionRecords,TrainingSubmissionThreads
        from local_inspection_service.runtime.identity import RequestIdentity
        other=Fixture(self.f.root/'other');other.root.mkdir();other.binding['model_profiles']['pipeline']['version']=8
        def compose(f):
            provider=Mock(side_effect=lambda:f.resolver)
            runner=TrainingRunner(TrainingRunnerRecords(f.find,f.path,lambda:f.load,lambda:f.update,f.sync),
                TrainingRunnerPaths(lambda:f.resolve,lambda:f.root,lambda:f.root/'app',lambda:f.output),
                TrainingDatasetExecution(f.mode,f.generate,f.runpod,f.remote),TrainingLocalExecution(f.base,f.device,f.cli,lambda:f.popen,f.progress,lambda:f.warmup),provider)
            identity=RequestIdentity()
            def owner():
                user=identity.get();return {'owner_user_id':user['id'],'owner_username':user.get('username','')} if user else {}
            submission=TrainingSubmission(TrainingSubmissionPolicy(lambda:f.estimate,f.ocr),TrainingSubmissionIdentity(identity.get,owner,lambda:f.background),
                TrainingSubmissionRecords(f.save,f.public),TrainingSubmissionThreads(lambda:runner.run_training_task,f.thread_factory,lambda:f.threads))
            provider.assert_not_called();self.assertEqual(f.events,[]);self.assertEqual(f.resolver.scopes,[])
            return runner,submission,identity,provider
        first,first_submission,first_identity,first_provider=compose(self.f)
        second,second_submission,second_identity,second_provider=compose(other)
        first.run_training_task('job');second.run_training_task(job_id='job')
        first_provider.assert_called_once_with();second_provider.assert_called_once_with()
        self.assertEqual(self.f.resolver.scopes,[self.f.binding['model_profiles']]);self.assertEqual(other.resolver.scopes,[other.binding['model_profiles']])
        self.assertIsNone(self.f.resolver.current_snapshot());self.assertIsNone(other.resolver.current_snapshot())
        request=self.api.TrainingStartRequest(selected_accessory_ids=[])
        for f,submission,identity,name in [(self.f,first_submission,first_identity,'alice'),(other,second_submission,second_identity,'bob')]:
            with identity.bind({'id':name}):submission.enqueue_training_task(request,[],'generate_samples')
            self.assertEqual(f.saved[0]['owner_user_id'],name);self.assertIs(f.thread_factory.call_args.kwargs['target'],first.run_training_task if name=='alice' else second.run_training_task)
        self.assertEqual(len(self.f.threads),1);self.assertEqual(len(other.threads),1)
        first_provider.side_effect=None;first_provider.return_value=None;self.f.find.reset_mock();self.f.update.reset_mock()
        with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'):first.run_training_task('job')
        self.f.find.assert_not_called();self.f.update.assert_not_called()


    def test_runner_and_submission_capture_callbacks_before_arguments(self):
        api=self.api
        for stage in ('load','resolve-yaml','resolve-dir','output','start','warmup','estimate','background','update'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(stage=stage,mode=mode),ExitStack() as stack:
                    f=Fixture(self.f.root/(stage+'-'+mode));f.root.mkdir();f.bind(api,stack);events=[]
                    field={'load':'load_training_task','resolve-yaml':'resolve_service_path','resolve-dir':'resolve_service_path',
                        'output':'output_write_dir_for_owner','start':'Popen','warmup':'start_yolo_warmup','estimate':'training_estimate',
                        'background':'selected_background_set_id','thread':'Thread','update':'update_training_task'}[stage]
                    target=subprocess if stage=='start' else (threading if stage=='thread' else api)
                    original=getattr(target,field)
                    if stage=='thread':original=f.thread_factory
                    def callback(label):
                        def call(*args,**kwargs):events.append(label);return original(*args,**kwargs)
                        return call
                    stack.enter_context(patch.object(target,field,callback('A')))
                    prior_done=[]
                    def before():
                        if not prior_done:
                            prior_done.append(True)
                            if mode!='ordinary':setattr(target,field,callback('B') if mode=='prior' else None)
                    def argument():events.append('argument');setattr(target,field,callback('C'))
                    f.task['action']='train_model' if stage in ('output','start','warmup') else 'generate_samples'
                    if stage=='load':
                        original_path=f.path.side_effect
                        f.path.side_effect=lambda value:argument() or original_path(value)
                    elif stage in ('resolve-yaml','resolve-dir','output'):
                        key={'resolve-yaml':'dataset_yaml','resolve-dir':'dataset_dir','output':'owner_user_id'}[stage]
                        counts=[]
                        class Task(dict):
                            def get(self,name,*args):
                                if name==key:
                                    counts.append(True)
                                    if stage=='resolve-dir' and len(counts)==1:before()
                                    if stage!='resolve-dir' or len(counts)==2:argument()
                                return super().get(name,*args)
                        if stage=='resolve-dir':
                            path=f.root/'dataset.yaml';path.write_text('synthetic');f.task.update(dataset_yaml=str(path),dataset_dir=str(f.root/'dataset'))
                        f.task=Task(f.task)
                    elif stage=='start':
                        class AppPath:
                            def __str__(self):argument();return str(f.root/'app')
                        stack.enter_context(patch.object(api,'APP_DIR',AppPath()))
                    elif stage=='warmup':
                        class Variant(str):
                            def __format__(self,spec):argument();return super().__format__(spec)
                        class Mode:
                            def __str__(self):return Variant('yolo')
                        f.task['model_variant']=Mode()
                    elif stage=='update':
                        calls=[]
                        def clock():
                            calls.append(True)
                            if len(calls)==1:argument()
                            return 42.9
                        stack.enter_context(patch('time.time',side_effect=clock))
                    elif stage=='estimate':
                        class Selected(list):
                            def __len__(self):argument();return super().__len__()
                        selected=Selected([])
                    elif stage=='background':
                        class Identity:
                            def get(self):argument();return None
                        stack.enter_context(patch.object(api,'_request_user',Identity()))
                    previous={'load':f.find,'resolve-yaml':f.mode,'output':f.generate,'start':f.cli,'warmup':f.sync,'background':f.estimate,'update':f.load}.get(stage)
                    if previous is not None:
                        old_effect=previous.side_effect;old_value=previous.return_value
                        def preceding(*args,**kwargs):before();return old_effect(*args,**kwargs) if callable(old_effect) else old_value
                        previous.side_effect=preceding
                    request=api.TrainingStartRequest(selected_accessory_ids=[])
                    if stage=='estimate':
                        class Size:
                            def __int__(self):before();return 640
                        object.__setattr__(request,'image_size',Size())
                    def invoke():
                        if stage in ('estimate','background'):
                            stack.enter_context(patch.object(threading,'Thread',f.thread_factory))
                            return api.enqueue_training_task(request,selected if stage=='estimate' else [],'generate_samples')
                        return api.run_training_task('job')
                    if mode=='missing' and stage in ('load','estimate','background'):
                        with self.assertRaises(BaseException) as error:invoke()
                        self.assertIs(type(error.exception),TypeError)
                    else:
                        raised=None
                        try:invoke()
                        except BaseException as error:raised=error
                        self.assertIsNone(raised)
                    self.assertIn('argument',events)
                    start=events.index('argument')
                    if mode=='missing':
                        self.assertNotIn('A',events[start+1:]);self.assertNotIn('B',events[start+1:])
                        if stage not in ('load','estimate','background'):
                            self.assertEqual(f.updates[-1]['status'],'failed');self.assertIn('NoneType',f.updates[-1]['error'])
                        if stage=='update':self.assertEqual([v['status'] for v in f.updates],['failed']);self.assertEqual(events[start+1:],['C'])
                        else:self.assertNotIn('C',events[start+1:])
                    else:
                        self.assertEqual(events[start+1],'A' if mode=='ordinary' else 'B')
                        self.assertFalse(any(v.get('status')=='failed' for v in f.updates))


    def test_runner_first_failure_never_repeats_unknown_work(self):
        api=self.api
        for stage in ('find','path','load','mode','mode-second','resolve','generate','output','base','device','cli','popen','progress-loop','progress-final','warmup','sync','sync-generated','runpod','remote'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture(self.f.root/stage);f.root.mkdir();f.bind(api,stack);f.task['action']='train_model'
                failure=OSError('first-only-'+stage);calls=[]
                field={'mode-second':'mode','progress-loop':'progress','progress-final':'progress','sync-generated':'sync'}.get(stage,stage);probe=getattr(f,field)
                if stage=='sync-generated':f.task['action']='generate_samples'
                if stage=='runpod':f.mode.side_effect=lambda:'runpod'
                if stage=='remote':f.mode.side_effect=lambda:'remote'
                if stage=='progress-loop':f.process.poll.side_effect=[None,0]
                original=probe.side_effect;valid=probe.return_value;fail_at=2 if stage=='mode-second' else 1
                def bad(*args,**kwargs):
                    calls.append((args,kwargs))
                    if len(calls)==fail_at:raise failure
                    return original(*args,**kwargs) if callable(original) else valid
                probe.side_effect=bad
                if stage in ('find','path','load'):
                    with self.assertRaises(BaseException) as error:api.run_training_task('job')
                    self.assertIs(error.exception,failure);self.assertEqual(f.updates,[]);f.sync.assert_not_called()
                else:
                    self.assertIsNone(api.run_training_task('job'))
                    self.assertEqual(f.updates[-1]['status'],'failed');self.assertEqual(f.updates[-1]['error'],str(failure))
                    if stage in ('sync','sync-generated','warmup'):self.assertEqual([v.get('status') for v in f.updates][-2:],['completed','failed']);self.assertEqual(f.sync.call_count,2)
                    else:self.assertEqual(f.sync.call_count,1)
                self.assertEqual(probe.call_count,2 if stage in ('mode-second','sync','sync-generated') else 1)
                if stage in ('find','path','load','mode','mode-second','resolve','generate','output','base','device','cli','runpod','remote','sync-generated'):f.popen.assert_not_called()
                if stage not in ('warmup',):f.warmup.assert_not_called()
                f.process.terminate.assert_not_called();f.process.kill.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())

    def test_each_training_update_failure_retains_original_settlement(self):
        api=self.api
        for stage in ('started','existing-dataset','generated','local-ready','pid','epoch','terminal','failure-update','failure-sync'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture(self.f.root/stage);f.root.mkdir();f.bind(api,stack)
                f.task['action']='generate_samples' if stage in ('started','existing-dataset','generated','failure-update','failure-sync') else 'train_model'
                if stage=='existing-dataset':
                    path=f.root/'dataset.yaml';path.write_text('synthetic');f.task['dataset_yaml']=str(path)
                if stage=='epoch':f.process.poll.side_effect=[None,0];f.progress.return_value=(1,3);f.progress.side_effect=None
                initial=OSError('initial-generation');failure=OSError('first-only-'+stage);calls=[]
                if stage in ('failure-update','failure-sync'):f.generate.side_effect=initial
                def should_fail(values):
                    return {'started':values.get('progress')==5,'existing-dataset':values.get('progress')==74,
                        'generated':values.get('status')=='completed','local-ready':values.get('progress')==76,'pid':values.get('progress')==82 and 'training_pid' in values,
                        'epoch':'current_epoch' in values and values.get('status')=='running','terminal':values.get('status')=='completed',
                        'failure-update':values.get('status')=='failed','failure-sync':False}[stage]
                failed=[]
                def update(job,**values):
                    calls.append(dict(values))
                    if should_fail(values) and not failed:failed.append(True);raise failure
                    return f.updated(job,**values)
                f.update.side_effect=update
                if stage=='failure-sync':
                    original=f.sync.side_effect;count=[]
                    def sync(job):
                        count.append(True)
                        if len(count)==1:raise failure
                        return original(job)
                    f.sync.side_effect=sync
                if stage in ('failure-update','failure-sync'):
                    with self.assertRaises(BaseException) as error:api.run_training_task('job')
                    self.assertIs(error.exception,failure)
                    self.assertEqual(f.sync.call_count,int(stage=='failure-sync'))
                else:
                    api.run_training_task('job');self.assertEqual(f.updates[-1]['status'],'failed');self.assertEqual(f.updates[-1]['error'],str(failure));self.assertEqual(f.sync.call_count,1)
                    self.assertEqual(sum(should_fail(value) for value in calls),1)
                self.assertEqual([value.get('status') for value in calls].count('failed'),1)
                f.warmup.assert_not_called();f.process.terminate.assert_not_called();f.process.kill.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())

    def test_submission_first_failures_preserve_publication_residue(self):
        api=self.api
        for stage in ('estimate','ocr','background','owner','save','thread','start','public'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture(self.f.root/stage);f.root.mkdir();f.bind(api,stack);failure=OSError('first-only-'+stage);calls=[]
                stack.enter_context(patch.object(threading,'Thread',f.thread_factory))
                if stage=='owner':probe=stack.enter_context(patch.object(api,'current_owner_fields',return_value={'owner_user_id':'alice'}))
                elif stage=='thread':probe=f.thread_factory
                elif stage=='start':probe=f.thread.start
                else:probe=getattr(f,stage)
                original=probe.side_effect;valid=probe.return_value
                def bad(*args,**kwargs):
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return original(*args,**kwargs) if callable(original) else valid
                probe.side_effect=bad
                with self.assertRaises(BaseException) as error:api.enqueue_training_task(api.TrainingStartRequest(selected_accessory_ids=['a']),[{'id':'a'}],'generate_samples')
                self.assertIs(error.exception,failure);self.assertEqual(probe.call_count,1)
                if stage in ('estimate','ocr','background','owner','save'):self.assertEqual(f.saved,[]);self.assertEqual(f.threads,{});f.thread_factory.assert_not_called();f.thread.start.assert_not_called()
                elif stage=='thread':self.assertEqual(len(f.saved),1);self.assertEqual(f.threads,{});f.thread.start.assert_not_called()
                else:self.assertEqual(len(f.saved),1);self.assertEqual(len(f.threads),1);self.assertIs(next(iter(f.threads.values())),f.thread);self.assertEqual(f.thread.start.call_count,1)
                if stage!='public':f.public.assert_not_called()
                self.assertIsNone(f.resolver.current_snapshot())


    def test_new_runner_getter_failures(self):
        from dataclasses import replace
        api=self.api
        for stage in ('load','resolve','resolve-dir','output','start','warmup','update','estimate','background','tasks','app','target','thread-records'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture(self.f.root/stage);f.root.mkdir();f.bind(api,stack);f.task['action']='train_model';failure=OSError('first-only-'+stage);calls=[]
                stack.enter_context(patch.object(threading,'Thread',f.thread_factory))
                if stage=='resolve-dir':
                    path=f.root/'dataset.yaml';path.write_text('synthetic');f.task.update(dataset_yaml=str(path),dataset_dir=str(f.root/'dataset'))
                runner=api._training_runner;submission=api._training_submission
                owner,group,field,valid={
                    'load':(runner,'records','load',f.load),'resolve':(runner,'paths','resolve',f.resolve),'resolve-dir':(runner,'paths','resolve',f.resolve),
                    'output':(runner,'paths','output',f.output),'start':(runner,'local','start',f.popen),'warmup':(runner,'local','warmup',f.warmup),
                    'update':(runner,'records','update_provider',f.update),'estimate':(submission,'policy','estimate',f.estimate),
                    'background':(submission,'identity','background',f.background),'tasks':(runner,'paths','tasks',f.root),
                    'app':(runner,'paths','app',f.root/'app'),'target':(submission,'threads','target',lambda *a:None),
                    'thread-records':(submission,'threads','records',f.threads),
                }[stage]
                def getter():
                    calls.append(True)
                    if len(calls)==(2 if stage=='resolve-dir' else 1):raise failure
                    return valid
                probe=Mock(side_effect=getter);stack.enter_context(patch.object(owner,group,replace(getattr(owner,group),**{field:probe})))
                def invoke():
                    if owner is submission:return api.enqueue_training_task(api.TrainingStartRequest(selected_accessory_ids=[]),[],'generate_samples')
                    return api.run_training_task('job')
                if stage in ('load','estimate','background','target','thread-records'):
                    with self.assertRaises(BaseException) as error:invoke()
                    self.assertIs(error.exception,failure)
                else:
                    raised=None
                    try:result=invoke()
                    except BaseException as error:raised=error
                    self.assertIsNone(raised);self.assertIsNone(result);self.assertEqual(f.updates[-1]['status'],'failed');self.assertEqual(f.updates[-1]['error'],str(failure))
                    self.assertEqual(f.sync.call_count,2 if stage=='warmup' else 1)
                self.assertEqual(probe.call_count,2 if stage in ('resolve-dir','update') else 1)
                if stage=='load':f.path.assert_not_called();self.assertEqual(f.updates,[])
                if stage=='update':self.assertEqual([v['status'] for v in f.updates],['failed'])
                if stage=='start':f.popen.assert_not_called()
                if stage=='warmup':f.warmup.assert_not_called();self.assertEqual([v.get('status') for v in f.updates][-2:],['completed','failed'])
                if stage in ('estimate','background'):self.assertEqual(f.saved,[]);f.thread_factory.assert_not_called()
                if stage in ('target','thread-records'):self.assertEqual(len(f.saved),1);self.assertEqual(f.threads,{});f.thread.start.assert_not_called();self.assertEqual(f.thread_factory.call_count,int(stage=='thread-records'))
                self.assertIsNone(f.resolver.current_snapshot());f.process.terminate.assert_not_called();f.process.kill.assert_not_called()


    def test_log_reader_first_failures_follow_original_io_boundary(self):
        fn=self.original_progress
        for stage in ('exists','open','enter','seek-end','tell','seek-start','read','decode','close','regex'):
            for failure in (OSError('first-only'),ValueError('first-only'),KeyboardInterrupt('first-only')):
                with self.subTest(stage=stage,failure=type(failure).__name__),ExitStack() as stack:
                    counts={};events=[]
                    def step(name,value=None):
                        events.append(name);counts[name]=counts.get(name,0)+1
                        if name==stage and counts[name]==1:raise failure
                        return value
                    class Bytes:
                        def decode(self,*a,**k):return step('decode',' 1/3 ')
                    class Reader:
                        def __enter__(self):return step('enter',self)
                        def __exit__(self,*a):step('close');return False
                        def seek(self,offset,whence):return step('seek-end' if whence==os.SEEK_END else 'seek-start',0)
                        def tell(self):return step('tell',6)
                        def read(self):return step('read',Bytes())
                    reader=Reader()
                    class Log:
                        def exists(self):return step('exists',True)
                        def open(self,*a,**k):return step('open',reader)
                    import re
                    original=re.findall
                    if stage=='regex':stack.enter_context(patch.object(re,'findall',side_effect=lambda *a,**k:step('regex',original(*a,**k))))
                    swallowed=isinstance(failure,OSError) and stage not in ('exists','regex')
                    if swallowed:self.assertIsNone(fn(Log(),3))
                    else:
                        with self.assertRaises(BaseException) as error:fn(Log(),3)
                        self.assertIs(error.exception,failure)
                    self.assertEqual(counts[stage],1)
                    ordered=['exists','open','enter','seek-end','tell','seek-start','read','decode']
                    if stage in ordered:
                        for later in ordered[ordered.index(stage)+1:]:self.assertNotIn(later,counts)
                    if stage in ('exists','open','enter'):self.assertNotIn('close',counts)
                    else:self.assertEqual(counts.get('close'),1)

    def test_each_update_provider_failure_obeys_settlement_boundary(self):
        from dataclasses import replace
        api=self.api
        cases=[('started',1),('existing',2),('generated',2),('ready',2),('pid',3),('epoch',4),('terminal',4),('failed',2)]
        for stage,fail_at in cases:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture(self.f.root/stage);f.root.mkdir();f.bind(api,stack);failure=OSError('getter-'+stage);calls=[]
                f.task['action']='generate_samples' if stage in ('started','existing','generated','failed') else 'train_model'
                if stage=='existing':path=f.root/'dataset.yaml';path.write_text('synthetic');f.task['dataset_yaml']=str(path)
                if stage=='epoch':f.process.poll.side_effect=[None,0];f.progress.side_effect=None;f.progress.return_value=(1,3)
                if stage=='failed':f.generate.side_effect=OSError('initial')
                def getter():
                    calls.append(True)
                    if len(calls)==fail_at:raise failure
                    return f.update
                probe=Mock(side_effect=getter);runner=api._training_runner
                stack.enter_context(patch.object(runner,'records',replace(runner.records,update_provider=probe)))
                if stage=='failed':
                    with self.assertRaises(BaseException) as error:api.run_training_task('job')
                    self.assertIs(error.exception,failure);f.sync.assert_not_called()
                else:
                    captured=None
                    try:api.run_training_task('job')
                    except BaseException as error:captured=error
                    self.assertIsNone(captured);self.assertEqual(f.updates[-1]['status'],'failed');self.assertEqual(f.updates[-1]['error'],str(failure));self.assertEqual(f.sync.call_count,1)
                self.assertEqual(probe.call_count,fail_at+int(stage!='failed'));self.assertEqual(f.update.call_count,probe.call_count-1)
                f.warmup.assert_not_called();f.process.terminate.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())

    def test_runner_io_and_clock_first_failures(self):
        api=self.api
        for stage in ('log-open','poll','sleep','clock-started','clock-generated','clock-terminal','clock-failed'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture(self.f.root/stage);f.root.mkdir();f.bind(api,stack);failure=OSError('first-only-'+stage);calls=[]
                f.task['action']='generate_samples' if stage in ('clock-started','clock-generated','clock-failed') else 'train_model'
                if stage=='clock-failed':f.generate.side_effect=OSError('initial')
                fail_at=2 if stage in ('clock-generated','clock-terminal','clock-failed') else 1
                def trigger(value):
                    calls.append(True)
                    if len(calls)==fail_at:raise failure
                    return value
                if stage.startswith('clock-'):probe=stack.enter_context(patch('time.time',side_effect=lambda:trigger(42.9)))
                elif stage=='poll':probe=f.process.poll;probe.side_effect=lambda:trigger(0)
                elif stage=='sleep':f.process.poll.side_effect=[None,0];probe=f.sleep;probe.side_effect=lambda value:trigger(None)
                else:
                    original=Path.open;path=f.root/'job.log'
                    def open_log(current,*args,**kwargs):
                        if current==path:trigger(None)
                        return original(current,*args,**kwargs)
                    probe=stack.enter_context(patch.object(Path,'open',open_log))
                if stage=='clock-failed':
                    with self.assertRaises(BaseException) as error:api.run_training_task('job')
                    self.assertIs(error.exception,failure);f.sync.assert_not_called();self.assertEqual([v['status'] for v in f.updates],['running'])
                else:
                    self.assertIsNone(api.run_training_task('job'));self.assertEqual(f.updates[-1]['status'],'failed');self.assertEqual(f.updates[-1]['error'],str(failure));self.assertEqual(f.sync.call_count,1)
                self.assertEqual(len(calls),fail_at+int(stage.startswith('clock-') and stage!='clock-failed'))
                if stage in ('log-open','clock-started','clock-generated','clock-failed'):f.popen.assert_not_called()
                f.warmup.assert_not_called();f.process.terminate.assert_not_called();f.process.kill.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())

    def test_submission_clock_uuid_and_identity_first_failures(self):
        api=self.api
        for stage in ('first-clock','second-clock','uuid','user'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture(self.f.root/stage);f.root.mkdir();f.bind(api,stack);failure=OSError('first-only-'+stage);calls=[]
                stack.enter_context(patch.object(threading,'Thread',f.thread_factory))
                fail_at=2 if stage=='second-clock' else 1
                def trigger(value):
                    calls.append(True)
                    if len(calls)==fail_at:raise failure
                    return value
                if stage.endswith('clock'):stack.enter_context(patch('time.time',side_effect=lambda:trigger(42.9)))
                elif stage=='uuid':
                    import uuid
                    value=uuid.uuid4();stack.enter_context(patch.object(uuid,'uuid4',side_effect=lambda:trigger(value)))
                else:
                    class Identity:
                        def get(self):return trigger(None)
                    stack.enter_context(patch.object(api,'_request_user',Identity()))
                with self.assertRaises(BaseException) as error:api.enqueue_training_task(api.TrainingStartRequest(selected_accessory_ids=[]),[],'generate_samples')
                self.assertIs(error.exception,failure);self.assertEqual(len(calls),fail_at);self.assertEqual(f.saved,[]);self.assertEqual(f.threads,{})
                f.thread_factory.assert_not_called();f.thread.start.assert_not_called();f.public.assert_not_called()

    def test_cli_first_failures_do_not_scan_again(self):
        import shutil
        fn=self.original_cli
        for stage in ('configured','virtual-env','which','exists'):
            with self.subTest(stage=stage),ExitStack() as stack:
                failure=OSError('first-only-'+stage);calls=[]
                def first(value):
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return value
                def environment(key,default=None):
                    if key=='INSPECTION_YOLO_COMMAND':return first('synthetic-yolo') if stage=='configured' else ''
                    if key=='VIRTUAL_ENV':return first(str(self.f.root)) if stage=='virtual-env' else str(self.f.root)
                    return default
                stack.enter_context(patch.object(os.environ,'get',side_effect=environment))
                which=stack.enter_context(patch.object(shutil,'which',side_effect=lambda name:first('synthetic-yolo')) if stage=='which' else patch.object(shutil,'which',return_value=None))
                if stage=='exists':stack.enter_context(patch.object(Path,'exists',side_effect=lambda:first(True)))
                with self.assertRaises(BaseException) as error:fn()
                self.assertIs(error.exception,failure);self.assertEqual(len(calls),1)
                if stage=='configured':which.assert_not_called()


    def test_later_update_capture_preserves_each_argument_window(self):
        api=self.api
        for stage in ('generated','ready','pid','epoch','terminal','failed'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(stage=stage,mode=mode),ExitStack() as stack:
                    f=Fixture(self.f.root/(stage+'-'+mode));f.root.mkdir();f.bind(api,stack);calls=[];effects=[];prior=[]
                    f.task['action']='generate_samples' if stage in ('generated','failed') else 'train_model'
                    def callback(label):
                        def call(job,**values):calls.append((label,dict(values)));return f.updated(job,**values)
                        return call
                    stack.enter_context(patch.object(api,'update_training_task',callback('A')))
                    def before():
                        if not prior:
                            prior.append(True)
                            if mode!='ordinary':api.update_training_task=callback('B') if mode=='prior' else None
                    def argument():effects.append(True);api.update_training_task=callback('C')
                    if stage in ('generated','terminal'):
                        clock=[]
                        def now():
                            clock.append(True)
                            if len(clock)==2:argument()
                            return 42.9
                        stack.enter_context(patch('time.time',side_effect=now))
                    if stage in ('generated','ready'):
                        class Dataset(dict):
                            def __iter__(self):return super().__iter__()
                            def keys(self):argument();return super().keys()
                        f.generate.side_effect=lambda task:before() or (Dataset(f.dataset) if stage=='ready' else f.dataset)
                    elif stage=='pid':
                        class Process:
                            returncode=0
                            @property
                            def pid(self):argument();return 123
                            def poll(self):return 0
                        f.popen.side_effect=lambda *a,**k:before() or Process()
                    elif stage=='epoch':
                        class Parsed(tuple):
                            def __getitem__(self,key):
                                if key==1:argument()
                                return super().__getitem__(key)
                        f.process.poll.side_effect=[None,0]
                        f.progress.side_effect=lambda *a:before() or Parsed((1,3))
                    elif stage=='terminal':f.progress.side_effect=lambda *a:before() or None
                    else:
                        class Failure(Exception):
                            def __str__(self):argument();return 'initial'
                        def generate(task):before();raise Failure()
                        f.generate.side_effect=generate
                    raised=None
                    try:api.run_training_task('job')
                    except BaseException as error:raised=error
                    if mode=='missing' and stage=='failed':self.assertIs(type(raised),TypeError)
                    else:self.assertIsNone(raised)
                    self.assertTrue(prior);self.assertTrue(effects)
                    def selected(value):
                        return {'generated':value.get('status')=='completed','ready':value.get('progress')==76,
                            'pid':'training_pid' in value,'epoch':value.get('status')=='running' and value.get('current_epoch')==1,
                            'terminal':value.get('status')=='completed','failed':value.get('status')=='failed'}[stage]
                    captured=[label for label,value in calls if selected(value)]
                    self.assertEqual(captured,[] if mode=='missing' else ['A' if mode=='ordinary' else 'B'])
                    if mode=='missing' and stage!='failed':self.assertEqual(f.updates[-1]['status'],'failed');self.assertIn('NoneType',f.updates[-1]['error'])
                    elif mode!='missing':self.assertEqual(f.updates[-1]['status'],'failed' if stage=='failed' else 'completed')
                    self.assertIsNone(f.resolver.current_snapshot())

    def test_baseexception_and_failure_message_errors_are_not_settled_again(self):
        api=self.api
        for stage in ('baseexception','error-text','note-text'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture(self.f.root/stage);f.root.mkdir();f.bind(api,stack);f.task['action']='generate_samples';calls=[]
                failure=KeyboardInterrupt('synthetic') if stage=='baseexception' else OSError('format-first-only')
                class Initial(Exception):
                    def __str__(self):
                        calls.append(True)
                        if len(calls)==(1 if stage=='error-text' else 2):raise failure
                        return 'initial'
                f.generate.side_effect=failure if stage=='baseexception' else Initial()
                with self.assertRaises(BaseException) as error:api.run_training_task('job')
                self.assertIs(error.exception,failure);self.assertEqual(len(calls),0 if stage=='baseexception' else (1 if stage=='error-text' else 2))
                self.assertEqual([v['status'] for v in f.updates],['running']);f.sync.assert_not_called();f.popen.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())


if __name__=='__main__':unittest.main()
