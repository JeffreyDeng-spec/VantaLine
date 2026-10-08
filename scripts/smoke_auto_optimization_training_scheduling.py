"""Training scheduling contracts: no real models, processes, DB or paid calls."""
import ast
from contextvars import ContextVar
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
from auto_optimization_test_ports import test_capability, assert_capability_owner
BASELINE=os.environ.get('VANTALINE_AUTO_TRAINING_SCHEDULING_BASELINE_SOURCE')
NAMES=('maybe_start_auto_optimize_training_locked','auto_optimize_training_check_worker','start_auto_optimize_training_check_worker')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==3
        for node in nodes:node.decorator_list=[]
        ns=dict(bindings,Any=Any,time=time,os=os,threading=threading)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.training.auto_optimization_training_scheduling import AutoOptimizationTrainingScheduling
    from local_inspection_service.training.auto_optimization_training_scheduling_ports import SchedulingPolicy,SchedulingSubmission,SchedulingState
    def ports(cls):return cls(**{f.name:test_capability(bindings, f.name) for f in fields(cls)})
    service=AutoOptimizationTrainingScheduling(ports(SchedulingPolicy),ports(SchedulingSubmission),ports(SchedulingState))
    bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class SchedulingContract(unittest.TestCase):
    def fixture(self):
        events=[];identity=ContextVar('scheduling-user',default=None);identity.set({'id':'caller'});depth=[0]
        class Lock:
            def __enter__(self):depth[0]+=1;events.append(('enter',depth[0]))
            def __exit__(self,*args):events.append(('exit',depth[0]));depth[0]-=1
        state={'task_id':'task','owner_user_id':'owner','owner_username':'Owner','settings':{'enabled':True},'samples':[{'label_status':s,'sample_id':str(i)} for i,s in enumerate(('trainable','trainable_bbox_only','negative','negative'))]}
        dataset={'id':'dataset','selected_accessory_ids':['part'],'sample_count':9,'background_set_id':'bg'}
        def build(task,s,samples):events.append(('build',task,list(samples)));return dataset
        def save(s):events.append(('save',list(s.get('datasets',[])),list(s.get('candidate_models',[])),depth[0]))
        def load_config():events.append(('config',identity.get()));return {'config':True}
        def selected(config,ids):events.append(('selected',identity.get(),ids));return [{'id':'part'}]
        def enqueue(request,selected,action,*,dataset):events.append(('enqueue',identity.get(),request,selected,action,dataset));return {'job_id':'job','status':'running'}
        b={'auto_optimize_completed_model_id':lambda s:'','auto_optimize_stop_capture_for_model_locked':Mock(),
           'default_auto_optimize_settings':lambda:{'enabled':True},'auto_optimize_training_requirements':lambda opts,real_positive_source_count=0:{'min_trainable_samples':1,'min_positive_samples':1,'min_negative_samples':1},
           'auto_optimize_samples_per_real_image':lambda opts:3,'auto_optimize_positive_derivatives_per_real_image':lambda opts:2,
           'auto_optimize_negative_samples_per_real_image':lambda opts:1,'AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT':2,
           'auto_optimize_training_parameters':lambda opts:{'training_epochs':5,'training_image_size':640},
           'build_auto_optimize_dataset':build,'LEGACY_OWNER_ID':'legacy','_request_user':identity,
           'scope_config_for_user':lambda config,user:config,'load_config':load_config,'selected_accessories':selected,
           'TrainingStartRequest':lambda **kw:SimpleNamespace(**kw),'pipeline_ai_task_id':lambda t:'pipeline:'+t,'enqueue_training_task':enqueue,
           'sanitize_ai_detection_task_id':lambda t:t.strip(),'_auto_optimize_lock':Lock(),'load_auto_optimize_state':lambda t:state,
           'save_auto_optimize_state':save,'bounded_text':lambda s,n:s[:n]}
        service,b=create(b)
        return SimpleNamespace(service=service,b=b,state=state,dataset=dataset,events=events,identity=identity,depth=depth)

    def run_admission(self,f):
        with patch.dict(os.environ,{'VANTALINE_AUTO_OPT_NEGATIVE_RATIO':'0.25'}),patch.object(time,'time',return_value=123.9):
            return f.service.maybe_start_auto_optimize_training_locked(f.state)

    def test_completed_disabled_thresholds_and_active_candidate(self):
        f=self.fixture();f.b['auto_optimize_completed_model_id']=lambda s:'ready';self.run_admission(f)
        f.b['auto_optimize_stop_capture_for_model_locked'].assert_called_once_with(f.state,'ready',reason='completed_model_ready');self.assertEqual(f.events,[])
        for scenario in ('disabled','total','positive','negative','queued','running'):
            with self.subTest(scenario=scenario):
                f=self.fixture()
                if scenario=='disabled':f.state['settings']['enabled']=False
                elif scenario in ('queued','running'):f.state['candidate_models']=[{'status':scenario}]
                else:
                    required={'min_trainable_samples':1,'min_positive_samples':1,'min_negative_samples':1};required[{'total':'min_trainable_samples','positive':'min_positive_samples','negative':'min_negative_samples'}[scenario]]=100
                    f.b['auto_optimize_training_requirements']=lambda *a,**kw:required
                self.run_admission(f);self.assertEqual(f.events,[])

    def test_submission_order_counts_identity_and_candidate(self):
        f=self.fixture();self.run_admission(f)
        self.assertEqual([e[0] for e in f.events],['build','save','config','selected','enqueue','save'])
        self.assertEqual([s['sample_id'] for s in f.events[0][2]],['0','1','2']);self.assertIs(f.state['datasets'][0],f.dataset)
        event=f.events[-2];self.assertEqual(event[1],{'id':'owner','username':'Owner','role':'admin'});self.assertEqual(event[4],'train_model');self.assertIs(event[5],f.dataset)
        self.assertEqual(vars(event[2]),{'selected_accessory_ids':['part'],'sample_count':9,'train_mode':'yolo','dataset_id':'dataset','epochs':5,'image_size':640,'background_set_id':'bg','pipeline_task_id':'pipeline:task','pipeline_task_name':'task'})
        self.assertEqual(f.identity.get(),{'id':'caller'});candidate=f.state['candidate_models'][0]
        self.assertEqual((candidate['job_id'],candidate['status'],candidate['model_id'],candidate['created_at']),('job','running','trained_job__yolo',123))

    def test_dataset_none_and_no_selection_keep_original_partial_state(self):
        f=self.fixture();f.b['build_auto_optimize_dataset']=lambda *a:None;self.run_admission(f);self.assertEqual([e[0] for e in f.events],['save']);self.assertNotIn('datasets',f.state)
        f=self.fixture();f.b['selected_accessories']=lambda *a:[];self.run_admission(f);self.assertIs(f.state['datasets'][0],f.dataset);self.assertNotIn('candidate_models',f.state);self.assertEqual(f.identity.get(),{'id':'caller'})

    def test_errors_restore_identity_and_preserve_persisted_dataset(self):
        for name in ('scope_config_for_user','selected_accessories','TrainingStartRequest','enqueue_training_task'):
            with self.subTest(name=name):
                f=self.fixture();error=RuntimeError(name);f.b[name]=Mock(side_effect=error)
                with self.assertRaises(RuntimeError) as caught:self.run_admission(f)
                self.assertIs(caught.exception,error);self.assertEqual(f.identity.get(),{'id':'caller'});self.assertIs(f.state['datasets'][0],f.dataset);self.assertNotIn('candidate_models',f.state)

    def test_legacy_owner_and_callback_selection_before_load(self):
        f=self.fixture();f.state.pop('owner_user_id');f.state.pop('owner_username');late=Mock(side_effect=AssertionError('late scope'))
        def load():f.b['scope_config_for_user']=late;return {}
        f.b['load_config']=load;self.run_admission(f);late.assert_not_called();event=next(e for e in f.events if e[0]=='enqueue');self.assertEqual(event[1]['id'],'legacy');self.assertEqual(f.identity.get(),{'id':'caller'})

    def test_check_delay_lock_order_and_error_recovery(self):
        f=self.fixture();seen=[]
        def admit(state):seen.append((state,f.depth[0]))
        f.b['maybe_start_auto_optimize_training_locked']=admit
        with patch.object(time,'sleep',side_effect=lambda n:f.events.append(('sleep',n))):f.service.auto_optimize_training_check_worker(' task ',0.5)
        self.assertEqual(seen,[(f.state,1)]);self.assertEqual([e[0] for e in f.events],['sleep','enter','save','exit']);self.assertEqual(f.depth,[0])
        f=self.fixture();f.b['maybe_start_auto_optimize_training_locked']=Mock(side_effect=RuntimeError('x'*300));f.service.auto_optimize_training_check_worker('task')
        self.assertEqual(f.state['last_training_check_error'],'x'*240);self.assertEqual([e[0] for e in f.events],['enter','exit','enter','save','exit']);self.assertEqual(f.depth,[0])
        f=self.fixture();f.service.auto_optimize_training_check_worker(' ');self.assertEqual(f.events,[])

    def test_check_save_failure_reloads_and_retry_failure_propagates(self):
        f=self.fixture();f.b['maybe_start_auto_optimize_training_locked']=lambda s:None;failure=RuntimeError('save failed');f.b['save_auto_optimize_state']=Mock(side_effect=failure)
        with self.assertRaises(RuntimeError) as caught:f.service.auto_optimize_training_check_worker('task')
        self.assertIs(caught.exception,failure);self.assertEqual(f.b['save_auto_optimize_state'].call_count,2);self.assertEqual(f.state['last_training_check_error'],'save failed');self.assertEqual(f.depth,[0])

    def test_start_thread_target_arguments_and_failure(self):
        f=self.fixture();thread=Mock();selected=Mock();f.b['auto_optimize_training_check_worker']=selected
        with patch.object(threading,'Thread',return_value=thread) as factory:
            f.service.start_auto_optimize_training_check_worker(' task ',1.5);factory.assert_called_once_with(target=factory.call_args.kwargs['target'],args=('task',1.5),name='auto-opt-training-check-task',daemon=True);thread.start.assert_called_once_with()
            factory.call_args.kwargs['target'](*factory.call_args.kwargs['args']);selected.assert_called_once_with('task',1.5)
        with patch.object(threading,'Thread',side_effect=AssertionError('must not start')):f.service.start_auto_optimize_training_check_worker(' ')
        error=RuntimeError('start');thread.start.side_effect=error
        with patch.object(threading,'Thread',return_value=thread),self.assertRaises(RuntimeError) as caught:f.service.start_auto_optimize_training_check_worker('task')
        self.assertIs(caught.exception,error)

    @unittest.skipIf(BASELINE,'candidate root assembly and preserved snapshot decorator')
    def test_actual_composition_forwarding_and_snapshot_boundary(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_training_scheduling
        for group in (service.policy,service.submission,service.state):
            for f in fields(group):assert_capability_owner(self, group, f.name, server)
        for name,args in zip(NAMES,(({},),('t',2.0),('t',3.0))):
            mock=Mock(return_value=object());fn=getattr(server,name)
            if hasattr(fn,'__wrapped__'):fn=fn.__wrapped__
            with patch.object(server,'_auto_optimization_training_scheduling',SimpleNamespace(**{name:mock})):self.assertIs(fn(*args),mock.return_value)
            mock.assert_called_once_with(*args)
        self.assertTrue(hasattr(server.auto_optimize_training_check_worker,'__wrapped__'))
        tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==NAMES[1])
        self.assertEqual(ast.unparse(node.decorator_list[0]),'pinned_model_profiles(resolve_model_profiles, lambda identity: load_auto_optimize_state(identity))')
        subprocess.run([sys.executable,'-c',"import sys; import local_inspection_service.training.auto_optimization_training_scheduling; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
