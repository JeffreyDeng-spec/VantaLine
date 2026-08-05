#!/usr/bin/env python3
"""Verify imported PostgreSQL table counts against a migration report.

Production mode reads counts through `psql`. Smoke tests can pass observed
counts as JSON without needing a local PostgreSQL server. The generated report
is non-secret and intended to feed the final cutover gate summary.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.validate_postgres_migration_report import (  # noqa: E402
    MigrationReportValidationError,
    load_report,
    stable_json,
    validate_migration_report,
)
from local_inspection_service.storage.postgres_schema import quote_ident  # noqa: E402


FORBIDDEN_REPORT_MARKERS = (
    "DATABASE_URL=",
    "postgresql://",
    "password_hash",
    "sha256$",
    "vantaline_session=",
)


class RowCountReportError(AssertionError):
    """Raised when row-count parity cannot be verified safely."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RowCountReportError(message)


def validate_no_secret_markers(report: dict[str, Any]) -> bool:
    text = stable_json(report).lower()
    return not any(marker.lower() in text for marker in FORBIDDEN_REPORT_MARKERS)


def parse_counts_json(text: str) -> dict[str, int]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RowCountReportError("observed counts JSON is invalid") from exc
    require(isinstance(payload, dict), "observed counts must be a JSON object")
    counts: dict[str, int] = {}
    for table, value in payload.items():
        require(isinstance(table, str) and table, "observed count table names must be non-empty strings")
        require(isinstance(value, int) and value >= 0, f"observed count for {table} must be a non-negative integer")
        counts[table] = int(value)
    return counts


def load_observed_counts(*, inline_json: str, counts_file: str) -> dict[str, int] | None:
    if inline_json and counts_file:
        raise RowCountReportError("use only one of --observed-counts-json or --observed-counts-file")
    if inline_json:
        return parse_counts_json(inline_json)
    if counts_file:
        try:
            return parse_counts_json(Path(counts_file).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RowCountReportError(f"observed counts file not found: {counts_file}") from exc
    return None


def psql_count(*, psql_bin: str, db_url: str, schema_name: str, table_name: str) -> int:
    sql = f"select count(*) from {quote_ident(schema_name)}.{quote_ident(table_name)}"
    result = subprocess.run(
        [psql_bin, db_url, "-v", "ON_ERROR_STOP=1", "-tAc", sql],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RowCountReportError(f"psql count failed for table={table_name}")
    value = result.stdout.strip()
    try:
        count = int(value)
    except ValueError as exc:
        raise RowCountReportError(f"psql count for table={table_name} was not an integer") from exc
    require(count >= 0, f"psql count for table={table_name} must be non-negative")
    return count


def collect_psql_counts(*, psql_bin: str, db_url: str, schema_name: str, table_names: tuple[str, ...]) -> dict[str, int]:
    require(bool(db_url), "--db-url is required when observed counts are not supplied")
    return {
        table_name: psql_count(psql_bin=psql_bin, db_url=db_url, schema_name=schema_name, table_name=table_name)
        for table_name in table_names
    }


def build_row_count_report(
    *,
    migration_report: dict[str, Any],
    observed_counts: dict[str, int],
    allow_source_error_waiver: bool = False,
) -> dict[str, Any]:
    try:
        expected_counts = validate_migration_report(
            migration_report,
            allow_source_error_waiver=allow_source_error_waiver,
        )
    except MigrationReportValidationError as exc:
        raise RowCountReportError(str(exc)) from exc

    mismatches: list[dict[str, int | str | None]] = []
    for table_name, expected_count in sorted(expected_counts.items()):
        observed = observed_counts.get(table_name)
        if observed != expected_count:
            mismatches.append({"table": table_name, "expected": expected_count, "observed": observed})
    extra_tables = sorted(set(observed_counts) - set(expected_counts))
    for table_name in extra_tables:
        mismatches.append({"table": table_name, "expected": None, "observed": observed_counts[table_name]})
    report: dict[str, Any] = {
        "mode": "postgres-import-row-count-report",
        "migration_schema_version": migration_report.get("schema_version"),
        "postgres_schema": migration_report.get("postgres_schema"),
        "migration_cutover_allowed": migration_report.get("cutover_allowed") is True,
        "checked_table_count": len(expected_counts),
        "row_count_parity_pass": not mismatches,
        "mismatches": mismatches,
        "schema_migrations_expected": expected_counts.get("schema_migrations"),
        "schema_migrations_observed": observed_counts.get("schema_migrations"),
        "non_secret_report": True,
    }
    report["non_secret_report"] = validate_no_secret_markers(report)
    if not report["non_secret_report"]:
        report["row_count_parity_pass"] = False
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration-report", required=True)
    parser.add_argument("--db-url", default="")
    parser.add_argument("--schema-name", default="")
    parser.add_argument("--psql-bin", default="psql")
    parser.add_argument("--observed-counts-json", default="")
    parser.add_argument("--observed-counts-file", default="")
    parser.add_argument("--report", default="")
    parser.add_argument("--allow-source-error-waiver", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        migration_report = load_report(Path(args.migration_report))
        expected_counts = validate_migration_report(
            migration_report,
            allow_source_error_waiver=args.allow_source_error_waiver,
        )
        observed_counts = load_observed_counts(
            inline_json=args.observed_counts_json,
            counts_file=args.observed_counts_file,
        )
        if observed_counts is None:
            schema_name = args.schema_name or str(migration_report.get("postgres_schema") or "")
            observed_counts = collect_psql_counts(
                psql_bin=args.psql_bin,
                db_url=args.db_url,
                schema_name=schema_name,
                table_names=tuple(sorted(expected_counts)),
            )
        report = build_row_count_report(
            migration_report=migration_report,
            observed_counts=observed_counts,
            allow_source_error_waiver=args.allow_source_error_waiver,
        )
    except (MigrationReportValidationError, RowCountReportError) as exc:
        print(f"postgres import row count report failed: {exc}", file=sys.stderr)
        return 1

    output = stable_json(report) + "\n"
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if report["row_count_parity_pass"]:
        print("postgres import row count parity passed")
        return 0
    print("postgres import row count parity failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
