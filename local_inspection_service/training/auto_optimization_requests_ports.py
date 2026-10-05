"""Authentication, state and action interfaces for auto-optimization requests."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from ..schemas.training import AutoOptimizeSettingsRequest
from .auto_optimization_label_generation_ports import ImageFiles
from .auto_optimization_shadow_evaluation_ports import Analyze
from .auto_optimization_status_ports import PublicStatus
Record = dict[str, Any]

class Access(Protocol):
    def __call__(self, record: Record, user: Record | None, *, write: bool = False) -> Any: ...

class HttpError(Protocol):
    def __call__(self, *, status_code: int, detail: str) -> Exception: ...

class SourceFiles(Protocol):
    def exists(self, path: Path) -> bool: ...

class TrainingCheck(Protocol):
    def __call__(self, task_id: str, delay_seconds: float = 0.0) -> None: ...

@dataclass(frozen=True)
class RequestAccess:
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]
    safe_record_id: Callable[[], Callable[[str], str]]
    current_auth_user: Callable[[], Callable[[], Record | None]]
    load_ai_detection_tasks: Callable[[], Callable[[], list[Record]]]
    require_record_access: Callable[[], Access]
    HTTPException: Callable[[], HttpError]

@dataclass(frozen=True)
class RequestState:
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    save_auto_optimize_state: Callable[[], Callable[[Record], None]]
    public_auto_optimize_state: Callable[[], PublicStatus]
    auto_optimize_update_settings: Callable[[], Callable[[str, AutoOptimizeSettingsRequest], Record]]

@dataclass(frozen=True)
class RequestActions:
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _business_files: Callable[[], SourceFiles]
    _image_files: Callable[[], ImageFiles]
    analyze_bgr: Callable[[], Analyze]
    AI_DETECTION_TASK_PREFIX: Callable[[], str]
    auto_optimize_bbox_training_entries: Callable[[], Callable[[Record], list[Record]]]
    start_auto_optimize_training_check_worker: Callable[[], TrainingCheck]
