"""Local model configuration normalization and persistence without Web imports."""
from dataclasses import dataclass
import json
import os
from typing import Any
from pathlib import Path
from .local_model_config_ports import LocalModelConfigFiles, LocalJsonModelPolicy, LocalImageModelPolicy

@dataclass(frozen=True)
class LocalModelConfig:
    files: LocalModelConfigFiles
    json_policy: LocalJsonModelPolicy
    image_policy: LocalImageModelPolicy

    def load_ai_local_config(self) -> dict[str, Any]:
        self.files.ensure_dirs()()
        if not self.files._business_files().exists(self.files.AI_LOCAL_CONFIG_PATH()):
            return dict(self.files.DEFAULT_AI_CONFIG())
        try:
            raw = json.loads(self.files._business_files().read_text(self.files.AI_LOCAL_CONFIG_PATH(), encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        config = dict(self.files.DEFAULT_AI_CONFIG())
        for key in self.files.DEFAULT_AI_CONFIG():
            if key in raw:
                config[key] = raw[key]
        raw_provider = str(config.get("provider") or self.json_policy.AI_DEFAULT_PROVIDER()).strip().lower()
        provider = raw_provider
        legacy_provider = provider in {"openai", "openai_compatible"} or provider not in self.json_policy.AI_SUPPORTED_PROVIDERS()
        if provider == "openai_compatible" and "generativelanguage.googleapis.com" in str(config.get("base_url") or ""):
            provider = "gemini"
        if provider not in self.json_policy.AI_SUPPORTED_PROVIDERS():
            provider = self.json_policy.AI_DEFAULT_PROVIDER()
        config["provider"] = provider
        config["model"] = str((self.json_policy.default_ai_model()(provider) if legacy_provider else config.get("model")) or self.json_policy.default_ai_model()(provider)).strip() or self.json_policy.default_ai_model()(provider)
        config["base_url"] = str((self.json_policy.default_ai_base_url()(provider) if legacy_provider else config.get("base_url")) or self.json_policy.default_ai_base_url()(provider)).strip() or self.json_policy.default_ai_base_url()(provider)
        if provider == "gemini" and "/openai/" in config["base_url"]:
            config["base_url"] = self.json_policy.default_ai_base_url()(provider)
        try:
            config["proxy_url"] = self.json_policy.validate_ai_proxy_url()(config.get("proxy_url"))
        except self.files.HTTPException():
            config["proxy_url"] = ""
        config["auto_local_proxy"] = bool(config.get("auto_local_proxy", True))
        try:
            config["timeout_seconds"] = self.json_policy.validate_ai_timeout()(config.get("timeout_seconds"))
        except self.files.HTTPException():
            config["timeout_seconds"] = self.json_policy.AI_DEFAULT_TIMEOUT_SECONDS()
        config["api_key_env"] = str(config.get("api_key_env") or "").strip()
        config["api_keys"] = self.json_policy.normalize_ai_key_items()(config, provider)
        active_key_id = str(config.get("active_key_id") or "").strip()
        current_ai_keys = self.json_policy.ai_keys_for_provider()(config["api_keys"], provider)
        if active_key_id and not any(item["id"] == active_key_id for item in current_ai_keys):
            active_key_id = ""
        config["active_key_id"] = active_key_id or (current_ai_keys[0]["id"] if current_ai_keys else "")
        config["api_key"] = ""
        image_provider = str(config.get("image_provider") or self.image_policy.IMAGE_GENERATION_DEFAULT_PROVIDER()).strip().lower()
        if image_provider not in self.image_policy.IMAGE_GENERATION_SUPPORTED_PROVIDERS():
            image_provider = self.image_policy.IMAGE_GENERATION_DEFAULT_PROVIDER()
        config["image_provider"] = image_provider
        config["image_model"] = str(config.get("image_model") or self.image_policy.default_image_generation_model()(image_provider)).strip() or self.image_policy.default_image_generation_model()(image_provider)
        config["image_base_url"] = str(config.get("image_base_url") or self.image_policy.default_image_generation_base_url()(image_provider)).strip() or self.image_policy.default_image_generation_base_url()(image_provider)
        try:
            config["image_base_url"] = self.image_policy.validate_ai_base_url()(config["image_base_url"])
        except self.files.HTTPException():
            config["image_base_url"] = self.image_policy.default_image_generation_base_url()(image_provider)
        try:
            config["image_timeout_seconds"] = self.image_policy.validate_image_generation_timeout()(config.get("image_timeout_seconds"))
        except self.files.HTTPException():
            config["image_timeout_seconds"] = self.image_policy.IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS()
        config["image_api_key_env"] = str(config.get("image_api_key_env") or "").strip()
        config["image_api_keys"] = self.image_policy.normalize_image_key_items()(config, image_provider)
        image_active_key_id = str(config.get("image_active_key_id") or "").strip()
        current_image_keys = self.image_policy.image_keys_for_provider()(config["image_api_keys"], image_provider)
        if image_active_key_id and not any(item["id"] == image_active_key_id for item in current_image_keys):
            image_active_key_id = ""
        config["image_active_key_id"] = image_active_key_id or (current_image_keys[0]["id"] if current_image_keys else "")
        config["image_api_key"] = ""
        return config


    def ai_local_config_temp_path(self) -> Path:
        return self.files.AI_LOCAL_CONFIG_PATH().with_name(f"{self.files.AI_LOCAL_CONFIG_PATH().name}.tmp")


    def save_ai_local_config(self, config: dict[str, Any]) -> None:
        self.files.DATA_DIR().mkdir(parents=True, exist_ok=True)
        payload = {key: config.get(key, self.files.DEFAULT_AI_CONFIG()[key]) for key in self.files.DEFAULT_AI_CONFIG()}
        tmp_path = self.files.ai_local_config_temp_path()()
        self.files._business_files().write_text(tmp_path, json.dumps(payload, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, self.files.AI_LOCAL_CONFIG_PATH())
        try:
            os.chmod(self.files.AI_LOCAL_CONFIG_PATH(), 0o600)
        except OSError:
            pass
