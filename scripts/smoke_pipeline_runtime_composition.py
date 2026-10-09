"""Run actual native owners against actual stage, Agent and mutation services."""
import ast
import copy
from dataclasses import fields, replace
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from typing import get_type_hints
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
POSTGRES='--postgres' in sys.argv
if POSTGRES:sys.argv.remove('--postgres')
from local_inspection_service.pipeline import runtime_composition as module
from smoke_pipeline_query_composition import build as query_graph
from smoke_pipeline_stage_composition import build as stage_graph
from smoke_agent_pipeline_composition import graph as agent_graph
from smoke_pipeline_execution_composition import Graph, module as execution_module

GROUPS={name:kind for name,kind in get_type_hints(module.PipelineRuntimeWorkflows.__init__).items()
        if name not in ('queries','model_resolver','scope')}

def build(root,account,*,repository_factory=None):
    root=Path(root);root.mkdir()
    q=query_graph(root/'queries',account)
    if repository_factory is not None:
        repository=lambda:repository_factory.selection().repository
        q.persistence.tasks.repository=repository;q.persistence.state.repository=repository
        q.b['runtime_postgres_repository_or_none']=repository
    stage=stage_graph(root/'stage',account,queries=q)
    agent=agent_graph(root/'agent',account,queries=q)
    captured={};constructor=execution_module.PipelineExecution
    def capture(**kwargs):captured.update(kwargs);return constructor(**kwargs)
    with patch.object(execution_module,'PipelineExecution',side_effect=capture):
        native=Graph(root/'native',account,persistence_owner=q.persistence,
            repository_scope=repository_factory.thread_scope if repository_factory is not None else None)
    native.launched=[];thread_factory=native.thread_factory
    def thread(**kwargs):
        value=thread_factory(**kwargs);native.launched.append(value);return value
    native.thread_factory=thread
    def recommendation(stage_name,ids,count):
        assert native.active_scope.get(),'recommendation without repository scope'
        assert native.identity.get()=={'id':account},'recommendation wrong identity'
        assert not native.task_held.get(),'recommendation inside task guard'
        assert agent.models.current_snapshot()=={'pipeline':{'account':account,'version':1,'secret_ref':'synthetic-reference'}}
        native.events.append('recommendation')
        return {'params':{'sample_count':3},'reason':'uncached','source':'synthetic'}
    captured['recommendation_execution']=replace(captured['recommendation_execution'],recommend=lambda:recommendation)
    # Inert fixture construction above starts no threads. Capture only external
    # native abilities; the runtime owner replaces all cross-domain edges.
    inputs={}
    for name,kind in GROUPS.items():
        if name.startswith('stages_'):
            inputs[name]=kind(**{f.name:lambda key=f.name:stage.b[key] for f in fields(kind)})
        elif name.startswith('agent_'):
            inputs[name]=kind(**{f.name:lambda key=f.name:agent.b[key] for f in fields(kind)})
        elif name.startswith('execution_'):
            source=captured[name[len('execution_'):]]
            inputs[name]=kind(**{f.name:(lambda:lambda:q.config) if f.name=='load_config' else getattr(source,f.name) for f in fields(kind)})
        elif name=='mutations_storage':
            inputs[name]=kind(runtime_postgres_repository_or_none=lambda:repository if repository_factory is not None else lambda:None)
        else:
            inputs[name]=kind(sanitize_ai_detection_task_id=lambda:lambda value:str(value or '').strip(),
                record_mutable_by_user=lambda:lambda row,user:row.get('owner_user_id')==user['id'])
    def provider():
        assert native.active_scope.get(),'model selected outside repository scope'
        assert not native.task_held.get(),'provider selected inside task guard'
        return agent.provider()
    owner=module.PipelineRuntimeWorkflows(queries=q.owner,model_resolver=provider,
        scope=captured['scope'],**inputs)
    native.owner=owner.execution
    return SimpleNamespace(owner=owner,q=q,stage=stage,agent=agent,native=native,inputs=inputs,provider=provider,scope=captured['scope'],account=account)

class RuntimeCompositionContracts(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='pipeline-connected-');self.addCleanup(tmp.cleanup)
        self.a=build(Path(tmp.name)/'a','a');self.b=build(Path(tmp.name)/'b','b')
        for f in (self.a,self.b):
            self.addCleanup(f.native.drain)
    def seed(self,f,**kwargs):
        row=dict(id='same',name=f.account,owner_user_id=f.account,accessory_ids=['a'],
            detection_method='yolo',stage='draft',status='pending',params={'sample_count':2},
            model_profiles={'pipeline':{'account':f.account,'version':1,'secret_ref':'synthetic-reference'}})
        row.update(kwargs);f.q.persistence.save_pipeline_task(row);return row
    def test_constructor_is_inert_and_partial_failure_does_not_publish(self):
        def poison(*args,**kwargs):raise AssertionError('eager supplier')
        inputs={name:kind(**{field.name:poison for field in fields(kind)}) for name,kind in GROUPS.items()}
        original=self.a.owner;published=original
        owner=module.PipelineRuntimeWorkflows(queries=self.a.q.owner,model_resolver=poison,scope=poison,**inputs)
        self.assertIs(owner.runtime,self.a.q.persistence.runtime)
        self.assertIs(owner.agent.model_resolver,poison);self.assertIs(owner.execution.model_resolver,poison)
        with patch.object(module,'AgentPipelineWorkflows',side_effect=RuntimeError('constructor')):
            with self.assertRaisesRegex(RuntimeError,'constructor'):
                published=module.PipelineRuntimeWorkflows(queries=self.a.q.owner,model_resolver=poison,scope=poison,**inputs)
        self.assertIs(published,original)
        self.assertIsNot(owner.execution.auto.lifecycle,owner.execution.advance.lifecycle)
    def test_same_id_two_actual_native_stage_mutation_graphs(self):
        for f in (self.a,self.b):
            self.seed(f)
            self.assertTrue(f.owner.execution.schedule_pipeline_advance('same',{'id':f.account}))
        for f in (self.a,self.b):
            self.assertTrue(f.native.drain());self.assertEqual(f.native.errors,[]);self.assertEqual(f.native.runtime_errors,[])
            row=f.q.persistence.load_pipeline_task('same')
            self.assertEqual((row['stage'],row['samples_task_id']),('samples','generated'))
            self.assertEqual(row['model_profiles']['pipeline']['account'],f.account)
            self.assertEqual(len([e for e in f.stage.events if e[0]=='samples']),1)
            self.assertIsNone(f.native.identity.get());self.assertIsNone(f.agent.models.current_snapshot())
            self.assertEqual(f.native.events.count('repository-enter'),1)
            self.assertEqual(f.native.events.count('repository-exit'),1)
            self.assertFalse(f.owner.runtime.advance_inflight)
    def test_actual_agent_commit_marks_and_queues_owned_stage_advance(self):
        f=self.a;row=self.seed(f,stage='samples',status='completed',params={'epochs':2},auto_advance=True)
        original=f.agent.b['chat']
        def chat(messages,config):
            original(messages,config)
            return json.dumps({'action':'advance','message_to_user':'next','reason':'synthetic'})
        f.agent.b['chat']=chat
        f.owner.execution.schedule_pipeline_auto_agent(['same'],{'id':'a'})
        self.assertTrue(f.native.drain());self.assertEqual(f.native.errors,[]);self.assertEqual(f.native.runtime_errors,[])
        stored=f.q.persistence.load_pipeline_task('same')
        self.assertEqual((stored['stage'],stored['training_task_id']),('training','trained'))
        self.assertEqual(stored['model_profiles'],row['model_profiles'])
        self.assertEqual(stored['agent_mcp']['conversation'][-1]['message'],'next')
        self.assertEqual(len([e for e in f.stage.events if e[0]=='training']),1)
        self.assertTrue(all(e[2]==row['model_profiles'] for e in f.agent.events if e[0]=='chat'))
        self.assertIsNone(f.agent.models.current_snapshot());self.assertIsNone(f.native.identity.get())
    def test_stage_progress_is_persisted_before_asset_failure_without_retry(self):
        f=self.a;self.seed(f);seen=[]
        def fail(task,config):
            stored=f.q.persistence.load_pipeline_task('same');seen.append((stored['progress'],stored['job_note']))
            raise RuntimeError('asset failure')
        f.stage.b['prepare']=fail
        self.assertTrue(f.owner.execution.schedule_pipeline_advance('same',{'id':'a'}));self.assertTrue(f.native.drain())
        self.assertEqual(len(seen),1);self.assertEqual(seen[0][0],10)
        self.assertEqual(f.q.persistence.load_pipeline_task('same')['last_error'],'推进任务时发生内部错误，请稍后重试。')
        self.assertEqual(len(f.native.runtime_errors),1);self.assertIn('asset failure',f.native.runtime_errors[0])
        self.assertFalse(any(e[0]=='samples' for e in f.stage.events));self.assertEqual(f.native.errors,[])
    def test_actual_recommendation_readiness_prevents_another_provider_call(self):
        f=self.a;row=self.seed(f,params={})
        row['recommended_params']={'stage':'samples','signature':f.owner.pipeline_recommendation_signature(row,'samples'),
            'params':{'sample_count':3},'reason':'cached','source':'synthetic'}
        f.q.persistence.save_pipeline_task(row)
        def poison(*args,**kwargs):raise AssertionError('paid recommendation must not run')
        f.owner.execution.recommendation.execution=type(f.owner.execution.recommendation.execution)(
            **{field.name:(lambda:poison) if field.name=='recommend' else getattr(f.owner.execution.recommendation.execution,field.name)
               for field in fields(f.owner.execution.recommendation.execution)})
        f.owner.execution.schedule_pipeline_recommendation_pregen([('same','samples')],{'id':'a'})
        self.assertTrue(f.native.drain());self.assertEqual(f.native.errors,[]);self.assertEqual(f.native.runtime_errors,[])
        self.assertEqual(f.q.persistence.load_pipeline_task('same')['recommended_params'],row['recommended_params'])
        self.assertFalse(any(e=='recommendation' for e in f.native.events))
    def test_actual_cache_miss_saves_then_second_native_request_uses_cache(self):
        f=self.a;row=self.seed(f,params={})
        for index in (1,2):
            f.owner.execution.schedule_pipeline_recommendation_pregen([('same','samples')],{'id':'a'})
            self.assertEqual(len(f.native.launched),index)
            f.native.launched[-1].join(2);self.assertFalse(f.native.launched[-1].is_alive())
        self.assertTrue(f.native.drain());self.assertEqual(f.native.errors,[]);self.assertEqual(f.native.runtime_errors,[])
        recommendation=f.q.persistence.load_pipeline_task('same')['recommended_params']
        self.assertEqual(recommendation,{'stage':'samples','signature':f.owner.pipeline_recommendation_signature(row,'samples'),
            'params':{'sample_count':3},'reason':'uncached','source':'synthetic','created_at':100})
        self.assertEqual(f.native.events.count('recommendation'),1)
        self.assertIsNone(f.native.identity.get());self.assertIsNone(f.agent.models.current_snapshot())
    def test_blocked_actual_agent_producer_does_not_close_downstream(self):
        f=self.a;self.seed(f,stage='samples',status='completed',params={'epochs':2},auto_advance=True)
        entered=threading.Event();release=threading.Event();original=f.agent.b['chat']
        def chat(messages,config):
            entered.set()
            if not release.wait(5):raise AssertionError('blocked test did not release')
            original(messages,config)
            return json.dumps({'action':'advance','message_to_user':'next','reason':'synthetic'})
        f.agent.b['chat']=chat
        try:
            f.owner.execution.schedule_pipeline_auto_agent(['same'],{'id':'a'})
            self.assertTrue(entered.wait(2));self.assertFalse(f.owner.execution.auto.close(.01))
            self.seed(self.b);self.assertTrue(self.b.owner.execution.schedule_pipeline_advance('same',{'id':'b'}))
            self.assertTrue(self.b.native.drain());self.assertEqual(self.b.native.errors,[])
        finally:release.set()
        self.assertTrue(f.native.drain());self.assertEqual(f.native.runtime_errors,[])
        self.assertEqual(f.q.persistence.load_pipeline_task('same')['training_task_id'],'trained')
    def test_missing_captured_resolver_fails_before_any_stage_call(self):
        f=self.a;self.seed(f);f.owner.execution.model_resolver=lambda:None
        with f.scope():
            with self.assertRaisesRegex(RuntimeError,'resolver is not configured'):f.owner.execution.run_advance('same',{'id':'a'})
        self.assertFalse(any(e[0]=='samples' for e in f.stage.events))
        self.assertEqual(f.q.persistence.load_pipeline_task('same')['stage'],'draft')
    def test_frozen_mutation_test_seams_restore_and_preserve_other_graph(self):
        from pipeline_runtime_test_ports import patch_pipeline_runtime
        a,b=self.a.owner,self.b.owner
        names=('save_pipeline_task_batch_changes','persist_pipeline_task_progress','mark_pipeline_task_advancing')
        api=SimpleNamespace(_pipeline_workflows=a,**{name:getattr(a,name) for name in names})
        getters={
            'save_pipeline_task_batch_changes':a.mutations.storage.save_pipeline_task_batch_changes,
            'persist_pipeline_task_progress':a.stages.advance.runtime.persist_progress,
            'mark_pipeline_task_advancing':a.agent.actions._advance.mark,
        }
        other={
            'save_pipeline_task_batch_changes':b.mutations.storage.save_pipeline_task_batch_changes,
            'persist_pipeline_task_progress':b.stages.advance.runtime.persist_progress,
            'mark_pipeline_task_advancing':b.agent.actions._advance.mark,
        }
        original=a.mutations
        for name in names:
            with self.subTest(name=name):
                replacement=Mock(return_value='substituted')
                with patch_pipeline_runtime(api,name,replacement):
                    self.assertIs(getters[name](),replacement)
                    self.assertEqual(getters[name]()('synthetic'),'substituted')
                    replacement.assert_called_once_with('synthetic')
                    self.assertIs(other[name]().__self__,b)
                self.assertIs(getters[name]().__self__,a)
                self.assertIs(getattr(api,name).__self__,a)
                self.assertIs(a.mutations,original)
    def test_saved_owned_getter_selects_receiver_after_argument_effect(self):
        f=self.a;getter=f.owner.execution.auto.decision.decide()
        # The supplier returns a forwarder, not a captured sub-owner method.
        self.assertEqual(getter.__self__,f.owner)
        task=self.seed(self.b,detection_method='ai')
        def argument():f.owner.agent=self.b.owner.agent;return task
        with self.b.scope():
            decision=getter(argument(),self.b.q.config,user_message='hello')
        self.assertEqual(decision['message_to_user'],'b')
        self.assertFalse(any(e[0]=='chat' for e in f.agent.events))
    def test_runtime_type_hints_and_strict_original_source_inverse(self):
        get_type_hints(module.PipelineRuntimeWorkflows.advance_pipeline_task)
        from application_integration_source_contract import ROOT,CODEX_ENVIRONMENT,PIPELINE_RUNTIME,digest,restore_delta,restore_plc_domain_root
        source=(ROOT/'local_inspection_service/server.py').read_text();source=restore_delta(source,CODEX_ENVIRONMENT)
        self.assertEqual(digest(ast.parse(restore_delta(source,PIPELINE_RUNTIME))),PIPELINE_RUNTIME['parent_ast_sha256'])
        restore_plc_domain_root(source)

if POSTGRES:
    class RuntimePostgresContracts(unittest.TestCase):
        def test_two_native_graphs_scope_progress_failure_and_connection_release(self):
            import os
            import psycopg
            from psycopg import sql
            from uuid import uuid4
            from local_inspection_service.runtime.connections import ThreadRepositoryFactory
            from local_inspection_service.storage.postgres_schema import postgres_ddl
            from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
            dsn=os.environ['VANTALINE_POSTGRES_DSN'];connections=[];factories=[];graphs=[]
            schemas=['connected_pipeline_'+uuid4().hex for _ in range(2)]
            with tempfile.TemporaryDirectory(prefix='connected-pg-') as directory,psycopg.connect(dsn,autocommit=True) as control:
                try:
                    for account,schema in zip(('a','b'),schemas):
                        control.execute(postgres_ddl(schema))
                        def connect(schema=schema):
                            connection=psycopg.connect(dsn);connections.append(connection)
                            return SimpleNamespace(repository=PostgresRuntimeRepository(connection,'synthetic',schema))
                        factory=ThreadRepositoryFactory(connect,lambda schema=schema:schema);factories.append(factory)
                        f=build(Path(directory)/account,account,repository_factory=factory);graphs.append(f)
                        with factory.thread_scope():
                            RuntimeCompositionContracts.seed(self,f)
                        if account=='b':
                            def fail(task,config):raise RuntimeError('synthetic asset failure')
                            f.stage.b['prepare']=fail
                    for f in graphs:self.assertTrue(f.owner.execution.schedule_pipeline_advance('same',{'id':f.account}))
                    for f in graphs:
                        self.assertTrue(f.native.drain());self.assertEqual(f.native.errors,[])
                    self.assertTrue(all(connection.closed for connection in connections))
                    for f,factory in zip(graphs,factories):
                        with factory.thread_scope():
                            row=f.q.persistence.load_pipeline_task('same')
                            self.assertEqual(row['model_profiles']['pipeline']['account'],f.account)
                            if f.account=='a':self.assertEqual((row['stage'],row['samples_task_id']),('samples','generated'))
                            else:
                                self.assertEqual(row['stage'],'draft');self.assertIn('内部错误',row['last_error'])
                                self.assertEqual(len(f.native.runtime_errors),1);self.assertIn('synthetic asset failure',f.native.runtime_errors[0])
                        self.assertIsNone(f.native.identity.get());self.assertIsNone(f.agent.models.current_snapshot())
                    self.assertTrue(connections);self.assertTrue(all(connection.closed for connection in connections))
                finally:
                    for f in graphs:f.native.drain()
                    for factory in factories:factory.clear()
                    for schema in schemas:control.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
                self.assertTrue(all(connection.closed for connection in connections))

if __name__=='__main__':unittest.main()
