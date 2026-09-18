"""Resource GET adapters registered in the original application route order."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, HTTPException
from .dataset_catalog import FindDataset
from .resource_queries import ResourcePayload

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
