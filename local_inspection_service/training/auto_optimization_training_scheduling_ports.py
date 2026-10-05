"""Capabilities for automatic training admission and delayed checks."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol
from ..schemas.training import TrainingStartRequest
from .auto_optimization_status_ports import StopCapture, TrainingRequirements
Record = dict[str, Any]

class TrainingQueue(Protocol):
    def __call__(self, request: TrainingStartRequest, selected: list[Record], action: str, *, dataset: Record) -> Record: ...

class RequestFactory(Protocol):
    def __call__(self, *, selected_accessory_ids: list[str], sample_count: int, train_mode: str,
                 dataset_id: str, epochs: int, image_size: int, background_set_id: str | None,
                 pipeline_task_id: str, pipeline_task_name: str) -> TrainingStartRequest: ...

@dataclass(frozen=True)
class SchedulingPolicy:
    auto_optimize_completed_model_id: Callable[[], Callable[[Record], str]]
    auto_optimize_stop_capture_for_model_locked: Callable[[], StopCapture]
    default_auto_optimize_settings: Callable[[], Callable[[], Record]]
    auto_optimize_training_requirements: Callable[[], TrainingRequirements]
    auto_optimize_samples_per_real_image: Callable[[], Callable[[Record], int]]
    auto_optimize_positive_derivatives_per_real_image: Callable[[], Callable[[Record], int]]
    auto_optimize_negative_samples_per_real_image: Callable[[], Callable[[Record], int]]
    AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT: Callable[[], int]
    auto_optimize_training_parameters: Callable[[], Callable[[Record], dict[str, int]]]

@dataclass(frozen=True)
class SchedulingSubmission:
    build_auto_optimize_dataset: Callable[[], Callable[[str, Record, list[Record]], Record | None]]
    LEGACY_OWNER_ID: Callable[[], str]
    _request_user: Callable[[], ContextVar[Record | None]]
    scope_config_for_user: Callable[[], Callable[[Record, Record], Record]]
    load_config: Callable[[], Callable[[], Record]]
    selected_accessories: Callable[[], Callable[[Record, list[str]], list[Record]]]
    TrainingStartRequest: Callable[[], RequestFactory]
    pipeline_ai_task_id: Callable[[], Callable[[str], str]]
    enqueue_training_task: Callable[[], TrainingQueue]

@dataclass(frozen=True)
class SchedulingState:
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    save_auto_optimize_state: Callable[[], Callable[[Record], None]]
    maybe_start_auto_optimize_training_locked: Callable[[], Callable[[Record], None]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    auto_optimize_training_check_worker: Callable[[], Callable[[str, float], None]]
