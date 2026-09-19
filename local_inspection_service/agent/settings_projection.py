"""Explicit settings projection service without application imports."""
from typing import Any
from .settings_ports import AgentSettingsDefaults, AgentProviderPolicy, AgentSettingsAccess, AgentSettingsAuthorization, AgentSettingsKeys, AgentSettingsPresentation


class AgentSettingsProjection:
    def __init__(self, defaults: AgentSettingsDefaults, provider: AgentProviderPolicy, access: AgentSettingsAccess, auth: AgentSettingsAuthorization, keys: AgentSettingsKeys, presentation: AgentSettingsPresentation) -> None:
        self._defaults = defaults
        self._provider = provider
        self._access = access
        self._auth = auth
        self._keys = keys
        self._presentation = presentation

    def agent_required_fields_present(self, config: dict[str, Any]) -> bool:
        if not bool(config.get("enabled", True)):
            return False
        provider = self._provider.normalize()(config.get("provider"), str(config.get("base_url") or ""))
        if provider == self._defaults.cursor():
            return bool(config.get("base_url") and config.get("api_key"))
        return bool(config.get("base_url") and config.get("api_key") and config.get("model"))

    def agent_credentials_present(self, config: dict[str, Any]) -> bool:
        if not bool(config.get("enabled", True)):
            return False
        return bool(config.get("base_url") and config.get("api_key"))

    def agent_connected(self, config: dict[str, Any]) -> bool:
        return self._access.required()(config) and str(config.get("connection_status") or "") == "connected"

    def agent_recommendation_supported(self, config: dict[str, Any]) -> bool:
        return self._provider.normalize()(config.get("provider"), str(config.get("base_url") or "")) == self._defaults.openai() and self._access.connected()(config)

    def agent_configured(self, config: dict[str, Any] | None = None) -> bool:
        config = config or self._access.load()()
        return self._access.required()(config)

    def public_agent_config(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        config = config or self._access.load()()
        configured = self._access.credentials()(config)
        recommendation_supported = self._access.recommendation()(config)
        if not self._auth.is_admin()(self._auth.current_user()()):
            return {"enabled":bool(config.get("enabled")), "configured":configured,
                    "connection_status":config.get("connection_status","untested") if configured else "untested",
                    "recommendation_supported":recommendation_supported,
                    "auto_advance_default":bool(config.get("auto_advance_default")),
                    "mode":"agent" if recommendation_supported else "rules"}
        key_items = self._keys.normalize()(config)
        current_key_items = self._keys.for_provider()(key_items, config["provider"])
        active_key_id = str(config.get("active_key_id") or "").strip()
        active_item = next((item for item in current_key_items if item["id"] == active_key_id), None) or (current_key_items[0] if current_key_items else None)
        return {
            "enabled": config["enabled"],
            "provider": config["provider"],
            "provider_label": self._presentation.provider_label()(config["provider"]),
            "base_url": config["base_url"],
            "model": config["model"],
            "model_options": config["model_options"],
            "timeout_seconds": config["timeout_seconds"],
            "auto_advance_default": config["auto_advance_default"],
            "api_key_env": config.get("api_key_env") or "VANTALINE_AGENT_API_KEY",
            "api_keys": self._presentation.public_keys()(key_items),
            "active_key_id": active_item["id"] if active_item else "",
            "api_key_masked": self._presentation.mask()(config["api_key"]),
            "has_api_key": bool(config["api_key"]),
            "configured": configured,
            "connection_status": config["connection_status"] if configured else "untested",
            "connection_message": config["connection_message"] if configured else "",
            "last_tested_at": config["last_tested_at"] if configured else 0,
            "last_model_count": config["last_model_count"] if configured else 0,
            "recommendation_supported": recommendation_supported,
            "mode": "agent" if recommendation_supported else "rules",
        }
