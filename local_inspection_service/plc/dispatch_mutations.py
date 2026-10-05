"""Atomic historical dispatch creation and typed record transitions; no physical I/O."""
from dataclasses import dataclass
import hashlib
import json
import time
from typing import Any
from ..plc_fx_ascii import PlcAttemptTerminalResult
from .transition_policy import PlcDispatchTransitionKind
from .dispatch_mutation_ports import DispatchMutationStorage, DispatchMutationPolicy, DispatchMutationEvents, DispatchMutationEvidence

@dataclass(frozen=True)
class PlcDispatchMutations:
    storage: DispatchMutationStorage
    policy: DispatchMutationPolicy
    events: DispatchMutationEvents
    evidence: DispatchMutationEvidence

    def create_plc_dispatch(self,
        *,
        source: str,
        request_id: str,
        passed: bool,
        fingerprint: str,
        expected_generation: int | None = None,
    ) -> dict[str, Any]:
        """Atomically derive a queued v1 record from the authoritative PLC namespace."""
        if not isinstance(source, str) or not source.strip():
            raise self.policy.PlcDispatchStateConflict()("create_source_required")
        if not isinstance(request_id, str):
            raise self.policy.PlcDispatchStateConflict()("create_request_id_must_be_string")
        if type(passed) is not bool:
            raise self.policy.PlcDispatchStateConflict()("create_passed_must_be_boolean")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise self.policy.PlcDispatchStateConflict()("create_fingerprint_required")
        if expected_generation is not None and (
            type(expected_generation) is not int or expected_generation < 0
        ):
            raise self.policy.PlcDispatchStateConflict()("create_expected_generation_invalid")
        material = json.dumps(
            {"source": source.strip(), "request_id": request_id, "fingerprint": fingerprint},
            sort_keys=True,
            ensure_ascii=True,
        )
        dispatch_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        persisted: dict[str, Any] = {}
        repository_active = self.storage.runtime_postgres_repository_or_none()() is not None

        def insert_canonical_initial(config_values: dict[str, Any]) -> None:
            nonlocal persisted
            records = self.storage.plc_dispatch_audit_records()(config_values)
            existing = next(
                (dict(item) for item in reversed(records) if str(item.get("dispatch_id") or "") == dispatch_id),
                None,
            )
            if existing is not None:
                existing = self.storage.verify_persisted_plc_dispatch()(existing)
                identity_matches = (
                    existing.get("source") == source.strip()
                    and existing.get("request_id") == request_id
                    and existing.get("passed") is passed
                    and existing.get("detection_identity") == fingerprint
                )
                if identity_matches:
                    persisted = existing
                    return
                raise self.policy.PlcDispatchStateConflict()("create_dispatch_identity_conflict", existing)
            raw_namespace = self.storage.raw_plc_namespace()(config_values)
            if raw_namespace is self.policy.PLC_CONFIG_ABSENT():
                raise self.policy.PlcDispatchStateConflict()("create_plc_namespace_absent")
            try:
                normalized = self.policy.normalize_plc_config()(raw_namespace)
            except self.policy.PlcConfigError() as exc:
                raise self.policy.PlcDispatchStateConflict()("create_plc_namespace_invalid") from exc
            if not normalized["enabled"]:
                raise self.policy.PlcDispatchStateConflict()("create_plc_disabled")
            current_generation = int(config_values.get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0)
            if expected_generation is not None and expected_generation != current_generation:
                raise self.policy.PlcDispatchStateConflict()("create_generation_mismatch")
            if repository_active and not self.storage.plc_pg_coordination_available()():
                raise self.policy.PlcDispatchStateConflict()("plc_pg_coordination_unavailable")
            planned_targets, planned_frames = self.policy.build_plc_dispatch_plan()(normalized, passed)
            created_at = int(time.time())
            immutable_record = {
                "record_schema_version": self.policy.PLC_RECORD_SCHEMA_VERSION(),
                "protocol_contract_version": self.policy.PLC_PROTOCOL_CONTRACT_VERSION(),
                "dispatch_id": dispatch_id,
                "source": source.strip(),
                "request_id": request_id,
                "passed": passed,
                "detection_identity": fingerprint,
                "enabled": True,
                "protocol": normalized["protocol"],
                "checksum_mode": normalized["checksum_mode"],
                "planned_targets": planned_targets,
                "planned_frames": planned_frames,
                "duplicate": False,
                "created_at": created_at,
                "control_generation": current_generation,
                "dispatch_deadline_at_ms": int(time.time() * 1000) + int(self.policy.PLC_QUEUE_WAIT_SECONDS() * 1000),
                "config_snapshot": self.storage.public_path_sanitized()(dict(normalized)),
                "message": "PLC dispatch queued from authoritative configuration",
            }
            record = self.events.project_plc_dispatch_events()(
                immutable_record,
                [{"seq": 1, "kind": "create", "at": created_at}],
            )
            persisted = self.storage.public_path_sanitized()({**record, "state_version": 1})
            config_values["plc_dispatches"] = [*records, persisted]

        self.storage.mutate_app_config_atomically()(insert_canonical_initial)
        return persisted


    def _apply_plc_dispatch_event(self,
        dispatch_id: str,
        *,
        expected_version: int,
        transition_kind: PlcDispatchTransitionKind,
        event_payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            kind = self.events.PlcDispatchTransitionKind()(transition_kind)
        except (TypeError, ValueError) as exc:
            raise self.policy.PlcDispatchStateConflict()("unknown_transition_kind") from exc
        deriver = self.events._PLC_TYPED_EVENT_DERIVERS().get(kind)
        expected_fields = self.events._PLC_TYPED_EVENT_FIELDS().get(kind)
        if deriver is None or expected_fields is None:
            raise self.policy.PlcDispatchStateConflict()("transition_kind_has_no_typed_handler")
        extra_fields = set(event_payload) - expected_fields
        missing_fields = expected_fields - set(event_payload)
        if extra_fields:
            raise self.policy.PlcDispatchStateConflict()(f"transition_payload_extra_field:{sorted(extra_fields)[0]}")
        if missing_fields:
            raise self.policy.PlcDispatchStateConflict()(f"transition_payload_missing_field:{sorted(missing_fields)[0]}")
        persisted: dict[str, Any] = {}

        def mutate(config: dict[str, Any]) -> None:
            nonlocal persisted
            records = self.storage.plc_dispatch_audit_records()(config)
            existing = next(
                (dict(item) for item in reversed(records) if str(item.get("dispatch_id") or "") == dispatch_id),
                None,
            )
            if existing is None:
                raise self.policy.PlcDispatchStateConflict()("transition_requires_existing_dispatch")
            current_version = int(existing.get("state_version") or 0)
            if current_version != expected_version:
                raise self.policy.PlcDispatchStateConflict()(
                    f"state_version_mismatch: expected {expected_version}, found {current_version}", existing
                )
            existing = self.storage.verify_persisted_plc_dispatch()(existing)
            candidate = deriver(dict(existing), dict(event_payload))
            self.events.validate_plc_dispatch_transition()(existing, candidate, transition_kind=kind)
            persisted = self.storage.public_path_sanitized()({**candidate, "state_version": current_version + 1})
            remaining = [item for item in records if str(item.get("dispatch_id") or "") != dispatch_id]
            config["plc_dispatches"] = [*remaining, persisted]

        self.storage.mutate_app_config_atomically()(mutate)
        return persisted


    def plc_transition_attempting(self, dispatch_id: str, *, expected_version: int) -> dict[str, Any]:
        return self.events._apply_plc_dispatch_event()(
            dispatch_id,
            expected_version=expected_version,
            transition_kind=self.events.PlcDispatchTransitionKind().DISPATCH_TRANSITION,
            event_payload={},
        )


    def plc_start_attempt(self, dispatch_id: str, *, expected_version: int, target: str) -> dict[str, Any]:
        if not isinstance(target, str):
            raise self.policy.PlcDispatchStateConflict()("start_attempt_target_invalid")
        return self.events._apply_plc_dispatch_event()(
            dispatch_id,
            expected_version=expected_version,
            transition_kind=self.events.PlcDispatchTransitionKind().START_ATTEMPT,
            event_payload={"target": target},
        )


    def plc_advance_attempt(self,
        dispatch_id: str,
        *,
        expected_version: int,
        attempt_id: str,
        bytes_written: int,
        physical_status: str,
        outcome: str,
    ) -> dict[str, Any]:
        if not isinstance(attempt_id, str) or not attempt_id:
            raise self.policy.PlcDispatchStateConflict()("advance_attempt_id_invalid")
        if physical_status not in {"write_call_started", "not_written", "partial_write", "full_frame_written"}:
            raise self.policy.PlcDispatchStateConflict()("advance_attempt_physical_status_invalid")
        if outcome not in {"write_outcome_uncertain", "not_written", "outcome_uncertain", "awaiting_acknowledgement"}:
            raise self.policy.PlcDispatchStateConflict()("advance_attempt_outcome_invalid")

        return self.events._apply_plc_dispatch_event()(
            dispatch_id,
            expected_version=expected_version,
            transition_kind=self.events.PlcDispatchTransitionKind().ADVANCE_ATTEMPT,
            event_payload={
                "attempt_id": attempt_id,
                "bytes_written": bytes_written,
                "physical_status": physical_status,
                "outcome": outcome,
            },
        )


    def plc_finish_attempt(self,
        dispatch_id: str,
        *,
        expected_version: int,
        attempt_id: str,
        terminal_result: PlcAttemptTerminalResult,
    ) -> dict[str, Any]:
        if not isinstance(attempt_id, str) or not attempt_id:
            raise self.policy.PlcDispatchStateConflict()("finish_attempt_id_invalid")
        if type(terminal_result) is not self.evidence.PlcAttemptTerminalResult():
            raise self.policy.PlcDispatchStateConflict()("finish_attempt_result_type_invalid")
        result_code = terminal_result.code
        if not isinstance(result_code, self.evidence.PlcTerminalResultCode()) or result_code not in self.evidence.PLC_TERMINAL_RESULT_CODES():
            raise self.policy.PlcDispatchStateConflict()("finish_attempt_result_code_invalid")
        if not isinstance(terminal_result.phase, self.evidence.PlcTransportPhase()):
            raise self.policy.PlcDispatchStateConflict()("finish_attempt_result_phase_invalid")
        if terminal_result.phase not in self.evidence.PLC_TERMINAL_ALLOWED_PHASES()[result_code]:
            raise self.policy.PlcDispatchStateConflict()("finish_attempt_result_phase_not_allowed")
        if type(terminal_result.bytes_written) is not int or terminal_result.bytes_written < 0:
            raise self.policy.PlcDispatchStateConflict()("finish_attempt_result_bytes_invalid")
        if not isinstance(terminal_result.diagnostic_source, str):
            raise self.policy.PlcDispatchStateConflict()("finish_attempt_diagnostic_source_invalid")
        if terminal_result.diagnostic_source not in self.evidence.PLC_TERMINAL_DIAGNOSTIC_SOURCES()[result_code]:
            raise self.policy.PlcDispatchStateConflict()("finish_attempt_diagnostic_source_not_allowed")

        return self.events._apply_plc_dispatch_event()(
            dispatch_id,
            expected_version=expected_version,
            transition_kind=self.events.PlcDispatchTransitionKind().FINISH_ATTEMPT,
            event_payload={
                "attempt_id": attempt_id,
                "result_code": result_code.value,
                "result_phase": terminal_result.phase.value,
                "bytes_written": terminal_result.bytes_written,
                "diagnostic_source": terminal_result.diagnostic_source,
            },
        )


    def plc_mark_deadline(self, dispatch_id: str, *, expected_version: int) -> dict[str, Any]:
        return self.events._apply_plc_dispatch_event()(
            dispatch_id,
            expected_version=expected_version,
            transition_kind=self.events.PlcDispatchTransitionKind().DEADLINE,
            event_payload={},
        )


    def plc_finalize_dispatch(self,
        dispatch_id: str, *, expected_version: int, reason: str = ""
    ) -> dict[str, Any]:
        if reason not in self.policy.PLC_FINALIZE_REASONS():
            raise self.policy.PlcDispatchStateConflict()("finalize_reason_invalid")

        kind = (
            self.events.PlcDispatchTransitionKind().AUDIT_FAILURE_FINALIZE
            if reason == "audit_persist_failed_after_ack"
            else self.events.PlcDispatchTransitionKind().FINALIZE
        )
        return self.events._apply_plc_dispatch_event()(
            dispatch_id,
            expected_version=expected_version,
            transition_kind=kind,
            event_payload={"reason": reason},
        )


    def plc_cancel_dispatch(self,
        dispatch_id: str, *, expected_version: int, reason: str
    ) -> dict[str, Any]:
        if reason not in {"cancelled_after_disable", "cancelled_after_config_change"}:
            raise self.policy.PlcDispatchStateConflict()("cancel_reason_invalid")
        return self.events.plc_finalize_dispatch()(
            dispatch_id,
            expected_version=expected_version,
            reason=reason,
        )


    def persist_plc_dispatch_record(self,
        record: dict[str, Any], *, expected_version: int | None = None, transition_kind: Any = None
    ) -> dict[str, Any]:
        """Retired raw compatibility shim; all creates and mutations use typed handlers."""
        reason = (
            "public_raw_transition_kind_not_allowed"
            if transition_kind is not None
            else "public_raw_dispatch_persistence_not_allowed"
        )
        raise self.policy.PlcDispatchStateConflict()(
            reason,
            self.storage.plc_dispatch_existing()(str(record.get("dispatch_id") or "")),
        )
