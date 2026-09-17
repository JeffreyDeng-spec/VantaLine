"""Resource file mutations and existing partial-completion semantics."""
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import time
from typing import Any, Protocol
from fastapi import HTTPException
from ..schemas.training import TrainingResourceUpdateRequest
from .dataset_catalog import FindDataset
from .resource_queries import ResourcePayload
from .task_lifecycle import RequireTrainingAccess

Record = dict[str, Any]


class UniqueDatasetName(Protocol):
    def __call__(self, name: str, owner: str, user: Record, *, exclude_dataset_id: str = '') -> None: ...


class UniqueModelName(Protocol):
    def __call__(self, name: str, owner: str, *, exclude_run_id: str = '') -> None: ...


class DeleteResource(Protocol):
    def __call__(self, identifier: str, user: Record, *, missing_ok: bool = False) -> Record | None: ...


@dataclass(frozen=True)
class ResourceWriteAccess:
    current: Callable[[], Record]
    require: RequireTrainingAccess
    owner: Callable[[Record], str]
    unique_dataset: Callable[[], UniqueDatasetName]
    unique_model: Callable[[], UniqueModelName]


@dataclass(frozen=True)
class ResourceWriteCatalog:
    find: FindDataset
    models: Callable[[], list[Record]]
    resolve: Callable[[], Callable[[Any], Path]]
    payload: ResourcePayload


@dataclass(frozen=True)
class ResourceRetirement:
    delete_dataset: DeleteResource
    delete_model: DeleteResource
    training_dataset: Callable[[str, Record], int]
    pipeline_dataset: Callable[[str, Record], int]
    pipeline_model: Callable[[str, Record], int]


class TrainingResourceMutations:
    def __init__(self, access: ResourceWriteAccess, catalog: ResourceWriteCatalog,
                 retirement: ResourceRetirement):
        self.access, self.catalog, self.retirement = access, catalog, retirement

    def delete_training_dataset_resource(self, dataset_id: str, user: dict[str, Any], *, missing_ok: bool = False) -> dict[str, Any] | None:
        dataset_dir, item = self.catalog.find(dataset_id, user=user, include_samples=False, write=True)
        if not dataset_dir or not item:
            if missing_ok:
                return None
            raise HTTPException(status_code=404, detail="Dataset not found")
        shutil.rmtree(dataset_dir)
        return item

    def delete_training_model_resource(self, run_id: str, user: dict[str, Any], *, missing_ok: bool = False) -> dict[str, Any] | None:
        clean_id = re.sub(r"^trained_", "", run_id)
        spec = next((item for item in self.catalog.models() if str(item.get("run_id")) == re.sub(r"[^a-zA-Z0-9_.-]+", "_", clean_id)), None)
        run_dir = self.catalog.resolve()(spec.get("run_dir")) if spec else None
        if not run_dir or not run_dir.exists() or not run_dir.is_dir() or not spec:
            if missing_ok:
                return None
            raise HTTPException(status_code=404, detail="Model run not found")
        self.access.require(spec, user, write=True)
        shutil.rmtree(run_dir)
        return spec

    def delete_training_dataset(self, dataset_id: str) -> dict[str, Any]:
        user = self.access.current()
        deleted_item = self.retirement.delete_dataset(dataset_id, user, missing_ok=True)
        affected_training_tasks = self.retirement.training_dataset(dataset_id, user)
        affected_pipeline_tasks = self.retirement.pipeline_dataset(dataset_id, user)
        if not deleted_item and not affected_training_tasks and not affected_pipeline_tasks:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return {
            "status": "deleted",
            "dataset_id": dataset_id,
            "affected_training_tasks": affected_training_tasks,
            "affected_pipeline_tasks": affected_pipeline_tasks,
            **self.catalog.payload(user=user),
        }

    def update_training_dataset(self, dataset_id: str, request: TrainingResourceUpdateRequest) -> dict[str, Any]:
        user = self.access.current()
        dataset_dir, item = self.catalog.find(dataset_id, user=user, include_samples=False, write=True)
        if not dataset_dir or not item:
            raise HTTPException(status_code=404, detail="Dataset not found")
        manifest_path = dataset_dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail="Dataset manifest is unreadable") from exc
        if request.display_name is not None:
            next_display_name = request.display_name.strip() or dataset_id
            self.access.unique_dataset()(next_display_name, self.access.owner(item), user, exclude_dataset_id=dataset_id)
            manifest["display_name"] = next_display_name
        if request.note is not None:
            manifest["note"] = request.note.strip()
        manifest["updated_at"] = int(time.time())
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"status": "updated", "dataset_id": dataset_id, **self.catalog.payload(user=user)}

    def delete_training_dataset_sample(self, dataset_id: str, sample_name: str) -> dict[str, Any]:
        user = self.access.current()
        dataset_dir, item = self.catalog.find(dataset_id, user=user, include_samples=False, write=True)
        if not dataset_dir or not item:
            raise HTTPException(status_code=404, detail="Dataset not found")
        sample_stem = Path(sample_name).stem
        removed = 0
        for split in ("train", "val", "test"):
            for path in (
                dataset_dir / "images" / split / f"{sample_stem}.png",
                dataset_dir / "labels" / split / f"{sample_stem}.txt",
                dataset_dir / "previews" / split / f"{sample_stem}_boxed.jpg",
            ):
                if path.exists():
                    path.unlink()
                    removed += 1
        manifest_path = dataset_dir / "manifest.json"
        removed_manifest_records = 0
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                raw_samples = manifest.get("samples") if isinstance(manifest.get("samples"), list) else []
                samples = [
                    item
                    for item in raw_samples
                    if not isinstance(item, dict) or Path(str(item.get("image") or "")).stem != sample_stem
                ]
                removed_manifest_records = len(raw_samples) - len(samples)
                manifest["samples"] = samples
                manifest["sample_count"] = len(samples)
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            except (OSError, json.JSONDecodeError):
                pass
        if removed == 0 and removed_manifest_records == 0:
            raise HTTPException(status_code=404, detail="Sample not found")
        return {
            "status": "deleted",
            "dataset_id": dataset_id,
            "sample": sample_name,
            "removed_files": removed,
            "removed_manifest_records": removed_manifest_records,
            **self.catalog.payload(user=user),
        }

    def delete_training_model(self, run_id: str) -> dict[str, Any]:
        user = self.access.current()
        self.retirement.delete_model(run_id, user)
        affected_tasks = self.retirement.pipeline_model(run_id, user)
        return {"status": "deleted", "run_id": run_id, **self.catalog.payload(user=user)}

    def update_training_model(self, run_id: str, request: TrainingResourceUpdateRequest) -> dict[str, Any]:
        user = self.access.current()
        clean_id = re.sub(r"^trained_", "", run_id)
        spec = next((item for item in self.catalog.models() if str(item.get("run_id")) == re.sub(r"[^a-zA-Z0-9_.-]+", "_", clean_id)), None)
        run_dir = self.catalog.resolve()(spec.get("run_dir")) if spec else None
        if not run_dir or not run_dir.exists() or not run_dir.is_dir() or not spec:
            raise HTTPException(status_code=404, detail="Model run not found")
        self.access.require(spec, user, write=True)
        meta_path = run_dir / "library_metadata.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        except json.JSONDecodeError:
            meta = {}
        if request.display_name is not None:
            next_display_name = request.display_name.strip() or clean_id
            self.access.unique_model()(next_display_name, self.access.owner(spec), exclude_run_id=str(spec.get("run_id") or ""))
            meta["display_name"] = next_display_name
        if request.note is not None:
            meta["note"] = request.note.strip()
        meta["updated_at"] = int(time.time())
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return {"status": "updated", "run_id": run_id, **self.catalog.payload(user=user)}
