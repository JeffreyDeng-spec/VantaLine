"""Dispatch cache and deadline evidence contracts with isolated collaborators."""
import ast
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = os.environ.get('VANTALINE_PLC_DISPATCH_RUNTIME_STATE_BASELINE_SOURCE')
NAMES = ('_plc_runtime_entry', '_hydrate_plc_runtime_entry', '_register_plc_dispatch_runtime', '_plc_deadline_snapshot',
         '_plc_active_attempts_snapshot', 'plc_dispatch_identity', 'plc_dispatch_record_is_terminal',
         'plc_dispatch_is_pristine_queue', 'plc_dispatch_adoption_blocker')


def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 9
        bindings.update(Any=Any, hashlib=hashlib, json=json, time=time)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), bindings)
        return SimpleNamespace(**{name: bindings[name] for name in NAMES})
    from local_inspection_service.plc.dispatch_runtime_state import PlcDispatchRuntimeState
    from local_inspection_service.plc.dispatch_runtime_state_ports import DispatchRuntimeState, DispatchRuntimeRecords, DispatchRuntimePolicy
    def ports(cls):
        return cls(**{f.name: lambda name=f.name: bindings[name] for f in fields(cls)})
    service = PlcDispatchRuntimeState(ports(DispatchRuntimeState), ports(DispatchRuntimeRecords), ports(DispatchRuntimePolicy))
    bindings.update({name: getattr(service, name) for name in NAMES})
    return service


class DispatchStateContracts(unittest.TestCase):
    def fixture(self):
        config = {'plc_dispatches': []}
        bindings = dict(_plc_dispatch_runtime={}, _PLC_RUNTIME_LIMIT=2, _config_io_lock=threading.RLock(),
            _plc_active_attempts={}, load_config=Mock(return_value=config), plc_dispatch_audit_records=lambda c: c['plc_dispatches'],
            plc_mark_deadline=Mock(return_value={'state_version': 5, 'deadline_exceeded': True}),
            _plc_canonical=lambda x: json.dumps(x, sort_keys=True))
        service = create(bindings)
        return service, bindings, config

    def test_cache_evicts_only_completed_other_entries(self):
        service, b, _ = self.fixture()
        live = service._plc_runtime_entry('live')
        done = service._plc_runtime_entry('done'); done['worker_done'] = True
        current = service._plc_runtime_entry('current')
        self.assertEqual(list(b['_plc_dispatch_runtime']), ['live', 'current'])
        self.assertIs(service._plc_runtime_entry('live'), live)
        b['_PLC_RUNTIME_LIMIT'] = 0
        current['worker_done'] = True
        self.assertIs(service._plc_runtime_entry('current'), current)
        self.assertEqual(list(b['_plc_dispatch_runtime']), ['live', 'current'])

    def test_hydration_uses_last_record_once_and_shallow_copy(self):
        service, b, config = self.fixture()
        nested = []
        record = dict(dispatch_id='d', state_version=4, worker_done=True, operations=nested)
        config['plc_dispatches'] = [dict(record, state_version=1), record]
        self.assertIsNone(service._register_plc_dispatch_runtime('d'))
        entry = service._hydrate_plc_runtime_entry('d')
        self.assertEqual(entry['state_version'], 4)
        self.assertIsNot(entry['latest'], record)
        self.assertIs(entry['latest']['operations'], nested)
        b['load_config'].assert_called_once_with()
        service._hydrate_plc_runtime_entry('missing')
        self.assertTrue(service._plc_runtime_entry('missing')['hydrated'])

    def test_deadline_keeps_active_evidence_and_persists_version(self):
        service, b, _ = self.fixture()
        entry = service._plc_runtime_entry('d'); entry.update(state_version=4, worker_started=True)
        nested = []
        active = dict(dispatch_id='d', nested=nested, write_call_started=True)
        b['_plc_active_attempts'] = {'a': active, 'other': {'dispatch_id': 'other'}}
        with patch.object(time, 'time', return_value=100):
            result = service._plc_deadline_snapshot(dispatch_id='d', source='camera', request_id='r', passed=True)
        self.assertTrue(entry['deadline_exceeded'])
        self.assertEqual(entry['deadline_exceeded_at'], 100)
        self.assertEqual(entry['state_version'], 5)
        self.assertTrue(result['worker_continues'])
        self.assertFalse(result['worker_cleanup_pending'])
        self.assertIsNot(result['active_attempts'][0], active)
        self.assertIs(result['active_attempts'][0]['nested'], nested)
        b['plc_mark_deadline'].assert_called_once_with('d', expected_version=4)

    def test_failed_deadline_is_provisional_without_inventing_ack(self):
        service, b, _ = self.fixture()
        entry = service._plc_runtime_entry('d')
        entry.update(worker_started=True, latest={'state_version': 3, 'attempted': True, 'physical_status': 'full_frame_written', 'acknowledged_targets': ['D206']})
        b['plc_mark_deadline'].side_effect = OSError('synthetic persistence failure')
        result = service._plc_deadline_snapshot(dispatch_id='d', source='camera', request_id='r', passed=False)
        self.assertEqual(result['outcome'], 'outcome_uncertain')
        self.assertEqual(result['physical_status'], 'full_frame_written')
        self.assertEqual(result['acknowledged_targets'], ['D206'])
        self.assertTrue(result['provisional'])
        self.assertEqual(result['audit_status'], 'persist_failed')
        self.assertEqual(entry['state_version'], 0)
        self.assertTrue(entry['deadline_exceeded'])
        self.assertNotIn('worker_done', result)

    def test_identity_terminal_and_safe_queue_adoption(self):
        service, _, _ = self.fixture()
        identity = service.plc_dispatch_identity({'request_id': 'r', 'passed': True}, source='image', fingerprint='f')
        changed = service.plc_dispatch_identity({'request_id': 'r', 'passed': False}, source='image', fingerprint='f')
        self.assertEqual(identity[:2], changed[:2]); self.assertEqual(len(identity[0]), 24)
        self.assertEqual(identity[2], True); self.assertEqual(changed[2], False)
        self.assertTrue(service.plc_dispatch_record_is_terminal({'status': 'acknowledged'}))
        self.assertFalse(service.plc_dispatch_record_is_terminal({'status': 'acknowledged', 'provisional': True}))
        row = dict(status='queued', attempted=False, operations=[], events=[{'kind': 'create'}],
                   record_schema_version=2, protocol_contract_version=2, control_generation=1, config_snapshot={'a': 1}, dispatch_deadline_at_ms=101)
        def reason(record, generation=1, now=100):
            return service.plc_dispatch_adoption_blocker(record, settings={'a': 1}, generation=generation, now_ms=now)
        self.assertEqual(reason(row), '')
        self.assertEqual(reason(dict(row, attempted=0)), 'not_pristine')
        self.assertEqual(reason(dict(row, protocol_contract_version=1)), 'version_not_adoptable')
        self.assertEqual(reason(dict(row, control_generation=0), generation=0), 'generation_changed')
        self.assertEqual(reason(dict(row, config_snapshot={})), 'config_changed')
        self.assertEqual(reason(dict(row, dispatch_deadline_at_ms=True)), 'deadline_missing')
        self.assertEqual(reason(row, now=101), 'deadline_expired')

    def test_active_snapshot_shallow_identity_and_isolated_instances(self):
        first, a, _ = self.fixture(); second, b, _ = self.fixture()
        nested = []; record = {'nested': nested}
        a['_plc_active_attempts']['one'] = record
        snapshot = first._plc_active_attempts_snapshot()
        self.assertIsNot(snapshot[0], record); self.assertIs(snapshot[0]['nested'], nested)
        self.assertEqual(second._plc_active_attempts_snapshot(), [])
        self.assertEqual(first._plc_active_attempts_snapshot(), snapshot)

    @unittest.skipIf(BASELINE, 'Original root functions have no extracted port assembly')
    def test_actual_root_getters_and_forwarding(self):
        from local_inspection_service.scripts import smoke_plc_phase1_hardening as fixture
        server = fixture.server; service = server._plc_dispatch_runtime_state
        for group in ('state', 'records', 'policy'):
            ports = getattr(service, group)
            for field in fields(ports):
                getter = getattr(ports, field.name); original = getattr(server, field.name)
                self.assertIs(getter(), original)
                with patch.object(server, field.name, object()) as replacement:
                    self.assertIs(getter(), replacement)
                self.assertIs(getter(), original)
        cases = {
            '_plc_runtime_entry': (('d',), {}), '_hydrate_plc_runtime_entry': (('d',), {}),
            '_register_plc_dispatch_runtime': (('d',), {}),
            '_plc_deadline_snapshot': ((), dict(dispatch_id='d', source='camera', request_id='r', passed=True)),
            '_plc_active_attempts_snapshot': ((), {}),
            'plc_dispatch_identity': (({},), dict(source='camera', fingerprint='f')),
            'plc_dispatch_record_is_terminal': (({},), {}), 'plc_dispatch_is_pristine_queue': (({},), {}),
            'plc_dispatch_adoption_blocker': (({},), dict(settings={}, generation=1, now_ms=100)),
        }
        for name, (args, kwargs) in cases.items():
            callback = Mock(return_value=object())
            with patch.object(server, '_plc_dispatch_runtime_state', SimpleNamespace(**{name: callback})):
                self.assertIs(getattr(server, name)(*args, **kwargs), callback.return_value)
                callback.assert_called_once_with(*args, **kwargs)


if __name__ == '__main__':
    unittest.main()
