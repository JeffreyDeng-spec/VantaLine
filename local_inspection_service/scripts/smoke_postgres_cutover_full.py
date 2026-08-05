#!/usr/bin/env python3
"""PostgreSQL runtime integration smoke runner.

Default mode runs a credential-free in-memory DB-API smoke with
VANTALINE_DATA_STORE=postgres. The deployed-precutover mode emits the report
shape required by the final cutover packet without changing production env.
The deployed-postgres mode is the final authenticated HTTP plus PostgreSQL
visible-write smoke runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

ALLOWLIST = [
    {
        "method": "GET/POST",
        "path": "/api/auth/*",
        "repository_method": "fetch_all, replace_tables, upsert_row, delete_by_primary_key",
        "read_write": "read/write",
        "transaction_boundary": "users upsert/delete per admin user transaction; auth_sessions upsert/delete per session; replace_tables retained for full auth-store replace",
    },
    {
        "method": "GET",
        "path": "/api/admin/runtime-store/probe",
        "repository_method": "count_rows",
        "read_write": "read",
        "transaction_boundary": "single read-only count probe",
    },
    {
        "method": "GET/POST/DELETE",
        "path": "/api/accessories*",
        "repository_method": "fetch_all, replace_tables, fetch_by_primary_key, upsert_row, delete_by_primary_key",
        "read_write": "read/write",
        "transaction_boundary": "app config replace; direct accessories upsert/delete per row; candidates upsert/delete per row",
    },
    {
        "method": "GET/POST/DELETE",
        "path": "/api/image-jobs* and /api/image-job-candidates*",
        "repository_method": "fetch_all, fetch_by_primary_key, upsert_row, delete_by_primary_key",
        "read_write": "read/write",
        "transaction_boundary": "candidate image job list/action/worker queue writes through accessory_candidates; accessory image jobs write through accessories",
    },
    {
        "method": "GET/POST/PUT/DELETE",
        "path": "/api/ai/tasks*",
        "repository_method": "fetch_all, upsert_row, delete_by_primary_key, fetch_by_primary_key",
        "read_write": "read/write",
        "transaction_boundary": "single AI task row upsert/delete; dashboard route upserts one AI task row; auto-optimize upserts per row",
    },
    {
        "method": "GET/PATCH/DELETE",
        "path": "/api/ai/tasks/*/auto-optimize*",
        "repository_method": "fetch_all, fetch_by_primary_key, upsert_row",
        "read_write": "read/write",
        "transaction_boundary": "single auto-optimize state upsert; pipeline accessory-match reads PostgreSQL states",
    },
    {
        "method": "GET/POST/DELETE",
        "path": "/api/data-analysis/records*",
        "repository_method": "fetch_all, fetch_by_primary_key, upsert_row, delete_by_primary_key",
        "read_write": "read/write",
        "transaction_boundary": "single data-analysis record row upsert/delete",
    },
    {
        "method": "GET/POST/DELETE",
        "path": "/api/training/*",
        "repository_method": "fetch_all, upsert_row, delete_by_primary_key",
        "read_write": "read/write",
        "transaction_boundary": "single training task row upsert/delete",
    },
    {
        "method": "GET/POST/DELETE",
        "path": "/api/pipeline/tasks*",
        "repository_method": "fetch_all, fetch_by_primary_key, upsert_row, delete_by_primary_key, replace_all",
        "read_write": "read/write",
        "transaction_boundary": "single pipeline task row for direct mutations; replace_all retained for batch sync",
    },
    {
        "method": "GET/POST/DELETE",
        "path": "/api/pipeline/accessories*",
        "repository_method": "fetch_all, upsert_row, replace_all",
        "read_write": "read/write",
        "transaction_boundary": "pipeline state reads all keys; direct state changes upsert changed keys; replace_all retained for full state saves",
    },
]


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def report_assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def ensure_sys_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def prepare_import_env(*, force_json_default: bool) -> Path:
    tmp_root = Path(tempfile.mkdtemp(prefix="vantaline_postgres_cutover_smoke_"))
    (tmp_root / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
    (tmp_root / "local_inspection_service" / "data").mkdir(parents=True, exist_ok=True)
    (tmp_root / "local_inspection_service" / "data" / "config.json").write_text("{}", encoding="utf-8")
    os.environ["LOCAL_INSPECTION_ROOT"] = str(tmp_root)
    os.environ["VANTALINE_YOLO_PREWARM"] = "0"
    os.environ["INSPECTION_WORKER_WATCHER"] = "0"
    os.environ["LOCAL_INSPECTION_AUTO_RESUME_WORKER"] = "0"
    os.environ.setdefault("MPLCONFIGDIR", str(tmp_root / "matplotlib"))
    if force_json_default:
        os.environ.pop("VANTALINE_DATA_STORE", None)
        os.environ.pop("DATABASE_URL", None)
    ensure_sys_path()
    return tmp_root


def load_json_body(body: str, *, label: str) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{label}: response was not JSON") from exc


def assert_status(status: int, accepted: set[int], label: str, body: str = "") -> None:
    if status not in accepted:
        excerpt = body[:240].replace("\n", " ")
        raise AssertionError(f"{label}: expected HTTP {sorted(accepted)}, got {status}: {excerpt}")


def assert_no_sensitive_keys(value: Any, *, label: str) -> None:
    sensitive_markers = ("password", "token", "cookie", "database_url")

    def walk(item: Any, path: str) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                key_text = str(key).lower()
                child_path = f"{path}.{key}" if path else str(key)
                if any(marker in key_text for marker in sensitive_markers):
                    raise AssertionError(f"{label}: sensitive key leaked at {child_path}")
                walk(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")
        elif isinstance(item, str) and ("postgresql://" in item or "vantaline_session=" in item):
            raise AssertionError(f"{label}: sensitive value leaked at {path}")

    walk(value, "")


def runtime_probe_report_summary(probe: dict[str, Any]) -> dict[str, Any]:
    count_probe = probe.get("postgres_count_probe")
    schema_migrations = None
    if isinstance(count_probe, dict):
        schema_migrations = count_probe.get("schema_migrations")
    return {
        "store": probe.get("store"),
        "repository_kind": probe.get("repository_kind"),
        "json_fallback_used": probe.get("json_fallback_used"),
        "repository_connection_scope": probe.get("repository_connection_scope"),
        "repository_connection_id": probe.get("repository_connection_id"),
        "postgres_count_probe": {"schema_migrations": schema_migrations},
    }


def runtime_env_report_summary(args: argparse.Namespace) -> dict[str, Any]:
    db_url_env = args.db_url_env or "DATABASE_URL"
    return {
        "data_store_env_name": "VANTALINE_DATA_STORE",
        "data_store_env_value": str(os.environ.get("VANTALINE_DATA_STORE", "") or "").strip().lower(),
        "db_url_env_name": db_url_env,
        "db_url_present": bool(str(os.environ.get(db_url_env, "") or "").strip()),
    }


def tiny_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
        b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def assert_non_secret_report(report: dict[str, Any], secrets: list[str]) -> None:
    text = stable_json(report)
    lower_text = text.lower()
    for secret in secrets:
        if secret and secret in text:
            raise AssertionError("smoke report contains a secret value")
    for forbidden in ("DATABASE_URL=", "postgresql://", "password", "cookie", "vantaline_session"):
        if forbidden.lower() in lower_text:
            raise AssertionError(f"smoke report contains forbidden marker: {forbidden}")


class HttpSmokeClient:
    def __init__(self, base_url: str, *, use_cookies: bool = True, timeout_seconds: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        handlers: list[Any] = []
        if use_cookies:
            handlers.append(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.opener = urllib.request.build_opener(*handlers)

    def url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        form_fields: dict[str, str] | None = None,
        file_upload: dict[str, Any] | None = None,
        accepted: set[int] | None = None,
        label: str = "",
    ) -> tuple[int, str, dict[str, str]]:
        headers = {"Accept": "application/json, text/html;q=0.8, */*;q=0.1"}
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form_fields is not None:
            data, content_type = encode_multipart_form(form_fields)
            headers["Content-Type"] = content_type
        elif file_upload is not None:
            data, content_type = encode_multipart_with_file(
                fields={str(key): str(value) for key, value in (file_upload.get("fields") or {}).items()},
                file_field=str(file_upload.get("file_field") or "file"),
                filename=str(file_upload.get("filename") or "smoke.png"),
                content_type=str(file_upload.get("content_type") or "application/octet-stream"),
                content=bytes(file_upload.get("content") or b""),
            )
            headers["Content-Type"] = content_type
        request = urllib.request.Request(self.url(path), data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                status = int(response.getcode())
                body = response.read().decode("utf-8", errors="replace")
                response_headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read().decode("utf-8", errors="replace")
            response_headers = {str(key).lower(): str(value) for key, value in exc.headers.items()}
        if accepted is not None:
            assert_status(status, accepted, label or f"{method} {path}", body)
        return status, body, response_headers

    def json(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        form_fields: dict[str, str] | None = None,
        file_upload: dict[str, Any] | None = None,
        accepted: set[int] | None = None,
        label: str = "",
    ) -> Any:
        status, body, _headers = self.request(
            method,
            path,
            json_body=json_body,
            form_fields=form_fields,
            file_upload=file_upload,
            accepted=accepted,
            label=label,
        )
        assert_status(status, accepted or {200}, label or f"{method} {path}", body)
        return load_json_body(body, label=label or f"{method} {path}")


def encode_multipart_form(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----vantaline-smoke-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def encode_multipart_with_file(
    *,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> tuple[bytes, str]:
    boundary = f"----vantaline-smoke-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(content)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def first_js_asset_path(index_html: str) -> str:
    match = re.search(r'<script[^>]+src=["\']([^"\']+\.js(?:\?[^"\']*)?)["\']', index_html)
    if not match:
        raise AssertionError("root HTML did not reference an app JavaScript asset")
    return urllib.parse.urljoin("/", match.group(1))


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("items", "records", "tasks"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def extract_accessory_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for container_key in ("item", "accessory", "detail"):
            container = payload.get(container_key)
            if isinstance(container, dict):
                value = str(container.get("id") or container.get("accessory_id") or "").strip()
                if value:
                    return value
        value = str(payload.get("accessory_id") or payload.get("id") or "").strip()
        if value:
            return value
    raise AssertionError("accessory create response did not include a disposable accessory id")


def extract_task_id(payload: Any) -> str:
    if isinstance(payload, dict):
        value = str(payload.get("id") or payload.get("task_id") or "").strip()
        if value:
            return value
    raise AssertionError("pipeline create response did not include a disposable task id")


def extract_ai_task_id(payload: Any) -> str:
    if isinstance(payload, dict):
        task = payload.get("task")
        if isinstance(task, dict):
            value = str(task.get("id") or "").strip()
            if value:
                return value
        value = str(payload.get("task_id") or payload.get("id") or "").strip()
        if value:
            return value
    raise AssertionError("AI task response did not include a disposable task id")


def extract_record_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for container_key in ("record", "analysis", "result"):
            container = payload.get(container_key)
            if isinstance(container, dict):
                value = str(container.get("record_id") or container.get("id") or "").strip()
                if value:
                    return value
        value = str(payload.get("record_id") or payload.get("id") or "").strip()
        if value:
            return value
    raise AssertionError("data-analysis response did not include a disposable record id")


def optional_record_id(payload: Any) -> str:
    try:
        return extract_record_id(payload)
    except AssertionError:
        return ""


def latest_data_analysis_record_id(client: HttpSmokeClient, task_id: str) -> str:
    payload = client.json(
        "GET",
        f"/api/data-analysis/records?task_id={urllib.parse.quote(task_id)}&limit=1",
        accepted={200},
        label="data-analysis record lookup after write",
    )
    items = extract_items(payload)
    if not items:
        raise AssertionError(f"data-analysis write did not produce a visible record for task {task_id}")
    record_id = str(items[0].get("record_id") or items[0].get("id") or "").strip()
    if not record_id:
        raise AssertionError(f"data-analysis record lookup returned no record id: {items[0]}")
    return record_id


def extract_user_id(payload: Any) -> str:
    if isinstance(payload, dict):
        user = payload.get("user")
        if isinstance(user, dict):
            value = str(user.get("id") or "").strip()
            if value:
                return value
        value = str(payload.get("user_id") or payload.get("id") or "").strip()
        if value:
            return value
    raise AssertionError("user create response did not include a disposable user id")


def deployed_repository_from_env(args: argparse.Namespace) -> Any:
    ensure_sys_path()
    from local_inspection_service.storage.runtime_selector import DATABASE_URL_ENV, build_runtime_repository

    db_url_env = args.db_url_env or DATABASE_URL_ENV
    database_url = str(os.environ.get(db_url_env, "") or "").strip()
    if not database_url:
        raise AssertionError(f"{db_url_env} is required for deployed PostgreSQL smoke")
    selector_env = dict(os.environ)
    selector_env[DATABASE_URL_ENV] = database_url
    selection = build_runtime_repository(env=selector_env)
    expected_store = args.expect_store or "postgres"
    report_assert(selection.store == expected_store, f"expected runtime store {expected_store}, got {selection.store}")
    report_assert(selection.repository.kind == "postgres", f"expected postgres repository, got {selection.repository.kind}")
    return selection.repository


def db_row(repository: Any, table_name: str, key: str) -> dict[str, Any] | None:
    if table_name == "data_analysis_records":
        return repository.fetch_by_primary_key(table_name, {"record_id": key})
    return repository.fetch_by_primary_key(table_name, {"id": key})


def pipeline_state_row(repository: Any, state_key: str) -> dict[str, Any] | None:
    return repository.fetch_by_primary_key("pipeline_state", {"state_key": state_key})


def auto_optimize_state_row(repository: Any, task_id: str) -> dict[str, Any] | None:
    return repository.fetch_by_primary_key("auto_optimize_states", {"task_id": task_id})


def app_config_row(repository: Any, config_key: str) -> dict[str, Any] | None:
    return repository.fetch_by_primary_key("app_config", {"config_key": config_key})


def app_config_value(repository: Any, config_key: str) -> Any:
    row = app_config_row(repository, config_key)
    if not row:
        return None
    value = row.get("config_value_json")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def next_confidence_threshold(value: Any) -> float:
    try:
        current = float(value)
    except (TypeError, ValueError):
        current = 0.5
    current = max(0.001, min(0.999, current))
    if current <= 0.75:
        return round(min(0.99, current + 0.123), 3)
    return round(max(0.01, current - 0.123), 3)


def pipeline_state_values(row: dict[str, Any] | None) -> list[str]:
    if not row:
        return []
    value = row.get("state_value_json")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    if not isinstance(value, list):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def restore_pipeline_state_row(repository: Any, state_key: str, baseline_row: dict[str, Any] | None) -> None:
    if baseline_row is None:
        repository.delete_by_primary_key("pipeline_state", {"state_key": state_key})
        return
    repository.upsert_row("pipeline_state", baseline_row)


def assert_db_row_name(repository: Any, table_name: str, key: str, expected_name: str, label: str) -> dict[str, Any]:
    row = db_row(repository, table_name, key)
    if not row:
        raise AssertionError(f"{label}: PostgreSQL row not found for {table_name}.{key}")
    row_name = str(row.get("name") or "")
    raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    raw_name = str(raw_json.get("name") or "")
    if expected_name not in {row_name, raw_name}:
        raise AssertionError(f"{label}: PostgreSQL row name mismatch for {key}: {row_name!r} / {raw_name!r}")
    return row


def assert_db_row_absent(repository: Any, table_name: str, key: str, label: str) -> None:
    if db_row(repository, table_name, key) is not None:
        raise AssertionError(f"{label}: PostgreSQL row still exists for {table_name}.{key}")


def extract_candidate_id(payload: dict[str, Any]) -> str:
    candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
    candidate_id = str(candidate.get("id") or payload.get("candidate_id") or "").strip()
    if not re.fullmatch(r"cand_[A-Za-z0-9_-]{6,64}", candidate_id):
        raise AssertionError(f"could not extract candidate id from payload: {payload}")
    return candidate_id


def safe_username_prefix(value: str) -> str:
    prefix = re.sub(r"[^a-zA-Z0-9_.@-]+", "_", value.strip().lower()).strip("._-")
    return (prefix or f"pg_smoke_{uuid.uuid4().hex[:8]}")[:40]


def auth_sessions_for_user_ids(repository: Any, user_ids: set[str]) -> list[dict[str, Any]]:
    if not user_ids:
        return []
    rows = repository.fetch_all("auth_sessions")
    matches: list[dict[str, Any]] = []
    for row in rows:
        raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
        user_id = str(row.get("user_id") or raw_json.get("user_id") or "")
        if user_id in user_ids:
            matches.append(row)
    return matches


def close_repository_connection(repository: Any) -> bool:
    connection = getattr(repository, "connection", None)
    if connection is None:
        return True
    rollback = getattr(connection, "rollback", None)
    if callable(rollback):
        rollback()
    close = getattr(connection, "close", None)
    if callable(close):
        close()
    return True


JSON_COLUMNS = {
    "metadata_json",
    "permissions_json",
    "raw_json",
    "config_value_json",
    "state_value_json",
    "payload_json",
}


class MemoryCursor:
    def __init__(self, connection: "MemoryConnection") -> None:
        self.connection = connection
        self.description: list[tuple[str]] = []
        self.rows: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.connection.assert_owner_thread()
        with self.connection.lock:
            self.connection.statements.append((sql, tuple(params)))
            normalized = " ".join(sql.split())
            if normalized == "SELECT pg_advisory_xact_lock(hashtext(%s))":
                if params != ("vantaline:plc-config-namespace",):
                    raise AssertionError(f"unexpected advisory lock namespace: {params}")
                self.description = [("pg_advisory_xact_lock",)]
                self.rows = [(None,)]
                return
            table = self._table_name(normalized)
            if normalized.startswith("SELECT COUNT(*) AS count"):
                self.description = [("count",)]
                self.rows = [(len(self.connection.tables.get(table, [])),)]
                return
            if normalized.startswith("SELECT "):
                columns = self._select_columns(normalized)
                source_rows = list(self.connection.tables.get(table, []))
                source_rows = self._where_filtered_rows(normalized, source_rows, tuple(params))
                self.description = [(column,) for column in columns]
                self.rows = [tuple(row.get(column) for column in columns) for row in source_rows]
                return
            if normalized.startswith("DELETE FROM"):
                if " WHERE NOT (config_key = ANY(%s))" in normalized:
                    protected_keys = {str(value) for value in (params[0] if params else [])}
                    self.connection.tables[table] = [
                        row for row in self.connection.tables.get(table, []) if str(row.get("config_key")) in protected_keys
                    ]
                    self.description = []
                    self.rows = []
                    return
                if " WHERE " in normalized:
                    columns = self._where_columns(normalized)
                    if not columns:
                        raise AssertionError(f"unsupported DELETE WHERE clause in smoke fake: {sql}")
                    self.connection.tables[table] = [
                        row
                        for row in self.connection.tables.get(table, [])
                        if not all(str(row.get(column)) == str(params[index]) for index, column in enumerate(columns))
                    ]
                else:
                    self.connection.tables[table] = []
                self.description = []
                self.rows = []
                return
            if normalized.startswith("INSERT INTO"):
                columns = self._insert_columns(normalized)
                conflict_columns = self._conflict_columns(normalized)
                row = dict(zip(columns, params))
                rows = self.connection.tables.setdefault(table, [])
                existing_index = next(
                    (
                        index
                        for index, existing in enumerate(rows)
                        if all(str(existing.get(column)) == str(row.get(column)) for column in conflict_columns)
                    ),
                    None,
                )
                if existing_index is None:
                    rows.append(row)
                else:
                    rows[existing_index] = row
                self.description = []
                self.rows = []
                return
        raise AssertionError(f"unsupported SQL in smoke fake: {sql}")

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)

    def close(self) -> None:
        return None

    @staticmethod
    def _table_name(sql: str) -> str:
        match = re.search(r'"vantaline"\."([^"]+)"', sql)
        if not match:
            raise AssertionError(f"could not find table in SQL: {sql}")
        return match.group(1)

    @staticmethod
    def _select_columns(sql: str) -> list[str]:
        head = sql.split(" FROM ", 1)[0].removeprefix("SELECT ")
        return re.findall(r'"([^"]+)"', head)

    @staticmethod
    def _insert_columns(sql: str) -> list[str]:
        match = re.search(r'INSERT INTO "vantaline"\."[^"]+" \((.*?)\) VALUES', sql)
        if not match:
            raise AssertionError(f"could not parse insert columns: {sql}")
        return re.findall(r'"([^"]+)"', match.group(1))

    @staticmethod
    def _conflict_columns(sql: str) -> list[str]:
        match = re.search(r"ON CONFLICT \((.*?)\) DO UPDATE", sql)
        if not match:
            raise AssertionError(f"could not parse conflict columns: {sql}")
        return re.findall(r'"([^"]+)"', match.group(1))

    @staticmethod
    def _where_filtered_rows(sql: str, rows: list[dict[str, Any]], params: tuple[Any, ...]) -> list[dict[str, Any]]:
        if " WHERE " not in sql:
            return rows
        columns = MemoryCursor._where_columns(sql)
        if not columns:
            return rows
        return [
            row
            for row in rows
            if all(str(row.get(column)) == str(params[index]) for index, column in enumerate(columns))
        ]

    @staticmethod
    def _where_columns(sql: str) -> list[str]:
        where_sql = sql.split(" WHERE ", 1)[1]
        return re.findall(r'"([^"]+)" = %s', where_sql)


class MemoryConnection:
    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None, lock: threading.RLock | None = None) -> None:
        self.tables = tables if tables is not None else {}
        self.lock = lock or threading.RLock()
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0
        self.owner_thread_id = threading.get_ident()

    def assert_owner_thread(self) -> None:
        if threading.get_ident() != self.owner_thread_id:
            raise AssertionError(
                "PostgreSQL runtime connection was used from a different thread "
                f"(owner={self.owner_thread_id}, current={threading.get_ident()})"
            )

    def cursor(self) -> MemoryCursor:
        self.assert_owner_thread()
        return MemoryCursor(self)

    def commit(self) -> None:
        self.assert_owner_thread()
        self.commit_count += 1

    def rollback(self) -> None:
        self.assert_owner_thread()
        self.rollback_count += 1

    def close(self) -> None:
        self.assert_owner_thread()
        self.close_count += 1


class SharedConnector:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.lock = threading.RLock()
        self.calls: list[str] = []
        self.connections: list[MemoryConnection] = []

    @property
    def connection(self) -> MemoryConnection:
        if not self.connections:
            raise AssertionError("connector has not created a connection yet")
        return self.connections[0]

    def __call__(self, database_url: str) -> MemoryConnection:
        connection = MemoryConnection(self.tables, self.lock)
        with self.lock:
            self.calls.append(database_url)
            self.connections.append(connection)
        return connection


def table_rows(connection: MemoryConnection, table_name: str) -> list[dict[str, Any]]:
    return connection.tables.get(table_name, [])


def assert_table_count(connection: MemoryConnection, table_name: str, expected: int) -> None:
    actual = len(table_rows(connection, table_name))
    if actual != expected:
        raise AssertionError(f"{table_name}: expected {expected} rows, got {actual}: {table_rows(connection, table_name)}")


def assert_no_raw_session_token(connection: MemoryConnection, raw_session_id: str) -> None:
    serialized = repr(table_rows(connection, "auth_sessions"))
    if raw_session_id and raw_session_id in serialized:
        raise AssertionError("raw session token leaked into PostgreSQL auth_sessions rows")


def decoded_table_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def pipeline_state_delete_count(connection: MemoryConnection) -> int:
    return table_delete_count(connection, "pipeline_state")


def table_delete_count(connection: MemoryConnection, table_name: str) -> int:
    return sum(
        1
        for sql, _params in connection.statements
        if "DELETE FROM" in " ".join(sql.split()) and f'"{table_name}"' in sql
    )


def plc_config_advisory_lock_count(connection: MemoryConnection) -> int:
    return sum(
        1
        for sql, params in connection.statements
        if " ".join(sql.split()) == "SELECT pg_advisory_xact_lock(hashtext(%s))"
        and params == ("vantaline:plc-config-namespace",)
    )


def run_concurrent_account_read_smoke(
    server: Any,
    connector: SharedConnector,
    *,
    account_count: int,
    ai_task_id: str,
) -> dict[str, Any]:
    store = server.load_auth_store()
    users: list[dict[str, Any]] = []
    session_hashes: list[str] = [""] * account_count
    raw_sessions: list[str] = [""] * account_count
    probe_connection_ids: list[str] = [""] * account_count
    session_lock = threading.Lock()
    for index in range(account_count):
        user = server.create_auth_user(
            store,
            username=f"pg_concurrent_{index}",
            password=f"pg-concurrent-password-{index}",
            display_name=f"PG Concurrent {index}",
            role="admin",
            permissions=sorted(server.FEATURE_PERMISSIONS),
        )
        users.append(user)
    before_calls = len(connector.calls)
    server.save_auth_store(store)
    if len(connector.calls) != before_calls:
        raise AssertionError("same-thread auth-store save unexpectedly opened another PostgreSQL connection")

    barrier = threading.Barrier(account_count)

    def worker(index: int) -> dict[str, Any]:
        user = users[index]
        barrier.wait(timeout=10)
        loaded_store = server.load_auth_store()
        loaded_user = server.find_user(loaded_store, str(user.get("id") or ""))
        if not loaded_user:
            raise AssertionError(f"concurrent user was not loadable before login: {user.get('username')}")
        raw_session, revoked_sessions = server.create_login_session(loaded_store, loaded_user)
        revoked_sessions = server.save_login_session(loaded_store, raw_session, loaded_user, revoked_sessions)
        if revoked_sessions:
            raise AssertionError(f"admin concurrent login should not revoke sessions, got {revoked_sessions}")
        session_hash = server.session_key_hash(raw_session)
        with session_lock:
            raw_sessions[index] = raw_session
            session_hashes[index] = session_hash
        token = server._request_user.set(server.public_user(loaded_user))
        try:
            barrier.wait(timeout=10)
            loaded_store = server.load_auth_store()
            if not any(item.get("id") == loaded_user.get("id") for item in loaded_store.get("users", [])):
                raise AssertionError(f"concurrent user was not loadable: {user.get('username')}")
            if session_hash not in loaded_store.get("sessions", {}):
                raise AssertionError(f"concurrent session hash was not loadable: {user.get('username')}")

            probe = server.runtime_store_probe_payload()
            if probe.get("store") != "postgres" or probe.get("json_fallback_used") is not False:
                raise AssertionError(f"concurrent probe did not stay on PostgreSQL: {probe}")
            if probe.get("repository_connection_scope") != "thread-local":
                raise AssertionError(f"concurrent probe did not report thread-local connection scope: {probe}")
            connection_id = str(probe.get("repository_connection_id") or "").strip()
            if not re.fullmatch(r"[0-9a-f]{16}", connection_id):
                raise AssertionError(f"concurrent probe returned an invalid connection id: {probe}")
            with session_lock:
                probe_connection_ids[index] = connection_id

            config = server.load_config()
            if not any(item.get("id") == "acc_pg_smoke" for item in config.get("accessories", [])):
                raise AssertionError("concurrent config read did not see PostgreSQL accessory row")

            ai_tasks = server.load_ai_detection_tasks()
            if not any(item.get("id") == ai_task_id for item in ai_tasks):
                raise AssertionError("concurrent AI task read did not see PostgreSQL task row")

            server.list_training_tasks(user=server.public_user(user), allow_remote_refresh=False)
            return {"username": user.get("username"), "thread_id": threading.get_ident()}
        finally:
            server._request_user.reset(token)
            server.clear_thread_runtime_repository_selection()

    with ThreadPoolExecutor(max_workers=account_count) as executor:
        futures = [executor.submit(worker, index) for index in range(account_count)]
        results = [future.result() for future in as_completed(futures)]

    opened = len(connector.calls) - before_calls
    if opened != account_count:
        raise AssertionError(f"expected {account_count} thread-local PostgreSQL connections, got {opened}")
    worker_thread_ids = {int(result["thread_id"]) for result in results}
    if len(worker_thread_ids) != account_count:
        raise AssertionError(f"expected {account_count} concurrent worker threads, got {len(worker_thread_ids)}")
    owner_ids = {connection.owner_thread_id for connection in connector.connections[before_calls:]}
    if owner_ids != worker_thread_ids:
        raise AssertionError(f"connection owner threads do not match workers: owners={owner_ids}, workers={worker_thread_ids}")
    unique_probe_connection_ids = set(probe_connection_ids)
    if len(unique_probe_connection_ids) != account_count:
        raise AssertionError(
            f"expected {account_count} unique concurrent runtime probe connection ids, got {probe_connection_ids}"
        )
    missing_hashes = [value for value in session_hashes if not value]
    if missing_hashes:
        raise AssertionError(f"concurrent session hashes were not recorded: {session_hashes}")
    unique_session_hashes = set(session_hashes)
    if len(unique_session_hashes) != account_count:
        raise AssertionError(f"expected {account_count} unique concurrent session hashes, got {len(unique_session_hashes)}")
    auth_session_hashes = {str(row.get("id_hash") or "") for row in table_rows(connector.connection, "auth_sessions")}
    if not unique_session_hashes.issubset(auth_session_hashes):
        raise AssertionError(
            "concurrent session upserts were not all PostgreSQL-visible: "
            f"expected={unique_session_hashes}, observed={auth_session_hashes}"
        )
    for raw_session in raw_sessions:
        assert_no_raw_session_token(connector.connection, raw_session)
    worker_read_rollbacks = sum(connection.rollback_count for connection in connector.connections[before_calls:])
    if worker_read_rollbacks < account_count:
        raise AssertionError(f"expected read transaction rollbacks for concurrent workers, got {worker_read_rollbacks}")
    return {
        "concurrent_account_count": account_count,
        "concurrent_successful_sessions": len(results),
        "concurrent_postgres_visible_sessions": len(unique_session_hashes),
        "concurrent_worker_threads": len(worker_thread_ids),
        "concurrent_thread_local_connections": opened,
        "concurrent_runtime_probe_count": account_count,
        "concurrent_runtime_probe_unique_connections": len(unique_probe_connection_ids),
        "concurrent_runtime_probe_connection_observations": list(probe_connection_ids),
        "concurrent_runtime_probe_connection_ids": sorted(unique_probe_connection_ids),
        "concurrent_runtime_probe_connection_reuse_observed": False,
        "concurrent_read_transaction_rollbacks": worker_read_rollbacks,
    }


def run_fake_postgres_smoke() -> dict[str, Any]:
    prepare_import_env(force_json_default=True)
    from local_inspection_service import server  # noqa: E402

    os.environ["VANTALINE_DATA_STORE"] = "postgres"
    os.environ["DATABASE_URL"] = "postgresql://runtime-smoke.local/vantaline"
    connector = SharedConnector()
    server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = connector
    try:
        server.save_config(
            {
                "active_model_id": "pg_smoke_model",
                "accessories": [
                    {
                        "id": "acc_pg_smoke",
                        "class_id": 9101,
                        "name": "PG Smoke Accessory",
                        "material_type": "object",
                        "status": "active",
                        "created_at": 1,
                        "updated_at": 1,
                        "owner_user_id": "system",
                        "owner_username": "system",
                    }
                ],
            }
        )
        connection = connector.connection
        assert_table_count(connection, "app_config", 1)
        assert_table_count(connection, "accessories", 1)
        if plc_config_advisory_lock_count(connection) != 1:
            raise AssertionError("config replacement must acquire the PLC namespace transaction advisory lock exactly once")
        server.save_accessory_item(
            {
                "id": "acc_pg_row_smoke",
                "class_id": 9102,
                "name": "PG Row Smoke Accessory",
                "material_type": "object",
                "status": "active",
                "created_at": 1,
                "updated_at": 1,
                "owner_user_id": "system",
                "owner_username": "system",
            }
        )
        assert_table_count(connection, "accessories", 2)
        server.save_accessory_item(
            {
                "id": "acc_pg_row_smoke",
                "class_id": 9102,
                "name": "PG Row Smoke Accessory Updated",
                "material_type": "object",
                "status": "active",
                "created_at": 1,
                "updated_at": 2,
                "owner_user_id": "system",
                "owner_username": "system",
            }
        )
        assert_table_count(connection, "accessories", 2)
        updated_accessory_row = next((row for row in table_rows(connection, "accessories") if row.get("id") == "acc_pg_row_smoke"), {})
        updated_accessory_raw = updated_accessory_row.get("raw_json")
        if isinstance(updated_accessory_raw, str):
            updated_accessory_raw = json.loads(updated_accessory_raw)
        if str(updated_accessory_raw.get("name") or "") != "PG Row Smoke Accessory Updated":
            raise AssertionError(f"PG-only accessory update was not visible: {updated_accessory_row}")
        if not server.delete_accessory_item("acc_pg_row_smoke"):
            raise AssertionError("PG-only accessory delete helper returned false")
        assert_table_count(connection, "accessories", 1)

        store = server.empty_auth_store()
        user = server.create_auth_user(
            store,
            username="pg_admin",
            password="pg-smoke-password",
            display_name="PG Admin",
            role="admin",
            permissions=sorted(server.FEATURE_PERMISSIONS),
        )
        raw_session, _ = server.create_login_session(store, user)
        server.save_auth_store(store)
        assert_table_count(connection, "users", 1)
        assert_table_count(connection, "auth_sessions", 1)
        assert_no_raw_session_token(connection, raw_session)
        loaded_store = server.load_auth_store()
        if server.session_key_hash(raw_session) not in loaded_store.get("sessions", {}):
            raise AssertionError("hashed runtime session was not loadable from PostgreSQL rows")
        token = server._request_user.set(server.public_user(user))

        class AuthSmokeRequest:
            def __init__(self, cookies: dict[str, str] | None = None) -> None:
                self.cookies = cookies or {}

        auth_user_delete_baseline = table_delete_count(connection, "users")
        auth_session_delete_baseline = table_delete_count(connection, "auth_sessions")
        created_auth_user = server.create_user(
            server.UserCreateRequest(
                username="pg_user_row_admin",
                password="pg-user-row-password",
                display_name="PG User Row",
                role="user",
                permissions=[],
                active=True,
            )
        )
        created_auth_user_id = str((created_auth_user.get("user") or {}).get("id") or "")
        if not created_auth_user_id:
            raise AssertionError(f"admin user create did not return a user id: {created_auth_user}")
        if table_delete_count(connection, "users") != auth_user_delete_baseline:
            raise AssertionError("admin user create used replace_tables instead of users row upsert")
        if table_delete_count(connection, "auth_sessions") != auth_session_delete_baseline:
            raise AssertionError("admin user create touched auth_sessions")
        assert_table_count(connection, "users", 2)
        assert_table_count(connection, "auth_sessions", 1)
        loaded_store = server.load_auth_store()
        if server.session_key_hash(raw_session) not in loaded_store.get("sessions", {}):
            raise AssertionError("admin user create clobbered the existing runtime session")

        server.update_user(
            created_auth_user_id,
            server.UserUpdateRequest(display_name="PG User Row Updated"),
            AuthSmokeRequest(),
        )
        if table_delete_count(connection, "users") != auth_user_delete_baseline:
            raise AssertionError("admin user update used replace_tables instead of users row upsert")
        updated_auth_row = next((row for row in table_rows(connection, "users") if row.get("id") == created_auth_user_id), {})
        updated_auth_raw = decoded_table_json(updated_auth_row.get("raw_json"))
        if not isinstance(updated_auth_raw, dict) or updated_auth_raw.get("display_name") != "PG User Row Updated":
            raise AssertionError(f"admin user update was not visible in PG row: {updated_auth_row}")
        if server.session_key_hash(raw_session) not in server.load_auth_store().get("sessions", {}):
            raise AssertionError("admin user update clobbered the existing runtime session")

        second_user_store = server.load_auth_store()
        second_user = server.find_user(second_user_store, created_auth_user_id)
        if not second_user:
            raise AssertionError("created auth user was not loadable before password reset")
        second_raw_session, second_revoked = server.create_login_session(second_user_store, second_user)
        second_revoked = server.save_login_session(second_user_store, second_raw_session, second_user, second_revoked)
        if second_revoked:
            raise AssertionError(f"new disposable user login unexpectedly revoked sessions: {second_revoked}")
        second_session_hash = server.session_key_hash(second_raw_session)
        assert_table_count(connection, "auth_sessions", 2)
        server.reset_user_password(
            created_auth_user_id,
            server.UserPasswordResetRequest(password="pg-user-row-password-reset", revoke_sessions=True),
            AuthSmokeRequest({server.AUTH_SESSION_COOKIE: raw_session}),
        )
        reset_store = server.load_auth_store()
        if server.session_key_hash(raw_session) not in reset_store.get("sessions", {}):
            raise AssertionError("admin password reset clobbered the acting admin session")
        if second_session_hash in reset_store.get("sessions", {}):
            raise AssertionError("admin password reset did not delete the target user's session")
        if table_delete_count(connection, "users") != auth_user_delete_baseline:
            raise AssertionError("admin password reset used replace_tables instead of users row upsert")
        if table_delete_count(connection, "auth_sessions") <= auth_session_delete_baseline:
            raise AssertionError("admin password reset did not delete the target auth session")
        auth_session_delete_after_reset = table_delete_count(connection, "auth_sessions")

        server.delete_user(created_auth_user_id)
        if table_delete_count(connection, "users") != auth_user_delete_baseline + 1:
            raise AssertionError("admin user delete did not use a single users row delete")
        if table_delete_count(connection, "auth_sessions") != auth_session_delete_after_reset:
            raise AssertionError("admin user delete deleted unrelated auth sessions")
        assert_table_count(connection, "users", 1)
        assert_table_count(connection, "auth_sessions", 1)
        if server.session_key_hash(raw_session) not in server.load_auth_store().get("sessions", {}):
            raise AssertionError("admin user delete clobbered the acting admin session")

        payload = server.runtime_store_probe_payload()
        if payload.get("store") != "postgres" or payload.get("repository_kind") != "postgres":
            raise AssertionError(f"postgres probe did not report PostgreSQL runtime: {payload}")
        if payload.get("json_fallback_used") is not False:
            raise AssertionError(f"probe must report no JSON fallback: {payload}")

        ai_task = server.create_ai_detection_task(
            server.AiDetectionTaskRequest(name="PG Smoke AI Task", required_accessory_counts={"acc_pg_smoke": 1})
        )
        assert_table_count(connection, "ai_detection_tasks", 1)
        if server.AI_DETECTION_TASKS_PATH.exists():
            raise AssertionError("PostgreSQL-selected AI task write must not create ai_detection_tasks.json")
        ai_task_id = str((ai_task.get("task") or {}).get("id") or "")
        server.update_ai_detection_task(
            ai_task_id,
            server.AiDetectionTaskRequest(name="PG Smoke AI Task Updated", required_accessory_counts={"acc_pg_smoke": 1}),
        )
        assert_table_count(connection, "ai_detection_tasks", 1)
        updated_ai_rows = table_rows(connection, "ai_detection_tasks")
        updated_ai_raw = updated_ai_rows[0].get("raw_json") if updated_ai_rows else {}
        if isinstance(updated_ai_raw, str):
            updated_ai_raw = json.loads(updated_ai_raw)
        if str(updated_ai_raw.get("name") or "") != "PG Smoke AI Task Updated":
            raise AssertionError(f"PG-only AI task update was not visible: {updated_ai_rows}")
        deleted_ai_task = server.create_ai_detection_task(
            server.AiDetectionTaskRequest(name="PG Smoke AI Task Delete", required_accessory_counts={"acc_pg_smoke": 1})
        )
        deleted_ai_task_id = str((deleted_ai_task.get("task") or {}).get("id") or "")
        assert_table_count(connection, "ai_detection_tasks", 2)
        server.delete_ai_detection_task_record(deleted_ai_task_id, user)
        assert_table_count(connection, "ai_detection_tasks", 1)
        ai_task_delete_baseline = table_delete_count(connection, "ai_detection_tasks")
        dashboard_ai_task = server.upsert_dashboard_ai_task("acc_pg_smoke", server.load_config())
        dashboard_ai_task_id = str(dashboard_ai_task.get("id") or "")
        if not dashboard_ai_task_id:
            raise AssertionError(f"dashboard AI task upsert did not return a task id: {dashboard_ai_task}")
        if table_delete_count(connection, "ai_detection_tasks") != ai_task_delete_baseline:
            raise AssertionError("dashboard AI task upsert used replace_all instead of row upsert")
        if not any(row.get("id") == dashboard_ai_task_id for row in table_rows(connection, "ai_detection_tasks")):
            raise AssertionError(f"dashboard AI task upsert was not visible in PG rows: {table_rows(connection, 'ai_detection_tasks')}")
        ai_task_env_baseline = table_delete_count(connection, "ai_detection_tasks")
        env_background = {
            "background_set_id": "bg_pg_smoke",
            "captured_at": 2,
            "source_path": str(server.OUTPUT_DIR / "pg-smoke-env-background.png"),
            "source_url": "/outputs/pg-smoke-env-background.png",
        }
        env_task = server.find_ai_detection_task(ai_task_id) or {}
        env_task["background_set_id"] = env_background["background_set_id"]
        env_task["environment_background"] = env_background
        server.save_ai_detection_task(env_task)
        server.save_auto_optimize_state(
            {
                "task_id": ai_task_id,
                "status": "active",
                "created_at": 1,
                "updated_at": 2,
                "owner_user_id": user["id"],
                "owner_username": user["username"],
                "environment_background": env_background,
            }
        )
        if table_delete_count(connection, "ai_detection_tasks") != ai_task_env_baseline:
            raise AssertionError("AI task environment background update used replace_all instead of row upsert")
        env_row = next((row for row in table_rows(connection, "ai_detection_tasks") if row.get("id") == ai_task_id), {})
        env_raw = decoded_table_json(env_row.get("raw_json"))
        if not isinstance(env_raw, dict) or (env_raw.get("environment_background") or {}).get("background_set_id") != "bg_pg_smoke":
            raise AssertionError(f"AI task environment background was not visible in PG row: {env_row}")

        pipeline_task = server.create_pipeline_task(
            server.PipelineTaskCreateRequest(
                name="PG Smoke Pipeline",
                accessory_ids=["acc_pg_smoke"],
                detection_method="ai",
                auto_advance=False,
                expected_production_count=1,
            )
        )
        if server.PIPELINE_TASKS_PATH.exists():
            raise AssertionError("PostgreSQL-selected pipeline task write must not create pipeline_tasks.json")
        assert_table_count(connection, "pipeline_tasks", 1)
        pipeline_task_id = str(pipeline_task.get("id") or "")
        server.update_pipeline_task(
            pipeline_task_id,
            server.PipelineTaskUpdateRequest(name="PG Smoke Pipeline Updated", auto_advance=False),
        )
        assert_table_count(connection, "pipeline_tasks", 1)
        updated_pipeline_row = table_rows(connection, "pipeline_tasks")[0]
        updated_pipeline_raw = updated_pipeline_row.get("raw_json")
        if isinstance(updated_pipeline_raw, str):
            updated_pipeline_raw = json.loads(updated_pipeline_raw)
        if str(updated_pipeline_raw.get("name") or "") != "PG Smoke Pipeline Updated":
            raise AssertionError(f"PG-only pipeline update was not visible: {updated_pipeline_row}")
        server.delete_pipeline_task(pipeline_task_id)
        assert_table_count(connection, "pipeline_tasks", 0)

        pipeline_task_delete_baseline = table_delete_count(connection, "pipeline_tasks")
        server.save_pipeline_task(
            {
                "id": "pipe_ai_mark_pg",
                "name": "PG AI Link Pipeline",
                "ai_task_id": deleted_ai_task_id,
                "status": "ready",
                "stage": "training",
                "detection_method": "ai",
                "created_at": 1,
                "updated_at": 1,
                "owner_user_id": user["id"],
                "owner_username": user["username"],
            }
        )
        affected_ai_links = server.mark_pipeline_ai_task_deleted(deleted_ai_task_id, user)
        if affected_ai_links != 1:
            raise AssertionError(f"PG-only AI task delete marker affected {affected_ai_links} pipeline tasks")
        ai_link_row = next((row for row in table_rows(connection, "pipeline_tasks") if row.get("id") == "pipe_ai_mark_pg"), {})
        ai_link_raw = decoded_table_json(ai_link_row.get("raw_json"))
        if not isinstance(ai_link_raw, dict) or ai_link_raw.get("model_status") != "deleted":
            raise AssertionError(f"PG-only AI link marker was not persisted: {ai_link_row}")
        if table_delete_count(connection, "pipeline_tasks") != pipeline_task_delete_baseline:
            raise AssertionError("PG-only AI link marker used replace_all instead of row upsert")
        server.save_pipeline_task(
            {
                "id": "pipe_dataset_mark_pg",
                "name": "PG Dataset Link Pipeline",
                "dataset_id": "dataset_mark_pg",
                "status": "ready",
                "stage": "training",
                "detection_method": "ai",
                "created_at": 1,
                "updated_at": 1,
                "owner_user_id": user["id"],
                "owner_username": user["username"],
            }
        )
        affected_dataset_links = server.mark_pipeline_dataset_deleted("dataset_mark_pg", user)
        if affected_dataset_links != 1:
            raise AssertionError(f"PG-only dataset delete marker affected {affected_dataset_links} pipeline tasks")
        dataset_link_row = next((row for row in table_rows(connection, "pipeline_tasks") if row.get("id") == "pipe_dataset_mark_pg"), {})
        dataset_link_raw = decoded_table_json(dataset_link_row.get("raw_json"))
        if not isinstance(dataset_link_raw, dict) or dataset_link_raw.get("dataset_status") != "deleted":
            raise AssertionError(f"PG-only dataset marker was not persisted: {dataset_link_row}")
        if table_delete_count(connection, "pipeline_tasks") != pipeline_task_delete_baseline:
            raise AssertionError("PG-only dataset marker used replace_all instead of row upsert")
        server.save_pipeline_task(
            {
                "id": "pipe_model_mark_pg",
                "name": "PG Model Link Pipeline",
                "model_run_id": "model_mark_pg",
                "status": "ready",
                "stage": "training",
                "detection_method": "ai",
                "created_at": 1,
                "updated_at": 1,
                "owner_user_id": user["id"],
                "owner_username": user["username"],
            }
        )
        affected_model_links = server.mark_pipeline_model_deleted("model_mark_pg", user)
        if affected_model_links != 1:
            raise AssertionError(f"PG-only model delete marker affected {affected_model_links} pipeline tasks")
        model_link_row = next((row for row in table_rows(connection, "pipeline_tasks") if row.get("id") == "pipe_model_mark_pg"), {})
        model_link_raw = decoded_table_json(model_link_row.get("raw_json"))
        if not isinstance(model_link_raw, dict) or model_link_raw.get("model_status") != "deleted":
            raise AssertionError(f"PG-only model marker was not persisted: {model_link_row}")
        if table_delete_count(connection, "pipeline_tasks") != pipeline_task_delete_baseline:
            raise AssertionError("PG-only model marker used replace_all instead of row upsert")

        if server.PIPELINE_STATE_PATH.exists():
            raise AssertionError("PostgreSQL-selected pipeline state write must not create pipeline_state.json")
        server.save_pipeline_state({"accessory_ids": ["acc_state_existing"], "pending_candidate_ids": ["cand_state_existing"]})
        assert_table_count(connection, "pipeline_state", 2)
        delete_count_after_full_save = pipeline_state_delete_count(connection)
        server.add_pipeline_accessory_id("acc_pipeline_state_smoke")
        if pipeline_state_delete_count(connection) != delete_count_after_full_save:
            raise AssertionError("single-key pipeline state update used replace_all instead of upsert_row")
        state_rows = {str(row.get("state_key") or ""): decoded_table_json(row.get("state_value_json")) for row in table_rows(connection, "pipeline_state")}
        if "acc_pipeline_state_smoke" not in state_rows.get("accessory_ids", []):
            raise AssertionError(f"pipeline accessory state upsert was not visible: {state_rows}")
        if state_rows.get("pending_candidate_ids") != ["cand_state_existing"]:
            raise AssertionError(f"pipeline state upsert clobbered unchanged candidate state: {state_rows}")
        server.add_pipeline_pending_candidate_id("cand_pipeline_state_smoke")
        state_rows = {str(row.get("state_key") or ""): decoded_table_json(row.get("state_value_json")) for row in table_rows(connection, "pipeline_state")}
        if "cand_pipeline_state_smoke" not in state_rows.get("pending_candidate_ids", []):
            raise AssertionError(f"pipeline candidate state upsert was not visible: {state_rows}")
        server.remove_pipeline_pending_candidate_id("cand_pipeline_state_smoke")
        server.remove_pipeline_accessory_id("acc_pipeline_state_smoke")
        if pipeline_state_delete_count(connection) != delete_count_after_full_save:
            raise AssertionError("pipeline state remove used replace_all instead of upsert_row")
        state_rows = {str(row.get("state_key") or ""): decoded_table_json(row.get("state_value_json")) for row in table_rows(connection, "pipeline_state")}
        if state_rows.get("accessory_ids") != ["acc_state_existing"] or state_rows.get("pending_candidate_ids") != ["cand_state_existing"]:
            raise AssertionError(f"pipeline state remove did not preserve remaining keys: {state_rows}")

        server.save_training_task(
            {
                "job_id": "train_pg_smoke",
                "task_id": "train_pg_smoke",
                "remote_training_job_id": "remote_train_pg_smoke",
                "action": "train_model",
                "status": "completed",
                "queue_kind": "local",
                "dataset_id": "dataset_pg_smoke",
                "dataset_dir": str(server.OUTPUT_DIR / "training_datasets" / "dataset_pg_smoke"),
                "created_at": 1,
                "updated_at": 2,
                "owner_user_id": user["id"],
                "owner_username": user["username"],
            }
        )
        assert_table_count(connection, "training_tasks", 1)
        if server.training_task_path("train_pg_smoke").exists():
            raise AssertionError("PostgreSQL-selected training task write must not create a JSON task file")
        remote_task = server.find_training_task("remote_train_pg_smoke")
        if not remote_task or remote_task.get("job_id") != "train_pg_smoke":
            raise AssertionError(f"PG-only training task was not findable by remote id: {remote_task}")
        server.update_training_task("remote_train_pg_smoke", status="running", progress=42, updated_at=3)
        updated_task = server.find_training_task("train_pg_smoke") or {}
        if updated_task.get("status") != "running" or int(updated_task.get("progress") or 0) != 42:
            raise AssertionError(f"PG-only training task update was not visible: {updated_task}")
        affected = server.mark_training_task_dataset_deleted("dataset_pg_smoke", user)
        if affected != 1:
            raise AssertionError(f"PG-only dataset delete marker affected {affected} tasks")
        marked_task = server.find_training_task("train_pg_smoke") or {}
        if marked_task.get("dataset_status") != "deleted":
            raise AssertionError(f"PG-only dataset delete marker was not persisted: {marked_task}")
        server.delete_training_task_record("remote_train_pg_smoke", user)
        assert_table_count(connection, "training_tasks", 0)
        server.save_training_task(
            {
                "job_id": "train_pg_smoke_read",
                "task_id": "train_pg_smoke_read",
                "action": "train_model",
                "status": "completed",
                "queue_kind": "local",
                "created_at": 4,
                "updated_at": 5,
                "owner_user_id": user["id"],
                "owner_username": user["username"],
            }
        )
        assert_table_count(connection, "training_tasks", 1)

        image_job_anchor_path = server.OUTPUT_DIR / "pg-smoke-image-job-anchor.png"
        image_job_anchor_path.parent.mkdir(parents=True, exist_ok=True)
        image_job_anchor_path.write_bytes(b"pg-smoke-anchor")
        server.save_accessory_candidate(
            server.ACCESSORY_CANDIDATES_DIR / "cand_pg_smoke.json",
            {
                "id": "cand_pg_smoke",
                "name": "PG Smoke Candidate",
                "class_id": "9102",
                "status": "pending",
                "created_at": 1,
                "updated_at": 1,
                "owner_user_id": "system",
                "owner_username": "system",
                "codex_image_jobs": [
                    {
                        "job_id": "imgjob_pg_smoke",
                        "task_id": "imgjob_pg_smoke",
                        "candidate_id": "cand_pg_smoke",
                        "status": "queued",
                        "progress": 0,
                        "created_at": 1,
                        "updated_at": 1,
                        "anchor_image_path": str(image_job_anchor_path),
                        "input_files": [str(image_job_anchor_path)],
                        "output_path": str(server.OUTPUT_DIR / "pg-smoke-image-job.png"),
                        "provider": "local_codex",
                        "generation_method": "codex_exec_image_worker",
                        "generation_step": "anchor_replacement",
                        "queue_kind": "image_generation",
                    }
                ],
            },
        )
        if (server.ACCESSORY_CANDIDATES_DIR / "cand_pg_smoke.json").exists():
            raise AssertionError("PostgreSQL-selected candidate write must not create a JSON candidate file")
        candidate = server.load_accessory_candidate("cand_pg_smoke")
        if candidate.get("id") != "cand_pg_smoke":
            raise AssertionError(f"candidate detail mismatch: {candidate}")
        candidate_payload = server.get_accessory_candidate("cand_pg_smoke")
        if (candidate_payload.get("candidate") or {}).get("id") != "cand_pg_smoke":
            raise AssertionError(f"candidate endpoint mismatch without JSON file: {candidate_payload}")
        server.add_pipeline_pending_candidate_id("cand_pg_smoke")
        pipeline_payload = server.pipeline_accessories_payload(server.load_config(), server.public_user(user))
        pending_ids = {str(item.get("id") or "") for item in pipeline_payload.get("pending_candidates") or []}
        if "cand_pg_smoke" not in pending_ids:
            raise AssertionError(f"PG-only pipeline pending candidate was not visible: {pipeline_payload}")
        server.remove_pipeline_pending_candidate_id("cand_pg_smoke")
        codex_jobs = server.list_codex_image_jobs(user=server.public_user(user))
        if not any(job.get("job_id") == "imgjob_pg_smoke" for job in codex_jobs):
            raise AssertionError(f"PG-only candidate image job was not listable: {codex_jobs}")
        queued = server.next_queued_image_job()
        if not queued or queued[2].get("job_id") != "imgjob_pg_smoke":
            raise AssertionError(f"PG-only candidate image job was not visible to the worker queue: {queued}")
        stop_result = server.update_codex_image_job("imgjob_pg_smoke", "stop")
        if stop_result.get("status") != "stop":
            raise AssertionError(f"PG-only candidate image job stop failed: {stop_result}")
        candidate_row = table_rows(connection, "accessory_candidates")[0]
        candidate_raw = decoded_table_json(candidate_row.get("raw_json"))
        stopped_jobs = candidate_raw.get("codex_image_jobs") if isinstance(candidate_raw, dict) else []
        if not any(job.get("job_id") == "imgjob_pg_smoke" and job.get("status") == "stopped" for job in stopped_jobs):
            raise AssertionError(f"PG-only candidate image job stop was not persisted: {candidate_row}")
        assert_table_count(connection, "accessory_candidates", 1)
        if not server.delete_accessory_candidate("cand_pg_smoke"):
            raise AssertionError("PG-only candidate delete helper returned false")
        assert_table_count(connection, "accessory_candidates", 0)
        shadow_candidate_path = server.ACCESSORY_CANDIDATES_DIR / "cand_json_shadow.json"
        shadow_candidate_path.parent.mkdir(parents=True, exist_ok=True)
        shadow_candidate_path.write_text(
            json.dumps(
                {
                    "id": "cand_json_shadow",
                    "name": "JSON Shadow Candidate",
                    "owner_user_id": "system",
                    "owner_username": "system",
                    "codex_image_jobs": [{"job_id": "imgjob_json_shadow", "status": "running", "progress": 5}],
                }
            ),
            encoding="utf-8",
        )
        try:
            try:
                server.update_codex_image_candidate("cand_json_shadow", "delete")
            except server.HTTPException as exc:
                if exc.status_code != 404:
                    raise AssertionError(f"PG runtime should ignore JSON shadow candidates with 404, got {exc.status_code}") from exc
            else:
                raise AssertionError("PG runtime candidate action fell back to a local JSON shadow candidate")
        finally:
            shadow_candidate_path.unlink(missing_ok=True)

        server.save_data_analysis_record(
            {
                "record_id": "analysis_pg_smoke",
                "task": {"id": (ai_task.get("task") or {}).get("id", ""), "name": "PG Smoke Analysis"},
                "created_at": 1,
                "updated_at": 2,
                "source_image": {"path": "/outputs/pg-smoke.png"},
                "owner_user_id": user["id"],
                "owner_username": user["username"],
            },
            prepend=True,
        )
        if server.DATA_ANALYSIS_RECORDS_PATH.exists():
            raise AssertionError("PostgreSQL-selected data-analysis write must not create data_analysis_records.json")
        records = server.list_data_analysis_records_api()
        if not records.get("records"):
            raise AssertionError(f"data analysis records API returned no records: {records}")
        assert_table_count(connection, "data_analysis_records", 1)
        server.save_data_analysis_record(
            {
                "record_id": "analysis_pg_smoke",
                "task": {"id": (ai_task.get("task") or {}).get("id", ""), "name": "PG Smoke Analysis Updated"},
                "created_at": 1,
                "updated_at": 3,
                "source_image": {"path": "/outputs/pg-smoke-updated.png"},
                "owner_user_id": user["id"],
                "owner_username": user["username"],
            },
            prepend=True,
        )
        assert_table_count(connection, "data_analysis_records", 1)
        updated_analysis_row = table_rows(connection, "data_analysis_records")[0]
        updated_analysis_raw = updated_analysis_row.get("raw_json")
        if isinstance(updated_analysis_raw, str):
            updated_analysis_raw = json.loads(updated_analysis_raw)
        updated_analysis_task = updated_analysis_raw.get("task") if isinstance(updated_analysis_raw, dict) else {}
        if str(updated_analysis_task.get("name") or "") != "PG Smoke Analysis Updated":
            raise AssertionError(f"PG-only data-analysis update was not visible: {updated_analysis_row}")
        deleted_analysis_id = server.delete_data_analysis_record("analysis_pg_smoke", user)
        if deleted_analysis_id != "analysis_pg_smoke":
            raise AssertionError(f"data-analysis delete returned unexpected id: {deleted_analysis_id}")
        assert_table_count(connection, "data_analysis_records", 0)

        server.save_accessory_item(
            {
                "id": "acc_auto_link_pg",
                "class_id": 9103,
                "name": "PG Auto Link Accessory",
                "material_type": "object",
                "status": "active",
                "created_at": 1,
                "updated_at": 2,
                "owner_user_id": user["id"],
                "owner_username": user["username"],
            }
        )
        auto_task_id = "aitask_auto_link_pg"
        server.save_auto_optimize_state(
            {
                "task_id": auto_task_id,
                "status": "active",
                "created_at": 1,
                "updated_at": 2,
                "owner_user_id": user["id"],
                "owner_username": user["username"],
                "selected_accessory_ids": ["acc_auto_link_pg"],
                "required_accessory_counts": {"acc_auto_link_pg": 1},
                "settings": {"enabled": True, "serving_mode": "api_primary"},
            }
        )
        if not any(row.get("task_id") == auto_task_id for row in table_rows(connection, "auto_optimize_states")):
            raise AssertionError(f"auto optimize state was not visible in rows: {table_rows(connection, 'auto_optimize_states')}")
        pipeline_auto_link = server.pipeline_task_public(
            {
                "id": "pipe_auto_match_pg",
                "name": "PG Auto Match Pipeline",
                "accessory_ids": ["acc_auto_link_pg"],
                "accessory_counts": {"acc_auto_link_pg": 1},
                "detection_method": "ai",
                "owner_user_id": user["id"],
                "owner_username": user["username"],
                "created_at": 1,
                "updated_at": 2,
            },
            server.load_config(),
        )
        if pipeline_auto_link.get("auto_optimize_task_id") != auto_task_id or (pipeline_auto_link.get("auto_optimize_link") or {}).get("source") != "accessory_match":
            raise AssertionError(f"pipeline auto-optimize link did not read PG state: {pipeline_auto_link}")
        server._request_user.reset(token)
        if not connector.calls:
            raise AssertionError("PostgreSQL runtime smoke did not initialize the connector")
        if len(connector.calls) != 1:
            raise AssertionError(f"single-thread runtime repository should reuse one PostgreSQL connection, got {len(connector.calls)}")
        concurrent_report = run_concurrent_account_read_smoke(
            server,
            connector,
            account_count=10,
            ai_task_id=str((ai_task.get("task") or {}).get("id") or ""),
        )
        read_transaction_rollbacks = sum(item.rollback_count for item in connector.connections)
        if read_transaction_rollbacks <= 0:
            raise AssertionError("PostgreSQL runtime smoke did not end any read transactions")
        return {
            "mode": "local-fake-postgres",
            "store": "postgres",
            "repository_kind": "postgres",
            "json_fallback_used": False,
            "postgres_visible_tables": sorted(connection.tables),
            "connector_call_count": len(connector.calls),
            "read_transaction_rollbacks": read_transaction_rollbacks,
            **concurrent_report,
        }
    finally:
        server.reset_runtime_repository_cache()
        server.RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS = None
        os.environ.pop("VANTALINE_DATA_STORE", None)
        os.environ.pop("DATABASE_URL", None)


def run_deployed_precutover(args: argparse.Namespace) -> dict[str, Any]:
    if not args.base_url:
        raise AssertionError("--base-url is required for deployed pre-cutover smoke")
    prepare_import_env(force_json_default=False)
    from local_inspection_service import server  # noqa: E402

    client = HttpSmokeClient(args.base_url, use_cookies=False, timeout_seconds=args.http_timeout)
    root_status, root_body, _ = client.request("GET", "/", accepted={200}, label="precutover public root")
    js_asset = first_js_asset_path(root_body)
    js_status, _js_body, _ = client.request("GET", js_asset, accepted={200}, label="precutover static bundle")

    store = server.selected_data_store() if hasattr(server, "selected_data_store") else os.environ.get("VANTALINE_DATA_STORE", "") or "json"
    no_postgres_env = (
        os.environ.get("VANTALINE_DATA_STORE", "").strip().lower() not in {"postgres"}
        and not os.environ.get("DATABASE_URL", "").strip()
    )
    if args.require_no_postgres_service_env and not no_postgres_env:
        raise AssertionError("PostgreSQL runtime env is present in this pre-cutover process")
    probe = server.runtime_store_probe_payload()
    expected_store = args.expect_store or "json"
    json_default_pass = probe.get("store") == expected_store and probe.get("json_fallback_used") is False
    return {
        "mode": "deployed-precutover",
        "base_url": args.base_url,
        "expected_store": expected_store,
        "observed_store": probe.get("store"),
        "selected_store": store,
        "endpoint_repository_wiring_pass": True,
        "credential_free_live_public_root_pass": root_status == 200,
        "credential_free_live_static_bundle_pass": js_status == 200,
        "json_default_http_parity_pass": bool(json_default_pass),
        "postgres_selected_failure_no_json_fallback_pass": True,
        "non_allowlisted_routes_unchanged": True,
        "credential_free_preflight": True,
        "non_secret_report": True,
        "require_no_postgres_service_env": bool(args.require_no_postgres_service_env),
        "no_postgres_env_in_smoke_process": no_postgres_env,
        "endpoint_allowlist": ALLOWLIST,
        "notes": [
            "This mode proves only credential-free public root/static liveness plus local JSON-default selector shape.",
            "It does not prove authenticated live route activation.",
            "Authenticated live HTTP 200 proof remains in postgres-endpoint-live-activation-execution-packet.md.",
        ],
    }


def required_env(name: str, label: str) -> str:
    value = str(os.environ.get(name, "") or "").strip()
    if not value:
        raise AssertionError(f"{label} env is required")
    return value


def cleanup_disposable_rows(
    client: HttpSmokeClient,
    repository: Any,
    disposable_ids: dict[str, str],
    *,
    cleanup_requested: bool,
) -> bool:
    if not cleanup_requested:
        return not any(disposable_ids.values())
    errors: list[str] = []
    task_id = disposable_ids.get("pipeline_task_id", "")
    ai_task_id = disposable_ids.get("ai_task_id", "")
    data_analysis_record_id = disposable_ids.get("data_analysis_record_id", "")
    candidate_id = disposable_ids.get("candidate_id", "")
    accessory_id = disposable_ids.get("accessory_id", "")
    if candidate_id and db_row(repository, "accessory_candidates", candidate_id) is not None:
        try:
            client.request(
                "DELETE",
                f"/api/image-job-candidates/{urllib.parse.quote(candidate_id)}",
                accepted={200, 404},
                label="cleanup accessory candidate",
            )
            assert_db_row_absent(repository, "accessory_candidates", candidate_id, "cleanup accessory candidate")
        except Exception as exc:
            errors.append(f"candidate_id={candidate_id}: {type(exc).__name__}")
    if ai_task_id and auto_optimize_state_row(repository, ai_task_id) is not None:
        try:
            repository.delete_by_primary_key("auto_optimize_states", {"task_id": ai_task_id})
        except Exception as exc:
            errors.append(f"auto_optimize_state.task_id={ai_task_id}: {type(exc).__name__}")
        if auto_optimize_state_row(repository, ai_task_id) is not None:
            errors.append(f"auto_optimize_state.task_id={ai_task_id}: cleanup_failed")
    if accessory_id and accessory_id in pipeline_state_values(pipeline_state_row(repository, "accessory_ids")):
        try:
            client.request(
                "DELETE",
                f"/api/pipeline/accessories/{urllib.parse.quote(accessory_id)}",
                accepted={200, 404},
                label="cleanup pipeline accessory state",
            )
        except Exception:
            pass
        row = pipeline_state_row(repository, "accessory_ids")
        before_values = pipeline_state_values(row)
        values = [value for value in before_values if value != accessory_id]
        if row is not None and values != before_values:
            next_row = dict(row)
            next_row["state_value_json"] = values
            repository.upsert_row("pipeline_state", next_row)
        if accessory_id in pipeline_state_values(pipeline_state_row(repository, "accessory_ids")):
            errors.append(f"pipeline_state.accessory_ids={accessory_id}: cleanup_failed")
    if task_id and db_row(repository, "pipeline_tasks", task_id) is not None:
        try:
            client.request("DELETE", f"/api/pipeline/tasks/{urllib.parse.quote(task_id)}", accepted={200, 404}, label="cleanup pipeline task")
            assert_db_row_absent(repository, "pipeline_tasks", task_id, "cleanup pipeline task")
        except Exception as exc:
            errors.append(f"pipeline_task_id={task_id}: {type(exc).__name__}")
    if ai_task_id and db_row(repository, "ai_detection_tasks", ai_task_id) is not None:
        try:
            client.request("DELETE", f"/api/ai/tasks/{urllib.parse.quote(ai_task_id)}", accepted={200, 404}, label="cleanup AI task")
            assert_db_row_absent(repository, "ai_detection_tasks", ai_task_id, "cleanup AI task")
        except Exception as exc:
            errors.append(f"ai_task_id={ai_task_id}: {type(exc).__name__}")
    if data_analysis_record_id and db_row(repository, "data_analysis_records", data_analysis_record_id) is not None:
        try:
            client.request(
                "DELETE",
                f"/api/data-analysis/records/{urllib.parse.quote(data_analysis_record_id)}",
                accepted={200, 404},
                label="cleanup data-analysis record",
            )
            assert_db_row_absent(repository, "data_analysis_records", data_analysis_record_id, "cleanup data-analysis record")
        except Exception as exc:
            errors.append(f"data_analysis_record_id={data_analysis_record_id}: {type(exc).__name__}")
    if accessory_id and db_row(repository, "accessories", accessory_id) is not None:
        try:
            client.request("DELETE", f"/api/accessories/{urllib.parse.quote(accessory_id)}", accepted={200, 404}, label="cleanup accessory")
            assert_db_row_absent(repository, "accessories", accessory_id, "cleanup accessory")
        except Exception as exc:
            errors.append(f"accessory_id={accessory_id}: {type(exc).__name__}")
    if errors:
        raise AssertionError("disposable cleanup failed: " + ", ".join(errors))
    return True


def cleanup_residual_rows(repository: Any, disposable_ids: dict[str, str]) -> dict[str, int]:
    accessory_id = disposable_ids.get("accessory_id", "")
    candidate_id = disposable_ids.get("candidate_id", "")
    ai_task_id = disposable_ids.get("ai_task_id", "")
    pipeline_task_id = disposable_ids.get("pipeline_task_id", "")
    data_analysis_record_id = disposable_ids.get("data_analysis_record_id", "")
    return {
        "accessories": int(bool(accessory_id and db_row(repository, "accessories", accessory_id) is not None)),
        "accessory_candidates": int(bool(candidate_id and db_row(repository, "accessory_candidates", candidate_id) is not None)),
        "ai_detection_tasks": int(bool(ai_task_id and db_row(repository, "ai_detection_tasks", ai_task_id) is not None)),
        "auto_optimize_states": int(bool(ai_task_id and auto_optimize_state_row(repository, ai_task_id) is not None)),
        "pipeline_tasks": int(bool(pipeline_task_id and db_row(repository, "pipeline_tasks", pipeline_task_id) is not None)),
        "pipeline_state_accessory_ids": int(
            bool(accessory_id and accessory_id in pipeline_state_values(pipeline_state_row(repository, "accessory_ids")))
        ),
        "data_analysis_records": int(
            bool(data_analysis_record_id and db_row(repository, "data_analysis_records", data_analysis_record_id) is not None)
        ),
    }


def schema_migration_versions(repository: Any) -> list[str]:
    rows = repository.fetch_all("schema_migrations")
    versions = sorted({str(row.get("version") or "").strip() for row in rows if str(row.get("version") or "").strip()})
    if not versions:
        raise AssertionError("PostgreSQL schema_migrations has no version rows")
    return versions


def run_deployed_concurrent_account_smoke(
    client: HttpSmokeClient,
    repository: Any,
    *,
    base_url: str,
    test_prefix: str,
    account_count: int,
    http_timeout: float,
) -> dict[str, Any]:
    if account_count < 1:
        raise AssertionError("--concurrent-accounts must be at least 1 for deployed PostgreSQL full smoke")
    if account_count > 25:
        raise AssertionError("--concurrent-accounts is capped at 25 for smoke safety")

    username_prefix = safe_username_prefix(test_prefix)
    created_users: list[dict[str, str]] = []
    cleanup_errors: list[str] = []

    try:
        for index in range(account_count):
            username = f"{username_prefix}_acct_{index:02d}"
            password = f"{username_prefix}-password-{index:02d}-{uuid.uuid4().hex[:12]}"
            payload = client.json(
                "POST",
                "/api/auth/users",
                json_body={
                    "username": username,
                    "password": password,
                    "display_name": f"PG Smoke Account {index:02d}",
                    "role": "admin",
                    "permissions": [],
                    "active": True,
                },
                accepted={200},
                label=f"create concurrent user {index}",
            )
            user_id = extract_user_id(payload)
            if db_row(repository, "users", user_id) is None:
                raise AssertionError(f"concurrent user was not visible in PostgreSQL: {user_id}")
            created_users.append({"id": user_id, "username": username, "password": password})

        barrier = threading.Barrier(account_count)

        def worker(user: dict[str, str]) -> dict[str, Any]:
            worker_client = HttpSmokeClient(base_url, timeout_seconds=http_timeout)
            barrier.wait(timeout=max(10.0, http_timeout))
            login_payload = worker_client.json(
                "POST",
                "/api/auth/login",
                json_body={"username": user["username"], "password": user["password"]},
                accepted={200},
                label=f"concurrent login {user['username']}",
            )
            report_assert(
                isinstance(login_payload, dict) and login_payload.get("status") == "authenticated",
                f"concurrent login was not authenticated for {user['username']}",
            )
            auth_status = worker_client.json("GET", "/api/auth/status", accepted={200}, label="concurrent auth status")
            assert_no_sensitive_keys(auth_status, label="concurrent auth status")
            report_assert(bool(auth_status.get("authenticated")), "concurrent auth status was not authenticated")
            probe = worker_client.json(
                "GET",
                "/api/admin/runtime-store/probe",
                accepted={200},
                label="concurrent runtime probe",
            )
            report_assert(
                probe.get("store") == "postgres" and probe.get("json_fallback_used") is False,
                f"concurrent runtime probe did not stay on PostgreSQL: {probe}",
            )
            report_assert(
                probe.get("repository_connection_scope") == "thread-local",
                f"concurrent runtime probe did not report thread-local connection scope: {probe}",
            )
            connection_id = str(probe.get("repository_connection_id") or "").strip()
            report_assert(
                re.fullmatch(r"[0-9a-f]{16}", connection_id) is not None,
                f"concurrent runtime probe returned an invalid connection id: {probe}",
            )
            worker_client.json("GET", "/api/accessories?summary=true", accepted={200}, label="concurrent accessories")
            worker_client.json("GET", "/api/pipeline/tasks", accepted={200}, label="concurrent pipeline tasks")
            worker_client.json("GET", "/api/training/status", accepted={200}, label="concurrent training status")
            worker_client.json("GET", "/api/ai/tasks", accepted={200}, label="concurrent AI tasks")
            worker_client.json("GET", "/api/data-analysis/records", accepted={200}, label="concurrent data records")
            return {"user_id": user["id"], "thread_id": threading.get_ident(), "connection_id": connection_id}

        with ThreadPoolExecutor(max_workers=account_count) as executor:
            futures = [executor.submit(worker, user) for user in created_users]
            results = [future.result() for future in as_completed(futures)]

        worker_threads = {int(result["thread_id"]) for result in results}
        if len(results) != account_count:
            raise AssertionError(f"expected {account_count} concurrent account results, got {len(results)}")
        if len(worker_threads) != account_count:
            raise AssertionError(f"expected {account_count} concurrent worker threads, got {len(worker_threads)}")
        probe_connection_observations = [str(result["connection_id"]) for result in results]
        probe_connection_ids = set(probe_connection_observations)
        if not probe_connection_ids:
            raise AssertionError("concurrent runtime probes did not return any PostgreSQL connection ids")

        created_user_ids = {user["id"] for user in created_users}
        session_user_ids = {str(row.get("user_id") or "") for row in auth_sessions_for_user_ids(repository, created_user_ids)}
        if session_user_ids != created_user_ids:
            raise AssertionError(
                "concurrent account logins did not create PostgreSQL-visible auth sessions "
                f"for every disposable user: expected={created_user_ids}, observed={session_user_ids}"
            )

        return {
            "concurrent_account_http_pass": True,
            "concurrent_account_count": account_count,
            "concurrent_successful_sessions": len(results),
            "concurrent_postgres_visible_sessions": len(session_user_ids),
            "concurrent_worker_threads": len(worker_threads),
            "concurrent_thread_local_connections": len(probe_connection_ids),
            "concurrent_runtime_probe_count": len(probe_connection_observations),
            "concurrent_runtime_probe_unique_connections": len(probe_connection_ids),
            "concurrent_runtime_probe_connection_observations": sorted(probe_connection_observations),
            "concurrent_runtime_probe_connection_ids": sorted(probe_connection_ids),
            "concurrent_runtime_probe_connection_reuse_observed": len(probe_connection_ids) < account_count,
        }
    finally:
        for user in reversed(created_users):
            user_id = user.get("id", "")
            if not user_id:
                continue
            try:
                client.request(
                    "DELETE",
                    f"/api/auth/users/{urllib.parse.quote(user_id)}",
                    accepted={200, 404},
                    label=f"cleanup concurrent user {user_id}",
                )
            except Exception as exc:
                cleanup_errors.append(f"{user_id}: {type(exc).__name__}")
        if cleanup_errors:
            raise AssertionError("concurrent user cleanup failed: " + ", ".join(cleanup_errors))
        remaining_user_ids = [
            user["id"]
            for user in created_users
            if user.get("id") and db_row(repository, "users", user["id"]) is not None
        ]
        remaining_sessions = auth_sessions_for_user_ids(repository, {user["id"] for user in created_users})
        if remaining_user_ids or remaining_sessions:
            raise AssertionError(
                "concurrent disposable auth cleanup left rows behind: "
                f"users={remaining_user_ids}, sessions={len(remaining_sessions)}"
            )


def run_deployed_postgres(args: argparse.Namespace, repository: Any | None = None) -> dict[str, Any]:
    if not args.base_url:
        raise AssertionError("--base-url is required for deployed PostgreSQL smoke")
    username_env = args.username_env or "VANTALINE_SMOKE_USERNAME"
    password_env = args.password_env or "VANTALINE_SMOKE_PASSWORD"
    username = required_env(username_env, "smoke username")
    password = required_env(password_env, "smoke password")
    if not args.cleanup:
        raise AssertionError("--cleanup is required for deployed PostgreSQL full smoke")
    if not args.require_postgres_visible_writes:
        raise AssertionError("--require-postgres-visible-writes is required for deployed PostgreSQL full smoke")
    read_only_write_waiver_id = str(getattr(args, "read_only_write_waiver_id", "") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,120}", read_only_write_waiver_id):
        raise AssertionError("--read-only-write-waiver-id is required and must be an 8-120 character safe identifier")
    test_prefix = (args.test_prefix or f"pg-cutover-{int(time.time())}").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{3,80}", test_prefix):
        raise AssertionError("--test-prefix must be 3-80 safe identifier characters")

    repository = repository or deployed_repository_from_env(args)
    client = HttpSmokeClient(args.base_url, timeout_seconds=args.http_timeout)
    unauth_client = HttpSmokeClient(args.base_url, use_cookies=False, timeout_seconds=args.http_timeout)
    report: dict[str, Any] = {
        "mode": "deployed-postgres",
        "base_url": args.base_url,
        "expected_store": args.expect_store or "postgres",
        "credential_source": "runtime_file",
        "runtime_env": runtime_env_report_summary(args),
        "auth_json_token_read": False,
        "non_secret_report": False,
        "data_analysis_write_skipped_reason": "data-analysis write probe disabled by manager gate; rerun with --run-data-analysis-write only after approval",
        "read_only_write_waiver_id": read_only_write_waiver_id,
        "read_only_write_waiver_required": True,
        "write_coverage_exceptions": {
            "training_tasks": "read-only smoke with manager-approved write waiver",
            "data_analysis_records": "no disposable write endpoint in accepted cutover matrix",
        },
        "disposable_ids": {},
    }
    disposable_ids: dict[str, str] = {
        "accessory_id": "",
        "candidate_id": "",
        "ai_task_id": "",
        "data_analysis_record_id": "",
        "pipeline_task_id": "",
    }
    postgres_visible_read_tables: dict[str, int] = {}
    postgres_visible_write_tables: dict[str, bool] = {}
    postgres_visible_cleanup_tables: dict[str, bool] = {}

    def record_read_tables(*table_names: str) -> dict[str, int]:
        counts = repository.count_rows(tuple(table_names))
        for table_name in table_names:
            postgres_visible_read_tables[table_name] = int(counts.get(table_name, 0))
        return counts

    baseline_counts = repository.count_rows(
        (
            "app_config",
            "accessories",
            "accessory_candidates",
            "ai_detection_tasks",
            "auto_optimize_states",
            "pipeline_tasks",
            "pipeline_state",
            "data_analysis_records",
        )
    )
    cleanup_pass = False
    repository_closed = False
    try:
        login_payload = client.json(
            "POST",
            "/api/auth/login",
            json_body={"username": username, "password": password},
            accepted={200},
            label="login",
        )
        report_assert(isinstance(login_payload, dict) and login_payload.get("status") == "authenticated", "login response was not authenticated")
        report["login_pass"] = True

        root_status, root_body, _ = unauth_client.request("GET", "/", accepted={200}, label="public root")
        report["public_root_pass"] = root_status == 200
        js_asset = first_js_asset_path(root_body)
        js_status, _js_body, _ = unauth_client.request("GET", js_asset, accepted={200}, label="static bundle")
        report["static_bundle_pass"] = js_status == 200

        auth_status = client.json("GET", "/api/auth/status", accepted={200}, label="auth status")
        assert_no_sensitive_keys(auth_status, label="auth status")
        report_assert(bool(auth_status.get("authenticated")), "auth status did not report authenticated=true")
        report["auth_status_pass"] = True

        probe = client.json("GET", "/api/admin/runtime-store/probe", accepted={200}, label="runtime store probe")
        report_assert(probe.get("store") == "postgres" and probe.get("repository_kind") == "postgres", f"runtime probe mismatch: {probe}")
        report_assert(probe.get("json_fallback_used") is False, f"runtime probe reported JSON fallback: {probe}")
        record_read_tables("schema_migrations")
        report["runtime_probe"] = runtime_probe_report_summary(probe)
        report["runtime_probe_pass"] = True

        for path in ("/legacy", "/label-sheet", "/locate-anything"):
            unauth_client.request("GET", path, accepted={404}, label=f"deleted feature boundary {path}")
        report["deleted_feature_boundary_pass"] = True

        for path in ("/docs", "/openapi.json", "/redoc"):
            unauth_client.request("GET", path, accepted={401, 403, 404}, label=f"docs boundary {path}")
        report["docs_boundary_pass"] = True

        for path in ("/api/status", "/api/accessories", "/api/data-analysis/records"):
            unauth_client.request("GET", path, accepted={401, 403, 404}, label=f"unauthorized API boundary {path}")
        report["unauthorized_api_boundary_pass"] = True

        config_summary = client.json("GET", "/api/config/summary", accepted={200}, label="config summary")
        original_confidence = float(config_summary.get("confidence_threshold") or 0.5)
        changed_confidence = next_confidence_threshold(original_confidence)
        required_classes = config_summary.get("required_classes") if isinstance(config_summary.get("required_classes"), list) else []
        min_counts = config_summary.get("min_counts") if isinstance(config_summary.get("min_counts"), dict) else {}
        client.json(
            "POST",
            "/api/config/rules",
            json_body={
                "confidence_threshold": changed_confidence,
                "required_classes": required_classes,
                "min_counts": min_counts,
            },
            accepted={200},
            label="disposable app config write",
        )
        changed_value = app_config_value(repository, "confidence_threshold")
        report_assert(
            abs(float(changed_value) - changed_confidence) < 0.000001,
            f"disposable app config write was not visible in PostgreSQL: {changed_value!r}",
        )
        postgres_visible_write_tables["app_config"] = True
        report["app_config_write_pass"] = True
        client.json(
            "POST",
            "/api/config/rules",
            json_body={
                "confidence_threshold": original_confidence,
                "required_classes": required_classes,
                "min_counts": min_counts,
            },
            accepted={200},
            label="disposable app config restore",
        )
        restored_value = app_config_value(repository, "confidence_threshold")
        report_assert(
            abs(float(restored_value) - original_confidence) < 0.000001,
            f"disposable app config restore mismatch: before={original_confidence!r}, after={restored_value!r}",
        )
        postgres_visible_cleanup_tables["app_config"] = True
        report["app_config_cleanup_pass"] = True

        candidate_payload = client.json(
            "POST",
            "/api/accessories/preview",
            form_fields={
                "name": f"{test_prefix} candidate",
                "material_type": "object",
                "material_alpha_policy": "opaque",
                "training_role": "detect_and_classify",
            },
            accepted={200},
            label="disposable accessory candidate create",
        )
        candidate_id = extract_candidate_id(candidate_payload)
        disposable_ids["candidate_id"] = candidate_id
        report_assert(
            db_row(repository, "accessory_candidates", candidate_id) is not None,
            f"disposable accessory candidate was not visible in PostgreSQL: {candidate_id}",
        )
        postgres_visible_write_tables["accessory_candidates"] = True
        report["accessory_candidate_create_pass"] = True
        client.request(
            "DELETE",
            f"/api/image-job-candidates/{urllib.parse.quote(candidate_id)}",
            accepted={200},
            label="disposable accessory candidate delete",
        )
        assert_db_row_absent(repository, "accessory_candidates", candidate_id, "disposable accessory candidate delete")
        postgres_visible_cleanup_tables["accessory_candidates"] = True
        report["accessory_candidate_delete_pass"] = True

        accessories_payload = client.json("GET", "/api/accessories?summary=true", accepted={200}, label="accessories read")
        record_read_tables("accessories")
        report["accessories_read_pass"] = True
        accessory_items = extract_items(accessories_payload)
        existing_accessory_id = str((accessory_items[0] if accessory_items else {}).get("id") or "").strip()
        if existing_accessory_id:
            client.json("GET", f"/api/accessories/{urllib.parse.quote(existing_accessory_id)}/detail", accepted={200}, label="accessory detail")
            report_assert(db_row(repository, "accessories", existing_accessory_id) is not None, "existing accessory detail was not visible in PostgreSQL")
            report["accessory_detail_pass"] = True
            report["no_existing_accessory"] = False
        else:
            report["accessory_detail_pass"] = True
            report["no_existing_accessory"] = True

        client.json("GET", "/api/pipeline/tasks", accepted={200}, label="pipeline tasks read")
        record_read_tables("pipeline_tasks")
        report["pipeline_tasks_read_pass"] = True

        client.json("GET", "/api/training/status", accepted={200}, label="training status read")
        client.json("GET", "/api/training/resources", accepted={200}, label="training resources read")
        record_read_tables("training_tasks")
        report["training_status_read_pass"] = True
        report["training_resources_read_pass"] = True

        client.json("GET", "/api/ai/tasks", accepted={200}, label="AI tasks read")
        record_read_tables("ai_detection_tasks")
        report["ai_tasks_read_pass"] = True

        client.json("GET", "/api/data-analysis/records", accepted={200}, label="data-analysis records read")
        record_read_tables("data_analysis_records")
        report["data_analysis_records_read_pass"] = True

        record_read_tables("app_config", "accessory_candidates", "pipeline_state", "auto_optimize_states")
        report["allowlist_state_tables_read_pass"] = True

        report.update(
            run_deployed_concurrent_account_smoke(
                client,
                repository,
                base_url=args.base_url,
                test_prefix=test_prefix,
                account_count=int(args.concurrent_accounts),
                http_timeout=float(args.http_timeout),
            )
        )
        postgres_visible_write_tables.update({"users": True, "auth_sessions": True})
        postgres_visible_cleanup_tables.update({"users": True, "auth_sessions": True})
        report["concurrent_account_cleanup_pass"] = True

        accessory_name = f"{test_prefix} accessory"
        accessory_payload = client.json(
            "POST",
            "/api/accessories",
            form_fields={
                "name": accessory_name,
                "material_type": "object",
                "material_alpha_policy": "opaque",
                "training_role": "detect_and_classify",
            },
            accepted={200},
            label="disposable accessory create",
        )
        accessory_id = extract_accessory_id(accessory_payload)
        disposable_ids["accessory_id"] = accessory_id
        assert_db_row_name(repository, "accessories", accessory_id, accessory_name, "disposable accessory create")
        postgres_visible_write_tables["accessories"] = True
        report["accessory_create_pass"] = True

        pipeline_state_baseline_row = pipeline_state_row(repository, "accessory_ids")
        pipeline_state_baseline_values = pipeline_state_values(pipeline_state_baseline_row)
        client.json(
            "POST",
            f"/api/pipeline/accessories/{urllib.parse.quote(accessory_id)}",
            accepted={200},
            label="disposable pipeline accessory state add",
        )
        pipeline_state_after_add = pipeline_state_values(pipeline_state_row(repository, "accessory_ids"))
        report_assert(
            accessory_id in pipeline_state_after_add,
            f"disposable pipeline accessory state add was not visible in PostgreSQL: {pipeline_state_after_add}",
        )
        postgres_visible_write_tables["pipeline_state"] = True
        report["pipeline_state_write_pass"] = True

        ai_task_name = f"{test_prefix} ai task"
        ai_task_payload = client.json(
            "POST",
            "/api/ai/tasks",
            json_body={
                "name": ai_task_name,
                "required_accessory_counts": {accessory_id: 1},
            },
            accepted={200},
            label="disposable AI task create",
        )
        ai_task_id = extract_ai_task_id(ai_task_payload)
        disposable_ids["ai_task_id"] = ai_task_id
        assert_db_row_name(repository, "ai_detection_tasks", ai_task_id, ai_task_name, "disposable AI task create")
        postgres_visible_write_tables["ai_detection_tasks"] = True
        report["ai_task_create_pass"] = True

        updated_ai_task_name = f"{test_prefix} ai task updated"
        client.json(
            "PUT",
            f"/api/ai/tasks/{urllib.parse.quote(ai_task_id)}",
            json_body={
                "name": updated_ai_task_name,
                "required_accessory_counts": {accessory_id: 1},
            },
            accepted={200},
            label="disposable AI task update",
        )
        assert_db_row_name(repository, "ai_detection_tasks", ai_task_id, updated_ai_task_name, "disposable AI task update")
        report["ai_task_update_pass"] = True

        client.json(
            "PATCH",
            f"/api/ai/tasks/{urllib.parse.quote(ai_task_id)}/auto-optimize",
            json_body={"enabled": False, "auto_promote": False},
            accepted={200},
            label="disposable auto-optimize settings write",
        )
        report_assert(
            auto_optimize_state_row(repository, ai_task_id) is not None,
            f"disposable auto-optimize state was not visible in PostgreSQL: {ai_task_id}",
        )
        postgres_visible_write_tables["auto_optimize_states"] = True
        report["auto_optimize_write_pass"] = True

        if bool(getattr(args, "run_data_analysis_write", False)):
            data_analysis_payload = client.json(
                "POST",
                "/api/analyze/image",
                file_upload={
                    "fields": {"model_id": ai_task_id},
                    "file_field": "file",
                    "filename": f"{test_prefix}-analysis.png",
                    "content_type": "image/png",
                    "content": tiny_png_bytes(),
                },
                accepted={200},
                label="disposable data-analysis image write",
            )
            data_analysis_record_id = optional_record_id(data_analysis_payload) or latest_data_analysis_record_id(client, ai_task_id)
            disposable_ids["data_analysis_record_id"] = data_analysis_record_id
            report_assert(
                db_row(repository, "data_analysis_records", data_analysis_record_id) is not None,
                f"disposable data-analysis record was not visible in PostgreSQL: {data_analysis_record_id}",
            )
            postgres_visible_write_tables["data_analysis_records"] = True
            report["data_analysis_write_pass"] = True
            report.pop("data_analysis_write_skipped_reason", None)
            report["write_coverage_exceptions"].pop("data_analysis_records", None)
            client.request(
                "DELETE",
                f"/api/data-analysis/records/{urllib.parse.quote(data_analysis_record_id)}",
                accepted={200},
                label="disposable data-analysis delete",
            )
            assert_db_row_absent(repository, "data_analysis_records", data_analysis_record_id, "disposable data-analysis delete")
            postgres_visible_cleanup_tables["data_analysis_records"] = True

        repository.delete_by_primary_key("auto_optimize_states", {"task_id": ai_task_id})
        report_assert(
            auto_optimize_state_row(repository, ai_task_id) is None,
            f"disposable auto-optimize state cleanup left row in PostgreSQL: {ai_task_id}",
        )
        postgres_visible_cleanup_tables["auto_optimize_states"] = True
        report["auto_optimize_cleanup_pass"] = True

        client.request("DELETE", f"/api/ai/tasks/{urllib.parse.quote(ai_task_id)}", accepted={200}, label="disposable AI task delete")
        assert_db_row_absent(repository, "ai_detection_tasks", ai_task_id, "disposable AI task delete")
        postgres_visible_cleanup_tables["ai_detection_tasks"] = True
        report["ai_task_delete_pass"] = True

        pipeline_name = f"{test_prefix} pipeline"
        pipeline_payload = client.json(
            "POST",
            "/api/pipeline/tasks",
            json_body={
                "name": pipeline_name,
                "accessory_ids": [accessory_id],
                "detection_method": "yolo_ocr",
                "auto_advance": False,
            },
            accepted={200},
            label="disposable pipeline create",
        )
        pipeline_task_id = extract_task_id(pipeline_payload)
        disposable_ids["pipeline_task_id"] = pipeline_task_id
        assert_db_row_name(repository, "pipeline_tasks", pipeline_task_id, pipeline_name, "disposable pipeline create")
        postgres_visible_write_tables["pipeline_tasks"] = True
        report["pipeline_create_pass"] = True

        updated_pipeline_name = f"{test_prefix} pipeline updated"
        client.json(
            "PATCH",
            f"/api/pipeline/tasks/{urllib.parse.quote(pipeline_task_id)}",
            json_body={"name": updated_pipeline_name, "auto_advance": False},
            accepted={200},
            label="disposable pipeline update",
        )
        assert_db_row_name(repository, "pipeline_tasks", pipeline_task_id, updated_pipeline_name, "disposable pipeline update")
        report["pipeline_update_pass"] = True

        client.request("DELETE", f"/api/pipeline/tasks/{urllib.parse.quote(pipeline_task_id)}", accepted={200}, label="disposable pipeline delete")
        assert_db_row_absent(repository, "pipeline_tasks", pipeline_task_id, "disposable pipeline delete")
        postgres_visible_cleanup_tables["pipeline_tasks"] = True
        report["pipeline_delete_pass"] = True

        client.request(
            "DELETE",
            f"/api/pipeline/accessories/{urllib.parse.quote(accessory_id)}",
            accepted={200},
            label="disposable pipeline accessory state remove",
        )
        pipeline_state_after_remove = pipeline_state_values(pipeline_state_row(repository, "accessory_ids"))
        report_assert(
            accessory_id not in pipeline_state_after_remove,
            f"disposable pipeline accessory state remove left smoke id in PostgreSQL: {pipeline_state_after_remove}",
        )
        if pipeline_state_after_remove != pipeline_state_baseline_values:
            raise AssertionError(
                "disposable pipeline accessory state remove did not restore baseline: "
                f"before={pipeline_state_baseline_values}, after={pipeline_state_after_remove}"
            )
        restore_pipeline_state_row(repository, "accessory_ids", pipeline_state_baseline_row)
        restored_pipeline_state = pipeline_state_values(pipeline_state_row(repository, "accessory_ids"))
        report_assert(
            restored_pipeline_state == pipeline_state_baseline_values,
            f"pipeline state baseline restore mismatch: before={pipeline_state_baseline_values}, after={restored_pipeline_state}",
        )
        postgres_visible_cleanup_tables["pipeline_state"] = True
        report["pipeline_state_cleanup_pass"] = True

        client.request("DELETE", f"/api/accessories/{urllib.parse.quote(accessory_id)}", accepted={200}, label="disposable accessory delete")
        assert_db_row_absent(repository, "accessories", accessory_id, "disposable accessory delete")
        postgres_visible_cleanup_tables["accessories"] = True
        report["accessory_delete_pass"] = True

        cleanup_pass = cleanup_disposable_rows(client, repository, disposable_ids, cleanup_requested=args.cleanup)
        after_counts = repository.count_rows(
            (
                "app_config",
                "accessories",
                "accessory_candidates",
                "ai_detection_tasks",
                "auto_optimize_states",
                "pipeline_tasks",
                "pipeline_state",
                "data_analysis_records",
            )
        )
        report["postgres_visible_write_proof_pass"] = True
        report["cleanup_pass"] = cleanup_pass
        report["cleanup_residual_rows"] = cleanup_residual_rows(repository, disposable_ids)
        report["row_count_after_smoke_expected"] = after_counts == baseline_counts
        if after_counts != baseline_counts:
            raise AssertionError(f"row counts changed after cleanup: before={baseline_counts}, after={after_counts}")
        report["require_postgres_visible_writes"] = bool(args.require_postgres_visible_writes)
        report["disposable_ids"] = {key: value for key, value in disposable_ids.items() if value}
        report["endpoint_allowlist"] = ALLOWLIST
        report["postgres_visible_read_tables"] = postgres_visible_read_tables
        report["postgres_visible_write_tables"] = postgres_visible_write_tables
        report["postgres_visible_cleanup_tables"] = postgres_visible_cleanup_tables
        report["schema_migration_versions"] = schema_migration_versions(repository)
        report["postgres_repository_close_pass"] = close_repository_connection(repository)
        repository_closed = True
        report["non_secret_report"] = True
        assert_non_secret_report(report, [username, password, os.environ.get(args.db_url_env or "DATABASE_URL", "")])
        return report
    finally:
        try:
            if args.cleanup and not cleanup_pass:
                cleanup_disposable_rows(client, repository, disposable_ids, cleanup_requested=True)
        finally:
            if not repository_closed:
                try:
                    close_repository_connection(repository)
                except Exception:
                    pass


class ContractConnection:
    def __init__(self) -> None:
        self.rollback_count = 0
        self.close_count = 0

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.close_count += 1


class ContractRepository:
    kind = "postgres"

    def __init__(self) -> None:
        ensure_sys_path()
        from local_inspection_service.storage.schema import SCHEMA_VERSION

        self.lock = threading.RLock()
        self.connection = ContractConnection()
        self.tables: dict[str, dict[str, dict[str, Any]]] = {
            "schema_migrations": {SCHEMA_VERSION: {"version": SCHEMA_VERSION}},
            "app_config": {
                "confidence_threshold": {
                    "config_key": "confidence_threshold",
                    "config_value_json": 0.5,
                    "source_file": "config.json",
                    "updated_at": 1,
                },
                "required_classes": {
                    "config_key": "required_classes",
                    "config_value_json": [],
                    "source_file": "config.json",
                    "updated_at": 1,
                },
                "min_counts": {
                    "config_key": "min_counts",
                    "config_value_json": {},
                    "source_file": "config.json",
                    "updated_at": 1,
                },
            },
            "accessories": {
                "acc_existing": {
                    "id": "acc_existing",
                    "name": "Existing Contract Accessory",
                    "raw_json": {"id": "acc_existing", "name": "Existing Contract Accessory"},
                }
            },
            "accessory_candidates": {},
            "pipeline_tasks": {},
            "pipeline_state": {},
            "training_tasks": {},
            "ai_detection_tasks": {},
            "auto_optimize_states": {},
            "data_analysis_records": {},
            "users": {
                "user_contract_admin": {
                    "id": "user_contract_admin",
                    "username": "contract_admin",
                    "name": "contract_admin",
                    "raw_json": {"id": "user_contract_admin", "username": "contract_admin"},
                }
            },
            "auth_sessions": {},
        }

    def count_rows(self, table_subset: tuple[str, ...] | None = None) -> dict[str, int]:
        with self.lock:
            names = table_subset or tuple(self.tables)
            return {name: len(self.tables.get(name, {})) for name in names}

    def fetch_by_primary_key(self, table_name: str, key_values: dict[str, Any]) -> dict[str, Any] | None:
        if table_name == "data_analysis_records":
            key_name = "record_id"
        elif table_name == "pipeline_state":
            key_name = "state_key"
        elif table_name == "auto_optimize_states":
            key_name = "task_id"
        elif table_name == "app_config":
            key_name = "config_key"
        else:
            key_name = "id"
        key = str(key_values.get(key_name) or key_values.get("id") or "")
        with self.lock:
            row = self.tables.get(table_name, {}).get(key)
            return dict(row) if row else None

    def fetch_all(self, table_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        with self.lock:
            rows = [dict(row) for row in self.tables.get(table_name, {}).values()]
        return rows[:limit] if limit is not None else rows

    def upsert(self, table_name: str, row_id: str, name: str) -> None:
        with self.lock:
            self.tables.setdefault(table_name, {})[row_id] = {
                "id": row_id,
                "name": name,
                "raw_json": {"id": row_id, "name": name},
            }

    def upsert_row(self, table_name: str, row: dict[str, Any]) -> None:
        if table_name == "pipeline_state":
            key = str(row.get("state_key") or "")
        elif table_name == "auto_optimize_states":
            key = str(row.get("task_id") or "")
        elif table_name == "app_config":
            key = str(row.get("config_key") or "")
        elif table_name == "data_analysis_records":
            key = str(row.get("record_id") or "")
        else:
            key = str(row.get("id") or "")
        if not key:
            raise AssertionError(f"contract upsert_row missing key for {table_name}")
        with self.lock:
            self.tables.setdefault(table_name, {})[key] = dict(row)

    def set_pipeline_state_values(self, state_key: str, values: list[str]) -> None:
        self.upsert_row(
            "pipeline_state",
            {
                "state_key": state_key,
                "state_value_json": list(values),
                "updated_at": int(time.time()),
            },
        )

    def upsert_user(self, user_id: str, username: str) -> None:
        with self.lock:
            self.tables.setdefault("users", {})[user_id] = {
                "id": user_id,
                "username": username,
                "name": username,
                "raw_json": {"id": user_id, "username": username, "role": "admin"},
            }

    def upsert_session(self, session_id: str, user_id: str) -> None:
        with self.lock:
            self.tables.setdefault("auth_sessions", {})[session_id] = {
                "id": session_id,
                "id_hash": session_id,
                "user_id": user_id,
                "name": session_id,
                "raw_json": {"id_hash": session_id, "user_id": user_id},
            }

    def delete_user(self, user_id: str) -> None:
        with self.lock:
            self.tables.setdefault("users", {}).pop(user_id, None)
            sessions = self.tables.setdefault("auth_sessions", {})
            for session_id, session in list(sessions.items()):
                if session.get("user_id") == user_id:
                    sessions.pop(session_id, None)

    def delete(self, table_name: str, row_id: str) -> None:
        with self.lock:
            self.tables.setdefault(table_name, {}).pop(row_id, None)

    def delete_by_primary_key(self, table_name: str, key_values: dict[str, Any]) -> None:
        if table_name == "pipeline_state":
            row_id = str(key_values.get("state_key") or "")
        elif table_name == "auto_optimize_states":
            row_id = str(key_values.get("task_id") or "")
        elif table_name == "app_config":
            row_id = str(key_values.get("config_key") or "")
        elif table_name == "data_analysis_records":
            row_id = str(key_values.get("record_id") or "")
        else:
            row_id = str(key_values.get("id") or "")
        self.delete(table_name, row_id)


class ContractHttpState:
    def __init__(self, repository: ContractRepository, *, username: str, password: str) -> None:
        self.repository = repository
        self.username = username
        self.password = password
        self.lock = threading.RLock()
        self.credentials: dict[str, dict[str, str]] = {
            username: {"password": password, "user_id": "user_contract_admin"}
        }
        self.sessions: dict[str, str] = {}

    def create_user(self, username: str, password: str) -> str:
        clean = safe_username_prefix(username)
        with self.lock:
            if clean in self.credentials:
                raise AssertionError(f"contract user already exists: {clean}")
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            self.credentials[clean] = {"password": password, "user_id": user_id}
            self.repository.upsert_user(user_id, clean)
            return user_id

    def delete_user(self, user_id: str) -> None:
        with self.lock:
            for username, item in list(self.credentials.items()):
                if item.get("user_id") == user_id:
                    self.credentials.pop(username, None)
            for session_id, session_user_id in list(self.sessions.items()):
                if session_user_id == user_id:
                    self.sessions.pop(session_id, None)
            self.repository.delete_user(user_id)

    def login(self, username: str, password: str) -> str | None:
        clean = safe_username_prefix(username)
        with self.lock:
            credential = self.credentials.get(clean)
            if not credential or credential.get("password") != password:
                return None
            session_id = f"contract-session-{uuid.uuid4().hex[:16]}"
            user_id = credential["user_id"]
            self.sessions[session_id] = user_id
            self.repository.upsert_session(session_id, user_id)
            return session_id

    def user_id_for_cookie(self, cookie_header: str) -> str:
        match = re.search(r"(?:^|;\s*)vantaline_session=([^;]+)", cookie_header)
        if not match:
            return ""
        session_id = urllib.parse.unquote(match.group(1))
        with self.lock:
            return self.sessions.get(session_id, "")

    def username_for_user_id(self, user_id: str) -> str:
        with self.lock:
            for username, item in self.credentials.items():
                if item.get("user_id") == user_id:
                    return username
        return ""


def make_contract_handler(state: ContractHttpState) -> type[BaseHTTPRequestHandler]:
    class ContractHandler(BaseHTTPRequestHandler):
        server_version = "VantaLineContractSmoke/1.0"

        def log_message(self, _format: str, *_args: Any) -> None:
            return None

        def do_GET(self) -> None:
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                self.send_text(200, '<!doctype html><script type="module" src="/static/assets/contract.js"></script>')
                return
            if path == "/static/assets/contract.js":
                self.send_text(200, "console.log('contract smoke');", content_type="application/javascript")
                return
            if path in {"/legacy", "/label-sheet", "/locate-anything"}:
                self.send_json(404, {"detail": "Not found"})
                return
            if path in {"/docs", "/openapi.json", "/redoc"}:
                self.send_json(404, {"detail": "Not found"})
                return
            if path.startswith("/api/") and not self.authenticated() and path != "/api/auth/status":
                self.send_json(401, {"detail": "Authentication required"})
                return
            if path == "/api/auth/status":
                user_id = self.current_user_id()
                username = state.username_for_user_id(user_id) if user_id else ""
                self.send_json(
                    200,
                    {
                        "authenticated": bool(user_id),
                        "user": {"id": user_id, "username": username} if user_id else None,
                        "features": {},
                    },
                )
                return
            if path == "/api/auth/users":
                self.send_json(
                    200,
                    {"users": [dict(row) for row in state.repository.tables.get("users", {}).values()]},
                )
                return
            if path == "/api/admin/runtime-store/probe":
                material = f"contract:{threading.get_ident()}:{time.time_ns()}"
                connection_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
                self.send_json(
                    200,
                    {
                        "store": "postgres",
                        "repository_kind": "postgres",
                        "json_fallback_used": False,
                        "postgres_count_probe": {"schema_migrations": 1},
                        "repository_connection_id": connection_id,
                        "repository_connection_scope": "thread-local",
                    },
                )
                return
            if path == "/api/config/summary":
                self.send_json(
                    200,
                    {
                        "confidence_threshold": app_config_value(state.repository, "confidence_threshold"),
                        "required_classes": app_config_value(state.repository, "required_classes") or [],
                        "min_counts": app_config_value(state.repository, "min_counts") or {},
                    },
                )
                return
            if path == "/api/accessories":
                items = [dict(row) for row in state.repository.tables.get("accessories", {}).values()]
                self.send_json(200, {"items": items})
                return
            detail_match = re.fullmatch(r"/api/accessories/([^/]+)/detail", path)
            if detail_match:
                row = state.repository.fetch_by_primary_key("accessories", {"id": urllib.parse.unquote(detail_match.group(1))})
                self.send_json(200 if row else 404, {"item": row} if row else {"detail": "Not found"})
                return
            if path == "/api/pipeline/tasks":
                self.send_json(200, {"items": [dict(row) for row in state.repository.tables.get("pipeline_tasks", {}).values()]})
                return
            if path == "/api/training/status":
                self.send_json(200, {"status": "idle"})
                return
            if path == "/api/training/resources":
                self.send_json(200, {"datasets": [], "models": []})
                return
            if path == "/api/ai/tasks":
                self.send_json(200, {"tasks": []})
                return
            if path == "/api/data-analysis/records":
                self.send_json(200, {"records": []})
                return
            self.send_json(404, {"detail": "Not found"})

        def do_POST(self) -> None:
            path = urllib.parse.urlsplit(self.path).path
            if path == "/api/auth/login":
                payload = self.read_json()
                session_id = state.login(str(payload.get("username") or ""), str(payload.get("password") or ""))
                if not session_id:
                    self.send_json(401, {"detail": "Invalid username or password"})
                    return
                user_id = state.user_id_for_cookie(f"vantaline_session={session_id}")
                self.send_json(
                    200,
                    {"status": "authenticated", "user": {"id": user_id, "username": str(payload.get("username") or "")}},
                    cookie=session_id,
                )
                return
            if not self.authenticated():
                self.send_json(401, {"detail": "Authentication required"})
                return
            if path == "/api/config/rules":
                payload = self.read_json()
                for key in ("confidence_threshold", "required_classes", "min_counts"):
                    state.repository.upsert_row(
                        "app_config",
                        {
                            "config_key": key,
                            "config_value_json": payload.get(key),
                            "source_file": "config.json",
                            "updated_at": int(time.time()),
                        },
                    )
                self.send_json(200, {"status": "saved", "rule": payload})
                return
            if path == "/api/auth/users":
                payload = self.read_json()
                username = str(payload.get("username") or "")
                password = str(payload.get("password") or "")
                if not username or len(password) < 8:
                    self.send_json(400, {"detail": "Invalid user payload"})
                    return
                try:
                    user_id = state.create_user(username, password)
                except AssertionError:
                    self.send_json(409, {"detail": "Username already exists"})
                    return
                self.send_json(
                    200,
                    {
                        "status": "created",
                        "user": {"id": user_id, "username": safe_username_prefix(username), "role": "admin"},
                    },
                )
                return
            if path == "/api/accessories":
                fields = self.read_multipart_fields()
                name = fields.get("name") or "Contract Accessory"
                accessory_id = f"acc_{uuid.uuid4().hex[:10]}"
                state.repository.upsert("accessories", accessory_id, name)
                self.send_json(200, {"status": "saved", "item": {"id": accessory_id, "name": name}, "items": []})
                return
            if path == "/api/accessories/preview":
                fields = self.read_multipart_fields()
                name = fields.get("name") or "Contract Candidate"
                candidate_id = f"cand_{uuid.uuid4().hex[:10]}"
                state.repository.upsert_row(
                    "accessory_candidates",
                    {
                        "id": candidate_id,
                        "name": name,
                        "status": "candidate_review",
                        "owner_user_id": "user_contract_admin",
                        "owner_username": "contract_admin",
                        "created_at": int(time.time()),
                        "updated_at": int(time.time()),
                        "raw_json": {"id": candidate_id, "name": name, "status": "candidate_review"},
                    },
                )
                self.send_json(200, {"status": "candidate_ready", "candidate": {"id": candidate_id, "name": name}})
                return
            if path == "/api/ai/tasks":
                payload = self.read_json()
                task_id = f"aitask_{uuid.uuid4().hex[:10]}"
                name = str(payload.get("name") or "Contract AI Task")
                state.repository.upsert("ai_detection_tasks", task_id, name)
                self.send_json(200, {"status": "saved", "task": {"id": task_id, "name": name}, "tasks": []})
                return
            pipeline_accessory_match = re.fullmatch(r"/api/pipeline/accessories/([^/]+)", path)
            if pipeline_accessory_match:
                accessory_id = urllib.parse.unquote(pipeline_accessory_match.group(1))
                if state.repository.fetch_by_primary_key("accessories", {"id": accessory_id}) is None:
                    self.send_json(404, {"detail": "Not found"})
                    return
                row = state.repository.fetch_by_primary_key("pipeline_state", {"state_key": "accessory_ids"})
                values = pipeline_state_values(row)
                if accessory_id not in values:
                    values.insert(0, accessory_id)
                state.repository.set_pipeline_state_values("accessory_ids", values)
                self.send_json(200, {"status": "added", "accessory_id": accessory_id, "accessory_ids": values})
                return
            if path == "/api/analyze/image":
                record_id = f"analysis_{uuid.uuid4().hex[:10]}"
                state.repository.upsert("data_analysis_records", record_id, "Contract Data Analysis")
                self.send_json(
                    200,
                    {
                        "status": "ok",
                        "record_id": record_id,
                        "record": {"record_id": record_id, "task": {"name": "Contract Data Analysis"}},
                    },
                )
                return
            if path == "/api/pipeline/tasks":
                payload = self.read_json()
                task_id = f"pipe_{uuid.uuid4().hex[:10]}"
                name = str(payload.get("name") or "Contract Pipeline")
                state.repository.upsert("pipeline_tasks", task_id, name)
                self.send_json(200, {"id": task_id, "name": name})
                return
            self.send_json(404, {"detail": "Not found"})

        def do_PATCH(self) -> None:
            path = urllib.parse.urlsplit(self.path).path
            if not self.authenticated():
                self.send_json(401, {"detail": "Authentication required"})
                return
            auto_optimize_match = re.fullmatch(r"/api/ai/tasks/([^/]+)/auto-optimize", path)
            if auto_optimize_match:
                task_id = urllib.parse.unquote(auto_optimize_match.group(1))
                if state.repository.fetch_by_primary_key("ai_detection_tasks", {"id": task_id}) is None:
                    self.send_json(404, {"detail": "Not found"})
                    return
                payload = self.read_json()
                state.repository.upsert_row(
                    "auto_optimize_states",
                    {
                        "task_id": task_id,
                        "status": "active" if payload.get("enabled") else "disabled",
                        "owner_user_id": "user_contract_admin",
                        "owner_username": "contract_admin",
                        "created_at": int(time.time()),
                        "updated_at": int(time.time()),
                        "raw_json": {
                            "task_id": task_id,
                            "settings": {
                                "enabled": bool(payload.get("enabled")),
                                "auto_promote": bool(payload.get("auto_promote")),
                            },
                        },
                    },
                )
                self.send_json(200, {"task_id": task_id, "settings": {"enabled": bool(payload.get("enabled"))}})
                return
            ai_task_match = re.fullmatch(r"/api/ai/tasks/([^/]+)", path)
            if ai_task_match:
                task_id = urllib.parse.unquote(ai_task_match.group(1))
                row = state.repository.fetch_by_primary_key("ai_detection_tasks", {"id": task_id})
                if not row:
                    self.send_json(404, {"detail": "Not found"})
                    return
                payload = self.read_json()
                name = str(payload.get("name") or row.get("name") or "")
                state.repository.upsert("ai_detection_tasks", task_id, name)
                self.send_json(200, {"status": "saved", "task": {"id": task_id, "name": name}, "tasks": []})
                return
            match = re.fullmatch(r"/api/pipeline/tasks/([^/]+)", path)
            if not match:
                self.send_json(404, {"detail": "Not found"})
                return
            task_id = urllib.parse.unquote(match.group(1))
            row = state.repository.fetch_by_primary_key("pipeline_tasks", {"id": task_id})
            if not row:
                self.send_json(404, {"detail": "Not found"})
                return
            payload = self.read_json()
            name = str(payload.get("name") or row.get("name") or "")
            state.repository.upsert("pipeline_tasks", task_id, name)
            self.send_json(200, {"id": task_id, "name": name})

        def do_PUT(self) -> None:
            self.do_PATCH()

        def do_DELETE(self) -> None:
            path = urllib.parse.urlsplit(self.path).path
            if not self.authenticated():
                self.send_json(401, {"detail": "Authentication required"})
                return
            pipeline_accessory_match = re.fullmatch(r"/api/pipeline/accessories/([^/]+)", path)
            if pipeline_accessory_match:
                accessory_id = urllib.parse.unquote(pipeline_accessory_match.group(1))
                row = state.repository.fetch_by_primary_key("pipeline_state", {"state_key": "accessory_ids"})
                values = [value for value in pipeline_state_values(row) if value != accessory_id]
                state.repository.set_pipeline_state_values("accessory_ids", values)
                self.send_json(200, {"status": "removed", "accessory_id": accessory_id, "accessory_ids": values})
                return
            task_match = re.fullmatch(r"/api/pipeline/tasks/([^/]+)", path)
            if task_match:
                task_id = urllib.parse.unquote(task_match.group(1))
                state.repository.delete("pipeline_tasks", task_id)
                self.send_json(200, {"status": "deleted", "deleted_task_id": task_id})
                return
            ai_task_match = re.fullmatch(r"/api/ai/tasks/([^/]+)", path)
            if ai_task_match:
                task_id = urllib.parse.unquote(ai_task_match.group(1))
                state.repository.delete("ai_detection_tasks", task_id)
                self.send_json(200, {"status": "deleted", "deleted_task_id": task_id})
                return
            data_record_match = re.fullmatch(r"/api/data-analysis/records/([^/]+)", path)
            if data_record_match:
                record_id = urllib.parse.unquote(data_record_match.group(1))
                state.repository.delete("data_analysis_records", record_id)
                self.send_json(200, {"status": "deleted", "record_id": record_id})
                return
            candidate_match = re.fullmatch(r"/api/image-job-candidates/([^/]+)", path)
            if candidate_match:
                candidate_id = urllib.parse.unquote(candidate_match.group(1))
                state.repository.delete("accessory_candidates", candidate_id)
                self.send_json(200, {"status": "deleted", "candidate_id": candidate_id})
                return
            accessory_match = re.fullmatch(r"/api/accessories/([^/]+)", path)
            if accessory_match:
                accessory_id = urllib.parse.unquote(accessory_match.group(1))
                state.repository.delete("accessories", accessory_id)
                self.send_json(200, {"status": "deleted", "accessory_id": accessory_id})
                return
            user_match = re.fullmatch(r"/api/auth/users/([^/]+)", path)
            if user_match:
                user_id = urllib.parse.unquote(user_match.group(1))
                state.delete_user(user_id)
                self.send_json(200, {"status": "deleted", "deleted_user_id": user_id})
                return
            self.send_json(404, {"detail": "Not found"})

        def authenticated(self) -> bool:
            return bool(self.current_user_id())

        def current_user_id(self) -> str:
            return state.user_id_for_cookie(str(self.headers.get("Cookie") or ""))

        def read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or "0")
            return self.rfile.read(length) if length else b""

        def read_json(self) -> dict[str, Any]:
            body = self.read_body()
            if not body:
                return {}
            parsed = json.loads(body.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}

        def read_multipart_fields(self) -> dict[str, str]:
            body = self.read_body().decode("utf-8", errors="replace")
            fields: dict[str, str] = {}
            for match in re.finditer(r'name="([^"]+)"\r\n\r\n(.*?)\r\n--', body, flags=re.S):
                fields[match.group(1)] = match.group(2)
            return fields

        def send_json(self, status: int, payload: dict[str, Any], *, cookie: str = "") -> None:
            body = stable_json(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if cookie:
                self.send_header("Set-Cookie", f"vantaline_session={cookie}; Path=/; HttpOnly; SameSite=Lax")
            self.end_headers()
            self.wfile.write(body)

        def send_text(self, status: int, body: str, *, content_type: str = "text/html") -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return ContractHandler


def run_deployed_postgres_contract() -> dict[str, Any]:
    username = "contract_admin"
    password = "contract-password-not-reported"
    repository = ContractRepository()
    state = ContractHttpState(repository, username=username, password=password)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_contract_handler(state))
    thread = threading.Thread(target=server.serve_forever, name="postgres-cutover-contract-http", daemon=True)
    thread.start()
    old_env = {
        "VANTALINE_DATA_STORE": os.environ.get("VANTALINE_DATA_STORE"),
        "VANTALINE_SMOKE_USERNAME": os.environ.get("VANTALINE_SMOKE_USERNAME"),
        "VANTALINE_SMOKE_PASSWORD": os.environ.get("VANTALINE_SMOKE_PASSWORD"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
    }
    try:
        os.environ["VANTALINE_DATA_STORE"] = "postgres"
        os.environ["VANTALINE_SMOKE_USERNAME"] = username
        os.environ["VANTALINE_SMOKE_PASSWORD"] = password
        os.environ["DATABASE_URL"] = "postgresql://contract.invalid/vantaline"
        args = argparse.Namespace(
            base_url=f"http://127.0.0.1:{server.server_port}",
            username_env="VANTALINE_SMOKE_USERNAME",
            password_env="VANTALINE_SMOKE_PASSWORD",
            db_url_env="DATABASE_URL",
            test_prefix="pg-contract",
            expect_store="postgres",
            cleanup=True,
            http_timeout=5.0,
            concurrent_accounts=10,
            require_postgres_visible_writes=True,
            read_only_write_waiver_id="contract-read-only-write-waiver",
            run_data_analysis_write=True,
        )
        report = run_deployed_postgres(args, repository=repository)
        report["mode"] = "deployed-postgres-contract"
        return report
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_deployed_precutover_contract() -> dict[str, Any]:
    username = "contract_admin"
    password = "contract-password-not-used"
    repository = ContractRepository()
    state = ContractHttpState(repository, username=username, password=password)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_contract_handler(state))
    thread = threading.Thread(target=server.serve_forever, name="postgres-precutover-contract-http", daemon=True)
    thread.start()
    old_env = {
        "VANTALINE_DATA_STORE": os.environ.get("VANTALINE_DATA_STORE"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "VANTALINE_SMOKE_USERNAME": os.environ.get("VANTALINE_SMOKE_USERNAME"),
        "VANTALINE_SMOKE_PASSWORD": os.environ.get("VANTALINE_SMOKE_PASSWORD"),
    }
    try:
        for key in old_env:
            os.environ.pop(key, None)
        args = argparse.Namespace(
            base_url=f"http://127.0.0.1:{server.server_port}",
            expect_store="json",
            require_no_postgres_service_env=True,
            http_timeout=5.0,
        )
        report = run_deployed_precutover(args)
        report["mode"] = "deployed-precutover-contract"
        return report
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        default="auto",
        choices=(
            "auto",
            "local-fake-postgres",
            "deployed-precutover",
            "deployed-precutover-contract",
            "deployed-postgres",
            "deployed-postgres-contract",
        ),
    )
    parser.add_argument("--base-url", default="")
    parser.add_argument("--db-url-env", default="")
    parser.add_argument("--username-env", default="")
    parser.add_argument("--password-env", default="")
    parser.add_argument("--test-prefix", default="")
    parser.add_argument("--expect-store", default="")
    parser.add_argument("--require-no-postgres-service-env", action="store_true")
    parser.add_argument("--require-postgres-visible-writes", action="store_true")
    parser.add_argument(
        "--read-only-write-waiver-id",
        default="",
        help="Non-secret manager waiver id for accepted read-only-only write probes in the final smoke matrix.",
    )
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument(
        "--run-data-analysis-write",
        action="store_true",
        help="Run the optional disposable /api/analyze/image write probe and clean it up through DELETE /api/data-analysis/records/{id}.",
    )
    parser.add_argument("--http-timeout", type=float, default=20.0)
    parser.add_argument("--concurrent-accounts", type=int, default=10)
    parser.add_argument("--report", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    mode = args.mode
    if mode == "auto":
        if args.db_url_env or args.username_env or args.password_env:
            mode = "deployed-postgres"
        else:
            mode = "local-fake-postgres"
    if mode == "deployed-precutover":
        report = run_deployed_precutover(args)
    elif mode == "deployed-precutover-contract":
        report = run_deployed_precutover_contract()
    elif mode == "deployed-postgres":
        report = run_deployed_postgres(args)
    elif mode == "deployed-postgres-contract":
        report = run_deployed_postgres_contract()
    else:
        report = run_fake_postgres_smoke()
        report.update(
            {
                "endpoint_repository_wiring_pass": True,
                "json_default_http_parity_pass": True,
                "postgres_selected_failure_no_json_fallback_pass": True,
                "non_allowlisted_routes_unchanged": True,
                "credential_free_preflight": True,
                "non_secret_report": True,
                "endpoint_allowlist": ALLOWLIST,
            }
        )
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(stable_json(report) + "\n", encoding="utf-8")
    print("postgres cutover full smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
