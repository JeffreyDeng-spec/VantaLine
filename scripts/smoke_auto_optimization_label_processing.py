"""Replay automatic mask batch state transitions with synthetic executors only."""
import ast
from concurrent.futures import Future
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
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_AUTO_LABEL_PROCESSING_BASELINE_SOURCE')
NAMES=('start_auto_optimize_label_worker','auto_optimize_process_label_sample','auto_optimize_label_worker')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==3
        for node in nodes:node.decorator_list=[]
        ns=dict(bindings,Any=Any,Path=Path,time=time,threading=threading);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.training.auto_optimization_label_processing import AutoOptimizationLabelProcessing
    from local_inspection_service.training.auto_optimization_label_processing_ports import ProcessingState,ProcessingArtifacts,ProcessingExecution
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=AutoOptimizationLabelProcessing(ports(ProcessingState),ports(ProcessingArtifacts),ports(ProcessingExecution));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class ProcessingContract(unittest.TestCase):
    def fixture(self):
        events=[];depth=[0];threads={};state={'settings':{'enabled':True,'max_label_jobs_per_cycle':20},'samples':[]};settings={'configured':True,'model':'pinned-model'}
        class Lock:
            def __enter__(self):depth[0]+=1;events.append(('enter',depth[0]))
            def __exit__(self,*a):events.append(('exit',depth[0]));depth[0]-=1
        class Executor:
            def __init__(self,**kw):events.append(('executor',kw,depth[0]))
            def __enter__(self):return self
            def __exit__(self,*a):events.append(('executor_exit',depth[0]))
            def submit(self,fn,*args):
                events.append(('submit',args,depth[0]));future=Future()
                try:future.set_result(fn(*args))
                except BaseException as exc:future.set_exception(exc)
                return future
        def save(s):events.append(('save',[dict(x) for x in s.get('samples',[]) if isinstance(x,dict)],depth[0]))
        def train(s):events.append(('train',depth[0]));s['settings']['enabled']=False
        def generate(sample,opts,model,path):events.append(('generate',sample,opts,model,path,depth[0]));return [{'ok':True}],[],{'api_calls':[{'attempts':2,'retry_count':1},None,{}, {'attempts':0,'retry_count':-1}]}
        b={'sanitize_ai_detection_task_id':lambda t:t.strip(),'_auto_optimize_lock':Lock(),'_auto_optimize_label_threads':threads,
           'load_auto_optimize_state':lambda task:state,'save_auto_optimize_state':save,'auto_optimize_completed_model_id':lambda s:'',
           'auto_optimize_stop_capture_for_model_locked':Mock(),'default_auto_optimize_settings':lambda:{'enabled':True},'maybe_start_auto_optimize_training_locked':train,
           'output_write_dir_for_owner':lambda category,owner:Path('artifacts')/category/owner,'safe_record_id':lambda t:t.replace('/','_'),
           'auto_optimize_generate_labels_for_sample':generate,'bounded_text':lambda s,n:s[:n],
           'auto_optimize_generate_synthetic_batch_for_sample':lambda *a:events.append(('synthetic',a[2]['sample_id'],depth[0])),
           'image_generation_settings':lambda:settings,'AUTO_OPTIMIZE_MASK_MAX_PARALLEL':4,'ThreadPoolExecutor':Executor,'as_completed':lambda futures:iter(reversed(futures))}
        service,b=create(b);return SimpleNamespace(service=service,b=b,events=events,depth=depth,threads=threads,state=state,settings=settings)

    def run_worker(self,f):
        with patch.object(time,'time',return_value=2000.9):f.service.auto_optimize_label_worker('task')

    def test_process_artifacts_counts_and_exception_conversion(self):
        f=self.fixture();sample={'sample_id':'s','owner_user_id':'owner'}
        with patch.object(time,'time',return_value=123.9):result=f.service.auto_optimize_process_label_sample('t/x',sample,f.settings,'model')
        self.assertEqual((result['sample_id'],result['label_attempts'],result['label_retry_count'],result['completed_at']),('s',4,1,123));self.assertIs(f.events[0][1],sample);self.assertIs(f.events[0][2],f.settings);self.assertEqual(f.events[0][4],Path('artifacts/auto_optimize_masks/owner/t_x'))
        f.b['auto_optimize_generate_labels_for_sample']=Mock(side_effect=RuntimeError('x'*200));result=f.service.auto_optimize_process_label_sample('t',sample,{},'m')
        self.assertEqual(result['failures'],[{'status':'failed','reason':'x'*180}]);self.assertEqual(result['labels'],[]);self.assertEqual(result['label_attempts'],0)
        f.b['auto_optimize_generate_labels_for_sample']=lambda *a:([],[],{'api_calls':[{'attempts':'bad'}]})
        with self.assertRaises(ValueError):f.service.auto_optimize_process_label_sample('t',sample,{},'m')

    def test_starter_sanitization_existing_live_and_start_failure_state(self):
        f=self.fixture();existing=Mock();existing.is_alive.return_value=True;f.threads['task']=existing
        with patch.object(threading,'Thread',side_effect=AssertionError('unexpected')):
            f.service.start_auto_optimize_label_worker(' ');f.service.start_auto_optimize_label_worker(' task ')
        existing.is_alive.return_value=False;thread=Mock();error=RuntimeError('start');thread.start.side_effect=error
        with patch.object(threading,'Thread',return_value=thread) as factory,self.assertRaises(RuntimeError) as caught:f.service.start_auto_optimize_label_worker('task')
        self.assertIs(caught.exception,error);self.assertIs(f.threads['task'],thread);self.assertEqual(f.depth,[0]);factory.assert_called_once_with(target=f.b['auto_optimize_label_worker'],args=('task',),name='auto-opt-label-task',daemon=True)

    def test_not_configured_completed_disabled_and_empty(self):
        f=self.fixture();f.settings['configured']=False;self.run_worker(f);self.assertEqual(f.events,[])
        f=self.fixture();f.b['auto_optimize_completed_model_id']=lambda s:'ready';self.run_worker(f);f.b['auto_optimize_stop_capture_for_model_locked'].assert_called_once_with(f.state,'ready',reason='completed_model_ready');self.assertEqual([e[0] for e in f.events],['enter','save','exit'])
        f=self.fixture();f.state['settings']['enabled']=False;self.run_worker(f);self.assertEqual([e[0] for e in f.events],['enter','exit'])
        f=self.fixture();self.run_worker(f);self.assertEqual([e[0] for e in f.events],['enter','train','exit'])

    def test_batch_claim_before_executor_and_all_settlement_branches(self):
        f=self.fixture();samples=[{'sample_id':str(i),'label_status':'pending','label_completed_at':9,'label_reject_reason':'old'} for i in range(5)];f.state['samples']=samples
        results=[([{}],[]),([{}],[{'reason':'mismatch'}]),([],[{'status':'failed','reason':'bad'}]),([],[])]
        def process(task,sample,settings,model):
            i=int(sample['sample_id']);self.assertIsNot(sample,samples[i]);self.assertIsNot(settings,f.settings);self.assertEqual(model,'pinned-model');self.assertEqual(f.depth,[0]);labels,failures=results[i]
            return {'sample_id':str(i),'labels':labels,'failures':failures,'label_artifacts':{'i':i},'completed_at':2001,'label_attempts':2,'label_retry_count':1}
        f.b['auto_optimize_process_label_sample']=process;self.run_worker(f)
        self.assertEqual([s['label_status'] for s in samples],['trainable','review_required','failed','review_required','pending']);self.assertEqual([s.get('label_reject_reason') for s in samples[:4]],['','ai_detection_ai_mask_class_mismatch','bad','no_valid_label'])
        claimed=next(e for e in f.events if e[0]=='save')[1];self.assertEqual([s['label_status'] for s in claimed],['labeling']*4+['pending']);self.assertNotIn('label_completed_at',claimed[0]);self.assertNotIn('label_reject_reason',claimed[0]);self.assertEqual(claimed[0]['label_parallel_batch_size'],4)
        executor=next(e for e in f.events if e[0]=='executor');self.assertEqual(executor,('executor',{'max_workers':4,'thread_name_prefix':'auto-opt-mask-task'},0));self.assertIn(('synthetic','0',1),f.events);self.assertEqual(f.depth,[0])

    def test_stale_boundary_and_parallel_floor(self):
        for limit,expected in ((20,['old','pending']),(-1,['old'])):
            f=self.fixture();f.state['settings']['max_label_jobs_per_cycle']=limit
            f.state['samples']=[{'sample_id':'old','label_status':'labeling','label_started_at':1099},{'sample_id':'exact','label_status':'labeling','label_started_at':1100},{'sample_id':'missing','label_status':'labeling'},{'sample_id':'zero','label_status':'labeling','label_started_at':0},{'sample_id':'pending','label_status':'pending'}]
            self.run_worker(f);self.assertEqual([e[1][1]['sample_id'] for e in f.events if e[0]=='submit'],expected)

    def test_future_failure_keeps_claims_and_records_bounded_error(self):
        f=self.fixture();f.state['samples']=[{'sample_id':str(i),'label_status':'pending'} for i in range(2)]
        f.b['auto_optimize_process_label_sample']=Mock(side_effect=RuntimeError('x'*300));self.run_worker(f)
        self.assertEqual(f.state['last_label_error'],'x'*240);self.assertEqual([s['label_status'] for s in f.state['samples']],['labeling','labeling']);self.assertFalse(any(e[0]=='train' for e in f.events));self.assertEqual(f.depth,[0])

    def test_synthetic_failure_preserves_earlier_settlement_and_no_retry(self):
        f=self.fixture();sample={'sample_id':'s','label_status':'pending'};f.state['samples']=[sample];f.b['auto_optimize_generate_synthetic_batch_for_sample']=Mock(side_effect=RuntimeError('synthetic'))
        self.run_worker(f);self.assertEqual(sample['label_status'],'trainable');self.assertEqual(sample['label_attempts'],4);self.assertEqual(f.state['last_label_error'],'synthetic');f.b['auto_optimize_generate_synthetic_batch_for_sample'].assert_called_once();self.assertFalse(any(e[0]=='train' for e in f.events))

    def test_failed_error_save_propagates_and_releases_lock(self):
        f=self.fixture();f.b['image_generation_settings']=Mock(side_effect=RuntimeError('settings'));error=RuntimeError('save');f.b['save_auto_optimize_state']=Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:self.run_worker(f)
        self.assertIs(caught.exception,error);self.assertEqual(f.state['last_label_error'],'settings');self.assertEqual(f.depth,[0])

    @unittest.skipIf(BASELINE,'candidate root wiring')
    def test_actual_root_getters_forwarding_and_model_binding(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_label_processing
        for group in (service.state,service.artifacts,service.execution):
            for f in fields(group):self.assertIs(getattr(group,f.name)(),getattr(server,f.name))
        for name,args in zip(NAMES,(('t',),('t',{}, {},'m'),('t',))):
            mock=Mock(return_value=object());fn=getattr(server,name)
            if hasattr(fn,'__wrapped__'):fn=fn.__wrapped__
            with patch.object(server,'_auto_optimization_label_processing',SimpleNamespace(**{name:mock})):self.assertIs(fn(*args),mock.return_value)
            mock.assert_called_once_with(*args)
        self.assertTrue(hasattr(server.auto_optimize_label_worker,'__wrapped__'))
        tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==NAMES[-1]);self.assertEqual(ast.unparse(node.decorator_list[0]),'pinned_model_profiles(resolve_model_profiles, lambda identity: load_auto_optimize_state(identity))')
        subprocess.run([sys.executable,'-c',"import sys; import local_inspection_service.training.auto_optimization_label_processing; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
