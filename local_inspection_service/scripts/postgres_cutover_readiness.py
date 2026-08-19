#!/usr/bin/env python3
"""Read-only readiness preflight for the PostgreSQL cutover packet.

This preflight does not connect to PostgreSQL, restart services, read secret
files, or mutate the host. It checks whether the current host has the app,
scripts, docs, clean pre-cutover env, and local tooling needed before a manager
can open the destructive migration/cutover gate.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Any


DEFAULT_APP_ROOT = Path("/opt/vantaline/app")
DEFAULT_TARGET_PY = Path("/opt/vantaline/venv/bin/python")
DEFAULT_POSTGRES_ENV_FILE = Path("/etc/vantaline/postgres.env")
DEFAULT_SERVICE_NAME = "vantaline"

REQUIRED_RELATIVE_FILES = (
    "local_inspection_service/server.py",
    "local_inspection_service/scripts/smoke_postgres_cutover_full.py",
    "local_inspection_service/scripts/postgres_cutover_artifact_manifest.py",
    "local_inspection_service/scripts/postgres_cutover_deploy_package.py",
    "local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py",
    "local_inspection_service/scripts/postgres_cutover_gate_report.py",
    "local_inspection_service/scripts/validate_postgres_migration_report.py",
    "local_inspection_service/scripts/postgres_import_row_count_report.py",
    "local_inspection_service/scripts/smoke_postgres_schema_real_engine.py",
    "local_inspection_service/scripts/smoke_postgres_import_real_engine.py",
    "local_inspection_service/scripts/validate_postgres_precutover_report.py",
    "local_inspection_service/scripts/validate_postgres_full_smoke_report.py",
    "local_inspection_service/scripts/smoke_postgres_endpoint_source_contract.py",
    "local_inspection_service/scripts/migrate_json_to_sqlite.py",
    "local_inspection_service/scripts/smoke_data_layer_migration.py",
    "local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py",
    "local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py",
    "local_inspection_service/scripts/smoke_postgres_local_preflight_suite_report_validator.py",
    "local_inspection_service/scripts/prepare_json_to_postgres.py",
    "local_inspection_service/storage/postgres_schema.py",
    "local_inspection_service/storage/runtime_selector.py",
    "local_inspection_service/storage/postgres_runtime_repository.py",
    "local_inspection_service/docs/postgres-endpoint-integration-accepted.md",
    "local_inspection_service/docs/postgres-final-migration-cutover-execution-packet.md",
)

FILE_MARKERS = {
    "local_inspection_service/server.py": (
        "build_runtime_repository",
        "runtime_store_probe_payload",
        "runtime_postgres_repository_or_none",
        "VANTALINE_DATA_STORE",
    ),
    "local_inspection_service/scripts/smoke_postgres_cutover_full.py": (
        "deployed-postgres",
        "credential_free_live_public_root_pass",
        "credential_free_live_static_bundle_pass",
        "postgres_visible_write_proof_pass",
        "concurrent_account_http_pass",
        "concurrent_thread_local_connections",
        "concurrent_runtime_probe_unique_connections",
        "ai_task_create_pass",
        "ai_task_delete_pass",
        "run-data-analysis-write",
        "data_analysis_write_pass",
        "data_analysis_record_id",
    ),
    "local_inspection_service/scripts/postgres_cutover_artifact_manifest.py": (
        "artifact_count",
        "sha256",
        "verify_manifest",
        "non_secret_manifest",
    ),
    "local_inspection_service/scripts/postgres_cutover_deploy_package.py": (
        "postgres-cutover-deploy-package",
        "create_package",
        "verify_package",
        "extract_package",
        "backup_existing_targets",
        "restore_package_backup",
        "backup_performed",
        "PACKAGE_MANIFEST_NAME",
        "non_secret_report",
    ),
    "local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py": (
        "postgres cutover deploy package smoke passed",
        "assert_package_round_trip_passes",
        "assert_package_rejects_unsafe_member",
    ),
    "local_inspection_service/scripts/postgres_cutover_gate_report.py": (
        "final_acceptance_pass",
        "deployed-postgres",
        "strict-final",
        "expected_concurrent_accounts",
        "import_engine_report",
        "code_deploy_report",
        "code_deploy_report_missing",
        "concurrent_postgres_visible_sessions",
        "concurrent_runtime_probe_unique_connections",
    ),
    "local_inspection_service/scripts/validate_postgres_migration_report.py": (
        "cutover_allowed",
        "postgres_import_artifacts",
        "schema_migrations",
        "row_counts",
    ),
    "local_inspection_service/scripts/postgres_import_row_count_report.py": (
        "row_count_parity_pass",
        "observed_counts",
        "psql",
        "schema_migrations",
    ),
    "local_inspection_service/scripts/smoke_postgres_schema_real_engine.py": (
        "single-user",
        "schema_migrations",
        "postgres-bin-dir",
    ),
    "local_inspection_service/scripts/smoke_postgres_import_real_engine.py": (
        "postgres-import-real-engine-smoke",
        "existing-migration-packet",
        "ddl_sha256",
        "migration_report_sha256",
    ),
    "local_inspection_service/scripts/validate_postgres_precutover_report.py": (
        "credential_free_live_public_root_pass",
        "credential_free_live_static_bundle_pass",
        "expected_store",
        "observed_store",
    ),
    "local_inspection_service/scripts/validate_postgres_full_smoke_report.py": (
        "concurrent_successful_sessions",
        "concurrent_postgres_visible_sessions",
        "concurrent_thread_local_connections",
        "concurrent_runtime_probe_unique_connections",
        "ai_task_create_pass",
        "ai_task_delete_pass",
        "data_analysis_write_pass",
        "data_analysis_write_skipped_reason",
        "postgres_visible_write_proof_pass",
    ),
    "local_inspection_service/scripts/smoke_postgres_endpoint_source_contract.py": (
        "postgres endpoint source contract",
        "REQUIRED_RUNTIME_ADAPTERS",
        "REQUIRED_RUNTIME_ENTRY_HELPERS",
        "REQUIRED_REPOSITORY_METHODS",
        "REQUIRED_TABLE_REFERENCES",
        "MIN_RUNTIME_REPOSITORY_ENTRY_CALLS",
        "runtime_store_probe_payload",
    ),
    "local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py": (
        "postgres-local-preflight-suite",
        "production_cutover_proof",
        "socket_free",
        "real_engine_required",
        "real_engine_pass",
        "local-fake-postgres",
        "require-real-engine",
        "postgres cutover deploy package",
    ),
    "local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py": (
        "postgres-local-preflight-suite",
        "validate_local_preflight_suite_report",
        "REQUIRED_RESULT_NAMES",
        "real_engine_required",
        "real_engine_pass",
        "postgres cutover deploy package",
    ),
    "local_inspection_service/scripts/smoke_postgres_local_preflight_suite_report_validator.py": (
        "missing real-engine requirement",
        "production_cutover_proof",
        "results missing required names",
        "forbidden marker",
    ),
    "local_inspection_service/docs/postgres-endpoint-integration-accepted.md": (
        "PostgreSQL-visible write evidence",
        "validate_postgres_full_smoke_report.py",
        "--import-engine-report",
        "--require-real-engine",
        "concurrent_postgres_visible_sessions=10",
    ),
    "local_inspection_service/docs/postgres-final-migration-cutover-execution-packet.md": (
        "--concurrent-accounts 10",
        "--import-engine-report",
        "import_real_engine.ddl_sha256",
        "full_smoke.concurrent_postgres_visible_sessions=10",
        "full_smoke.concurrent_runtime_probe_count=10",
        "full_smoke.concurrent_runtime_probe_connection_observations=<10-16-hex-ids-duplicates-allowed>",
        "ai_task_create_pass=true",
        "ai_task_delete_pass=true",
        "--run-data-analysis-write",
        "data_analysis_write_pass=true",
        "data_analysis_write_skipped_reason=<manager-approved reason>",
        "validate_postgres_full_smoke_report.py",
    ),
}

PRE_CUTOVER_FORBIDDEN_ENV = (
    "VANTALINE_DATA_STORE",
    "DATABASE_URL",
    "VANTALINE_SMOKE_USERNAME",
    "VANTALINE_SMOKE_PASSWORD",
    "TASK21_ADMIN_CREDENTIAL_FILE",
)

FORBIDDEN_REPORT_MARKERS = (
    "postgresql://",
    "DATABASE_URL=",
    "VANTALINE_SMOKE_PASSWORD=",
    "password=",
    "vantaline_session=",
)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def check_record(name: str, passed: bool, detail: str, *, blocking: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "blocking": bool(blocking),
        "detail": detail,
    }


def file_mode(path: Path) -> str:
    try:
        return stat.filemode(path.stat().st_mode)
    except OSError:
        return ""


def readable_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def missing_markers(path: Path, markers: tuple[str, ...]) -> list[str]:
    text = readable_text(path)
    return [marker for marker in markers if marker not in text]


def next_action_for(name: str) -> str:
    actions = {
        "app_root_exists": "run readiness on the production host or deploy /opt/vantaline/app",
        "target_python_executable": "restore /opt/vantaline/venv/bin/python before cutover",
        "required_artifacts_present": "deploy the accepted PostgreSQL endpoint-integration/cutover artifacts",
        "file_markers_present": "deploy the reviewed code/docs packet; current files do not match the cutover gate",
        "pre_cutover_process_env_clean": "clear PostgreSQL/smoke env from the current shell before pre-manager readiness",
        "postgres_env_file_absent": "remove or explicitly review existing /etc/vantaline/postgres.env before cutover",
        "psql_available": "install PostgreSQL client tooling or run on a host where psql is available",
        "systemctl_available": "run on a systemd production host before service cutover",
        "non_secret_report": "fix readiness report redaction before sharing",
    }
    return actions.get(name, f"resolve blocking readiness check: {name}")


def build_readiness_report(
    *,
    app_root: Path = DEFAULT_APP_ROOT,
    target_py: Path = DEFAULT_TARGET_PY,
    postgres_env_file: Path = DEFAULT_POSTGRES_ENV_FILE,
    service_name: str = DEFAULT_SERVICE_NAME,
    required_binaries: tuple[str, ...] = ("psql", "systemctl"),
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    app_root = app_root.resolve()
    target_py = target_py.resolve()
    postgres_env_file = postgres_env_file.resolve()

    checks.append(
        check_record(
            "app_root_exists",
            app_root.is_dir(),
            f"app_root={app_root}",
        )
    )
    checks.append(
        check_record(
            "target_python_executable",
            target_py.is_file() and os.access(target_py, os.X_OK),
            f"target_py={target_py} mode={file_mode(target_py)}",
        )
    )

    missing_files = [relative for relative in REQUIRED_RELATIVE_FILES if not (app_root / relative).is_file()]
    checks.append(
        check_record(
            "required_artifacts_present",
            not missing_files,
            "missing=" + ",".join(missing_files) if missing_files else f"count={len(REQUIRED_RELATIVE_FILES)}",
        )
    )

    marker_failures: list[str] = []
    for relative, markers in FILE_MARKERS.items():
        path = app_root / relative
        missing = missing_markers(path, markers)
        if missing:
            marker_failures.append(f"{relative}:{'|'.join(missing)}")
    checks.append(
        check_record(
            "file_markers_present",
            not marker_failures,
            "missing=" + ";".join(marker_failures) if marker_failures else f"files={len(FILE_MARKERS)}",
        )
    )

    present_env = [name for name in PRE_CUTOVER_FORBIDDEN_ENV if os.environ.get(name)]
    checks.append(
        check_record(
            "pre_cutover_process_env_clean",
            not present_env,
            "present=" + ",".join(present_env) if present_env else "no forbidden pre-cutover env names present",
        )
    )

    checks.append(
        check_record(
            "postgres_env_file_absent",
            not postgres_env_file.exists(),
            f"postgres_env_file={postgres_env_file} present={postgres_env_file.exists()}",
        )
    )

    for binary in required_binaries:
        path = shutil.which(binary)
        checks.append(
            check_record(
                f"{binary}_available",
                path is not None,
                f"{binary}={path or 'missing'}",
            )
        )

    failed_blockers = [item for item in checks if item["status"] != "pass" and item.get("blocking")]
    report: dict[str, Any] = {
        "mode": "postgres-cutover-readiness",
        "service": service_name,
        "app_root": str(app_root),
        "target_py": str(target_py),
        "postgres_env_file": str(postgres_env_file),
        "ready_for_manager_cutover_gate": not failed_blockers,
        "checks": checks,
        "blockers": [item["name"] for item in failed_blockers],
        "next_required_actions": [next_action_for(item["name"]) for item in failed_blockers],
        "non_secret_report": True,
    }
    report["non_secret_report"] = validate_non_secret_report(report)
    if not report["non_secret_report"]:
        report["ready_for_manager_cutover_gate"] = False
        if "non_secret_report" not in report["blockers"]:
            report["blockers"].append("non_secret_report")
            report["next_required_actions"].append(next_action_for("non_secret_report"))
    return report


def validate_non_secret_report(report: dict[str, Any]) -> bool:
    text = stable_json(report).lower()
    return not any(marker.lower() in text for marker in FORBIDDEN_REPORT_MARKERS)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    parser.add_argument("--target-py", default=str(DEFAULT_TARGET_PY))
    parser.add_argument("--postgres-env-file", default=str(DEFAULT_POSTGRES_ENV_FILE))
    parser.add_argument("--service", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--skip-host-binary-checks",
        action="store_true",
        help="Skip psql/systemctl availability checks; intended only for isolated unit smoke.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    required_binaries: tuple[str, ...] = () if args.skip_host_binary_checks else ("psql", "systemctl")
    report = build_readiness_report(
        app_root=Path(args.app_root),
        target_py=Path(args.target_py),
        postgres_env_file=Path(args.postgres_env_file),
        service_name=args.service,
        required_binaries=required_binaries,
    )
    output = stable_json(report) + "\n"
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if report["ready_for_manager_cutover_gate"]:
        print("postgres cutover readiness preflight passed")
        return 0
    print("postgres cutover readiness preflight failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
