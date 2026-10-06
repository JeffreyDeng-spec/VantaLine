"""Detection task request ordering, authorization and partial effects."""
import ast,os,sys,unittest
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_inspection_service.schemas.detection import AiDetectionTaskRequest
BASELINE=os.environ.get('VANTALINE_DETECTION_TASK_REQUESTS_BASELINE_SOURCE')
NAMES=('get_ai_detection_tasks','create_ai_detection_task','update_ai_detection_task','delete_ai_detection_task_record','delete_ai_detection_task')
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==5
  for n in nodes:n.decorator_list=[]
  ns=dict(b,Any=Any,HTTPException=HTTPException,AiDetectionTaskRequest=AiDetectionTaskRequest);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
 from local_inspection_service.detection.task_requests import DetectionTaskRequests
 from local_inspection_service.detection.task_request_ports import TaskRequestAccess,TaskRequestPolicy,TaskRequestStore,TaskPipelineSync,TaskRequestClock
 def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
 service=DetectionTaskRequests(ports(TaskRequestAccess),ports(TaskRequestPolicy),ports(TaskRequestStore),ports(TaskPipelineSync),ports(TaskRequestClock))
 for n in NAMES:
  if n not in b:b[n]=getattr(service,n)
 return service,b
class Lock:
 def __init__(self,events):self.events=events;self.held=False
 def __enter__(self):self.held=True;self.events.append('enter')
 def __exit__(self,*args):self.events.append('exit');self.held=False
class Contracts(unittest.TestCase):
 def setUp(self):
  self.events=[];self.lock=Lock(self.events);self.user={'id':'alice'};self.config={'config':1};self.tasks=[{'id':'one'}];self.saved=[];self.existing={'id':'one','name':'old','created_at':12,'owner_user_id':'alice'}
  def mark(name,result=None):
   def fn(*args,**kw):self.events.append((name,args,kw));return result
   return fn
  self.mark=mark
  b=dict(current_auth_user=lambda:self.user,user_is_admin=lambda u:u.get('admin',False),scope_config_for_user=mark('scope',self.config),load_config=mark('config',self.config),current_owner_fields=mark('owner',{'owner_user_id':'alice'}),resource_owner_id_for_new_record=mark('new_owner','alice'),record_owner_id=mark('existing_owner','alice'),require_record_access=mark('access'),assert_unique_task_name=mark('unique'),sanitize_ai_detection_task_id=lambda s:str(s).strip(),ai_detection_task_payload_from_request=mark('payload',{'name':'new'}),ai_detection_tasks_response=lambda *a,**k:dict(response=True),serialize_ai_detection_task=lambda task,config:dict(task),load_pipeline_tasks=mark('pipeline_load',self.tasks),save_pipeline_tasks=mark('pipeline_save'),sync_ready_pipeline_ai_detection_tasks=mark('sync',True),_pipeline_tasks_lock=self.lock,mark_pipeline_ai_task_deleted=mark('pipeline_delete'),find_ai_detection_task=lambda tid:self.existing,save_ai_detection_task=lambda task,**kw:self.saved.append((dict(task),kw)),load_ai_detection_tasks=lambda:list(self.tasks),save_ai_detection_tasks=mark('save_all'),runtime_postgres_repository_or_none=lambda:None,store_read_cache_invalidate=mark('invalidate'),time=SimpleNamespace(time=lambda:100),uuid=SimpleNamespace(uuid4=lambda:SimpleNamespace(hex='a'*32)))
  self.s,self.b=create(b)
 def tags(self):return [e[0] if isinstance(e,tuple) else e for e in self.events]
 def test_list_admin_target_and_lock(self):
  self.s.get_ai_detection_tasks('bob');self.assertEqual(self.events[1][1][2],None);self.assertEqual(self.tags(),['config','scope','enter','pipeline_load','sync','pipeline_save','exit'])
  self.events.clear();self.user['admin']=True;self.s.get_ai_detection_tasks('bob');self.assertEqual(self.events[1][1][2],'bob');self.assertFalse(self.lock.held)
 def test_list_no_change_and_failure_unlock(self):
  self.b['sync_ready_pipeline_ai_detection_tasks']=self.mark('sync',False);self.s.get_ai_detection_tasks();self.assertNotIn('pipeline_save',self.tags())
  self.b['sync_ready_pipeline_ai_detection_tasks']=Mock(side_effect=RuntimeError('sync'))
  with self.assertRaisesRegex(RuntimeError,'sync'):self.s.get_ai_detection_tasks()
  self.assertFalse(self.lock.held)
 def test_create_save_then_projection_and_owner_overlay(self):
  self.b['ai_detection_task_payload_from_request']=self.mark('payload',{'name':'new','owner_user_id':'payload-owner'});out=self.s.create_ai_detection_task(object());task,kw=self.saved[0]
  self.assertEqual(kw,{'prepend':True});self.assertEqual(task,{'id':'aitask_aaaaaaaaaa','created_at':100,'updated_at':100,'owner_user_id':'payload-owner','name':'new'});self.assertEqual(out['status'],'saved');self.assertEqual(out['task'],task);self.assertEqual(self.tags()[:5],['config','scope','payload','new_owner','unique'])
 def test_create_selected_scope_and_partial_response_failure(self):
  def load():self.b['scope_config_for_user']=Mock(side_effect=RuntimeError('late scope'));return self.config
  self.b['load_config']=load
  with self.assertRaisesRegex(RuntimeError,'late scope'):self.s.create_ai_detection_task(object())
  self.assertEqual(len(self.saved),1)
 def test_create_duplicate_stops_before_clock_save(self):
  self.b['assert_unique_task_name']=Mock(side_effect=HTTPException(409,'duplicate'));self.b['time'].time=Mock(side_effect=AssertionError('clock'))
  with self.assertRaises(HTTPException) as err:self.s.create_ai_detection_task(object())
  self.assertEqual(err.exception.status_code,409);self.assertEqual(self.saved,[])
 def test_update_preserves_existing_and_error_order(self):
  out=self.s.update_ai_detection_task(' one ',object());self.assertEqual(out['task']['created_at'],12.0);self.assertEqual(out['task']['id'],'one');self.assertEqual(self.saved[0][1],{});self.assertEqual(self.events[3][0],'access');self.assertEqual(self.events[5][2],{'exclude_ai_task_id':'one'});self.assertEqual(self.existing['name'],'old')
  self.existing=None;self.b['ai_detection_task_payload_from_request']=Mock(side_effect=RuntimeError('payload-first'))
  with self.assertRaisesRegex(RuntimeError,'payload-first'):self.s.update_ai_detection_task('missing',object())
 def test_update_missing_denied_and_timestamp_failure(self):
  self.existing=None
  with self.assertRaises(HTTPException) as err:self.s.update_ai_detection_task('x',object())
  self.assertEqual(err.exception.status_code,404)
  self.existing={'id':'one','created_at':'bad'};self.b['require_record_access']=Mock(side_effect=HTTPException(403,'denied'))
  with self.assertRaises(HTTPException) as err:self.s.update_ai_detection_task('one',object())
  self.assertEqual(err.exception.status_code,403);self.assertEqual(self.saved,[])
  self.b['require_record_access']=self.mark('access')
  with self.assertRaises(ValueError):self.s.update_ai_detection_task('one',object())
  self.assertEqual(self.saved,[])
 def test_delete_missing_and_json_remaining(self):
  self.tasks.extend([{'id':'two'},{'id':'one'}]);self.assertEqual(self.s.delete_ai_detection_task_record(' one ',self.user),'one');self.assertEqual(self.events[-1][1][0],[{'id':'two'}]);self.existing=None;self.assertIsNone(self.s.delete_ai_detection_task_record('none',self.user,missing_ok=True))
  with self.assertRaises(HTTPException) as err:self.s.delete_ai_detection_task_record('none',self.user)
  self.assertEqual(err.exception.status_code,404)
 def test_delete_postgres_invalidate_first_and_failure(self):
  repo=SimpleNamespace(delete_by_primary_key=self.mark('delete'));self.b['runtime_postgres_repository_or_none']=lambda:repo;self.s.delete_ai_detection_task_record('one',self.user);self.assertEqual(self.tags(),['access','invalidate','delete']);self.assertEqual(self.events[-1][1],('ai_detection_tasks',{'id':'one'}))
  repo.delete_by_primary_key=Mock(side_effect=RuntimeError('database'))
  with self.assertRaisesRegex(RuntimeError,'database'):self.s.delete_ai_detection_task('one')
  self.assertNotIn('pipeline_delete',self.tags())
 def test_delete_link_failure_preserves_prior_deletion(self):
  self.b['mark_pipeline_ai_task_deleted']=Mock(side_effect=RuntimeError('link'))
  with self.assertRaisesRegex(RuntimeError,'link'):self.s.delete_ai_detection_task('one')
  self.assertIn('save_all',self.tags())
  self.b['mark_pipeline_ai_task_deleted']=self.mark('pipeline_delete');out=self.s.delete_ai_detection_task('one');self.assertEqual(out['deleted_task_id'],'one');self.assertEqual(out['status'],'deleted')
 @unittest.skipIf(bool(BASELINE),'candidate assembly only')
 def test_constructor_and_actual_assembly(self):
  tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text());binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_detection_task_requests' for t in n.targets));count=0
  for group in binding.keywords:
   for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
  self.assertEqual(count,27)
if __name__=='__main__':unittest.main()
