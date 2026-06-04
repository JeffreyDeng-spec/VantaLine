#!/usr/bin/env python3
"""Focused smoke checks for the AI Detection model path."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_http_error(fn: Any, message: str) -> None:
    try:
        fn()
    except server.HTTPException:
        return
    raise AssertionError(message)


class Patch:
    def __init__(self) -> None:
        self._attrs: list[tuple[Any, str, Any]] = []
        self._env: dict[str, str | None] = {}

    def attr(self, obj: Any, name: str, value: Any) -> None:
        self._attrs.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def env(self, name: str, value: str | None) -> None:
        if name not in self._env:
            self._env[name] = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def restore(self) -> None:
        for obj, name, value in reversed(self._attrs):
            setattr(obj, name, value)
        for name, value in self._env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def base_config() -> dict[str, Any]:
    item = {
        "id": "acc_smoke",
        "class_id": 7,
        "name": "Smoke Manual",
        "material_type": "text",
        "status": "active",
        "source_files": [],
        "normalized_assets": [],
        "ai_profile": {
            "accessory_id": "acc_smoke",
            "name": "Smoke Manual",
            "material_type": "text",
            "description": "Smoke Manual required accessory.",
            "tags": ["text"],
            "visual_signature": "name=Smoke Manual; material=text",
            "distinguishing_text": ["Smoke Manual"],
            "negative_cues": ["If visible printed text does not match this profile, mark missing."],
            "expected_count": 1,
        },
    }
    return {
        "active_model_id": server.DEFAULT_MODEL_ID,
        "image_size": 64,
        "confidence_threshold": 0.25,
        "required_classes": [7],
        "min_counts": {"7": 1},
        "ocr": {"enabled": False, "require_manual_types": False},
        "video": {"sample_every_seconds": 1.0, "max_frames": 2},
        "stream": {},
        "accessories": [item],
        "training": {"selected_accessory_ids": []},
    }


def patch_common(patch: Patch, tmpdir: Path, config: dict[str, Any]) -> None:
    output_dir = tmpdir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    patch.env("INSPECTION_AI_MCP_RUNTIME", None)
    patch.env("INSPECTION_AI_MCP_ENABLED", None)
    patch.attr(server, "OUTPUT_DIR", output_dir)
    patch.attr(server, "AI_LOCAL_CONFIG_PATH", tmpdir / "ai_config.local.json")
    patch.attr(server, "load_config", lambda: config)
    patch.attr(server, "save_config", lambda _config: None)
    patch.attr(server, "list_trained_model_specs", lambda: [])
    patch.attr(server, "list_training_tasks", lambda: [])


def disable_ai_env(patch: Patch) -> None:
    patch.env("INSPECTION_AI_DETECTION_ENABLED", None)
    patch.env("INSPECTION_AI_PROVIDER", None)
    patch.env("INSPECTION_AI_MODEL", None)
    patch.env("INSPECTION_AI_BASE_URL", None)
    patch.env("INSPECTION_AI_TIMEOUT_SECONDS", None)
    patch.env("INSPECTION_AI_API_KEY", None)
    patch.env("INSPECTION_AI_API_KEY_ENV", None)
    patch.env("GEMINI_API_KEY", None)
    patch.env("OPENAI_API_KEY", None)


def verify_status_and_ui_ai_option() -> None:
    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            disable_ai_env(patch)
            status = server.status()
            ids = [item["id"] for item in status["available_models"]]
            assert_true(server.AI_DETECTION_MODEL_ID in ids, "AI Detection must appear in /api/status available_models")
            app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
            assert_true("AI 检测" in app_js and "ai_detection" in app_js, "UI model menu must handle the AI Detection option")
    finally:
        patch.restore()


def verify_ai_key_config_smoke() -> None:
    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            disable_ai_env(patch)
            local_key = "dummy-local-ai-key-123456"
            env_key = "dummy-env-ai-key-654321"
            url_token = "dummy-url-token-abcdef"
            saved = server.update_ai_config(
                server.AiConfigRequest(
                    provider="gemini",
                    model="gemini-2.5-flash",
                    base_url="https://generativelanguage.googleapis.com/v1beta",
                    timeout_seconds=5,
                    api_key=local_key,
                )
            )
            saved_text = json.dumps(saved, sort_keys=True)
            assert_true(saved["key_present"], "saved local key should be present")
            assert_true(saved["key_source"] == "local", "saved key should resolve from local config")
            assert_true(saved["provider"] == "gemini", "AI provider should be Gemini in public config")
            assert_true(saved["api_keys"] and saved["api_keys"][0]["masked_key"], "AI key should be listed as a masked local key")
            assert_true(saved["masked_key"] and saved["masked_key"] != local_key, "saved key should be masked")
            assert_true(local_key not in saved_text, "AI config response must not include raw local key")
            assert_true(server.ai_detection_settings()["api_key"] == local_key, "provider settings should use saved local key")

            assert_http_error(
                lambda: server.update_ai_config(server.AiConfigRequest(base_url="https://example.com/v1/chat/completions?key=dummy-token")),
                "AI base_url must reject query strings because status returns the URL",
            )
            assert_http_error(
                lambda: server.update_ai_config(server.AiConfigRequest(base_url="https://example.com/v1/chat/completions#dummy-token")),
                "AI base_url must reject fragments because status returns the URL",
            )
            assert_http_error(
                lambda: server.update_ai_config(server.AiConfigRequest(base_url="http://api.example.com/v1/chat/completions")),
                "AI base_url must reject remote plain HTTP",
            )
            local_url_status = server.update_ai_config(server.AiConfigRequest(base_url="http://127.0.0.1:9999/v1/chat/completions"))
            assert_true(local_url_status["base_url"].startswith("http://127.0.0.1"), "localhost HTTP should remain available for local provider proxies")
            patch.env("INSPECTION_AI_BASE_URL", f"https://example.com/v1/chat/completions?key={url_token}#frag")
            url_status_text = json.dumps(server.get_ai_config(), sort_keys=True)
            assert_true(url_token not in url_status_text and "frag" not in url_status_text, "public AI config must strip query and fragment from base_url")
            patch.env("INSPECTION_AI_BASE_URL", None)

            patch.env("INSPECTION_AI_API_KEY", env_key)
            env_status = server.get_ai_config()
            env_text = json.dumps(env_status, sort_keys=True)
            assert_true(env_status["key_source"] == "env", "environment key should take precedence over local key")
            assert_true(env_status["masked_key"] != env_key, "environment key should be masked")
            assert_true(local_key not in env_text and env_key not in env_text, "AI config response must not include any raw key")
            assert_true(server.ai_detection_settings()["api_key"] == env_key, "provider settings should use env key before local key")

            patch.env("INSPECTION_AI_API_KEY", None)
            deleted = server.delete_ai_config_key()
            deleted_text = json.dumps(deleted, sort_keys=True)
            assert_true(not deleted["key_present"], "deleted local key should not be present without env key")
            assert_true(deleted["key_source"] == "missing", "deleted local key should resolve to missing key state")
            assert_true(local_key not in deleted_text, "delete response must not include raw deleted key")
    finally:
        patch.restore()


def verify_ai_config_secret_paths_are_gitignored() -> None:
    final_path = server.AI_LOCAL_CONFIG_PATH
    temp_path = server.ai_local_config_temp_path()
    legacy_suffix_temp_path = final_path.with_suffix(".local.json.tmp")
    assert_true(temp_path == final_path.with_name(f"{final_path.name}.tmp"), "AI config temp path must keep the final secret-file prefix")
    assert_true(
        legacy_suffix_temp_path.name == "ai_config.local.local.json.tmp",
        "legacy with_suffix temp path should stay covered by .gitignore",
    )
    for path in (final_path, temp_path, legacy_suffix_temp_path):
        result = subprocess.run(
            ["git", "-C", str(ROOT.parent), "check-ignore", "--quiet", str(path)],
            check=False,
        )
        assert_true(result.returncode == 0, f"AI config secret path must be gitignored: {path}")


def verify_accessory_profile_fallback() -> None:
    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            disable_ai_env(patch)
            item = {
                "id": "acc_profile",
                "class_id": 8,
                "name": "Profile Card",
                "material_type": "text",
                "source_files": [],
                "physical_size": server.physical_size_payload("text"),
            }
            profile = server.generate_accessory_ai_profile(item, allow_provider=True)
            required = {
                "accessory_id",
                "name",
                "material_type",
                "description",
                "tags",
                "visual_signature",
                "distinguishing_text",
                "negative_cues",
                "expected_count",
            }
            assert_true(required.issubset(profile.keys()), "fallback profile must include the stable required keys")
            assert_true(item["ai_profile_status"]["source"] == "fallback", "unconfigured provider should persist fallback status")
    finally:
        patch.restore()


def verify_mcp_tool_contracts() -> None:
    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            config = base_config()
            patch_common(patch, tmpdir, config)
            disable_ai_env(patch)
            image_a = tmpdir / "reference_a.jpg"
            image_b = tmpdir / "reference_b.jpg"
            cv2.imwrite(str(image_a), np.full((12, 16, 3), 80, dtype=np.uint8))
            cv2.imwrite(str(image_b), np.full((14, 18, 3), 160, dtype=np.uint8))
            item = {
                "id": "acc_contract",
                "class_id": 9,
                "name": "Contract Accessory",
                "material_type": "object",
                "source_files": [str(image_a), str(image_b)],
                "physical_size": server.physical_size_payload("object"),
            }

            profile_result = server.call_ai_mcp_tool(
                "accessory.profile.generate",
                {"accessory": item, "allow_provider": False, "provider_config": server.ai_detection_settings()},
            )
            assert_true(profile_result["tool"] == "accessory.profile.generate", "profile tool should identify its contract")
            assert_true(profile_result["profile"]["accessory_id"] == "acc_contract", "profile tool should normalize accessory id")
            assert_true(profile_result["status"]["source"] == "fallback", "profile tool fallback should be explicit")
            assert_true("ai_profile" not in item, "profile tool contract should not mutate its input accessory")

            reference_result = server.call_ai_mcp_tool(
                "accessory.reference.collect",
                {"accessory": item, "max_images": 1, "max_side": 64, "quality": 60},
            )
            assert_true(reference_result["tool"] == "accessory.reference.collect", "reference tool should identify its contract")
            assert_true(reference_result["reference_count"] == 1, "reference tool must obey max_images")
            descriptor = reference_result["references"][0]
            assert_true(descriptor["accessory_id"] == "acc_contract", "reference descriptor should carry accessory id")
            assert_true(descriptor["data_url"].startswith("data:image/jpeg;base64,"), "reference descriptor should carry image payload")

            provider_result = server.call_ai_mcp_tool(
                "provider.gemini.generate_json",
                {
                    "provider_config": server.ai_detection_settings(),
                    "system_prompt": "Return JSON.",
                    "user_content": [{"type": "text", "text": "{}"}],
                    "max_tokens": 16,
                },
            )
            provider_text = json.dumps(provider_result, sort_keys=True)
            assert_true(provider_result["ok"] is False, "unconfigured provider tool should fail closed")
            assert_true('"api_key"' not in provider_text, "provider tool output must not expose raw api key fields")
    finally:
        patch.restore()


def verify_mcp_runtime_defaults_to_in_process() -> None:
    calls: list[str] = []

    class ExplodingMcpClient:
        def call_tool(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            calls.append("call_tool")
            raise AssertionError("stdio MCP client must not be used by default")

        def ensure_started(self) -> None:
            calls.append("ensure_started")
            raise AssertionError("stdio MCP warmup must not run by default")

        def close(self) -> None:
            calls.append("close")

    class FakeThread:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            calls.append("thread_created")

        def start(self) -> None:
            calls.append("thread_started")

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            disable_ai_env(patch)
            patch.attr(server, "_ai_mcp_client", ExplodingMcpClient())
            patch.attr(server.threading, "Thread", FakeThread)
            assert_true(server.ai_mcp_runtime() == server.AI_MCP_RUNTIME_IN_PROCESS, "default MCP runtime should be in-process")
            assert_true(not server.external_ai_mcp_enabled(), "default MCP runtime should not enable stdio")
            server.warm_ai_mcp_client()
            server.start_ai_mcp_warmup()
            result = server.call_ai_mcp_tool(
                "provider.gemini.generate_json",
                {
                    "provider_config": server.ai_detection_settings(),
                    "system_prompt": "Return JSON.",
                    "user_content": [{"type": "text", "text": "{}"}],
                    "max_tokens": 16,
                },
            )
            assert_true(result["ok"] is False, "unconfigured provider should still fail closed")
            assert_true(result["mcp_transport"] == "in_process", "default tool dispatch should be in-process")
            assert_true(result["mcp_runtime"] == server.AI_MCP_RUNTIME_IN_PROCESS, "default runtime metadata should be in-process")
            assert_true(not calls, "default runtime must not start or call the stdio MCP client")
    finally:
        patch.restore()


def verify_mcp_stdio_opt_in_failure_falls_back() -> None:
    class BrokenMcpClient:
        def __init__(self) -> None:
            self.calls = 0
            self.closed = False

        def call_tool(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            raise json.JSONDecodeError("synthetic bad JSON", "{", 0)

        def ensure_started(self) -> None:
            self.calls += 1

        def close(self) -> None:
            self.closed = True

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            broken = BrokenMcpClient()
            patch_common(patch, Path(tmp), base_config())
            disable_ai_env(patch)
            patch.env("INSPECTION_AI_MCP_RUNTIME", "stdio")
            patch.attr(server, "_ai_mcp_client", broken)
            result = server.call_ai_mcp_tool(
                "provider.gemini.generate_json",
                {
                    "provider_config": server.ai_detection_settings(),
                    "system_prompt": "Return JSON.",
                    "user_content": [{"type": "text", "text": "{}"}],
                    "max_tokens": 16,
                },
            )
            result_text = json.dumps(result, sort_keys=True)
            assert_true(broken.calls == 1 and broken.closed, "stdio opt-in should try the client and close it after transport failure")
            assert_true(result["ok"] is False, "stdio transport failure should fall back to structured provider failure")
            assert_true(result["mcp_transport"] == "in_process", "stdio transport failure should fall back to in-process handler")
            assert_true(result["mcp_fallback_from"] == server.AI_MCP_RUNTIME_STDIO, "fallback source should be tagged")
            assert_true("JSONDecodeError" not in result_text, "transport JSONDecodeError class name should not leak to tool output")
    finally:
        patch.restore()


def verify_provider_malformed_json_and_bad_shape_fail_closed() -> None:
    class MalformedJsonProvider:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
            raise server.AiProviderError("AI provider did not return a JSON object")

    class BadShapeProvider:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> tuple[Any, int]:
            return ["not", "an", "object"], 11

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.env("GEMINI_API_KEY", None)
            settings = server.ai_detection_settings()
            payload = {
                "provider_config": settings,
                "system_prompt": "Return JSON.",
                "user_content": [{"type": "text", "text": "{}"}],
                "max_tokens": 16,
            }

            patch.attr(server, "ai_provider", lambda: MalformedJsonProvider())
            malformed = server.call_ai_mcp_tool("provider.gemini.generate_json", payload)
            malformed_text = json.dumps(malformed, sort_keys=True)
            assert_true(malformed["ok"] is False, "malformed provider JSON should return ok:false")
            assert_true(malformed["provider_failure"], "malformed provider JSON should be tagged as provider failure")
            assert_true(malformed["parsed"] == {}, "malformed provider JSON should not expose a parsed payload")
            assert_true("test-key" not in malformed_text, "malformed provider output must not leak raw API keys")

            patch.attr(server, "ai_provider", lambda: BadShapeProvider())
            bad_shape = server.call_ai_mcp_tool("provider.gemini.generate_json", payload)
            assert_true(bad_shape["ok"] is False, "provider bad parsed shape should return ok:false")
            assert_true("non-object JSON" in bad_shape["error"], "provider bad parsed shape should explain the bounded failure")
    finally:
        patch.restore()


def verify_ai_provider_malformed_json_returns_normal_failure_shape() -> None:
    class MalformedJsonProvider:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
            raise server.AiProviderError("AI provider did not return a JSON object")

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.env("GEMINI_API_KEY", None)
            patch.attr(server, "ai_provider", lambda: MalformedJsonProvider())
            image = np.zeros((24, 24, 3), dtype=np.uint8)
            result = server.analyze_bgr(image, "ai_malformed_provider_json", server.AI_DETECTION_MODEL_ID)
            result_text = json.dumps(result, sort_keys=True)
            for key in ("request_id", "passed", "model", "rule", "detections", "annotated_url", "ai"):
                assert_true(key in result, f"AI malformed provider result missing top-level key: {key}")
            assert_true(not result["passed"], "provider malformed JSON should fail closed")
            assert_true(result["rule"]["missing"] == ["acc_smoke"], "provider malformed JSON should report required accessory missing")
            assert_true(all("box_2d" not in det for det in result["detections"]), "provider malformed JSON should not return bbox fields")
            assert_true(result["ai"]["provider_failure"], "provider malformed JSON should be tagged in ai debug metadata")
            assert_true(result["ai"]["mcp_transport"] == "in_process", "AI debug should show in-process tool transport")
            assert_true("test-key" not in result_text, "AI debug output must not leak raw API keys")
    finally:
        patch.restore()


def verify_vision_presence_tool_contract() -> None:
    captured: dict[str, Any] = {}

    class ContractProvider:
        def generate_json(self, system_prompt: str, user_content: list[dict[str, Any]], **kwargs: Any) -> tuple[dict[str, Any], int]:
            captured["system_prompt"] = system_prompt
            captured["user_content"] = user_content
            captured["max_tokens"] = kwargs.get("max_tokens")
            return {
                "detections": [
                    {
                        "accessory_id": "acc_smoke",
                        "label": "Smoke Manual",
                        "present": True,
                        "confidence": 0.91,
                        "evidence": "matching text visible",
                        "box_2d": [100, 200, 700, 800],
                    }
                ],
                "rule": {"counts": {"acc_smoke": 1}},
                "raw_summary": "one accessory present",
            }, 77

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config = base_config()
            patch_common(patch, Path(tmp), config)
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.env("GEMINI_API_KEY", None)
            patch.attr(server, "AI_REFERENCE_IMAGES_PER_ACCESSORY", 1)
            patch.attr(server, "ai_provider", lambda: ContractProvider())
            image = np.zeros((24, 24, 3), dtype=np.uint8)
            required = [server.required_accessory_profile_payload(config["accessories"][0], 1)]
            duplicate_refs = [
                {
                    "accessory_id": "acc_smoke",
                    "data_url": server.image_bgr_data_url(np.ones((8, 8, 3), dtype=np.uint8), max_side=32, quality=60),
                    "detail": "low",
                },
                {
                    "accessory_id": "acc_smoke",
                    "data_url": server.image_bgr_data_url(np.ones((8, 8, 3), dtype=np.uint8) * 2, max_side=32, quality=60),
                    "detail": "low",
                },
            ]
            result = server.call_ai_mcp_tool(
                "vision.inspect.presence",
                {
                    "inspection_image_bgr": image,
                    "required_accessories": required,
                    "reference_descriptors": duplicate_refs,
                    "provider_config": server.ai_detection_settings(),
                },
            )
            assert_true(result["tool"] == "vision.inspect.presence", "vision tool should identify its contract")
            assert_true(result["passed"], "vision tool should return normalized pass state")
            assert_true(result["rule"]["present"] == ["acc_smoke"], "vision tool should normalize present ids")
            assert_true(result["detections"][0]["box_2d"] == [100.0, 200.0, 700.0, 800.0], "vision tool should normalize provider bbox")
            assert_true(result["ai"]["reference_images"] == 1, "vision tool should bound references to one per accessory")
            assert_true("test-key" not in json.dumps(result, sort_keys=True), "vision tool result must not echo raw API keys")
            image_parts = [part for part in captured["user_content"] if part.get("type") == "image_url"]
            assert_true(len(image_parts) == 2, "provider payload should include inspection image plus one bounded reference")
            assert_true("manuals or cards" not in captured["system_prompt"], "vision prompt should not hardcode manual/card special cases")
            assert_true("compact bbox JSON" in captured["system_prompt"], "vision prompt should ask for compact bbox JSON")
            assert_true(captured["max_tokens"] == server.ai_detection_output_token_budget(1), "vision provider output cap should be low and dynamic")
    finally:
        patch.restore()


def verify_ai_analyze_draws_provider_bbox() -> None:
    captured: dict[str, Any] = {"calls": 0}

    class BboxProvider:
        def generate_json(self, *_args: Any, **kwargs: Any) -> tuple[dict[str, Any], int]:
            captured["calls"] += 1
            captured["max_tokens"] = kwargs.get("max_tokens")
            return {
                "detections": [
                    {
                        "accessory_id": "acc_smoke",
                        "label": "Smoke Manual",
                        "present": True,
                        "confidence": 0.937,
                        "box_2d": [-10, 200, 620, 1200],
                        "observed_text": ["Smoke Manual"],
                    }
                ],
                "rule": {"counts": {"acc_smoke": 1}},
            }, 42

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.env("GEMINI_API_KEY", None)
            patch.attr(server, "ai_provider", lambda: BboxProvider())
            image = np.full((80, 100, 3), 18, dtype=np.uint8)
            result = server.analyze_bgr(image, "ai_bbox", server.AI_DETECTION_MODEL_ID)
            assert_true(captured["calls"] == 1, "AI bbox analyze must not make a second provider call")
            assert_true(captured["max_tokens"] == server.ai_detection_output_token_budget(1), "AI bbox provider max_tokens should use the low dynamic budget")
            assert_true(result["passed"], "valid provider bbox should keep the local pass decision")
            assert_true(result["annotated_url"].endswith("_ai_annotated.jpg"), "valid provider bbox should produce an AI annotated output")
            detection = result["detections"][0]
            assert_true(detection["box_2d"] == [0.0, 200.0, 620.0, 1000.0], "AI analyze should clamp and return normalized bbox")
            assert_true(detection["observed_text"] == ["Smoke Manual"], "AI analyze should keep observed_text compatibility")

            out_path = Path(tmp) / "outputs" / result["annotated_url"].removeprefix("/outputs/")
            saved = cv2.imread(str(out_path), cv2.IMREAD_COLOR)
            assert_true(saved is not None, "AI annotated output image should be saved")
            diff = cv2.absdiff(saved, image)
            assert_true(int(diff.max()) > 80, "AI annotated output should contain visible bbox pixels")
            assert_true(int(np.count_nonzero(diff > 35)) > 100, "AI annotated output should draw more than compression noise")

            assert_true(server.normalize_ai_box_2d([100, 100, 50, 200]) is None, "inverted AI bbox should be rejected")
            assert_true(server.normalize_ai_box_2d([0, 0, float("nan"), 100]) is None, "non-finite AI bbox should be rejected")
            assert_true(server.normalize_ai_box_2d(["0", 0, 100, 100]) is None, "non-numeric AI bbox should be rejected")
    finally:
        patch.restore()


def verify_ai_analyze_disabled_returns_original_shape() -> None:
    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            disable_ai_env(patch)
            image = np.zeros((32, 48, 3), dtype=np.uint8)
            result = server.analyze_bgr(image, "ai_disabled", server.AI_DETECTION_MODEL_ID)
            for key in ("request_id", "passed", "model", "rule", "detections", "annotated_url"):
                assert_true(key in result, f"AI result missing top-level key: {key}")
            assert_true(result["model"]["is_ai_detection"], "AI result model should be marked as AI Detection")
            assert_true(result["rule"]["match_policy"] == "ai_presence", "AI rule should use ai_presence policy")
            assert_true(all("box_2d" not in det for det in result["detections"]), "AI disabled path should not return bbox fields")
            out_path = Path(tmp) / "outputs" / result["annotated_url"].removeprefix("/outputs/")
            saved = cv2.imread(str(out_path), cv2.IMREAD_COLOR)
            assert_true(saved is not None and int(saved.max()) <= 2, "AI disabled path should return the original image without drawn boxes")
    finally:
        patch.restore()


def verify_ai_timeout_is_structured() -> None:
    class TimeoutProvider:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
            raise server.AiProviderTimeout("synthetic timeout")

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.attr(server, "ai_provider", lambda: TimeoutProvider())
            image = np.zeros((24, 24, 3), dtype=np.uint8)
            result = server.analyze_bgr(image, "ai_timeout", server.AI_DETECTION_MODEL_ID)
            assert_true(not result["passed"], "timeout should fail closed")
            assert_true(result["ai"]["timed_out"], "timeout should be surfaced in structured ai metadata")
            assert_true(result["rule"]["missing"] == ["acc_smoke"], "timeout should report required accessory as missing")
    finally:
        patch.restore()


def verify_ai_video_preserves_frame_debug_metadata() -> None:
    class FakeUpload:
        def __init__(self, path: Path) -> None:
            self.filename = path.name
            self.file = path.open("rb")

    def fake_analyze_bgr(_frame: np.ndarray, request_id: str, _model_id: str | None = None) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "passed": False,
            "model": {
                "id": server.AI_DETECTION_MODEL_ID,
                "label": server.AI_DETECTION_LABEL,
                "variant": "ai_detection",
                "is_ai_detection": True,
                "provider_model": "gemini-2.5-flash-lite",
            },
            "rule": {
                "match_policy": "ai_presence",
                "present": [],
                "missing": ["acc_smoke"],
                "extra": [],
                "counts": {"acc_smoke": 0},
            },
            "detections": [
                {
                    "accessory_id": "acc_smoke",
                    "label": "Smoke Manual",
                    "present": False,
                    "confidence": 0.0,
                }
            ],
            "annotated_url": f"/outputs/{request_id}_ai_original.jpg",
            "ai": {
                "latency_ms": 5000,
                "timed_out": True,
                "error": "synthetic timeout",
                "provider_status": "ready",
                "provider_model": "gemini-2.5-flash-lite",
            },
        }

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            config = base_config()
            config["video"] = {"sample_every_seconds": 1.0, "max_frames": 2}
            patch_common(patch, tmpdir, config)
            upload_dir = tmpdir / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            patch.attr(server, "UPLOAD_DIR", upload_dir)
            patch.attr(server, "analyze_bgr", fake_analyze_bgr)

            video_path = tmpdir / "ai_debug_video.avi"
            writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 2.0, (16, 16))
            assert_true(writer.isOpened(), "test video writer should open")
            for value in (20, 60, 100, 140):
                writer.write(np.full((16, 16, 3), value, dtype=np.uint8))
            writer.release()

            upload = FakeUpload(video_path)
            try:
                result = asyncio.run(server.analyze_video(upload, server.AI_DETECTION_MODEL_ID))
            finally:
                upload.file.close()

            assert_true(not result["passed"], "AI video timeout frame should fail overall video")
            assert_true(result["ai"]["timed_out"], "video response should aggregate AI timeout state")
            assert_true(result["ai"]["first_error"] == "synthetic timeout", "video response should expose first AI error")
            assert_true(result["frames"], "video response should include sampled frames")
            frame = result["frames"][0]
            assert_true(frame["ai"]["error"] == "synthetic timeout", "video frame should preserve AI error metadata")
            assert_true(frame["model"]["is_ai_detection"], "video frame should preserve AI model metadata")
            assert_true(frame["rule"]["match_policy"] == "ai_presence", "video frame should preserve AI rule metadata")
            assert_true(frame["detections"] == 1 and len(frame["detection_items"]) == 1, "video frame should keep compact and detailed detections")
            app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
            assert_true("video_frames" in app_js and "detection_items" in app_js, "AI debug modal should include video frame summaries")
    finally:
        patch.restore()


def verify_ai_malformed_present_string_fails_closed() -> None:
    class MalformedBooleanProvider:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
            return {
                "detections": [
                    {
                        "accessory_id": "acc_smoke",
                        "label": "Smoke Manual",
                        "present": "false",
                        "confidence": 0.9,
                        "evidence": "malformed provider boolean",
                    }
                ],
                "rule": {"counts": {"acc_smoke": 1}},
            }, 123

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.attr(server, "ai_provider", lambda: MalformedBooleanProvider())
            image = np.zeros((24, 24, 3), dtype=np.uint8)
            result = server.analyze_bgr(image, "ai_malformed_bool", server.AI_DETECTION_MODEL_ID)
            assert_true(not result["passed"], "string present=false must fail closed")
            assert_true(result["detections"][0]["present"] is False, "non-boolean present must normalize to false")
            assert_true(result["rule"]["missing"] == ["acc_smoke"], "malformed boolean must keep accessory in missing list")
            assert_true(result["rule"]["counts"]["acc_smoke"] == 0, "malformed boolean must not preserve provider count as present")
    finally:
        patch.restore()


def verify_ai_present_without_count_does_not_satisfy_multiple_required() -> None:
    class PresentNoCountProvider:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
            return {
                "detections": [
                    {
                        "accessory_id": "acc_smoke",
                        "label": "Smoke Manual",
                        "present": True,
                        "confidence": 0.95,
                        "evidence": "one visible item",
                        "box_2d": [100, 100, 700, 700],
                    }
                ],
                "rule": {"counts": {}},
            }, 94

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config = base_config()
            config["min_counts"] = {"7": 2}
            config["accessories"][0]["ai_profile"]["expected_count"] = 2
            patch_common(patch, Path(tmp), config)
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.attr(server, "ai_provider", lambda: PresentNoCountProvider())
            image = np.zeros((24, 24, 3), dtype=np.uint8)
            result = server.analyze_bgr(image, "ai_present_no_count", server.AI_DETECTION_MODEL_ID)
            assert_true(not result["passed"], "one boolean present without provider count must not satisfy expected_count=2")
            assert_true(result["rule"]["counts"]["acc_smoke"] == 1, "missing provider count should normalize to one visible item")
            assert_true(result["rule"]["missing"] == ["acc_smoke"], "accessory should remain missing until provider returns count >= expected")
    finally:
        patch.restore()


def verify_ai_present_requires_valid_provider_bbox() -> None:
    provider_payload: dict[str, Any] = {}

    class CaseProvider:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
            return provider_payload, 81

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.attr(server, "ai_provider", lambda: CaseProvider())
            image = np.zeros((32, 40, 3), dtype=np.uint8)

            for case_name, box_2d in (("missing_box", None), ("invalid_box", [100, 100, 50, 200])):
                detection = {
                    "accessory_id": "acc_smoke",
                    "label": "Smoke Manual",
                    "present": True,
                    "confidence": 0.9,
                }
                if box_2d is not None:
                    detection["box_2d"] = box_2d
                provider_payload.clear()
                provider_payload.update(
                    {
                        "detections": [detection],
                        "rule": {"counts": {"acc_smoke": 1}},
                    }
                )
                result = server.analyze_bgr(image, f"ai_present_{case_name}", server.AI_DETECTION_MODEL_ID)
                assert_true(not result["passed"], f"{case_name} must fail closed even with provider count")
                assert_true(
                    result["annotated_url"].endswith("_ai_original.jpg"),
                    f"{case_name} may return original image but must not pass without a drawn bbox",
                )
                assert_true(result["detections"][0]["present"] is False, f"{case_name} should clear present")
                assert_true("box_2d" not in result["detections"][0], f"{case_name} should not expose invalid bbox")
                assert_true(result["rule"]["counts"]["acc_smoke"] == 0, f"{case_name} should force zero count")
                assert_true(result["rule"]["missing"] == ["acc_smoke"], f"{case_name} should report missing accessory")
    finally:
        patch.restore()


def verify_ai_invalid_counts_and_confidence_fail_closed() -> None:
    provider_payload: dict[str, Any] = {}

    class CaseProvider:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
            return provider_payload, 88

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config = base_config()
            config["min_counts"] = {"7": 2}
            patch_common(patch, Path(tmp), config)
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.attr(server, "ai_provider", lambda: CaseProvider())
            image = np.zeros((24, 24, 3), dtype=np.uint8)

            for case_name, count_value in (("count_string", "2"), ("count_float", 2.9), ("count_bool", True)):
                provider_payload.clear()
                provider_payload.update(
                    {
                        "detections": [
                            {
                                "accessory_id": "acc_smoke",
                                "label": "Smoke Manual",
                                "present": True,
                                "confidence": 0.95,
                            }
                        ],
                        "rule": {"counts": {"acc_smoke": count_value}},
                    }
                )
                result = server.analyze_bgr(image, f"ai_{case_name}", server.AI_DETECTION_MODEL_ID)
                assert_true(not result["passed"], f"{case_name} must fail closed for expected_count=2")
                assert_true(result["rule"]["counts"]["acc_smoke"] == 0, f"{case_name} should normalize invalid count to zero")
                assert_true(result["rule"]["counts"]["acc_smoke"] != 2, f"{case_name} must not coerce invalid count to 2")
                assert_true(result["rule"]["missing"] == ["acc_smoke"], f"{case_name} should remain missing")

            provider_payload.clear()
            provider_payload.update(
                {
                    "detections": [
                        {
                            "accessory_id": "acc_smoke",
                            "label": "Smoke Manual",
                            "present": True,
                            "confidence": "NaN",
                        }
                    ],
                    "rule": {"counts": {"acc_smoke": 1}},
                }
            )
            result = server.analyze_bgr(image, "ai_confidence_nan", server.AI_DETECTION_MODEL_ID)
            assert_true(not result["passed"], "non-finite confidence must fail closed")
            assert_true(result["detections"][0]["confidence"] == 0.0, "non-finite confidence should normalize to zero")
            assert_true(result["detections"][0]["present"] is False, "non-finite confidence should clear present")
            assert_true(result["rule"]["counts"]["acc_smoke"] == 0, "non-finite confidence should force zero count")
    finally:
        patch.restore()


def verify_missing_required_class_fails_closed() -> None:
    class ExistingOnlyProvider:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
            return {
                "detections": [
                    {
                        "accessory_id": "acc_smoke",
                        "label": "Smoke Manual",
                        "present": True,
                        "confidence": 0.96,
                        "evidence": "existing accessory only",
                    }
                ],
                "rule": {"counts": {"acc_smoke": 1}},
            }, 10

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config = base_config()
            config["required_classes"] = [7, 8]
            config["min_counts"] = {"7": 1, "8": 1}
            patch_common(patch, Path(tmp), config)
            patch.env("INSPECTION_AI_DETECTION_ENABLED", "1")
            patch.env("INSPECTION_AI_API_KEY", "test-key")
            patch.attr(server, "ai_provider", lambda: ExistingOnlyProvider())
            image = np.zeros((24, 24, 3), dtype=np.uint8)
            result = server.analyze_bgr(image, "ai_missing_class", server.AI_DETECTION_MODEL_ID)
            assert_true(not result["passed"], "missing configured required class must fail closed")
            assert_true("required_class_8" in result["rule"]["missing"], "missing required class should remain in AI missing list")
            assert_true(result["rule"]["counts"].get("required_class_8") == 0, "missing required class should have zero count")
    finally:
        patch.restore()


def verify_yolo_path_still_runs_with_existing_shape() -> None:
    class FakeModel:
        def predict(self, *_args: Any, **_kwargs: Any) -> list[object]:
            return [object()]

    patch = Patch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            patch_common(patch, Path(tmp), base_config())
            patch.attr(server, "model", lambda *_args, **_kwargs: FakeModel())
            patch.attr(server, "parse_detections", lambda _result, _spec: [])
            patch.attr(server, "attach_ocr_results", lambda _image, detections, _config, _spec: detections)
            patch.attr(server, "draw_detections", lambda image, _detections, _rule: image.copy())
            image = np.zeros((20, 20, 3), dtype=np.uint8)
            result = server.analyze_bgr(image, "yolo_smoke", server.DEFAULT_MODEL_ID)
            assert_true(result["model"]["id"] == server.DEFAULT_MODEL_ID, "YOLO path should still select the requested local model")
            assert_true(result["rule"]["match_policy"] == "exact_count", "YOLO path should keep existing exact-count rule")
    finally:
        patch.restore()


def main() -> int:
    checks = [
        verify_status_and_ui_ai_option,
        verify_ai_key_config_smoke,
        verify_ai_config_secret_paths_are_gitignored,
        verify_accessory_profile_fallback,
        verify_mcp_tool_contracts,
        verify_mcp_runtime_defaults_to_in_process,
        verify_mcp_stdio_opt_in_failure_falls_back,
        verify_provider_malformed_json_and_bad_shape_fail_closed,
        verify_ai_provider_malformed_json_returns_normal_failure_shape,
        verify_vision_presence_tool_contract,
        verify_ai_analyze_draws_provider_bbox,
        verify_ai_analyze_disabled_returns_original_shape,
        verify_ai_timeout_is_structured,
        verify_ai_video_preserves_frame_debug_metadata,
        verify_ai_malformed_present_string_fails_closed,
        verify_ai_present_without_count_does_not_satisfy_multiple_required,
        verify_ai_present_requires_valid_provider_bbox,
        verify_ai_invalid_counts_and_confidence_fail_closed,
        verify_missing_required_class_fails_closed,
        verify_yolo_path_still_runs_with_existing_shape,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
