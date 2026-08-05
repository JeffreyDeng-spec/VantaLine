"""PostgreSQL runtime repository contract helpers.

This module is import-side-effect free: it does not import a PostgreSQL driver,
open a connection, read environment variables, or touch FastAPI endpoint code.
Connections are supplied by the disabled-default runtime selector.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .schema import columns_for_table, table_names


JSON_COLUMNS = frozenset(
    {
        "metadata_json",
        "permissions_json",
        "raw_json",
        "config_value_json",
        "state_value_json",
        "payload_json",
    }
)

BOOLEAN_COLUMNS = frozenset({"active", "path_exists"})

PRIMARY_KEY_COLUMNS = {
    "schema_migrations": ("version",),
    "users": ("id",),
    "auth_sessions": ("id_hash",),
    "app_config": ("config_key",),
    "accessories": ("id",),
    "accessory_assets": ("id",),
    "accessory_candidates": ("id",),
    "ai_detection_tasks": ("id",),
    "data_analysis_records": ("record_id",),
    "training_tasks": ("id",),
    "pipeline_tasks": ("id",),
    "pipeline_state": ("state_key",),
    "auto_optimize_states": ("task_id",),
    "audit_events": ("id",),
}

VALID_TABLE_NAMES = frozenset(table_names())


class PostgresRuntimeRepositoryError(RuntimeError):
    """Raised when a repository query cannot be built safely."""


def quote_ident(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise PostgresRuntimeRepositoryError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def _json_parameter(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _adapt_value(column: str, value: Any) -> Any:
    if value is None:
        raise PostgresRuntimeRepositoryError(f"Missing value for column: {column}")
    if column in JSON_COLUMNS:
        return _json_parameter(value)
    if column in BOOLEAN_COLUMNS:
        return bool(value)
    return value


def _decode_value(column: str, value: Any) -> Any:
    if column in JSON_COLUMNS and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if column in BOOLEAN_COLUMNS:
        return bool(value)
    return value


def _missing_required_values(values: Mapping[str, Any], required_columns: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for column in required_columns:
        value = values.get(column)
        if value is None or str(value).strip() == "":
            missing.append(column)
    return missing


def _missing_present_values(values: Mapping[str, Any], required_columns: tuple[str, ...]) -> list[str]:
    return [column for column in required_columns if column not in values or values.get(column) is None]


@dataclass(frozen=True)
class PostgresRuntimeRepository:
    """Small DB-API repository wrapper for the accepted PostgreSQL schema.

    Endpoint integration remains a later gate. These helpers only prove the SQL
    contract can be built around an explicit connection object.
    """

    connection: Any
    database_url_redacted: str
    schema_name: str = "vantaline"
    kind: str = "postgres"

    def __post_init__(self) -> None:
        quote_ident(self.schema_name)

    def _qualified_table(self, table_name: str) -> str:
        if table_name not in VALID_TABLE_NAMES:
            raise PostgresRuntimeRepositoryError(f"Unknown runtime table: {table_name}")
        return f"{quote_ident(self.schema_name)}.{quote_ident(table_name)}"

    def _cursor(self) -> Any:
        return self.connection.cursor()

    def _end_read_transaction(self) -> None:
        rollback = getattr(self.connection, "rollback", None)
        if callable(rollback):
            rollback()

    def _row_to_dict(self, cursor: Any, row: Any) -> dict[str, Any]:
        if isinstance(row, Mapping):
            return dict(row)
        description = getattr(cursor, "description", None) or ()
        columns = [str(item[0]) for item in description]
        return dict(zip(columns, row))

    def count_rows(self, table_subset: tuple[str, ...] | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        target_tables = table_subset or table_names()
        cursor = self._cursor()
        try:
            for table_name in target_tables:
                cursor.execute(f"SELECT COUNT(*) AS count FROM {self._qualified_table(table_name)}")
                row = cursor.fetchone()
                if row is None:
                    counts[table_name] = 0
                    continue
                data = self._row_to_dict(cursor, row)
                counts[table_name] = int(data.get("count") or 0)
        finally:
            close = getattr(cursor, "close", None)
            try:
                if callable(close):
                    close()
            finally:
                self._end_read_transaction()
        return counts

    def fetch_all(self, table_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        qualified_table = self._qualified_table(table_name)
        columns = columns_for_table(table_name)
        column_sql = ", ".join(quote_ident(column) for column in columns)
        primary_key = PRIMARY_KEY_COLUMNS.get(table_name, (columns[0],))
        order_sql = ", ".join(quote_ident(column) for column in primary_key)
        sql = f"SELECT {column_sql} FROM {qualified_table} ORDER BY {order_sql}"
        params: tuple[Any, ...] = ()
        if limit is not None:
            if limit < 1:
                raise PostgresRuntimeRepositoryError("limit must be positive")
            sql = f"{sql} LIMIT %s"
            params = (limit,)

        cursor = self._cursor()
        try:
            cursor.execute(sql, params)
            rows = []
            for row in cursor.fetchall():
                data = self._row_to_dict(cursor, row)
                rows.append({column: _decode_value(column, data.get(column)) for column in columns})
            return rows
        finally:
            close = getattr(cursor, "close", None)
            try:
                if callable(close):
                    close()
            finally:
                self._end_read_transaction()

    def fetch_by_primary_key(self, table_name: str, key_values: Mapping[str, Any]) -> dict[str, Any] | None:
        qualified_table = self._qualified_table(table_name)
        columns = columns_for_table(table_name)
        primary_key = PRIMARY_KEY_COLUMNS.get(table_name)
        if not primary_key:
            raise PostgresRuntimeRepositoryError(f"Missing primary key metadata for table: {table_name}")
        missing = _missing_required_values(key_values, primary_key)
        if missing:
            raise PostgresRuntimeRepositoryError(f"Missing primary key values for {table_name}: {', '.join(missing)}")
        column_sql = ", ".join(quote_ident(column) for column in columns)
        where_sql = " AND ".join(f"{quote_ident(column)} = %s" for column in primary_key)
        params = tuple(key_values[column] for column in primary_key)
        cursor = self._cursor()
        try:
            cursor.execute(f"SELECT {column_sql} FROM {qualified_table} WHERE {where_sql}", params)
            row = cursor.fetchone()
            if row is None:
                return None
            data = self._row_to_dict(cursor, row)
            return {column: _decode_value(column, data.get(column)) for column in columns}
        finally:
            close = getattr(cursor, "close", None)
            try:
                if callable(close):
                    close()
            finally:
                self._end_read_transaction()

    def _upsert_sql_params(self, table_name: str, row: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
        qualified_table = self._qualified_table(table_name)
        columns = columns_for_table(table_name)
        primary_key = PRIMARY_KEY_COLUMNS.get(table_name)
        if not primary_key:
            raise PostgresRuntimeRepositoryError(f"Missing primary key metadata for table: {table_name}")
        missing_primary_key = _missing_required_values(row, primary_key)
        if missing_primary_key:
            raise PostgresRuntimeRepositoryError(
                f"Missing primary key values for {table_name}: {', '.join(missing_primary_key)}"
            )
        missing_columns = _missing_present_values(row, columns)
        if missing_columns:
            raise PostgresRuntimeRepositoryError(f"Missing column values for {table_name}: {', '.join(missing_columns)}")
        column_sql = ", ".join(quote_ident(column) for column in columns)
        placeholders = ", ".join("%s::jsonb" if column in JSON_COLUMNS else "%s" for column in columns)
        conflict_sql = ", ".join(quote_ident(column) for column in primary_key)
        update_columns = [column for column in columns if column not in primary_key]
        update_sql = ", ".join(f"{quote_ident(column)} = EXCLUDED.{quote_ident(column)}" for column in update_columns)
        sql = (
            f"INSERT INTO {qualified_table} ({column_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}"
        )
        params = tuple(_adapt_value(column, row.get(column)) for column in columns)
        return sql, params

    def upsert_row(self, table_name: str, row: Mapping[str, Any], *, commit: bool = True) -> None:
        sql, params = self._upsert_sql_params(table_name, row)
        cursor = self._cursor()
        try:
            cursor.execute(sql, params)
            if commit:
                self.connection.commit()
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def replace_all(self, table_name: str, rows: list[Mapping[str, Any]], *, commit: bool = True) -> None:
        table_plan = [(self._qualified_table(table_name), [self._upsert_sql_params(table_name, row) for row in rows])]
        cursor = self._cursor()
        try:
            for qualified_table, statements in table_plan:
                cursor.execute(f"DELETE FROM {qualified_table}")
                for sql, params in statements:
                    cursor.execute(sql, params)
            if commit:
                self.connection.commit()
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def mutate_app_config_namespace(
        self,
        protected_keys: tuple[str, ...],
        mutator: Callable[[dict[str, Any]], None],
        *,
        updated_at: int,
    ) -> dict[str, Any]:
        """Atomically mutate a protected app-config namespace across instances.

        A transaction-scoped advisory lock also serializes the absent-row case,
        which a plain ``SELECT ... FOR UPDATE`` cannot protect.
        """
        qualified_table = self._qualified_table("app_config")
        cursor = self._cursor()
        try:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("vantaline:plc-config-namespace",))
            cursor.execute(
                f"SELECT config_key, config_value_json FROM {qualified_table} "
                "WHERE config_key = ANY(%s) FOR UPDATE",
                (list(protected_keys),),
            )
            values: dict[str, Any] = {}
            for row in cursor.fetchall():
                data = self._row_to_dict(cursor, row)
                key = str(data.get("config_key") or "")
                if key:
                    values[key] = _decode_value("config_value_json", data.get("config_value_json"))
            mutator(values)
            for key in protected_keys:
                if key not in values:
                    continue
                row = {
                    "config_key": key,
                    "config_value_json": values[key],
                    "source_file": "config.json",
                    "updated_at": updated_at,
                }
                sql, params = self._upsert_sql_params("app_config", row)
                cursor.execute(sql, params)
            self.connection.commit()
            return values
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def replace_app_config_preserving_keys(
        self,
        rows: list[Mapping[str, Any]],
        protected_keys: tuple[str, ...],
        *,
        additional_tables: Mapping[str, list[Mapping[str, Any]]] | None = None,
    ) -> None:
        """Replace generic app config without overwriting the PLC namespace."""
        qualified_table = self._qualified_table("app_config")
        cursor = self._cursor()
        try:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("vantaline:plc-config-namespace",))
            cursor.execute(
                f"DELETE FROM {qualified_table} WHERE NOT (config_key = ANY(%s))",
                (list(protected_keys),),
            )
            for row in rows:
                if str(row.get("config_key") or "") in protected_keys:
                    continue
                sql, params = self._upsert_sql_params("app_config", row)
                cursor.execute(sql, params)
            for table_name, table_rows in (additional_tables or {}).items():
                table = self._qualified_table(table_name)
                cursor.execute(f"DELETE FROM {table}")
                for row in table_rows:
                    sql, params = self._upsert_sql_params(table_name, row)
                    cursor.execute(sql, params)
            self.connection.commit()
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def replace_tables(self, table_rows: Mapping[str, list[Mapping[str, Any]]], *, commit: bool = True) -> None:
        table_plan = [
            (self._qualified_table(table_name), [self._upsert_sql_params(table_name, row) for row in rows])
            for table_name, rows in table_rows.items()
        ]
        cursor = self._cursor()
        try:
            for qualified_table, statements in table_plan:
                cursor.execute(f"DELETE FROM {qualified_table}")
                for sql, params in statements:
                    cursor.execute(sql, params)
            if commit:
                self.connection.commit()
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def delete_by_primary_key(self, table_name: str, key_values: Mapping[str, Any], *, commit: bool = True) -> None:
        qualified_table = self._qualified_table(table_name)
        primary_key = PRIMARY_KEY_COLUMNS.get(table_name)
        if not primary_key:
            raise PostgresRuntimeRepositoryError(f"Missing primary key metadata for table: {table_name}")
        missing = _missing_required_values(key_values, primary_key)
        if missing:
            raise PostgresRuntimeRepositoryError(f"Missing primary key values for {table_name}: {', '.join(missing)}")
        where_sql = " AND ".join(f"{quote_ident(column)} = %s" for column in primary_key)
        params = tuple(key_values[column] for column in primary_key)
        cursor = self._cursor()
        try:
            cursor.execute(f"DELETE FROM {qualified_table} WHERE {where_sql}", params)
            if commit:
                self.connection.commit()
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
