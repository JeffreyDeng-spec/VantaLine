#!/usr/bin/env python3
"""Validate a PostgreSQL JSON-to-import migration report.

This validator is read-only. It checks the redacted report emitted by
`prepare_json_to_postgres.py` before production import and rejects reports that
do not prove the import artifacts are present, cutover is allowed, and table
row-count baselines are complete.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.storage.schema import SCHEMA_VERSION, TABLES  # noqa: E402


FORBIDDEN_REPORT_MARKERS = (
    "DATABASE_URL=",
    "postgresql://",
    "password_hash",
    "sha256$",
    "raw-session",
    "provider-key",
    "agent-token",
    "env-secret",
    "vantaline_session=",
)


class MigrationReportValidationError(AssertionError):
    """Raised when the migration report does not satisfy the cutover gate."""


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MigrationReportValidationError(message)


def is_sha256_hex(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def load_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MigrationReportValidationError(f"report file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MigrationReportValidationError(f"report is not valid JSON: {path}") from exc
    require(isinstance(payload, dict), "report root must be a JSON object")
    return payload


def validate_no_secret_markers(report: dict[str, Any]) -> None:
    text = stable_json(report).lower()
    for marker in FORBIDDEN_REPORT_MARKERS:
        require(marker.lower() not in text, f"report contains forbidden marker: {marker}")


def normalized_row_counts(report: dict[str, Any]) -> dict[str, int]:
    row_counts = report.get("row_counts")
    require(isinstance(row_counts, dict), "row_counts must be an object")
    expected_tables = {table.name for table in TABLES}
    actual_tables = {str(table) for table in row_counts}
    missing = sorted(expected_tables - actual_tables)
    extra = sorted(actual_tables - expected_tables)
    require(not missing, "row_counts missing tables: " + ",".join(missing))
    require(not extra, "row_counts includes unknown tables: " + ",".join(extra))
    normalized: dict[str, int] = {}
    for table in TABLES:
        raw_value = row_counts.get(table.name)
        require(isinstance(raw_value, int) and raw_value >= 0, f"row_counts.{table.name} must be a non-negative integer")
        normalized[table.name] = int(raw_value)
    require(normalized.get("schema_migrations") == 1, "row_counts.schema_migrations must be exactly 1")
    require(normalized.get("audit_events", 0) >= 1, "row_counts.audit_events must include the import audit event")
    return normalized


def validate_import_artifacts(report: dict[str, Any]) -> None:
    artifacts = report.get("postgres_import_artifacts")
    require(isinstance(artifacts, dict), "postgres_import_artifacts must be an object")
    require(artifacts.get("emitted") is True, "postgres_import_artifacts.emitted must be true")
    require(bool(artifacts.get("import_dir")), "postgres_import_artifacts.import_dir is required")
    require(bool(artifacts.get("load_sql_path")), "postgres_import_artifacts.load_sql_path is required")
    csv_files = artifacts.get("csv_files")
    require(isinstance(csv_files, dict) and bool(csv_files), "postgres_import_artifacts.csv_files must be a non-empty object")
    require("schema_migrations" not in csv_files, "schema_migrations must be seeded by DDL, not imported by CSV")
    for table, path in csv_files.items():
        require(str(table) != "schema_migrations", "schema_migrations CSV entry is forbidden")
        require("schema_migrations.csv" not in str(path), "schema_migrations.csv path is forbidden")


def validate_migration_report(
    report: dict[str, Any],
    *,
    allow_source_error_waiver: bool = False,
) -> dict[str, int]:
    require(report.get("report_version") == 1, "report_version must be 1")
    require(report.get("schema_version") == SCHEMA_VERSION, f"schema_version must be {SCHEMA_VERSION}")
    require(report.get("target") == "postgresql", "target must be postgresql")
    require(bool(report.get("postgres_schema")), "postgres_schema is required")
    require(is_sha256_hex(report.get("ddl_sha256")), "ddl_sha256 must be a lowercase SHA-256 hex digest")
    require(report.get("cutover_allowed") is True, "cutover_allowed must be true")
    blocking_errors = report.get("blocking_errors")
    require(blocking_errors == [], "blocking_errors must be empty")
    blocking_error_counts = report.get("blocking_error_counts")
    require(blocking_error_counts in ({}, None), "blocking_error_counts must be empty")

    source_error_count = int(report.get("source_error_count") or 0)
    if source_error_count:
        require(allow_source_error_waiver, "source errors require explicit waiver permission")
        require(report.get("source_error_policy") == "waived_explicitly", "source_error_policy must be waived_explicitly")
        require(bool(str(report.get("source_error_waiver_id") or "").strip()), "source_error_waiver_id is required")
    else:
        require(report.get("source_errors") in ([], None), "source_errors must be empty when source_error_count is zero")

    row_counts = normalized_row_counts(report)
    validate_import_artifacts(report)
    validate_no_secret_markers(report)
    return row_counts


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--allow-source-error-waiver",
        action="store_true",
        help="Accept source errors only when the report records an explicit manager waiver id.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        report = load_report(Path(args.report))
        validate_migration_report(report, allow_source_error_waiver=args.allow_source_error_waiver)
    except MigrationReportValidationError as exc:
        print(f"postgres migration report validation failed: {exc}", file=sys.stderr)
        return 1
    print("postgres migration report validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
