"""Explicit protocol policy service without application imports."""
from typing import Any
import urllib.error
from .invocation_ports import AgentProtocolRuntime


class AgentProtocolPolicy:
    def __init__(self, runtime: AgentProtocolRuntime) -> None:
        self._runtime = runtime

    def openai_compatible_chat_url(self, base_url: str) -> str:
        normalized = str(base_url or "").strip().rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    def openai_compatible_models_url(self, base_url: str) -> str:
        normalized = str(base_url or "").strip().rstrip("/")
        if normalized.endswith("/chat/completions"):
            normalized = normalized[: -len("/chat/completions")]
        return f"{normalized}/models"

    def cursor_auth_headers(self, api_key: str) -> dict[str, str]:
        token = self._runtime.base64_encode()(f"{api_key}:".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    def cursor_api_url(self, base_url: str, path: str) -> str:
        normalized = str(base_url or self._runtime.cursor_base_url()).strip().rstrip("/")
        return f"{normalized}/{path.lstrip('/')}"

    def cursor_model_available(self, model: str, items: list[dict[str, Any]]) -> bool:
        selected = str(model or "").strip().lower()
        if not selected or selected in {"auto", "default"}:
            return True
        for item in items:
            ids = [str(item.get("id") or "").lower()]
            ids.extend(str(alias or "").lower() for alias in item.get("aliases") or [])
            if selected in ids:
                return True
        return False
