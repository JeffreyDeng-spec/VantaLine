"""Per-application connection factory and HTTP repository access ownership."""
from collections.abc import Mapping
from typing import Any
from .connections import ThreadRepositoryFactory
from .repository_access import RuntimeRepositoryAccess, runtime_repository_connection_probe_id
from ..storage.runtime_selector import POSTGRES_STORE, PostgresConnector, build_runtime_repository


class RuntimeRepositories:
    """Construction is inert; environment values remain operation-time inputs."""
    def __init__(self, environment: Mapping[str, str], *, connector: PostgresConnector | None = None):
        self.environment = environment
        self.connector = connector
        self.factory = ThreadRepositoryFactory(self._create, self.cache_key)
        self.access = RuntimeRepositoryAccess(
            factory=lambda: self.factory,
            selection=lambda: self.access.runtime_repository_selection,
            probe_id=lambda: runtime_repository_connection_probe_id,
            postgres_store=lambda: POSTGRES_STORE,
        )

    def cache_key(self) -> tuple[str, str, int | None]:
        return (
            self.environment.get("VANTALINE_DATA_STORE", "").strip().lower() or "json",
            self.environment.get("DATABASE_URL", "").strip(),
            id(self.connector) if self.connector is not None else None,
        )

    def _create(self) -> Any:
        return build_runtime_repository(env=self.environment, postgres_connector=self.connector)
