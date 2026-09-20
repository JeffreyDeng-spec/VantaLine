"""Explicit pose render configuration service without application imports."""
from typing import Any
from .pose_render_ports import PoseRenderConfigurationSources, PoseRenderConfigurationDefaults


class PoseRenderConfiguration:
    def __init__(self, sources: PoseRenderConfigurationSources, defaults: PoseRenderConfigurationDefaults) -> None:
        self._sources = sources
        self._defaults = defaults

    def agent_mcp_gemini_image_config(self) -> dict[str, Any]:
        settings = self._sources.settings()()
        provider = str(settings.get("provider") or self._defaults.provider()).strip().lower()
        provider_key = self._sources.provider_key()(provider)
        provider_label = self._sources.provider_label()(provider)
        model = str(settings.get("model") or self._sources.model()(provider)).strip()
        timeout_seconds = max(10.0, min(300.0, float(settings.get("timeout_seconds") or self._defaults.timeout())))
        configured = bool(settings.get("configured"))
        missing: list[str] = []
        if not settings.get("api_key_present"):
            missing.append(str(settings.get("api_key_env") or self._defaults.key_environment()))
        if not model:
            missing.append(self._defaults.model_environment())
        return {
            "provider": provider_key,
            "provider_name": provider,
            "provider_label": provider_label,
            "configured": configured and bool(model),
            "model": model,
            "default_model": self._sources.model()(provider),
            "high_fidelity_model": self._defaults.high_fidelity_model(),
            "model_env": self._defaults.model_environment(),
            "legacy_model_env": self._defaults.legacy_model_environment(),
            "timeout_env": self._defaults.timeout_environment(),
            "legacy_timeout_env": self._defaults.legacy_timeout_environment(),
            "timeout_seconds": timeout_seconds,
            "base_url": settings.get("base_url") or self._sources.base_url()(provider),
            "api_key_env": settings.get("api_key_env") or self._sources.key_environment()(provider),
            "api_key_present": bool(settings.get("api_key_present")),
            "proxy_configured": bool(settings.get("proxy_configured")),
            "proxy_source_name": settings.get("proxy_source_name") or "",
            "missing": missing,
            "status": "ready" if configured and model else "missing_configuration",
            "message": (
                f"{provider_label} image generation is configured."
                if configured and model
                else f"Image generation requires provider settings: {', '.join(missing) or settings.get('message') or 'missing configuration'}."
            ),
        }
