"""Own the MCP client and its in-process detection tool graph.

Construction is inert. All internal targets exist before the owner is returned;
external profile, reference and provider capabilities are explicitly supplied.
"""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .mcp_client import LocalAiMcpClient
from .tool_dispatch import ModelToolDispatch
from .tool_dispatch_ports import ToolErrorPolicy, JsonToolExecution, McpToolTransport
from ..detection.presence_inspection import PresenceInspection
from ..detection.presence_inspection_ports import PresenceInput, PresenceGeneration, PresenceOutput, PresencePolicy

Record = dict[str, Any]


@dataclass(frozen=True)
class JsonProviderCalls:
    settings: Callable[[], Callable[[], Record]]
    metadata: Callable[[], Callable[[Record], Record]]
    generate: Callable[[], Callable[..., tuple[Record, int, Record]]]


@dataclass(frozen=True)
class McpRuntimeSelection:
    root: Callable[[], Path]
    runtime: Callable[[], Callable[[], str]]
    stdio: Callable[[], str]
    in_process: Callable[[], str]
    prepare: Callable[[], Callable[[str, Record], Record]]


@dataclass(frozen=True)
class AccessoryTools:
    profile: Callable[[Record], Record]
    reference: Callable[[Record], Record]


@dataclass(frozen=True)
class PresencePreparation:
    task: Callable[[list[Record]], Record]
    cache: Callable[[list[Record], Record], Record]
    tokens: Callable[[], Callable[[int, Record], int]]
    covers: Callable[[], Callable[[Any, set[str]], bool]]


class ModelTools:
    def __init__(self, *, errors: ToolErrorPolicy, provider: JsonProviderCalls,
                 runtime: McpRuntimeSelection, accessories: AccessoryTools,
                 presence_input: PresenceInput, presence: PresencePreparation,
                 presence_output: PresenceOutput, policy: PresencePolicy,
                 clock: Callable[[], float]):
        self.client = LocalAiMcpClient(root=runtime.root, error=errors.AiProviderError,
                                       runtime=runtime.stdio)
        self.presence = PresenceInspection(
            presence_input,
            PresenceGeneration(task=presence.task, cache=presence.cache,
                               tokens=presence.tokens,
                               call=lambda: self.dispatch.call_ai_mcp_tool,
                               covers=presence.covers),
            presence_output, policy, clock,
        )
        self.handlers = {
            "accessory.profile.generate": accessories.profile,
            "accessory.reference.collect": accessories.reference,
            "vision.inspect.presence": self.presence.tool_vision_inspect_presence,
            "provider.gemini.generate_json": self._generate_json,
        }
        self.dispatch = ModelToolDispatch(
            errors=errors,
            execution=JsonToolExecution(
                ai_detection_settings=provider.settings,
                ai_tool_provider_meta=provider.metadata,
                provider_generate_json_error_payload=lambda: self.dispatch.provider_generate_json_error_payload,
                generate_provider_json_with_fallback=provider.generate,
            ),
            transport=McpToolTransport(
                admission=lambda: self.client.admission,
                ai_mcp_runtime=runtime.runtime,
                AI_MCP_RUNTIME_STDIO=runtime.stdio,
                AI_MCP_RUNTIME_IN_PROCESS=runtime.in_process,
                _ai_mcp_client=lambda: self.client,
                prepare_ai_mcp_payload=runtime.prepare,
                AI_MCP_TOOL_HANDLERS=lambda: self.handlers,
            ),
        )

    def _generate_json(self, payload: Record) -> Record:
        return self.dispatch.tool_provider_gemini_generate_json(payload)
