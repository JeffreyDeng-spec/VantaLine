#!/usr/bin/env python3
"""Validate a final PostgreSQL cutover full-smoke report.

This script is intentionally read-only. It validates the JSON report emitted by
`smoke_postgres_cutover_full.py` after the deployed-postgres or local contract
mode, including the 10-account concurrent HTTP gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.storage.schema import SCHEMA_VERSION  # noqa: E402

FINAL_MODES = frozenset({"deployed-postgres", "deployed-postgres-contract"})
PRODUCTION_BASE_URL = "http://127.0.0.1:8765"

REQUIRED_TRUE_FIELDS = (
    "login_pass",
    "public_root_pass",
    "static_bundle_pass",
    "auth_status_pass",
    "runtime_probe_pass",
    "deleted_feature_boundary_pass",
    "docs_boundary_pass",
    "unauthorized_api_boundary_pass",
    "app_config_write_pass",
    "app_config_cleanup_pass",
    "accessories_read_pass",
    "accessory_detail_pass",
    "accessory_candidate_create_pass",
    "accessory_candidate_delete_pass",
    "pipeline_tasks_read_pass",
    "training_status_read_pass",
    "training_resources_read_pass",
    "ai_tasks_read_pass",
    "ai_task_create_pass",
    "ai_task_update_pass",
    "auto_optimize_write_pass",
    "auto_optimize_cleanup_pass",
    "ai_task_delete_pass",
    "data_analysis_records_read_pass",
    "allowlist_state_tables_read_pass",
    "accessory_create_pass",
    "pipeline_state_write_pass",
    "pipeline_state_cleanup_pass",
    "pipeline_create_pass",
    "pipeline_update_pass",
    "pipeline_delete_pass",
    "accessory_delete_pass",
    "concurrent_account_http_pass",
    "concurrent_account_cleanup_pass",
    "postgres_visible_write_proof_pass",
    "cleanup_pass",
    "row_count_after_smoke_expected",
    "require_postgres_visible_writes",
    "postgres_repository_close_pass",
    "non_secret_report",
)

ALLOWLIST_KEYS = ("method", "path", "repository_method", "read_write", "transaction_boundary")
REQUIRED_ALLOWLIST_PATHS = (
    "/api/auth/*",
    "/api/admin/runtime-store/probe",
    "/api/accessories*",
    "/api/image-jobs* and /api/image-job-candidates*",
    "/api/ai/tasks*",
    "/api/ai/tasks/*/auto-optimize*",
    "/api/data-analysis/records*",
    "/api/training/*",
    "/api/pipeline/tasks*",
    "/api/pipeline/accessories*",
)
REQUIRED_POSTGRES_READ_TABLES = (
    "schema_migrations",
    "app_config",
    "accessories",
    "accessory_candidates",
    "pipeline_tasks",
    "pipeline_state",
    "training_tasks",
    "ai_detection_tasks",
    "auto_optimize_states",
    "data_analysis_records",
)
REQUIRED_POSTGRES_WRITE_TABLES = (
    "users",
    "auth_sessions",
    "app_config",
    "accessories",
    "accessory_candidates",
    "ai_detection_tasks",
    "pipeline_tasks",
    "pipeline_state",
    "auto_optimize_states",
)
REQUIRED_POSTGRES_CLEANUP_TABLES = REQUIRED_POSTGRES_WRITE_TABLES
REQUIRED_WRITE_COVERAGE_EXCEPTIONS = (
    "training_tasks",
    "data_analysis_records",
)
RUNTIME_PROBE_CONNECTION_SCOPE = "thread-local"
CLEANUP_RESIDUAL_ROW_KEYS = (
    "accessories",
    "accessory_candidates",
    "ai_detection_tasks",
    "auto_optimize_states",
    "pipeline_tasks",
    "pipeline_state_accessory_ids",
    "data_analysis_records",
)
DISPOSABLE_ID_PATTERNS = {
    "accessory_id": re.compile(r"^acc_[A-Za-z0-9_-]{6,64}$"),
    "candidate_id": re.compile(r"^cand_[A-Za-z0-9_-]{6,64}$"),
    "ai_task_id": re.compile(r"^aitask_[A-Za-z0-9_-]{6,64}$"),
    "data_analysis_record_id": re.compile(r"^analysis_[A-Za-z0-9_-]{6,80}$"),
    "pipeline_task_id": re.compile(r"^pipe_[A-Za-z0-9_-]{6,64}$"),
}
OPTIONAL_DISPOSABLE_ID_KEYS = frozenset({"data_analysis_record_id"})
FORBIDDEN_REPORT_MARKERS = ("DATABASE_URL=", "postgresql://", "password", "cookie", "vantaline_session")


class ReportValidationError(AssertionError):
    """Raised when the final smoke report does not satisfy the cutover gate."""


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReportValidationError(f"report file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReportValidationError(f"report is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ReportValidationError("report root must be a JSON object")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportValidationError(message)


def validate_no_secret_markers(report: dict[str, Any]) -> None:
    text = stable_json(report).lower()
    for marker in FORBIDDEN_REPORT_MARKERS:
        require(marker.lower() not in text, f"report contains forbidden marker: {marker}")


def validate_base_url(report: dict[str, Any], *, mode: str) -> None:
    base_url = str(report.get("base_url") or "").strip()
    require(bool(base_url), "base_url is required")
    parsed = urllib.parse.urlparse(base_url)
    require(parsed.scheme == "http", "base_url must use http")
    require(parsed.username is None and parsed.password is None, "base_url must not include credentials")
    require(not parsed.path or parsed.path == "/", "base_url must not include a path")
    require(not parsed.query and not parsed.fragment, "base_url must not include query or fragment")
    if mode == "deployed-postgres":
        require(base_url == PRODUCTION_BASE_URL, f"base_url must be {PRODUCTION_BASE_URL}")
        return
    require(parsed.hostname in {"127.0.0.1", "localhost"}, "contract base_url must be localhost")
    require(isinstance(parsed.port, int) and parsed.port > 0, "contract base_url must include a port")


def validate_runtime_probe(report: dict[str, Any]) -> None:
    probe = report.get("runtime_probe")
    require(isinstance(probe, dict), "runtime_probe must be an object")
    require(probe.get("store") == "postgres", "runtime_probe.store must be postgres")
    require(probe.get("repository_kind") == "postgres", "runtime_probe.repository_kind must be postgres")
    require(probe.get("json_fallback_used") is False, "runtime_probe.json_fallback_used must be false")
    require(
        probe.get("repository_connection_scope") == RUNTIME_PROBE_CONNECTION_SCOPE,
        f"runtime_probe.repository_connection_scope must be {RUNTIME_PROBE_CONNECTION_SCOPE}",
    )
    connection_id = str(probe.get("repository_connection_id") or "").strip()
    require(
        re.fullmatch(r"[0-9a-f]{16}", connection_id) is not None,
        f"runtime_probe.repository_connection_id has unexpected shape: {connection_id!r}",
    )
    count_probe = probe.get("postgres_count_probe")
    require(isinstance(count_probe, dict), "runtime_probe.postgres_count_probe must be an object")
    schema_migrations = count_probe.get("schema_migrations")
    require(
        isinstance(schema_migrations, int) and schema_migrations >= 1,
        "runtime_probe.postgres_count_probe.schema_migrations must be a positive integer",
    )


def validate_runtime_env(report: dict[str, Any]) -> None:
    runtime_env = report.get("runtime_env")
    require(isinstance(runtime_env, dict), "runtime_env must be an object")
    require(
        runtime_env.get("data_store_env_name") == "VANTALINE_DATA_STORE",
        "runtime_env.data_store_env_name must be VANTALINE_DATA_STORE",
    )
    require(
        runtime_env.get("data_store_env_value") == "postgres",
        "runtime_env.data_store_env_value must be postgres",
    )
    require(runtime_env.get("db_url_env_name") == "DATABASE_URL", "runtime_env.db_url_env_name must be DATABASE_URL")
    require(runtime_env.get("db_url_present") is True, "runtime_env.db_url_present must be true")


def validate_cleanup_residual_rows(report: dict[str, Any]) -> None:
    residuals = report.get("cleanup_residual_rows")
    require(isinstance(residuals, dict), "cleanup_residual_rows must be an object")
    for key in CLEANUP_RESIDUAL_ROW_KEYS:
        require(residuals.get(key) == 0, f"cleanup_residual_rows.{key} must be 0")


def validate_schema_migration_versions(report: dict[str, Any]) -> None:
    versions = report.get("schema_migration_versions")
    require(isinstance(versions, list), "schema_migration_versions must be a list")
    normalized = sorted({str(version or "").strip() for version in versions if str(version or "").strip()})
    require(normalized == [SCHEMA_VERSION], f"schema_migration_versions must equal [{SCHEMA_VERSION}]")


def validate_allowlist(report: dict[str, Any]) -> None:
    allowlist = report.get("endpoint_allowlist")
    require(isinstance(allowlist, list) and bool(allowlist), "endpoint_allowlist must be a non-empty list")
    paths: set[str] = set()
    for index, item in enumerate(allowlist):
        require(isinstance(item, dict), f"endpoint_allowlist[{index}] must be an object")
        for key in ALLOWLIST_KEYS:
            require(bool(item.get(key)), f"endpoint_allowlist[{index}] missing {key}")
        paths.add(str(item.get("path") or ""))
    missing_paths = [path for path in REQUIRED_ALLOWLIST_PATHS if path not in paths]
    require(not missing_paths, "endpoint_allowlist missing required paths: " + ",".join(missing_paths))


def validate_disposable_ids(report: dict[str, Any]) -> None:
    disposable_ids = report.get("disposable_ids")
    require(isinstance(disposable_ids, dict), "disposable_ids must be an object")
    for key, pattern in DISPOSABLE_ID_PATTERNS.items():
        if key in OPTIONAL_DISPOSABLE_ID_KEYS and report.get("data_analysis_write_pass") is not True:
            continue
        value = str(disposable_ids.get(key) or "")
        require(bool(value), f"disposable_ids.{key} is required")
        require(pattern.fullmatch(value) is not None, f"disposable_ids.{key} has unexpected shape: {value!r}")


def validate_data_analysis_write(report: dict[str, Any]) -> None:
    if report.get("data_analysis_write_pass") is True:
        write_tables = report.get("postgres_visible_write_tables")
        cleanup_tables = report.get("postgres_visible_cleanup_tables")
        require(isinstance(write_tables, dict), "postgres_visible_write_tables must be an object")
        require(isinstance(cleanup_tables, dict), "postgres_visible_cleanup_tables must be an object")
        require(write_tables.get("data_analysis_records") is True, "postgres_visible_write_tables.data_analysis_records must be true")
        require(cleanup_tables.get("data_analysis_records") is True, "postgres_visible_cleanup_tables.data_analysis_records must be true")
        return
    reason = str(report.get("data_analysis_write_skipped_reason") or "").strip()
    require(bool(reason), "data analysis write must either pass or include data_analysis_write_skipped_reason")


def validate_write_coverage_exceptions(report: dict[str, Any]) -> None:
    waiver_id = str(report.get("read_only_write_waiver_id") or "").strip()
    require(bool(waiver_id), "read_only_write_waiver_id is required for read-only-only write probes")
    require(
        re.fullmatch(r"[A-Za-z0-9_.:-]{8,120}", waiver_id) is not None,
        "read_only_write_waiver_id must be an 8-120 character safe identifier",
    )
    require(report.get("read_only_write_waiver_required") is True, "read_only_write_waiver_required must be true")
    exceptions = report.get("write_coverage_exceptions")
    require(isinstance(exceptions, dict), "write_coverage_exceptions must be an object")
    write_tables = report.get("postgres_visible_write_tables")
    cleanup_tables = report.get("postgres_visible_cleanup_tables")
    require(isinstance(write_tables, dict), "postgres_visible_write_tables must be an object")
    require(isinstance(cleanup_tables, dict), "postgres_visible_cleanup_tables must be an object")
    allowed_exception_tables: set[str] = set()
    for table_name in REQUIRED_WRITE_COVERAGE_EXCEPTIONS:
        if write_tables.get(table_name) is True and cleanup_tables.get(table_name) is True:
            continue
        allowed_exception_tables.add(table_name)
        reason = str(exceptions.get(table_name) or "").strip()
        require(bool(reason), f"write_coverage_exceptions.{table_name} is required")
    unexpected = sorted(str(table_name) for table_name in exceptions if str(table_name) not in allowed_exception_tables)
    require(not unexpected, "write_coverage_exceptions contains unexpected tables: " + ",".join(unexpected))


def validate_postgres_visible_table_evidence(report: dict[str, Any]) -> None:
    read_tables = report.get("postgres_visible_read_tables")
    require(isinstance(read_tables, dict), "postgres_visible_read_tables must be an object")
    for table_name in REQUIRED_POSTGRES_READ_TABLES:
        value = read_tables.get(table_name)
        require(isinstance(value, int) and value >= 0, f"postgres_visible_read_tables.{table_name} must be a non-negative integer")

    write_tables = report.get("postgres_visible_write_tables")
    require(isinstance(write_tables, dict), "postgres_visible_write_tables must be an object")
    for table_name in REQUIRED_POSTGRES_WRITE_TABLES:
        require(write_tables.get(table_name) is True, f"postgres_visible_write_tables.{table_name} must be true")

    cleanup_tables = report.get("postgres_visible_cleanup_tables")
    require(isinstance(cleanup_tables, dict), "postgres_visible_cleanup_tables must be an object")
    for table_name in REQUIRED_POSTGRES_CLEANUP_TABLES:
        require(cleanup_tables.get(table_name) is True, f"postgres_visible_cleanup_tables.{table_name} must be true")


def validate_concurrent_connection_evidence(report: dict[str, Any], *, expected_concurrent_accounts: int) -> None:
    thread_local_connections = report.get("concurrent_thread_local_connections")
    require(
        type(thread_local_connections) is int and 1 <= thread_local_connections <= expected_concurrent_accounts,
        f"concurrent_thread_local_connections must be between 1 and {expected_concurrent_accounts}",
    )
    runtime_probe_count = report.get("concurrent_runtime_probe_count")
    require(
        runtime_probe_count == expected_concurrent_accounts,
        f"concurrent_runtime_probe_count must be {expected_concurrent_accounts}",
    )
    unique_connection_count = report.get("concurrent_runtime_probe_unique_connections")
    require(
        type(unique_connection_count) is int and unique_connection_count == thread_local_connections,
        "concurrent_runtime_probe_unique_connections must match concurrent_thread_local_connections",
    )
    connection_ids = report.get("concurrent_runtime_probe_connection_ids")
    require(
        isinstance(connection_ids, list) and len(connection_ids) == unique_connection_count,
        "concurrent_runtime_probe_connection_ids must contain the unique runtime probe connection ids",
    )
    normalized = [str(value or "").strip() for value in connection_ids]
    require(len(set(normalized)) == unique_connection_count, "concurrent runtime probe connection ids must be unique")
    for index, value in enumerate(normalized):
        require(
            re.fullmatch(r"[0-9a-f]{16}", value) is not None,
            f"concurrent_runtime_probe_connection_ids[{index}] has unexpected shape: {value!r}",
        )
    observations = report.get("concurrent_runtime_probe_connection_observations")
    require(
        isinstance(observations, list) and len(observations) == expected_concurrent_accounts,
        f"concurrent_runtime_probe_connection_observations must contain {expected_concurrent_accounts} items",
    )
    normalized_observations = [str(value or "").strip() for value in observations]
    for index, value in enumerate(normalized_observations):
        require(
            re.fullmatch(r"[0-9a-f]{16}", value) is not None,
            f"concurrent_runtime_probe_connection_observations[{index}] has unexpected shape: {value!r}",
        )
    require(
        set(normalized_observations) == set(normalized),
        "concurrent runtime probe observations must match the unique connection id set",
    )
    reuse_observed = report.get("concurrent_runtime_probe_connection_reuse_observed")
    require(
        type(reuse_observed) is bool and reuse_observed == (unique_connection_count < expected_concurrent_accounts),
        "concurrent_runtime_probe_connection_reuse_observed must match observed connection reuse",
    )


def validate_final_report(
    report: dict[str, Any],
    *,
    expected_mode: str,
    expected_concurrent_accounts: int,
) -> None:
    mode = str(report.get("mode") or "")
    if expected_mode:
        require(mode == expected_mode, f"mode mismatch: expected {expected_mode}, got {mode}")
    else:
        require(mode in FINAL_MODES, f"mode must be one of {sorted(FINAL_MODES)}, got {mode!r}")
    require(report.get("expected_store") == "postgres", "expected_store must be postgres")
    require(report.get("credential_source") == "runtime_file", "credential_source must be runtime_file")
    require(report.get("auth_json_token_read") is False, "auth_json_token_read must be false")
    validate_base_url(report, mode=mode)

    for field in REQUIRED_TRUE_FIELDS:
        require(report.get(field) is True, f"{field} must be true")

    validate_runtime_probe(report)
    validate_runtime_env(report)
    validate_cleanup_residual_rows(report)
    validate_schema_migration_versions(report)

    require(
        report.get("concurrent_account_count") == expected_concurrent_accounts,
        f"concurrent_account_count must be {expected_concurrent_accounts}",
    )
    require(
        report.get("concurrent_successful_sessions") == expected_concurrent_accounts,
        f"concurrent_successful_sessions must be {expected_concurrent_accounts}",
    )
    require(
        report.get("concurrent_postgres_visible_sessions") == expected_concurrent_accounts,
        f"concurrent_postgres_visible_sessions must be {expected_concurrent_accounts}",
    )
    require(
        report.get("concurrent_worker_threads") == expected_concurrent_accounts,
        f"concurrent_worker_threads must be {expected_concurrent_accounts}",
    )

    validate_concurrent_connection_evidence(report, expected_concurrent_accounts=expected_concurrent_accounts)
    validate_disposable_ids(report)
    validate_data_analysis_write(report)
    validate_write_coverage_exceptions(report)
    validate_allowlist(report)
    validate_postgres_visible_table_evidence(report)
    validate_no_secret_markers(report)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Path to full-smoke report JSON")
    parser.add_argument(
        "--expected-mode",
        default="",
        choices=("", "deployed-postgres", "deployed-postgres-contract"),
        help="Require a specific final-smoke mode",
    )
    parser.add_argument("--expected-concurrent-accounts", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        report = load_report(Path(args.report))
        validate_final_report(
            report,
            expected_mode=args.expected_mode,
            expected_concurrent_accounts=args.expected_concurrent_accounts,
        )
    except ReportValidationError as exc:
        print(f"postgres full-smoke report validation failed: {exc}", file=sys.stderr)
        return 1
    print("postgres full-smoke report validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
