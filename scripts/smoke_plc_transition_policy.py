"""Pure historical evidence-transition regression; no physical dispatch."""
import ast
import copy
from enum import Enum
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from smoke_plc_event_projection import record, stream, ack_items
from local_inspection_service.plc.event_projection import project_plc_dispatch_events
from local_inspection_service.plc.errors import PlcDispatchStateConflict
from local_inspection_service.plc_fx_ascii import plc_terminal_result_is_retryable

BASELINE = os.environ.get("VANTALINE_PLC_TRANSITION_BASELINE_SOURCE")
if BASELINE:
    source = Path(BASELINE).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    first = next(n.lineno for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PLC_DISPATCH_STATE_ORDER" for t in n.targets))
    last = next(n.end_lineno for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "validate_plc_dispatch_transition")
    nodes = [n for n in tree.body if first <= n.lineno <= last]
    policy = types.ModuleType("baseline_policy")
    policy.__dict__.update(Any=object, Enum=Enum, json=json, PlcDispatchStateConflict=PlcDispatchStateConflict,
                           plc_terminal_result_is_retryable=plc_terminal_result_is_retryable)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, "exec"), policy.__dict__)
else:
    from local_inspection_service.plc import transition_policy as policy


class TransitionContract(unittest.TestCase):
    def validate(self, before, after, kind="RECORD_UPDATE"):
        original = copy.deepcopy((before, after))
        try:
            return policy.validate_plc_dispatch_transition(before, after,
                transition_kind=getattr(policy.PlcDispatchTransitionKind, kind, kind))
        finally:
            self.assertEqual((before, after), original)

    def rejected(self, before, after, reason, kind="RECORD_UPDATE"):
        with self.assertRaises(PlcDispatchStateConflict) as error:
            self.validate(before, after, kind)
        self.assertEqual(error.exception.reason, reason)
        self.assertEqual(error.exception.authoritative, before)

    def projected(self, events):
        return project_plc_dispatch_events(record(), events)

    def test_real_projected_event_chain(self):
        events = stream(*ack_items(), {"kind": "finalize", "reason": ""})
        transitions = {"attempting": "DISPATCH_TRANSITION", "start_attempt": "START_ATTEMPT",
                       "advance_attempt": "ADVANCE_ATTEMPT", "finish_attempt": "FINISH_ATTEMPT", "finalize": "FINALIZE"}
        for index in range(1, len(events)):
            with self.subTest(event=events[index]["kind"], index=index):
                self.validate(self.projected(events[:index]), self.projected(events[:index+1]), transitions[events[index]["kind"]])

    def test_record_metadata_update_and_unknown_transition(self):
        before = self.projected(stream()[:1])
        self.validate(before, {**before, "message": "local evidence"})
        self.rejected(before, before, "unknown_transition_kind", "unknown")
        self.validate({}, {"arbitrary": True})  # Create validation belongs to its own boundary.

    def test_bound_identity_cannot_change_even_equal_python_values(self):
        before = self.projected(stream()[:1])
        before["control_generation"] = 1
        before["state_version"] = 1
        for key, value in (("dispatch_id", "other"), ("control_generation", True),
                           ("config_snapshot", {"retries": 2}), ("planned_targets", [])):
            self.rejected(before, {**before, key: value}, "immutable_identity_conflict:"+key)
        self.rejected(before, {**before, "state_version": 2}, "immutable_bound_field_conflict:state_version")

    def test_unknown_legacy_field_retained_and_new_field_denied(self):
        before = self.projected(stream()[:1])
        before["legacy_marker"] = {"x": [1]}
        self.validate(before, copy.deepcopy(before))
        for after in ({k:v for k,v in before.items() if k != "legacy_marker"},
                      {**before, "legacy_marker": {"x": [True]}}):
            self.rejected(before, after, "legacy_unknown_field_is_immutable:legacy_marker")
        self.rejected(before, {**before, "invented": 1}, "unknown_field_addition:invented")

    def test_known_evidence_cannot_be_deleted(self):
        before = self.projected(stream()[:1])
        for key in ("status", "history", "worker_done", "planned_frames"):
            after = copy.deepcopy(before); del after[key]
            self.rejected(before, after, "known_field_cannot_be_deleted:"+key)

    def test_transition_cannot_smuggle_physical_projection(self):
        before = self.projected(stream()[:1])
        self.rejected(before, {**before, "target": "Y04"}, "transition_projection_field_not_allowed:target")
        self.rejected(before, {**before, "physical_status": "acknowledged"}, "transition_projection_field_not_allowed:physical_status", "FINISH_ATTEMPT")

    def test_terminal_evidence_is_frozen(self):
        before = self.projected(stream(*ack_items(), {"kind": "finalize", "reason": ""}))
        self.validate(before, {**before, "message": "audit note"})
        self.rejected(before, {**before, "status": "failed"}, "terminal_state_is_immutable", "FINALIZE")
        self.rejected(before, {**before, "outcome": "not_attempted"}, "terminal_physical_projection_is_immutable:outcome", "FINALIZE")
        after = copy.deepcopy(before); after["history"].append({"status":"acknowledged","at":999})
        self.rejected(before, after, "terminal_physical_projection_is_immutable:history", "FINALIZE")

    def test_history_prefix_and_order_preserved(self):
        before = self.projected(stream())
        self.rejected(before, {**before, "status": "queued"}, "nonterminal_state_regression", "DISPATCH_TRANSITION")
        after = copy.deepcopy(before); after["history"][0]["at"] = 0
        self.rejected(before, after, "history_evidence_cannot_be_deleted_or_changed", "DISPATCH_TRANSITION")
        after = copy.deepcopy(before); after["history"].append({"status":"sent","at":103})
        self.rejected(before, after, "history_transition_entry_invalid", "DISPATCH_TRANSITION")

    def test_no_forged_provisional_or_active_attempts(self):
        before = self.projected(stream())
        self.rejected(before, {**before, "provisional": True}, "provisional_state_requires_timeout_snapshot", "DEADLINE")
        self.rejected(before, {**before, "active_attempts": ["forged"]}, "active_attempts_is_runtime_derived", "DEADLINE")

    def test_operation_start_must_match_plan_and_be_declared(self):
        before = self.projected(stream())
        after = self.projected(stream(ack_items()[0]))
        operation = after["operations"][0]
        for key, value, reason in (("target", "Y04", "attempt_target_out_of_plan_or_order"),
                                  ("frame_hex", "FFFF", "attempt_frame_does_not_match_plan"),
                                  ("attempt", 2, "attempt_sequence_invalid"),
                                  ("attempt_id", "forged", "attempt_id_not_repository_derived"),
                                  ("bytes_written", 1, "attempt_start_evidence_invalid")):
            with self.subTest(key=key), self.assertRaises(PlcDispatchStateConflict) as caught:
                policy.validate_plc_attempt_start(before, after, {**operation, key:value})
            self.assertEqual(caught.exception.reason, reason)
        self.rejected(before, before, "start_attempt_did_not_create_operation", "START_ATTEMPT")

    def test_operation_evidence_monotonic_and_error_wrap(self):
        before = self.projected(stream(*ack_items()[:3]))
        operation = before["operations"][0]
        cases = (("target", "Y04", "operation_identity_conflict:target"),
                 ("bytes_written", 0, "operation_bytes_written_invalid"),
                 ("physical_status", "not_attempted", "operation_physical_status_regression"),
                 ("outcome", "not_attempted", "operation_outcome_regression"))
        for key, value, reason in cases:
            with self.subTest(key=key), self.assertRaises(PlcDispatchStateConflict) as caught:
                policy.validate_plc_operation_evidence(operation, {**operation, key:value})
            self.assertEqual(caught.exception.reason, reason)
        after = copy.deepcopy(before); after["operations"][0]["target"] = "Y04"
        self.rejected(before, after, "operation_identity_conflict:target", "ADVANCE_ATTEMPT")

    def test_finished_evidence_cannot_change(self):
        before = self.projected(stream(*ack_items()))["operations"][0]
        for key in ("result_code", "result_phase", "diagnostic_source", "finished_at"):
            with self.subTest(key=key), self.assertRaises(PlcDispatchStateConflict) as caught:
                policy.validate_plc_operation_evidence(before, {**before, key:"changed"})
            self.assertEqual(caught.exception.reason, "operation_"+key+"_cannot_be_changed")

    @unittest.skipIf(BASELINE, "candidate import boundary")
    def test_lightweight_direct_identity(self):
        child = "import sys; from local_inspection_service.plc import transition_policy; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg','serial'))"
        subprocess.run([sys.executable, "-c", child], cwd=ROOT, check=True, timeout=10)
        source = read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8')
        imports = [n for n in ast.parse(source).body if isinstance(n,ast.ImportFrom) and n.module == "plc.transition_policy" and n.level == 1]
        self.assertEqual(len(imports), 1)
        for name in ("PlcDispatchTransitionKind", "validate_plc_dispatch_transition", "validate_plc_operation_evidence", "validate_plc_attempt_start"):
            self.assertIn(name, {a.name for a in imports[0].names if a.asname is None})


if __name__ == "__main__":
    unittest.main()
