"""Service status orchestration parity with synthetic catalogs and account identities."""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import fields
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_SERVICE_STATUS_REQUESTS_BASELINE_SOURCE')
NAMES=('status','get_config_summary')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==2
        for n in nodes:n.decorator_list=[]
        ns=dict(bindings,Any=Any,Path=Path);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.auth.status_requests import ServiceStatusRequests
    from local_inspection_service.auth.status_requests_ports import StatusRequestAccess,StatusRequestCatalog,StatusRequestRuntime
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    return ServiceStatusRequests(ports(StatusRequestAccess),ports(StatusRequestCatalog),ports(StatusRequestRuntime)),bindings

class StatusRequestsContract(unittest.TestCase):
    def fixture(self):
        user={'id':'u','admin':False};events=[];config={'accessories':[{'id':'a','name':'A'}],'confidence_threshold':0.5,'required_classes':[0],'min_counts':{'0':1},'training':{'private':True},'ocr':{'enabled':True}}
        def spec(id,**kw):return dict(id=id,run_id='run',task_id='task',variant='yolo',label=id,description='description',path='/models/'+id,owner_user_id='u',**kw)
        specs=[spec('one',accessory_labels={'a':'First'},required_accessory_counts={'a':2},confidence_threshold=0.6),spec('two',confidence_threshold=0.7),spec('hidden')];specs[-1]['owner_user_id']='other';generated=spec('ai',task_source='ai_detection_task_config',is_ai_detection=True)
        def trace(name,result):
            def call(*a,**kw):events.append((name,a,kw));return result(*a,**kw) if callable(result) else result
            return call
        b={'current_auth_user':lambda:user,'user_is_admin':lambda u:u['admin'],'scope_config_for_user':trace('scope',lambda c,u,t=None:c),
           'record_visible_to_user':lambda s,u,t:s['owner_user_id']==(t or u['id']),'user_has_permission':lambda u,p:u['admin'],
           'redact_status_payload_for_user':trace('redact',lambda p,u:p),'redact_config_summary_for_user':trace('redact_summary',lambda p,u:p),'public_path_sanitized':trace('sanitize',lambda p:dict(p,sanitized=True)),
           'load_config':trace('config',config),'selected_model_spec':lambda i,c:{'id':'active','is_ai_detection':True},'accessory_uid':lambda i:'fallback',
           'list_training_tasks':trace('training_tasks',[{'job_id':'task','label':'Training','selected_accessory_ids':['a','unknown']}]),'list_trained_model_specs':lambda:specs,
           'legacy_model_specs':lambda:[{'id':'legacy','label':'Legacy','description':'L','path':'/missing'},{'id':'ai-legacy','label':'AI','description':'A','is_ai_detection':True}],
           'list_ai_detection_specialized_model_specs':trace('specialized',[generated]),'ai_detection_tasks_response':trace('ai_tasks',{'tasks':[{'id':'ai-task'}]}),
           '_business_files':SimpleNamespace(exists=trace('exists',lambda p:p.name in ('one','two'))),'public_ai_detection_status':trace('ai_status',{'configured':True}),
           'record_owner_username':lambda s:'Owner','LEGACY_OWNER_ID':'legacy','training_execution_status':trace('execution',{'status':'ready','executor':'worker'}),
           'public_cursor_image2_status':trace('cursor',{'configured':True}),'public_yolo_warmup_status':trace('warmup',{'ready':True}),'CLASS_LABELS':{0:'Class A'},'CLASS_NAMES':{0:'class_a'}}
        service,b=create(b);return SimpleNamespace(s=service,b=b,user=user,events=events,config=config,specs=specs,generated=generated)

    def test_member_scope_visibility_grouping_and_permission_projection(self):
        f=self.fixture();result=f.s.status('other');scope=next(e for e in f.events if e[0]=='scope');self.assertIs(scope[1][1],f.user);self.assertIsNone(scope[1][2]);self.assertEqual([m['id'] for m in result['specialized_models']],['one','two','ai']);self.assertTrue(result['model_exists']);self.assertEqual(result['training_execution'],{'status':'restricted','executor':''});self.assertEqual(result['cursor_image2'],{'status':'restricted','configured':False})
        group=result['specialized_model_tasks'][0];self.assertEqual(group['label'],'A + unknown');self.assertEqual([m['id'] for m in group['models']],['one','two']);self.assertEqual(group['confidence_threshold'],0.7);self.assertEqual(group['required_accessory_counts'],{'a':2});self.assertEqual(result['classes'],[{'class_id':0,'name':'class_a','label':'Class A'}]);self.assertEqual(result['ai_detection_tasks'],[{'id':'ai-task'}]);self.assertEqual(f.events[-1][0],'redact');self.assertIs(f.events[-1][1][0],result)
        self.assertEqual(next(e for e in f.events if e[0]=='execution')[2],{'include_worker_probe':False});self.assertTrue(any(e[0]=='cursor' for e in f.events))

    def test_admin_target_forwarded_and_legacy_short_circuit(self):
        f=self.fixture();f.user['admin']=True;result=f.s.status('other');self.assertEqual([m['id'] for m in result['specialized_models']],['hidden','ai']);self.assertEqual(result['training_execution']['executor'],'worker');self.assertTrue(result['cursor_image2']['configured']);self.assertEqual(next(e for e in f.events if e[0]=='training_tasks')[2],{'user':f.user,'target_user_id':'other'});self.assertEqual(next(e for e in f.events if e[0]=='specialized')[1][2],'other');self.assertFalse(result['available_models'][0]['exists']);self.assertTrue(result['available_models'][1]['exists']);self.assertEqual(result['available_models'][1]['provider_status'],result['ai_detection'])

    def test_summary_sanitize_then_redact_and_scope(self):
        for admin in (False,True):
            f=self.fixture();f.user['admin']=admin;result=f.s.get_config_summary('target');self.assertTrue(result['sanitized']);self.assertEqual(result['training'],{'private':True});self.assertEqual([e[0] for e in f.events],['config','scope','sanitize','redact_summary']);self.assertEqual(f.events[1][1][2],'target' if admin else None);self.assertIs(f.events[-1][1][0],result);self.assertIs(f.events[-1][1][1],f.user)

    def test_error_precedence_and_no_replay(self):
        f=self.fixture();f.b['current_auth_user']=Mock(side_effect=RuntimeError('identity'));f.b['load_config']=Mock()
        with self.assertRaisesRegex(RuntimeError,'identity'):f.s.status()
        f.b['load_config'].assert_not_called()
        f=self.fixture();f.b['CLASS_LABELS']={};f.b['redact_status_payload_for_user']=Mock()
        with self.assertRaises(KeyError):f.s.status()
        f.b['redact_status_payload_for_user'].assert_not_called();self.assertEqual(sum(e[0]=='ai_tasks' for e in f.events),1);self.assertEqual(sum(e[0]=='warmup' for e in f.events),1)
        f=self.fixture();f.b['public_path_sanitized']=Mock(side_effect=RuntimeError('sanitize'));f.b['redact_config_summary_for_user']=Mock()
        with self.assertRaisesRegex(RuntimeError,'sanitize'):f.s.get_config_summary()
        f.b['redact_config_summary_for_user'].assert_not_called()

    def test_scope_selected_before_load_then_later_redactor_rebound(self):
        f=self.fixture();oldscope=f.b['scope_config_for_user']
        def load():f.b['scope_config_for_user']=Mock(side_effect=AssertionError('too late'));f.b['redact_status_payload_for_user']=lambda p,u:dict(p,new=True);return f.config
        f.b['load_config']=load;result=f.s.status();self.assertTrue(result['new']);self.assertEqual(sum(e[0]=='scope' for e in f.events),1);f.b['scope_config_for_user'].assert_not_called()

    def test_same_service_two_request_identities_are_not_retained(self):
        f=self.fixture();identity=ContextVar('status_identity');barrier=threading.Barrier(2);f.b['current_auth_user']=identity.get;f.b['user_is_admin']=lambda u:False;f.b['record_visible_to_user']=lambda s,u,t:s['owner_user_id']==u['id'];f.b['list_ai_detection_specialized_model_specs']=lambda *a:[];f.b['redact_status_payload_for_user']=lambda p,u:dict(p,user=u['id']);f.b['user_has_permission']=lambda u,p:False
        def run(id):
            token=identity.set({'id':id})
            try:barrier.wait(timeout=3);return f.s.status()
            finally:identity.reset(token)
        with ThreadPoolExecutor(max_workers=2) as pool:one=pool.submit(run,'u');two=pool.submit(run,'other');a,b=one.result(timeout=5),two.result(timeout=5)
        self.assertEqual(a['user'],'u');self.assertEqual(b['user'],'other');self.assertEqual([m['id'] for m in a['specialized_models']],['one','two']);self.assertEqual([m['id'] for m in b['specialized_models']],['hidden'])

    @unittest.skipIf(bool(BASELINE),'candidate wiring only')
    def test_wiring_original_route_decorators_and_light_import(self):
        tree=ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8'));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_service_status_requests' for t in n.targets));count=0
        for group in binding.keywords:
            for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
        self.assertEqual(count,25)
        for name,path in [('status','/api/status'),('get_config_summary','/api/config/summary')]:
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);self.assertEqual(len(node.body),1);self.assertIsInstance(node.body[0],ast.Return);self.assertEqual(node.body[0].value.func.attr,name);self.assertEqual(node.decorator_list[0].args[0].value,path)
        subprocess.run([sys.executable,'-B','-c',"import sys; import local_inspection_service.auth.status_requests; assert 'local_inspection_service.server' not in sys.modules"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
