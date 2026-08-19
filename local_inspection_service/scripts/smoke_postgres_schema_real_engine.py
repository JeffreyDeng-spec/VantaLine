#!/usr/bin/env python3
"""Run the generated PostgreSQL DDL through a real PostgreSQL backend.

This smoke intentionally uses PostgreSQL single-user mode. It validates SQL
parsing/execution without opening TCP or Unix sockets, so it can run in locked
down environments where a normal postmaster cannot be started.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service.storage.postgres_schema import postgres_ddl  # noqa: E402
from local_inspection_service.storage.schema import SCHEMA_VERSION, TABLES  # noqa: E402


def compact_generated_ddl(sql: str) -> str:
    """Make generated DDL safe for postgres --single's line-oriented input."""
    without_comments = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    statements = [" ".join(part.split()) + ";" for part in without_comments.split(";") if part.strip()]
    return "\n".join(statements)


def run_command(command: list[str], *, env: dict[str, str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def assert_clean_process(result: subprocess.CompletedProcess[str], label: str) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        raise AssertionError(f"{label} failed with exit {result.returncode}:\n{combined[-4000:]}")
    for marker in ("ERROR:", "FATAL:", "PANIC:"):
        if marker in combined:
            raise AssertionError(f"{label} emitted {marker}\n{combined[-4000:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin-dir", default=os.environ.get("VANTALINE_POSTGRES_BIN_DIR", ""))
    parser.add_argument("--library-dir", default=os.environ.get("VANTALINE_POSTGRES_LIBRARY_DIR", ""))
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--schema-name", default="vantaline_real_engine_smoke")
    args = parser.parse_args()

    bin_dir = Path(args.postgres_bin_dir) if args.postgres_bin_dir else Path()
    initdb = bin_dir / "initdb"
    postgres = bin_dir / "postgres"
    if not initdb.exists() or not postgres.exists():
        raise SystemExit("--postgres-bin-dir must point to a directory containing initdb and postgres")

    env = dict(os.environ)
    if args.library_dir:
        env["LD_LIBRARY_PATH"] = args.library_dir + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")

    owned_tmp = None
    if args.data_dir:
        data_dir = Path(args.data_dir)
        if data_dir.exists() and any(data_dir.iterdir()):
            raise SystemExit(f"--data-dir must be empty or absent: {data_dir}")
        data_dir.mkdir(parents=True, exist_ok=True)
    else:
        owned_tmp = tempfile.TemporaryDirectory(prefix="vantaline_pg_real_engine_", dir="/tmp")
        data_dir = Path(owned_tmp.name) / "cluster"

    try:
        init_result = run_command([str(initdb), "-D", str(data_dir), "-A", "trust", "-U", "postgres"], env=env)
        assert_clean_process(init_result, "initdb")

        schema_name = args.schema_name
        ddl = compact_generated_ddl(postgres_ddl(schema_name))
        verification_sql = "\n".join(
            [
                ddl,
                f"SET search_path TO \"{schema_name}\", public;",
                "SELECT version, metadata_json->>'schema_version' AS schema_version FROM schema_migrations;",
                (
                    "SELECT count(*) AS table_count FROM information_schema.tables "
                    f"WHERE table_schema = '{schema_name}' AND table_type = 'BASE TABLE';"
                ),
                "",
            ]
        )
        ddl_result = run_command([str(postgres), "--single", "-D", str(data_dir), "postgres"], env=env, input_text=verification_sql)
        assert_clean_process(ddl_result, "postgres DDL single-user smoke")

        if SCHEMA_VERSION not in ddl_result.stdout:
            raise AssertionError("schema_migrations version was not visible in PostgreSQL single-user output")
        table_count_text = f'table_count = "{len(TABLES)}"'
        if table_count_text not in ddl_result.stdout:
            raise AssertionError(
                f"expected {len(TABLES)} PostgreSQL tables in schema {schema_name}; output was:\n{ddl_result.stdout[-4000:]}"
            )
    finally:
        if owned_tmp is not None:
            owned_tmp.cleanup()
        elif args.data_dir:
            # Leave explicit data dirs in place for caller inspection.
            pass
        else:
            shutil.rmtree(data_dir, ignore_errors=True)

    print("postgres schema real-engine smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
