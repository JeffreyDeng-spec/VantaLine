"""Synthetic initialization contract: provider substitutes and caller-owned state only."""
import ast
import copy
from dataclasses import fields
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_inspection_service.training.auto_optimization_settings import normalize_expected_production_count
from auto_optimization_test_ports import test_capability, assert_capability_owner
BASELINE=os.environ.get('VANTALINE_AUTO_INITIALIZATION_BASELINE_SOURCE')
NAMES={'agent_auto_optimize_initialization_recommendation','initialize_auto_optimize_for_pipeline_task'}


def create(bindings,negative_default=3):
    if BASELINE:
        nodes=[node for node in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body
            if isinstance(node,ast.FunctionDef) and node.name in NAMES]
        assert len(nodes)==2
        namespace=dict(bindings,Any=Any,json=json,AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE=negative_default,
            normalize_expected_production_count=normalize_expected_production_count)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),namespace)
        # Keep the caller-supplied advisor in the task workflow, as on a patched root.
        namespace['agent_auto_optimize_initialization_recommendation']=bindings['agent_auto_optimize_initialization_recommendation']
        original=next(node for node in nodes if node.name=='agent_auto_optimize_initialization_recommendation')
        advisor_namespace=dict(namespace)
        exec(compile(ast.Module(body=[original],type_ignores=[]),BASELINE,'exec'),advisor_namespace)
        service=types.SimpleNamespace(initialize_auto_optimize_for_pipeline_task=namespace['initialize_auto_optimize_for_pipeline_task'],
            agent_auto_optimize_initialization_recommendation=advisor_namespace['agent_auto_optimize_initialization_recommendation'])
        def replace(name,value):
            bindings[name]=value;namespace[name]=value;advisor_namespace[name]=value
        return service,replace
    from local_inspection_service.training.auto_optimization_initialization import AutoOptimizationInitialization
    from local_inspection_service.training.auto_optimization_initialization_ports import AutoOptimizationAdvisorPorts,AutoOptimizationTaskInitializationPorts
    def ports(kind):
        return kind(**{field.name:test_capability(bindings, field.name) for field in fields(kind)})
    service=AutoOptimizationInitialization(negative_default,ports(AutoOptimizationAdvisorPorts),ports(AutoOptimizationTaskInitializationPorts))
    return service,lambda name,value:bindings.__setitem__(name,value)


class TracedLock:
    def __init__(self,events,label='lock'):
        self.events=events;self.held=False;self.label=label
    def __enter__(self):
        assert not self.held
        self.held=True;self.events.append(self.label+'.enter')
    def __exit__(self,*args):
        self.events.append(self.label+'.exit');self.held=False


class InitializationContract(unittest.TestCase):
    def fixture(self,*,enabled=True):
        events=[];lock=TracedLock(events);state={'settings':{'custom':'keep'},'samples':[{'existing':True}]}
        recommendation={'enabled':enabled,'min_trainable_samples':400,'min_positive_samples':100,'min_negative_samples':0,
            'negative_samples_per_real_image':0,'auto_promote':True}
        config={'a':{'name':'A','source_files':['one'],'ai_profile':{'description':'description','tags':['x']}}}
        task={'ai_task_id':'ai-1','name':'Task','accessory_ids':['a',7,'a'],'expected_production_count':10000,
            'params':{},'owner_user_id':'u','owner_username':'name','accessory_counts':{'a':2}}
        defaults={'enabled':False,'min_trainable_samples':200,'negative_samples_per_real_image':3,'serving_mode':'old'}
        def trace(name,value):
            def call(*args,**kwargs):
                events.append((name,lock.held,args,kwargs));return value
            return call
        bindings={
            'sanitize_ai_detection_task_id':trace('sanitize','ai-1'),
            'canonical_pipeline_accessory_ids':trace('canonical',['a']),
            'auto_optimize_complexity_rule_recommendation':trace('rule',{'fallback':True}),
            'agent_auto_optimize_initialization_recommendation':trace('advisor',recommendation),
            '_auto_optimize_lock':lock,
            'load_auto_optimize_state':trace('load',state),
            'default_auto_optimize_settings':trace('defaults',defaults),
            'save_auto_optimize_state':trace('save',state),
            'start_auto_optimize_label_worker':trace('start',None),
            'ai_detection_settings':trace('model.settings',{'configured':True,'provider':'synthetic','model':'stub'}),
            'accessory_lookup_by_id':trace('lookup',config),
            'accessory_material_type':trace('material','object'),
            'bounded_text':lambda value,limit:str(value or '')[:limit],
            'generate_provider_json_with_fallback':trace('provider',({'from_provider':True},12.5,{'usage_metadata':{'tokens':1}})),
            'clamp_auto_optimize_initialization_recommendation':trace('clamp',{'enabled':True}),
        }
        service,replace=create(bindings)
        return types.SimpleNamespace(service=service,replace=replace,events=events,lock=lock,state=state,config=config,
            task=task,recommendation=recommendation,bindings=bindings,defaults=defaults)

    def test_task_order_lock_scope_identity_and_post_save_start(self):
        f=self.fixture();result=f.service.initialize_auto_optimize_for_pipeline_task(f.task,f.config)
        self.assertIs(result,f.recommendation);self.assertIs(f.state['auto_optimize_initialization'],result)
        self.assertIs(f.task['auto_optimize_initialization'],result);self.assertIs(f.state['required_accessory_counts'],f.task['accessory_counts'])
        names=[event if isinstance(event,str) else event[0] for event in f.events]
        self.assertEqual(names,['sanitize','canonical','rule','advisor','lock.enter','load','defaults','save','lock.exit','start'])
        self.assertTrue(all(event[1] for event in f.events if not isinstance(event,str) and event[0] in {'load','defaults','save'}))
        self.assertTrue(all(not event[1] for event in f.events if not isinstance(event,str) and event[0] not in {'load','defaults','save'}))
        self.assertEqual(f.state['settings']['negative_samples_per_real_image'],0)
        self.assertEqual(f.state['settings']['custom'],'keep');self.assertEqual(f.state['settings']['serving_mode'],'api_primary')
        self.assertEqual(f.task['params']['expected_production_count'],10000)
        self.assertEqual(next(event for event in f.events if isinstance(event,tuple) and event[0]=='canonical')[2][1],['a','7','a'])

    def test_missing_id_and_disabled_recommendation(self):
        f=self.fixture();f.replace('sanitize_ai_detection_task_id',lambda value:'')
        saved=copy.deepcopy(f.task);self.assertEqual(f.service.initialize_auto_optimize_for_pipeline_task(f.task,f.config),{})
        self.assertEqual(f.task,saved);self.assertEqual(f.events,[])
        f=self.fixture(enabled=False);f.service.initialize_auto_optimize_for_pipeline_task(f.task,f.config)
        self.assertFalse(any(isinstance(event,tuple) and event[0]=='start' for event in f.events))

    def test_save_failure_preserves_state_mutation_but_not_task_mutation(self):
        f=self.fixture();saved_task=copy.deepcopy(f.task);sentinel=RuntimeError('save failed')
        def save(state):
            self.assertTrue(f.lock.held);self.assertIs(state,f.state);raise sentinel
        f.replace('save_auto_optimize_state',save)
        with self.assertRaises(RuntimeError) as raised:f.service.initialize_auto_optimize_for_pipeline_task(f.task,f.config)
        self.assertIs(raised.exception,sentinel);self.assertEqual(f.task,saved_task)
        self.assertIs(f.state['auto_optimize_initialization'],f.recommendation);self.assertFalse(f.lock.held)
        self.assertEqual(f.events[-1],'lock.exit')

    def test_start_failure_keeps_saved_state_and_task_mutation(self):
        f=self.fixture();sentinel=RuntimeError('start failed')
        def start(task_id):
            self.assertFalse(f.lock.held);self.assertEqual(task_id,'ai-1');raise sentinel
        f.replace('start_auto_optimize_label_worker',start)
        with self.assertRaises(RuntimeError) as raised:f.service.initialize_auto_optimize_for_pipeline_task(f.task,f.config)
        self.assertIs(raised.exception,sentinel);self.assertIs(f.task['auto_optimize_initialization'],f.recommendation)
        self.assertEqual(f.task['params']['expected_production_count'],10000)
        self.assertTrue(any(isinstance(event,tuple) and event[0]=='save' for event in f.events))

    def test_advisor_failure_is_before_lock_and_settings_failure_releases_lock(self):
        for name in ('agent_auto_optimize_initialization_recommendation','default_auto_optimize_settings'):
            f=self.fixture();before=copy.deepcopy((f.task,f.state));sentinel=ValueError(name)
            def fail(*args):raise sentinel
            f.replace(name,fail)
            with self.assertRaises(ValueError) as raised:f.service.initialize_auto_optimize_for_pipeline_task(f.task,f.config)
            self.assertIs(raised.exception,sentinel);self.assertEqual((f.task,f.state),before);self.assertFalse(f.lock.held)
            self.assertEqual('lock.enter' in f.events,name=='default_auto_optimize_settings')

    def test_model_unconfigured_is_same_fallback_and_no_provider(self):
        f=self.fixture();f.replace('ai_detection_settings',lambda target:{'configured':False})
        fallback={};self.assertIs(f.service.agent_auto_optimize_initialization_recommendation(f.config,['a'],10000,fallback),fallback)
        self.assertEqual(f.events,[])

    def test_provider_payload_limits_metadata_and_single_attempt(self):
        f=self.fixture();fallback={'original':True}
        result=f.service.agent_auto_optimize_initialization_recommendation(f.config,['a','missing','a'],10000,fallback)
        provider=next(event for event in f.events if isinstance(event,tuple) and event[0]=='provider')
        self.assertEqual(provider[3],{'max_tokens':800,'max_attempts':1})
        self.assertEqual(hashlib.sha256(provider[2][1].encode('utf-8')).hexdigest(),'ffed9108aa362e61cdd649214e544869145a81ec6a9f37f7a57be29d42b6beeb')
        prompt=json.loads(provider[2][2][0]['text']);self.assertEqual(prompt['expected_production_count'],10000)
        self.assertEqual(prompt['front_30_percent_quota'],3000);self.assertEqual([item['id'] for item in prompt['accessories']],['a','missing','a'])
        self.assertEqual(prompt['policy']['negative_samples_per_real_image_default'],3)
        self.assertEqual(result,{'enabled':True,'provider':'synthetic','model':'stub','latency_ms':12.5,'usage_metadata':{'tokens':1}})
        self.assertEqual(fallback,{'original':True})

    def test_provider_and_clamp_failures_fallback_but_preparation_errors_escape(self):
        for name,caught in [('generate_provider_json_with_fallback',True),('clamp_auto_optimize_initialization_recommendation',True),('accessory_lookup_by_id',False),('ai_detection_settings',False)]:
            f=self.fixture();sentinel=RuntimeError(name)
            def fail(*args,**kwargs):raise sentinel
            f.replace(name,fail);fallback={'nested':[]}
            if caught:
                result=f.service.agent_auto_optimize_initialization_recommendation(f.config,['a'],10000,fallback)
                self.assertEqual(result['agent_error'],name);self.assertIs(result['nested'],fallback['nested']);self.assertNotIn('agent_error',fallback)
            else:
                with self.assertRaises(RuntimeError) as raised:f.service.agent_auto_optimize_initialization_recommendation(f.config,['a'],10000,fallback)
                self.assertIs(raised.exception,sentinel)

    def test_a_b_a_dependencies_and_late_lock_resolution(self):
        a=self.fixture();b=self.fixture(enabled=False)
        a.replace('agent_auto_optimize_initialization_recommendation',lambda *args:dict(a.recommendation,enabled=False))
        a.service.initialize_auto_optimize_for_pipeline_task(a.task,a.config)
        b.service.initialize_auto_optimize_for_pipeline_task(b.task,b.config)
        other=TracedLock(a.events,'other')
        def advisor(*args):a.replace('_auto_optimize_lock',other);return a.recommendation
        a.replace('agent_auto_optimize_initialization_recommendation',advisor)
        a.service.initialize_auto_optimize_for_pipeline_task(a.task,a.config)
        self.assertIn('other.enter',a.events);self.assertNotIn('other.enter',b.events)
        self.assertTrue(a.state['settings']['enabled']);self.assertFalse(b.state['settings']['enabled'])

    def test_model_scope_is_used_for_advice_and_frozen_only_at_save(self):
        from contextvars import ContextVar
        from local_inspection_service.model_profiles.snapshots import freeze_record
        for active,existing,expected_saved in [('A','B','B'),('A',None,'A'),(None,None,'C')]:
            f=self.fixture();scope=ContextVar('synthetic_model_scope',default=active)
            catalog={'version':'A'};observed=[]
            if existing:f.state['model_profiles']={'version':existing}
            resolver=types.SimpleNamespace(current_snapshot=lambda:({'version':scope.get()} if scope.get() else None),
                snapshot_for_record=lambda record:{'version':catalog['version']})
            def resolve(purpose):
                observed.append(('settings',scope.get() or catalog['version']))
                return {'configured':True,'provider':'synthetic','model':scope.get() or catalog['version']}
            def provider(*args,**kwargs):
                catalog['version']='C';return {},1,{}
            def save(state):
                self.assertTrue(f.lock.held);observed.append(('save',scope.get()))
                freeze_record(lambda:resolver,state);return state
            f.replace('ai_detection_settings',resolve)
            f.replace('generate_provider_json_with_fallback',provider)
            f.replace('clamp_auto_optimize_initialization_recommendation',lambda *args:dict(f.recommendation,enabled=False))
            f.replace('agent_auto_optimize_initialization_recommendation',f.service.agent_auto_optimize_initialization_recommendation)
            f.replace('save_auto_optimize_state',save)
            f.service.initialize_auto_optimize_for_pipeline_task(f.task,f.config)
            self.assertEqual(observed,[('settings','A'),('save',active)])
            self.assertEqual(f.state['model_profiles'],{'version':expected_saved})
            self.assertEqual(f.task['auto_optimize_initialization']['model'],'A')

    def test_provider_and_canonical_callees_are_selected_before_arguments(self):
        from unittest.mock import patch
        f=self.fixture();calls=[];original_json_dumps=json.dumps
        def old_provider(*args,**kwargs):calls.append('old.provider');return {},0,{}
        def new_provider(*args,**kwargs):calls.append('new.provider');return {},0,{}
        def serialize(*args,**kwargs):
            calls.append('serialize');f.replace('generate_provider_json_with_fallback',new_provider)
            return original_json_dumps(*args,**kwargs)
        f.replace('generate_provider_json_with_fallback',old_provider)
        with patch.object(json,'dumps',side_effect=serialize):
            f.service.agent_auto_optimize_initialization_recommendation(f.config,['a'],10000,{})
        self.assertEqual(calls,['serialize','old.provider'])
        f=self.fixture();calls=[]
        def old_canonical(config,ids):calls.append(('old.canonical',ids));return ['a']
        def new_canonical(config,ids):calls.append(('new.canonical',ids));return ['a']
        class RebindingId:
            def __str__(self):f.replace('canonical_pipeline_accessory_ids',new_canonical);calls.append('id.str');return 'a'
        f.replace('canonical_pipeline_accessory_ids',old_canonical);f.task['accessory_ids']=[RebindingId()]
        f.service.initialize_auto_optimize_for_pipeline_task(f.task,f.config)
        self.assertEqual(calls,['id.str',('old.canonical',['a'])])

    def test_error_formatter_selection_and_secondary_failure(self):
        for formatter_fails in (False,True):
            f=self.fixture();events=[];secondary=RuntimeError('formatter failed')
            def old_text(value,limit):
                events.append('old.text')
                if formatter_fails:raise secondary
                return 'old:'+value
            def new_text(value,limit):events.append('new.text');return 'new:'+value
            class RebindingError(Exception):
                def __str__(self):f.replace('bounded_text',new_text);events.append('str.error');return 'provider failure'
            def provider(*args,**kwargs):f.replace('bounded_text',old_text);raise RebindingError()
            f.replace('generate_provider_json_with_fallback',provider)
            if formatter_fails:
                with self.assertRaises(RuntimeError) as raised:f.service.agent_auto_optimize_initialization_recommendation({},[],1,{})
                self.assertIs(raised.exception,secondary)
            else:
                result=f.service.agent_auto_optimize_initialization_recommendation({},[],1,{})
                self.assertEqual(result['agent_error'],'old:provider failure')
            self.assertEqual(events,['str.error','old.text'])

    @unittest.skipIf(BASELINE,'candidate-only actual composition')
    def test_actual_root_keeps_model_and_request_context_across_threadpool(self):
        import asyncio
        import threading
        from unittest.mock import Mock, patch
        from starlette.concurrency import run_in_threadpool
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_initialization
        self.assertEqual(service.negative_samples_default,server.AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE)
        self.assertIs(service.advisor.ai_detection_settings(),server.ai_detection_settings)
        self.assertIs(service.task._auto_optimize_lock(),server._auto_optimize_lock)
        for port in (service.advisor,service.task):
            for field in fields(port):assert_capability_owner(self, port, field.name, server)
        barrier=threading.Barrier(2,timeout=10)
        def resolve(purpose):
            self.assertEqual(purpose,'training_vision')
            user=server._request_user.get()['id'];snapshot=server.model_profile_service.current_snapshot()
            self.assertEqual(snapshot,{'synthetic':user})
            return {'configured':True,'provider':user,'model':'stub'}
        def provider(*args,**kwargs):
            user=server._request_user.get()['id'];barrier.wait()
            self.assertEqual(server.model_profile_service.current_snapshot(),{'synthetic':user})
            return {'owner':user},1,{}
        async def request(user):
            with server._request_user.bind({'id':user}),server.model_profile_service.scope({'synthetic':user}):
                return await run_in_threadpool(server.agent_auto_optimize_initialization_recommendation,{},[],1000,{})
        async def both():return await asyncio.gather(request('alpha'),request('beta'))
        with patch.object(server.model_profile_service,'resolve',side_effect=resolve), \
             patch.object(server,'accessory_lookup_by_id',return_value={}), \
             patch.object(server,'generate_provider_json_with_fallback',side_effect=provider), \
             patch.object(server._auto_optimization_execution,'clamp_auto_optimize_initialization_recommendation',side_effect=lambda raw,*args:dict(raw)):
            results=asyncio.run(both())
        self.assertEqual([(item['owner'],item['provider']) for item in results],[('alpha','alpha'),('beta','beta')])
        self.assertIsNone(server._request_user.get());self.assertIsNone(server.model_profile_service.current_snapshot())
        sentinel=RuntimeError('missing model dependency')
        with patch.object(server.model_profile_service,'resolve',side_effect=sentinel):
            with self.assertRaises(RuntimeError) as raised:server.agent_auto_optimize_initialization_recommendation({},[],1000,{})
            self.assertIs(raised.exception,sentinel)
        for name,args in [('agent_auto_optimize_initialization_recommendation',({},[],1000,{})),('initialize_auto_optimize_for_pipeline_task',({},{}))]:
            result=object();method=Mock(return_value=result)
            with patch.object(server,'_auto_optimization_initialization',types.SimpleNamespace(**{name:method})):
                self.assertIs(getattr(server,name)(*args),result);method.assert_called_once_with(*args)

    @unittest.skipIf(BASELINE,'candidate-only import')
    def test_lightweight_import(self):
        code="import sys; import local_inspection_service.training.auto_optimization_initialization; assert not any(x in sys.modules for x in ('local_inspection_service.server','fastapi','psycopg'))"
        subprocess.run([sys.executable,'-c',code],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
