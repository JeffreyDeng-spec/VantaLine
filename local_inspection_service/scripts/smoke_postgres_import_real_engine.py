#!/usr/bin/env python3
"""Validate PostgreSQL import artifacts with a real PostgreSQL backend.

By default this smoke creates a clean JSON fixture and generates the normal
PostgreSQL migration packet. For cutover, pass --ddl and --migration-report to
validate the actual frozen migration artifacts. The smoke executes the DDL,
imports the emitted CSV files via server-side COPY, and checks row counts. It
uses PostgreSQL single-user mode so it does not open TCP or Unix sockets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service.scripts.smoke_postgres_migration_packet import run_packet  # noqa: E402
from local_inspection_service.scripts.smoke_postgres_schema_real_engine import (  # noqa: E402
    assert_clean_process,
    compact_generated_ddl,
    run_command,
)
from local_inspection_service.scripts.smoke_data_layer_migration import build_source  # noqa: E402
from local_inspection_service.scripts.prepare_json_to_postgres import copy_options_for_table  # noqa: E402
from local_inspection_service.storage.postgres_schema import quote_ident  # noqa: E402
from local_inspection_service.storage.schema import TABLES  # noqa: E402


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_statement(table_name: str, csv_path: Path) -> str:
    table = next(table for table in TABLES if table.name == table_name)
    columns = ", ".join(quote_ident(column) for column in table.columns)
    return (
        f"COPY {quote_ident(table_name)} ({columns}) FROM {sql_literal(str(csv_path))} "
        f"WITH ({copy_options_for_table(table)});"
    )


def count_statement(table_name: str) -> str:
    return (
        f"SELECT {sql_literal(table_name)} AS table_name, "
        f"count(*)::text AS row_count FROM {quote_ident(table_name)};"
    )


def load_existing_packet(ddl_path: Path, report_path: Path) -> tuple[Path, dict[str, object], str]:
    if not ddl_path.is_file():
        raise AssertionError(f"DDL artifact is missing: {ddl_path}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssertionError(f"migration report is missing: {report_path}") from exc
    except json.JSONDecodeError as exc:
        raise AssertionError(f"migration report is not valid JSON: {report_path}") from exc
    if not isinstance(report, dict):
        raise AssertionError("migration report root must be a JSON object")
    schema_name = str(report.get("postgres_schema") or "").strip()
    if not schema_name:
        raise AssertionError("migration report missing postgres_schema")
    return ddl_path, report, schema_name


def build_fixture_packet(root: Path) -> tuple[Path, dict[str, object], str]:
    source = build_source(root / "source")
    packet_root = root / "packet"
    _summary, report = run_packet(source, packet_root)
    return packet_root / "schema.sql", report, str(report.get("postgres_schema") or "vantaline")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin-dir", default=os.environ.get("VANTALINE_POSTGRES_BIN_DIR", ""))
    parser.add_argument("--library-dir", default=os.environ.get("VANTALINE_POSTGRES_LIBRARY_DIR", ""))
    parser.add_argument("--ddl", default="", help="Existing generated PostgreSQL DDL artifact to validate")
    parser.add_argument("--migration-report", default="", help="Existing migration report whose CSV artifacts should be imported")
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    if bool(args.ddl) != bool(args.migration_report):
        raise SystemExit("--ddl and --migration-report must be supplied together")

    bin_dir = Path(args.postgres_bin_dir) if args.postgres_bin_dir else Path()
    initdb = bin_dir / "initdb"
    postgres = bin_dir / "postgres"
    if not initdb.exists() or not postgres.exists():
        raise SystemExit("--postgres-bin-dir must point to a directory containing initdb and postgres")

    env = dict(os.environ)
    if args.library_dir:
        env["LD_LIBRARY_PATH"] = args.library_dir + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")

    with tempfile.TemporaryDirectory(prefix="vantaline_pg_import_real_engine_", dir="/tmp") as tmp_raw:
        root = Path(tmp_raw)
        if args.ddl:
            ddl_path, report, schema_name = load_existing_packet(Path(args.ddl), Path(args.migration_report))
            artifact_source = "existing-migration-packet"
        else:
            ddl_path, report, schema_name = build_fixture_packet(root)
            artifact_source = "fixture-migration-packet"
        csv_files = (report.get("postgres_import_artifacts") or {}).get("csv_files") or {}
        if not csv_files:
            raise AssertionError("migration packet did not emit CSV import artifacts")

        data_dir = root / "cluster"
        init_result = run_command([str(initdb), "-D", str(data_dir), "-A", "trust", "-U", "postgres"], env=env)
        assert_clean_process(init_result, "initdb")

        statements = [compact_generated_ddl(ddl_path.read_text(encoding="utf-8")), f"SET search_path TO {quote_ident(schema_name)}, public;"]
        for table in TABLES:
            if table.name == "schema_migrations":
                continue
            csv_path_text = csv_files.get(table.name)
            if not csv_path_text:
                raise AssertionError(f"missing CSV path for import table: {table.name}")
            csv_path = Path(str(csv_path_text))
            if not csv_path.exists():
                raise AssertionError(f"CSV import artifact is missing: {csv_path}")
            statements.append(copy_statement(table.name, csv_path))
        for table in TABLES:
            statements.append(count_statement(table.name))
        statements.append("")

        import_result = run_command(
            [str(postgres), "--single", "-D", str(data_dir), "postgres"],
            env=env,
            input_text="\n".join(statements),
        )
        assert_clean_process(import_result, "postgres import single-user smoke")

        row_counts = report.get("row_counts") or {}
        expected_counts = {table.name: int(row_counts.get(table.name, 0)) for table in TABLES}
        expected_counts["schema_migrations"] = 1
        for table_name, expected in expected_counts.items():
            if f'table_name = "{table_name}"' not in import_result.stdout or f'row_count = "{expected}"' not in import_result.stdout:
                raise AssertionError(
                    f"PostgreSQL row count output missing {table_name}={expected}; output was:\n"
                    f"{import_result.stdout[-6000:]}"
                )

        smoke_report = {
            "mode": "postgres-import-real-engine-smoke",
            "postgres_engine": "single-user",
            "artifact_source": artifact_source,
            "schema_name": schema_name,
            "migration_schema_version": str(report.get("schema_version") or ""),
            "migration_report_sha256": hashlib.sha256(stable_json(report).encode("utf-8")).hexdigest(),
            "ddl_sha256": file_sha256(ddl_path),
            "ddl_real_engine_pass": True,
            "csv_import_real_engine_pass": True,
            "row_count_parity_pass": True,
            "checked_table_count": len(expected_counts),
            "non_secret_report": True,
        }
        if args.report:
            report_path = Path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(stable_json(smoke_report) + "\n", encoding="utf-8")

    print("postgres import real-engine smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
