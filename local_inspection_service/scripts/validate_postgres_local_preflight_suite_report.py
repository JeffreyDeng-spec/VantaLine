#!/usr/bin/env python3
"""Validate the socket-free local PostgreSQL preflight suite report.

This validator is read-only. It validates the JSON report emitted by
`smoke_postgres_local_preflight_suite.py --require-real-engine`; it does not
prove production cutover, PostgreSQL service mutation, env switching, or live
HTTP behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_RESULT_NAMES = frozenset(
    {
        "runtime selector",
        "postgres runtime repository",
        "postgres endpoint source contract",
        "endpoint runtime-store probe",
        "postgres migration packet",
        "postgres import row-count report",
        "postgres precutover report validator",
        "postgres full-smoke report validator",
        "postgres local preflight suite report validator",
        "postgres cutover deploy package",
        "postgres cutover gate report",
        "local fake-postgres full smoke",
        "postgres schema real-engine",
        "postgres import real-engine",
    }
)
FORBIDDEN_REPORT_MARKERS = (
    "DATABASE_URL=",
    "postgresql://",
    "VANTALINE_SMOKE_PASSWORD=",
    "password=",
    "password_hash",
    "sha256$",
    "cookie",
    "vantaline_session=",
)


class LocalPreflightSuiteReportValidationError(AssertionError):
    """Raised when the local preflight suite report fails the gate."""


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LocalPreflightSuiteReportValidationError(message)


def load_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LocalPreflightSuiteReportValidationError(f"report file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LocalPreflightSuiteReportValidationError(f"report is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise LocalPreflightSuiteReportValidationError("report root must be a JSON object")
    return payload


def validate_no_secret_markers(report: dict[str, Any]) -> None:
    text = stable_json(report).lower()
    for marker in FORBIDDEN_REPORT_MARKERS:
        require(marker.lower() not in text, f"report contains forbidden marker: {marker}")


def validate_results(report: dict[str, Any]) -> dict[str, Any]:
    results = report.get("results")
    require(isinstance(results, list) and bool(results), "results must be a non-empty list")
    require(report.get("result_count") == len(results), "result_count must equal results length")

    required_seen: set[str] = set()
    failed_required: list[str] = []
    for index, item in enumerate(results):
        require(isinstance(item, dict), f"results[{index}] must be an object")
        name = str(item.get("name") or "").strip()
        require(bool(name), f"results[{index}].name is required")
        status = str(item.get("status") or "").strip()
        require(status in {"pass", "fail", "skip"}, f"results[{index}].status has unexpected value: {status!r}")
        required = item.get("required") is True
        if required:
            required_seen.add(name)
            if status != "pass":
                failed_required.append(name)
        if name in REQUIRED_RESULT_NAMES:
            require(required, f"required result {name!r} must be marked required")
            require(status == "pass", f"required result {name!r} must pass")

    missing = sorted(REQUIRED_RESULT_NAMES - required_seen)
    require(not missing, "results missing required names: " + ",".join(missing))
    require(not failed_required, "required results failed: " + ",".join(failed_required))
    return {
        "result_count": len(results),
        "required_result_count": len(required_seen),
        "required_result_names": sorted(required_seen),
    }


def validate_local_preflight_suite_report(report: dict[str, Any]) -> dict[str, Any]:
    require(report.get("mode") == "postgres-local-preflight-suite", "mode must be postgres-local-preflight-suite")
    require(report.get("required_pass") is True, "required_pass must be true")
    require(report.get("production_cutover_proof") is False, "production_cutover_proof must be false")
    require(report.get("socket_free") is True, "socket_free must be true")
    require(report.get("real_engine_required") is True, "real_engine_required must be true")
    require(report.get("real_engine_pass") is True, "real_engine_pass must be true")
    require(report.get("service_restart_performed") is False, "service_restart_performed must be false")
    require(report.get("postgres_service_mutation_performed") is False, "postgres_service_mutation_performed must be false")
    require(report.get("runtime_env_switch_performed") is False, "runtime_env_switch_performed must be false")
    require(report.get("non_secret_report") is True, "non_secret_report must be true")
    require(report.get("failed_required") == [], "failed_required must be an empty list")

    result_summary = validate_results(report)
    validate_no_secret_markers(report)
    return {
        "result_count": result_summary["result_count"],
        "required_result_count": result_summary["required_result_count"],
        "real_engine_required": True,
        "real_engine_pass": True,
        "production_cutover_proof": False,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Path to local preflight suite report JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        validate_local_preflight_suite_report(load_report(Path(args.report)))
    except LocalPreflightSuiteReportValidationError as exc:
        print(f"postgres local preflight suite report validation failed: {exc}", file=sys.stderr)
        return 1
    print("postgres local preflight suite report validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
