"""Pipeline AI activation parity without provider calls or persistent storage."""
import ast
from dataclasses import fields
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock,patch
import uuid
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_PIPELINE_AI_ACTIVATION_BASELINE_SOURCE')
NAMES=('upsert_pipeline_ai_detection_task','activate_pipeline_ai_detection_task')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==2
        ns=dict(bindings,Any=Any,json=json,time=time,uuid=uuid);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.pipeline.ai_activation import PipelineAiActivation
    from local_inspection_service.pipeline.ai_activation_ports import ActivationPolicy,ActivationStorage
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=PipelineAiActivation(ports(ActivationPolicy),ports(ActivationStorage));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class ActivationContract(unittest.TestCase):
    def fixture(self):
        events=[];existing={'id':'old','created_at':2,'owner_user_id':'original','owner_username':'original-name','shared_with_user_ids':['keep']};task={'id':'p','name':'Pipeline','accessory_ids':['a'],'owner_user_id':'u','owner_username':'U'};config={'accessories':[{'id':'a','name':'A'}]}
        def save(t,**kw):events.append(('save',t,kw))
        def public(t,c):events.append(('public',t,c));return dict(t,model_id='ai:'+t['id'])
        b={'canonical_pipeline_accessory_ids':lambda c,ids:ids,'HTTPException':HTTPException,'accessory_lookup_by_id':lambda c:{i['id']:i for i in c['accessories']},
           'normalize_pipeline_accessory_counts':lambda c,ids,raw:{i:2 for i in ids},'clean_ai_detection_task_name':lambda name,default:name or default,
           'sanitize_ai_detection_task_id':lambda i:str(i or '').strip(),'normalize_pipeline_detection_method':lambda v:'ai' if v in ('ai','gemini') else 'yolo',
           'current_owner_fields':lambda:{'owner_user_id':'fallback','owner_username':'Fallback'},'find_ai_detection_task':lambda i:existing,
           'save_ai_detection_task':save,'serialize_ai_detection_task':public}
        service,b=create(b);return SimpleNamespace(s=service,b=b,events=events,existing=existing,task=task,config=config)

    def test_create_owner_shared_identity_and_payload(self):
        f=self.fixture();shared=['x'];f.task['shared_with_user_ids']=shared
        with patch.object(time,'time',return_value=12.5),patch.object(uuid,'uuid4',return_value=SimpleNamespace(hex='1234567890abcdef')):result=f.s.upsert_pipeline_ai_detection_task(f.task,f.config)
        record=f.events[0][1];self.assertEqual(record['id'],'aitask_1234567890');self.assertEqual((record['created_at'],record['updated_at']),(12.5,12.5));self.assertEqual(record['selected_accessory_ids'],['a']);self.assertEqual(record['required_accessory_counts'],{'a':2});self.assertEqual(record['accessory_labels'],{'a':'A'});self.assertEqual(record['source'],'pipeline');self.assertIs(record['shared_with_user_ids'],shared);self.assertEqual(f.events[0][2],{'prepend':True});self.assertIs(f.events[1][1],record);self.assertIs(f.events[1][2],f.config);self.assertEqual(result['model_id'],'ai:aitask_1234567890')

    def test_existing_owner_and_sharing_not_overwritten(self):
        f=self.fixture();f.task['ai_task_id']=' old ';f.task['shared_with_user_ids']=['replace']
        with patch.object(time,'time',return_value=9):result=f.s.upsert_pipeline_ai_detection_task(f.task,f.config)
        record=f.events[0][1];self.assertEqual(record['created_at'],2.0);self.assertEqual(record['owner_user_id'],'original');self.assertEqual(record['shared_with_user_ids'],['keep']);self.assertEqual(f.events[0][2],{});self.assertEqual(f.existing['created_at'],2);self.assertNotIn('source',f.existing)
        f=self.fixture();f.task['ai_task_id']='old';f.task.pop('owner_user_id');f.existing['owner_user_id']='';f.existing['owner_username']=''
        with patch.object(time,'time',return_value=9):result=f.s.upsert_pipeline_ai_detection_task(f.task,f.config)
        self.assertEqual(result['owner_user_id'],'fallback');self.assertEqual(result['owner_username'],'Fallback')

    def test_empty_selection_priority_and_projection_failure_after_save(self):
        f=self.fixture();f.task['accessory_ids']=[];f.b['accessory_lookup_by_id']=Mock(side_effect=AssertionError('unexpected'))
        with self.assertRaises(HTTPException) as err:f.s.upsert_pipeline_ai_detection_task(f.task,f.config)
        self.assertEqual(err.exception.status_code,400);f.b['accessory_lookup_by_id'].assert_not_called();self.assertEqual(f.events,[])
        f=self.fixture();f.b['serialize_ai_detection_task']=Mock(side_effect=RuntimeError('public'))
        with patch.object(time,'time',return_value=9),patch.object(uuid,'uuid4',return_value=SimpleNamespace(hex='abc')):
            with self.assertRaisesRegex(RuntimeError,'public'):f.s.upsert_pipeline_ai_detection_task(f.task,f.config)
        self.assertEqual(len(f.events),1);self.assertEqual(f.events[0][0],'save')

    def test_activation_noop_and_full_state(self):
        for changes in ({'detection_method':'yolo'},{'detection_method':'ai','accessory_ids':[]}):
            f=self.fixture();f.task.update(changes);f.b['upsert_pipeline_ai_detection_task']=Mock(side_effect=AssertionError('unexpected'));self.assertFalse(f.s.activate_pipeline_ai_detection_task(f.task,f.config));f.b['upsert_pipeline_ai_detection_task'].assert_not_called()
        f=self.fixture();f.task['params']={'route':'gemini','train_mode':'yolo','retained':True};params=f.task['params'];f.b['upsert_pipeline_ai_detection_task']=lambda t,c:{'id':'a','model_id':'ai:a'}
        with patch.object(time,'time',return_value=10):self.assertTrue(f.s.activate_pipeline_ai_detection_task(f.task,f.config))
        self.assertEqual(f.task['params'],{'route':'ai','retained':True});self.assertEqual(params['train_mode'],'yolo');self.assertEqual((f.task['stage'],f.task['status'],f.task['progress']),('library','completed',100));self.assertEqual(f.task['ai_model_id'],'ai:a');self.assertEqual(f.task['linked_view'],'aiInspect')
        with patch.object(time,'time',return_value=10):self.assertFalse(f.s.activate_pipeline_ai_detection_task(f.task,f.config))

    def test_activation_upsert_before_params_and_atomic_dict_expression_failure(self):
        f=self.fixture();f.task.update(detection_method='ai',params=['bad']);calls=[];f.b['upsert_pipeline_ai_detection_task']=lambda t,c:calls.append('upsert') or {'id':'a','model_id':'ai:a'}
        with self.assertRaises(ValueError):f.s.activate_pipeline_ai_detection_task(f.task,f.config)
        self.assertEqual(calls,['upsert']);self.assertNotIn('stage',f.task)
        f=self.fixture();f.task['detection_method']='ai';f.b['upsert_pipeline_ai_detection_task']=lambda t,c:{'id':'a'};before=dict(f.task)
        with self.assertRaises(KeyError):f.s.activate_pipeline_ai_detection_task(f.task,f.config)
        self.assertEqual(f.task,before)
        f.b['upsert_pipeline_ai_detection_task']=lambda t,c:{'id':'a','model_id':'ai:a'}
        with patch.object(time,'time',side_effect=RuntimeError('clock')):
            with self.assertRaisesRegex(RuntimeError,'clock'):f.s.activate_pipeline_ai_detection_task(f.task,f.config)
        self.assertEqual(f.task,before)

    def test_late_saver_after_owner_and_projection_after_save(self):
        f=self.fixture();f.task.pop('owner_user_id')
        def owner():
            def save(t,**kw):f.events.append(('new_save',t));f.b['serialize_ai_detection_task']=lambda t,c:{'new_public':True}
            f.b['save_ai_detection_task']=save;return {'owner_user_id':'u'}
        f.b['current_owner_fields']=owner
        with patch.object(time,'time',return_value=1),patch.object(uuid,'uuid4',return_value=SimpleNamespace(hex='abc')):self.assertEqual(f.s.upsert_pipeline_ai_detection_task(f.task,f.config),{'new_public':True})
        self.assertEqual(f.events[0][0],'new_save')

    @unittest.skipIf(bool(BASELINE),'candidate wiring only')
    def test_wiring_and_light_import(self):
        from application_integration_source_contract import restore_plc_domain_root
        tree=ast.parse(restore_plc_domain_root((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8')));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_pipeline_ai_activation' for t in n.targets));count=0
        for group in binding.keywords:
            for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
        self.assertEqual(count,12)
        for name in NAMES:
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);self.assertEqual(len(node.body),1);self.assertIsInstance(node.body[0],ast.Return);self.assertEqual(node.body[0].value.func.attr,name)
        subprocess.run([sys.executable,'-B','-c',"import sys; import local_inspection_service.pipeline.ai_activation; assert 'local_inspection_service.server' not in sys.modules"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
