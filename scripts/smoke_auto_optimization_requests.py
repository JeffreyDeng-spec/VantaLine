"""Auto-optimization request workflows with explicit identity/state/action substitutes."""
import ast
import copy
from dataclasses import fields
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_optimization_test_ports import assert_capability_owner
from local_inspection_service.schemas.training import AutoOptimizeSettingsRequest,AutoOptimizeSampleApproveRequest
BASELINE=os.environ.get('VANTALINE_AUTO_REQUESTS_BASELINE_SOURCE')
NAMES=('get_ai_task_auto_optimize_status','update_ai_task_auto_optimize_status','delete_ai_task_auto_optimize_sample','retry_ai_task_auto_optimize_sample','approve_ai_task_auto_optimize_sample')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==5
        for n in nodes:n.decorator_list=[]
        ns=dict(bindings,Any=Any,time=time,copy=copy,cv2=cv2,AutoOptimizeSettingsRequest=AutoOptimizeSettingsRequest,AutoOptimizeSampleApproveRequest=AutoOptimizeSampleApproveRequest);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.training.auto_optimization_requests import AutoOptimizationRequests
    from local_inspection_service.training.auto_optimization_requests_ports import RequestAccess,RequestState,RequestActions
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=AutoOptimizationRequests(ports(RequestAccess),ports(RequestState),ports(RequestActions));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class RequestsContract(unittest.TestCase):
    def fixture(self):
        events=[];depth=[0];user={'id':'owner','username':'Owner'};task={'id':'task','kind':'task','owner_user_id':'owner'}
        sample={'sample_id':'sample','owner_user_id':'owner','label_status':'review_required','source_image':{'path':'source'},'labels':[{'bbox':[1,2,3,4],'sprite':{'path':'sprite'}}],'label_failures':[{'reason':'bad','nested':[1]}],'label_reject_reason':'old','manual_review':{'prior':True}}
        state={'samples':[sample]};image=np.zeros((3,4,3),np.uint8);response={'response':True}
        class Lock:
            def __enter__(self):depth[0]+=1;events.append(('enter',depth[0]))
            def __exit__(self,*a):events.append(('exit',depth[0]));depth[0]-=1
        def access(record,identity,*,write=False):
            events.append(('access',record,identity,write,depth[0]))
            if record.get('owner_user_id')!=identity['id']:raise HTTPException(status_code=403,detail='denied')
        def save(s):events.append(('save',depth[0]))
        def public(task,*,user):events.append(('public',task,user,depth[0]));return response
        b={'sanitize_ai_detection_task_id':lambda t:t.strip(),'safe_record_id':lambda t:t.strip(),'current_auth_user':lambda:user,
           'load_ai_detection_tasks':lambda:[task],'require_record_access':access,'HTTPException':HTTPException,'_auto_optimize_lock':Lock(),
           'load_auto_optimize_state':lambda t:state,'save_auto_optimize_state':save,'public_auto_optimize_state':public,
           'auto_optimize_update_settings':lambda *a:events.append(('settings',a)) or response,'resolve_service_path':lambda s:Path(s),
           '_business_files':SimpleNamespace(exists=lambda p:True),'_image_files':SimpleNamespace(imread=lambda *a:image),
           'analyze_bgr':lambda *a,**kw:events.append(('analyze',a,kw,depth[0])),'AI_DETECTION_TASK_PREFIX':'ai:',
           'auto_optimize_bbox_training_entries':lambda s:[{'accessory_id':'a','bbox_xyxy':[1,2,3,4]}],
           'start_auto_optimize_training_check_worker':lambda *a,**kw:events.append(('start',a,kw,depth[0]))}
        service,b=create(b);return SimpleNamespace(service=service,b=b,events=events,depth=depth,user=user,task=task,sample=sample,state=state,image=image,response=response)

    def approve(self,f,mode=None):
        with patch.object(time,'time',return_value=123.9):return f.service.approve_ai_task_auto_optimize_sample(' task ',' sample ',None if mode is None else SimpleNamespace(mode=mode))

    def test_get_update_clean_ids_permissions_and_request_identity(self):
        f=self.fixture();request=object();self.assertIs(f.service.get_ai_task_auto_optimize_status(' task '),f.response);self.assertFalse(f.events[0][3]);self.assertIs(f.events[1][2],f.user)
        f.events.clear();self.assertIs(f.service.update_ai_task_auto_optimize_status(' task ',request),f.response);self.assertTrue(f.events[0][3]);self.assertIs(f.events[-1][1][1],request)
        f.events.clear();f.b['load_ai_detection_tasks']=lambda:[];self.assertIs(f.service.get_ai_task_auto_optimize_status('task'),f.response);self.assertEqual([e[0] for e in f.events],['public'])
        for name,args in ((NAMES[0],(' ',)),(NAMES[1],(' ',request)),(NAMES[2],('task',' ')),(NAMES[3],(' ','sample')),(NAMES[4],(' ','sample'))):
            with self.assertRaises(HTTPException) as caught:getattr(f.service,name)(*args)
            self.assertEqual(caught.exception.status_code,404)

    def test_task_and_sample_access_denial_before_mutation(self):
        for name in NAMES:
            for denied in ('task','sample'):
                if denied=='sample' and name in NAMES[:2]:continue
                f=self.fixture();getattr(f,denied)['owner_user_id']='other';before=copy.deepcopy(f.state)
                args=('task',) if name==NAMES[0] else ('task',object()) if name==NAMES[1] else ('task','sample')
                with self.assertRaises(HTTPException) as caught:getattr(f.service,name)(*args)
                self.assertEqual(caught.exception.status_code,403);self.assertEqual(f.state,before);self.assertFalse(any(e[0] in ('save','analyze','start','settings') for e in f.events));self.assertEqual(f.depth,[0])

    def test_delete_removes_duplicates_non_records_and_keeps_other_identity(self):
        f=self.fixture();other={'sample_id':'other'};f.state['samples']=[None,f.sample,dict(f.sample),other]
        self.assertIs(f.service.delete_ai_task_auto_optimize_sample('task','sample'),f.response);self.assertEqual(f.state['samples'],[other]);self.assertIs(f.state['samples'][0],other);self.assertEqual([e[0] for e in f.events],['access','enter','access','save','exit','public'])
        with self.assertRaises(HTTPException) as caught:f.service.delete_ai_task_auto_optimize_sample('task','absent')
        self.assertEqual(caught.exception.status_code,404)

    def test_retry_claim_save_before_analysis_and_final_reload(self):
        f=self.fixture();seen=[];load=f.b['load_auto_optimize_state'];f.b['load_auto_optimize_state']=lambda t:seen.append(t) or load(t)
        with patch.object(time,'time',return_value=123.9):result=f.service.retry_ai_task_auto_optimize_sample('task','sample')
        self.assertIs(result,f.response);self.assertEqual(seen,['task','task']);self.assertEqual(f.sample['label_status'],'retried');self.assertEqual(f.sample['retry_requested_at'],123);self.assertEqual(f.sample['retried_at'],123)
        event=next(e for e in f.events if e[0]=='analyze');self.assertIs(event[1][0],f.image);self.assertEqual(event[1][1:],('retry_sample_123','ai:task'));self.assertEqual(event[2],{'image_path':Path('source')});self.assertEqual(event[3],0)
        self.assertEqual([e[0] for e in f.events],['access','enter','access','save','exit','analyze','enter','save','exit','public'])

    def test_retry_missing_decode_and_analysis_failure_partial_state(self):
        for failure in ('missing','decode','analysis'):
            f=self.fixture()
            if failure=='missing':f.b['_business_files'].exists=lambda p:False
            elif failure=='decode':f.b['_image_files'].imread=lambda *a:None
            else:f.b['analyze_bgr']=Mock(side_effect=RuntimeError('analysis'))
            with self.assertRaises((HTTPException,RuntimeError)) as caught:f.service.retry_ai_task_auto_optimize_sample('task','sample')
            if failure!='analysis':self.assertEqual(caught.exception.status_code,404 if failure=='missing' else 400)
            self.assertEqual(f.sample['label_status'],'review_required' if failure=='missing' else 'retrying');self.assertNotIn('retried_at',f.sample);self.assertEqual(f.depth,[0])

    def test_approval_modes_deep_evidence_and_delayed_training_order(self):
        for mode in (None,'sprite','bbox_only','image_only'):
            f=self.fixture();old=f.sample['label_failures'];self.assertIs(self.approve(f,mode),f.response);bbox=mode in ('bbox_only','image_only')
            self.assertEqual(f.sample['label_status'],'trainable_bbox_only' if bbox else 'trainable');review=f.sample['manual_review'];self.assertTrue(review['prior']);self.assertEqual(review['mode'],'bbox_only' if bbox else 'sprite');self.assertEqual(review['approved_by_user_id'],'owner');self.assertEqual(review['previous_label_reject_reason'],'old');self.assertEqual(review['previous_label_failures'],old);self.assertIsNot(review['previous_label_failures'][0]['nested'],old[0]['nested']);self.assertEqual(f.sample['label_failures'],[])
            self.assertEqual(f.sample['manual_approved_at'],123);self.assertEqual(f.sample['label_completed_at'],123);self.assertEqual(f.sample['synthetic_status'],'skipped' if bbox else 'pending');self.assertEqual([e[0] for e in f.events][-4:],['save','exit','public','start']);self.assertEqual(f.events[-1],('start',('task',),{'delay_seconds':2.0},0))

    def test_approval_conflicts_idempotence_and_artifact_alternative(self):
        for scenario,status in [('mode',400),('status',409),('bbox',409),('labels',409),('artifact',409)]:
            f=self.fixture();mode='sprite'
            if scenario=='mode':mode='unknown'
            elif scenario=='status':f.sample['label_status']='pending'
            elif scenario=='bbox':mode='bbox_only';f.b['auto_optimize_bbox_training_entries']=lambda s:[]
            elif scenario=='labels':f.sample['labels']=[]
            elif scenario=='artifact':f.sample['labels']=[{}]
            before=copy.deepcopy(f.state)
            with self.assertRaises(HTTPException) as caught:self.approve(f,mode)
            self.assertEqual(caught.exception.status_code,status);self.assertEqual(f.state,before)
        f=self.fixture();f.sample['label_status']='trainable';self.assertIs(self.approve(f),f.response);self.assertFalse(any(e[0] in ('save','start') for e in f.events));self.assertEqual(next(e for e in f.events if e[0]=='public')[3],1)
        f=self.fixture();f.sample['labels']=[{}];f.sample['label_artifacts']={'mask_url':'existing'};self.approve(f);self.assertEqual(f.sample['label_status'],'trainable')

    def test_approval_save_public_and_start_failure_retains_prior_mutation(self):
        for phase in ('save_auto_optimize_state','public_auto_optimize_state','start_auto_optimize_training_check_worker'):
            f=self.fixture();error=RuntimeError(phase);f.b[phase]=Mock(side_effect=error)
            with self.assertRaises(RuntimeError) as caught:self.approve(f)
            self.assertIs(caught.exception,error);self.assertEqual(f.sample['label_status'],'trainable');self.assertEqual(f.depth,[0]);f.b[phase].assert_called_once()
            if phase!='start_auto_optimize_training_check_worker':self.assertFalse(any(e[0]=='start' for e in f.events))

    @unittest.skipIf(BASELINE,'candidate root assembly and HTTP contracts')
    def test_root_wiring_decorators_and_light_import(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_requests
        for group in (service.access,service.state,service.actions):
            for f in fields(group): assert_capability_owner(self, group, f.name, server)
        for name,args in zip(NAMES,(('t',),('t',object()),('t','s'),('t','s'),('t','s',None))):
            mock=Mock(return_value=object())
            with patch.object(server,'_auto_optimization_requests',SimpleNamespace(**{name:mock})):self.assertIs(getattr(server,name)(*args),mock.return_value)
            mock.assert_called_once_with(*args)
        routes=[r for r in server.app.routes if '/auto-optimize' in getattr(r,'path','')];self.assertEqual(len(routes),5)
        subprocess.run([sys.executable,'-c',"import sys; import local_inspection_service.training.auto_optimization_requests; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
