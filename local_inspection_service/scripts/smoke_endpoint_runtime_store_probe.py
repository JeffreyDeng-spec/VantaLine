#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = Path(tempfile.mkdtemp(prefix="vantaline_runtime_probe_smoke_"))
(TMP_ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
(TMP_ROOT / "local_inspection_service" / "data").mkdir(parents=True, exist_ok=True)
(TMP_ROOT / "local_inspection_service" / "data" / "config.json").write_text("{}", encoding="utf-8")
os.environ["LOCAL_INSPECTION_ROOT"] = str(TMP_ROOT)
os.environ["VANTALINE_YOLO_PREWARM"] = "0"
os.environ["INSPECTION_WORKER_WATCHER"] = "0"
os.environ["LOCAL_INSPECTION_AUTO_RESUME_WORKER"] = "0"
os.environ.setdefault("MPLCONFIGDIR", str(TMP_ROOT / "matplotlib"))
os.environ.pop("VANTALINE_DATA_STORE", None)
os.environ.pop("DATABASE_URL", None)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException  # noqa: E402
from local_inspection_service import server  # noqa: E402


class RecordingConnector:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def __call__(self, database_url: str) -> object:
        self.calls.append(database_url)
        if self.fail:
            raise RuntimeError(f"cannot connect to {database_url}")
        return object()


class CloseTrackingConnection:
    def __init__(self, label: str) -> None:
        self.label = label
        self.closed = False
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True


class CloseTrackingConnector:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.connections: list[CloseTrackingConnection] = []

    def __call__(self, database_url: str) -> CloseTrackingConnection:
        self.calls.append(database_url)
        connection = CloseTrackingConnection(label=f"connection-{len(self.connections) + 1}")
        self.connections.append(connection)
        return connection


def bootstrap_admin() -> None:
    store = server.empty_auth_store()
    user = server.create_auth_user(
        store,
        username="runtime_probe_admin",
        password="runtime-probe-password",
        display_name="Runtime Probe",
        role="admin",
        permissions=sorted(server.FEATURE_PERMISSIONS),
    )
    server.create_login_session(store, user)
    server.save_auth_store(store)


def assert_json_default_probe_does_not_connect() -> None:
    os.environ.pop("VANTALINE_DATA_STORE", None)
    os.environ.pop("DATABASE_URL", None)
    connector = RecordingConnector()
    server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = connector
    try:
        bootstrap_admin()
        payload = server.runtime_store_probe_payload()
        if payload.get("store") != "json" or payload.get("repository_kind") != "json":
            raise AssertionError(f"expected JSON runtime probe payload, got {payload}")
        if payload.get("postgres_count_probe") is not None:
            raise AssertionError(f"JSON runtime must not run PostgreSQL count probe: {payload}")
        if payload.get("repository_connection_id") is not None or payload.get("repository_connection_scope") is not None:
            raise AssertionError(f"JSON runtime must not report PostgreSQL connection evidence: {payload}")
        if payload.get("json_fallback_used") is not False:
            raise AssertionError(f"probe must report no fallback: {payload}")
        if connector.calls:
            raise AssertionError(f"JSON-default probe must not connect to PostgreSQL: {connector.calls}")
    finally:
        server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = None


def assert_postgres_missing_url_fails_closed() -> None:
    os.environ["VANTALINE_DATA_STORE"] = "postgres"
    os.environ.pop("DATABASE_URL", None)
    server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = RecordingConnector()
    try:
        try:
            server.load_auth_store()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            if exc.status_code != 503 or detail.get("code") != "runtime_store_config_error":
                raise AssertionError(f"expected postgres config failure, got {exc.status_code}: {exc.detail}") from exc
            if detail.get("json_fallback_used") is not False:
                raise AssertionError(f"postgres-selected failure must not fall back to JSON: {detail}")
        else:
            raise AssertionError("postgres selection without DATABASE_URL must fail before auth JSON fallback")
    finally:
        server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = None
        os.environ.pop("VANTALINE_DATA_STORE", None)


def assert_postgres_connector_failure_is_redacted() -> None:
    raw_url = "postgresql://user:super-secret@example.local/vantaline?password=secret2"
    os.environ["VANTALINE_DATA_STORE"] = "postgres"
    os.environ["DATABASE_URL"] = raw_url
    connector = RecordingConnector(fail=True)
    server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = connector
    try:
        try:
            server.load_auth_store()
        except HTTPException as exc:
            body = str(exc.detail)
            if "super-secret" in body or "secret2" in body or raw_url in body:
                raise AssertionError(f"runtime probe leaked a raw database URL: {body}") from exc
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            if exc.status_code != 503 or detail.get("code") != "runtime_store_connection_error":
                raise AssertionError(f"expected connection error detail, got {exc.status_code}: {exc.detail}") from exc
            if "no JSON fallback was used" not in str(detail.get("message") or ""):
                raise AssertionError(f"connection failure must explicitly fail closed: {detail}") from exc
            if detail.get("json_fallback_used") is not False:
                raise AssertionError(f"postgres failure must not fall back to JSON: {detail}") from exc
        else:
            raise AssertionError("failing postgres connector must not return auth JSON fallback")
        if connector.calls != [raw_url]:
            raise AssertionError(f"connector call mismatch: {connector.calls}")
    finally:
        server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = None
        os.environ.pop("VANTALINE_DATA_STORE", None)
        os.environ.pop("DATABASE_URL", None)


def assert_postgres_thread_cache_reuses_and_rebuilds_connections() -> None:
    raw_url = "postgresql://cache-user:cache-secret@example.local/vantaline"
    os.environ["VANTALINE_DATA_STORE"] = "postgres"
    os.environ["DATABASE_URL"] = raw_url
    connector = CloseTrackingConnector()
    server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = connector
    server.reset_runtime_repository_cache()
    try:
        first = server.runtime_repository_selection()
        first_connection = first.repository.connection
        second = server.runtime_repository_selection()
        if second is not first:
            raise AssertionError("same-thread PostgreSQL runtime selection should be cached")
        if connector.calls != [raw_url]:
            raise AssertionError(f"same-thread cache should connect once, got {connector.calls}")
        if first_connection.close_calls != 0:
            raise AssertionError("fresh cached connection was closed unexpectedly")

        first_connection.closed = True
        rebuilt = server.runtime_repository_selection()
        second_connection = rebuilt.repository.connection
        if rebuilt is first or second_connection is first_connection:
            raise AssertionError("closed cached PostgreSQL connection must be rebuilt")
        if connector.calls != [raw_url, raw_url]:
            raise AssertionError(f"closed connection rebuild should reconnect once, got {connector.calls}")
        if first_connection.close_calls != 1:
            raise AssertionError("closed cached connection should still be close-attempted during eviction")

        generation_before_reset = server.current_runtime_repository_generation()
        server.reset_runtime_repository_cache()
        if server.current_runtime_repository_generation() != generation_before_reset + 1:
            raise AssertionError("runtime repository reset should increment the cache generation")
        if second_connection.close_calls != 1 or not second_connection.closed:
            raise AssertionError("runtime repository reset should close the current thread connection")

        after_reset = server.runtime_repository_selection()
        third_connection = after_reset.repository.connection
        if third_connection is second_connection or connector.calls != [raw_url, raw_url, raw_url]:
            raise AssertionError("runtime repository reset should force a new PostgreSQL connection")

        server.clear_thread_runtime_repository_selection()
        if third_connection.close_calls != 1 or not third_connection.closed:
            raise AssertionError("clearing the current thread selection should close its connection")
        after_clear = server.runtime_repository_selection()
        if after_clear.repository.connection is third_connection or connector.calls != [raw_url] * 4:
            raise AssertionError("clearing the current thread selection should force a reconnect")
    finally:
        server.clear_thread_runtime_repository_selection()
        server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = None
        os.environ.pop("VANTALINE_DATA_STORE", None)
        os.environ.pop("DATABASE_URL", None)
        server.reset_runtime_repository_cache()


def main() -> None:
    assert_json_default_probe_does_not_connect()
    assert_postgres_missing_url_fails_closed()
    assert_postgres_connector_failure_is_redacted()
    assert_postgres_thread_cache_reuses_and_rebuilds_connections()
    print("endpoint runtime store probe smoke passed")


if __name__ == "__main__":
    main()
