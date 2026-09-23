"""Manual pipeline advance/cancel HTTP routes, mounted in historical order."""
from typing import Any
from fastapi import FastAPI
from .advance_control import PipelineAdvanceController


def register_pipeline_advance_control_api(app: FastAPI, controller: PipelineAdvanceController):
    @app.post("/api/pipeline/tasks/{task_id}/advance")
    def advance_pipeline_task_endpoint(task_id: str) -> dict[str, Any]:
        return controller.advance(task_id)

    @app.post("/api/pipeline/tasks/{task_id}/cancel-advance")
    def cancel_pipeline_advance_endpoint(task_id: str) -> dict[str, Any]:
        return controller.cancel(task_id)

    return advance_pipeline_task_endpoint, cancel_pipeline_advance_endpoint
