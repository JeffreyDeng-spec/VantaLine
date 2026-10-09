"""Actual lease/diagnostic graphs using synthetic state and optional isolated PG."""
from dataclasses import fields
from pathlib import Path
import copy
import math
import re
import secrets
import sys
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
POSTGRES = '--postgres' in sys.argv
if POSTGRES: sys.argv.remove('--postgres')
from smoke_plc_workstation_composition import Rows, build, seed
from local_inspection_service.plc import lease_diagnostic_composition as module
from local_inspection_service import plc_web_serial as protocol
from local_inspection_service.plc_fx_ascii import PlcConfigError

def operations(workstation, rows, *, poison=None, events=None):
    def get(value): return poison or (lambda: value)
    current=workstation.station.identity.current_auth_user
    return module.PlcLeaseDiagnosticWorkflows(
        workstation=workstation,
        admission=module.LeaseAdmission(current_user=poison or current,
            release_version=get(lambda: {'consistent': True}), fullmatch=get(re.fullmatch),
            protocol_version=get(protocol.WEB_SERIAL_PROTOCOL_VERSION),
            require_model_permission=get(lambda model: events.append(model) if events is not None else None),
            migrate_config=get(protocol.migrate_web_serial_config), clock=get(lambda: rows.now),
            uuid4=get(lambda: SimpleNamespace(hex='same-session')), connecting_ttl=get(10), active_ttl=get(30), config_error=get(PlcConfigError)),
        maintenance_policy=module.LeaseMaintenancePolicy(current_user=poison or current,
            clock=get(lambda: rows.now), active_ttl=get(30), config_error=get(PlcConfigError)),
        diagnostic_policy=module.DiagnosticPolicy(token_hex=get(lambda size: 'same-diagnostic'),
            token_urlsafe=get(lambda size: 'token-'+str((current()() or {})['id'])), config_error=get(PlcConfigError),
            clock=get(lambda: rows.now), ceil=get(math.ceil), protocol_version=get(protocol.WEB_SERIAL_PROTOCOL_VERSION),
            frames=get(protocol.build_web_serial_diagnostic_plan), compare_digest=get(secrets.compare_digest), current_user=poison or current))

class LeaseDiagnosticContracts(unittest.TestCase):
    def graph(self, identity):
        rows=Rows(); user={'id':identity}; workstation=build(rows,user); seed(workstation,rows,identity)
        rows.tables['plc_workstation_leases'].clear()
        return operations(workstation,rows),rows,user
    def claim_activate(self, owner):
        claimed=owner.plc_web_serial_claim_connecting_lease('same-station',SimpleNamespace(client_instance_id='client-001',model_id='model',bundle_version=protocol.WEB_SERIAL_PROTOCOL_VERSION))
        request=SimpleNamespace(session_id=claimed['session_id'],lease_epoch=claimed['lease_epoch'],usb_vendor_id=1,usb_product_id=2)
        activated=owner.plc_web_serial_activate_lease('same-station',request)
        self.assertEqual(activated['state'],'active')
        return activated
    def test_constructor_poison_partial_failure_and_internal_getters(self):
        workstation=build(Rows(),{'id':'A'})
        def poison(): self.fail('constructor selected external supplier')
        owner=operations(workstation,Rows(),poison=poison)
        mapping={'mutate':'_plc_web_serial_mutate','record':'_plc_web_serial_record','lease_row':'_plc_workstation_lease_row','token_hash':'_plc_web_serial_token_hash'}
        count=0
        for component in (owner.acquisition,owner.maintenance,owner.diagnostics):
            for field in fields(component.ports):
                getter=getattr(component.ports,field.name)
                if getter is poison: continue
                expected=owner.require_active_lease if field.name in {'active_lease','require_active_lease'} else getattr(owner,mapping[field.name])
                self.assertEqual(getter(),expected);count+=1
        self.assertEqual(count,12)
        with patch.object(module,'DiagnosticState',side_effect=ValueError('construction')):
            with self.assertRaisesRegex(ValueError,'construction'): operations(workstation,Rows(),poison=poison)
    def test_after_arguments_workstation_selection_and_fixed_active_lease(self):
        owner,rows,_=self.graph('A');self.claim_activate(owner)
        original=owner.workstation; selected=[]
        before=SimpleNamespace(_plc_web_serial_mutate=lambda *a:selected.append('before'))
        after=SimpleNamespace(_plc_web_serial_mutate=lambda *a:selected.append('after'))
        owner.workstation=before;saved=owner.acquisition.ports.mutate()
        def argument(): owner.workstation=after;return 'same-station'
        saved(argument(),None,lambda state:None)
        self.assertEqual(selected,['after'])
        state={'station':rows.tables['plc_workstations']['same-station'],'lease':rows.tables['plc_workstation_leases']['same-station'],'clock':{'now':100}}
        station,lease,now=owner.maintenance.ports.require_active_lease()(state,'plcwsess_same-session',1)
        self.assertEqual((station['name'],lease['owner_user_id'],now),('A','A',100))
        self.assertIs(owner.require_active_lease.__self__,original.station)
    def test_two_retained_graphs_claim_activate_heartbeat_rebind_diagnostic(self):
        graphs=[self.graph('A'),self.graph('B')]
        plans=[]
        for owner,rows,user in graphs:
            activated=self.claim_activate(owner)
            request=SimpleNamespace(session_id=activated['session_id'],lease_epoch=activated['lease_epoch'])
            heartbeat=owner.plc_web_serial_heartbeat('same-station',request)
            self.assertEqual(heartbeat['owner_user_id'],user['id'])
            rebind=SimpleNamespace(**vars(request),model_id='next-model')
            self.assertEqual(owner.plc_web_serial_rebind_model('same-station',rebind)['model_id'],'next-model')
            attempt=SimpleNamespace(**vars(request),config_generation=3)
            plans.append(owner.plc_web_serial_diagnostic_plan('same-station',attempt))
        self.assertEqual(plans[0]['diagnostic_id'],plans[1]['diagnostic_id'])
        self.assertNotEqual(plans[0]['attempt_token'],plans[1]['attempt_token'])
        for index,(owner,rows,user) in enumerate(graphs):
            plan=plans[index]
            request=SimpleNamespace(session_id='plcwsess_same-session',lease_epoch=1,diagnostic_id=plan['diagnostic_id'],attempt_token=plans[1-index]['attempt_token'])
            before=copy.deepcopy(rows.tables)
            with self.assertRaisesRegex(PlcConfigError,'plc_diagnostic_token_invalid'):
                owner.plc_web_serial_confirm_diagnostic('same-station',request)
            self.assertEqual(rows.tables,before)
            request.attempt_token=plan['attempt_token']
            request.lease_epoch=2
            with self.assertRaisesRegex(PlcConfigError,'fenced'):owner.plc_web_serial_confirm_diagnostic('same-station',request)
            self.assertEqual(rows.tables,before)
            request.lease_epoch=1
            self.assertTrue(owner.plc_web_serial_confirm_diagnostic('same-station',request)['confirmed'])
            released=owner.plc_web_serial_release_lease('same-station',request)
            self.assertEqual(released['state'],'draining')
            request.outcome='uncertain';rows.now=1000
            self.assertTrue(owner.plc_web_serial_finish_diagnostic('same-station',request)['released'])
            stored=rows.tables['plc_workstation_leases']['same-station']['raw_json']
            self.assertEqual(stored['state'],'draining')
            self.assertNotIn('in_flight_dispatch_id',stored)
            with self.assertRaisesRegex(PlcConfigError,'plc_diagnostic_not_in_flight'):
                owner.plc_web_serial_finish_diagnostic('same-station',request)
    def test_permission_priority_identity_and_transaction_failure(self):
        owner,rows,user=self.graph('A')
        def forbidden(model):raise PermissionError('permission')
        from dataclasses import replace
        owner.acquisition.ports=replace(owner.acquisition.ports,require_model_permission=lambda:forbidden)
        before=copy.deepcopy(rows.tables)
        with self.assertRaisesRegex(PermissionError,'permission'):
            self.claim_activate(owner)
        self.assertEqual(rows.tables,before)
        owner.acquisition.ports=replace(owner.acquisition.ports,require_model_permission=lambda:lambda model:None)
        activated=self.claim_activate(owner);user['id']='intruder'
        request=SimpleNamespace(session_id=activated['session_id'],lease_epoch=activated['lease_epoch'])
        before=copy.deepcopy(rows.tables)
        with self.assertRaisesRegex(PlcConfigError,'fenced'):owner.plc_web_serial_heartbeat('same-station',request)
        self.assertEqual(rows.tables,before)
    def test_frame_builder_and_serializer_errors_rollback_actual_transactions(self):
        from dataclasses import replace
        owner,rows,_=self.graph('A');activated=self.claim_activate(owner)
        before=copy.deepcopy(rows.tables)
        def fail():raise ValueError('frames')
        owner.diagnostics.ports=replace(owner.diagnostics.ports,frames=lambda:fail)
        request=SimpleNamespace(session_id=activated['session_id'],lease_epoch=1,config_generation=3)
        with self.assertRaisesRegex(ValueError,'frames'):owner.plc_web_serial_diagnostic_plan('same-station',request)
        self.assertEqual(rows.tables,before)
        def bad_row(record):raise ValueError('serialize')
        owner._plc_workstation_lease_row=bad_row
        with self.assertRaisesRegex(ValueError,'serialize'):owner.plc_web_serial_heartbeat('same-station',request)
        self.assertEqual(rows.tables,before)

    def test_whole_root_inverse_and_actual_owner_mutation_guards(self):
        import ast
        from application_integration_source_contract import ROOT,PIPELINE_TASKS,PIPELINE_STAGES,AGENT_PIPELINE,PIPELINE_QUERIES,PIPELINE_EXECUTION,PIPELINE_PERSISTENCE,PLC_CAPTURE,PLC_OPERATIONS,restore_delta,restore_plc_domain_root,digest
        source=(ROOT/'local_inspection_service/server.py').read_text()
        self.assertEqual(digest(ast.parse(restore_delta(restore_delta(restore_delta(restore_delta(restore_delta(restore_delta(restore_delta(restore_delta(source,PIPELINE_TASKS),PIPELINE_STAGES),AGENT_PIPELINE),PIPELINE_QUERIES),PIPELINE_EXECUTION),PIPELINE_PERSISTENCE),PLC_CAPTURE),PLC_OPERATIONS))),PLC_OPERATIONS['parent_ast_sha256'])
        restore_plc_domain_root(source)
        for old,new in [('_plc_lease_diagnostic_workflows.acquisition','_plc_lease_diagnostic_workflows.maintenance'),('workstation=_plc_workstation_workflows','workstation=None')]:
            with self.assertRaises(AssertionError):restore_plc_domain_root(source.replace(old,new,1))

if POSTGRES:
    class LeaseDiagnosticPostgresContracts(unittest.TestCase):
        def test_real_two_schema_concurrent_claim_activate_and_diagnostic_rollback(self):
            import os
            import time
            import threading
            import psycopg
            from psycopg import sql
            from concurrent.futures import ThreadPoolExecutor
            from local_inspection_service.runtime.connections import ThreadRepositoryFactory
            from local_inspection_service.storage.postgres_schema import postgres_ddl
            from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
            dsn=os.environ['VANTALINE_POSTGRES_DSN']
            schemas=['plc_lease_graph_'+uuid.uuid4().hex for _ in range(2)]
            factories,connections,owners=[],[],[]
            with psycopg.connect(dsn,autocommit=True) as control:
                try:
                    for index,schema in enumerate(schemas):
                        control.execute(postgres_ddl(schema))
                        def create(schema=schema):
                            connection=psycopg.connect(dsn);connections.append(connection)
                            return SimpleNamespace(repository=PostgresRuntimeRepository(connection,'synthetic',schema))
                        factory=ThreadRepositoryFactory(create,lambda schema=schema:schema);factories.append(factory)
                        rows=Rows();rows.now=int(time.time());identity={'id':'account-'+str(index)}
                        workstation=build(rows,identity,repository=lambda factory=factory:factory.selection().repository)
                        owner=operations(workstation,rows);owners.append(owner)
                        with factory.thread_scope():
                            repository=factory.selection().repository
                            seed(workstation,repository,identity['id'],now=rows.now)
                            repository.connection.execute('DELETE FROM '+repository._qualified_table('plc_workstation_leases'))
                            repository.connection.commit()
                    def claim_activate(index):
                        with factories[index].thread_scope():
                            owner=owners[index]
                            try:
                                lease=owner.plc_web_serial_claim_connecting_lease('same-station',SimpleNamespace(client_instance_id='client-001',model_id='model',bundle_version=protocol.WEB_SERIAL_PROTOCOL_VERSION))
                            except PlcConfigError as error:
                                self.assertEqual(str(error),'plc_workstation_in_use');return False
                            activated=owner.plc_web_serial_activate_lease('same-station',SimpleNamespace(session_id=lease['session_id'],lease_epoch=lease['lease_epoch'],usb_vendor_id=1,usb_product_id=2))
                            self.assertEqual(activated['owner_user_id'],'account-'+str(index));return True
                    with ThreadPoolExecutor(4) as pool:
                        results=[future.result(timeout=20) for future in [pool.submit(claim_activate,index) for index in (0,0,1,1)]]
                    self.assertEqual(sorted(results),[False,False,True,True])
                    from dataclasses import replace
                    for index,owner in enumerate(owners):
                        with factories[index].thread_scope():
                            repository=factories[index].selection().repository
                            before=repository.fetch_all('plc_workstation_leases')
                            def fail():raise ValueError('frames')
                            owner.diagnostics.ports=replace(owner.diagnostics.ports,frames=lambda:fail)
                            with self.assertRaisesRegex(ValueError,'frames'):
                                owner.plc_web_serial_diagnostic_plan('same-station',SimpleNamespace(session_id='plcwsess_same-session',lease_epoch=1,config_generation=3))
                            self.assertEqual(repository.fetch_all('plc_workstation_leases'),before)
                    self.assertTrue(connections);self.assertTrue(all(connection.closed for connection in connections))
                finally:
                    for factory in factories:factory.clear()
                    for schema in schemas:control.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

if __name__=='__main__':unittest.main()
