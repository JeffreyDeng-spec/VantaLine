"""Retained dispatch identity, cache hydration and deadline evidence projection."""
from dataclasses import dataclass
import hashlib
import json
import time
from typing import Any
from .dispatch_runtime_state_ports import DispatchRuntimeState, DispatchRuntimeRecords, DispatchRuntimePolicy

@dataclass(frozen=True)
class PlcDispatchRuntimeState:
    state: DispatchRuntimeState
    records: DispatchRuntimeRecords
    policy: DispatchRuntimePolicy

    def _plc_runtime_entry(self, dispatch_id: str) -> dict[str, Any]:
        entry = self.state._plc_dispatch_runtime().setdefault(
            dispatch_id,
            {
                "dispatch_id": dispatch_id,
                "state_version": 0,
                "deadline_exceeded": False,
                "worker_started": False,
                "worker_done": False,
                "latest": {},
                "hydrated": False,
            },
        )
        if len(self.state._plc_dispatch_runtime()) > self.state._PLC_RUNTIME_LIMIT():
            for key, candidate in list(self.state._plc_dispatch_runtime().items()):
                if key != dispatch_id and candidate.get("worker_done"):
                    self.state._plc_dispatch_runtime().pop(key, None)
                    if len(self.state._plc_dispatch_runtime()) <= self.state._PLC_RUNTIME_LIMIT():
                        break
        return entry


    def _hydrate_plc_runtime_entry(self, dispatch_id: str) -> dict[str, Any]:
        entry = self.state._plc_runtime_entry()(dispatch_id)
        if entry.get("hydrated"):
            return entry
        config = self.records.load_config()()
        existing = next(
            (
                dict(item)
                for item in reversed(self.records.plc_dispatch_audit_records()(config))
                if str(item.get("dispatch_id") or "") == dispatch_id
            ),
            None,
        )
        if existing:
            entry["state_version"] = int(existing.get("state_version") or 0)
            entry["latest"] = existing
            entry["worker_done"] = bool(existing.get("worker_done"))
        entry["hydrated"] = True
        return entry


    def _register_plc_dispatch_runtime(self, dispatch_id: str) -> None:
        with self.state._config_io_lock():
            self.state._hydrate_plc_runtime_entry()(dispatch_id)


    def _plc_deadline_snapshot(self,
        *, dispatch_id: str, source: str, request_id: str, passed: bool
    ) -> dict[str, Any]:
        with self.state._config_io_lock():
            entry = self.state._plc_runtime_entry()(dispatch_id)
            entry["deadline_exceeded"] = True
            entry["deadline_exceeded_at"] = int(time.time())
            active = [
                item for item in self.state._plc_active_attempts().values() if str(item.get("dispatch_id") or "") == dispatch_id
            ]
            latest = dict(entry.get("latest") or {})
            attempted = bool(active) or bool(latest.get("attempted"))
            physical_status = (
                str(latest.get("physical_status") or "write_outcome_uncertain")
                if attempted
                else "not_attempted"
            )
            worker_continues = bool(active)
            worker_cleanup_pending = bool(entry.get("worker_started")) and not worker_continues and not bool(entry.get("worker_done"))
            expected_version = int(entry.get("state_version") or latest.get("state_version") or 0)
            try:
                persisted = self.records.plc_mark_deadline()(dispatch_id, expected_version=expected_version)
                entry["state_version"] = int(persisted["state_version"])
                entry["latest"] = dict(persisted)
                return {
                    **persisted,
                    "active_attempts": [dict(item) for item in active],
                    "worker_continues": worker_continues,
                    "worker_cleanup_pending": worker_cleanup_pending,
                }
            except Exception:
                return {
                    **latest,
                    "attempted": attempted,
                    "physical_status": physical_status,
                    "outcome": "outcome_uncertain" if attempted else "deadline_exceeded",
                    "error_code": "plc_worker_total_timeout",
                    "deadline_exceeded": True,
                    "provisional": True,
                    "active_attempts": [dict(item) for item in active],
                    "audit_status": "persist_failed",
                }


    def _plc_active_attempts_snapshot(self) -> list[dict[str, Any]]:
        with self.state._config_io_lock():
            return [dict(item) for item in self.state._plc_active_attempts().values()]


    def plc_dispatch_identity(self, result: dict[str, Any], *, source: str, fingerprint: str) -> tuple[str, str, bool]:
        request_id = str(result.get("request_id") or "")
        passed = bool(result.get("passed"))
        material = json.dumps(
            {"source": source, "request_id": request_id, "fingerprint": fingerprint},
            sort_keys=True,
            ensure_ascii=True,
        )
        dispatch_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        return dispatch_id, request_id, passed


    def plc_dispatch_record_is_terminal(self, record: dict[str, Any]) -> bool:
        return str(record.get("status") or "") in {"acknowledged", "failed", "disabled"} and not bool(
            record.get("provisional")
        )


    def plc_dispatch_is_pristine_queue(self, record: dict[str, Any]) -> bool:
        """Only a dispatch with proof that physical I/O never began may change owners."""
        events = record.get("events") if isinstance(record.get("events"), list) else []
        operations = record.get("operations") if isinstance(record.get("operations"), list) else []
        return bool(
            record.get("status") == "queued"
            and record.get("attempted") is False
            and not operations
            and len(events) == 1
            and isinstance(events[0], dict)
            and events[0].get("kind") == "create"
        )


    def plc_dispatch_adoption_blocker(self,
        record: dict[str, Any],
        *,
        settings: dict[str, Any],
        generation: int,
        now_ms: int | None = None,
    ) -> str:
        """Return a no-I/O reason when a queued record is unsafe or stale to adopt."""
        if not self.policy.plc_dispatch_is_pristine_queue()(record):
            return "not_pristine"
        if record.get("record_schema_version") != 2 or record.get("protocol_contract_version") != 2:
            return "version_not_adoptable"
        if int(record.get("control_generation") or -1) != generation:
            return "generation_changed"
        if self.policy._plc_canonical()(record.get("config_snapshot")) != self.policy._plc_canonical()(settings):
            return "config_changed"
        deadline = record.get("dispatch_deadline_at_ms")
        if type(deadline) is not int:
            return "deadline_missing"
        if int(deadline) <= (int(time.time() * 1000) if now_ms is None else now_ms):
            return "deadline_expired"
        return ""
