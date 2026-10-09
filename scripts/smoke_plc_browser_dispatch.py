"""Replay camera plan, at-most-once declaration and browser receipt contracts."""
import ast
import copy
import hashlib
import hmac
import inspect
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service import plc_web_serial as protocol
from local_inspection_service.plc_fx_ascii import PlcConfigError

NAMES = {"plc_web_serial_begin_camera_detection", "plc_web_serial_finish_camera_detection",
         "plc_web_serial_dispatch_public", "verify_plc_web_serial_dispatch",
         "plc_web_serial_declare_attempt", "_plc_web_serial_receipt_outcome", "plc_web_serial_record_receipt"}
BASELINE = os.environ.get("VANTALINE_PLC_BROWSER_DISPATCH_BASELINE_SOURCE")


def load_target():
    source = Path(BASELINE) if BASELINE else Path(__file__).resolve().parents[1] / "local_inspection_service/server.py"
    nodes = []
    raw = source.read_text(encoding="utf-8-sig")
    if not BASELINE:
        from application_integration_source_contract import verify_actual_compositions, restore_delta, PLC_WORKSTATION
        verify_actual_compositions()
        raw = restore_delta(raw, PLC_WORKSTATION)
    for n in ast.parse(raw).body:
        if isinstance(n, ast.FunctionDef) and n.name in NAMES:
            nodes.append(n)
        elif not BASELINE and isinstance(n, ast.ImportFrom) and n.module in {"plc.browser_dispatch", "plc.browser_dispatch_ports"}:
            nodes.append(n)
        elif not BASELINE and isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_plc_browser_dispatch" for t in n.targets):
            nodes.append(n)
    assert {n.name for n in nodes if isinstance(n, ast.FunctionDef)} == NAMES
    target = types.ModuleType("local_inspection_service._browser_dispatch_contract")
    target.__package__ = "local_inspection_service"
    target.__dict__.update(Any=object, PlcWebSerialAttemptRequest=object, PlcWebSerialReceiptRequest=object,
                          copy=copy, hashlib=hashlib, hmac=hmac, json=json, math=math, re=re, secrets=secrets, time=time)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), target.__dict__)
    return target


class BrowserDispatchContracts(unittest.TestCase):
    def setUp(self):
        self.api = load_target()
        self.calls = []
        self.state = {"station": {"id": "station", "config_generation": 3, "config": dict(protocol.DEFAULT_WEB_SERIAL_CONFIG)},
                      "lease": {"session_id": "session", "lease_epoch": 7, "expires_at": 130, "model_id": "model", "state": "active"},
                      "clock": {"now": 100}, "dispatch": None}
        def mutate(station_id, dispatch_id, callback):
            self.calls.append((station_id, dispatch_id))
            draft = copy.deepcopy(self.state)
            callback(draft)
            self.state = draft
            return draft
        def active(state, session_id, lease_epoch=None):
            self.assertEqual(session_id, "session")
            if lease_epoch is not None: self.assertEqual(lease_epoch, 7)
            return state["station"], state["lease"], state["clock"]["now"]
        self.api.__dict__.update(PlcConfigError=PlcConfigError, PLC_PROTOCOL_ID=protocol.PROTOCOL_ID,
            _plc_web_serial_mutate=mutate, _plc_web_serial_record=lambda row: row,
            _plc_web_serial_dispatch_row=lambda row: row, _plc_workstation_lease_row=lambda row: row,
            _plc_web_serial_require_active_lease=active,
            _plc_web_serial_token_hash=lambda token: hashlib.sha256(token.encode()).hexdigest())
        for name in ("LEGACY_WEB_SERIAL_PROTOCOL_VERSION", "WEB_SERIAL_PROTOCOL_VERSION", "WEB_SERIAL_PLAN_DEADLINE_SECONDS",
                     "build_legacy_web_serial_plan", "build_web_serial_plan", "normalize_legacy_web_serial_config",
                     "normalize_web_serial_config", "migrate_web_serial_config", "legacy_web_serial_config_fingerprint", "web_serial_config_fingerprint"):
            setattr(self.api, name, getattr(protocol, name))

    def begin(self):
        return self.api.plc_web_serial_begin_camera_detection("station", "session", "request-001", "model", "fingerprint")

    def plan(self):
        record, _ = self.begin()
        return self.api.plc_web_serial_finish_camera_detection("station", record["dispatch_id"], "session", {"passed": True, "detail": [1]})

    def declare(self):
        record = self.plan()
        request = types.SimpleNamespace(session_id="session", lease_epoch=7, config_generation=3)
        with patch("secrets.token_urlsafe", return_value="attempt-token"):
            return self.api.plc_web_serial_declare_attempt("station", record["dispatch_id"], request)

    def receipt(self, status="acknowledged", response="06", outcome=""):
        record = self.state["dispatch"]
        operations = [dict(target=f["target"], frame_sha256=f["frame_sha256"], status=status, response_hex=response) for f in record["frames"]]
        return types.SimpleNamespace(session_id="session", lease_epoch=7, attempt_token="attempt-token", outcome=outcome,
            operations=[types.SimpleNamespace(model_dump=lambda item=item: dict(item)) for item in operations])

    def test_admission_identity_duplicate_and_error_priority(self):
        with self.assertRaisesRegex(PlcConfigError, "invalid_camera_request_id"):
            self.api.plc_web_serial_begin_camera_detection("station", "session", "bad", "model", "fingerprint")
        self.assertEqual(self.calls, [])
        record, created = self.begin()
        self.assertTrue(created)
        expected = "plcweb_" + hashlib.sha256(b"station:request-001").hexdigest()[:32]
        self.assertEqual(record["dispatch_id"], expected)
        self.assertEqual(self.state["lease"]["in_flight_deadline_at"], 130)
        replay, created = self.begin()
        self.assertFalse(created)
        self.assertEqual(replay, record)
        with self.assertRaisesRegex(PlcConfigError, "plc_camera_request_payload_conflict"):
            self.api.plc_web_serial_begin_camera_detection("station", "session", "request-001", "model", "different")
        self.state["lease"]["in_flight_dispatch_id"] = "other"
        with self.assertRaisesRegex(PlcConfigError, "plc_workstation_attempt_in_flight"):
            self.begin()

    def test_detection_failure_and_immutable_success_result(self):
        record, _ = self.begin()
        result = {"passed": True, "nested": [1]}
        planned = self.api.plc_web_serial_finish_camera_detection("station", record["dispatch_id"], "session", result)
        result["nested"].append(2)
        self.assertEqual(planned["result"]["nested"], [1])
        self.assertEqual(len(planned["frames"]), 1)  # Blank Y has no operation.
        self.assertEqual(planned["status"], "planned")
        self.assertEqual(self.api.plc_web_serial_finish_camera_detection("station", record["dispatch_id"], "session", None, "late"), planned)
        self.state["dispatch"]["status"] = "detecting"
        failed = self.api.plc_web_serial_finish_camera_detection("station", record["dispatch_id"], "session", None, "e" * 200)
        self.assertEqual(failed["error_code"], "e" * 120)
        self.assertNotIn("in_flight_dispatch_id", self.state["lease"])

    def test_plan_tampering_and_old_generation_projection(self):
        record = self.plan()
        station = self.state["station"]
        self.api.verify_plc_web_serial_dispatch(record, station)
        for field, value, message in (("dispatch_id", "bad", "identity_invalid"), ("source", "upload", "source_invalid"),
                                      ("passed", 1, "passed_invalid"), ("frames", [], "frames_invalid"), ("targets", [], "targets_invalid")):
            bad = copy.deepcopy(record); bad[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(PlcConfigError, message):
                self.api.verify_plc_web_serial_dispatch(bad, station)
        station["config_generation"] = 4
        with self.assertRaisesRegex(PlcConfigError, "generation_invalid"):
            self.api.verify_plc_web_serial_dispatch(record, station)
        self.api.verify_plc_web_serial_dispatch(record, station, require_current_config=False)

    def test_declaration_persists_before_projection_and_rejects_repeat(self):
        planned = self.plan()
        request = types.SimpleNamespace(session_id="session", lease_epoch=7, config_generation=3)
        self.api.plc_web_serial_dispatch_public = lambda record: (_ for _ in ()).throw(ValueError("projection"))
        with patch("secrets.token_urlsafe", return_value="attempt-token"):
            with self.assertRaisesRegex(ValueError, "projection"):
                self.api.plc_web_serial_declare_attempt("station", planned["dispatch_id"], request)
        record = self.state["dispatch"]
        self.assertEqual(record["status"], "browser_attempt_declared")
        self.assertEqual(record["deadline_at"], 102)
        self.assertEqual(record["attempt_token_hash"], hashlib.sha256(b"attempt-token").hexdigest())
        self.assertNotIn("attempt_token", record)
        with self.assertRaisesRegex(PlcConfigError, "already_declared"):
            self.api.plc_web_serial_declare_attempt("station", planned["dispatch_id"], request)

    def test_receipt_idempotence_conflict_and_late_ack_cannot_replace_uncertain(self):
        declared = self.declare()
        request = self.receipt()
        self.state["lease"]["state"] = "draining"
        result = self.api.plc_web_serial_record_receipt("station", declared["dispatch_id"], request)
        self.assertEqual(result["outcome"], "acknowledged")
        self.assertEqual(self.state["lease"]["state"], "released")
        self.assertEqual(self.api.plc_web_serial_record_receipt("station", declared["dispatch_id"], request), result)
        with self.assertRaisesRegex(PlcConfigError, "receipt_conflict"):
            self.api.plc_web_serial_record_receipt("station", declared["dispatch_id"], self.receipt("timeout", ""))
        self.state["dispatch"].update(status="uncertain", outcome="uncertain", receipt_fingerprint="")
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(PlcConfigError, "receipt_conflict"):
            self.api.plc_web_serial_record_receipt("station", declared["dispatch_id"], request)
        self.assertEqual(self.state, before)

    def test_ack_evidence_d_before_y_and_partial_normalization(self):
        frames = [{"target": "D", "frame_sha256": "d"}, {"target": "Y", "frame_sha256": "y"}]
        def ops(first, second=None):
            statuses = [first] + ([second] if second else [])
            return [dict(frames[i], status=status, response_hex={"acknowledged": "06", "nak": "15"}.get(status, "")) for i, status in enumerate(statuses)]
        self.assertEqual(self.api._plc_web_serial_receipt_outcome(frames, []), "uncertain")
        self.assertEqual(self.api._plc_web_serial_receipt_outcome(frames, ops("acknowledged")), "uncertain")
        self.assertEqual(self.api._plc_web_serial_receipt_outcome(frames, ops("acknowledged", "nak")), "partial_success")
        self.assertEqual(self.api._plc_web_serial_receipt_outcome(frames, ops("nak")), "rejected")
        with self.assertRaisesRegex(PlcConfigError, "y_without_d_ack"):
            self.api._plc_web_serial_receipt_outcome(frames, ops("nak", "acknowledged"))
        bad = ops("acknowledged"); bad[0]["response_hex"] = "15"
        with self.assertRaisesRegex(PlcConfigError, "ack_evidence_invalid"):
            self.api._plc_web_serial_receipt_outcome(frames, bad)
        extra = ops("acknowledged", "acknowledged") + [dict(frames[0])]
        with self.assertRaisesRegex(PlcConfigError, "extra_operations"):
            self.api._plc_web_serial_receipt_outcome(frames, extra)

    def test_receipt_token_error_precedes_operation_conversion(self):
        declared = self.declare()
        request = self.receipt(); request.attempt_token = "wrong"
        request.operations = [types.SimpleNamespace(model_dump=lambda: self.fail("invalid token reached operation"))]
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(PlcConfigError, "attempt_token_invalid"):
            self.api.plc_web_serial_record_receipt("station", declared["dispatch_id"], request)
        self.assertEqual(self.state, before)

    @unittest.skipIf(BASELINE, "candidate assembly only")
    def test_21_late_ports_and_seven_actual_root_forwarders(self):
        service = self.api._plc_browser_dispatch
        count = 0
        for group in (service.storage, service.identity, service.policy, service.projection):
            for name in group.__dataclass_fields__:
                a, b = object(), object()
                for value in (a, b, a):
                    setattr(self.api, name, value)
                    self.assertIs(getattr(group, name)(), value)
                count += 1
        self.assertEqual(count, 21)
        api = load_target(); calls = []; result = object()
        class Fake:
            def __getattr__(self, name):
                return lambda *args, **kwargs: calls.append((name, args, kwargs)) or result
        api._plc_browser_dispatch = Fake()
        for name in NAMES:
            fn = getattr(api, name); args = []; kwargs = {}
            for parameter in inspect.signature(fn).parameters.values():
                if parameter.kind == parameter.KEYWORD_ONLY: kwargs[parameter.name] = object()
                else: args.append(object())
            self.assertIs(fn(*args, **kwargs), result)
            self.assertEqual(calls[-1], (name, tuple(args), kwargs))


if __name__ == "__main__":
    unittest.main()
