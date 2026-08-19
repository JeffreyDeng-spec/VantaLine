#!/usr/bin/env python3
"""Smoke tests for the disabled-default PostgreSQL runtime repository helpers."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.storage.postgres_runtime_repository import (  # noqa: E402
    PostgresRuntimeRepository,
    PostgresRuntimeRepositoryError,
)


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.description: list[tuple[str]] = []
        self.rows: list[tuple[Any, ...]] = []
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.connection.statements.append((sql, params))
        normalized = " ".join(sql.split())
        if normalized.startswith('SELECT COUNT(*) AS count FROM "vantaline"."accessories"'):
            self.description = [("count",)]
            self.rows = [(2,)]
            return
        if normalized.startswith('SELECT "id", "username"'):
            self.description = [
                ("id",),
                ("username",),
                ("display_name",),
                ("role",),
                ("permissions_json",),
                ("password_hash",),
                ("active",),
                ("created_at",),
                ("updated_at",),
                ("raw_json",),
            ]
            self.rows = [
                (
                    "user_1",
                    "admin",
                    "Admin",
                    "admin",
                    '["task_pipeline"]',
                    "hash",
                    True,
                    1,
                    2,
                    '{"id":"user_1"}',
                )
            ]
            return
        if normalized.startswith('SELECT "id", "class_id"') and 'WHERE "id" = %s' in normalized:
            self.description = [
                ("id",),
                ("class_id",),
                ("name",),
                ("status",),
                ("material_type",),
                ("owner_user_id",),
                ("owner_username",),
                ("created_at",),
                ("updated_at",),
                ("raw_json",),
            ]
            self.rows = [
                (
                    params[0],
                    "cls_1",
                    "Fuse",
                    "active",
                    "metal",
                    "user_1",
                    "admin",
                    1,
                    2,
                    '{"id":"acc_1"}',
                )
            ]
            return
        self.description = []
        self.rows = []

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)

    def close(self) -> None:
        self.closed = True


class CloseFailingCursor(FakeCursor):
    def close(self) -> None:
        self.closed = True
        raise RuntimeError("cursor close failed")


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.cursor_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self) -> FakeCursor:
        self.cursor_count += 1
        return FakeCursor(self)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


class CloseFailingConnection(FakeConnection):
    def cursor(self) -> FakeCursor:
        self.cursor_count += 1
        return CloseFailingCursor(self)


def assert_count_rows_uses_safe_schema_table_names() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    counts = repository.count_rows(("accessories",))
    if counts != {"accessories": 2}:
        raise AssertionError(f"count mismatch: {counts}")
    sql, params = connection.statements[-1]
    if sql != 'SELECT COUNT(*) AS count FROM "vantaline"."accessories"' or params:
        raise AssertionError(f"unexpected count SQL: {sql!r}, params={params!r}")
    if connection.rollback_count != 1:
        raise AssertionError(f"count_rows must end the read transaction once, got {connection.rollback_count}")


def assert_fetch_all_decodes_json_columns() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    rows = repository.fetch_all("users", limit=1)
    if rows[0]["permissions_json"] != ["task_pipeline"] or rows[0]["raw_json"] != {"id": "user_1"}:
        raise AssertionError(f"JSON columns were not decoded: {rows}")
    sql, params = connection.statements[-1]
    if 'FROM "vantaline"."users"' not in sql or "LIMIT %s" not in sql or params != (1,):
        raise AssertionError(f"unexpected fetch SQL: {sql!r}, params={params!r}")
    if connection.rollback_count != 1:
        raise AssertionError(f"fetch_all must end the read transaction once, got {connection.rollback_count}")


def assert_upsert_row_uses_primary_key_conflict() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    repository.upsert_row(
        "accessories",
        {
            "id": "acc_1",
            "class_id": "cls_1",
            "name": "Fuse",
            "status": "active",
            "material_type": "metal",
            "owner_user_id": "user_1",
            "owner_username": "admin",
            "created_at": 1,
            "updated_at": 2,
            "raw_json": {"id": "acc_1", "name": "Fuse"},
        },
    )
    sql, params = connection.statements[-1]
    if 'INSERT INTO "vantaline"."accessories"' not in sql:
        raise AssertionError(f"unexpected upsert target: {sql}")
    if 'ON CONFLICT ("id") DO UPDATE SET' not in sql:
        raise AssertionError(f"missing primary-key upsert clause: {sql}")
    if params[-1] != '{"id":"acc_1","name":"Fuse"}':
        raise AssertionError(f"raw_json was not compact JSON: {params[-1]!r}")
    if "%s::jsonb" not in sql:
        raise AssertionError(f"JSONB columns must use explicit jsonb casts: {sql}")
    if connection.commit_count != 1 or connection.rollback_count != 0:
        raise AssertionError("successful upsert should commit once without rollback")


def assert_string_config_values_are_valid_jsonb_parameters() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    repository.upsert_row(
        "app_config",
        {
            "config_key": "active_model_id",
            "config_value_json": "yolo26_2class_ocr",
            "source_file": "config.json",
            "updated_at": 1,
        },
    )
    sql, params = connection.statements[-1]
    if '"config_value_json"' not in sql or "%s::jsonb" not in sql:
        raise AssertionError(f"app_config JSONB value must be explicitly cast: {sql}")
    if params[1] != '"yolo26_2class_ocr"':
        raise AssertionError(f"plain string config value was not encoded as a JSON string: {params!r}")


def assert_fetch_by_primary_key_uses_where_clause() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    row = repository.fetch_by_primary_key("accessories", {"id": "acc_1"})
    if not row or row.get("raw_json") != {"id": "acc_1"}:
        raise AssertionError(f"primary-key fetch did not decode row: {row}")
    sql, params = connection.statements[-1]
    if 'WHERE "id" = %s' not in sql or params != ("acc_1",):
        raise AssertionError(f"unexpected primary-key fetch SQL: {sql!r}, params={params!r}")
    if connection.rollback_count != 1:
        raise AssertionError(f"fetch_by_primary_key must end the read transaction once, got {connection.rollback_count}")


def assert_read_transaction_ends_even_when_cursor_close_fails() -> None:
    connection = CloseFailingConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    try:
        repository.count_rows(("accessories",))
    except RuntimeError as exc:
        if "cursor close failed" not in str(exc):
            raise AssertionError(f"unexpected close failure: {exc}") from exc
    else:
        raise AssertionError("cursor close failure must still propagate")
    if connection.rollback_count != 1:
        raise AssertionError(f"read transaction cleanup must run after cursor close failure, got {connection.rollback_count}")


def assert_replace_all_validates_before_delete_and_commits_once() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    try:
        repository.replace_all("accessories", [{"id": "acc_incomplete"}])
    except PostgresRuntimeRepositoryError as exc:
        if "Missing column values" not in str(exc):
            raise AssertionError(f"wrong replace validation error: {exc}") from exc
    else:
        raise AssertionError("replace_all with incomplete rows must fail")
    if connection.statements:
        raise AssertionError(f"replace_all must validate rows before DELETE: {connection.statements}")

    repository.replace_all(
        "accessories",
        [
            {
                "id": "acc_1",
                "class_id": "cls_1",
                "name": "Fuse",
                "status": "active",
                "material_type": "metal",
                "owner_user_id": "user_1",
                "owner_username": "admin",
                "created_at": 1,
                "updated_at": 2,
                "raw_json": {"id": "acc_1"},
            }
        ],
    )
    statements = [sql for sql, _ in connection.statements]
    if not statements[0].startswith('DELETE FROM "vantaline"."accessories"'):
        raise AssertionError(f"replace_all must delete table first, got: {statements}")
    if 'INSERT INTO "vantaline"."accessories"' not in statements[1]:
        raise AssertionError(f"replace_all must upsert rows after delete, got: {statements}")
    if connection.commit_count != 1 or connection.rollback_count != 0:
        raise AssertionError("successful replace_all should commit once without rollback")


def assert_replace_tables_validates_all_tables_before_delete() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    try:
        repository.replace_tables(
            {
                "users": [
                    {
                        "id": "user_1",
                        "username": "admin",
                        "display_name": "Admin",
                        "role": "admin",
                        "permissions_json": ["inspection"],
                        "password_hash": "hash",
                        "active": True,
                        "created_at": 1,
                        "updated_at": 2,
                        "raw_json": {"id": "user_1"},
                    }
                ],
                "auth_sessions": [{"id_hash": "session_only"}],
            }
        )
    except PostgresRuntimeRepositoryError as exc:
        if "Missing column values" not in str(exc):
            raise AssertionError(f"wrong replace_tables validation error: {exc}") from exc
    else:
        raise AssertionError("replace_tables must fail when any table row is incomplete")
    if connection.statements:
        raise AssertionError(f"replace_tables must validate every table before any DELETE: {connection.statements}")

    repository.replace_tables(
        {
            "users": [
                {
                    "id": "user_1",
                    "username": "admin",
                    "display_name": "Admin",
                    "role": "admin",
                    "permissions_json": ["inspection"],
                    "password_hash": "hash",
                    "active": True,
                    "created_at": 1,
                    "updated_at": 2,
                    "raw_json": {"id": "user_1"},
                }
            ],
            "auth_sessions": [
                {
                    "id_hash": "hash_1",
                    "user_id": "user_1",
                    "created_at": 1,
                    "last_seen_at": 2,
                    "expires_at": 3,
                    "raw_json": {"id_hash": "hash_1", "user_id": "user_1"},
                }
            ],
        }
    )
    statements = [sql for sql, _ in connection.statements]
    if not statements[0].startswith('DELETE FROM "vantaline"."users"'):
        raise AssertionError(f"replace_tables should delete first table first, got: {statements}")
    if not any(sql.startswith('DELETE FROM "vantaline"."auth_sessions"') for sql in statements):
        raise AssertionError(f"replace_tables did not delete second table: {statements}")
    if connection.commit_count != 1 or connection.rollback_count != 0:
        raise AssertionError("successful replace_tables should commit once without rollback")


def assert_upsert_requires_primary_key_before_sql() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    try:
        repository.upsert_row("accessories", {})
    except PostgresRuntimeRepositoryError as exc:
        if "Missing primary key values" not in str(exc) or "id" not in str(exc):
            raise AssertionError(f"wrong missing-primary-key error: {exc}") from exc
    else:
        raise AssertionError("upsert without primary key must fail")
    if connection.cursor_count != 0 or connection.statements:
        raise AssertionError("missing-primary-key upsert must fail before cursor creation or SQL execution")
    if connection.commit_count != 0 or connection.rollback_count != 0:
        raise AssertionError("missing-primary-key upsert must not commit or rollback")

    try:
        repository.upsert_row("accessories", {"id": "   "})
    except PostgresRuntimeRepositoryError:
        pass
    else:
        raise AssertionError("blank primary key must fail")
    if connection.cursor_count != 0 or connection.statements or connection.commit_count != 0:
        raise AssertionError("blank-primary-key upsert must not execute SQL or commit")


def assert_upsert_requires_complete_schema_row_before_sql() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    try:
        repository.upsert_row("accessories", {"id": "acc_minimal"})
    except PostgresRuntimeRepositoryError as exc:
        if "Missing column values" not in str(exc) or "class_id" not in str(exc):
            raise AssertionError(f"wrong missing-column error: {exc}") from exc
    else:
        raise AssertionError("upsert with missing non-primary columns must fail")
    if connection.cursor_count != 0 or connection.statements:
        raise AssertionError("missing-column upsert must fail before cursor creation or SQL execution")
    if connection.commit_count != 0 or connection.rollback_count != 0:
        raise AssertionError("missing-column upsert must not commit or rollback")


def assert_delete_requires_primary_key_values() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    try:
        repository.delete_by_primary_key("accessories", {})
    except PostgresRuntimeRepositoryError as exc:
        if "Missing primary key values" not in str(exc):
            raise AssertionError(f"wrong missing-key error: {exc}") from exc
    else:
        raise AssertionError("delete without primary key must fail")


def assert_rejects_unknown_table_and_unsafe_schema() -> None:
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    try:
        repository.count_rows(("accessories; drop schema public",))
    except PostgresRuntimeRepositoryError:
        pass
    else:
        raise AssertionError("unknown or unsafe table name must fail")

    try:
        repository.fetch_all("not_a_runtime_table")
    except PostgresRuntimeRepositoryError:
        pass
    else:
        raise AssertionError("fetching an unknown table must fail through repository validation")

    try:
        PostgresRuntimeRepository(
            connection=connection,
            database_url_redacted="postgresql:///vantaline",
            schema_name="vantaline; drop schema public",
        )
    except PostgresRuntimeRepositoryError:
        pass
    else:
        raise AssertionError("unsafe schema name must fail")


def main() -> None:
    assert_count_rows_uses_safe_schema_table_names()
    assert_fetch_all_decodes_json_columns()
    assert_upsert_row_uses_primary_key_conflict()
    assert_string_config_values_are_valid_jsonb_parameters()
    assert_fetch_by_primary_key_uses_where_clause()
    assert_read_transaction_ends_even_when_cursor_close_fails()
    assert_replace_all_validates_before_delete_and_commits_once()
    assert_replace_tables_validates_all_tables_before_delete()
    assert_upsert_requires_primary_key_before_sql()
    assert_upsert_requires_complete_schema_row_before_sql()
    assert_delete_requires_primary_key_values()
    assert_rejects_unknown_table_and_unsafe_schema()
    print("postgres runtime repository smoke passed")


if __name__ == "__main__":
    main()
