"""Application-independent image generation through explicit capabilities."""
import json
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from ..model_profiles.audit import metered_instance
from ..model_profiles.dependencies import ResolverProvider
from .image_ports import ImageTransportIO, ImageTransportErrors

class QwenImageProvider:
    def __init__(self, settings: dict[str, Any], io: ImageTransportIO,
                 errors: ImageTransportErrors, resolve: ResolverProvider,
                 image_size: Callable[[], str]):
        self.settings = settings
        self.last_raw_text = ""
        self.io, self.errors, self.resolve, self.image_size = io, errors, resolve, image_size

    def input_content(self, user_content: list[dict[str, Any]]) -> list[dict[str, str]]:
        content: list[dict[str, str]] = []
        for item in user_content:
            if item.get("type") == "text":
                text = str(item.get("text") or "").strip()
                if text:
                    content.append({"text": text})
                continue
            if item.get("type") != "image_url":
                continue
            image_url = item.get("image_url") if isinstance(item.get("image_url"), dict) else {}
            url = str(image_url.get("url") or "").strip()
            if url:
                content.append({"image": url})
        return content[:4]

    def request_image(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        request = urllib.request.Request(
            str(self.settings["base_url"]).strip(),
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
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
            raise self.errors.timeout()("Qwen image provider timed out") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            error_text = f"Qwen image provider request failed: HTTP {exc.code} {self.io.text()(detail, 180)}"
            if exc.code in {401, 403}:
                raise self.errors.auth()(error_text, http_status=exc.code) from exc
            if exc.code in {429, 503}:
                raise self.errors.overloaded()(f"Qwen image provider overloaded: HTTP {exc.code} {self.io.text()(detail, 180)}", http_status=exc.code) from exc
            if exc.code in {400, 404}:
                raise self.errors.config()(error_text, http_status=exc.code) from exc
            raise self.errors.error()(error_text, http_status=exc.code) from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), socket.timeout):
                raise self.errors.timeout()("Qwen image provider timed out") from exc
            raise self.errors.error()(f"Qwen image provider request failed: {self.io.text()(exc, 180)}") from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise self.errors.error()("Qwen image provider response shape was not recognized") from exc
        if not isinstance(parsed, dict):
            raise self.errors.error()("Qwen image provider response shape was not recognized")
        return parsed, latency_ms

    def extract_image_bytes(self, payload: dict[str, Any]) -> bytes:
        stack: list[Any] = [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(reversed(item))
                continue
            if not isinstance(item, dict):
                continue
            for key in ("b64_json", "base64", "image_base64"):
                image_bytes = self.io.decode()(item.get(key))
                if image_bytes:
                    return image_bytes
            url = str(item.get("url") or item.get("image") or item.get("image_url") or "").strip()
            if url:
                try:
                    response = self.io.download()(url, timeout=float(self.settings["timeout_seconds"]))
                    response.raise_for_status()
                    return response.content
                except self.errors.download_error() as exc:
                    raise self.errors.error()(f"Qwen image provider URL download failed: {self.io.text()(exc, 180)}") from exc
            stack.extend(reversed(list(item.values())))
        raise self.errors.error()("Qwen image provider did not return image bytes")

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
            raise self.errors.config()(str(self.settings.get("message") or "Qwen image provider is not configured"))
        model_name = str(model or self.settings.get("model") or "").strip()
        if not model_name:
            raise self.errors.config()("Qwen image model is not configured")
        request_prompt = prompt
        if system_prompt:
            request_prompt = "\n\n".join(
                [
                    "SYSTEM_INSTRUCTIONS:",
                    system_prompt,
                    "USER_TASK:",
                    prompt,
                ]
            )
        content = [{"text": request_prompt}, *self.input_content(user_content)]
        payload: dict[str, Any] = {
            "model": model_name,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {
                "n": 1,
                "watermark": False,
                "size": "1024*1024" if self.settings.get("single_attempt") else (self.image_size().strip() or "1024*1024"),
            },
        }
        response_json, latency_ms = self.request_image(payload)
        image_bytes = self.extract_image_bytes(response_json)
        return {
            "bytes": image_bytes,
            "mime_type": "image/png",
            "latency_ms": latency_ms,
            "model": model_name,
            "usage_metadata": {},
            "text": "",
            "proxy_used": bool(str(self.settings.get("proxy_url_raw") or self.settings.get("proxy_url") or "").strip()),
            "proxy_source_name": str(self.settings.get("proxy_source_name") or ""),
            "proxy_url": self.io.mask_url()(self.settings.get("proxy_url_raw") or self.settings.get("proxy_url") or ""),
            "proxy_auto_local": bool(self.settings.get("proxy_auto_local")),
        }
