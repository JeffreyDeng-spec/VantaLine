"""Pipeline task-list HTTP adapter at the original route position."""
from typing import Any
from fastapi import FastAPI
from .task_list import PipelineTaskList


def register_pipeline_task_list_api(app: FastAPI, controller: PipelineTaskList):
    @app.get("/api/pipeline/tasks")
    def get_pipeline_tasks(user_id: str | None = None) -> dict[str, Any]:
        return controller.list_tasks(user_id)

    return get_pipeline_tasks