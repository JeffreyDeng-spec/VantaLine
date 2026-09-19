"""Narrow capabilities for Agent conversation and pipeline decisions."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from .invocation_ports import EncodeJson

Record = dict[str, Any]

@dataclass(frozen=True)
class AgentDecisionText:
    bounded: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class AgentConversationRuntime:
    orchestration: Callable[[], Callable[[Record], Record]]
    now: Callable[[], Callable[[], int]]
    uuid: Callable[[], Callable[[], UUID]]
    limit: Callable[[], int]

@dataclass(frozen=True)
class AgentPipelineEvidence:
    orchestration: Callable[[], Callable[[Record], Record]]
    image_config: Callable[[], Callable[[], Record]]
    missing_assets: Callable[[], Callable[[Record, Record, Record], list[str]]]
    training_job: Callable[[], Callable[[Record], Record | None]]
    pose_tool: Callable[[], str]

@dataclass(frozen=True)
class AgentDecisionAccessories:
    canonical: Callable[[], Callable[[Record, list[str]], list[str]]]
    counts: Callable[[], Callable[[Record, list[str], Any], dict[str, int]]]
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    material: Callable[[], Callable[[Record], str]]
    detection: Callable[[], Callable[[str | None], str]]

@dataclass(frozen=True)
class AgentDecisionContextCalls:
    quality: Callable[[], Callable[[Record, Record], Record]]
    stage_order: Callable[[], list[str]]

@dataclass(frozen=True)
class AgentDecisionPolicyValues:
    actions: Callable[[], set[str]]
    targets: Callable[[], set[str]]

@dataclass(frozen=True)
class AgentDecisionRuleCalls:
    rerun: Callable[[], Callable[[str], tuple[str, str]]]
    normalize: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class AgentDecisionInvocationSettings:
    load: Callable[[], Callable[[], Record]]
    supported: Callable[[], Callable[[Record], bool]]
    prompt: Callable[[], str]

@dataclass(frozen=True)
class AgentDecisionCodec:
    dumps: Callable[[], EncodeJson]
    parse: Callable[[], Callable[[str], Record]]

@dataclass(frozen=True)
class AgentDecisionFlowCalls:
    context: Callable[[], Callable[[Record, Record, str | None, str], Record]]
    chat: Callable[[], Callable[[list[dict[str, str]], Record | None], str]]
    normalize: Callable[[], Callable[[Record], Record]]
    rule: Callable[[], Callable[[Record, str | None, str], Record]]
