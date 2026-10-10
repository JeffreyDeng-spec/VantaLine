"""Actual three-component PLC ownership; no physical or paid operations."""
import ast
import copy
from dataclasses import fields, replace
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from local_inspection_service.plc import workstation_composition as module
from local_inspection_service import plc_web_serial as protocol
from local_inspection_service.plc_fx_ascii import PlcConfigError
from fastapi import HTTPException

class Rows:
    def __init__(self):
        self.tables = {name: {} for name in ('plc_workstations', 'plc_workstation_leases', 'plc_web_serial_dispatches')}
        self.lock = threading.RLock()
        self.now = 100
        self.writes = []
    def __bool__(self): return False
    def key(self, table, row):
        return row['id' if table == 'plc_workstations' else 'station_id' if table == 'plc_workstation_leases' else 'id']
    def upsert_row(self, table, row, *, commit=True):
        self.writes.append(table)
        self.tables[table][self.key(table, row)] = copy.deepcopy(row)
    def fetch_one_by_columns(self, table, columns):
        return next((copy.deepcopy(row) for row in self.tables[table].values() if all(row.get(k) == v for k, v in columns.items())), None)
    def fetch_by_primary_key(self, table, columns): return self.fetch_one_by_columns(table, columns)
    def fetch_all(self, table): return copy.deepcopy(list(self.tables[table].values()))
    def mutate_plc_web_serial_rows(self, station_id, dispatch_id, callback):
        with self.lock:
            state = {'station': copy.deepcopy(self.tables['plc_workstations'].get(station_id)),
                     'lease': copy.deepcopy(self.tables['plc_workstation_leases'].get(station_id)),
                     'dispatch': copy.deepcopy(self.tables['plc_web_serial_dispatches'].get(dispatch_id)),
                     'clock': {'now': self.now}}
            callback(state)
            for key, table in [('station', 'plc_workstations'), ('lease', 'plc_workstation_leases'), ('dispatch', 'plc_web_serial_dispatches')]:
                if state.get(key) is not None: self.upsert_row(table, state[key])
            return state

def build(rows, identity, *, poison=None, repository=None):
    def get(value): return poison or (lambda: value)
    return module.PlcWorkstationWorkflows(
        files=module.WorkstationRepositoryFiles(get(None), get(Path('unused')), get(Path('unused/state'))),
        repository_policy=module.WorkstationRepositoryPolicy(get('unused-test-gate'), get(PlcConfigError), get('system')),
        storage=module.WorkstationAccess(get(repository if repository is not None else lambda: rows), get(rows.lock)),
        identity=module.WorkstationIdentity(get('station'), get(3600), get('system'), get(lambda: {'id': identity['id']}), get(lambda request: True)),
        station_policy=module.StationPolicy(get(lambda: rows.now), get(PlcConfigError), get(HTTPException), get(protocol.DEFAULT_WEB_SERIAL_CONFIG),
            get(30), get(5), get(protocol.WEB_SERIAL_PROTOCOL_VERSION), get(protocol.migrate_web_serial_config),
            get(protocol.normalize_web_serial_config), get(protocol.web_serial_profile_fingerprint)),
        projection=module.WorkstationProjection(get(lambda: {'consistent': True}), get(protocol.build_web_serial_capture_read_plan), get(protocol.web_serial_resolved_addresses)),
        dispatch_policy=module.BrowserDispatchPolicy(get(PlcConfigError), get(protocol.LEGACY_WEB_SERIAL_PROTOCOL_VERSION), get(protocol.WEB_SERIAL_PROTOCOL_VERSION),
            get(30), get(protocol.PROTOCOL_ID), get(protocol.build_legacy_web_serial_plan), get(protocol.build_web_serial_plan),
            get(protocol.normalize_legacy_web_serial_config), get(protocol.normalize_web_serial_config), get(protocol.migrate_web_serial_config),
            get(protocol.legacy_web_serial_config_fingerprint), get(protocol.web_serial_config_fingerprint)))

def seed(owner, rows, identity, *, now=None):
    station = {'id': 'same-station', 'name': identity, 'token_hash': owner._plc_web_serial_token_hash('same-cookie'),
               'config_generation': 3, 'config': {**protocol.DEFAULT_WEB_SERIAL_CONFIG, 'enabled': True}, 'profile_verified': True}
    lease = {'station_id': station['id'], 'session_id': 'same-session', 'owner_user_id': identity, 'state': 'active', 'communication_verified': True, 'lease_epoch': 7,
             'expires_at': (rows.now if now is None else now) + 300, 'model_id': 'model', 'client_instance_id': 'client', 'bundle_version': protocol.WEB_SERIAL_PROTOCOL_VERSION,
             'config_generation': 3, 'heartbeat_at': 100}
    rows.upsert_row('plc_workstations', owner._plc_workstation_row(station))
    rows.upsert_row('plc_workstation_leases', owner._plc_workstation_lease_row(lease))

class WorkstationCompositionContracts(unittest.TestCase):
    def setUp(self):
        self.rows = Rows(); self.identity = {'id': 'account-A'}
        self.owner = build(self.rows, self.identity)
        seed(self.owner, self.rows, self.identity['id'])
    def test_constructor_inert_and_all_internal_getters_select_owned_methods(self):
        def poison(): self.fail('construction selected a capability')
        owner = build(Rows(), {'id': 'B'}, poison=poison)
        count = 0
        for component in (owner.repository, owner.station, owner.browser):
            for group_field in fields(component):
                group = getattr(component, group_field.name)
                for field in fields(group):
                    getter = getattr(group, field.name)
                    if getter is poison: continue
                    result = getter()
                    expected = owner.require_active_lease if field.name == '_plc_web_serial_require_active_lease' else getattr(owner, field.name)
                    self.assertEqual(result, expected)
                    count += 1
        self.assertEqual(count, 25)
    def test_fixed_lease_binding_and_after_argument_repository_selection(self):
        owner = self.owner
        original_station = owner.station
        captured = owner.require_active_lease
        owner.station = SimpleNamespace(_plc_web_serial_require_active_lease=lambda *args: self.fail('captured lease drifted'))
        self.assertIs(captured.__self__, original_station)
        self.assertIs(owner.browser.identity._plc_web_serial_require_active_lease(), captured)
        state = {'station': self.rows.tables['plc_workstations']['same-station'],
                 'lease': self.rows.tables['plc_workstation_leases']['same-station'], 'clock': {'now': 100}}
        station, lease, now = captured(state, 'same-session', 7)
        self.assertEqual((station['name'], lease['owner_user_id'], now), ('account-A', 'account-A', 100))
        rebound = original_station._plc_web_serial_require_active_lease
        self.assertIs(captured.__self__, rebound.__self__)
        self.assertIs(captured.__func__, rebound.__func__)
        owner.station = original_station
        selected = []
        old = owner.repository
        after = SimpleNamespace(_plc_web_serial_upsert_row=lambda *args: selected.append('after'))
        def row(record): owner.repository = after; return record
        owner._plc_workstation_row = row
        owner.plc_web_serial_station_from_request = lambda request: None
        owner.plc_web_serial_station_payload = lambda record: record
        with patch('time.time', return_value=100):
            owner.plc_web_serial_pair(SimpleNamespace(cookies={}), SimpleNamespace(set_cookie=lambda *a, **k: None), 'New')
        self.assertEqual(selected, ['after'])
        owner.repository = old
    def test_two_graphs_same_ids_and_request_time_identity(self):
        rows_b = Rows(); identity_b = {'id': 'account-B'}; owner_b = build(rows_b, identity_b); seed(owner_b, rows_b, identity_b['id'])
        request = SimpleNamespace(cookies={'station': 'same-cookie'})
        self.assertEqual(self.owner.plc_web_serial_station_from_request(request)['name'], 'account-A')
        self.assertEqual(owner_b.plc_web_serial_station_from_request(request)['name'], 'account-B')
        for owner, rows, identity in [(self.owner, self.rows, self.identity), (owner_b, rows_b, identity_b)]:
            begun, created = owner.plc_web_serial_begin_camera_detection('same-station', 'same-session', 'request-001', 'model', 'fp')
            self.assertTrue(created)
            duplicate, created = owner.plc_web_serial_begin_camera_detection('same-station', 'same-session', 'request-001', 'model', 'fp')
            self.assertFalse(created); self.assertEqual(begun, duplicate)
            identity['id'] = 'intruder'
            before = copy.deepcopy(rows.tables)
            with self.assertRaises(PlcConfigError): owner.plc_web_serial_begin_camera_detection('same-station', 'same-session', 'request-002', 'model', 'fp')
            self.assertEqual(rows.tables, before)
        self.assertIsNot(self.owner.repository, owner_b.repository)
    def test_unverified_active_lease_cannot_admit_detection(self):
        lease=self.rows.tables['plc_workstation_leases']['same-station']['raw_json']
        lease.pop('communication_verified')
        before=copy.deepcopy(self.rows.tables)
        with self.assertRaisesRegex(PlcConfigError,'plc_workstation_lease_fenced'):
            self.owner.plc_web_serial_begin_camera_detection('same-station','same-session','request-001','model','fp')
        self.assertEqual(self.rows.tables,before)

    def test_declare_persists_before_projection_error_and_never_retries(self):
        owner = self.owner; rows = self.rows
        begun, _ = owner.plc_web_serial_begin_camera_detection('same-station', 'same-session', 'request-001', 'model', 'fp')
        dispatch_id = begun['dispatch_id']
        owner.plc_web_serial_finish_camera_detection('same-station', dispatch_id, 'same-session', {'passed': True})
        request = SimpleNamespace(session_id='same-session', lease_epoch=7, config_generation=3)
        def fail(record): raise ValueError('projection')
        owner.plc_web_serial_dispatch_public = fail
        with self.assertRaisesRegex(ValueError, 'projection'): owner.plc_web_serial_declare_attempt('same-station', dispatch_id, request)
        row = rows.tables['plc_web_serial_dispatches'][dispatch_id]['raw_json']
        self.assertEqual(row['status'], 'browser_attempt_declared')
        before = copy.deepcopy(rows.tables)
        with self.assertRaises(PlcConfigError): owner.plc_web_serial_declare_attempt('same-station', dispatch_id, request)
        self.assertEqual(rows.tables, before)
    def test_timeout_settlement_transaction_and_callback_rollback(self):
        owner = self.owner; rows = self.rows
        record = {'dispatch_id': 'd', 'station_id': 'same-station', 'detection_request_id': 'request', 'session_id': 'same-session', 'lease_epoch': 7, 'config_generation': 3, 'created_at': 90, 'status': 'browser_attempt_declared', 'deadline_at': 100, 'updated_at': 90}
        rows.upsert_row('plc_web_serial_dispatches', owner._plc_web_serial_dispatch_row(record))
        result = owner.plc_web_serial_recent_dispatches('same-station')
        self.assertEqual(result[0]['outcome'], 'uncertain')
        before = copy.deepcopy(rows.tables)
        def abort(state): state['station']['name'] = 'mutated'; raise ValueError('abort')
        with self.assertRaisesRegex(ValueError, 'abort'): owner._plc_web_serial_mutate('same-station', 'd', abort)
        self.assertEqual(rows.tables, before)
    def test_two_actual_pair_config_lease_plan_and_ack_graphs(self):
        for label in ('account-A', 'account-B'):
            rows = Rows(); owner = build(rows, {'id': label})
            request = SimpleNamespace(cookies={})
            cookies = []
            with patch('uuid.uuid4', return_value=SimpleNamespace(hex='same')), patch('secrets.token_urlsafe', return_value='same-cookie'), patch('time.time', return_value=100):
                paired = owner.plc_web_serial_pair(request, SimpleNamespace(set_cookie=lambda *a, **k: cookies.append(a)), label)
            station_id = paired['station']['id']
            self.assertEqual(station_id, 'plcws_same')
            self.assertEqual(cookies, [('station', 'same-cookie')])
            updated = owner.plc_web_serial_update_config(station_id, {**protocol.DEFAULT_WEB_SERIAL_CONFIG, 'enabled': True})
            generation = updated['config_generation']
            self.assertEqual(generation, 1)
            lease = {'station_id': station_id, 'session_id': 'same-session', 'owner_user_id': label, 'state': 'active', 'communication_verified': True, 'lease_epoch': 7,
                     'expires_at': 300, 'model_id': 'model', 'client_instance_id': 'client', 'bundle_version': protocol.WEB_SERIAL_PROTOCOL_VERSION,
                     'config_generation': generation, 'heartbeat_at': 100}
            rows.upsert_row('plc_workstation_leases', owner._plc_workstation_lease_row(lease))
            begun, created = owner.plc_web_serial_begin_camera_detection(station_id, 'same-session', 'request-001', 'model', 'fp')
            self.assertTrue(created)
            dispatch_id = begun['dispatch_id']
            planned = owner.plc_web_serial_finish_camera_detection(station_id, dispatch_id, 'same-session', {'passed': True})
            self.assertEqual([frame['target'] for frame in planned['frames']], ['D206'])
            attempt = SimpleNamespace(session_id='same-session', lease_epoch=7, config_generation=generation)
            with patch('secrets.token_urlsafe', return_value='attempt-token'):
                declared = owner.plc_web_serial_declare_attempt(station_id, dispatch_id, attempt)
            before = copy.deepcopy(rows.tables)
            receipt = SimpleNamespace(session_id='same-session', lease_epoch=8, attempt_token='attempt-token', outcome='', operations=[])
            with self.assertRaises(PlcConfigError): owner.plc_web_serial_record_receipt(station_id, dispatch_id, receipt)
            self.assertEqual(rows.tables, before)
            receipt.lease_epoch = 7; receipt.attempt_token = 'wrong'
            receipt.operations = [SimpleNamespace(model_dump=lambda: self.fail('wrong token converted media'))]
            with self.assertRaisesRegex(PlcConfigError, 'attempt_token_invalid'):
                owner.plc_web_serial_record_receipt(station_id, dispatch_id, receipt)
            self.assertEqual(rows.tables, before)
            receipt.attempt_token = 'attempt-token'
            operations = [dict(target=frame['target'], frame_sha256=frame['frame_sha256'], status='acknowledged', response_hex='06') for frame in declared['frames']]
            receipt.operations = [SimpleNamespace(model_dump=lambda item=item: item) for item in operations]
            completed = owner.plc_web_serial_record_receipt(station_id, dispatch_id, receipt)
            self.assertEqual(completed['outcome'], 'acknowledged')
            self.assertEqual(owner.plc_web_serial_record_receipt(station_id, dispatch_id, receipt), completed)
            self.assertEqual(owner.plc_web_serial_station_from_request(SimpleNamespace(cookies={'station': 'same-cookie'}))['name'], label)

    def test_root_inverse_actual_owner_and_business_identity(self):
        from application_integration_source_contract import verify_actual_compositions, restore_plc_domain_root, PLC_WORKSTATION, digest
        verify_actual_compositions()
        source = read_checked_application_source(ROOT / 'local_inspection_service/server.py')
        restored = restore_plc_domain_root(source)
        self.assertEqual(digest(ast.parse(restored)), PLC_WORKSTATION['parent_ast_sha256'])
        for old, new in [('_plc_workstation_workflows.repository', '_plc_workstation_workflows.station'),
                         ('runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none', 'runtime_postgres_repository_or_none=lambda: None')]:
            with self.assertRaises(AssertionError): restore_plc_domain_root(source.replace(old, new, 1))

if '--postgres' in sys.argv:
    sys.argv.remove('--postgres')
    class WorkstationPostgresContracts(unittest.TestCase):
        def test_actual_two_schema_factory_graphs_duplicate_admission_and_release(self):
            import os
            import time
            import uuid
            import psycopg
            from psycopg import sql
            from concurrent.futures import ThreadPoolExecutor
            from local_inspection_service.runtime.connections import ThreadRepositoryFactory
            from local_inspection_service.storage.postgres_schema import postgres_ddl
            from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
            dsn = os.environ['VANTALINE_POSTGRES_DSN']
            schemas = ['plc_graph_' + uuid.uuid4().hex for _ in range(2)]
            factories, connections, owners = [], [], []
            with psycopg.connect(dsn, autocommit=True) as control:
                try:
                    for index, schema in enumerate(schemas):
                        control.execute(postgres_ddl(schema))
                        def create(schema=schema):
                            connection = psycopg.connect(dsn)
                            connections.append(connection)
                            return SimpleNamespace(repository=PostgresRuntimeRepository(connection, 'synthetic', schema))
                        factory = ThreadRepositoryFactory(create, lambda schema=schema: schema)
                        factories.append(factory)
                        rows = Rows(); rows.now = int(time.time())
                        identity = {'id': 'account-' + str(index)}
                        owner = build(rows, identity, repository=lambda factory=factory: factory.selection().repository)
                        owners.append(owner)
                        with factory.thread_scope():
                            repository = factory.selection().repository
                            seed(owner, repository, identity['id'], now=rows.now)
                    def submit(index):
                        with factories[index].thread_scope():
                            return owners[index].plc_web_serial_begin_camera_detection('same-station', 'same-session', 'request-001', 'model', 'fp')
                    with ThreadPoolExecutor(4) as pool:
                        futures = [pool.submit(submit, index) for index in (0, 0, 1, 1)]
                        results = [future.result(timeout=20) for future in futures]
                    self.assertEqual(sorted(created for _, created in results), [False, False, True, True])
                    for index, owner in enumerate(owners):
                        with factories[index].thread_scope():
                            repository = factories[index].selection().repository
                            dispatches = repository.fetch_all('plc_web_serial_dispatches')
                            self.assertEqual(len(dispatches), 1)
                            station = owner.plc_web_serial_station_from_request(SimpleNamespace(cookies={'station': 'same-cookie'}))
                            self.assertEqual(station['name'], 'account-' + str(index))
                            before = copy.deepcopy(station)
                            def abort(state): state['station']['name'] = 'changed'; raise ValueError('rollback')
                            with self.assertRaisesRegex(ValueError, 'rollback'):
                                owner._plc_web_serial_mutate('same-station', None, abort)
                            self.assertEqual(owner.plc_web_serial_station_from_request(SimpleNamespace(cookies={'station': 'same-cookie'})), before)
                    self.assertTrue(connections)
                    self.assertTrue(all(connection.closed for connection in connections))
                finally:
                    for factory in factories: factory.clear()
                    for schema in schemas:
                        control.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

if __name__ == '__main__': unittest.main()
