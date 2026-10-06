"""State/identity and projection capabilities used only by auto-optimization status."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

Record = dict[str, Any]


class StopCapture(Protocol):
    def __call__(self, state: Record, model_id: str, *, reason: str) -> bool: ...


class PublicStatus(Protocol):
    def __call__(self, task_id: str, *, user: Record | None = None) -> Record: ...


class TrainingRequirements(Protocol):
    def __call__(self, settings: Record, *, real_positive_source_count: int = 0) -> dict[str, int]: ...


@dataclass(frozen=True)
class AutoOptimizationStatusState:
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    save_auto_optimize_state: Callable[[], Callable[[Record], None]]
    hydrate_auto_optimize_background_from_ai_task: Callable[[], Callable[[Record], bool]]
    auto_optimize_completed_model_id: Callable[[], Callable[[Record], str]]
    auto_optimize_stop_capture_for_model_locked: Callable[[], StopCapture]
    find_training_task: Callable[[], Callable[[str], Record | None]]
    record_visible_to_user: Callable[[], Callable[[Record, Record], bool]]
    current_auth_user: Callable[[], Callable[[], Record | None]]
    start_auto_optimize_label_worker: Callable[[], Callable[[str], None]]
    public_auto_optimize_state: Callable[[], PublicStatus]


@dataclass(frozen=True)
class AutoOptimizationStatusPolicy:
    default_auto_optimize_settings: Callable[[], Record]
    auto_optimize_public_sprite_pool: Callable[[], Callable[[Record], list[Record]]]
    background_set_payload: Callable[[], Callable[[str], Record]]
    auto_optimize_samples_per_real_image: Callable[[Record], int]
    auto_optimize_training_parameters: Callable[[Record], Record]
    auto_optimize_training_requirements: TrainingRequirements
    auto_optimize_negative_samples_per_real_image: Callable[[Record], int]
    auto_optimize_positive_derivatives_per_real_image: Callable[[Record], int]
    AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT: Callable[[], int]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]
    auto_optimize_phase_name: Callable[[], Callable[[Record], str]]
    normalize_expected_production_count: Callable[[], Callable[[Any], int]]
    public_auto_optimize_initialization_payload: Callable[[], Callable[[Record, Record], Record]]
