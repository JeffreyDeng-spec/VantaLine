#!/usr/bin/env python3
"""Smoke tests for the disabled-default runtime datastore selector."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.storage.runtime_selector import (  # noqa: E402
    DATABASE_URL_ENV,
    DATA_STORE_ENV,
    JSON_STORE,
    POSTGRES_STORE,
    JsonRuntimeRepository,
    PostgresRuntimeRepository,
    RuntimeStoreConfigError,
    RuntimeStoreConnectionError,
    build_runtime_repository,
    redact_database_url,
)


class MockConnector:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def __call__(self, database_url: str) -> object:
        self.calls.append(database_url)
        if self.fail:
            raise RuntimeError(f"cannot connect to {database_url}")
        return {"connected_to": database_url}


def assert_default_json_does_not_connect() -> None:
    connector = MockConnector()
    selection = build_runtime_repository(env={}, postgres_connector=connector)
    if selection.store != JSON_STORE or not isinstance(selection.repository, JsonRuntimeRepository):
        raise AssertionError(f"expected default JSON selection, got {selection}")
    if connector.calls:
        raise AssertionError(f"default JSON selection must not initialize PostgreSQL: {connector.calls}")

    selection = build_runtime_repository(
        env={DATA_STORE_ENV: "json", DATABASE_URL_ENV: "postgresql://user:secret@example.local/vantaline"},
        postgres_connector=connector,
    )
    if selection.store != JSON_STORE or connector.calls:
        raise AssertionError("explicit JSON selection must ignore DATABASE_URL and not connect")


def assert_postgres_is_explicit_and_uses_connector() -> None:
    connector = MockConnector()
    raw_url = "postgresql://user:secret@example.local:5432/vantaline?sslmode=require&password=secret2"
    selection = build_runtime_repository(
        env={DATA_STORE_ENV: POSTGRES_STORE, DATABASE_URL_ENV: raw_url},
        postgres_connector=connector,
    )
    if selection.store != POSTGRES_STORE or not isinstance(selection.repository, PostgresRuntimeRepository):
        raise AssertionError(f"expected postgres selection, got {selection}")
    if connector.calls != [raw_url]:
        raise AssertionError(f"postgres connector call mismatch: {connector.calls}")
    redacted = selection.repository.database_url_redacted
    if "secret" in redacted or "secret2" in redacted:
        raise AssertionError(f"redacted url leaked a secret: {redacted}")
    if "<credentials>" not in redacted or "password=%3Credacted%3E" not in redacted:
        raise AssertionError(f"redacted url did not mark credentials/query secret: {redacted}")


def assert_invalid_config_fails() -> None:
    try:
        build_runtime_repository(env={DATA_STORE_ENV: "sqlite"})
    except RuntimeStoreConfigError as exc:
        if DATA_STORE_ENV not in str(exc):
            raise AssertionError(f"config error should identify env var: {exc}") from exc
    else:
        raise AssertionError("invalid datastore value must fail")

    try:
        build_runtime_repository(env={DATA_STORE_ENV: POSTGRES_STORE})
    except RuntimeStoreConfigError as exc:
        if DATABASE_URL_ENV not in str(exc):
            raise AssertionError(f"missing database url error should identify env var: {exc}") from exc
    else:
        raise AssertionError("postgres selection without DATABASE_URL must fail")


def assert_postgres_failure_is_fail_closed_and_redacted() -> None:
    raw_url = "postgresql://user:super-secret@example.local/vantaline?connect_timeout=2"
    try:
        build_runtime_repository(
            env={DATA_STORE_ENV: POSTGRES_STORE, DATABASE_URL_ENV: raw_url},
            postgres_connector=MockConnector(fail=True),
        )
    except RuntimeStoreConnectionError as exc:
        message = str(exc)
        if "super-secret" in message or raw_url in message:
            raise AssertionError(f"connection failure leaked raw DATABASE_URL: {message}") from exc
        if "no JSON fallback was used" not in message:
            raise AssertionError(f"connection failure must explicitly fail closed: {message}") from exc
    else:
        raise AssertionError("failing postgres connector must not return a JSON fallback")


def assert_redaction_handles_peer_url() -> None:
    redacted = redact_database_url("postgresql:///vantaline?host=/var/run/postgresql&user=vantaline")
    if "vantaline" not in redacted or "host=%2Fvar%2Frun%2Fpostgresql" not in redacted:
        raise AssertionError(f"peer-auth URL should preserve non-secret routing fields: {redacted}")


def main() -> None:
    assert_default_json_does_not_connect()
    assert_postgres_is_explicit_and_uses_connector()
    assert_invalid_config_fails()
    assert_postgres_failure_is_fail_closed_and_redacted()
    assert_redaction_handles_peer_url()
    print("runtime store selector smoke passed")


if __name__ == "__main__":
    main()
