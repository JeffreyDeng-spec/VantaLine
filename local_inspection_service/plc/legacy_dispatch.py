"""Retained legacy dispatch orchestration with explicit capabilities.

Current Web Serial startup and HTTP paths never start this compatibility consumer.
"""
from dataclasses import dataclass
import asyncio
import copy
import time
from typing import Any
from .legacy_dispatch_ports import LegacyDispatchPolicy, LegacyDispatchConfiguration, LegacyDispatchRecords, LegacyDispatchExecution

@dataclass(frozen=True)
class LegacyDispatch:
    policy: LegacyDispatchPolicy
    configuration: LegacyDispatchConfiguration
    records: LegacyDispatchRecords
    execution: LegacyDispatchExecution

    def dispatch_plc_for_detection(self,
        result: dict[str, Any],
        *,
        source: str,
        fingerprint: str,
        expected_generation: int | None = None,
    ) -> dict[str, Any]:
        """Attach PLC sync status without changing or invalidating the detection result."""
        dispatch_id, request_id, passed = self.records.plc_dispatch_identity()(result, source=source, fingerprint=fingerprint)
        enabled_hint = False
        try:
            with self.execution._config_io_lock():
                config = self.configuration.load_config()()
                generation = (
                    int(expected_generation)
                    if expected_generation is not None
                    else int(config.get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0)
                )
                entry = self.execution._plc_runtime_entry()(dispatch_id)
                entry["worker_started"] = True
                entry["generation"] = generation
                existing = self.records.get_validated_idempotent_dispatch()(
                    source=source,
                    request_id=request_id,
                    passed=passed,
                    fingerprint=fingerprint,
                )
                current_worker_create = bool(entry.pop("created_by_current_worker", False))
                if isinstance(existing, dict) and existing.get("protocol_contract_version") == 1:
                    entry["hydrated"] = True
                    entry["state_version"] = int(existing.get("state_version") or 0)
                    entry["latest"] = dict(existing)
                    entry["worker_done"] = True
                    result["plc_sync"] = {
                        **existing,
                        "duplicate": True,
                        "worker_done": True,
                        "worker_continues": False,
                        **(
                            {}
                            if self.records.plc_dispatch_record_is_terminal()(existing)
                            else {
                                "error_code": "dispatch_migration_required",
                                "message": "旧版非终态记录仅可审计，禁止追加事件或执行物理 I/O",
                            }
                        ),
                    }
                    return result
                if isinstance(existing, dict) and current_worker_create and entry.get("deadline_exceeded"):
                    finalized = self.records.plc_finalize_dispatch()(
                        dispatch_id,
                        expected_version=int(existing.get("state_version") or 0),
                        reason="deadline_exceeded",
                    )
                    entry["worker_done"] = True
                    entry["state_version"] = int(finalized["state_version"])
                    entry["latest"] = dict(finalized)
                    result["plc_sync"] = finalized
                    return result
                adoptable_existing = bool(
                    isinstance(existing, dict)
                    and not current_worker_create
                    and self.records.plc_dispatch_is_pristine_queue()(existing)
                )
                if isinstance(existing, dict) and not current_worker_create and not adoptable_existing:
                    entry["hydrated"] = True
                    entry["state_version"] = int(existing.get("state_version") or 0)
                    entry["latest"] = dict(existing)
                    if self.records.plc_dispatch_record_is_terminal()(existing):
                        entry["worker_done"] = True
                        result["plc_sync"] = {**existing, "duplicate": True}
                        return result
                    try:
                        result["plc_sync"] = self.records.plc_finalize_dispatch()(
                            dispatch_id,
                            expected_version=int(existing.get("state_version") or 0),
                            reason=(
                                "deadline_exceeded"
                                if existing.get("deadline_exceeded")
                                else "restart_recovery_required"
                            ),
                        )
                    except Exception:
                        result["plc_sync"] = {**existing, "duplicate": True, "audit_status": "state_conflict"}
                    return result
            raw_plc = self.configuration.raw_plc_namespace()(config)
            enabled_hint = bool(raw_plc.get("enabled")) if isinstance(raw_plc, dict) else False
            try:
                effective_plc = self.configuration.normalize_plc_config()(self.configuration.raw_plc_namespace()(config))
            except self.policy.PlcConfigError():
                effective_plc = None
            capability_errors = self.configuration.plc_activation_errors()(effective_plc) if effective_plc is not None else []
            if effective_plc is not None and effective_plc["enabled"] and capability_errors:
                first_error = capability_errors[0]
                result["plc_sync"] = {
                    "dispatch_id": dispatch_id,
                    "source": source,
                    "request_id": request_id,
                    "passed": passed,
                    "enabled": True,
                    "attempted": False,
                    "status": "failed",
                    "physical_status": "not_attempted",
                    "outcome": "activation_blocked",
                    "error_code": first_error["code"],
                    "worker_done": True,
                    "message": first_error["message"],
                    "updated_at": int(time.time()),
                }
                return result
            if isinstance(existing, dict) and adoptable_existing:
                adoption_blocker = (
                    self.records.plc_dispatch_adoption_blocker()(
                        existing,
                        settings=effective_plc,
                        generation=generation,
                    )
                    if effective_plc is not None
                    else "config_changed"
                )
                if adoption_blocker:
                    if adoption_blocker == "version_not_adoptable":
                        result["plc_sync"] = {
                            **existing,
                            "duplicate": True,
                            "worker_done": True,
                            "worker_continues": False,
                            "error_code": "dispatch_migration_required",
                            "message": "旧版 queued 记录仅可审计，不允许跨 owner 执行",
                        }
                        return result
                    reason = (
                        "plc_dispatch_queue_timeout"
                        if adoption_blocker in {"deadline_missing", "deadline_expired"}
                        else "cancelled_after_config_change"
                    )
                    result["plc_sync"] = self.records.plc_finalize_dispatch()(
                        dispatch_id,
                        expected_version=int(existing.get("state_version") or 0),
                        reason=reason,
                    )
                    return result
            if effective_plc is not None and effective_plc["enabled"]:
                io_owner = self.configuration.plc_claim_or_renew_io_owner()()
                if io_owner is None:
                    queued = (
                        dict(existing)
                        if isinstance(existing, dict) and self.records.plc_dispatch_is_pristine_queue()(existing)
                        else {
                            "dispatch_id": dispatch_id,
                            "source": source,
                            "request_id": request_id,
                            "passed": passed,
                            "enabled": True,
                            "attempted": False,
                            "status": "queued",
                        }
                    )
                    result["plc_sync"] = {
                        **queued,
                        "physical_status": "not_attempted",
                        "outcome": "queued_for_io_owner",
                        "error_code": "plc_io_owner_pending",
                        "worker_done": True,
                        "worker_continues": False,
                        "message": "结果已持久排队，等待当前 PLC 串口所有者处理",
                        "updated_at": int(time.time()),
                    }
                    return result
                io_owner_epoch = int(io_owner["epoch"])
                created = (
                    dict(existing)
                    if isinstance(existing, dict) and self.records.plc_dispatch_is_pristine_queue()(existing)
                    else self.records.create_plc_dispatch()(
                        source=source,
                        request_id=request_id,
                        passed=passed,
                        fingerprint=fingerprint,
                        expected_generation=generation,
                    )
                )
                with self.execution._config_io_lock():
                    entry = self.execution._plc_runtime_entry()(dispatch_id)
                    entry["hydrated"] = True
                    entry["state_version"] = int(created["state_version"])
                    entry["latest"] = dict(created)
            def attempt_key(target: str, attempt: int) -> str:
                return f"{dispatch_id}:{target}:{attempt}"

            def before_attempt(target: str, attempt: int) -> bool | str:
                key = attempt_key(target, attempt)
                with self.execution._config_io_lock():
                    entry = self.execution._plc_runtime_entry()(dispatch_id)
                    if entry.get("deadline_exceeded"):
                        return "deadline_exceeded"
                    current = self.configuration.load_config()()
                    current_generation = int(current.get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0)
                    try:
                        current_plc = self.configuration.normalize_plc_config()(self.configuration.raw_plc_namespace()(current))
                    except self.policy.PlcConfigError():
                        return "cancelled_after_config_change"
                    if not current_plc["enabled"]:
                        return "cancelled_after_disable"
                    if current_generation != generation:
                        return "cancelled_after_config_change"
                    if not self.configuration.plc_current_process_owns_io()(io_owner_epoch):
                        return "cancelled_after_config_change"
                    return True

            def after_attempt(target: str, attempt: int) -> None:
                with self.execution._config_io_lock():
                    self.execution._plc_active_attempts().pop(attempt_key(target, attempt), None)

            def dispatch_cancel_reason() -> str:
                with self.execution._config_io_lock():
                    if self.execution._plc_runtime_entry()(dispatch_id).get("deadline_exceeded"):
                        return "deadline_exceeded"
                    current = self.configuration.load_config()()
                    try:
                        current_plc = self.configuration.normalize_plc_config()(self.configuration.raw_plc_namespace()(current))
                    except self.policy.PlcConfigError():
                        return "cancelled_after_config_change"
                    if not current_plc["enabled"]:
                        return "cancelled_after_disable"
                    if int(current.get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0) != generation:
                        return "cancelled_after_config_change"
                    if not self.configuration.plc_current_process_owns_io()(io_owner_epoch):
                        return "cancelled_after_config_change"
                    return ""

            def persist_runtime(record: dict[str, Any], transition_kind: str = "record_update") -> None:
                with self.execution._config_io_lock():
                    persist_runtime_locked(record, transition_kind)

            def persist_runtime_locked(record: dict[str, Any], transition_kind: str = "record_update") -> None:
                with self.execution._config_io_lock():
                    entry = self.execution._plc_runtime_entry()(dispatch_id)
                    latest = dict(entry.get("latest") or {})
                    expected_version = int(entry.get("state_version") or latest.get("state_version") or 0)
                if transition_kind == "record_update" and record.get("status") == "queued":
                    persisted = latest
                elif transition_kind == "dispatch_transition":
                    persisted = self.records.plc_transition_attempting()(dispatch_id, expected_version=expected_version)
                elif transition_kind == "advance_attempt":
                    operations = record.get("operations") if isinstance(record.get("operations"), list) else []
                    operation = operations[-1] if operations and isinstance(operations[-1], dict) else {}
                    persisted = self.records.plc_advance_attempt()(
                        dispatch_id,
                        expected_version=expected_version,
                        attempt_id=str(operation.get("attempt_id") or ""),
                        bytes_written=int(operation.get("bytes_written") or 0),
                        physical_status=str(operation.get("physical_status") or "not_attempted"),
                        outcome=str(operation.get("outcome") or "not_attempted"),
                    )
                    if operation.get("physical_status") == "write_call_started":
                        target = str(operation.get("target") or "")
                        attempt = int(operation.get("attempt") or 0)
                        key = attempt_key(target, attempt)
                        declared = dict(self.execution._plc_active_attempts().get(key) or {})
                        self.execution._plc_active_attempts()[key] = {
                            **declared,
                            "dispatch_id": dispatch_id,
                            "target": target,
                            "attempt": attempt,
                            "generation": generation,
                            "started_at": int(time.time()),
                            "write_call_started": True,
                            "disable_revokes_started_io": False,
                        }
                elif transition_kind in {"finalize", "audit_failure_finalize"}:
                    raw_reason = str(record.get("error_code") or "")
                    reason = raw_reason if raw_reason in self.policy.PLC_FINALIZE_REASONS() else ""
                    persisted = self.records.plc_finalize_dispatch()(
                        dispatch_id, expected_version=expected_version, reason=reason
                    )
                else:
                    raise self.policy.PlcDispatchStateConflict()("runtime_transition_kind_not_supported", latest)
                record.clear()
                record.update(dict(persisted))
                with self.execution._config_io_lock():
                    entry = self.execution._plc_runtime_entry()(dispatch_id)
                    entry["state_version"] = int(persisted.get("state_version") or expected_version)
                    entry["latest"] = dict(persisted)

            def start_attempt(target: str, attempt: int, frame: bytes) -> dict[str, Any]:
                with self.execution._config_io_lock():
                    entry = self.execution._plc_runtime_entry()(dispatch_id)
                    if entry.get("deadline_exceeded"):
                        raise self.policy.PlcTransportError()(
                            "deadline_exceeded",
                            "PLC synchronization deadline expired before attempt declaration",
                            attempts=attempt - 1,
                        )
                    current = self.configuration.load_config()()
                    current_generation = int(current.get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0)
                    try:
                        current_plc = self.configuration.normalize_plc_config()(self.configuration.raw_plc_namespace()(current))
                    except self.policy.PlcConfigError() as exc:
                        raise self.policy.PlcTransportError()(
                            "cancelled_after_config_change",
                            "PLC configuration became invalid before attempt declaration",
                            attempts=attempt - 1,
                        ) from exc
                    if not current_plc["enabled"]:
                        raise self.policy.PlcTransportError()(
                            "cancelled_after_disable",
                            "PLC synchronization was disabled before attempt declaration",
                            attempts=attempt - 1,
                        )
                    if current_generation != generation:
                        raise self.policy.PlcTransportError()(
                            "cancelled_after_config_change",
                            "PLC configuration generation changed before attempt declaration",
                            attempts=attempt - 1,
                        )
                    if not self.configuration.plc_current_process_owns_io()(io_owner_epoch):
                        raise self.policy.PlcTransportError()(
                            "cancelled_after_config_change",
                            "PLC I/O owner lease was lost before attempt declaration",
                            attempts=attempt - 1,
                        )
                    expected_version = int(entry.get("state_version") or 0)
                    persisted = self.records.plc_start_attempt()(
                        dispatch_id, expected_version=expected_version, target=target
                    )
                    operation = dict(persisted["operations"][-1])
                    if operation.get("attempt") != attempt or operation.get("frame_hex") != frame.hex().upper():
                        raise self.policy.PlcDispatchStateConflict()("runtime_start_attempt_binding_mismatch", persisted)
                    entry = self.execution._plc_runtime_entry()(dispatch_id)
                    entry["state_version"] = int(persisted["state_version"])
                    entry["latest"] = dict(persisted)
                    self.execution._plc_active_attempts()[attempt_key(target, attempt)] = {
                        "dispatch_id": dispatch_id,
                        "target": target,
                        "attempt": attempt,
                        "generation": generation,
                        "declared_at": int(time.time()),
                        "write_call_started": False,
                        "disable_revokes_started_io": False,
                    }
                    return operation

            def finish_attempt(operation: dict[str, Any]) -> None:
                with self.execution._config_io_lock():
                    finish_attempt_locked(operation)

            def finish_attempt_locked(operation: dict[str, Any]) -> None:
                with self.execution._config_io_lock():
                    entry = self.execution._plc_runtime_entry()(dispatch_id)
                    expected_version = int(entry.get("state_version") or 0)
                raw_code = operation.get("result_code")
                raw_phase = operation.get("result_phase")
                raw_diagnostic = str(operation.get("diagnostic_source") or "")
                try:
                    terminal_code = self.policy.PlcTerminalResultCode()(raw_code)
                    terminal_phase = self.policy.PlcTransportPhase()(raw_phase)
                except (TypeError, ValueError):
                    terminal_code = self.policy.PlcTerminalResultCode().INTERNAL_TRANSITION_ERROR
                    terminal_phase = self.policy.PlcTransportPhase().INTERNAL
                    raw_diagnostic = "unknown_client_terminal_code"
                if (
                    terminal_phase not in self.policy.PLC_TERMINAL_ALLOWED_PHASES()[terminal_code]
                    or raw_diagnostic not in self.policy.PLC_TERMINAL_DIAGNOSTIC_SOURCES()[terminal_code]
                ):
                    terminal_code = self.policy.PlcTerminalResultCode().INTERNAL_TRANSITION_ERROR
                    terminal_phase = self.policy.PlcTransportPhase().INTERNAL
                    raw_diagnostic = "terminal_diagnostic_contract_violation"
                persisted = self.records.plc_finish_attempt()(
                    dispatch_id,
                    expected_version=expected_version,
                    attempt_id=str(operation.get("attempt_id") or ""),
                    terminal_result=self.policy.PlcAttemptTerminalResult()(
                        code=terminal_code,
                        phase=terminal_phase,
                        bytes_written=int(operation.get("bytes_written") or 0),
                        diagnostic_source=raw_diagnostic,
                    ),
                )
                with self.execution._config_io_lock():
                    entry = self.execution._plc_runtime_entry()(dispatch_id)
                    entry["state_version"] = int(persisted["state_version"])
                    entry["latest"] = dict(persisted)

            sync = self.execution.dispatch_fx_plc_detection_result()(
                dispatch_id=dispatch_id,
                source=source,
                request_id=request_id,
                passed=passed,
                config=self.configuration.raw_plc_namespace()(config),
                transport_factory=self.execution._plc_transport_factory(),
                load_existing=lambda _dispatch_id: None,
                persist=persist_runtime,
                before_attempt=before_attempt,
                after_attempt=after_attempt,
                on_attempt_started=start_attempt,
                on_attempt_finished=finish_attempt,
                dispatch_cancel_reason=dispatch_cancel_reason,
            )
        except self.policy.PlcDispatchStateConflict() as exc:
            sync = self.records.plc_dispatch_conflict_response()(
                exc,
                dispatch_id=dispatch_id,
                source=source,
                request_id=request_id,
                passed=passed,
            )
        except Exception:
            with self.execution._config_io_lock():
                entry = self.execution._plc_runtime_entry()(dispatch_id)
                latest = dict(entry.get("latest") or {})
                active = [
                    item for item in self.execution._plc_active_attempts().values() if str(item.get("dispatch_id") or "") == dispatch_id
                ]
            attempted = bool(latest.get("attempted")) or bool(active)
            sync = {
                **latest,
                "dispatch_id": dispatch_id,
                "source": source,
                "request_id": request_id,
                "passed": passed,
                "enabled": enabled_hint,
                "attempted": attempted,
                "status": "failed",
                "physical_status": str(latest.get("physical_status") or ("write_outcome_uncertain" if active else "not_attempted")),
                "outcome": str(latest.get("outcome") or ("outcome_uncertain" if attempted else "not_attempted")),
                "error_code": "dispatcher_internal_error",
                "control_state_unavailable": True,
                "active_attempts": [dict(item) for item in active],
                "message": "PLC synchronization control/audit finalization failed; known physical evidence was preserved",
                "updated_at": int(time.time()),
            }
        if sync.get("duplicate") and self.records.plc_dispatch_record_is_terminal()(sync):
            with self.execution._config_io_lock():
                self.execution._plc_runtime_entry()(dispatch_id)["worker_done"] = True
            result["plc_sync"] = sync
            return result
        sync.setdefault("control_generation", (generation if "generation" in locals() else 0))
        if "config" in locals():
            sync.setdefault("config_snapshot", self.configuration.plc_config_audit_snapshot()(config))
        if "created" in locals():
            try:
                with self.execution._config_io_lock():
                    entry = self.execution._plc_runtime_entry()(dispatch_id)
                    latest = dict(entry.get("latest") or {})
                    version = int(entry.get("state_version") or latest.get("state_version") or 0)
                if sync.get("status") == "disabled" and not self.records.plc_dispatch_record_is_terminal()(latest):
                    latest = self.records.plc_finalize_dispatch()(
                        dispatch_id, expected_version=version, reason="disabled"
                    )
                if self.records.plc_dispatch_record_is_terminal()(latest):
                    sync = latest
                else:
                    sync = {**latest, "worker_done": True, "audit_status": "persist_failed"}
            except Exception:
                sync = {**sync, "worker_done": True, "worker_continues": False, "audit_status": "persist_failed"}
        else:
            sync = {**sync, "worker_done": True, "worker_continues": False}
        with self.execution._config_io_lock():
            entry = self.execution._plc_runtime_entry()(dispatch_id)
            entry["worker_done"] = True
            entry["latest"] = dict(sync)
        result["plc_sync"] = sync
        return result


    def _run_queued_plc_dispatch(self, result: dict[str, Any], *, source: str, fingerprint: str) -> dict[str, Any]:
        dispatch_id, request_id, passed = self.records.plc_dispatch_identity()(result, source=source, fingerprint=fingerprint)
        with self.execution._config_io_lock():
            entry = self.execution._plc_runtime_entry()(dispatch_id)
            initial_config = self.configuration.load_config()()
            initial_generation = int(initial_config.get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0)
            entry["generation"] = initial_generation
            if entry.get("deadline_exceeded"):
                final = {**dict(entry.get("latest") or {}), "worker_cleanup_pending": False, "worker_continues": False}
                if final.get("state_version"):
                    try:
                        result["plc_sync"] = self.records.plc_finalize_dispatch()(
                            dispatch_id,
                            expected_version=int(final["state_version"]),
                            reason="deadline_exceeded",
                        )
                    except Exception:
                        result["plc_sync"] = {**final, "worker_done": True, "audit_status": "persist_failed"}
                else:
                    result["plc_sync"] = {**final, "worker_done": True, "deadline_exceeded": True}
                return result
        try:
            initial_plc = self.configuration.normalize_plc_config()(self.configuration.raw_plc_namespace()(initial_config))
        except self.policy.PlcConfigError():
            initial_plc = None
        try:
            validated_existing = self.records.get_validated_idempotent_dispatch()(
                source=source,
                request_id=request_id,
                passed=passed,
                fingerprint=fingerprint,
            )
        except self.policy.PlcDispatchStateConflict() as exc:
            result["plc_sync"] = self.records.plc_dispatch_conflict_response()(
                exc,
                dispatch_id=dispatch_id,
                source=source,
                request_id=request_id,
                passed=passed,
            )
            return result
        if (
            initial_plc is not None
            and initial_plc["enabled"]
            and validated_existing is None
            and not self.configuration.plc_activation_errors()(initial_plc)
        ):
            created = self.records.create_plc_dispatch()(
                source=source,
                request_id=request_id,
                passed=passed,
                fingerprint=fingerprint,
                expected_generation=initial_generation,
            )
            with self.execution._config_io_lock():
                entry = self.execution._plc_runtime_entry()(dispatch_id)
                entry["hydrated"] = True
                entry["state_version"] = int(created["state_version"])
                entry["latest"] = dict(created)
                entry["created_by_current_worker"] = True
        self.execution._plc_write_pending().set()
        acquired = self.execution._plc_dispatch_slots().acquire(timeout=self.policy.PLC_QUEUE_WAIT_SECONDS())
        if not acquired:
            self.execution._plc_write_pending().clear()
            with self.execution._config_io_lock():
                current = self.configuration.load_config()()
                try:
                    current_plc = self.configuration.normalize_plc_config()(self.configuration.raw_plc_namespace()(current))
                    enabled = bool(current_plc["enabled"])
                except self.policy.PlcConfigError():
                    enabled = False
                generation_changed = int(current.get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0) != initial_generation
            cancelled = not enabled or generation_changed
            with self.execution._config_io_lock():
                entry = self.execution._plc_runtime_entry()(dispatch_id)
                latest = dict(entry.get("latest") or {})
                version = int(entry.get("state_version") or latest.get("state_version") or 0)
            try:
                result["plc_sync"] = self.records.plc_finalize_dispatch()(
                    dispatch_id,
                    expected_version=version,
                    reason="cancelled_after_disable" if cancelled else "plc_dispatch_queue_timeout",
                )
            except Exception:
                result["plc_sync"] = {**latest, "worker_done": True, "audit_status": "persist_failed"}
            return result
        try:
            self.execution._plc_write_pending().clear()
            with self.execution._config_io_lock():
                entry = self.execution._plc_runtime_entry()(dispatch_id)
                if entry.get("deadline_exceeded"):
                    final = {**dict(entry.get("latest") or {}), "worker_cleanup_pending": False, "worker_continues": False}
                    try:
                        result["plc_sync"] = self.records.plc_finalize_dispatch()(
                            dispatch_id,
                            expected_version=int(final.get("state_version") or 0),
                            reason="deadline_exceeded",
                        )
                    except Exception:
                        result["plc_sync"] = {**final, "worker_done": True, "audit_status": "persist_failed"}
                    return result
            return self.execution.dispatch_plc_for_detection()(
                result,
                source=source,
                fingerprint=fingerprint,
                expected_generation=initial_generation,
            )
        finally:
            self.execution._plc_write_pending().clear()
            self.execution._plc_dispatch_slots().release()


    async def dispatch_plc_for_detection_async(self,
        result: dict[str, Any], *, source: str, fingerprint: str, inline_fake_transport: bool = False
    ) -> dict[str, Any]:
        """Run bounded synchronous serial work off the ASGI event loop."""
        worker_result = copy.deepcopy(result)
        dispatch_id, request_id, passed = self.records.plc_dispatch_identity()(result, source=source, fingerprint=fingerprint)
        self.execution._register_plc_dispatch_runtime()(dispatch_id)
        if self.execution._plc_transport_factory() is not None and inline_fake_transport:
            return self.execution._run_queued_plc_dispatch()(worker_result, source=source, fingerprint=fingerprint)
        loop = asyncio.get_running_loop()
        worker = loop.run_in_executor(
            self.execution._plc_io_executor(),
            lambda: self.execution._run_queued_plc_dispatch()(worker_result, source=source, fingerprint=fingerprint),
        )
        deadline = loop.time() + self.policy.PLC_WORKER_TOTAL_TIMEOUT_SECONDS()
        while not worker.done() and loop.time() < deadline:
            await asyncio.sleep(0.01)
        if worker.done():
            return worker.result()
        result["plc_sync"] = self.execution._plc_deadline_snapshot()(
            dispatch_id=dispatch_id,
            source=source,
            request_id=request_id,
            passed=passed,
        )
        return result
