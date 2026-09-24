"""Late-resolved collaborators for pipeline advance lifecycle management."""
from dataclasses import dataclass
from typing import Any, Callable, ContextManager

Record = dict[str, Any]


@dataclass(frozen=True)
class AdvanceTasks:
    lock: Callable[[], ContextManager[Any]]
    load: Callable[[], Callable[[str], Record | None]]
    sync: Callable[[], Callable[[Record], Any]]
    save: Callable[[], Callable[[Record], Any]]
    deepcopy: Callable[[], Callable[[Record], Record]]


@dataclass(frozen=True)
class AdvancePolicy:
    advance: Callable[[], Callable[..., Any]]
    guarded: Callable[[], Callable[[Record, Record, Any], None]]
    cancelled_error: Callable[[], type[Exception]]
    http_error: Callable[[], type[Exception]]
    orchestration: Callable[[], Callable[[Record], Record]]
    pause: Callable[[], Callable[..., Any]]
    bounded_text: Callable[[], Callable[[Any, int], str]]


@dataclass(frozen=True)
class AdvanceExecution:
    identity: Callable[[], Any]
    scope_config: Callable[[], Callable[[Record, Record | None], Record]]
    load_config: Callable[[], Callable[[], Record]]
    clock: Callable[[], Callable[[], float]]
    traceback: Callable[[], Callable[..., Any]]
    stderr: Callable[[], Any]
    print: Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class AdvanceScheduling:
    registry_lock: Callable[[], ContextManager[Any]]
    inflight: Callable[[], set[str]]
    cancel_events: Callable[[], dict[str, Any]]
    event: Callable[[], Callable[[], Any]]
    thread: Callable[[], Callable[..., Any]]
    runner: Callable[[], Callable[[str, Record | None], None]]
