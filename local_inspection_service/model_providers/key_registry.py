"""Provider key normalization and public projection without application imports."""
from typing import Any
from .key_registry_ports import KeyMaterial, KeyPresentation, JsonKeyPolicy, ImageKeyPolicy, AgentKeyPolicy


class ProviderKeyRegistry:
    def __init__(self, material: KeyMaterial, presentation: KeyPresentation, json: JsonKeyPolicy, image: ImageKeyPolicy, agent: AgentKeyPolicy) -> None:
        self._material = material
        self._presentation = presentation
        self._json = json
        self._image = image
        self._agent = agent

    def normalize_ai_key_items(self, config: dict[str, Any], provider: str | None = None) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        fallback_provider = str(provider or config.get("provider") or self._json.default_provider()).strip().lower()
        if fallback_provider not in self._json.supported():
            fallback_provider = self._json.default_provider()
        raw_items = config.get("api_keys") if isinstance(config.get("api_keys"), list) else []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            env_name = str(raw.get("env") or raw.get("env_name") or raw.get("api_key_env") or "").strip()
            env_secret = self._material.environment()(env_name)
            secret = env_secret or str(raw.get("key") or raw.get("api_key") or "").strip()
            if not secret and not env_name:
                continue
            raw_provider = str(raw.get("provider") or raw.get("ai_provider") or "").strip().lower()
            item_provider = raw_provider or fallback_provider
            if item_provider not in self._json.supported():
                if raw_provider:
                    continue
                item_provider = fallback_provider
            item_id = str(raw.get("id") or self._material.identity()(env_name, secret)).strip()
            dedupe_key = f"{item_provider}:{item_id}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            label = self._presentation.text()(raw.get("label") or f"{self._presentation.json_label()(item_provider)} API Key {len(items) + 1}", 80)
            items.append({"id": item_id, "label": label, "key": secret, "env": env_name, "provider": item_provider})
        legacy_key = str(config.get("api_key") or "").strip()
        if legacy_key:
            env_name = self._material.default_environment()("VANTALINE_AI_KEY", legacy_key, provider=fallback_provider)
            item_id = self._material.identity()(env_name, legacy_key)
            dedupe_key = f"{fallback_provider}:{item_id}"
            if dedupe_key not in seen:
                items.append(
                    {
                        "id": item_id,
                        "label": f"{self._presentation.json_label()(fallback_provider)} API Key {len(items) + 1}",
                        "key": legacy_key,
                        "env": env_name,
                        "provider": fallback_provider,
                    }
                )
        return items

    def public_ai_key_items(self, items: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            {
                "id": item["id"],
                "label": item.get("label") or f"API Key {idx + 1}",
                "masked_key": self._presentation.mask()(item.get("key", "")),
                "env_name": item.get("env") or item.get("env_name") or "",
                "provider": item.get("provider") or "",
            }
            for idx, item in enumerate(items)
        ]

    def ai_keys_for_provider(self, items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
        clean_provider = str(provider or "").strip().lower()
        return [item for item in items if str(item.get("provider") or "").strip().lower() == clean_provider]

    def normalize_image_key_items(self, config: dict[str, Any], provider: str) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        fallback_provider = self._image.validate()(provider or self._image.default_provider())
        raw_items = config.get("image_api_keys") if isinstance(config.get("image_api_keys"), list) else []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            env_name = str(raw.get("env") or raw.get("env_name") or raw.get("api_key_env") or "").strip()
            env_secret = self._material.environment()(env_name)
            secret = env_secret or str(raw.get("key") or raw.get("api_key") or "").strip()
            if not secret and not env_name:
                continue
            item_provider = str(raw.get("provider") or raw.get("image_provider") or fallback_provider).strip().lower()
            if item_provider not in self._image.supported():
                item_provider = fallback_provider
            item_id = str(raw.get("id") or self._material.identity()(env_name, secret)).strip()
            dedupe_key = f"{item_provider}:{item_id}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            label = self._presentation.text()(raw.get("label") or f"{self._presentation.image_label()(item_provider)} API Key {len(items) + 1}", 80)
            items.append({"id": item_id, "label": label, "key": secret, "provider": item_provider, "env": env_name})
        legacy_key = str(config.get("image_api_key") or "").strip()
        if legacy_key:
            env_name = self._material.default_environment()(f"VANTALINE_{fallback_provider.upper()}_IMAGE_KEY", legacy_key)
            item_id = self._material.identity()(env_name, legacy_key)
            dedupe_key = f"{fallback_provider}:{item_id}"
            if dedupe_key not in seen:
                items.append(
                    {
                        "id": item_id,
                        "label": f"{self._presentation.image_label()(fallback_provider)} API Key {len(items) + 1}",
                        "key": legacy_key,
                        "provider": fallback_provider,
                        "env": env_name,
                    }
                )
        return items

    def normalize_agent_key_items(self, config: dict[str, Any]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        fallback_provider = self._agent.normalize()(config.get("provider"), str(config.get("base_url") or ""))
        raw_items = config.get("api_keys") if isinstance(config.get("api_keys"), list) else []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            secret = str(raw.get("key") or raw.get("api_key") or "").strip()
            env_name = str(raw.get("env") or raw.get("env_name") or raw.get("api_key_env") or "").strip()
            env_secret = self._material.environment()(env_name)
            if env_secret:
                secret = env_secret
            if not secret and not env_name:
                continue
            item_provider = str(raw.get("provider") or raw.get("agent_provider") or fallback_provider).strip().lower()
            if item_provider not in self._agent.supported():
                item_provider = fallback_provider
            if secret and (not env_name or env_name.startswith("VANTALINE_AI_KEY_")):
                env_name = self._material.default_environment()("VANTALINE_AGENT_KEY", secret, provider=item_provider)
            item_id = str(raw.get("id") or self._material.identity()(env_name, secret)).strip()
            dedupe_key = f"{item_provider}:{item_id}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            label = self._presentation.text()(raw.get("label") or f"{self._presentation.agent_label()(item_provider)} API Key {len(normalized) + 1}", 80)
            if label.startswith("API Key"):
                label = f"Agent {label}"
            normalized.append(
                {
                    "id": item_id,
                    "label": label,
                    "key": secret,
                    "env": env_name,
                    "provider": item_provider,
                }
            )
        legacy_key = str(config.get("api_key") or "").strip()
        if legacy_key:
            env_name = self._material.default_environment()("VANTALINE_AGENT_KEY", legacy_key, provider=fallback_provider)
            item_id = self._material.identity()(env_name, legacy_key)
            dedupe_key = f"{fallback_provider}:{item_id}"
            if dedupe_key not in seen:
                normalized.append(
                    {
                        "id": item_id,
                        "label": f"{self._presentation.agent_label()(fallback_provider)} API Key {len(normalized) + 1}",
                        "key": legacy_key,
                        "env": env_name,
                        "provider": fallback_provider,
                    }
                )
        return normalized

    def image_keys_for_provider(self, items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
        clean_provider = str(provider or "").strip().lower()
        return [item for item in items if str(item.get("provider") or "").strip().lower() == clean_provider]

    def agent_keys_for_provider(self, items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
        clean_provider = str(provider or "").strip().lower()
        return [item for item in items if str(item.get("provider") or "").strip().lower() == clean_provider]
