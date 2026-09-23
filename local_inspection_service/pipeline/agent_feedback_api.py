"""Pipeline Agent feedback HTTP route at its historical position."""
from typing import Any
from fastapi import FastAPI
from ..schemas.pipeline import PipelineAgentFeedbackRequest
from .agent_feedback import PipelineAgentFeedback


def register_pipeline_agent_feedback_api(app: FastAPI, controller: PipelineAgentFeedback):
    @app.post("/api/pipeline/tasks/{task_id}/agent-feedback")
    def pipeline_agent_feedback(task_id: str, request: PipelineAgentFeedbackRequest) -> dict[str, Any]:
        return controller.feedback(task_id, request)

    return pipeline_agent_feedback