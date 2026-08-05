"""Disabled-default runtime datastore selector.

This module is intentionally side-effect free on import. It does not connect to
PostgreSQL unless `VANTALINE_DATA_STORE=postgres` is explicitly selected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .postgres_runtime_repository import PostgresRuntimeRepository


DATA_STORE_ENV = "VANTALINE_DATA_STORE"
DATABASE_URL_ENV = "DATABASE_URL"
JSON_STORE = "json"
POSTGRES_STORE = "postgres"
VALID_DATA_STORES = frozenset({JSON_STORE, POSTGRES_STORE})


class RuntimeStoreConfigError(RuntimeError):
    """Raised when the datastore environment is invalid."""


class RuntimeStoreConnectionError(RuntimeError):
    """Raised when PostgreSQL was explicitly selected but cannot connect."""


class PostgresConnector(Protocol):
    def __call__(self, database_url: str) -> Any:
        """Return a PostgreSQL connection for `database_url`."""


@dataclass(frozen=True)
class JsonRuntimeRepository:
    """Placeholder JSON runtime repository.

    HTTP runtime integration remains a later gate. Keeping this object small
    makes the selector testable without changing endpoint behavior.
    """

    kind: str = JSON_STORE


@dataclass(frozen=True)
class RuntimeRepositorySelection:
    store: str
    repository: JsonRuntimeRepository | PostgresRuntimeRepository


def selected_data_store(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    value = str(source.get(DATA_STORE_ENV, "") or "").strip().lower() or JSON_STORE
    if value not in VALID_DATA_STORES:
        raise RuntimeStoreConfigError(f"{DATA_STORE_ENV} must be one of: json, postgres")
    return value


def redact_database_url(database_url: str) -> str:
    """Return a URL safe for reports and exception messages."""

    if not database_url:
        return ""
    try:
        parts = urlsplit(database_url)
    except Exception:
        return "<redacted-database-url>"
    if not parts.scheme:
        return "<redacted-database-url>"

    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}" if host else f":{parts.port}"
    if parts.username or parts.password:
        netloc = f"<credentials>@{host}" if host else "<credentials>"
    else:
        netloc = parts.netloc

    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    safe_query: list[tuple[str, str]] = []
    for key, value in query_pairs:
        if any(marker in key.lower() for marker in ("pass", "password", "secret", "token", "key")):
            safe_query.append((key, "<redacted>"))
        else:
            safe_query.append((key, value))
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(safe_query), ""))


def default_postgres_connector(database_url: str) -> Any:
    """Connect with an installed PostgreSQL driver.

    The current repository does not vendor a driver. This function is called
    only when PostgreSQL is explicitly selected, so JSON runtime does not depend
    on driver availability.
    """

    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        psycopg = None  # type: ignore[assignment]
    if psycopg is not None:
        return psycopg.connect(database_url)

    try:
        import psycopg2  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        psycopg2 = None  # type: ignore[assignment]
    if psycopg2 is not None:
        return psycopg2.connect(database_url)

    raise RuntimeStoreConfigError(
        "PostgreSQL datastore was requested, but no supported PostgreSQL Python driver is installed"
    )


def build_runtime_repository(
    *,
    env: Mapping[str, str] | None = None,
    postgres_connector: PostgresConnector | None = None,
) -> RuntimeRepositorySelection:
    store = selected_data_store(env)
    if store == JSON_STORE:
        return RuntimeRepositorySelection(store=JSON_STORE, repository=JsonRuntimeRepository())

    source = os.environ if env is None else env
    database_url = str(source.get(DATABASE_URL_ENV, "") or "").strip()
    if not database_url:
        raise RuntimeStoreConfigError(f"{DATA_STORE_ENV}=postgres requires {DATABASE_URL_ENV}")

    connector = postgres_connector or default_postgres_connector
    redacted_url = redact_database_url(database_url)
    try:
        connection = connector(database_url)
    except RuntimeStoreConfigError:
        raise
    except Exception as exc:
        raise RuntimeStoreConnectionError(
            "PostgreSQL datastore connection failed for "
            f"{DATABASE_URL_ENV}={redacted_url}; no JSON fallback was used ({type(exc).__name__})"
        ) from None
    return RuntimeRepositorySelection(
        store=POSTGRES_STORE,
        repository=PostgresRuntimeRepository(connection=connection, database_url_redacted=redacted_url),
    )
