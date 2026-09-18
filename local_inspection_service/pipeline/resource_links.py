"""Pipeline dataset/model retirement markers, preserving batch persistence and guard scope."""
from collections.abc import Callable
from contextlib import AbstractContextManager
import re
import time
from typing import Any

Record = dict[str, Any]


class PipelineResourceLinks:
    def __init__(self, guard: Callable[[], AbstractContextManager], load: Callable[[], list[Record]],
                 save_batch: Callable[[list[Record], list[Record]], None],
                 mutable: Callable[[Record, Record], bool]):
        self.guard, self.load, self.save_batch, self.mutable = guard, load, save_batch, mutable

    def mark_pipeline_dataset_deleted(self, dataset_id: str, user: dict[str, Any]) -> int:
        clean_id = str(dataset_id or "").strip()
        if not clean_id:
            return 0
        now = int(time.time())
        changed = 0
        with self.guard():
            tasks = self.load()
            changed_tasks: list[dict[str, Any]] = []
            for task in tasks:
                linked_ids = {str(task.get("dataset_id") or ""), str(task.get("samples_task_id") or "")}
                if clean_id not in linked_ids or not self.mutable(task, user):
                    continue
                task.update({"dataset_status": "deleted", "dataset_deleted_at": now, "updated_at": now})
                changed_tasks.append(task)
                changed += 1
            self.save_batch(tasks, changed_tasks)
        return changed

    def mark_pipeline_model_deleted(self, run_id: str, user: dict[str, Any]) -> int:
        clean_id = re.sub(r"^trained_", "", str(run_id or ""))
        clean_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", clean_id)
        if not clean_id:
            return 0
        now = int(time.time())
        changed = 0
        with self.guard():
            tasks = self.load()
            changed_tasks: list[dict[str, Any]] = []
            for task in tasks:
                linked_ids = {
                    str(task.get("model_run_id") or ""),
                    str(task.get("training_task_id") or ""),
                    re.sub(r"^trained_", "", str(task.get("ai_model_id") or "")),
                }
                if clean_id not in linked_ids or not self.mutable(task, user):
                    continue
                task.update({"model_status": "deleted", "model_exists": False, "model_deleted_at": now, "updated_at": now})
                changed_tasks.append(task)
                changed += 1
            self.save_batch(tasks, changed_tasks)
        return changed
