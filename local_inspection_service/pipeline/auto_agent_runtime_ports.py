"""Late-resolved collaborators for pipeline auto-Agent background steps."""
from dataclasses import dataclass
from typing import Any, Callable, ContextManager

Record = dict[str, Any]


@dataclass(frozen=True)
class AutoAgentTasks:
    lock: Callable[[], ContextManager[Any]]
    load: Callable[[], Callable[[str], Record | None]]
    needs_agent: Callable[[], Callable[[Record], bool]]
    orchestration: Callable[[], Callable[[Record], Record]]
    signature: Callable[[], Callable[[Record], str]]
    max_steps: Callable[[], int]
    pause: Callable[[], Callable[..., Any]]
    append_conversation: Callable[[], Callable[..., Any]]
    save: Callable[[], Callable[[Record], Any]]
    deepcopy: Callable[[], Callable[[Record], Record]]


@dataclass(frozen=True)
class AutoAgentDecision:
    scope_config: Callable[[], Callable[[Record, Record | None], Record]]
    load_config: Callable[[], Callable[[], Record]]
    decide: Callable[[], Callable[..., Record]]
    commit: Callable[[], Callable[..., Any]]
    now: Callable[[], Callable[[], Any]]
    schedule_advance: Callable[[], Callable[[str, Record | None], Any]]


@dataclass(frozen=True)
class AutoAgentExecution:
    identity: Callable[[], Any]
    traceback: Callable[[], Callable[..., Any]]
    stderr: Callable[[], Any]


@dataclass(frozen=True)
class AutoAgentScheduling:
    lock: Callable[[], ContextManager[Any]]
    inflight: Callable[[], set[str]]
    thread: Callable[[], Callable[..., Any]]
    runner: Callable[[], Callable[[str, Record | None], None]]
