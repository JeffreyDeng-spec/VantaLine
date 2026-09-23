"""Pipeline Agent chat HTTP route, mounted at its historical position."""
from typing import Any
from fastapi import FastAPI
from ..schemas.pipeline import PipelineAgentChatRequest
from .agent_chat import PipelineAgentChat


def register_pipeline_agent_chat_api(app: FastAPI, controller: PipelineAgentChat):
    @app.post("/api/pipeline/tasks/{task_id}/chat")
    def pipeline_agent_chat(task_id: str, request: PipelineAgentChatRequest) -> dict[str, Any]:
        return controller.chat(task_id, request)

    return pipeline_agent_chat