"""Image prompt, model selection, endpoint settings and response protocol."""
from dataclasses import dataclass
import os
from pathlib import Path
import requests
import shutil
from typing import Any
from .image_provider_configuration_ports import ImageProviderSelection, ImageProviderSettings, ImageProviderPayload

@dataclass(frozen=True)
class ImageProviderConfiguration:
    selection: ImageProviderSelection
    settings: ImageProviderSettings
    payload: ImageProviderPayload

    def image_job_prompt(self, job: dict[str, Any]) -> str:
        output_path = str(job.get("output_path", ""))
        pose_family = str(job.get("pose_family") or "combined")
        generation_step = str(job.get("generation_step") or "")
        input_count = len(job.get("input_files", []) or [])
        video_frame_count = len(job.get("video_reference_frames", []) or [])
        mode_hint = (
            "The first attached image is a hidden backend anchor image. Use it only for layout, pose, scale, camera, and table/background."
            if generation_step == "anchor_replacement"
            else "Follow the core prompt exactly."
        )
        pose_hint = {
            "upright": "Final image must contain exactly nine replacement objects matched to the nine anchor bars.",
            "lying": "Final image must contain exactly nine horizontal replacement objects.",
        }.get(pose_family, "Final image must follow the requested pose collection.")
        return f"""
You are the ImageWorker for the local assembly-line inspection service.

Use all {input_count} attached images. {video_frame_count} may be frames extracted from a user video.
{mode_hint}

Core prompt:
{job.get("prompt", "")}

- Generate a realistic PNG with AI image generation; do not satisfy this with local drawing or script-only image editing.
- {pose_hint}
- Save the final PNG exactly here:
  {output_path}
""".strip()


    def cursor_image_model_score(self, model_id: str) -> tuple[int, int]:
        lowered = str(model_id or "").lower()
        for index, marker in enumerate(self.selection.CURSOR_IMAGE_MODEL_PRIORITY()):
            if marker in lowered:
                return (100 - index, len(lowered))
        if any(marker in lowered for marker in self.selection.CURSOR_IMAGE_MODEL_KEYWORDS()):
            return (10, len(lowered))
        return (0, len(lowered))


    def inspect_cursor_image_models(self, agent_config: dict[str, Any]) -> dict[str, Any]:
        options = self.selection.normalize_agent_model_options()(agent_config.get("model_options"))
        image_options = [
            option
            for option in options
            if self.selection.cursor_image_model_score()(str(option.get("id") or option.get("label") or ""))[0] > 0
        ]
        image_options.sort(key=lambda item: self.selection.cursor_image_model_score()(str(item.get("id") or item.get("label") or "")), reverse=True)
        recommended_model = str(image_options[0]["id"]) if image_options else ""
        connected = self.selection.normalize_agent_provider()(agent_config.get("provider"), agent_config.get("base_url", "")) == self.selection.AGENT_PROVIDER_CURSOR() and self.selection.agent_connected()(agent_config)
        if recommended_model:
            status = "image_model_available"
            message = f"Cursor model list includes image-capable candidate {recommended_model}."
        elif connected and options:
            status = "no_image_model"
            message = "Cursor /v1/models is reachable, but the returned model list does not expose an image-generation-capable model."
        elif connected:
            status = "no_model_list"
            message = "Cursor is connected, but no cached model list is available; run Agent config test to refresh /v1/models."
        else:
            status = "not_connected"
            message = "Cursor Agent credentials are not connected; cannot inspect /v1/models for image-capable models."
        return {
            "status": status,
            "connected": bool(connected),
            "model_count": len(options),
            "image_model_count": len(image_options),
            "image_models": image_options[:12],
            "recommended_model": recommended_model,
            "message": message,
        }


    def cursor_image2_settings(self) -> dict[str, Any]:
        agent_config = self.settings.load_agent_config()()
        agent_is_cursor = self.selection.normalize_agent_provider()(agent_config.get("provider"), agent_config.get("base_url", "")) == self.selection.AGENT_PROVIDER_CURSOR()
        model_inspection = self.settings.inspect_cursor_image_models()(agent_config)
        base_url = (
            os.environ.get(self.settings.CURSOR_IMAGE2_BASE_URL_ENV(), "").strip().rstrip("/")
            or (str(agent_config.get("base_url") or "").strip().rstrip("/") if agent_is_cursor else "")
            or self.settings.AGENT_CURSOR_DEFAULT_BASE_URL()
        )
        endpoint = os.environ.get(self.settings.CURSOR_IMAGE2_ENDPOINT_ENV(), "").strip().rstrip("/")
        api_key = os.environ.get(self.settings.CURSOR_IMAGE2_API_KEY_ENV(), "").strip() or (str(agent_config.get("api_key") or "").strip() if agent_is_cursor else "")
        model = os.environ.get(self.settings.CURSOR_IMAGE2_MODEL_ENV(), "").strip() or model_inspection.get("recommended_model") or self.settings.CURSOR_IMAGE2_DEFAULT_MODEL()
        missing: list[str] = []
        if not endpoint:
            missing.append(self.settings.CURSOR_IMAGE2_ENDPOINT_ENV())
        if not api_key:
            missing.append(self.settings.CURSOR_IMAGE2_API_KEY_ENV())
        if not model:
            missing.append(self.settings.CURSOR_IMAGE2_MODEL_ENV())
        return {
            "configured": not missing,
            "base_url": base_url,
            "endpoint": endpoint,
            "endpoint_public": self.settings.masked_url_for_status()(endpoint),
            "api_key": api_key,
            "has_api_key": bool(api_key),
            "model": model,
            "missing": missing,
            "status": "ready" if not missing else "missing_config",
            "message": (
                "Cursor Image2 endpoint is configured."
                if not missing
                else f"{model_inspection['message']} Cursor image generation requires an explicit image-generation endpoint/protocol or private relay. "
                + f"Set {self.settings.CURSOR_IMAGE2_ENDPOINT_ENV()}; use {self.settings.CURSOR_IMAGE2_API_KEY_ENV()} if the existing Cursor Agent key should not be reused."
            ),
            "model_inspection": model_inspection,
            "timeout_seconds": max(10.0, min(900.0, float(agent_config.get("timeout_seconds") or 120.0))),
        }


    def public_cursor_image2_status(self) -> dict[str, Any]:
        settings = self.settings.cursor_image2_settings()()
        local_codex_available = bool(shutil.which("codex"))
        fallback = {
            "provider": self.settings.LOCAL_CODEX_IMAGE_PROVIDER(),
            "configured": local_codex_available,
            "endpoint": "local-codex-cli" if local_codex_available else "",
            "route": "codex exec",
            "status": "available" if local_codex_available else "missing_config",
            "message": "Local Codex image fallback is available." if local_codex_available else "codex CLI is not available on this host.",
        }
        return {
            "provider": self.settings.CURSOR_IMAGE2_PROVIDER(),
            "configured": bool(settings.get("configured")),
            "endpoint": settings.get("endpoint_public") or "",
            "model": settings.get("model") or "",
            "has_api_key": bool(settings.get("has_api_key")),
            "status": settings.get("status") or "",
            "message": settings.get("message") or "",
            "missing": settings.get("missing") or [],
            "model_inspection": settings.get("model_inspection") or {},
            "fallback": fallback,
        }


    def cursor_image2_payload(self, job: dict[str, Any], input_files: list[str], settings: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": settings["model"],
            "prompt": self.payload.image_job_prompt()(job),
            "n": 1,
            "size": os.environ.get("INSPECTION_CURSOR_IMAGE2_SIZE", "1024x1024").strip() or "1024x1024",
            "response_format": "b64_json",
            "input_images": [self.payload.image_file_payload()(Path(path)) for path in input_files[:self.payload.MAX_IMAGE_WORKER_INPUTS()]],
        }


    def cursor_image2_response_candidates(self, payload: Any) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            for key in ("data", "images", "output", "result"):
                value = payload.get(key)
                if isinstance(value, list):
                    candidates.extend(item for item in value if isinstance(item, dict))
                elif isinstance(value, dict):
                    candidates.append(value)
            if any(key in payload for key in ("b64_json", "base64", "image_base64", "url")):
                candidates.append(payload)
        elif isinstance(payload, list):
            candidates.extend(item for item in payload if isinstance(item, dict))
        return candidates


    def extract_cursor_image2_bytes(self, payload: dict[str, Any], settings: dict[str, Any]) -> bytes:
        for item in self.payload.cursor_image2_response_candidates()(payload):
            for key in ("b64_json", "base64", "image_base64"):
                image_bytes = self.payload.decode_b64_image()(item.get(key))
                if image_bytes:
                    return image_bytes
            url = str(item.get("url") or "").strip()
            if url:
                response = requests.get(url, timeout=float(settings["timeout_seconds"]))
                response.raise_for_status()
                return response.content
        raise RuntimeError(
            "Cursor Image2 response did not include image bytes. Expected data[0].b64_json/base64/image_base64 or data[0].url; "
            f"set {self.settings.CURSOR_IMAGE2_ENDPOINT_ENV()} if this Cursor Image2 endpoint uses a different response shape."
        )
