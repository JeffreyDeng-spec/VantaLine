#!/usr/bin/env python3
"""Smoke test for PostgreSQL migration packet generation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "local_inspection_service" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from smoke_data_layer_migration import build_source, make_recoverable_extra_data_source, read_json, write_json

SCRIPT_PATH = SCRIPTS_DIR / "prepare_json_to_postgres.py"
MIGRATION_REPORT_VALIDATOR = SCRIPTS_DIR / "validate_postgres_migration_report.py"
ROW_COUNT_REPORTER = SCRIPTS_DIR / "postgres_import_row_count_report.py"


def run_packet(source: Path, out_root: Path, *, waiver_id: str = "") -> tuple[dict, dict]:
    ddl_path = out_root / "schema.sql"
    out_dir = out_root / "import"
    report_path = out_root / "report.json"
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--source",
        str(source),
        "--ddl",
        str(ddl_path),
        "--out-dir",
        str(out_dir),
        "--report",
        str(report_path),
        "--allow-legacy-id-repair",
    ]
    if waiver_id:
        cmd.extend(["--source-error-waiver-id", waiver_id])
    result = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=True)
    summary = json.loads(result.stdout)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return summary, report


def assert_clean_packet(summary: dict, report: dict, out_root: Path) -> None:
    ddl_text = (out_root / "schema.sql").read_text(encoding="utf-8")
    load_text = (out_root / "import" / "load_postgres.sql").read_text(encoding="utf-8")
    if "JSONB" not in ddl_text or "BIGINT" not in ddl_text:
        raise AssertionError("PostgreSQL DDL did not use expected PostgreSQL types")
    if "CREATE SCHEMA IF NOT EXISTS" not in ddl_text:
        raise AssertionError("PostgreSQL DDL did not create an isolated schema")
    if "INSERT INTO schema_migrations" not in ddl_text:
        raise AssertionError("PostgreSQL DDL should seed schema_migrations with upsert semantics")
    if "\\copy" not in load_text or "users.csv" not in load_text:
        raise AssertionError("psql load script did not include CSV import commands")
    if "FORCE_NOT_NULL" not in load_text or '"class_id"' not in load_text or '"actor_user_id"' not in load_text:
        raise AssertionError("psql load script must force empty TEXT fields to empty strings, not PostgreSQL NULL")
    if "schema_migrations.csv" in load_text or (out_root / "import" / "tables" / "schema_migrations.csv").exists():
        raise AssertionError("psql import artifacts must not copy schema_migrations after DDL seed")
    expected_ddl_sha256 = hashlib.sha256((out_root / "schema.sql").read_bytes()).hexdigest()
    if report.get("ddl_sha256") != expected_ddl_sha256:
        raise AssertionError(f"migration report ddl_sha256 does not match schema.sql: {report.get('ddl_sha256')}")
    if not summary.get("import_artifact_emitted") or not report.get("cutover_allowed"):
        raise AssertionError(f"clean fixture should emit import artifacts: {summary} {report}")
    if report.get("source_error_count") or report.get("blocking_errors"):
        raise AssertionError(f"clean fixture should have no source/blocking errors: {report}")
    users_csv = out_root / "import" / "tables" / "users.csv"
    if "sha256$public-smoke-password-hash" not in users_csv.read_text(encoding="utf-8"):
        raise AssertionError("user password verifier should be present only in import artifacts, not reports")
    report_text = json.dumps(report, ensure_ascii=False)
    for forbidden in (
        "raw-session-token-should-not-leak",
        "sha256$public-smoke-password-hash",
        "provider-key-should-not-leak",
        "agent-token-should-not-leak",
        "env-secret-should-not-leak",
    ):
        if forbidden in report_text:
            raise AssertionError(f"report leaked sensitive fixture value: {forbidden}")
    subprocess.run(
        [sys.executable, str(MIGRATION_REPORT_VALIDATOR), "--report", str(out_root / "report.json")],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    row_count_report = out_root / "row-count-report.json"
    subprocess.run(
        [
            sys.executable,
            str(ROW_COUNT_REPORTER),
            "--migration-report",
            str(out_root / "report.json"),
            "--observed-counts-json",
            json.dumps(report["row_counts"], sort_keys=True),
            "--report",
            str(row_count_report),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    row_count_payload = json.loads(row_count_report.read_text(encoding="utf-8"))
    if row_count_payload.get("row_count_parity_pass") is not True:
        raise AssertionError(f"row count parity report should pass for clean fixture: {row_count_payload}")


def assert_no_schema_migrations_import(out_root: Path) -> None:
    ddl_text = (out_root / "schema.sql").read_text(encoding="utf-8")
    load_text = (out_root / "import" / "load_postgres.sql").read_text(encoding="utf-8")
    if "INSERT INTO schema_migrations" not in ddl_text:
        raise AssertionError("DDL should own schema_migrations seeding")
    if "schema_migrations.csv" in load_text:
        raise AssertionError("load script must not copy schema_migrations after DDL seed")
    if (out_root / "import" / "tables" / "schema_migrations.csv").exists():
        raise AssertionError("import artifact directory must not include schema_migrations.csv")


def assert_source_error_blocks_import(root: Path) -> None:
    source = build_source(root / "source_error")
    bad_path = source / "data" / "accessory_candidates" / "broken.json"
    bad_path.write_text("{not-json", encoding="utf-8")
    summary, report = run_packet(source, root / "source_error_packet")
    if summary.get("import_artifact_emitted") or report.get("postgres_import_artifacts", {}).get("emitted"):
        raise AssertionError("source parse errors must block import artifact emission without waiver")
    if summary.get("source_error_count") != 1 or report.get("source_error_count") != 1:
        raise AssertionError(f"source error was not counted: {summary} {report}")
    if report.get("next_required_action") != "fix_source_errors_or_record_manager_waiver":
        raise AssertionError(f"source error next action is wrong: {report.get('next_required_action')}")
    waived_out = root / "source_error_waived_packet"
    waived_summary, waived_report = run_packet(source, waived_out, waiver_id="manager-waiver-smoke")
    if not waived_summary.get("import_artifact_emitted") or not waived_report.get("postgres_import_artifacts", {}).get("emitted"):
        raise AssertionError(f"waiver-mode should emit import artifacts: {waived_summary} {waived_report}")
    if waived_report.get("source_error_policy") != "waived_explicitly":
        raise AssertionError(f"waiver-mode did not record source-error policy: {waived_report.get('source_error_policy')}")
    assert_no_schema_migrations_import(waived_out)


def assert_recoverable_extra_data_is_warning(root: Path) -> None:
    source = make_recoverable_extra_data_source(root / "recoverable_extra")
    summary, report = run_packet(source, root / "recoverable_extra_packet")
    if summary.get("source_error_count") or report.get("source_errors"):
        raise AssertionError(f"recoverable accessory candidate extra data should not block postgres packet: {summary} {report}")
    if not summary.get("import_artifact_emitted") or not report.get("cutover_allowed"):
        raise AssertionError(f"recoverable extra data should emit import artifacts as warning-only: {summary} {report}")
    if not any(item.get("warning") == "recovered_accessory_candidate_extra_data" for item in report.get("source_warnings", [])):
        raise AssertionError(f"recoverable extra data warning missing from report: {report.get('source_warnings')}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vantaline_postgres_packet_smoke_") as tmp_raw:
        root = Path(tmp_raw)
        source = build_source(root / "clean_source")
        # Keep the clean fixture aligned with the existing SQLite smoke.
        config = read_json(source / "data" / "config.json")
        if not isinstance(config, dict):
            raise AssertionError("fixture config should be object")
        write_json(source / "data" / "config.json", config)
        out_root = root / "clean_packet"
        summary, report = run_packet(source, out_root)
        assert_clean_packet(summary, report, out_root)
        assert_source_error_blocks_import(root)
        assert_recoverable_extra_data_is_warning(root)
    print("postgres migration packet smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
