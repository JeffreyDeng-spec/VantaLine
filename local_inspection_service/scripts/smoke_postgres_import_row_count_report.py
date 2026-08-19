#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.postgres_import_row_count_report import (  # noqa: E402
    build_row_count_report,
    load_observed_counts,
)
from local_inspection_service.scripts.validate_postgres_migration_report import (  # noqa: E402
    MigrationReportValidationError,
    validate_migration_report,
)
from local_inspection_service.storage.schema import SCHEMA_VERSION, TABLES  # noqa: E402


def migration_report() -> dict[str, object]:
    row_counts = {table.name: 0 for table in TABLES}
    row_counts.update(
        {
            "schema_migrations": 1,
            "users": 2,
            "auth_sessions": 1,
            "accessories": 3,
            "audit_events": 1,
        }
    )
    return {
        "report_version": 1,
        "schema_version": SCHEMA_VERSION,
        "target": "postgresql",
        "postgres_schema": "vantaline",
        "ddl_sha256": "a" * 64,
        "row_counts": row_counts,
        "source_errors": [],
        "source_error_count": 0,
        "blocking_errors": [],
        "blocking_error_counts": {},
        "postgres_import_artifacts": {
            "emitted": True,
            "import_dir": "/tmp/vantaline_import",
            "load_sql_path": "/tmp/vantaline_import/load_postgres.sql",
            "csv_files": {
                table.name: f"/tmp/vantaline_import/tables/{table.name}.csv"
                for table in TABLES
                if table.name != "schema_migrations"
            },
        },
        "cutover_allowed": True,
    }


def assert_valid_migration_report_passes() -> dict[str, int]:
    report = migration_report()
    counts = validate_migration_report(report)
    if counts["schema_migrations"] != 1:
        raise AssertionError(f"schema_migrations baseline should be 1: {counts}")
    return counts


def assert_bad_migration_report_fails() -> None:
    report = migration_report()
    report["cutover_allowed"] = False
    try:
        validate_migration_report(report)
    except MigrationReportValidationError:
        return
    raise AssertionError("migration report validator accepted cutover_allowed=false")


def assert_row_count_parity_passes(expected_counts: dict[str, int]) -> None:
    report = build_row_count_report(migration_report=migration_report(), observed_counts=dict(expected_counts))
    if report.get("row_count_parity_pass") is not True:
        raise AssertionError(f"expected row count parity to pass: {report}")
    if report.get("checked_table_count") != len(TABLES):
        raise AssertionError(f"unexpected checked_table_count: {report}")


def assert_row_count_mismatch_fails(expected_counts: dict[str, int]) -> None:
    observed = dict(expected_counts)
    observed["users"] += 1
    report = build_row_count_report(migration_report=migration_report(), observed_counts=observed)
    if report.get("row_count_parity_pass") is not False:
        raise AssertionError(f"expected row count parity to fail: {report}")
    if not any(item.get("table") == "users" for item in report.get("mismatches", [])):
        raise AssertionError(f"users mismatch missing from report: {report}")


def assert_observed_counts_file_loads(expected_counts: dict[str, int]) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_import_counts_"))
    counts_path = temp_root / "counts.json"
    counts_path.write_text(json.dumps(expected_counts, sort_keys=True), encoding="utf-8")
    loaded = load_observed_counts(inline_json="", counts_file=str(counts_path))
    if loaded != expected_counts:
        raise AssertionError(f"observed counts file did not round-trip: {loaded}")


def assert_secret_marker_is_rejected() -> None:
    report = migration_report()
    report["leak"] = "password_hash=bad"
    try:
        validate_migration_report(report)
    except MigrationReportValidationError:
        return
    raise AssertionError("migration report validator accepted a forbidden secret marker")


def main() -> None:
    expected_counts = assert_valid_migration_report_passes()
    assert_bad_migration_report_fails()
    assert_row_count_parity_passes(expected_counts)
    assert_row_count_mismatch_fails(expected_counts)
    assert_observed_counts_file_loads(expected_counts)
    assert_secret_marker_is_rejected()
    print("postgres import row count report smoke passed")


if __name__ == "__main__":
    main()
