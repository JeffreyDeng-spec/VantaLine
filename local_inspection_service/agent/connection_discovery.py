"""Explicit connection discovery service without application imports."""
from typing import Any
import urllib.error
from .invocation_ports import AgentInvocationSettings, AgentHttpIO, AgentInvocationCodec, AgentModelCalls


class AgentConnectionDiscovery:
    def __init__(self, settings: AgentInvocationSettings, http: AgentHttpIO, codec: AgentInvocationCodec, models: AgentModelCalls) -> None:
        self._settings = settings
        self._http = http
        self._codec = codec
        self._models = models

    def fetch_openai_compatible_model_options(self, config: dict[str, Any]) -> list[dict[str, str]]:
        request = self._http.request()(
            self._models.models_url()(config["base_url"]),
            headers={"Authorization": f"Bearer {config['api_key']}"},
            method="GET",
        )
        with self._http.open()(request, timeout=config["timeout_seconds"]) as response:
            body = self._codec.loads()(response.read().decode("utf-8"))
        items = body.get("data") if isinstance(body, dict) else []
        return self._models.options()(items)

    def test_cursor_agent_connection(self, config: dict[str, Any]) -> dict[str, Any]:
        request = self._http.request()(
            self._models.cursor_url()(config["base_url"], "/v1/models"),
            headers=self._models.auth_headers()(config["api_key"]),
            method="GET",
        )
        try:
            with self._http.open()(request, timeout=config["timeout_seconds"]) as response:
                body = self._codec.loads()(response.read().decode("utf-8"))
        except self._http.http_error() as exc:
            raise RuntimeError(self._http.error_message()("Cursor API 请求失败", exc)) from exc
        except self._http.url_error() as exc:
            raise RuntimeError(f"Cursor API 请求失败:{self._http.text()(exc, 180)}") from exc
        items = body.get("items") if isinstance(body, dict) else []
        models = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
        model_options = self._models.options()(models, prepend=[{"id": "auto", "label": "auto · Cursor 默认模型"}])
        model = str(config.get("model") or "auto").strip() or "auto"
        available = self._models.available()(model, models)
        if model.lower() in {"auto", "default"}:
            model_message = "auto 将使用 Cursor 默认模型"
        elif available:
            model_message = f"模型 {model} 在 Cursor 模型列表中"
        else:
            model_message = f"模型 {model} 未出现在 Cursor 模型列表中，已切换为 auto"
            model = "auto"
        return {
            "message": f"Cursor 连接成功，可用模型 {len(models)} 个；{model_message}。",
            "last_model_count": len(models),
            "model": model,
            "model_options": model_options,
            "model_available": available,
        }

    def test_openai_agent_connection(self, config: dict[str, Any]) -> dict[str, Any]:
        model_options: list[dict[str, str]] = []
        models_warning = ""
        try:
            model_options = self._models.fetch()(config)
        except self._http.http_error() as exc:
            models_warning = self._http.error_message()("模型列表获取失败", exc)
        except self._http.url_error() as exc:
            models_warning = f"模型列表获取失败:{self._http.text()(exc, 180)}"
        selected_model = str(config.get("model") or "").strip()
        if not selected_model and model_options:
            selected_model = model_options[0]["id"]
        if not selected_model:
            if models_warning:
                raise RuntimeError(f"{models_warning}；且 Model 为空，无法测试 /chat/completions。")
            raise RuntimeError("未获取到可用模型，且 Model 为空，无法测试 /chat/completions。")
        test_config = {**config, "model": selected_model}
        content = self._models.legacy_chat()(
            [{"role": "user", "content": "回复 ok"}],
            test_config,
            require_connected=False,
        )
        suffix = f"；{models_warning}" if models_warning else ""
        return {
            "message": f"连接成功，模型 {selected_model} 已响应:{content[:60]}{suffix}",
            "last_model_count": len(model_options),
            "model": selected_model,
            "model_options": model_options,
        }

    def test_agent_connection(self, config: dict[str, Any]) -> dict[str, Any]:
        provider = self._settings.normalize_provider()(config.get("provider"), config.get("base_url", ""))
        if provider == self._settings.cursor_provider():
            return self._models.cursor_test()(config)
        return self._models.openai_test()(config)
