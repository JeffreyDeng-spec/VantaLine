"""Narrow capabilities for caller-owned Agent pipeline actions and turn commits."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

Record = dict[str, Any]

class PauseAction(Protocol):
    def __call__(self, task: Record, orchestration: Record, *, stage: str, reason: str, suggested_actions: list[str]) -> None: ...

class DeleteActionJob(Protocol):
    def __call__(self, job_id: str, user: Record, *, missing_ok: bool = False) -> Record | None: ...

class PlanActionPose(Protocol):
    def __call__(self, task: Record, config: Record, *, force: bool = False) -> Record: ...

class ApplyAction(Protocol):
    def __call__(self, task: Record, config: Record, decision: Record, user: Record | None, *, trigger: str = 'chat', pending_advances: list[str] | None = None) -> None: ...

class AppendTurn(Protocol):
    def __call__(self, task: Record, role: str, message: str, *, action: str = '', reason: str = '', target_stage: str = '', source: str = '', needs_user: bool = False, agent_error: str = '') -> Record: ...

@dataclass(frozen=True)
class AgentActionState:
    http_error_type: Callable[[], type[Exception]]
    orchestration: Callable[[], Callable[[Record], Record]]
    now: Callable[[], Callable[[], int]]
    pause: Callable[[], PauseAction]
    bounded: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class AgentActionAdvance:
    mark: Callable[[], Callable[[Record], None]]
    sync: Callable[[], Callable[[Record], bool]]
    advance: Callable[[], Callable[[Record], None]]

@dataclass(frozen=True)
class AgentActionJobs:
    delete: Callable[[], DeleteActionJob]

@dataclass(frozen=True)
class AgentActionPolicy:
    normalize: Callable[[], Callable[[str | None], str]]
    uses_training: Callable[[], Callable[[str | None], bool]]

@dataclass(frozen=True)
class AgentActionPose:
    photo_flow: Callable[[], Callable[[Record, Record], bool]]
    skip_legacy: Callable[[], Callable[[Record, Record, Record], Record]]
    plan: Callable[[], PlanActionPose]
    ensure_calls: Callable[[], Callable[[Record, Record], Record]]
    config: Callable[[], Callable[[], Record]]
    execute: Callable[[], Callable[[Record, Record], bool]]

@dataclass(frozen=True)
class AgentActionCalls:
    safe_advance: Callable[[], Callable[[Record, Record, list[str] | None], None]]
    reset: Callable[[], Callable[[Record, str, Record | None], None]]

@dataclass(frozen=True)
class AgentTurnCalls:
    append: Callable[[], AppendTurn]
    apply: Callable[[], ApplyAction]
