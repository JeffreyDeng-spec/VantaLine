"""Training records, authorized lifecycle and account-filtered views."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from ..model_profiles.dependencies import ResolverProvider
from ..runtime.training_tasks import TrainingTaskRuntime, TrainingTaskState
from .record_store import TrainingRecordStore, TrainingRows, TrainingRecordsRepository, EnrichTrainingRecord
from .task_lifecycle import TrainingTaskLifecycle, TrainingTaskRecords, TrainingTaskWrites, RequireTrainingAccess
from .task_views import TrainingTaskViews, TrainingViewAccess
Record = dict[str, Any]

@dataclass(frozen=True)
class TrainingRecordAccess:
    repository: Callable[[], TrainingRecordsRepository | None]
    directory: Callable[[], Path]
    resolver: Callable[[], ResolverProvider]
    invalidate: Callable[[str], None]
    enrich: EnrichTrainingRecord

class TrainingStateWorkflows:
    def __init__(self, *, runtime: TrainingTaskRuntime, storage: TrainingRecordAccess,
                 rows: TrainingRows, writes: TrainingTaskWrites,
                 require_access: RequireTrainingAccess, view_access: TrainingViewAccess):
        self.runtime = runtime
        self.records = TrainingRecordStore(
            repository=storage.repository, directory=storage.directory,
            guard=lambda: self.runtime.lock, resolver=storage.resolver,
            invalidate=storage.invalidate, rows=rows, enrich=storage.enrich,
        )
        self.lifecycle = TrainingTaskLifecycle(
            state=TrainingTaskState(guard=lambda: self.runtime.lock,
                                   threads=lambda: self.runtime.threads,
                                   tombstones=lambda: self.runtime.tombstones),
            records=TrainingTaskRecords(
                path=lambda job_id: self.training_task_path(job_id),
                load=lambda path: self.load_training_task(path),
                save=lambda task: self.save_training_task(task),
                find=lambda job_id: self.find_training_task(job_id),
            ),
            writes=writes, require_access=require_access,
        )
        self.views = TrainingTaskViews(
            records=lambda: self.load_training_task_records(),
            refresh=lambda task: self.refresh_interrupted_local_training_task(task),
            access=view_access,
        )

    def training_task_path(self, task_id: str) -> Path:
        return self.records.training_task_path(task_id)

    def load_training_task_records(self) -> list[dict[str, Any]]:
        return self.records.load_training_task_records()

    def save_training_task(self, task: dict[str, Any]) -> None:
        return self.records.save_training_task(task)

    def load_training_task(self, path: Path) -> dict[str, Any] | None:
        return self.records.load_training_task(path)

    def find_training_task(self, job_id: str) -> dict[str, Any] | None:
        return self.records.find_training_task(job_id)

    def local_training_task_is_active(self, task: dict[str, Any]) -> bool:
        return self.lifecycle.local_training_task_is_active(task)

    def refresh_interrupted_local_training_task(self, task: dict[str, Any]) -> dict[str, Any]:
        return self.lifecycle.refresh_interrupted_local_training_task(task)

    def public_refreshed_training_task(self, task: dict[str, Any], *, allow_remote_refresh: bool=False) -> dict[str, Any]:
        return self.views.public_refreshed_training_task(task, allow_remote_refresh=allow_remote_refresh)

    def list_training_tasks(self, user: dict[str, Any] | None=None, target_user_id: str | None=None, *, allow_remote_refresh: bool=False) -> list[dict[str, Any]]:
        return self.views.list_training_tasks(user, target_user_id, allow_remote_refresh=allow_remote_refresh)

    def public_training_task(self, task: dict[str, Any]) -> dict[str, Any]:
        return self.views.public_training_task(task)

    def update_training_task(self, job_id: str, **updates: Any) -> dict[str, Any]:
        return self.lifecycle.update_training_task(job_id, **updates)

    def stop_training_task_process(self, task: dict[str, Any], *, note: str) -> dict[str, Any]:
        return self.lifecycle.stop_training_task_process(task, note=note)

    def delete_training_task_record(self, job_id: str, user: dict[str, Any], *, missing_ok: bool=False) -> dict[str, Any] | None:
        return self.lifecycle.delete_training_task_record(job_id, user, missing_ok=missing_ok)
