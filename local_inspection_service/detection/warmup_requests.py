"""Permission-scoped model warmup requests, independent of HTTP registration."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import HTTPException
from ..schemas.detection import ModelWarmupRequest

Record = dict[str, Any]
WarmupStart = Callable[[str, list[str]], None]


@dataclass(frozen=True)
class ModelWarmupAccess:
    user: Callable[[], Record]
    config: Callable[[], Record]
    scope: Callable[[Record, Record], Record]


@dataclass(frozen=True)
class ModelWarmupModels:
    select: Callable[[str, Record], Record]
    ready: Callable[[str, Record], bool]


class ModelWarmupRequests:
    def __init__(self, access: ModelWarmupAccess, models: ModelWarmupModels, *,
                 status: Callable[[Record], Record], start: WarmupStart):
        self.access, self.models = access, models
        self.status, self.start = status, start

    def warmup_detection_model(self, request: ModelWarmupRequest) -> dict[str, Any]:
        user = self.access.user()
        config = self.access.scope(self.access.config(), user)
        model_id = str(request.model_id or "").strip()
        if not model_id:
            raise HTTPException(status_code=400, detail="model_id is required")
        spec = self.models.select(model_id, config)
        if spec.get("is_ai_detection") or spec.get("is_label_sheet_match"):
            return {**self.status(config), "selected_model_id": model_id, "selected_model_ready": True, "skipped": True}
        if not self.models.ready(model_id, config):
            self.start("selection", [model_id])
        return {
            **self.status(config),
            "selected_model_id": model_id,
            "selected_model_ready": self.models.ready(model_id, config),
            "skipped": False,
        }
