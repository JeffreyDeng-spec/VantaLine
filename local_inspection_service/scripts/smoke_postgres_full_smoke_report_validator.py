#!/usr/bin/env python3
"""Smoke-test the final PostgreSQL full-smoke report validator.

This smoke is intentionally socket-free. It does not replace the deployed
HTTP smoke; it guards the report contract that the deployed smoke must satisfy.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.validate_postgres_full_smoke_report import (  # noqa: E402
    REQUIRED_ALLOWLIST_PATHS,
    REQUIRED_POSTGRES_CLEANUP_TABLES,
    REQUIRED_POSTGRES_READ_TABLES,
    REQUIRED_POSTGRES_WRITE_TABLES,
    REQUIRED_TRUE_FIELDS,
    REQUIRED_WRITE_COVERAGE_EXCEPTIONS,
    CLEANUP_RESIDUAL_ROW_KEYS,
    ReportValidationError,
    validate_final_report,
)
from local_inspection_service.storage.schema import SCHEMA_VERSION  # noqa: E402


def valid_report(
    *,
    mode: str = "deployed-postgres",
    concurrent_accounts: int = 10,
    unique_connections: int | None = None,
    data_analysis_write: bool = True,
) -> dict[str, object]:
    if unique_connections is None:
        unique_connections = concurrent_accounts
    connection_ids = [f"{index + 1:016x}" for index in range(unique_connections)]
    connection_observations = [
        connection_ids[index % unique_connections]
        for index in range(concurrent_accounts)
    ]
    write_exceptions = {
        table_name: f"{table_name} read-only-only write coverage waiver"
        for table_name in REQUIRED_WRITE_COVERAGE_EXCEPTIONS
    }
    if not data_analysis_write:
        write_exceptions["data_analysis_records"] = "data-analysis write probe disabled by manager gate"
    base_url = "http://127.0.0.1:8765" if mode == "deployed-postgres" else "http://127.0.0.1:45678"
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
        "concurrent_account_count": concurrent_accounts,
        "concurrent_successful_sessions": concurrent_accounts,
        "concurrent_postgres_visible_sessions": concurrent_accounts,
        "concurrent_worker_threads": concurrent_accounts,
        "concurrent_thread_local_connections": unique_connections,
        "concurrent_runtime_probe_count": concurrent_accounts,
        "concurrent_runtime_probe_unique_connections": unique_connections,
        "concurrent_runtime_probe_connection_observations": connection_observations,
        "concurrent_runtime_probe_connection_ids": connection_ids,
        "concurrent_runtime_probe_connection_reuse_observed": unique_connections < concurrent_accounts,
        "disposable_ids": {
            "accessory_id": "acc_validator123",
            "candidate_id": "cand_validator123",
            "ai_task_id": "aitask_validator123",
            "data_analysis_record_id": "analysis_validator123",
            "pipeline_task_id": "pipe_validator123",
        },
        "data_analysis_write_pass": data_analysis_write,
        "read_only_write_waiver_id": "validator-waiver-123",
        "read_only_write_waiver_required": True,
        "write_coverage_exceptions": write_exceptions,
        "cleanup_residual_rows": {key: 0 for key in CLEANUP_RESIDUAL_ROW_KEYS},
        "schema_migration_versions": [SCHEMA_VERSION],
        "endpoint_allowlist": [
            {
                "method": "GET/POST",
                "path": path,
                "repository_method": "fetch_all",
                "read_write": "read/write",
                "transaction_boundary": "single request",
            }
            for path in REQUIRED_ALLOWLIST_PATHS
        ],
        "postgres_visible_read_tables": {table: 0 for table in REQUIRED_POSTGRES_READ_TABLES},
        "postgres_visible_write_tables": {table: True for table in REQUIRED_POSTGRES_WRITE_TABLES},
        "postgres_visible_cleanup_tables": {table: True for table in REQUIRED_POSTGRES_CLEANUP_TABLES},
    }
    if data_analysis_write:
        write_exceptions.pop("data_analysis_records", None)
        write_tables = report["postgres_visible_write_tables"]
        cleanup_tables = report["postgres_visible_cleanup_tables"]
        if isinstance(write_tables, dict):
            write_tables["data_analysis_records"] = True
        if isinstance(cleanup_tables, dict):
            cleanup_tables["data_analysis_records"] = True
    else:
        report.pop("data_analysis_write_pass", None)
        report["data_analysis_write_skipped_reason"] = "data-analysis write probe disabled by manager gate"
        disposable_ids = report["disposable_ids"]
        if isinstance(disposable_ids, dict):
            disposable_ids.pop("data_analysis_record_id", None)
    for field in REQUIRED_TRUE_FIELDS:
        report[field] = True
    return report


def assert_validator_passes() -> None:
    validate_final_report(valid_report(), expected_mode="deployed-postgres", expected_concurrent_accounts=10)
    validate_final_report(
        valid_report(unique_connections=5),
        expected_mode="deployed-postgres",
        expected_concurrent_accounts=10,
    )
    validate_final_report(
        valid_report(mode="deployed-postgres-contract"),
        expected_mode="deployed-postgres-contract",
        expected_concurrent_accounts=10,
    )
    validate_final_report(
        valid_report(data_analysis_write=False),
        expected_mode="deployed-postgres",
        expected_concurrent_accounts=10,
    )


def assert_rejects(label: str, report: dict[str, object], expected_fragment: str) -> None:
    try:
        validate_final_report(report, expected_mode="", expected_concurrent_accounts=10)
    except ReportValidationError as exc:
        if expected_fragment not in str(exc):
            raise AssertionError(f"{label}: unexpected validation error: {exc}") from exc
        return
    raise AssertionError(f"{label}: validator unexpectedly accepted invalid report")


def assert_validator_rejects_missing_concurrency_evidence() -> None:
    report = valid_report()
    report.pop("concurrent_postgres_visible_sessions", None)
    assert_rejects("missing PostgreSQL-visible sessions", report, "concurrent_postgres_visible_sessions")

    report = valid_report()
    report["concurrent_postgres_visible_sessions"] = 9
    assert_rejects("short PostgreSQL-visible sessions", report, "concurrent_postgres_visible_sessions")

    report = valid_report()
    report.pop("concurrent_thread_local_connections", None)
    assert_rejects("missing thread-local connections", report, "concurrent_thread_local_connections")

    report = valid_report()
    report.pop("concurrent_runtime_probe_connection_observations", None)
    assert_rejects("missing runtime probe observations", report, "concurrent_runtime_probe_connection_observations")

    report = valid_report(unique_connections=5)
    report["concurrent_runtime_probe_connection_reuse_observed"] = False
    assert_rejects("wrong runtime probe reuse flag", report, "concurrent_runtime_probe_connection_reuse_observed")

    report = valid_report()
    report["concurrent_runtime_probe_connection_ids"] = ["0000000000000001"] * 10
    assert_rejects("duplicate runtime probe connection ids", report, "concurrent runtime probe connection ids")


def assert_validator_rejects_bad_runtime_probe_evidence() -> None:
    report = valid_report()
    report.pop("runtime_probe", None)
    assert_rejects("missing runtime probe", report, "runtime_probe must be an object")

    report = valid_report()
    runtime_probe = report["runtime_probe"]
    if not isinstance(runtime_probe, dict):
        raise AssertionError("fixture runtime_probe should be a dict")
    runtime_probe["store"] = "json"
    assert_rejects("runtime probe JSON store", report, "runtime_probe.store")

    report = valid_report()
    runtime_probe = report["runtime_probe"]
    if not isinstance(runtime_probe, dict):
        raise AssertionError("fixture runtime_probe should be a dict")
    runtime_probe["json_fallback_used"] = True
    assert_rejects("runtime probe fallback", report, "runtime_probe.json_fallback_used")

    report = valid_report()
    runtime_probe = report["runtime_probe"]
    if not isinstance(runtime_probe, dict):
        raise AssertionError("fixture runtime_probe should be a dict")
    runtime_probe["postgres_count_probe"] = {"schema_migrations": 0}
    assert_rejects("runtime probe schema count", report, "runtime_probe.postgres_count_probe.schema_migrations")


def assert_validator_rejects_bad_base_url() -> None:
    report = valid_report()
    report.pop("base_url", None)
    assert_rejects("missing base URL", report, "base_url is required")

    report = valid_report()
    report["base_url"] = "http://example.com:8765"
    assert_rejects("remote production base URL", report, "base_url must be http://127.0.0.1:8765")

    report = valid_report()
    report["base_url"] = "http://127.0.0.1:8766"
    assert_rejects("wrong production base URL port", report, "base_url must be http://127.0.0.1:8765")

    validate_final_report(
        valid_report(mode="deployed-postgres-contract"),
        expected_mode="deployed-postgres-contract",
        expected_concurrent_accounts=10,
    )


def assert_validator_rejects_bad_runtime_env_evidence() -> None:
    report = valid_report()
    report.pop("runtime_env", None)
    assert_rejects("missing runtime env", report, "runtime_env must be an object")

    report = valid_report()
    runtime_env = report["runtime_env"]
    if not isinstance(runtime_env, dict):
        raise AssertionError("fixture runtime_env should be a dict")
    runtime_env["data_store_env_value"] = "json"
    assert_rejects("runtime env JSON store", report, "runtime_env.data_store_env_value")

    report = valid_report()
    runtime_env = report["runtime_env"]
    if not isinstance(runtime_env, dict):
        raise AssertionError("fixture runtime_env should be a dict")
    runtime_env["db_url_present"] = False
    assert_rejects("runtime env missing DB URL", report, "runtime_env.db_url_present")


def assert_validator_rejects_cleanup_residual_rows() -> None:
    report = valid_report()
    report.pop("cleanup_residual_rows", None)
    assert_rejects("missing cleanup residual rows", report, "cleanup_residual_rows must be an object")

    report = valid_report()
    residuals = report["cleanup_residual_rows"]
    if not isinstance(residuals, dict):
        raise AssertionError("fixture cleanup_residual_rows should be a dict")
    residuals["accessories"] = 1
    assert_rejects("accessory cleanup residual", report, "cleanup_residual_rows.accessories")


def assert_validator_rejects_schema_version_mismatch() -> None:
    report = valid_report()
    report.pop("schema_migration_versions", None)
    assert_rejects("missing schema migration versions", report, "schema_migration_versions must be a list")

    report = valid_report()
    report["schema_migration_versions"] = ["2026_wrong"]
    assert_rejects("wrong schema migration version", report, "schema_migration_versions must equal")


def assert_validator_rejects_missing_table_evidence() -> None:
    report = valid_report()
    read_tables = report["postgres_visible_read_tables"]
    if not isinstance(read_tables, dict):
        raise AssertionError("fixture postgres_visible_read_tables should be a dict")
    read_tables.pop("auto_optimize_states", None)
    assert_rejects("missing PostgreSQL-visible read table", report, "postgres_visible_read_tables.auto_optimize_states")

    report = valid_report()
    report["postgres_visible_write_tables"] = {"users": True, "data_analysis_records": True}
    assert_rejects("missing PostgreSQL-visible write table", report, "postgres_visible_write_tables.auth_sessions")

    report = valid_report()
    write_tables = report["postgres_visible_write_tables"]
    if not isinstance(write_tables, dict):
        raise AssertionError("fixture postgres_visible_write_tables should be a dict")
    write_tables.pop("data_analysis_records", None)
    assert_rejects("missing data-analysis write table", report, "postgres_visible_write_tables.data_analysis_records")


def assert_validator_rejects_missing_write_coverage_exception() -> None:
    report = valid_report()
    exceptions = report["write_coverage_exceptions"]
    if not isinstance(exceptions, dict):
        raise AssertionError("fixture write_coverage_exceptions should be a dict")
    exceptions.pop("training_tasks", None)
    assert_rejects("missing read-only write coverage exception", report, "write_coverage_exceptions.training_tasks")

    report = valid_report()
    exceptions = report["write_coverage_exceptions"]
    if not isinstance(exceptions, dict):
        raise AssertionError("fixture write_coverage_exceptions should be a dict")
    exceptions["app_config"] = "stale app_config waiver should be rejected because write/cleanup proof exists"
    assert_rejects("unexpected write coverage exception", report, "write_coverage_exceptions contains unexpected tables")


def assert_validator_rejects_missing_allowlist_path() -> None:
    report = valid_report()
    allowlist = copy.deepcopy(report["endpoint_allowlist"])
    if not isinstance(allowlist, list):
        raise AssertionError("fixture endpoint_allowlist should be a list")
    report["endpoint_allowlist"] = [item for item in allowlist if item.get("path") != "/api/pipeline/tasks*"]
    assert_rejects("missing allowlist path", report, "endpoint_allowlist missing required paths")

    report = valid_report()
    allowlist = copy.deepcopy(report["endpoint_allowlist"])
    if not isinstance(allowlist, list):
        raise AssertionError("fixture endpoint_allowlist should be a list")
    report["endpoint_allowlist"] = [
        item for item in allowlist if item.get("path") != "/api/image-jobs* and /api/image-job-candidates*"
    ]
    assert_rejects("missing image-job allowlist path", report, "endpoint_allowlist missing required paths")


def assert_validator_rejects_secret_markers() -> None:
    report = valid_report()
    report["note"] = "DATABASE_URL=redacted"
    assert_rejects("secret marker", report, "forbidden marker")


def main() -> None:
    assert_validator_passes()
    assert_validator_rejects_bad_base_url()
    assert_validator_rejects_bad_runtime_probe_evidence()
    assert_validator_rejects_bad_runtime_env_evidence()
    assert_validator_rejects_cleanup_residual_rows()
    assert_validator_rejects_schema_version_mismatch()
    assert_validator_rejects_missing_concurrency_evidence()
    assert_validator_rejects_missing_table_evidence()
    assert_validator_rejects_missing_write_coverage_exception()
    assert_validator_rejects_missing_allowlist_path()
    assert_validator_rejects_secret_markers()
    print("postgres full-smoke report validator smoke passed")


if __name__ == "__main__":
    main()
