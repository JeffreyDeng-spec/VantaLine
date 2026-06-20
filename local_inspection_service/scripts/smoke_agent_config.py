#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service import server as server_module


class FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class UrlopenRecorder:
    def __init__(self, payload: dict[str, object] | list[dict[str, object]] | None = None, exc: Exception | None = None):
        self.payloads = payload if isinstance(payload, list) else [payload or {}]
        self.exc = exc
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: object, timeout: float | None = None) -> FakeResponse:
        index = len(self.requests)
        self.requests.append(
            {
                "url": getattr(request, "full_url", ""),
                "method": request.get_method(),
                "headers": dict(request.header_items()),
                "timeout": timeout,
            }
        )
        if self.exc:
            raise self.exc
        return FakeResponse(self.payloads[min(index, len(self.payloads) - 1)])


def with_urlopen(recorder: UrlopenRecorder, fn) -> object:
    original = server_module.urllib.request.urlopen
    server_module.urllib.request.urlopen = recorder
    try:
        return fn()
    finally:
        server_module.urllib.request.urlopen = original


def test_openai_compatible_url() -> None:
    recorder = UrlopenRecorder({"choices": [{"message": {"content": "ok"}}]})
    config = {
        "enabled": True,
        "provider": "openai_compatible",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "model": "gpt-test",
        "timeout_seconds": 12,
        "connection_status": "untested",
    }

    result = with_urlopen(
        recorder,
        lambda: server_module.agent_openai_chat_completion(
            [{"role": "user", "content": "ping"}],
            config,
            require_connected=False,
        ),
    )

    assert result == "ok"
    assert recorder.requests[0]["url"] == "https://api.example.com/v1/chat/completions"
    assert recorder.requests[0]["method"] == "POST"


def test_cursor_models_endpoint() -> None:
    recorder = UrlopenRecorder({"items": [{"id": "default", "aliases": ["composer"]}]})
    config = server_module.normalize_agent_config(
        {
            "enabled": True,
            "base_url": "https://api.cursor.com",
            "api_key": "crsr-test",
            "model": "auto",
            "timeout_seconds": 12,
        }
    )

    result = with_urlopen(recorder, lambda: server_module.test_cursor_agent_connection(config))

    request = recorder.requests[0]
    assert request["url"] == "https://api.cursor.com/v1/models"
    assert request["method"] == "GET"
    assert "/chat/completions" not in str(request["url"])
    assert str(request["headers"].get("Authorization", "")).startswith("Basic ")
    assert result["last_model_count"] == 1
    assert [item["id"] for item in result["model_options"]] == ["auto", "default"]


def test_openai_models_endpoint_selects_default_model() -> None:
    recorder = UrlopenRecorder(
        [
            {"data": [{"id": "gpt-default"}, {"id": "gpt-large"}]},
            {"choices": [{"message": {"content": "ok"}}]},
        ]
    )
    config = server_module.normalize_agent_config(
        {
            "enabled": True,
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "model": "",
            "timeout_seconds": 12,
        }
    )

    result = with_urlopen(recorder, lambda: server_module.test_openai_agent_connection(config))

    assert recorder.requests[0]["url"] == "https://api.example.com/v1/models"
    assert recorder.requests[0]["method"] == "GET"
    assert recorder.requests[1]["url"] == "https://api.example.com/v1/chat/completions"
    assert recorder.requests[1]["method"] == "POST"
    assert result["model"] == "gpt-default"
    assert [item["id"] for item in result["model_options"]] == ["gpt-default", "gpt-large"]


def test_failed_connection_is_not_connected() -> None:
    with tempfile.TemporaryDirectory() as tmp_raw:
        original_path = server_module.AGENT_LOCAL_CONFIG_PATH
        server_module.AGENT_LOCAL_CONFIG_PATH = Path(tmp_raw) / "agent_config.local.json"
        try:
            server_module.save_agent_config(
                {
                    "enabled": True,
                    "provider": "cursor",
                    "base_url": "https://api.cursor.com",
                    "api_key": "crsr-test",
                    "model": "auto",
                    "timeout_seconds": 12,
                    "connection_status": "untested",
                }
            )
            recorder = UrlopenRecorder(exc=URLError("offline"))
            result = with_urlopen(recorder, server_module.test_agent_config)
            saved = server_module.load_agent_config()
        finally:
            server_module.AGENT_LOCAL_CONFIG_PATH = original_path

    assert result["ok"] is False
    assert result["connection_status"] == "failed"
    assert result["mode"] == "rules"
    assert saved["connection_status"] == "failed"


def test_save_resets_connection_status() -> None:
    with tempfile.TemporaryDirectory() as tmp_raw:
        original_path = server_module.AGENT_LOCAL_CONFIG_PATH
        server_module.AGENT_LOCAL_CONFIG_PATH = Path(tmp_raw) / "agent_config.local.json"
        try:
            server_module.save_agent_config(
                {
                    "enabled": True,
                    "provider": "cursor",
                    "base_url": "https://api.cursor.com",
                    "api_key": "crsr-test",
                    "model": "auto",
                    "timeout_seconds": 12,
                    "connection_status": "connected",
                    "connection_message": "connected",
                    "last_tested_at": 123,
                    "last_model_count": 1,
                }
            )
            result = server_module.update_agent_config(
                server_module.AgentConfigRequest(
                    base_url="https://api.cursor.com",
                    model="composer-2",
                    timeout_seconds=12,
                )
            )
            saved = server_module.load_agent_config()
        finally:
            server_module.AGENT_LOCAL_CONFIG_PATH = original_path

    assert result["connection_status"] == "untested"
    assert result["mode"] == "rules"
    assert saved["connection_status"] == "untested"
    assert saved["last_tested_at"] == 0


def test_base_url_overrides_stale_provider() -> None:
    with tempfile.TemporaryDirectory() as tmp_raw:
        original_path = server_module.AGENT_LOCAL_CONFIG_PATH
        server_module.AGENT_LOCAL_CONFIG_PATH = Path(tmp_raw) / "agent_config.local.json"
        try:
            server_module.save_agent_config(
                {
                    "enabled": True,
                    "provider": "cursor",
                    "base_url": "https://api.cursor.com",
                    "api_key": "crsr-test",
                    "model": "auto",
                    "timeout_seconds": 12,
                    "connection_status": "connected",
                }
            )
            result = server_module.update_agent_config(
                server_module.AgentConfigRequest(
                    base_url="https://api.openai.com/v1",
                    model="gpt-test",
                    timeout_seconds=12,
                )
            )
            saved = server_module.load_agent_config()
        finally:
            server_module.AGENT_LOCAL_CONFIG_PATH = original_path

    assert result["provider"] == "openai_compatible"
    assert saved["provider"] == "openai_compatible"
    assert saved["base_url"] == "https://api.openai.com/v1"
    assert saved["connection_status"] == "untested"


def main() -> None:
    test_openai_compatible_url()
    test_cursor_models_endpoint()
    test_openai_models_endpoint_selects_default_model()
    test_failed_connection_is_not_connected()
    test_save_resets_connection_status()
    test_base_url_overrides_stale_provider()
    print("smoke_agent_config: ok")


if __name__ == "__main__":
    main()
