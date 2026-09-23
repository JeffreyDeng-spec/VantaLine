"""Narrow, late-resolved capabilities for pipeline task listing."""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TaskListAccess:
    current_user: Callable[[], Callable[[], Any]]
    is_admin: Callable[[], Callable[[Any], bool]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    load_ai_tasks: Callable[[], Callable[[], list[dict[str, Any]]]]
    visible: Callable[[], Callable[..., bool]]
    incoming_allowed: Callable[[], Callable[..., bool]]
    has_permission: Callable[[], Callable[..., bool]]


@dataclass(frozen=True)
class TaskListReconciliation:
    task_lock: Callable[[], AbstractContextManager[Any]]
    load_tasks: Callable[[], Callable[[], list[dict[str, Any]]]]
    monotonic: Callable[[], Callable[[], float]]
    last_sync_at: Callable[[], float]
    set_last_sync_at: Callable[[float], None]
    min_interval: Callable[[], float]
    ensure_accessories: Callable[[], Callable[..., bool]]
    save_config: Callable[[], Callable[[dict[str, Any]], Any]]
    sync_ai_tasks: Callable[[], Callable[..., bool]]
    sync_ready_ai_tasks: Callable[[], Callable[..., bool]]
    normalize_auto_defaults: Callable[[], Callable[..., bool]]
    sync_and_advance: Callable[[], Callable[..., tuple[Any, list[str], list[str]]]]
    save_tasks: Callable[[], Callable[..., Any]]
    collect_pregen: Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class TaskListPresentation:
    schedule_agent: Callable[[], Callable[..., Any]]
    schedule_advance: Callable[[], Callable[..., Any]]
    schedule_pregen: Callable[[], Callable[..., Any]]
    trained_specs: Callable[[], Callable[..., Any]]
    optimize_states: Callable[[], Callable[[], Any]]
    optimize_by_id: Callable[[], Callable[..., Any]]
    public_task: Callable[[], Callable[..., dict[str, Any]]]
    public_agent_config: Callable[[], Callable[[], dict[str, Any]]]
    accessories_payload: Callable[[], Callable[..., dict[str, Any]]]
    sanitize: Callable[[], Callable[..., dict[str, Any]]]