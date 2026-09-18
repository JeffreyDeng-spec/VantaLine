"""Synchronous preview HTTP adapters registered at the original position."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI
from ..schemas.training import TrainingPreviewRequest
from .preview_query import TrainingPlanQuery
from .preview_submission import TrainingPreviewSubmission

Record = dict[str, Any]


@dataclass(frozen=True)
class PreviewRoutes:
    training_plan: Callable[[str | None], Record]
    training_preview: Callable[[TrainingPreviewRequest], Record]


def register(app: FastAPI, query: TrainingPlanQuery, submission: TrainingPreviewSubmission) -> PreviewRoutes:
    @app.get("/api/training/plan")
    def training_plan(user_id: str | None = None) -> dict[str, Any]:
        return query.training_plan(user_id)

    @app.post("/api/training/preview")
    def training_preview(request: TrainingPreviewRequest) -> dict[str, Any]:
        return submission.training_preview(request)

    return PreviewRoutes(training_plan, training_preview)
