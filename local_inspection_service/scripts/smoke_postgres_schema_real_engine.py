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


def single_user_input(commands: list[str]) -> str:
    """Frame complete SQL commands for postgres --single -j without parsing SQL.

    Commands must use LF line endings. The backend input reader recognizes
    ;\n\n even inside quotes; reject it instead of changing SQL contents.
    """
    framed = []
    for command in commands:
        if "\r" in command:
            raise ValueError("Single-user SQL command must use LF line endings")
        command = command.rstrip("\n")
        if ";\n\n" in command:
            raise ValueError("SQL contains the single-user command delimiter")
        if not command.endswith(";"):
            raise ValueError("Single-user SQL command must end with a semicolon")
        framed.append(command + "\n\n")
    return "".join(framed)


def verify_input_framing() -> None:
    command = "DO $body$\nBEGIN\n    PERFORM 'two  spaces;quoted';\nEND;\n$body$;"
    if single_user_input([command]) != command + "\n\n":
        raise AssertionError("SQL command content was changed during framing")
    for invalid in ("SELECT ';\n\nquoted';", "SELECT 1;\r\n", "SELECT 1"):
        try:
            single_user_input([invalid])
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe single-user input framing was accepted")


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
    verify_input_framing()
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
        ddl = postgres_ddl(schema_name)
        verification_sql = single_user_input(
            [
                ddl,
                f"SET search_path TO \"{schema_name}\", public;",
                "SELECT version, metadata_json->>'schema_version' AS schema_version FROM schema_migrations;",
                (
                    "SELECT count(*) AS table_count FROM information_schema.tables "
                    f"WHERE table_schema = '{schema_name}' AND table_type = 'BASE TABLE';"
                ),
                (
                    "SELECT count(*) AS invalidation_trigger_count FROM pg_trigger t "
                    "JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    f"WHERE n.nspname='{schema_name}' AND c.relname='label_inspection_objects' "
                    "AND t.tgname='invalidate_label_run_projection' AND NOT t.tgisinternal;"
                ),
                "SELECT 'semi;colon' AS input_framing;",
            ]
        )
        ddl_result = run_command([str(postgres), "--single", "-j", "-D", str(data_dir), "postgres"], env=env, input_text=verification_sql)
        assert_clean_process(ddl_result, "postgres DDL single-user smoke")

        if SCHEMA_VERSION not in ddl_result.stdout:
            raise AssertionError("schema_migrations version was not visible in PostgreSQL single-user output")
        table_count_text = f'table_count = "{len(TABLES)}"'
        if table_count_text not in ddl_result.stdout:
            raise AssertionError(
                f"expected {len(TABLES)} PostgreSQL tables in schema {schema_name}; output was:\n{ddl_result.stdout[-4000:]}"
            )
        for expected in ('invalidation_trigger_count = "1"', 'input_framing = "semi;colon"'):
            if expected not in ddl_result.stdout:
                raise AssertionError(f"single-user verification output missing {expected}")

        # Single-user mode can return zero despite a SQL error: keep the output
        # gate effective, rather than treating process success as DDL success.
        invalid_result = run_command(
            [str(postgres), "--single", "-j", "-D", str(data_dir), "postgres"],
            env=env,
            input_text=single_user_input(["SELECT 1/0;"]),
        )
        if "ERROR:" not in invalid_result.stdout + invalid_result.stderr:
            raise AssertionError("negative SQL control did not emit ERROR")
        try:
            assert_clean_process(invalid_result, "intentional invalid SQL")
        except AssertionError:
            pass
        else:
            raise AssertionError("SQL error was accepted by the real-engine gate")
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
