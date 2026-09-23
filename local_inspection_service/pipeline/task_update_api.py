"""Pipeline task update HTTP boundary, mounted at its historical route position."""
from typing import Any
from fastapi import FastAPI
from ..schemas.pipeline import PipelineTaskUpdateRequest
from .task_update import PipelineTaskUpdater


def register_pipeline_task_update_api(app: FastAPI, updater: PipelineTaskUpdater):
    @app.patch("/api/pipeline/tasks/{task_id}")
    def update_pipeline_task(task_id: str, request: PipelineTaskUpdateRequest) -> dict[str, Any]:
        return updater.update(task_id, request)

    return update_pipeline_task
