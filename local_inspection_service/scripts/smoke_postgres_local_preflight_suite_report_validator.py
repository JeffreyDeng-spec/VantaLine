#!/usr/bin/env python3
"""Smoke-test the local PostgreSQL preflight suite report validator."""

from __future__ import annotations

import copy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.validate_postgres_local_preflight_suite_report import (  # noqa: E402
    LocalPreflightSuiteReportValidationError,
    REQUIRED_RESULT_NAMES,
    validate_local_preflight_suite_report,
)


def valid_report() -> dict[str, object]:
    return {
        "mode": "postgres-local-preflight-suite",
        "production_cutover_proof": False,
        "socket_free": True,
        "real_engine_required": True,
        "real_engine_pass": True,
        "service_restart_performed": False,
        "postgres_service_mutation_performed": False,
        "runtime_env_switch_performed": False,
        "required_pass": True,
        "failed_required": [],
        "result_count": len(REQUIRED_RESULT_NAMES),
        "results": [
            {
                "name": name,
                "required": True,
                "status": "pass",
                "returncode": 0,
                "duration_ms": 1,
                "command": ["python3", name.replace(" ", "_")],
                "stdout_tail": "",
                "stderr_tail": "",
            }
            for name in sorted(REQUIRED_RESULT_NAMES)
        ],
        "non_secret_report": True,
    }


def assert_validator_passes() -> None:
    summary = validate_local_preflight_suite_report(valid_report())
    if summary.get("result_count") != len(REQUIRED_RESULT_NAMES):
        raise AssertionError(f"unexpected validator summary: {summary}")


def assert_rejects(label: str, report: dict[str, object], expected_fragment: str) -> None:
    try:
        validate_local_preflight_suite_report(report)
    except LocalPreflightSuiteReportValidationError as exc:
        if expected_fragment not in str(exc):
            raise AssertionError(f"{label}: unexpected validation error: {exc}") from exc
        return
    raise AssertionError(f"{label}: validator unexpectedly accepted invalid report")


def assert_validator_rejects_missing_real_engine_requirement() -> None:
    report = valid_report()
    report["real_engine_required"] = False
    assert_rejects("missing real-engine requirement", report, "real_engine_required")

    report = valid_report()
    report["real_engine_pass"] = False
    assert_rejects("missing real-engine pass", report, "real_engine_pass")


def assert_validator_rejects_production_claims() -> None:
    report = valid_report()
    report["production_cutover_proof"] = True
    assert_rejects("production proof claim", report, "production_cutover_proof")

    report = valid_report()
    report["service_restart_performed"] = True
    assert_rejects("service restart claim", report, "service_restart_performed")


def assert_validator_rejects_missing_required_result() -> None:
    report = valid_report()
    results = copy.deepcopy(report["results"])
    if not isinstance(results, list):
        raise AssertionError("fixture results should be a list")
    report["results"] = [item for item in results if item.get("name") != "postgres import real-engine"]
    report["result_count"] = len(report["results"])
    assert_rejects("missing required result", report, "results missing required names")


def assert_validator_rejects_failed_required_result() -> None:
    report = valid_report()
    results = report["results"]
    if not isinstance(results, list):
        raise AssertionError("fixture results should be a list")
    for item in results:
        if isinstance(item, dict) and item.get("name") == "local fake-postgres full smoke":
            item["status"] = "fail"
            break
    report["required_pass"] = False
    report["failed_required"] = ["local fake-postgres full smoke"]
    assert_rejects("failed required result", report, "required_pass")


def assert_validator_rejects_secret_markers() -> None:
    report = valid_report()
    report["note"] = "DATABASE_URL=redacted"
    assert_rejects("secret marker", report, "forbidden marker")


def main() -> None:
    assert_validator_passes()
    assert_validator_rejects_missing_real_engine_requirement()
    assert_validator_rejects_production_claims()
    assert_validator_rejects_missing_required_result()
    assert_validator_rejects_failed_required_result()
    assert_validator_rejects_secret_markers()
    print("postgres local preflight suite report validator smoke passed")


if __name__ == "__main__":
    main()
