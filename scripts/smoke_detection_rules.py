"""Detection rule normalization and update failure boundaries."""
import ast,os,sys,unittest
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from local_inspection_service.schemas.detection import RuleConfig,TaskRuleConfig
BASELINE=os.environ.get('VANTALINE_DETECTION_RULES_BASELINE_SOURCE')
NAMES=('task_rule_overrides','apply_task_rule_override_to_spec','update_rules','update_task_rules')
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==4
  for n in nodes:n.decorator_list=[]
  ns=dict(b,Any=Any,HTTPException=HTTPException,RuleConfig=RuleConfig,TaskRuleConfig=TaskRuleConfig);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
 from local_inspection_service.detection.rule_requests import DetectionRules
 from local_inspection_service.detection.rule_request_ports import RulePolicy,RuleStore,RuleAccess
 def ports(cls):
  def capability(name):
   if name in ('CLASS_NAMES','time'):return b[name]
   return lambda *args,**kwargs:b[name](*args,**kwargs)
  return cls(**{f.name:capability(f.name) for f in fields(cls)})
 service=DetectionRules(ports(RulePolicy),ports(RuleStore),ports(RuleAccess))
 for n in NAMES:
  if n not in b:b[n]=getattr(service,n)
 return service,b
class Contracts(unittest.TestCase):
 def setUp(self):
  self.config={};self.saved=[];self.user={'id':'alice'};self.specs=[{'task_id':'one','selected_accessory_ids':['a','b'],'owner':'alice'},{'run_id':'one','selected_accessory_ids':['private'],'owner':'bob'}]
  b=dict(task_rule_id=lambda v:str(v or '').strip(),CLASS_NAMES={0:'part',1:'body'},load_config=lambda:self.config,save_config=lambda c:self.saved.append(c),current_auth_user=lambda:self.user,record_visible_to_user=lambda spec,u:spec['owner']==u['id'],list_trained_model_specs=lambda c:self.specs,time=SimpleNamespace(time=lambda:100))
  self.s,self.b=create(b)
 def rule(self,confidence=.5,counts=None):return SimpleNamespace(confidence_threshold=confidence,required_accessory_counts={'a':2} if counts is None else counts)
 def test_override_shape_and_identity(self):
  rule={'confidence_threshold':.6};config={'task_rules':{'one':rule,'bad':7}};self.assertIs(self.s.task_rule_overrides(config,' one '),rule)
  for conf,tid in [({},'one'),({'task_rules':[]},'one'),(config,''),(config,'bad')]:self.assertEqual(self.s.task_rule_overrides(conf,tid),{})
 def test_no_override_mutates_original_and_default_failure(self):
  spec={'task_id':'one'};self.assertIs(self.s.apply_task_rule_override_to_spec(spec,{}),spec);self.assertEqual(spec['confidence_threshold'],.25)
  with self.assertRaises(ValueError):self.s.apply_task_rule_override_to_spec({'confidence_threshold':.5},{'confidence_threshold':'bad'})
 def test_override_copy_counts_filter_and_clamp(self):
  nested=[];spec={'task_id':'one','selected_accessory_ids':['a'],'nested':nested,'required_accessory_counts':{'old':1}};conf={'task_rules':{'one':{'confidence_threshold':2,'required_accessory_counts':{'a':'3','b':2,'bad':'oops'}}}};out=self.s.apply_task_rule_override_to_spec(spec,conf);self.assertIsNot(out,spec);self.assertIs(out['nested'],nested);self.assertEqual(out['confidence_threshold'],.99);self.assertEqual(out['required_accessory_counts'],{'a':3});self.assertEqual(spec['required_accessory_counts'],{'old':1})
 def test_bad_override_fallback_and_zero_counts_retains(self):
  counts={'prior':2};spec={'run_id':'one','required_accessory_counts':counts};conf={'confidence_threshold':.4,'task_rules':{'one':{'confidence_threshold':'bad','required_accessory_counts':{'a':0,'b':-1,'c':'bad'}}}};out=self.s.apply_task_rule_override_to_spec(spec,conf);self.assertEqual(out['confidence_threshold'],.4);self.assertIs(out['required_accessory_counts'],counts)
  conf['task_rules']['one']['required_accessory_counts']={'a':1000};self.assertEqual(self.s.apply_task_rule_override_to_spec(spec,conf)['required_accessory_counts'],{'a':1000})
 def test_global_rule_validation_before_config(self):
  self.b['load_config']=Mock(side_effect=AssertionError('read'))
  for rule,status in [(SimpleNamespace(confidence_threshold=-1),400),(SimpleNamespace(confidence_threshold=.5,required_classes=[9]),400)]:
   with self.assertRaises(HTTPException) as err:self.s.update_rules(rule)
   self.assertEqual(err.exception.status_code,status)
 def test_global_update_reference_and_partial_mutation(self):
  classes=[0,1];rule=SimpleNamespace(confidence_threshold=1,required_classes=classes,min_counts={'0':0,'1':'3'});out=self.s.update_rules(rule);self.assertIs(out['rule'],self.config);self.assertIs(self.config['required_classes'],classes);self.assertEqual(self.config['min_counts'],{'0':1,'1':3});self.assertIs(self.saved[0],self.config)
  self.saved.clear();rule.min_counts={'0':'bad'};rule.confidence_threshold=.3
  with self.assertRaises(ValueError):self.s.update_rules(rule)
  self.assertEqual(self.config['confidence_threshold'],.3);self.assertEqual(self.saved,[])
 def test_task_invalid_id_threshold_and_visibility(self):
  for tid,rule,status in [('',self.rule(),400),('one',self.rule(float('nan')),400),('none',self.rule(),404)]:
   with self.assertRaises(HTTPException) as err:self.s.update_task_rules(tid,rule)
   self.assertEqual(err.exception.status_code,status)
  self.user={'id':'nobody'}
  with self.assertRaises(HTTPException) as err:self.s.update_task_rules('one',self.rule())
  self.assertEqual(err.exception.status_code,404);self.assertEqual(self.saved,[])
 def test_task_counts_filter_clamp_and_return_alias(self):
  out=self.s.update_task_rules(' one ',self.rule(0,{' a ':1000,'b':'3','private':7,'':2,'unknown':9}));self.assertEqual(out['rule'],{'confidence_threshold':.001,'required_accessory_counts':{'a':99,'b':3},'updated_at':100});self.assertIs(out['rule'],self.config['task_rules']['one']);self.assertIs(self.saved[0],self.config)
 def test_task_no_counts_and_existing_malformed_store(self):
  with self.assertRaises(HTTPException) as err:self.s.update_task_rules('one',self.rule(counts={'a':0,'b':'bad'}))
  self.assertEqual(err.exception.status_code,400);self.assertEqual(self.saved,[])
  self.config['task_rules']=[]
  with self.assertRaises(TypeError):self.s.update_task_rules('one',self.rule())
 def test_save_failure_keeps_original_mutation(self):
  self.b['save_config']=Mock(side_effect=RuntimeError('save'))
  with self.assertRaisesRegex(RuntimeError,'save'):self.s.update_task_rules('one',self.rule())
  self.assertIn('one',self.config['task_rules'])
 @unittest.skipIf(bool(BASELINE),'candidate assembly only')
 def test_actual_assembly(self):
  tree=ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py'));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_detection_rule_requests' for t in n.targets));count=0
  for group in binding.keywords:
   for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Name);self.assertEqual(kw.arg,kw.value.id);count+=1
  self.assertEqual(count,8)
  self.assertEqual(sum(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_detection_rule_requests' for t in n.targets) for n in tree.body),1)
  import subprocess,tempfile
  with tempfile.TemporaryDirectory(prefix='rule-assembly-') as tmp:
   (Path(tmp)/'local_inspection_service/static').mkdir(parents=True)
   env={**os.environ,'LOCAL_INSPECTION_ROOT':tmp,'VANTALINE_DATA_STORE':'json','VANTALINE_LABEL_INSPECTION_ENABLED':'false','LOCAL_INSPECTION_AUTO_RESUME_WORKER':'0','YOLO_AUTOINSTALL':'false'}
   subprocess.run([sys.executable,'-X','utf8','-B','-c',"from local_inspection_service import server; from local_inspection_service.detection.rule_requests import DetectionRules; from local_inspection_service.detection.rules import CountRules; assert isinstance(server._detection_rule_requests,DetectionRules); assert isinstance(server._detection_rules,CountRules); assert server.apply_task_rule_override_to_spec({}, {}) == {'confidence_threshold': .25}"],cwd=ROOT,env=env,check=True)

if __name__=='__main__':unittest.main()
