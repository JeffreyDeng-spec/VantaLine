"""Legacy text records with explicit paths, row adapters and thread-owned persistence."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

Record = dict[str, Any]


@dataclass(frozen=True)
class IncomingPaths:
    references: Callable[[], Path]
    inspections: Callable[[], Path]
    audit: Callable[[], Path]


@dataclass(frozen=True)
class IncomingRows:
    reference: Callable[[Record], Record | None]
    inspection: Callable[[Record], Record | None]
    audit: Callable[[Record], Record | None]
    decode: Callable[[list[Record]], list[Record]]


class IncomingTextStore:
    def __init__(self, repository: Callable[[], PostgresRuntimeRepository | None],
                 guard: Callable[[], AbstractContextManager[Any]], paths: IncomingPaths,
                 rows: IncomingRows, read_json: Callable[[Path], list[Record]],
                 write_json: Callable[[Path, list[Record]], None]):
        self.repository, self.guard, self.paths = repository, guard, paths
        self.rows, self.read_json, self.write_json = rows, read_json, write_json

    def load_incoming_text_references(self) -> list[dict[str, Any]]:
        repository = self.repository()
        if repository is not None:
            return self.rows.decode(repository.fetch_all("incoming_text_reference_versions"))
        with self.guard():
            return self.read_json(self.paths.references())

    def load_incoming_text_inspections(self) -> list[dict[str, Any]]:
        repository = self.repository()
        if repository is not None:
            return self.rows.decode(repository.fetch_all("incoming_text_inspections"))
        with self.guard():
            return self.read_json(self.paths.inspections())

    def load_incoming_text_reference(self, reference_id: str) -> dict[str, Any] | None:
        repository = self.repository()
        if repository is not None:
            row = repository.fetch_by_primary_key("incoming_text_reference_versions", {"id": reference_id})
            values = self.rows.decode([row]) if row else []
            return values[0] if values else None
        return next((item for item in self.load_incoming_text_references() if str(item.get("id")) == reference_id), None)

    def load_incoming_text_inspection(self, inspection_id: str) -> dict[str, Any] | None:
        repository = self.repository()
        if repository is not None:
            row = repository.fetch_by_primary_key("incoming_text_inspections", {"id": inspection_id})
            values = self.rows.decode([row]) if row else []
            return values[0] if values else None
        return next((item for item in self.load_incoming_text_inspections() if str(item.get("id")) == inspection_id), None)

    def save_incoming_text_reference(self, reference: dict[str, Any], *, insert_only: bool = False) -> bool:
        row = self.rows.reference(reference)
        if not row:
            raise RuntimeError("invalid incoming text reference row")
        repository = self.repository()
        if repository is not None:
            if insert_only:
                return bool(repository.insert_row_once("incoming_text_reference_versions", row))
            repository.upsert_row("incoming_text_reference_versions", row)
            return True
        with self.guard():
            values = self.read_json(self.paths.references())
            existing_index = next((index for index, item in enumerate(values) if str(item.get("id")) == str(reference["id"])), None)
            if existing_index is not None:
                if insert_only:
                    return False
                values[existing_index] = dict(reference)
            else:
                if any(
                    str(item.get("owner_user_id")) == str(reference.get("owner_user_id"))
                    and str(item.get("task_id")) == str(reference.get("task_id"))
                    and str(item.get("version_label")) == str(reference.get("version_label"))
                    for item in values
                ):
                    return False
                values.insert(0, dict(reference))
            self.write_json(self.paths.references(), values)
            return True

    def save_incoming_text_inspection(self, inspection: dict[str, Any], *, insert_only: bool = False) -> bool:
        row = self.rows.inspection(inspection)
        if not row:
            raise RuntimeError("invalid incoming text inspection row")
        repository = self.repository()
        if repository is not None:
            if insert_only:
                return bool(repository.insert_row_once("incoming_text_inspections", row))
            repository.upsert_row("incoming_text_inspections", row)
            return True
        with self.guard():
            values = self.read_json(self.paths.inspections())
            duplicate = next(
                (
                    item
                    for item in values
                    if str(item.get("owner_user_id")) == str(inspection.get("owner_user_id"))
                    and str(item.get("task_id")) == str(inspection.get("task_id"))
                    and str(item.get("capture_id")) == str(inspection.get("capture_id"))
                ),
                None,
            )
            existing_index = next((index for index, item in enumerate(values) if str(item.get("id")) == str(inspection["id"])), None)
            if insert_only and (duplicate is not None or existing_index is not None):
                return False
            if existing_index is None:
                values.insert(0, dict(inspection))
            else:
                values[existing_index] = dict(inspection)
            self.write_json(self.paths.inspections(), values)
            return True

    def append_incoming_text_audit(self, event: dict[str, Any]) -> None:
        repository = self.repository()
        if repository is not None:
            row = self.rows.audit(event)
            if row:
                repository.insert_row_once("audit_events", row)
            return
        with self.guard():
            values = self.read_json(self.paths.audit())
            if not any(str(item.get("id")) == str(event.get("id")) for item in values):
                values.insert(0, dict(event))
                self.write_json(self.paths.audit(), values)
