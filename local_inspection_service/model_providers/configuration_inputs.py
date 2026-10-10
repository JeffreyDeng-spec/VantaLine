"""Typed provider construction inputs; no registry or application entry lookup."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from .configuration_composition import ProviderConfiguration
if TYPE_CHECKING:
    from ..storage.artifacts.files import BusinessFiles
from local_inspection_service.model_providers.configuration_ports import JsonDefaults, ImageDefaults, ValidationCapabilities, PublicUrlCapabilities
from local_inspection_service.model_providers.key_material_ports import KeyIdentityRuntime as _KeyIdentityRuntime, SecretPaths as _SecretPaths, SecretCodec as _SecretCodec, SecretFileOperations as _SecretFileOperations, SecretEnvironment as _SecretEnvironment, SecretPolicy as _SecretPolicy, SecretStoreAccess as _SecretStoreAccess
from local_inspection_service.model_providers.key_registry_ports import KeyMaterial as _KeyMaterial, KeyPresentation as _KeyPresentation, JsonKeyPolicy as _JsonKeyPolicy, ImageKeyPolicy as _ImageKeyPolicy, AgentKeyPolicy as _AgentKeyPolicy
from local_inspection_service.model_providers.proxy_runtime_ports import ProxySettings, ProxyCalls, ProxyTransports
from local_inspection_service.model_providers.local_model_config_ports import LocalModelConfigFiles, LocalJsonModelPolicy, LocalImageModelPolicy
from local_inspection_service.model_providers.legacy_settings_ports import LegacySettingsIO, LegacyPresentation, LegacyJsonPolicy, LegacyJsonCallbacks, LegacyImagePolicy, LegacyImageEnvironment, LegacyImageCallbacks
from local_inspection_service.agent.settings_ports import AgentSettingsDefaults as _AgentSettingsDefaults, AgentProviderPolicy as _AgentProviderPolicy, AgentSettingsKeys as _AgentSettingsKeys, AgentSettingsPaths as _AgentSettingsPaths, AgentSettingsCodec as _AgentSettingsCodec, AgentSettingsFiles as _AgentSettingsFiles, AgentSettingsPersistence as _AgentSettingsPersistence


@dataclass(frozen=True)
class ProviderConfigurationInputs:
    json_defaults: JsonDefaults
    image_defaults: ImageDefaults
    validation_capabilities: ValidationCapabilities
    public_url_capabilities: PublicUrlCapabilities
    key_identity_runtime: _KeyIdentityRuntime
    secret_paths: _SecretPaths
    secret_codec: _SecretCodec
    secret_file_operations: _SecretFileOperations
    secret_environment: _SecretEnvironment
    secret_policy: _SecretPolicy
    secret_store_access: _SecretStoreAccess
    key_material: _KeyMaterial
    key_presentation: _KeyPresentation
    json_key_policy: _JsonKeyPolicy
    image_key_policy: _ImageKeyPolicy
    agent_key_policy: _AgentKeyPolicy
    proxy_settings: ProxySettings
    proxy_calls: ProxyCalls
    proxy_transports: ProxyTransports
    local_model_config_files: LocalModelConfigFiles
    local_json_model_policy: LocalJsonModelPolicy
    local_image_model_policy: LocalImageModelPolicy
    legacy_settings_i_o: LegacySettingsIO
    legacy_presentation: LegacyPresentation
    legacy_json_policy: LegacyJsonPolicy
    legacy_json_callbacks: LegacyJsonCallbacks
    legacy_image_policy: LegacyImagePolicy
    legacy_image_environment: LegacyImageEnvironment
    legacy_image_callbacks: LegacyImageCallbacks
    agent_settings_defaults: _AgentSettingsDefaults
    agent_provider_policy: _AgentProviderPolicy
    agent_settings_keys: _AgentSettingsKeys
    agent_settings_paths: _AgentSettingsPaths
    agent_settings_codec: _AgentSettingsCodec
    agent_settings_files: _AgentSettingsFiles
    agent_settings_persistence: _AgentSettingsPersistence

    def build(self, *, files: BusinessFiles, ensure_dirs: Callable[[], None]) -> ProviderConfiguration:
        """Bind local file configuration to the selected infrastructure graph."""
        return ProviderConfiguration(
            json_defaults=self.json_defaults,
            image_defaults=self.image_defaults,
            validation_capabilities=self.validation_capabilities,
            public_url_capabilities=self.public_url_capabilities,
            key_identity_runtime=self.key_identity_runtime,
            secret_paths=self.secret_paths,
            secret_codec=self.secret_codec,
            secret_file_operations=self.secret_file_operations,
            secret_environment=self.secret_environment,
            secret_policy=self.secret_policy,
            secret_store_access=self.secret_store_access,
            key_material=self.key_material,
            key_presentation=self.key_presentation,
            json_key_policy=self.json_key_policy,
            image_key_policy=self.image_key_policy,
            agent_key_policy=self.agent_key_policy,
            proxy_settings=self.proxy_settings,
            proxy_calls=self.proxy_calls,
            proxy_transports=self.proxy_transports,
            local_model_config_files=replace(self.local_model_config_files, ensure_dirs=lambda: ensure_dirs, _business_files=lambda: files),
            local_json_model_policy=self.local_json_model_policy,
            local_image_model_policy=self.local_image_model_policy,
            legacy_settings_i_o=self.legacy_settings_i_o,
            legacy_presentation=self.legacy_presentation,
            legacy_json_policy=self.legacy_json_policy,
            legacy_json_callbacks=self.legacy_json_callbacks,
            legacy_image_policy=self.legacy_image_policy,
            legacy_image_environment=self.legacy_image_environment,
            legacy_image_callbacks=self.legacy_image_callbacks,
            agent_settings_defaults=self.agent_settings_defaults,
            agent_provider_policy=self.agent_provider_policy,
            agent_settings_keys=self.agent_settings_keys,
            agent_settings_paths=self.agent_settings_paths,
            agent_settings_codec=self.agent_settings_codec,
            agent_settings_files=self.agent_settings_files,
            agent_settings_persistence=self.agent_settings_persistence,
        )
