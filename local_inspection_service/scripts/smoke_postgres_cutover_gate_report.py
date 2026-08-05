#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.postgres_cutover_gate_report import (  # noqa: E402
    build_gate_report,
    load_json_report,
    report_sha256,
)
from local_inspection_service.scripts.validate_postgres_full_smoke_report import (  # noqa: E402
    CLEANUP_RESIDUAL_ROW_KEYS,
    REQUIRED_POSTGRES_CLEANUP_TABLES,
    REQUIRED_POSTGRES_READ_TABLES,
    REQUIRED_POSTGRES_WRITE_TABLES,
    REQUIRED_TRUE_FIELDS as FULL_REQUIRED_TRUE_FIELDS,
    REQUIRED_WRITE_COVERAGE_EXCEPTIONS,
)
from local_inspection_service.scripts.validate_postgres_precutover_report import (  # noqa: E402
    REQUIRED_ALLOWLIST_PATHS,
    REQUIRED_TRUE_FIELDS as PRECUTOVER_REQUIRED_TRUE_FIELDS,
)
from local_inspection_service.scripts.validate_postgres_local_preflight_suite_report import (  # noqa: E402
    REQUIRED_RESULT_NAMES as LOCAL_PREFLIGHT_REQUIRED_RESULT_NAMES,
)
from local_inspection_service.storage.schema import SCHEMA_VERSION, TABLES  # noqa: E402

SCRIPT_PATH = ROOT / "local_inspection_service" / "scripts" / "postgres_cutover_gate_report.py"
DUMMY_DDL_SHA256 = "a" * 64
DUMMY_MANIFEST_SHA256 = "c" * 64


ALLOWLIST = [
    {
        "method": "GET/POST",
        "path": path,
        "repository_method": "fetch_all",
        "read_write": "read/write",
        "transaction_boundary": "single request",
    }
    for path in REQUIRED_ALLOWLIST_PATHS
]


def artifact_report() -> dict[str, object]:
    return {
        "mode": "postgres-cutover-artifact-manifest-verify",
        "artifact_count": 40,
        "manifest_sha256": DUMMY_MANIFEST_SHA256,
        "verified": True,
        "failures": [],
        "non_secret_report": True,
    }


def readiness_report(*, ready: bool = True) -> dict[str, object]:
    return {
        "mode": "postgres-cutover-readiness",
        "ready_for_manager_cutover_gate": ready,
        "blockers": [] if ready else ["psql_available"],
        "next_required_actions": [] if ready else ["install PostgreSQL client tooling"],
        "non_secret_report": True,
    }


def code_deploy_report(*, passed: bool = True) -> dict[str, object]:
    return {
        "mode": "postgres-cutover-deploy-package-extract",
        "package_kind": "vantaline-postgres-cutover-deploy-package",
        "package_version": 1,
        "package_path": "/tmp/vantaline-postgres-cutover-deploy-package.tar.gz",
        "package_sha256": "b" * 64,
        "manifest_sha256": DUMMY_MANIFEST_SHA256,
        "app_root": "/opt/vantaline/app",
        "artifact_count": 40,
        "metadata_entries_written": [
            ".vantaline_postgres_cutover_package/manifest.json",
            ".vantaline_postgres_cutover_package/INSTALL.md",
            ".vantaline_postgres_cutover_package/sha256sums.txt",
        ],
        "backup_performed": passed,
        "backup_dir": "/opt/vantaline/backups/postgres-cutover-code-deploy/20260702000000",
        "backup_entry_count": 42 if passed else 0,
        "backup_manifest": "/opt/vantaline/backups/postgres-cutover-code-deploy/20260702000000/backup-manifest.json" if passed else "",
        "artifact_manifest_verified_after_extract": passed,
        "extracted": passed,
        "non_secret_report": True,
    }


def local_preflight_report(*, passed: bool = True) -> dict[str, object]:
    results = [
        {"name": name, "required": True, "status": "pass"}
        for name in sorted(LOCAL_PREFLIGHT_REQUIRED_RESULT_NAMES)
    ]
    if not passed:
        for item in results:
            if item.get("name") == "postgres import real-engine":
                item["status"] = "fail"
                break
    return {
        "mode": "postgres-local-preflight-suite",
        "production_cutover_proof": False,
        "socket_free": True,
        "real_engine_required": True,
        "real_engine_pass": passed,
        "service_restart_performed": False,
        "postgres_service_mutation_performed": False,
        "runtime_env_switch_performed": False,
        "required_pass": passed,
        "failed_required": [] if passed else ["postgres import row-count report"],
        "result_count": len(results),
        "results": results,
        "non_secret_report": True,
    }


def migration_report() -> dict[str, object]:
    row_counts = {table.name: 0 for table in TABLES}
    row_counts.update({"schema_migrations": 1, "users": 2, "auth_sessions": 1, "audit_events": 1})
    return {
        "report_version": 1,
        "schema_version": SCHEMA_VERSION,
        "target": "postgresql",
        "postgres_schema": "vantaline",
        "ddl_sha256": DUMMY_DDL_SHA256,
        "row_counts": row_counts,
        "source_errors": [],
        "source_error_count": 0,
        "blocking_errors": [],
        "blocking_error_counts": {},
        "postgres_import_artifacts": {
            "emitted": True,
            "import_dir": "/tmp/vantaline_import",
            "load_sql_path": "/tmp/vantaline_import/load_postgres.sql",
            "csv_files": {
                table.name: f"/tmp/vantaline_import/tables/{table.name}.csv"
                for table in TABLES
                if table.name != "schema_migrations"
            },
        },
        "cutover_allowed": True,
        "security_policy": {
            "reports": "raw session tokens, password verifier values, provider keys, and local env contents are omitted",
        },
    }


def row_count_report(*, parity: bool = True) -> dict[str, object]:
    return {
        "mode": "postgres-import-row-count-report",
        "migration_schema_version": SCHEMA_VERSION,
        "postgres_schema": "vantaline",
        "migration_cutover_allowed": True,
        "checked_table_count": len(TABLES),
        "row_count_parity_pass": parity,
        "mismatches": [] if parity else [{"table": "users", "expected": 2, "observed": 3}],
        "schema_migrations_expected": 1,
        "schema_migrations_observed": 1,
        "non_secret_report": True,
    }


def import_engine_report(*, passed: bool = True) -> dict[str, object]:
    return {
        "mode": "postgres-import-real-engine-smoke",
        "postgres_engine": "single-user",
        "artifact_source": "existing-migration-packet",
        "migration_schema_version": SCHEMA_VERSION,
        "migration_report_sha256": report_sha256(migration_report()),
        "ddl_sha256": DUMMY_DDL_SHA256,
        "ddl_real_engine_pass": passed,
        "csv_import_real_engine_pass": passed,
        "row_count_parity_pass": passed,
        "checked_table_count": len(TABLES),
        "non_secret_report": True,
    }


def precutover_report(*, mode: str = "deployed-precutover") -> dict[str, object]:
    report: dict[str, object] = {
        "mode": mode,
        "base_url": "http://127.0.0.1:8765",
        "expected_store": "json",
        "observed_store": "json",
        "endpoint_allowlist": ALLOWLIST,
        "notes": ["does not prove authenticated routes; final full smoke covers those routes"],
    }
    for field in PRECUTOVER_REQUIRED_TRUE_FIELDS:
        report[field] = True
    return report


def full_smoke_report(
    *,
    mode: str = "deployed-postgres",
    count: int = 10,
    unique_connections: int | None = None,
) -> dict[str, object]:
    base_url = "http://127.0.0.1:8765" if mode == "deployed-postgres" else "http://127.0.0.1:45678"
    if unique_connections is None:
        unique_connections = count
    connection_ids = [f"{index + 1:016x}" for index in range(unique_connections)]
    connection_observations = [
        connection_ids[index % unique_connections]
        for index in range(count)
    ]
    report: dict[str, object] = {
        "mode": mode,
        "base_url": base_url,
        "expected_store": "postgres",
        "credential_source": "runtime_file",
        "runtime_env": {
            "data_store_env_name": "VANTALINE_DATA_STORE",
            "data_store_env_value": "postgres",
            "db_url_env_name": "DATABASE_URL",
            "db_url_present": True,
        },
        "auth_json_token_read": False,
        "runtime_probe": {
            "store": "postgres",
            "repository_kind": "postgres",
            "json_fallback_used": False,
            "repository_connection_scope": "thread-local",
            "repository_connection_id": "1234567890abcdef",
            "postgres_count_probe": {"schema_migrations": 1},
        },
        "concurrent_account_count": count,
        "concurrent_successful_sessions": count,
        "concurrent_postgres_visible_sessions": count,
        "concurrent_worker_threads": count,
        "concurrent_thread_local_connections": unique_connections,
        "concurrent_runtime_probe_count": count,
        "concurrent_runtime_probe_unique_connections": unique_connections,
        "concurrent_runtime_probe_connection_observations": connection_observations,
        "concurrent_runtime_probe_connection_ids": connection_ids,
        "concurrent_runtime_probe_connection_reuse_observed": unique_connections < count,
        "disposable_ids": {
            "accessory_id": "acc_gate123",
            "candidate_id": "cand_gate123",
            "ai_task_id": "aitask_gate123",
            "data_analysis_record_id": "analysis_gate123",
            "pipeline_task_id": "pipe_gate123",
        },
        "data_analysis_write_pass": True,
        "read_only_write_waiver_id": "contract-read-only-write-waiver",
        "read_only_write_waiver_required": True,
        "write_coverage_exceptions": {
            table_name: f"{table_name} read-only-only write coverage waiver"
            for table_name in REQUIRED_WRITE_COVERAGE_EXCEPTIONS
            if table_name != "data_analysis_records"
        },
        "cleanup_residual_rows": {key: 0 for key in CLEANUP_RESIDUAL_ROW_KEYS},
        "schema_migration_versions": [SCHEMA_VERSION],
        "endpoint_allowlist": ALLOWLIST,
        "postgres_visible_read_tables": {table: 0 for table in REQUIRED_POSTGRES_READ_TABLES},
        "postgres_visible_write_tables": {table: True for table in REQUIRED_POSTGRES_WRITE_TABLES},
        "postgres_visible_cleanup_tables": {table: True for table in REQUIRED_POSTGRES_CLEANUP_TABLES},
    }
    write_tables = report["postgres_visible_write_tables"]
    cleanup_tables = report["postgres_visible_cleanup_tables"]
    if isinstance(write_tables, dict):
        write_tables["data_analysis_records"] = True
    if isinstance(cleanup_tables, dict):
        cleanup_tables["data_analysis_records"] = True
    for field in FULL_REQUIRED_TRUE_FIELDS:
        report[field] = True
    return report


def gate_report(
    *,
    artifact: dict[str, object] | None = None,
    readiness: dict[str, object] | None = None,
    local_preflight: dict[str, object] | None = None,
    migration: dict[str, object] | None = None,
    row_counts: dict[str, object] | None = None,
    import_engine: dict[str, object] | None = None,
    code_deploy: dict[str, object] | None = None,
    precutover: dict[str, object] | None = None,
    full: dict[str, object] | None = None,
    artifact_status: str = "loaded",
    readiness_status: str = "loaded",
    local_preflight_status: str = "loaded",
    migration_status: str = "loaded",
    row_count_status: str = "loaded",
    import_engine_status: str = "loaded",
    code_deploy_status: str = "loaded",
    precutover_status: str = "loaded",
    full_status: str = "loaded",
    expected_concurrent_accounts: int = 10,
) -> dict[str, object]:
    if code_deploy is None and code_deploy_status == "loaded":
        code_deploy = code_deploy_report()
    return build_gate_report(
        artifact_report=artifact,
        artifact_load_status=artifact_status,
        readiness_report=readiness,
        readiness_load_status=readiness_status,
        code_deploy_report=code_deploy,
        code_deploy_load_status=code_deploy_status,
        local_preflight_report=local_preflight,
        local_preflight_load_status=local_preflight_status,
        migration_report=migration,
        migration_load_status=migration_status,
        row_count_report=row_counts,
        row_count_load_status=row_count_status,
        import_engine_report=import_engine,
        import_engine_load_status=import_engine_status,
        precutover_report=precutover,
        precutover_load_status=precutover_status,
        full_smoke_report=full,
        full_smoke_load_status=full_status,
        expected_concurrent_accounts=expected_concurrent_accounts,
    )


def assert_production_gate_passes() -> None:
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        code_deploy=code_deploy_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not True:
        raise AssertionError(f"expected production gate to pass: {report}")
    if report.get("production_cutover_evidence_pass") is not True:
        raise AssertionError(f"expected production cutover evidence to pass: {report}")
    if report.get("blockers"):
        raise AssertionError(f"production gate should not include blockers: {report}")
    full_smoke = report.get("full_smoke")
    if not isinstance(full_smoke, dict):
        raise AssertionError(f"production gate should include full_smoke evidence: {report}")
    if full_smoke.get("base_url") != "http://127.0.0.1:8765":
        raise AssertionError(f"production gate should surface the reviewed service base URL: {report}")
    runtime_probe = full_smoke.get("runtime_probe")
    if not isinstance(runtime_probe, dict) or runtime_probe.get("store") != "postgres":
        raise AssertionError(f"production gate should surface PostgreSQL runtime probe evidence: {report}")
    runtime_env = full_smoke.get("runtime_env")
    if not isinstance(runtime_env, dict) or runtime_env.get("data_store_env_value") != "postgres":
        raise AssertionError(f"production gate should surface PostgreSQL runtime env evidence: {report}")
    if full_smoke.get("schema_migration_versions") != [SCHEMA_VERSION]:
        raise AssertionError(f"production gate should surface PostgreSQL schema version evidence: {report}")
    residuals = full_smoke.get("cleanup_residual_rows")
    if not isinstance(residuals, dict) or any(value != 0 for value in residuals.values()):
        raise AssertionError(f"production gate should surface zero cleanup residual evidence: {report}")
    connection_observations = full_smoke.get("concurrent_runtime_probe_connection_observations")
    if not isinstance(connection_observations, list) or len(connection_observations) != 10:
        raise AssertionError(f"production gate should surface 10 runtime probe observations: {report}")
    connection_ids = full_smoke.get("concurrent_runtime_probe_connection_ids")
    if not isinstance(connection_ids, list) or not (1 <= len(set(connection_ids)) <= 10):
        raise AssertionError(f"production gate should surface valid concurrent runtime probe connection ids: {report}")

    reused_report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        code_deploy=code_deploy_report(),
        precutover=precutover_report(),
        full=full_smoke_report(unique_connections=5),
    )
    if reused_report.get("final_acceptance_pass") is not True:
        raise AssertionError(f"expected production gate to accept observed connection reuse: {reused_report}")


def assert_contract_gate_does_not_pass_final() -> None:
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        code_deploy=code_deploy_report(),
        precutover=precutover_report(mode="deployed-precutover-contract"),
        full=full_smoke_report(mode="deployed-postgres-contract"),
    )
    blockers = set(report.get("blockers") or [])
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"contract gate must not pass final acceptance: {report}")
    if "precutover_contract_not_production" not in blockers:
        raise AssertionError(f"missing precutover contract blocker: {report}")
    if "full_smoke_contract_not_production" not in blockers:
        raise AssertionError(f"missing full-smoke contract blocker: {report}")


def assert_readiness_failure_blocks_final() -> None:
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(ready=False),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        code_deploy=code_deploy_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"readiness failure must block final acceptance: {report}")
    if "readiness_report_failed" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing readiness blocker: {report}")


def assert_code_deploy_missing_blocks_final() -> None:
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        code_deploy=None,
        code_deploy_status="missing",
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"missing code deploy report must block final acceptance: {report}")
    if "code_deploy_report_missing" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing code deploy blocker: {report}")


def assert_code_deploy_without_backup_blocks_final() -> None:
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        code_deploy=code_deploy_report(passed=False),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"code deploy without backup must block final acceptance: {report}")
    if "code_deploy_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing invalid code deploy blocker: {report}")


def assert_code_deploy_weak_metadata_blocks_final() -> None:
    weak_report = code_deploy_report()
    weak_report["metadata_entries_written"] = [
        ".vantaline_postgres_cutover_package/manifest.json",
    ]
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        code_deploy=weak_report,
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"code deploy with weak metadata must block final acceptance: {report}")
    if "code_deploy_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing weak metadata code deploy blocker: {report}")


def assert_code_deploy_bad_sha_blocks_final() -> None:
    weak_report = code_deploy_report()
    weak_report["package_sha256"] = "not-a-sha"
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        code_deploy=weak_report,
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"code deploy with bad package sha must block final acceptance: {report}")
    if "code_deploy_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing bad sha code deploy blocker: {report}")


def assert_code_deploy_bad_manifest_sha_blocks_final() -> None:
    weak_report = code_deploy_report()
    weak_report["manifest_sha256"] = "not-a-sha"
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        code_deploy=weak_report,
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"code deploy with bad manifest sha must block final acceptance: {report}")
    if "code_deploy_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing bad manifest sha code deploy blocker: {report}")


def assert_code_deploy_manifest_mismatch_blocks_final() -> None:
    weak_report = code_deploy_report()
    weak_report["manifest_sha256"] = "d" * 64
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        code_deploy=weak_report,
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"code deploy manifest mismatch must block final acceptance: {report}")
    if "code_deploy_manifest_mismatch" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing manifest mismatch code deploy blocker: {report}")


def assert_code_deploy_artifact_count_mismatch_blocks_final() -> None:
    weak_report = code_deploy_report()
    weak_report["artifact_count"] = 39
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        code_deploy=weak_report,
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"code deploy artifact count mismatch must block final acceptance: {report}")
    if "code_deploy_artifact_count_mismatch" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing artifact count mismatch code deploy blocker: {report}")


def assert_local_preflight_failure_blocks_final() -> None:
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(passed=False),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"local preflight failure must block final acceptance: {report}")
    if "local_preflight_suite_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing local preflight blocker: {report}")


def assert_local_preflight_without_required_real_engine_blocks_final() -> None:
    local_report = local_preflight_report()
    local_report["real_engine_required"] = False
    local_report["real_engine_pass"] = True
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_report,
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"local preflight without required real-engine must block final acceptance: {report}")
    if "local_preflight_suite_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing local preflight real-engine-required blocker: {report}")


def assert_row_count_failure_blocks_final() -> None:
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(parity=False),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"row count mismatch must block final acceptance: {report}")
    if "row_count_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing row-count blocker: {report}")


def assert_missing_full_smoke_allowlist_blocks_final() -> None:
    full_report = full_smoke_report()
    full_report["endpoint_allowlist"] = [
        item for item in ALLOWLIST if item["path"] != "/api/pipeline/tasks*"
    ]
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_report,
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"missing full-smoke allowlist path must block final acceptance: {report}")
    if "full_smoke_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing full-smoke allowlist blocker: {report}")


def assert_missing_full_smoke_table_evidence_blocks_final() -> None:
    full_report = full_smoke_report()
    full_report["postgres_visible_write_tables"] = {"users": True, "auth_sessions": True, "accessories": True}
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_report,
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"missing table evidence must block final acceptance: {report}")
    if "full_smoke_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing table evidence blocker: {report}")


def assert_bad_concurrent_evidence_blocks_final() -> None:
    concurrent_failures: list[tuple[str, object]] = [
        ("concurrent_successful_sessions", 9),
        ("concurrent_postgres_visible_sessions", 9),
        ("concurrent_worker_threads", 9),
        ("concurrent_thread_local_connections", 9),
        ("concurrent_runtime_probe_unique_connections", 9),
        ("concurrent_runtime_probe_connection_ids", [f"{index + 1:016x}" for index in range(9)]),
        ("concurrent_runtime_probe_connection_ids", ["0000000000000001"] * 10),
    ]
    for field_name, bad_value in concurrent_failures:
        full_report = full_smoke_report()
        full_report[field_name] = bad_value
        report = gate_report(
            artifact=artifact_report(),
            readiness=readiness_report(),
            local_preflight=local_preflight_report(),
            migration=migration_report(),
            row_counts=row_count_report(),
            import_engine=import_engine_report(),
            precutover=precutover_report(),
            full=full_report,
        )
        if report.get("final_acceptance_pass") is not False:
            raise AssertionError(f"bad concurrent evidence must block final acceptance for {field_name}: {report}")
        if "full_smoke_report_invalid" not in set(report.get("blockers") or []):
            raise AssertionError(f"bad concurrent evidence missed full-smoke blocker for {field_name}: {report}")


def assert_strict_expected_concurrent_accounts_blocks_final() -> None:
    full_report = full_smoke_report(count=10)
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_report,
        expected_concurrent_accounts=11,
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"strict expected concurrent account count must block final acceptance: {report}")
    if "full_smoke_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing strict concurrent count full-smoke blocker: {report}")


def assert_missing_write_waiver_blocks_final() -> None:
    full_report = full_smoke_report()
    full_report.pop("read_only_write_waiver_id", None)
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_report,
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"missing read-only write waiver must block final acceptance: {report}")
    if "full_smoke_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing read-only write waiver blocker: {report}")


def assert_secret_markers_do_not_leak() -> None:
    artifact = artifact_report()
    artifact["note"] = "DATABASE_URL=redacted"
    report = gate_report(
        artifact=artifact,
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"secret marker input must block final acceptance: {report}")
    serialized = json.dumps(report, sort_keys=True)
    if "DATABASE_URL=" in serialized:
        raise AssertionError(f"gate report leaked forbidden marker: {report}")
    if report.get("non_secret_report") is not True:
        raise AssertionError(f"gate report should remain shareable after sanitizing input: {report}")


def assert_import_engine_failure_blocks_final() -> None:
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_engine_report(passed=False),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"real-engine import failure must block final acceptance: {report}")
    if "import_engine_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing real-engine import blocker: {report}")


def assert_fixture_import_engine_report_blocks_final() -> None:
    fixture_report = import_engine_report()
    fixture_report["artifact_source"] = "fixture-migration-packet"
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=fixture_report,
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"fixture import-engine report must not pass final acceptance: {report}")
    if "import_engine_report_invalid" not in set(report.get("blockers") or []):
        raise AssertionError(f"fixture import-engine report did not block final acceptance: {report}")


def assert_cross_report_schema_mismatch_blocks_final() -> None:
    import_report = import_engine_report()
    import_report["migration_schema_version"] = "different_schema_version"
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_report,
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    blockers = set(report.get("blockers") or [])
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"schema mismatch must block final acceptance: {report}")
    if "import_engine_schema_mismatch" not in blockers:
        raise AssertionError(f"missing import-engine schema mismatch blocker: {report}")

    row_report = row_count_report()
    row_report["migration_schema_version"] = "different_schema_version"
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_report,
        import_engine=import_engine_report(),
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    blockers = set(report.get("blockers") or [])
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"row-count schema mismatch must block final acceptance: {report}")
    if "row_count_schema_mismatch" not in blockers:
        raise AssertionError(f"missing row-count schema mismatch blocker: {report}")


def assert_import_engine_report_hash_mismatch_blocks_final() -> None:
    import_report = import_engine_report()
    import_report["migration_report_sha256"] = "0" * 64
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_report,
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"migration report hash mismatch must block final acceptance: {report}")
    if "import_engine_report_mismatch" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing import-engine report-hash blocker: {report}")


def assert_import_engine_ddl_hash_mismatch_blocks_final() -> None:
    import_report = import_engine_report()
    import_report["ddl_sha256"] = "0" * 64
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_report,
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"DDL hash mismatch must block final acceptance: {report}")
    if "import_engine_ddl_mismatch" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing import-engine DDL-hash blocker: {report}")


def assert_import_engine_table_count_mismatch_blocks_final() -> None:
    import_report = import_engine_report()
    import_report["checked_table_count"] = len(TABLES) - 1
    report = gate_report(
        artifact=artifact_report(),
        readiness=readiness_report(),
        local_preflight=local_preflight_report(),
        migration=migration_report(),
        row_counts=row_count_report(),
        import_engine=import_report,
        precutover=precutover_report(),
        full=full_smoke_report(),
    )
    if report.get("final_acceptance_pass") is not False:
        raise AssertionError(f"import-engine table count mismatch must block final acceptance: {report}")
    if "import_engine_table_count_mismatch" not in set(report.get("blockers") or []):
        raise AssertionError(f"missing import-engine table-count blocker: {report}")


def assert_file_loading_path_works() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_cutover_gate_report_"))
    path = temp_root / "artifact.json"
    path.write_text(json.dumps(artifact_report(), sort_keys=True), encoding="utf-8")
    loaded, status = load_json_report(path)
    if status != "loaded" or loaded is None:
        raise AssertionError(f"expected report file to load, got status={status}")
    missing, missing_status = load_json_report(temp_root / "missing.json")
    if missing is not None or missing_status != "missing":
        raise AssertionError(f"expected missing report status, got {missing_status}")


def write_report(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def assert_cli_consumes_import_engine_report() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_cutover_gate_cli_"))
    artifact_path = temp_root / "artifact.json"
    readiness_path = temp_root / "readiness.json"
    code_deploy_path = temp_root / "code-deploy.json"
    local_preflight_path = temp_root / "local-preflight.json"
    migration_path = temp_root / "migration.json"
    row_count_path = temp_root / "row-count.json"
    import_engine_path = temp_root / "import-engine.json"
    precutover_path = temp_root / "precutover.json"
    full_path = temp_root / "full.json"
    final_report_path = temp_root / "final.json"

    write_report(artifact_path, artifact_report())
    write_report(readiness_path, readiness_report())
    write_report(code_deploy_path, code_deploy_report())
    write_report(local_preflight_path, local_preflight_report())
    write_report(migration_path, migration_report())
    write_report(row_count_path, row_count_report())
    write_report(import_engine_path, import_engine_report())
    write_report(precutover_path, precutover_report())
    write_report(full_path, full_smoke_report())

    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--artifact-verify-report",
        str(artifact_path),
        "--readiness-report",
        str(readiness_path),
        "--deploy-package-extract-report",
        str(code_deploy_path),
        "--local-preflight-suite-report",
        str(local_preflight_path),
        "--migration-report",
        str(migration_path),
        "--row-count-report",
        str(row_count_path),
        "--import-engine-report",
        str(import_engine_path),
        "--precutover-report",
        str(precutover_path),
        "--full-smoke-report",
        str(full_path),
        "--expected-concurrent-accounts",
        "10",
        "--report",
        str(final_report_path),
        "--strict-final",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"gate report CLI should pass with import-engine report: {result.stdout}\n{result.stderr}")
    final_report = json.loads(final_report_path.read_text(encoding="utf-8"))
    if final_report.get("final_acceptance_pass") is not True:
        raise AssertionError(f"gate report CLI did not pass final acceptance: {final_report}")
    if (final_report.get("import_real_engine") or {}).get("passed") is not True:
        raise AssertionError(f"gate report CLI did not consume import-engine report: {final_report}")
    if (final_report.get("local_preflight_suite") or {}).get("passed") is not True:
        raise AssertionError(f"gate report CLI did not consume local preflight report: {final_report}")

    missing_local_preflight_output_path = temp_root / "missing-local-preflight-final.json"
    missing_local_preflight_command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--artifact-verify-report",
        str(artifact_path),
        "--readiness-report",
        str(readiness_path),
        "--deploy-package-extract-report",
        str(code_deploy_path),
        "--migration-report",
        str(migration_path),
        "--row-count-report",
        str(row_count_path),
        "--import-engine-report",
        str(import_engine_path),
        "--precutover-report",
        str(precutover_path),
        "--full-smoke-report",
        str(full_path),
        "--expected-concurrent-accounts",
        "10",
        "--report",
        str(missing_local_preflight_output_path),
        "--strict-final",
    ]
    missing_local_preflight_result = subprocess.run(
        missing_local_preflight_command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if missing_local_preflight_result.returncode == 0:
        raise AssertionError("gate report CLI should fail strict-final without local preflight suite report")
    missing_local_preflight_report = json.loads(missing_local_preflight_output_path.read_text(encoding="utf-8"))
    if "local_preflight_suite_missing" not in set(missing_local_preflight_report.get("blockers") or []):
        raise AssertionError(f"missing local preflight report did not block final acceptance: {missing_local_preflight_report}")

    missing_output_path = temp_root / "missing-import-engine-final.json"
    missing_command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--artifact-verify-report",
        str(artifact_path),
        "--readiness-report",
        str(readiness_path),
        "--deploy-package-extract-report",
        str(code_deploy_path),
        "--local-preflight-suite-report",
        str(local_preflight_path),
        "--migration-report",
        str(migration_path),
        "--row-count-report",
        str(row_count_path),
        "--precutover-report",
        str(precutover_path),
        "--full-smoke-report",
        str(full_path),
        "--expected-concurrent-accounts",
        "10",
        "--report",
        str(missing_output_path),
        "--strict-final",
    ]
    missing_result = subprocess.run(missing_command, cwd=ROOT, text=True, capture_output=True, check=False)
    if missing_result.returncode == 0:
        raise AssertionError("gate report CLI should fail strict-final without import-engine report")
    missing_report = json.loads(missing_output_path.read_text(encoding="utf-8"))
    if "import_engine_report_missing" not in set(missing_report.get("blockers") or []):
        raise AssertionError(f"missing import-engine report did not block final acceptance: {missing_report}")


def main() -> None:
    assert_production_gate_passes()
    assert_contract_gate_does_not_pass_final()
    assert_readiness_failure_blocks_final()
    assert_code_deploy_missing_blocks_final()
    assert_code_deploy_without_backup_blocks_final()
    assert_code_deploy_weak_metadata_blocks_final()
    assert_code_deploy_bad_sha_blocks_final()
    assert_code_deploy_bad_manifest_sha_blocks_final()
    assert_code_deploy_manifest_mismatch_blocks_final()
    assert_code_deploy_artifact_count_mismatch_blocks_final()
    assert_local_preflight_failure_blocks_final()
    assert_local_preflight_without_required_real_engine_blocks_final()
    assert_row_count_failure_blocks_final()
    assert_missing_full_smoke_allowlist_blocks_final()
    assert_missing_full_smoke_table_evidence_blocks_final()
    assert_bad_concurrent_evidence_blocks_final()
    assert_strict_expected_concurrent_accounts_blocks_final()
    assert_missing_write_waiver_blocks_final()
    assert_secret_markers_do_not_leak()
    assert_import_engine_failure_blocks_final()
    assert_fixture_import_engine_report_blocks_final()
    assert_cross_report_schema_mismatch_blocks_final()
    assert_import_engine_report_hash_mismatch_blocks_final()
    assert_import_engine_ddl_hash_mismatch_blocks_final()
    assert_import_engine_table_count_mismatch_blocks_final()
    assert_file_loading_path_works()
    assert_cli_consumes_import_engine_report()
    print("postgres cutover gate report smoke passed")


if __name__ == "__main__":
    main()
