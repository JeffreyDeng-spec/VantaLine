"""Late-resolved dependencies of the pipeline recommendation background runtime."""
from dataclasses import dataclass
from typing import Any, Callable, ContextManager

Record = dict[str, Any]


@dataclass(frozen=True)
class RecommendationTasks:
    lock: Callable[[], ContextManager[Any]]
    load: Callable[[], Callable[[str], Record | None]]
    next_stage: Callable[[], Callable[[Record], str]]
    ready: Callable[[], Callable[[Record, str], bool]]
    signature: Callable[[], Callable[[Record, str], str]]
    save: Callable[[], Callable[[Record], Any]]


@dataclass(frozen=True)
class RecommendationExecution:
    identity: Callable[[], Any]
    recommend: Callable[[], Callable[[str, list[str], int | None], Record]]
    clock: Callable[[], Callable[[], float]]
    traceback: Callable[[], Callable[..., Any]]
    stderr: Callable[[], Any]


@dataclass(frozen=True)
class RecommendationScheduling:
    lock: Callable[[], ContextManager[Any]]
    inflight: Callable[[], set[str]]
    thread: Callable[[], Callable[..., Any]]
    runner: Callable[[], Callable[[str, str, Record | None], None]]
