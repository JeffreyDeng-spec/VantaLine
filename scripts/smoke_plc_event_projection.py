"""Synthetic event-history contracts; no Web app, database or physical I/O needed."""
import ast
import copy
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service import plc_fx_ascii as protocol

BASELINE = os.environ.get("VANTALINE_PLC_PROJECTION_BASELINE_SOURCE")
if BASELINE:
    source = Path(BASELINE).read_text(encoding="utf-8-sig")
    names = {"PlcDispatchStateConflict", "PLC_REDUCER_DERIVED_FIELDS",
             "PLC_FINALIZE_REASONS", "project_plc_dispatch_events"}
    nodes = [n for n in ast.parse(source).body
             if (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names)
             or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))]
    assert len(nodes) == 4
    projection = types.ModuleType("baseline_projection")
    projection.__dict__.update(copy=copy, Any=object,
        PLC_TERMINAL_ALLOWED_PHASES=protocol.PLC_TERMINAL_ALLOWED_PHASES,
        PLC_TERMINAL_DIAGNOSTIC_SOURCES=protocol.PLC_TERMINAL_DIAGNOSTIC_SOURCES,
        PlcTerminalResultCode=protocol.PlcTerminalResultCode,
        PlcTransportPhase=protocol.PlcTransportPhase,
        plc_terminal_result_is_retryable=protocol.plc_terminal_result_is_retryable)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, "exec"), projection.__dict__)
else:
    from local_inspection_service.plc import event_projection as projection


def record(targets=("D206",), retries=0):
    return {"dispatch_id": "dispatch", "planned_targets": list(targets),
            "planned_frames": [{"target": target, "frame_hex": "0203"} for target in targets],
            "config_snapshot": {"retries": retries, "nested": ["preserved"]},
            "status": "untrusted", "operations": [{"outcome": "untrusted"}]}


def event_stream(items):
    return [{"seq": i, "at": 100 + i, **item} for i, item in enumerate(items, 1)]


def ack_items(target="D206", attempt=1):
    identity = f"dispatch:{target}:{attempt}"
    return [
        {"kind": "start_attempt", "target": target, "attempt_id": identity},
        {"kind": "advance_attempt", "attempt_id": identity, "bytes_written": 0,
         "physical_status": "write_call_started", "outcome": "write_outcome_uncertain"},
        {"kind": "advance_attempt", "attempt_id": identity, "bytes_written": 2,
         "physical_status": "full_frame_written", "outcome": "awaiting_acknowledgement"},
        {"kind": "finish_attempt", "attempt_id": identity, "bytes_written": 2,
         "result_code": "acknowledged", "result_phase": "response", "diagnostic_source": "ack_byte"},
    ]


def stream(*tail):
    return event_stream([{"kind": "create"}, {"kind": "attempting"}, *tail])


class ProjectionContract(unittest.TestCase):
    def project(self, rec, events):
        before = copy.deepcopy((rec, events))
        try:
            return projection.project_plc_dispatch_events(rec, events)
        finally:
            self.assertEqual((rec, events), before, "projection mutated caller evidence")

    def rejected(self, rec, events, reason):
        with self.assertRaises(projection.PlcDispatchStateConflict) as caught:
            self.project(rec, events)
        self.assertEqual(caught.exception.reason, "corrupt_persisted_dispatch:" + reason)
        self.assertEqual(caught.exception.authoritative, rec)
        self.assertIsNot(caught.exception.authoritative, rec)

    def test_queued_discards_derived_fields_and_deep_copies(self):
        rec, events = record(), event_stream([{"kind": "create"}])
        value = self.project(rec, events)
        self.assertEqual(value["status"], "queued")
        self.assertNotIn("operations", value)
        self.assertNotIn("attempt_ids", value)
        value["config_snapshot"]["nested"].append("changed")
        value["events"][0]["at"] = 0
        self.assertEqual(rec["config_snapshot"]["nested"], ["preserved"])
        self.assertEqual(events[0]["at"], 101)

    def test_acknowledged_evidence_and_blank_y(self):
        value = self.project(record(), stream(*ack_items(), {"kind": "finalize", "reason": ""}))
        self.assertEqual(value["status"], "acknowledged")
        self.assertEqual(value["targets"], ["D206"])
        self.assertEqual(value["frames"], [{"target": "D206", "frame_hex": "0203", "attempts": 1}])
        self.assertTrue(value["worker_done"])
        self.assertEqual([row["status"] for row in value["history"]], ["queued", "attempting", "sent", "acknowledged"])

    def test_d_ack_before_y_and_partial_failure(self):
        items = ack_items() + ack_items("Y04")
        items[-1].update(result_code="timeout", result_phase="read", diagnostic_source="empty_read")
        value = self.project(record(("D206", "Y04")), stream(*items, {"kind": "finalize", "reason": ""}))
        self.assertEqual(value["status"], "failed")
        self.assertEqual(value["targets"], ["D206"])
        self.assertEqual(value["failed_target"], "Y04")
        self.assertEqual(value["outcome"], "partial_failure")
        self.assertTrue(value["no_automatic_retry"])
        self.rejected(record(("D206", "Y04")), stream(ack_items("Y04")[0]), "attempt_target_order_invalid")

    def test_create_schema(self):
        self.rejected(record(), [], "create_event_missing")
        for event in ({"seq": True, "kind": "create", "at": 1},
                      {"seq": 1, "kind": "create", "at": True},
                      {"seq": 1, "kind": "create", "at": -1},
                      {"seq": 1, "kind": "create", "at": 1, "extra": 1}):
            with self.subTest(event=event):
                self.rejected(record(), [event], "create_event_invalid")

    def test_sequence_time_schema_and_terminal_fences(self):
        for key, value, reason in (("seq", True, "event_sequence_invalid"),
                                   ("seq", 3, "event_sequence_invalid"),
                                   ("at", True, "event_sequence_invalid"),
                                   ("at", 100, "event_time_regression")):
            events = stream()
            events[1][key] = value
            self.rejected(record(), events, reason)
        self.rejected(record(), stream({"kind": "unknown"}), "unknown_event_kind")
        self.rejected(record(), stream({"kind": "attempting"}), "attempting_event_invalid")
        self.rejected(record(), stream({"kind": "finalize", "reason": "disabled"}, {"kind": "deadline"}), "event_after_terminal")

    def test_attempt_identity_order_and_inflight_duplicate(self):
        item = ack_items()[0]
        self.rejected(record(), stream({**item, "attempt_id": "forged"}), "attempt_sequence_invalid")
        self.rejected(record(), stream({**item, "extra": 1}), "start_event_schema_invalid")
        self.rejected(record(retries=1), stream(item, {**item, "attempt_id": "dispatch:D206:2"}), "retry_chain_invalid")
        self.rejected(record(), stream(*ack_items(), ack_items()[0]), "attempt_target_order_invalid")

    def test_advance_rejects_forged_write_evidence(self):
        items = ack_items()
        self.rejected(record(), stream(items[1]), "advance_without_start")
        self.rejected(record(), stream(items[0], items[2]), "advance_evidence_invalid")
        for count in (True, -1, 3):
            self.rejected(record(), stream(*items[:2], {**items[2], "bytes_written": count}), "advance_evidence_invalid")

    def test_terminal_schema_evidence_and_diagnostic(self):
        items = ack_items()
        self.rejected(record(), stream(items[-1]), "finish_without_start")
        self.rejected(record(), stream(*items, items[-1]), "finish_without_start")
        self.rejected(record(), stream(*items[:1], {**items[-1], "bytes_written": 0}), "ack_evidence_invalid")
        for patch in ({"extra": 1}, {"result_code": "invented"}, {"bytes_written": True},
                      {"result_phase": "open"}, {"diagnostic_source": "nak_byte"}):
            reason = "finish_event_schema_invalid" if "extra" in patch else "terminal_result_invalid"
            self.rejected(record(), stream(*items[:-1], {**items[-1], **patch}), reason)

    def test_unknown_write_retains_uncertainty(self):
        items = ack_items()
        finish = {**items[-1], "bytes_written": 0, "result_code": "write_result_unknown",
                  "result_phase": "write", "diagnostic_source": "write_returned_none"}
        value = self.project(record(), stream(*items[:2], finish, {"kind": "finalize", "reason": ""}))
        self.assertEqual(value["status"], "failed")
        self.assertEqual(value["outcome"], "write_outcome_uncertain")
        self.rejected(record(retries=1), stream(*items[:2], finish, ack_items(attempt=2)[0]), "retry_chain_invalid")

    def test_legacy_retry_policy_is_preserved_only_in_history(self):
        items = ack_items()
        items[-1].update(result_code="timeout", result_phase="read", diagnostic_source="empty_read")
        self.rejected(record(retries=1), stream(*items, {"kind": "finalize", "reason": ""}), "retry_budget_not_exhausted")
        value = self.project(record(retries=1), stream(*items, *ack_items(attempt=2), {"kind": "finalize", "reason": ""}))
        self.assertEqual(value["status"], "acknowledged")
        # Historical aggregate retains the failed prior attempt even after an ACK.
        self.assertEqual(value["attempts"], 1)
        self.assertEqual([item["attempt"] for item in value["operations"]], [1, 2])

    def test_deadline_then_late_ack_with_deadline_finalization(self):
        items = ack_items()
        value = self.project(record(), stream(*items[:3], {"kind": "deadline"}))
        self.assertEqual(value["status"], "failed")
        self.assertTrue(value["provisional"])
        self.assertTrue(value["worker_continues"])
        value = self.project(record(), stream(*items[:3], {"kind": "deadline"}, items[-1],
                                              {"kind": "finalize", "reason": "deadline_exceeded"}))
        self.assertEqual(value["status"], "failed")
        self.assertTrue(value["deadline_exceeded"])
        self.assertFalse(value["provisional"])
        self.assertTrue(value["worker_done"])

    def test_finalize_requires_finished_evidence(self):
        self.rejected(record(), stream(ack_items()[0], {"kind": "finalize", "reason": "disabled"}), "finalize_event_invalid")
        self.rejected(record(), stream({"kind": "finalize", "reason": ""}), "finalize_without_terminal_evidence")
        self.rejected(record(), stream({"kind": "finalize", "reason": "arbitrary"}), "finalize_event_invalid")
        value = self.project(record(), stream({"kind": "finalize", "reason": "disabled"}))
        self.assertEqual(value["status"], "disabled")
        self.assertFalse(value["attempted"])

    @unittest.skipIf(BASELINE, "candidate import boundary")
    def test_import_is_lightweight_and_entry_keeps_same_symbols(self):
        child = "import sys; from local_inspection_service.plc import event_projection; assert not any(n in sys.modules for n in ('local_inspection_service.server', 'fastapi', 'psycopg', 'serial'))"
        subprocess.run([sys.executable, "-c", child], cwd=ROOT, check=True, timeout=10)
        tree = ast.parse((ROOT / "local_inspection_service/server.py").read_text(encoding="utf-8"))
        expected = {"PlcDispatchStateConflict", "PLC_REDUCER_DERIVED_FIELDS", "PLC_FINALIZE_REASONS", "project_plc_dispatch_events"}
        bindings = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module in ("plc.event_projection", "plc.errors")]
        actual = {a.name for n in bindings for a in n.names if a.asname is None}
        self.assertEqual(actual, expected)
        self.assertFalse(any(isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in expected for n in tree.body))


if __name__ == "__main__":
    unittest.main()
