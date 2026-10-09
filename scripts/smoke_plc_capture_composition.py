"""Exercise the actual retained capture graph with atomic synthetic storage."""
import ast
from dataclasses import fields
from pathlib import Path
import sys
import unittest
POSTGRES = "--postgres" in sys.argv
if POSTGRES: sys.argv.remove("--postgres")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smoke_plc_capture_state as baseline
from local_inspection_service.plc.capture_composition import PlcCaptureWorkflows, CaptureStorage, CapturePolicy
from local_inspection_service.plc.legacy_coordination import LegacyCoordinationPolicy
from application_integration_source_contract import restore_plc_domain_root, digest, PLC_CAPTURE

def build(b, process_id='owner', repository=None):
    storage = CaptureStorage(repository=lambda: repository or (lambda: None),
        load_config=lambda: b['load_config'],
        mutate_config=lambda: b['mutate_app_config_atomically'],
        start_heartbeat=lambda: lambda _: (_ for _ in ()).throw(AssertionError('worker started')))
    policy = CapturePolicy(**{f.name: lambda name=f.name: b[name] for f in fields(CapturePolicy)})
    coordination = LegacyCoordinationPolicy(runtime_key=lambda: b['PLC_RUNTIME_COORDINATION_KEY'],
        receipts_key=lambda: b['PLC_CAPTURE_RESULTS_KEY'], process_id=lambda: process_id,
        lease_seconds=lambda: 5., quarantine_seconds=lambda: 17., clock=lambda: lambda: 100.)
    return PlcCaptureWorkflows(storage=storage, coordination_policy=coordination, capture_policy=policy)

class ActualCaptureContract(baseline.CaptureContract):
    def fixture(self):
        _, b, config = super().fixture()
        return build(b), b, config

    def test_constructor_is_inert_and_actual_internal_edges(self):
        def poison(): raise AssertionError('eager dependency selection')
        owner = PlcCaptureWorkflows(
            storage=CaptureStorage(**{f.name: poison for f in fields(CaptureStorage)}),
            coordination_policy=LegacyCoordinationPolicy(**{f.name: poison for f in fields(LegacyCoordinationPolicy)}),
            capture_policy=CapturePolicy(**{f.name: poison for f in fields(CapturePolicy)}))
        pairs = [(owner.coordination.storage, 'mutate_rows', '_mutate_plc_runtime_rows'),
            (owner.coordination.storage, 'mutate_runtime', 'mutate_plc_runtime_coordination'),
            (owner.capture.transactions, 'mutate_plc_runtime_coordination', 'mutate_plc_runtime_coordination'),
            (owner.capture.transactions, 'plc_completed_capture_receipt', 'plc_completed_capture_receipt'),
            (owner.capture.policy, '_plc_capture_runtime', '_plc_capture_runtime'),
            (owner.capture.policy, '_plc_expire_capture_state', '_plc_expire_capture_state')]
        for group, field, method in pairs:
            callback = getattr(group, field)()
            expected_owner = owner.coordination if method in ('mutate_plc_runtime_coordination', 'plc_completed_capture_receipt', '_mutate_plc_runtime_rows') else owner
            self.assertIs(callback.__self__, expected_owner)
            self.assertIs(callback.__func__, getattr(owner, method).__func__)

    def test_two_graphs_receipts_owner_epochs_and_argument_order(self):
        a, _, ac = self.fixture(); b, _, bc = self.fixture()
        self.assertEqual(a.plc_claim_or_renew_io_owner()['epoch'], 1)
        self.assertTrue(a.plc_current_process_owns_io(1))
        self.assertFalse(b.plc_current_process_owns_io(1))
        self.assertEqual(b.plc_claim_or_renew_io_owner()['epoch'], 1)
        a.plc_capture_disarm('a'); b.plc_capture_disarm('b')
        self.assertEqual(ac['runtime']['capture']['disarmed_reason'], 'a')
        self.assertEqual(bc['runtime']['capture']['disarmed_reason'], 'b')
        ac['receipts']={'same': {'value':'a'}}; bc['receipts']={'same': {'value':'b'}}
        self.assertEqual(a.plc_completed_capture_receipt('same'), {'value':'a'})
        self.assertEqual(b.plc_completed_capture_receipt('same'), {'value':'b'})
        saved = a.capture.transactions.plc_completed_capture_receipt()
        def switch():
            a.coordination = b.coordination
            return 'same'
        original_coordination = a.coordination
        self.assertEqual(saved(switch()), {'value':'a'})
        self.assertIs(saved.__self__, original_coordination)
        self.assertIs(a.mutate_plc_runtime_coordination.__self__, original_coordination)
        self.assertIs(a._mutate_plc_runtime_rows.__self__, original_coordination)
        self.assertEqual(ac['receipts']['same'], {'value':'a'})

    def test_strict_root_inverse_and_no_capture_startup_enablement(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'local_inspection_service/server.py').read_text(encoding='utf-8-sig')
        restored=restore_plc_domain_root(source)
        self.assertNotEqual(digest(ast.parse(source)), digest(ast.parse(restored)))
        with self.assertRaises(AssertionError):
            restore_plc_domain_root(source.replace('_plc_capture_state = _legacy_capture_workflows.capture',
                '_plc_capture_state = _legacy_capture_workflows.coordination'))
        tree=ast.parse(source)
        hook=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='start_plc_runtime_workers')
        self.assertEqual(ast.dump(hook.body[0]), ast.dump(ast.Return(ast.Constant(None))))
        self.assertEqual(PLC_CAPTURE['unchanged_business_sha256'].keys(),
            {'local_inspection_service/plc/legacy_coordination.py', 'local_inspection_service/plc/plc_capture_state.py'})

if POSTGRES:
    class CapturePostgresContract(unittest.TestCase):
        def test_real_two_schema_concurrent_namespace_mutation_and_rollback(self):
            import os
            import uuid
            import json
            from types import SimpleNamespace
            from concurrent.futures import ThreadPoolExecutor
            import psycopg
            from psycopg import sql
            from local_inspection_service.runtime.connections import ThreadRepositoryFactory
            from local_inspection_service.storage.postgres_schema import postgres_ddl
            from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
            dsn=os.environ['VANTALINE_POSTGRES_DSN']
            schemas=['plc_capture_graph_'+uuid.uuid4().hex for _ in range(2)]
            factories, connections, owners=[],[],[]
            with psycopg.connect(dsn,autocommit=True) as control:
                try:
                    for index,schema in enumerate(schemas):
                        control.execute(postgres_ddl(schema))
                        def create(schema=schema):
                            connection=psycopg.connect(dsn);connections.append(connection)
                            return SimpleNamespace(repository=PostgresRuntimeRepository(connection,'synthetic',schema))
                        factory=ThreadRepositoryFactory(create,lambda schema=schema:schema);factories.append(factory)
                        _,b,_=baseline.CaptureContract().fixture()
                        owner=build(b, process_id=str(index),
                            repository=lambda factory=factory: factory.selection().repository)
                        # Both graphs retain their actual constructed coordination/capture instances.
                        owners.append(owner)
                    def mutation(index):
                        with factories[index].thread_scope():
                            def increment(state): state['counter']=state.get('counter',0)+1
                            owners[index].mutate_plc_runtime_coordination(increment)
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        list(pool.map(mutation,[0,1,0,1,0,1,0,1]))
                    for index,owner in enumerate(owners):
                        with factories[index].thread_scope():
                            repository=factories[index].selection().repository
                            before=repository.fetch_one_by_columns('app_config',{'config_key':'runtime'})
                            value=before['config_value_json']
                            if isinstance(value,str): value=json.loads(value)
                            self.assertEqual(value,{'counter':4})
                            def fail(state):
                                state['counter']=999
                                raise ValueError('atomic rollback')
                            with self.assertRaisesRegex(ValueError,'atomic rollback'):
                                owner.mutate_plc_runtime_coordination(fail)
                            self.assertEqual(repository.fetch_one_by_columns('app_config',{'config_key':'runtime'}),before)
                    self.assertTrue(connections)
                    self.assertTrue(all(connection.closed for connection in connections))
                finally:
                    for factory in factories: factory.clear()
                    for schema in schemas:
                        control.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

if __name__=='__main__':
    unittest.main(verbosity=2)
