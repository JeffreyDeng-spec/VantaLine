"""Actual pipeline task graph, original HTTP registrars and isolated account state."""
from application_integration_source_contract import restore_pose_domain_root
import ast
import copy
from contextvars import ContextVar
from dataclasses import fields
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import get_type_hints
import unittest
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
POSTGRES='--postgres' in sys.argv
if POSTGRES:sys.argv.remove('--postgres')
from fastapi import HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.pipeline import task_composition as module
from local_inspection_service.runtime.http_application import create_http_application
from smoke_pipeline_query_composition import build as query_graph
from smoke_pipeline_stage_composition import build as stage_graph
from smoke_agent_pipeline_composition import graph as agent_graph
from smoke_pipeline_execution_composition import Graph as ExecutionGraph

GROUPS={name:kind for name,kind in get_type_hints(module.PipelineTaskWorkflows.__init__).items()
        if name not in ('queries','stages','execution','agent')}
REGISTRARS=('task_list','task_create','task_update','accessory_routes','task_delete',
            'agent_feedback','agent_chat','advance_control')

def compose(queries,stages,execution,agent,bindings):
    return module.PipelineTaskWorkflows(queries=queries,stages=stages,execution=execution,agent=agent,
        **{name:kind(**{f.name:lambda key=f.name:bindings[key] for f in fields(kind)})
           for name,kind in GROUPS.items()})

def build(root,account):
    root=Path(root);root.mkdir()
    queries=query_graph(root/'queries',account)
    stages=stage_graph(root/'stages',account,queries=queries)
    agent=agent_graph(root/'agent',account,queries=queries)
    execution=ExecutionGraph(root/'execution',account,persistence_owner=queries.persistence)
    identity=ContextVar('task-http-'+account,default={'id':account})
    events=[];permissions={'training_pipeline','incoming_material_config','inspection'}
    def current():
        user=identity.get()
        if user is None:raise HTTPException(401,'unauthenticated')
        return user
    def permitted(permission,**kwargs):
        events.append(('permission',permission))
        if permission not in permissions:raise HTTPException(403,'denied')
    def require_access(row,user,**kwargs):
        events.append(('access',row['id'],user['id']))
        if row.get('owner_user_id')!=user['id']:raise HTTPException(403,'denied')
    def unique(name,owner,**kwargs):
        for row in queries.persistence.load_pipeline_tasks():
            if row.get('id')!=kwargs.get('exclude_pipeline_task_id') and row.get('name')==name and row.get('owner_user_id')==owner:
                raise HTTPException(409,'duplicate')
    def cleanup(kind):
        def run(key,user,**kwargs):events.append(('delete_'+kind,key));return {'id':key}
        return run
    def poison(*args,**kwargs):raise AssertionError('unplanned paid/process operation')
    b={
        'current_user':current,'is_admin':lambda user:False,'load_config':lambda:queries.config,
        'scope_config':lambda config,user,*args:config,'load_ai_tasks':lambda:[],
        'visible':lambda row,user,target:row.get('owner_user_id')==user['id'],
        'incoming_allowed':lambda row,user:row.get('owner_user_id')==user['id'],
        'has_permission':lambda user,key:key in permissions,'monotonic':lambda:10,'min_interval':5,
        'save_config':lambda config:events.append(('save_config',)),
        'sync_ready_ai_tasks':lambda *args:False,'trained_specs':lambda *args:[],
        'optimize_states':lambda:[],'public_agent_config':lambda:{'enabled':True},'sanitize':lambda row:copy.deepcopy(row),
        'require_permission':permitted,'http_error':HTTPException,
        'owner_fields':lambda user,target:{'owner_user_id':user['id'],'owner_username':user['id']},
        'fallback_owner':lambda user:user['id'],'accessory_lookup':queries.b['accessory_lookup_by_id'],
        'load_agent_config':lambda:{'auto_advance_default':False},'normalize_expected_count':lambda value:max(0,int(value or 0)),
        'assert_unique_name':unique,'uuid4':uuid4,'now':lambda:100,
        'initialize_auto_optimize':lambda task,config:events.append(('initialize',task['id'])),
        'request_user':identity,'require_record_access':require_access,'record_owner_id':lambda row:row.get('owner_user_id'),
        'detection_methods':{'ai','yolo','yolo_ocr'},'resolve':queries.b['resolve_accessory_id'],
        'aliases':queries.b['accessory_id_aliases'],'delete_dataset':cleanup('dataset'),
        'delete_model':cleanup('model'),'delete_training_job':cleanup('training'),'delete_ai_task':cleanup('ai'),
        'sprite_flow':lambda *args:False,'ensure_plan':poison,'skip_legacy':poison,'mark_advancing':poison,
        'pose_calls':poison,'image_config':poison,'execute_calls':poison,'pause_task':poison,
        'bounded_text':lambda value,limit:str(value or '').strip()[:limit],'deepcopy':copy.deepcopy,
    }
    owner=compose(queries.owner,stages.owner,execution.owner,agent.owner,b)
    app=create_http_application({}).app
    endpoints=[]
    for name in REGISTRARS:endpoints.append(getattr(owner,'register_'+name)(app))
    return SimpleNamespace(owner=owner,queries=queries,stages=stages,agent=agent,execution=execution,
        identity=identity,permissions=permissions,b=b,app=app,endpoints=endpoints,events=events,account=account)

class TaskCompositionContracts(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='pipeline-task-graph-');self.addCleanup(tmp.cleanup)
        self.a=build(Path(tmp.name)/'a','a');self.b=build(Path(tmp.name)/'b','b')
        for f in (self.a,self.b):
            self.addCleanup(f.execution.owner.auto.close,1)
            self.addCleanup(f.execution.owner.advance.close,1)
            self.addCleanup(f.execution.owner.recommendation.close,1)
    def seed(self,f,**kwargs):
        row=dict(id='same',name='original',owner_user_id=f.account,accessory_ids=['a'],
            detection_method='yolo',stage='draft',status='ready',auto_advance=False,params={},
            model_profiles={'pipeline':{'version':1,'account':f.account}})
        row.update(kwargs);f.queries.persistence.save_pipeline_task(row);return row
    def test_constructor_inert_and_rejects_mismatched_owner_before_components(self):
        def poison(*args,**kwargs):raise AssertionError('eager selection')
        b={f.name:poison for kind in GROUPS.values() for f in fields(kind)}
        f=self.a;published=f.owner
        owner=compose(f.queries.owner,f.stages.owner,f.execution.owner,f.agent.owner,b)
        self.assertIs(owner.runtime,f.queries.persistence.runtime)
        for key,value in [('stages',self.b.stages.owner),('execution',self.b.execution.owner),('agent',self.b.agent.owner)]:
            args=dict(queries=f.queries.owner,stages=f.stages.owner,execution=f.execution.owner,agent=f.agent.owner,bindings=b);args[key]=value
            with patch.object(module,'PipelineTaskList',side_effect=AssertionError('component constructed')):
                with self.assertRaisesRegex(ValueError,'share queries'):published=compose(**args)
            self.assertIs(published,f.owner)
    def test_two_http_apps_original_route_order_schema_and_endpoint_identity(self):
        expected=[('/api/pipeline/tasks',{'GET'}),('/api/pipeline/tasks',{'POST'}),
            ('/api/pipeline/tasks/{task_id}',{'PATCH'}),('/api/pipeline/accessories/{accessory_id}',{'POST'}),
            ('/api/pipeline/accessories/{accessory_id}',{'DELETE'}),('/api/pipeline/tasks/{task_id}',{'DELETE'}),
            ('/api/pipeline/tasks/{task_id}/agent-feedback',{'POST'}),('/api/pipeline/tasks/{task_id}/chat',{'POST'}),
            ('/api/pipeline/tasks/{task_id}/advance',{'POST'}),('/api/pipeline/tasks/{task_id}/cancel-advance',{'POST'})]
        for f in (self.a,self.b):self.assertEqual([(r.path,r.methods) for r in f.app.routes],expected)
        self.assertEqual(self.a.app.openapi(),self.b.app.openapi())
        self.assertIsNot(self.a.app.routes[0].endpoint,self.b.app.routes[0].endpoint)
        self.assertIs(self.a.app.routes[0].endpoint,self.a.endpoints[0])
        self.assertEqual(len(self.a.app.router.on_startup),0)
    def test_http_auth_permissions_validation_and_same_id_account_isolation(self):
        for f in (self.a,self.b):self.seed(f)
        with TestClient(self.a.app) as client:
            self.a.identity.set(None);self.assertEqual(client.get('/api/pipeline/tasks').status_code,401)
            self.a.identity.set({'id':'a'});self.a.permissions.clear()
            self.assertEqual(client.post('/api/pipeline/tasks',json={'name':'new','accessory_ids':['a']}).status_code,403)
            self.assertEqual(client.patch('/api/pipeline/tasks/same',json={'expected_production_count':'bad'}).status_code,422)
            self.a.identity.set({'id':'b'})
            self.assertEqual(client.patch('/api/pipeline/tasks/same',json={'name':'forbidden'}).status_code,403)
        self.assertEqual(self.a.queries.persistence.load_pipeline_task('same')['name'],'original')
        self.assertEqual(self.b.queries.persistence.load_pipeline_task('same')['owner_user_id'],'b')
    def test_actual_ai_create_activation_persistence_projection_and_snapshot(self):
        f=self.a
        with TestClient(f.app) as client:
            result=client.post('/api/pipeline/tasks',json={'name':'AI','accessory_ids':['alias'],'detection_method':'ai','expected_production_count':10,'auto_advance':False})
        self.assertEqual(result.status_code,200);public=result.json();self.assertEqual(public['stage'],'library')
        stored=f.queries.persistence.load_pipeline_task(public['id'])
        self.assertEqual(stored['accessory_ids'],['a']);self.assertEqual(stored['owner_user_id'],'a')
        self.assertIn('model_profiles',stored);self.assertNotIn('model_profiles',public)
        self.assertIn(stored['ai_task_id'],f.stages.records)
        self.assertEqual(f.queries.persistence.load_pipeline_tasks()[0]['id'],stored['id'])
        self.assertEqual(self.b.queries.persistence.load_pipeline_tasks(),[])
    def test_http_update_real_store_preserves_bound_model_after_config_change(self):
        for f in (self.a,self.b):self.seed(f)
        old=self.a.queries.persistence.load_pipeline_task('same')['model_profiles']
        self.a.queries.persistence.tasks.resolver()().version=9
        with TestClient(self.a.app) as client:
            response=client.patch('/api/pipeline/tasks/same',json={'name':'renamed','accessory_ids':['alias'],'accessory_counts':{'alias':2}})
        self.assertEqual(response.status_code,200)
        stored=self.a.queries.persistence.load_pipeline_task('same')
        self.assertEqual(stored['name'],'renamed');self.assertEqual(stored['accessory_counts'],{'a':2})
        self.assertEqual(stored['model_profiles'],old);self.assertEqual(self.b.queries.persistence.load_pipeline_task('same')['name'],'original')
        with TestClient(self.b.app) as client:
            second=client.patch('/api/pipeline/tasks/same',json={'name':'b-renamed'})
        self.assertEqual(second.status_code,200)
        self.assertEqual(self.b.queries.persistence.load_pipeline_task('same')['name'],'b-renamed')
        self.assertEqual(self.a.queries.persistence.load_pipeline_task('same')['name'],'renamed')
    def test_chat_real_agent_single_pin_outside_guard_second_auth_and_saved_turn(self):
        f=self.a;self.seed(f);checks=[];old=f.b['require_record_access']
        def access(row,user,**kwargs):checks.append(f.execution.task_held.get());return old(row,user,**kwargs)
        f.b['require_record_access']=access;old_chat=f.agent.b['chat']
        def chat(*args):self.assertFalse(f.execution.task_held.get());return old_chat(*args)
        f.agent.b['chat']=chat
        with TestClient(f.app) as client:result=client.post('/api/pipeline/tasks/same/chat',json={'message':'hello'})
        self.assertEqual(result.status_code,200);self.assertEqual(checks,[True,True])
        events=f.agent.events;self.assertEqual([e[0] for e in events],['provider','pin-enter','chat','pin-exit'])
        self.assertEqual(events[2][2],{'pipeline':{'version':1,'account':'a'}})
        self.assertIsNone(f.agent.models.current_snapshot())
        row=f.queries.persistence.load_pipeline_task('same')
        self.assertEqual([r['message'] for r in row['agent_mcp']['conversation']],['hello','a'])
    def test_second_chat_permission_failure_keeps_original_record_without_replay(self):
        f=self.a;self.seed(f);calls=[];access=f.b['require_record_access']
        def deny_second(row,user,**kwargs):
            calls.append(row['id'])
            if len(calls)==2:raise HTTPException(403,'second denial')
            return access(row,user,**kwargs)
        f.b['require_record_access']=deny_second
        with TestClient(f.app) as client:result=client.post('/api/pipeline/tasks/same/chat',json={'message':'hello'})
        self.assertEqual(result.status_code,403);self.assertEqual(len([e for e in f.agent.events if e[0]=='chat']),1)
        self.assertNotIn('agent_mcp',f.queries.persistence.load_pipeline_task('same'))
    def test_update_projection_failure_retains_committed_change(self):
        f=self.a;self.seed(f)
        with patch.object(f.queries.owner,'pipeline_task_public',side_effect=RuntimeError('projection')):
            with TestClient(f.app,raise_server_exceptions=False) as client:
                self.assertEqual(client.patch('/api/pipeline/tasks/same',json={'name':'saved'}).status_code,500)
        self.assertEqual(f.queries.persistence.load_pipeline_task('same')['name'],'saved')
    def test_delete_uses_actual_cancel_then_permission_and_partial_cleanup(self):
        f=self.a;self.seed(f,dataset_id='dataset',model_run_id='model')
        event=__import__('threading').Event();f.owner.runtime.advance_cancel['same']=event
        f.identity.set({'id':'denied'})
        with TestClient(f.app) as client:self.assertEqual(client.delete('/api/pipeline/tasks/same').status_code,403)
        self.assertTrue(event.is_set());self.assertIsNotNone(f.queries.persistence.load_pipeline_task('same'))
        f.identity.set({'id':'a'})
        def fail(*args,**kwargs):raise RuntimeError('model cleanup')
        f.b['delete_model']=fail
        with TestClient(f.app,raise_server_exceptions=False) as client:self.assertEqual(client.delete('/api/pipeline/tasks/same').status_code,500)
        self.assertIsNone(f.queries.persistence.load_pipeline_task('same'));self.assertIn(('delete_dataset','dataset'),f.events)
    def test_list_real_reconciliation_once_throttles_and_filters_after_saved_changes(self):
        f=self.a;self.seed(f,stage='samples',status='running',samples_task_id='job',params={'epochs':1})
        self.seed(f,id='hidden',owner_user_id='hidden',stage='samples',status='running',samples_task_id='job',params={'epochs':1})
        f.stages.jobs['job']={'status':'completed','progress':100}
        with TestClient(f.app) as client:
            first=client.get('/api/pipeline/tasks');second=client.get('/api/pipeline/tasks')
        self.assertEqual((first.status_code,second.status_code),(200,200))
        self.assertEqual([row['id'] for row in first.json()['items']],['same'])
        self.assertEqual(first.json()['items'][0]['status'],'completed')
        self.assertEqual(f.queries.persistence.load_pipeline_task('hidden')['status'],'completed')
        self.assertEqual(f.stages.events,[('finder',)])
        self.assertEqual(f.owner.runtime.last_sync_at,10)

    def test_advance_shared_registry_suppresses_duplicates_and_schedules_after_unlock(self):
        f=self.a;self.seed(f);runtime=f.owner.runtime
        runtime.advance_inflight.add('same')
        seen=[]
        def schedule(task,user):
            self.assertFalse(f.execution.task_held.get())
            self.assertTrue(f.queries.persistence.load_pipeline_task(task)['advancing'])
            seen.append((task,user['id']));return True
        with patch.object(f.execution.owner.advance,'schedule',side_effect=schedule) as scheduled:
            with TestClient(f.app) as client:
                self.assertEqual(client.post('/api/pipeline/tasks/same/advance').status_code,200)
                scheduled.assert_not_called()
                runtime.advance_inflight.clear()
                self.assertEqual(client.post('/api/pipeline/tasks/same/advance').status_code,200)
        self.assertEqual(seen,[('same','a')]);self.assertTrue(f.queries.persistence.load_pipeline_task('same')['advancing'])

    def test_feedback_cancel_keeps_external_pose_boundary_and_partial_saved_state(self):
        f=self.a;self.seed(f)
        def plan(task,config,**kwargs):
            self.assertTrue(f.execution.task_held.get());return task.setdefault('agent_mcp',{})
        f.b['ensure_plan']=plan
        with TestClient(f.app) as client:result=client.post('/api/pipeline/tasks/same/agent-feedback',json={'action':'cancel'})
        self.assertEqual(result.status_code,200)
        row=f.queries.persistence.load_pipeline_task('same')
        self.assertEqual(row['status'],'stopped');self.assertEqual(row['agent_mcp']['state'],'cancelled')
        self.assertEqual(len(row['agent_mcp']['feedback']),1)

    def test_saved_public_getter_selects_actual_query_after_argument_effect(self):
        a,b=self.a,self.b
        getter=a.owner.updater.runtime.public_task
        saved=getter()
        task={'id':'same','ai_task_id':'same','accessory_ids':['a'],'detection_method':'ai'}
        def argument():
            a.owner.queries=b.queries.owner
            return task
        result=saved(argument(),a.queries.config)
        self.assertEqual(result['accessory_labels']['a'],'b')
        self.assertIs(getter().__self__,a.owner)

    def test_source_inverse_rejects_unknown_route_or_owner(self):
        from application_integration_source_contract import ROOT,CODEX_ENVIRONMENT,PIPELINE_RUNTIME,PIPELINE_TASKS,restore_delta,restore_plc_domain_root
        source=read_checked_application_source(ROOT / 'local_inspection_service/server.py');source=restore_pose_domain_root(source);source=restore_delta(source,CODEX_ENVIRONMENT);source=restore_delta(source,PIPELINE_RUNTIME);restore_plc_domain_root(source)
        restored=restore_delta(source,PIPELINE_TASKS);self.assertNotIn('_pipeline_tasks = PipelineTaskWorkflows',restored)
        with self.assertRaises(AssertionError):restore_plc_domain_root(source.replace('stages=_pipeline_stages,','stages=None,',1))

if POSTGRES:
    class TaskPostgresContracts(unittest.TestCase):
        def test_parallel_actual_account_graphs_same_id_updates_and_projection_failure(self):
            from concurrent.futures import ThreadPoolExecutor
            import os
            import psycopg
            from psycopg import sql
            from local_inspection_service.runtime.connections import ThreadRepositoryFactory
            from local_inspection_service.storage.postgres_schema import postgres_ddl
            from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
            from local_inspection_service.schemas.pipeline import PipelineTaskCreateRequest,PipelineTaskUpdateRequest
            dsn=os.environ['VANTALINE_POSTGRES_DSN'];connections=[];factories=[];graphs=[]
            schemas=['task_graph_'+uuid4().hex for _ in range(2)]
            with tempfile.TemporaryDirectory(prefix='task-graph-pg-') as directory,psycopg.connect(dsn,autocommit=True) as control:
                try:
                    for account,schema in zip(('a','b'),schemas):
                        control.execute(postgres_ddl(schema));f=build(Path(directory)/account,account);graphs.append(f)
                        def connect(schema=schema):
                            connection=psycopg.connect(dsn);connections.append(connection)
                            return SimpleNamespace(repository=PostgresRuntimeRepository(connection,'synthetic',schema))
                        factory=ThreadRepositoryFactory(connect,lambda schema=schema:schema);factories.append(factory)
                        get=lambda factory=factory:factory.selection().repository
                        f.queries.persistence.tasks.repository=get;f.queries.persistence.state.repository=get
                        f.queries.b['runtime_postgres_repository_or_none']=get
                        f.queries.b['PIPELINE_DETECTION_METHODS'].add('label_text_compare')
                        f.b['uuid4']=lambda:SimpleNamespace(hex='1234567890abcdef')
                    def exercise(index):
                        f=graphs[index];factory=factories[index]
                        with factory.thread_scope():
                            created=f.owner.creator.create(PipelineTaskCreateRequest(name='material',task_kind='incoming_material_text',material_code='code',auto_advance=False))
                            self.assertEqual(created['id'],'pipe_1234567890');self.assertEqual(created['owner_user_id'],f.account)
                            before=f.owner.load_pipeline_task(created['id'])['model_profiles']
                            f.queries.persistence.tasks.resolver()().version=9
                            updated=f.owner.updater.update(created['id'],PipelineTaskUpdateRequest(name='renamed_'+f.account))
                            self.assertEqual(updated['name'],'renamed_'+f.account)
                            self.assertEqual(f.owner.load_pipeline_task(created['id'])['model_profiles'],before)
                            with patch.object(f.queries.owner,'pipeline_task_public',side_effect=RuntimeError('postcommit projection')):
                                with self.assertRaisesRegex(RuntimeError,'postcommit projection'):
                                    f.owner.updater.update(created['id'],PipelineTaskUpdateRequest(name='saved_'+f.account))
                            self.assertEqual(f.owner.load_pipeline_task(created['id'])['name'],'saved_'+f.account)
                            self.assertIsNone(graphs[1-index].agent.models.current_snapshot())
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures=[pool.submit(exercise,index) for index in range(2)]
                        for future in futures:future.result(timeout=30)
                    self.assertTrue(connections);self.assertTrue(all(c.closed for c in connections))
                    for f,factory in zip(graphs,factories):
                        with factory.thread_scope():
                            rows=f.owner.load_pipeline_tasks();self.assertEqual(len(rows),1)
                            self.assertEqual((rows[0]['owner_user_id'],rows[0]['name']),(f.account,'saved_'+f.account))
                    self.assertTrue(all(c.closed for c in connections))
                finally:
                    for f in graphs:
                        for owner in (f.execution.owner.auto,f.execution.owner.advance,f.execution.owner.recommendation):owner.close(1)
                    for factory in factories:factory.clear()
                    for schema in schemas:control.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
if __name__=='__main__':unittest.main()
