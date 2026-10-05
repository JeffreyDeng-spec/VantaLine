"""Pure projection of stored PLC event evidence, including historical versions.

This module validates records only. It does not acquire leases or execute I/O;
legacy retry evidence must not be treated as permission to retry browser writes.
"""
import copy
from typing import Any

from ..plc_fx_ascii import (
    PLC_TERMINAL_ALLOWED_PHASES,
    PLC_TERMINAL_DIAGNOSTIC_SOURCES,
    PlcTerminalResultCode,
    PlcTransportPhase,
    plc_terminal_result_is_retryable,
)
from .errors import PlcDispatchStateConflict


PLC_REDUCER_DERIVED_FIELDS = frozenset(
    {
        "status", "history", "attempted", "physical_status", "outcome", "audit_status",
        "error_code", "diagnostic_source", "target", "bytes_written", "frame_bytes",
        "attempts", "targets", "acknowledged_targets", "failed_target", "frames",
        "failed_operation", "operations", "attempt_ids", "cancelled_after_disable",
        "cancelled_after_config_change", "deadline_exceeded", "no_automatic_retry",
        "worker_done", "worker_continues", "worker_cleanup_pending", "provisional",
        "control_state_unavailable", "active_attempts", "events", "updated_at",
    }
)


PLC_FINALIZE_REASONS = frozenset(
    {
        "", "cancelled_after_disable", "cancelled_after_config_change", "deadline_exceeded",
        "control_state_check_failed_after_ack", "control_state_check_failed_after_partial_ack",
        "control_state_check_failed_before_io", "plc_pg_coordination_unavailable",
        "audit_persist_failed_after_ack", "restart_recovery_required", "plc_dispatch_queue_timeout",
        "invalid_config", "disabled",
    }
)


def project_plc_dispatch_events(record: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure versioned reducer from immutable binding + strict typed event stream."""
    base = {key: copy.deepcopy(value) for key, value in record.items() if key not in PLC_REDUCER_DERIVED_FIELDS}
    planned_targets = [str(item) for item in base.get("planned_targets", [])]
    planned_frames = base.get("planned_frames") if isinstance(base.get("planned_frames"), list) else []
    planned_by_target = {
        str(item.get("target") or ""): str(item.get("frame_hex") or "")
        for item in planned_frames if isinstance(item, dict)
    }
    retries = int((base.get("config_snapshot") or {}).get("retries") or 0)
    if not events or not isinstance(events[0], dict) or events[0].get("kind") != "create":
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:create_event_missing", record)
    create_at = events[0].get("at")
    if (
        events[0] != {"seq": 1, "kind": "create", "at": create_at}
        or type(events[0].get("seq")) is not int
        or type(create_at) is not int
        or int(create_at) < 0
    ):
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:create_event_invalid", record)
    projected: dict[str, Any] = {
        **base,
        "events": copy.deepcopy(events),
        "status": "queued",
        "history": [{"status": "queued", "at": create_at}],
        "attempted": False,
        "duplicate": False,
        "worker_done": False,
        "worker_continues": False,
        "worker_cleanup_pending": False,
        "deadline_exceeded": False,
        "updated_at": create_at,
    }
    operations: list[dict[str, Any]] = []
    attempt_ids: list[str] = []
    acknowledged_targets: list[str] = []
    terminal_seen = False
    previous_event_at = int(create_at)

    for index, event in enumerate(events[1:], start=2):
        if (
            not isinstance(event, dict)
            or type(event.get("seq")) is not int
            or event.get("seq") != index
            or type(event.get("at")) is not int
            or int(event.get("at")) < 0
        ):
            raise PlcDispatchStateConflict("corrupt_persisted_dispatch:event_sequence_invalid", record)
        if int(event["at"]) < previous_event_at:
            raise PlcDispatchStateConflict("corrupt_persisted_dispatch:event_time_regression", record)
        if terminal_seen:
            raise PlcDispatchStateConflict("corrupt_persisted_dispatch:event_after_terminal", record)
        kind = event.get("kind")
        at = int(event["at"])
        previous_event_at = at
        projected["updated_at"] = at
        if kind == "attempting":
            if set(event) != {"seq", "kind", "at"} or projected["status"] != "queued":
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:attempting_event_invalid", record)
            projected["status"] = "attempting"
            projected["physical_status"] = "not_attempted"
            projected["history"].append({"status": "attempting", "at": at})
        elif kind == "start_attempt":
            if set(event) != {"seq", "kind", "at", "target", "attempt_id"}:
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:start_event_schema_invalid", record)
            if projected["status"] not in {"attempting", "sent"} or projected.get("provisional"):
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:start_event_state_invalid", record)
            if not isinstance(event.get("target"), str) or not isinstance(event.get("attempt_id"), str):
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:start_event_schema_invalid", record)
            target = event["target"]
            expected_target = next((item for item in planned_targets if item not in acknowledged_targets), "")
            if target != expected_target:
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:attempt_target_order_invalid", record)
            prior = [item for item in operations if item["target"] == target]
            attempt = len(prior) + 1
            expected_id = f"{base.get('dispatch_id')}:{target}:{attempt}"
            if event.get("attempt_id") != expected_id or attempt > retries + 1:
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:attempt_sequence_invalid", record)
            if prior and (
                prior[-1].get("finished_at") is None
                or prior[-1].get("outcome") == "acknowledged"
                or not plc_terminal_result_is_retryable(
                    prior[-1].get("result_code"), prior[-1].get("result_phase")
                )
            ):
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:retry_chain_invalid", record)
            frame_hex = planned_by_target.get(target, "")
            operation = {
                "attempt_id": expected_id,
                "target": target,
                "attempt": attempt,
                "frame_hex": frame_hex,
                "frame_bytes": len(bytes.fromhex(frame_hex)),
                "bytes_written": 0,
                "write_count_known": False,
                "reported_write_count": None,
                "physical_status": "not_attempted",
                "outcome": "not_attempted",
                "started_at": at,
            }
            operations.append(operation)
            attempt_ids.append(expected_id)
        elif kind == "advance_attempt":
            expected_keys = {
                "seq", "kind", "at", "attempt_id", "bytes_written", "physical_status", "outcome"
            }
            if set(event) != expected_keys:
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:advance_event_schema_invalid", record)
            operation = next((item for item in operations if item["attempt_id"] == event.get("attempt_id")), None)
            if operation is None or operation.get("finished_at") is not None:
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:advance_without_start", record)
            bytes_written = event.get("bytes_written")
            physical_status = event.get("physical_status")
            outcome = event.get("outcome")
            frame_bytes = int(operation["frame_bytes"])
            previous_physical = str(operation.get("physical_status") or "not_attempted")
            allowed_next_physical = {
                "not_attempted": {"write_call_started"},
                "write_call_started": {"not_written", "partial_write", "full_frame_written"},
            }
            valid = (
                (physical_status == "write_call_started" and bytes_written == 0 and outcome == "write_outcome_uncertain")
                or (physical_status == "not_written" and bytes_written == 0 and outcome == "not_written")
                or (
                    physical_status == "partial_write" and type(bytes_written) is int
                    and 0 < bytes_written < frame_bytes and outcome == "outcome_uncertain"
                )
                or (
                    physical_status == "full_frame_written" and bytes_written == frame_bytes
                    and outcome == "awaiting_acknowledgement"
                )
            )
            if (
                not valid
                or physical_status not in allowed_next_physical.get(previous_physical, set())
                or int(bytes_written) < int(operation["bytes_written"])
            ):
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:advance_evidence_invalid", record)
            operation.update(
                bytes_written=int(bytes_written),
                write_count_known=physical_status != "write_call_started",
                reported_write_count=(None if physical_status == "write_call_started" else int(bytes_written)),
                physical_status=physical_status,
                outcome=outcome,
            )
            if not projected.get("provisional"):
                projected["attempted"] = True
                projected["physical_status"] = physical_status
                projected["outcome"] = outcome
                projected["target"] = operation["target"]
                projected["bytes_written"] = max(int(projected.get("bytes_written") or 0), int(bytes_written))
                projected["frame_bytes"] = frame_bytes
                if physical_status == "full_frame_written" and projected["status"] != "sent":
                    projected["status"] = "sent"
                    projected["history"].append({"status": "sent", "at": at, "target": operation["target"]})
        elif kind == "finish_attempt":
            expected_keys = {
                "seq", "kind", "at", "attempt_id", "result_code", "result_phase",
                "bytes_written", "diagnostic_source",
            }
            if set(event) != expected_keys:
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:finish_event_schema_invalid", record)
            operation = next((item for item in operations if item["attempt_id"] == event.get("attempt_id")), None)
            if operation is None or operation.get("finished_at") is not None:
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:finish_without_start", record)
            if at < int(operation["started_at"]):
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:finish_before_start", record)
            try:
                code = PlcTerminalResultCode(event.get("result_code"))
                phase = PlcTransportPhase(event.get("result_phase"))
            except (TypeError, ValueError) as exc:
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:terminal_result_invalid", record) from exc
            bytes_written = event.get("bytes_written")
            if (
                type(bytes_written) is not int
                or bytes_written != operation["bytes_written"]
                or phase not in PLC_TERMINAL_ALLOWED_PHASES[code]
                or event.get("diagnostic_source") not in PLC_TERMINAL_DIAGNOSTIC_SOURCES[code]
            ):
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:terminal_result_invalid", record)
            frame_bytes = int(operation["frame_bytes"])
            operation_physical = str(operation.get("physical_status") or "not_attempted")
            expected_physical = operation["physical_status"]
            expected_outcome = operation["outcome"]
            if code is PlcTerminalResultCode.ACKNOWLEDGED:
                if (
                    phase is not PlcTransportPhase.RESPONSE
                    or bytes_written != frame_bytes
                    or operation_physical != "full_frame_written"
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:ack_evidence_invalid", record)
                expected_physical, expected_outcome = "acknowledged", "acknowledged"
            elif code is PlcTerminalResultCode.NAK:
                if (
                    phase is not PlcTransportPhase.RESPONSE
                    or bytes_written != frame_bytes
                    or operation_physical != "full_frame_written"
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:nak_evidence_invalid", record)
                expected_physical, expected_outcome = "rejected", "rejected"
            elif code in {PlcTerminalResultCode.SHORT_RESPONSE, PlcTerminalResultCode.UNEXPECTED_RESPONSE}:
                if (
                    phase is not PlcTransportPhase.RESPONSE
                    or bytes_written != frame_bytes
                    or operation_physical != "full_frame_written"
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:response_evidence_invalid", record)
                expected_physical, expected_outcome = "full_frame_written", "outcome_uncertain"
            elif code is PlcTerminalResultCode.TIMEOUT:
                if phase in {PlcTransportPhase.READ, PlcTransportPhase.FLUSH} and (
                    bytes_written != frame_bytes or operation_physical != "full_frame_written"
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:timeout_evidence_invalid", record)
                if phase is PlcTransportPhase.WRITE and (
                    bytes_written != 0 or operation_physical != "write_call_started"
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:timeout_evidence_invalid", record)
                expected_outcome = "outcome_uncertain" if bytes_written > 0 or phase is PlcTransportPhase.WRITE else expected_outcome
            elif code is PlcTerminalResultCode.SHORT_WRITE:
                if (
                    phase is not PlcTransportPhase.WRITE
                    or not 0 <= bytes_written < frame_bytes
                    or operation_physical not in {"not_written", "partial_write"}
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:short_write_evidence_invalid", record)
            elif code is PlcTerminalResultCode.WRITE_RESULT_UNKNOWN:
                if (
                    phase is not PlcTransportPhase.WRITE
                    or bytes_written != 0
                    or operation_physical != "write_call_started"
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:write_unknown_evidence_invalid", record)
            elif code is PlcTerminalResultCode.SERIAL_IO_FAILED:
                if phase is PlcTransportPhase.READ and (
                    bytes_written != frame_bytes or operation_physical != "full_frame_written"
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:serial_io_evidence_invalid", record)
                if phase is PlcTransportPhase.WRITE and (
                    bytes_written != 0 or operation_physical != "write_call_started"
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:serial_io_evidence_invalid", record)
                if bytes_written > 0:
                    expected_outcome = "outcome_uncertain"
            elif code is PlcTerminalResultCode.FLUSH_FAILED:
                if (
                    phase is not PlcTransportPhase.FLUSH
                    or bytes_written != frame_bytes
                    or operation_physical != "full_frame_written"
                ):
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:flush_evidence_invalid", record)
                expected_outcome = "outcome_uncertain"
            elif code in {
                PlcTerminalResultCode.SERIAL_OPEN_FAILED,
                PlcTerminalResultCode.SERIAL_DEPENDENCY_MISSING,
            }:
                if phase is not PlcTransportPhase.OPEN or bytes_written != 0 or operation["physical_status"] != "not_attempted":
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:open_evidence_invalid", record)
            elif code is PlcTerminalResultCode.INTERNAL_TRANSITION_ERROR:
                if phase is not PlcTransportPhase.INTERNAL:
                    raise PlcDispatchStateConflict("corrupt_persisted_dispatch:internal_result_invalid", record)
                if operation_physical == "write_call_started":
                    expected_outcome = "write_outcome_uncertain"
                elif operation_physical in {"partial_write", "full_frame_written"}:
                    expected_outcome = "outcome_uncertain"
                elif operation_physical == "not_attempted":
                    expected_outcome = "not_attempted"
                elif operation_physical == "not_written":
                    expected_outcome = "not_written"
                else:
                    raise PlcDispatchStateConflict(
                        "corrupt_persisted_dispatch:internal_physical_state_invalid", record
                    )
            operation.update(
                physical_status=expected_physical,
                outcome=expected_outcome,
                result_code=code.value,
                result_phase=phase.value,
                diagnostic_source=event["diagnostic_source"],
                finished_at=at,
            )
            if code is PlcTerminalResultCode.ACKNOWLEDGED:
                acknowledged_targets.append(operation["target"])
        elif kind == "deadline":
            if set(event) != {"seq", "kind", "at"} or projected.get("worker_done"):
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:deadline_event_invalid", record)
            attempted = bool(projected.get("attempted")) or any(
                item["physical_status"] not in {"not_attempted", ""} for item in operations
            )
            projected.update(
                status="failed", attempted=attempted,
                physical_status=str(projected.get("physical_status") or ("write_outcome_uncertain" if attempted else "not_attempted")),
                outcome="outcome_uncertain" if attempted else "deadline_exceeded",
                error_code="plc_worker_total_timeout", deadline_exceeded=True,
                provisional=True, worker_done=False, worker_continues=attempted,
            )
        elif kind == "finalize":
            if set(event) != {"seq", "kind", "at", "reason"}:
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:finalize_event_schema_invalid", record)
            if not isinstance(event.get("reason"), str):
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:finalize_event_schema_invalid", record)
            reason = event["reason"]
            if reason not in PLC_FINALIZE_REASONS or any(item.get("finished_at") is None for item in operations):
                raise PlcDispatchStateConflict("corrupt_persisted_dispatch:finalize_event_invalid", record)
            acknowledged_ops = {
                item["target"]: item for item in operations if item.get("outcome") == "acknowledged"
            }
            ack_targets = [target for target in planned_targets if target in acknowledged_ops]
            frames = [
                {"target": target, "frame_hex": acknowledged_ops[target]["frame_hex"], "attempts": acknowledged_ops[target]["attempt"]}
                for target in ack_targets
            ]
            failed_operation = next(
                (item for item in reversed(operations) if item.get("outcome") != "acknowledged"), None
            )
            failed_target = str((failed_operation or {}).get("target") or "") or next(
                (target for target in planned_targets if target not in ack_targets), ""
            )
            all_ack = bool(planned_targets) and ack_targets == planned_targets
            if not reason and not all_ack and failed_operation is None:
                raise PlcDispatchStateConflict(
                    "corrupt_persisted_dispatch:finalize_without_terminal_evidence", record
                )
            if not reason and failed_operation is not None:
                result_code = str(failed_operation.get("result_code") or "")
                result_phase = str(failed_operation.get("result_phase") or "")
                attempts_for_failed_target = sum(
                    1 for item in operations if item.get("target") == failed_operation.get("target")
                )
                if (
                    plc_terminal_result_is_retryable(result_code, result_phase)
                    and attempts_for_failed_target < retries + 1
                ):
                    raise PlcDispatchStateConflict(
                        "corrupt_persisted_dispatch:retry_budget_not_exhausted", record
                    )
            status = "disabled" if reason in {"disabled", "cancelled_after_disable"} and not operations else (
                "acknowledged" if not reason and all_ack else "failed"
            )
            error_code = reason or (str((failed_operation or {}).get("result_code") or "") if status == "failed" else "")
            attempted = any(
                int(item.get("bytes_written") or 0) > 0
                or item.get("physical_status") not in {None, "", "not_attempted"}
                for item in operations
            )
            last = operations[-1] if operations else {}
            if status == "acknowledged":
                physical_status, outcome = "acknowledged", "acknowledged"
            elif reason == "audit_persist_failed_after_ack" and all_ack:
                physical_status, outcome = "acknowledged", "acknowledged_audit_unpersisted"
            elif ack_targets and failed_target:
                physical_status, outcome = "partial_success", "partial_failure"
            elif last:
                physical_status = str(last.get("physical_status") or "not_attempted")
                outcome = str(last.get("outcome") or "not_attempted")
            else:
                physical_status = "not_attempted"
                outcome = (
                    "cancelled_before_attempt" if reason.startswith("cancelled_")
                    else "queue_timeout" if reason == "plc_dispatch_queue_timeout"
                    else "activation_blocked" if reason == "plc_pg_coordination_unavailable"
                    else "not_attempted"
                )
            history = projected["history"]
            if reason == "audit_persist_failed_after_ack" and all_ack:
                history.append({"status": "acknowledged", "at": at})
            history.append({"status": status, "at": at})
            projected.update(
                status=status, history=history, attempted=attempted,
                physical_status=physical_status, outcome=outcome, error_code=error_code,
                attempts=(int((failed_operation or {}).get("attempt") or 0) if failed_target else sum(int(item["attempt"]) for item in acknowledged_ops.values())),
                acknowledged_targets=ack_targets, targets=ack_targets, frames=frames,
                failed_target=failed_target, target=str(last.get("target") or failed_target),
                bytes_written=max([int(item.get("bytes_written") or 0) for item in operations] or [0]),
                frame_bytes=int(last.get("frame_bytes") or 0),
                cancelled_after_disable=reason == "cancelled_after_disable",
                cancelled_after_config_change=reason == "cancelled_after_config_change",
                deadline_exceeded=reason == "deadline_exceeded" or bool(projected.get("deadline_exceeded")),
                no_automatic_retry=bool(ack_targets and status == "failed"),
                provisional=False, worker_done=True, worker_continues=False,
                worker_cleanup_pending=False,
            )
            if reason == "audit_persist_failed_after_ack":
                projected["audit_status"] = "persist_failed"
            if failed_operation:
                projected["diagnostic_source"] = failed_operation.get("diagnostic_source", "")
                projected["failed_operation"] = {
                    "attempt_id": failed_operation["attempt_id"],
                    "target": failed_operation["target"],
                    "frame_hex": failed_operation["frame_hex"],
                    "frame_bytes": failed_operation["frame_bytes"],
                    "bytes_written": failed_operation["bytes_written"],
                    "write_count_known": failed_operation["write_count_known"],
                    "reported_write_count": failed_operation["reported_write_count"],
                    "physical_status": failed_operation["physical_status"],
                    "outcome": failed_operation["outcome"],
                    "result_phase": failed_operation.get("result_phase", ""),
                    "diagnostic_source": failed_operation.get("diagnostic_source", ""),
                    "attempts": failed_operation["attempt"],
                    "error_code": error_code,
                }
            terminal_seen = True
        else:
            raise PlcDispatchStateConflict("corrupt_persisted_dispatch:unknown_event_kind", record)
        projected["operations"] = copy.deepcopy(operations)
        projected["attempt_ids"] = list(attempt_ids)

    if not operations:
        projected.pop("operations", None)
        projected.pop("attempt_ids", None)
    return projected
