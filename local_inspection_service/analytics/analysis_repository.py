"""Analysis persistence with original lock and replace/upsert semantics."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
from fastapi import HTTPException

from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from ..storage.runtime_records import data_analysis_record_row, row_raw_json_list
from .analysis_records import sanitize_data_analysis_record_id

Record = dict[str, Any]


@dataclass(frozen=True)
class AnalysisStoreDependencies:
    path: Callable[[], Path]
    runtime_repository: Callable[[], PostgresRuntimeRepository | None]
    lock: Callable[[], AbstractContextManager]
    ensure_dirs: Callable[[], None]


class AnalysisRepository:
    def __init__(self, dependencies: AnalysisStoreDependencies,
                 normalize: Callable[[Record], Record | None]):
        self.dependencies = dependencies
        self.normalize = normalize

    def data_analysis_records_temp_path(self) -> Path:
        return self.dependencies.path().with_name(f"{self.dependencies.path().name}.tmp")

    def load_data_analysis_records(self) -> list[dict[str, Any]]:
        self.dependencies.ensure_dirs()
        with self.dependencies.lock():
            repository = self.dependencies.runtime_repository()
            if repository is not None:
                raw_records = row_raw_json_list(repository.fetch_all("data_analysis_records"))
                records = []
                for raw in raw_records:
                    record = self.normalize(raw)
                    if record:
                        records.append(record)
                records.sort(key=lambda item: (int(item.get("created_at") or 0), str(item.get("record_id") or "")), reverse=True)
                return records
            if not self.dependencies.path().exists():
                return []
            try:
                data = json.loads(self.dependencies.path().read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            raw_records = data.get("records") if isinstance(data, dict) else data
            if not isinstance(raw_records, list):
                return []
            records = []
            for raw in raw_records:
                record = self.normalize(raw)
                if record:
                    records.append(record)
            records.sort(key=lambda item: (int(item.get("created_at") or 0), str(item.get("record_id") or "")), reverse=True)
            return records

    def save_data_analysis_records(self, records: list[dict[str, Any]]) -> None:
        self.dependencies.ensure_dirs()
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            rows = [row for record in records if isinstance(record, dict) for row in [data_analysis_record_row(record)] if row]
            with self.dependencies.lock():
                repository.replace_all("data_analysis_records", rows)
            return
        payload = {"records": records}
        with self.dependencies.lock():
            tmp_path = self.data_analysis_records_temp_path()
            tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp_path, self.dependencies.path())

    def load_data_analysis_record(self, record_id: str) -> dict[str, Any] | None:
        clean_id = sanitize_data_analysis_record_id(record_id)
        if not clean_id:
            return None
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            row = repository.fetch_by_primary_key("data_analysis_records", {"record_id": clean_id})
            raw_records = row_raw_json_list([row]) if row else []
            return self.normalize(raw_records[0]) if raw_records else None
        return next((record for record in self.load_data_analysis_records() if record.get("record_id") == clean_id), None)

    def save_data_analysis_record(self, record: dict[str, Any], *, prepend: bool = False, max_records: int = 5000) -> dict[str, Any] | None:
        normalized = self.normalize(record)
        if not normalized:
            return None
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            row = data_analysis_record_row(normalized)
            if row:
                with self.dependencies.lock():
                    repository.upsert_row("data_analysis_records", row)
            return normalized
        with self.dependencies.lock():
            records = self.load_data_analysis_records()
            clean_id = str(normalized.get("record_id") or "")
            for index, existing in enumerate(records):
                if str(existing.get("record_id") or "") == clean_id:
                    records[index] = normalized
                    self.save_data_analysis_records(records[:max_records])
                    return normalized
            if prepend:
                records.insert(0, normalized)
            else:
                records.append(normalized)
            self.save_data_analysis_records(records[:max_records])
        return normalized

    def delete_data_analysis_record(self, clean_id: str, *, missing_ok: bool = False) -> str | None:
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            repository.delete_by_primary_key("data_analysis_records", {"record_id": clean_id})
            return clean_id
        with self.dependencies.lock():
            records = self.load_data_analysis_records()
            remaining = [item for item in records if str(item.get("record_id") or "") != clean_id]
            if len(remaining) == len(records):
                if missing_ok:
                    return None
                raise HTTPException(status_code=404, detail="Analysis record not found")
            self.save_data_analysis_records(remaining)
        return clean_id
