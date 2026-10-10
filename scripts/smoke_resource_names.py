"""Cross-domain resource naming constraints, ownership and exclusion contracts."""
import ast,os,re,sys
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_RESOURCE_NAMES_BASELINE_SOURCE')
NAMES=('resource_name_key','resource_owner_id_for_new_record','duplicate_name_error','assert_unique_accessory_name','task_record_name','task_matches_excluded_identity','assert_unique_task_name','assert_unique_dataset_name','assert_unique_model_name')
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==9
  ns=dict(b,Any=Any,re=re,HTTPException=HTTPException);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
 from local_inspection_service.records.resource_names import ResourceNames
 from local_inspection_service.records.resource_name_ports import NamePolicy,NameCatalogs
 def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
 service=ResourceNames(ports(NamePolicy),ports(NameCatalogs))
 for name in NAMES:
  if name not in b:b[name]=getattr(service,name)
 return service,b
class Contracts(unittest.TestCase):
 def fixture(self):
  b=dict(LEGACY_OWNER_ID='legacy',accessory_uid=lambda i:i['id'],record_owner_id=lambda i:i.get('owner','legacy'),load_pipeline_tasks=Mock(return_value=[]),load_ai_detection_tasks=Mock(return_value=[]),training_resources_payload=Mock(return_value={'datasets':[]}),list_trained_model_specs=Mock(return_value=[]))
  s,b=create(b);return SimpleNamespace(s=s,b=b)
 def conflict(self,fn,label):
  with self.assertRaises(HTTPException) as exc:fn()
  self.assertEqual(exc.exception.status_code,409);self.assertEqual(exc.exception.detail,label+'名称已存在，请换一个名称')
 def test_normalization_false_values_unicode_and_owner_defaults(self):
  f=self.fixture()
  for raw,want in [(None,''),(False,''),(0,''),('  STRAßE\t X\n','strasse x'),(' 名称　  项目 ','名称 项目'),(23,'23')]:self.assertEqual(f.s.resource_name_key(raw),want)
  self.assertEqual(f.s.resource_owner_id_for_new_record({}),'legacy');self.assertEqual(f.s.resource_owner_id_for_new_record({'id':0}),'legacy');self.assertEqual(f.s.resource_owner_id_for_new_record({'id':42}),'42')
 def test_record_name_priority_and_excluded_identity(self):
  f=self.fixture();self.assertEqual(f.s.task_record_name({'name':'','label':'label','candidate_name':'candidate','id':'id'}),'label');self.assertEqual(f.s.task_record_name({}),'')
  for task,want in [({'id':'one'},True),({'id':'two','ai_task_id':'ai'},True),({'id':'two','ai_task_id':''},False)]:self.assertEqual(f.s.task_matches_excluded_identity(task,excluded_pipeline_task_ids={'one'},excluded_ai_task_ids={'ai'}),want)
 def test_blank_name_never_queries_catalogs(self):
  f=self.fixture();f.s.assert_unique_task_name('  ','a');f.s.assert_unique_dataset_name('', 'a',{});f.s.assert_unique_model_name(None,'a')
  for name in ('load_pipeline_tasks','load_ai_detection_tasks','training_resources_payload','list_trained_model_specs'):f.b[name].assert_not_called()
 def test_accessory_owner_alias_and_id_exclusion(self):
  f=self.fixture();c={'accessories':[{'id':'x','owner':'bob','name':'same'},{'id':'a','owner':'alice','label':'Same'}]};f.s.assert_unique_accessory_name(c,'same','alice',exclude_id='a');self.conflict(lambda:f.s.assert_unique_accessory_name(c,' SAME ','alice'),'配件');f.s.assert_unique_accessory_name(c,'same','other')
 def test_linked_task_exclusion_propagates_only_first_match(self):
  f=self.fixture();f.b['load_pipeline_tasks'].return_value=[{'id':'p','ai_task_id':'a','owner':'alice','name':'same'},{'id':'other','ai_task_id':'a','owner':'alice','name':'same'}];f.b['load_ai_detection_tasks'].return_value=[{'id':'a','owner':'alice','name':'same'}];f.s.assert_unique_task_name('same','alice',exclude_pipeline_task_id='p')
  f.b['load_pipeline_tasks'].return_value.append({'id':'unlinked','owner':'alice','name':'same'});self.conflict(lambda:f.s.assert_unique_task_name('same','alice',exclude_pipeline_task_id='p'),'任务')
 def test_pipeline_conflict_precedes_ai_read_and_cross_owner(self):
  f=self.fixture();f.b['load_pipeline_tasks'].return_value=[{'id':'p','name':'same','owner':'alice'}];self.conflict(lambda:f.s.assert_unique_task_name('same','alice'),'任务');f.b['load_ai_detection_tasks'].assert_not_called();f.s.assert_unique_task_name('same','bob');f.b['load_ai_detection_tasks'].assert_called_once()
 def test_ai_exclusion_and_candidate_label(self):
  f=self.fixture();f.b['load_ai_detection_tasks'].return_value=[{'id':'a','candidate_name':'same','owner':'alice'}];f.s.assert_unique_task_name('same','alice',exclude_ai_task_id='a');self.conflict(lambda:f.s.assert_unique_task_name('same','alice'),'任务')
 def test_dataset_scope_exclusion_and_fallback_id(self):
  f=self.fixture();user={'id':'alice'};f.b['training_resources_payload'].return_value={'datasets':[{'id':'same','owner':'alice'}]};self.conflict(lambda:f.s.assert_unique_dataset_name('same','alice',user),'样本集');f.b['training_resources_payload'].assert_called_with(user=user);f.s.assert_unique_dataset_name('same','alice',user,exclude_dataset_id='same')
 def test_model_dedup_first_seen_and_empty_run(self):
  f=self.fixture();f.b['list_trained_model_specs'].return_value=[{'run_id':'','label':'same','owner':'alice'},{'run_id':'r','label':'other','owner':'bob'},{'run_id':'r','label':'same','owner':'alice'},{'run_id':'second','label':'same','owner':'alice'}];f.s.assert_unique_model_name('same','alice',exclude_run_id='second');self.conflict(lambda:f.s.assert_unique_model_name('same','alice'),'模型')
 def test_selected_key_callback_then_late_error_and_partial_reads(self):
  f=self.fixture();called=[]
  def catalog():f.b['duplicate_name_error']=lambda label:called.append(label);return [{'id':'p','name':'same','owner':'alice'}]
  f.b['load_pipeline_tasks']=catalog;f.s.assert_unique_task_name('same','alice');self.assertEqual(called,['任务']);f.b['load_ai_detection_tasks'].assert_called_once()
  f=self.fixture();f.b['load_pipeline_tasks']=Mock(side_effect=RuntimeError('catalog'))
  with self.assertRaisesRegex(RuntimeError,'catalog'):f.s.assert_unique_task_name('name','alice')
  f.b['load_ai_detection_tasks'].assert_not_called()
 @unittest.skipIf(bool(BASELINE),'candidate assembly only')
 def test_wiring_and_import(self):
  import subprocess
  tree=ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8'));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_resource_names' for t in n.targets));count=0
  for group in binding.keywords:
   for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
  self.assertEqual(count,11)
  subprocess.run([sys.executable,'-B','-c',"import sys; import local_inspection_service.records.resource_names; assert 'local_inspection_service.server' not in sys.modules"],cwd=ROOT,check=True)
if __name__=='__main__':unittest.main()
