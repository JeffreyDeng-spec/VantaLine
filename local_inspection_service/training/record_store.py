"""Training record persistence with per-operation repositories and explicit model binding."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Protocol
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import freeze_record as freeze_model_record
from .task_identity import training_task_path, training_task_matches_identifier, training_task_sort_key

Record = dict[str, Any]


class TrainingRecordsRepository(Protocol):
    def fetch_all(self, table: str) -> list[Record]: ...
    def upsert_row(self, table: str, row: Record) -> Any: ...


class EncodeTrainingRow(Protocol):
    def __call__(self, task: Record, *, fallback_id: str = '') -> Record | None: ...


class EnrichTrainingRecord(Protocol):
    def __call__(self, task: Record, fallback_path: Path | None = None) -> Record: ...


@dataclass(frozen=True)
class TrainingRows:
    encode: Callable[[], EncodeTrainingRow]
    decode: Callable[[], Callable[[list[Record]], list[Record]]]
    identifier: Callable[[Path], str]


class TrainingRecordStore:
    def __init__(self, repository: Callable[[], TrainingRecordsRepository | None], directory: Callable[[], Path],
                 guard: Callable[[], AbstractContextManager], resolver: Callable[[], ResolverProvider],
                 invalidate: Callable[[str], None], rows: TrainingRows, enrich: EnrichTrainingRecord):
        self.repository, self.directory, self.guard = repository, directory, guard
        self.resolver, self.invalidate, self.rows, self.enrich = resolver, invalidate, rows, enrich

    def training_task_path(self, task_id: str) -> Path:
        return training_task_path(task_id, directory=self.directory)

    def load_training_task_records(self) -> list[dict[str, Any]]:
        repository = self.repository()
        if repository is not None:
            tasks = self.rows.decode()(repository.fetch_all("training_tasks"))
            tasks.sort(key=training_task_sort_key, reverse=True)
            return [self.enrich(task) for task in tasks]
        records: list[dict[str, Any]] = []
        for path in sorted(self.directory().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            task = self.load_training_task(path)
            if task:
                records.append(self.enrich(task, path))
        return records

    def save_training_task(self, task: dict[str, Any]) -> None:
        freeze_model_record(self.resolver(), task)
        self.invalidate("training_task_pairs")
        with self.guard():
            repository = self.repository()
            if repository is not None:
                row = self.rows.encode()(task, fallback_id=str(task.get("job_id") or task.get("task_id") or task.get("id") or ""))
                if row:
                    repository.upsert_row("training_tasks", row)
                return
            self.training_task_path(str(task["job_id"])).write_text(json.dumps(task, indent=2), encoding="utf-8")

    def load_training_task(self, path: Path) -> dict[str, Any] | None:
        repository = self.repository()
        if repository is not None:
            requested = self.rows.identifier(path)
            for row in repository.fetch_all("training_tasks"):
                raw_tasks = self.rows.decode()([row])
                task = raw_tasks[0] if raw_tasks else {}
                if task and training_task_matches_identifier(task, requested, row):
                    return task
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def find_training_task(self, job_id: str) -> dict[str, Any] | None:
        requested = str(job_id or "").strip()
        if not requested:
            return None
        direct = self.load_training_task(self.training_task_path(requested))
        if direct and (
            str(direct.get("job_id") or "") == requested
            or str(direct.get("task_id") or "") == requested
            or str(direct.get("remote_training_job_id") or "") == requested
        ):
            return direct
        for task in self.load_training_task_records():
            if training_task_matches_identifier(task, requested):
                return task
        return None
