"""Single legacy PLC iterations with synthetic I/O; no workers or serial devices."""
import ast
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from local_inspection_service.plc.errors import PlcDispatchStateConflict
from local_inspection_service.plc_fx_ascii import PlcConfigError
BASELINE = os.environ.get('VANTALINE_PLC_LEGACY_OPERATIONS_BASELINE_SOURCE')
NAMES = {'plc_reconcile_pending_dispatches_once', 'plc_capture_poll_once'}


def build():
    source = Path(BASELINE) if BASELINE else ROOT / 'local_inspection_service/server.py'
    nodes = []
    for node in ast.parse(read_checked_application_source(source, encoding='utf-8-sig')).body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.ImportFrom) and node.module == 'plc.legacy_operations':
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in NAMES | {'_legacy_plc_operations'} for t in node.targets
        ):
            nodes.append(node)
    target = ModuleType('local_inspection_service._legacy_operations_contract')
    target.__package__ = 'local_inspection_service'
    target.__dict__.update(Any=Any, PlcConfigError=PlcConfigError, PlcDispatchStateConflict=PlcDispatchStateConflict)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), target.__dict__)
    return target


class LegacyOperationsContract(unittest.TestCase):
    def setUp(self):
        self.api = build()
        self.settings = {'enabled': True, 'capture_trigger_enabled': True, 'timeout': 3,
                         'capture_input_register': 'D10', 'capture_trigger_value': '1'}
        self.config = {'plc': self.settings, 'generation': 5}
        bindings = {'load_config': Mock(side_effect=lambda: self.config),
                    'raw_plc_namespace': Mock(side_effect=lambda c: c['plc']),
                    'normalize_plc_config': Mock(side_effect=lambda c: c),
                    'plc_activation_errors': Mock(return_value=[]),
                    'PLC_CONTROL_GENERATION_KEY': 'generation',
                    'plc_claim_or_renew_io_owner': Mock(return_value={'epoch': '7'}),
                    'plc_current_process_owns_io': Mock(return_value=True),
                    'plc_dispatch_audit_records': Mock(return_value=[]),
                    'verify_persisted_plc_dispatch': Mock(side_effect=lambda c: c),
                    'plc_dispatch_is_pristine_queue': Mock(return_value=True),
                    'plc_dispatch_adoption_blocker': Mock(return_value=None),
                    'plc_finalize_dispatch': Mock(return_value={'finalized': True}),
                    '_run_queued_plc_dispatch': Mock(return_value={'plc_sync': {'dispatched': True}}),
                    '_plc_write_pending': SimpleNamespace(is_set=Mock(return_value=False)),
                    '_plc_dispatch_slots': SimpleNamespace(acquire=Mock(return_value=True), release=Mock()),
                    'read_d_register_value': Mock(return_value=1), '_plc_transport_factory': object(),
                    'plc_capture_disarm': Mock(), 'plc_apply_capture_observation': Mock(return_value={'observed': True})}
        self.api.__dict__.update(bindings)

    def test_normalization_failure_disabled_and_unavailable_owner_gates(self):
        for name in NAMES:
            for reason in ('malformed', 'disabled', 'activation', 'owner'):
                with self.subTest(name=name, reason=reason):
                    self.setUp()
                    if reason == 'malformed':
                        self.api.normalize_plc_config.side_effect = PlcConfigError('synthetic')
                    elif reason == 'disabled':
                        self.settings['enabled'] = False
                    elif reason == 'activation':
                        self.api.plc_activation_errors.return_value = [{'code': 'unavailable'}]
                    else:
                        self.api.plc_claim_or_renew_io_owner.return_value = None
                    self.assertIsNone(getattr(self.api, name)())
                    self.api.read_d_register_value.assert_not_called()
                    self.api.plc_dispatch_audit_records.assert_not_called()
                    if reason in ('malformed', 'disabled'):
                        self.api.plc_activation_errors.assert_not_called()
        self.setUp()
        self.settings['capture_trigger_enabled'] = False
        self.assertIsNone(self.api.plc_capture_poll_once())
        self.api.plc_activation_errors.assert_not_called()

    def test_errors_outside_normalization_boundary_propagate(self):
        error = RuntimeError('normalization')
        self.api.normalize_plc_config.side_effect = error
        for name in NAMES:
            with self.assertRaises(RuntimeError) as caught:
                getattr(self.api, name)()
            self.assertIs(caught.exception, error)
        self.setUp()
        self.config['generation'] = 'bad'
        with self.assertRaises(ValueError):
            self.api.plc_capture_poll_once()
        self.api.normalize_plc_config.assert_not_called()

    def test_reconcile_skips_unverified_nonpristine_and_wrong_version(self):
        rows = [{'id': 'invalid'}, {'id': 'started'}, {'id': 'old'},
                {'id': 'eligible', 'request_id': 9, 'source': 4, 'passed': [1], 'detection_identity': 8}, {'id': 'later'}]
        self.api.plc_dispatch_audit_records.return_value = rows
        def verify(row):
            if row['id'] == 'invalid':
                raise PlcDispatchStateConflict('corrupt')
            return row
        self.api.verify_persisted_plc_dispatch.side_effect = verify
        self.api.plc_dispatch_is_pristine_queue.side_effect = lambda r: r['id'] != 'started'
        self.api.plc_dispatch_adoption_blocker.side_effect = lambda r, **kw: 'version_not_adoptable' if r['id'] == 'old' else None
        self.assertEqual(self.api.plc_reconcile_pending_dispatches_once(), {'dispatched': True})
        self.api._run_queued_plc_dispatch.assert_called_once_with({'request_id': '9', 'passed': True}, source='4', fingerprint='8')
        self.api.plc_dispatch_audit_records.assert_called_once_with(self.config)
        self.assertEqual(self.api.verify_persisted_plc_dispatch.call_count, 4)
        self.api.plc_finalize_dispatch.assert_not_called()

    def test_reconcile_blocker_reason_and_first_result_no_retry(self):
        row = {'dispatch_id': 5, 'state_version': '2'}
        for blocker, reason in (('deadline_missing', 'plc_dispatch_queue_timeout'),
                                ('deadline_expired', 'plc_dispatch_queue_timeout'),
                                ('config_changed', 'cancelled_after_config_change')):
            self.setUp()
            self.api.plc_dispatch_audit_records.return_value = [row, {'dispatch_id': 'later'}]
            self.api.plc_dispatch_adoption_blocker.return_value = blocker
            self.assertEqual(self.api.plc_reconcile_pending_dispatches_once(), {'finalized': True})
            self.api.plc_finalize_dispatch.assert_called_once_with('5', expected_version=2, reason=reason)
            self.api.plc_dispatch_adoption_blocker.assert_called_once_with(row, settings=self.settings, generation=5)
            self.api._run_queued_plc_dispatch.assert_not_called()
        error = RuntimeError('finalize')
        self.api.plc_finalize_dispatch.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            self.api.plc_reconcile_pending_dispatches_once()
        self.assertIs(caught.exception, error)

    def test_poll_preacquire_and_postacquire_gates(self):
        for reason in ('pending-before', 'slot-busy', 'pending-after', 'owner-after'):
            self.setUp()
            if reason == 'pending-before':
                self.api._plc_write_pending.is_set.return_value = True
            elif reason == 'slot-busy':
                self.api._plc_dispatch_slots.acquire.return_value = False
            elif reason == 'pending-after':
                self.api._plc_write_pending.is_set.side_effect = [False, True]
            else:
                self.api.plc_current_process_owns_io.return_value = False
            self.assertIsNone(self.api.plc_capture_poll_once())
            self.api.read_d_register_value.assert_not_called()
            self.api.plc_capture_disarm.assert_not_called()
            self.assertEqual(self.api._plc_dispatch_slots.release.call_count, int(reason.endswith('after')))
            if reason == 'pending-before':
                self.api._plc_dispatch_slots.acquire.assert_not_called()
            else:
                self.api._plc_dispatch_slots.acquire.assert_called_once_with(blocking=False)

    def test_poll_read_arguments_release_then_observation(self):
        for timeout, expected in ((3, .15), (.05, .05)):
            self.setUp()
            self.settings['timeout'] = timeout
            events = []
            def read(settings, register, **kwargs):
                self.assertIsNot(settings, self.settings)
                self.assertEqual(settings, {**self.settings, 'timeout': expected})
                self.assertEqual(register, 'D10')
                self.assertIs(kwargs['transport_factory'], self.api._plc_transport_factory)
                events.append('read')
                return 1
            self.api.read_d_register_value.side_effect = read
            self.api._plc_dispatch_slots.release.side_effect = lambda: events.append('release')
            self.api.plc_apply_capture_observation.side_effect = lambda *args, **kw: events.append('observe') or {'ok': True}
            self.assertEqual(self.api.plc_capture_poll_once(), {'ok': True})
            self.assertEqual(events, ['read', 'release', 'observe'])
            self.api.plc_apply_capture_observation.assert_called_once_with(1, generation=5, owner_epoch=7, trigger_value=1)
            self.assertEqual(self.settings['timeout'], timeout)

    def test_read_exception_and_baseexception_always_release(self):
        error = ValueError('read fixture')
        self.api.read_d_register_value.side_effect = error
        self.assertIsNone(self.api.plc_capture_poll_once())
        self.api.plc_capture_disarm.assert_called_once_with('read_failed:ValueError')
        self.api._plc_dispatch_slots.release.assert_called_once()
        self.api.plc_apply_capture_observation.assert_not_called()
        self.setUp()
        error = SystemExit('stop fixture')
        self.api.read_d_register_value.side_effect = error
        with self.assertRaises(SystemExit) as caught:
            self.api.plc_capture_poll_once()
        self.assertIs(caught.exception, error)
        self.api._plc_dispatch_slots.release.assert_called_once()
        self.api.plc_capture_disarm.assert_not_called()

    def test_disarm_failure_still_releases_and_second_read_failure_propagates(self):
        error = RuntimeError('disarm failed')
        self.api.read_d_register_value.side_effect = OSError('read')
        self.api.plc_capture_disarm.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            self.api.plc_capture_poll_once()
        self.assertIs(caught.exception, error)
        self.api._plc_dispatch_slots.release.assert_called_once()
        self.setUp()
        self.api.load_config.side_effect = [self.config, error]
        with self.assertRaises(RuntimeError) as caught:
            self.api.plc_capture_poll_once()
        self.assertIs(caught.exception, error)
        self.api._plc_dispatch_slots.release.assert_called_once()
        self.api.plc_capture_disarm.assert_not_called()

    def test_stale_generation_or_owner_disarms_after_slot_release(self):
        for reason in ('generation', 'owner'):
            self.setUp()
            if reason == 'generation':
                self.api.load_config.side_effect = [self.config, {**self.config, 'generation': 6}]
            else:
                self.api.plc_current_process_owns_io.side_effect = [True, False]
            self.assertIsNone(self.api.plc_capture_poll_once())
            self.api.plc_capture_disarm.assert_called_once_with('stale_read_discarded')
            self.api._plc_dispatch_slots.release.assert_called_once()
            self.api.plc_apply_capture_observation.assert_not_called()

    @unittest.skipIf(BASELINE, 'candidate assembly and dormant lifecycle')
    def test_root_binding_and_no_startup_activation(self):
        for name in NAMES:
            self.assertIs(getattr(self.api, name).__self__, self.api._legacy_plc_operations)
        self.api.load_config.assert_not_called()
        self.assertIsNot(build()._legacy_plc_operations, self.api._legacy_plc_operations)
        tree = ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py'))
        startup = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'start_plc_runtime_workers')
        self.assertEqual(len(startup.body), 1)
        self.assertEqual(ast.dump(startup.body[0]), ast.dump(ast.Return(value=ast.Constant(value=None))))


if __name__ == '__main__':
    unittest.main(verbosity=2)
