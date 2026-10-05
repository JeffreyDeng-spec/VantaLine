"""Explicit identity, catalog and runtime projections for service status requests."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
Record = dict[str, Any]

class ScopedConfig(Protocol):
    def __call__(self, config: Record, user: Record | None = None, target_user_id: str | None = None) -> Record: ...
class TrainingTasks(Protocol):
    def __call__(self, *, user: Record | None, target_user_id: str | None) -> list[Record]: ...
class DetectionTasks(Protocol):
    def __call__(self, config: Record, *, user: Record | None, target_user_id: str | None) -> Record: ...
class TrainingExecution(Protocol):
    def __call__(self, *, include_worker_probe: bool) -> Record: ...
class BusinessFiles(Protocol):
    def exists(self, path: Path) -> bool: ...

@dataclass(frozen=True)
class StatusRequestAccess:
    current_auth_user: Callable[[], Callable[[], Record | None]]
    user_is_admin: Callable[[], Callable[[Record | None], bool]]
    scope_config_for_user: Callable[[], ScopedConfig]
    record_visible_to_user: Callable[[], Callable[[Record, Record | None, str | None], bool]]
    user_has_permission: Callable[[], Callable[[Record | None, str], bool]]
    redact_status_payload_for_user: Callable[[], Callable[[Record, Record | None], Record]]
    redact_config_summary_for_user: Callable[[], Callable[[Record, Record | None], Record]]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]

@dataclass(frozen=True)
class StatusRequestCatalog:
    load_config: Callable[[], Callable[[], Record]]
    selected_model_spec: Callable[[], Callable[[str | None, Record], Record]]
    accessory_uid: Callable[[], Callable[[Record], str]]
    list_training_tasks: Callable[[], TrainingTasks]
    list_trained_model_specs: Callable[[], Callable[[], list[Record]]]
    legacy_model_specs: Callable[[], Callable[[], list[Record]]]
    list_ai_detection_specialized_model_specs: Callable[[], Callable[[Record, list[Record], str | None], list[Record]]]
    ai_detection_tasks_response: Callable[[], DetectionTasks]
    _business_files: Callable[[], BusinessFiles]

@dataclass(frozen=True)
class StatusRequestRuntime:
    public_ai_detection_status: Callable[[], Callable[[], Record]]
    record_owner_username: Callable[[], Callable[[Record], str]]
    LEGACY_OWNER_ID: Callable[[], str]
    training_execution_status: Callable[[], TrainingExecution]
    public_cursor_image2_status: Callable[[], Callable[[], Record]]
    public_yolo_warmup_status: Callable[[], Callable[[Record], Record]]
    CLASS_LABELS: Callable[[], dict[int, str]]
    CLASS_NAMES: Callable[[], dict[int, str]]
