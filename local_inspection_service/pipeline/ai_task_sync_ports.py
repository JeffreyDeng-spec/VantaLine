"""Narrow, late-resolved dependencies for AI task pipeline cards."""
from dataclasses import dataclass
from typing import Any, Callable

Record = dict[str, Any]


@dataclass(frozen=True)
class PipelineAiIdentity:
    safe_record_id: Callable[[], Callable[[Any], str]]
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    ai_detection_task_model_id: Callable[[], Callable[[str], str]]


@dataclass(frozen=True)
class PipelineAiAccessories:
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    canonical_pipeline_accessory_ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    normalize_pipeline_accessory_counts: Callable[[], Callable[[Record, list[str], Any], dict[str, int]]]


@dataclass(frozen=True)
class PipelineAiAccess:
    source: Callable[[], str]
    record_visible_to_user: Callable[[], Callable[[Record, Record | None, str | None], bool]]
    load_ai_detection_tasks: Callable[[], Callable[[], list[Record]]]


@dataclass(frozen=True)
class PipelineAiProjection:
    clean_ai_detection_task_name: Callable[[], Callable[[Any, str], str]]
    training_route: Callable[[], Callable[[Record, Record], str]]
    task_id: Callable[[], Callable[[str], str]]
    now: Callable[[], Callable[[], float]]
