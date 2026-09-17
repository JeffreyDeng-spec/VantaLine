"""Bounded diagnostic projections and event logging through narrow capabilities."""
import io
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from PIL import Image


def diagnostic_value(value: Any, *, depth: int = 0) -> Any:
    """Bound diagnostic payloads and remove credentials or embedded media."""
    if depth > 6:
        return "<depth-limit>"
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:120]:
            key = str(raw_key)[:120]
            normalized = key.lower().replace("-", "_")
            sensitive_key = (
                normalized in {"api_key", "authorization", "cookie", "set_cookie", "secret", "token"}
                or normalized.endswith(("_api_key", "_authorization", "_cookie", "_secret", "_token"))
            )
            if sensitive_key:
                clean[key] = "<redacted>"
            elif normalized in {"image_url", "data_url", "url"} and str(raw_value).startswith("data:"):
                clean[key] = f"<embedded-media:{len(str(raw_value))}-chars>"
            else:
                clean[key] = diagnostic_value(raw_value, depth=depth + 1)
        return clean
    if isinstance(value, (list, tuple)):
        return [diagnostic_value(item, depth=depth + 1) for item in list(value)[:120]]
    if isinstance(value, str):
        if value.startswith("data:") and ";base64," in value[:160]:
            return f"<embedded-media:{len(value)}-chars>"
        return value[:8192]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:1000]


def diagnostic_event(
    diagnostics: dict[str, Any],
    stage: str,
    status: str,
    *,
    details: dict[str, Any] | None = None,
) -> None:
    started_ms = int(diagnostics.get("request_received_at_ms") or int(time.time() * 1000))
    now_ms = int(time.time() * 1000)
    event: dict[str, Any] = {
        "stage": str(stage),
        "status": str(status),
        "at_ms": now_ms,
        "elapsed_ms": max(0, now_ms - started_ms),
    }
    if details:
        event["details"] = diagnostic_value(details)
    diagnostics.setdefault("events", []).append(event)


def provider_diagnostics(provider: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "ok", "tool", "provider", "provider_model", "latency_ms", "timed_out", "overloaded",
        "provider_failure", "error", "error_type", "http_status", "attempts", "retry_count",
        "previous_errors", "fallback_model", "fallback_reason", "usage_metadata",
        "failed_usage_metadata", "response_sha256", "response_preview",
    )
    result = {key: provider.get(key) for key in keys if provider.get(key) not in (None, "", [], {})}
    result["provider"] = provider.get("provider") or settings.get("provider") or ""
    result["model"] = provider.get("model") or provider.get("provider_model") or settings.get("model") or ""
    result["parsed_response"] = provider.get("parsed") if isinstance(provider.get("parsed"), dict) else {}
    return diagnostic_value(result)


class TextDiagnostics:
    def __init__(self, digest: Callable[[bytes], str], logger: Callable[[], logging.Logger]):
        self.digest = digest
        self.logger = logger

    def image_diagnostics(self, contents: bytes, *, source_format: str, mime_type: str) -> dict[str, Any]:
        width = height = 0
        mode = ""
        try:
            with Image.open(io.BytesIO(contents)) as image:
                width, height = image.size
                mode = str(image.mode or "")
        except Exception:
            pass
        return {
            "bytes": len(contents),
            "sha256": self.digest(contents),
            "source_format": str(source_format or ""),
            "mime_type": str(mime_type or ""),
            "width": int(width),
            "height": int(height),
            "mode": mode,
        }

    def write_server_diagnostic(self, record: dict[str, Any]) -> None:
        diagnostics = record.get("diagnostics") if isinstance(record.get("diagnostics"), dict) else {}
        failure = diagnostics.get("failure") if isinstance(diagnostics.get("failure"), dict) else {}
        payload = {
            "event": "text_inspection_label_compare",
            "inspection_id": record.get("id"),
            "comparison_id": record.get("comparison_id"),
            "standard_id": record.get("standard_id"),
            "standard_asset_id": record.get("standard_asset_id"),
            "status": record.get("status"),
            "decision": record.get("decision"),
            "provider": record.get("provider") or record.get("planned_provider"),
            "model": record.get("model") or record.get("planned_model"),
            "failure_stage": failure.get("stage"),
            "error_type": failure.get("error_type"),
            "error_message_sha256": (
                self.digest(str(failure.get("message") or "").encode("utf-8", errors="replace"))
                if failure.get("message") else ""
            ),
            "elapsed_ms": max(0, int(time.time() * 1000) - int(diagnostics.get("request_received_at_ms") or 0)),
        }
        self.logger().info(
            "text_inspection_diagnostic %s",
            json.dumps(diagnostic_value(payload), ensure_ascii=False, separators=(",", ":")),
        )
