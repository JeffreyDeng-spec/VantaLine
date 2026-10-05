"""Pure preservation rules for typed historical PLC evidence transitions.

These validators never dispatch physical I/O or authorize browser retries.
"""
from enum import Enum
import json
from typing import Any

from ..plc_fx_ascii import plc_terminal_result_is_retryable
from .errors import PlcDispatchStateConflict


PLC_DISPATCH_STATE_ORDER = {"queued": 1, "attempting": 2, "sent": 3}
PLC_DISPATCH_FINAL_STATES = frozenset({"acknowledged", "failed", "disabled"})
PLC_MONOTONIC_LIST_FIELDS = ("targets", "acknowledged_targets", "frames", "attempt_ids", "events")
PLC_IMMUTABLE_BINDING_FIELDS = (
    "record_schema_version",
    "protocol_contract_version",
    "dispatch_id",
    "source",
    "request_id",
    "passed",
    "detection_identity",
    "control_generation",
    "dispatch_deadline_at_ms",
    "config_snapshot",
    "protocol",
    "checksum_mode",
    "planned_targets",
    "planned_frames",
)
PLC_DISPATCH_KNOWN_FIELDS = frozenset(
    {
        "record_schema_version", "dispatch_id", "source", "request_id", "passed", "enabled",
        "protocol_contract_version",
        "effective_enabled", "protocol", "checksum_mode", "planned_targets", "planned_frames",
        "detection_identity", "created_at", "attempted", "duplicate", "updated_at", "status",
        "dispatch_deadline_at_ms",
        "history", "message", "physical_status", "outcome", "audit_status", "error_code",
        "diagnostic_source", "target", "bytes_written", "frame_bytes", "attempts", "targets",
        "acknowledged_targets", "failed_target", "frames", "failed_operation", "operations",
        "attempt_ids", "events", "cancelled_after_disable", "cancelled_after_config_change", "deadline_exceeded",
        "no_automatic_retry", "control_generation", "config_snapshot", "state_version", "worker_done",
        "worker_continues", "worker_cleanup_pending", "active_attempts", "provisional",
        "control_state_unavailable", "namespace_present", "namespace_valid", "value_type",
    }
)
PLC_DISPATCH_IMMUTABLE_ONCE_BOUND_FIELDS = frozenset(
    {
        *PLC_IMMUTABLE_BINDING_FIELDS,
        "enabled",
        "effective_enabled",
        "created_at",
        "duplicate",
        "namespace_present",
        "namespace_valid",
        "value_type",
        "state_version",
    }
)
PLC_DISPATCH_TRANSITION_MUTABLE_FIELDS = frozenset(
    {
        "updated_at",
        "status",
        "history",
        "message",
        "attempted",
        "physical_status",
        "outcome",
        "audit_status",
        "error_code",
        "diagnostic_source",
        "target",
        "bytes_written",
        "frame_bytes",
        "attempts",
        "targets",
        "acknowledged_targets",
        "failed_target",
        "frames",
        "failed_operation",
        "operations",
        "attempt_ids",
        "events",
        "cancelled_after_disable",
        "cancelled_after_config_change",
        "deadline_exceeded",
        "no_automatic_retry",
        "worker_done",
        "worker_continues",
        "worker_cleanup_pending",
        "active_attempts",
        "provisional",
        "control_state_unavailable",
    }
)
PLC_DISPATCH_PHYSICAL_PROJECTION_FIELDS = frozenset(
    {
        "status", "history", "attempted", "physical_status", "outcome", "error_code",
        "diagnostic_source", "target", "bytes_written", "frame_bytes", "attempts", "targets",
        "acknowledged_targets", "failed_target", "frames", "failed_operation", "operations",
        "attempt_ids", "events", "cancelled_after_disable", "cancelled_after_config_change",
        "deadline_exceeded", "no_automatic_retry", "provisional", "active_attempts",
        "control_state_unavailable",
    }
)


class PlcDispatchTransitionKind(str, Enum):
    RECORD_UPDATE = "record_update"
    DISPATCH_TRANSITION = "dispatch_transition"
    START_ATTEMPT = "start_attempt"
    ADVANCE_ATTEMPT = "advance_attempt"
    FINISH_ATTEMPT = "finish_attempt"
    FINALIZE = "finalize"
    AUDIT_FAILURE_FINALIZE = "audit_failure_finalize"
    DEADLINE = "deadline"
    RECOVERY_FINALIZE = "recovery_finalize"
    CONTROL_FAILURE_FINALIZE = "control_failure_finalize"
    WORKER_FINALIZE = "worker_finalize"


PLC_TRANSITION_PROJECTION_ALLOWLIST = {
    PlcDispatchTransitionKind.RECORD_UPDATE: frozenset(),
    PlcDispatchTransitionKind.DISPATCH_TRANSITION: frozenset({"status", "history", "physical_status", "events"}),
    PlcDispatchTransitionKind.START_ATTEMPT: frozenset({"operations", "attempt_ids", "events"}),
    PlcDispatchTransitionKind.ADVANCE_ATTEMPT: frozenset(
        {"status", "history", "attempted", "physical_status", "outcome", "target", "bytes_written", "frame_bytes", "operations", "events"}
    ),
    PlcDispatchTransitionKind.FINISH_ATTEMPT: frozenset({"operations", "events"}),
    PlcDispatchTransitionKind.FINALIZE: PLC_DISPATCH_PHYSICAL_PROJECTION_FIELDS - {"active_attempts"},
    PlcDispatchTransitionKind.AUDIT_FAILURE_FINALIZE: PLC_DISPATCH_PHYSICAL_PROJECTION_FIELDS - {"active_attempts"},
    PlcDispatchTransitionKind.DEADLINE: frozenset(
        {"status", "attempted", "physical_status", "outcome", "error_code", "deadline_exceeded", "provisional", "active_attempts", "events"}
    ),
    PlcDispatchTransitionKind.RECOVERY_FINALIZE: frozenset(
        {"status", "outcome", "error_code", "provisional", "deadline_exceeded"}
    ),
    PlcDispatchTransitionKind.CONTROL_FAILURE_FINALIZE: frozenset(
        {"status", "attempted", "physical_status", "outcome", "error_code", "active_attempts", "control_state_unavailable"}
    ),
    PlcDispatchTransitionKind.WORKER_FINALIZE: frozenset({"provisional"}),
}


def _plc_canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _plc_evidence_list_contains(existing: list[Any], candidate: list[Any]) -> bool:
    for old in existing:
        if isinstance(old, dict):
            matches = [new for new in candidate if isinstance(new, dict) and all(new.get(key) == value for key, value in old.items())]
            if not matches:
                return False
        elif old not in candidate:
            return False
    return True


PLC_OPERATION_STATUS_ALLOWED = {
    "not_attempted": {"not_attempted", "write_call_started"},
    "write_call_started": {"write_call_started", "not_written", "partial_write", "full_frame_written"},
    "not_written": {"not_written"},
    "partial_write": {"partial_write"},
    "full_frame_written": {"full_frame_written", "acknowledged", "rejected"},
    "acknowledged": {"acknowledged"},
    "rejected": {"rejected"},
}
PLC_OPERATION_OUTCOME_ALLOWED = {
    "not_attempted": {"not_attempted", "write_outcome_uncertain"},
    "write_outcome_uncertain": {"write_outcome_uncertain", "not_written", "outcome_uncertain", "awaiting_acknowledgement"},
    "not_written": {"not_written"},
    "awaiting_acknowledgement": {"awaiting_acknowledgement", "acknowledged", "rejected", "outcome_uncertain"},
    "outcome_uncertain": {"outcome_uncertain"},
    "acknowledged": {"acknowledged"},
    "rejected": {"rejected"},
}
PLC_OPERATION_KNOWN_FIELDS = frozenset(
    {
        "attempt_id",
        "target",
        "attempt",
        "frame_hex",
        "frame_bytes",
        "bytes_written",
        "write_count_known",
        "reported_write_count",
        "physical_status",
        "outcome",
        "result_code",
        "result_phase",
        "diagnostic_source",
        "started_at",
        "finished_at",
    }
)


def validate_plc_operation_evidence(existing: dict[str, Any], candidate: dict[str, Any]) -> None:
    if set(candidate) - PLC_OPERATION_KNOWN_FIELDS:
        raise PlcDispatchStateConflict("operation_unknown_field")
    for field in ("attempt_id", "target", "attempt", "frame_hex", "frame_bytes", "started_at"):
        if _plc_canonical(candidate.get(field)) != _plc_canonical(existing.get(field)):
            raise PlcDispatchStateConflict(f"operation_identity_conflict:{field}")
    old_bytes = int(existing.get("bytes_written") or 0)
    new_bytes = int(candidate.get("bytes_written") or 0)
    frame_bytes = int(existing.get("frame_bytes") or 0)
    if new_bytes < old_bytes or new_bytes > frame_bytes:
        raise PlcDispatchStateConflict("operation_bytes_written_invalid")
    old_status = str(existing.get("physical_status") or "not_attempted")
    new_status = str(candidate.get("physical_status") or "not_attempted")
    if new_status not in PLC_OPERATION_STATUS_ALLOWED.get(old_status, {old_status}):
        raise PlcDispatchStateConflict("operation_physical_status_regression")
    old_outcome = str(existing.get("outcome") or "not_attempted")
    new_outcome = str(candidate.get("outcome") or "not_attempted")
    if new_outcome not in PLC_OPERATION_OUTCOME_ALLOWED.get(old_outcome, {old_outcome}):
        raise PlcDispatchStateConflict("operation_outcome_regression")
    for field in ("result_code", "result_phase", "diagnostic_source"):
        if existing.get(field) not in (None, "") and candidate.get(field) != existing.get(field):
            raise PlcDispatchStateConflict(f"operation_{field}_cannot_be_changed")
    if existing.get("finished_at") is not None and candidate.get("finished_at") != existing.get("finished_at"):
        raise PlcDispatchStateConflict("operation_finished_at_cannot_be_changed")


def validate_plc_attempt_start(existing: dict[str, Any], candidate: dict[str, Any], operation: dict[str, Any]) -> None:
    if set(operation) - PLC_OPERATION_KNOWN_FIELDS:
        raise PlcDispatchStateConflict("operation_unknown_field", existing)
    if str(existing.get("status") or "") in PLC_DISPATCH_FINAL_STATES:
        raise PlcDispatchStateConflict("terminal_dispatch_cannot_start_attempt", existing)
    required = {
        "attempt_id", "target", "attempt", "frame_hex", "frame_bytes", "bytes_written",
        "write_count_known", "reported_write_count", "physical_status", "outcome", "started_at",
    }
    if not required.issubset(operation) or set(operation) - required:
        raise PlcDispatchStateConflict("attempt_start_schema_invalid", existing)
    planned_targets = existing.get("planned_targets") if isinstance(existing.get("planned_targets"), list) else []
    planned_frames = existing.get("planned_frames") if isinstance(existing.get("planned_frames"), list) else []
    target = str(operation.get("target") or "")
    acknowledged = existing.get("acknowledged_targets") if isinstance(existing.get("acknowledged_targets"), list) else []
    expected_target = next((str(item) for item in planned_targets if str(item) not in acknowledged), "")
    if not target or target != expected_target:
        raise PlcDispatchStateConflict("attempt_target_out_of_plan_or_order", existing)
    planned = next((item for item in planned_frames if isinstance(item, dict) and item.get("target") == target), None)
    if not isinstance(planned, dict) or str(operation.get("frame_hex") or "") != str(planned.get("frame_hex") or ""):
        raise PlcDispatchStateConflict("attempt_frame_does_not_match_plan", existing)
    old_operations = existing.get("operations") if isinstance(existing.get("operations"), list) else []
    prior_for_target = [item for item in old_operations if isinstance(item, dict) and item.get("target") == target]
    expected_attempt = len(prior_for_target) + 1
    if int(operation.get("attempt") or 0) != expected_attempt:
        raise PlcDispatchStateConflict("attempt_sequence_invalid", existing)
    expected_id = f"{existing.get('dispatch_id')}:{target}:{expected_attempt}"
    if str(operation.get("attempt_id") or "") != expected_id:
        raise PlcDispatchStateConflict("attempt_id_not_repository_derived", existing)
    retries = int((existing.get("config_snapshot") or {}).get("retries") or 0) if isinstance(existing.get("config_snapshot"), dict) else 0
    if expected_attempt > retries + 1:
        raise PlcDispatchStateConflict("attempt_retry_budget_exceeded", existing)
    if prior_for_target and prior_for_target[-1].get("finished_at") is None:
        raise PlcDispatchStateConflict("previous_attempt_not_finished", existing)
    if prior_for_target and prior_for_target[-1].get("outcome") == "acknowledged":
        raise PlcDispatchStateConflict("acknowledged_target_cannot_retry", existing)
    if prior_for_target and not plc_terminal_result_is_retryable(
        prior_for_target[-1].get("result_code"), prior_for_target[-1].get("result_phase")
    ):
        raise PlcDispatchStateConflict("previous_attempt_result_is_not_retryable", existing)
    if (
        int(operation.get("frame_bytes") or 0) * 2 != len(str(operation.get("frame_hex") or ""))
        or int(operation.get("bytes_written") or 0) != 0
        or operation.get("write_count_known") is not False
        or operation.get("reported_write_count") is not None
        or operation.get("physical_status") != "not_attempted"
        or operation.get("outcome") != "not_attempted"
        or not isinstance(operation.get("started_at"), int)
    ):
        raise PlcDispatchStateConflict("attempt_start_evidence_invalid", existing)


def validate_plc_dispatch_transition(
    existing: dict[str, Any], candidate: dict[str, Any], *, transition_kind: PlcDispatchTransitionKind
) -> None:
    if not existing:
        return
    for field in set(candidate) - PLC_DISPATCH_KNOWN_FIELDS:
        if field not in existing:
            raise PlcDispatchStateConflict(f"unknown_field_addition:{field}", existing)
    for field in set(existing) - PLC_DISPATCH_KNOWN_FIELDS:
        if field not in candidate or _plc_canonical(candidate.get(field)) != _plc_canonical(existing.get(field)):
            raise PlcDispatchStateConflict(f"legacy_unknown_field_is_immutable:{field}", existing)
    for field in PLC_DISPATCH_KNOWN_FIELDS:
        old_present = field in existing
        new_present = field in candidate
        if old_present == new_present and (
            not old_present or _plc_canonical(candidate.get(field)) == _plc_canonical(existing.get(field))
        ):
            continue
        if old_present and not new_present:
            raise PlcDispatchStateConflict(f"known_field_cannot_be_deleted:{field}", existing)
        if field in PLC_DISPATCH_IMMUTABLE_ONCE_BOUND_FIELDS:
            reason = "immutable_identity_conflict" if field in PLC_IMMUTABLE_BINDING_FIELDS else "immutable_bound_field_conflict"
            raise PlcDispatchStateConflict(f"{reason}:{field}", existing)
        if field not in PLC_DISPATCH_TRANSITION_MUTABLE_FIELDS:
            raise PlcDispatchStateConflict(f"field_not_transition_mutable:{field}", existing)
    for field in PLC_IMMUTABLE_BINDING_FIELDS:
        if field in existing and _plc_canonical(candidate.get(field)) != _plc_canonical(existing.get(field)):
            raise PlcDispatchStateConflict(f"immutable_identity_conflict:{field}", existing)
    changed_projection_fields = {
        field
        for field in PLC_DISPATCH_PHYSICAL_PROJECTION_FIELDS
        if (field in existing) != (field in candidate)
        or _plc_canonical(existing.get(field)) != _plc_canonical(candidate.get(field))
    }
    allowed_projection_fields = PLC_TRANSITION_PROJECTION_ALLOWLIST.get(transition_kind)
    if allowed_projection_fields is None:
        raise PlcDispatchStateConflict("unknown_transition_kind", existing)
    disallowed_projection_fields = changed_projection_fields - allowed_projection_fields
    if disallowed_projection_fields:
        raise PlcDispatchStateConflict(
            f"transition_projection_field_not_allowed:{sorted(disallowed_projection_fields)[0]}",
            existing,
        )
    old_status = str(existing.get("status") or "")
    new_status = str(candidate.get("status") or "")
    old_provisional = bool(existing.get("provisional"))
    if old_status in PLC_DISPATCH_FINAL_STATES and not old_provisional:
        if new_status != old_status:
            raise PlcDispatchStateConflict("terminal_state_is_immutable", existing)
        if changed_projection_fields:
            raise PlcDispatchStateConflict(
                f"terminal_physical_projection_is_immutable:{sorted(changed_projection_fields)[0]}",
                existing,
            )
        for field in ("outcome", "error_code", "physical_status"):
            if existing.get(field) not in (None, "") and candidate.get(field) != existing.get(field):
                raise PlcDispatchStateConflict(f"terminal_{field}_is_immutable", existing)
    elif old_status in PLC_DISPATCH_STATE_ORDER and new_status in PLC_DISPATCH_STATE_ORDER:
        if PLC_DISPATCH_STATE_ORDER[new_status] < PLC_DISPATCH_STATE_ORDER[old_status]:
            raise PlcDispatchStateConflict("nonterminal_state_regression", existing)
    elif old_provisional:
        if bool(candidate.get("provisional")) and new_status != old_status:
            raise PlcDispatchStateConflict("provisional_state_changed_before_finalization", existing)

    old_history = existing.get("history") if isinstance(existing.get("history"), list) else []
    new_history = candidate.get("history") if isinstance(candidate.get("history"), list) else []
    if old_status in PLC_DISPATCH_FINAL_STATES and not old_provisional and _plc_canonical(new_history) != _plc_canonical(old_history):
        raise PlcDispatchStateConflict("terminal_history_is_immutable", existing)
    if old_history:
        if len(new_history) < len(old_history) or any(
            _plc_canonical(new_history[index]) != _plc_canonical(item)
            for index, item in enumerate(old_history)
        ):
            raise PlcDispatchStateConflict("history_evidence_cannot_be_deleted_or_changed", existing)
    appended_history = new_history[len(old_history):]
    expected_appended_statuses = (
        ["acknowledged", "failed"]
        if transition_kind is PlcDispatchTransitionKind.AUDIT_FAILURE_FINALIZE
        else ([new_status] if appended_history else [])
    )
    if len(appended_history) != len(expected_appended_statuses):
        raise PlcDispatchStateConflict("history_transition_append_count_invalid", existing)
    for entry, expected_history_status in zip(appended_history, expected_appended_statuses):
        if (
            not isinstance(entry, dict)
            or set(entry) - {"status", "at", "target"}
            or str(entry.get("status") or "") != expected_history_status
            or not isinstance(entry.get("at"), int)
        ):
            raise PlcDispatchStateConflict("history_transition_entry_invalid", existing)

    active_attempts_changed = _plc_canonical(candidate.get("active_attempts")) != _plc_canonical(existing.get("active_attempts"))
    if active_attempts_changed:
        timeout_snapshot = (
            bool(candidate.get("provisional"))
            and bool(candidate.get("deadline_exceeded"))
            and candidate.get("error_code") == "plc_worker_total_timeout"
        )
        control_failure_snapshot = (
            new_status == "failed" and bool(candidate.get("control_state_unavailable"))
        )
        if not (timeout_snapshot or control_failure_snapshot):
            raise PlcDispatchStateConflict("active_attempts_is_runtime_derived", existing)
    if not bool(existing.get("provisional")) and bool(candidate.get("provisional")):
        if not (
            new_status == "failed"
            and bool(candidate.get("deadline_exceeded"))
            and candidate.get("error_code") == "plc_worker_total_timeout"
        ):
            raise PlcDispatchStateConflict("provisional_state_requires_timeout_snapshot", existing)

    if existing.get("attempted") is True and candidate.get("attempted") is not True:
        raise PlcDispatchStateConflict("attempted_evidence_cannot_regress", existing)
    if existing.get("worker_done") is True and candidate.get("worker_done") is not True:
        raise PlcDispatchStateConflict("worker_done_cannot_regress", existing)
    if int(candidate.get("bytes_written") or 0) < int(existing.get("bytes_written") or 0):
        raise PlcDispatchStateConflict("bytes_written_cannot_regress", existing)
    for field in PLC_MONOTONIC_LIST_FIELDS:
        old_items = existing.get(field) if isinstance(existing.get(field), list) else []
        new_items = candidate.get(field) if isinstance(candidate.get(field), list) else []
        if old_items and not _plc_evidence_list_contains(old_items, new_items):
            raise PlcDispatchStateConflict(f"{field}_evidence_cannot_be_deleted_or_changed", existing)
    old_operations = existing.get("operations") if isinstance(existing.get("operations"), list) else []
    new_operations = candidate.get("operations") if isinstance(candidate.get("operations"), list) else []
    operations_by_id = {
        str(item.get("attempt_id") or ""): item for item in new_operations if isinstance(item, dict)
    }
    if len(operations_by_id) != len(new_operations):
        raise PlcDispatchStateConflict("operation_attempt_id_missing_or_duplicate", existing)
    old_operation_ids = {
        str(item.get("attempt_id") or "") for item in old_operations if isinstance(item, dict)
    }
    added_operations = [
        item for item in new_operations
        if isinstance(item, dict) and str(item.get("attempt_id") or "") not in old_operation_ids
    ]
    if added_operations:
        if transition_kind is not PlcDispatchTransitionKind.START_ATTEMPT or len(added_operations) != 1:
            raise PlcDispatchStateConflict("operation_can_only_be_created_by_start_attempt", existing)
        validate_plc_attempt_start(existing, candidate, added_operations[0])
    elif transition_kind is PlcDispatchTransitionKind.START_ATTEMPT:
        raise PlcDispatchStateConflict("start_attempt_did_not_create_operation", existing)
    for old_operation in old_operations:
        if not isinstance(old_operation, dict):
            continue
        attempt_id = str(old_operation.get("attempt_id") or "")
        new_operation = operations_by_id.get(attempt_id)
        if not isinstance(new_operation, dict):
            raise PlcDispatchStateConflict("operation_evidence_cannot_be_deleted", existing)
        changed = _plc_canonical(new_operation) != _plc_canonical(old_operation)
        if changed and transition_kind not in {
            PlcDispatchTransitionKind.ADVANCE_ATTEMPT,
            PlcDispatchTransitionKind.FINISH_ATTEMPT,
        }:
            raise PlcDispatchStateConflict("operation_can_only_change_via_attempt_transition", existing)
        try:
            validate_plc_operation_evidence(old_operation, new_operation)
        except PlcDispatchStateConflict as exc:
            raise PlcDispatchStateConflict(exc.reason, existing) from exc
        if changed and transition_kind is PlcDispatchTransitionKind.ADVANCE_ATTEMPT and new_operation.get("finished_at") is not None:
            raise PlcDispatchStateConflict("advance_attempt_cannot_finish_operation", existing)
        if changed and transition_kind is PlcDispatchTransitionKind.FINISH_ATTEMPT:
            if old_operation.get("finished_at") is not None:
                raise PlcDispatchStateConflict("finished_attempt_is_immutable", existing)
            if (
                new_operation.get("finished_at") is None
                or new_operation.get("result_code") in (None, "")
            ):
                raise PlcDispatchStateConflict("finish_attempt_evidence_incomplete", existing)
    if existing.get("failed_target") not in (None, "") and candidate.get("failed_target") != existing.get("failed_target"):
        raise PlcDispatchStateConflict("failed_target_evidence_cannot_be_deleted_or_changed", existing)
    old_failure = existing.get("failed_operation") if isinstance(existing.get("failed_operation"), dict) else {}
    new_failure = candidate.get("failed_operation") if isinstance(candidate.get("failed_operation"), dict) else {}
    if old_failure and not new_failure:
        raise PlcDispatchStateConflict("failed_operation_evidence_cannot_be_deleted", existing)
    for field, old_value in old_failure.items():
        if field == "bytes_written":
            if int(new_failure.get(field) or 0) < int(old_value or 0):
                raise PlcDispatchStateConflict(f"failed_operation_{field}_cannot_regress", existing)
        elif field not in new_failure or _plc_canonical(new_failure.get(field)) != _plc_canonical(old_value):
            raise PlcDispatchStateConflict(f"failed_operation_{field}_cannot_be_deleted_or_changed", existing)
    if new_failure.get("attempt_id"):
        operation = operations_by_id.get(str(new_failure.get("attempt_id") or ""))
        if not isinstance(operation, dict):
            raise PlcDispatchStateConflict("failed_operation_missing_canonical_operation", existing)
        for field in (
            "target", "frame_hex", "frame_bytes", "write_count_known",
            "reported_write_count", "diagnostic_source", "physical_status", "outcome",
        ):
            if _plc_canonical(new_failure.get(field)) != _plc_canonical(operation.get(field)):
                raise PlcDispatchStateConflict(f"failed_operation_canonical_mismatch:{field}", existing)
        if int(new_failure.get("bytes_written") or 0) > int(operation.get("bytes_written") or 0):
            raise PlcDispatchStateConflict("failed_operation_bytes_exceed_canonical_operation", existing)
