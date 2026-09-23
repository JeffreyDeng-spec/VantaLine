"""Late-resolved capabilities for the pipeline task creation use case."""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TaskCreateAccess:
    current_user: Callable[[], Callable[[], Any]]
    require_permission: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]
    is_admin: Callable[[], Callable[[Any], bool]]
    owner_fields: Callable[[], Callable[..., dict[str, Any]]]
    fallback_owner: Callable[[], Callable[[Any], str]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    accessory_lookup: Callable[[], Callable[[dict[str, Any]], dict[str, Any]]]
    load_agent_config: Callable[[], Callable[[], dict[str, Any]]]


@dataclass(frozen=True)
class TaskCreatePolicy:
    canonical_accessory_ids: Callable[[], Callable[..., list[str]]]
    normalize_detection_method: Callable[[], Callable[[Any], str]]
    normalize_expected_count: Callable[[], Callable[[Any], int]]
    method_uses_training: Callable[[], Callable[[str], bool]]
    normalize_accessory_counts: Callable[[], Callable[..., dict[str, int]]]
    assert_unique_name: Callable[[], Callable[[str, str], Any]]
    next_recommendation_stage: Callable[[], Callable[[dict[str, Any]], str | None]]


@dataclass(frozen=True)
class TaskCreateRuntime:
    uuid4: Callable[[], Callable[[], Any]]
    now: Callable[[], Callable[[], float]]
    lock: Callable[[], AbstractContextManager[Any]]
    activate_ai_task: Callable[[], Callable[..., Any]]
    save_task: Callable[[], Callable[[dict[str, Any]], Any]]
    initialize_auto_optimize: Callable[[], Callable[..., Any]]
    load_task: Callable[[], Callable[[str], dict[str, Any] | None]]
    schedule_pregen: Callable[[], Callable[..., Any]]
    request_user: Callable[[], Any]
    public_task: Callable[[], Callable[..., dict[str, Any]]]
