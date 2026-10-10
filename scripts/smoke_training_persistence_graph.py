"""Actual completion graph contracts using synthetic files and models only."""
import copy
from contextlib import nullcontext
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
from smoke_pipeline_stores import Fixture, available
from local_inspection_service.training.persistence_graph import (
    TrainingPersistenceGraph, TrainingAccountInputs, PipelinePersistenceInputs,
    TrainingCandidateInputs)
from local_inspection_service.runtime.training_tasks import TrainingTaskRuntime
from local_inspection_service.training.state_composition import TrainingRecordAccess
from local_inspection_service.training.record_store import TrainingRows
from local_inspection_service.training.task_lifecycle import TrainingTaskWrites
from local_inspection_service.training.task_views import TrainingViewAccess
from local_inspection_service.training.user_state import TrainingStateAccess
from local_inspection_service.training.account_state_composition import TrainingConfiguration
from local_inspection_service.pipeline.task_store import PipelineTaskPaths, PipelineTaskRows
from local_inspection_service.pipeline.state_store import PipelineStatePaths, PipelineStateRows
from local_inspection_service.detection.training_candidate_sync import CandidateTrainingRecords
from local_inspection_service.storage.runtime_records import (
    pipeline_task_row, row_raw_json_list, pipeline_state_rows, pipeline_state_from_rows,
    training_task_row)


class FixtureGraph:
    def __init__(self, root, marker):
        self.fixture = f = Fixture(root)
        self.marker = marker
        self.events = []
        self.configuration = {}
        self.candidate = {'id': 'same'}
        self.specs = [{'run_id': 'job', 'id': marker}]
        self.auto_guard = threading.RLock()
        self.fail = None
        self.directory = Path(root)/'training'
        self.directory.mkdir()
        self.inputs = dict(
            account=TrainingAccountInputs(
                runtime=TrainingTaskRuntime(),
                storage=TrainingRecordAccess(f.repository, lambda:self.directory,
                    lambda:f.provider, lambda key:None, lambda value,*args:value),
                rows=TrainingRows(lambda:training_task_row, lambda:row_raw_json_list, lambda path:path.stem),
                writes=TrainingTaskWrites(f.repository, training_task_row, lambda key:None),
                require_access=lambda record,user,write=False:None,
                view_access=TrainingViewAccess(lambda value:value, lambda:lambda value:value,
                    lambda record,user,target:True),
                defaults=lambda:{}, legacy_owner=lambda:'legacy',
                access=TrainingStateAccess(lambda value:(value or {}).get('owner_user_id',''),
                    lambda record,user,target=None:True, lambda user:False, lambda:{}),
                configuration=TrainingConfiguration(lambda:copy.deepcopy(self.configuration), self.save_config)),
            pipeline=PipelinePersistenceInputs(f.repository,
                PipelineTaskPaths(lambda:f.data, lambda:f.tasks),
                PipelineTaskRows(pipeline_task_row, lambda:row_raw_json_list), lambda:f.provider,
                PipelineStatePaths(lambda:f.data, lambda:f.state),
                PipelineStateRows(lambda:pipeline_state_rows, lambda:pipeline_state_from_rows),
                self.link, lambda:lambda value:value or 'yolo', lambda:lambda value:str(value)),
            candidate=TrainingCandidateInputs(lambda:self.auto_guard,
                CandidateTrainingRecords(lambda task_id:copy.deepcopy(self.candidate), self.save_candidate),
                lambda value:str(value), self.stop_capture),
            model_specs=lambda:self.specs)
        self.graph = TrainingPersistenceGraph(**self.inputs)
        f.guard = self.graph.pipeline.runtime.state_lock

    def save_config(self, value):
        self.events.append('config')
        if self.fail == 'config': raise ValueError('config failure')
        self.configuration = copy.deepcopy(value)

    def link(self, task):
        self.events.append(('link', available(self.graph.pipeline.runtime.task_lock)))

    def stop_capture(self, state, model_id, *, reason):
        self.events.append(('stop', model_id, available(self.graph.pipeline.runtime.task_lock),
            available(self.auto_guard)))
        if self.fail == 'stop': raise ValueError('stop failure')
        return True

    def save_candidate(self, value):
        self.events.append('candidate')
        self.candidate = copy.deepcopy(value)
        return value

    def seed(self):
        self.graph.pipeline.save_pipeline_task({'id':'same', 'ai_task_id':'same', 'detection_method':'yolo'})
        self.graph.account.records.save_training_task({'job_id':'job', 'action':'train_model',
            'owner_user_id':self.marker, 'pipeline_task_id':'same', 'status':'completed'})


class TrainingPersistenceContracts(unittest.TestCase):
    def test_actual_default_graph_and_fixed_parent_inverse(self):
        import ast
        import application_integration_source_contract as contract
        source=read_checked_application_source(contract.ROOT / 'local_inspection_service/server.py')
        self.assertEqual(contract.digest(ast.parse(contract.restore_account_visibility_root(source))),
            contract.TRAINING_PERSISTENCE_GRAPH['integrated_ast_sha256'])
        inverse=contract.restore_training_persistence_graph_root(source)
        self.assertEqual(contract.digest(ast.parse(inverse)),
            contract.TRAINING_PERSISTENCE_GRAPH['parent_ast_sha256'])
        from verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        graph=server._training_persistence_graph
        for alias,owner in (('_training_account_state',graph.account),
            ('_training_task_models',graph.models),('_pipeline_persistence',graph.pipeline),
            ('_training_candidate_sync',graph.candidates)):
            self.assertIs(getattr(server,alias),owner)
        for edge in (graph.account.users.sync_pipeline, graph.pipeline.training.models.resolve,
            graph.pipeline.training.sync_candidate):
            self.assertIs(edge.__self__,graph)

    def fixture(self, marker):
        temporary = tempfile.TemporaryDirectory(prefix='training-completion-')
        self.addCleanup(temporary.cleanup)
        return FixtureGraph(temporary.name, marker)

    def test_constructor_is_inert_and_owners_are_distinct(self):
        f = self.fixture('inert')
        def poison(*args, **kwargs): raise AssertionError('eager dependency selection')
        inputs = dict(f.inputs)
        def poisoned(value):
            if is_dataclass(value):
                return type(value)(**{field.name:poisoned(getattr(value,field.name))
                    for field in fields(value)})
            return poison if callable(value) else value
        for key in ('account','pipeline','candidate'):
            inputs[key] = poisoned(inputs[key])
        inputs['account'] = replace(inputs['account'], runtime=TrainingTaskRuntime(scope=poison))
        inputs['model_specs'] = poison
        a,b = TrainingPersistenceGraph(**inputs), TrainingPersistenceGraph(**inputs)
        self.assertIsNot(a.account,b.account)
        self.assertIsNot(a.pipeline.runtime,b.pipeline.runtime)
        self.assertIsNot(a.models,b.models)
        self.assertIsNot(a.candidates,b.candidates)
        import local_inspection_service.training.persistence_graph as module
        with patch.object(module,'TrainingAccountState',side_effect=ValueError('late constructor')):
            with self.assertRaisesRegex(ValueError,'late constructor'):
                TrainingPersistenceGraph(**inputs)
        self.assertEqual(f.configuration,{})
        self.assertEqual(f.events,[])

    def test_same_identifiers_complete_through_own_config_pipeline_and_candidates(self):
        a,b = self.fixture('a'), self.fixture('b')
        for f in (a,b): f.seed()
        a.graph.account.sync_training_state_from_task('job')
        self.assertEqual(b.configuration,{})
        self.assertNotIn('candidate_models',b.candidate)
        self.assertNotEqual(b.graph.pipeline.load_pipeline_task('same').get('status'),'completed')
        b.specs = [{'run_id':'job','id':'late-b'}]
        b.graph.account.sync_training_state_from_task('job')
        for f,model in ((a,'a'),(b,'late-b')):
            self.assertEqual(f.configuration['training_by_user_id'][f.marker]['status'],'completed')
            self.assertEqual(f.graph.pipeline.load_pipeline_task('same')['ai_model_id'],model)
            self.assertEqual(f.candidate['candidate_models'][0]['model_id'],model)
            self.assertEqual(f.events,['config',('link',False),('stop',model,True,False),'candidate'])

    def test_failure_preserves_existing_partial_commit_boundaries_and_releases_locks(self):
        for failure in ('config','pipeline','stop'):
            with self.subTest(failure=failure):
                f=self.fixture(failure);f.seed();f.fail=failure
                before=f.fixture.tasks.read_bytes()
                with patch.object(f.graph.pipeline,'save_pipeline_task',
                    side_effect=ValueError('pipeline failure')) if failure=='pipeline' else nullcontext():
                    with self.assertRaisesRegex(ValueError,failure+' failure'):
                        f.graph.account.sync_training_state_from_task('job')
                self.assertEqual(f.events.count('config'),1)
                self.assertNotIn('candidate',f.events)
                self.assertNotIn('candidate_models',f.candidate)
                self.assertEqual(bool(f.configuration),failure!='config')
                self.assertEqual(f.fixture.tasks.read_bytes()==before,failure!='stop')
                self.assertTrue(available(f.graph.pipeline.runtime.task_lock))
                self.assertTrue(available(f.auto_guard))

    def test_saved_internal_edges_select_graph_owner_after_arguments(self):
        a,b=self.fixture('a'),self.fixture('b')
        resolve=a.graph.pipeline.training.models.resolve
        def switch(): a.graph.models=b.graph.models;return {'job_id':'job'}
        self.assertEqual(resolve(switch(),'job'),'b')
        candidate=a.graph.pipeline.training.sync_candidate
        b.seed()
        def switch_candidate(): a.graph.candidates=b.graph.candidates;return {'job_id':'job','status':'completed'}
        candidate(switch_candidate(),ai_task_id='same',model_id='b')
        self.assertNotIn('candidate_models',a.candidate)
        self.assertEqual(b.candidate['candidate_models'][0]['model_id'],'b')
        sync=a.graph.account.users.sync_pipeline
        def switch_pipeline():
            a.graph.pipeline=b.graph.pipeline
            return {'job_id':'job','pipeline_task_id':'same','status':'completed'}
        sync(switch_pipeline())
        self.assertEqual(b.graph.pipeline.load_pipeline_task('same')['ai_model_id'],'b')


if __name__=='__main__': unittest.main()
