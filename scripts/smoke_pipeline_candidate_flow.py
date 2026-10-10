"""Pending candidate parity with isolated records and no real database or model calls."""
import ast
from contextlib import contextmanager
from dataclasses import fields
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_PIPELINE_CANDIDATE_FLOW_BASELINE_SOURCE')
NAMES=('canonical_pipeline_accessory_ids','candidate_confirmed_accessory_id','pipeline_candidate_job_status','pipeline_candidate_public','refresh_pipeline_candidate','pipeline_accessories_payload')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==6
        ns=dict(bindings,Any=Any,json=json);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.pipeline.candidate_flow import PipelineCandidateFlow
    from local_inspection_service.pipeline.candidate_flow_ports import CandidateStorage,CandidateProgress,CandidateProjection
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=PipelineCandidateFlow(ports(CandidateStorage),ports(CandidateProgress),ports(CandidateProjection))
    bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class CandidateFlowContract(unittest.TestCase):
    def fixture(self):
        events=[];holder={'locked':False};candidate={'id':'c','jobs':[]};state={'accessory_ids':['a'],'pending_candidate_ids':[]};items={'a':{'id':'a'},'b':{'id':'b'}}
        @contextmanager
        def lock():
            self.assertFalse(holder['locked']);holder['locked']=True;events.append('lock')
            try:yield
            finally:holder['locked']=False;events.append('unlock')
        files=SimpleNamespace(exists=Mock(return_value=True),read_text=Mock(return_value=json.dumps(candidate)))
        def save(path,c):self.assertTrue(holder['locked']);events.append(('save',path,c))
        def update(fn):events.append('update');fn(state);return state
        b={'ACCESSORY_CANDIDATES_DIR':Path('/synthetic-candidates'),'_candidate_store_lock':lock(),'runtime_postgres_repository_or_none':lambda:object(),
           'load_accessory_candidate':lambda i:candidate,'HTTPException':HTTPException,'_business_files':files,'save_accessory_candidate':save,
           'load_config':lambda:{'loaded':True},'load_pipeline_state':lambda:{k:list(v) for k,v in state.items()},'update_pipeline_state':update,
           'candidate_image_jobs':lambda c:c.get('jobs',[]),'IMAGE_JOB_ACTIVE_STATUSES':{'queued','running'},'ensure_candidate_image_job_task_ids':lambda c:False,
           'refresh_codex_image_job':lambda j:j,'store_candidate_image_job':lambda c,j:events.append(('store',j)),
           'resolve_accessory_id':lambda c,i:('a',items['a']) if i in ('a','alias') else (('b',items['b']) if i=='b' else None),
           'enrich_record_audit_fields':lambda c,path=None:dict(c),'accessory_material_type':lambda c:c.get('material_type','object'),'LEGACY_OWNER_ID':'legacy',
           'record_owner_username':lambda c:'legacy-name','accessory_lookup_by_id':lambda c:items,'record_visible_to_user':lambda c,u,t:True,'serialize_accessory':lambda i:dict(i)}
        service,b=create(b);return SimpleNamespace(s=service,b=b,events=events,holder=holder,candidate=candidate,state=state,items=items,files=files)

    def test_canonical_ids_and_progress_precedence(self):
        f=self.fixture();self.assertEqual(f.s.canonical_pipeline_accessory_ids({},['alias','a','missing',None,'b']),['a','b']);self.assertEqual(f.s.candidate_confirmed_accessory_id({'confirmed_accessory_id':' b '}),'b')
        for jobs,expected in [([],('ready',100,'已上传，待确认')),([{'status':'failed'},{'status':'queued','progress':20}],('running',10,'排队中')),([{'status':'running','progress':300}],('running',100,'生成中')),([{'status':'failed'}],('failed',100,'建档失败')),([{'status':'completed'}],('ready',100,'已生成，待确认')),([{'status':'unknown','progress':-10}],('unknown',0,'已上传，待确认'))]:
            self.assertEqual(f.s.pipeline_candidate_job_status({'jobs':jobs}),expected)
        with self.assertRaises(ValueError):f.s.pipeline_candidate_job_status({'jobs':[{'progress':'bad'}]})

    def test_public_audit_defaults_and_error_order(self):
        f=self.fixture();f.b['enrich_record_audit_fields']=lambda c:dict(c,created_at='7',material_type='text')
        result=f.s.pipeline_candidate_public({'id':9});self.assertEqual(result,{'id':'9','name':'新配件','material_type':'text','status':'ready','status_text':'已上传，待确认','progress':100,'created_at':7,'updated_at':7,'owner_user_id':'legacy','owner_username':'legacy-name'})
        f.b['record_owner_username']=Mock(side_effect=AssertionError('unexpected'));self.assertEqual(f.s.pipeline_candidate_public({'owner_username':'named'})['owner_username'],'named')
        f.b['pipeline_candidate_job_status']=Mock(side_effect=RuntimeError('progress'));f.b['accessory_material_type']=Mock()
        with self.assertRaisesRegex(RuntimeError,'progress'):f.s.pipeline_candidate_public({})
        f.b['accessory_material_type'].assert_not_called()

    def test_refresh_postgres_missing_confirmed_and_failure_unlock(self):
        for status in (404,403):
            f=self.fixture();f.b['load_accessory_candidate']=Mock(side_effect=HTTPException(status_code=status))
            if status==404:self.assertEqual(f.s.refresh_pipeline_candidate('c'),(None,True))
            else:
                with self.assertRaises(HTTPException) as error:f.s.refresh_pipeline_candidate('c')
                self.assertEqual(error.exception.status_code,403)
            self.assertFalse(f.holder['locked']);self.assertEqual(f.events,['lock','unlock']);f.files.exists.assert_not_called()
        f=self.fixture();f.candidate['confirmed_accessory_id']='a';f.b['ensure_candidate_image_job_task_ids']=Mock(side_effect=AssertionError('unexpected'))
        self.assertEqual(f.s.refresh_pipeline_candidate('c'),(f.candidate,True));f.b['ensure_candidate_image_job_task_ids'].assert_not_called()

    def test_refresh_files_decode_errors_and_partial_save(self):
        for mode in ('missing','invalid','io'):
            f=self.fixture();f.b['runtime_postgres_repository_or_none']=lambda:None
            if mode=='missing':f.files.exists.return_value=False
            elif mode=='invalid':f.files.read_text.return_value='{'
            else:f.files.read_text.side_effect=OSError('read')
            if mode=='io':
                with self.assertRaisesRegex(OSError,'read'):f.s.refresh_pipeline_candidate('c')
            else:self.assertEqual(f.s.refresh_pipeline_candidate('c'),(None,True))
            self.assertFalse(f.holder['locked'])
        f=self.fixture();j1={'id':'j1','status':'running'};j2={'id':'j2','status':'completed'};f.candidate['jobs']=[j1,j2]
        f.b['refresh_codex_image_job']=lambda j:dict(j,status='completed',ignored=1)
        result,remove=f.s.refresh_pipeline_candidate('c');self.assertFalse(remove);self.assertEqual([e[0] for e in f.events if isinstance(e,tuple)],['store','save']);self.assertEqual(f.events[-1],'unlock')
        f=self.fixture();f.candidate['jobs']=[j1,j2];calls=[]
        def refresh(j):
            calls.append(j['id'])
            if j['id']=='j2':raise RuntimeError('second')
            return dict(j,status='completed')
        f.b['refresh_codex_image_job']=refresh
        with self.assertRaisesRegex(RuntimeError,'second'):f.s.refresh_pipeline_candidate('c')
        self.assertEqual(calls,['j1','j2']);self.assertEqual([e[0] for e in f.events if isinstance(e,tuple)],['store']);self.assertFalse(f.holder['locked'])

    def test_payload_pruning_migration_visibility_and_concurrent_new_candidate(self):
        f=self.fixture();f.state.update(accessory_ids=['alias','a','missing'],pending_candidate_ids=['gone','confirmed','hidden','shown'])
        def refresh(i):
            if i=='gone':return None,True
            if i=='confirmed':f.state['pending_candidate_ids'].append('concurrent');return {'confirmed_accessory_id':'b'},True
            return {'id':i},False
        f.b['refresh_pipeline_candidate']=refresh;seen=[];user={'id':'u'}
        def visible(c,u,t):seen.append((c['id'],u,t));return c['id']=='shown'
        f.b['record_visible_to_user']=visible;f.b['pipeline_candidate_public']=lambda c:c
        result=f.s.pipeline_accessories_payload({},user,'target')
        self.assertEqual(result,{'accessories':[{'id':'b'},{'id':'a'}],'pending_candidates':[{'id':'shown'}]});self.assertEqual(f.state,{'accessory_ids':['b','a'],'pending_candidate_ids':['hidden','shown','concurrent']});self.assertEqual(seen,[('hidden',user,'target'),('shown',user,'target')]);self.assertEqual(f.events,['update','update'])

    def test_payload_error_after_first_prune_no_replay_and_falsey_candidate_retained(self):
        f=self.fixture();f.state.update(accessory_ids=['alias'],pending_candidate_ids=['empty']);f.b['refresh_pipeline_candidate']=lambda i:({},False)
        self.assertEqual(f.s.pipeline_accessories_payload()['pending_candidates'],[]);self.assertEqual(f.state['pending_candidate_ids'],['empty'])
        f=self.fixture();f.state.update(accessory_ids=['alias'],pending_candidate_ids=['bad']);f.b['refresh_pipeline_candidate']=Mock(side_effect=RuntimeError('refresh'))
        with self.assertRaisesRegex(RuntimeError,'refresh'):f.s.pipeline_accessories_payload()
        self.assertEqual(f.state['accessory_ids'],['a']);self.assertEqual(f.events,['update']);f.b['refresh_pipeline_candidate'].assert_called_once_with('bad')

    def test_callback_rebinding_before_next_read_and_no_user_visibility(self):
        f=self.fixture();f.state['pending_candidate_ids']=['c'];f.b['record_visible_to_user']=Mock(side_effect=AssertionError('unexpected'))
        def refresh(i):f.b['pipeline_candidate_public']=lambda c:{'new':True};return {'id':i},False
        f.b['refresh_pipeline_candidate']=refresh;self.assertEqual(f.s.pipeline_accessories_payload(user={})['pending_candidates'],[{'new':True}]);f.b['record_visible_to_user'].assert_not_called()

    @unittest.skipIf(bool(BASELINE),'candidate wiring only')
    def test_narrow_ports_forwarding_and_no_web_import(self):
        from application_integration_source_contract import restore_plc_domain_root
        tree=ast.parse(restore_plc_domain_root(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8')));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_pipeline_candidate_flow' for t in n.targets));count=0
        for group in binding.keywords:
            for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
        self.assertEqual(count,28)
        for name in NAMES:
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);self.assertEqual(len(node.body),1);self.assertIsInstance(node.body[0],ast.Return);self.assertEqual(node.body[0].value.func.attr,name)
        subprocess.run([sys.executable,'-B','-c',"import sys; import local_inspection_service.pipeline.candidate_flow; assert 'local_inspection_service.server' not in sys.modules"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
