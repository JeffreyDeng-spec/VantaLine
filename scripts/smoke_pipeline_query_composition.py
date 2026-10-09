"""Actual six-service query graph, including its protected write side effects."""
import ast
from dataclasses import fields
import json
from pathlib import Path
import sys
import tempfile
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
POSTGRES='--postgres' in sys.argv
if POSTGRES:sys.argv.remove('--postgres')
from local_inspection_service.pipeline import query_composition as module
from local_inspection_service.storage.artifacts.files import BusinessFiles
from smoke_pipeline_stores import Fixture
from smoke_pipeline_persistence_composition import build as persistence_graph

GROUPS = {
    'metadata_policy': module.QueryMetadataPolicyInputs,
    'metadata_snapshots': module.QueryMetadataSnapshotsInputs,
    'candidates_storage': module.QueryCandidateStorageInputs,
    'candidates_progress': module.QueryCandidateProgressInputs,
    'candidates_projection': module.QueryCandidateProjectionInputs,
    'snapshots_0': module.QueryPipelineTaskSnapshotLinksInputs,
    'resources_0': module.QueryPipelineResourceStatusLinksInputs,
    'optimization_state': module.QueryLinkStateInputs,
    'optimization_projection': module.QueryLinkProjectionInputs,
    'projection_metadata': module.QueryProjectionMetadataInputs,
    'projection_resources': module.QueryProjectionResourcesInputs,
}

class Guard:
    def __init__(self): self.lock=RLock(); self.depth=0
    def __enter__(self): self.lock.acquire(); self.depth+=1
    def __exit__(self,*args): self.depth-=1; self.lock.release()

def compose(persistence, files, bindings):
    groups={name:cls(**{f.name:lambda key=f.name:bindings[key] for f in fields(cls)})
            for name,cls in GROUPS.items()}
    return module.PipelineQueries(persistence=persistence,files=files,**groups)

def build(root, account):
    root=Path(root); root.mkdir(exist_ok=True)
    f=Fixture(root); persistence=persistence_graph(f)
    events=[]; candidate_guard=Guard(); optimize_guard=Guard(); files=BusinessFiles()
    item={'id':'a','name':account,'aliases':['alias'],'owner_user_id':account}
    config={'accessories':[item]}
    def lookup(c): return {row['id']:row for row in c.get('accessories',[])}
    def resolve(c,key): return ('a',lookup(c)['a']) if key in ('a','alias') else None
    state={'task_id':'same','task_name':account,'owner_user_id':account,
           'active_model_id':'model_'+account,'settings':{'enabled':True},
           'selected_accessory_ids':['a'],'required_accessory_counts':{'a':1}}
    def save_candidate(path,row):
        assert candidate_guard.depth==1
        events.append(('candidate_save',account)); path.write_text(json.dumps(row))
    def stop(row,model,*,reason):
        assert optimize_guard.depth==1
        events.append(('stop',account,model)); row['capture_stop_reason']=reason; return True
    def save_auto(row):
        assert optimize_guard.depth==1
        events.append(('optimization_save',account))
    bindings={
        'PIPELINE_DETECTION_METHODS':{'ai','yolo','yolo_ocr'},'PIPELINE_TRAINING_METHODS':{'yolo','yolo_ocr'},
        'accessory_lookup_by_id':lookup,'LEGACY_OWNER_ID':'legacy',
        'record_owner_username':lambda row:row.get('owner_user_id','legacy'),
        'accessory_id_aliases':lambda row:[row['id']]+row.get('aliases',[]),
        'ACCESSORY_CANDIDATES_DIR':root,'_candidate_store_lock':candidate_guard,
        'runtime_postgres_repository_or_none':lambda:None,
        'load_accessory_candidate':lambda key:json.loads((root/(key+'.json')).read_text()),
        'HTTPException':type('HttpError',(Exception,),{'status_code':404}),
        '_business_files':files,'save_accessory_candidate':save_candidate,'load_config':lambda:config,
        'candidate_image_jobs':lambda row:row.get('jobs',[]),'IMAGE_JOB_ACTIVE_STATUSES':{'running','queued'},
        'ensure_candidate_image_job_task_ids':lambda row:False,
        'refresh_codex_image_job':lambda job:dict(job,status='completed',progress=100),
        'store_candidate_image_job':lambda row,job:row.update(jobs=[job]),
        'resolve_accessory_id':resolve,'enrich_record_audit_fields':lambda row,*args:dict(row),
        'accessory_material_type':lambda row:'object',
        'record_visible_to_user':lambda row,user,target:row.get('owner_user_id')==user['id'],
        'serialize_accessory':lambda row:dict(row),
        'load_ai_tasks':lambda:[{'id':'same','accessory_labels':{'a':account}}],
        'accessory_lookup':lookup,'find_dataset':lambda key:(root,None),
        'list_trained_specs':lambda:[], 'sanitize_ai_detection_task_id':lambda value:str(value or '').strip(),
        '_auto_optimize_lock':optimize_guard,'load_auto_optimize_state':lambda key:state,
        'auto_optimize_completed_model_id':lambda row:row['active_model_id'],
        'auto_optimize_stop_capture_for_model_locked':stop,'save_auto_optimize_state':save_auto,
        'list_auto_optimize_states':lambda:[state], 'auto_optimize_phase_name':lambda row:'ready',
        'ai_detection_task_model_id':lambda key:'ai_'+account,'public_path_sanitized':lambda row:dict(row),
    }
    owner=compose(persistence,files,bindings)
    return SimpleNamespace(owner=owner,b=bindings,events=events,state=state,config=config,root=root,
        persistence=persistence,candidate_guard=candidate_guard,optimize_guard=optimize_guard,files=files)

class QueryCompositionContracts(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='pipeline-query-');self.addCleanup(self.directory.cleanup)
        self.a=build(Path(self.directory.name)/'a','account_a')
        self.b=build(Path(self.directory.name)/'b','account_b')

    def test_constructor_selects_no_suppliers_and_partial_failure_not_published(self):
        def poison(*args,**kwargs):raise AssertionError('eager supplier')
        bindings={f.name:poison for cls in GROUPS.values() for f in fields(cls)}
        class FalseFiles:
            def __bool__(self):return False
            def __getattr__(self,name):raise AssertionError('eager files')
        files=FalseFiles();owner=compose(object(),files,bindings)
        self.assertIs(owner.resources.files,files)
        published=owner
        with self.assertRaisesRegex(TypeError,'files is required'):published=compose(object(),None,bindings)
        self.assertIs(published,owner)

    def test_two_actual_graphs_keep_same_ids_accounts_snapshots_and_state_isolated(self):
        for f,account in ((self.a,'account_a'),(self.b,'account_b'),(self.a,'account_a')):
            task={'ai_task_id':'same','accessory_ids':['alias','a','unknown'],
                  'accessory_counts':{'alias':2},'model_profiles':{'secret':'synthetic'},'detection_method':'ai'}
            result=f.owner.pipeline_task_public(task,f.config,ai_task_ids={'same'},
                trained_model_specs=[],auto_optimize_states=[],auto_optimize_states_by_id={})
            self.assertNotIn('model_profiles',result);self.assertIn('model_profiles',task)
            self.assertEqual(result['accessory_ids'],['a','unknown'])
            self.assertEqual(result['accessory_labels']['a'],account)
            self.assertEqual(result['accessory_counts']['a'],2)
            self.assertEqual(f.events,[])
        self.a.persistence.add_pipeline_accessory_id('a')
        self.assertEqual(self.a.owner.load_pipeline_state()['accessory_ids'],['a'])
        self.assertEqual(self.b.owner.load_pipeline_state()['accessory_ids'],[])

    def test_candidate_refresh_saves_inside_guard_and_retains_failed_write_effects(self):
        f=self.a;path=f.root/'same.json';row={'id':'same','owner_user_id':'account_a','jobs':[{'status':'running'}]}
        path.write_text(json.dumps(row));result,removed=f.owner.refresh_pipeline_candidate('same')
        self.assertFalse(removed);self.assertEqual(result['jobs'][0]['status'],'completed')
        self.assertEqual(json.loads(path.read_text())['jobs'][0]['status'],'completed')
        self.assertEqual(f.events,[('candidate_save','account_a')]);self.assertEqual(f.candidate_guard.depth,0)
        path.write_text(json.dumps(row));error=RuntimeError('save after mutation');seen=[]
        def fail(path,record):
            self.assertEqual(f.candidate_guard.depth,1);seen.append(record);raise error
        f.b['save_accessory_candidate']=fail
        with self.assertRaises(RuntimeError) as caught:f.owner.refresh_pipeline_candidate('same')
        self.assertIs(caught.exception,error);self.assertEqual(seen[0]['jobs'][0]['status'],'completed')
        self.assertEqual(json.loads(path.read_text())['jobs'][0]['status'],'running')
        self.assertEqual(f.candidate_guard.depth,0)

    def test_candidates_refresh_before_visibility_and_confirmed_pruning_is_persisted(self):
        f=self.a
        for key,row in {'hidden':{'id':'hidden','owner_user_id':'account_b','jobs':[{'status':'running'}]},
                        'confirmed':{'id':'confirmed','confirmed_accessory_id':'alias'}}.items():
            (f.root/(key+'.json')).write_text(json.dumps(row));f.persistence.add_pipeline_pending_candidate_id(key)
        result=f.owner.pipeline_accessories_payload(f.config,{'id':'account_a'})
        self.assertEqual(result['pending_candidates'],[])
        self.assertEqual(result['accessories'][0]['id'],'a')
        self.assertEqual(f.owner.load_pipeline_state(),{'accessory_ids':['a'],'pending_candidate_ids':['hidden']})
        self.assertEqual(json.loads((f.root/'hidden.json').read_text())['jobs'][0]['status'],'completed')

    def test_optimization_live_state_writes_under_guard_supplied_state_does_not(self):
        f=self.a;result=f.owner.public_auto_optimize_link_for_task_id('same',source='direct')
        self.assertEqual(result['completed_model_id'],'model_account_a')
        self.assertEqual(f.events,[('stop','account_a','model_account_a'),('optimization_save','account_a')])
        self.assertEqual(f.optimize_guard.depth,0);f.events.clear()
        supplied=dict(f.state);f.owner.public_auto_optimize_link_for_task_id('same',source='cached',state=supplied)
        self.assertEqual(f.events,[])
        error=RuntimeError('state save')
        def fail(row):self.assertEqual(f.optimize_guard.depth,1);raise error
        f.b['save_auto_optimize_state']=fail
        with self.assertRaises(RuntimeError) as caught:f.owner.public_auto_optimize_link_for_task_id('same',source='direct')
        self.assertIs(caught.exception,error);self.assertEqual(f.optimize_guard.depth,0)
        self.assertEqual(f.state['capture_stop_reason'],'completed_model_ready')

    def test_preloaded_resources_and_links_skip_storage_except_required_label_snapshot(self):
        f=self.a
        def poison(*args):raise AssertionError('unneeded load')
        for key in ('list_trained_specs','list_auto_optimize_states','load_auto_optimize_state'):
            f.b[key]=poison
        loads=[]
        f.b['load_ai_tasks']=lambda:loads.append('snapshot') or [{'id':'same','accessory_labels':{'a':'historical'}}]
        task={'ai_task_id':'same','detection_method':'ai','accessory_ids':['a']}
        result=f.owner.pipeline_task_public(task,f.config,ai_task_ids={'same'},trained_model_specs=[],
            auto_optimize_states=[f.state],auto_optimize_states_by_id={'same':f.state},sanitize=False)
        self.assertEqual(result['model_status'],'available');self.assertEqual(f.events,[])
        self.assertEqual(loads,['snapshot']);self.assertEqual(result['accessory_labels']['a'],'historical')

    def test_owned_callbacks_select_component_after_effectful_arguments(self):
        a,b=self.a.owner,self.b.owner
        self.b.b['PIPELINE_DETECTION_METHODS']={'ai','yolo_ocr'}
        self.assertEqual(a.normalize_pipeline_detection_method('yolo'),'yolo')
        self.assertEqual(b.normalize_pipeline_detection_method('yolo'),'yolo_ocr')
        saved=a.metadata.policy.normalize_pipeline_detection_method()
        saved_label=a.metadata.snapshots.pipeline_task_label_snapshot()
        self.assertIs(saved_label.__self__,a)
        def switch():a.metadata=b.metadata;return 'yolo'
        self.assertEqual(saved(switch()),'yolo_ocr')
        def switch_snapshot():a.snapshots=b.snapshots;return {'ai_task_id':'same'}
        self.assertEqual(saved_label(switch_snapshot()),{'a':'account_b'})

    def test_resource_files_captured_but_candidate_files_selected_per_operation(self):
        f=self.a
        path=f.root/'same.json';path.write_text(json.dumps({'id':'same','jobs':[]}))
        self.assertTrue(f.files.exists(path))
        self.assertEqual(f.owner.refresh_pipeline_candidate('same'),({'id':'same','jobs':[]},False))
        visits=[]
        class MissingFiles:
            def exists(self,path):visits.append(path);return False
            def read_text(self,*args,**kwargs):raise AssertionError('read missing candidate')
        f.b['_business_files']=MissingFiles()
        f.b['refresh_codex_image_job']=lambda job:(_ for _ in ()).throw(AssertionError('refresh missing candidate'))
        f.b['save_accessory_candidate']=lambda *args:(_ for _ in ()).throw(AssertionError('save missing candidate'))
        self.assertEqual(f.owner.refresh_pipeline_candidate('same'),(None,True))
        self.assertEqual(visits,[path]);self.assertEqual(f.events,[])
        self.assertIs(f.owner.resources.files,f.files)
        self.assertEqual(f.owner.pipeline_task_dataset_status({'dataset_id':'same'}),'available')

    def test_source_inverse_rejects_wrong_owned_targets(self):
        from application_integration_source_contract import ROOT,PIPELINE_RUNTIME,PIPELINE_TASKS,PIPELINE_STAGES,AGENT_PIPELINE,PIPELINE_QUERIES,digest,restore_delta,restore_plc_domain_root
        source=(ROOT/'local_inspection_service/server.py').read_text();source=restore_delta(source,PIPELINE_RUNTIME)
        self.assertEqual(digest(ast.parse(restore_delta(restore_delta(restore_delta(restore_delta(source,PIPELINE_TASKS),PIPELINE_STAGES),AGENT_PIPELINE),PIPELINE_QUERIES))),PIPELINE_QUERIES['parent_ast_sha256'])
        restore_plc_domain_root(source)
        with self.assertRaises(AssertionError):
            restore_plc_domain_root(source.replace('_pipeline_candidate_flow = _pipeline_queries.candidates',
                '_pipeline_candidate_flow = _pipeline_queries.metadata'))

if POSTGRES:
    class QueryPostgresContracts(unittest.TestCase):
        def test_two_schema_candidate_refresh_state_and_connection_lifetime(self):
            import os
            import uuid
            import psycopg
            from psycopg import sql
            from local_inspection_service.runtime.connections import ThreadRepositoryFactory
            from local_inspection_service.storage.postgres_schema import postgres_ddl
            from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
            from local_inspection_service.storage.runtime_records import accessory_candidate_row
            dsn=os.environ['VANTALINE_POSTGRES_DSN'];connections=[];factories=[]
            schemas=['query_owned_'+uuid.uuid4().hex for _ in range(2)]
            with tempfile.TemporaryDirectory(prefix='query-pg-') as directory, psycopg.connect(dsn,autocommit=True) as control:
                try:
                    for index,schema in enumerate(schemas):
                        control.execute(postgres_ddl(schema));f=build(Path(directory)/str(index),str(index))
                        def create(schema=schema):
                            connection=psycopg.connect(dsn);connections.append(connection)
                            return SimpleNamespace(repository=PostgresRuntimeRepository(connection,'synthetic',schema))
                        factory=ThreadRepositoryFactory(create,lambda schema=schema:schema);factories.append(factory)
                        get=lambda factory=factory:factory.selection().repository
                        f.persistence.tasks.repository=get;f.persistence.state.repository=get
                        f.b['runtime_postgres_repository_or_none']=get
                        f.b['load_accessory_candidate']=lambda key,get=get:get().fetch_one_by_columns('accessory_candidates',{'id':key})['raw_json']
                        def save(path,row,f=f,get=get):
                            self.assertEqual(f.candidate_guard.depth,1)
                            get().upsert_row('accessory_candidates',accessory_candidate_row(row))
                        f.b['save_accessory_candidate']=save
                        with factory.thread_scope():
                            get().upsert_row('accessory_candidates',accessory_candidate_row(
                                {'id':'same','owner_user_id':str(index),'jobs':[{'status':'running'}]}))
                            f.persistence.add_pipeline_pending_candidate_id('same')
                            result=f.owner.pipeline_accessories_payload(f.config,{'id':str(index)})
                            self.assertEqual(result['pending_candidates'][0]['owner_user_id'],str(index))
                            self.assertEqual(get().fetch_one_by_columns('accessory_candidates',{'id':'same'})['raw_json']['jobs'][0]['status'],'completed')
                            row={'id':'confirmed','confirmed_accessory_id':'a','owner_user_id':str(index)}
                            get().upsert_row('accessory_candidates',accessory_candidate_row(row))
                            f.persistence.add_pipeline_pending_candidate_id('confirmed')
                            f.owner.pipeline_accessories_payload(f.config,{'id':str(index)})
                            self.assertEqual(f.owner.load_pipeline_state(),{'accessory_ids':['a'],'pending_candidate_ids':['same']})
                            before=get().fetch_all('pipeline_state')
                            def fail(state):state['accessory_ids']=['bad'];raise ValueError('state failure')
                            with self.assertRaisesRegex(ValueError,'state failure'):f.owner.update_pipeline_state(fail)
                            self.assertEqual(get().fetch_all('pipeline_state'),before)
                        self.assertEqual(f.candidate_guard.depth,0)
                    self.assertTrue(connections);self.assertTrue(all(c.closed for c in connections))
                finally:
                    for factory in factories:factory.clear()
                    for schema in schemas:control.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

if __name__=='__main__':unittest.main(verbosity=2)
