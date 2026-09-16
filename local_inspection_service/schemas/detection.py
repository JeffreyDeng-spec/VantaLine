"""Detection request shapes; defaults and coercion match the existing API."""
from pydantic import BaseModel


class RuleConfig(BaseModel):
    confidence_threshold: float
    required_classes: list[int]
    min_counts: dict[str, int]


class TaskRuleConfig(BaseModel):
    confidence_threshold: float
    required_accessory_counts: dict[str, int]


class AiDetectionTaskAccessory(BaseModel):
    accessory_id: str
    required_count: int = 1


class AiDetectionTaskRequest(BaseModel):
    name: str | None = None
    accessories: list[AiDetectionTaskAccessory] | None = None
    required_accessory_counts: dict[str, int] | None = None


class ModelWarmupRequest(BaseModel):
    model_id: str
