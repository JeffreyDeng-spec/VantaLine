"""Agent settings HTTP behavior with explicit dependencies and unchanged guards."""
from typing import Any
from ..schemas.configuration import AgentConfigRequest
from ..schemas.pipeline import AgentRecommendRequest
from .settings_api_ports import AgentSettingsHttpAccess, AgentSettingsProjectionCall, AgentRecommendationCall, AgentLegacySettingsPolicy, AgentLegacyKeyPolicy, AgentLegacySettingsEffects


class AgentSettingsApi:
    def __init__(self, access: AgentSettingsHttpAccess, projection: AgentSettingsProjectionCall, recommendation: AgentRecommendationCall, policy: AgentLegacySettingsPolicy, keys: AgentLegacyKeyPolicy, effects: AgentLegacySettingsEffects) -> None:
        self._access = access
        self._projection = projection
        self._recommendation = recommendation
        self._policy = policy
        self._keys = keys
        self._effects = effects

    def get_agent_config(self) -> dict[str, Any]:
        self._access.admin()()
        return self._projection.public()()

    def update_agent_config(self, request: AgentConfigRequest) -> dict[str, Any]:
        self._access.admin()()
        raise self._access.http_error()(409, "请使用模型与 API 配置库；旧配置入口已停用")
        config = self._policy.load()()
        reset_connection = False
        clear_model_options = False
        if request.enabled is not None:
            reset_connection = reset_connection or config["enabled"] != bool(request.enabled)
            config["enabled"] = bool(request.enabled)
        if request.provider is not None:
            provider = str(request.provider or "").strip().lower()
            if provider not in self._policy.supported():
                raise self._access.http_error()(status_code=400, detail="Unsupported Agent provider")
            clear_model_options = clear_model_options or config["provider"] != provider
            reset_connection = reset_connection or config["provider"] != provider
            config["provider"] = provider
        if request.base_url is not None:
            base_url = request.base_url.strip().rstrip("/")
            clear_model_options = clear_model_options or config["base_url"] != base_url
            reset_connection = reset_connection or config["base_url"] != base_url
            config["base_url"] = base_url
        if request.api_key_env is not None:
            config["api_key_env"] = self._keys.validate()(request.api_key_env)
        if request.api_key is not None and request.api_key.strip():
            api_key = request.api_key.strip()
            key_provider = self._policy.provider()(config.get("provider"), str(config.get("base_url") or ""))
            env_name = self._keys.validate()(request.api_key_env) or self._keys.name()("VANTALINE_AGENT_KEY", api_key, provider=key_provider)
            self._effects.secret()(env_name, api_key)
            key_items = self._keys.normalize()(config)
            item_id = self._keys.identity()(env_name, api_key)
            existing = next((item for item in key_items if item["id"] == item_id and item.get("provider") == key_provider), None)
            if existing:
                existing["key"] = api_key
                existing["env"] = env_name
                existing["provider"] = key_provider
            else:
                key_items.append(
                    {
                        "id": item_id,
                        "label": f"{self._policy.label()(key_provider)} API Key",
                        "key": api_key,
                        "env": env_name,
                        "provider": key_provider,
                    }
                )
            config["api_keys"] = key_items
            config["active_key_id"] = item_id
            clear_model_options = clear_model_options or config["api_key"] != api_key
            reset_connection = reset_connection or config["api_key"] != api_key
            config["api_key"] = api_key
        if request.active_key_id is not None:
            active_key_id = request.active_key_id.strip()
            key_provider = self._policy.provider()(config.get("provider"), str(config.get("base_url") or ""))
            current_keys = self._keys.for_provider()(self._keys.normalize()(config), key_provider)
            if active_key_id and not any(item["id"] == active_key_id for item in current_keys):
                raise self._access.http_error()(status_code=400, detail="Agent active_key_id was not found")
            config["active_key_id"] = active_key_id
            selected = next((item for item in current_keys if item["id"] == active_key_id), None)
            if selected and selected.get("key") and config.get("api_key") != selected["key"]:
                clear_model_options = True
                reset_connection = True
                config["api_key"] = selected["key"]
        if request.model is not None:
            model = request.model.strip()
            reset_connection = reset_connection or config["model"] != model
            config["model"] = model
        if request.timeout_seconds is not None:
            timeout_seconds = max(5.0, min(300.0, float(request.timeout_seconds)))
            reset_connection = reset_connection or config["timeout_seconds"] != timeout_seconds
            config["timeout_seconds"] = timeout_seconds
        if request.auto_advance_default is not None:
            config["auto_advance_default"] = bool(request.auto_advance_default)
        if request.provider is None:
            config.pop("provider", None)
        config = self._policy.normalize()(config)
        if reset_connection:
            config["connection_status"] = "untested"
            config["connection_message"] = "已保存，尚未测试。"
            config["last_tested_at"] = 0
            config["last_model_count"] = 0
            if clear_model_options:
                config["model_options"] = []
        self._effects.save()(config)
        return self._projection.public()(config)

    def test_agent_config(self) -> dict[str, Any]:
        self._access.admin()()
        raise self._access.http_error()(409, "请使用模型与 API 配置库；旧配置入口已停用")
        config = self._policy.load()()
        if not self._policy.credentials()(config):
            provider_label = "Cursor" if self._policy.provider()(config.get("provider"), config.get("base_url", "")) == self._policy.cursor() else "OpenAI 兼容"
            message = f"Agent API 未配置完整。当前识别为 {provider_label}；测试连接需要 Base URL / API Key。"
            config["connection_status"] = "failed"
            config["connection_message"] = message
            config["last_tested_at"] = int(self._effects.now()())
            self._effects.save()(config)
            return {**self._projection.public()(config), "ok": False, "message": message}
        try:
            result = self._effects.test()(config)
            if result.get("model"):
                config["model"] = str(result["model"]).strip()
            config["model_options"] = self._policy.options()(result.get("model_options") or [])
            config["connection_status"] = "connected"
            config["connection_message"] = str(result.get("message") or "连接成功。")[:300]
            config["last_tested_at"] = int(self._effects.now()())
            config["last_model_count"] = int(result.get("last_model_count") or len(config["model_options"]) or 0)
            self._effects.save()(config)
            return {**self._projection.public()(config), "ok": True, "message": config["connection_message"]}
        except Exception as exc:  # noqa: BLE001
            message = f"连接失败:{str(exc)[:200]}"
            config["connection_status"] = "failed"
            config["connection_message"] = message
            config["last_tested_at"] = int(self._effects.now()())
            self._effects.save()(config)
            return {**self._projection.public()(config), "ok": False, "message": message}

    def agent_recommend(self, request: AgentRecommendRequest) -> dict[str, Any]:
        stage = request.stage if request.stage in {"samples", "training"} else "samples"
        return self._recommendation.recommend()(stage, request.accessory_ids, request.sample_count)
