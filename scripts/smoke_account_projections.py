"""Account projection, media access and model permission behavior contracts."""
import ast,copy,json,os,sys,tempfile,threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import fields
from pathlib import Path,PurePosixPath
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_ACCOUNT_PROJECTIONS_BASELINE_SOURCE')
NAMES=('merge_scoped_accessory_updates','scope_config_for_user','require_analyze_model_permission','output_path_visible_to_user','redact_status_payload_for_user','redact_config_summary_for_user','redact_accessory_payload_for_user')
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==7
  ns=dict(b,Any=Any,Path=Path,PurePosixPath=PurePosixPath,json=json,copy=copy,HTTPException=HTTPException)
  exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
  return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
 from local_inspection_service.auth.account_projections import AccountProjections
 from local_inspection_service.auth.account_projection_ports import AccountAccess,AccountConfig,AccountModels,AccountMedia
 def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
 return AccountProjections(ports(AccountAccess),ports(AccountConfig),ports(AccountModels),ports(AccountMedia)),b
class Contracts(unittest.TestCase):
 def fixture(self):
  actor={'id':'alice','admin':False,'permissions':set()}
  b=dict(current_auth_user=lambda:actor,user_is_admin=lambda u:u['admin'],user_has_permission=lambda u,p:p in u['permissions'],include_internal_runtime_details=lambda u:u['admin'],record_mutable_by_user=lambda i,u:i.get('owner')==u['id'],record_visible_to_user=lambda i,u,t:i.get('owner')==(t or u['id']),accessory_uid=lambda i:i['id'],training_state_for_user=lambda c,u,ids,t:{'selected_accessory_ids':['a','hidden',1],'owner':u['id']},PLC_CAPTURE_RESULTS_KEY='capture',load_config=lambda:{},selected_model_spec=lambda m,c:{'is_ai_detection':m=='ai'},public_ai_detection_status_for_user=lambda u:{'owner':u['id']},OUTPUT_DIR=ROOT/'outputs')
  service,b=create(b)
  if not BASELINE:b['scope_config_for_user']=service.scope_config_for_user
  return SimpleNamespace(s=service,b=b,user=actor)
 def test_scoped_deepcopy_private_keys_and_selected_ids(self):
  f=self.fixture();config={'accessories':[{'id':'a','owner':'alice','nested':[1]},{'id':'b','owner':'bob'},None], 'capture':{},'plc_runtime_coordination':{},'other':{'x':[1]}}
  out=f.s.scope_config_for_user(config);self.assertEqual([i['id'] for i in out['accessories']],['a']);self.assertNotIn('capture',out);self.assertNotIn('plc_runtime_coordination',out);self.assertEqual(out['training']['selected_accessory_ids'],['a']);out['other']['x'].append(2);self.assertEqual(config['other']['x'],[1]);self.assertEqual(len(config['accessories']),3)
  self.assertEqual([i['id'] for i in f.s.scope_config_for_user(config,f.user,'bob')['accessories']],['b'])
 def test_false_user_fallback_and_serialization_failure_order(self):
  f=self.fixture();f.b['current_auth_user']=Mock(return_value=f.user);f.b['training_state_for_user']=Mock();f.b['record_visible_to_user']=Mock()
  with self.assertRaises(TypeError):f.s.scope_config_for_user({'value':object()}, {})
  f.b['current_auth_user'].assert_called_once();f.b['training_state_for_user'].assert_not_called();f.b['record_visible_to_user'].assert_not_called()
 def test_merge_only_existing_mutable_records_last_duplicate_wins(self):
  f=self.fixture();one={'id':'a','owner':'alice'};other={'id':'b','owner':'bob'};full={'accessories':[one,other,None]};replacement={'id':'a','value':3}
  f.s.merge_scoped_accessory_updates(full,{'accessories':[{'id':'a','value':1},replacement,{'id':'b','value':4},{'id':'new'},False]},f.user)
  self.assertIs(full['accessories'][0],replacement);self.assertIs(full['accessories'][1],other);self.assertIsNone(full['accessories'][2]);self.assertEqual(len(full['accessories']),3)
 def test_merge_failure_keeps_original_list(self):
  f=self.fixture();original=[{'id':'a','owner':'alice'},{'id':'b','owner':'alice'}];full={'accessories':original};f.b['record_mutable_by_user']=Mock(side_effect=[True,RuntimeError('deny')])
  with self.assertRaisesRegex(RuntimeError,'deny'):f.s.merge_scoped_accessory_updates(full,{'accessories':[{'id':'a'},{'id':'b'}]},f.user)
  self.assertIs(full['accessories'],original)
 def test_model_permission_short_circuit_and_denial(self):
  f=self.fixture();f.user['permissions']={'inspection'};f.b['load_config']=Mock(side_effect=AssertionError('unneeded'));self.assertIsNone(f.s.require_analyze_model_permission('standard'));f.b['load_config'].assert_not_called()
  f=self.fixture();f.user['permissions']={'ai_detection'};self.assertIsNone(f.s.require_analyze_model_permission('ai'))
  for permission in (set(),{'ai_detection'}):
   f.user['permissions']=permission
   with self.assertRaises(HTTPException) as exc:f.s.require_analyze_model_permission('standard')
   self.assertEqual(exc.exception.status_code,403);self.assertEqual(exc.exception.detail,'Inspection permission required for non-AI detection models')
 def test_permission_selected_callable_before_config_then_late_scope(self):
  f=self.fixture();f.user['permissions']={'ai_detection'};selected=f.b['selected_model_spec'];events=[]
  def load():f.b['selected_model_spec']=Mock(side_effect=AssertionError('late'));events.append('load');return {}
  f.b['load_config']=load;self.assertIsNone(f.s.require_analyze_model_permission('ai'));self.assertEqual(events,['load']);f.b['selected_model_spec'].assert_not_called()
 def test_status_redaction_member_deepcopy_admin_identity(self):
  f=self.fixture();p={'model_path':'private','available_models':[{'path':'p','provider_status':'x'},None],'specialized_models':[{'path':'p','artifact_path':'p','metadata_path':'p','provider_status':'x','id':'m'}],'other':{'a':[1]}}
  before=copy.deepcopy(p);r=f.s.redact_status_payload_for_user(p,f.user);self.assertEqual(p,before);self.assertNotIn('model_path',r);self.assertEqual(r['specialized_models'],[{'id':'m'}]);self.assertEqual(r['available_models'],[{},None]);self.assertEqual(r['ai_detection'],{'owner':'alice'});r['other']['a'].append(2);self.assertEqual(p,before)
  f.user['admin']=True;self.assertIs(f.s.redact_status_payload_for_user(p,f.user),p)
 def test_config_projection_shallow_fields_accessory_list_only(self):
  f=self.fixture();p={'required_classes':[1],'min_counts':{},'private':'x'};r=f.s.redact_config_summary_for_user(p,f.user);self.assertEqual(set(r),{'required_classes','confidence_threshold','min_counts'});self.assertIs(r['required_classes'],p['required_classes']);self.assertIsNone(r['confidence_threshold'])
  a={'source_files':['x'],'original_source_files':'legacy','other':[1]};r=f.s.redact_accessory_payload_for_user(a,f.user);self.assertEqual(r['source_files'],[]);self.assertEqual(r['original_source_files'],'legacy');self.assertEqual(a['source_files'],['x']);self.assertIsNot(a['other'],r['other']);f.user['admin']=True;self.assertIs(f.s.redact_config_summary_for_user(p,f.user),p);self.assertIs(f.s.redact_accessory_payload_for_user(a,f.user),a)
 def test_output_owner_legacy_escape_admin_and_symlink(self):
  f=self.fixture()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);out=root/'outputs';out.mkdir();f.b['OUTPUT_DIR']=out
   for path,allowed in [('/outputs/users/alice/a',True),('/outputs/users/bob/a',False),('/outputs/legacy/a',True),('/outputs/../../escape',False)]:self.assertEqual(f.s.output_path_visible_to_user(path,f.user),allowed)
   if os.name!='nt':
    (out/'escape').symlink_to(root,target_is_directory=True);self.assertFalse(f.s.output_path_visible_to_user('/outputs/escape/private',f.user))
   f.user['admin']=True;self.assertTrue(f.s.output_path_visible_to_user('/outputs/../../escape',f.user))
 def test_concurrent_request_identity_not_stored(self):
  f=self.fixture();identity=ContextVar('account');barrier=threading.Barrier(2);f.b['current_auth_user']=identity.get
  config={'accessories':[{'id':'a','owner':'alice'},{'id':'b','owner':'bob'}]}
  def invoke(who):
   token=identity.set({'id':who})
   try:barrier.wait(timeout=3);return f.s.scope_config_for_user(config)
   finally:identity.reset(token)
  with ThreadPoolExecutor(max_workers=2) as pool:a=pool.submit(invoke,'alice');b=pool.submit(invoke,'bob');left,right=a.result(timeout=5),b.result(timeout=5)
  self.assertEqual([i['id'] for i in left['accessories']],['a']);self.assertEqual([i['id'] for i in right['accessories']],['b'])
 @unittest.skipIf(bool(BASELINE),'candidate assembly only')
 def test_actual_assembly_and_light_import(self):
  import subprocess
  from application_integration_source_contract import restore_account_visibility_root
  tree=ast.parse(restore_account_visibility_root(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8')));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_account_projections' for t in n.targets));count=0
  for group in binding.keywords:
   for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
  self.assertEqual(count,14)
  for name in NAMES:
   fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);self.assertEqual(len(fn.body),1);self.assertEqual(fn.body[0].value.func.attr,name)
  subprocess.run([sys.executable,'-B','-c',"import sys; import local_inspection_service.auth.account_projections; assert 'local_inspection_service.server' not in sys.modules"],cwd=ROOT,check=True)
if __name__=='__main__':unittest.main()
