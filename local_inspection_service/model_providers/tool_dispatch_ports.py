"""Explicit JSON tool invocation, error projection and MCP transport dependencies."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from contextlib import AbstractContextManager
from typing import Any, Protocol
Record = dict[str, Any]
class McpClient(Protocol):
    def call_tool(self, name: str, payload: Record) -> Record: ...
    def close(self) -> None: ...
@dataclass(frozen=True)
class ToolErrorPolicy:
    bounded_text: Callable[[], Callable[[Any, int], str]]
    _text_v2_diagnostic_value: Callable[[], Callable[[Any], Any]]
    AiProviderError: Callable[[], type[Exception]]
    AiProviderTimeout: Callable[[], type[Exception]]
    AiProviderOverloaded: Callable[[], type[Exception]]
    AI_DEFAULT_TIMEOUT_SECONDS: Callable[[], int | float]
@dataclass(frozen=True)
class JsonToolExecution:
    ai_detection_settings: Callable[[], Callable[[], Record]]
    ai_tool_provider_meta: Callable[[], Callable[[Record], Record]]
    provider_generate_json_error_payload: Callable[[], Callable[..., Record]]
    generate_provider_json_with_fallback: Callable[[], Callable[..., tuple[Record, int, Record]]]
@dataclass(frozen=True)
class McpToolTransport:
    admission: Callable[[], Callable[[], AbstractContextManager]]
    ai_mcp_runtime: Callable[[], Callable[[], str]]
    AI_MCP_RUNTIME_STDIO: Callable[[], str]
    AI_MCP_RUNTIME_IN_PROCESS: Callable[[], str]
    _ai_mcp_client: Callable[[], McpClient]
    prepare_ai_mcp_payload: Callable[[], Callable[[str, Record], Record]]
    AI_MCP_TOOL_HANDLERS: Callable[[], Mapping[str, Callable[[Record], Record]]]
