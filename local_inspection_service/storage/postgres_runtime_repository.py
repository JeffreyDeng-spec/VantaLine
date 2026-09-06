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

BOOLEAN_COLUMNS = frozenset({"active", "path_exists", "profile_verified", "passed"})

PRIMARY_KEY_COLUMNS = {
    "text_label_extractions": ("id",),
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
    "incoming_text_reference_versions": ("id",),
    "incoming_text_inspections": ("id",),
    "text_inspection_standards": ("id",),
    "text_inspection_assets": ("id",),
    "text_inspection_standard_revisions": ("id",),
    "text_inspection_records": ("id",),
    "text_inspection_manual_sessions": ("id",),
    "text_inspection_manual_pages": ("id",),
    "text_inspection_classification_feedback": ("id",),
    "plc_workstations": ("id",),
    "plc_workstation_leases": ("station_id",),
    "plc_web_serial_dispatches": ("id",),
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


def _text_standard_asset_snapshot(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [item for item in assets if item.get("status") in {"candidate", "page"}]
    selected.sort(key=lambda item: int(item.get("ordinal") or 0))
    return [
        {
            "id": item["id"],
            "sha256": item.get("sha256", ""),
            "ordinal": int(item.get("ordinal") or 0),
            "mime_type": item.get("mime_type", ""),
        }
        for item in selected
    ]


def _legacy_text_standard_snapshot(standard: Mapping[str, Any]) -> list[dict[str, Any]]:
    snapshots = standard.get("confirmed_assets")
    if not isinstance(snapshots, list):
        return []
    return [dict(item) for item in snapshots if isinstance(item, Mapping) and item.get("id")]


def _legacy_text_standard_baseline_revision(standard: Mapping[str, Any], created_at: int) -> dict[str, Any]:
    snapshot = _legacy_text_standard_snapshot(standard)
    standard_id = str(standard["id"])
    return {
        "id": f"rev_baseline_{standard_id}", "standard_id": standard_id,
        "owner_user_id": str(standard["owner_user_id"]), "revision_number": 1,
        "action": "baseline", "asset_id": "", "confirmed_assets": snapshot,
        "confirmed_asset_ids": [str(item["id"]) for item in snapshot], "created_at": created_at,
    }


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

    def fetch_label_extraction_rows(self, owner_user_id: str, root_id: str | None = None) -> list[dict[str, Any]]:
        table = self._qualified_table("text_label_extractions")
        sql = f"SELECT raw_json FROM {table} WHERE owner_user_id = %s"
        params = (owner_user_id,)
        if root_id is not None:
            sql += " AND raw_json->>'root_id' = %s"
            params += (root_id,)
        cursor = self._cursor()
        try:
            cursor.execute(sql, params)
            return [_decode_value("raw_json", self._row_to_dict(cursor, row)["raw_json"]) for row in cursor.fetchall()]
        finally:
            cursor.close()
            self._end_read_transaction()

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

    def insert_row_once(self, table_name: str, row: Mapping[str, Any], *, commit: bool = True) -> bool:
        """Insert an immutable/runtime-authority row without overwriting a conflict."""
        qualified_table = self._qualified_table(table_name)
        columns = columns_for_table(table_name)
        missing_columns = _missing_present_values(row, columns)
        if missing_columns:
            raise PostgresRuntimeRepositoryError(f"Missing column values for {table_name}: {', '.join(missing_columns)}")
        column_sql = ", ".join(quote_ident(column) for column in columns)
        placeholders = ", ".join("%s::jsonb" if column in JSON_COLUMNS else "%s" for column in columns)
        params = tuple(_adapt_value(column, row.get(column)) for column in columns)
        cursor = self._cursor()
        try:
            cursor.execute(
                f"INSERT INTO {qualified_table} ({column_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                params,
            )
            inserted = int(getattr(cursor, "rowcount", 0) or 0) == 1
            if commit:
                self.connection.commit()
            return inserted
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def fetch_one_by_columns(self, table_name: str, key_values: Mapping[str, Any], *, for_update: bool = False) -> dict[str, Any] | None:
        """Fetch by a small exact-match key map; identifiers stay schema allowlisted."""
        qualified_table = self._qualified_table(table_name)
        columns = columns_for_table(table_name)
        if not key_values or any(column not in columns for column in key_values):
            raise PostgresRuntimeRepositoryError(f"Invalid lookup columns for table: {table_name}")
        missing = _missing_required_values(key_values, tuple(key_values))
        if missing:
            raise PostgresRuntimeRepositoryError(f"Missing lookup values for {table_name}: {', '.join(missing)}")
        column_sql = ", ".join(quote_ident(column) for column in columns)
        where_sql = " AND ".join(f"{quote_ident(column)} = %s" for column in key_values)
        params = tuple(key_values[column] for column in key_values)
        cursor = self._cursor()
        try:
            suffix = " FOR UPDATE" if for_update else ""
            cursor.execute(f"SELECT {column_sql} FROM {qualified_table} WHERE {where_sql}{suffix}", params)
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
                if not for_update:
                    self._end_read_transaction()

    def activate_incoming_text_reference(self, reference_id: str, owner_user_id: str, task_id: str, raw_json_value: Mapping[str, Any]) -> None:
        """Atomically archive the previous active version and activate one immutable draft."""
        table = self._qualified_table("incoming_text_reference_versions")
        cursor = self._cursor()
        try:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"vantaline:incoming-text:{owner_user_id}:{task_id}",))
            cursor.execute(
                f"UPDATE {table} SET status = 'archived', raw_json = jsonb_set(raw_json, '{{status}}', '\"archived\"'::jsonb, true) "
                "WHERE owner_user_id = %s AND task_id = %s AND status = 'active' AND id <> %s",
                (owner_user_id, task_id, reference_id),
            )
            cursor.execute(
                f"UPDATE {table} SET status = 'active', activated_at = %s, raw_json = %s::jsonb "
                "WHERE id = %s AND owner_user_id = %s AND task_id = %s AND status = 'draft'",
                (
                    int(raw_json_value.get("activated_at") or 0),
                    _json_parameter(raw_json_value),
                    reference_id,
                    owner_user_id,
                    task_id,
                ),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) != 1:
                raise PostgresRuntimeRepositoryError("Incoming text reference is not an activatable draft")
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

    def _insert_text_standard_revision(self, cursor: Any, revision: Mapping[str, Any]) -> None:
        revisions = self._qualified_table("text_inspection_standard_revisions")
        cursor.execute(
            f"INSERT INTO {revisions} (id, standard_id, owner_user_id, revision_number, action, asset_id, created_at, raw_json) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
            (
                revision["id"], revision["standard_id"], revision["owner_user_id"],
                int(revision["revision_number"]), revision["action"], revision.get("asset_id", ""),
                int(revision["created_at"]), _json_parameter(revision),
            ),
        )

    def add_text_inspection_standard_asset(
        self,
        standard_id: str,
        owner_user_id: str,
        asset: dict[str, Any],
        *,
        revision_id: str,
        updated_at: int,
        expected_revision: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        standards = self._qualified_table("text_inspection_standards")
        assets = self._qualified_table("text_inspection_assets")
        cursor = self._cursor()
        try:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"vantaline:text-standard:{owner_user_id}:{standard_id}",))
            cursor.execute(f"SELECT raw_json FROM {standards} WHERE id = %s AND owner_user_id = %s FOR UPDATE", (standard_id, owner_user_id))
            row = cursor.fetchone()
            if row is None:
                raise PostgresRuntimeRepositoryError("Text inspection standard not found")
            standard = _decode_value("raw_json", self._row_to_dict(cursor, row).get("raw_json"))
            if not isinstance(standard, dict) or standard.get("standard_type") != "label":
                raise PostgresRuntimeRepositoryError("Text inspection standard does not accept label images")
            current_revision = int(standard.get("revision_number") or 0)
            if expected_revision is not None and expected_revision != current_revision:
                raise PostgresRuntimeRepositoryError("Text inspection standard revision changed")
            cursor.execute(f"SELECT raw_json FROM {assets} WHERE standard_id = %s AND owner_user_id = %s ORDER BY ordinal FOR UPDATE", (standard_id, owner_user_id))
            existing_assets = []
            for asset_row in cursor.fetchall():
                value = _decode_value("raw_json", self._row_to_dict(cursor, asset_row).get("raw_json"))
                if isinstance(value, dict):
                    existing_assets.append(value)
            next_asset = dict(asset)
            next_asset["ordinal"] = max((int(item.get("ordinal") or 0) for item in existing_assets), default=0) + 1
            cursor.execute(
                f"INSERT INTO {assets} (id, standard_id, owner_user_id, asset_kind, ordinal, status, sha256, created_at, updated_at, raw_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    next_asset["id"], standard_id, owner_user_id, next_asset["asset_kind"], next_asset["ordinal"],
                    next_asset["status"], next_asset["sha256"], next_asset["created_at"], next_asset["updated_at"],
                    _json_parameter(next_asset),
                ),
            )
            selected = _text_standard_asset_snapshot([*existing_assets, next_asset])
            standard["asset_count"] = len(selected)
            standard["updated_at"] = updated_at
            revision: dict[str, Any] | None = None
            if standard.get("status") == "confirmed":
                if current_revision == 0:
                    baseline = _legacy_text_standard_baseline_revision(standard, updated_at)
                    self._insert_text_standard_revision(cursor, baseline)
                    current_revision = 1
                next_revision = current_revision + 1
                revision = {
                    "id": revision_id, "standard_id": standard_id, "owner_user_id": owner_user_id,
                    "revision_number": next_revision, "action": "add", "asset_id": next_asset["id"],
                    "confirmed_assets": selected, "confirmed_asset_ids": [item["id"] for item in selected],
                    "created_at": updated_at,
                }
                standard.update({
                    "revision_number": next_revision, "current_revision_id": revision_id,
                    "confirmed_assets": selected, "confirmed_asset_ids": revision["confirmed_asset_ids"],
                })
                self._insert_text_standard_revision(cursor, revision)
            cursor.execute(
                f"UPDATE {standards} SET updated_at = %s, raw_json = %s::jsonb WHERE id = %s AND owner_user_id = %s",
                (updated_at, _json_parameter(standard), standard_id, owner_user_id),
            )
            self.connection.commit()
            return next_asset, standard
        except Exception:
            self.connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def patch_text_inspection_asset(
        self,
        standard_id: str,
        asset_id: str,
        owner_user_id: str,
        action: str,
        updated_at: int,
        *,
        revision_id: str,
        expected_revision: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        standards = self._qualified_table("text_inspection_standards")
        assets = self._qualified_table("text_inspection_assets")
        cursor = self._cursor()
        try:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"vantaline:text-standard:{owner_user_id}:{standard_id}",))
            cursor.execute(f"SELECT raw_json FROM {standards} WHERE id = %s AND owner_user_id = %s FOR UPDATE", (standard_id, owner_user_id))
            standard_row = cursor.fetchone()
            if standard_row is None:
                raise PostgresRuntimeRepositoryError("Text inspection standard not found")
            standard = _decode_value("raw_json", self._row_to_dict(cursor, standard_row).get("raw_json"))
            if not isinstance(standard, dict):
                raise PostgresRuntimeRepositoryError("Text inspection standard authority is corrupt")
            current_revision = int(standard.get("revision_number") or 0)
            if expected_revision is not None and expected_revision != current_revision:
                raise PostgresRuntimeRepositoryError("Text inspection standard revision changed")
            cursor.execute(f"SELECT raw_json FROM {assets} WHERE standard_id = %s AND owner_user_id = %s ORDER BY ordinal FOR UPDATE", (standard_id, owner_user_id))
            all_assets: list[dict[str, Any]] = []
            for asset_row in cursor.fetchall():
                value = _decode_value("raw_json", self._row_to_dict(cursor, asset_row).get("raw_json"))
                if isinstance(value, dict):
                    all_assets.append(value)
            asset = next((item for item in all_assets if str(item.get("id")) == asset_id), None)
            if asset is None:
                raise PostgresRuntimeRepositoryError("Text inspection asset not found")
            target_status = {"restore": "candidate", "remove": "excluded", "exclude": "excluded", "confirm": "candidate"}[action]
            if asset.get("status") == target_status:
                self.connection.commit()
                return asset, standard
            asset["status"] = target_status
            asset["classification_source"] = "human"
            asset["updated_at"] = updated_at
            cursor.execute(f"UPDATE {assets} SET status = %s, updated_at = %s, raw_json = %s::jsonb WHERE id = %s", (asset["status"], updated_at, _json_parameter(asset), asset_id))
            selected = _text_standard_asset_snapshot(all_assets)
            standard["asset_count"] = len(selected)
            standard["updated_at"] = updated_at
            if standard.get("status") == "confirmed":
                if current_revision == 0:
                    baseline = _legacy_text_standard_baseline_revision(standard, updated_at)
                    self._insert_text_standard_revision(cursor, baseline)
                    current_revision = 1
                next_revision = current_revision + 1
                revision = {
                    "id": revision_id, "standard_id": standard_id, "owner_user_id": owner_user_id,
                    "revision_number": next_revision, "action": "restore" if action in {"restore", "confirm"} else "remove",
                    "asset_id": asset_id, "confirmed_assets": selected,
                    "confirmed_asset_ids": [item["id"] for item in selected], "created_at": updated_at,
                }
                standard.update({
                    "revision_number": next_revision, "current_revision_id": revision_id,
                    "confirmed_assets": selected, "confirmed_asset_ids": revision["confirmed_asset_ids"],
                })
                self._insert_text_standard_revision(cursor, revision)
            cursor.execute(
                f"UPDATE {standards} SET updated_at = %s, raw_json = %s::jsonb WHERE id = %s AND owner_user_id = %s",
                (updated_at, _json_parameter(standard), standard_id, owner_user_id),
            )
            self.connection.commit()
            return asset, standard
        except Exception:
            self.connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def confirm_text_inspection_standard(self, standard_id: str, owner_user_id: str, confirmed_at: int, *, revision_id: str) -> dict[str, Any]:
        standards = self._qualified_table("text_inspection_standards")
        assets = self._qualified_table("text_inspection_assets")
        cursor = self._cursor()
        try:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"vantaline:text-standard:{owner_user_id}:{standard_id}",))
            cursor.execute(f"SELECT raw_json FROM {standards} WHERE id = %s AND owner_user_id = %s FOR UPDATE", (standard_id, owner_user_id))
            row = cursor.fetchone()
            if row is None:
                raise PostgresRuntimeRepositoryError("Text inspection standard not found")
            standard = _decode_value("raw_json", self._row_to_dict(cursor, row).get("raw_json"))
            if not isinstance(standard, dict):
                raise PostgresRuntimeRepositoryError("Text inspection standard authority is corrupt")
            if standard.get("status") == "confirmed":
                self.connection.commit()
                return standard
            if standard.get("status") != "draft":
                raise PostgresRuntimeRepositoryError("Text inspection standard is not confirmable")
            cursor.execute(f"SELECT raw_json FROM {assets} WHERE standard_id = %s AND owner_user_id = %s ORDER BY ordinal FOR UPDATE", (standard_id, owner_user_id))
            selected = []
            for asset_row in cursor.fetchall():
                asset = _decode_value("raw_json", self._row_to_dict(cursor, asset_row).get("raw_json"))
                if isinstance(asset, dict) and asset.get("status") in {"candidate", "page"}:
                    selected.append(asset)
            if not selected:
                raise PostgresRuntimeRepositoryError("Text inspection standard requires at least one selected asset")
            revision_number = int(standard.get("revision_number") or 0) + 1
            snapshot = _text_standard_asset_snapshot(selected)
            revision = {
                "id": revision_id, "standard_id": standard_id, "owner_user_id": owner_user_id,
                "revision_number": revision_number, "action": "confirm", "asset_id": "",
                "confirmed_assets": snapshot, "confirmed_asset_ids": [item["id"] for item in snapshot],
                "created_at": confirmed_at,
            }
            standard["status"] = "confirmed"
            standard["confirmed_at"] = standard["updated_at"] = confirmed_at
            standard["revision_number"] = revision_number
            standard["current_revision_id"] = revision_id
            standard["confirmed_assets"] = snapshot
            standard["confirmed_asset_ids"] = revision["confirmed_asset_ids"]
            standard["asset_count"] = len(snapshot)
            self._insert_text_standard_revision(cursor, revision)
            cursor.execute(f"UPDATE {standards} SET status = 'confirmed', updated_at = %s, raw_json = %s::jsonb WHERE id = %s", (confirmed_at, _json_parameter(standard), standard_id))
            self.connection.commit()
            return standard
        except Exception:
            self.connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def review_incoming_text_inspection(
        self,
        inspection_id: str,
        *,
        decision: str,
        reason: str,
        actor_user_id: str,
        reviewed_at: int,
    ) -> dict[str, Any]:
        """CAS the human decision and append its audit event in one transaction."""
        inspection_table = self._qualified_table("incoming_text_inspections")
        audit_table = self._qualified_table("audit_events")
        cursor = self._cursor()
        try:
            cursor.execute(
                f"SELECT raw_json FROM {inspection_table} WHERE id = %s FOR UPDATE",
                (inspection_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise PostgresRuntimeRepositoryError("Incoming text inspection not found")
            data = self._row_to_dict(cursor, row)
            raw = _decode_value("raw_json", data.get("raw_json"))
            if not isinstance(raw, dict):
                raise PostgresRuntimeRepositoryError("Incoming text inspection authority is corrupt")
            if str(raw.get("auto_decision") or "") != "REVIEW_REQUIRED":
                raise PostgresRuntimeRepositoryError("Inspection is not reviewable")
            existing = str(raw.get("final_decision") or "")
            if existing and existing != decision:
                raise PostgresRuntimeRepositoryError("Inspection already has a different review decision")
            if existing == decision:
                self.connection.commit()
                return raw
            raw.update(
                {
                    "final_decision": decision,
                    "review_reason": reason,
                    "reviewed_at": reviewed_at,
                    "reviewed_by_user_id": actor_user_id,
                    "updated_at": reviewed_at,
                }
            )
            cursor.execute(
                f"UPDATE {inspection_table} SET final_decision = %s, updated_at = %s, raw_json = %s::jsonb WHERE id = %s",
                (decision, reviewed_at, _json_parameter(raw), inspection_id),
            )
            event_id = f"incoming_review_{inspection_id}"
            payload = {
                "inspection_id": inspection_id,
                "task_id": raw.get("task_id"),
                "decision": decision,
                "reason": reason,
            }
            cursor.execute(
                f"INSERT INTO {audit_table} (id, event_type, created_at, actor_user_id, payload_json) "
                "VALUES (%s, %s, %s, %s, %s::jsonb) ON CONFLICT (id) DO NOTHING",
                (event_id, "incoming_text.reviewed", reviewed_at, actor_user_id, _json_parameter(payload)),
            )
            self.connection.commit()
            return raw
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def list_incoming_text_inspections(
        self,
        *,
        task_ids: list[str],
        task_id: str = "",
        material_code: str = "",
        decision: str = "",
        limit: int = 100,
    ) -> dict[str, Any]:
        table = self._qualified_table("incoming_text_inspections")
        if not task_ids:
            return {"items": [], "total": 0, "summary": {}}
        columns = columns_for_table("incoming_text_inspections")
        column_sql = ", ".join(quote_ident(column) for column in columns)
        conditions = ["task_id = ANY(%s)"]
        params: list[Any] = [task_ids]
        if task_id:
            conditions.append("task_id = %s")
            params.append(task_id)
        if material_code:
            conditions.append("material_code = %s")
            params.append(material_code)
        if decision:
            conditions.append("%s IN (auto_decision, final_decision)")
            params.append(decision)
        where_sql = " AND ".join(conditions)
        cursor = self._cursor()
        try:
            cursor.execute(
                f"SELECT {column_sql} FROM {table} WHERE {where_sql} ORDER BY created_at DESC LIMIT %s",
                (*params, max(1, min(500, int(limit)))),
            )
            rows = []
            for row in cursor.fetchall():
                data = self._row_to_dict(cursor, row)
                rows.append({column: _decode_value(column, data.get(column)) for column in columns})
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where_sql}", tuple(params))
            count_data = self._row_to_dict(cursor, cursor.fetchone())
            cursor.execute(
                f"SELECT COALESCE(NULLIF(final_decision, ''), NULLIF(auto_decision, ''), 'UNKNOWN') AS decision, COUNT(*) AS count "
                f"FROM {table} WHERE {where_sql} GROUP BY 1",
                tuple(params),
            )
            summary = {str(item.get("decision")): int(item.get("count") or 0) for item in (self._row_to_dict(cursor, row) for row in cursor.fetchall())}
            return {"items": rows, "total": int(count_data.get("count") or 0), "summary": summary}
        finally:
            close = getattr(cursor, "close", None)
            try:
                if callable(close):
                    close()
            finally:
                self._end_read_transaction()

    def incoming_text_retention_candidates(self, *, before_created_at: int, limit: int = 1000) -> list[dict[str, Any]]:
        table = self._qualified_table("incoming_text_inspections")
        cursor = self._cursor()
        try:
            cursor.execute(
                f"SELECT raw_json FROM {table} WHERE created_at < %s "
                "AND COALESCE((raw_json ->> 'evidence_purged_at')::bigint, 0) = 0 "
                "ORDER BY created_at ASC LIMIT %s",
                (before_created_at, max(1, min(5000, int(limit)))),
            )
            return [
                value
                for value in (_decode_value("raw_json", self._row_to_dict(cursor, row).get("raw_json")) for row in cursor.fetchall())
                if isinstance(value, dict)
            ]
        finally:
            close = getattr(cursor, "close", None)
            try:
                if callable(close):
                    close()
            finally:
                self._end_read_transaction()

    def mark_incoming_text_evidence_purged(self, inspection_id: str, *, purged_at: int, retention_days: int) -> bool:
        """Patch only retention metadata so a concurrent human review cannot be lost."""
        table = self._qualified_table("incoming_text_inspections")
        cursor = self._cursor()
        try:
            cursor.execute(
                f"UPDATE {table} SET raw_json = jsonb_set(jsonb_set(raw_json, '{{evidence_purged_at}}', to_jsonb(%s::bigint), true), "
                "'{evidence_retention_days}', to_jsonb(%s::bigint), true) WHERE id = %s "
                "AND COALESCE((raw_json ->> 'evidence_purged_at')::bigint, 0) = 0",
                (purged_at, retention_days, inspection_id),
            )
            changed = int(getattr(cursor, "rowcount", 0) or 0) == 1
            self.connection.commit()
            return changed
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

    def mutate_plc_web_serial_rows(
        self,
        station_id: str,
        dispatch_id: str | None,
        mutator: Callable[[dict[str, dict[str, Any] | None]], None],
    ) -> dict[str, dict[str, Any] | None]:
        """Atomically fence one Web Serial workstation and optional dispatch."""
        if not station_id:
            raise PostgresRuntimeRepositoryError("station_id is required")
        tables = {
            "station": ("plc_workstations", "id", station_id),
            "lease": ("plc_workstation_leases", "station_id", station_id),
        }
        if dispatch_id:
            tables["dispatch"] = ("plc_web_serial_dispatches", "id", dispatch_id)
        cursor = self._cursor()
        try:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"vantaline:plc-web-serial:{station_id}",))
            state: dict[str, dict[str, Any] | None] = {}
            for key, (table_name, id_column, id_value) in tables.items():
                columns = columns_for_table(table_name)
                column_sql = ", ".join(quote_ident(column) for column in columns)
                cursor.execute(
                    f"SELECT {column_sql} FROM {self._qualified_table(table_name)} "
                    f"WHERE {quote_ident(id_column)} = %s FOR UPDATE",
                    (id_value,),
                )
                row = cursor.fetchone()
                if row is None:
                    state[key] = None
                    continue
                data = self._row_to_dict(cursor, row)
                state[key] = {column: _decode_value(column, data.get(column)) for column in columns}
            cursor.execute("SELECT EXTRACT(EPOCH FROM clock_timestamp())::BIGINT AS now")
            clock_row = cursor.fetchone()
            clock_data = self._row_to_dict(cursor, clock_row)
            state["clock"] = {"now": int(clock_data.get("now") or 0)}
            mutator(state)
            for key, (table_name, _, _) in tables.items():
                row = state.get(key)
                if row is None:
                    continue
                sql, params = self._upsert_sql_params(table_name, row)
                cursor.execute(sql, params)
            self.connection.commit()
            return state
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
