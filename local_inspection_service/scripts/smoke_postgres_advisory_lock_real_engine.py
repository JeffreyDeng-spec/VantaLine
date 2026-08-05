#!/usr/bin/env python3
"""Prove the PLC config advisory lock with two real PostgreSQL connections."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import threading
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository  # noqa: E402
from local_inspection_service.storage.postgres_schema import postgres_ddl  # noqa: E402


LOCK_NAMESPACE = "vantaline:plc-config-namespace"


def wait_for_postgres(dsn: str, deadline: float):
    import psycopg

    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return psycopg.connect(dsn)
        except Exception as exc:  # noqa: BLE001 - startup polling records the final concrete error
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"temporary PostgreSQL did not start: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin-dir", default=os.environ.get("VANTALINE_POSTGRES_BIN_DIR", ""))
    parser.add_argument("--library-dir", default=os.environ.get("VANTALINE_POSTGRES_LIBRARY_DIR", ""))
    args = parser.parse_args()
    bin_dir = Path(args.postgres_bin_dir)
    initdb = bin_dir / "initdb"
    postgres = bin_dir / "postgres"
    if not initdb.is_file() or not postgres.is_file():
        raise SystemExit("--postgres-bin-dir must contain initdb and postgres")

    env = dict(os.environ)
    if args.library_dir:
        env["LD_LIBRARY_PATH"] = args.library_dir + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")

    with tempfile.TemporaryDirectory(prefix="vantaline_pg_lock_real_", dir="/tmp") as tmp_raw:
        root = Path(tmp_raw)
        cluster = root / "cluster"
        socket_dir = root / "socket"
        socket_dir.mkdir()
        initialized = subprocess.run(
            [str(initdb), "-D", str(cluster), "-A", "trust", "-U", "postgres"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if initialized.returncode != 0:
            raise RuntimeError(f"initdb failed: {initialized.stderr[-2000:]}")
        port = random.randint(20000, 50000)
        process = subprocess.Popen(
            [str(postgres), "-D", str(cluster), "-k", str(socket_dir), "-p", str(port), "-c", "listen_addresses="],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        dsn = f"dbname=postgres user=postgres host={socket_dir} port={port}"
        owner = None
        try:
            owner = wait_for_postgres(dsn, time.time() + 15)
            owner.execute(postgres_ddl("vantaline"))
            owner.commit()

            owner.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_NAMESPACE,))
            owner.execute(
                'INSERT INTO "vantaline"."app_config" '
                '(config_key, config_value_json, source_file, updated_at) VALUES (%s, %s, %s, %s)',
                ("plc.enabled", json.dumps(True), "config.json", 1),
            )

            replace_started = threading.Event()
            replace_finished = threading.Event()
            replace_errors: list[BaseException] = []

            def replace_config() -> None:
                import psycopg

                connection = psycopg.connect(dsn)
                try:
                    replace_started.set()
                    PostgresRuntimeRepository(connection, "postgresql://redacted").replace_app_config_preserving_keys(
                        [
                            {
                                "config_key": "active_model_id",
                                "config_value_json": "model-a",
                                "source_file": "config.json",
                                "updated_at": 2,
                            }
                        ],
                        ("plc.enabled",),
                    )
                except BaseException as exc:  # noqa: BLE001 - propagate worker failures to the main assertion thread
                    replace_errors.append(exc)
                finally:
                    connection.close()
                    replace_finished.set()

            worker = threading.Thread(target=replace_config, daemon=True)
            worker.start()
            if not replace_started.wait(3):
                raise AssertionError("replacement connection did not start")
            time.sleep(0.5)
            if replace_finished.is_set():
                raise AssertionError("second connection bypassed the held advisory transaction lock")
            owner.commit()
            worker.join(timeout=5)
            if worker.is_alive() or replace_errors:
                raise AssertionError(f"replacement did not complete cleanly after commit: {replace_errors}")

            rows = owner.execute(
                'SELECT config_key, config_value_json FROM "vantaline"."app_config" ORDER BY config_key'
            ).fetchall()
            owner.rollback()
            values = {str(key): value for key, value in rows}
            if values.get("plc.enabled") is not True or values.get("active_model_id") != "model-a":
                raise AssertionError(f"locked absent-row insert was not preserved across config replacement: {values}")

            owner.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_NAMESPACE,))
            rollback_acquired = threading.Event()
            rollback_errors: list[BaseException] = []

            def wait_after_rollback() -> None:
                import psycopg

                connection = psycopg.connect(dsn)
                try:
                    connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_NAMESPACE,))
                    rollback_acquired.set()
                    connection.commit()
                except BaseException as exc:  # noqa: BLE001
                    rollback_errors.append(exc)
                finally:
                    connection.close()

            rollback_worker = threading.Thread(target=wait_after_rollback, daemon=True)
            rollback_worker.start()
            time.sleep(0.5)
            if rollback_acquired.is_set():
                raise AssertionError("second connection acquired lock before owner rollback")
            owner.rollback()
            rollback_worker.join(timeout=5)
            if rollback_worker.is_alive() or rollback_errors or not rollback_acquired.is_set():
                raise AssertionError(f"advisory lock was not released by rollback: {rollback_errors}")
        finally:
            if owner is not None:
                owner.close()
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.returncode not in {0, -15}:
                output = process.stdout.read() if process.stdout else ""
                raise RuntimeError(f"temporary postgres exited unexpectedly ({process.returncode}): {output[-2000:]}")

    print("PASS: real PostgreSQL advisory lock serializes absent-row config replacement and releases on commit/rollback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
