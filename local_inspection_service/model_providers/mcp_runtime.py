"""MCP mode policy, image payload preparation and optional warmup boundary."""
from collections.abc import Callable
from dataclasses import dataclass
import os
from typing import Any, Protocol
import numpy as np


class EncodeArray(Protocol):
    def __call__(self, image_bgr: np.ndarray, max_side: int = 1280, quality: int = 82) -> str: ...


class WarmupClient(Protocol):
    def ensure_started(self) -> None: ...
    def close(self) -> None: ...


AI_MCP_RUNTIME_ENV = "INSPECTION_AI_MCP_RUNTIME"
AI_MCP_LEGACY_ENABLED_ENV = "INSPECTION_AI_MCP_ENABLED"
AI_MCP_RUNTIME_IN_PROCESS = "in_process"
AI_MCP_RUNTIME_STDIO = "stdio"


def ai_mcp_runtime() -> str:
    if os.environ.get("INSPECTION_AI_MCP_SERVER_MODE"):
        return AI_MCP_RUNTIME_IN_PROCESS
    runtime = os.environ.get(AI_MCP_RUNTIME_ENV, "").strip().lower().replace("-", "_")
    if runtime in {"stdio", "external", "subprocess", "mcp"}:
        return AI_MCP_RUNTIME_STDIO
    if runtime in {"in_process", "inprocess", "local", "direct", ""}:
        return AI_MCP_RUNTIME_IN_PROCESS
    legacy_enabled = os.environ.get(AI_MCP_LEGACY_ENABLED_ENV)
    if legacy_enabled is not None and legacy_enabled.strip().lower() in {"1", "true", "yes", "on", "stdio"}:
        return AI_MCP_RUNTIME_STDIO
    return AI_MCP_RUNTIME_IN_PROCESS


def external_ai_mcp_enabled() -> bool:
    return ai_mcp_runtime() == AI_MCP_RUNTIME_STDIO


@dataclass(frozen=True)
class McpPayloadPreparation:
    encoder: Callable[[], EncodeArray]
    max_side: Callable[[], int]
    quality: Callable[[], int]

    def prepare_ai_mcp_payload(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(payload)
        image_bgr = prepared.get("inspection_image_bgr")
        if tool_name == "vision.inspect.presence" and prepared.get("inspection_image_path"):
            prepared.pop("inspection_image_bgr", None)
        elif tool_name == "vision.inspect.presence" and isinstance(image_bgr, np.ndarray):
            prepared["inspection_image_data_url"] = self.encoder()(
                image_bgr,
                max_side=self.max_side(),
                quality=self.quality(),
            )
            prepared.pop("inspection_image_bgr", None)
        return prepared


@dataclass(frozen=True)
class McpWarmup:
    enabled: Callable[[], bool]
    client: Callable[[], WarmupClient]

    def warm_ai_mcp_client(self) -> None:
        if not self.enabled():
            return
        try:
            self.client().ensure_started()
        except Exception:
            self.client().close()
