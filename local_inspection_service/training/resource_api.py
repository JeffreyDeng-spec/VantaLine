"""Resource GET adapters registered in the original application route order."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, HTTPException
from .dataset_catalog import FindDataset
from .resource_queries import ResourcePayload
from .resource_mutations import TrainingResourceMutations
from ..schemas.training import TrainingResourceUpdateRequest

Record = dict[str, Any]


@dataclass(frozen=True)
class ResourceReadAccess:
    current: Callable[[], Record]
    is_admin: Callable[[Record], bool]
    sanitize: Callable[[Record], Record]


@dataclass(frozen=True)
class ResourceReadRoutes:
    training_resources: Callable[..., Record]
    training_dataset_detail: Callable[[str], Record]


def register(app: FastAPI, access: ResourceReadAccess,
             payload: Callable[[], ResourcePayload], find: FindDataset) -> ResourceReadRoutes:
    @app.get("/api/training/resources")
    def training_resources(include_samples: bool = False, user_id: str | None = None) -> dict[str, Any]:
        user = access.current()
        return payload()(
            include_samples=include_samples,
            user=user,
            target_user_id=user_id if access.is_admin(user) else None,
        )

    @app.get("/api/training/resources/datasets/{dataset_id}/detail")
    def training_dataset_detail(dataset_id: str) -> dict[str, Any]:
        user = access.current()
        _, item = find(dataset_id, user=user, include_samples=True)
        if not item:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return access.sanitize({"status": "ready", "dataset": item})

    return ResourceReadRoutes(training_resources, training_dataset_detail)


@dataclass(frozen=True)
class ResourceWriteRoutes:
    delete_training_dataset: Callable[[str], Record]
    update_training_dataset: Callable[[str, TrainingResourceUpdateRequest], Record]
    delete_training_dataset_sample: Callable[[str, str], Record]
    delete_training_model: Callable[[str], Record]
    update_training_model: Callable[[str, TrainingResourceUpdateRequest], Record]


def register_writes(app: FastAPI, mutations: TrainingResourceMutations) -> ResourceWriteRoutes:
    @app.delete("/api/training/resources/datasets/{dataset_id}")
    def delete_training_dataset(dataset_id: str) -> dict[str, Any]:
        return mutations.delete_training_dataset(dataset_id)

    @app.patch("/api/training/resources/datasets/{dataset_id}")
    def update_training_dataset(dataset_id: str, request: TrainingResourceUpdateRequest) -> dict[str, Any]:
        return mutations.update_training_dataset(dataset_id, request)

    @app.delete("/api/training/resources/datasets/{dataset_id}/samples/{sample_name}")
    def delete_training_dataset_sample(dataset_id: str, sample_name: str) -> dict[str, Any]:
        return mutations.delete_training_dataset_sample(dataset_id, sample_name)

    @app.delete("/api/training/resources/models/{run_id}")
    def delete_training_model(run_id: str) -> dict[str, Any]:
        return mutations.delete_training_model(run_id)

    @app.patch("/api/training/resources/models/{run_id}")
    def update_training_model(run_id: str, request: TrainingResourceUpdateRequest) -> dict[str, Any]:
        return mutations.update_training_model(run_id, request)

    return ResourceWriteRoutes(delete_training_dataset, update_training_dataset, delete_training_dataset_sample, delete_training_model, update_training_model)
