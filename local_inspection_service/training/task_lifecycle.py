"""Training activity, stopped-state updates and authorized deletion orchestration."""
from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import time
from typing import Any, Protocol
from fastapi import HTTPException
from ..runtime.training_tasks import TrainingTaskState
from .record_store import EncodeTrainingRow

Record = dict[str, Any]


def training_task_uses_worker(task: dict[str, Any]) -> bool:
    executor = str(task.get("training_executor") or "").strip().lower()
    if executor == "runpod":
        return False
    if executor == "worker":
        return True
    remote_job_id = str(task.get("remote_training_job_id") or "").strip()
    return remote_job_id.startswith("worker_") or bool(task.get("worker_transfer_required"))


class TrainingDeletionRepository(Protocol):
    def delete_by_primary_key(self, table: str, keys: Record) -> None: ...


class RequireTrainingAccess(Protocol):
    def __call__(self, record: Record, user: Record, *, write: bool = False) -> None: ...


@dataclass(frozen=True)
class TrainingTaskRecords:
    path: Callable[[str], Path]
    load: Callable[[Path], Record | None]
    save: Callable[[Record], None]
    find: Callable[[str], Record | None]


@dataclass(frozen=True)
class TrainingTaskWrites:
    repository: Callable[[], TrainingDeletionRepository | None]
    row: EncodeTrainingRow
    invalidate: Callable[[str], None]


class TrainingTaskLifecycle:
    def __init__(self, state: TrainingTaskState, records: TrainingTaskRecords,
                 writes: TrainingTaskWrites, require_access: RequireTrainingAccess):
        self.state, self.records, self.writes, self.require_access = state, records, writes, require_access

    def local_training_task_is_active(self, task: dict[str, Any]) -> bool:
        job_id = str(task.get("job_id") or task.get("task_id") or "").strip()
        if not job_id:
            return False
        thread = self.state.threads().get(job_id)
        if thread and thread.is_alive():
            return True
        pid = task.get("training_pid")
        if not pid:
            return False
        try:
            return Path(f"/proc/{int(pid)}").exists()
        except (TypeError, ValueError):
            return False

    def refresh_interrupted_local_training_task(self, task: dict[str, Any]) -> dict[str, Any]:
        if training_task_uses_worker(task):
            return task
        if task.get("status") not in {"queued", "running"}:
            return task
        if self.local_training_task_is_active(task):
            return task
        job_id = str(task.get("job_id") or task.get("task_id") or "").strip()
        if not job_id:
            return task
        return self.update_training_task(
            job_id,
            status="stopped",
            progress=100,
            stopped_at=int(time.time()),
            completed_at=int(time.time()),
            error="Local training worker is no longer active. Delete and retry the task.",
            note="本地训练任务已中断；请删除后重试。",
        )

    def update_training_task(self, job_id: str, **updates: Any) -> dict[str, Any]:
        path = self.records.path(job_id)
        with self.state.guard():
            tombstone = self.state.tombstones().get(str(job_id or "").strip())
            if tombstone:
                existing = self.records.load(path)
                return dict(existing or tombstone)
            task = self.records.load(path) or {"job_id": job_id, "created_at": int(time.time())}
            task.update(updates)
            self.records.save(task)
            return task

    def stop_training_task_process(self, task: dict[str, Any], *, note: str) -> dict[str, Any]:
        job_id = str(task.get("job_id") or task.get("task_id") or "").strip()
        if not job_id:
            return task
        pid = task.get("training_pid")
        if task.get("status") == "running" and pid:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (OSError, ValueError):
                pass
        if task.get("status") in {"queued", "running"}:
            return self.update_training_task(
                job_id,
                status="stopped",
                progress=100,
                stopped_at=int(time.time()),
                completed_at=int(time.time()),
                note=note,
            )
        return task

    def delete_training_task_record(self, job_id: str, user: dict[str, Any], *, missing_ok: bool = False) -> dict[str, Any] | None:
        clean_job_id = str(job_id or "").strip()
        if not clean_job_id:
            return None
        task = self.records.find(clean_job_id)
        if not task:
            if missing_ok:
                return None
            raise HTTPException(status_code=404, detail="Training task not found")
        canonical_job_id = str(task.get("job_id") or task.get("task_id") or clean_job_id).strip() or clean_job_id
        path = self.records.path(canonical_job_id)
        self.require_access(task, user, write=True)
        preserve_stopped_record = (
            not training_task_uses_worker(task)
            and self.local_training_task_is_active(task)
            and task.get("status") in {"queued", "running"}
        )
        stopped = self.stop_training_task_process(task, note="关联流水线任务已删除，训练任务已停止。")
        with self.state.guard():
            tombstone = dict(stopped or task)
            tombstone.update(
                {
                    "job_id": canonical_job_id,
                    "task_id": tombstone.get("task_id") or canonical_job_id,
                    "status": "stopped",
                    "progress": 100,
                    "stopped_at": int(time.time()),
                    "completed_at": int(time.time()),
                    "cancelled_at": int(time.time()),
                    "deleted_at": int(time.time()),
                    "delete_tombstone": True,
                    "note": "关联流水线任务已删除，训练任务已停止。",
                }
            )
            self.state.tombstones()[clean_job_id] = tombstone
            self.state.tombstones()[canonical_job_id] = tombstone
            if preserve_stopped_record:
                self.records.save(tombstone)
            else:
                repository = self.writes.repository()
                if repository is not None:
                    row = self.writes.row(tombstone, fallback_id=canonical_job_id)
                    if row:
                        self.writes.invalidate("training_task_pairs")
                        repository.delete_by_primary_key("training_tasks", {"id": row["id"]})
                else:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        raise HTTPException(status_code=500, detail=f"Failed to delete task: {exc}") from exc
        return stopped
