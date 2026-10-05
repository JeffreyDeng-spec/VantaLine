"""Readiness lookup capabilities; each getter selects a callable at use time."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class AutoOptimizationReadinessPorts:
    find_training_task: Callable[[], Callable[[str], Record | None]]
    auto_optimize_linked_pipeline_model_id: Callable[[], Callable[[Record], str]]
    load_config: Callable[[], Callable[[], Record]]
    canonical_pipeline_accessory_ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    normalize_pipeline_accessory_counts: Callable[[], Callable[[Record, list[str], Any], dict[str, int]]]
    load_pipeline_tasks: Callable[[], Callable[[], list[Record]]]
    normalize_pipeline_detection_method: Callable[[], Callable[[str], str]]
    pipeline_task_model_status: Callable[[], Callable[[Record], str]]
    pipeline_task_model_id: Callable[[], Callable[[Record], str]]
    default_auto_optimize_settings: Callable[[], Callable[[], Record]]
    auto_optimize_completed_model_id: Callable[[], Callable[[Record], str]]
