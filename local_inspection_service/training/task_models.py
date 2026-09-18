"""Training task model selection from the current catalog and legacy fallback ID."""
from collections.abc import Callable
from typing import Any

Record = dict[str, Any]


def training_task_model_variant(task: dict[str, Any]) -> str:
    variant = str(task.get("model_variant") or task.get("mode") or task.get("train_mode") or "yolo").strip()
    return variant if variant in {"yolo", "yolo_ocr"} else "yolo"


class TrainingTaskModels:
    def __init__(self, specs: Callable[[], list[Record]]):
        self.specs = specs

    def training_task_model_id(self, task: dict[str, Any], job_id: str) -> str:
        spec = next((item for item in self.specs() if str(item.get("run_id") or "") == job_id), None)
        if spec and str(spec.get("id") or "").strip():
            return str(spec.get("id") or "").strip()
        return f"trained_{job_id}__{training_task_model_variant(task)}"
