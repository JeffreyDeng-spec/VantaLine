"""Cost owner wiring and inherited pricing/aggregation/permission contracts."""
from contextlib import ExitStack
import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from scripts import smoke_cost_ledger as original
from local_inspection_service.analytics.cost_composition import CostServices
from local_inspection_service.analytics.cost_repository import CostPaths, CostStoreDependencies
from local_inspection_service.pipeline.task_store import PipelineTaskStore, PipelineTaskPaths, PipelineTaskRows


class ComposedCosts(original.CostTests):
    def setUp(self):
        super().setUp()
        self.graph=CostServices(self.repository.dependencies,self.ledger.timestamp)
        self.repository,self.ledger=self.graph.repository,self.graph.ledger
        # Original tests that explicitly supply a separate CostSource/fake Ledger
        # remain direct business/HTTP contracts, not claimed as composer coverage.


class Composition(unittest.TestCase):
    def test_inert_distinct_owners_and_original_pipeline_constructor(self):
        fail=Mock(side_effect=AssertionError('eager capability call'))
        storage=CostStoreDependencies(fail,fail,fail,fail,fail,fail,fail)
        a,b=CostServices(storage,fail),CostServices(storage,fail)
        self.assertIsNot(a.repository,b.repository)
        self.assertIsNot(a.ledger,b.ledger)
        self.assertIs(a.ledger.repository,a.repository)
        self.assertIs(b.ledger.repository,b.repository)
        PipelineTaskStore(fail,PipelineTaskPaths(fail,fail),PipelineTaskRows(fail,fail),fail)
        fail.assert_not_called()

    def test_actual_entry_binding_permissions_and_explicit_injection(self):
        from scripts import verify_backend_contract as contract
        self.assertEqual(contract.encoded(contract.capture()),contract.BASELINE.read_text(encoding='utf8'))
        from local_inspection_service import server
        graph=server._cost_services
        storage=graph.repository.dependencies
        bindings={
            'runtime_repository':server._runtime_repository_access.runtime_postgres_repository_or_none,
            'detection_tasks':server._detection_task_store.load_ai_detection_tasks,
            'pipeline_tasks':server._pipeline_task_store.load_pipeline_tasks,
            'auto_states':server._auto_optimization_state_store.list_auto_optimize_states,
            'training_tasks':server._training_records.load_training_task_records,
            'sanitize_task_id':server.sanitize_ai_detection_task_id,
        }
        for name,expected in bindings.items():self.assertEqual(getattr(storage,name),expected)
        self.assertEqual(graph.ledger.timestamp,server.coerce_record_timestamp)
        paths=storage.paths()
        self.assertEqual(paths,CostPaths(server.DATA_DIR,server.DATA_ANALYSIS_RECORDS_PATH,
            server.AI_DETECTION_TASKS_PATH,server.PIPELINE_TASKS_PATH,server.AUTO_OPTIMIZE_DIR,server.AI_PROFILE_CACHE_PATH))
        self.assertEqual(inspect.getclosurevars(server.get_api_cost_ledger).nonlocals['require_admin'],
                         server._access_control.require_admin_role)
        for name,method in {'api_cost_walk_usage':graph.ledger.walk_usage,
            'api_cost_store_payloads':graph.repository.store_payloads,'api_cost_training_records':graph.ledger.training_records,
            'api_cost_collect_records':graph.ledger.collect_records,'api_cost_summary':graph.ledger.summary}.items():
            self.assertEqual(getattr(server,name),method)
        poison=Mock(side_effect=AssertionError('entry alias/cost source accessed'))
        identity=server._authentication_domain.identity
        with ExitStack() as stack:
            for name in ('require_admin_role','runtime_postgres_repository_or_none','load_ai_detection_tasks',
                         'load_pipeline_tasks','list_auto_optimize_states','load_training_task_records',
                         'sanitize_ai_detection_task_id','coerce_record_timestamp','DATA_DIR',
                         'DATA_ANALYSIS_RECORDS_PATH','AI_DETECTION_TASKS_PATH','PIPELINE_TASKS_PATH',
                         'AUTO_OPTIMIZE_DIR','AI_PROFILE_CACHE_PATH'):
                stack.enter_context(patch.object(server,name,poison))
            self.assertIs(storage.paths(),paths)
            for name,expected in bindings.items():self.assertEqual(getattr(storage,name),expected)
            with patch.object(graph.repository,'dependencies',CostStoreDependencies(*([poison]*7))):
                for user,status in (({},401),({'id':'member','role':'user'},403)):
                    with identity.bind(user),self.assertRaises(HTTPException) as caught:server.get_api_cost_ledger()
                    self.assertEqual(caught.exception.status_code,status)
                poison.assert_not_called()
            with tempfile.TemporaryDirectory(prefix='cost-composed-') as directory:
                root=Path(directory);events=[]
                def observed(name,value):
                    def read():events.append(name);return value
                    return read
                injected=CostStoreDependencies(lambda:CostPaths(root,root/'analysis',root/'detection',
                    root/'pipeline',root/'auto',root/'cache'),observed('repository',None),
                    observed('detection',[]),observed('pipeline',[]),observed('auto',[]),
                    observed('training',[]),lambda value:value)
                with patch.object(graph.repository,'dependencies',injected),identity.bind({'id':'admin','role':'admin'}):
                    first=server.get_api_cost_ledger();second=server.get_api_cost_ledger()
                self.assertEqual(first['summary']['total_cost_usd'],0)
                self.assertEqual(second['summary']['total_cost_usd'],0)
                self.assertEqual(events.count('repository'),2)
                self.assertEqual(events.count('training'),2)
                self.assertGreaterEqual(events.count('auto'),4)
            poison.assert_not_called()


if __name__=='__main__':unittest.main()
