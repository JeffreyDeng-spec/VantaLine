"""Shadow evaluation replay with synthetic images and non-destructive file adapters."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_optimization_test_ports import test_capability, assert_capability_owner
BASELINE=os.environ.get('VANTALINE_AUTO_SHADOW_EVALUATION_BASELINE_SOURCE')
NAMES=('start_auto_optimize_shadow_worker','auto_optimize_shadow_worker','maybe_promote_auto_optimize_model_locked','cleanup_auto_optimize_retired_candidate_locked')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==4
        for n in nodes:n.decorator_list=[]
        ns=dict(bindings,Any=Any,Path=Path,time=time,threading=threading,cv2=cv2);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.training.auto_optimization_shadow_evaluation import AutoOptimizationShadowEvaluation
    from local_inspection_service.training.auto_optimization_shadow_evaluation_ports import ShadowState,ShadowObservation,ShadowPromotion
    def ports(cls):return cls(**{f.name:test_capability(bindings, f.name) for f in fields(cls)})
    service=AutoOptimizationShadowEvaluation(ports(ShadowState),ports(ShadowObservation),ports(ShadowPromotion));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class ShadowContract(unittest.TestCase):
    def fixture(self):
        events=[];depth=[0];threads={};image=np.zeros((3,4,3),np.uint8)
        state={'settings':{'enabled':True},'samples':[{'sample_id':'sample','source_image':{'path':'source'},'ai_result':{'rule':{'counts':{'a':2}}}}], 'candidate_models':[{'model_id':'new','job_id':'job','dataset_id':'autoopt_d'}]}
        class Lock:
            def __enter__(self):depth[0]+=1;events.append(('enter',depth[0]))
            def __exit__(self,*a):events.append(('exit',depth[0]));depth[0]-=1
        def analyze(*a,**kw):events.append(('analyze',a,kw,depth[0]));return {'rule':{'counts':{'a':'2'}}}
        b={'sanitize_ai_detection_task_id':lambda t:t.strip(),'_auto_optimize_lock':Lock(),'_auto_optimize_shadow_threads':threads,
           'load_auto_optimize_state':lambda task:state,'save_auto_optimize_state':lambda s:events.append(('save',depth[0])),
           'bounded_text':lambda s,n:s[:n],'resolve_service_path':lambda s:Path(s),'_image_files':SimpleNamespace(imread=lambda *a:image),
           'analyze_bgr':analyze,'safe_record_id':lambda s:s.replace('/','_'),'default_auto_optimize_settings':lambda:{'default':True},
           'LEGACY_OWNER_ID':'legacy','delete_training_task_record':lambda *a,**kw:events.append(('delete',a,kw)),
           'training_run_roots':lambda:[Path('run-a'),Path('run-b')],
           '_business_files':SimpleNamespace(exists=lambda p:True,is_dir=lambda p:True,rmtree=lambda p:events.append(('rmtree',p)))}
        service,b=create(b);return SimpleNamespace(service=service,b=b,state=state,events=events,depth=depth,threads=threads,image=image)

    def run_shadow(self,f):
        with patch.object(time,'time',return_value=123.9),patch.object(time,'sleep',side_effect=lambda n:f.events.append(('sleep',n))):f.service.auto_optimize_shadow_worker('task','sample')

    def test_starter_key_dedupe_and_failed_start_retains_slot(self):
        f=self.fixture();f.b['auto_optimize_shadow_worker']=Mock();thread=Mock();thread.is_alive.return_value=True;f.threads['task:sample']=thread
        with patch.object(threading,'Thread',side_effect=AssertionError('unexpected')):f.service.start_auto_optimize_shadow_worker(' ' ,'sample');f.service.start_auto_optimize_shadow_worker(' task ','sample')
        thread.is_alive.return_value=False;new=Mock();error=RuntimeError('start');new.start.side_effect=error
        with patch.object(threading,'Thread',return_value=new) as factory,self.assertRaises(RuntimeError) as caught:f.service.start_auto_optimize_shadow_worker('task','sample')
        self.assertIs(caught.exception,error);self.assertIs(f.threads['task:sample'],new);self.assertEqual(f.depth,[0]);factory.assert_called_once_with(target=factory.call_args.kwargs['target'],args=('task','sample'),name='auto-opt-shadow-task',daemon=True)
        if BASELINE:self.assertIs(factory.call_args.kwargs['target'],f.b['auto_optimize_shadow_worker'])
        else:
            self.assertIsNot(factory.call_args.kwargs['target'],f.b['auto_optimize_shadow_worker'])
            factory.call_args.kwargs['target'](*factory.call_args.kwargs['args'])
            f.b['auto_optimize_shadow_worker'].assert_not_called()
            self.assertFalse(f.service.close(0))  # Failed start is still owned; invoked late target was revoked.

    def test_gates_and_missing_image_skip_analysis(self):
        for scenario in ('disabled','candidate','sample','image'):
            with self.subTest(scenario=scenario):
                f=self.fixture();f.b['analyze_bgr']=Mock(side_effect=AssertionError('unexpected'))
                if scenario=='disabled':f.state['settings']['enabled']=False
                elif scenario=='candidate':f.state['candidate_models']=[]
                elif scenario=='sample':f.state['samples']=[]
                else:f.b['_image_files'].imread=lambda *a:None
                self.run_shadow(f);f.b['analyze_bgr'].assert_not_called();self.assertNotIn('shadow_runs',f.state);self.assertEqual(f.depth,[0])

    def test_agreement_lock_release_and_bounded_history(self):
        f=self.fixture();f.state['shadow_runs']=[{'old':i} for i in range(5001)];self.run_shadow(f)
        result=f.state['shadow_runs'][0];self.assertEqual(result,{'sample_id':'sample','model_id':'new','status':'completed','agreement':1.0,'ai_counts':{'a':2},'yolo_counts':{'a':'2'},'created_at':123});self.assertEqual(len(f.state['shadow_runs']),5000)
        event=next(e for e in f.events if e[0]=='analyze');self.assertIs(event[1][0],f.image);self.assertEqual(event[1][1:],('shadow_sample','new'));self.assertEqual(event[2],{'image_path':Path('source')});self.assertEqual(event[3],0);self.assertEqual(f.events[-2],('save',1));self.assertEqual(f.depth,[0])
        f=self.fixture();f.b['analyze_bgr']=lambda *a,**kw:{'rule':{}};self.run_shadow(f);self.assertEqual(f.state['shadow_runs'][0]['agreement'],0.0)

    def test_analysis_and_promotion_errors_record_without_undo(self):
        for name in ('analyze_bgr','maybe_promote_auto_optimize_model_locked'):
            f=self.fixture();f.b[name]=Mock(side_effect=RuntimeError('x'*300));self.run_shadow(f);self.assertEqual(f.state['last_shadow_error'],'x'*240);self.assertEqual('shadow_runs' in f.state,name.startswith('maybe'));self.assertEqual(f.depth,[0])
        f=self.fixture();f.b['analyze_bgr']=Mock(side_effect=RuntimeError('analysis'));error=RuntimeError('save');f.b['save_auto_optimize_state']=Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:self.run_shadow(f)
        self.assertIs(caught.exception,error);self.assertEqual(f.depth,[0])

    def test_promotion_thresholds_and_original_mixed_model_history(self):
        f=self.fixture();f.state['settings'].update(auto_promote=True,shadow_min_samples=2,shadow_min_agreement=.98);f.state['active_model_id']='old';f.state['shadow_runs']=[{'status':'completed','model_id':'new','agreement':1.0},{'status':'completed','model_id':'other','agreement':1.0}]
        cleanup=Mock();f.b['cleanup_auto_optimize_retired_candidate_locked']=cleanup
        with patch.object(time,'time',return_value=123.9):f.service.maybe_promote_auto_optimize_model_locked(f.state)
        cleanup.assert_called_once_with(f.state,'old',keep_model_id='new');self.assertEqual(f.state['retired_model_ids'],['old']);self.assertEqual(f.state['active_model_id'],'new');self.assertFalse(f.state['settings']['enabled']);self.assertEqual(f.state['settings']['serving_mode'],'promoted_yolo');self.assertEqual(f.state['last_promotion'],{'model_id':'new','agreement':1.0,'sample_count':2,'promoted_at':123})
        for scenario in ('disabled','few','agreement','empty-model'):
            g=self.fixture();g.state['settings'].update(auto_promote=scenario!='disabled',shadow_min_samples=2,shadow_min_agreement=.98);g.state['shadow_runs']=[{'status':'completed','model_id':'' if scenario=='empty-model' else 'new','agreement':0 if scenario=='agreement' else 1.0}]* (1 if scenario=='few' else 2)
            g.service.maybe_promote_auto_optimize_model_locked(g.state);self.assertNotIn('active_model_id',g.state)

    def test_cleanup_gates_owner_and_delete_order_without_filesystem_deletion(self):
        for scenario in ('same','missing','job','dataset'):
            f=self.fixture();candidate=f.state['candidate_models'][0]
            if scenario=='job':candidate['job_id']=' '
            if scenario=='dataset':candidate['dataset_id']='manual_dataset'
            f.service.cleanup_auto_optimize_retired_candidate_locked(f.state,'absent' if scenario=='missing' else 'new',keep_model_id='new' if scenario=='same' else 'keep');self.assertEqual(f.events,[])
        f=self.fixture()
        with patch.object(time,'time',return_value=123.9):f.service.cleanup_auto_optimize_retired_candidate_locked(f.state,'new',keep_model_id='keep')
        self.assertEqual([e[0] for e in f.events],['delete','rmtree','rmtree']);self.assertEqual(f.events[0][1],('job',{'id':'legacy','username':'legacy','role':'admin'}));self.assertEqual(f.events[0][2],{'missing_ok':True})
        candidate=f.state['candidate_models'][0];self.assertEqual(candidate['status'],'retired_deleted');self.assertEqual(candidate['deleted_at'],123);self.assertEqual(candidate['deleted_paths'],[str(Path('run-a/job')),str(Path('run-b/job'))])

    def test_cleanup_errors_preserve_partial_effects_and_promotion_order(self):
        f=self.fixture();f.b['delete_training_task_record']=Mock(side_effect=RuntimeError('x'*200));f.service.cleanup_auto_optimize_retired_candidate_locked(f.state,'new',keep_model_id='keep');self.assertEqual(f.state['candidate_models'][0]['retire_cleanup_error'],'x'*180);self.assertEqual(f.events,[])
        f=self.fixture();calls=[]
        def remove(path):
            calls.append(path)
            if len(calls)==2:raise OSError('second')
        f.b['_business_files'].rmtree=remove;f.service.cleanup_auto_optimize_retired_candidate_locked(f.state,'new',keep_model_id='keep');self.assertEqual(len(calls),2);self.assertNotIn('deleted_paths',f.state['candidate_models'][0]);self.assertEqual(f.state['candidate_models'][0]['retire_cleanup_error'],'second')
        f=self.fixture();f.state['settings'].update(auto_promote=True,shadow_min_samples=1);f.state['active_model_id']='old';f.state['shadow_runs']=[{'status':'completed','model_id':'new','agreement':1}];error=RuntimeError('cleanup');f.b['cleanup_auto_optimize_retired_candidate_locked']=Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:f.service.maybe_promote_auto_optimize_model_locked(f.state)
        self.assertIs(caught.exception,error);self.assertEqual(f.state['retired_model_ids'],['old']);self.assertEqual(f.state['active_model_id'],'old')

    @unittest.skipIf(BASELINE,'candidate assembly')
    def test_root_forwarders_keyword_only_and_model_binding(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_shadow_evaluation
        for group in (service.state,service.observation,service.promotion):
            for f in fields(group):assert_capability_owner(self, group, f.name, server)
        for name,args,kwargs in zip(NAMES,(('t','s'),('t','s'),({},),({},'old')),({},{},{},{'keep_model_id':'new'})):
            mock=Mock(return_value=object());fn=getattr(server,name)
            if hasattr(fn,'__wrapped__'):fn=fn.__wrapped__
            with patch.object(server,'_auto_optimization_shadow_evaluation',SimpleNamespace(**{name:mock})):self.assertIs(fn(*args,**kwargs),mock.return_value)
            mock.assert_called_once_with(*args,**kwargs)
        self.assertTrue(hasattr(server.auto_optimize_shadow_worker,'__wrapped__'))
        tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==NAMES[1]);self.assertEqual(ast.unparse(node.decorator_list[0]),'pinned_model_profiles(resolve_model_profiles, lambda identity: load_auto_optimize_state(identity))')
        subprocess.run([sys.executable,'-c',"import sys; import local_inspection_service.training.auto_optimization_shadow_evaluation; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
