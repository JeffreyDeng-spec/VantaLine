"""Construct only repository, authentication and record owners for one app."""
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from .repository_composition import RuntimeRepositories
from ..auth.application import AuthenticationDomain
from ..auth.composition import AuthenticationSettings, AuthenticationStorage
from ..auth.policy import find_user
from ..records.composition import RecordServices
from ..storage.runtime_selector import PostgresConnector


@dataclass(frozen=True)
class FoundationInputs:
    environment: Mapping[str, str]
    data_directory: Path
    auth_path: Path
    authentication: AuthenticationSettings
    legacy_owner: str
    system_owner: str
    connector: PostgresConnector | None = None


@dataclass(frozen=True)
class ApplicationFoundation:
    repositories: RuntimeRepositories
    authentication: AuthenticationDomain
    records: RecordServices


def build_foundation(inputs: FoundationInputs) -> ApplicationFoundation:
    """Allocate independent owners without files, connections, routes or workers.

    Environment and settings suppliers remain live inputs. Callers building
    isolated configurations must supply distinct mutable environment mappings.
    """
    repositories = RuntimeRepositories(inputs.environment, connector=inputs.connector)
    authentication = AuthenticationDomain(
        storage=AuthenticationStorage(
            directory=lambda: inputs.data_directory,
            path=lambda: inputs.auth_path,
            repository=repositories.access.runtime_postgres_repository_or_none,
        ),
        settings=inputs.authentication,
    )
    records = RecordServices(
        identity=authentication.identity,
        legacy_owner=inputs.legacy_owner,
        system_owner=inputs.system_owner,
        current_user=authentication.services.access.current_auth_user,
        find_user=lambda target, load=authentication.services.repository.load_auth_store, find=find_user: find(load(), target),
    )
    return ApplicationFoundation(repositories, authentication, records)
