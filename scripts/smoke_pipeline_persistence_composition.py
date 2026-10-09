"""Actual pipeline persistence graph; synthetic models and isolated storage only."""
import ast
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
POSTGRES = '--postgres' in sys.argv
if POSTGRES: sys.argv.remove('--postgres')
from smoke_pipeline_stores import Fixture, available
from local_inspection_service.pipeline.persistence_composition import PipelinePersistence
from local_inspection_service.pipeline.task_store import PipelineTaskPaths, PipelineTaskRows
from local_inspection_service.pipeline.state_store import PipelineStatePaths, PipelineStateRows
from local_inspection_service.pipeline.training_sync import PipelineTrainingModels
from local_inspection_service.storage.runtime_records import pipeline_task_row, row_raw_json_list, pipeline_state_rows, pipeline_state_from_rows

def build(f, *, repository=None, link=None, candidate=None):
    owner=PipelinePersistence(repository=repository or f.repository,
        task_paths=PipelineTaskPaths(lambda:f.data,lambda:f.tasks),
        task_rows=PipelineTaskRows(pipeline_task_row,lambda:row_raw_json_list), resolver=lambda:f.provider,
        state_paths=PipelineStatePaths(lambda:f.data,lambda:f.state),
        state_rows=PipelineStateRows(lambda:pipeline_state_rows,lambda:pipeline_state_from_rows),
        training_models=PipelineTrainingModels(resolve=lambda task,job:'model_'+job,link=link or (lambda task: None)),
        normalize_method=lambda:lambda value:value or 'yolo',clean_id=lambda:lambda value:str(value),
        sync_candidate=candidate or (lambda task,**kwargs:None))
    f.guard=owner.runtime.state_lock
    return owner

class PipelineCompositionContracts(unittest.TestCase):
    def test_constructor_does_no_dependency_selection_and_guards_are_owned(self):
        def poison(*args,**kwargs): raise AssertionError('eager selection')
        def graph():
            return PipelinePersistence(repository=poison,
                task_paths=PipelineTaskPaths(poison,poison),task_rows=PipelineTaskRows(poison,poison),resolver=poison,
                state_paths=PipelineStatePaths(poison,poison),state_rows=PipelineStateRows(poison,poison),
                training_models=PipelineTrainingModels(poison,poison),normalize_method=poison,clean_id=poison,sync_candidate=poison)
        a,b=graph(),graph()
        self.assertIs(a.state.guard(),a.runtime.state_lock)
        self.assertIs(a.training.guard(),a.runtime.task_lock)
        self.assertIsNot(a.runtime.task_lock,b.runtime.task_lock)
        self.assertIsNot(a.runtime.state_lock,b.runtime.state_lock)
        self.assertEqual(a.runtime.advance_inflight,set());self.assertEqual(b.runtime.advance_inflight,set())

    def test_two_retained_graphs_keep_records_snapshots_state_and_late_paths(self):
        with tempfile.TemporaryDirectory(prefix='pipeline-owned-') as directory:
            owners=[]
            for label in ('a','b'):
                root=Path(directory)/label;root.mkdir();f=Fixture(root);owner=build(f);owners.append((owner,f))
                owner.save_pipeline_task({'id':'same','owner_user_id':label,'detection_method':'yolo'})
                owner.add_pipeline_accessory_id(label)
            for owner,f in owners:
                f.resolver.version=9
                row=owner.load_pipeline_task('same')
                self.assertEqual(row['owner_user_id'],f.root.name)
                self.assertEqual(row['model_profiles']['pipeline']['version'],1)
                self.assertEqual(owner.load_pipeline_state()['accessory_ids'],[f.root.name])
            owner,f=owners[0];f.state=f.root/'late.json';owner.add_pipeline_pending_candidate_id('late')
            self.assertTrue(f.state.exists());self.assertEqual(owners[1][0].load_pipeline_state()['pending_candidate_ids'],[])

    def test_training_completion_uses_owned_guard_records_and_candidate_after_unlock(self):
        with tempfile.TemporaryDirectory(prefix='pipeline-training-owned-') as directory:
            f=Fixture(directory);events=[];owner=None
            def link(task):
                events.append(('link',available(owner.runtime.task_lock)))
            def candidate(task,**kwargs):
                events.append(('candidate',available(owner.runtime.task_lock),kwargs))
            owner=build(f,link=link,candidate=candidate)
            owner.save_pipeline_task({'id':'same','detection_method':'yolo','ai_task_id':'ai'})
            owner.sync_pipeline_training_state_from_task({'job_id':'job','pipeline_task_id':'same','status':'completed'})
            row=owner.load_pipeline_task('same')
            self.assertEqual((row['stage'],row['status'],row['ai_model_id']),('library','completed','model_job'))
            self.assertEqual(events,[('link',False),('candidate',True,{'ai_task_id':'ai','model_id':'model_job'})])
            self.assertTrue(available(owner.runtime.task_lock))

    def test_model_or_link_failure_keeps_records_and_guard_released(self):
        with tempfile.TemporaryDirectory(prefix='pipeline-rollback-owned-') as directory:
            f=Fixture(directory);calls=[]
            def fail(task): raise ValueError('model link')
            owner=build(f,link=fail,candidate=lambda *args,**kwargs:calls.append(True))
            owner.save_pipeline_task({'id':'same','detection_method':'yolo'})
            before=f.tasks.read_bytes()
            with self.assertRaisesRegex(ValueError,'model link'):
                owner.sync_pipeline_training_state_from_task({'job_id':'job','pipeline_task_id':'same','status':'completed'})
            self.assertEqual(f.tasks.read_bytes(),before);self.assertEqual(calls,[])
            self.assertTrue(available(owner.runtime.task_lock))
            owner.tasks.resolver=lambda: lambda:None
            with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'):
                owner.save_pipeline_task({'id':'missing-model'})
            self.assertEqual(f.tasks.read_bytes(),before)

    def test_saved_training_record_callback_selects_owner_after_arguments(self):
        with tempfile.TemporaryDirectory(prefix='pipeline-selection-owned-') as directory:
            root=Path(directory);(root/'a').mkdir();(root/'b').mkdir()
            a,b=build(Fixture(root/'a')),build(Fixture(root/'b'))
            a.save_pipeline_task({'id':'same','label':'a'});b.save_pipeline_task({'id':'same','label':'b'})
            saved=a.training.records.load
            def switch(): a.tasks=b.tasks;return 'same'
            self.assertEqual(saved(switch())['label'],'b')

    def test_partial_constructor_and_model_failure_publish_nothing(self):
        import local_inspection_service.pipeline.persistence_composition as module
        with tempfile.TemporaryDirectory(prefix='pipeline-partial-owned-') as directory:
            f=Fixture(directory);published=build(f);original=published
            with patch.object(module,'PipelineStateStore',side_effect=ValueError('state constructor')):
                with self.assertRaisesRegex(ValueError,'state constructor'):published=build(f)
            self.assertIs(published,original);self.assertFalse(f.data.exists())
            trace=[]
            published.tasks.resolver=lambda: lambda:None
            published.tasks.rows=PipelineTaskRows(lambda task:trace.append('encode'),lambda:row_raw_json_list)
            published.tasks.repository=lambda:trace.append('repository')
            with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'):
                published.save_pipeline_task({'id':'same'})
            self.assertEqual(trace,[]);self.assertFalse(f.data.exists())

    def test_root_inverse_and_actual_owner_reject_wrong_bindings(self):
        from application_integration_source_contract import ROOT,AGENT_PIPELINE,PIPELINE_QUERIES,PIPELINE_EXECUTION,PIPELINE_PERSISTENCE,digest,restore_delta,restore_plc_domain_root
        source=(ROOT/'local_inspection_service/server.py').read_text()
        self.assertEqual(digest(ast.parse(restore_delta(restore_delta(restore_delta(restore_delta(source,AGENT_PIPELINE),PIPELINE_QUERIES),PIPELINE_EXECUTION),PIPELINE_PERSISTENCE))),PIPELINE_PERSISTENCE['parent_ast_sha256'])
        restore_plc_domain_root(source)
        for old,new in [('_pipeline_runtime = _pipeline_persistence.runtime','_pipeline_runtime = None'),
            ('_pipeline_training_sync = _pipeline_persistence.training','_pipeline_training_sync = _pipeline_persistence.state')]:
            with self.assertRaises(AssertionError):restore_plc_domain_root(source.replace(old,new))

if POSTGRES:
    class PipelinePersistencePostgresContracts(unittest.TestCase):
        def test_real_two_schema_task_snapshots_state_concurrency_and_connections(self):
            import os
            import uuid
            from types import SimpleNamespace
            from concurrent.futures import ThreadPoolExecutor
            import psycopg
            from psycopg import sql
            from local_inspection_service.runtime.connections import ThreadRepositoryFactory
            from local_inspection_service.storage.postgres_schema import postgres_ddl
            from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
            dsn=os.environ['VANTALINE_POSTGRES_DSN']
            schemas=['pipeline_owned_'+uuid.uuid4().hex for _ in range(2)]
            factories,connections,graphs=[],[],[]
            with tempfile.TemporaryDirectory(prefix='pipeline-pg-owned-') as directory, psycopg.connect(dsn,autocommit=True) as control:
                try:
                    for index,schema in enumerate(schemas):
                        control.execute(postgres_ddl(schema))
                        def create(schema=schema):
                            connection=psycopg.connect(dsn);connections.append(connection)
                            return SimpleNamespace(repository=PostgresRuntimeRepository(connection,'synthetic',schema))
                        factory=ThreadRepositoryFactory(create,lambda schema=schema:schema);factories.append(factory)
                        f=Fixture(Path(directory)/str(index))
                        owner=build(f,repository=lambda factory=factory:factory.selection().repository)
                        graphs.append((owner,f))
                        with factory.thread_scope():
                            owner.save_pipeline_task({'id':'same','owner_user_id':str(index),'detection_method':'yolo'})
                    def mutate(pair):
                        index,item=pair;owner,_=graphs[index]
                        with factories[index].thread_scope():owner.add_pipeline_accessory_id(str(item))
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        list(pool.map(mutate,[(index,item) for index in (0,1) for item in range(4)]))
                    for index,(owner,f) in enumerate(graphs):
                        f.resolver.version=9
                        with factories[index].thread_scope():
                            owner.sync_pipeline_training_state_from_task({'job_id':'job','pipeline_task_id':'same','status':'completed'})
                            row=owner.load_pipeline_task('same')
                            self.assertEqual((row['owner_user_id'],row['status'],row['model_profiles']['pipeline']['version']),
                                (str(index),'completed',1))
                            self.assertEqual(set(owner.load_pipeline_state()['accessory_ids']),{'0','1','2','3'})
                            repository=factories[index].selection().repository
                            before=repository.fetch_all('pipeline_state')
                            with self.assertRaisesRegex(ValueError,'update failure'):
                                def fail(state):state['accessory_ids']=['bad'];raise ValueError('update failure')
                                owner.update_pipeline_state(fail)
                            self.assertEqual(repository.fetch_all('pipeline_state'),before)
                    self.assertTrue(connections);self.assertTrue(all(c.closed for c in connections))
                finally:
                    for factory in factories:factory.clear()
                    for schema in schemas:control.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

if __name__=='__main__': unittest.main(verbosity=2)
