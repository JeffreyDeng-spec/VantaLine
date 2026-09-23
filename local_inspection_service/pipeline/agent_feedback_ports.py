"""Late-resolved capabilities for pipeline Agent feedback."""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class AgentFeedbackAccess:
    current_user: Callable[[], Callable[[], Any]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    load_task: Callable[[], Callable[[str], dict[str, Any] | None]]
    require_record_access: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]


@dataclass(frozen=True)
class AgentFeedbackPolicy:
    normalize_method: Callable[[], Callable[[str], str]]
    uses_training: Callable[[], Callable[[str], bool]]
    sprite_flow: Callable[[], Callable[..., bool]]


@dataclass(frozen=True)
class AgentFeedbackRuntime:
    task_lock: Callable[[], AbstractContextManager[Any]]
    ensure_plan: Callable[[], Callable[..., dict[str, Any]]]
    now: Callable[[], Callable[[], int]]
    skip_legacy: Callable[[], Callable[..., dict[str, Any]]]
    mark_advancing: Callable[[], Callable[..., Any]]
    pose_calls: Callable[[], Callable[..., dict[str, Any]]]
    image_config: Callable[[], Callable[[], dict[str, Any]]]
    execute_calls: Callable[[], Callable[..., bool]]
    pause_task: Callable[[], Callable[..., Any]]
    save_task: Callable[[], Callable[..., Any]]
    public_task: Callable[[], Callable[..., dict[str, Any]]]
    schedule_advance: Callable[[], Callable[..., Any]]