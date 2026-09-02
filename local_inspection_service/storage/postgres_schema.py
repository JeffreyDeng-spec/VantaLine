"""PostgreSQL DDL generation for VantaLine migration artifacts.

This module is script-only. It must not be imported by the FastAPI runtime.
"""

from __future__ import annotations

import re

from .schema import SCHEMA_VERSION, TABLES, TableSchema


JSONB_COLUMNS = frozenset(
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

INTEGER_COLUMNS = frozenset({"config_generation", "lease_epoch", "ordinal", "revision_number"})

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

UNIQUE_COLUMNS = {
    "users": (("username",),),
    "incoming_text_reference_versions": (("owner_user_id", "task_id", "version_label"),),
    "incoming_text_inspections": (("owner_user_id", "task_id", "capture_id"),),
    "text_inspection_standards": (("owner_user_id", "material_code", "version_label", "standard_type"),),
    "text_inspection_assets": (("standard_id", "ordinal"),),
    "text_inspection_standard_revisions": (("standard_id", "revision_number"),),
    "text_inspection_records": (("owner_user_id", "comparison_id"),),
    "text_inspection_manual_pages": (("owner_user_id", "session_id", "capture_id"),),
    "plc_workstations": (("token_hash",),),
    "plc_web_serial_dispatches": (("station_id", "detection_request_id"),),
}


def quote_ident(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def postgres_type(column: str) -> str:
    if column in JSONB_COLUMNS:
        return "JSONB"
    if column in BOOLEAN_COLUMNS:
        return "BOOLEAN"
    if column in INTEGER_COLUMNS:
        return "BIGINT"
    if column.endswith("_at"):
        return "BIGINT"
    return "TEXT"


def create_table_statement(table: TableSchema) -> str:
    lines: list[str] = []
    for column in table.columns:
        lines.append(f"    {quote_ident(column)} {postgres_type(column)} NOT NULL")
    primary_key = PRIMARY_KEY_COLUMNS.get(table.name)
    if primary_key:
        cols = ", ".join(quote_ident(column) for column in primary_key)
        lines.append(f"    PRIMARY KEY ({cols})")
    for unique_columns in UNIQUE_COLUMNS.get(table.name, ()):
        cols = ", ".join(quote_ident(column) for column in unique_columns)
        lines.append(f"    UNIQUE ({cols})")
    body = ",\n".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {quote_ident(table.name)} (\n{body}\n);"


def index_statement(statement: str) -> str:
    # Existing index statements use portable identifiers and are valid after
    # search_path is set to the migration schema.
    clean = " ".join(statement.strip().split())
    return clean if clean.endswith(";") else f"{clean};"


def postgres_ddl(schema_name: str = "vantaline") -> str:
    quote_ident(schema_name)
    statements = [
        "-- VantaLine PostgreSQL migration schema artifact.",
        "-- Generated from local_inspection_service.storage.schema; runtime remains JSON until cutover gate.",
        "BEGIN;",
        f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema_name)};",
        f"SET search_path TO {quote_ident(schema_name)}, public;",
    ]
    for table in TABLES:
        statements.append(create_table_statement(table))
        statements.extend(index_statement(index) for index in table.indexes)
    statements.extend(
        [
            "INSERT INTO schema_migrations (version, applied_at, metadata_json)",
            f"VALUES ('{SCHEMA_VERSION}', 0, '{{\"schema_version\":\"{SCHEMA_VERSION}\",\"artifact\":\"postgres_ddl\"}}'::jsonb)",
            "ON CONFLICT (version) DO UPDATE SET metadata_json = EXCLUDED.metadata_json;",
            "COMMIT;",
            "",
        ]
    )
    return "\n".join(statements)
