"""Existing model registry and secret-reader composition for the label process."""
import json
import os
from pathlib import Path
import re

from ..model_profiles.service import Service
from ..model_profiles.dependencies import ProfileDependencies
from ..model_providers.local_secret_store import LocalSecretStore
from ..model_providers.key_material_ports import (SecretPaths, SecretCodec, SecretFileOperations,
    SecretEnvironment, SecretPolicy, SecretStoreAccess)
from ..runtime.label_identity import RuntimeUnavailable
from .dependencies import RepositoryLifecycle


def _unavailable(*args, **kwargs):
    raise RuntimeUnavailable("Label runtime cannot initialize or change model configuration")


class ExistingModelProfiles(Service):
    """Reuse version/snapshot resolution, but never migrate legacy Web settings."""
    def initialize(self):
        repository = self.repository()
        with repository.read_tx() as cursor:
            if repository.state(cursor) is None:
                raise RuntimeUnavailable("Model profile registry is not initialized")


def create_models(repositories: RepositoryLifecycle, data_directory: Path, environment=None):
    environment = os.environ if environment is None else environment
    secrets = LocalSecretStore(
        SecretPaths(directory=lambda: data_directory, file=lambda: data_directory / "runtime_secrets.local.env"),
        SecretCodec(loads=lambda: json.loads, dumps=lambda: json.dumps, decode_error=lambda: json.JSONDecodeError),
        SecretFileOperations(chmod=lambda: _unavailable, replace=lambda: _unavailable),
        SecretEnvironment(values=lambda: environment),
        SecretPolicy(fullmatch=lambda: re.fullmatch, validate=lambda: _unavailable,
            default_environment=lambda: _unavailable, identity=lambda: _unavailable, text=lambda: _unavailable),
        SecretStoreAccess(load=lambda: secrets.load_local_secret_env, save=lambda: _unavailable, set=lambda: _unavailable),
    )
    return ExistingModelProfiles(ProfileDependencies(
        runtime_repository=repositories.repository, read_secret=secrets.local_secret_env_value,
        write_secret=_unavailable, legacy_sources=_unavailable, validate_model=_unavailable,
        validate_base_url=_unavailable, mask_secret=_unavailable))
