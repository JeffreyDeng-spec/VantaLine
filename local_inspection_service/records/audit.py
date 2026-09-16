"""Existing timestamp precedence and audit projection without record mutation."""
from pathlib import Path
from typing import Any
from .ownership import RecordOwnership


def coerce_record_timestamp(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def path_mtime_timestamp(path: Path | None) -> int:
    if not path:
        return 0
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return 0


def record_created_at(record: dict[str, Any] | None, fallback_path: Path | None = None) -> int:
    if isinstance(record, dict):
        for key in ("created_at", "created", "started_at", "queued_at", "requested_at", "completed_at", "updated_at"):
            timestamp = coerce_record_timestamp(record.get(key))
            if timestamp:
                return timestamp
    return path_mtime_timestamp(fallback_path)


def record_updated_at(record: dict[str, Any] | None, fallback_path: Path | None = None) -> int:
    if isinstance(record, dict):
        for key in ("updated_at", "completed_at", "failed_at", "confirmed_at", "started_at", "created_at"):
            timestamp = coerce_record_timestamp(record.get(key))
            if timestamp:
                return timestamp
    return path_mtime_timestamp(fallback_path)


class RecordAudit:
    def __init__(self, ownership: RecordOwnership):
        self.ownership = ownership

    def record_audit_fields(self, record: dict[str, Any] | None, fallback_path: Path | None = None) -> dict[str, Any]:
        return {
            "created_at": record_created_at(record, fallback_path),
            "updated_at": record_updated_at(record, fallback_path),
            "owner_user_id": self.ownership.record_owner_id(record),
            "owner_username": self.ownership.record_owner_username(record),
        }

    def enrich_record_audit_fields(self, record: dict[str, Any], fallback_path: Path | None = None) -> dict[str, Any]:
        copy = dict(record)
        copy.update(self.record_audit_fields(copy, fallback_path))
        return copy
