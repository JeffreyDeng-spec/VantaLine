"""Pipeline AI task activation policies and persistence dependencies."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from fastapi import HTTPException
Record = dict[str, Any]

class TaskSaver(Protocol):
    def __call__(self, task: Record, *, prepend: bool = False) -> Any: ...

@dataclass(frozen=True)
class ActivationPolicy:
    canonical_pipeline_accessory_ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    HTTPException: Callable[[], type[HTTPException]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    normalize_pipeline_accessory_counts: Callable[[], Callable[[Record, list[str], Any], dict[str, int]]]
    clean_ai_detection_task_name: Callable[[], Callable[[Any, str], str]]
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    normalize_pipeline_detection_method: Callable[[], Callable[[str | None], str]]

@dataclass(frozen=True)
class ActivationStorage:
    current_owner_fields: Callable[[], Callable[[], Record]]
    find_ai_detection_task: Callable[[], Callable[[str], Record | None]]
    save_ai_detection_task: Callable[[], TaskSaver]
    serialize_ai_detection_task: Callable[[], Callable[[Record, Record], Record]]
    upsert_pipeline_ai_detection_task: Callable[[], Callable[[Record, Record], Record]]
