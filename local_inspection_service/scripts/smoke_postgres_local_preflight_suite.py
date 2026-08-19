#!/usr/bin/env python3
"""Run the socket-free local PostgreSQL migration preflight smoke suite.

This suite is read-only with respect to production. It does not connect to a
live PostgreSQL service, mutate roles/databases, change service env, restart
services, or prove deployed-postgres final acceptance.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "local_inspection_service" / "scripts"
DEFAULT_REPORT = Path(tempfile.gettempdir()) / "vantaline_postgres_local_preflight_suite.json"
DEFAULT_PG_RUNTIME = Path("/tmp/vantaline_pg_runtime")
DEFAULT_POSTGRES_BIN_DIR = DEFAULT_PG_RUNTIME / "usr/lib/postgresql/16/bin"
DEFAULT_POSTGRES_LIBRARY_DIR = DEFAULT_PG_RUNTIME / "usr/lib/x86_64-linux-gnu"

FORBIDDEN_REPORT_MARKERS = (
    "DATABASE_URL=",
    "postgresql://",
    "VANTALINE_SMOKE_PASSWORD=",
    "password=",
    "cookie",
    "vantaline_session=",
)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def script(name: str) -> str:
    return str(SCRIPT_DIR / name)


def command_result(
    *,
    name: str,
    args: list[str],
    env: dict[str, str],
    required: bool = True,
) -> dict[str, Any]:
    start = time.time()
    result = subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    duration_ms = int((time.time() - start) * 1000)
    stdout_tail = result.stdout[-2000:]
    stderr_tail = result.stderr[-2000:]
    return {
        "name": name,
        "required": required,
        "status": "pass" if result.returncode == 0 else "fail",
        "returncode": result.returncode,
        "duration_ms": duration_ms,
        "command": command_summary(args),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


def command_summary(args: list[str]) -> list[str]:
    return [str(item) for item in args]


def skip_result(name: str, reason: str, *, required: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "required": required,
        "status": "skip",
        "returncode": None,
        "duration_ms": 0,
        "command": [],
        "stdout_tail": "",
        "stderr_tail": reason,
    }


def has_no_secret_markers(value: Any) -> bool:
    text = stable_json(value).lower()
    return not any(marker.lower() in text for marker in FORBIDDEN_REPORT_MARKERS)


def suite_commands(report_root: Path) -> list[tuple[str, list[str]]]:
    python = sys.executable
    return [
        ("runtime selector", [python, script("smoke_runtime_store_selector.py")]),
        ("postgres runtime repository", [python, script("smoke_postgres_runtime_repository.py")]),
        ("postgres endpoint source contract", [python, script("smoke_postgres_endpoint_source_contract.py")]),
        ("endpoint runtime-store probe", [python, script("smoke_endpoint_runtime_store_probe.py")]),
        ("postgres migration packet", [python, script("smoke_postgres_migration_packet.py")]),
        ("data layer migration", [python, script("smoke_data_layer_migration.py")]),
        ("postgres import row-count report", [python, script("smoke_postgres_import_row_count_report.py")]),
        ("postgres precutover report validator", [python, script("smoke_postgres_precutover_report_validator.py")]),
        ("postgres full-smoke report validator", [python, script("smoke_postgres_full_smoke_report_validator.py")]),
        (
            "postgres local preflight suite report validator",
            [python, script("smoke_postgres_local_preflight_suite_report_validator.py")],
        ),
        ("postgres final cutover packet docs", [python, script("smoke_postgres_final_cutover_packet_docs.py")]),
        ("postgres cutover artifact manifest", [python, script("smoke_postgres_cutover_artifact_manifest.py")]),
        ("postgres cutover deploy package", [python, script("smoke_postgres_cutover_deploy_package.py")]),
        ("postgres cutover readiness", [python, script("smoke_postgres_cutover_readiness.py")]),
        ("postgres cutover gate report", [python, script("smoke_postgres_cutover_gate_report.py")]),
        (
            "local fake-postgres full smoke",
            [
                python,
                script("smoke_postgres_cutover_full.py"),
                "--mode",
                "local-fake-postgres",
                "--report",
                str(report_root / "local-fake-postgres-full-smoke.json"),
            ],
        ),
    ]


def real_engine_commands(
    *,
    postgres_bin_dir: Path,
    library_dir: Path | None,
    report_root: Path,
) -> list[tuple[str, list[str]]]:
    python = sys.executable
    base_args = ["--postgres-bin-dir", str(postgres_bin_dir)]
    if library_dir:
        base_args.extend(["--library-dir", str(library_dir)])
    return [
        ("postgres schema real-engine", [python, script("smoke_postgres_schema_real_engine.py"), *base_args]),
        (
            "postgres import real-engine",
            [
                python,
                script("smoke_postgres_import_real_engine.py"),
                *base_args,
                "--report",
                str(report_root / "import-real-engine-smoke.json"),
            ],
        ),
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--postgres-bin-dir", default=os.environ.get("VANTALINE_POSTGRES_BIN_DIR", ""))
    parser.add_argument("--library-dir", default=os.environ.get("VANTALINE_POSTGRES_LIBRARY_DIR", ""))
    parser.add_argument(
        "--require-real-engine",
        action="store_true",
        help="Fail when PostgreSQL single-user smoke binaries are unavailable.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_root = report_path.parent / f"{report_path.stem}_artifacts"
    report_root.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["PYTHONPYCACHEPREFIX"] = env.get("PYTHONPYCACHEPREFIX", str(Path(tempfile.gettempdir()) / "vantaline_pycache"))

    results: list[dict[str, Any]] = []
    for name, command in suite_commands(report_root):
        results.append(command_result(name=name, args=command, env=env))

    postgres_bin_dir = Path(args.postgres_bin_dir) if args.postgres_bin_dir else DEFAULT_POSTGRES_BIN_DIR
    library_dir = Path(args.library_dir) if args.library_dir else (DEFAULT_POSTGRES_LIBRARY_DIR if DEFAULT_POSTGRES_LIBRARY_DIR.exists() else None)
    real_engine_available = (postgres_bin_dir / "initdb").exists() and (postgres_bin_dir / "postgres").exists()
    real_engine_pass = False
    if real_engine_available:
        real_engine_start = len(results)
        for name, command in real_engine_commands(postgres_bin_dir=postgres_bin_dir, library_dir=library_dir, report_root=report_root):
            results.append(command_result(name=name, args=command, env=env))
        real_engine_results = results[real_engine_start:]
        real_engine_pass = bool(real_engine_results) and all(item["status"] == "pass" for item in real_engine_results)
    else:
        skip = skip_result(
            "postgres real-engine smokes",
            f"initdb/postgres not found under {postgres_bin_dir}",
            required=bool(args.require_real_engine),
        )
        results.append(skip)

    failed_required = [item["name"] for item in results if item["required"] and item["status"] != "pass"]
    report: dict[str, Any] = {
        "mode": "postgres-local-preflight-suite",
        "production_cutover_proof": False,
        "socket_free": True,
        "real_engine_required": bool(args.require_real_engine),
        "real_engine_pass": real_engine_pass,
        "service_restart_performed": False,
        "postgres_service_mutation_performed": False,
        "runtime_env_switch_performed": False,
        "required_pass": not failed_required,
        "failed_required": failed_required,
        "result_count": len(results),
        "results": results,
        "non_secret_report": True,
    }
    report["non_secret_report"] = has_no_secret_markers(report)
    if not report["non_secret_report"]:
        report["required_pass"] = False
        if "non_secret_report" not in report["failed_required"]:
            report["failed_required"].append("non_secret_report")

    report_path.write_text(stable_json(report) + "\n", encoding="utf-8")
    if report["required_pass"]:
        print(f"postgres local preflight suite passed: {report_path}")
        return 0
    print(f"postgres local preflight suite failed: {report_path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
