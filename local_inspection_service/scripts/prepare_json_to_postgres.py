#!/usr/bin/env python3
"""Prepare reviewable VantaLine JSON-to-PostgreSQL migration artifacts.

This script does not connect to production PostgreSQL, does not change the
FastAPI runtime, and does not set VANTALINE_DATA_STORE. It inventories JSON
metadata, applies the same validation policy as the accepted SQLite shadow
migrator, then emits PostgreSQL DDL plus psql import artifacts only when the
source is clean or an explicit source-error waiver id is supplied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service.scripts.migrate_json_to_sqlite import collect_rows, stable_hash, stable_json
from local_inspection_service.storage.json_loader import load_inventory
from local_inspection_service.storage.postgres_schema import BOOLEAN_COLUMNS, JSONB_COLUMNS, postgres_ddl, postgres_type, quote_ident
from local_inspection_service.storage.schema import SCHEMA_VERSION, SOURCE_TO_TABLE_MAPPING, TABLES


def default_artifact_path(name: str) -> Path:
    timestamp = int(time.time() * 1000)
    return Path(tempfile.gettempdir()) / f"vantaline_postgres_{name}_{timestamp}"


def csv_value(column: str, value: Any) -> str:
    if column in JSONB_COLUMNS:
        if isinstance(value, str):
            # Validate and compact JSON strings that were produced by stable_json.
            return stable_json(json.loads(value))
        return stable_json(value)
    if column in BOOLEAN_COLUMNS:
        return "true" if bool(value) else "false"
    return str(value if value is not None else "")


def schema_migration_row() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "applied_at": 0,
        "metadata_json": stable_json({"schema_version": SCHEMA_VERSION, "artifact": "postgres_import"}),
    }


def audit_event_row() -> dict[str, Any]:
    return {
        "id": stable_hash({"schema_version": SCHEMA_VERSION, "event": "postgres_import_prepare"}, prefix="audit_")[:24],
        "event_type": "postgres_import_prepare",
        "created_at": 0,
        "actor_user_id": "",
        "payload_json": stable_json({"schema_version": SCHEMA_VERSION, "artifact": "postgres_import"}),
    }


def collected_rows_by_table(state: Any) -> dict[str, list[dict[str, Any]]]:
    rows = {name: list(items) for name, items in state.rows.items()}
    rows["schema_migrations"] = [schema_migration_row()]
    rows["audit_events"] = list(rows.get("audit_events", [])) + [audit_event_row()]
    return rows


def write_csv_table(path: Path, table_name: str, rows: list[dict[str, Any]]) -> None:
    table = next(table for table in TABLES if table.name == table_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(table.columns)
        for row in rows:
            writer.writerow([csv_value(column, row.get(column)) for column in table.columns])


def psql_literal(path: Path) -> str:
    return str(path).replace("'", "''")


def copy_options_for_table(table: Any) -> str:
    text_columns = [column for column in table.columns if postgres_type(column) == "TEXT"]
    options = ["FORMAT csv", "HEADER true"]
    if text_columns:
        options.append("FORCE_NOT_NULL (" + ", ".join(quote_ident(column) for column in text_columns) + ")")
    return ", ".join(options)


def write_import_artifacts(*, out_dir: Path, schema_name: str, state: Any) -> dict[str, Any]:
    rows_by_table = collected_rows_by_table(state)
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    load_lines = [
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        f"SET search_path TO {quote_ident(schema_name)}, public;",
    ]
    csv_files: dict[str, str] = {}
    for table in TABLES:
        if table.name == "schema_migrations":
            # The DDL seeds schema_migrations with ON CONFLICT semantics. psql
            # \copy cannot upsert, so importing this table would duplicate the
            # seeded version in the normal DDL-then-load flow.
            continue
        rows = rows_by_table.get(table.name, [])
        csv_path = tables_dir / f"{table.name}.csv"
        write_csv_table(csv_path, table.name, rows)
        csv_files[table.name] = str(csv_path)
        columns = ", ".join(quote_ident(column) for column in table.columns)
        load_lines.append(
            f"\\copy {quote_ident(table.name)} ({columns}) FROM '{psql_literal(csv_path)}' WITH ({copy_options_for_table(table)})"
        )
    load_lines.extend(["COMMIT;", ""])
    load_sql = out_dir / "load_postgres.sql"
    load_sql.write_text("\n".join(load_lines), encoding="utf-8")
    return {"import_dir": str(out_dir), "load_sql_path": str(load_sql), "csv_files": csv_files}


def summarize_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        code = str(item.get("code") or "unknown")
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_report(
    *,
    source: Path,
    ddl_path: Path,
    out_dir: Path,
    schema_name: str,
    state: Any,
    import_artifacts: dict[str, Any] | None,
    waiver_id: str,
) -> dict[str, Any]:
    source_errors = sorted(state.source_errors, key=lambda item: item["source"])
    blocking_errors = sorted(state.blocking_errors, key=lambda item: (item["table"], item["code"], item["detail"]))
    source_errors_waived = bool(source_errors and waiver_id)
    cutover_allowed = not blocking_errors and (not source_errors or source_errors_waived)
    return {
        "report_version": 1,
        "schema_version": SCHEMA_VERSION,
        "target": "postgresql",
        "source_root": str(Path(source).resolve()),
        "postgres_schema": schema_name,
        "ddl_path": str(ddl_path),
        "ddl_sha256": file_sha256(ddl_path),
        "source_to_table_mapping": SOURCE_TO_TABLE_MAPPING,
        "row_counts": {table.name: len(collected_rows_by_table(state).get(table.name, [])) for table in TABLES},
        "source_errors": source_errors,
        "source_warnings": sorted(state.source_warnings, key=lambda item: item["source"]),
        "source_error_count": len(source_errors),
        "source_error_policy": "waived_explicitly" if source_errors_waived else "block_cutover",
        "source_error_waiver_id": waiver_id if source_errors_waived else "",
        "blocking_errors": blocking_errors,
        "blocking_error_counts": summarize_counts(blocking_errors),
        "warnings": sorted(state.warnings, key=lambda item: (item["table"], item["code"], item["detail"]))[:200],
        "warning_counts": summarize_counts(state.warnings),
        "duplicate_counts": dict(sorted(state.duplicate_counts.items())),
        "missing_owner_counts": dict(sorted(state.missing_owner_counts.items())),
        "orphan_counts": dict(sorted(state.orphan_counts.items())),
        "missing_path_counts": dict(sorted(state.missing_path_counts.items())),
        "legacy_repair_count": len(state.legacy_repairs),
        "postgres_import_artifacts": import_artifacts or {"import_dir": str(out_dir), "emitted": False},
        "cutover_allowed": cutover_allowed,
        "next_required_action": (
            "fix_source_errors_or_record_manager_waiver"
            if source_errors and not source_errors_waived
            else ("clear_blocking_errors" if blocking_errors else "challenger_review")
        ),
        "security_policy": {
            "reports": "raw session tokens, password verifier values, provider keys, and local env contents are omitted",
            "import_artifacts": "auth session ids are hashed; local secret/config files are excluded",
            "runtime": "no production apply, no runtime switch, no VANTALINE_DATA_STORE mutation",
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(REPO_ROOT / "local_inspection_service"), help="Repo, service, or data directory to inventory")
    parser.add_argument("--schema-name", default="vantaline", help="PostgreSQL schema name for generated DDL/load scripts")
    parser.add_argument("--ddl", default="", help="DDL output path. Defaults to /tmp.")
    parser.add_argument("--out-dir", default="", help="Import artifact directory. Defaults to /tmp.")
    parser.add_argument("--report", default="", help="Redacted JSON report path. Defaults to /tmp.")
    parser.add_argument("--allow-legacy-id-repair", action="store_true", help="Deterministically repair legacy accessory IDs missing in config.json.")
    parser.add_argument("--source-error-waiver-id", default="", help="Explicit manager waiver id required before emitting import files with source parse errors.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    source = Path(args.source)
    schema_name = args.schema_name
    quote_ident(schema_name)
    ddl_path = Path(args.ddl) if args.ddl else default_artifact_path("schema.sql")
    out_dir = Path(args.out_dir) if args.out_dir else default_artifact_path("import")
    report_path = Path(args.report) if args.report else default_artifact_path("report.json")
    ddl_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    inventory = load_inventory(source)
    state = collect_rows(inventory, allow_legacy_id_repair=bool(args.allow_legacy_id_repair))
    ddl_path.write_text(postgres_ddl(schema_name), encoding="utf-8")
    can_emit_import = not state.blocking_errors and (not state.source_errors or bool(args.source_error_waiver_id))
    import_artifacts = write_import_artifacts(out_dir=out_dir, schema_name=schema_name, state=state) if can_emit_import else None
    if import_artifacts:
        import_artifacts["emitted"] = True
    report = build_report(
        source=source,
        ddl_path=ddl_path,
        out_dir=out_dir,
        schema_name=schema_name,
        state=state,
        import_artifacts=import_artifacts,
        waiver_id=str(args.source_error_waiver_id or "").strip(),
    )
    report_path.write_text(stable_json(report) + "\n", encoding="utf-8")
    summary = {
        "report_path": str(report_path),
        "ddl_path": str(ddl_path),
        "import_artifact_emitted": bool(import_artifacts),
        "source_error_count": len(state.source_errors),
        "blocking_error_count": len(state.blocking_errors),
        "cutover_allowed": report["cutover_allowed"],
        "next_required_action": report["next_required_action"],
    }
    print(stable_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
