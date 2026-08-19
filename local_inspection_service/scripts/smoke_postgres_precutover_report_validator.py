#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.validate_postgres_precutover_report import (  # noqa: E402
    REQUIRED_ALLOWLIST_PATHS,
    PrecutoverReportValidationError,
    validate_precutover_report,
)


VALID_REPORT = {
    "mode": "deployed-precutover-contract",
    "base_url": "http://127.0.0.1:8765",
    "expected_store": "json",
    "observed_store": "json",
    "selected_store": "json",
    "endpoint_repository_wiring_pass": True,
    "credential_free_live_public_root_pass": True,
    "credential_free_live_static_bundle_pass": True,
    "json_default_http_parity_pass": True,
    "postgres_selected_failure_no_json_fallback_pass": True,
    "non_allowlisted_routes_unchanged": True,
    "credential_free_preflight": True,
    "require_no_postgres_service_env": True,
    "no_postgres_env_in_smoke_process": True,
    "non_secret_report": True,
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
    "notes": [
        "This mode proves only credential-free public root/static liveness plus local JSON-default selector shape.",
        "It does not prove authenticated live route activation.",
    ],
}


def expect_failure(report: dict[str, object], expected_message: str) -> None:
    try:
        validate_precutover_report(report, expected_mode="deployed-precutover-contract")
    except PrecutoverReportValidationError as exc:
        if expected_message not in str(exc):
            raise AssertionError(f"unexpected validation failure: {exc}") from exc
        return
    raise AssertionError("invalid pre-cutover report unexpectedly passed validation")


def main() -> None:
    validate_precutover_report(dict(VALID_REPORT), expected_mode="deployed-precutover-contract")

    missing_static = dict(VALID_REPORT)
    missing_static.pop("credential_free_live_static_bundle_pass", None)
    expect_failure(missing_static, "credential_free_live_static_bundle_pass must be true")

    full_smoke_mode = dict(VALID_REPORT)
    full_smoke_mode["mode"] = "deployed-postgres-contract"
    expect_failure(full_smoke_mode, "mode mismatch")

    secret_report = dict(VALID_REPORT)
    secret_report["detail"] = "DATABASE_URL=postgresql://secret.invalid/vantaline"
    expect_failure(secret_report, "forbidden marker")

    missing_allowlist_path = dict(VALID_REPORT)
    missing_allowlist_path["endpoint_allowlist"] = [
        item for item in VALID_REPORT["endpoint_allowlist"] if item["path"] != "/api/pipeline/tasks*"
    ]
    expect_failure(missing_allowlist_path, "endpoint_allowlist missing required paths")

    missing_image_job_path = dict(VALID_REPORT)
    missing_image_job_path["endpoint_allowlist"] = [
        item
        for item in VALID_REPORT["endpoint_allowlist"]
        if item["path"] != "/api/image-jobs* and /api/image-job-candidates*"
    ]
    expect_failure(missing_image_job_path, "endpoint_allowlist missing required paths")

    print("postgres pre-cutover report validator smoke passed")


if __name__ == "__main__":
    main()
