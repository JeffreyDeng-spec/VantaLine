"""Pipeline task creation HTTP boundary, registered in historical route order."""
from typing import Any
from fastapi import FastAPI
from ..schemas.pipeline import PipelineTaskCreateRequest
from .task_create import PipelineTaskCreator


def register_pipeline_task_create_api(app: FastAPI, creator: PipelineTaskCreator):
    @app.post("/api/pipeline/tasks")
    def create_pipeline_task(request: PipelineTaskCreateRequest, user_id: str | None = None) -> dict[str, Any]:
        return creator.create(request, user_id)

    return create_pipeline_task
