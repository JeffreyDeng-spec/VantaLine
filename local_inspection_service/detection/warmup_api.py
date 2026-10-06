"""Install model warmup HTTP against an explicitly supplied service/runtime."""
from collections.abc import Callable
from fastapi import FastAPI
from .warmup_requests import ModelWarmupAccess, ModelWarmupModels, ModelWarmupRequests, Record, WarmupStart
from ..runtime.yolo_warmup import YoloWarmup

WARMUP_PATH = "/api/models/warmup"


def bind_warmup_start(runtime: YoloWarmup) -> WarmupStart:
    def start(reason: str, model_ids: list[str]) -> None:
        # Resolve the owned worker when the existing runtime requests it, after
        # its enable check, without looking back into application globals.
        return runtime.start_yolo_warmup(reason, model_ids, worker=lambda: runtime.yolo_warmup_worker)
    return start


def compose_model_warmup_api(app: FastAPI, *, access: ModelWarmupAccess, models: ModelWarmupModels,
                             status: Callable[[Record], Record], start: WarmupStart) -> ModelWarmupRequests:
    for route in app.routes:
        if getattr(route, "path", None) == WARMUP_PATH and "POST" in (getattr(route, "methods", None) or ()):
            raise ValueError("Model warmup route is already registered")
    service = ModelWarmupRequests(access, models, status=status, start=start)
    app.post(WARMUP_PATH)(service.warmup_detection_model)
    return service
