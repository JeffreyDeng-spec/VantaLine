"""Training launch flows with the original validation, queue and user-state write order."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from ..schemas.training import TrainingStartRequest

Record = dict[str, Any]


class TrainingDataset(Protocol):
    def __call__(self, dataset_id: str, user: Record | None = None) -> Record: ...


class ApprovedPreview(Protocol):
    def __call__(self, config: Record, request: TrainingStartRequest,
                 selected: list[Record], user: Record | None = None) -> None: ...


class EnqueueTraining(Protocol):
    def __call__(self, request: TrainingStartRequest, selected: list[Record], action: str,
                 dataset: Record | None = None) -> Record: ...


@dataclass(frozen=True)
class LaunchConfiguration:
    load: Callable[[], Record]
    scope: Callable[[Record, Record], Record]
    ensure: Callable[[], Callable[[Record, Record, Record, list[str]], bool]]
    set_state: Callable[[Record, Record, Record], None]
    merge: Callable[[Record, Record, Record], None]
    save: Callable[[Record], Any]


@dataclass(frozen=True)
class LaunchInputs:
    selected: Callable[[], Callable[[Record, list[str]], list[Record]]]
    dataset: Callable[[], TrainingDataset]
    approve: ApprovedPreview


class TrainingLaunchSubmission:
    def __init__(self, current: Callable[[], Record], config: LaunchConfiguration, inputs: LaunchInputs,
                 enqueue: EnqueueTraining, clock: Callable[[], float], physical_size: Callable[[], Record]):
        self.current, self.config, self.inputs = current, config, inputs
        self.enqueue, self.clock, self.physical_size = enqueue, clock, physical_size

    def request_training(self, request: TrainingStartRequest) -> dict[str, Any]:
        user = self.current()
        full_config = self.config.load()
        config = self.config.scope(full_config, user)
        dataset = None
        if request.dataset_id:
            dataset = self.inputs.dataset()(request.dataset_id, user=user)
            selected = self.inputs.selected()(config, dataset.get("selected_accessory_ids") or request.selected_accessory_ids)
        else:
            selected = self.inputs.selected()(config, request.selected_accessory_ids)
            self.inputs.approve(config, request, selected, user=user)
            if self.config.ensure()(full_config, config, user, [item["id"] for item in selected]):
                config = self.config.scope(full_config, user)
                selected = self.inputs.selected()(config, request.selected_accessory_ids)
        task = self.enqueue(request, selected, "train_model", dataset=dataset)
        training_state = {
            "status": "queued",
            "last_requested_at": int(self.clock()),
            "selected_accessory_ids": [item["id"] for item in selected],
            "sample_count": task["sample_count"],
            "mode": request.train_mode,
            "epochs": task["epochs"],
            "image_size": task["image_size"],
            "background_set_id": task.get("background_set_id"),
            "approved_preview_id": request.approved_preview_id,
            "active_training_task_id": task["job_id"],
            "note": task["note"],
            "estimated_minutes": task["estimated_minutes"],
        }
        self.config.set_state(full_config, user, training_state)
        self.config.merge(full_config, config, user)
        self.config.save(full_config)
        return task

    def request_sample_generation(self, request: TrainingStartRequest) -> dict[str, Any]:
        user = self.current()
        full_config = self.config.load()
        config = self.config.scope(full_config, user)
        selected = self.inputs.selected()(config, request.selected_accessory_ids)
        self.inputs.approve(config, request, selected, user=user)
        if self.config.ensure()(full_config, config, user, [item["id"] for item in selected]):
            config = self.config.scope(full_config, user)
            selected = self.inputs.selected()(config, request.selected_accessory_ids)
        task = self.enqueue(request, selected, "generate_samples")
        training_state = {
            "status": "queued",
            "last_requested_at": int(self.clock()),
            "selected_accessory_ids": [item["id"] for item in selected],
            "sample_count": task["sample_count"],
            "mode": request.train_mode,
            "background_set_id": task.get("background_set_id"),
            "approved_preview_id": request.approved_preview_id,
            "preview_urls": [],
            "previews": [],
            "preview_cache_key": None,
            "preview_sprite_versions": {},
            "render_policy": {
                "background_physical_size": self.physical_size(),
                "physical_size_rule": "Object samples use clean alpha sprites scaled by physical_size; document samples paste the saved rectified full document directly at paper physical_size.",
                "pose_collection_rule": "Pose Collection provides pose only; physical_size is applied only during preview and dataset rendering.",
            },
            "active_training_task_id": task["job_id"],
            "note": task["note"],
            "estimated_minutes": task["estimated_minutes"],
            "estimated_gb": task["estimated_gb"],
        }
        self.config.set_state(full_config, user, training_state)
        self.config.merge(full_config, config, user)
        self.config.save(full_config)
        return task
