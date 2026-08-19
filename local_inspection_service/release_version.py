"""Read-only release identity and PLC protocol consistency checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def release_version_status(root: Path, expected_protocol: str) -> dict[str, Any]:
    version_path = root / "VERSION.json"
    try:
        document = json.loads(version_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        document = {}

    backend_protocol = str(document.get("backend_protocol") or "")
    frontend_protocol = str(document.get("frontend_protocol") or "")
    bundle_name = str(document.get("frontend_bundle") or "")
    expected_sha = str(document.get("frontend_bundle_sha256") or "").lower()
    release = str(document.get("release") or "unknown")
    bundle_ok = True
    if release != "development" or bundle_name or expected_sha:
        bundle_path = root / "local_inspection_service" / "frontend" / "dist-production" / "assets" / bundle_name
        try:
            actual_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        except OSError:
            actual_sha = ""
        bundle_ok = bool(bundle_name and expected_sha and actual_sha == expected_sha)

    consistent = bool(
        document
        and backend_protocol == expected_protocol
        and frontend_protocol == expected_protocol
        and bundle_ok
    )
    return {
        "release": release,
        "git_commit": str(document.get("git_commit") or "unknown"),
        "built_at": str(document.get("built_at") or "unknown"),
        "backend_protocol": backend_protocol or "unknown",
        "frontend_protocol": frontend_protocol or "unknown",
        "consistent": consistent,
    }
