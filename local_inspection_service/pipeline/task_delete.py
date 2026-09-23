"""Pipeline task deletion and ordered cleanup; resource implementations remain with their owners."""
from typing import Any
from .task_delete_ports import TaskDeleteAccess, TaskDeleteRuntime, TaskDeleteCleanup


class PipelineTaskDeleter:
    def __init__(self, access: TaskDeleteAccess, runtime: TaskDeleteRuntime, cleanup: TaskDeleteCleanup):
        self.access = access
        self.runtime = runtime
        self.cleanup = cleanup

    def delete(self, task_id: str) -> dict[str, Any]:
        user = self.access.current_user()()
        linked_job_ids: list[str] = []
        linked_dataset_ids: list[str] = []
        linked_model_run_ids: list[str] = []
        linked_ai_task_ids: list[str] = []
        # Stop any in-flight advance worker first so it self-cleans and doesn't keep
        # burning CPU or re-create a ghost record after we delete it.
        self.runtime.cancel_advance()(task_id)
        with self.runtime.lock():
            task = self.access.load_task()(task_id)
            if task:
                self.access.require_record_access()(task, user, write=True)
                linked_job_ids = [
                    str(item_id)
                    for item_id in (task.get("samples_task_id"), task.get("training_task_id"))
                    if str(item_id or "").strip()
                ]
                linked_dataset_ids = list(
                    dict.fromkeys(
                        str(item_id)
                        for item_id in (task.get("dataset_id"), task.get("samples_task_id"))
                        if str(item_id or "").strip()
                    )
                )
                linked_model_run_ids = list(
                    dict.fromkeys(
                        str(item_id)
                        for item_id in (task.get("model_run_id"), task.get("training_task_id"))
                        if str(item_id or "").strip()
                    )
                )
                linked_ai_task_ids = [
                    str(item_id)
                    for item_id in (task.get("ai_task_id"),)
                    if str(item_id or "").strip()
                ]
            if not self.runtime.delete_task_row()(task_id):
                raise self.access.http_error()(status_code=404, detail="流水线任务不存在")
        deleted_datasets = []
        for dataset_id in linked_dataset_ids:
            deleted = self.cleanup.delete_dataset()(dataset_id, user, missing_ok=True)
            if deleted:
                deleted_datasets.append(dataset_id)
        deleted_models = []
        for run_id in linked_model_run_ids:
            deleted = self.cleanup.delete_model()(run_id, user, missing_ok=True)
            if deleted:
                deleted_models.append(run_id)
        deleted_training_jobs = []
        for job_id in linked_job_ids:
            deleted = self.cleanup.delete_training_job()(job_id, user, missing_ok=True)
            if deleted:
                deleted_training_jobs.append(job_id)
        deleted_ai_tasks = []
        for ai_task_id in linked_ai_task_ids:
            deleted = self.cleanup.delete_ai_task()(ai_task_id, user, missing_ok=True)
            if deleted:
                deleted_ai_tasks.append(ai_task_id)
        return {
            "status": "deleted",
            "deleted_task_id": task_id,
            "deleted_datasets": deleted_datasets,
            "deleted_models": deleted_models,
            "deleted_ai_tasks": deleted_ai_tasks,
            "deleted_training_jobs": deleted_training_jobs,
        }
