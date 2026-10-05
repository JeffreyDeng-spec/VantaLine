"""State, projection and accessory matching capabilities for training links."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from ..training.auto_optimization_status_ports import StopCapture
Record = dict[str, Any]

class PublicLink(Protocol):
    def __call__(self, task_id: str, *, source: str, state: Record | None = None) -> Record | None: ...

@dataclass(frozen=True)
class LinkState:
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    auto_optimize_completed_model_id: Callable[[], Callable[[Record], str]]
    auto_optimize_stop_capture_for_model_locked: Callable[[], StopCapture]
    save_auto_optimize_state: Callable[[], Callable[[Record], None]]
    fast_completed_auto_optimize_model_id: Callable[[], Callable[[Record], str]]
    list_auto_optimize_states: Callable[[], Callable[[], list[Record]]]
    auto_optimize_states_by_task_id: Callable[[], Callable[[list[Record]], dict[str, Record]]]

@dataclass(frozen=True)
class LinkProjection:
    auto_optimize_phase_name: Callable[[], Callable[[Record], str]]
    ai_detection_task_model_id: Callable[[], Callable[[str], str]]
    public_auto_optimize_link_for_task_id: Callable[[], PublicLink]

@dataclass(frozen=True)
class LinkMatching:
    canonical_pipeline_accessory_ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    normalize_pipeline_accessory_counts: Callable[[], Callable[[Record, list[str], Any], dict[str, int]]]
