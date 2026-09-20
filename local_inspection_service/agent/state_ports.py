"""Narrow capabilities for Agent orchestration state and tool-call records."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from .pipeline_action_ports import PauseAction

Record = dict[str, Any]

class SetAgentStage(Protocol):
    def __call__(self, orchestration: Record, key: str, status: str, progress: int, **extra: Any) -> None: ...

class AgentToolIdentifier(Protocol):
    def __call__(self, task_id: str, tool_name: str, accessory_id: str = '', pose_id: str = '') -> str: ...

@dataclass(frozen=True)
class AgentStateRuntime:
    clock: Callable[[], Callable[[], float]]
    now: Callable[[], Callable[[], int]]
    version: Callable[[], str]
    image_config: Callable[[], Callable[[], Record]]

@dataclass(frozen=True)
class AgentStateCalls:
    defaults: Callable[[], Callable[[], list[Record]]]
    orchestration: Callable[[], Callable[[Record], Record]]
    pause: Callable[[], PauseAction]
    stage: Callable[[], SetAgentStage]

@dataclass(frozen=True)
class AgentToolCallIdentity:
    sanitize: Callable[[], Callable[[str], str]]
    identifier: Callable[[], AgentToolIdentifier]
    samples: Callable[[], str]
    training: Callable[[], str]

@dataclass(frozen=True)
class AgentToolCallState:
    now: Callable[[], Callable[[], int]]
    orchestration: Callable[[], Callable[[Record], Record]]
    upsert: Callable[[], Callable[[Record, Record], Record]]
    stage: Callable[[], SetAgentStage]
