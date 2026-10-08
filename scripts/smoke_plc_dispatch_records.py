"""Retained PLC record lookup and evidence projection; no physical transport."""
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.plc.errors import PlcDispatchStateConflict
BASELINE = os.environ.get('VANTALINE_PLC_DISPATCH_RECORDS_BASELINE_SOURCE')
NAMES = {'plc_dispatch_audit_records', 'raw_plc_namespace', 'plc_config_audit_snapshot',
         'plc_dispatch_existing', 'get_validated_idempotent_dispatch', 'plc_dispatch_conflict_response'}


def build():
    source = Path(BASELINE) if BASELINE else ROOT / 'local_inspection_service/server.py'
    nodes = []
    for node in ast.parse(source.read_text(encoding='utf-8-sig')).body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.ImportFrom) and node.module == 'plc.legacy_records':
            nodes.append(node)
        elif not BASELINE and isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in NAMES | {'_legacy_plc_records'} for t in node.targets
        ):
            nodes.append(node)
    target = ModuleType('local_inspection_service._legacy_records_contract')
    target.__package__ = 'local_inspection_service'
    target.__dict__.update(Any=Any, hashlib=hashlib, json=json, PlcDispatchStateConflict=PlcDispatchStateConflict)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), target.__dict__)
    return target


class DispatchRecordsContract(unittest.TestCase):
    def setUp(self):
        self.api = build()
        self.config = {}
        self.api.load_config = Mock(side_effect=lambda: self.config)
        self.api.public_path_sanitized = Mock(side_effect=lambda value: value)
        self.api.PLC_CONFIG_ABSENT = object()
        self.api._config_io_lock = threading.RLock()
        self.api.time = SimpleNamespace(time=lambda: 41.9)
        self.api.verify_persisted_plc_dispatch = Mock(side_effect=lambda record: record)

    def test_list_filter_shallow_copy_and_explicit_empty_config(self):
        nested = {'evidence': [1]}
        record = {'dispatch_id': 'id', 'nested': nested}
        self.config['plc_dispatches'] = [None, 'wrong', record, {}, 7]
        result = self.api.plc_dispatch_audit_records()
        self.assertEqual(result, [record, {}])
        self.assertIsNot(result[0], record)
        self.assertIs(result[0]['nested'], nested)
        self.api.load_config.reset_mock()
        self.assertEqual(self.api.plc_dispatch_audit_records({}), [])
        self.api.load_config.assert_not_called()
        for value in (None, [], False):
            self.assertEqual(len(self.api.plc_dispatch_audit_records(value)), 2)
        self.config['plc_dispatches'] = ({'dispatch_id': 'tuple'},)
        self.assertEqual(self.api.plc_dispatch_audit_records(), [])

    def test_namespace_absence_malformed_and_sanitizer_copy(self):
        absent = self.api.PLC_CONFIG_ABSENT
        self.assertIs(self.api.raw_plc_namespace({}), absent)
        self.assertIsNone(self.api.raw_plc_namespace({'plc': None}))
        self.assertEqual(self.api.plc_config_audit_snapshot({}), {'namespace_present': False, 'enabled': False})
        for value in (None, [], '', False, 0):
            self.assertEqual(self.api.plc_config_audit_snapshot({'plc': value}),
                             {'namespace_present': True, 'namespace_valid': False, 'value_type': type(value).__name__})
        value = {'nested': []}
        result = self.api.plc_config_audit_snapshot({'plc': value})
        self.assertEqual(result, value)
        self.assertIsNot(result, value)
        self.assertIs(result['nested'], value['nested'])
        self.api.public_path_sanitized.assert_called_once()

    def test_reverse_lookup_preserves_last_matching_record(self):
        first, last = {'dispatch_id': 'same', 'n': 1}, {'dispatch_id': 'same', 'n': 2}
        self.config['plc_dispatches'] = [first, last, {'dispatch_id': 9}, {'dispatch_id': None}]
        self.assertEqual(self.api.plc_dispatch_existing('same'), last)
        self.assertEqual(self.api.plc_dispatch_existing('9'), {'dispatch_id': 9})
        self.assertEqual(self.api.plc_dispatch_existing(''), {'dispatch_id': None})
        self.assertIsNone(self.api.plc_dispatch_existing('absent'))

    def test_exact_hash_guard_and_verification_after_release(self):
        record = {'source': 'camera', 'request_id': 'r', 'passed': True, 'detection_identity': 'fp'}
        seen = []
        guard = self.api._config_io_lock
        def guard_available():
            acquired = guard.acquire(timeout=1)
            if acquired:
                guard.release()
            return acquired
        def lookup(identity):
            with ThreadPoolExecutor(1) as pool:
                self.assertFalse(pool.submit(guard_available).result(timeout=2))
            seen.append(identity)
            return record
        def verify(value):
            with ThreadPoolExecutor(1) as pool:
                self.assertTrue(pool.submit(guard_available).result(timeout=2))
            self.assertIs(value, record)
            return record
        self.api.plc_dispatch_existing = lookup
        self.api.verify_persisted_plc_dispatch = verify
        result = self.api.get_validated_idempotent_dispatch(source=' camera ', request_id='r', passed=True, fingerprint='fp')
        self.assertIs(result, record)
        material = json.dumps({'source': 'camera', 'request_id': 'r', 'fingerprint': 'fp'}, sort_keys=True, ensure_ascii=True)
        self.assertEqual(seen, [hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]])

    def test_missing_strict_identity_conflict_and_exception_release(self):
        self.api.plc_dispatch_existing = Mock(return_value=None)
        self.assertIsNone(self.api.get_validated_idempotent_dispatch(source='camera', request_id='r', passed=True, fingerprint='fp'))
        self.api.verify_persisted_plc_dispatch.assert_not_called()
        original = {'source': 'camera', 'request_id': 'r', 'passed': True, 'detection_identity': 'fp'}
        for field, value in (('source', 'video'), ('request_id', 'other'), ('passed', 1), ('detection_identity', 'other')):
            record = {**original, field: value}
            self.api.plc_dispatch_existing = Mock(return_value=record)
            with self.assertRaises(PlcDispatchStateConflict) as caught:
                self.api.get_validated_idempotent_dispatch(source='camera', request_id='r', passed=True, fingerprint='fp')
            self.assertEqual(caught.exception.reason, 'create_dispatch_identity_conflict')
            self.assertEqual(caught.exception.authoritative, record)
        error = RuntimeError('lookup failed')
        self.api.plc_dispatch_existing = Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:
            self.api.get_validated_idempotent_dispatch(source='camera', request_id='r', passed=True, fingerprint='fp')
        self.assertIs(caught.exception, error)
        def take():
            lock = self.api._config_io_lock
            acquired = lock.acquire(timeout=1)
            if acquired:
                lock.release()
            return acquired
        with ThreadPoolExecutor(1) as pool:
            self.assertTrue(pool.submit(take).result(timeout=2))

    def test_late_verifier_and_conflict_payload_retains_nested_evidence(self):
        record = {'source': 'camera', 'request_id': 'r', 'passed': True, 'detection_identity': 'fp'}
        verifier = Mock(return_value=record)
        def lookup(identity):
            self.api.verify_persisted_plc_dispatch = verifier
            return record
        self.api.plc_dispatch_existing = lookup
        self.api.get_validated_idempotent_dispatch(source='camera', request_id='r', passed=True, fingerprint='fp')
        verifier.assert_called_once_with(record)
        evidence = []
        conflict = PlcDispatchStateConflict('reason', {'status': 'passed', 'attempted': [1], 'nested': evidence, 'worker_continues': True})
        result = self.api.plc_dispatch_conflict_response(conflict, dispatch_id='id', source='camera', request_id='r', passed=False)
        self.assertEqual(result['status'], 'failed')
        self.assertIs(result['attempted'], True)
        self.assertFalse(result['duplicate'])
        self.assertTrue(result['worker_done'])
        self.assertFalse(result['worker_continues'])
        self.assertEqual(result['updated_at'], 41)
        self.assertEqual(result['error_code'], 'reason')
        self.assertIs(result['nested'], evidence)
        self.assertEqual(conflict.authoritative['status'], 'passed')

    @unittest.skipIf(BASELINE, 'candidate root binding')
    def test_actual_root_binding_and_instance_isolation(self):
        for name in NAMES:
            self.assertIs(getattr(self.api, name).__self__, self.api._legacy_plc_records)
        self.assertIsNot(build()._legacy_plc_records, self.api._legacy_plc_records)
        self.api.load_config.assert_not_called()
        self.api.public_path_sanitized.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
