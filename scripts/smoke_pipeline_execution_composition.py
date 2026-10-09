"""Actual native pipeline execution: pinning, identity, scopes, drain and isolation."""
import ast
import copy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields
from pathlib import Path
import sys
import tempfile
import threading
import traceback
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
POSTGRES='--postgres' in sys.argv
if POSTGRES:sys.argv.remove('--postgres')
from smoke_pipeline_stores import Fixture, available
from smoke_pipeline_persistence_composition import build as persistence
from local_inspection_service.pipeline import execution_composition as module
from local_inspection_service.runtime.training_tasks import TrainingRuntimeClosed

class Graph:
    def __init__(self, root, label, *, repository=None, repository_scope=None):
        self.label=label;self.identity=ContextVar('pipeline-user-'+label,default=None)
        self.active_scope=ContextVar('pipeline-repository-'+label,default=False)
        self.snapshot=ContextVar('pipeline-model-'+label,default=None)
        self.inherited_snapshot=None
        self.events=[];self.errors=[];self.runtime_errors=[];self.provider_calls=0;self.pin_calls=0
        self.block_exit=None;self.exit_entered=threading.Event()
        self.decide_entered=threading.Event();self.decide_release=None
        self.fixture=Fixture(root);self.persistence=persistence(self.fixture,repository=repository)
        self.task_held=ContextVar('pipeline-task-held-'+label,default=False)
        mutex=self.persistence.runtime.task_lock
        graph=self
        class Guard:
            def acquire(self,*args,**kwargs):return mutex.acquire(*args,**kwargs)
            def release(self):return mutex.release()
            def __enter__(self):
                mutex.acquire();graph.task_held.set(True)
            def __exit__(self,*args):
                graph.task_held.set(False);mutex.release()
        self.persistence.runtime.task_lock=Guard()
        graph=self
        class Thread(threading.Thread):
            def run(self):
                try:super().run()
                except BaseException as error:graph.errors.append(error)
        self.thread_factory=Thread
        @contextmanager
        def scope():
            token=self.active_scope.set(True);self.events.append('repository-enter')
            snapshot_token=self.snapshot.set(copy.deepcopy(self.inherited_snapshot))
            try:
                if repository_scope is None:yield
                else:
                    with repository_scope():yield
            finally:
                self.exit_entered.set()
                if self.block_exit is not None:
                    if not self.block_exit.wait(5):raise AssertionError('scope exit stalled')
                assert self.snapshot.get()==self.inherited_snapshot, 'outer snapshot not restored'
                self.snapshot.reset(snapshot_token)
                self.events.append('repository-exit');self.active_scope.reset(token)
        class Models:
            def current_snapshot(self):return graph.snapshot.get()
            def snapshot_for_record(self,record):return {'account':label,'version':9}
            @contextmanager
            def scope(self,snapshot):
                graph.pin_calls+=1
                assert graph.active_scope.get(), 'pin before repository scope'
                assert graph.identity.get() is None, 'pin after identity'
                token=graph.snapshot.set(copy.deepcopy(snapshot));graph.events.append('pin-enter')
                try:yield
                finally:
                    assert graph.identity.get() is None, 'identity leaked before pin exit'
                    graph.events.append('pin-exit');graph.snapshot.reset(token)
        self.models=Models()
        def provider():
            self.provider_calls+=1
            assert self.active_scope.get(), 'provider before repository scope'
            return self.models
        self.provider=provider
        def observe(stage):
            assert self.identity.get()=={'id':label}, 'wrong account'
            assert self.snapshot.get()=={'account':label,'version':1}, 'wrong snapshot'
            assert self.active_scope.get(), 'missing scope'
            assert not self.task_held.get(), 'provider under current thread task lock'
            self.events.append(stage)
        def decide(task,config,**kwargs):
            observe('decide');self.decide_entered.set()
            if self.decide_release is not None and not self.decide_release.wait(5):raise AssertionError('decision stalled')
            return {'action':'advance'}
        def commit(task,config,user,message,decision,source,*,pending_advances):
            assert self.task_held.get()
            task['auto_pending']=False;pending_advances.append(task['id'])
        def advance(task,*,cancel_event=None):
            observe('advance');task.update(stage='library',status='completed')
        def recommendation(stage,ids,count):
            observe('recommendation');return {'params':{'account':label},'source':'synthetic'}
        def getter(value):return lambda:value
        self.owner=module.PipelineExecution(persistence=self.persistence,model_resolver=provider,scope=scope,
            auto_tasks=module.PipelineAutoAgentTasksInputs(getter(lambda task:task.get('auto_pending',False)),getter(lambda task:task.setdefault('orchestration',{})),getter(lambda task:'sig'),getter(12),getter(lambda *a,**k:None),getter(lambda *a,**k:None),getter(copy.deepcopy)),
            auto_decision=module.PipelineAutoAgentDecisionInputs(getter(lambda config,user:config),getter(lambda:{}),getter(decide),getter(commit),getter(lambda:100)),
            auto_execution=module.PipelineAutoAgentExecutionInputs(getter(self.identity),getter(self.record_runtime_error),getter(None)),
            auto_scheduling=module.PipelineAutoAgentSchedulingInputs(lambda:self.thread_factory),
            advance_tasks=module.PipelineAdvanceTasksInputs(getter(lambda task:None),getter(copy.deepcopy)),
            advance_policy=module.PipelineAdvancePolicyInputs(getter(advance),getter(type('Cancelled',(Exception,),{})),getter(type('HttpError',(Exception,),{})),getter(lambda task:task.setdefault('orchestration',{})),getter(lambda *a,**k:None),getter(lambda value,limit:str(value)[:limit])),
            advance_execution=module.PipelineAdvanceExecutionInputs(getter(self.identity),getter(lambda config,user:config),getter(lambda:{}),getter(lambda:100),getter(self.record_runtime_error),getter(None),getter(lambda *a,**k:None)),
            advance_scheduling=module.PipelineAdvanceSchedulingInputs(getter(threading.Event),lambda:self.thread_factory),
            recommendation_tasks=module.PipelineRecommendationTasksInputs(getter(lambda task:'training'),getter(lambda task,stage:False),getter(lambda task,stage:'sig')),
            recommendation_execution=module.PipelineRecommendationExecutionInputs(getter(self.identity),getter(recommendation),getter(lambda:100),getter(self.record_runtime_error),getter(None)),
            recommendation_scheduling=module.PipelineRecommendationSchedulingInputs(lambda:self.thread_factory))
    def record_runtime_error(self, **kwargs):
        self.runtime_errors.append(traceback.format_exc())
        self.events.append('runtime-error')

    def seed(self, key, *, auto=False):
        return self.persistence.save_pipeline_task({'id':key,'owner_user_id':self.label,
            'stage':'samples','status':'running','auto_pending':auto,
            'model_profiles':{'account':self.label,'version':1}})
    def drain(self):
        # Preserve producer-first close; stop at a false result.
        for owner in (self.owner.auto,self.owner.advance,self.owner.recommendation):
            if not owner.close(2):return False
        return True

class PipelineExecutionContracts(unittest.TestCase):
    def test_constructor_is_inert_and_partial_failure_publishes_nothing(self):
        def poison(*args,**kwargs):raise AssertionError('eager dependency')
        groups={name:cls for name,cls in vars(module).items() if name.startswith('Pipeline') and name.endswith('Inputs')}
        params={'auto_tasks':'PipelineAutoAgentTasksInputs','auto_decision':'PipelineAutoAgentDecisionInputs','auto_execution':'PipelineAutoAgentExecutionInputs','auto_scheduling':'PipelineAutoAgentSchedulingInputs','advance_tasks':'PipelineAdvanceTasksInputs','advance_policy':'PipelineAdvancePolicyInputs','advance_execution':'PipelineAdvanceExecutionInputs','advance_scheduling':'PipelineAdvanceSchedulingInputs','recommendation_tasks':'PipelineRecommendationTasksInputs','recommendation_execution':'PipelineRecommendationExecutionInputs','recommendation_scheduling':'PipelineRecommendationSchedulingInputs'}
        inputs={name:groups[cls](**{field.name:poison for field in fields(groups[cls])}) for name,cls in params.items()}
        owner=module.PipelineExecution(persistence=SimpleNamespace(),model_resolver=poison,scope=poison,**inputs)
        self.assertIs(owner.model_resolver,poison)
        self.assertIsNot(owner.auto.lifecycle,owner.advance.lifecycle)
        self.assertIsNot(owner.advance.lifecycle,owner.recommendation.lifecycle)
        original=owner
        with patch.object(module,'PipelineAdvanceRuntime',side_effect=ValueError('constructor')):
            with self.assertRaisesRegex(ValueError,'constructor'):
                owner=module.PipelineExecution(persistence=SimpleNamespace(),model_resolver=poison,scope=poison,**inputs)
        self.assertIs(owner,original)
    def test_three_actual_runners_use_single_pin_identity_and_thread_scope(self):
        with tempfile.TemporaryDirectory(prefix='pipeline-native-') as root:
            graph=Graph(root,'alice')
            for key in ('auto','advance','recommend'):graph.seed(key,auto=key=='auto')
            graph.owner.schedule_pipeline_auto_agent(['auto'],{'id':'alice'})
            self.assertTrue(graph.owner.schedule_pipeline_advance('advance',{'id':'alice'}))
            graph.owner.schedule_pipeline_recommendation_pregen([('recommend','training')],{'id':'alice'})
            self.assertTrue(graph.drain());self.assertEqual(graph.errors,[]);self.assertNotIn("runtime-error",graph.events)
            self.assertEqual(graph.pin_calls,4);self.assertEqual(graph.provider_calls,4)
            self.assertEqual(graph.events.count('repository-enter'),4);self.assertEqual(graph.events.count('repository-exit'),4)
            self.assertEqual(graph.persistence.load_pipeline_task('auto')['status'],'completed')
            self.assertEqual(graph.persistence.load_pipeline_task('advance')['status'],'completed')
            self.assertEqual(graph.persistence.load_pipeline_task('recommend')['recommended_params']['params'],{'account':'alice'})
            self.assertIsNone(graph.identity.get());self.assertIsNone(graph.snapshot.get())
            self.assertEqual(graph.persistence.runtime.auto_agent_inflight,set())
            self.assertEqual(graph.persistence.runtime.advance_inflight,set())
            self.assertEqual(graph.persistence.runtime.recommendation_inflight,set())
    def test_record_snapshot_precedes_inherited_scope_and_outer_scope_is_restored(self):
        with tempfile.TemporaryDirectory(prefix='pipeline-inherited-model-') as root:
            graph=Graph(root,'a');graph.inherited_snapshot={'account':'outer','version':99}
            graph.seed('same')
            self.assertTrue(graph.owner.schedule_pipeline_advance('same',{'id':'a'}))
            self.assertTrue(graph.drain());self.assertEqual(graph.errors,[]);self.assertEqual(graph.runtime_errors,[])
            self.assertEqual((graph.pin_calls,graph.provider_calls),(1,1))
            self.assertEqual(graph.persistence.load_pipeline_task('same')['model_profiles'],{'account':'a','version':1})
            self.assertIsNone(graph.snapshot.get())

    def test_blocked_auto_producer_drains_to_own_advance_and_other_graph_continues(self):
        with tempfile.TemporaryDirectory(prefix='pipeline-drain-') as root:
            for label in ('a','b','c'):(Path(root)/label).mkdir()
            a,b=Graph(Path(root)/'a','a'),Graph(Path(root)/'b','b')
            a.seed('same',auto=True);b.seed('same');a.decide_release=threading.Event()
            a.owner.schedule_pipeline_auto_agent(['same'],{'id':'a'})
            self.assertTrue(a.decide_entered.wait(2));self.assertFalse(a.owner.auto.close(.01))
            self.assertTrue(b.owner.schedule_pipeline_advance('same',{'id':'b'}));self.assertTrue(b.drain())
            self.assertEqual(b.persistence.load_pipeline_task('same')['status'],'completed')
            a.decide_release.set();self.assertTrue(a.drain());self.assertEqual(a.errors,[]);self.assertNotIn("runtime-error",a.events)
            self.assertEqual(a.persistence.load_pipeline_task('same')['status'],'completed')
            with self.assertRaises(TrainingRuntimeClosed):a.owner.schedule_pipeline_advance('same',{'id':'a'})
            c=Graph(Path(root)/'c','c');c.seed('same');self.assertTrue(c.owner.schedule_pipeline_advance('same',{'id':'c'}));self.assertTrue(c.drain())
    def test_blocked_repository_scope_exit_is_not_reported_drained(self):
        with tempfile.TemporaryDirectory(prefix='pipeline-scope-exit-') as root:
            graph=Graph(root,'a');graph.seed('same');graph.block_exit=threading.Event()
            graph.owner.schedule_pipeline_advance('same',{'id':'a'})
            try:
                self.assertTrue(graph.exit_entered.wait(2));self.assertFalse(graph.owner.advance.close(.01))
                self.assertEqual(graph.events.count('repository-exit'),0)
            finally:graph.block_exit.set()
            self.assertTrue(graph.drain());self.assertEqual(graph.events.count('repository-exit'),1)
    def test_pin_loader_failure_preserves_original_registry_and_no_retry(self):
        for mode in ('resolver','loader'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='pipeline-pin-fail-') as root:
                graph=Graph(root,'a');graph.seed('same')
                if mode=='resolver':graph.owner.model_resolver=lambda:None
                else:graph.owner.load_pipeline_task=lambda key:(_ for _ in ()).throw(ValueError('loader'))
                graph.owner.schedule_pipeline_advance('same',{'id':'a'})
                self.assertTrue(graph.drain());self.assertEqual(len(graph.errors),1)
                self.assertEqual(graph.pin_calls,0);self.assertNotIn('advance',graph.events)
                self.assertEqual(graph.persistence.runtime.advance_inflight,{'same'})
                self.assertIn('same',graph.persistence.runtime.advance_cancel)
                self.assertEqual(graph.events.count('repository-enter'),1);self.assertEqual(graph.events.count('repository-exit'),1)
    def test_thread_constructor_and_uncertain_start_do_not_retry(self):
        for mode in ('constructor','start'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='pipeline-start-fail-') as root:
                graph=Graph(root,'a');graph.seed('same');calls=[]
                def construct(**kwargs):
                    calls.append('construct')
                    if mode=='constructor':raise ValueError('thread constructor')
                    class Uncertain:
                        def start(self):calls.append('start');raise ValueError('uncertain start')
                        def is_alive(self):return False
                        def join(self,timeout=None):raise RuntimeError('never started')
                    return Uncertain()
                graph.thread_factory=construct
                with self.assertRaises(ValueError):graph.owner.schedule_pipeline_advance('same',{'id':'a'})
                self.assertEqual(calls,['construct'] if mode=='constructor' else ['construct','start'])
                self.assertEqual(graph.persistence.runtime.advance_inflight,{'same'})
                self.assertEqual(graph.pin_calls,0)
                # An uncertain start remains fail-closed even when is_alive returns false.
                self.assertEqual(graph.owner.advance.close(.01),mode=='constructor')
    def test_binding_selects_actual_runtime_after_model_scope_entry(self):
        with tempfile.TemporaryDirectory(prefix='pipeline-pin-selection-') as root:
            graph=Graph(root,'a');graph.seed('same');calls=[]
            original=graph.models.scope
            @contextmanager
            def scope(snapshot):
                with original(snapshot):
                    graph.owner.advance=SimpleNamespace(run=lambda key,user:calls.append((key,user)))
                    yield
            graph.models.scope=scope
            token=graph.active_scope.set(True)
            try:graph.owner.run_advance('same',{'id':'a'})
            finally:graph.active_scope.reset(token)
            self.assertEqual(calls,[('same',{'id':'a'})]);self.assertEqual(graph.pin_calls,1)
    def test_exact_root_inverse_and_actual_execution_guards(self):
        from application_integration_source_contract import ROOT,PIPELINE_STAGES,AGENT_PIPELINE,PIPELINE_QUERIES,PIPELINE_EXECUTION,digest,restore_delta,restore_plc_domain_root
        source=(ROOT/'local_inspection_service/server.py').read_text()
        self.assertEqual(digest(ast.parse(restore_delta(restore_delta(restore_delta(restore_delta(source,PIPELINE_STAGES),AGENT_PIPELINE),PIPELINE_QUERIES),PIPELINE_EXECUTION))),PIPELINE_EXECUTION['parent_ast_sha256'])
        restore_plc_domain_root(source)
        with self.assertRaises(AssertionError):restore_plc_domain_root(source.replace('_pipeline_advance_runtime = _pipeline_execution.advance','_pipeline_advance_runtime = _pipeline_execution.auto'))

if POSTGRES:
    class PipelineExecutionPostgresContracts(unittest.TestCase):
        def test_two_actual_schema_graphs_native_models_identity_and_connection_cleanup(self):
            import os
            import uuid
            import psycopg
            from psycopg import sql
            from local_inspection_service.runtime.connections import ThreadRepositoryFactory
            from local_inspection_service.storage.postgres_schema import postgres_ddl
            from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
            dsn=os.environ['VANTALINE_POSTGRES_DSN']
            schemas=['pipeline_native_'+uuid.uuid4().hex for _ in range(2)]
            factories,connections,graphs=[],[],[]
            with tempfile.TemporaryDirectory(prefix='pipeline-native-pg-') as directory, psycopg.connect(dsn,autocommit=True) as control:
                try:
                    for index,schema in enumerate(schemas):
                        control.execute(postgres_ddl(schema))
                        def create(schema=schema):
                            connection=psycopg.connect(dsn);connections.append(connection)
                            return SimpleNamespace(repository=PostgresRuntimeRepository(connection,'synthetic',schema))
                        factory=ThreadRepositoryFactory(create,lambda schema=schema:schema);factories.append(factory)
                        root=Path(directory)/str(index);root.mkdir()
                        graph=Graph(root,str(index),repository=lambda factory=factory:factory.selection().repository,
                            repository_scope=factory.thread_scope);graphs.append(graph)
                        with factory.thread_scope():
                            for key in ('auto','advance','recommend'):graph.seed(key,auto=key=='auto')
                    for graph in graphs:
                        user={'id':graph.label}
                        graph.owner.schedule_pipeline_auto_agent(['auto'],user)
                        self.assertTrue(graph.owner.schedule_pipeline_advance('advance',user))
                        graph.owner.schedule_pipeline_recommendation_pregen([('recommend','training')],user)
                    for index,graph in enumerate(graphs):
                        self.assertTrue(graph.drain())
                        self.assertEqual(graph.errors,[]);self.assertEqual(graph.runtime_errors,[])
                        self.assertEqual((graph.pin_calls,graph.provider_calls),(4,4))
                        self.assertEqual(graph.events.count('repository-exit'),4)
                        with factories[index].thread_scope():
                            for key in ('auto','advance'):
                                task=graph.persistence.load_pipeline_task(key)
                                self.assertEqual((task['owner_user_id'],task['status']),(graph.label,'completed'))
                                self.assertEqual(task['model_profiles'],{'account':graph.label,'version':1})
                            self.assertEqual(graph.persistence.load_pipeline_task('recommend')['recommended_params']['params'],{'account':graph.label})
                    self.assertTrue(connections);self.assertTrue(all(connection.closed for connection in connections))
                finally:
                    for graph in graphs:
                        if graph.decide_release is not None:graph.decide_release.set()
                        if graph.block_exit is not None:graph.block_exit.set()
                        self.assertTrue(graph.drain())
                    for factory in factories:factory.clear()
                    for schema in schemas:control.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

if __name__=='__main__':unittest.main(verbosity=2)
