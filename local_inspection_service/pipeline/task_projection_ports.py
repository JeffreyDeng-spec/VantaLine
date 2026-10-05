"""Task metadata and resource projection capabilities; no request state retained."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
Record = dict[str, Any]

class ModelStatus(Protocol):
    def __call__(self, task: Record, *, ai_task_ids: set[str] | None = None, trained_model_specs: list[Record] | None = None) -> str: ...

class TrainingLink(Protocol):
    def __call__(self, task: Record, config: Record, *, auto_optimize_states: list[Record] | None = None, auto_optimize_states_by_id: dict[str, Record] | None = None) -> Record | None: ...

@dataclass(frozen=True)
class ProjectionMetadata:
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    enrich_record_audit_fields: Callable[[], Callable[[Record], Record]]
    normalize_pipeline_detection_method: Callable[[], Callable[[str], str]]
    pipeline_method_uses_training: Callable[[], Callable[[str], bool]]
    resolve_accessory_id: Callable[[], Callable[[Record, str], tuple[str, Record] | None]]
    normalize_pipeline_accessory_counts: Callable[[], Callable[[Record, list[str], Any], dict[str, int]]]
    pipeline_task_accessory_snapshot: Callable[[], Callable[[Record, Record, list[str]], tuple[dict[str, str], list[str]]]]
    accessory_material_type: Callable[[], Callable[[Record], str]]

@dataclass(frozen=True)
class ProjectionResources:
    pipeline_task_dataset_status: Callable[[], Callable[[Record], str]]
    pipeline_task_model_status: Callable[[], ModelStatus]
    pipeline_task_auto_optimize_link: Callable[[], TrainingLink]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]
