"""Dataset input lookup, file validation and sample-count projection for training."""
from collections.abc import Callable
import json
from typing import Any
from fastapi import HTTPException
from .dataset_catalog import FindDataset
from .task_lifecycle import RequireTrainingAccess

Record = dict[str, Any]


class TrainingDatasetInput:
    def __init__(self, find: FindDataset, require: RequireTrainingAccess,
                 sanitize: Callable[[], Callable[[list[Any]], list[Any]]]):
        self.find, self.require, self.sanitize = find, require, sanitize

    def dataset_for_training(self, dataset_id: str, user: dict[str, Any] | None = None) -> dict[str, Any]:
        dataset_dir, item = self.find(dataset_id, user=user, include_samples=False)
        if dataset_dir is None or item is None:
            raise HTTPException(status_code=404, detail="Training dataset not found")
        manifest_path = dataset_dir / "manifest.json"
        dataset_yaml = dataset_dir / "dataset.yaml"
        if not dataset_dir.exists() or not manifest_path.exists() or not dataset_yaml.exists():
            raise HTTPException(status_code=404, detail="Training dataset not found")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail="Training dataset manifest is unreadable") from exc
        if user and item:
            self.require(item, user)
        samples = self.sanitize()(manifest.get("samples") if isinstance(manifest.get("samples"), list) else [])
        sample_count = len(samples) or int(manifest.get("sample_count") or 0)
        if sample_count <= 0:
            raise HTTPException(status_code=409, detail="Training dataset has no samples")
        return {
            "id": dataset_dir.name,
            "dataset_dir": str(dataset_dir),
            "dataset_yaml": str(dataset_yaml),
            "manifest_path": str(manifest_path),
            "sample_count": sample_count,
            "selected_accessory_ids": manifest.get("selected_accessory_ids") or [],
            "background_set_id": manifest.get("background_set_id") or "",
            "display_name": manifest.get("display_name") or dataset_dir.name,
        }
