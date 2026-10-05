"""Pipeline task progress persistence and linked AI-task deletion effects."""
import time
from dataclasses import dataclass
from typing import Any
from .task_mutations_ports import MutationStorage, MutationAccess

@dataclass(frozen=True)
class PipelineTaskMutations:
    storage: MutationStorage
    access: MutationAccess

    def save_pipeline_task_batch_changes(self, tasks: list[dict[str, Any]], changed_tasks: list[dict[str, Any]]) -> None:
        if not changed_tasks:
            return
        if self.storage.runtime_postgres_repository_or_none()() is not None:
            for task in changed_tasks:
                self.storage.save_pipeline_task()(task)
            return
        self.storage.save_pipeline_tasks()(tasks)


    def mark_pipeline_ai_task_deleted(self, ai_task_id: str, user: dict[str, Any]) -> int:
        clean_task_id = self.access.sanitize_ai_detection_task_id()(ai_task_id)
        if not clean_task_id:
            return 0
        now = int(time.time())
        changed = 0
        with self.storage._pipeline_tasks_lock():
            tasks = self.storage.load_pipeline_tasks()()
            changed_tasks: list[dict[str, Any]] = []
            for task in tasks:
                if str(task.get("ai_task_id") or "") != clean_task_id or not self.access.record_mutable_by_user()(task, user):
                    continue
                task.update({"model_status": "deleted", "model_exists": False, "model_deleted_at": now, "updated_at": now})
                changed_tasks.append(task)
                changed += 1
            self.storage.save_pipeline_task_batch_changes()(tasks, changed_tasks)
        return changed


    def mark_pipeline_task_advancing(self, task: dict[str, Any]) -> None:
        'Flag a task (in memory) as queued for the async advance runner. The caller\n    persists it and then schedules the worker after releasing _pipeline_tasks_lock.'
        task["advancing"] = True
        task["advance_started_at"] = int(time.time())
        task["last_error"] = ""
        task["job_note"] = "正在推进…"
        task["updated_at"] = int(time.time())


    def persist_pipeline_task_progress(self,
        task_id: str,
        *,
        job_note: str | None = None,
        progress: int | None = None,
        status: str | None = None,
    ) -> None:
        'Write live sub-step progress to the stored task record so the UI reflects\n    an in-flight advance immediately. Safe to call from the advance worker thread\n    (it briefly takes _pipeline_tasks_lock); never call while already holding it.'
        if not task_id:
            return
        with self.storage._pipeline_tasks_lock():
            stored = self.storage.load_pipeline_task()(task_id)
            if not stored:
                return
            if job_note is not None:
                stored["job_note"] = job_note
            if progress is not None:
                stored["progress"] = int(progress)
            if status is not None:
                stored["status"] = status
            stored["updated_at"] = int(time.time())
            self.storage.save_pipeline_task()(stored)
