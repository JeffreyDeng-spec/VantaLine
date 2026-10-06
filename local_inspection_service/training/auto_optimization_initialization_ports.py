"""Narrow, late-resolved capabilities for the initialization use case."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

Record = dict[str, Any]


class GenerateInitializationJson(Protocol):
    def __call__(self, settings: Record, system: str, content: list[Record], *,
                 max_tokens: int, max_attempts: int) -> tuple[Record, float, Record]: ...


@dataclass(frozen=True)
class AutoOptimizationAdvisorPorts:
    ai_detection_settings: Callable[[], Callable[[str], Record]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    generate_provider_json_with_fallback: Callable[[], GenerateInitializationJson]
    clamp_auto_optimize_initialization_recommendation: Callable[[], Callable[[Record, Record, int], Record]]


@dataclass(frozen=True)
class AutoOptimizationTaskInitializationPorts:
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    canonical_pipeline_accessory_ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    auto_optimize_complexity_rule_recommendation: Callable[[], Callable[[Record, list[str], int], Record]]
    agent_auto_optimize_initialization_recommendation: Callable[[], Callable[[Record, list[str], int, Record], Record]]
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    default_auto_optimize_settings: Callable[[], Record]
    save_auto_optimize_state: Callable[[], Callable[[Record], Record]]
    start_auto_optimize_label_worker: Callable[[], Callable[[str], None]]
