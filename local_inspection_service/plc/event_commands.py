"""Typed historical event construction, with no persistence or physical I/O.

The standard clock timestamps new evidence; validation and projection remain in
explicit policy modules. Current browser dispatch authorization is separate.
"""
import time
from typing import Any, Callable
from ..plc_fx_ascii import plc_terminal_result_is_retryable
from .errors import PlcDispatchStateConflict
from .event_projection import project_plc_dispatch_events
from .transition_policy import PlcDispatchTransitionKind


def append_plc_typed_event(record: dict[str, Any], kind: str, **payload: Any) -> list[dict[str, Any]]:
    events = [dict(item) for item in record.get("events", []) if isinstance(item, dict)]
    return [
        *events,
        {"seq": len(events) + 1, "kind": kind, "at": int(time.time()), **payload},
    ]

def _derive_plc_attempting(existing: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if existing.get("status") != "queued":
        raise PlcDispatchStateConflict("attempting_requires_queued", existing)
    candidate = project_plc_dispatch_events(
        existing, append_plc_typed_event(existing, "attempting")
    )
    candidate["message"] = "Preparing to open the configured serial port and write a PLC frame"
    return candidate

def _derive_plc_start_attempt(existing: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    dispatch_id = str(existing.get("dispatch_id") or "")
    target = payload["target"]
    planned_targets = existing.get("planned_targets") if isinstance(existing.get("planned_targets"), list) else []
    acknowledged = existing.get("acknowledged_targets") if isinstance(existing.get("acknowledged_targets"), list) else []
    expected_target = next((str(item) for item in planned_targets if str(item) not in acknowledged), "")
    if target != expected_target:
        raise PlcDispatchStateConflict("attempt_target_out_of_plan_or_order", existing)
    planned_frames = existing.get("planned_frames") if isinstance(existing.get("planned_frames"), list) else []
    planned = next((item for item in planned_frames if isinstance(item, dict) and item.get("target") == target), None)
    if not isinstance(planned, dict):
        raise PlcDispatchStateConflict("attempt_frame_does_not_match_plan", existing)
    operations = [dict(item) for item in existing.get("operations", []) if isinstance(item, dict)] if isinstance(existing.get("operations"), list) else []
    prior = [item for item in operations if item.get("target") == target]
    attempt = len(prior) + 1
    retries = int((existing.get("config_snapshot") or {}).get("retries") or 0)
    if attempt > retries + 1:
        raise PlcDispatchStateConflict("attempt_retry_budget_exceeded", existing)
    if prior and prior[-1].get("finished_at") is None:
        raise PlcDispatchStateConflict("previous_attempt_not_finished", existing)
    if prior and prior[-1].get("outcome") == "acknowledged":
        raise PlcDispatchStateConflict("acknowledged_target_cannot_retry", existing)
    if prior and not plc_terminal_result_is_retryable(
        prior[-1].get("result_code"), prior[-1].get("result_phase")
    ):
        raise PlcDispatchStateConflict("previous_attempt_result_is_not_retryable", existing)
    attempt_id = f"{dispatch_id}:{target}:{attempt}"
    candidate = project_plc_dispatch_events(
        existing,
        append_plc_typed_event(
            existing, "start_attempt", target=target, attempt_id=attempt_id
        ),
    )
    candidate["message"] = "PLC attempt created from the immutable dispatch plan"
    return candidate

def _derive_plc_advance_attempt(existing: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    attempt_id = payload["attempt_id"]
    bytes_written = payload["bytes_written"]
    physical_status = payload["physical_status"]
    outcome = payload["outcome"]
    operations = [dict(item) for item in existing.get("operations", []) if isinstance(item, dict)] if isinstance(existing.get("operations"), list) else []
    operation = next((item for item in operations if item.get("attempt_id") == attempt_id), None)
    if not isinstance(operation, dict) or operation.get("finished_at") is not None:
        raise PlcDispatchStateConflict("advance_attempt_requires_started_operation", existing)
    frame_bytes = int(operation.get("frame_bytes") or 0)
    if type(bytes_written) is not int or not 0 <= bytes_written <= frame_bytes:
        raise PlcDispatchStateConflict("advance_attempt_bytes_written_invalid", existing)
    valid_evidence = (
        (physical_status == "write_call_started" and bytes_written == 0 and outcome == "write_outcome_uncertain")
        or (physical_status == "not_written" and bytes_written == 0 and outcome == "not_written")
        or (
            physical_status == "partial_write"
            and 0 < bytes_written < frame_bytes
            and outcome == "outcome_uncertain"
        )
        or (
            physical_status == "full_frame_written"
            and bytes_written == frame_bytes
            and outcome == "awaiting_acknowledgement"
        )
    )
    if not valid_evidence:
        raise PlcDispatchStateConflict("advance_attempt_evidence_combination_invalid", existing)
    candidate = project_plc_dispatch_events(
        existing,
        append_plc_typed_event(
            existing,
            "advance_attempt",
            attempt_id=attempt_id,
            bytes_written=bytes_written,
            physical_status=physical_status,
            outcome=outcome,
        ),
    )
    candidate["message"] = "Serial transport evidence advanced through the typed attempt handler"
    return candidate

def _derive_plc_finish_attempt(existing: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    attempt_id = payload["attempt_id"]
    terminal_code = payload["result_code"]
    result_phase = payload["result_phase"]
    reported_bytes_written = payload["bytes_written"]
    diagnostic_source = payload["diagnostic_source"]
    operations = [dict(item) for item in existing.get("operations", []) if isinstance(item, dict)] if isinstance(existing.get("operations"), list) else []
    operation = next((item for item in operations if item.get("attempt_id") == attempt_id), None)
    if not isinstance(operation, dict) or operation.get("finished_at") is not None:
        raise PlcDispatchStateConflict("finish_attempt_requires_started_operation", existing)
    if int(operation.get("bytes_written") or 0) != reported_bytes_written:
        raise PlcDispatchStateConflict("finish_attempt_bytes_do_not_match_authoritative_operation", existing)
    candidate = project_plc_dispatch_events(
        existing,
        append_plc_typed_event(
            existing,
            "finish_attempt",
            attempt_id=attempt_id,
            result_code=terminal_code,
            result_phase=result_phase,
            bytes_written=reported_bytes_written,
            diagnostic_source=diagnostic_source,
        ),
    )
    candidate["message"] = "Terminal transport evidence finalized through the typed attempt handler"
    return candidate

def _derive_plc_deadline(existing: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    candidate = project_plc_dispatch_events(
        existing, append_plc_typed_event(existing, "deadline")
    )
    candidate["message"] = "The request deadline expired; typed attempt events remain authoritative until worker finalization"
    return candidate

def _derive_plc_finalize(existing: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    reason = payload["reason"]
    candidate = project_plc_dispatch_events(
        existing, append_plc_typed_event(existing, "finalize", reason=reason)
    )
    candidate["message"] = "PLC dispatch projection finalized from authoritative typed attempt events"
    return candidate

_PLC_TYPED_EVENT_DERIVERS: dict[
    PlcDispatchTransitionKind, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
] = {
    PlcDispatchTransitionKind.DISPATCH_TRANSITION: _derive_plc_attempting,
    PlcDispatchTransitionKind.START_ATTEMPT: _derive_plc_start_attempt,
    PlcDispatchTransitionKind.ADVANCE_ATTEMPT: _derive_plc_advance_attempt,
    PlcDispatchTransitionKind.FINISH_ATTEMPT: _derive_plc_finish_attempt,
    PlcDispatchTransitionKind.DEADLINE: _derive_plc_deadline,
    PlcDispatchTransitionKind.FINALIZE: _derive_plc_finalize,
    PlcDispatchTransitionKind.AUDIT_FAILURE_FINALIZE: _derive_plc_finalize,
}

_PLC_TYPED_EVENT_FIELDS: dict[PlcDispatchTransitionKind, frozenset[str]] = {
    PlcDispatchTransitionKind.DISPATCH_TRANSITION: frozenset(),
    PlcDispatchTransitionKind.START_ATTEMPT: frozenset({"target"}),
    PlcDispatchTransitionKind.ADVANCE_ATTEMPT: frozenset(
        {"attempt_id", "bytes_written", "physical_status", "outcome"}
    ),
    PlcDispatchTransitionKind.FINISH_ATTEMPT: frozenset(
        {"attempt_id", "result_code", "result_phase", "bytes_written", "diagnostic_source"}
    ),
    PlcDispatchTransitionKind.DEADLINE: frozenset(),
    PlcDispatchTransitionKind.FINALIZE: frozenset({"reason"}),
    PlcDispatchTransitionKind.AUDIT_FAILURE_FINALIZE: frozenset({"reason"}),
}
