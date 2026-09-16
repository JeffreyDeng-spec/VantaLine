"""Candidate persistence with existing read-time repair and transaction boundaries."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
from fastapi import HTTPException
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from ..storage.runtime_records import accessory_candidate_row, file_stem_identifier, row_raw_json_list

Record = dict[str, Any]


@dataclass(frozen=True)
class CandidateStoreDependencies:
    runtime_repository: Callable[[], PostgresRuntimeRepository | None]
    directory: Callable[[], Path]
    lock: Callable[[], AbstractContextManager]
    ensure_task_ids: Callable[[Record], bool]
    safe_id: Callable[[Any], str]
    created_at: Callable[[Record, Path], int]
    updated_at: Callable[[Record, Path], int]


class CandidateRepository:
    def __init__(self, dependencies: CandidateStoreDependencies):
        self.dependencies = dependencies

    def load_accessory_candidate(self, candidate_id: str) -> dict[str, Any]:
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            row = repository.fetch_by_primary_key("accessory_candidates", {"id": candidate_id})
            if row is None:
                raise HTTPException(status_code=404, detail="Accessory candidate not found")
            candidate = row_raw_json_list([row])[0]
            if self.dependencies.ensure_task_ids(candidate):
                self.save_accessory_candidate(self.dependencies.directory() / f"{candidate_id}.json", candidate)
            return candidate
        path = self.dependencies.directory() / f"{candidate_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Accessory candidate not found")
        with self.dependencies.lock():
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if self.dependencies.ensure_task_ids(candidate):
                self.save_accessory_candidate(path, candidate)
            return candidate

    def save_accessory_candidate(self, path: Path, candidate: dict[str, Any]) -> None:
        with self.dependencies.lock():
            repository = self.dependencies.runtime_repository()
            if repository is not None:
                fallback_id = file_stem_identifier(path)
                row = accessory_candidate_row(candidate, fallback_id=fallback_id)
                if row:
                    repository.upsert_row("accessory_candidates", row)
                return
            self.write_accessory_candidate_file(path, candidate)

    def delete_accessory_candidate(self, candidate_id: str, path: Path | None = None) -> bool:
        clean_id = str(candidate_id or "").strip()
        if not clean_id:
            return False
        with self.dependencies.lock():
            repository = self.dependencies.runtime_repository()
            if repository is not None:
                if repository.fetch_by_primary_key("accessory_candidates", {"id": clean_id}) is None:
                    return False
                repository.delete_by_primary_key("accessory_candidates", {"id": clean_id})
                return True
            candidate_path = path or self.dependencies.directory() / f"{clean_id}.json"
            if not candidate_path.exists():
                return False
            candidate_path.unlink()
            return True

    def accessory_candidate_record_path(self, candidate: dict[str, Any], fallback_id: str = "candidate") -> Path:
        candidate_id = self.dependencies.safe_id(candidate.get("id") or candidate.get("candidate_id") or fallback_id or "candidate")
        return self.dependencies.directory() / f"{candidate_id}.json"

    def list_accessory_candidate_records(self, *, reverse: bool = True) -> list[tuple[Path, dict[str, Any]]]:
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            records: list[tuple[Path, dict[str, Any]]] = []
            for row in repository.fetch_all("accessory_candidates"):
                raw_candidates = row_raw_json_list([row])
                if not raw_candidates:
                    continue
                candidate = raw_candidates[0]
                candidate_id = str(candidate.get("id") or row.get("id") or "").strip()
                if candidate_id and not candidate.get("id"):
                    candidate["id"] = candidate_id
                records.append((self.accessory_candidate_record_path(candidate, candidate_id), candidate))
            records.sort(
                key=lambda item: (
                    self.dependencies.updated_at(item[1], item[0]),
                    self.dependencies.created_at(item[1], item[0]),
                    str(item[1].get("id") or ""),
                ),
                reverse=reverse,
            )
            return records
        records = []
        for path in sorted(self.dependencies.directory().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=reverse):
            with self.dependencies.lock():
                try:
                    candidate = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
            records.append((path, candidate))
        return records

    def write_accessory_candidate_file(self, path: Path, candidate: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
