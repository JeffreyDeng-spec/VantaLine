"""Task metadata policy and historical snapshot capabilities."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
Record = dict[str, Any]

@dataclass(frozen=True)
class MetadataPolicy:
    PIPELINE_DETECTION_METHODS: Callable[[], set[str]]
    PIPELINE_TRAINING_METHODS: Callable[[], set[str]]
    normalize_pipeline_detection_method: Callable[[], Callable[[str | None], str]]

@dataclass(frozen=True)
class MetadataSnapshots:
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    pipeline_task_label_snapshot: Callable[[], Callable[[Record], dict[str, str]]]
    LEGACY_OWNER_ID: Callable[[], str]
    record_owner_username: Callable[[], Callable[[Record], str]]
    accessory_id_aliases: Callable[[], Callable[[Record], list[str]]]
