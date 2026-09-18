"""Worker archive metadata preserves eager evaluation and original payload compatibility."""
from collections.abc import Callable
from pathlib import Path
from typing import Any


class WorkerBundleMetadata:
    def __init__(self, digest: Callable[[Path], str], manifest: Callable[[Path], list[dict[str, Any]]]):
        self.digest, self.manifest = digest, manifest

    def worker_training_bundle_metadata(self, job_id: str, task: dict[str, Any], dataset: dict[str, Any], dataset_dir: Path, archive_path: Path) -> dict[str, Any]:
        return {
            "bundle_version": 1,
            "job_id": job_id,
            "task_id": str(task.get("task_id") or job_id),
            "task_type": "training",
            "action": "train_model",
            "owner_user_id": str(task.get("owner_user_id") or ""),
            "owner_username": str(task.get("owner_username") or ""),
            "source_dataset_id": str(task.get("source_dataset_id") or Path(str(dataset.get("dataset_dir") or dataset_dir)).name),
            "selected_accessory_ids": [str(item) for item in task.get("selected_accessory_ids") or []],
            "sample_count": max(1, min(20000, int(task.get("sample_count") or 1))),
            "train_mode": str(task.get("train_mode") or task.get("mode") or task.get("model_variant") or "yolo_ocr"),
            "epochs": max(1, min(500, int(task.get("epochs") or 1))),
            "image_size": max(320, min(1280, int(task.get("image_size") or 640))),
            "dataset_archive": {
                "filename": archive_path.name,
                "size": archive_path.stat().st_size,
                "sha256": self.digest(archive_path),
            },
            "dataset_files": self.manifest(dataset_dir),
            "callback": {
                "import_target": "training_runs",
                "expected_artifacts": ["model", "logs", "result_manifest"],
            },
        }
