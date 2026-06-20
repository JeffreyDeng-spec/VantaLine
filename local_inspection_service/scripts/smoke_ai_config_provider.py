#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service import server as server_module  # noqa: E402


def test_partial_ai_config_save_preserves_openai_compatible_provider() -> None:
    with tempfile.TemporaryDirectory() as tmp_raw:
        original_path = server_module.AI_LOCAL_CONFIG_PATH
        server_module.AI_LOCAL_CONFIG_PATH = Path(tmp_raw) / "ai_config.local.json"
        try:
            server_module.save_ai_local_config(
                {
                    "provider": "openai_compatible",
                    "model": "gpt-4o-mini",
                    "base_url": "https://api.openai.com/v1",
                    "timeout_seconds": 20,
                    "api_key_env": "",
                    "api_key": "",
                    "api_keys": [],
                    "active_key_id": "",
                }
            )

            result = server_module.update_ai_config(
                server_module.AiConfigRequest(
                    model="gpt-4o",
                    base_url="https://api.openai.com/v1",
                    timeout_seconds=30,
                )
            )
            saved = server_module.load_ai_local_config()
        finally:
            server_module.AI_LOCAL_CONFIG_PATH = original_path

    assert result["provider"] == "openai_compatible"
    assert saved["provider"] == "openai_compatible"
    assert saved["model"] == "gpt-4o"
    assert saved["base_url"] == "https://api.openai.com/v1"
    assert saved["timeout_seconds"] == 30


def main() -> None:
    test_partial_ai_config_save_preserves_openai_compatible_provider()
    print("smoke_ai_config_provider: ok")


if __name__ == "__main__":
    main()
