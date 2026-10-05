"""Explicit resource naming policy and catalog readers."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
Record = dict[str, Any]
@dataclass(frozen=True)
class NamePolicy:
    resource_name_key: Callable[[], Callable[[Any], str]]
    LEGACY_OWNER_ID: Callable[[], str]
    accessory_uid: Callable[[], Callable[[Record], str]]
    record_owner_id: Callable[[], Callable[[Record], str]]
    duplicate_name_error: Callable[[], Callable[[str], None]]
    task_matches_excluded_identity: Callable[[], Callable[..., bool]]
    task_record_name: Callable[[], Callable[[Record], str]]
@dataclass(frozen=True)
class NameCatalogs:
    load_pipeline_tasks: Callable[[], Callable[[], list[Record]]]
    load_ai_detection_tasks: Callable[[], Callable[[], list[Record]]]
    training_resources_payload: Callable[[], Callable[..., Record]]
    list_trained_model_specs: Callable[[], Callable[[], list[Record]]]
