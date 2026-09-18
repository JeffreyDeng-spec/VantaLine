"""Resolve the first pipeline record linked to a training run."""
from collections.abc import Callable
import re
from typing import Any

Record = dict[str, Any]


class TrainingLinks:
    def __init__(self, tasks: Callable[[], list[Record]], name: Callable[[Record], str]):
        self.tasks, self.name = tasks, name

    def pipeline_task_link_for_training_run(self, run_id: str, tasks: list[dict[str, Any]] | None = None) -> dict[str, str]:
        clean_run_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", re.sub(r"^trained_", "", str(run_id or "")))
        if not clean_run_id:
            return {}
        for task in (tasks if tasks is not None else self.tasks()):
            linked_ids = {
                str(task.get("model_run_id") or ""),
                str(task.get("training_task_id") or ""),
                re.sub(r"^trained_", "", str(task.get("ai_model_id") or "")),
            }
            if clean_run_id not in linked_ids:
                continue
            return {
                "pipeline_task_id": str(task.get("id") or ""),
                "pipeline_task_name": self.name(task),
            }
        return {}
