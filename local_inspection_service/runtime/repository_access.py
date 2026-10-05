"""HTTP-safe repository selection and administrative probe projection."""
from collections.abc import Callable, Mapping
from typing import Any, Protocol
import hashlib
import os
import threading
from fastapi import HTTPException
from ..storage.runtime_selector import RuntimeStoreConfigError, RuntimeStoreConnectionError


class ProbeRepository(Protocol):
    kind: str
    def count_rows(self, tables: tuple[str, ...]) -> Mapping[str, int]: ...


class RepositorySelection(Protocol):
    store: str
    repository: ProbeRepository


class RepositoryFactory(Protocol):
    def selection(self) -> RepositorySelection: ...


def runtime_repository_connection_probe_id(repository: Any) -> str:
    """Return a non-secret process-local fingerprint for the repository connection."""

    connection = getattr(repository, "connection", None)
    if connection is None:
        return ""
    material = f"{os.getpid()}:{threading.get_ident()}:{id(connection)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


class RuntimeRepositoryAccess:
    def __init__(self, *, factory: Callable[[], RepositoryFactory],
                 selection: Callable[[], Callable[[], RepositorySelection]],
                 probe_id: Callable[[], Callable[[ProbeRepository], str]],
                 postgres_store: Callable[[], str]) -> None:
        self.factory, self.selection = factory, selection
        self.probe_id, self.postgres_store = probe_id, postgres_store

    def runtime_repository_selection(self) -> Any:
        """Build the explicit runtime repository selection with HTTP-safe errors."""

        try:
            return self.factory().selection()
        except RuntimeStoreConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "runtime_store_config_error",
                    "message": str(exc),
                    "json_fallback_used": False,
                },
            ) from None
        except RuntimeStoreConnectionError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "runtime_store_connection_error",
                    "message": str(exc),
                    "json_fallback_used": False,
                },
            ) from None


    def runtime_postgres_repository_or_none(self) -> Any | None:
        """Return the explicit PostgreSQL repository, or None for JSON runtime."""

        selection = self.selection()()
        if selection.store == self.postgres_store():
            return selection.repository
        return None


    def runtime_store_probe_payload(self) -> dict[str, Any]:
        """Return a non-secret runtime-store probe for an admin HTTP endpoint."""

        selection = self.selection()()
        payload: dict[str, Any] = {
            "store": selection.store,
            "repository_kind": selection.repository.kind,
            "json_fallback_used": False,
            "repository_connection_id": None,
            "repository_connection_scope": None,
        }
        if selection.store == self.postgres_store():
            try:
                counts = selection.repository.count_rows(("schema_migrations",))
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "runtime_store_probe_error",
                        "message": type(exc).__name__,
                        "json_fallback_used": False,
                    },
                ) from None
            payload["postgres_count_probe"] = {"schema_migrations": counts.get("schema_migrations", 0)}
            payload["repository_connection_id"] = self.probe_id()(selection.repository)
            payload["repository_connection_scope"] = "thread-local"
        else:
            payload["postgres_count_probe"] = None
        return payload
