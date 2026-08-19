#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.postgres_cutover_readiness import build_readiness_report  # noqa: E402


REQUIRED_FILE_CONTENT = {
    "local_inspection_service/server.py": (
        "build_runtime_repository\n"
        "runtime_store_probe_payload\n"
        "runtime_postgres_repository_or_none\n"
        "VANTALINE_DATA_STORE\n"
    ),
    "local_inspection_service/scripts/smoke_postgres_cutover_full.py": (
        "deployed-postgres\n"
        "credential_free_live_public_root_pass\n"
        "credential_free_live_static_bundle_pass\n"
        "postgres_visible_write_proof_pass\n"
        "concurrent_account_http_pass\n"
        "concurrent_thread_local_connections\n"
        "concurrent_runtime_probe_unique_connections\n"
        "ai_task_create_pass\n"
        "ai_task_delete_pass\n"
        "run-data-analysis-write\n"
        "data_analysis_write_pass\n"
        "data_analysis_record_id\n"
    ),
    "local_inspection_service/scripts/postgres_cutover_artifact_manifest.py": (
        "artifact_count\n"
        "sha256\n"
        "verify_manifest\n"
        "non_secret_manifest\n"
    ),
    "local_inspection_service/scripts/postgres_cutover_deploy_package.py": (
        "postgres-cutover-deploy-package\n"
        "create_package\n"
        "verify_package\n"
        "extract_package\n"
        "backup_existing_targets\n"
        "restore_package_backup\n"
        "backup_performed\n"
        "PACKAGE_MANIFEST_NAME\n"
        "non_secret_report\n"
    ),
    "local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py": (
        "postgres cutover deploy package smoke passed\n"
        "assert_package_round_trip_passes\n"
        "assert_package_rejects_unsafe_member\n"
    ),
    "local_inspection_service/scripts/postgres_cutover_gate_report.py": (
        "final_acceptance_pass\n"
        "deployed-postgres\n"
        "strict-final\n"
        "expected_concurrent_accounts\n"
        "import_engine_report\n"
        "code_deploy_report\n"
        "code_deploy_report_missing\n"
        "concurrent_postgres_visible_sessions\n"
        "concurrent_runtime_probe_unique_connections\n"
    ),
    "local_inspection_service/scripts/validate_postgres_migration_report.py": (
        "cutover_allowed\n"
        "postgres_import_artifacts\n"
        "schema_migrations\n"
        "row_counts\n"
    ),
    "local_inspection_service/scripts/migrate_json_to_sqlite.py": (
        "migrate json to sqlite fixture\n"
    ),
    "local_inspection_service/scripts/smoke_data_layer_migration.py": (
        "smoke data layer migration fixture\n"
    ),
    "local_inspection_service/scripts/postgres_import_row_count_report.py": (
        "row_count_parity_pass\n"
        "observed_counts\n"
        "psql\n"
        "schema_migrations\n"
    ),
    "local_inspection_service/scripts/smoke_postgres_schema_real_engine.py": (
        "single-user\n"
        "schema_migrations\n"
        "postgres-bin-dir\n"
    ),
    "local_inspection_service/scripts/smoke_postgres_import_real_engine.py": (
        "postgres-import-real-engine-smoke\n"
        "existing-migration-packet\n"
        "ddl_sha256\n"
        "migration_report_sha256\n"
    ),
    "local_inspection_service/scripts/validate_postgres_precutover_report.py": (
        "credential_free_live_public_root_pass\n"
        "credential_free_live_static_bundle_pass\n"
        "expected_store\n"
        "observed_store\n"
    ),
    "local_inspection_service/scripts/validate_postgres_full_smoke_report.py": (
        "concurrent_successful_sessions\n"
        "concurrent_postgres_visible_sessions\n"
        "concurrent_thread_local_connections\n"
        "concurrent_runtime_probe_unique_connections\n"
        "ai_task_create_pass\n"
        "ai_task_delete_pass\n"
        "data_analysis_write_pass\n"
        "data_analysis_write_skipped_reason\n"
        "postgres_visible_write_proof_pass\n"
    ),
    "local_inspection_service/scripts/smoke_postgres_endpoint_source_contract.py": (
        "postgres endpoint source contract\n"
        "REQUIRED_RUNTIME_ADAPTERS\n"
        "REQUIRED_RUNTIME_ENTRY_HELPERS\n"
        "REQUIRED_REPOSITORY_METHODS\n"
        "REQUIRED_TABLE_REFERENCES\n"
        "MIN_RUNTIME_REPOSITORY_ENTRY_CALLS\n"
        "runtime_store_probe_payload\n"
    ),
    "local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py": (
        "postgres-local-preflight-suite\n"
        "production_cutover_proof\n"
        "socket_free\n"
        "real_engine_required\n"
        "real_engine_pass\n"
        "local-fake-postgres\n"
        "require-real-engine\n"
        "postgres cutover deploy package\n"
    ),
    "local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py": (
        "postgres-local-preflight-suite\n"
        "validate_local_preflight_suite_report\n"
        "REQUIRED_RESULT_NAMES\n"
        "real_engine_required\n"
        "real_engine_pass\n"
        "postgres cutover deploy package\n"
    ),
    "local_inspection_service/scripts/smoke_postgres_local_preflight_suite_report_validator.py": (
        "missing real-engine requirement\n"
        "production_cutover_proof\n"
        "results missing required names\n"
        "forbidden marker\n"
    ),
    "local_inspection_service/scripts/prepare_json_to_postgres.py": "prepare\n",
    "local_inspection_service/storage/postgres_schema.py": "schema\n",
    "local_inspection_service/storage/runtime_selector.py": "selector\n",
    "local_inspection_service/storage/postgres_runtime_repository.py": "repository\n",
    "local_inspection_service/docs/postgres-endpoint-integration-accepted.md": (
        "PostgreSQL-visible write evidence\n"
        "validate_postgres_full_smoke_report.py\n"
        "--import-engine-report\n"
        "--require-real-engine\n"
        "concurrent_postgres_visible_sessions=10\n"
    ),
    "local_inspection_service/docs/postgres-final-migration-cutover-execution-packet.md": (
        "--concurrent-accounts 10\n"
        "--import-engine-report\n"
        "import_real_engine.ddl_sha256\n"
        "full_smoke.concurrent_postgres_visible_sessions=10\n"
        "full_smoke.concurrent_runtime_probe_count=10\n"
        "full_smoke.concurrent_runtime_probe_connection_observations=<10-16-hex-ids-duplicates-allowed>\n"
        "ai_task_create_pass=true\n"
        "ai_task_delete_pass=true\n"
        "--run-data-analysis-write\n"
        "data_analysis_write_pass=true\n"
        "data_analysis_write_skipped_reason=<manager-approved reason>\n"
        "validate_postgres_full_smoke_report.py\n"
    ),
}


def write_fixture_app(root: Path) -> None:
    for relative, content in REQUIRED_FILE_CONTENT.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def without_env(names: tuple[str, ...]) -> dict[str, str | None]:
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ.pop(name, None)
    return previous


def restore_env(previous: dict[str, str | None]) -> None:
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def assert_ready_report_passes() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_cutover_readiness_pass_"))
    app_root = temp_root / "app"
    target_py = temp_root / "venv" / "bin" / "python"
    postgres_env_file = temp_root / "etc" / "postgres.env"
    write_fixture_app(app_root)
    make_executable(target_py)
    previous_env = without_env(
        (
            "VANTALINE_DATA_STORE",
            "DATABASE_URL",
            "VANTALINE_SMOKE_USERNAME",
            "VANTALINE_SMOKE_PASSWORD",
            "TASK21_ADMIN_CREDENTIAL_FILE",
        )
    )
    try:
        report = build_readiness_report(
            app_root=app_root,
            target_py=target_py,
            postgres_env_file=postgres_env_file,
            required_binaries=(),
        )
    finally:
        restore_env(previous_env)
    if report.get("ready_for_manager_cutover_gate") is not True:
        raise AssertionError(f"expected ready report, got {report}")
    if report.get("blockers"):
        raise AssertionError(f"ready report should not include blockers: {report}")
    if report.get("non_secret_report") is not True:
        raise AssertionError(f"readiness report should be non-secret: {report}")


def assert_missing_artifacts_fail_closed() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_cutover_readiness_fail_"))
    app_root = temp_root / "app"
    target_py = temp_root / "venv" / "bin" / "python"
    postgres_env_file = temp_root / "etc" / "postgres.env"
    write_fixture_app(app_root)
    (app_root / "local_inspection_service/scripts/validate_postgres_full_smoke_report.py").unlink()
    make_executable(target_py)
    previous_env = without_env(
        (
            "VANTALINE_DATA_STORE",
            "DATABASE_URL",
            "VANTALINE_SMOKE_USERNAME",
            "VANTALINE_SMOKE_PASSWORD",
            "TASK21_ADMIN_CREDENTIAL_FILE",
        )
    )
    os.environ["DATABASE_URL"] = "postgresql://secret.invalid/vantaline"
    try:
        report = build_readiness_report(
            app_root=app_root,
            target_py=target_py,
            postgres_env_file=postgres_env_file,
            required_binaries=(),
        )
    finally:
        restore_env(previous_env)
    if report.get("ready_for_manager_cutover_gate") is not False:
        raise AssertionError(f"expected fail-closed report, got {report}")
    blockers = set(report.get("blockers") or [])
    if "required_artifacts_present" not in blockers:
        raise AssertionError(f"missing artifact blocker not reported: {report}")
    if "pre_cutover_process_env_clean" not in blockers:
        raise AssertionError(f"dirty env blocker not reported: {report}")
    if report.get("non_secret_report") is not True:
        raise AssertionError(f"readiness report should not echo secret env values: {report}")
    if "postgresql://secret.invalid" in str(report):
        raise AssertionError(f"readiness report leaked raw DATABASE_URL: {report}")


def main() -> None:
    assert_ready_report_passes()
    assert_missing_artifacts_fail_closed()
    print("postgres cutover readiness smoke passed")


if __name__ == "__main__":
    main()
