"""Remote training compatibility contracts with synthetic archives and no network calls."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def _capture_remote_window(ns,site,mode,directory=None):
 events=[];cleanups=[]
 field='resolve_service_path' if site=='resolve' else 'update_training_task'
 def set_callback(value):
  if site=='post':ns['requests'].post=value
  else:ns[field]=value
 def called(label):
  def callback(*args,**kwargs):
   if site in ('resolve','post') or kwargs.get('progress')==(78 if site=='initial' else 100):events.append(label)
   if site=='resolve':return root/'data'
   if site=='post':
    handle=kwargs['files']['dataset_archive'][1];assert not handle.closed;assert handle.read()==b'archive';return response
  return callback
 a,b,c=called('A'),called('B'),called('C')
 def prior():events.append('prior');set_callback(a if mode=='ordinary' else b if mode=='prior' else None)
 def argument():events.append('argument');set_callback(c)
 with tempfile.TemporaryDirectory(prefix='remote-compat-capture-',dir=directory) as tmp:
  root=Path(tmp);archive=root/'data.zip';archive.write_bytes(b'archive');task={};dataset={'dataset_dir':'input'}
  body={'status':'completed','job_id':'remote'};response=SimpleNamespace(text='',raise_for_status=lambda:None,json=lambda:body)
  ns.update(os=SimpleNamespace(environ={}),time=SimpleNamespace(time=lambda:101),requests=SimpleNamespace(post=lambda *a,**k:response),remote_training_endpoint=lambda:'https://fixture.invalid/private',resolve_service_path=lambda value:root/'data',masked_url_for_status=lambda value:'masked',update_training_task=lambda *a,**k:None,package_training_dataset=lambda *a:(SimpleNamespace(cleanup=lambda:cleanups.append('cleanup')),archive),remote_training_timeout_seconds=lambda:30,public_path_sanitized=lambda value:value)
  set_callback(a)
  if site=='resolve':
   class Dataset(dict):
    def get(self,key,default=None):
     if key=='dataset_dir':argument()
     return super().get(key,default)
   dataset=Dataset(dataset)
   ns['remote_training_endpoint']=lambda:prior() or 'https://fixture.invalid/private'
  elif site=='initial':
   ns['resolve_service_path']=lambda value:prior() or root/'data'
   ns['masked_url_for_status']=lambda value:argument() or 'masked'
  elif site=='post':
   class Archive(type(Path())):
    def open(self,*args,**kwargs):
     handle=super().open(*args,**kwargs)
     class Opened:
      def __enter__(self):prior();return handle.__enter__()
      def __exit__(self,*error):return handle.__exit__(*error)
     return Opened()
   archive=Archive(archive);ns['remote_training_timeout_seconds']=lambda:argument() or 30
  else:
   class Identifier:
    def __str__(self):prior();return 'remote'
   body['job_id']=Identifier();ns['time']=SimpleNamespace(time=lambda:argument() or 101)
  caught=None
  try:ns['run_remote_training_task']('job',task,dataset)
  except BaseException as error:caught=error
  if mode=='missing':assert type(caught) is TypeError,(caught,events)
  else:assert caught is None,(caught,events)
  assert events==['prior','argument']+([] if mode=='missing' else ['A' if mode=='ordinary' else 'B']),events
  assert len(cleanups)==(0 if mode=='missing' and site in ('resolve','initial') else 1),cleanups
 return events

class RemoteFixture:
    def __init__(self,root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True); self.archive=self.root/'dataset.zip'; self.archive.write_bytes(b'synthetic archive')
        self.events=[]; self.updates=[]; self.body={'status':' SUCCESS ','job_id':' remote ','nested':{'token':'synthetic'},'token':'synthetic','Token':'case-sensitive'}
        self.task={'train_mode':'中文模式','epochs':999,'image_size':1}; self.dataset={'dataset_dir':'raw dataset','dataset_yaml':'synthetic.yaml','manifest_path':'manifest'}
        self.endpoint=Mock(side_effect=lambda:self.event('endpoint') or 'https://fixture.invalid/private')
        self.resolve=Mock(side_effect=lambda value:self.event('resolve') or self.root/'data')
        self.mask=Mock(side_effect=lambda value:self.event('mask') or 'masked-endpoint')
        self.update=Mock(side_effect=self.updated); self.cleanup=Mock(side_effect=lambda:self.event('cleanup'))
        self.temporary=SimpleNamespace(cleanup=self.cleanup); self.package=Mock(side_effect=lambda *args:self.event('package') or (self.temporary,self.archive))
        self.timeout=Mock(side_effect=lambda:self.event('timeout') or 45.5); self.clock=Mock(side_effect=lambda:self.event('clock') or 123.9)
        self.response=Mock(); self.response.text='text fallback'
        self.response.raise_for_status.side_effect=lambda:self.event('raise')
        self.response.json.side_effect=lambda:self.event('json') or self.body
        self.post=Mock(side_effect=self.posted)
    def event(self,name): self.events.append(name)
    def updated(self,identifier,**values): self.event('update'); self.updates.append(values); return False
    def posted(self,*args,**kwargs):
        self.event('post'); handle=kwargs['files']['dataset_archive'][1]
        assert not handle.closed; assert handle.read()==b'synthetic archive'; return self.response
    def bind(self,api,stack):
        for name,value in {'remote_training_endpoint':self.endpoint,'resolve_service_path':self.resolve,'masked_url_for_status':self.mask,
                           'update_training_task':self.update,'package_training_dataset':self.package,'remote_training_timeout_seconds':self.timeout}.items():
            stack.enter_context(patch.object(api,name,value))
        stack.enter_context(patch.object(requests,'post',self.post)); stack.enter_context(patch('time.time',self.clock))
        stack.enter_context(patch.dict(os.environ,{api.REMOTE_TRAINING_API_KEY_ENV:'  synthetic-key  '}))


class TrainingRemoteCompatibilityContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='remote-training-root-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close); self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='remote-training-')))
        self.f=RemoteFixture(self.root/'base'); self.f.bind(self.api,self.stack)
        for target in ['requests.request','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
    def run_remote(self,f=None):
        f=f or self.f; return self.api.run_remote_training_task(' job ',f.task,f.dataset)
    def test_exact_request_metadata_response_and_closed_archive_before_status(self):
        f=self.f
        def status():
            self.assertTrue(f.post.call_args.kwargs['files']['dataset_archive'][1].closed); f.event('raise')
        f.response.raise_for_status.side_effect=status
        self.assertIsNone(self.run_remote())
        self.assertEqual(f.events,['endpoint','resolve','mask','update','package','timeout','post','raise','json','clock','update','cleanup'])
        f.resolve.assert_called_once_with('raw dataset'); f.package.assert_called_once_with(f.root/'data',' job ')
        f.post.assert_called_once(); self.assertEqual(f.post.call_args.args,('https://fixture.invalid/private',))
        kwargs=f.post.call_args.kwargs; self.assertEqual(set(kwargs),{'data','files','headers','timeout'})
        self.assertEqual(kwargs['headers'],{'Authorization':'Bearer synthetic-key'}); self.assertEqual(kwargs['timeout'],45.5)
        self.assertEqual(kwargs['files']['dataset_archive'][::2],('dataset.zip','application/zip'))
        expected={'job_id':' job ','train_mode':'中文模式','epochs':500,'image_size':320,'dataset_yaml':'synthetic.yaml','manifest_path':'manifest','source':'vantaline_cloud'}
        self.assertEqual(kwargs['data'],{'metadata':json.dumps(expected,ensure_ascii=False)})
        self.assertEqual(f.updates[0],{'status':'running','progress':78,'note':'样本已生成，正在提交到 Windows 远程训练端点。','training_executor':'remote','remote_training_endpoint':'masked-endpoint',**f.dataset})
        self.assertEqual(f.updates[1],{'status':'completed','progress':100,'completed_at':123,'remote_training_status':'success','remote_training_job_id':'remote',
            'remote_training_response':{'status':' SUCCESS ','job_id':' remote ','nested':{'token':'synthetic'},'Token':'case-sensitive'},'note':'Windows 远程训练已完成。'})
        self.assertIs(f.updates[1]['remote_training_response']['nested'],f.body['nested']); f.cleanup.assert_called_once()
    def test_status_sets_whitespace_falsey_values_and_clock_short_circuit(self):
        f=self.f
        for status,completed in [('completed',True),('SUCCEEDED',True),(' success ',True),('done',True),('failed',False),('cancelled',False),('',False),('pending',False)]:
            with self.subTest(status=status):
                f.updates.clear(); f.clock.reset_mock(); f.body={'status':status,'state':' queued ','id':123}
                self.run_remote(); result=f.updates[-1]
                self.assertEqual(result['status'],'completed' if completed else 'running'); self.assertEqual(result['progress'],100 if completed else 90)
                self.assertEqual(result['completed_at'],123 if completed else 0); self.assertEqual(f.clock.call_count,int(completed))
                self.assertEqual(result['remote_training_job_id'],'123'); self.assertEqual(result['remote_training_status'],status.strip().lower() if status else 'queued')
        f.body={}; self.run_remote(); self.assertEqual(f.updates[-1]['remote_training_status'],'submitted')
    def test_json_value_error_fallback_non_dict_coercion_and_exact_top_level_filter(self):
        f=self.f; error=ValueError('not json'); f.response.text='x'*350
        def json_once():
            if f.response.json.call_count==1: raise error
            return f.body
        f.response.json.side_effect=json_once
        self.run_remote(); self.assertEqual(f.updates[-1]['remote_training_response'],{'status':'submitted','message':'x'*300})
        f.response.json.assert_called_once_with()
        f.response.json.side_effect=lambda:f.body
        for value in [None,['x'*350],True,'y'*350]:
            f.body=value; self.run_remote(); self.assertEqual(f.updates[-1]['remote_training_response'],{'status':'submitted','message':str(value)[:300]})
        f.body={'api_key':'one','token':'two','secret':'three','API_KEY':'kept','secret_ref':'kept','nested':{'secret':'kept'}}
        self.run_remote(); self.assertEqual(f.updates[-1]['remote_training_response'],{key:value for key,value in f.body.items() if key not in {'api_key','token','secret'}})
    def test_missing_endpoint_and_prepackage_failures_have_no_cleanup_or_post(self):
        f=self.f; f.endpoint.side_effect=None; f.endpoint.return_value=''
        with self.assertRaises(RuntimeError) as caught: self.run_remote()
        self.assertIn(self.api.REMOTE_TRAINING_ENDPOINT_ENV,str(caught.exception)); self.assertIn(self.api.REMOTE_TRAINING_API_KEY_ENV,str(caught.exception))
        f.resolve.assert_not_called(); f.package.assert_not_called(); f.cleanup.assert_not_called(); f.post.assert_not_called()
        for stage in ['resolve','update','package']:
            with self.subTest(stage=stage),ExitStack() as stack:
                item=RemoteFixture(self.root/stage); item.bind(self.api,stack); target=getattr(item,stage); original=target.side_effect; calls=[]; error=OSError(stage)
                def first(*args,**kwargs):
                    calls.append(True)
                    if len(calls)==1: raise error
                    return original(*args,**kwargs)
                target.side_effect=first
                with self.assertRaises(OSError) as caught: self.run_remote(item)
                self.assertIs(caught.exception,error); target.assert_called_once(); item.cleanup.assert_not_called(); item.post.assert_not_called()
        f.endpoint.return_value='endpoint'; f.dataset['status']='collision'
        with self.assertRaises(TypeError): self.run_remote()
        f.package.assert_not_called(); f.cleanup.assert_not_called()
    def test_after_package_pretry_metadata_or_environment_failure_still_does_not_cleanup(self):
        f=self.f; f.task['epochs']='invalid'
        with self.assertRaises(ValueError): self.run_remote()
        f.package.assert_called_once(); f.cleanup.assert_not_called(); f.post.assert_not_called()
        f.task['epochs']=1; f.package.reset_mock()
        with patch.object(os,'environ',{self.api.REMOTE_TRAINING_API_KEY_ENV:123}):
            with self.assertRaises(AttributeError): self.run_remote()
        f.package.assert_called_once(); f.cleanup.assert_not_called(); f.post.assert_not_called()
    def test_inside_try_failures_cleanup_once_and_never_retry_http(self):
        stages=['open','timeout','post','raise_for_status','json','clock','final-update']
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=RemoteFixture(self.root/stage); f.bind(self.api,stack); error=OSError(stage)
                if stage=='open': target=None
                elif stage in ['raise_for_status','json']: target=getattr(f.response,stage)
                elif stage=='final-update': target=f.update
                else: target=getattr(f,stage)
                if stage=='open':
                    original=Path.open; count=[]
                    def first_open(path,*args,**kwargs):
                        count.append(True)
                        if len(count)==1: raise error
                        return original(path,*args,**kwargs)
                    target=stack.enter_context(patch.object(Path,'open',autospec=True,side_effect=first_open))
                else:
                    original=target.side_effect; calls=[]
                    def first(*args,**kwargs):
                        match=stage!='final-update' or kwargs.get('progress')==100
                        if match:
                            calls.append(True)
                            if len(calls)==1: raise error
                        return original(*args,**kwargs)
                    target.side_effect=first
                with self.assertRaises(OSError) as caught: self.run_remote(f)
                self.assertIs(caught.exception,error); f.cleanup.assert_called_once()
                self.assertEqual(target.call_count,2 if stage=='final-update' else 1)
                self.assertEqual(f.post.call_count,int(stage not in ['open','timeout']))
                if f.post.called: self.assertTrue(f.post.call_args.kwargs['files']['dataset_archive'][1].closed)
    def test_cleanup_failure_overrides_success_or_original_http_error(self):
        f=self.f; cleanup_error=RuntimeError('cleanup'); f.cleanup.side_effect=[cleanup_error,None]
        with self.assertRaises(RuntimeError) as caught: self.run_remote()
        self.assertIs(caught.exception,cleanup_error); f.cleanup.assert_called_once(); self.assertEqual(f.updates[-1]['status'],'completed')
        f.cleanup.reset_mock(); f.cleanup.side_effect=[cleanup_error,None]; f.post.reset_mock(); f.post.side_effect=[OSError('post'),f.response]
        with self.assertRaises(RuntimeError) as caught: self.run_remote()
        self.assertIs(caught.exception,cleanup_error); f.cleanup.assert_called_once(); f.post.assert_called_once()
    def test_empty_api_key_and_mode_defaults_leave_request_shape_unchanged(self):
        f=self.f; f.task={}; f.dataset={}
        with patch.dict(os.environ,{self.api.REMOTE_TRAINING_API_KEY_ENV:'  '}): self.run_remote()
        metadata=json.loads(f.post.call_args.kwargs['data']['metadata']); self.assertEqual(f.post.call_args.kwargs['headers'],{})
        self.assertEqual(metadata,{'job_id':' job ','train_mode':'yolo_ocr','epochs':1,'image_size':640,'dataset_yaml':'','manifest_path':'','source':'vantaline_cloud'})
        f.task={'train_mode':'','mode':'legacy','model_variant':'not-used','epochs':'0','image_size':9999}; self.run_remote()
        metadata=json.loads(f.post.call_args.kwargs['data']['metadata']); self.assertEqual((metadata['train_mode'],metadata['epochs'],metadata['image_size']),('legacy',1,1280))
    def test_worker_payload_exact_defaults_priority_order_duplicates_and_truthiness(self):
        self.assertEqual(self.api.worker_training_payload({}),{'selected_accessory_ids':[],'sample_count':1,'train_mode':'yolo_ocr',
            'approved_preview_id':None,'dataset_id':None,'epochs':1,'image_size':640,'background_set_id':None})
        task={'selected_accessory_ids':['a','a',3,None],'sample_count':0,'train_mode':'','mode':'legacy','model_variant':'variant',
              'approved_preview_id':'','source_dataset_id':'source','dataset_id':'dataset','epochs':'0','image_size':0,'background_set_id':''}
        before=copy.deepcopy(task); result=self.api.worker_training_payload(task)
        self.assertEqual(result,{'selected_accessory_ids':['a','a','3','None'],'sample_count':1,'train_mode':'legacy','approved_preview_id':None,
            'dataset_id':'source','epochs':1,'image_size':640,'background_set_id':None}); self.assertEqual(task,before)
        self.assertIsNot(result['selected_accessory_ids'],task['selected_accessory_ids'])
        self.assertEqual(self.api.worker_training_payload({'selected_accessory_ids':'aba'})['selected_accessory_ids'],['a','b','a'])
        for value,expected in [(0,640),('0',320),(-1,320),(99999,1280)]: self.assertEqual(self.api.worker_training_payload({'image_size':value})['image_size'],expected)
        for key,limit in [('sample_count',20000),('epochs',500)]:
            for value,expected in [(0,1),('0',1),(-1,1),(999999,limit)]: self.assertEqual(self.api.worker_training_payload({key:value})[key],expected)
            for boundary in [limit-1,limit,limit+1]:
                for value in [boundary,str(boundary)]: self.assertEqual(self.api.worker_training_payload({key:value})[key],min(boundary,limit))
        for values,mode in [({'train_mode':'first','mode':'second','model_variant':'third'},'first'),({'mode':'second','model_variant':'third'},'second'),({'model_variant':'third'},'third'),({},'yolo_ocr')]:
            self.assertEqual(self.api.worker_training_payload(values)['train_mode'],mode)
        for key in ['sample_count','epochs','image_size']:
            for value,error in [('bad',ValueError),(float('nan'),ValueError),(float('inf'),OverflowError)]:
                with self.assertRaises(error): self.api.worker_training_payload({key:value})
    def test_terminal_status_only_lowercase_without_strip_or_remote_success_aliases(self):
        for value,expected in [('completed',True),('FAILED',True),('Cancelled',True),('canceled',True),('stopped',True),(' completed ',False),('success',False),('done',False),('',False)]:
            self.assertIs(self.api.worker_training_terminal_status(value),expected)
        for value in [None,1]:
            with self.assertRaises(AttributeError): self.api.worker_training_terminal_status(value)
    def test_artifact_summary_allowlist_call_order_aliases_and_failure_stops_projection(self):
        nested=['one']; item={'unknown':'ignored','status':'completed','selected_accessory_ids':nested,'label':'Label','api_key':'ignored','dataset_yaml':'path','Status':'ignored'}
        with patch.object(self.api,'public_path_sanitized',side_effect=lambda value:value) as sanitize:
            result=self.api.worker_training_artifact_summary(item)
            self.assertEqual(list(result),['status','selected_accessory_ids','label','dataset_yaml'])
            self.assertEqual(sanitize.call_args_list,[call('completed'),call(nested),call('Label'),call('path')]); self.assertIs(result['selected_accessory_ids'],nested)
        keys=['id','run_id','task_id','label','display_name','status','sample_count','selected_accessory_ids','artifact_path','dataset_yaml']
        all_fields={key:{'synthetic':key} for key in keys}
        with patch.object(self.api,'public_path_sanitized',side_effect=lambda value:value) as sanitize:
            result=self.api.worker_training_artifact_summary(all_fields)
            self.assertEqual(list(result),keys); self.assertEqual(sanitize.call_args_list,[call(all_fields[key]) for key in keys])
            for key in keys: self.assertIs(result[key],all_fields[key])
        error=OSError('sanitize')
        def sanitize_once(value):
            if sanitize.call_count==1: raise error
            return value
        with patch.object(self.api,'public_path_sanitized',side_effect=sanitize_once) as sanitize:
            with self.assertRaises(OSError) as caught: self.api.worker_training_artifact_summary(item)
            self.assertIs(caught.exception,error); sanitize.assert_called_once_with('completed')
        with patch.object(self.api,'public_path_sanitized',side_effect=AssertionError('no allowlisted values')):
            self.assertEqual(self.api.worker_training_artifact_summary({'unknown':nested}),{})


    def test_independent_remote_compositions_and_pure_aliases_without_constructor_reads(self):
        from local_inspection_service.training.remote_training import RemoteTrainingSettings, RemoteTrainingPaths, RemoteTraining
        from local_inspection_service.training.worker_compatibility import worker_training_payload, worker_training_terminal_status, WorkerArtifactSummary
        self.assertIs(self.api.worker_training_payload,worker_training_payload); self.assertIs(self.api.worker_training_terminal_status,worker_training_terminal_status)
        def build(owner,stamp):
            f=RemoteFixture(self.root/owner); f.archive.write_bytes(owner.encode()); f.task['train_mode']=owner
            f.body={'status':'done','job_id':owner,'nested':{'owner':owner}}; callbacks=[]; environment={self.api.REMOTE_TRAINING_API_KEY_ENV:owner+'-key'}
            def port(fn): value=Mock(side_effect=fn); callbacks.append(value); return value
            def post(endpoint,**kwargs):
                self.assertEqual(endpoint,'https://'+owner+'.invalid/private'); self.assertEqual(kwargs['headers'],{'Authorization':'Bearer '+environment[self.api.REMOTE_TRAINING_API_KEY_ENV]})
                self.assertEqual(kwargs['files']['dataset_archive'][1].read(),owner.encode()); self.assertFalse(kwargs['files']['dataset_archive'][1].closed)
                self.assertEqual(json.loads(kwargs['data']['metadata'])['train_mode'],owner); return f.response
            transport=port(post); clock=port(lambda:stamp)
            service=RemoteTraining(RemoteTrainingSettings(port(lambda:'https://'+owner+'.invalid/private'),port(lambda value:'masked-'+owner),port(lambda:environment),port(lambda:stamp/10)),
                RemoteTrainingPaths(port(lambda:(lambda value:f.root/'data')),port(f.package)),port(lambda: f.update),port(lambda:transport),clock)
            summary=WorkerArtifactSummary(port(lambda value:{'owner':owner,'value':value}))
            for callback in callbacks: callback.assert_not_called()
            self.assertEqual(f.events,[])
            return f,owner,stamp,environment,transport,service,summary
        instances=[build('alice',111),build('bob',222)]
        for name in ['remote_training_endpoint','resolve_service_path','masked_url_for_status','update_training_task','package_training_dataset',
                     'remote_training_timeout_seconds','public_path_sanitized','run_remote_training_task','worker_training_artifact_summary']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected root dependency')))
        self.stack.enter_context(patch.object(requests,'post',side_effect=AssertionError('unexpected network')))
        for index in [1,0,1,0]:
            f,owner,stamp,environment,transport,service,summary=instances[index]
            service.run_remote_training_task(owner,f.task,f.dataset)
            self.assertEqual(f.update.call_args.args,(owner,)); self.assertEqual(f.updates[-1]['remote_training_job_id'],owner)
            self.assertEqual(f.updates[-1]['completed_at'],stamp); self.assertEqual(f.updates[-2]['remote_training_endpoint'],'masked-'+owner)
            self.assertIs(f.updates[-1]['remote_training_response']['nested'],f.body['nested'])
            self.assertEqual(transport.call_args.kwargs['timeout'],stamp/10); self.assertTrue(transport.call_args.kwargs['files']['dataset_archive'][1].closed)
            self.assertEqual(f.cleanup.call_count,transport.call_count)
            projected=summary.worker_training_artifact_summary({'status':owner,'ignored':'secret'})
            self.assertEqual(projected,{'status':{'owner':owner,'value':owner}})
            environment[self.api.REMOTE_TRAINING_API_KEY_ENV]=owner+'-next-key'


    def test_update_target_captured_before_mask_clock_and_int_arguments(self):
        for stage in ['mask','clock','int']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=RemoteFixture(self.root/stage); f.bind(self.api,stack); events=[]
                first=Mock(side_effect=lambda *args,**kwargs:events.append('first'))
                later=Mock(side_effect=lambda *args,**kwargs:events.append('later'))
                self.api.update_training_task=first
                def switch():
                    events.append(stage); self.api.update_training_task=later
                if stage=='mask':
                    f.mask.side_effect=lambda value:switch() or 'masked-endpoint'
                elif stage=='clock':
                    f.clock.side_effect=lambda:switch() or 123.9
                else:
                    class Stamp:
                        def __int__(self): switch(); return 123
                    f.clock.side_effect=lambda:Stamp()
                self.assertIsNone(self.run_remote(f))
                initial=call(' job ',status='running',progress=78,note='样本已生成，正在提交到 Windows 远程训练端点。',
                    training_executor='remote',remote_training_endpoint='masked-endpoint',**f.dataset)
                final=call(' job ',status='completed',progress=100,completed_at=123,remote_training_status='success',remote_training_job_id='remote',
                    remote_training_response={'status':' SUCCESS ','job_id':' remote ','nested':{'token':'synthetic'},'Token':'case-sensitive'},note='Windows 远程训练已完成。')
                self.assertEqual(first.call_args_list,[initial] if stage=='mask' else [initial,final])
                self.assertEqual(later.call_args_list,[final] if stage=='mask' else [])
                self.assertEqual(events,[stage,'first','later'] if stage=='mask' else ['first',stage,'first'])
                first.reset_mock(); later.reset_mock(); self.run_remote(f)
                first.assert_not_called(); self.assertEqual(later.call_args_list,[initial,final]); self.assertEqual(f.post.call_count,2)
    def test_captured_update_error_not_replaced_by_successful_new_target(self):
        f=self.f; error=OSError('captured update failed'); later=Mock(return_value=True)
        def update_once(*args,**kwargs):
            if f.update.call_count==2: raise error
            return False
        f.update.side_effect=update_once
        def clock(): self.api.update_training_task=later; return 123.9
        f.clock.side_effect=clock
        with self.assertRaises(OSError) as caught:self.run_remote()
        self.assertIs(caught.exception,error); self.assertEqual(f.update.call_count,2); later.assert_not_called()
        f.clock.assert_called_once_with(); f.post.assert_called_once(); f.cleanup.assert_called_once_with()


    def test_noncallable_update_still_evaluates_mask_before_type_error(self):
        f=self.f; later=Mock(); self.api.update_training_task=None
        def mask(value): self.api.update_training_task=later; return 'masked-endpoint'
        f.mask.side_effect=mask
        with self.assertRaisesRegex(TypeError,"NoneType.*not callable"):self.run_remote()
        f.mask.assert_called_once_with('https://fixture.invalid/private'); later.assert_not_called()
        f.package.assert_not_called(); f.post.assert_not_called(); f.cleanup.assert_not_called()


    def test_first_dependency_and_archive_errors_preserve_cleanup_without_retry(self):
        stages=['endpoint','resolve','mask','update-first','package','timeout','clock','post','raise','json','cleanup','update-final','open','dumps']
        for stage in stages:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=RemoteFixture(self.root/stage); f.bind(self.api,stack); error=RuntimeError(stage); calls=[]
                index=2 if stage=='update-final' else 1
                def first(fn):
                    def invoke(*args,**kwargs):
                        calls.append('call')
                        if len(calls)==index: raise error
                        return fn(*args,**kwargs)
                    return invoke
                if stage=='open':
                    original=Path.open; failed=first(original)
                    stack.enter_context(patch.object(Path,'open',autospec=True,side_effect=lambda path,*args,**kwargs:failed(path,*args,**kwargs) if path==f.archive else original(path,*args,**kwargs)))
                elif stage=='dumps': stack.enter_context(patch.object(json,'dumps',side_effect=first(json.dumps)))
                else:
                    target=f.update if stage.startswith('update-') else f.response.raise_for_status if stage=='raise' else f.response.json if stage=='json' else getattr(f,stage)
                    target.side_effect=first(target.side_effect)
                caught=None
                try: self.run_remote(f)
                except BaseException as exc: caught=exc
                self.assertIs(caught,error); self.assertEqual(len(calls),index)
                self.assertEqual(f.cleanup.call_count,int(stage not in ['endpoint','resolve','mask','update-first','package']))
                self.assertLessEqual(f.post.call_count,1)
                if f.post.call_count: self.assertTrue(f.post.call_args.kwargs['files']['dataset_archive'][1].closed)

    def test_new_getter_first_errors_preserve_pretry_and_finally_boundaries(self):
        from dataclasses import replace
        for stage in ['resolve','post','update-first','update-final']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=RemoteFixture(self.root/stage); f.bind(self.api,stack); error=RuntimeError(stage)
                index=2 if stage=='update-final' else 1
                selected=f.resolve if stage=='resolve' else f.post if stage=='post' else f.update
                def provide():
                    if getter.call_count==index: raise error
                    return selected
                getter=Mock(side_effect=provide); service=self.api._remote_training
                if stage=='resolve': stack.enter_context(patch.object(service,'paths',replace(service.paths,resolve=getter)))
                else: stack.enter_context(patch.object(service,'post' if stage=='post' else 'update_provider',getter))
                getter.assert_not_called(); caught=None
                try: self.run_remote(f)
                except BaseException as exc: caught=exc
                self.assertIs(caught,error); self.assertEqual(getter.call_count,index)
                self.assertEqual(f.cleanup.call_count,int(stage in ['post','update-final']))
                self.assertEqual(f.post.call_count,int(stage=='update-final'))
                self.assertEqual(f.update.call_count,int(stage in ['post','update-final']))
                f.clock.assert_not_called()
                if stage=='post': f.timeout.assert_not_called()
                if stage=='resolve': f.resolve.assert_not_called()

    def test_callbacks_capture_after_actual_prior_effect_before_arguments(self):
        for site in ['resolve','initial','post','final']:
            for mode in ['ordinary','prior','missing']:
                with self.subTest(site=site,mode=mode), patch.dict(self.api.__dict__):
                    _capture_remote_window(self.api.__dict__,site,mode,directory=self.root)

    def test_environment_mapping_first_error_after_package_has_no_cleanup_or_post(self):
        f=self.f; error=RuntimeError('environment lookup'); calls=[]
        class Environment(dict):
            def get(inner,key,default=None):
                calls.append((key,default))
                if len(calls)==1: raise error
                return super().get(key,default)
        environment=Environment({self.api.REMOTE_TRAINING_API_KEY_ENV:'synthetic'})
        with patch.object(self.api,'os',SimpleNamespace(environ=environment)):
            caught=None
            try: self.run_remote(f)
            except BaseException as exc: caught=exc
        self.assertIs(caught,error); self.assertEqual(calls,[(self.api.REMOTE_TRAINING_API_KEY_ENV,'')])
        f.package.assert_called_once(); f.cleanup.assert_not_called(); f.post.assert_not_called(); f.update.assert_called_once()

    def test_environment_provider_first_error_after_package_has_no_cleanup_or_post(self):
        from dataclasses import replace
        f=self.f; error=RuntimeError('environment provider'); calls=[]
        def environment():
            calls.append('get')
            if len(calls)==1: raise error
            return {self.api.REMOTE_TRAINING_API_KEY_ENV:'synthetic'}
        service=self.api._remote_training
        with patch.object(service,'settings',replace(service.settings,environment=environment)):
            caught=None
            try: self.run_remote(f)
            except BaseException as exc: caught=exc
        self.assertIs(caught,error); self.assertEqual(calls,['get'])
        f.package.assert_called_once(); f.cleanup.assert_not_called(); f.post.assert_not_called(); f.update.assert_called_once()

if __name__=='__main__': unittest.main()
