"""Retained capture-state contracts with synthetic atomic storage and no PLC I/O."""
import ast
import copy
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.plc_fx_ascii import PlcConfigError, DEFAULT_PLC_CONFIG, normalize_config

BASELINE = os.environ.get('VANTALINE_PLC_CAPTURE_STATE_BASELINE_SOURCE')
NAMES = ('_plc_capture_runtime', '_plc_expire_capture_state', 'plc_claim_capture_session', 'plc_heartbeat_capture_session', 'plc_release_capture_session', 'plc_capture_disarm', 'plc_apply_capture_observation', 'plc_claim_next_capture_event', 'plc_begin_triggered_analysis', 'plc_prepare_triggered_dispatch', 'plc_finish_triggered_analysis')


def create(b):
    if BASELINE:
        tree = ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 11
        b.update(Any=Any, copy=copy, hashlib=hashlib, time=time, uuid=uuid)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), b)
        return SimpleNamespace(**{name: b[name] for name in NAMES})
    from local_inspection_service.plc.plc_capture_state import PlcCaptureState
    from local_inspection_service.plc.plc_capture_state_ports import CaptureStateTransactions, CaptureStatePolicy
    def ports(cls):
        return cls(**{f.name: lambda name=f.name: b[name] for f in fields(cls)})
    service = PlcCaptureState(ports(CaptureStateTransactions), ports(CaptureStatePolicy))
    b.update({name: getattr(service, name) for name in NAMES})
    return service


class CaptureContract(unittest.TestCase):
    def fixture(self):
        config = {'generation': 7, 'runtime': {}}
        def mutate_config(callback):
            working = copy.deepcopy(config)
            callback(working)
            config.clear()
            config.update(working)
        def mutate_runtime(callback):
            def apply(current):
                state = current.setdefault('runtime', {})
                callback(state)
            mutate_config(apply)
        b = dict(load_config=lambda: copy.deepcopy(config), mutate_app_config_atomically=mutate_config,
                 mutate_plc_runtime_coordination=mutate_runtime,
                 plc_completed_capture_receipt=lambda identity: copy.deepcopy(config.get('receipts', {}).get(identity)),
                 _plc_canonical=lambda value: json.dumps(value, sort_keys=True), PlcConfigError=PlcConfigError,
                 PLC_CAPTURE_EVENT_TTL_SECONDS=20, PLC_CAPTURE_PROCESSING_TTL_SECONDS=60,
                 PLC_CAPTURE_RESULTS_KEY='receipts', PLC_CONTROL_GENERATION_KEY='generation',
                 PLC_RUNTIME_COORDINATION_KEY='runtime', PLC_WORKER_TOTAL_TIMEOUT_SECONDS=15)
        return create(b), b, config

    def event(self, s):
        session = s.plc_claim_capture_session('alice', 'model')
        self.assertIsNone(s.plc_apply_capture_observation(0, generation=7, owner_epoch=3, trigger_value=1))
        event = s.plc_apply_capture_observation(1, generation=7, owner_epoch=3, trigger_value=1)
        return session, event

    def test_original_edge_session_and_idempotency_regression(self):
        s, b, _ = self.fixture()
        # Preserve the original scenario and assertions; execute only its synthetic
        # state test against this service, not the old module's startup/transport code.
        original = ROOT / 'local_inspection_service/scripts/smoke_plc_phase2.py'
        node = next(n for n in ast.parse(original.read_text(encoding='utf-8')).body if isinstance(n, ast.FunctionDef) and n.name == 'test_capture_edge_session_and_idempotency')
        server = SimpleNamespace(**{name: getattr(s, name) for name in NAMES}, **{name: value for name, value in b.items() if name not in NAMES})
        scope = dict(server=server, Any=Any, time=time, PlcConfigError=PlcConfigError, normalize_config=normalize_config, DEFAULT_PLC_CONFIG=DEFAULT_PLC_CONFIG)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(original), 'exec'), scope)
        scope[node.name]()

    def test_runtime_normalization_and_expiry_deadlines(self):
        s, _, _ = self.fixture()
        state = {'capture': None}
        capture = s._plc_capture_runtime(state)
        self.assertIs(capture, state['capture'])
        self.assertEqual(capture, {'sequence': 0, 'armed': False, 'events': []})
        original = {'status': 'claimed', 'session_id': 's', 'submission_expires_at': 99, 'nested': {'evidence': True}}
        capture.update(session={'session_id': 's', 'busy': True, 'expires_at': 200}, events=[None, original])
        s._plc_expire_capture_state(capture, 100)
        self.assertEqual(capture['events'][0]['status'], 'expired')
        self.assertEqual(original['status'], 'claimed')
        self.assertIs(capture['events'][0]['nested'], original['nested'])
        self.assertFalse(capture['session']['busy'])
        for status, field in [('pending', 'expires_at'), ('processing', 'processing_expires_at'), ('dispatching', 'dispatch_expires_at')]:
            capture['events'] = [{'status': status, field: 100}]
            s._plc_expire_capture_state(capture, 100)
            self.assertEqual(capture['events'][0]['status'], 'expired')
        capture['events'] = [{'status': 'completed', 'sequence': i} for i in range(110)]
        s._plc_expire_capture_state(capture, 201)
        self.assertNotIn('session', capture)
        self.assertEqual(len(capture['events']), 100)
        self.assertEqual(capture['events'][0]['sequence'], 10)

    def test_session_ownership_generation_and_release(self):
        s, _, config = self.fixture()
        with patch.object(time, 'time', return_value=100):
            session = s.plc_claim_capture_session('alice', 'model')
            with self.assertRaisesRegex(PlcConfigError, 'in_use'):
                s.plc_claim_capture_session('bob', 'model')
            with self.assertRaisesRegex(PlcConfigError, 'not_owned'):
                s.plc_heartbeat_capture_session(session['session_id'], 'bob')
            s.plc_release_capture_session(session['session_id'], 'bob')
            self.assertIn('session', config['runtime']['capture'])
            config['generation'] = 8
            with self.assertRaisesRegex(PlcConfigError, 'generation_changed'):
                s.plc_heartbeat_capture_session(session['session_id'], 'alice')
            s.plc_release_capture_session(session['session_id'], 'alice')
            self.assertNotIn('session', config['runtime']['capture'])

    def test_missed_edges_disarm_and_rebinding(self):
        s, _, config = self.fixture()
        with patch.object(time, 'time', return_value=100):
            self.assertIsNone(s.plc_apply_capture_observation(1, generation=7, owner_epoch=3, trigger_value=1))
            s.plc_apply_capture_observation(0, generation=7, owner_epoch=3, trigger_value=1)
            event = s.plc_apply_capture_observation(1, generation=7, owner_epoch=3, trigger_value=1)
            self.assertEqual(event['status'], 'missed')
            self.assertEqual(event['reason'], 'no_ready_capture_session')
            event['value'] = 999
            self.assertEqual(config['runtime']['capture']['events'][0]['value'], 1)
            self.assertIsNone(s.plc_apply_capture_observation(1, generation=8, owner_epoch=4, trigger_value=1))
            s.plc_capture_disarm('fixture')
            self.assertEqual(config['runtime']['capture']['disarmed_reason'], 'fixture')
            self.assertIsNone(config['runtime']['capture']['last_value'])

    def test_claim_prepare_receipt_and_duplicate_copy(self):
        s, _, config = self.fixture()
        with patch.object(time, 'time', return_value=100):
            session, event = self.event(s)
            sid, tid = session['session_id'], event['trigger_id']
            claimed = s.plc_claim_next_capture_event(sid, 'alice')
            self.assertEqual(claimed['submission_expires_at'], 110)
            self.assertIsNone(s.plc_claim_next_capture_event(sid, 'alice'))
            self.assertIsNone(s.plc_begin_triggered_analysis(tid, sid, 'alice', 'model', 'fp'))
            s.plc_prepare_triggered_dispatch(tid, sid, 'alice')
            result = {'passed': True, 'nested': {'value': 1}}
            s.plc_finish_triggered_analysis(tid, sid, 'alice', result)
            result['nested']['value'] = 2
            stored = s.plc_begin_triggered_analysis(tid, sid, 'alice', 'model', 'fp')
            self.assertEqual(stored['nested']['value'], 1)
            stored['nested']['value'] = 3
            self.assertEqual(config['receipts'][tid]['result']['nested']['value'], 1)
            with self.assertRaisesRegex(PlcConfigError, 'payload_conflict'):
                s.plc_begin_triggered_analysis(tid, sid, 'alice', 'model', 'changed')
            with self.assertRaisesRegex(PlcConfigError, 'not_owned'):
                s.plc_begin_triggered_analysis(tid, sid, 'bob', 'model', 'fp')

    def test_expired_analysis_cannot_become_passed(self):
        s, _, config = self.fixture()
        with patch.object(time, 'time', return_value=100):
            session, event = self.event(s)
            sid, tid = session['session_id'], event['trigger_id']
            s.plc_claim_next_capture_event(sid, 'alice')
            s.plc_begin_triggered_analysis(tid, sid, 'alice', 'model', 'fp')
        with patch.object(time, 'time', return_value=161):
            s.plc_finish_triggered_analysis(tid, sid, 'alice', {'passed': True})
        self.assertEqual(config['runtime']['capture']['events'][0]['status'], 'expired')
        self.assertNotIn('receipts', config)

    def test_fenced_dispatch_and_conflicting_receipt_rollback(self):
        s, _, config = self.fixture()
        with patch.object(time, 'time', return_value=100):
            session, event = self.event(s)
            sid, tid = session['session_id'], event['trigger_id']
            s.plc_claim_next_capture_event(sid, 'alice')
            s.plc_begin_triggered_analysis(tid, sid, 'alice', 'model', 'fp')
            config['generation'] = 8
            with self.assertRaisesRegex(PlcConfigError, 'not_dispatchable'):
                s.plc_prepare_triggered_dispatch(tid, sid, 'alice')
            config['receipts'] = {tid: {'result': 'existing evidence'}}
            previous = copy.deepcopy(config)
            with self.assertRaisesRegex(PlcConfigError, 'receipt_conflict'):
                s.plc_finish_triggered_analysis(tid, sid, 'alice', {'passed': True})
            self.assertEqual(config, previous)
            s.plc_finish_triggered_analysis(tid, sid, 'alice', None, 'x' * 300)
            self.assertEqual(config['runtime']['capture']['events'][0]['error'], 'x' * 240)
            self.assertEqual(config['receipts'][tid], {'result': 'existing evidence'})

    @unittest.skipIf(BASELINE, 'candidate composition only')
    def test_assembly_and_instance_isolation(self):
        from local_inspection_service.plc.plc_capture_state_ports import CaptureStateTransactions, CaptureStatePolicy
        tree = ast.parse((ROOT / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_plc_capture_state' for t in n.targets))
        for group, cls in zip(assignment.value.keywords, (CaptureStateTransactions, CaptureStatePolicy)):
            self.assertEqual({k.arg for k in group.value.keywords}, {f.name for f in fields(cls)})
            for getter in group.value.keywords:
                self.assertIsInstance(getter.value, ast.Lambda)
                self.assertEqual(getter.value.body.id, getter.arg)
                self.assertFalse(getter.value.args.args)
        a, _, ac = self.fixture()
        b, _, bc = self.fixture()
        a.plc_capture_disarm('a')
        b.plc_capture_disarm('b')
        a.plc_capture_disarm('a2')
        self.assertEqual(ac['runtime']['capture']['disarmed_reason'], 'a2')
        self.assertEqual(bc['runtime']['capture']['disarmed_reason'], 'b')


if __name__ == '__main__':
    unittest.main(verbosity=2)
