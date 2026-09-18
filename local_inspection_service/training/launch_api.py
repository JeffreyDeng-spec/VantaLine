"""Training HTTP adapters registered separately to preserve interleaved route order."""
from collections.abc import Callable
from typing import Any
from fastapi import FastAPI
from ..schemas.training import TrainingStartRequest
from .launch_submission import TrainingLaunchSubmission
from .status_query import TrainingStatusQuery

Record = dict[str, Any]


def register_start(app: FastAPI, submission: TrainingLaunchSubmission) -> Callable[[TrainingStartRequest], Record]:
    @app.post("/api/training/start")
    def request_training(request: TrainingStartRequest) -> dict[str, Any]:
        return submission.request_training(request)

    return request_training


def register_generate(app: FastAPI, submission: TrainingLaunchSubmission) -> Callable[[TrainingStartRequest], Record]:
    @app.post("/api/training/generate")
    def request_sample_generation(request: TrainingStartRequest) -> dict[str, Any]:
        return submission.request_sample_generation(request)

    return request_sample_generation


def register_status(app: FastAPI, query: TrainingStatusQuery) -> Callable[[str | None], Record]:
    @app.get("/api/training/status")
    def training_status(user_id: str | None = None) -> dict[str, Any]:
        return query.training_status(user_id)

    return training_status
