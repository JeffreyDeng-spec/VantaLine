"""Legacy settings used by profile migration, without application imports."""
from typing import Any
from .legacy_settings_ports import LegacySettingsIO, LegacyPresentation, LegacyImagePolicy, LegacyImageEnvironment, LegacyImageCallbacks

class LegacyImageSettings:
    def __init__(self, io: LegacySettingsIO, presentation: LegacyPresentation, policy: LegacyImagePolicy, environment: LegacyImageEnvironment, callbacks: LegacyImageCallbacks) -> None:
        self._io = io
        self._presentation = presentation
        self._policy = policy
        self._environment = environment
        self._callbacks = callbacks

    def _legacy_image_generation_settings(self) -> dict[str, Any]:
        local = self._io.load()()
        provider = (
            self._io.environment().get(self._environment.provider(), "").strip().lower()
            or str(local.get("image_provider") or self._policy.provider()).strip().lower()
        )
        if provider not in self._policy.supported():
            provider = self._policy.provider()
        legacy_gemini_model = self._io.environment().get(self._environment.gemini_model(), "").strip()
        model = (
            self._io.environment().get(self._environment.model(), "").strip()
            or (legacy_gemini_model if provider == "gemini" else "")
            or str(local.get("image_model") or "").strip()
            or self._callbacks.default_model()(provider)
        )
        base_url = (
            self._io.environment().get(self._environment.base(), "").strip()
            or str(local.get("image_base_url") or "").strip()
            or self._callbacks.default_base()(provider)
        )
        proxy_url, proxy_source_name, proxy_auto_local = self._io.proxy()(local, provider)
        legacy_gemini_timeout = self._io.environment().get(self._environment.gemini_timeout(), "").strip()
        timeout_raw = (
            self._io.environment().get(self._environment.timeout(), "").strip()
            or (legacy_gemini_timeout if provider == "gemini" else "")
            or local.get("image_timeout_seconds", self._policy.timeout())
        )
        try:
            timeout = self._callbacks.validate_timeout()(timeout_raw)
        except self._io.http_error():
            timeout = self._policy.timeout()
        timeout = max(10.0, min(300.0, float(timeout)))
        key_env = self._io.environment().get(self._environment.named_key(), "").strip()
        if not key_env:
            key_env = self._callbacks.default_key_env()(provider)

        direct_env_key = self._io.environment().get(self._environment.direct_key(), "").strip()
        named_env_key = self._io.environment().get(key_env, "").strip() if key_env else ""
        all_image_keys = self._callbacks.normalize_keys()(local, provider)
        image_keys = self._callbacks.select_keys()(all_image_keys, provider)
        active_key_id = str(local.get("image_active_key_id") or "").strip()
        active_item = next((item for item in image_keys if item["id"] == active_key_id), None) or (image_keys[0] if image_keys else None)
        local_key = str(active_item.get("key") if active_item else "").strip()
        api_key = ""
        key_source = "missing"
        key_source_name = ""
        if local_key:
            api_key = local_key
            key_source = "env"
            key_source_name = str(active_item.get("env") or "local_secret_env") if active_item else "local_secret_env"
        elif direct_env_key:
            api_key = direct_env_key
            key_source = "env"
            key_source_name = self._environment.direct_key()
        elif named_env_key:
            api_key = named_env_key
            key_source = "env"
            key_source_name = key_env

        try:
            self._io.validate_base()(base_url)
            base_url_valid = True
        except self._io.http_error():
            base_url_valid = False
        configured = bool(provider in self._policy.supported() and base_url_valid and api_key and model)
        if provider not in self._policy.supported():
            status = "unsupported_provider"
            message = f"Unsupported image generation provider: {provider}"
        elif not base_url_valid:
            status = "invalid_base_url"
            message = "Image generation provider base_url is invalid."
        elif not model:
            status = "missing_model"
            message = "Image generation model is required."
        elif not api_key:
            status = "missing_api_key"
            message = f"Missing image generation API key ({key_env or self._environment.direct_key()})."
        else:
            status = "ready"
            message = f"{self._callbacks.label()(provider)} image generation is configured."
        return {
            "provider": provider,
            "provider_key": self._callbacks.provider_key()(provider),
            "provider_label": self._callbacks.label()(provider),
            "configured": configured,
            "enabled": configured,
            "model": model,
            "model_options": self._policy.models(),
            "base_url": self._presentation.public_base()(base_url),
            "timeout_seconds": timeout,
            "api_key_env": key_env or self._environment.direct_key(),
            "api_key_present": bool(api_key),
            "key_present": bool(api_key),
            "local_key_present": bool(local_key),
            "api_keys": self._presentation.public_keys()(all_image_keys),
            "active_key_id": active_item["id"] if active_item else "",
            "key_source": key_source,
            "key_source_name": key_source_name,
            "masked_key": self._presentation.mask_secret()(api_key),
            "api_key": api_key,
            "proxy_configured": bool(proxy_url),
            "proxy_url": self._presentation.mask_url()(proxy_url),
            "proxy_source_name": proxy_source_name,
            "proxy_auto_local": bool(proxy_auto_local),
            "proxy_url_raw": proxy_url,
            "status": status,
            "message": message,
        }
