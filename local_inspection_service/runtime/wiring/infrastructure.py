"""Static application wiring; original narrow business ports remain the boundary.

Only the canonical assembler consumes this result. Business components receive
their existing narrow ports; no application-entry callback is used.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import MutableMapping
from typing import Any, Callable
import contextvars
import _thread
from ..application_values import ApplicationValues
from local_inspection_service.model_providers.proxy_runtime import AI_LOCAL_PROXY_URL
from local_inspection_service.auth.account_projection_ports import AccountMedia
from local_inspection_service.auth.account_projection_ports import AccountModels
from local_inspection_service.auth.visibility_composition import AccountVisibility
from typing import Any
from local_inspection_service.auth.http_composition import AuthenticationHttpPolicy
from local_inspection_service.auth.composition import AuthenticationSettings
from typing import Callable
from local_inspection_service.runtime.infrastructure import ConfigurationRowCodecs
from local_inspection_service.storage.artifacts.files import FileDigest
from local_inspection_service.runtime.application_foundation import FoundationInputs
from fastapi import HTTPException
from PIL import Image
from local_inspection_service.model_providers.configuration_ports import ImageDefaults
from local_inspection_service.storage.artifacts.images import ImageFiles
from local_inspection_service.runtime.infrastructure import InfrastructureInputs
from local_inspection_service.model_providers.configuration_ports import JsonDefaults
from local_inspection_service.model_providers.legacy_settings_ports import LegacyImageCallbacks
from local_inspection_service.model_providers.legacy_settings_ports import LegacyImageEnvironment
from local_inspection_service.model_providers.legacy_settings_ports import LegacyImagePolicy
from local_inspection_service.model_providers.legacy_settings_ports import LegacyJsonCallbacks
from local_inspection_service.model_providers.legacy_settings_ports import LegacyJsonPolicy
from local_inspection_service.model_providers.legacy_settings_ports import LegacyPresentation
from local_inspection_service.model_providers.legacy_settings_ports import LegacySettingsIO
from local_inspection_service.auth.login_limits import LoginLimitSettings
from local_inspection_service.records.resource_name_ports import NameCatalogs
from local_inspection_service.records.resource_name_ports import NamePolicy
from pathlib import Path
from local_inspection_service.runtime.path_configuration_composition import PathConfigurationLocations
from local_inspection_service.runtime.service_path_ports import PathProjectionPolicy
from local_inspection_service.model_providers.configuration_inputs import ProviderConfigurationInputs
from local_inspection_service.auth.status import PublicStatusProjection
from local_inspection_service.model_providers.configuration_ports import PublicUrlCapabilities
from local_inspection_service.retired_features import REMOVED_PHASE1_PUBLIC_CONFIG_KEYS
from local_inspection_service.records.resource_names import ResourceNames
from local_inspection_service.runtime.service_path_ports import ServicePathSettings
from local_inspection_service.auth.status_requests import ServiceStatusRequests
from local_inspection_service.auth.sessions import SessionSettings
from local_inspection_service.auth.status_ports import StatusPolicy
from local_inspection_service.auth.status_ports import StatusProjectionCalls
from local_inspection_service.auth.status_requests_ports import StatusRequestAccess
from local_inspection_service.auth.status_requests_ports import StatusRequestCatalog
from local_inspection_service.auth.status_requests_ports import StatusRequestRuntime
from local_inspection_service.auth.status_ports import StatusSources
from local_inspection_service.config.stream import StreamConfiguration
from local_inspection_service.model_providers.configuration_ports import ValidationCapabilities
from local_inspection_service.auth.visibility_composition import VisibilityAccess
from local_inspection_service.auth.visibility_composition import VisibilityConfiguration
from local_inspection_service.auth.visibility_composition import VisibilityOrigins
from local_inspection_service.runtime.web_shell import WebShell
from ultralytics import YOLO
from local_inspection_service.accessories import policy as _accessory_policy
from local_inspection_service.model_providers.key_registry_ports import AgentKeyPolicy as _native_AgentKeyPolicy_844
from local_inspection_service.agent.settings_ports import AgentProviderPolicy as _native_AgentProviderPolicy_847
from local_inspection_service.agent.settings_ports import AgentSettingsCodec as _native_AgentSettingsCodec_847
from local_inspection_service.agent.settings_ports import AgentSettingsDefaults as _native_AgentSettingsDefaults_847
from local_inspection_service.agent.settings_ports import AgentSettingsFiles as _native_AgentSettingsFiles_847
from local_inspection_service.agent.settings_ports import AgentSettingsKeys as _native_AgentSettingsKeys_847
from local_inspection_service.agent.settings_ports import AgentSettingsPaths as _native_AgentSettingsPaths_847
from local_inspection_service.agent.settings_ports import AgentSettingsPersistence as _native_AgentSettingsPersistence_847
from local_inspection_service.model_providers.key_registry_ports import ImageKeyPolicy as _native_ImageKeyPolicy_844
from local_inspection_service.model_providers.key_registry_ports import JsonKeyPolicy as _native_JsonKeyPolicy_844
from local_inspection_service.model_providers.key_material_ports import KeyIdentityRuntime as _native_KeyIdentityRuntime_843
from local_inspection_service.model_providers.key_registry_ports import KeyMaterial as _native_KeyMaterial_844
from local_inspection_service.model_providers.key_registry_ports import KeyPresentation as _native_KeyPresentation_844
from local_inspection_service.model_providers.local_model_config_ports import LocalImageModelPolicy as _native_LocalImageModelPolicy_846
from local_inspection_service.model_providers.local_model_config_ports import LocalJsonModelPolicy as _native_LocalJsonModelPolicy_846
from local_inspection_service.model_providers.local_model_config_ports import LocalModelConfigFiles as _native_LocalModelConfigFiles_846
from local_inspection_service.model_providers.proxy_runtime_ports import ProxyCalls as _native_ProxyCalls_845
from local_inspection_service.model_providers.proxy_runtime_ports import ProxySettings as _native_ProxySettings_845
from local_inspection_service.model_providers.proxy_runtime_ports import ProxyTransports as _native_ProxyTransports_845
from local_inspection_service.model_providers.key_material_ports import SecretCodec as _native_SecretCodec_843
from local_inspection_service.model_providers.key_material_ports import SecretEnvironment as _native_SecretEnvironment_843
from local_inspection_service.model_providers.key_material_ports import SecretFileOperations as _native_SecretFileOperations_843
from local_inspection_service.model_providers.key_material_ports import SecretPaths as _native_SecretPaths_843
from local_inspection_service.model_providers.key_material_ports import SecretPolicy as _native_SecretPolicy_843
from local_inspection_service.model_providers.key_material_ports import SecretStoreAccess as _native_SecretStoreAccess_843
from local_inspection_service.storage.runtime_records import accessory_rows
from local_inspection_service.storage.runtime_records import app_config_rows
from local_inspection_service.runtime.text_policy import bounded_text
from local_inspection_service.runtime.infrastructure import build_infrastructure
from local_inspection_service.storage.runtime_records import config_from_rows
import contextvars
import cv2
import hashlib
import json
from local_inspection_service.label_inspection.model import legacy_settings as legacy_label_settings
import os
import re
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from urllib.parse import urlunsplit
from local_inspection_service.auth.policy import user_has_permission
from local_inspection_service.auth.policy import user_is_admin
import local_inspection_service.agent.legacy_settings_store
import local_inspection_service.agent.settings_policy
import local_inspection_service.auth.access
import local_inspection_service.auth.account_projections
import local_inspection_service.auth.accounts
import local_inspection_service.auth.application
import local_inspection_service.auth.composition
import local_inspection_service.auth.credentials
import local_inspection_service.auth.docs_api
import local_inspection_service.auth.flows
import local_inspection_service.auth.http_composition
import local_inspection_service.auth.login_limits
import local_inspection_service.auth.public_network
import local_inspection_service.auth.repository
import local_inspection_service.auth.sessions
import local_inspection_service.auth.status
import local_inspection_service.auth.status_requests
import local_inspection_service.auth.users
import local_inspection_service.auth.visibility_composition
import local_inspection_service.config.app_store
import local_inspection_service.config.application_composition
import local_inspection_service.config.stream
import local_inspection_service.detection.local_models
import local_inspection_service.detection.model_selection
import local_inspection_service.detection.task_catalog
import local_inspection_service.detection.task_store
import local_inspection_service.model_profiles.composition
import local_inspection_service.model_profiles.service
import local_inspection_service.model_providers.configuration_composition
import local_inspection_service.model_providers.configuration_defaults
import local_inspection_service.model_providers.configuration_validation
import local_inspection_service.model_providers.image_provider_configuration
import local_inspection_service.model_providers.key_identity
import local_inspection_service.model_providers.key_registry
import local_inspection_service.model_providers.legacy_image_settings
import local_inspection_service.model_providers.legacy_json_settings
import local_inspection_service.model_providers.local_model_config
import local_inspection_service.model_providers.local_secret_store
import local_inspection_service.model_providers.proxy_runtime
import local_inspection_service.model_providers.public_urls
import local_inspection_service.pipeline.task_store
import local_inspection_service.records.access
import local_inspection_service.records.audit
import local_inspection_service.records.composition
import local_inspection_service.records.ownership
import local_inspection_service.records.resource_names
import local_inspection_service.runtime.application_foundation
import local_inspection_service.runtime.connections
import local_inspection_service.runtime.directories
import local_inspection_service.runtime.identity
import local_inspection_service.runtime.infrastructure
import local_inspection_service.runtime.path_configuration_composition
import local_inspection_service.runtime.read_caches
import local_inspection_service.runtime.repository_access
import local_inspection_service.runtime.repository_composition
import local_inspection_service.runtime.service_paths
import local_inspection_service.runtime.web_shell
import local_inspection_service.runtime.yolo_warmup
import local_inspection_service.storage.artifacts.composition
import local_inspection_service.storage.artifacts.files
import local_inspection_service.storage.artifacts.images
import local_inspection_service.training.account_state_composition
import local_inspection_service.training.catalog_composition
import local_inspection_service.training.executor_settings
import local_inspection_service.training.model_catalog
import local_inspection_service.training.resource_queries
import local_inspection_service.training.state_composition

@dataclass(frozen=True)
class InfrastructureWiringInputs:
    CORS_ORIGINS: Callable[[], list[Any]]
    CORS_ORIGIN_REGEX: Callable[[], str]
    _artifact_composition: Callable[[], local_inspection_service.storage.artifacts.composition.ArtifactComposition]
    _business_files: Callable[[], local_inspection_service.storage.artifacts.files.BusinessFiles]
    _detection_task_catalog: Callable[[], local_inspection_service.detection.task_catalog.TaskCatalog]
    _detection_task_store: Callable[[], local_inspection_service.detection.task_store.DetectionTaskStore]
    _image_provider_configuration: Callable[[], local_inspection_service.model_providers.image_provider_configuration.ImageProviderConfiguration]
    _local_models: Callable[[], local_inspection_service.detection.local_models.LocalModels]
    _model_catalog: Callable[[], local_inspection_service.training.catalog_composition.ModelCatalog]
    _model_selection: Callable[[], local_inspection_service.detection.model_selection.ModelSelection]
    _pipeline_task_store: Callable[[], local_inspection_service.pipeline.task_store.PipelineTaskStore]
    _trained_model_catalog: Callable[[], local_inspection_service.training.model_catalog.TrainedModelCatalog]
    _training_account_state: Callable[[], local_inspection_service.training.account_state_composition.TrainingAccountState]
    _training_executor_settings: Callable[[], local_inspection_service.training.executor_settings.ExecutorSettings]
    _training_resources: Callable[[], local_inspection_service.training.resource_queries.TrainingResources]
    _training_state_workflows: Callable[[], local_inspection_service.training.state_composition.TrainingStateWorkflows]
    _yolo_warmup_runtime: Callable[[], local_inspection_service.runtime.yolo_warmup.YoloWarmup]

@dataclass(frozen=True)
class InfrastructureAssembly:
    _access_control: local_inspection_service.auth.access.AccessControl
    _accessory_image_io: local_inspection_service.storage.artifacts.images.ImageFiles
    _account_projections: local_inspection_service.auth.account_projections.AccountProjections
    _account_service: local_inspection_service.auth.accounts.AccountService
    _account_visibility: local_inspection_service.auth.visibility_composition.AccountVisibility
    _agent_pil_images: local_inspection_service.storage.artifacts.images.ImageFiles
    _agent_settings_policy: local_inspection_service.agent.settings_policy.AgentSettingsPolicy
    _app_config_store: local_inspection_service.config.app_store.AppConfigStore
    _app_configuration: local_inspection_service.config.application_composition.ApplicationConfiguration
    _auth_flows: local_inspection_service.auth.flows.AuthFlows
    _auth_repository: local_inspection_service.auth.repository.AuthRepository
    _authentication: local_inspection_service.auth.composition.AuthenticationServices
    _authentication_domain: local_inspection_service.auth.application.AuthenticationDomain
    _authentication_http: local_inspection_service.auth.http_composition.AuthenticationHttp
    _background_image_io: local_inspection_service.storage.artifacts.images.ImageFiles
    _config_io_lock: _thread.RLock
    _documentation_access: local_inspection_service.auth.docs_api.DocumentationAccess
    _file_digest: local_inspection_service.storage.artifacts.files.FileDigest
    _foundation: local_inspection_service.runtime.application_foundation.ApplicationFoundation
    _incoming_image_files: local_inspection_service.storage.artifacts.images.ImageFiles
    _infrastructure: local_inspection_service.runtime.infrastructure.ApplicationInfrastructure
    _json_cache: local_inspection_service.runtime.read_caches.JsonFileReadCache
    _key_identity: local_inspection_service.model_providers.key_identity.KeyIdentity
    _legacy_agent_settings_store: local_inspection_service.agent.legacy_settings_store.LegacyAgentSettingsStore
    _legacy_image_settings_service: local_inspection_service.model_providers.legacy_image_settings.LegacyImageSettings
    _legacy_json_settings_service: local_inspection_service.model_providers.legacy_json_settings.LegacyJsonSettings
    _local_model_config: local_inspection_service.model_providers.local_model_config.LocalModelConfig
    _local_path_migration: local_inspection_service.runtime.directories.LocalPathMigration
    _local_secret_store: local_inspection_service.model_providers.local_secret_store.LocalSecretStore
    _login_blocked_until: dict[str, Any]
    _login_failures: dict[str, Any]
    _login_limiter: local_inspection_service.auth.login_limits.LoginRateLimiter
    _login_rate_limit_lock: _thread.RLock
    _model_profile_configuration: local_inspection_service.model_profiles.composition.ModelConfiguration
    _password_hasher: local_inspection_service.auth.credentials.PasswordHasher
    _path_configuration: local_inspection_service.runtime.path_configuration_composition.PathConfigurationWorkflows
    _provider_configuration: local_inspection_service.model_providers.configuration_composition.ProviderConfiguration
    _provider_configuration_defaults: local_inspection_service.model_providers.configuration_defaults.ProviderDefaults
    _provider_configuration_validation: local_inspection_service.model_providers.configuration_validation.ProviderValidation
    _provider_key_registry: local_inspection_service.model_providers.key_registry.ProviderKeyRegistry
    _provider_proxy_runtime: local_inspection_service.model_providers.proxy_runtime.ProviderProxyRuntime
    _provider_public_urls: local_inspection_service.model_providers.public_urls.PublicProviderURLs
    _public_network_policy: local_inspection_service.auth.public_network.PublicNetworkPolicy
    _public_status_projection: local_inspection_service.auth.status.PublicStatusProjection
    _read_path_cache: contextvars.ContextVar[Any]
    _record_access: local_inspection_service.records.access.RecordAccess
    _record_audit: local_inspection_service.records.audit.RecordAudit
    _record_ownership: local_inspection_service.records.ownership.RecordOwnership
    _record_services: local_inspection_service.records.composition.RecordServices
    _request_read_cache: local_inspection_service.runtime.read_caches.RequestReadCache
    _request_user: local_inspection_service.runtime.identity.RequestIdentity
    _resource_names: local_inspection_service.records.resource_names.ResourceNames
    _runtime_repositories: local_inspection_service.runtime.connections.ThreadRepositoryFactory
    _runtime_repository_access: local_inspection_service.runtime.repository_access.RuntimeRepositoryAccess
    _runtime_repository_owner: local_inspection_service.runtime.repository_composition.RuntimeRepositories
    _service_directories: local_inspection_service.runtime.directories.ServiceDirectories
    _service_paths: local_inspection_service.runtime.service_paths.ServicePaths
    _service_status_requests: local_inspection_service.auth.status_requests.ServiceStatusRequests
    _session_service: local_inspection_service.auth.sessions.SessionService
    _store_cache: local_inspection_service.runtime.read_caches.StoreReadCache
    _stream_configuration: local_inspection_service.config.stream.StreamConfiguration
    _training_image_io: local_inspection_service.storage.artifacts.images.ImageFiles
    _user_service: local_inspection_service.auth.users.UserService
    _web_shell: local_inspection_service.runtime.web_shell.WebShell
    authenticate_request: Callable[..., Any]
    bootstrap_admin_from_env: Callable[..., Any]
    clear_failed_login_attempts: Callable[..., Any]
    clear_session_cookie: Callable[..., Any]
    create_auth_user: Callable[..., Any]
    create_login_session: Callable[..., Any]
    create_session: Callable[..., Any]
    current_auth_user: Callable[..., Any]
    current_owner_fields: Callable[..., Any]
    delete_auth_session: Callable[..., Any]
    delete_auth_sessions_for_user: Callable[..., Any]
    delete_auth_user: Callable[..., Any]
    delete_expired_auth_sessions: Callable[..., Any]
    enforce_login_rate_limit: Callable[..., Any]
    enrich_record_audit_fields: Callable[..., Any]
    ensure_dirs: Callable[..., Any]
    index: Callable[..., Any]
    legacy_index: Callable[..., Any]
    load_auth_store: Callable[..., Any]
    load_json_file_mtime_cached: Callable[..., Any]
    migrate_persisted_local_paths_once: Callable[..., Any]
    model_profile_service: local_inspection_service.model_profiles.service.Service
    mutate_app_config_atomically: Callable[..., Any]
    owner_fields_for_new_record: Callable[..., Any]
    password_hash: Callable[..., Any]
    prune_login_rate_limit_state: Callable[..., Any]
    react_preview: Callable[..., Any]
    react_production_spa: Callable[..., Any]
    read_path_cache_scope: Callable[..., Any]
    record_audit_fields: Callable[..., Any]
    record_failed_login_attempt: Callable[..., Any]
    record_matches_owner_filter: Callable[..., Any]
    record_mutable_by_user: Callable[..., Any]
    record_owner_id: Callable[..., Any]
    record_owner_username: Callable[..., Any]
    record_visible_to_user: Callable[..., Any]
    require_admin_role: Callable[..., Any]
    require_docs_admin: Callable[..., Any]
    require_permission: Callable[..., Any]
    require_record_access: Callable[..., Any]
    runtime_repository_cache_key: Callable[..., Any]
    save_app_config: Callable[..., Any]
    save_auth_session: Callable[..., Any]
    save_auth_session_touch_or_prune: Callable[..., Any]
    save_auth_store: Callable[..., Any]
    save_auth_user: Callable[..., Any]
    save_login_session: Callable[..., Any]
    set_session_cookie: Callable[..., Any]
    set_user_password: Callable[..., Any]
    store_read_cache_get: Callable[..., Any]
    store_read_cache_invalidate: Callable[..., Any]
    store_read_cache_put: Callable[..., Any]
    users_exist: Callable[..., Any]
from local_inspection_service.storage.runtime_selector import PostgresConnector

def assemble_infrastructure(values: ApplicationValues, environment: MutableMapping[str, str], ports: InfrastructureWiringInputs, *, connector: PostgresConnector | None = None) -> InfrastructureAssembly:
    def legacy_model_specs() -> list[dict[str, Any]]:
        return ports._model_catalog().legacy_model_specs()

    def resource_name_key(value: Any) -> str:
        return _resource_names.resource_name_key(value)

    def duplicate_name_error(resource_label: str) -> None:
        return _resource_names.duplicate_name_error(resource_label)

    def task_record_name(record: dict[str, Any]) -> str:
        return _resource_names.task_record_name(record)

    def task_matches_excluded_identity(task: dict[str, Any], *, excluded_pipeline_task_ids: set[str], excluded_ai_task_ids: set[str]) -> bool:
        return _resource_names.task_matches_excluded_identity(task, excluded_pipeline_task_ids=excluded_pipeline_task_ids, excluded_ai_task_ids=excluded_ai_task_ids)

    def training_state_for_user(config: dict[str, Any], user: dict[str, Any], selected_ids: set[str], target_user_id: str | None=None) -> dict[str, Any]:
        return ports._training_account_state().training_state_for_user(config, user, selected_ids, target_user_id)

    def scope_config_for_user(config: dict[str, Any], user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
        return _account_projections.scope_config_for_user(config, user, target_user_id)

    def load_config() -> dict[str, Any]:
        return _app_configuration.load_config()

    def save_config(config: dict[str, Any]) -> None:
        return _app_configuration.save_config(config)

    def accessory_uid(item: dict[str, Any]) -> str:
        return _accessory_policy.accessory_uid(item)

    def public_path_sanitized(value: Any) -> Any:
        return _service_paths.public_path_sanitized(value)

    def default_ai_model(provider: str) -> str:
        return _provider_configuration.default_ai_model(provider)

    def default_ai_base_url(provider: str) -> str:
        return _provider_configuration.default_ai_base_url(provider)

    def ai_provider_label(provider: str) -> str:
        return _provider_configuration.ai_provider_label(provider)

    def default_image_generation_model(provider: str) -> str:
        return _provider_configuration.default_image_generation_model(provider)

    def default_image_generation_base_url(provider: str) -> str:
        return _provider_configuration.default_image_generation_base_url(provider)

    def default_image_generation_api_key_env(provider: str) -> str:
        return _provider_configuration.default_image_generation_api_key_env(provider)

    def image_generation_provider_key(provider: str) -> str:
        return _provider_configuration.image_generation_provider_key(provider)

    def image_generation_provider_label(provider: str) -> str:
        return _provider_configuration.image_generation_provider_label(provider)

    def mask_secret(value: str) -> str:
        return _provider_configuration.mask_secret(value)

    def ai_key_id(secret: str) -> str:
        return _provider_configuration.ai_key_id(secret)

    def secret_key_item_id(env_name: str, secret: str='') -> str:
        return _provider_configuration.secret_key_item_id(env_name, secret)

    def default_secret_env_name(prefix: str, secret: str='', *, provider: str='') -> str:
        return _provider_configuration.default_secret_env_name(prefix, secret, provider=provider)

    def load_local_secret_env() -> dict[str, str]:
        return _provider_configuration.load_local_secret_env()

    def save_local_secret_env(values: dict[str, str]) -> None:
        return _provider_configuration.save_local_secret_env(values)

    def local_secret_env_value(name: str) -> str:
        return _provider_configuration.local_secret_env_value(name)

    def set_local_secret_env(name: str, value: str) -> None:
        return _provider_configuration.set_local_secret_env(name, value)

    def persist_secret_key_items(items: list[dict[str, str]], default_prefix: str) -> list[dict[str, str]]:
        return _provider_configuration.persist_secret_key_items(items, default_prefix)

    def normalize_ai_key_items(config: dict[str, Any], provider: str | None=None) -> list[dict[str, str]]:
        return _provider_configuration.normalize_ai_key_items(config, provider)

    def public_ai_key_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
        return _provider_configuration.public_ai_key_items(items)

    def ai_keys_for_provider(items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
        return _provider_configuration.ai_keys_for_provider(items, provider)

    def normalize_image_key_items(config: dict[str, Any], provider: str) -> list[dict[str, str]]:
        return _provider_configuration.normalize_image_key_items(config, provider)

    def normalize_agent_key_items(config: dict[str, Any]) -> list[dict[str, str]]:
        return _provider_configuration.normalize_agent_key_items(config)

    def image_keys_for_provider(items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
        return _provider_configuration.image_keys_for_provider(items, provider)

    def agent_keys_for_provider(items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
        return _provider_configuration.agent_keys_for_provider(items, provider)

    def validate_image_generation_provider(value: Any) -> str:
        return _provider_configuration.validate_image_generation_provider(value)

    def validate_ai_base_url(value: Any) -> str:
        return _provider_configuration.validate_ai_base_url(value)

    def public_ai_base_url(value: Any) -> str:
        return _provider_configuration.public_ai_base_url(value)

    def masked_url_for_status(value: Any) -> str:
        return _provider_configuration.masked_url_for_status(value)

    def validate_ai_proxy_url(value: Any) -> str:
        return _provider_configuration.validate_ai_proxy_url(value)

    def ai_proxy_url_from_environment() -> tuple[str, str]:
        return _provider_configuration.ai_proxy_url_from_environment()

    def local_proxy_available(proxy_url: str=AI_LOCAL_PROXY_URL) -> bool:
        return _provider_configuration.local_proxy_available(proxy_url)

    def env_flag_enabled(name: str, default: bool=True) -> bool:
        return _provider_configuration.env_flag_enabled(name, default)

    def ai_proxy_url_from_config(local: dict[str, Any], provider: str) -> tuple[str, str, bool]:
        return _provider_configuration.ai_proxy_url_from_config(local, provider)

    def validate_ai_timeout(value: Any) -> float:
        return _provider_configuration.validate_ai_timeout(value)

    def validate_image_generation_timeout(value: Any) -> float:
        return _provider_configuration.validate_image_generation_timeout(value)

    def validate_ai_key_env(value: Any) -> str:
        return _provider_configuration.validate_ai_key_env(value)

    def load_ai_local_config() -> dict[str, Any]:
        return _provider_configuration.load_ai_local_config()

    def ai_local_config_temp_path() -> Path:
        return _provider_configuration.ai_local_config_temp_path()

    def redact_status_payload_for_user(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        return _account_projections.redact_status_payload_for_user(payload, user)

    def redact_config_summary_for_user(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        return _account_projections.redact_config_summary_for_user(payload, user)

    def ai_detection_settings(purpose: str='pipeline') -> dict[str, Any]:
        return _model_profile_configuration.ai_detection_settings(purpose)

    def image_generation_settings() -> dict[str, Any]:
        return _model_profile_configuration.image_generation_settings()

    def public_ai_detection_status() -> dict[str, Any]:
        return _public_status_projection.public_ai_detection_status()

    def public_ai_detection_status_for_user(user: dict[str, Any] | None) -> dict[str, Any]:
        return _public_status_projection.public_ai_detection_status_for_user(user)

    def public_status_model_for_user(model: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
        return _public_status_projection.public_status_model_for_user(model, user)

    def public_image_generation_status() -> dict[str, Any]:
        return _public_status_projection.public_image_generation_status()

    def public_cursor_image2_status() -> dict[str, Any]:
        return ports._image_provider_configuration().public_cursor_image2_status()

    def list_training_tasks(user: dict[str, Any] | None=None, target_user_id: str | None=None, *, allow_remote_refresh: bool=False) -> list[dict[str, Any]]:
        return ports._training_state_workflows().list_training_tasks(user, target_user_id, allow_remote_refresh=allow_remote_refresh)

    def training_execution_status(*, include_worker_probe: bool=False, include_worker_services: bool=False) -> dict[str, Any]:
        return ports._training_executor_settings().training_execution_status(include_worker_probe=include_worker_probe, include_worker_services=include_worker_services)

    def list_trained_model_specs(config: dict[str, Any] | None=None) -> list[dict[str, Any]]:
        return ports._trained_model_catalog().list_trained_model_specs(config)

    def load_ai_detection_tasks() -> list[dict[str, Any]]:
        return ports._detection_task_store().load_ai_detection_tasks()

    def ai_detection_tasks_response(config: dict[str, Any], selected_id: str | None=None, *, user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
        return ports._detection_task_catalog().ai_detection_tasks_response(config, selected_id, user=user, target_user_id=target_user_id)

    def list_ai_detection_specialized_model_specs(config: dict[str, Any] | None=None, trained_specs: list[dict[str, Any]] | None=None, target_user_id: str | None=None) -> list[dict[str, Any]]:
        return ports._detection_task_catalog().list_ai_detection_specialized_model_specs(config, trained_specs, target_user_id)

    def selected_model_spec(model_id: str | None, config: dict[str, Any] | None=None) -> dict[str, Any]:
        return ports._model_selection().selected_model_spec(model_id, config)

    def model(model_id: str | None=None, config: dict[str, Any] | None=None) -> YOLO:
        return ports._local_models().model(model_id, config)

    def public_yolo_warmup_status(config: dict[str, Any]) -> dict[str, Any]:
        return ports._yolo_warmup_runtime().public_yolo_warmup_status(config)

    def training_resources_payload(*, include_samples: bool=False, user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
        return ports._training_resources().training_resources_payload(include_samples=include_samples, user=user, target_user_id=target_user_id)

    def agent_base_url_host(base_url: str) -> str:
        return _provider_configuration.agent_base_url_host(base_url)

    def is_cursor_base_url(base_url: str) -> bool:
        return _provider_configuration.is_cursor_base_url(base_url)

    def detect_agent_provider_from_base_url(base_url: str) -> str:
        return _provider_configuration.detect_agent_provider_from_base_url(base_url)

    def normalize_agent_provider(provider: str | None, base_url: str='') -> str:
        return _provider_configuration.normalize_agent_provider(provider, base_url)

    def agent_provider_label(provider: str) -> str:
        return _provider_configuration.agent_provider_label(provider)

    def normalize_agent_model_options(value: Any) -> list[dict[str, str]]:
        return _provider_configuration.normalize_agent_model_options(value)

    def normalize_agent_config(config: dict[str, Any]) -> dict[str, Any]:
        return _provider_configuration.normalize_agent_config(config)

    def load_pipeline_tasks() -> list[dict[str, Any]]:
        return ports._pipeline_task_store().load_pipeline_tasks()

    def react_production_spa_enabled() -> bool:
        return True

    _infrastructure = build_infrastructure(InfrastructureInputs(foundation=FoundationInputs(environment=environment, data_directory=values.DATA_DIR, auth_path=values.AUTH_PATH, legacy_owner=values.LEGACY_OWNER_ID, system_owner=values.SYSTEM_OWNER_ID, authentication=AuthenticationSettings(password_iterations=lambda iterations=values.PASSWORD_HASH_ITERATIONS: iterations, sessions=lambda cookie=values.AUTH_SESSION_COOKIE, ttl=values.AUTH_SESSION_TTL_SECONDS, persist=values.AUTH_SESSION_PERSIST_INTERVAL_SECONDS: SessionSettings(cookie, ttl, persist), login_limits=lambda window=values.LOGIN_RATE_LIMIT_WINDOW_SECONDS, attempts=values.LOGIN_RATE_LIMIT_MAX_ATTEMPTS, lockout=values.LOGIN_RATE_LIMIT_LOCKOUT_SECONDS: LoginLimitSettings(window, attempts, lockout), legacy_owner=lambda owner=values.LEGACY_OWNER_ID: owner), connector=connector), cv2=lambda: cv2, pil=lambda: Image, locations=PathConfigurationLocations(directories=lambda: (values.UPLOAD_DIR, values.OUTPUT_DIR, values.DATA_DIR, values.NORMALIZED_DIR, values.TRAINING_JOBS_DIR, values.TRAINING_TASKS_DIR, values.ACCESSORY_CANDIDATES_DIR, values.AUTO_OPTIMIZE_DIR, values.IMAGE_WORKER_LOG_DIR, values.BACKGROUND_DIR, values.BACKGROUND_SETS_DIR), primary=lambda: values.CONFIG_PATH, backup=lambda: values.CONFIG_BACKUP_PATH, data=lambda: values.DATA_DIR, migration_roots=lambda: (values.DATA_DIR, values.BACKGROUND_DIR, values.STANDARDIZED_MANUALS_DIR, values.PRECISE_MANUALS_DIR)), paths=ServicePathSettings(ROOT=lambda: values.ROOT, APP_DIR=lambda: values.APP_DIR, OUTPUT_DIR=lambda: values.OUTPUT_DIR), path_policy=PathProjectionPolicy(STALE_REPO_PATH_PREFIXES=lambda: values.STALE_REPO_PATH_PREFIXES, REMOVED_PHASE1_PUBLIC_CONFIG_KEYS=lambda: REMOVED_PHASE1_PUBLIC_CONFIG_KEYS, LEGACY_OWNER_ID=lambda: values.LEGACY_OWNER_ID, SYSTEM_OWNER_ID=lambda: values.SYSTEM_OWNER_ID), rows=ConfigurationRowCodecs(config_from_rows, app_config_rows, accessory_rows), defaults=lambda: values.DEFAULT_CONFIG, protected_keys=lambda: values.PLC_PROTECTED_CONFIG_KEYS, provider=ProviderConfigurationInputs(json_defaults=JsonDefaults(lambda: values.AI_DEFAULT_MODELS, lambda: values.AI_DEFAULT_MODEL, lambda: values.AI_DEFAULT_BASE_URLS, lambda: values.AI_DEFAULT_PROVIDER, lambda: values.AI_PROVIDER_LABELS), image_defaults=ImageDefaults(lambda: values.IMAGE_GENERATION_DEFAULT_MODELS, lambda: values.IMAGE_GENERATION_DEFAULT_BASE_URLS, lambda: values.IMAGE_GENERATION_DEFAULT_PROVIDER, lambda: values.IMAGE_GENERATION_DEFAULT_API_KEY_ENVS, lambda: values.IMAGE_GENERATION_API_KEY_ENV, lambda: values.IMAGE_GENERATION_PROVIDER_KEYS, lambda: values.IMAGE_GENERATION_PROVIDER_LABELS), validation_capabilities=ValidationCapabilities(lambda: values.AI_SUPPORTED_PROVIDERS, lambda: values.IMAGE_GENERATION_SUPPORTED_PROVIDERS, lambda: HTTPException, lambda: re.fullmatch, lambda: urlsplit), public_url_capabilities=PublicUrlCapabilities(lambda: urlsplit, lambda: urlunsplit, lambda: bounded_text), key_identity_runtime=_native_KeyIdentityRuntime_843(sha256=lambda: hashlib.sha256, time_ns=lambda: time.time_ns, substitute=lambda: re.sub, fullmatch=lambda: re.fullmatch, key_id=lambda: ai_key_id), secret_paths=_native_SecretPaths_843(directory=lambda: values.DATA_DIR, file=lambda: values.LOCAL_SECRET_ENV_PATH), secret_codec=_native_SecretCodec_843(loads=lambda: json.loads, dumps=lambda: json.dumps, decode_error=lambda: json.JSONDecodeError), secret_file_operations=_native_SecretFileOperations_843(chmod=lambda: os.chmod, replace=lambda: os.replace), secret_environment=_native_SecretEnvironment_843(values=lambda: environment), secret_policy=_native_SecretPolicy_843(fullmatch=lambda: re.fullmatch, validate=lambda: validate_ai_key_env, default_environment=lambda: default_secret_env_name, identity=lambda: secret_key_item_id, text=lambda: bounded_text), secret_store_access=_native_SecretStoreAccess_843(load=lambda: load_local_secret_env, save=lambda: save_local_secret_env, set=lambda: set_local_secret_env), key_material=_native_KeyMaterial_844(environment=lambda: local_secret_env_value, identity=lambda: secret_key_item_id, default_environment=lambda: default_secret_env_name), key_presentation=_native_KeyPresentation_844(text=lambda: bounded_text, mask=lambda: mask_secret, json_label=lambda: ai_provider_label, image_label=lambda: image_generation_provider_label, agent_label=lambda: agent_provider_label), json_key_policy=_native_JsonKeyPolicy_844(default_provider=lambda: values.AI_DEFAULT_PROVIDER, supported=lambda: values.AI_SUPPORTED_PROVIDERS), image_key_policy=_native_ImageKeyPolicy_844(default_provider=lambda: values.IMAGE_GENERATION_DEFAULT_PROVIDER, supported=lambda: values.IMAGE_GENERATION_SUPPORTED_PROVIDERS, validate=lambda: validate_image_generation_provider), agent_key_policy=_native_AgentKeyPolicy_844(supported=lambda: values.AGENT_SUPPORTED_PROVIDERS, normalize=lambda: normalize_agent_provider), proxy_settings=_native_ProxySettings_845(AI_PROXY_ENV_NAMES=lambda: values.AI_PROXY_ENV_NAMES, AI_LOCAL_PROXY_URL=lambda: AI_LOCAL_PROXY_URL, AI_AUTO_LOCAL_PROXY_ENV=lambda: values.AI_AUTO_LOCAL_PROXY_ENV), proxy_calls=_native_ProxyCalls_845(validate_ai_proxy_url=lambda: validate_ai_proxy_url, ai_proxy_url_from_environment=lambda: ai_proxy_url_from_environment, env_flag_enabled=lambda: env_flag_enabled, local_proxy_available=lambda: local_proxy_available), proxy_transports=_native_ProxyTransports_845(os=lambda: os, socket=lambda: socket, urllib=lambda: urllib), local_model_config_files=_native_LocalModelConfigFiles_846(ensure_dirs=lambda: ensure_dirs, _business_files=lambda: ports._business_files(), AI_LOCAL_CONFIG_PATH=lambda: values.AI_LOCAL_CONFIG_PATH, DATA_DIR=lambda: values.DATA_DIR, ai_local_config_temp_path=lambda: ai_local_config_temp_path, DEFAULT_AI_CONFIG=lambda: values.DEFAULT_AI_CONFIG, HTTPException=lambda: HTTPException), local_json_model_policy=_native_LocalJsonModelPolicy_846(AI_DEFAULT_PROVIDER=lambda: values.AI_DEFAULT_PROVIDER, AI_SUPPORTED_PROVIDERS=lambda: values.AI_SUPPORTED_PROVIDERS, AI_DEFAULT_TIMEOUT_SECONDS=lambda: values.AI_DEFAULT_TIMEOUT_SECONDS, default_ai_model=lambda: default_ai_model, default_ai_base_url=lambda: default_ai_base_url, validate_ai_proxy_url=lambda: validate_ai_proxy_url, validate_ai_timeout=lambda: validate_ai_timeout, normalize_ai_key_items=lambda: normalize_ai_key_items, ai_keys_for_provider=lambda: ai_keys_for_provider), local_image_model_policy=_native_LocalImageModelPolicy_846(IMAGE_GENERATION_DEFAULT_PROVIDER=lambda: values.IMAGE_GENERATION_DEFAULT_PROVIDER, IMAGE_GENERATION_SUPPORTED_PROVIDERS=lambda: values.IMAGE_GENERATION_SUPPORTED_PROVIDERS, IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS=lambda: values.IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS, default_image_generation_model=lambda: default_image_generation_model, default_image_generation_base_url=lambda: default_image_generation_base_url, validate_ai_base_url=lambda: validate_ai_base_url, validate_image_generation_timeout=lambda: validate_image_generation_timeout, normalize_image_key_items=lambda: normalize_image_key_items, image_keys_for_provider=lambda: image_keys_for_provider), legacy_settings_i_o=LegacySettingsIO(lambda: load_ai_local_config, lambda: environment, lambda: ai_proxy_url_from_config, lambda: validate_ai_base_url, lambda: HTTPException), legacy_presentation=LegacyPresentation(lambda: public_ai_key_items, lambda: mask_secret, lambda: public_ai_base_url, lambda: masked_url_for_status), legacy_json_policy=LegacyJsonPolicy(lambda: values.AI_DEFAULT_PROVIDER, lambda: values.AI_DEFAULT_MODEL, lambda: values.AI_DEFAULT_TIMEOUT_SECONDS, lambda: values.AI_MODEL_OPTIONS, lambda: values.AI_SUPPORTED_PROVIDERS, lambda: values.AI_AUTO_LOCAL_PROXY_ENV), legacy_json_callbacks=LegacyJsonCallbacks(lambda: default_ai_base_url, lambda: validate_ai_timeout, lambda: normalize_ai_key_items, lambda: ai_keys_for_provider, lambda: secret_key_item_id, lambda: bounded_text, lambda: ai_provider_label, lambda: env_flag_enabled), legacy_image_policy=LegacyImagePolicy(lambda: values.IMAGE_GENERATION_DEFAULT_PROVIDER, lambda: values.IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS, lambda: values.IMAGE_GENERATION_MODEL_OPTIONS, lambda: values.IMAGE_GENERATION_SUPPORTED_PROVIDERS), legacy_image_environment=LegacyImageEnvironment(lambda: values.IMAGE_GENERATION_PROVIDER_ENV, lambda: values.IMAGE_GENERATION_MODEL_ENV, lambda: values.IMAGE_GENERATION_BASE_URL_ENV, lambda: values.IMAGE_GENERATION_TIMEOUT_ENV, lambda: values.IMAGE_GENERATION_NAMED_API_KEY_ENV, lambda: values.IMAGE_GENERATION_API_KEY_ENV, lambda: values.AGENT_MCP_GEMINI_IMAGE_MODEL_ENV, lambda: values.AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV), legacy_image_callbacks=LegacyImageCallbacks(lambda: default_image_generation_model, lambda: default_image_generation_base_url, lambda: default_image_generation_api_key_env, lambda: validate_image_generation_timeout, lambda: normalize_image_key_items, lambda: image_keys_for_provider, lambda: image_generation_provider_label, lambda: image_generation_provider_key), agent_settings_defaults=_native_AgentSettingsDefaults_847(cursor=lambda: values.AGENT_PROVIDER_CURSOR, openai=lambda: values.AGENT_PROVIDER_OPENAI_COMPATIBLE, config=lambda: values.DEFAULT_AGENT_CONFIG, cursor_url=lambda: values.AGENT_CURSOR_DEFAULT_BASE_URL, statuses=lambda: values.AGENT_CONNECTION_STATUSES), agent_provider_policy=_native_AgentProviderPolicy_847(split_url=lambda: urlsplit, host=lambda: agent_base_url_host, is_cursor=lambda: is_cursor_base_url, detect=lambda: detect_agent_provider_from_base_url, normalize=lambda: normalize_agent_provider, options=lambda: normalize_agent_model_options), agent_settings_keys=_native_AgentSettingsKeys_847(validate_environment=lambda: validate_ai_key_env, normalize=lambda: normalize_agent_key_items, for_provider=lambda: agent_keys_for_provider, environment_value=lambda: local_secret_env_value), agent_settings_paths=_native_AgentSettingsPaths_847(file=lambda: values.AGENT_LOCAL_CONFIG_PATH, directory=lambda: values.DATA_DIR), agent_settings_codec=_native_AgentSettingsCodec_847(loads=lambda: json.loads, dumps=lambda: json.dumps, decode_error=lambda: json.JSONDecodeError), agent_settings_files=_native_AgentSettingsFiles_847(replace=lambda: os.replace, chmod=lambda: os.chmod), agent_settings_persistence=_native_AgentSettingsPersistence_847(normalize=lambda: normalize_agent_config, keys=lambda: normalize_agent_key_items, persist=lambda: persist_secret_key_items)), legacy_label=lambda: legacy_label_settings(), agent_defaults=lambda: values.DEFAULT_AGENT_CONFIG, cache_ttl=lambda: values.STORE_READ_CACHE_TTL_SECONDS, clock=lambda: time.monotonic()), artifacts=ports._artifact_composition())
    _foundation = _infrastructure.foundation
    _runtime_repository_owner = _foundation.repositories
    _runtime_repositories = _runtime_repository_owner.factory
    _runtime_repository_access = _runtime_repository_owner.access
    runtime_repository_cache_key = _runtime_repository_owner.cache_key
    _authentication_domain = _foundation.authentication
    _authentication = _authentication_domain.services
    _request_user = _authentication_domain.identity
    _password_hasher = _authentication.hasher
    password_hash = _password_hasher.password_hash
    _auth_repository = _authentication.repository
    load_auth_store = _auth_repository.load_auth_store
    save_auth_store = _auth_repository.save_auth_store
    save_auth_user = _auth_repository.save_auth_user
    delete_auth_user = _auth_repository.delete_auth_user
    save_auth_session = _auth_repository.save_auth_session
    delete_auth_session = _auth_repository.delete_auth_session
    delete_expired_auth_sessions = _auth_repository.delete_expired_auth_sessions
    delete_auth_sessions_for_user = _auth_repository.delete_auth_sessions_for_user
    save_login_session = _auth_repository.save_login_session
    save_auth_session_touch_or_prune = _auth_repository.save_auth_session_touch_or_prune
    _account_visibility = AccountVisibility(access=VisibilityAccess(current_auth_user=lambda: current_auth_user, user_is_admin=lambda: user_is_admin, user_has_permission=lambda: user_has_permission, record_mutable_by_user=lambda: record_mutable_by_user, record_visible_to_user=lambda: record_visible_to_user), configuration=VisibilityConfiguration(accessory_uid=lambda: accessory_uid, training_state_for_user=lambda: training_state_for_user, PLC_CAPTURE_RESULTS_KEY=lambda: values.PLC_CAPTURE_RESULTS_KEY, load_config=lambda: load_config), models=AccountModels(selected_model_spec=lambda: selected_model_spec, public_ai_detection_status_for_user=lambda: public_ai_detection_status_for_user), media=AccountMedia(OUTPUT_DIR=lambda: values.OUTPUT_DIR), origins=VisibilityOrigins(values=lambda: ports.CORS_ORIGINS(), regex=lambda: ports.CORS_ORIGIN_REGEX()), masked_url=lambda: _provider_configuration.masked_url_for_status)
    _public_network_policy = _account_visibility.network
    _account_service = _authentication.accounts
    _session_service = _authentication.sessions
    _access_control = _authentication.access
    users_exist = _account_service.users_exist
    create_auth_user = _account_service.create_auth_user
    bootstrap_admin_from_env = _account_service.bootstrap_admin_from_env
    set_session_cookie = _session_service.set_session_cookie
    clear_session_cookie = _session_service.clear_session_cookie
    create_session = _session_service.create_session
    create_login_session = _session_service.create_login_session
    set_user_password = _account_service.set_user_password
    authenticate_request = _session_service.authenticate_request
    current_auth_user = _access_control.current_auth_user
    require_admin_role = _access_control.require_admin_role
    _record_services = _foundation.records
    _record_ownership = _record_services.ownership
    _record_audit = _record_services.audit
    _record_access = _record_services.access
    record_owner_id = _record_ownership.record_owner_id
    current_owner_fields = _record_access.current_owner_fields
    owner_fields_for_new_record = _record_access.owner_fields_for_new_record
    record_owner_username = _record_ownership.record_owner_username
    record_audit_fields = _record_audit.record_audit_fields
    enrich_record_audit_fields = _record_audit.enrich_record_audit_fields
    record_matches_owner_filter = _record_ownership.record_matches_owner_filter
    record_visible_to_user = _record_ownership.record_visible_to_user
    record_mutable_by_user = _record_ownership.record_mutable_by_user
    _resource_names = ResourceNames(policy=NamePolicy(resource_name_key=lambda: resource_name_key, LEGACY_OWNER_ID=lambda: values.LEGACY_OWNER_ID, accessory_uid=lambda: accessory_uid, record_owner_id=lambda: record_owner_id, duplicate_name_error=lambda: duplicate_name_error, task_matches_excluded_identity=lambda: task_matches_excluded_identity, task_record_name=lambda: task_record_name), catalogs=NameCatalogs(load_pipeline_tasks=lambda: load_pipeline_tasks, load_ai_detection_tasks=lambda: load_ai_detection_tasks, training_resources_payload=lambda: training_resources_payload, list_trained_model_specs=lambda: list_trained_model_specs))
    _account_projections = _account_visibility.projections
    require_record_access = _record_access.require_record_access
    require_permission = _access_control.require_permission
    _login_limiter = _authentication.limits
    _login_rate_limit_lock = _login_limiter.lock
    _login_failures = _login_limiter.failures
    _login_blocked_until = _login_limiter.blocked_until
    prune_login_rate_limit_state = _login_limiter.prune_login_rate_limit_state
    enforce_login_rate_limit = _login_limiter.enforce_login_rate_limit
    record_failed_login_attempt = _login_limiter.record_failed_login_attempt
    clear_failed_login_attempts = _login_limiter.clear_failed_login_attempts
    _authentication_http = _authentication_domain.http(AuthenticationHttpPolicy(output_visible=_account_projections.output_path_visible_to_user, same_origin=_public_network_policy.same_origin, cors_origin_allowed=_public_network_policy.cors_origin_allowed))
    _documentation_access = _authentication_http.documentation
    require_docs_admin = _documentation_access.require_docs_admin
    _path_configuration = _infrastructure.paths
    _service_directories = _path_configuration.directories
    ensure_dirs = _service_directories.ensure
    _app_configuration = _path_configuration.configuration
    _app_config_store = _app_configuration.store
    _config_io_lock = _app_configuration.lock
    save_app_config = _app_configuration.save_app_config
    mutate_app_config_atomically = _app_configuration.mutate_app_config_atomically
    _service_paths = _path_configuration.paths
    _local_path_migration = _path_configuration.migration
    migrate_persisted_local_paths_once = _local_path_migration.run
    _accessory_image_io = ImageFiles(lambda: cv2, files=ports._business_files())
    _file_digest = FileDigest(files=lambda: ports._business_files())
    _provider_configuration = _infrastructure.provider
    _provider_configuration_defaults = _provider_configuration.defaults
    _provider_configuration_validation = _provider_configuration.validation
    _provider_public_urls = _provider_configuration.public_urls
    _key_identity = _provider_configuration.identity
    _local_secret_store = _provider_configuration.secrets
    _provider_key_registry = _provider_configuration.keys
    _provider_proxy_runtime = _provider_configuration.proxy
    _local_model_config = _provider_configuration.local
    _request_read_cache = _infrastructure.caches.request
    _read_path_cache = _request_read_cache.current
    read_path_cache_scope = _request_read_cache.scope
    _store_cache = _infrastructure.caches.store
    store_read_cache_get = _store_cache.get
    store_read_cache_put = _store_cache.put
    store_read_cache_invalidate = _store_cache.invalidate
    _json_cache = _infrastructure.caches.json
    load_json_file_mtime_cached = _json_cache.load
    _legacy_json_settings_service = _provider_configuration.legacy_json
    _legacy_image_settings_service = _provider_configuration.legacy_image
    _public_status_projection = PublicStatusProjection(StatusPolicy(lambda: user_is_admin, lambda: user_has_permission, lambda: values.STATUS_MODEL_PUBLIC_KEYS, lambda: public_path_sanitized), StatusSources(lambda: ai_detection_settings, lambda: image_generation_settings), StatusProjectionCalls(lambda: public_ai_detection_status, lambda: public_image_generation_status, lambda: public_status_model_for_user, lambda: public_ai_detection_status_for_user))
    _background_image_io = ImageFiles(lambda: cv2, files=ports._business_files())
    _training_image_io = ImageFiles(lambda: cv2, files=ports._business_files())
    _user_service = _authentication.users
    _auth_flows = _authentication.flows
    _web_shell = WebShell(production_dist=lambda: values.REACT_PRODUCTION_DIST_DIR, exists=lambda path: ports._business_files().exists(path), route_segments=lambda: values.REACT_PRODUCTION_ROUTE_SEGMENTS, blocked_prefixes=lambda: values.REACT_PRODUCTION_BLOCKED_PREFIXES, enabled=lambda: react_production_spa_enabled())
    index = _web_shell.index
    legacy_index = _web_shell.legacy_index
    react_preview = _web_shell.react_preview
    _service_status_requests = ServiceStatusRequests(access=StatusRequestAccess(current_auth_user=lambda: current_auth_user, user_is_admin=lambda: user_is_admin, scope_config_for_user=lambda: scope_config_for_user, record_visible_to_user=lambda: record_visible_to_user, user_has_permission=lambda: user_has_permission, redact_status_payload_for_user=lambda: redact_status_payload_for_user, redact_config_summary_for_user=lambda: redact_config_summary_for_user, public_path_sanitized=lambda: public_path_sanitized), catalog=StatusRequestCatalog(load_config=lambda: load_config, selected_model_spec=lambda: selected_model_spec, accessory_uid=lambda: accessory_uid, list_training_tasks=lambda: list_training_tasks, list_trained_model_specs=lambda: list_trained_model_specs, legacy_model_specs=lambda: legacy_model_specs, list_ai_detection_specialized_model_specs=lambda: list_ai_detection_specialized_model_specs, ai_detection_tasks_response=lambda: ai_detection_tasks_response, _business_files=lambda: ports._business_files()), runtime=StatusRequestRuntime(public_ai_detection_status=lambda: public_ai_detection_status, record_owner_username=lambda: record_owner_username, LEGACY_OWNER_ID=lambda: values.LEGACY_OWNER_ID, training_execution_status=lambda: training_execution_status, public_cursor_image2_status=lambda: public_cursor_image2_status, public_yolo_warmup_status=lambda: public_yolo_warmup_status, CLASS_LABELS=lambda: values.CLASS_LABELS, CLASS_NAMES=lambda: values.CLASS_NAMES))
    _stream_configuration = StreamConfiguration(lambda: load_config(), lambda config: save_config(config))
    _agent_settings_policy = _provider_configuration.agent_policy
    _legacy_agent_settings_store = _provider_configuration.legacy_agent
    _agent_pil_images = ImageFiles(pil_provider=lambda: Image, files=ports._business_files())
    _incoming_image_files = ImageFiles(lambda: cv2, files=ports._business_files())
    _model_profile_configuration = _infrastructure.models
    model_profile_service = _model_profile_configuration.service
    react_production_spa = _web_shell.react_production_spa
    return InfrastructureAssembly(
        _access_control=_access_control,
        _accessory_image_io=_accessory_image_io,
        _account_projections=_account_projections,
        _account_service=_account_service,
        _account_visibility=_account_visibility,
        _agent_pil_images=_agent_pil_images,
        _agent_settings_policy=_agent_settings_policy,
        _app_config_store=_app_config_store,
        _app_configuration=_app_configuration,
        _auth_flows=_auth_flows,
        _auth_repository=_auth_repository,
        _authentication=_authentication,
        _authentication_domain=_authentication_domain,
        _authentication_http=_authentication_http,
        _background_image_io=_background_image_io,
        _config_io_lock=_config_io_lock,
        _documentation_access=_documentation_access,
        _file_digest=_file_digest,
        _foundation=_foundation,
        _incoming_image_files=_incoming_image_files,
        _infrastructure=_infrastructure,
        _json_cache=_json_cache,
        _key_identity=_key_identity,
        _legacy_agent_settings_store=_legacy_agent_settings_store,
        _legacy_image_settings_service=_legacy_image_settings_service,
        _legacy_json_settings_service=_legacy_json_settings_service,
        _local_model_config=_local_model_config,
        _local_path_migration=_local_path_migration,
        _local_secret_store=_local_secret_store,
        _login_blocked_until=_login_blocked_until,
        _login_failures=_login_failures,
        _login_limiter=_login_limiter,
        _login_rate_limit_lock=_login_rate_limit_lock,
        _model_profile_configuration=_model_profile_configuration,
        _password_hasher=_password_hasher,
        _path_configuration=_path_configuration,
        _provider_configuration=_provider_configuration,
        _provider_configuration_defaults=_provider_configuration_defaults,
        _provider_configuration_validation=_provider_configuration_validation,
        _provider_key_registry=_provider_key_registry,
        _provider_proxy_runtime=_provider_proxy_runtime,
        _provider_public_urls=_provider_public_urls,
        _public_network_policy=_public_network_policy,
        _public_status_projection=_public_status_projection,
        _read_path_cache=_read_path_cache,
        _record_access=_record_access,
        _record_audit=_record_audit,
        _record_ownership=_record_ownership,
        _record_services=_record_services,
        _request_read_cache=_request_read_cache,
        _request_user=_request_user,
        _resource_names=_resource_names,
        _runtime_repositories=_runtime_repositories,
        _runtime_repository_access=_runtime_repository_access,
        _runtime_repository_owner=_runtime_repository_owner,
        _service_directories=_service_directories,
        _service_paths=_service_paths,
        _service_status_requests=_service_status_requests,
        _session_service=_session_service,
        _store_cache=_store_cache,
        _stream_configuration=_stream_configuration,
        _training_image_io=_training_image_io,
        _user_service=_user_service,
        _web_shell=_web_shell,
        authenticate_request=authenticate_request,
        bootstrap_admin_from_env=bootstrap_admin_from_env,
        clear_failed_login_attempts=clear_failed_login_attempts,
        clear_session_cookie=clear_session_cookie,
        create_auth_user=create_auth_user,
        create_login_session=create_login_session,
        create_session=create_session,
        current_auth_user=current_auth_user,
        current_owner_fields=current_owner_fields,
        delete_auth_session=delete_auth_session,
        delete_auth_sessions_for_user=delete_auth_sessions_for_user,
        delete_auth_user=delete_auth_user,
        delete_expired_auth_sessions=delete_expired_auth_sessions,
        enforce_login_rate_limit=enforce_login_rate_limit,
        enrich_record_audit_fields=enrich_record_audit_fields,
        ensure_dirs=ensure_dirs,
        index=index,
        legacy_index=legacy_index,
        load_auth_store=load_auth_store,
        load_json_file_mtime_cached=load_json_file_mtime_cached,
        migrate_persisted_local_paths_once=migrate_persisted_local_paths_once,
        model_profile_service=model_profile_service,
        mutate_app_config_atomically=mutate_app_config_atomically,
        owner_fields_for_new_record=owner_fields_for_new_record,
        password_hash=password_hash,
        prune_login_rate_limit_state=prune_login_rate_limit_state,
        react_preview=react_preview,
        react_production_spa=react_production_spa,
        read_path_cache_scope=read_path_cache_scope,
        record_audit_fields=record_audit_fields,
        record_failed_login_attempt=record_failed_login_attempt,
        record_matches_owner_filter=record_matches_owner_filter,
        record_mutable_by_user=record_mutable_by_user,
        record_owner_id=record_owner_id,
        record_owner_username=record_owner_username,
        record_visible_to_user=record_visible_to_user,
        require_admin_role=require_admin_role,
        require_docs_admin=require_docs_admin,
        require_permission=require_permission,
        require_record_access=require_record_access,
        runtime_repository_cache_key=runtime_repository_cache_key,
        save_app_config=save_app_config,
        save_auth_session=save_auth_session,
        save_auth_session_touch_or_prune=save_auth_session_touch_or_prune,
        save_auth_store=save_auth_store,
        save_auth_user=save_auth_user,
        save_login_session=save_login_session,
        set_session_cookie=set_session_cookie,
        set_user_password=set_user_password,
        store_read_cache_get=store_read_cache_get,
        store_read_cache_invalidate=store_read_cache_invalidate,
        store_read_cache_put=store_read_cache_put,
        users_exist=users_exist,
    )
