"""Text record JSON/PostgreSQL persistence with unchanged write boundaries."""
import copy
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

Record = dict[str, Any]


TEXT_INSPECTION_TABLES = {
    "ocr_evidence": "text_ocr_evidence",
    "extractions": "text_label_extractions",
    "standards": "text_inspection_standards",
    "assets": "text_inspection_assets",
    "revisions": "text_inspection_standard_revisions",
    "records": "text_inspection_records",
    "sessions": "text_inspection_manual_sessions",
    "pages": "text_inspection_manual_pages",
    "feedback": "text_inspection_classification_feedback",
}


def record_row(kind: str, value: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    fields = {
        "ocr_evidence": ("id", "owner_user_id", "status", "created_at"),
        "extractions": ("id", "owner_user_id", "created_at"),
        "standards": ("id", "owner_user_id", "name", "material_code", "version_label", "standard_type", "status", "source_sha256", "created_at", "updated_at"),
        "assets": ("id", "standard_id", "owner_user_id", "asset_kind", "ordinal", "status", "sha256", "created_at", "updated_at"),
        "revisions": ("id", "standard_id", "owner_user_id", "revision_number", "action", "asset_id", "created_at"),
        "records": ("id", "owner_user_id", "standard_id", "comparison_id", "status", "auto_decision", "final_decision", "source_sha256", "created_at", "updated_at"),
        "sessions": ("id", "owner_user_id", "standard_id", "status", "created_at", "updated_at"),
        "pages": ("id", "session_id", "owner_user_id", "capture_id", "standard_asset_id", "status", "created_at", "updated_at"),
        "feedback": ("id", "owner_user_id", "standard_id", "asset_id", "action", "created_at"),
    }[kind]
    # Extraction queries index fields inside JSONB: write an object, not a
    # JSON-encoded string (legacy tables retain their existing representation).
    return {**{field: value.get(field, "") for field in fields}, "raw_json": value if kind in {"extractions", "ocr_evidence"} else raw}


@dataclass(frozen=True)
class TextRecordDependencies:
    runtime_repository: Callable[[], PostgresRuntimeRepository | None]
    guard: Callable[[], AbstractContextManager[Any]]
    directory: Callable[[], Path]
    tables: Callable[[], dict[str, str]]
    json_reader: Callable[[], Callable[[Path], list[Record]]]
    json_writer: Callable[[], Callable[[Path, list[Record]], None]]
    row_decoder: Callable[[], Callable[[list[Record]], list[Record]]]


class TextRecordStore:
    def __init__(self, dependencies: TextRecordDependencies):
        self.dependencies = dependencies

    def json_path(self, kind: str) -> Path:
        return self.dependencies.directory() / f"{kind}.json"

    def load(self, kind: str) -> list[dict[str, Any]]:
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            return self.dependencies.row_decoder()(repository.fetch_all(self.dependencies.tables()[kind]))
        return self.dependencies.json_reader()(self.json_path(kind))

    def save(self, kind: str, value: dict[str, Any], *, insert_only: bool = False) -> bool:
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            row = record_row(kind, value)
            if insert_only:
                return bool(repository.insert_row_once(self.dependencies.tables()[kind], row))
            repository.upsert_row(self.dependencies.tables()[kind], row)
            return True
        with self.dependencies.guard():
            values = self.dependencies.json_reader()(self.json_path(kind))
            index = next((i for i, item in enumerate(values) if str(item.get("id")) == str(value.get("id"))), None)
            unique_fields = {
                "standards": ("owner_user_id", "material_code", "version_label", "standard_type"),
                "assets": ("standard_id", "ordinal"),
                "revisions": ("standard_id", "revision_number"),
                "records": ("owner_user_id", "comparison_id"),
                "pages": ("owner_user_id", "session_id", "capture_id"),
            }.get(kind, ("id",))
            business_duplicate = next((item for item in values if all(str(item.get(field)) == str(value.get(field)) for field in unique_fields)), None)
            if insert_only and (index is not None or business_duplicate is not None):
                return False
            if index is None:
                values.insert(0, copy.deepcopy(value))
            else:
                values[index] = copy.deepcopy(value)
            self.dependencies.json_writer()(self.json_path(kind), values)
            return True

    def update_attempt(self, kind: str, value: dict[str, Any], expected_status: str = "attempting") -> bool:
        if kind not in {"records", "ocr_evidence"}:
            raise ValueError("unsupported_attempt_kind")
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            return repository.update_text_attempt(self.dependencies.tables()[kind], record_row(kind, value), expected_status)
        with self.dependencies.guard():
            previous = self.owned(kind, value["id"], value["owner_user_id"])
            if previous is None or previous.get("status") != expected_status:
                return False
            return self.save(kind, value)

    def owned(self, kind: str, record_id: str, owner_user_id: str) -> dict[str, Any] | None:
        if kind in {"ocr_evidence", "records"}:
            repository = self.dependencies.runtime_repository()
            if repository is not None:
                row = repository.fetch_one_by_columns(self.dependencies.tables()[kind], {"id": record_id, "owner_user_id": owner_user_id})
                values = self.dependencies.row_decoder()([row]) if row else []
                return values[0] if values else None
        return next((item for item in self.load(kind) if str(item.get("id")) == record_id and str(item.get("owner_user_id")) == owner_user_id), None)
