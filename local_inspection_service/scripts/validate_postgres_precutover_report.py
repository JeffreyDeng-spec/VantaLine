#!/usr/bin/env python3
"""Validate a deployed pre-cutover PostgreSQL readiness report.

This validator is read-only and validates the report emitted by
`smoke_postgres_cutover_full.py --mode deployed-precutover`. It intentionally
does not validate authenticated live routes or PostgreSQL-visible writes; those
belong to the post-switch full-smoke validator.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PRECUTOVER_MODES = frozenset({"deployed-precutover", "deployed-precutover-contract"})

REQUIRED_TRUE_FIELDS = (
    "endpoint_repository_wiring_pass",
    "credential_free_live_public_root_pass",
    "credential_free_live_static_bundle_pass",
    "json_default_http_parity_pass",
    "postgres_selected_failure_no_json_fallback_pass",
    "non_allowlisted_routes_unchanged",
    "credential_free_preflight",
    "require_no_postgres_service_env",
    "no_postgres_env_in_smoke_process",
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
FORBIDDEN_REPORT_MARKERS = ("DATABASE_URL=", "postgresql://", "password", "cookie", "vantaline_session")


class PrecutoverReportValidationError(AssertionError):
    """Raised when the pre-cutover report does not satisfy the gate."""


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PrecutoverReportValidationError(message)


def load_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PrecutoverReportValidationError(f"report file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PrecutoverReportValidationError(f"report is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise PrecutoverReportValidationError("report root must be a JSON object")
    return payload


def validate_no_secret_markers(report: dict[str, Any]) -> None:
    text = stable_json(report).lower()
    for marker in FORBIDDEN_REPORT_MARKERS:
        require(marker.lower() not in text, f"report contains forbidden marker: {marker}")


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


def validate_precutover_report(report: dict[str, Any], *, expected_mode: str) -> None:
    mode = str(report.get("mode") or "")
    if expected_mode:
        require(mode == expected_mode, f"mode mismatch: expected {expected_mode}, got {mode}")
    else:
        require(mode in PRECUTOVER_MODES, f"mode must be one of {sorted(PRECUTOVER_MODES)}, got {mode!r}")

    require(str(report.get("base_url") or "").startswith(("http://", "https://")), "base_url must be an HTTP URL")
    require(report.get("expected_store") == "json", "expected_store must be json")
    require(report.get("observed_store") == "json", "observed_store must be json")
    if "selected_store" in report:
        require(report.get("selected_store") == "json", "selected_store must be json")

    for field in REQUIRED_TRUE_FIELDS:
        require(report.get(field) is True, f"{field} must be true")

    notes = report.get("notes")
    require(isinstance(notes, list) and notes, "notes must explain the pre-cutover proof boundary")
    note_text = " ".join(str(item) for item in notes).lower()
    require("does not prove authenticated" in note_text, "notes must state that authenticated proof is not covered")

    validate_allowlist(report)
    validate_no_secret_markers(report)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Path to deployed pre-cutover report JSON")
    parser.add_argument(
        "--expected-mode",
        default="",
        choices=("", "deployed-precutover", "deployed-precutover-contract"),
        help="Require a specific pre-cutover mode",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        report = load_report(Path(args.report))
        validate_precutover_report(report, expected_mode=args.expected_mode)
    except PrecutoverReportValidationError as exc:
        print(f"postgres pre-cutover report validation failed: {exc}", file=sys.stderr)
        return 1
    print("postgres pre-cutover report validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
