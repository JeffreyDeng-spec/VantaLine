"""Allocate application infrastructure; only the application assembler consumes this result."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .application_foundation import ApplicationFoundation, FoundationInputs, build_foundation
from .path_configuration_composition import PathConfigurationLocations, PathConfigurationWorkflows
from .read_caches import JsonFileReadCache, RequestReadCache, StoreReadCache
from .service_path_ports import PathIdentity, PathProjectionPolicy, ServicePathSettings
from ..auth.policy import user_is_admin
from ..config.app_store_ports import AppConfigRows
from ..model_profiles.composition import ModelConfiguration
from ..model_providers.configuration_composition import ProviderConfiguration
from ..model_providers.configuration_inputs import ProviderConfigurationInputs
from ..storage.artifacts.composition import ArtifactComposition, create_artifact_composition
from ..storage.artifacts.runtime import RuntimeBuilder

Record = dict[str, Any]


@dataclass(frozen=True)
class ConfigurationRowCodecs:
    config: Callable[[list[Record], list[Record]], Record]
    settings: Callable[..., list[Record]]
    accessories: Callable[[Record], list[Record]]


@dataclass(frozen=True)
class InfrastructureInputs:
    foundation: FoundationInputs
    cv2: Callable[[], Any]
    pil: Callable[[], Any]
    locations: PathConfigurationLocations
    paths: ServicePathSettings
    path_policy: PathProjectionPolicy
    rows: ConfigurationRowCodecs
    defaults: Callable[[], Record]
    protected_keys: Callable[[], tuple[str, ...]]
    provider: ProviderConfigurationInputs
    legacy_label: Callable[[], Record]
    agent_defaults: Callable[[], Record]
    cache_ttl: Callable[[], float]
    clock: Callable[[], float]
    artifact_builder: RuntimeBuilder | None = None


@dataclass(frozen=True)
class InfrastructureReadCaches:
    request: RequestReadCache
    store: StoreReadCache
    json: JsonFileReadCache


@dataclass(frozen=True)
class ApplicationInfrastructure:
    """Assembly handles, never a dependency passed wholesale to business services."""
    foundation: ApplicationFoundation
    artifacts: ArtifactComposition
    paths: PathConfigurationWorkflows
    provider: ProviderConfiguration
    models: ModelConfiguration
    caches: InfrastructureReadCaches


def build_infrastructure(inputs: InfrastructureInputs, *, artifacts: ArtifactComposition | None = None) -> ApplicationInfrastructure:
    """Construct fresh inert owners; initialization and lifecycle belong to the caller.

    No supplier, file, repository, secret, route or worker is selected here.
    Environment mappings and policy suppliers remain the explicit live inputs.
    Repository acquisition occurs later inside its native thread scope.
    """
    foundation = build_foundation(inputs.foundation)
    if artifacts is None:
        artifacts = create_artifact_composition(
            lambda: inputs.foundation.environment, inputs.cv2, inputs.pil,
            builder=inputs.artifact_builder)
    paths = PathConfigurationWorkflows(
        locations=inputs.locations, settings=inputs.paths, path_policy=inputs.path_policy,
        identity=PathIdentity(
            _request_user=lambda: foundation.authentication.identity,
            user_is_admin=lambda: user_is_admin),
        files=lambda: artifacts.files,
        rows=AppConfigRows(
            runtime_postgres_repository_or_none=lambda: foundation.repositories.access.runtime_postgres_repository_or_none,
            config_from_rows=lambda: inputs.rows.config,
            app_config_rows=lambda: inputs.rows.settings,
            accessory_rows=lambda: inputs.rows.accessories),
        defaults=inputs.defaults, protected_keys=inputs.protected_keys)
    provider = inputs.provider.build(files=artifacts.files, ensure_dirs=paths.ensure_dirs)
    models = provider.create_model_configuration(
        runtime_repository=lambda: foundation.repositories.access.runtime_postgres_repository_or_none(),
        legacy_label=inputs.legacy_label, agent_defaults=inputs.agent_defaults)
    caches = InfrastructureReadCaches(
        RequestReadCache(), StoreReadCache(inputs.cache_ttl, inputs.clock),
        JsonFileReadCache(lambda: artifacts.files))
    return ApplicationInfrastructure(foundation, artifacts, paths, provider, models, caches)
