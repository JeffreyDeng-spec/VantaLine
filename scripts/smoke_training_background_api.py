"""Background HTTP and image-validation contracts using synthetic identities and files only."""
import asyncio
from contextlib import ExitStack
import copy
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch
import cv2
import numpy as np
from fastapi import HTTPException, UploadFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def _capture_background_api_window(ns,site,mode,fixture_root):
 events=[];field='bounded_text' if site.startswith('text-') else {'selected':'selected_background_set_id','output':'output_write_dir_for_owner','save':'save_task_environment_background_set','update':'update_background_set_manifest'}[site]
 def called(label):
  def callback(*args,**kwargs):
   events.append(label)
   return 'Bound' if site.startswith('text-') else 'chosen' if site=='selected' else root/'captures' if site=='output' else {'id':'bg'} if site=='save' else kwargs
  return callback
 a,b,c=called('A'),called('B'),called('C')
 def prior():events.append('prior');ns[field]=a if mode=='ordinary' else b if mode=='prior' else None
 def argument():events.append('argument');ns[field]=c
 with tempfile.TemporaryDirectory(prefix='background-api-capture-',dir=fixture_root) as directory:
  root=Path(directory);source=root/'source.png';assert cv2.imwrite(str(source),np.zeros((3,4,3),np.uint8))
  user={'id':'owner'};task={'id':'task','name':'Task'}
  ns.update(BACKGROUND_SETS_DIR=root/'sets',IMAGE_REFERENCE_SUFFIXES={'.png'},AI_DETECTION_TASK_PREFIX='fixture:',time=SimpleNamespace(time=lambda:101),uuid=SimpleNamespace(uuid4=lambda:SimpleNamespace(hex='abcdef')),
   current_auth_user=lambda:user,user_is_admin=lambda value:False,sanitize_ai_detection_task_id=lambda value:'task',safe_background_set_id=lambda value:'set',
   list_background_sets=lambda *args,**kwargs:[],load_background_sets_manifest=lambda:{},selected_background_set_id=lambda *args:'set',
   unique_background_set_id=lambda value:'set',current_owner_fields=lambda:{},enqueue_background_set_task=lambda *args:{'job_id':'job'},background_set_payload=lambda key,meta:meta,
   load_ai_detection_tasks=lambda:[task],require_record_access=lambda *args,**kwargs:None,output_write_dir_for_owner=lambda *args:root/'captures',
   save_task_environment_background_set=lambda *args,**kwargs:{'id':'bg'},public_output_url=lambda value:'/url',save_ai_detection_task=lambda value:None,
   _auto_optimize_lock=threading.RLock(),load_auto_optimize_state=lambda value:{},save_auto_optimize_state=lambda value:None,public_auto_optimize_state=lambda *args,**kwargs:{},public_path_sanitized=lambda value:value,
   analyze_bgr=lambda *args,**kwargs:{},bounded_text=lambda value,limit:str(value))
  ns[field]=a;expected_http=None;copy_override=None
  if site=='selected':
   class Manifest(dict):
    def get(self,key,default=None):argument();return 'set'
   def load():prior();return Manifest()
   ns['load_background_sets_manifest']=load;invoke=lambda:ns['training_background_sets']()
  elif site.startswith('text-'):
   result={};expected_http=503 if site in ('text-error','text-provider') else 409
   if site=='text-error':
    class Failure(RuntimeError):
     def __str__(self):argument();return 'unknown'
    failure=Failure()
    def analyze(*args,**kwargs):prior();raise failure
    ns['analyze_bgr']=analyze
   elif site=='text-provider':
    class AI(dict):
     def get(self,key,default=None):
      if key=='provider_failure':prior();return True
      if key=='failure_reason':argument();return 'unavailable'
      return super().get(key,default)
    result={'ai':AI()}
   elif site=='text-detection':
    class Item(dict):
     def get(self,key,default=None):
      if key=='accessory_id':prior();return 'part'
      if key=='label':argument();return 'Part'
      return super().get(key,default)
    result={'detections':[Item(present=True)]}
   else:
    class Key(str):
     def __str__(self):prior();return str.__str__(self)
    class Labels(dict):
     def get(self,key,default=None):argument();return 'Part'
    task['accessory_labels']=Labels();result={'rule':{'counts':{Key('part'):1}}}
   if site!='text-error':ns['analyze_bgr']=lambda *args,**kwargs:result
   invoke=lambda:ns['validate_task_environment_background_image']('task',task,source)
  elif site in ('output','save'):
   if site=='output':
    class User(dict):
     done=False
     def get(self,key,default=None):
      if key=='id' and not self.done:self.done=True;argument()
      return super().get(key,default)
    user=User(id='owner');ns['require_record_access']=lambda *args,**kwargs:prior()
   else:
    class Task(dict):
     done=False
     def get(self,key,default=None):
      if key=='name' and not self.done:self.done=True;argument()
      return super().get(key,default)
    task=Task(id='task',name='Task')
   def validate(*args):
    if site=='save':prior()
    return {'status':'accepted'}
   ns['validate_task_environment_background_image']=validate
   invoke=lambda:asyncio.run(ns['upload_ai_task_environment_background']('task',UploadFile(filename='x.png',file=io.BytesIO(b'synthetic'))))
  else:
   ns['training_background_sets']=lambda:{}
   original_copy=shutil.copyfileobj
   def copied(*args,**kwargs):original_copy(*args,**kwargs);prior()
   copy_override=copied
   def clock():argument();return 101
   ns['time']=SimpleNamespace(time=clock)
   invoke=lambda:asyncio.run(ns['upload_training_background_set']('Set',UploadFile(filename='x.png',file=io.BytesIO(b'synthetic'))))
  caught=None
  try:
   if copy_override:
    with patch.object(shutil,'copyfileobj',copy_override):invoke()
   else:invoke()
  except BaseException as error:caught=error
  assert events[:2]==['prior','argument'],events
  if mode=='missing':
   assert type(caught) is TypeError,(type(caught),events)
   assert events==['prior','argument'],events
  else:
   if expected_http:assert isinstance(caught,HTTPException) and caught.status_code==expected_http,(caught,events)
   else:assert caught is None,(caught,events)
   assert events==['prior','argument','A' if mode=='ordinary' else 'B'],events
 return events

class RecordingLock:
    def __init__(self,events): self.events=events; self.depth=0
    def __enter__(self): self.events.append('lock'); self.depth+=1; return self
    def __exit__(self,*args): self.depth-=1; self.events.append('unlock')


class BackgroundApiFixture:
    def __init__(self,root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True); self.sets=self.root/'sets'; self.capture=self.root/'captures'
        self.source=self.root/'source.png'; self.image=np.full((7,11,3),73,dtype=np.uint8); assert cv2.imwrite(str(self.source),self.image)
        self.events=[]; self.user={'id':'alice','username':'Alice','role':'member'}; self.rows=[{'id':'safe-set'}]
        self.task={'id':'task','name':'Task','owner_user_id':'owner','owner_username':'Owner'}; self.tasks=[self.task]
        self.state={'task_name':'Old','owner_user_id':'state-owner','owner_username':'State owner'}; self.lock=RecordingLock(self.events)
        self.saved_tasks=[]; self.saved_states=[]; self.metas=[]; self.response={'old':'value','status':'old'}
        self.background={'id':'saved-bg','source':'background-source','image_count':6,'generation_method':'local'}
        self.accepted={'status':'accepted'}; self.catalog={'background_sets':['catalog'],'default_set_id':'chosen'}
        self.manifest={'default_set_id':'default'}; self.queued={'job_id':'job'}
        def named(name,value): return Mock(side_effect=lambda *args,**kwargs:self.event(name) or value())
        self.current=named('user',lambda:self.user); self.admin=Mock(side_effect=lambda user:self.event('admin') or user.get('role')=='admin')
        self.safe=Mock(side_effect=lambda identifier:self.event('safe') or 'safe-set'); self.sanitize=Mock(side_effect=lambda identifier:self.event('sanitize') or 'task')
        self.list=named('list',lambda:self.rows); self.load=named('manifest',lambda:self.manifest); self.selected=named('selected',lambda:'chosen')
        self.unique=named('unique',lambda:'chosen'); self.owner=named('owner',lambda:{'owner_user_id':self.user['id']})
        self.enqueue=named('enqueue',lambda:self.queued); self.payload=Mock(side_effect=lambda identifier,meta:self.event('payload') or {'id':identifier,'meta':meta})
        self.meta=Mock(side_effect=self.write_meta); self.clock=named('clock',lambda:101.9); self.uuid=Mock(return_value=SimpleNamespace(hex='abcdef1234'))
        self.tasks_load=named('tasks',lambda:self.tasks); self.guard=named('guard',lambda:None); self.output=named('output',lambda:self.capture)
        self.validate=named('validate',lambda:self.accepted); self.save_background=named('background',lambda:self.background)
        self.url=named('url',lambda:'/synthetic.png'); self.save_task=Mock(side_effect=self.persist_task)
        self.state_load=Mock(side_effect=self.read_state); self.state_save=Mock(side_effect=self.persist_state)
        self.public=named('public',lambda:self.response); self.sanitize_public=Mock(side_effect=lambda value:self.event('sanitize-public') or {'safe':value['id']})
        self.analysis={'request_id':'returned','ai':{'latency_ms':12},'model':{'provider_model':'fixture'},'detections':[],'rule':{}}
        self.analyze=named('analyze',lambda:self.analysis)
    def event(self,name): self.events.append(name)
    def write_meta(self,identifier,**values): self.event('meta'); self.metas.append(values); return values
    def persist_task(self,task): assert self.lock.depth==0; self.event('save-task'); self.saved_tasks.append(task); return False
    def read_state(self,identifier): assert self.lock.depth==1; self.event('state-load'); return self.state
    def persist_state(self,state): assert self.lock.depth==1; self.event('state-save'); self.saved_states.append(state); return False
    def bind(self,api,stack):
        values={'BACKGROUND_SETS_DIR':self.sets,'IMAGE_REFERENCE_SUFFIXES':{'.png','.jpg'},'AI_DETECTION_TASK_PREFIX':'fixture:',
                'current_auth_user':self.current,'user_is_admin':self.admin,'safe_background_set_id':self.safe,'sanitize_ai_detection_task_id':self.sanitize,
                'list_background_sets':self.list,'load_background_sets_manifest':self.load,'selected_background_set_id':self.selected,
                'unique_background_set_id':self.unique,'update_background_set_manifest':self.meta,'current_owner_fields':self.owner,
                'enqueue_background_set_task':self.enqueue,'background_set_payload':self.payload,'load_ai_detection_tasks':self.tasks_load,
                'require_record_access':self.guard,'output_write_dir_for_owner':self.output,'save_task_environment_background_set':self.save_background,
                'public_output_url':self.url,'save_ai_detection_task':self.save_task,'_auto_optimize_lock':self.lock,
                'load_auto_optimize_state':self.state_load,'save_auto_optimize_state':self.state_save,'public_auto_optimize_state':self.public,
                'public_path_sanitized':self.sanitize_public,'analyze_bgr':self.analyze}
        for name,value in values.items(): stack.enter_context(patch.object(api,name,value))
        stack.enter_context(patch('time.time',self.clock)); stack.enter_context(patch('uuid.uuid4',self.uuid))


class TrainingBackgroundApiContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='background-api-root-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close); self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='background-api-')))
        self.f=BackgroundApiFixture(self.root/'base'); self.f.bind(self.api,self.stack)
        for target in ['requests.request','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
    def upload(self,filename='input.PNG',data=b'synthetic upload'): return UploadFile(file=io.BytesIO(data),filename=filename)
    def environment_upload(self,f=None):
        f=f or self.f
        with patch.object(self.api,'validate_task_environment_background_image',f.validate):
            return asyncio.run(self.api.upload_ai_task_environment_background(' raw ',self.upload()))
    def training_upload(self,f=None,name='  Name  ',file=None):
        f=f or self.f
        with patch.object(self.api,'training_background_sets',side_effect=lambda:f.event('catalog') or f.catalog):
            return asyncio.run(self.api.upload_training_background_set(name,file or self.upload()))
    def test_validator_exact_call_pixels_and_accepted_projection(self):
        f=self.f; result=self.api.validate_task_environment_background_image(' raw ',f.task,f.source)
        self.assertEqual(result,{'status':'accepted','request_id':'returned','latency_ms':12,'provider_model':'fixture'})
        f.sanitize.assert_called_once_with(' raw '); f.analyze.assert_called_once()
        args=f.analyze.call_args.args; self.assertTrue(np.array_equal(args[0],f.image))
        self.assertEqual(args[1:],('background_probe_task_101_abcdef','fixture:task')); self.assertEqual(f.analyze.call_args.kwargs,{'image_path':f.source})
        self.assertEqual(f.events,['sanitize','clock','analyze'])
        f.analysis={'ai':[],'model':[],'detections':'ignored','rule':None}
        self.assertEqual(self.api.validate_task_environment_background_image('raw',{},f.source),
            {'status':'accepted','request_id':'background_probe_task_101_abcdef','latency_ms':0,'provider_model':''})
    def test_validator_preflight_error_boundaries_and_no_retry(self):
        f=self.f; f.sanitize.return_value=''; f.sanitize.side_effect=None
        with patch.object(cv2,'imread',side_effect=AssertionError('must not read')):
            with self.assertRaises(HTTPException) as caught: self.api.validate_task_environment_background_image('bad',{},f.source)
        self.assertEqual((caught.exception.status_code,caught.exception.detail),(404,'AI detection task not found')); f.clock.assert_not_called(); f.analyze.assert_not_called()
        f.sanitize.return_value='task'
        with patch.object(cv2,'imread',return_value=None):
            with self.assertRaises(HTTPException) as caught: self.api.validate_task_environment_background_image('raw',{},f.source)
        self.assertEqual((caught.exception.status_code,caught.exception.detail),(400,'无法读取背景图片，请重新上传。')); f.clock.assert_not_called()
        for target in [f.clock,f.uuid]:
            previous=target.side_effect; target.side_effect=[OSError('before analyze'),101]
            try:
                with self.assertRaisesRegex(OSError,'before analyze'): self.api.validate_task_environment_background_image('raw',{},f.source)
            finally: target.side_effect=previous
        f.analyze.assert_not_called()
    def test_validator_preserves_http_errors_bounds_other_errors_and_strict_provider_flag(self):
        f=self.f; error=HTTPException(429,'original'); f.analyze.side_effect=[error,{}]
        with self.assertRaises(HTTPException) as caught: self.api.validate_task_environment_background_image('raw',{},f.source)
        self.assertIs(caught.exception,error); f.analyze.assert_called_once()
        f.analyze.reset_mock(); error=OSError('x'*150); f.analyze.side_effect=[error,{}]
        with self.assertRaises(HTTPException) as caught: self.api.validate_task_environment_background_image('raw',{},f.source)
        self.assertEqual(caught.exception.status_code,503); self.assertIn('x'*120,caught.exception.detail); self.assertNotIn('x'*121,caught.exception.detail)
        self.assertIs(caught.exception.__cause__,error); f.analyze.assert_called_once()
        for flag in [1,'true',True]:
            f.analyze.side_effect=lambda *args,**kwargs:{'ai':{'provider_failure':flag,'failure_reason':' reason  with spaces '}}
            if flag is True:
                with self.assertRaises(HTTPException) as caught: self.api.validate_task_environment_background_image('raw',{},f.source)
                self.assertEqual(caught.exception.detail,'背景图验收失败：AI 检测不可用（reason with spaces）。请稍后重试。')
            else: self.assertEqual(self.api.validate_task_environment_background_image('raw',{},f.source)['status'],'accepted')
    def test_validator_detection_order_deduplication_and_overflow_is_not_reclassified(self):
        f=self.f; labels={'a':'A','b':' B   label ','c':'C'}
        f.analysis={'detections':[None,{'present':1,'label':'ignore'}, {'count':'bad','label':'ignore'},
            {'present':True,'label':' B label '},{'count':'1','accessory_id':'a'}, {'count':2,'label':'B   label'},
            {'present':True,'label':'z'*90},{'count':3,'label':'z'*80+'different'}],
            'rule':{'counts':{'a':2,'b':'bad','c':1,'zero':0,'negative':-1,'none':None}}}
        with self.assertRaises(HTTPException) as caught: self.api.validate_task_environment_background_image('raw',{'accessory_labels':labels},f.source)
        self.assertEqual((caught.exception.status_code,caught.exception.detail),(409,'背景图检测到目标配件：B label、A、'+'z'*80+'、C。请清空画面后重新拍摄空背景。'))
        for result in [{'detections':[{'count':float('inf')}]},{'rule':{'counts':{'a':float('inf')}}}]:
            f.analysis=result
            with self.assertRaises(OverflowError): self.api.validate_task_environment_background_image('raw',{},f.source)
        f.analysis=None
        with self.assertRaises(AttributeError): self.api.validate_task_environment_background_image('raw',{},f.source)
    def test_media_permission_before_path_then_basename_and_suffix(self):
        f=self.f; f.rows=[]
        with patch.object(Path,'exists',side_effect=AssertionError('invisible path must not be probed')):
            with self.assertRaises(HTTPException) as caught: self.api.background_image(' raw ','image.PNG')
        self.assertEqual((caught.exception.status_code,caught.exception.detail),(404,'Background image not found')); self.assertEqual(f.events,['user','safe','list'])
        f.rows=[{'id':'safe-set'}]; directory=f.sets/'safe-set'; directory.mkdir(parents=True); source=directory/'image.PNG'; source.write_bytes(b'image')
        response=self.api.background_image('raw','nested/image.PNG'); self.assertEqual(Path(response.path),source)
        (directory/'bad.txt').write_bytes(b'bad')
        for name in ['missing.png','bad.txt']:
            with self.assertRaises(HTTPException) as caught: self.api.background_image('raw',name)
            self.assertEqual(caught.exception.status_code,404)
        f.list.assert_called_with(f.user)
    def test_catalog_admin_target_and_separate_selection_read_order(self):
        f=self.f
        for role,target in [('member',None),('admin','bob'),('admin','')]:
            f.events.clear(); f.user['role']=role; result=self.api.training_background_sets('bob' if target is None else target)
            self.assertEqual(f.events,['user','admin','list','manifest','selected']); f.list.assert_called_with(f.user,target)
            f.selected.assert_called_with('default',f.user,target); self.assertIs(result['background_sets'],f.rows); self.assertEqual(result['default_set_id'],'chosen')
        f.manifest['default_set_id']=''; self.api.training_background_sets(); self.assertIsNone(f.selected.call_args.args[0])
    def test_training_upload_precise_file_metadata_order_and_final_response_overwrite(self):
        f=self.f; result=self.training_upload(); source=f.sets/'chosen/source.png'
        self.assertEqual(source.read_bytes(),b'synthetic upload'); f.unique.assert_called_once_with('Name'); f.current.assert_not_called()
        self.assertEqual(f.events,['unique','clock','owner','meta','enqueue','payload','catalog'])
        self.assertEqual(f.metas,[{'id':'chosen','name':'Name','description':'用户上传背景生成的同环境背景集','source':str(source),
            'created_at':101,'generation_method':'queued_codexcli_imgworker','status':'queued','owner_user_id':'alice'}])
        f.enqueue.assert_called_once_with('chosen','Name',source); self.assertIs(result['task'],f.queued); self.assertEqual(result['task_id'],'job')
        f.catalog={'status':'override','task_id':'replacement','background_set':'from-list'}
        result=self.training_upload(name=' ',file=self.upload('  photo.JPG')); self.assertEqual(result['status'],'override'); self.assertEqual(result['background_set'],'from-list')
        f.unique.assert_called_with('  photo'); self.assertEqual((f.sets/'chosen/source.jpg').read_bytes(),b'synthetic upload')
    def test_training_upload_bad_suffix_and_partial_copy_failure_stop_before_metadata(self):
        f=self.f
        with self.assertRaises(HTTPException) as caught: self.training_upload(file=self.upload('input.txt'))
        self.assertEqual((caught.exception.status_code,caught.exception.detail),(400,'Only image background files are supported')); self.assertEqual(f.events,[])
        error=OSError('partial upload'); original=shutil.copyfileobj
        def copy_once(source,target):
            if copied.call_count==1: target.write(b'partial'); raise error
            return original(source,target)
        with patch.object(shutil,'copyfileobj',side_effect=copy_once) as copied:
            with self.assertRaises(OSError) as caught: self.training_upload()
            self.assertIs(caught.exception,error); copied.assert_called_once()
        self.assertEqual((f.sets/'chosen/source.png').read_bytes(),b'partial'); f.meta.assert_not_called(); f.enqueue.assert_not_called(); f.clock.assert_not_called()
    def test_training_upload_late_errors_do_not_repeat_copy_or_queue(self):
        for stage in ['clock','owner','meta','enqueue','payload','catalog']:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=BackgroundApiFixture(self.root/stage); f.bind(self.api,stack); error=OSError(stage)
                target=getattr(f,stage) if stage!='catalog' else Mock(side_effect=[error,{}])
                if stage!='catalog':
                    previous=target.side_effect; count=[]
                    def first(*args,**kwargs):
                        count.append(True)
                        if len(count)==1: raise error
                        return previous(*args,**kwargs)
                    target.side_effect=first
                with patch.object(shutil,'copyfileobj',wraps=shutil.copyfileobj) as copied,patch.object(self.api,'training_background_sets',target if stage=='catalog' else Mock(return_value=f.catalog)):
                    with self.assertRaises(OSError) as caught: asyncio.run(self.api.upload_training_background_set('Name',self.upload()))
                    self.assertIs(caught.exception,error); copied.assert_called_once(); target.assert_called_once()
                self.assertEqual((f.sets/'chosen/source.png').read_bytes(),b'synthetic upload')
                self.assertEqual(f.enqueue.call_count,int(stage in ['enqueue','payload','catalog']))
    def test_environment_precise_order_aliases_and_all_state_mutations_inside_lock(self):
        f=self.f; original=f.state
        class GuardedState(dict):
            def __setitem__(self,key,value):
                self_outer.assertEqual(f.lock.depth,1); return super().__setitem__(key,value)
        self_outer=self; f.state=GuardedState(original); result=self.environment_upload()
        self.assertIs(result,f.response); self.assertEqual(result,{'old':'value','status':'saved','background_set':{'safe':'saved-bg'}})
        self.assertEqual(f.events,['sanitize','user','tasks','guard','output','clock','validate','background','clock','url','save-task',
            'lock','state-load','state-save','unlock','public','sanitize-public'])
        capture=f.capture/'task/environment_101_abcdef.png'; self.assertEqual(capture.read_bytes(),b'synthetic upload')
        f.guard.assert_called_once_with(f.task,f.user,write=True); f.output.assert_called_once_with('task_environment_backgrounds','alice')
        f.validate.assert_called_once_with('task',f.task,capture)
        f.save_background.assert_called_once_with('task',capture,f.user,display_name='Task · 空场景背景')
        environment=f.task['environment_background']; self.assertIs(environment,f.state['environment_background']); self.assertIs(environment['validation'],f.accepted)
        self.assertEqual(environment,{'background_set_id':'saved-bg','captured_at':101,'source_path':str(capture),'source_url':'/synthetic.png',
            'background_source':'background-source','image_count':6,'generation_method':'local','validation':f.accepted})
        self.assertEqual((f.state['task_name'],f.state['owner_user_id'],f.state['owner_username']),('Task','owner','Owner'))
        f.public.assert_called_once_with('task',user=f.user); self.assertIs(f.saved_tasks[0],f.task); self.assertIs(f.saved_states[0],f.state); self.assertEqual(f.lock.depth,0)
    def test_environment_validation_and_permission_preflight_keep_expected_file_residue(self):
        f=self.f; f.sanitize.side_effect=None; f.sanitize.return_value=''
        with self.assertRaises(HTTPException) as caught: asyncio.run(self.api.upload_ai_task_environment_background('bad',self.upload('bad.txt')))
        self.assertEqual(caught.exception.status_code,404); f.current.assert_not_called()
        f.sanitize.return_value='task'
        with self.assertRaises(HTTPException) as caught: asyncio.run(self.api.upload_ai_task_environment_background('task',self.upload('bad.txt')))
        self.assertEqual(caught.exception.status_code,400); f.current.assert_not_called()
        f.tasks=[]
        with self.assertRaises(HTTPException) as caught: self.environment_upload()
        self.assertEqual(caught.exception.status_code,404); f.guard.assert_not_called(); f.output.assert_not_called()
        f.tasks=[f.task]; f.guard.side_effect=HTTPException(403,'write denied')
        with self.assertRaises(HTTPException) as caught: self.environment_upload()
        self.assertEqual(caught.exception.detail,'write denied'); f.output.assert_not_called()
        f.guard.side_effect=None; f.validate.side_effect=[HTTPException(409,'objects remain'),f.accepted]
        with self.assertRaises(HTTPException) as caught: self.environment_upload()
        self.assertEqual(caught.exception.status_code,409); f.validate.assert_called_once(); f.save_background.assert_not_called()
        self.assertEqual((f.capture/'task/environment_101_abcdef.png').read_bytes(),b'synthetic upload'); f.save_task.assert_not_called(); f.state_load.assert_not_called()
    def test_environment_late_failure_residue_and_no_retries(self):
        for stage in ['background','save_task','state_load','state_save','public','sanitize_public']:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=BackgroundApiFixture(self.root/stage); f.bind(self.api,stack)
                target=f.save_background if stage=='background' else getattr(f,stage); original=target.side_effect; error=OSError(stage); count=[]
                def first(*args,**kwargs):
                    count.append(True)
                    if len(count)==1: raise error
                    return original(*args,**kwargs)
                target.side_effect=first
                with patch.object(shutil,'copyfileobj',wraps=shutil.copyfileobj) as copied:
                    with self.assertRaises(OSError) as caught: self.environment_upload(f)
                    self.assertIs(caught.exception,error); target.assert_called_once(); copied.assert_called_once()
                f.validate.assert_called_once(); f.save_background.assert_called_once(); self.assertEqual(f.lock.depth,0)
                self.assertEqual((f.capture/'task/environment_101_abcdef.png').read_bytes(),b'synthetic upload')
                if stage!='background': self.assertEqual(f.task['background_set_id'],'saved-bg')
                if stage in ['state_save','public','sanitize_public']: self.assertIs(f.state['environment_background'],f.task['environment_background'])
                if stage=='sanitize_public': self.assertEqual(f.response['status'],'saved'); self.assertNotIn('background_set',f.response)
    def test_environment_owner_and_name_fallbacks_preserve_first_matching_task(self):
        f=self.f; f.task.update(name='',owner_user_id='',owner_username=''); duplicate={'id':'task','name':'second'}; f.tasks.append(duplicate)
        self.environment_upload(); self.assertNotIn('background_set_id',duplicate)
        self.assertEqual((f.state['task_name'],f.state['owner_user_id'],f.state['owner_username']),('Old','state-owner','State owner'))
        f.state.update(task_name='',owner_user_id='',owner_username=''); self.environment_upload()
        self.assertEqual((f.state['task_name'],f.state['owner_user_id'],f.state['owner_username']),('','alice','Alice'))
        self.assertEqual(f.save_background.call_args.kwargs['display_name'],'task · 空场景背景')
    def test_http_validation_errors_media_bytes_and_original_route_order(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app=FastAPI(); app.get('/api/backgrounds/{set_id}/{image_name}')(self.api.background_image)
        app.get('/api/training/background-sets')(self.api.training_background_sets)
        app.post('/api/training/background-sets')(self.api.upload_training_background_set)
        app.post('/api/ai/tasks/{task_id}/environment-background')(self.api.upload_ai_task_environment_background)
        with TestClient(app) as client:
            for route in ['/api/training/background-sets','/api/ai/tasks/task/environment-background']:
                response=client.post(route); self.assertEqual(response.status_code,422); self.assertEqual(response.json()['detail'][0]['loc'],['body','file'])
            directory=self.f.sets/'safe-set'; directory.mkdir(parents=True); (directory/'test.png').write_bytes(b'actual bytes')
            response=client.get('/api/backgrounds/visible/test.png'); self.assertEqual(response.content,b'actual bytes'); self.assertEqual(response.status_code,200)
            self.f.rows=[]; response=client.get('/api/backgrounds/hidden/test.png'); self.assertEqual(response.json(),{'detail':'Background image not found'}); self.assertEqual(response.status_code,404)
            for status in [401,403]:
                self.f.current.side_effect=HTTPException(status,'denied')
                for route in ['/api/training/background-sets','/api/backgrounds/visible/test.png']:
                    response=client.get(route); self.assertEqual((response.status_code,response.json()),(status,{'detail':'denied'}))
        paths=[getattr(route,'path','') for route in self.api.app.routes]
        sequence=['/api/backgrounds/{set_id}/{image_name}','/api/training/background-sets','/api/ai/tasks/{task_id}/environment-background','/api/training/start']
        self.assertEqual([paths.index(path) for path in sequence],sorted(paths.index(path) for path in sequence)); self.assertEqual(paths.count('/api/training/background-sets'),2)


    def test_environment_partial_copy_failure_keeps_capture_and_skips_all_later_mutation(self):
        f=self.f; task=copy.deepcopy(f.task); state=copy.deepcopy(f.state); upload=self.upload(); original=shutil.copyfileobj
        error=OSError('partial capture copy')
        def fail_first(source,target):
            if copied.call_count==1: target.write(source.read(4)); raise error
            return original(source,target)
        with patch.object(shutil,'copyfileobj',side_effect=fail_first) as copied,patch.object(self.api,'validate_task_environment_background_image',f.validate):
            with self.assertRaises(OSError) as caught: asyncio.run(self.api.upload_ai_task_environment_background(' raw ',upload))
            self.assertIs(caught.exception,error); copied.assert_called_once()
            self.assertIs(copied.call_args.args[0],upload.file); self.assertTrue(copied.call_args.args[1].closed)
        self.assertEqual(upload.file.tell(),4); self.assertEqual(upload.file.getvalue(),b'synthetic upload')
        capture=f.capture/'task/environment_101_abcdef.png'; self.assertEqual(capture.read_bytes(),b'synt')
        self.assertEqual(list(capture.parent.iterdir()),[capture]); self.assertEqual(f.task,task); self.assertEqual(f.state,state)
        self.assertEqual(f.events,['sanitize','user','tasks','guard','output','clock']); self.assertEqual(f.lock.depth,0)
        for callback in [f.validate,f.save_background,f.url,f.save_task,f.state_load,f.state_save,f.public,f.sanitize_public]: callback.assert_not_called()
        f.clock.assert_called_once(); f.uuid.assert_called_once()

    def test_independent_asgi_apps_real_auth_threadpool_identity_and_upload_files(self):
        import httpx
        import threading
        from uuid import UUID
        from fastapi import FastAPI
        from local_inspection_service.auth.middleware import SecurityDependencies, register_security_middleware
        from local_inspection_service.auth.policy import user_is_admin
        from local_inspection_service.runtime.identity import RequestIdentity
        from local_inspection_service.training.background_validation import BackgroundValidation
        from local_inspection_service.training.background_query import BackgroundQuery
        from local_inspection_service.training.background_uploads import (BackgroundUploadPaths, BackgroundUploadRecords, BackgroundUpload,
            BackgroundCaptureIdentity, BackgroundCapturePaths, BackgroundCaptureTasks, BackgroundCaptureSets, BackgroundCaptureState, BackgroundCapture)
        from local_inspection_service.training.background_api import register
        barrier=threading.Barrier(2); observations=[]
        def build(owner,stamp):
            f=BackgroundApiFixture(self.root/owner); f.user.update(id=owner,username=owner,role='user',permissions=['training_pipeline','ai_detection','inspection'],active=True)
            f.task.update(owner_user_id=owner,owner_username=owner); f.rows=[{'id':owner}]; identity=RequestIdentity(); callbacks=[]
            directory=f.sets/owner; directory.mkdir(parents=True); (directory/'image.png').write_bytes(owner.encode())
            def port(fn): value=Mock(side_effect=fn); callbacks.append(value); return value
            def current():
                user=identity.get(); observations.append((owner,user['id'],threading.get_ident()))
                if threading.current_thread() is not threading.main_thread(): barrier.wait(timeout=10)
                return user
            clock=port(lambda:stamp); uuid=port(lambda:UUID('abcdef00-0000-0000-0000-000000000000'))
            def analyze(image,request_id,model_id,*,image_path):
                self.assertEqual(identity.get()['id'],owner); self.assertTrue(image_path.resolve().is_relative_to(f.root.resolve()))
                self.assertEqual(model_id,'fixture:task'); return {'request_id':owner,'model':{'provider_model':owner}}
            validation=BackgroundValidation(port(lambda value:'task'),port(lambda:'fixture:'),clock,uuid,port(analyze),port(lambda:(lambda value,limit:str(value or '').strip()[:limit])))
            query=BackgroundQuery(port(current),port(user_is_admin),port(lambda value:value),port(f.list),port(f.load),port(lambda:f.selected),port(lambda:f.sets),port(lambda:{'.png'}))
            def save_background(identifier,path,user,display_name=''):
                self.assertEqual(user['id'],owner); self.assertEqual(identity.get()['id'],owner)
                return {'id':'saved-'+owner,'source':str(path),'image_count':1,'generation_method':'fixture'}
            def access(record,user,*,write=False):
                self.assertTrue(write)
                if record['owner_user_id']!=user['id']: raise HTTPException(403,'denied')
            def public(identifier,*,user):
                self.assertEqual(f.lock.depth,0); self.assertEqual(user['id'],owner); return {'owner':owner}
            upload=BackgroundUpload(BackgroundUploadPaths(port(lambda:f.sets),port(lambda:{'.png'})),
                BackgroundUploadRecords(port(f.unique),port(lambda: f.meta),port(f.enqueue),port(f.payload)),
                port(lambda:{'owner_user_id':identity.get()['id']}),clock,port(query.training_background_sets))
            capture=BackgroundCapture(BackgroundCaptureIdentity(port(lambda value:'task'),port(current),port(lambda value:{'id':value['id']})),
                BackgroundCapturePaths(port(lambda:{'.png'}),port(lambda:f.output),port(f.url)),BackgroundCaptureTasks(port(f.tasks_load),port(access),port(f.save_task)),
                BackgroundCaptureSets(port(validation.validate_task_environment_background_image),port(lambda:save_background)),
                BackgroundCaptureState(port(lambda:f.lock),port(f.state_load),port(f.state_save),port(public)),clock,uuid)
            app=FastAPI(); routes=register(app,query,upload,capture)
            def authenticate(request,*,indexed=False):
                cookie=request.cookies.get('fixture'); user=f.user if cookie==owner else ({**f.user,'permissions':[]} if cookie=='denied' else None)
                return user,{'users':[f.user]},False
            register_security_middleware(app,SecurityDependencies(authenticate,lambda store:True,identity,
                lambda path,user:False,lambda origin,host:origin=='https://fixture.invalid',lambda origin:False))
            for callback in callbacks: callback.assert_not_called()
            self.assertEqual(f.events,[]); self.assertEqual(app.router.on_startup,[])
            self.assertEqual(len([r for r in app.routes if getattr(r,'path','').startswith('/api/')]),4)
            return app,f,identity,validation,query,upload,capture
        instances=[build('alice',111),build('bob',222)]
        for name in ['current_auth_user','user_is_admin','safe_background_set_id','sanitize_ai_detection_task_id','list_background_sets',
                     'load_background_sets_manifest','selected_background_set_id','unique_background_set_id','update_background_set_manifest',
                     'current_owner_fields','enqueue_background_set_task','background_set_payload','training_background_sets','load_ai_detection_tasks',
                     'require_record_access','output_write_dir_for_owner','save_task_environment_background_set','validate_task_environment_background_image',
                     'public_output_url','save_ai_detection_task','load_auto_optimize_state','save_auto_optimize_state','public_auto_optimize_state',
                     'public_path_sanitized','analyze_bgr','bounded_text']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected root dependency')))
        async def exercise(instance):
            app,f,identity,*_=instance; owner=f.user['id']; data=cv2.imencode('.png',f.image)[1].tobytes()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://fixture.invalid') as client:
                for method,path in [('GET','/api/training/background-sets'),('GET','/api/backgrounds/'+owner+'/image.png'),
                                    ('POST','/api/training/background-sets'),('POST','/api/ai/tasks/task/environment-background')]:
                    response=await client.request(method,path); self.assertEqual((response.status_code,response.json()),(401,{'detail':'Authentication required'}))
                client.cookies.set('fixture','denied')
                response=await client.get('/api/training/background-sets'); self.assertEqual(response.status_code,403); self.assertEqual(response.json()['detail'],'Permission denied')
                client.cookies.set('fixture',owner)
                response=await client.get('/api/training/background-sets'); self.assertEqual(response.status_code,200); self.assertEqual(response.json()['background_sets'],[{'id':owner}])
                response=await client.get('/api/backgrounds/'+owner+'/image.png'); self.assertEqual(response.content,owner.encode())
                for path in ['/api/training/background-sets','/api/ai/tasks/task/environment-background']:
                    response=await client.post(path); self.assertEqual(response.status_code,422)
                response=await client.post('/api/training/background-sets',data={'name':'Name'},files={'file':('new.png',data,'image/png')})
                self.assertEqual(response.status_code,200); self.assertEqual(response.json()['task_id'],'job'); self.assertEqual((f.sets/'chosen/source.png').read_bytes(),data)
                self.assertEqual(f.metas[0]['owner_user_id'],owner)
                response=await client.post('/api/ai/tasks/task/environment-background',files={'file':('capture.png',data,'image/png')})
                self.assertEqual(response.status_code,200); self.assertEqual(response.json(),{'owner':owner,'status':'saved','background_set':{'id':'saved-'+owner}})
                captured=next((f.capture/'task').glob('*.png')); self.assertEqual(captured.read_bytes(),data)
                self.assertEqual(f.task['environment_background']['validation']['request_id'],owner)
                self.assertIs(f.task['environment_background'],f.state['environment_background']); self.assertEqual(f.state['owner_user_id'],owner)
                self.assertEqual(len(f.saved_tasks),1); self.assertEqual(len(f.saved_states),1); self.assertEqual(f.lock.depth,0)
                self.assertIsNone(identity.get())
        async def both(): await asyncio.gather(*(exercise(instance) for instance in instances))
        asyncio.run(both())
        self.assertTrue(all(owner==actual for owner,actual,_ in observations)); self.assertEqual({owner for owner,_,_ in observations},{'alice','bob'})
        self.assertTrue(any(identifier!=threading.get_ident() for _,_,identifier in observations))
        for _,_,identity,*_ in instances: self.assertIsNone(identity.get())


    def test_training_upload_captures_after_copy_before_clock_owner_and_mapping(self):
        for stage in ['clock','int','owner','keys','getitem']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundApiFixture(self.root/stage); f.bind(self.api,stack); events=[]
                first=Mock(side_effect=f.write_meta); second=Mock(side_effect=f.write_meta); third=Mock(side_effect=f.write_meta)
                self.api.update_background_set_manifest=first
                class Input(io.BytesIO):
                    def read(inner,*args):
                        self.api.update_background_set_manifest=second; return super().read(*args)
                def switch(point):
                    events.append(point)
                    if point==stage: self.api.update_background_set_manifest=third
                class Stamp:
                    def __int__(inner): switch('int'); return 123
                class Owner:
                    def keys(inner): switch('keys'); return ['owner_user_id']
                    def __getitem__(inner,key): switch('getitem'); return 'alice'
                def clock():
                    self.assertEqual((f.sets/'chosen/source.png').read_bytes(),b'copied')
                    switch('clock'); return Stamp()
                def owner(): switch('owner'); return Owner()
                f.clock.side_effect=clock; f.owner.side_effect=owner
                result=self.training_upload(f,file=UploadFile(filename='file.PNG',file=Input(b'copied')))
                expected={'id':'chosen','name':'Name','description':'用户上传背景生成的同环境背景集','source':str(f.sets/'chosen/source.png'),
                    'created_at':123,'generation_method':'queued_codexcli_imgworker','status':'queued','owner_user_id':'alice'}
                self.assertEqual(events,['clock','int','owner','keys','getitem']); first.assert_not_called(); third.assert_not_called()
                second.assert_called_once_with('chosen',**expected); self.assertIs(result['background_set']['meta'],f.metas[0])
                self.assertEqual(result,{'status':'queued','task':f.queued,'task_id':'job','background_set':{'id':'chosen','meta':expected},**f.catalog})
                f.enqueue.assert_called_once_with('chosen','Name',f.sets/'chosen/source.png')
                # Next invocation observes the replacement after a normal copy, without caching a writer.
                result=self.training_upload(f,file=self.upload(data=b'copied')); third.assert_called_once_with('chosen',**expected)

    def test_training_upload_argument_and_captured_write_errors_keep_copy_without_enqueue(self):
        for stage in ['none','clock','owner','keys','getitem','duplicate-created_at','duplicate-id','write']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundApiFixture(self.root/stage); f.bind(self.api,stack); events=[]
                first=Mock(side_effect=OSError('old write')); later=Mock(side_effect=f.write_meta)
                self.api.update_background_set_manifest=None if stage=='none' else first
                class Owner:
                    def keys(inner):
                        events.append('keys')
                        if stage=='keys': raise OSError('keys')
                        return [stage.removeprefix('duplicate-')] if stage.startswith('duplicate-') else ['owner_user_id']
                    def __getitem__(inner,key):
                        events.append('getitem')
                        if stage=='getitem': raise OSError('getitem')
                        return 'alice'
                def clock():
                    events.append('clock'); self.api.update_background_set_manifest=later
                    if stage=='clock': raise OSError('clock')
                    return 101.9
                def owner():
                    events.append('owner')
                    if stage=='owner': raise OSError('owner')
                    return Owner()
                f.clock.side_effect=clock; f.owner.side_effect=owner
                with self.assertRaises(TypeError if stage=='none' or stage.startswith('duplicate-') else OSError): self.training_upload(f)
                self.assertEqual(events, ['clock'] if stage=='clock' else ['clock','owner'] if stage=='owner' else ['clock','owner','keys'] if stage=='keys' or stage.startswith('duplicate-') else ['clock','owner','keys','getitem'])
                self.assertEqual(first.call_count,int(stage=='write')); later.assert_not_called()
                f.enqueue.assert_not_called(); f.payload.assert_not_called(); self.assertNotIn('catalog',f.events)
                self.assertEqual((f.sets/'chosen/source.png').read_bytes(),b'synthetic upload')


    def test_provider_lookup_training_upload_error_follows_copy_precedes_arguments(self):
        from local_inspection_service.training.background_uploads import BackgroundUpload, BackgroundUploadPaths, BackgroundUploadRecords
        f=self.f; catalog=Mock(); error=OSError('lookup')
        def provider():
            self.assertEqual((f.sets/'chosen/source.png').read_bytes(),b'synthetic upload')
            raise error
        lookup=Mock(side_effect=provider)
        service=BackgroundUpload(BackgroundUploadPaths(lambda:f.sets,lambda:{'.png'}),
            BackgroundUploadRecords(f.unique,lookup,f.enqueue,f.payload),f.owner,f.clock,catalog)
        lookup.assert_not_called(); f.clock.assert_not_called(); f.owner.assert_not_called()
        with self.assertRaises(OSError) as caught: asyncio.run(service.upload_training_background_set('Name',self.upload()))
        self.assertIs(caught.exception,error); lookup.assert_called_once_with()
        f.clock.assert_not_called(); f.owner.assert_not_called(); f.enqueue.assert_not_called(); f.payload.assert_not_called(); catalog.assert_not_called()


    def test_new_getter_first_failure_precedes_argument_effects_without_retry(self):
        from dataclasses import replace
        for stage in ['selected','output','save','text-exception','text-provider','text-detection','text-rule']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundApiFixture(self.root/stage); f.bind(self.api,stack)
                error=RuntimeError(stage)
                actual={'selected':f.selected,'output':f.output,'save':f.save_background}.get(stage,lambda value,limit:str(value or '').strip()[:limit])
                next_callback=Mock(side_effect=actual)
                def provide():
                    if getter.call_count==1: raise error
                    return next_callback
                getter=Mock(side_effect=provide)
                if stage=='selected':
                    stack.enter_context(patch.object(self.api._background_query,'selected',getter))
                    action=lambda:self.api.training_background_sets()
                elif stage=='output':
                    service=self.api._background_capture
                    stack.enter_context(patch.object(service,'paths',replace(service.paths,output=getter)))
                    action=lambda:self.environment_upload(f)
                elif stage=='save':
                    service=self.api._background_capture
                    stack.enter_context(patch.object(service,'background',replace(service.background,save=getter)))
                    action=lambda:self.environment_upload(f)
                else:
                    stack.enter_context(patch.object(self.api._background_validation,'text',getter))
                    if stage=='text-exception': f.analyze.side_effect=ValueError('provider')
                    elif stage=='text-provider': f.analysis['ai']={'provider_failure':True,'failure_reason':'offline'}
                    elif stage=='text-detection': f.analysis['detections']=[{'present':True,'accessory_id':'part'}]
                    else: f.analysis['rule']={'counts':{'part':1}}
                    action=lambda:self.api.validate_task_environment_background_image('task',f.task,f.source)
                caught=None
                try: action()
                except BaseException as exc: caught=exc
                self.assertIs(caught,error); getter.assert_called_once(); next_callback.assert_not_called()
                if stage=='output': f.validate.assert_not_called(); self.assertFalse(f.capture.exists())
                if stage=='save': f.save_background.assert_not_called(); f.save_task.assert_not_called()

    def test_callback_capture_precedes_catalog_identity_name_and_text_arguments(self):
        for stage in ['selected','output','save','text-exception','text-provider','text-detection','text-rule']:
            for noncallable in [False,True]:
                with self.subTest(stage=stage,noncallable=noncallable), ExitStack() as stack:
                    f=BackgroundApiFixture(self.root/(stage+str(noncallable))); f.bind(self.api,stack); events=[]
                    name={'selected':'selected_background_set_id','output':'output_write_dir_for_owner','save':'save_task_environment_background_set'}.get(stage,'bounded_text')
                    value={'selected':'chosen','output':f.capture,'save':f.background}.get(stage,'part')
                    selected=None if noncallable else Mock(return_value=value); newer=Mock(return_value=value)
                    stack.enter_context(patch.object(self.api,name,selected))
                    def mutate(): events.append('argument'); setattr(self.api,name,newer)
                    class Mapping(dict):
                        def get(inner,key,default=None):
                            trigger={'selected':'default_set_id','output':'id','save':'name','text-provider':'failure_reason','text-detection':'label','text-rule':'part'}.get(stage)
                            if key==trigger: mutate()
                            return super().get(key,default)
                    if stage=='selected':
                        f.manifest=Mapping(f.manifest); action=lambda:self.api.training_background_sets()
                    elif stage=='output':
                        f.user=Mapping(f.user); action=lambda:self.environment_upload(f)
                    elif stage=='save':
                        f.task=Mapping(f.task); f.tasks=[f.task]; action=lambda:self.environment_upload(f)
                    else:
                        if stage=='text-exception':
                            class Failure(ValueError):
                                def __str__(inner): mutate(); return 'provider'
                            f.analyze.side_effect=Failure()
                        elif stage=='text-provider': f.analysis['ai']=Mapping(provider_failure=True,failure_reason='offline')
                        elif stage=='text-detection': f.analysis['detections']=[Mapping(present=True,accessory_id='part',label='Part')]
                        else: f.task['accessory_labels']=Mapping(part='Part'); f.analysis['rule']={'counts':{'part':1}}
                        action=lambda:self.api.validate_task_environment_background_image('task',f.task,f.source)
                    caught=None
                    try: action()
                    except BaseException as exc: caught=exc
                    if noncallable: self.assertIsInstance(caught,TypeError)
                    elif stage.startswith('text-'):
                        self.assertIsInstance(caught,HTTPException); self.assertEqual(caught.status_code,503 if stage in ['text-exception','text-provider'] else 409)
                    else: self.assertIsNone(caught)
                    self.assertTrue(events); newer.assert_not_called()
                    if selected is not None: selected.assert_called_once()

    def test_first_callback_failures_keep_original_boundaries_without_retry(self):
        cases={
            'training':['unique','meta','owner','clock','enqueue','payload'],
            'environment':['sanitize','current','tasks_load','guard','output','validate','save_background','clock','uuid','url','save_task','state_load','state_save','public','sanitize_public'],
            'catalog':['current','admin','list','load','selected'],
            'media':['current','safe','list'],
            'validation':['sanitize','clock','uuid','analyze'],
        }
        for domain,names in cases.items():
            for name in names:
                with self.subTest(domain=domain,name=name), ExitStack() as stack:
                    f=BackgroundApiFixture(self.root/(domain+'-'+name)); f.bind(self.api,stack)
                    target=getattr(f,name); original=target.side_effect; returned=target.return_value; error=RuntimeError(domain+'-'+name); attempts=[]
                    def fail_first(*args,**kwargs):
                        attempts.append('call')
                        if len(attempts)==1: raise error
                        return original(*args,**kwargs) if callable(original) else returned
                    target.side_effect=fail_first
                    if domain=='training': action=lambda:self.training_upload(f)
                    elif domain=='environment': action=lambda:self.environment_upload(f)
                    elif domain=='catalog': action=lambda:self.api.training_background_sets()
                    elif domain=='media': action=lambda:self.api.background_image('raw','image.png')
                    else: action=lambda:self.api.validate_task_environment_background_image('task',f.task,f.source)
                    caught=None
                    try: action()
                    except BaseException as exc: caught=exc
                    if domain=='validation' and name=='analyze':
                        self.assertIsInstance(caught,HTTPException); self.assertEqual(caught.status_code,503); self.assertIs(caught.__cause__,error)
                    else: self.assertIs(caught,error)
                    self.assertEqual(attempts,['call']); self.assertEqual(target.call_count,1); self.assertEqual(f.lock.depth,0)

    def test_callbacks_refresh_after_nearest_prior_effect_before_arguments(self):
        for site in ['selected','text-error','text-provider','text-detection','text-rule','output','save','update']:
            for mode in ['ordinary','prior','missing']:
                with self.subTest(site=site,mode=mode), patch.dict(self.api.__dict__):
                    _capture_background_api_window(self.api.__dict__,site,mode,self.root)

    def test_direct_image_file_text_and_second_clock_first_errors_never_retry(self):
        cases=['imread','text-exception','text-provider','text-detection','text-rule','media-exists','training-mkdir','training-open','environment-mkdir','environment-open','environment-clock']
        for stage in cases:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundApiFixture(self.root/stage); f.bind(self.api,stack); error=RuntimeError(stage); calls=[]
                index=2 if stage=='environment-clock' else 1
                def first(fn):
                    def invoke(*args,**kwargs):
                        calls.append('call')
                        if len(calls)==index: raise error
                        return fn(*args,**kwargs)
                    return invoke
                if stage=='media-exists':
                    target=f.sets/'safe-set/image.png'; target.parent.mkdir(parents=True); target.write_bytes(f.source.read_bytes())
                    original=Path.exists; failed=first(original)
                    stack.enter_context(patch.object(Path,'exists',autospec=True,side_effect=lambda path:failed(path) if path==target else original(path)))
                    action=lambda:self.api.background_image('set','image.png')
                elif stage.startswith(('training-','environment-')):
                    training=stage.startswith('training-')
                    if stage.endswith('clock'): f.clock.side_effect=first(lambda:101.9)
                    else:
                        operation=stage.rsplit('-',1)[1]; original=getattr(Path,operation); failed=first(original)
                        target_dir=f.sets/'chosen' if training else f.capture/'task'
                        def operation_call(path,*args,**kwargs):
                            matched=path==target_dir if operation=='mkdir' else path.parent==target_dir
                            return failed(path,*args,**kwargs) if matched else original(path,*args,**kwargs)
                        stack.enter_context(patch.object(Path,operation,autospec=True,side_effect=operation_call))
                    action=(lambda:self.training_upload(f)) if training else (lambda:self.environment_upload(f))
                else:
                    if stage=='imread': stack.enter_context(patch.object(cv2,'imread',side_effect=first(cv2.imread)))
                    else:
                        stack.enter_context(patch.object(self.api,'bounded_text',side_effect=first(lambda value,limit:str(value or '').strip()[:limit])))
                        if stage=='text-exception': f.analyze.side_effect=ValueError('provider')
                        elif stage=='text-provider': f.analysis['ai']={'provider_failure':True,'failure_reason':'offline'}
                        elif stage=='text-detection': f.analysis['detections']=[{'present':True,'accessory_id':'part'}]
                        else: f.analysis['rule']={'counts':{'part':1}}
                    action=lambda:self.api.validate_task_environment_background_image('task',f.task,f.source)
                caught=None
                try: action()
                except BaseException as exc: caught=exc
                self.assertIs(caught,error); self.assertEqual(len(calls),index); self.assertEqual(f.lock.depth,0)
                if stage=='environment-clock': f.save_task.assert_not_called(); f.state_load.assert_not_called()

    def test_path_policy_and_state_lock_provider_first_errors_never_retry(self):
        from dataclasses import replace
        for stage in ['prefix','media-sets','media-suffixes','training-sets','training-suffixes','environment-suffixes','state-lock']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundApiFixture(self.root/stage); f.bind(self.api,stack); error=RuntimeError(stage); calls=[]
                value='fixture:' if stage=='prefix' else f.lock if stage=='state-lock' else {'.png'} if stage.endswith('suffixes') else f.sets
                def provider():
                    calls.append('call')
                    if len(calls)==1: raise error
                    return value
                if stage=='prefix':
                    stack.enter_context(patch.object(self.api._background_validation,'prefix',provider))
                    action=lambda:self.api.validate_task_environment_background_image('task',f.task,f.source)
                elif stage.startswith('media-'):
                    target=f.sets/'safe-set/image.png'; target.parent.mkdir(parents=True); target.write_bytes(f.source.read_bytes())
                    stack.enter_context(patch.object(self.api._background_query,stage.split('-')[1],provider))
                    action=lambda:self.api.background_image('set','image.png')
                elif stage.startswith('training-'):
                    service=self.api._background_upload
                    stack.enter_context(patch.object(service,'paths',replace(service.paths,**{stage.split('-')[1]:provider})))
                    action=lambda:self.training_upload(f)
                else:
                    service=self.api._background_capture
                    if stage=='state-lock': stack.enter_context(patch.object(service,'state',replace(service.state,lock=provider)))
                    else: stack.enter_context(patch.object(service,'paths',replace(service.paths,suffixes=provider)))
                    action=lambda:self.environment_upload(f)
                caught=None
                try: action()
                except BaseException as exc: caught=exc
                self.assertIs(caught,error); self.assertEqual(calls,['call']); self.assertEqual(f.lock.depth,0)
                if stage=='state-lock': f.save_task.assert_called_once(); f.state_load.assert_not_called()

    def test_validation_formatter_refreshes_for_each_detection_and_rule_item(self):
        for stage in ['detections','rule']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=BackgroundApiFixture(self.root/('refresh-'+stage)); f.bind(self.api,stack); events=[]
                def later(value,limit): events.append(('B',value,limit)); return 'Beta'
                def first(value,limit):
                    events.append(('A',value,limit)); self.api.bounded_text=later; return 'Alpha'
                stack.enter_context(patch.object(self.api,'bounded_text',first))
                if stage=='detections': f.analysis['detections']=[{'present':True,'label':'one'},{'present':True,'label':'two'}]
                else: f.analysis['rule']={'counts':{'one':1,'two':2}}
                caught=None
                try: self.api.validate_task_environment_background_image('task',f.task,f.source)
                except BaseException as exc: caught=exc
                self.assertIsInstance(caught,HTTPException); self.assertEqual(caught.status_code,409)
                self.assertEqual(events,[('A','one',80),('B','two',80)])
                self.assertEqual(caught.detail,'背景图检测到目标配件：Alpha、Beta。请清空画面后重新拍摄空背景。')

if __name__=='__main__': unittest.main()
