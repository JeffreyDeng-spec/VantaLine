"""OpenAI-compatible JSON transport with explicit runtime dependencies."""
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any
from ..model_profiles.audit import metered_instance
from ..model_profiles.dependencies import ResolverProvider
from .openai_ports import OpenAITransportIO, OpenAITransportErrors

class OpenAICompatibleAiProvider:
    def __init__(self, settings: dict[str, Any], io: OpenAITransportIO,
                 errors: OpenAITransportErrors, resolve: ResolverProvider):
        self.settings = settings
        self.last_usage_metadata: dict[str, Any] = {}
        self.io, self.errors, self.resolve = io, errors, resolve

    @metered_instance(lambda provider: provider.resolve())
    def generate_json(self, system_prompt: str, user_content: list[dict[str, Any]], *, max_tokens: int = 1400) -> tuple[dict[str, Any], int]:
        if not self.settings.get("configured"):
            raise self.errors.config()(str(self.settings.get("message") or "AI provider is not configured"))
        self.last_usage_metadata = {}
        payload = {
            "model": self.settings["model"],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        if self.settings.get("provider") == "doubao":
            payload["thinking"] = {"type": "disabled"}
        elif self.settings.get("provider") == "qwen":
            payload["enable_thinking"] = False
        request = urllib.request.Request(
            self.settings["base_url"],
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings['api_key']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        start = time.monotonic()
        try:
            with self.io.open()(request, self.settings, timeout=float(self.settings["timeout_seconds"])) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (TimeoutError, socket.timeout) as exc:
            raise self.errors.timeout()("AI provider timed out") from exc
        except urllib.error.HTTPError as exc:
            raise self.io.http_error()("AI provider request failed", exc) from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), socket.timeout):
                raise self.errors.timeout()("AI provider timed out") from exc
            raise self.errors.error()(f"AI provider request failed: {self.io.text()(exc, 180)}") from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        try:
            response_json = json.loads(body)
            self.last_usage_metadata = response_json.get("usage") if isinstance(response_json.get("usage"), dict) else {}
            choices = response_json["choices"]
            if self.settings.get("profile_id") and (len(choices) != 1 or choices[0].get("finish_reason") != "stop"):
                raise self.errors.error()("AI provider output is incomplete")
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            provider_error = self.errors.error()("AI provider response shape was not recognized")
            provider_error.response_sha256 = self.io.digest()(body.encode("utf-8", errors="replace"))
            provider_error.response_preview = body[:8192]
            raise provider_error from exc
        if isinstance(content, list):
            content = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        response_text = str(content or "")
        try:
            return self.io.parse()(response_text), latency_ms
        except self.errors.error() as exc:
            exc.response_sha256 = self.io.digest()(response_text.encode("utf-8", errors="replace"))
            exc.response_preview = response_text[:8192]
            raise
