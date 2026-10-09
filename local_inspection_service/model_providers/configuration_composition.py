"""Compose the provider configuration domain with explicit external capabilities.

Constructors are inert. Internal callbacks select named owner methods at operation
 time; request identity and database connections remain external suppliers.
"""
from __future__ import annotations
from dataclasses import replace
from collections.abc import Callable
from typing import Any, TYPE_CHECKING
from pathlib import Path
import urllib.request
from .proxy_runtime import AI_LOCAL_PROXY_URL
if TYPE_CHECKING:
    from ..model_profiles.composition import ModelConfiguration
    from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

from local_inspection_service.model_providers.configuration_ports import JsonDefaults, ImageDefaults, ValidationCapabilities, PublicUrlCapabilities
from local_inspection_service.model_providers.configuration_defaults import ProviderDefaults
from local_inspection_service.model_providers.configuration_validation import ProviderValidation
from local_inspection_service.model_providers.public_urls import PublicProviderURLs
from local_inspection_service.model_providers.key_identity import KeyIdentity as _KeyIdentity
from local_inspection_service.model_providers.local_secret_store import LocalSecretStore as _LocalSecretStore
from local_inspection_service.model_providers.key_material_ports import KeyIdentityRuntime as _KeyIdentityRuntime, SecretPaths as _SecretPaths, SecretCodec as _SecretCodec, SecretFileOperations as _SecretFileOperations, SecretEnvironment as _SecretEnvironment, SecretPolicy as _SecretPolicy, SecretStoreAccess as _SecretStoreAccess
from local_inspection_service.model_providers.key_registry import ProviderKeyRegistry as _ProviderKeyRegistry
from local_inspection_service.model_providers.key_registry_ports import KeyMaterial as _KeyMaterial, KeyPresentation as _KeyPresentation, JsonKeyPolicy as _JsonKeyPolicy, ImageKeyPolicy as _ImageKeyPolicy, AgentKeyPolicy as _AgentKeyPolicy
from local_inspection_service.model_providers.proxy_runtime import ProviderProxyRuntime
from local_inspection_service.model_providers.proxy_runtime_ports import ProxySettings, ProxyCalls, ProxyTransports
from local_inspection_service.model_providers.local_model_config import LocalModelConfig
from local_inspection_service.model_providers.local_model_config_ports import LocalModelConfigFiles, LocalJsonModelPolicy, LocalImageModelPolicy
from local_inspection_service.model_providers.legacy_settings_ports import LegacySettingsIO, LegacyPresentation, LegacyJsonPolicy, LegacyJsonCallbacks, LegacyImagePolicy, LegacyImageEnvironment, LegacyImageCallbacks
from local_inspection_service.model_providers.legacy_json_settings import LegacyJsonSettings
from local_inspection_service.model_providers.legacy_image_settings import LegacyImageSettings
from local_inspection_service.agent.settings_policy import AgentSettingsPolicy as _AgentSettingsPolicy
from local_inspection_service.agent.legacy_settings_store import LegacyAgentSettingsStore as _LegacyAgentSettingsStore
from local_inspection_service.agent.settings_ports import AgentSettingsDefaults as _AgentSettingsDefaults, AgentProviderPolicy as _AgentProviderPolicy, AgentSettingsKeys as _AgentSettingsKeys, AgentSettingsAccess as _AgentSettingsAccess, AgentSettingsAuthorization as _AgentSettingsAuthorization, AgentSettingsPresentation as _AgentSettingsPresentation, AgentSettingsPaths as _AgentSettingsPaths, AgentSettingsCodec as _AgentSettingsCodec, AgentSettingsFiles as _AgentSettingsFiles, AgentSettingsPersistence as _AgentSettingsPersistence

class ProviderConfiguration:
    """Own configuration policy, key material and legacy migration settings."""

    def create_model_configuration(
        self,
        *,
        runtime_repository: Callable[[], PostgresRuntimeRepository | None],
        legacy_label: Callable[[], dict[str, Any]],
        agent_defaults: Callable[[], dict[str, Any]],
    ) -> ModelConfiguration:
        """Close profiles over this provider owner without reading any source."""
        from ..model_profiles.composition import ModelConfiguration
        from ..model_profiles.dependencies import ProfileDependencies
        from ..model_profiles.legacy import LegacyConfiguration, sources

        def legacy_sources():
            return sources(LegacyConfiguration(
                ai=lambda: self._legacy_ai_detection_settings(),
                image=lambda: self._legacy_image_generation_settings(),
                agent=lambda: self._legacy_load_agent_config(),
                local=lambda: self.load_ai_local_config(),
                ai_keys=lambda config: self.normalize_ai_key_items(config),
                image_keys=lambda config, provider: self.normalize_image_key_items(config, provider),
                agent_keys=lambda config: self.normalize_agent_key_items(config),
                label=legacy_label,
            ))

        return ModelConfiguration(ProfileDependencies(
            runtime_repository=runtime_repository,
            write_secret=lambda name, value: self.set_local_secret_env(name, value),
            read_secret=lambda name: self.local_secret_env_value(name),
            legacy_sources=legacy_sources,
            validate_model=lambda value: self.validate_ai_model(value),
            validate_base_url=lambda value: self.validate_ai_base_url(value),
            mask_secret=lambda value: self.mask_secret(value),
        ), agent_defaults=agent_defaults)

    def __init__(
        self,
        *,
        json_defaults: JsonDefaults,
        image_defaults: ImageDefaults,
        validation_capabilities: ValidationCapabilities,
        public_url_capabilities: PublicUrlCapabilities,
        key_identity_runtime: _KeyIdentityRuntime,
        secret_paths: _SecretPaths,
        secret_codec: _SecretCodec,
        secret_file_operations: _SecretFileOperations,
        secret_environment: _SecretEnvironment,
        secret_policy: _SecretPolicy,
        secret_store_access: _SecretStoreAccess,
        key_material: _KeyMaterial,
        key_presentation: _KeyPresentation,
        json_key_policy: _JsonKeyPolicy,
        image_key_policy: _ImageKeyPolicy,
        agent_key_policy: _AgentKeyPolicy,
        proxy_settings: ProxySettings,
        proxy_calls: ProxyCalls,
        proxy_transports: ProxyTransports,
        local_model_config_files: LocalModelConfigFiles,
        local_json_model_policy: LocalJsonModelPolicy,
        local_image_model_policy: LocalImageModelPolicy,
        legacy_settings_i_o: LegacySettingsIO,
        legacy_presentation: LegacyPresentation,
        legacy_json_policy: LegacyJsonPolicy,
        legacy_json_callbacks: LegacyJsonCallbacks,
        legacy_image_policy: LegacyImagePolicy,
        legacy_image_environment: LegacyImageEnvironment,
        legacy_image_callbacks: LegacyImageCallbacks,
        agent_settings_defaults: _AgentSettingsDefaults,
        agent_provider_policy: _AgentProviderPolicy,
        agent_settings_keys: _AgentSettingsKeys,
        agent_settings_paths: _AgentSettingsPaths,
        agent_settings_codec: _AgentSettingsCodec,
        agent_settings_files: _AgentSettingsFiles,
        agent_settings_persistence: _AgentSettingsPersistence,
    ):
        self.defaults = ProviderDefaults(json_defaults, image_defaults)
        self.validation = ProviderValidation(validation_capabilities)
        self.public_urls = PublicProviderURLs(public_url_capabilities)
        self.identity = _KeyIdentity(replace(key_identity_runtime, key_id=lambda: self.ai_key_id))
        self.secrets = _LocalSecretStore(
            secret_paths,
            secret_codec,
            secret_file_operations,
            secret_environment,
            replace(
                secret_policy,
                validate=lambda: self.validate_ai_key_env,
                default_environment=lambda: self.default_secret_env_name,
                identity=lambda: self.secret_key_item_id,
            ),
            replace(
                secret_store_access,
                load=lambda: self.load_local_secret_env,
                save=lambda: self.save_local_secret_env,
                set=lambda: self.set_local_secret_env,
            ),
        )
        self.keys = _ProviderKeyRegistry(
            replace(
                key_material,
                environment=lambda: self.local_secret_env_value,
                identity=lambda: self.secret_key_item_id,
                default_environment=lambda: self.default_secret_env_name,
            ),
            replace(
                key_presentation,
                mask=lambda: self.mask_secret,
                json_label=lambda: self.ai_provider_label,
                image_label=lambda: self.image_generation_provider_label,
                agent_label=lambda: self.agent_provider_label,
            ),
            json_key_policy,
            replace(image_key_policy, validate=lambda: self.validate_image_generation_provider),
            replace(agent_key_policy, normalize=lambda: self.normalize_agent_provider),
        )
        self.proxy = ProviderProxyRuntime(
            settings=proxy_settings,
            calls=replace(
                      proxy_calls,
                      validate_ai_proxy_url=lambda: self.validate_ai_proxy_url,
                      ai_proxy_url_from_environment=lambda: self.ai_proxy_url_from_environment,
                      env_flag_enabled=lambda: self.env_flag_enabled,
                      local_proxy_available=lambda: self.local_proxy_available,
                  ),
            transports=proxy_transports,
        )
        self.local = LocalModelConfig(
            files=replace(
                      local_model_config_files,
                      ai_local_config_temp_path=lambda: self.ai_local_config_temp_path,
                  ),
            json_policy=replace(
                            local_json_model_policy,
                            default_ai_model=lambda: self.default_ai_model,
                            default_ai_base_url=lambda: self.default_ai_base_url,
                            validate_ai_proxy_url=lambda: self.validate_ai_proxy_url,
                            validate_ai_timeout=lambda: self.validate_ai_timeout,
                            normalize_ai_key_items=lambda: self.normalize_ai_key_items,
                            ai_keys_for_provider=lambda: self.ai_keys_for_provider,
                        ),
            image_policy=replace(
                             local_image_model_policy,
                             default_image_generation_model=lambda: self.default_image_generation_model,
                             default_image_generation_base_url=lambda: self.default_image_generation_base_url,
                             validate_ai_base_url=lambda: self.validate_ai_base_url,
                             validate_image_generation_timeout=lambda: self.validate_image_generation_timeout,
                             normalize_image_key_items=lambda: self.normalize_image_key_items,
                             image_keys_for_provider=lambda: self.image_keys_for_provider,
                         ),
        )
        self.legacy_json = LegacyJsonSettings(
            replace(
                legacy_settings_i_o,
                load=lambda: self.load_ai_local_config,
                proxy=lambda: self.ai_proxy_url_from_config,
                validate_base=lambda: self.validate_ai_base_url,
            ),
            replace(
                legacy_presentation,
                public_keys=lambda: self.public_ai_key_items,
                mask_secret=lambda: self.mask_secret,
                public_base=lambda: self.public_ai_base_url,
                mask_url=lambda: self.masked_url_for_status,
            ),
            legacy_json_policy,
            replace(
                legacy_json_callbacks,
                default_base=lambda: self.default_ai_base_url,
                validate_timeout=lambda: self.validate_ai_timeout,
                normalize_keys=lambda: self.normalize_ai_key_items,
                select_keys=lambda: self.ai_keys_for_provider,
                key_id=lambda: self.secret_key_item_id,
                label=lambda: self.ai_provider_label,
                flag=lambda: self.env_flag_enabled,
            ),
        )
        self.legacy_image = LegacyImageSettings(
            replace(
                legacy_settings_i_o,
                load=lambda: self.load_ai_local_config,
                proxy=lambda: self.ai_proxy_url_from_config,
                validate_base=lambda: self.validate_ai_base_url,
            ),
            replace(
                legacy_presentation,
                public_keys=lambda: self.public_ai_key_items,
                mask_secret=lambda: self.mask_secret,
                public_base=lambda: self.public_ai_base_url,
                mask_url=lambda: self.masked_url_for_status,
            ),
            legacy_image_policy,
            legacy_image_environment,
            replace(
                legacy_image_callbacks,
                default_model=lambda: self.default_image_generation_model,
                default_base=lambda: self.default_image_generation_base_url,
                default_key_env=lambda: self.default_image_generation_api_key_env,
                validate_timeout=lambda: self.validate_image_generation_timeout,
                normalize_keys=lambda: self.normalize_image_key_items,
                select_keys=lambda: self.image_keys_for_provider,
                label=lambda: self.image_generation_provider_label,
                provider_key=lambda: self.image_generation_provider_key,
            ),
        )
        self.agent_policy = _AgentSettingsPolicy(
            agent_settings_defaults,
            replace(
                agent_provider_policy,
                host=lambda: self.agent_base_url_host,
                is_cursor=lambda: self.is_cursor_base_url,
                detect=lambda: self.detect_agent_provider_from_base_url,
                normalize=lambda: self.normalize_agent_provider,
                options=lambda: self.normalize_agent_model_options,
            ),
            replace(
                agent_settings_keys,
                validate_environment=lambda: self.validate_ai_key_env,
                normalize=lambda: self.normalize_agent_key_items,
                for_provider=lambda: self.agent_keys_for_provider,
                environment_value=lambda: self.local_secret_env_value,
            ),
        )
        self.legacy_agent = _LegacyAgentSettingsStore(
            agent_settings_defaults,
            agent_settings_paths,
            agent_settings_codec,
            agent_settings_files,
            replace(
                agent_settings_persistence,
                normalize=lambda: self.normalize_agent_config,
                keys=lambda: self.normalize_agent_key_items,
                persist=lambda: self.persist_secret_key_items,
            ),
        )

    def default_ai_model(self, provider: str) -> str:
        return self.defaults.default_ai_model(provider)

    def default_ai_base_url(self, provider: str) -> str:
        return self.defaults.default_ai_base_url(provider)

    def ai_provider_label(self, provider: str) -> str:
        return self.defaults.ai_provider_label(provider)

    def default_image_generation_model(self, provider: str) -> str:
        return self.defaults.default_image_generation_model(provider)

    def default_image_generation_base_url(self, provider: str) -> str:
        return self.defaults.default_image_generation_base_url(provider)

    def default_image_generation_api_key_env(self, provider: str) -> str:
        return self.defaults.default_image_generation_api_key_env(provider)

    def image_generation_provider_key(self, provider: str) -> str:
        return self.defaults.image_generation_provider_key(provider)

    def image_generation_provider_label(self, provider: str) -> str:
        return self.defaults.image_generation_provider_label(provider)

    def mask_secret(self, value: str) -> str:
        return self.identity.mask_secret(value)

    def ai_key_id(self, secret: str) -> str:
        return self.identity.ai_key_id(secret)

    def secret_key_item_id(self, env_name: str, secret: str='') -> str:
        return self.identity.secret_key_item_id(env_name, secret)

    def default_secret_env_name(self, prefix: str, secret: str='', *, provider: str='') -> str:
        return self.identity.default_secret_env_name(prefix, secret, provider=provider)

    def load_local_secret_env(self) -> dict[str, str]:
        return self.secrets.load_local_secret_env()

    def save_local_secret_env(self, values: dict[str, str]) -> None:
        return self.secrets.save_local_secret_env(values)

    def local_secret_env_value(self, name: str) -> str:
        return self.secrets.local_secret_env_value(name)

    def set_local_secret_env(self, name: str, value: str) -> None:
        return self.secrets.set_local_secret_env(name, value)

    def delete_local_secret_env(self, name: str) -> None:
        return self.secrets.delete_local_secret_env(name)

    def persist_secret_key_items(self, items: list[dict[str, str]], default_prefix: str) -> list[dict[str, str]]:
        return self.secrets.persist_secret_key_items(items, default_prefix)

    def normalize_ai_key_items(self, config: dict[str, Any], provider: str | None=None) -> list[dict[str, str]]:
        return self.keys.normalize_ai_key_items(config, provider)

    def public_ai_key_items(self, items: list[dict[str, str]]) -> list[dict[str, str]]:
        return self.keys.public_ai_key_items(items)

    def ai_keys_for_provider(self, items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
        return self.keys.ai_keys_for_provider(items, provider)

    def normalize_image_key_items(self, config: dict[str, Any], provider: str) -> list[dict[str, str]]:
        return self.keys.normalize_image_key_items(config, provider)

    def normalize_agent_key_items(self, config: dict[str, Any]) -> list[dict[str, str]]:
        return self.keys.normalize_agent_key_items(config)

    def image_keys_for_provider(self, items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
        return self.keys.image_keys_for_provider(items, provider)

    def agent_keys_for_provider(self, items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
        return self.keys.agent_keys_for_provider(items, provider)

    def validate_ai_provider(self, value: Any) -> str:
        return self.validation.validate_ai_provider(value)

    def validate_image_generation_provider(self, value: Any) -> str:
        return self.validation.validate_image_generation_provider(value)

    def validate_ai_model(self, value: Any) -> str:
        return self.validation.validate_ai_model(value)

    def validate_ai_base_url(self, value: Any) -> str:
        return self.validation.validate_ai_base_url(value)

    def public_ai_base_url(self, value: Any) -> str:
        return self.public_urls.public_ai_base_url(value)

    def masked_url_for_status(self, value: Any) -> str:
        return self.public_urls.masked_url_for_status(value)

    def validate_ai_proxy_url(self, value: Any) -> str:
        return self.validation.validate_ai_proxy_url(value)

    def ai_proxy_url_from_environment(self) -> tuple[str, str]:
        return self.proxy.ai_proxy_url_from_environment()

    def local_proxy_available(self, proxy_url: str=AI_LOCAL_PROXY_URL) -> bool:
        return self.proxy.local_proxy_available(proxy_url)

    def env_flag_enabled(self, name: str, default: bool=True) -> bool:
        return self.proxy.env_flag_enabled(name, default)

    def ai_proxy_url_from_config(self, local: dict[str, Any], provider: str) -> tuple[str, str, bool]:
        return self.proxy.ai_proxy_url_from_config(local, provider)

    def ai_urlopen(self, request: urllib.request.Request, settings: dict[str, Any], *, timeout: float):
        return self.proxy.ai_urlopen(request, settings, timeout=timeout)

    def validate_ai_timeout(self, value: Any) -> float:
        return self.validation.validate_ai_timeout(value)

    def validate_image_generation_timeout(self, value: Any) -> float:
        return self.validation.validate_image_generation_timeout(value)

    def validate_ai_key_env(self, value: Any) -> str:
        return self.validation.validate_ai_key_env(value)

    def load_ai_local_config(self) -> dict[str, Any]:
        return self.local.load_ai_local_config()

    def ai_local_config_temp_path(self) -> Path:
        return self.local.ai_local_config_temp_path()

    def save_ai_local_config(self, config: dict[str, Any]) -> None:
        return self.local.save_ai_local_config(config)

    def _legacy_ai_detection_settings(self) -> dict[str, Any]:
        return self.legacy_json._legacy_ai_detection_settings()

    def _legacy_image_generation_settings(self) -> dict[str, Any]:
        return self.legacy_image._legacy_image_generation_settings()

    def agent_base_url_host(self, base_url: str) -> str:
        return self.agent_policy.agent_base_url_host(base_url)

    def is_cursor_base_url(self, base_url: str) -> bool:
        return self.agent_policy.is_cursor_base_url(base_url)

    def detect_agent_provider_from_base_url(self, base_url: str) -> str:
        return self.agent_policy.detect_agent_provider_from_base_url(base_url)

    def normalize_agent_provider(self, provider: str | None, base_url: str='') -> str:
        return self.agent_policy.normalize_agent_provider(provider, base_url)

    def agent_provider_label(self, provider: str) -> str:
        return self.agent_policy.agent_provider_label(provider)

    def normalize_agent_model_options(self, value: Any) -> list[dict[str, str]]:
        return self.agent_policy.normalize_agent_model_options(value)

    def agent_model_options_from_items(self, items: Any, *, prepend: list[dict[str, str]] | None=None) -> list[dict[str, str]]:
        return self.agent_policy.agent_model_options_from_items(items, prepend=prepend)

    def normalize_agent_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return self.agent_policy.normalize_agent_config(config)

    def _legacy_load_agent_config(self) -> dict[str, Any]:
        return self.legacy_agent._legacy_load_agent_config()

    def save_agent_config(self, config: dict[str, Any]) -> None:
        return self.legacy_agent.save_agent_config(config)
