"""Explicit chat transport service without application imports."""
from typing import Any
import urllib.error
from .invocation_ports import AgentInvocationSettings, AgentHttpIO, AgentInvocationCodec, AgentChatCalls


class AgentChatTransport:
    def __init__(self, settings: AgentInvocationSettings, http: AgentHttpIO, codec: AgentInvocationCodec, calls: AgentChatCalls) -> None:
        self._settings = settings
        self._http = http
        self._codec = codec
        self._calls = calls

    def agent_http_error_message(self, prefix: str, exc: urllib.error.HTTPError) -> str:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        return f"{prefix}: HTTP {exc.code} {self._http.text()(detail, 180)}"

    def agent_openai_chat_completion(self,
        messages: list[dict[str, str]],
        config: dict[str, Any] | None = None,
        *,
        require_connected: bool = True,
    ) -> str:
        config = config or self._settings.load()()
        if self._settings.normalize_provider()(config.get("provider"), config.get("base_url", "")) != self._settings.openai_provider():
            raise RuntimeError("当前 Agent Base URL 识别为非 OpenAI 兼容接口")
        if self._settings.is_cursor_url()(config.get("base_url", "")):
            raise RuntimeError("检测到 Cursor Base URL；Cursor API 不是 Chat Completions 接口")
        if not self._settings.required()(config):
            raise RuntimeError("Agent API is not configured")
        if require_connected and not self._settings.connected()(config):
            raise RuntimeError("Agent API 已配置但尚未测试成功")
        payload = {
            "model": config["model"],
            "messages": messages,
            "temperature": 0.2,
        }
        request = self._http.request()(
            self._calls.chat_url()(config["base_url"]),
            data=self._codec.dumps()(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config['api_key']}",
            },
            method="POST",
        )
        try:
            with self._http.open()(request, timeout=config["timeout_seconds"]) as response:
                body = self._codec.loads()(response.read().decode("utf-8"))
        except self._http.http_error() as exc:
            raise RuntimeError(self._http.error_message()("Agent API 请求失败", exc)) from exc
        except self._http.url_error() as exc:
            raise RuntimeError(f"Agent API 请求失败:{self._http.text()(exc, 180)}") from exc
        content = (((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("Agent API returned an empty response")
        return content

    def agent_chat_completion(self, messages: list[dict[str, str]], config: dict[str, Any] | None = None) -> str:
        config = config or self._settings.load()()
        if self._settings.normalize_provider()(config.get("provider"), config.get("base_url", "")) == self._settings.cursor_provider():
            raise RuntimeError(self._settings.cursor_message())
        if config.get("profile_id"):
            if not self._settings.connected()(config):
                raise RuntimeError("Training assistant connection is not verified")
            settings = dict(config)
            if settings["provider"] == "openai_compatible":
                settings["base_url"] = self._calls.chat_url()(settings["base_url"])
            system = "\n".join(m["content"] for m in messages if m["role"] == "system")
            content = [{"type":"text", "text":m["content"]} for m in messages if m["role"] != "system"]
            result, _, _ = self._calls.generate()(settings, system, content, max_tokens=1400, max_attempts=1)
            return self._codec.dumps()(result, ensure_ascii=False)
        return self._calls.legacy_chat()(messages, config, require_connected=True)
