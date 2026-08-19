#!/usr/bin/env python3
"""Smoke-check the final PostgreSQL cutover packet command contract.

This test does not execute the packet. It guards the reviewed runbook against
doc edits that accidentally remove the import row-count gate, final gate
summary arguments, or the 10-account concurrent full-smoke requirement.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "local_inspection_service" / "docs" / "postgres-final-migration-cutover-execution-packet.md"


REQUIRED_SNIPPETS = (
    'IMPORT_ROW_COUNT_REPORT="$BACKUP_ROOT/import-row-count-report.json"',
    'IMPORT_ENGINE_REPORT="$BACKUP_ROOT/import-real-engine-report.json"',
    'POSTGRES_BIN_DIR="${POSTGRES_BIN_DIR:-/usr/lib/postgresql/16/bin}"',
    "local_inspection_service/scripts/postgres_cutover_deploy_package.py create",
    "local_inspection_service/scripts/postgres_cutover_deploy_package.py verify",
    "local_inspection_service/scripts/postgres_cutover_deploy_package.py extract",
    "local_inspection_service/scripts/postgres_cutover_deploy_package.py restore",
    '--backup-dir "/opt/vantaline/backups/postgres-cutover-code-deploy/$CUTOVER_UTC"',
    "vantaline-postgres-cutover-deploy-package-extract-report.json",
    "vantaline-postgres-cutover-deploy-package-restore-report.json",
    "`backup_performed=true`",
    "`restored=true`",
    "`artifact_manifest_verified_after_extract=true`",
    "`backup_manifest`",
    "`manifest_sha256`",
    "the artifact verification report's `manifest_sha256`",
    "local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py",
    "MIGRATION_REPORT_VALIDATOR=local_inspection_service/scripts/validate_postgres_migration_report.py",
    "IMPORT_ROW_COUNT_REPORTER=local_inspection_service/scripts/postgres_import_row_count_report.py",
    "DATA_LAYER_MIGRATOR=local_inspection_service/scripts/migrate_json_to_sqlite.py",
    "DATA_LAYER_MIGRATION_SMOKE=local_inspection_service/scripts/smoke_data_layer_migration.py",
    "CUTOVER_DEPLOY_PACKAGE=local_inspection_service/scripts/postgres_cutover_deploy_package.py",
    "CUTOVER_DEPLOY_PACKAGE_SMOKE=local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py",
    "ENDPOINT_SOURCE_CONTRACT=local_inspection_service/scripts/smoke_postgres_endpoint_source_contract.py",
    'DEPLOY_PACKAGE_EXTRACT_REPORT="/tmp/vantaline-postgres-cutover-deploy-package-extract-report.json"',
    "LOCAL_PREFLIGHT_SUITE=local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py",
    "LOCAL_PREFLIGHT_SUITE_VALIDATOR=local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py",
    'LOCAL_PREFLIGHT_SUITE_REPORT="/tmp/vantaline_local_preflight_suite_$CUTOVER_UTC.json"',
    "SCHEMA_ENGINE_SMOKE=local_inspection_service/scripts/smoke_postgres_schema_real_engine.py",
    "IMPORT_ENGINE_SMOKE=local_inspection_service/scripts/smoke_postgres_import_real_engine.py",
    "test -s \"$MIGRATION_REPORT_VALIDATOR\"",
    "test -s \"$IMPORT_ROW_COUNT_REPORTER\"",
    "test -s \"$DATA_LAYER_MIGRATOR\"",
    "test -s \"$DATA_LAYER_MIGRATION_SMOKE\"",
    "test -s \"$CUTOVER_DEPLOY_PACKAGE\"",
    "test -s \"$CUTOVER_DEPLOY_PACKAGE_SMOKE\"",
    "test -s \"$ENDPOINT_SOURCE_CONTRACT\"",
    "test -s \"$LOCAL_PREFLIGHT_SUITE\"",
    "test -s \"$LOCAL_PREFLIGHT_SUITE_VALIDATOR\"",
    "test -s \"$SCHEMA_ENGINE_SMOKE\"",
    "test -s \"$IMPORT_ENGINE_SMOKE\"",
    "local_inspection_service/scripts/validate_postgres_migration_report.py",
    "local_inspection_service/scripts/migrate_json_to_sqlite.py",
    "local_inspection_service/scripts/smoke_data_layer_migration.py",
    "local_inspection_service/scripts/postgres_import_row_count_report.py",
    "local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py",
    "local_inspection_service/scripts/smoke_postgres_endpoint_source_contract.py",
    "local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py",
    "local_inspection_service/scripts/smoke_postgres_schema_real_engine.py",
    "local_inspection_service/scripts/smoke_postgres_import_real_engine.py",
    "SUITE_ENGINE_ARGS=()",
    'SUITE_ENGINE_ARGS+=(--postgres-bin-dir "$POSTGRES_BIN_DIR")',
    'SUITE_ENGINE_ARGS+=(--library-dir "$POSTGRES_LIBRARY_DIR")',
    '"$LOCAL_PREFLIGHT_SUITE" "${SUITE_ENGINE_ARGS[@]}"',
    "--require-real-engine",
    "--report \"$LOCAL_PREFLIGHT_SUITE_REPORT\"",
    '"$LOCAL_PREFLIGHT_SUITE_VALIDATOR"',
    "`postgres endpoint source contract`",
    "helper-level `runtime_postgres_repository_or_none()` coverage",
    "`production_cutover_proof=false`",
    'SCHEMA_ENGINE_ARGS=(--postgres-bin-dir "$POSTGRES_BIN_DIR")',
    'SCHEMA_ENGINE_ARGS+=(--library-dir "$POSTGRES_LIBRARY_DIR")',
    "assert report[\"ddl_sha256\"] == hashlib.sha256(ddl_path.read_bytes()).hexdigest()",
    "print(f\"ddl_sha256={report['ddl_sha256']}\")",
    '"$IMPORT_ENGINE_SMOKE" "${SCHEMA_ENGINE_ARGS[@]}"',
    "--ddl \"$SCHEMA_PATH\"",
    "--migration-report \"$REPORT_PATH\"",
    "--report \"$IMPORT_ENGINE_REPORT\"",
    "--migration-report \"$REPORT_PATH\"",
    "--db-url \"$DB_URL\"",
    "--report \"$IMPORT_ROW_COUNT_REPORT\"",
    "local_inspection_service/scripts/postgres_cutover_gate_report.py",
    "--local-preflight-suite-report \"$LOCAL_PREFLIGHT_SUITE_REPORT\"",
    "--deploy-package-extract-report \"$DEPLOY_PACKAGE_EXTRACT_REPORT\"",
    "--row-count-report \"$IMPORT_ROW_COUNT_REPORT\"",
    "--import-engine-report \"$IMPORT_ENGINE_REPORT\"",
    "--expected-concurrent-accounts 10",
    "--strict-final",
    'READ_ONLY_WRITE_WAIVER_ID="${READ_ONLY_WRITE_WAIVER_ID:?manager-approved read-only write waiver id required}"',
    'DATA_ANALYSIS_WRITE_FLAG="${RUN_DATA_ANALYSIS_WRITE:-0}"',
    "DATA_ANALYSIS_WRITE_ARGS=()",
    'DATA_ANALYSIS_WRITE_ARGS+=(--run-data-analysis-write)',
    '--read-only-write-waiver-id "$3"',
    '"${DATA_ANALYSIS_WRITE_ARGS[@]}"',
    "`migration_report.import_artifact_emitted=true`",
    "`code_deploy.passed=true`",
    "`code_deploy.manifest_sha256=<artifact_manifest.manifest_sha256>`",
    "`code_deploy.backup_performed=true`",
    "`code_deploy.artifact_manifest_verified_after_extract=true`",
    "`local_preflight_suite.passed=true`",
    "`local_preflight_suite.real_engine_required=true`",
    "`local_preflight_suite.real_engine_pass=true`",
    "`import_row_counts.row_count_parity_pass=true`",
    "`import_real_engine.artifact_source=existing-migration-packet`",
    "`import_real_engine.migration_report_sha256=<sha256-of-migration-report>`",
    "`import_real_engine.ddl_sha256=<sha256-of-schema-sql>`",
    "`import_real_engine.csv_import_real_engine_pass=true`",
    "`full_smoke.base_url=http://127.0.0.1:8765`",
    "`full_smoke.runtime_probe.store=postgres`",
    "`full_smoke.runtime_probe.repository_kind=postgres`",
    "`full_smoke.runtime_probe.json_fallback_used=false`",
    "`full_smoke.runtime_probe.postgres_count_probe.schema_migrations>=1`",
    "`full_smoke.runtime_env.data_store_env_value=postgres`",
    "`full_smoke.runtime_env.db_url_present=true`",
    "`full_smoke.schema_migration_versions=[2026_07_01_phase4_pr1]`",
    "`full_smoke.cleanup_residual_rows.accessories=0`",
    "`full_smoke.cleanup_residual_rows.accessory_candidates=0`",
    "`full_smoke.cleanup_residual_rows.ai_detection_tasks=0`",
    "`full_smoke.cleanup_residual_rows.auto_optimize_states=0`",
    "`full_smoke.cleanup_residual_rows.pipeline_tasks=0`",
    "`full_smoke.cleanup_residual_rows.pipeline_state_accessory_ids=0`",
    "`full_smoke.cleanup_residual_rows.data_analysis_records=0`",
    "`full_smoke.concurrent_successful_sessions=10`",
    "`full_smoke.concurrent_postgres_visible_sessions=10`",
    "`full_smoke.concurrent_runtime_probe_count=10`",
    "`full_smoke.concurrent_thread_local_connections=<1..10>`",
    "`full_smoke.concurrent_runtime_probe_unique_connections=<same-as-concurrent_thread_local_connections>`",
    "`full_smoke.concurrent_runtime_probe_connection_observations=<10-16-hex-ids-duplicates-allowed>`",
    "`full_smoke.concurrent_runtime_probe_connection_ids=<1..10-unique-16-hex-ids>`",
    "`full_smoke.concurrent_runtime_probe_connection_reuse_observed=<true iff unique connections < 10>`",
    "`full_smoke.postgres_visible_write_proof_pass=true`",
    "/api/image-jobs* and /api/image-job-candidates*",
    "/api/ai/tasks/*/auto-optimize*",
    "/api/pipeline/accessories*",
    "`full_smoke.read_only_write_waiver_required=true`",
    "`read_only_write_waiver_required=true`",
    "write_coverage_exceptions=<table-reason-json>",
    "`base_url=http://127.0.0.1:8765`",
    "`app_config`",
    "`accessory_candidates`",
    "`pipeline_state`",
    "`auto_optimize_states`",
    "`postgres_visible_write_proof_pass=true`",
    "`concurrent_runtime_probe_count=10`",
    "`concurrent_thread_local_connections=<1..10>`",
    "`concurrent_runtime_probe_unique_connections=<same-as-concurrent_thread_local_connections>`",
    "`concurrent_runtime_probe_connection_observations=<10-16-hex-ids-duplicates-allowed>`",
    "`concurrent_runtime_probe_connection_ids=<1..10-unique-16-hex-ids>`",
    "`concurrent_runtime_probe_connection_reuse_observed=<true iff unique connections < 10>`",
    "`runtime_probe.store=postgres`",
    "`runtime_probe.repository_kind=postgres`",
    "`runtime_probe.json_fallback_used=false`",
    "`runtime_probe.postgres_count_probe.schema_migrations>=1`",
    "`runtime_env.data_store_env_value=postgres`",
    "`runtime_env.db_url_present=true`",
    "`schema_migration_versions=[2026_07_01_phase4_pr1]`",
    "`app_config_write_pass=true`",
    "`app_config_cleanup_pass=true`",
    "`accessory_candidate_create_pass=true`",
    "`accessory_candidate_delete_pass=true`",
    "`ai_task_create_pass=true`",
    "`ai_task_update_pass=true`",
    "`auto_optimize_write_pass=true`",
    "`auto_optimize_cleanup_pass=true`",
    "`ai_task_delete_pass=true`",
    "`pipeline_state_write_pass=true`",
    "`pipeline_state_cleanup_pass=true`",
    "`allowlist_state_tables_read_pass=true`",
    "POST /api/analyze/image",
    "DELETE /api/data-analysis/records/{record_id}",
    "`data_analysis_write_pass=true`",
    "data_analysis_write_skipped_reason=<manager-approved reason>",
    "`disposable_ids.data_analysis_record_id=<analysis_...>`",
    "`cleanup_residual_rows.accessories=0`",
    "`cleanup_residual_rows.accessory_candidates=0`",
    "`cleanup_residual_rows.ai_detection_tasks=0`",
    "`cleanup_residual_rows.auto_optimize_states=0`",
    "`cleanup_residual_rows.pipeline_tasks=0`",
    "`cleanup_residual_rows.pipeline_state_accessory_ids=0`",
    "`cleanup_residual_rows.data_analysis_records=0`",
    "postgres_visible_read_tables=<redacted-count-json>",
    "`auto_optimize_states`",
    "`pipeline_state`",
    "`accessory_candidates`",
    "`app_config`",
    "postgres_visible_write_tables=<table-bool-json>",
    "postgres_visible_cleanup_tables=<table-bool-json>",
    "migration_report_validation_pass=<true|false>",
    "local_preflight_suite_report=<path|not-created>",
    "local_preflight_suite_real_engine_required=<true|false>",
    "local_preflight_suite_real_engine_pass=<true|false>",
    "import_real_engine_report=<path|not-created>",
    "import_row_count_report=<path|not-created>",
    "cutover_gate_report_final_acceptance_pass=<true|false>",
    "migration report validation, real-engine import smoke, and import row-count",
)


ORDERED_SNIPPETS = (
    "local_inspection_service/scripts/validate_postgres_migration_report.py",
    "local_inspection_service/scripts/postgres_import_row_count_report.py",
    "local_inspection_service/scripts/postgres_cutover_gate_report.py",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    text = PACKET.read_text(encoding="utf-8")
    require(text.count("```") % 2 == 0, "markdown code fences must be balanced")
    missing = [snippet for snippet in REQUIRED_SNIPPETS if snippet not in text]
    require(not missing, "final cutover packet missing snippets: " + ", ".join(missing))

    positions = [text.index(snippet) for snippet in ORDERED_SNIPPETS]
    require(positions == sorted(positions), "migration validation, row-count parity, and final gate order changed")

    full_smoke_section = text[text.index("Required smoke command:") :]
    require("--concurrent-accounts 10" in full_smoke_section, "final full smoke must require 10 concurrent accounts")
    require(
        "--row-count-report \"$IMPORT_ROW_COUNT_REPORT\"" in full_smoke_section,
        "final gate summary must consume the import row-count report",
    )
    print("postgres final cutover packet docs smoke passed")


if __name__ == "__main__":
    main()
