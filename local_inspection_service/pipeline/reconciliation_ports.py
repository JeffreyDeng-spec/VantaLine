"""Late-resolved capabilities for pipeline status reconciliation."""
from dataclasses import dataclass
from typing import Any, Callable

Record = dict[str, Any]


@dataclass(frozen=True)
class ReconciliationPolicy:
    normalize: Callable[[], Callable[[str], str]]
    uses_training: Callable[[], Callable[[str], bool]]


@dataclass(frozen=True)
class ReconciliationRegistry:
    lock: Callable[[], Any]
    inflight: Callable[[], Any]
    timeout: Callable[[], int]
    now: Callable[[], Callable[[], float]]


@dataclass(frozen=True)
class ReconciliationCalls:
    load_agent_config: Callable[[], Callable[[], Record]]
    supported: Callable[[], Callable[[Record], bool]]
    training_finder: Callable[[], Callable[[], Any]]
    reap: Callable[[], Callable[[Record], bool]]
    sync: Callable[[], Callable[[Record, Any], bool]]
    needs_auto_agent: Callable[[], Callable[[Record], bool]]
    orchestration: Callable[[], Callable[[Record], Record]]
    signature: Callable[[], Callable[[Record], str]]