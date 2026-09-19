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

class AgnesImageProvider:
    def __init__(self, settings: dict[str, Any], io: ImageTransportIO,
                 errors: ImageTransportErrors, resolve: ResolverProvider,
                 image_size: Callable[[], str], candidates: Callable[[], Callable[[Any], list[dict[str, Any]]]]):
        self.settings = settings
        self.last_raw_text = ""
        self.io, self.errors, self.resolve, self.image_size = io, errors, resolve, image_size
        self.candidates = candidates

    def input_images(self, user_content: list[dict[str, Any]]) -> list[str]:
        images: list[str] = []
        for item in user_content:
            if item.get("type") != "image_url":
                continue
            image_url = item.get("image_url") if isinstance(item.get("image_url"), dict) else {}
            url = str(image_url.get("url") or "").strip()
            if url:
                images.append(url)
        return images[:8]

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
            raise self.errors.timeout()("Agnes image provider timed out") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            error_text = f"Agnes image provider request failed: HTTP {exc.code} {self.io.text()(detail, 180)}"
            if exc.code in {401, 403}:
                raise self.errors.auth()(error_text, http_status=exc.code) from exc
            if exc.code in {429, 503}:
                raise self.errors.overloaded()(f"Agnes image provider overloaded: HTTP {exc.code} {self.io.text()(detail, 180)}", http_status=exc.code) from exc
            if exc.code in {400, 404}:
                raise self.errors.config()(error_text, http_status=exc.code) from exc
            raise self.errors.error()(error_text, http_status=exc.code) from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), socket.timeout):
                raise self.errors.timeout()("Agnes image provider timed out") from exc
            raise self.errors.error()(f"Agnes image provider request failed: {self.io.text()(exc, 180)}") from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise self.errors.error()("Agnes image provider response shape was not recognized") from exc
        if not isinstance(parsed, dict):
            raise self.errors.error()("Agnes image provider response shape was not recognized")
        return parsed, latency_ms

    def extract_image_bytes(self, payload: dict[str, Any]) -> bytes:
        for item in self.candidates()(payload):
            for key in ("b64_json", "base64", "image_base64"):
                image_bytes = self.io.decode()(item.get(key))
                if image_bytes:
                    return image_bytes
            url = str(item.get("url") or "").strip()
            if url:
                try:
                    response = self.io.download()(url, timeout=float(self.settings["timeout_seconds"]))
                    response.raise_for_status()
                    return response.content
                except self.errors.download_error() as exc:
                    raise self.errors.error()(f"Agnes image provider URL download failed: {self.io.text()(exc, 180)}") from exc
        raise self.errors.error()("Agnes image provider did not return image bytes")

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
            raise self.errors.config()(str(self.settings.get("message") or "Agnes image provider is not configured"))
        model_name = str(model or self.settings.get("model") or "").strip()
        if not model_name:
            raise self.errors.config()("Agnes image model is not configured")
        images = self.input_images(user_content)
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
        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": request_prompt,
            "n": 1,
            "size": "1024x1024" if self.settings.get("single_attempt") else (self.image_size().strip() or "1024x1024"),
        }
        extra_body: dict[str, Any] = {"response_format": "b64_json"}
        if images:
            extra_body["image"] = images
        payload["extra_body"] = extra_body
        try:
            response_json, latency_ms = self.request_image(payload)
        except self.errors.config() as exc:
            if self.settings.get("single_attempt") or "response_format" not in str(exc).lower():
                raise
            payload["extra_body"] = {key: value for key, value in extra_body.items() if key != "response_format"}
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
