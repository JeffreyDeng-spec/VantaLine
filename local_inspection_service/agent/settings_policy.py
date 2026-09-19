"""Explicit settings policy service without application imports."""
from typing import Any
from .settings_ports import AgentSettingsDefaults, AgentProviderPolicy, AgentSettingsKeys


class AgentSettingsPolicy:
    def __init__(self, defaults: AgentSettingsDefaults, provider: AgentProviderPolicy, keys: AgentSettingsKeys) -> None:
        self._defaults = defaults
        self._provider = provider
        self._keys = keys

    def agent_base_url_host(self, base_url: str) -> str:
        try:
            return (self._provider.split_url()(str(base_url or "").strip()).hostname or "").lower()
        except ValueError:
            return ""

    def is_cursor_base_url(self, base_url: str) -> bool:
        return self._provider.host()(base_url) == "api.cursor.com"

    def detect_agent_provider_from_base_url(self, base_url: str) -> str:
        return self._defaults.cursor() if self._provider.is_cursor()(base_url) else self._defaults.openai()

    def normalize_agent_provider(self, provider: str | None, base_url: str = "") -> str:
        if str(base_url or "").strip():
            return self._provider.detect()(base_url)
        value = str(provider or "").strip().lower()
        if value == self._defaults.cursor():
            return value
        return self._defaults.openai()

    def agent_provider_label(self, provider: str) -> str:
        return "Cursor" if str(provider or "").strip().lower() == self._defaults.cursor() else "OpenAI 兼容"

    def normalize_agent_model_options(self, value: Any) -> list[dict[str, str]]:
        options: list[dict[str, str]] = []
        seen: set[str] = set()
        raw_items = value if isinstance(value, list) else []
        for item in raw_items:
            if isinstance(item, str):
                model_id = item.strip()
                label = model_id
            elif isinstance(item, dict):
                model_id = str(item.get("id") or item.get("value") or "").strip()
                label = str(item.get("label") or item.get("name") or item.get("display_name") or model_id).strip()
            else:
                continue
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            options.append({"id": model_id, "label": label or model_id})
            if len(options) >= 250:
                break
        return options

    def agent_model_options_from_items(self, items: Any, *, prepend: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
        options: list[dict[str, str]] = []
        if prepend:
            options.extend(prepend)
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                model_id = str(item.get("id") or "").strip()
                if not model_id:
                    continue
                label_parts = [model_id]
                display_name = str(item.get("display_name") or item.get("name") or "").strip()
                if display_name and display_name != model_id:
                    label_parts.append(display_name)
                aliases = [str(alias).strip() for alias in item.get("aliases") or [] if str(alias).strip()]
                if aliases:
                    label_parts.append(f"alias: {', '.join(aliases[:3])}")
                options.append({"id": model_id, "label": " · ".join(label_parts)})
        return self._provider.options()(options)

    def normalize_agent_config(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = dict(self._defaults.config())
        provider_value = config.get("provider") if "provider" in config else None
        merged.update({key: config[key] for key in self._defaults.config() if key in config})
        merged["base_url"] = str(merged.get("base_url") or "").strip().rstrip("/")
        merged["api_key"] = str(merged.get("api_key") or "").strip()
        merged["provider"] = self._provider.normalize()(provider_value, merged["base_url"])
        merged["api_key_env"] = self._keys.validate_environment()(merged.get("api_key_env"))
        merged["api_keys"] = self._keys.normalize()(merged)
        active_key_id = str(merged.get("active_key_id") or "").strip()
        current_key_items = self._keys.for_provider()(merged["api_keys"], merged["provider"])
        if active_key_id and not any(item["id"] == active_key_id for item in current_key_items):
            active_key_id = ""
        merged["active_key_id"] = active_key_id or (current_key_items[0]["id"] if current_key_items else "")
        active_item = next((item for item in current_key_items if item["id"] == merged["active_key_id"]), None)
        active_key = str(active_item.get("key") if active_item else "").strip()
        fallback_env_key = self._keys.environment_value()(merged["api_key_env"]) if merged["api_key_env"] else ""
        if active_key:
            merged["api_key"] = active_key
        elif fallback_env_key:
            merged["api_key"] = fallback_env_key
        merged["model"] = str(merged.get("model") or "").strip()
        merged["model_options"] = self._provider.options()(merged.get("model_options"))
        if merged["provider"] == self._defaults.cursor():
            if not merged["base_url"]:
                merged["base_url"] = self._defaults.cursor_url()
            if not merged["model"]:
                merged["model"] = "auto"
        try:
            merged["timeout_seconds"] = max(5.0, min(300.0, float(merged.get("timeout_seconds") or 45.0)))
        except (TypeError, ValueError):
            merged["timeout_seconds"] = 45.0
        merged["enabled"] = bool(merged.get("enabled", True))
        merged["auto_advance_default"] = bool(merged.get("auto_advance_default", False))
        if str(merged.get("connection_status") or "") not in self._defaults.statuses():
            merged["connection_status"] = "untested"
        merged["connection_message"] = str(merged.get("connection_message") or "").strip()[:300]
        try:
            merged["last_tested_at"] = int(float(merged.get("last_tested_at") or 0))
        except (TypeError, ValueError):
            merged["last_tested_at"] = 0
        try:
            merged["last_model_count"] = max(0, int(merged.get("last_model_count") or 0))
        except (TypeError, ValueError):
            merged["last_model_count"] = 0
        return merged
