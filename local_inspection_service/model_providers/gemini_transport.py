"""Gemini provider operations through explicit runtime capabilities."""
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any
from ..model_profiles.audit import metered_instance
from ..model_profiles.dependencies import ResolverProvider
from .gemini_ports import GeminiTransportIO, GeminiTransportErrors

class GeminiAiProvider:
    def __init__(self, settings: dict[str, Any], io: GeminiTransportIO,
                 errors: GeminiTransportErrors, resolve: ResolverProvider):
        self.settings = settings
        self.last_usage_metadata: dict[str, Any] = {}
        self.last_raw_text = ""
        self.io, self.errors, self.resolve = io, errors, resolve

    def content_parts(self, user_content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        for item in user_content:
            if item.get("type") == "text":
                parts.append({"text": str(item.get("text") or "")})
            elif item.get("type") == "image_url":
                image_url = item.get("image_url") if isinstance(item.get("image_url"), dict) else {}
                mime_type, data = self.io.data_url()(str(image_url.get("url") or ""))
                parts.append({"inlineData": {"mimeType": mime_type, "data": data}})
        return parts

    def create_cached_content(
        self,
        system_prompt: str,
        user_content: list[dict[str, Any]],
        *,
        display_name: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        if not self.settings.get("configured"):
            raise self.errors.config()(str(self.settings.get("message") or "AI provider is not configured"))
        model_name = str(self.settings["model"]).strip()
        model = self.io.quote()(model_name, safe="-_.")
        payload = {
            "model": f"models/{model_name}",
            "displayName": self.io.text()(display_name, 120),
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": self.content_parts(user_content)}],
            "ttl": f"{max(300, int(ttl_seconds))}s",
        }
        base_url = str(self.settings["base_url"]).rstrip("/")
        request = urllib.request.Request(
            f"{base_url}/cachedContents",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.settings["api_key"],
            },
            method="POST",
        )
        start = time.monotonic()
        try:
            with self.io.open()(request, self.settings, timeout=float(self.settings["timeout_seconds"])) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (TimeoutError, socket.timeout) as exc:
            raise self.errors.timeout()("AI cache provider timed out") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:240]
            raise self.errors.error()(f"AI cache create failed: HTTP {exc.code} {self.io.text()(detail, 180)}") from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), socket.timeout):
                raise self.errors.timeout()("AI cache provider timed out") from exc
            raise self.errors.error()(f"AI cache create failed: {self.io.text()(exc, 180)}") from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        try:
            response_json = json.loads(body)
        except json.JSONDecodeError as exc:
            raise self.errors.error()("AI cache response shape was not recognized") from exc
        if not isinstance(response_json, dict) or not response_json.get("name"):
            raise self.errors.error()("AI cache response did not include a cache name")
        return {
            "name": str(response_json.get("name")),
            "model": model_name,
            "latency_ms": latency_ms,
            "usage_metadata": response_json.get("usageMetadata") if isinstance(response_json.get("usageMetadata"), dict) else {},
            "expire_time": str(response_json.get("expireTime") or ""),
        }

    @metered_instance(lambda provider: provider.resolve())
    def generate_json(
        self,
        system_prompt: str,
        user_content: list[dict[str, Any]],
        *,
        max_tokens: int = 1400,
        cached_content: str = "",
    ) -> tuple[dict[str, Any], int]:
        if not self.settings.get("configured"):
            raise self.errors.config()(str(self.settings.get("message") or "AI provider is not configured"))
        self.last_usage_metadata = {}
        self.last_raw_text = ""
        parts = self.content_parts(user_content)
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        if cached_content:
            payload["cachedContent"] = cached_content
        else:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        model_name = str(self.settings["model"]).strip()
        generation_config = payload["generationConfig"]
        if model_name.startswith("gemini-2.5-flash") or model_name.startswith("gemini-flash-lite"):
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}
        elif model_name.startswith("gemini-2.5-pro"):
            generation_config["thinkingConfig"] = {"thinkingBudget": 128}
        elif model_name.startswith("gemini-3"):
            generation_config["thinkingConfig"] = {"thinkingLevel": "minimal"}
        base_url = str(self.settings["base_url"]).rstrip("/")
        model = self.io.quote()(model_name, safe="-_.")
        request = urllib.request.Request(
            f"{base_url}/models/{model}:generateContent",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.settings["api_key"],
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
            self.last_usage_metadata = response_json.get("usageMetadata") if isinstance(response_json.get("usageMetadata"), dict) else {}
            candidates = response_json["candidates"]
            if self.settings.get("profile_id") and (len(candidates) != 1 or candidates[0].get("finishReason") != "STOP"):
                raise self.errors.error()("AI provider output is incomplete")
            parts = candidates[0]["content"]["parts"]
            content = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise self.errors.error()("AI provider response shape was not recognized") from exc
        self.last_raw_text = str(content or "")
        return self.io.parse()(str(content or "")), latency_ms

    @metered_instance(lambda provider: provider.resolve())
    def generate_image(
        self,
        prompt: str,
        user_content: list[dict[str, Any]],
        *,
        model: str,
        system_prompt: str = "",
    ) -> dict[str, Any]:
        if not self.settings.get("configured"):
            raise self.errors.config()(str(self.settings.get("message") or "AI provider is not configured"))
        self.last_usage_metadata = {}
        self.last_raw_text = ""
        model_name = str(model or self.settings.get("model") or "").strip()
        if not model_name:
            raise self.errors.config()("Gemini image model is not configured")
        parts = self.content_parts([{"type": "text", "text": prompt}, *user_content])
        payload = {"contents": [{"role": "user", "parts": parts}]}
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        base_url = str(self.settings["base_url"]).rstrip("/")
        request = urllib.request.Request(
            f"{base_url}/models/{self.io.quote()(model_name, safe='-_.')}:generateContent",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.settings["api_key"],
            },
            method="POST",
        )
        start = time.monotonic()
        try:
            with self.io.open()(request, self.settings, timeout=float(self.settings["timeout_seconds"])) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (TimeoutError, socket.timeout) as exc:
            raise self.errors.timeout()("Gemini image provider timed out") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            proxy_used = bool(str(self.settings.get("proxy_url_raw") or self.settings.get("proxy_url") or "").strip())
            proxy_source = str(self.settings.get("proxy_source_name") or "proxy").strip()
            if exc.code == 400 and "User location is not supported" in detail:
                if proxy_used:
                    raise self.errors.config()(
                        f"Gemini image provider is still region-blocked while using proxy source {proxy_source}; verify server-side proxy routing."
                    ) from exc
                raise self.errors.config()(
                    "Gemini image provider is region-blocked on direct egress; configure AI proxy or enable the server-local Gemini proxy."
                ) from exc
            error_text = f"Gemini image provider request failed: HTTP {exc.code} {self.io.text()(detail, 180)}"
            if exc.code in {401, 403}:
                raise self.errors.auth()(error_text, http_status=exc.code) from exc
            if exc.code in {429, 503}:
                raise self.errors.overloaded()(f"Gemini image provider overloaded: HTTP {exc.code} {self.io.text()(detail, 180)}", http_status=exc.code) from exc
            if exc.code in {400, 404}:
                raise self.errors.config()(error_text, http_status=exc.code) from exc
            raise self.errors.error()(error_text, http_status=exc.code) from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), socket.timeout):
                raise self.errors.timeout()("Gemini image provider timed out") from exc
            if str(self.settings.get("proxy_url_raw") or self.settings.get("proxy_url") or "").strip():
                proxy_source = str(self.settings.get("proxy_source_name") or "proxy").strip()
                raise self.errors.error()(f"Gemini image provider proxy/connectivity failed via {proxy_source}: {self.io.text()(exc, 180)}") from exc
            raise self.errors.error()(f"Gemini image provider request failed: {self.io.text()(exc, 180)}") from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        try:
            response_json = json.loads(body)
            self.last_usage_metadata = response_json.get("usageMetadata") if isinstance(response_json.get("usageMetadata"), dict) else {}
            parts = response_json["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise self.errors.error()("Gemini image provider response shape was not recognized") from exc
        text_parts: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("text"):
                text_parts.append(str(part.get("text") or ""))
                continue
            inline = part.get("inlineData") if isinstance(part.get("inlineData"), dict) else part.get("inline_data")
            if not isinstance(inline, dict):
                continue
            image_bytes = self.io.decode()(inline.get("data"))
            if image_bytes:
                self.last_raw_text = "\n".join(text_parts)
                return {
                    "bytes": image_bytes,
                    "mime_type": str(inline.get("mimeType") or inline.get("mime_type") or "image/png"),
                    "latency_ms": latency_ms,
                    "model": model_name,
                    "usage_metadata": self.last_usage_metadata,
                    "text": self.last_raw_text,
                    "proxy_used": bool(str(self.settings.get("proxy_url_raw") or self.settings.get("proxy_url") or "").strip()),
                    "proxy_source_name": str(self.settings.get("proxy_source_name") or ""),
                    "proxy_url": self.io.mask_url()(self.settings.get("proxy_url_raw") or self.settings.get("proxy_url") or ""),
                    "proxy_auto_local": bool(self.settings.get("proxy_auto_local")),
                }
        self.last_raw_text = "\n".join(text_parts)
        raise self.errors.error()("Gemini image provider did not return inline image data")
