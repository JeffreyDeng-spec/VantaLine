"""Legacy settings used by profile migration, without application imports."""
from typing import Any
from .legacy_settings_ports import LegacySettingsIO, LegacyPresentation, LegacyJsonPolicy, LegacyJsonCallbacks

class LegacyJsonSettings:
    def __init__(self, io: LegacySettingsIO, presentation: LegacyPresentation, policy: LegacyJsonPolicy, callbacks: LegacyJsonCallbacks) -> None:
        self._io = io
        self._presentation = presentation
        self._policy = policy
        self._callbacks = callbacks

    def _legacy_ai_detection_settings(self) -> dict[str, Any]:
        local = self._io.load()()
        provider = self._io.environment().get("INSPECTION_AI_PROVIDER", "").strip().lower() or str(local.get("provider") or self._policy.provider()).strip().lower()
        model = self._io.environment().get("INSPECTION_AI_MODEL", "").strip() or str(local.get("model") or self._policy.model()).strip() or self._policy.model()
        base_url = self._io.environment().get("INSPECTION_AI_BASE_URL", "").strip() or str(local.get("base_url") or self._callbacks.default_base()(provider)).strip() or self._callbacks.default_base()(provider)
        proxy_url, proxy_source_name, proxy_auto_local = self._io.proxy()(local, provider)
        timeout_raw = self._io.environment().get("INSPECTION_AI_TIMEOUT_SECONDS", "").strip() or local.get("timeout_seconds", self._policy.timeout())
        try:
            timeout = self._callbacks.validate_timeout()(timeout_raw)
        except self._io.http_error():
            timeout = self._policy.timeout()
        key_env = self._io.environment().get("INSPECTION_AI_API_KEY_ENV", "").strip() or str(local.get("api_key_env") or "").strip()
        if not key_env and provider == "gemini":
            key_env = "GEMINI_API_KEY"
        elif not key_env and provider == "qwen":
            key_env = "DASHSCOPE_API_KEY"

        direct_env_key = self._io.environment().get("INSPECTION_AI_API_KEY", "").strip()
        named_env_key = self._io.environment().get(key_env, "").strip() if key_env else ""
        all_local_keys = self._callbacks.normalize_keys()(local, provider)
        local_keys = self._callbacks.select_keys()(all_local_keys, provider)
        active_key_id = str(local.get("active_key_id") or "").strip()
        active_item = next((item for item in local_keys if item["id"] == active_key_id), None) or (local_keys[0] if local_keys else None)
        local_key = str(active_item.get("key") if active_item else "").strip()
        api_key = ""
        key_source = "missing"
        key_source_name = ""
        if direct_env_key:
            api_key = direct_env_key
            key_source = "env"
            key_source_name = "INSPECTION_AI_API_KEY"
        elif named_env_key:
            api_key = named_env_key
            key_source = "env"
            key_source_name = key_env
        elif local_key:
            api_key = local_key
            key_source = "env"
            key_source_name = str(active_item.get("env") or "local_secret_env") if active_item else "local_secret_env"
        key_candidates: list[dict[str, str]] = []
        seen_candidate_keys: set[str] = set()

        def add_key_candidate(candidate: dict[str, Any]) -> None:
            key_value = str(candidate.get("key") or "").strip()
            if not key_value or key_value in seen_candidate_keys:
                return
            seen_candidate_keys.add(key_value)
            key_candidates.append(
                {
                    "id": str(candidate.get("id") or self._callbacks.key_id()(candidate.get("env") or "", key_value)),
                    "label": self._callbacks.text()(candidate.get("label") or "AI API Key", 80),
                    "env": str(candidate.get("env") or ""),
                    "provider": provider,
                    "key": key_value,
                }
            )

        for item in local_keys:
            add_key_candidate(item)
        if direct_env_key:
            add_key_candidate(
                {
                    "id": self._callbacks.key_id()("INSPECTION_AI_API_KEY", direct_env_key),
                    "label": "INSPECTION_AI_API_KEY",
                    "env": "INSPECTION_AI_API_KEY",
                    "key": direct_env_key,
                }
            )
        if named_env_key and key_env:
            add_key_candidate(
                {
                    "id": self._callbacks.key_id()(key_env, named_env_key),
                    "label": key_env,
                    "env": key_env,
                    "key": named_env_key,
                }
            )
        key_candidates.sort(key=lambda item: 0 if item["key"] == api_key else 1)

        supported = provider in self._policy.supported()
        try:
            self._io.validate_base()(base_url)
            base_url_valid = True
        except self._io.http_error():
            base_url_valid = False
        configured = bool(supported and base_url_valid and api_key)
        if not supported:
            status = "unsupported_provider"
            message = f"Unsupported INSPECTION_AI_PROVIDER: {provider}"
        elif not base_url_valid:
            status = "invalid_base_url"
            message = "AI provider base_url is invalid."
        elif not api_key:
            status = "missing_api_key"
            message = f"Missing AI provider API key ({key_env or 'INSPECTION_AI_API_KEY'})."
        else:
            status = "ready"
            message = "AI provider is configured."
        return {
            "enabled": configured,
            "configured": configured,
            "provider": provider,
            "provider_label": self._callbacks.label()(provider),
            "model": model,
            "model_options": self._policy.models(),
            "timeout_seconds": timeout,
            "api_key_env": key_env or "INSPECTION_AI_API_KEY",
            "api_key_present": bool(api_key),
            "key_present": bool(api_key),
            "local_key_present": bool(local_key),
            "api_keys": self._presentation.public_keys()(all_local_keys),
            "active_key_id": active_item["id"] if active_item else "",
            "api_key_candidates": key_candidates,
            "key_source": key_source,
            "key_source_name": key_source_name,
            "masked_key": self._presentation.mask_secret()(api_key),
            "api_key": api_key,
            "base_url": self._presentation.public_base()(base_url),
            "proxy_configured": bool(proxy_url),
            "proxy_url": self._presentation.mask_url()(proxy_url),
            "proxy_source_name": proxy_source_name,
            "proxy_auto_local": bool(proxy_auto_local),
            "auto_local_proxy_enabled": bool(local.get("auto_local_proxy", True)) and self._callbacks.flag()(self._policy.proxy_flag(), True),
            "proxy_url_raw": proxy_url,
            "status": status,
            "message": message,
        }
