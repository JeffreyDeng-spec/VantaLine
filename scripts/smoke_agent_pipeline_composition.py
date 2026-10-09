"""Actual six-service Agent graph and real model scopes with offline providers."""
import ast
from contextlib import contextmanager
from dataclasses import fields
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import get_type_hints
from uuid import uuid4
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.agent import pipeline_composition as module
from local_inspection_service.model_profiles.dependencies import ProfileDependencies
from local_inspection_service.model_profiles.service import Service
from smoke_pipeline_query_composition import build as query_graph

GROUPS={name:kind for name,kind in get_type_hints(module.AgentPipelineWorkflows.__init__).items()
        if name not in ('queries','model_resolver')}

def compose(queries,provider,bindings):
    return module.AgentPipelineWorkflows(queries=queries,model_resolver=provider,
        **{name:kind(**{f.name:lambda key=f.name:bindings[key] for f in fields(kind)})
           for name,kind in GROUPS.items()})

def graph(root,account,*,queries=None):
    queries=queries if queries is not None else query_graph(root,account);events=[]
    def poison(*args,**kwargs):raise AssertionError('model storage/secret access forbidden')
    models=Service(ProfileDependencies(**{f.name:poison for f in fields(ProfileDependencies)}))
    scope=models.scope
    @contextmanager
    def observed_scope(snapshot):
        events.append(('pin-enter',snapshot))
        with scope(snapshot):
            try:yield
            finally:events.append(('pin-exit',snapshot))
    models.scope=observed_scope
    def provider():events.append(('provider',account));return models
    def orchestration(task):return task.setdefault('agent_mcp',{})
    def chat(messages,config):
        events.append(('chat',account,models.current_snapshot(),messages,config))
        return json.dumps({'action':'reply','message_to_user':account,'reason':'synthetic'})
    def mark(task):events.append(('mark',account));task['status']='advancing'
    bindings={
        'orchestration':orchestration,'now':lambda:1,'uuid':uuid4,'limit':5,
        'bounded':lambda value,limit:str(value or '')[:limit],
        'image_config':lambda:{'configured':False},'missing_assets':lambda *args:[],
        'training_job':lambda task:None,'pose_tool':'pose',
        'lookup':queries.b['accessory_lookup_by_id'],'material':lambda item:'object',
        'stage_order':['draft','samples','training','library'],
        'actions':{'reply','advance','set_params','goto_stage','retry','replan','pause_and_ask','continue_existing_assets','continue_training','cancel'},
        'targets':{'draft','samples'},'load':lambda:{'account':account},'supported':lambda config:True,
        'prompt':'synthetic-'+account,'dumps':json.dumps,'parse':json.loads,'chat':chat,
        'http_error_type':type('HttpError',(Exception,),{}),'pause':lambda *args,**kwargs:None,
        'mark':mark,'sync':lambda task:events.append(('sync',account)) or False,
        'advance':lambda task:events.append(('advance',account)),
        'delete':lambda *args,**kwargs:events.append(('delete',account)),
        'photo_flow':lambda task,config:False,'skip_legacy':lambda task,config,orch:orch,
        'plan':lambda task,config,**kwargs:orchestration(task),'ensure_calls':lambda task,config:orchestration(task),
        'config':lambda:{},'execute':lambda task,config:True,
    }
    owner=compose(queries.owner,provider,bindings)
    return SimpleNamespace(owner=owner,queries=queries,models=models,events=events,b=bindings,provider=provider)

class AgentCompositionContracts(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory(prefix='agent-owned-');self.addCleanup(directory.cleanup)
        self.a=graph(Path(directory.name)/'a','a');self.b=graph(Path(directory.name)/'b','b')
    def task(self,account):return {'id':'same','accessory_ids':['a'],'detection_method':'ai',
        'model_profiles':{'pipeline':{'account':account,'version':1,'secret_ref':'synthetic-reference'}}}

    def test_constructor_inert_partial_failure_never_publishes_owner(self):
        def poison(*args,**kwargs):raise AssertionError('constructor selected supplier')
        bindings={f.name:poison for kind in GROUPS.values() for f in fields(kind)}
        owner=compose(object(),poison,bindings);published=owner
        with patch.object(module,'AgentDecisionFlow',side_effect=RuntimeError('flow constructor')):
            with self.assertRaisesRegex(RuntimeError,'flow constructor'):published=compose(object(),poison,bindings)
        self.assertIs(published,owner)

    def test_two_actual_graphs_same_ids_real_model_scopes_queries_and_conversations(self):
        tasks={account:self.task(account) for account in ('a','b')}
        for f,account in ((self.a,'a'),(self.b,'b'),(self.a,'a')):
            task=tasks[account]
            result=f.owner.agent_pipeline_decide(task,f.queries.config,user_message='hello')
            self.assertEqual(result['message_to_user'],account)
            pending=[];f.owner.commit_pipeline_agent_turn(task,f.queries.config,{'id':account},'hello',result,'chat',pending)
            chats=[e for e in f.events if e[0]=='chat'];self.assertEqual(chats[-1][2],task['model_profiles'])
            context=json.loads(chats[-1][3][1]['content'])
            self.assertEqual(context['accessories'][0]['name'],account)
            self.assertEqual(chats[-1][3][0]['content'],'synthetic-'+account)
            self.assertIsNone(f.models.current_snapshot());self.assertEqual(pending,[])
        self.assertEqual([x['message'] for x in tasks['a']['agent_mcp']['conversation']],['hello','a','hello','a'])
        self.assertEqual([x['message'] for x in tasks['b']['agent_mcp']['conversation']],['hello','b'])
        self.assertIsNot(tasks['a']['agent_mcp'],tasks['b']['agent_mcp'])

    def test_record_snapshot_priority_and_outer_scope_restoration_single_pin(self):
        f=self.a;task=self.task('a');outer={'pipeline':{'version':9}}
        with f.models.scope(outer):
            f.events.clear();f.owner.agent_pipeline_decide(task,f.queries.config)
            self.assertEqual(f.models.current_snapshot(),outer)
            self.assertEqual([e[0] for e in f.events],['provider','pin-enter','chat','pin-exit'])
            self.assertIs([e for e in f.events if e[0]=='chat'][0][2],task['model_profiles'])
        self.assertIsNone(f.models.current_snapshot())

    def test_public_compatibility_decision_real_service_single_pin(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        f=self.a;task=self.task('a')
        with patch.object(server._model_profile_configuration,'service',f.models), \
             patch.object(server,'_agent_decision_flow',f.owner.decision):
            result=server.agent_pipeline_decide(task,f.queries.config,user_message='public')
        self.assertEqual(result['message_to_user'],'a')
        self.assertEqual([e[0] for e in f.events],['pin-enter','chat','pin-exit'])
        self.assertIs(f.events[1][2],task['model_profiles']);self.assertIsNone(f.models.current_snapshot())

    def test_missing_model_fails_before_settings_context_chat_and_rule_fallback(self):
        f=self.a;f.owner.model_resolver=lambda:None
        def poison(*args,**kwargs):raise AssertionError('work before model binding')
        for key in ('load','supported','chat'):f.b[key]=poison
        with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'):
            f.owner.agent_pipeline_decide(self.task('a'),{})
        self.assertEqual(f.events,[])

    def test_receiver_selected_after_scope_entry_and_provider_is_direct(self):
        f=self.a;old_scope=f.models.scope;seen=[]
        alternate=SimpleNamespace(agent_pipeline_decide=lambda *args,**kwargs:seen.append(f.models.current_snapshot()) or {'receiver':'late'})
        @contextmanager
        def switch(snapshot):
            with old_scope(snapshot):f.owner.decision=alternate;yield
        f.models.scope=switch;self.assertIs(f.owner.model_resolver,f.provider)
        task=self.task('a');self.assertEqual(f.owner.agent_pipeline_decide(task,{}),{'receiver':'late'})
        self.assertEqual(seen,[task['model_profiles']]);self.assertIsNone(f.models.current_snapshot())

    def test_flow_try_boundary_chat_failure_no_retry_and_scope_release(self):
        f=self.a;error=RuntimeError('context before try');calls=[]
        with patch.object(f.owner,'agent_pipeline_context',side_effect=error):
            with self.assertRaises(RuntimeError) as caught:f.owner.agent_pipeline_decide(self.task('a'),{})
        self.assertIs(caught.exception,error);self.assertFalse(any(e[0]=='chat' for e in f.events))
        def fail_chat(*args):calls.append('chat');raise RuntimeError('transport')
        f.b['chat']=fail_chat
        result=f.owner.agent_pipeline_decide(self.task('a'),f.queries.config)
        self.assertEqual(result['source'],'rules');self.assertEqual(result['agent_error'],'transport')
        self.assertEqual(calls,['chat']);self.assertIsNone(f.models.current_snapshot())
        def interrupt(*args):raise KeyboardInterrupt('interrupt')
        f.b['chat']=interrupt
        with self.assertRaises(KeyboardInterrupt):f.owner.agent_pipeline_decide(self.task('a'),f.queries.config)
        self.assertIsNone(f.models.current_snapshot())

    def test_empty_pending_queues_only_and_none_preserves_inline_behavior(self):
        f=self.a;task=self.task('a');pending=[]
        f.owner.agent_safe_advance(task,{},pending);f.owner.agent_safe_advance(task,{},pending)
        self.assertEqual(pending,['same']);self.assertEqual(f.events,[('mark','a'),('mark','a')])
        f.events.clear();f.owner.agent_safe_advance(task,{},None)
        self.assertEqual(f.events,[('sync','a'),('advance','a')])

    def test_turn_failures_preserve_prior_conversation_and_action_no_retry(self):
        f=self.a;task=self.task('a');error=RuntimeError('apply');calls=[]
        def fail_apply(*args,**kwargs):calls.append('apply');raise error
        with patch.object(f.owner,'apply_agent_pipeline_decision',side_effect=fail_apply):
            with self.assertRaises(RuntimeError) as caught:f.owner.commit_pipeline_agent_turn(task,{},None,'question',{},'chat')
        self.assertIs(caught.exception,error);self.assertEqual(calls,['apply'])
        self.assertEqual([x['message'] for x in task['agent_mcp']['conversation']],['question'])
        real_append=f.owner.agent_mcp_append_conversation;appends=[]
        task['detection_method']='yolo'
        def append(*args,**kwargs):
            appends.append(args[1])
            if args[1]=='agent':raise RuntimeError('final append')
            return real_append(*args,**kwargs)
        with patch.object(f.owner,'agent_mcp_append_conversation',side_effect=append):
            with self.assertRaisesRegex(RuntimeError,'final append'):
                f.owner.commit_pipeline_agent_turn(task,{},None,'second',{'action':'cancel'},'chat')
        self.assertEqual(appends,['user','agent']);self.assertEqual(task['status'],'stopped')
        self.assertEqual([x['message'] for x in task['agent_mcp']['conversation']],['question','second'])

    def test_actual_native_caller_decides_outside_guard_commits_saves_inside_then_schedules(self):
        from dataclasses import replace
        from smoke_pipeline_execution_composition import Graph
        with tempfile.TemporaryDirectory(prefix='agent-native-caller-') as root:
            native=Graph(root,'a');f=self.a;trace=[]
            native.models=f.models;native.snapshot=f.models._scope
            native.seed('same',auto=True)
            row=native.persistence.load_pipeline_task('same');row.update(detection_method='yolo',accessory_ids=['a'])
            native.persistence.save_pipeline_task(row)
            def chat(*args):
                self.assertFalse(native.task_held.get());self.assertTrue(native.active_scope.get())
                self.assertEqual(native.identity.get(),{'id':'a'})
                trace.append('decide');return json.dumps({'action':'advance','message_to_user':'advance','reason':'synthetic'})
            f.b['chat']=chat
            def commit(*args,**kwargs):
                self.assertTrue(native.task_held.get());trace.append('commit')
                return f.owner.commit_pipeline_agent_turn(*args,**kwargs)
            runtime=native.owner.auto
            runtime.decision=replace(runtime.decision,load_config=lambda:lambda:f.queries.config,
                decide=lambda:f.owner.agent_pipeline_decide,commit=lambda:commit)
            real_save=native.owner.save_pipeline_task
            def save(task):
                self.assertTrue(native.task_held.get());trace.append('save');return real_save(task)
            native.owner.save_pipeline_task=save
            real_schedule=native.owner.schedule_pipeline_advance
            def schedule(*args):
                self.assertFalse(native.task_held.get());trace.append('schedule');return real_schedule(*args)
            native.owner.schedule_pipeline_advance=schedule
            native.owner.schedule_pipeline_auto_agent(['same'],{'id':'a'})
            self.assertTrue(native.drain());self.assertEqual(native.errors,[]);self.assertEqual(native.runtime_errors,[])
            self.assertEqual(trace,['decide','commit','save','schedule','save','save'])
            row=native.persistence.load_pipeline_task('same');self.assertEqual(row['status'],'completed')
            self.assertEqual(row['agent_mcp']['conversation'][0]['message'],'advance')
            self.assertIsNone(f.models.current_snapshot());self.assertIsNone(native.identity.get())

    def test_saved_callbacks_keep_original_callee_selection_and_late_receiver(self):
        f=self.a;a=f.owner;b=self.b.owner
        self.b.b['now']=lambda:99
        self.assertEqual(self.a.b['now'](),1)
        saved=a.turns._turn.append()
        def switch_task():a.conversation=b.conversation;return {}
        task=switch_task();saved(task,'user','late')
        self.assertEqual(task['agent_mcp']['conversation'][0]['message'],'late')
        self.assertEqual(task['agent_mcp']['conversation'][0]['created_at'],99)
        self.assertEqual(task['agent_mcp']['updated_at'],99)
        self.assertIs(saved.__self__,a)
        selected=[];late=[]
        a.canonical_pipeline_accessory_ids=lambda config,ids:selected.append(ids) or ['a']
        class Identifier:
            def __str__(self):a.canonical_pipeline_accessory_ids=lambda *args:late.append(True) or [];return 'a'
        result=a.agent_pipeline_quality_signals({'accessory_ids':[Identifier()]},f.queries.config)
        self.assertEqual(result['accessory_count'],1);self.assertEqual(selected,[['a']]);self.assertEqual(late,[])

    def test_strict_source_inverse_rejects_owner_or_provider_mutation(self):
        from application_integration_source_contract import ROOT,PIPELINE_RUNTIME,PIPELINE_TASKS,PIPELINE_STAGES,AGENT_PIPELINE,digest,restore_delta,restore_plc_domain_root
        source=(ROOT/'local_inspection_service/server.py').read_text();source=restore_delta(source,PIPELINE_RUNTIME)
        self.assertEqual(digest(ast.parse(restore_delta(restore_delta(restore_delta(source,PIPELINE_TASKS),PIPELINE_STAGES),AGENT_PIPELINE))),AGENT_PIPELINE['parent_ast_sha256'])
        restore_plc_domain_root(source)
        for old,new in (('_agent_decision_flow = _agent_pipeline_workflows.decision','_agent_decision_flow = _agent_pipeline_workflows.policy'),
            ('model_resolver=resolve_model_profiles,','model_resolver=lambda: resolve_model_profiles,')):
            self.assertIn(old,source)
            with self.assertRaises(AssertionError):restore_plc_domain_root(source.replace(old,new))

if __name__=='__main__':unittest.main(verbosity=2)
