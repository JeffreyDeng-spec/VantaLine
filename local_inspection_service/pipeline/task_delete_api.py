"""Pipeline task deletion HTTP boundary, registered in historical route order."""
from typing import Any
from fastapi import FastAPI
from .task_delete import PipelineTaskDeleter


def register_pipeline_task_delete_api(app: FastAPI, deleter: PipelineTaskDeleter):
    @app.delete("/api/pipeline/tasks/{task_id}")
    def delete_pipeline_task(task_id: str) -> dict[str, Any]:
        return deleter.delete(task_id)

    return delete_pipeline_task
