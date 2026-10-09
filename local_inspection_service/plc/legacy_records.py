"""Retained PLC audit projection and persisted dispatch identity checks."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import hashlib
import json
from typing import Any
from .errors import PlcDispatchStateConflict

Record = dict[str, Any]


@dataclass(frozen=True)
class DispatchRecordSources:
    config: Callable[[], Callable[[], Record]]
    namespace: Callable[[], Callable[[Record], Any]]
    sanitize: Callable[[], Callable[[Record], Record]]
    records: Callable[[], Callable[..., list[Record]]]
    existing: Callable[[], Callable[[str], Record | None]]
    verify: Callable[[], Callable[[Record], Record]]


@dataclass(frozen=True)
class DispatchRecordPolicy:
    absent: Callable[[], Any]
    guard: Callable[[], AbstractContextManager]
    conflict: Callable[[], type[PlcDispatchStateConflict]]
    clock: Callable[[], Callable[[], float]]


@dataclass(frozen=True)
class LegacyDispatchRecords:
    sources: DispatchRecordSources
    policy: DispatchRecordPolicy

    def plc_dispatch_audit_records(self, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        current = config if isinstance(config, dict) else self.sources.config()()
        records = current.get("plc_dispatches") if isinstance(current.get("plc_dispatches"), list) else []
        return [dict(item) for item in records if isinstance(item, dict)]


    def raw_plc_namespace(self, config: dict[str, Any]) -> Any:
        return config["plc"] if "plc" in config else self.policy.absent()


    def plc_config_audit_snapshot(self, config: dict[str, Any]) -> dict[str, Any]:
        raw = self.sources.namespace()(config)
        if isinstance(raw, dict):
            return self.sources.sanitize()(dict(raw))
        if raw is self.policy.absent():
            return {"namespace_present": False, "enabled": False}
        return {"namespace_present": True, "namespace_valid": False, "value_type": type(raw).__name__}


    def plc_dispatch_existing(self, dispatch_id: str) -> dict[str, Any] | None:
        for record in reversed(self.sources.records()()):
            if str(record.get("dispatch_id") or "") == dispatch_id:
                return record
        return None


    def get_validated_idempotent_dispatch(self,
        *, source: str, request_id: str, passed: bool, fingerprint: str
    ) -> dict[str, Any] | None:
        material = json.dumps(
            {"source": source.strip(), "request_id": request_id, "fingerprint": fingerprint},
            sort_keys=True,
            ensure_ascii=True,
        )
        dispatch_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        with self.policy.guard():
            existing = self.sources.existing()(dispatch_id)
        if existing is None:
            return None
        verified = self.sources.verify()(existing)
        if not (
            verified.get("source") == source.strip()
            and verified.get("request_id") == request_id
            and verified.get("passed") is passed
            and verified.get("detection_identity") == fingerprint
        ):
            raise self.policy.conflict()("create_dispatch_identity_conflict", verified)
        return verified


    def plc_dispatch_conflict_response(self,
        conflict: PlcDispatchStateConflict,
        *,
        dispatch_id: str,
        source: str,
        request_id: str,
        passed: bool,
    ) -> dict[str, Any]:
        authoritative = dict(conflict.authoritative)
        return {
            **authoritative,
            "dispatch_id": dispatch_id,
            "source": source,
            "request_id": request_id,
            "passed": passed,
            "duplicate": False,
            "status": "failed",
            "error_code": conflict.reason,
            "audit_status": "state_conflict",
            "attempted": bool(authoritative.get("attempted")),
            "worker_done": True,
            "worker_continues": False,
            "message": "Stored PLC dispatch requires migration or manual corruption review; no I/O was attempted",
            "updated_at": int(self.policy.clock()()),
        }
