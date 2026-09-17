"""Training resource aggregation; task listing preserves its lifecycle settlement."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from .dataset_catalog import DatasetItem

Record = dict[str, Any]


class ListResourceTasks(Protocol):
    def __call__(self, *, user: Record | None, target_user_id: str | None) -> list[Record]: ...


class ResourcePayload(Protocol):
    def __call__(self, *, include_samples: bool = False, user: Record | None = None,
                 target_user_id: str | None = None) -> Record: ...


@dataclass(frozen=True)
class ResourceDatasets:
    roots: Callable[[], list[Path]]
    item: DatasetItem
    task_id: Callable[[Record], str]


@dataclass(frozen=True)
class ResourceRecords:
    tasks: ListResourceTasks
    models: Callable[[], list[Record]]
    ai: Callable[[], list[Record]]


@dataclass(frozen=True)
class ResourceConfiguration:
    load: Callable[[], Record]
    scope: Callable[[], Callable[[Record, Record, str | None], Record]]
    serialize_ai: Callable[[Record, Record], Record]


@dataclass(frozen=True)
class ResourceAccess:
    visible: Callable[[Record, Record, str | None], bool]
    owner_username: Callable[[Record], str]
    legacy_owner: Callable[[], str]
    sanitize: Callable[[Record], Record]


class TrainingResources:
    def __init__(self, datasets: ResourceDatasets, records: ResourceRecords,
                 config: ResourceConfiguration, access: ResourceAccess,
                 resolve: Callable[[], Callable[[Any], Path]], output: Callable[[], Path]):
        self.datasets, self.records, self.config = datasets, records, config
        self.access, self.resolve, self.output = access, resolve, output

    def training_resources_payload(self,
        *,
        include_samples: bool = False,
        user: dict[str, Any] | None = None,
        target_user_id: str | None = None,
    ) -> dict[str, Any]:
        datasets = []
        for datasets_dir in self.datasets.roots():
            if not datasets_dir.exists():
                continue
            for dataset_dir in sorted([p for p in datasets_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
                item = self.datasets.item(dataset_dir, include_samples=include_samples)
                if item:
                    if user and not self.access.visible(item, user, target_user_id):
                        continue
                    datasets.append(item)
        task_items = self.records.tasks(user=user, target_user_id=target_user_id)
        dataset_ids = {item["id"] for item in datasets}
        for task in task_items:
            dataset_dir_value = task.get("dataset_dir")
            if task.get("action") not in {"generate_samples", "train_model"} or not dataset_dir_value:
                continue
            if str(task.get("dataset_status") or "") == "deleted":
                continue
            dataset_id = self.datasets.task_id(task)
            if not dataset_id:
                continue
            if dataset_id in dataset_ids:
                continue
            datasets.append(
                {
                    "id": dataset_id,
                    "kind": "dataset",
                    "display_name": task.get("label") or dataset_id,
                    "note": "样本文件缺失或已被删除；这是任务记录中的历史资源。",
                    "path": str(dataset_dir_value),
                    "manifest_path": str(task.get("manifest_path") or ""),
                    "sample_count": int(task.get("completed_samples") or task.get("sample_count") or 0),
                    "created_at": int(task.get("created_at") or 0),
                    "selected_accessory_ids": task.get("selected_accessory_ids") or [],
                    "background_set_id": task.get("background_set_id") or "",
                    "owner_user_id": str(task.get("owner_user_id") or ""),
                    "owner_username": str(task.get("owner_username") or ""),
                    "samples": [] if include_samples else None,
                    "samples_loaded": bool(include_samples),
                    "missing_files": True,
                }
            )
            dataset_ids.add(dataset_id)
        specs = self.records.models()
        models = []
        for spec in specs:
            if user and not self.access.visible(spec, user, target_user_id):
                continue
            model_path = Path(spec["path"])
            run_id = str(spec["run_id"])
            run_dir = self.resolve()(spec.get("run_dir") or (self.output() / "training_runs" / run_id))
            timestamp_path = model_path if model_path.exists() else run_dir
            models.append(
                {
                    "id": spec["id"],
                    "run_id": run_id,
                    "task_id": spec["task_id"],
                    "pipeline_task_id": spec.get("pipeline_task_id") or "",
                    "pipeline_task_name": spec.get("pipeline_task_name") or "",
                    "variant": spec["variant"],
                    "kind": "model",
                    "label": spec["label"],
                    "note": spec.get("note") or "",
                    "path": str(model_path),
                    "exists": model_path.exists(),
                    "uses_ocr": bool(spec.get("uses_ocr", False)),
                    "created_at": int(spec.get("created_at") or (timestamp_path.stat().st_mtime if timestamp_path.exists() else 0)),
                    "updated_at": int(spec.get("updated_at") or spec.get("created_at") or (timestamp_path.stat().st_mtime if timestamp_path.exists() else 0)),
                    "accessory_names": spec.get("accessory_names") or [],
                    "selected_accessory_ids": spec.get("selected_accessory_ids") or [],
                    "owner_user_id": str(spec.get("owner_user_id") or self.access.legacy_owner()),
                    "owner_username": str(spec.get("owner_username") or self.access.owner_username(spec)),
                }
            )
        completed_tasks = []
        for task in task_items:
            if task.get("action") not in {"generate_samples", "train_model"}:
                continue
            task_id = str(task.get("job_id") or "")
            completed_tasks.append(
                {
                    **task,
                    "dataset": next((item for item in datasets if item["id"] == task_id), None),
                    "models": [item for item in models if item.get("task_id") == task_id],
                }
            )
        config = self.config.scope()(self.config.load(), user, target_user_id) if user else self.config.load()
        # sync_ready_pipeline_ai_detection_tasks is a permanent no-op, so the former
        # load-and-maybe-save of pipeline tasks here was removed from this read path.
        ai_detection_tasks = [
            {**self.config.serialize_ai(task, config), "kind": "ai_detection_task", "task_type": "ai_detection"}
            for task in self.records.ai()
            if not user or self.access.visible(task, user, target_user_id)
        ]
        return self.access.sanitize({
            "datasets": datasets,
            "models": models,
            "tasks": task_items,
            "training_tasks": completed_tasks,
            "ai_detection_tasks": ai_detection_tasks,
        })
