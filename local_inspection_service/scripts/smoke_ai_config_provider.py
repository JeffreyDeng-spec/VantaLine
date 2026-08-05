#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service import server as server_module  # noqa: E402


def test_legacy_openai_detection_provider_falls_back_to_gemini() -> None:
    with tempfile.TemporaryDirectory() as tmp_raw:
        original_path = server_module.AI_LOCAL_CONFIG_PATH
        server_module.AI_LOCAL_CONFIG_PATH = Path(tmp_raw) / "ai_config.local.json"
        try:
            server_module.save_ai_local_config(
                {
                    "provider": "openai_compatible",
                    "model": "gpt-4o-mini",
                    "base_url": "https://api.openai.com/v1/chat/completions",
                    "timeout_seconds": 20,
                    "api_key_env": "",
                    "api_key": "",
                    "api_keys": [{"id": "legacy", "label": "OpenAI API Key", "env": "OPENAI_API_KEY", "provider": "openai_compatible"}],
                    "active_key_id": "",
                }
            )

            result = server_module.update_ai_config(
                server_module.AiConfigRequest(
                    timeout_seconds=30,
                )
            )
            saved = server_module.load_ai_local_config()
        finally:
            server_module.AI_LOCAL_CONFIG_PATH = original_path

    assert result["provider"] == "gemini"
    assert saved["provider"] == "gemini"
    assert saved["model"] == "gemini-2.5-flash"
    assert saved["base_url"] == "https://generativelanguage.googleapis.com/v1beta"
    assert saved["timeout_seconds"] == 30
    assert saved["api_keys"] == []


def test_qwen_provider_defaults_and_secret_isolation() -> None:
    with tempfile.TemporaryDirectory() as tmp_raw:
        tmp = Path(tmp_raw)
        original_config_path = server_module.AI_LOCAL_CONFIG_PATH
        original_secret_path = server_module.LOCAL_SECRET_ENV_PATH
        env_names = [
            "INSPECTION_AI_API_KEY",
            "INSPECTION_AI_API_KEY_ENV",
            "DASHSCOPE_API_KEY",
            "QWEN_API_KEY",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
        ]
        original_env = {name: os.environ.get(name) for name in env_names}
        server_module.AI_LOCAL_CONFIG_PATH = tmp / "ai_config.local.json"
        server_module.LOCAL_SECRET_ENV_PATH = tmp / "runtime_secrets.local.env"
        try:
            for name in env_names:
                os.environ.pop(name, None)
            result = server_module.update_ai_config(server_module.AiConfigRequest(provider="qwen"))
            saved = server_module.load_ai_local_config()

            assert result["provider"] == "qwen"
            assert result["provider_label"] == "Qwen"
            assert result["model"] == server_module.default_ai_model("qwen")
            assert result["base_url"] == server_module.default_ai_base_url("qwen")
            assert result["api_key_env"] == "DASHSCOPE_API_KEY"
            assert saved["provider"] == "qwen"
            assert saved["model"] == server_module.default_ai_model("qwen")

            secret = "dummy-qwen-api-key-123456"
            keyed = server_module.update_ai_config(
                server_module.AiConfigRequest(provider="qwen", api_key_env="DASHSCOPE_API_KEY", api_key=secret)
            )
            keyed_text = str(keyed)
            settings = server_module.ai_detection_settings()
            provider = server_module.ai_provider_from_settings(settings)
        finally:
            server_module.AI_LOCAL_CONFIG_PATH = original_config_path
            server_module.LOCAL_SECRET_ENV_PATH = original_secret_path
            for name, value in original_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    assert keyed["provider"] == "qwen"
    assert keyed["key_present"]
    assert keyed["masked_key"] != secret
    assert secret not in keyed_text
    assert settings["provider"] == "qwen"
    assert settings["api_key"] == secret
    assert isinstance(provider, server_module.OpenAICompatibleAiProvider)


def test_qwen_cost_pricing_and_usage_metadata() -> None:
    plus_cost, plus_tokens, plus_priced = server_module.api_cost_from_usage(
        "qwen3.7-plus",
        {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "total_tokens": 2_000_000},
    )
    flash_cost, _, flash_priced = server_module.api_cost_from_usage(
        "qwen3.6-flash-2026-04-16",
        {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "total_tokens": 2_000_000},
    )
    max_cost, _, max_priced = server_module.api_cost_from_usage(
        "qwen3.7-max",
        {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "total_tokens": 2_000_000},
    )

    assert plus_priced
    assert flash_priced
    assert max_priced
    assert plus_tokens["input"] == 1_000_000
    assert plus_tokens["output_text"] == 1_000_000
    assert plus_tokens["total"] == 2_000_000
    assert abs(plus_cost - 2.0) < 1e-9
    assert abs(flash_cost - 1.75) < 1e-9
    assert abs(max_cost - 10.0) < 1e-9
    assert "Qwen" in server_module.api_cost_summary([])["pricing_source"]

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [{"message": {"content": "{\"ok\": true}"}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
                }
            ).encode("utf-8")

    original_urlopen = server_module.ai_urlopen
    server_module.ai_urlopen = lambda *args, **kwargs: FakeResponse()
    try:
        provider = server_module.OpenAICompatibleAiProvider(
            {
                "configured": True,
                "base_url": "https://example.invalid/v1/chat/completions",
                "api_key": "dummy",
                "model": "qwen3.7-plus",
                "timeout_seconds": 10,
            }
        )
        parsed, latency_ms = provider.generate_json("system", [{"type": "text", "text": "hi"}], max_tokens=20)
    finally:
        server_module.ai_urlopen = original_urlopen

    assert parsed == {"ok": True}
    assert latency_ms >= 0
    assert provider.last_usage_metadata == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def test_cost_ledger_uses_actual_usage_only() -> None:
    with tempfile.TemporaryDirectory() as tmp_raw:
        tmp = Path(tmp_raw)
        data_dir = tmp / "data"
        auto_dir = data_dir / "auto_optimize"
        auto_dir.mkdir(parents=True)
        originals = {
            "DATA_DIR": server_module.DATA_DIR,
            "AUTO_OPTIMIZE_DIR": server_module.AUTO_OPTIMIZE_DIR,
            "AI_PROFILE_CACHE_PATH": server_module.AI_PROFILE_CACHE_PATH,
            "DATA_ANALYSIS_RECORDS_PATH": server_module.DATA_ANALYSIS_RECORDS_PATH,
            "AI_DETECTION_TASKS_PATH": server_module.AI_DETECTION_TASKS_PATH,
            "PIPELINE_TASKS_PATH": server_module.PIPELINE_TASKS_PATH,
        }
        server_module.DATA_DIR = data_dir
        server_module.AUTO_OPTIMIZE_DIR = auto_dir
        server_module.AI_PROFILE_CACHE_PATH = data_dir / "ai_profile_cache.local.json"
        server_module.DATA_ANALYSIS_RECORDS_PATH = data_dir / "data_analysis_records.json"
        server_module.AI_DETECTION_TASKS_PATH = data_dir / "ai_detection_tasks.json"
        server_module.PIPELINE_TASKS_PATH = data_dir / "pipeline_tasks.json"
        try:
            server_module.DATA_ANALYSIS_RECORDS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "model": "qwen3.7-plus",
                            "created_at": 1_700_000_000,
                            "usage_metadata": {
                                "prompt_tokens": 1_000,
                                "completion_tokens": 500,
                                "total_tokens": 1_500,
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (auto_dir / "legacy_mask_without_usage.json").write_text(
                json.dumps(
                    {
                        "samples": [
                            {
                                "sample_id": "legacy",
                                "label_status": "trainable",
                                "label_artifacts": {"model": "gemini-3.1-flash-image"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            records = server_module.api_cost_collect_records()
            summary = server_module.api_cost_summary(records)
        finally:
            for name, value in originals.items():
                setattr(server_module, name, value)

    assert len(records) == 1
    assert not any(record.get("estimated") for record in records)
    assert records[0]["model"] == "qwen3.7-plus"
    assert records[0]["tokens"]["total"] == 1_500
    assert summary["summary"]["estimated_call_count"] == 0
    assert summary["summary"]["estimated_cost_usd"] == 0.0
    assert "not estimated" in summary["pricing_source"]


def main() -> None:
    test_legacy_openai_detection_provider_falls_back_to_gemini()
    test_qwen_provider_defaults_and_secret_isolation()
    test_qwen_cost_pricing_and_usage_metadata()
    test_cost_ledger_uses_actual_usage_only()
    print("smoke_ai_config_provider: ok")


if __name__ == "__main__":
    main()
