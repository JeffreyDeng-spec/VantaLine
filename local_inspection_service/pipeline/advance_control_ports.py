"""Late-resolved capabilities for manual pipeline advance and cancellation."""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable, Container


@dataclass(frozen=True)
class AdvanceControlAccess:
    current_user: Callable[[], Callable[[], Any]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    load_task: Callable[[], Callable[[str], dict[str, Any] | None]]
    require_record_access: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]


@dataclass(frozen=True)
class AdvanceControlRuntime:
    task_lock: Callable[[], AbstractContextManager[Any]]
    registry_lock: Callable[[], AbstractContextManager[Any]]
    inflight: Callable[[], Container[str]]
    sync_task: Callable[[], Callable[[dict[str, Any]], Any]]
    now: Callable[[], Callable[[], float]]
    save_task: Callable[[], Callable[[dict[str, Any]], Any]]
    public_task: Callable[[], Callable[..., dict[str, Any]]]
    schedule_advance: Callable[[], Callable[..., Any]]
    cancel_advance: Callable[[], Callable[[str], Any]]
