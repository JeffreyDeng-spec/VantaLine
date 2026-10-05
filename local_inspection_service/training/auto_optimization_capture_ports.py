"""Per-call capture capabilities without captured identity or connection state."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]


class StopCapture(Protocol):
    def __call__(self, state: Record, model_id: str, *, reason: str) -> bool: ...


@dataclass(frozen=True)
class AutoOptimizationCapturePorts:
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    save_auto_optimize_state: Callable[[], Callable[[Record], None]]
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    auto_optimize_completed_model_id: Callable[[], Callable[[Record], str]]
    auto_optimize_stop_capture_for_model_locked: Callable[[], StopCapture]
    auto_optimize_capture_enabled: Callable[[], Callable[[Record], bool]]
    resolve_service_path: Callable[[], Callable[[Path], Path]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    current_owner_fields: Callable[[], Callable[[], Record]]
    start_auto_optimize_label_worker: Callable[[], Callable[[str], None]]
    start_auto_optimize_shadow_worker: Callable[[], Callable[[str, str], None]]
    auto_optimize_detection_candidates: Callable[[], Callable[[Record], list[Record]]]
