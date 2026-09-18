"""Offline bundle metadata/submission contracts; no real HTTP, wait or thread starts."""
from contextlib import ExitStack
import json
import types
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def _capture_worker_bundle_window(ns,site,mode,directory=None):
 events=[];cleanups=[];stops=[];joins=[];ticks=[]
 field={'resolve':'resolve_service_path','form':'windows_worker_form_request'}.get(site,'update_training_task')
 def selected(kwargs):
  if site in ('resolve','form'):return True
  if site=='initial':return 'worker_upload_started_at' in kwargs
  if site=='completed':return kwargs.get('worker_upload_status')=='completed'
  return '正在重试' in kwargs.get('note','')
 def called(label):
  def callback(*args,**kwargs):
   if selected(kwargs):events.append(label)
   if site=='resolve':return root/'data'
   if site=='form':assert kwargs['files']['dataset_archive'][1].read()==b'archive';return body
  return callback
 a,b,c=called('A'),called('B'),called('C')
 def prior():events.append('prior');ns[field]=a if mode=='ordinary' else b if mode=='prior' else None
 def argument():events.append('argument');ns[field]=c
 with tempfile.TemporaryDirectory(prefix='bundle-capture-',dir=directory) as tmp:
  root=Path(tmp);archive=root/'bundle.zip';archive.write_bytes(b'archive');dataset={'dataset_dir':'input'};body={'ok':True}
  def clock():
   ticks.append(1)
   if (site=='initial' and len(ticks)==1) or (site=='completed' and len(ticks)==2):argument()
   return 11.9
  def progress(*args,**kwargs):return types.SimpleNamespace(set=lambda:stops.append('set')),types.SimpleNamespace(join=lambda **kw:joins.append(kw))
  ns.update(time=types.SimpleNamespace(time=clock,sleep=lambda seconds:None),resolve_service_path=lambda value:root/'data',build_worker_training_bundle=lambda *args:(types.SimpleNamespace(cleanup=lambda:cleanups.append('cleanup')),archive),worker_training_bundle_metadata=lambda *args:{'x':1},update_training_task=lambda *args,**kwargs:None,worker_training_upload_timeout_seconds=lambda:1801,_start_transfer_progress_thread=progress,windows_worker_upload_bundle_streamed=lambda *args,**kwargs:body,windows_worker_form_request=lambda *args,**kwargs:body)
  ns[field]=a
  if site=='resolve':
   class Dataset(dict):
    def get(self,key,default=None):argument();return super().get(key,default)
   dataset=Dataset(dataset);prior()
  elif site=='initial':
   class Count(int):
    def __truediv__(self,value):prior();return super().__truediv__(value)
   class Archive(type(Path())):
    def stat(self,*args,**kwargs):return types.SimpleNamespace(st_size=Count(7))
   archive=Archive(archive)
  elif site=='completed':ns['windows_worker_upload_bundle_streamed']=lambda *args,**kwargs:prior() or body
  elif site=='retry':
   class UploadError(RuntimeError):
    def __str__(self):argument();return 'fixture error'
   def stream(*args,**kwargs):prior();raise UploadError()
   ns['windows_worker_upload_bundle_streamed']=stream
  else:
   def stream(*args,**kwargs):raise RuntimeError('fallback')
   ns['windows_worker_upload_bundle_streamed']=stream
   class Archive(type(Path())):
    @property
    def name(self):argument();return super().name
    def open(self,*args,**kwargs):
     handle=super().open(*args,**kwargs)
     class Opened:
      def __enter__(self):prior();return handle.__enter__()
      def __exit__(self,*error):return handle.__exit__(*error)
     return Opened()
   archive=Archive(archive)
  caught=None
  try:ns['post_worker_training_bundle']('job',{},dataset)
  except BaseException as error:caught=error
  if mode=='missing':assert type(caught)is TypeError,(caught,events)
  else:assert caught is None,(caught,events)
  assert events==['prior','argument']+([] if mode=='missing' else ['A' if mode=='ordinary' else 'B']),events
  assert len(cleanups)==(0 if site=='resolve' and mode=='missing' else 1),cleanups
  assert len(stops)==len(joins),(stops,joins)
 return events


def _refresh_worker_bundle_completion(ns,directory=None):
 events=[];a_completions=[];body={'ok':True};cleanups=[]
 with tempfile.TemporaryDirectory(prefix='bundle-refresh-',dir=directory) as tmp:
  root=Path(tmp);archive=root/'a.zip';archive.write_bytes(b'archive')
  def a(job_id,**updates):
   status=updates['worker_upload_status'];events.append(('A',status))
   if status=='completed':
    a_completions.append(1)
    if len(a_completions)==1:ns['update_training_task']=b;raise RuntimeError('first completion write')
  def b(job_id,**updates):events.append(('B',updates['worker_upload_status']))
  def form(*args,**kwargs):assert kwargs['files']['dataset_archive'][1].read()==b'archive';return body
  ns.update(time=types.SimpleNamespace(time=lambda:11,sleep=lambda seconds:None),resolve_service_path=lambda value:root/'data',build_worker_training_bundle=lambda *args:(types.SimpleNamespace(cleanup=lambda:cleanups.append(1)),archive),worker_training_bundle_metadata=lambda *args:{'x':1},worker_training_upload_timeout_seconds=lambda:1801,update_training_task=a,_start_transfer_progress_thread=lambda *args,**kwargs:(types.SimpleNamespace(set=lambda:None),types.SimpleNamespace(join=lambda **kw:None)),windows_worker_upload_bundle_streamed=lambda *args,**kwargs:body,windows_worker_form_request=form)
  result=ns['post_worker_training_bundle']('job',{},{});assert result is body
  assert events==[('A','running'),('A','completed'),('B','running'),('B','completed')],events
  assert cleanups==[1],cleanups
 return events


class BundleFixture:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.archive=self.root/'环境.zip';self.archive.write_bytes(b'archive!!!')
        self.dataset_dir=self.root/'dataset';self.dataset_dir.mkdir();self.dataset={'dataset_dir':'relative-dataset'};self.task={'task_id':'task'}
        self.events=[];self.updates=[];self.states=[];self.stops=[];self.threads=[];self.body={'accepted':'stream'};self.form_body={'accepted':'form'}
        self.metadata_value={'title':'环境','nested':[1,2]};self.manifest_value=[{'path':'img.png','nested':[]}]
        self.resolve=Mock(side_effect=lambda value:self.event('resolve') or self.dataset_dir)
        self.cleanup=Mock(side_effect=lambda:self.event('cleanup'));self.temp=SimpleNamespace(cleanup=self.cleanup)
        self.build=Mock(side_effect=lambda *args:self.event('build') or (self.temp,self.archive))
        self.metadata=Mock(side_effect=lambda *args:self.event('metadata') or self.metadata_value)
        self.hash=Mock(side_effect=lambda *args:self.event('hash') or 'synthetic-sha')
        self.manifest=Mock(side_effect=lambda *args:self.event('manifest') or self.manifest_value)
        self.clock_values=iter([11.9,22.9,33.9,44.9]);self.clock=Mock(side_effect=lambda:self.event('clock') or next(self.clock_values))
        self.timeout=Mock(side_effect=lambda:self.event('timeout') or 1801.5)
        self.remote_timeout=Mock(return_value=1900.5)
        self.update=Mock(side_effect=self.record_update);self.progress=Mock(side_effect=self.start_progress)
        self.stream=Mock(side_effect=lambda *args,**kwargs:self.event('stream') or self.body)
        self.form=Mock(side_effect=self.read_form);self.sleep=Mock(side_effect=lambda seconds:self.event('sleep'))
        self.form_data=[];self.form_handles=[]
    def event(self,name):self.events.append(name)
    def record_update(self,job_id,**updates):self.event('update');self.updates.append(updates)
    def start_progress(self,job_id,state,**kwargs):
        self.event('progress');number=len(self.states)+1;self.states.append(state)
        stop=Mock();stop.set.side_effect=lambda:self.event('set'+str(number));thread=Mock();thread.join.side_effect=lambda **kwargs:self.event('join'+str(number))
        self.stops.append(stop);self.threads.append(thread);return stop,thread
    def read_form(self,*args,**kwargs):
        self.event('form');handle=kwargs['files']['dataset_archive'][1];self.form_handles.append(handle);self.form_data.append(handle.read());return self.form_body
    def bind(self,api,stack):
        values={'resolve_service_path':self.resolve,'build_worker_training_bundle':self.build,'worker_training_bundle_metadata':self.metadata,
            'file_sha256':self.hash,'dataset_file_manifest':self.manifest,'update_training_task':self.update,'worker_training_upload_timeout_seconds':self.timeout,
            'remote_training_timeout_seconds':self.remote_timeout,'_start_transfer_progress_thread':self.progress,
            'windows_worker_upload_bundle_streamed':self.stream,'windows_worker_form_request':self.form}
        for name,value in values.items():stack.enter_context(patch.object(api,name,value))
        stack.enter_context(patch('time.time',self.clock));stack.enter_context(patch('time.sleep',self.sleep))


class TrainingWorkerBundleContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start();cls.runtime=tempfile.TemporaryDirectory(prefix='worker-bundle-root-')
        root=Path(cls.runtime.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server;cls.metadata_fn=staticmethod(server.worker_training_bundle_metadata);cls.timeout_fn=staticmethod(server.worker_training_upload_timeout_seconds)
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='worker-bundle-')));self.sequence=0
        self.f=self.fixture()
        for target in ['requests.request','requests.get','requests.post','subprocess.Popen','os.kill','threading.Thread','threading.Event']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
    def fixture(self):
        self.sequence+=1;f=BundleFixture(self.root/str(self.sequence));f.bind(self.api,self.stack);return f
    def metadata(self,task=None,dataset=None):
        f=self.f;return self.metadata_fn(' job ',f.task if task is None else task,f.dataset if dataset is None else dataset,f.dataset_dir,f.archive)
    def submit(self):return self.api.post_worker_training_bundle(' job ',self.f.task,self.f.dataset)
    def test_metadata_full_defaults_and_aliases(self):
        f=self.f;body=self.metadata({},{});self.assertEqual(body,{'bundle_version':1,'job_id':' job ','task_id':' job ','task_type':'training','action':'train_model',
            'owner_user_id':'','owner_username':'','source_dataset_id':'dataset','selected_accessory_ids':[],'sample_count':1,'train_mode':'yolo_ocr','epochs':1,'image_size':640,
            'dataset_archive':{'filename':'环境.zip','size':10,'sha256':'synthetic-sha'},'dataset_files':f.manifest_value,
            'callback':{'import_target':'training_runs','expected_artifacts':['model','logs','result_manifest']}})
        self.assertIs(body['dataset_files'],f.manifest_value);self.assertEqual(f.events,['hash','manifest']);f.hash.assert_called_once_with(f.archive);f.manifest.assert_called_once_with(f.dataset_dir)
        selected=[1,None,{'a':1},1];task={'task_id':8,'owner_user_id':9,'owner_username':10,'selected_accessory_ids':selected,'source_dataset_id':0}
        body=self.metadata(task,{'dataset_dir':'one/two'});self.assertEqual([body[k] for k in ['task_id','owner_user_id','owner_username','source_dataset_id']],['8','9','10','two'])
        self.assertEqual(body['selected_accessory_ids'],['1','None',"{'a': 1}",'1']);self.assertEqual(selected,[1,None,{'a':1},1])
        body=self.metadata({'selected_accessory_ids':'aba','source_dataset_id':'explicit'},{});self.assertEqual(body['selected_accessory_ids'],['a','b','a']);self.assertEqual(body['source_dataset_id'],'explicit')
    def test_metadata_mode_priority_and_numeric_boundaries(self):
        for task,expected in [({'train_mode':'a','mode':'b','model_variant':'c'},'a'),({'mode':'b','model_variant':'c'},'b'),({'model_variant':'c'},'c'),({'train_mode':0,'mode':'','model_variant':0},'yolo_ocr')]:
            self.assertEqual(self.metadata(task)['train_mode'],expected)
        for field,low,high,default in [('sample_count',1,20000,1),('epochs',1,500,1),('image_size',320,1280,640)]:
            for value in [low-1,low,low+1,high-1,high,high+1,999999,-1,0,'0','',None,str(high+1),True]:
                self.assertEqual(self.metadata({field:value})[field],max(low,min(high,int(value or default))),(field,value))
            for value,error in [('bad',ValueError),([],None),([1],TypeError),(float('inf'),OverflowError)]:
                if error is None: self.assertEqual(self.metadata({field:value})[field],default)
                else:
                    with self.assertRaises(error):self.metadata({field:value})
    def test_metadata_stat_hash_manifest_failures_short_circuit_without_retry(self):
        f=self.f;failure=OSError('stat failed')
        with patch.object(Path,'stat',side_effect=failure):
            with self.assertRaises(OSError) as caught:self.metadata()
        self.assertIs(caught.exception,failure);f.hash.assert_not_called();f.manifest.assert_not_called()
        for port,later in [('hash','manifest'),('manifest',None)]:
            self.f=self.fixture();f=self.f;failure=OSError(port);target=getattr(f,port);target.side_effect=[failure,'would succeed']
            with self.assertRaises(OSError) as caught:self.metadata()
            self.assertIs(caught.exception,failure);target.assert_called_once()
            if later:getattr(f,later).assert_not_called()
    def test_timeout_floor_and_provider_failures(self):
        f=self.f
        for value,expected in [(-1,1800),(0,1800),(1799.9,1800),(1800,1800),(1800.1,1800.1),(float('inf'),float('inf')),(float('nan'),1800)]:
            f.remote_timeout.return_value=value;before=f.remote_timeout.call_count;self.assertEqual(self.timeout_fn(),expected);self.assertEqual(f.remote_timeout.call_count,before+1)
        for value in [None,'1900']:
            f.remote_timeout.return_value=value
            with self.assertRaises(TypeError):self.timeout_fn()
        error=RuntimeError('timeout setting');f.remote_timeout.reset_mock();f.remote_timeout.side_effect=[error,2000]
        with self.assertRaises(RuntimeError) as caught:self.timeout_fn()
        self.assertIs(caught.exception,error);f.remote_timeout.assert_called_once()
    def test_stream_success_exact_order_arguments_and_shared_state(self):
        f=self.f;self.assertIs(self.submit(),f.body)
        self.assertEqual(f.events,['resolve','build','metadata','clock','update','timeout','progress','stream','clock','update','set1','join1','cleanup'])
        f.resolve.assert_called_once_with('relative-dataset');f.build.assert_called_once_with(f.dataset_dir,' job ');f.metadata.assert_called_once_with(' job ',f.task,f.dataset,f.dataset_dir,f.archive)
        self.assertEqual(f.updates,[{'progress':20,'worker_bundle_size_mb':0.0,'worker_upload_status':'running','worker_upload_started_at':11,'worker_upload_total_bytes':10,'worker_upload_sent_bytes':0,
            'note':'已压缩 HK 样本集（0.0MB，仅训练所需图像），正在上传到 Windows Worker。'},
            {'worker_upload_status':'completed','worker_upload_sent_bytes':10,'worker_upload_total_bytes':10,'worker_upload_completed_at':22}])
        f.stream.assert_called_once_with('/training/jobs/import',metadata_json=json.dumps(f.metadata_value,ensure_ascii=False),archive_path=f.archive,state={'done':0,'total':10},timeout_seconds=1801.5)
        self.assertIs(f.stream.call_args.kwargs['state'],f.states[0]);f.progress.assert_called_once_with(' job ',f.states[0],done_field='worker_upload_sent_bytes',total_field='worker_upload_total_bytes',status_field='worker_upload_status')
        f.stops[0].set.assert_called_once_with();f.threads[0].join.assert_called_once_with(timeout=2.0);f.form.assert_not_called();f.sleep.assert_not_called();f.cleanup.assert_called_once()
    def test_runtime_error_falls_back_once_with_new_state_and_closes_archive(self):
        f=self.f;error=RuntimeError('失'*200)
        def stream(*args,**kwargs):f.event('stream');kwargs['state']['done']=7;raise error
        f.stream.side_effect=stream;self.assertIs(self.submit(),f.form_body)
        self.assertEqual(f.events,['resolve','build','metadata','clock','update','timeout','progress','stream','update','sleep','set1','join1','progress','form','clock','update','set2','join2','cleanup'])
        self.assertEqual(f.updates[1],{'progress':20,'worker_upload_status':'running','note':'上传到 Windows Worker 失败（第 1 次），正在重试：'+('失'*160)})
        self.assertEqual(f.states,[{'done':7,'total':10},{'done':0,'total':10}]);self.assertIsNot(f.states[0],f.states[1]);f.sleep.assert_called_once_with(5);f.stream.assert_called_once();f.form.assert_called_once()
        self.assertEqual(f.form.call_args.args,('POST','/training/jobs/import'));self.assertEqual(f.form.call_args.kwargs['data'],{'metadata':json.dumps(f.metadata_value,ensure_ascii=False)})
        self.assertEqual(f.form.call_args.kwargs['timeout_seconds'],1801.5);self.assertEqual(f.form_data,[b'archive!!!']);self.assertTrue(f.form_handles[0].closed)
        self.assertEqual(f.form.call_args.kwargs['files']['dataset_archive'][::2],('环境.zip','application/zip'));self.assertEqual(f.updates[-1]['worker_upload_completed_at'],22)
        for thread in f.threads:thread.join.assert_called_once_with(timeout=2.0)
    def test_second_runtime_error_marks_failed_and_reraises_same_error(self):
        f=self.f;first=RuntimeError('first');second=RuntimeError('second');f.stream.side_effect=[first,f.body];f.form.side_effect=[second,f.form_body]
        with self.assertRaises(RuntimeError) as caught:self.submit()
        self.assertIs(caught.exception,second);f.stream.assert_called_once();f.form.assert_called_once();self.assertEqual(f.updates[-1],{'worker_upload_status':'failed'})
        self.assertEqual(f.events[-4:],['update','set2','join2','cleanup']);self.assertTrue(f.form.call_args.kwargs['files']['dataset_archive'][1].closed);f.cleanup.assert_called_once();f.sleep.assert_called_once_with(5)
    def test_other_upload_exceptions_do_not_retry_but_stop_join_cleanup(self):
        for kind in [OSError,ValueError,KeyboardInterrupt]:
            self.f=self.fixture();f=self.f;error=kind('send');f.stream.side_effect=[error,f.body]
            with self.assertRaises(kind) as caught:self.submit()
            self.assertIs(caught.exception,error);f.stream.assert_called_once();f.form.assert_not_called();f.sleep.assert_not_called();self.assertEqual(len(f.updates),1)
            self.assertEqual(f.events[-3:],['set1','join1','cleanup']);f.cleanup.assert_called_once()
    def test_resolve_and_build_failures_outside_cleanup_boundary(self):
        for port in ['resolve','build']:
            self.f=self.fixture();f=self.f;error=RuntimeError(port);target=getattr(f,port);target.side_effect=[error,f.dataset_dir if port=='resolve' else (f.temp,f.archive)]
            with self.assertRaises(RuntimeError) as caught:self.submit()
            self.assertIs(caught.exception,error);target.assert_called_once();f.cleanup.assert_not_called();f.metadata.assert_not_called();f.progress.assert_not_called()
    def test_preflight_failures_cleanup_without_progress_or_send(self):
        for stage in ['metadata','json','stat','clock','update','timeout']:
            with self.subTest(stage=stage):
                self.f=self.fixture();f=self.f;error=OSError(stage)
                with ExitStack() as stack:
                    hits=[]
                    def first(callback):
                        def invoke(*args,**kwargs):
                            hits.append(stage)
                            if len(hits)==1:raise error
                            return callback(*args,**kwargs)
                        return invoke
                    if stage=='json':stack.enter_context(patch('json.dumps',side_effect=first(json.dumps)))
                    elif stage=='stat':stack.enter_context(patch.object(Path,'stat',autospec=True,side_effect=first(Path.stat)))
                    else:
                        target=getattr(f,stage);target.side_effect=first(target.side_effect)
                    with self.assertRaises(OSError) as caught:self.submit()
                self.assertIs(caught.exception,error);f.cleanup.assert_called_once();f.progress.assert_not_called();f.stream.assert_not_called();f.form.assert_not_called();f.sleep.assert_not_called()
                if stage not in ['json','stat']:getattr(f,stage).assert_called_once()
                self.assertEqual(hits,[stage])
    def test_progress_factory_failure_is_outside_attempt_cleanup(self):
        for attempt in [1,2]:
            self.f=self.fixture();f=self.f;error=RuntimeError('factory');original=f.start_progress;calls=[]
            def progress(*args,**kwargs):
                calls.append(True)
                if len(calls)==attempt:raise error
                return original(*args,**kwargs)
            f.progress.side_effect=progress
            if attempt==2:f.stream.side_effect=RuntimeError('first upload')
            with self.assertRaises(RuntimeError) as caught:self.submit()
            self.assertIs(caught.exception,error);self.assertEqual(f.progress.call_count,attempt);self.assertEqual(len(f.stops),attempt-1);f.form.assert_not_called();f.cleanup.assert_called_once()
            if attempt==1:f.stream.assert_not_called();self.assertEqual(len(f.updates),1)
            else:self.assertEqual(f.events[-3:],['set1','join1','cleanup']);f.stops[0].set.assert_called_once();f.threads[0].join.assert_called_once()
    def test_completed_update_runtime_error_preserves_existing_fallback(self):
        f=self.f;error=RuntimeError('completion write');calls=[]
        def update(job_id,**updates):
            f.record_update(job_id,**updates);calls.append(updates)
            if len(calls)==2:raise error
        f.update.side_effect=update;self.assertIs(self.submit(),f.form_body);f.stream.assert_called_once();f.form.assert_called_once();f.sleep.assert_called_once_with(5)
        self.assertEqual([item['worker_upload_status'] for item in f.updates],['running','completed','running','completed']);self.assertEqual(f.updates[-1]['worker_upload_completed_at'],33)
    def test_sleep_stop_join_and_cleanup_failure_precedence(self):
        for stage in ['sleep','set','join','cleanup']:
            self.f=self.fixture();f=self.f;error=OSError(stage);f.stream.side_effect=RuntimeError('send')
            if stage in ['sleep','cleanup']:getattr(f,stage).side_effect=[error,None]
            else:
                original=f.start_progress
                def progress(*args,**kwargs):
                    stop,thread=original(*args,**kwargs);getattr(stop if stage=='set' else thread,stage).side_effect=[error,None];return stop,thread
                f.progress.side_effect=progress
            if stage=='cleanup':f.stream.side_effect=None;f.stream.return_value=f.body
            with self.assertRaises(OSError) as caught:self.submit()
            self.assertIs(caught.exception,error);f.form.assert_not_called();f.cleanup.assert_called_once()
            if stage=='set':f.stops[0].set.assert_called_once();f.threads[0].join.assert_not_called()
            else:f.stops[0].set.assert_called_once();f.threads[0].join.assert_called_once_with(timeout=2.0)
        self.f=self.fixture();f=self.f;original_error=ValueError('send');cleanup_error=OSError('cleanup wins');f.stream.side_effect=original_error;f.cleanup.side_effect=cleanup_error
        with self.assertRaises(OSError) as caught:self.submit()
        self.assertIs(caught.exception,cleanup_error);self.assertIs(caught.exception.__context__,original_error)


    def test_metadata_evaluation_order_and_fresh_callback_lists(self):
        f=self.f
        class Number:
            def __init__(self,label,value):self.label,self.value=label,value
            def __int__(self):f.event(self.label);return self.value
        original=Path.stat
        def stat(path,*args,**kwargs):f.event('stat');return original(path,*args,**kwargs)
        with patch.object(Path,'stat',autospec=True,side_effect=stat):
            first=self.metadata({'sample_count':Number('samples',2),'epochs':Number('epochs',3),'image_size':Number('image_size',640)}, {'dataset_dir':'one/two','dataset_id':'ignored'})
        self.assertEqual(f.events,['samples','epochs','image_size','stat','hash','manifest']);self.assertEqual(first['source_dataset_id'],'two')
        first['callback']['expected_artifacts'].append('mutated');second=self.metadata({},{});self.assertEqual(second['callback']['expected_artifacts'],['model','logs','result_manifest'])
        self.assertIsNot(first['callback'],second['callback']);self.assertIsNot(first['callback']['expected_artifacts'],second['callback']['expected_artifacts']);self.assertIs(first['dataset_files'],second['dataset_files'])
        before=(f.hash.call_count,f.manifest.call_count)
        with self.assertRaises(ValueError):self.metadata({'sample_count':'invalid'})
        self.assertEqual((f.hash.call_count,f.manifest.call_count),before)
    def test_retry_and_failed_status_write_failures_are_not_retried(self):
        for stage in ['retry','failed']:
            self.f=self.fixture();f=self.f;error=RuntimeError(stage+' write');f.stream.side_effect=RuntimeError('first upload')
            if stage=='failed':f.form.side_effect=RuntimeError('second upload')
            calls=[]
            def update(job_id,**updates):
                f.record_update(job_id,**updates);calls.append(updates)
                if len(calls)==(2 if stage=='retry' else 3):raise error
                return False
            f.update.side_effect=update
            with self.assertRaises(RuntimeError) as caught:self.submit()
            self.assertIs(caught.exception,error);self.assertEqual(f.update.call_count,2 if stage=='retry' else 3);f.stream.assert_called_once();f.cleanup.assert_called_once()
            self.assertEqual(f.form.call_count,0 if stage=='retry' else 1);self.assertEqual(f.sleep.call_count,0 if stage=='retry' else 1)
            self.assertEqual(f.events[-3:],['set1','join1','cleanup'] if stage=='retry' else ['set2','join2','cleanup'])
    def test_false_updates_are_ignored_and_raw_response_identity_is_preserved(self):
        for fallback in [False,True]:
            for body in [None,[],False,{'nested':[]}]:
                self.f=self.fixture();f=self.f
                def update(job_id,**updates):f.record_update(job_id,**updates);return False
                f.update.side_effect=update;f.body=body;f.form_body=body
                if fallback:f.stream.side_effect=RuntimeError('first upload')
                self.assertIs(self.submit(),body);self.assertEqual(f.updates[-1]['worker_upload_status'],'completed');f.cleanup.assert_called_once()
                self.assertEqual(f.form.call_count,int(fallback));self.assertEqual(f.stream.call_count,1)


    def test_bundle_size_uses_mebibytes_and_one_decimal_rounding_with_raw_byte_counters(self):
        for size,megabytes,note in [
            (1572864,1.5,'已压缩 HK 样本集（1.5MB，仅训练所需图像），正在上传到 Windows Worker。'),
            (1310720,1.2,'已压缩 HK 样本集（1.2MB，仅训练所需图像），正在上传到 Windows Worker。'),
            (1835008,1.8,'已压缩 HK 样本集（1.8MB，仅训练所需图像），正在上传到 Windows Worker。'),
        ]:
            self.f=self.fixture();f=self.f;f.archive.write_bytes(b'Z'*size);self.assertIs(self.submit(),f.body)
            self.assertEqual(f.updates[0]['worker_bundle_size_mb'],megabytes);self.assertEqual(f.updates[0]['note'],note)
            self.assertEqual(f.updates[0]['worker_upload_total_bytes'],size);self.assertEqual(f.updates[0]['worker_upload_sent_bytes'],0)
            self.assertEqual(f.states,[{'done':0,'total':size}]);self.assertEqual(f.updates[-1]['worker_upload_sent_bytes'],size);self.assertEqual(f.updates[-1]['worker_upload_total_bytes'],size)
            f.stream.assert_called_once();f.form.assert_not_called();f.cleanup.assert_called_once()

    def test_independent_compositions_use_real_archive_metadata_without_constructor_reads(self):
        import hashlib
        from local_inspection_service.training.worker_bundle_metadata import WorkerBundleMetadata
        from local_inspection_service.training.worker_bundle_submission import WorkerBundleFiles, WorkerBundleTransport, WorkerBundleTimeout, WorkerBundleSubmission
        instances=[]
        for index,owner in enumerate(['alice','bob']):
            f=BundleFixture(self.root/owner);f.archive.write_bytes(owner.encode());f.task={'owner_user_id':owner};f.body={'owner':owner};f.form_body={'owner':owner,'fallback':True}
            f.manifest_value=[{'path':owner+'.png'}];f.remote_timeout.return_value=2000.5+index;f.clock_values=iter([101.9+index,201.9+index,301.9+index,401.9+index])
            f.hash.side_effect=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
            metadata=WorkerBundleMetadata(f.hash,f.manifest);timeout=WorkerBundleTimeout(f.remote_timeout)
            f.metadata.side_effect=metadata.worker_training_bundle_metadata
            f.timeout.side_effect=timeout.worker_training_upload_timeout_seconds
            submission=WorkerBundleSubmission(WorkerBundleFiles(lambda f=f:f.resolve,f.build,f.metadata),WorkerBundleTransport(f.timeout,f.progress,f.stream,lambda f=f:f.form),lambda f=f: f.update,f.clock,f.sleep)
            if owner=='bob':f.stream.side_effect=RuntimeError('fixture stream fallback')
            for callback in [f.resolve,f.build,f.metadata,f.hash,f.manifest,f.remote_timeout,f.timeout,f.progress,f.stream,f.form,f.update,f.clock,f.sleep,f.cleanup]:callback.assert_not_called()
            self.assertEqual(f.events,[]);instances.append((owner,f,submission))
        for name in ['file_sha256','dataset_file_manifest','remote_training_timeout_seconds','resolve_service_path','build_worker_training_bundle',
                     'worker_training_bundle_metadata','update_training_task','worker_training_upload_timeout_seconds','_start_transfer_progress_thread',
                     'windows_worker_upload_bundle_streamed','windows_worker_form_request','post_worker_training_bundle']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected root dependency')))
        for name in ['time.time','time.sleep']:self.stack.enter_context(patch(name,side_effect=AssertionError('unexpected global timing')))
        for index in [1,0,1,0]:
            owner,f,submission=instances[index];before=len(f.states);result=submission.post_worker_training_bundle(owner,f.task,f.dataset)
            self.assertIs(result,f.form_body if owner=='bob' else f.body)
            metadata=json.loads(f.stream.call_args.kwargs['metadata_json']);self.assertEqual(metadata['owner_user_id'],owner);self.assertEqual(metadata['job_id'],owner)
            self.assertEqual(metadata['dataset_files'],f.manifest_value);self.assertEqual(metadata['dataset_archive'],{'filename':'环境.zip','size':len(owner),'sha256':hashlib.sha256(owner.encode()).hexdigest()})
            self.assertEqual(f.stream.call_args.kwargs['timeout_seconds'],f.remote_timeout.return_value);self.assertIs(f.stream.call_args.kwargs['state'],f.states[before])
            self.assertEqual(f.updates[-1]['worker_upload_sent_bytes'],len(owner));self.assertEqual(f.updates[-1]['worker_upload_status'],'completed')
            if owner=='bob':
                self.assertEqual(f.form_data[-1],owner.encode());self.assertTrue(f.form_handles[-1].closed);self.assertIsNot(f.states[before],f.states[before+1])
                self.assertEqual(f.form.call_args.kwargs['timeout_seconds'],f.remote_timeout.return_value)
            f.remote_timeout.return_value+=10
        for owner,f,submission in instances:
            for callback in [f.resolve,f.build,f.metadata,f.hash,f.manifest,f.remote_timeout,f.timeout,f.stream,f.cleanup]:self.assertEqual(callback.call_count,2)
            self.assertEqual(f.form.call_count,2 if owner=='bob' else 0);self.assertEqual(f.progress.call_count,4 if owner=='bob' else 2)
            for stop,thread in zip(f.stops,f.threads):stop.set.assert_called_once_with();thread.join.assert_called_once_with(timeout=2.0);thread.start.assert_not_called()


    def test_update_target_captured_before_each_clock_and_retry_error_string(self):
        for stage in ['initial','completed','retry']:
            with self.subTest(stage=stage):
                self.f=self.fixture(); f=self.f; events=[]
                first=Mock(side_effect=lambda *args,**kwargs:events.append('first'))
                later=Mock(side_effect=lambda *args,**kwargs:events.append('later'))
                self.api.update_training_task=first; ticks=[]
                def switch(): events.append(stage); self.api.update_training_task=later
                def clock():
                    ticks.append(True)
                    if (stage=='initial' and len(ticks)==1) or (stage=='completed' and len(ticks)==2):switch()
                    return 11.9 if len(ticks)==1 else 22.9
                f.clock.side_effect=clock
                class TransferError(RuntimeError):
                    def __str__(self): switch(); return 'synthetic error'
                if stage=='retry':f.stream.side_effect=TransferError()
                self.assertIs(self.submit(),f.form_body if stage=='retry' else f.body)
                initial=call(' job ',progress=20,worker_bundle_size_mb=0.0,worker_upload_status='running',worker_upload_started_at=11,
                    worker_upload_total_bytes=10,worker_upload_sent_bytes=0,note='已压缩 HK 样本集（0.0MB，仅训练所需图像），正在上传到 Windows Worker。')
                final=call(' job ',worker_upload_status='completed',worker_upload_sent_bytes=10,worker_upload_total_bytes=10,worker_upload_completed_at=22)
                retry=call(' job ',progress=20,worker_upload_status='running',note='上传到 Windows Worker 失败（第 1 次），正在重试：synthetic error')
                self.assertEqual(first.call_args_list,[initial,final] if stage=='completed' else ([initial,retry] if stage=='retry' else [initial]))
                self.assertEqual(later.call_args_list,[] if stage=='completed' else [final])
                self.assertEqual(events,['initial','first','later'] if stage=='initial' else (['first','completed','first'] if stage=='completed' else ['first','retry','first','later']))
                f.cleanup.assert_called_once_with(); self.assertEqual(f.clock.call_count,2)
                first.reset_mock(); later.reset_mock(); self.submit(); first.assert_not_called()
                self.assertEqual(later.call_count,3 if stage=='retry' else 2)
    def test_clock_conversion_failure_keeps_both_update_targets_unused(self):
        f=self.f; error=ValueError('timestamp'); later=Mock(return_value=True); events=[]
        class Stamp:
            def __int__(stamp):
                events.append('int'); self.api.update_training_task=later; raise error
        f.clock.side_effect=lambda:Stamp()
        with self.assertRaises(ValueError) as caught:self.submit()
        self.assertIs(caught.exception,error); self.assertEqual(events,['int']); f.update.assert_not_called(); later.assert_not_called()
        f.clock.assert_called_once_with(); f.progress.assert_not_called(); f.stream.assert_not_called(); f.form.assert_not_called(); f.cleanup.assert_called_once_with()


    def test_noncallable_update_still_evaluates_clock_before_type_error(self):
        f=self.f; later=Mock(); self.api.update_training_task=None
        def clock(): self.api.update_training_task=later; return 11.9
        f.clock.side_effect=clock
        with self.assertRaisesRegex(TypeError,"NoneType.*not callable"):self.submit()
        f.clock.assert_called_once_with(); later.assert_not_called(); f.progress.assert_not_called(); f.stream.assert_not_called(); f.cleanup.assert_called_once_with()


    def test_remaining_filesystem_and_argument_failures_do_not_retry(self):
        for site in ['metadata_stat','dataset_get','archive_open','completed_clock']:
            with self.subTest(site=site), ExitStack() as stack:
                self.f=self.fixture();f=self.f;hits=[];error=OSError(site)
                def first(callback):
                    def invoke(*args,**kwargs):
                        hits.append(site)
                        if len(hits)==1:raise error
                        return callback(*args,**kwargs)
                    return invoke
                action=self.submit
                if site=='metadata_stat':
                    original=Path.stat;stack.enter_context(patch.object(Path,'stat',autospec=True,side_effect=first(original)));action=self.metadata
                elif site=='dataset_get':
                    class Dataset(dict):get=first(dict.get)
                    f.dataset=Dataset(f.dataset)
                elif site=='archive_open':
                    f.stream.side_effect=RuntimeError('fallback');original=Path.open
                    stack.enter_context(patch.object(Path,'open',autospec=True,side_effect=first(original)))
                else:
                    def clock():
                        hits.append(site)
                        if len(hits)==2:raise error
                        return 11.9
                    f.clock.side_effect=clock
                with self.assertRaises(OSError) as caught:action()
                self.assertIs(caught.exception,error);self.assertEqual(len(hits),2 if site=='completed_clock' else 1)
                self.assertEqual(f.cleanup.call_count,0 if site in ['metadata_stat','dataset_get'] else 1)
                if site=='archive_open':f.form.assert_not_called();self.assertEqual(len(f.stops),2)
                if site=='completed_clock':f.stream.assert_called_once();f.form.assert_not_called()

    def test_submission_getter_failures_preserve_cleanup_and_never_retry(self):
        from local_inspection_service.training.worker_bundle_submission import WorkerBundleFiles,WorkerBundleTransport,WorkerBundleSubmission
        for site in ['resolve','form','initial','completed','retry','failed']:
            with self.subTest(site=site):
                self.f=self.fixture();f=self.f;hits=[];error=OSError(site)
                at=2 if site in ['completed','retry'] else 3 if site=='failed' else 1
                def provider(callback):
                    def get():
                        hits.append(site)
                        if len(hits)==at:raise error
                        return callback
                    return get
                resolve=provider(f.resolve) if site=='resolve' else lambda:f.resolve
                form=provider(f.form) if site=='form' else lambda:f.form
                update=provider(f.update) if site not in ['resolve','form'] else lambda:f.update
                if site in ['form','retry','failed']:f.stream.side_effect=RuntimeError('stream fallback')
                if site=='failed':f.form.side_effect=RuntimeError('form failure')
                obj=WorkerBundleSubmission(WorkerBundleFiles(resolve,f.build,f.metadata),WorkerBundleTransport(f.timeout,f.progress,f.stream,form),update,f.clock,f.sleep)
                with self.assertRaises(BaseException) as caught:obj.post_worker_training_bundle('job',f.task,f.dataset)
                self.assertIs(caught.exception,error);self.assertEqual(len(hits),at)
                self.assertEqual(f.cleanup.call_count,0 if site=='resolve' else 1)
                self.assertEqual(f.form.call_count,1 if site=='failed' else 0)
                if site=='initial':f.clock.assert_not_called();f.progress.assert_not_called()
                if site=='completed':self.assertEqual(f.clock.call_count,1)
                if site=='retry':f.sleep.assert_not_called()
                for stop,thread in zip(f.stops,f.threads):stop.set.assert_called_once();thread.join.assert_called_once_with(timeout=2.0)


    def test_callback_capture_retains_prior_argument_and_noncallable_order(self):
        for site in ('resolve','form','initial','completed','retry'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode),patch.dict(self.api.__dict__):
                    _capture_worker_bundle_window(self.api.__dict__,site,mode,self.f.root)


    def test_completion_target_is_refreshed_after_existing_form_fallback(self):
        with patch.dict(self.api.__dict__):
            _refresh_worker_bundle_completion(self.api.__dict__,self.f.root)


if __name__=='__main__':unittest.main()
