"""Pipeline task persistence; orchestration retains ownership of task write locks."""
from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Protocol
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import freeze_record as freeze_model_record

Record = dict[str, Any]


class PipelineTaskRepository(Protocol):
    def fetch_all(self, table: str) -> list[Record]: ...
    def fetch_by_primary_key(self, table: str, keys: Record) -> Record | None: ...
    def replace_all(self, table: str, rows: list[Record]) -> None: ...
    def upsert_row(self, table: str, row: Record) -> None: ...
    def delete_by_primary_key(self, table: str, keys: Record) -> None: ...


@dataclass(frozen=True)
class PipelineTaskPaths:
    data: Callable[[], Path]
    tasks: Callable[[], Path]


@dataclass(frozen=True)
class PipelineTaskRows:
    encode: Callable[[Record], Record | None]
    decode: Callable[[], Callable[[list[Record]], list[Record]]]


class PipelineTaskStore:
    def __init__(self, repository: Callable[[], PipelineTaskRepository | None], paths: PipelineTaskPaths,
                 rows: PipelineTaskRows, resolver: Callable[[], ResolverProvider]):
        self.repository, self.paths, self.rows, self.resolver = repository, paths, rows, resolver

    def load_pipeline_tasks(self) -> list[dict[str, Any]]:
        repository = self.repository()
        if repository is not None:
            return self.rows.decode()(repository.fetch_all("pipeline_tasks"))
        if not self.paths.tasks().exists():
            return []
        try:
            raw = json.loads(self.paths.tasks().read_text(encoding="utf-8"))
            return raw if isinstance(raw, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def save_pipeline_tasks(self, tasks: list[dict[str, Any]]) -> None:
        self.paths.data().mkdir(parents=True, exist_ok=True)
        repository = self.repository()
        if repository is not None:
            rows = [row for task in tasks if isinstance(task, dict) for row in [self.rows.encode(task)] if row]
            repository.replace_all("pipeline_tasks", rows)
            return
        tmp_path = self.paths.tasks().with_name(f"{self.paths.tasks().name}.tmp")
        tmp_path.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, self.paths.tasks())

    def load_pipeline_task(self, task_id: str) -> dict[str, Any] | None:
        clean_id = str(task_id or "").strip()
        if not clean_id:
            return None
        repository = self.repository()
        if repository is not None:
            row = repository.fetch_by_primary_key("pipeline_tasks", {"id": clean_id})
            raw_tasks = self.rows.decode()([row]) if row else []
            return raw_tasks[0] if raw_tasks else None
        return next((task for task in self.load_pipeline_tasks() if str(task.get("id") or "") == clean_id), None)

    def save_pipeline_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(task, dict):
            return None
        freeze_model_record(self.resolver(), task)
        row = self.rows.encode(task)
        if not row:
            return None
        repository = self.repository()
        if repository is not None:
            repository.upsert_row("pipeline_tasks", row)
            return dict(task)
        tasks = self.load_pipeline_tasks()
        clean_id = str(row["id"])
        for index, existing in enumerate(tasks):
            if str(existing.get("id") or "") == clean_id:
                tasks[index] = dict(task)
                self.save_pipeline_tasks(tasks)
                return dict(task)
        tasks.insert(0, dict(task))
        self.save_pipeline_tasks(tasks)
        return dict(task)

    def delete_pipeline_task_row(self, task_id: str) -> bool:
        clean_id = str(task_id or "").strip()
        if not clean_id:
            return False
        repository = self.repository()
        if repository is not None:
            if repository.fetch_by_primary_key("pipeline_tasks", {"id": clean_id}) is None:
                return False
            repository.delete_by_primary_key("pipeline_tasks", {"id": clean_id})
            return True
        tasks = self.load_pipeline_tasks()
        remaining = [item for item in tasks if str(item.get("id") or "") != clean_id]
        if len(remaining) == len(tasks):
            return False
        self.save_pipeline_tasks(remaining)
        return True
