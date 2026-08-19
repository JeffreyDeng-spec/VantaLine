#!/usr/bin/env python3
"""Build a non-secret PostgreSQL cutover gate summary from reviewed reports.

This script is read-only. It does not run smoke, connect to PostgreSQL, restart
services, or read secret files. Its job is to keep local contract evidence
separate from production cutover evidence so a green contract smoke cannot be
mistaken for task #17 final acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.validate_postgres_full_smoke_report import (  # noqa: E402
    ReportValidationError,
    validate_final_report,
)
from local_inspection_service.scripts.validate_postgres_migration_report import (  # noqa: E402
    MigrationReportValidationError,
    validate_migration_report,
)
from local_inspection_service.scripts.validate_postgres_local_preflight_suite_report import (  # noqa: E402
    LocalPreflightSuiteReportValidationError,
    validate_local_preflight_suite_report,
)
from local_inspection_service.scripts.validate_postgres_precutover_report import (  # noqa: E402
    PrecutoverReportValidationError,
    validate_precutover_report,
)


FORBIDDEN_REPORT_MARKERS = (
    "DATABASE_URL=",
    "postgresql://",
    "VANTALINE_SMOKE_PASSWORD=",
    "password_hash",
    "sha256$",
    "cookie",
    "vantaline_session=",
)


class GateReportError(AssertionError):
    """Raised when the gate report cannot be created safely."""


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json_report(path: Path | None) -> tuple[dict[str, Any] | None, str]:
    if path is None:
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(payload, dict):
        return None, "invalid_root"
    return payload, "loaded"


def has_no_secret_markers(value: Any) -> bool:
    text = stable_json(value).lower()
    return not any(marker.lower() in text for marker in FORBIDDEN_REPORT_MARKERS)


def report_sha256(report: dict[str, Any]) -> str:
    return hashlib.sha256(stable_json(report).encode("utf-8")).hexdigest()


def is_sha256_hex(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def artifact_evidence(report: dict[str, Any] | None, load_status: str) -> dict[str, Any]:
    if report is None:
        return {"status": load_status, "passed": False, "artifact_count": 0}
    passed = (
        report.get("mode") == "postgres-cutover-artifact-manifest-verify"
        and report.get("verified") is True
        and report.get("non_secret_report") is True
        and is_sha256_hex(report.get("manifest_sha256"))
        and isinstance(report.get("artifact_count"), int)
        and report.get("artifact_count", 0) > 0
        and report.get("failures") == []
        and has_no_secret_markers(report)
    )
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "artifact_count": int(report.get("artifact_count") or 0),
        "manifest_sha256": str(report.get("manifest_sha256") or ""),
    }


def readiness_evidence(report: dict[str, Any] | None, load_status: str) -> dict[str, Any]:
    if report is None:
        return {"status": load_status, "passed": False, "blockers": []}
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    passed = (
        report.get("mode") == "postgres-cutover-readiness"
        and report.get("ready_for_manager_cutover_gate") is True
        and report.get("non_secret_report") is True
        and not blockers
        and has_no_secret_markers(report)
    )
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "blockers": [str(item) for item in blockers],
    }


def code_deploy_evidence(report: dict[str, Any] | None, load_status: str) -> dict[str, Any]:
    if report is None:
        return {"status": load_status, "passed": False, "artifact_count": 0}
    metadata_entries = report.get("metadata_entries_written")
    backup_manifest = str(report.get("backup_manifest") or "").strip()
    passed = (
        report.get("mode") == "postgres-cutover-deploy-package-extract"
        and report.get("package_kind") == "vantaline-postgres-cutover-deploy-package"
        and report.get("package_version") == 1
        and is_sha256_hex(report.get("package_sha256"))
        and is_sha256_hex(report.get("manifest_sha256"))
        and report.get("extracted") is True
        and report.get("backup_performed") is True
        and report.get("artifact_manifest_verified_after_extract") is True
        and report.get("non_secret_report") is True
        and metadata_entries
        == [
            ".vantaline_postgres_cutover_package/manifest.json",
            ".vantaline_postgres_cutover_package/INSTALL.md",
            ".vantaline_postgres_cutover_package/sha256sums.txt",
        ]
        and isinstance(report.get("artifact_count"), int)
        and report.get("artifact_count", 0) > 0
        and isinstance(report.get("backup_entry_count"), int)
        and report.get("backup_entry_count", 0) > 0
        and bool(backup_manifest)
        and backup_manifest.endswith("/backup-manifest.json")
        and has_no_secret_markers(report)
    )
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "artifact_count": int(report.get("artifact_count") or 0),
        "manifest_sha256": str(report.get("manifest_sha256") or ""),
        "backup_entry_count": int(report.get("backup_entry_count") or 0),
        "backup_performed": report.get("backup_performed") is True,
        "artifact_manifest_verified_after_extract": report.get("artifact_manifest_verified_after_extract") is True,
    }


def local_preflight_evidence(report: dict[str, Any] | None, load_status: str) -> dict[str, Any]:
    if report is None:
        return {"status": load_status, "passed": False, "result_count": 0}
    if not has_no_secret_markers(report):
        return {"status": "fail", "passed": False, "result_count": 0}
    try:
        summary = validate_local_preflight_suite_report(report)
    except LocalPreflightSuiteReportValidationError:
        failed_required = report.get("failed_required") if isinstance(report.get("failed_required"), list) else []
        return {
            "status": "fail",
            "passed": False,
            "result_count": int(report.get("result_count") or 0),
            "failed_required": [str(item) for item in failed_required],
            "production_cutover_proof": report.get("production_cutover_proof") is True,
            "real_engine_required": report.get("real_engine_required") is True,
            "real_engine_pass": report.get("real_engine_pass") is True,
        }
    return {
        "status": "pass",
        "passed": True,
        "result_count": int(summary["result_count"]),
        "required_result_count": int(summary["required_result_count"]),
        "failed_required": [],
        "production_cutover_proof": False,
        "real_engine_required": True,
        "real_engine_pass": True,
    }


def migration_evidence(report: dict[str, Any] | None, load_status: str) -> dict[str, Any]:
    if report is None:
        return {"status": load_status, "passed": False, "checked_table_count": 0}
    if not has_no_secret_markers(report):
        return {"status": "fail", "passed": False, "checked_table_count": 0}
    try:
        row_counts = validate_migration_report(report)
    except MigrationReportValidationError:
        return {"status": "fail", "passed": False, "checked_table_count": 0}
    return {
        "status": "pass",
        "passed": True,
        "schema_version": str(report.get("schema_version") or ""),
        "report_sha256": report_sha256(report),
        "ddl_sha256": str(report.get("ddl_sha256") or ""),
        "checked_table_count": len(row_counts),
        "schema_migrations_count": row_counts.get("schema_migrations", 0),
        "import_artifact_emitted": True,
    }


def row_count_evidence(report: dict[str, Any] | None, load_status: str) -> dict[str, Any]:
    if report is None:
        return {"status": load_status, "passed": False, "checked_table_count": 0}
    if not has_no_secret_markers(report):
        return {"status": "fail", "passed": False, "checked_table_count": 0}
    passed = (
        report.get("mode") == "postgres-import-row-count-report"
        and report.get("migration_cutover_allowed") is True
        and report.get("row_count_parity_pass") is True
        and report.get("non_secret_report") is True
        and isinstance(report.get("checked_table_count"), int)
        and report.get("checked_table_count", 0) > 0
        and report.get("mismatches") == []
        and report.get("schema_migrations_expected") == 1
        and report.get("schema_migrations_observed") == 1
    )
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "checked_table_count": int(report.get("checked_table_count") or 0),
        "schema_migrations_observed": int(report.get("schema_migrations_observed") or 0),
        "migration_schema_version": str(report.get("migration_schema_version") or ""),
    }


def import_engine_evidence(report: dict[str, Any] | None, load_status: str) -> dict[str, Any]:
    if report is None:
        return {"status": load_status, "passed": False, "checked_table_count": 0}
    if not has_no_secret_markers(report):
        return {"status": "fail", "passed": False, "checked_table_count": 0}
    passed = (
        report.get("mode") == "postgres-import-real-engine-smoke"
        and report.get("postgres_engine") == "single-user"
        and report.get("artifact_source") == "existing-migration-packet"
        and report.get("ddl_real_engine_pass") is True
        and report.get("csv_import_real_engine_pass") is True
        and report.get("row_count_parity_pass") is True
        and report.get("non_secret_report") is True
        and is_sha256_hex(report.get("ddl_sha256"))
        and isinstance(report.get("checked_table_count"), int)
        and report.get("checked_table_count", 0) > 0
    )
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "checked_table_count": int(report.get("checked_table_count") or 0),
        "migration_schema_version": str(report.get("migration_schema_version") or ""),
        "migration_report_sha256": str(report.get("migration_report_sha256") or ""),
        "ddl_sha256": str(report.get("ddl_sha256") or ""),
        "artifact_source": str(report.get("artifact_source") or ""),
    }


def precutover_evidence(report: dict[str, Any] | None, load_status: str) -> dict[str, Any]:
    if report is None:
        return {"status": load_status, "passed": False, "evidence_kind": "missing"}
    if not has_no_secret_markers(report):
        return {"status": "fail", "passed": False, "evidence_kind": "invalid"}
    try:
        validate_precutover_report(report, expected_mode="")
    except PrecutoverReportValidationError:
        return {"status": "fail", "passed": False, "evidence_kind": "invalid"}
    mode = str(report.get("mode") or "")
    evidence_kind = "production" if mode == "deployed-precutover" else "contract"
    return {
        "status": "pass",
        "passed": True,
        "evidence_kind": evidence_kind,
        "observed_store": str(report.get("observed_store") or ""),
    }


def full_smoke_evidence(
    report: dict[str, Any] | None,
    load_status: str,
    *,
    expected_concurrent_accounts: int,
) -> dict[str, Any]:
    if report is None:
        return {"status": load_status, "passed": False, "evidence_kind": "missing"}
    if not has_no_secret_markers(report):
        return {"status": "fail", "passed": False, "evidence_kind": "invalid"}
    try:
        validate_final_report(
            report,
            expected_mode="",
            expected_concurrent_accounts=expected_concurrent_accounts,
        )
    except ReportValidationError:
        return {"status": "fail", "passed": False, "evidence_kind": "invalid"}
    mode = str(report.get("mode") or "")
    evidence_kind = "production" if mode == "deployed-postgres" else "contract"
    connection_ids = [str(value or "").strip() for value in report.get("concurrent_runtime_probe_connection_ids", [])]
    connection_observations = [
        str(value or "").strip()
        for value in report.get("concurrent_runtime_probe_connection_observations", [])
    ]
    return {
        "status": "pass",
        "passed": True,
        "evidence_kind": evidence_kind,
        "base_url": str(report.get("base_url") or ""),
        "runtime_probe": report.get("runtime_probe"),
        "runtime_env": report.get("runtime_env"),
        "schema_migration_versions": report.get("schema_migration_versions"),
        "cleanup_residual_rows": report.get("cleanup_residual_rows"),
        "concurrent_account_count": int(report.get("concurrent_account_count") or 0),
        "concurrent_successful_sessions": int(report.get("concurrent_successful_sessions") or 0),
        "concurrent_postgres_visible_sessions": int(report.get("concurrent_postgres_visible_sessions") or 0),
        "concurrent_worker_threads": int(report.get("concurrent_worker_threads") or 0),
        "concurrent_thread_local_connections": int(report.get("concurrent_thread_local_connections") or 0),
        "concurrent_runtime_probe_count": int(report.get("concurrent_runtime_probe_count") or 0),
        "concurrent_runtime_probe_unique_connections": int(report.get("concurrent_runtime_probe_unique_connections") or 0),
        "concurrent_runtime_probe_connection_observations": connection_observations,
        "concurrent_runtime_probe_connection_ids": connection_ids,
        "concurrent_runtime_probe_connection_reuse_observed": report.get(
            "concurrent_runtime_probe_connection_reuse_observed"
        )
        is True,
        "postgres_visible_write_proof_pass": report.get("postgres_visible_write_proof_pass") is True,
    }


def blocker_actions(blockers: list[str]) -> list[str]:
    actions = {
        "artifact_manifest_missing": "create or provide the reviewed artifact manifest verification report",
        "artifact_manifest_invalid": "rerun artifact manifest verification against the reviewed cutover package",
        "readiness_report_missing": "run read-only cutover readiness before the manager execution gate",
        "readiness_report_failed": "resolve readiness blockers before PostgreSQL mutation or restart",
        "code_deploy_report_missing": "run deploy package extract with a backup directory before final cutover",
        "code_deploy_report_invalid": "fix deploy package extract evidence before PostgreSQL mutation or restart",
        "code_deploy_manifest_mismatch": "rerun deploy package extract and artifact verification from the same reviewed package manifest",
        "code_deploy_artifact_count_mismatch": "rerun deploy package extract and artifact verification from the same reviewed artifact allowlist",
        "local_preflight_suite_missing": "run the local PostgreSQL preflight suite before the manager execution gate",
        "local_preflight_suite_invalid": "fix local PostgreSQL preflight suite failures before the manager execution gate",
        "migration_report_missing": "run prepare_json_to_postgres.py and validate the migration report",
        "migration_report_invalid": "fix migration report blockers before import",
        "row_count_report_missing": "run import row-count parity after PostgreSQL import",
        "row_count_report_invalid": "fix PostgreSQL import row-count mismatches before env switch",
        "import_engine_report_missing": "run real PostgreSQL engine DDL/CSV import smoke before the manager execution gate",
        "import_engine_report_invalid": "fix real-engine PostgreSQL import smoke failures before production import",
        "row_count_schema_mismatch": "regenerate the import row-count report from the same migration report",
        "import_engine_schema_mismatch": "rerun real-engine import smoke against the final migration report and DDL",
        "import_engine_report_mismatch": "rerun real-engine import smoke against the exact final migration report",
        "import_engine_ddl_mismatch": "rerun real-engine import smoke against the exact final PostgreSQL DDL artifact",
        "import_engine_table_count_mismatch": "rerun real-engine import smoke against the final migration CSV artifact set",
        "precutover_report_missing": "run credential-free deployed-precutover smoke against the live service",
        "precutover_report_invalid": "fix the deployed-precutover report until its validator passes",
        "precutover_contract_not_production": "replace local pre-cutover contract evidence with live deployed-precutover evidence",
        "full_smoke_report_missing": "run post-switch deployed-postgres full smoke",
        "full_smoke_report_invalid": "fix the full-smoke report until its validator passes",
        "full_smoke_contract_not_production": "replace local full-smoke contract evidence with real deployed-postgres evidence",
        "non_secret_report": "remove secret-like markers from reports before sharing",
    }
    return [actions.get(item, f"resolve gate blocker: {item}") for item in blockers]


def build_gate_report(
    *,
    artifact_report: dict[str, Any] | None,
    artifact_load_status: str,
    readiness_report: dict[str, Any] | None,
    readiness_load_status: str,
    code_deploy_report: dict[str, Any] | None,
    code_deploy_load_status: str,
    local_preflight_report: dict[str, Any] | None,
    local_preflight_load_status: str,
    migration_report: dict[str, Any] | None,
    migration_load_status: str,
    row_count_report: dict[str, Any] | None,
    row_count_load_status: str,
    import_engine_report: dict[str, Any] | None,
    import_engine_load_status: str,
    precutover_report: dict[str, Any] | None,
    precutover_load_status: str,
    full_smoke_report: dict[str, Any] | None,
    full_smoke_load_status: str,
    expected_concurrent_accounts: int = 10,
) -> dict[str, Any]:
    artifacts = artifact_evidence(artifact_report, artifact_load_status)
    readiness = readiness_evidence(readiness_report, readiness_load_status)
    code_deploy = code_deploy_evidence(code_deploy_report, code_deploy_load_status)
    local_preflight = local_preflight_evidence(local_preflight_report, local_preflight_load_status)
    migration = migration_evidence(migration_report, migration_load_status)
    row_counts = row_count_evidence(row_count_report, row_count_load_status)
    import_engine = import_engine_evidence(import_engine_report, import_engine_load_status)
    precutover = precutover_evidence(precutover_report, precutover_load_status)
    full_smoke = full_smoke_evidence(
        full_smoke_report,
        full_smoke_load_status,
        expected_concurrent_accounts=expected_concurrent_accounts,
    )

    blockers: list[str] = []
    if artifacts["status"] == "missing":
        blockers.append("artifact_manifest_missing")
    elif not artifacts["passed"]:
        blockers.append("artifact_manifest_invalid")
    if readiness["status"] == "missing":
        blockers.append("readiness_report_missing")
    elif not readiness["passed"]:
        blockers.append("readiness_report_failed")
    if code_deploy["status"] == "missing":
        blockers.append("code_deploy_report_missing")
    elif not code_deploy["passed"]:
        blockers.append("code_deploy_report_invalid")
    if artifacts["passed"] and code_deploy["passed"]:
        if code_deploy.get("manifest_sha256") != artifacts.get("manifest_sha256"):
            blockers.append("code_deploy_manifest_mismatch")
        if code_deploy.get("artifact_count") != artifacts.get("artifact_count"):
            blockers.append("code_deploy_artifact_count_mismatch")
    if local_preflight["status"] == "missing":
        blockers.append("local_preflight_suite_missing")
    elif not local_preflight["passed"]:
        blockers.append("local_preflight_suite_invalid")
    if migration["status"] == "missing":
        blockers.append("migration_report_missing")
    elif not migration["passed"]:
        blockers.append("migration_report_invalid")
    if row_counts["status"] == "missing":
        blockers.append("row_count_report_missing")
    elif not row_counts["passed"]:
        blockers.append("row_count_report_invalid")
    if import_engine["status"] == "missing":
        blockers.append("import_engine_report_missing")
    elif not import_engine["passed"]:
        blockers.append("import_engine_report_invalid")
    if migration["passed"] and row_counts["passed"]:
        if row_counts.get("migration_schema_version") != migration.get("schema_version"):
            blockers.append("row_count_schema_mismatch")
    if migration["passed"] and import_engine["passed"]:
        if import_engine.get("migration_schema_version") != migration.get("schema_version"):
            blockers.append("import_engine_schema_mismatch")
        if import_engine.get("migration_report_sha256") != migration.get("report_sha256"):
            blockers.append("import_engine_report_mismatch")
        if import_engine.get("ddl_sha256") != migration.get("ddl_sha256"):
            blockers.append("import_engine_ddl_mismatch")
        if import_engine.get("checked_table_count") != migration.get("checked_table_count"):
            blockers.append("import_engine_table_count_mismatch")
    if precutover["status"] == "missing":
        blockers.append("precutover_report_missing")
    elif not precutover["passed"]:
        blockers.append("precutover_report_invalid")
    elif precutover["evidence_kind"] != "production":
        blockers.append("precutover_contract_not_production")
    if full_smoke["status"] == "missing":
        blockers.append("full_smoke_report_missing")
    elif not full_smoke["passed"]:
        blockers.append("full_smoke_report_invalid")
    elif full_smoke["evidence_kind"] != "production":
        blockers.append("full_smoke_contract_not_production")

    production_cutover_evidence_pass = (
        full_smoke.get("passed") is True
        and full_smoke.get("evidence_kind") == "production"
        and full_smoke.get("postgres_visible_write_proof_pass") is True
        and full_smoke.get("concurrent_successful_sessions") == expected_concurrent_accounts
        and full_smoke.get("concurrent_postgres_visible_sessions") == expected_concurrent_accounts
        and full_smoke.get("concurrent_worker_threads") == expected_concurrent_accounts
        and 1 <= int(full_smoke.get("concurrent_thread_local_connections") or 0) <= expected_concurrent_accounts
        and full_smoke.get("concurrent_runtime_probe_count") == expected_concurrent_accounts
        and full_smoke.get("concurrent_runtime_probe_unique_connections")
        == full_smoke.get("concurrent_thread_local_connections")
        and len(set(full_smoke.get("concurrent_runtime_probe_connection_ids") or []))
        == full_smoke.get("concurrent_runtime_probe_unique_connections")
        and len(full_smoke.get("concurrent_runtime_probe_connection_observations") or [])
        == expected_concurrent_accounts
    )
    final_acceptance_pass = (
        artifacts["passed"] is True
        and readiness["passed"] is True
        and code_deploy["passed"] is True
        and "code_deploy_manifest_mismatch" not in blockers
        and "code_deploy_artifact_count_mismatch" not in blockers
        and local_preflight["passed"] is True
        and migration["passed"] is True
        and row_counts["passed"] is True
        and import_engine["passed"] is True
        and "row_count_schema_mismatch" not in blockers
        and "import_engine_schema_mismatch" not in blockers
        and "import_engine_report_mismatch" not in blockers
        and "import_engine_ddl_mismatch" not in blockers
        and "import_engine_table_count_mismatch" not in blockers
        and precutover.get("evidence_kind") == "production"
        and production_cutover_evidence_pass
    )
    report: dict[str, Any] = {
        "mode": "postgres-cutover-gate-report",
        "expected_concurrent_accounts": expected_concurrent_accounts,
        "artifact_manifest": artifacts,
        "precutover_readiness": readiness,
        "code_deploy": code_deploy,
        "local_preflight_suite": local_preflight,
        "migration_report": migration,
        "import_row_counts": row_counts,
        "import_real_engine": import_engine,
        "precutover_http": precutover,
        "full_smoke": full_smoke,
        "production_cutover_evidence_pass": production_cutover_evidence_pass,
        "final_acceptance_pass": final_acceptance_pass,
        "blockers": blockers,
        "next_required_actions": blocker_actions(blockers),
        "notes": [
            "Contract reports are local shape checks only and do not prove production PostgreSQL cutover.",
            "The local preflight suite must pass before the manager execution gate, but it is not production cutover evidence.",
            "Code deploy extract evidence proves reviewed files were installed with a backup; it is not PostgreSQL runtime evidence.",
            "Import row-count parity must match the migration report before the runtime env switch.",
            "Real-engine import smoke must prove generated DDL and CSV artifacts load through PostgreSQL before production import.",
            "Final acceptance requires deployed-postgres full smoke with PostgreSQL-visible writes and 10 concurrent sessions.",
        ],
        "non_secret_report": True,
    }
    report["non_secret_report"] = has_no_secret_markers(report)
    if not report["non_secret_report"] and "non_secret_report" not in blockers:
        report["blockers"].append("non_secret_report")
        report["next_required_actions"] = blocker_actions(report["blockers"])
        report["final_acceptance_pass"] = False
        report["production_cutover_evidence_pass"] = False
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-verify-report", default="")
    parser.add_argument("--readiness-report", default="")
    parser.add_argument("--deploy-package-extract-report", default="")
    parser.add_argument("--local-preflight-suite-report", default="")
    parser.add_argument("--migration-report", default="")
    parser.add_argument("--row-count-report", default="")
    parser.add_argument("--import-engine-report", default="")
    parser.add_argument("--precutover-report", default="")
    parser.add_argument("--full-smoke-report", default="")
    parser.add_argument("--expected-concurrent-accounts", type=int, default=10)
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--strict-final",
        action="store_true",
        help="Exit non-zero unless final_acceptance_pass is true.",
    )
    return parser.parse_args(argv)


def optional_path(value: str) -> Path | None:
    value = value.strip()
    return Path(value) if value else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.expected_concurrent_accounts < 1:
        print("postgres cutover gate report error: expected concurrent accounts must be positive", file=sys.stderr)
        return 1
    artifact_report, artifact_status = load_json_report(optional_path(args.artifact_verify_report))
    readiness_report, readiness_status = load_json_report(optional_path(args.readiness_report))
    code_deploy_report, code_deploy_status = load_json_report(optional_path(args.deploy_package_extract_report))
    local_preflight_report, local_preflight_status = load_json_report(optional_path(args.local_preflight_suite_report))
    migration_report, migration_status = load_json_report(optional_path(args.migration_report))
    row_count_report, row_count_status = load_json_report(optional_path(args.row_count_report))
    import_engine_report, import_engine_status = load_json_report(optional_path(args.import_engine_report))
    precutover_report, precutover_status = load_json_report(optional_path(args.precutover_report))
    full_smoke_report, full_smoke_status = load_json_report(optional_path(args.full_smoke_report))
    report = build_gate_report(
        artifact_report=artifact_report,
        artifact_load_status=artifact_status,
        readiness_report=readiness_report,
        readiness_load_status=readiness_status,
        code_deploy_report=code_deploy_report,
        code_deploy_load_status=code_deploy_status,
        local_preflight_report=local_preflight_report,
        local_preflight_load_status=local_preflight_status,
        migration_report=migration_report,
        migration_load_status=migration_status,
        row_count_report=row_count_report,
        row_count_load_status=row_count_status,
        import_engine_report=import_engine_report,
        import_engine_load_status=import_engine_status,
        precutover_report=precutover_report,
        precutover_load_status=precutover_status,
        full_smoke_report=full_smoke_report,
        full_smoke_load_status=full_smoke_status,
        expected_concurrent_accounts=args.expected_concurrent_accounts,
    )
    if not report["non_secret_report"]:
        print("postgres cutover gate report error: non-secret report check failed", file=sys.stderr)
        return 1
    output = stable_json(report) + "\n"
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if args.strict_final and not report["final_acceptance_pass"]:
        print("postgres cutover gate report final acceptance failed", file=sys.stderr)
        return 1
    print("postgres cutover gate report generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
