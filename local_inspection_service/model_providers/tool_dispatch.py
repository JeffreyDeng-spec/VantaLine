"""JSON model tool dispatch and existing MCP fallback behavior."""
from dataclasses import dataclass
import time
from typing import Any
from .tool_dispatch_ports import ToolErrorPolicy, JsonToolExecution, McpToolTransport

@dataclass(frozen=True)
class ModelToolDispatch:
    errors: ToolErrorPolicy
    execution: JsonToolExecution
    transport: McpToolTransport

    def provider_generate_json_error_payload(self,
        settings: dict[str, Any],
        meta: dict[str, Any],
        exc: BaseException | str,
        *,
        timed_out: bool = False,
        overloaded: bool = False,
        latency_ms: int = 0,
    ) -> dict[str, Any]:
        error_text = self.errors.bounded_text()(str(exc) or exc.__class__.__name__, 240)
        error_type = "not_configured" if isinstance(exc, str) else self.errors.bounded_text()(exc.__class__.__name__, 80)
        provider_failure_meta: dict[str, Any] = {}
        if not isinstance(exc, str):
            usage_metadata = getattr(exc, "usage_metadata", None)
            failed_usage_metadata = getattr(exc, "failed_usage_metadata", None)
            attempts = getattr(exc, "attempts", None)
            retry_count = getattr(exc, "retry_count", None)
            previous_errors = getattr(exc, "previous_errors", None)
            http_status = getattr(exc, "http_status", None)
            fallback_model = getattr(exc, "fallback_model", "")
            fallback_reason = getattr(exc, "fallback_reason", "")
            response_sha256 = getattr(exc, "response_sha256", "")
            response_preview = getattr(exc, "response_preview", "")
            if isinstance(usage_metadata, dict) and usage_metadata:
                provider_failure_meta["usage_metadata"] = usage_metadata
            if isinstance(failed_usage_metadata, list) and failed_usage_metadata:
                provider_failure_meta["failed_usage_metadata"] = failed_usage_metadata
            if isinstance(attempts, int):
                provider_failure_meta["attempts"] = attempts
            if isinstance(retry_count, int):
                provider_failure_meta["retry_count"] = retry_count
            if isinstance(previous_errors, list) and previous_errors:
                provider_failure_meta["previous_errors"] = previous_errors[-2:]
            if isinstance(http_status, int):
                provider_failure_meta["http_status"] = http_status
            if fallback_model:
                provider_failure_meta["fallback_model"] = str(fallback_model)
            if fallback_reason:
                provider_failure_meta["fallback_reason"] = str(fallback_reason)
            if response_sha256:
                provider_failure_meta["response_sha256"] = str(response_sha256)
            if response_preview:
                provider_failure_meta["response_preview"] = self.errors._text_v2_diagnostic_value()(str(response_preview))
        error_meta = {**meta, "error_type": error_type, "overloaded": overloaded, **provider_failure_meta}
        return {
            "tool": "provider.gemini.generate_json",
            "ok": False,
            "parsed": {},
            "latency_ms": latency_ms,
            "timed_out": timed_out,
            "overloaded": overloaded,
            "provider_failure": True,
            "error": error_text,
            "error_type": error_type,
            "meta": error_meta,
            **meta,
            **provider_failure_meta,
        }


    def tool_provider_gemini_generate_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = dict(payload.get("provider_config") or self.execution.ai_detection_settings()())
        meta = self.execution.ai_tool_provider_meta()(settings)
        if not settings.get("configured"):
            return self.execution.provider_generate_json_error_payload()(settings, meta, settings.get("message") or "AI provider is not configured")
        max_attempts: int | None = None
        if payload.get("max_attempts") is not None:
            try:
                max_attempts = max(1, int(payload.get("max_attempts")))
            except (TypeError, ValueError):
                max_attempts = None
        try:
            parsed, latency_ms, provider_meta = self.execution.generate_provider_json_with_fallback()(
                settings,
                str(payload.get("system_prompt") or ""),
                payload.get("user_content") if isinstance(payload.get("user_content"), list) else [],
                max_tokens=int(payload.get("max_tokens") or 1400),
                cached_content=str(payload.get("cached_content") or ""),
                max_attempts=max_attempts,
            )
            return {
                "tool": "provider.gemini.generate_json",
                "ok": True,
                "parsed": parsed,
                "latency_ms": latency_ms,
                "timed_out": False,
                "error": "",
                "provider_failure": False,
                "meta": {**meta, **provider_meta},
                **meta,
                **provider_meta,
            }
        except self.errors.AiProviderTimeout() as exc:
            return self.execution.provider_generate_json_error_payload()(
                settings,
                meta,
                exc,
                timed_out=True,
                latency_ms=int(float(settings.get("timeout_seconds") or self.errors.AI_DEFAULT_TIMEOUT_SECONDS()) * 1000),
            )
        except self.errors.AiProviderOverloaded() as exc:
            return self.execution.provider_generate_json_error_payload()(settings, meta, exc, overloaded=True)
        except self.errors.AiProviderError() as exc:
            return self.execution.provider_generate_json_error_payload()(settings, meta, exc)
        except Exception as exc:
            return self.execution.provider_generate_json_error_payload()(settings, meta, exc)


    def call_ai_mcp_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.transport.admission()():
            # Extraction point for out-of-process MCP: default is an O(1) in-process tool dispatch.
            dispatch_start = time.monotonic()
            arguments = payload if isinstance(payload, dict) else {}
            runtime = self.transport.ai_mcp_runtime()()
            fallback_error = ""
            if runtime == self.transport.AI_MCP_RUNTIME_STDIO():
                try:
                    result = self.transport._ai_mcp_client().call_tool(tool_name, self.transport.prepare_ai_mcp_payload()(tool_name, arguments))
                    result.setdefault("mcp_transport", "stdio")
                    result.setdefault("mcp_runtime", self.transport.AI_MCP_RUNTIME_STDIO())
                    result.setdefault("mcp_dispatch_ms", int((time.monotonic() - dispatch_start) * 1000))
                    return result
                except Exception as exc:
                    fallback_error = self.errors.bounded_text()(str(exc) or exc.__class__.__name__, 180)
                    self.transport._ai_mcp_client().close()
            handler = self.transport.AI_MCP_TOOL_HANDLERS().get(tool_name)
            if handler is None:
                raise self.errors.AiProviderError()(f"Unknown AI MCP tool: {tool_name}")
            result = handler(arguments)
            if not isinstance(result, dict):
                raise self.errors.AiProviderError()(f"AI MCP tool returned non-object result: {tool_name}")
            result.setdefault("tool", tool_name)
            result.setdefault("mcp_transport", "in_process")
            result.setdefault("mcp_runtime", self.transport.AI_MCP_RUNTIME_IN_PROCESS())
            result.setdefault("mcp_dispatch_ms", int((time.monotonic() - dispatch_start) * 1000))
            if fallback_error:
                result.setdefault("mcp_fallback_from", self.transport.AI_MCP_RUNTIME_STDIO())
                result.setdefault("mcp_fallback_error", fallback_error)
            return result
