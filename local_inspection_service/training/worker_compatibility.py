"""Worker request/status compatibility and explicit per-value artifact projection."""
from collections.abc import Callable
from typing import Any


def worker_training_payload(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "selected_accessory_ids": [str(item) for item in task.get("selected_accessory_ids") or []],
        "sample_count": max(1, min(20000, int(task.get("sample_count") or 1))),
        "train_mode": str(task.get("train_mode") or task.get("mode") or task.get("model_variant") or "yolo_ocr"),
        "approved_preview_id": task.get("approved_preview_id") or None,
        "dataset_id": task.get("source_dataset_id") or task.get("dataset_id") or None,
        "epochs": max(1, min(500, int(task.get("epochs") or 1))),
        "image_size": max(320, min(1280, int(task.get("image_size") or 640))),
        "background_set_id": task.get("background_set_id") or None,
    }


def worker_training_terminal_status(status: str) -> bool:
    return status.lower() in {"completed", "failed", "cancelled", "canceled", "stopped"}



class WorkerArtifactSummary:
    def __init__(self, sanitize: Callable[[Any], Any]):
        self.sanitize = sanitize

    def worker_training_artifact_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "id",
            "run_id",
            "task_id",
            "label",
            "display_name",
            "status",
            "sample_count",
            "selected_accessory_ids",
            "artifact_path",
            "dataset_yaml",
        }
        return {key: self.sanitize(value) for key, value in item.items() if key in allowed}
