"""Pipeline request shapes; defaults and coercion match the existing API."""
from typing import Any
from pydantic import BaseModel


class AgentRecommendRequest(BaseModel):
    stage: str
    accessory_ids: list[str] = []
    sample_count: int | None = None


class PipelineTaskCreateRequest(BaseModel):
    name: str | None = None
    accessory_ids: list[str] = []
    accessory_counts: dict[str, int] | None = None
    detection_method: str | None = None
    auto_advance: bool | None = None
    expected_production_count: int | None = None
    task_kind: str | None = None
    material_code: str | None = None
    material_name: str | None = None
    inspection_user_ids: list[str] = []


class PipelineTaskUpdateRequest(BaseModel):
    name: str | None = None
    accessory_ids: list[str] | None = None
    accessory_counts: dict[str, int] | None = None
    detection_method: str | None = None
    params: dict[str, Any] | None = None
    auto_advance: bool | None = None
    expected_production_count: int | None = None
    material_code: str | None = None
    material_name: str | None = None
    inspection_user_ids: list[str] | None = None


class PipelineAgentFeedbackRequest(BaseModel):
    action: str
    decision: str | None = None
    message: str | None = None
    updated_plan: dict[str, Any] | None = None


class PipelineAgentChatRequest(BaseModel):
    message: str
