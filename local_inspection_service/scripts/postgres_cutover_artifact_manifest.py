#!/usr/bin/env python3
"""Create or verify a non-secret PostgreSQL cutover artifact manifest.

The manifest covers reviewed code, scripts, and docs required by the final
PostgreSQL migration/cutover gate. It intentionally excludes runtime data,
reports, backups, env files, and any local secret material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_APP_ROOT = Path(".")

DEFAULT_ARTIFACTS = (
    "local_inspection_service/server.py",
    "local_inspection_service/storage/__init__.py",
    "local_inspection_service/storage/schema.py",
    "local_inspection_service/storage/json_loader.py",
    "local_inspection_service/storage/postgres_schema.py",
    "local_inspection_service/storage/runtime_selector.py",
    "local_inspection_service/storage/postgres_runtime_repository.py",
    "local_inspection_service/storage/runtime_records.py",
    "local_inspection_service/scripts/migrate_json_to_sqlite.py",
    "local_inspection_service/scripts/prepare_json_to_postgres.py",
    "local_inspection_service/scripts/smoke_data_layer_migration.py",
    "local_inspection_service/scripts/smoke_postgres_migration_packet.py",
    "local_inspection_service/scripts/smoke_postgres_schema_real_engine.py",
    "local_inspection_service/scripts/smoke_postgres_import_real_engine.py",
    "local_inspection_service/scripts/smoke_runtime_store_selector.py",
    "local_inspection_service/scripts/smoke_postgres_runtime_repository.py",
    "local_inspection_service/scripts/smoke_endpoint_runtime_store_probe.py",
    "local_inspection_service/scripts/smoke_postgres_endpoint_source_contract.py",
    "local_inspection_service/scripts/postgres_cutover_artifact_manifest.py",
    "local_inspection_service/scripts/smoke_postgres_cutover_artifact_manifest.py",
    "local_inspection_service/scripts/postgres_cutover_deploy_package.py",
    "local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py",
    "local_inspection_service/scripts/postgres_cutover_readiness.py",
    "local_inspection_service/scripts/smoke_postgres_cutover_readiness.py",
    "local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py",
    "local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py",
    "local_inspection_service/scripts/smoke_postgres_local_preflight_suite_report_validator.py",
    "local_inspection_service/scripts/smoke_postgres_cutover_full.py",
    "local_inspection_service/scripts/postgres_cutover_gate_report.py",
    "local_inspection_service/scripts/smoke_postgres_cutover_gate_report.py",
    "local_inspection_service/scripts/validate_postgres_migration_report.py",
    "local_inspection_service/scripts/postgres_import_row_count_report.py",
    "local_inspection_service/scripts/smoke_postgres_import_row_count_report.py",
    "local_inspection_service/scripts/smoke_postgres_final_cutover_packet_docs.py",
    "local_inspection_service/scripts/validate_postgres_precutover_report.py",
    "local_inspection_service/scripts/smoke_postgres_precutover_report_validator.py",
    "local_inspection_service/scripts/validate_postgres_full_smoke_report.py",
    "local_inspection_service/scripts/smoke_postgres_full_smoke_report_validator.py",
    "local_inspection_service/docs/data-layer-migration.md",
    "local_inspection_service/docs/postgres-migration-runbook.md",
    "local_inspection_service/docs/postgres-endpoint-integration-accepted.md",
    "local_inspection_service/docs/postgres-final-migration-cutover-execution-packet.md",
)

FORBIDDEN_PARTS = {
    ".git",
    "data",
    "backups",
    "__pycache__",
}
FORBIDDEN_SUFFIXES = (
    ".env",
    ".local",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".jsonl",
)
FORBIDDEN_NAME_MARKERS = (
    "secret",
    "credential",
    "password",
    "token",
)
FORBIDDEN_MANIFEST_MARKERS = (
    "postgresql://",
    "DATABASE_URL=",
    "password=",
    "vantaline_session=",
)


class ManifestError(AssertionError):
    """Raised when an artifact manifest cannot be created or verified safely."""


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def normalize_artifact_path(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    require(raw, "artifact path is empty")
    path = PurePosixPath(raw)
    require(not path.is_absolute(), f"artifact path must be relative: {raw}")
    require(".." not in path.parts, f"artifact path must not contain '..': {raw}")
    parts = tuple(part for part in path.parts if part not in {"", "."})
    require(parts, "artifact path is empty after normalization")
    lower_parts = {part.lower() for part in parts}
    forbidden_parts = sorted(lower_parts.intersection(FORBIDDEN_PARTS))
    require(not forbidden_parts, f"artifact path contains forbidden directory: {raw}")
    name_lower = parts[-1].lower()
    require(not any(name_lower.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES), f"forbidden artifact suffix: {raw}")
    require(not any(marker in name_lower for marker in FORBIDDEN_NAME_MARKERS), f"forbidden artifact name marker: {raw}")
    return "/".join(parts)


def artifact_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_digest(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(stable_json(manifest).encode("utf-8")).hexdigest()


def build_manifest(app_root: Path, artifacts: tuple[str, ...] = DEFAULT_ARTIFACTS) -> dict[str, Any]:
    app_root = app_root.resolve()
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_relative in artifacts:
        relative = normalize_artifact_path(raw_relative)
        require(relative not in seen, f"duplicate artifact path: {relative}")
        seen.add(relative)
        path = (app_root / relative).resolve()
        require(path.is_relative_to(app_root), f"artifact escapes app root: {relative}")
        require(path.is_file(), f"artifact file not found: {relative}")
        entries.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": artifact_digest(path),
            }
        )
    manifest = {
        "manifest_kind": "vantaline-postgres-cutover-artifacts",
        "manifest_version": 1,
        "artifact_count": len(entries),
        "artifacts": entries,
        "non_secret_manifest": True,
    }
    manifest["non_secret_manifest"] = validate_non_secret_manifest(manifest)
    require(manifest["non_secret_manifest"], "manifest contains forbidden secret marker")
    return manifest


def validate_non_secret_manifest(manifest: dict[str, Any]) -> bool:
    text = stable_json(manifest).lower()
    return not any(marker.lower() in text for marker in FORBIDDEN_MANIFEST_MARKERS)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {path}") from exc
    require(isinstance(payload, dict), "manifest root must be an object")
    return payload


def verify_manifest(app_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    app_root = app_root.resolve()
    require(manifest.get("manifest_kind") == "vantaline-postgres-cutover-artifacts", "manifest kind mismatch")
    require(manifest.get("manifest_version") == 1, "manifest version mismatch")
    require(manifest.get("non_secret_manifest") is True, "manifest must declare non_secret_manifest=true")
    require(validate_non_secret_manifest(manifest), "manifest contains forbidden secret marker")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list) and artifacts, "manifest artifacts must be a non-empty list")
    expected_count = manifest.get("artifact_count")
    require(expected_count == len(artifacts), "manifest artifact_count mismatch")

    failures: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            failures.append({"path": "<invalid>", "reason": "artifact entry is not an object"})
            continue
        try:
            relative = normalize_artifact_path(str(item.get("path") or ""))
            require(relative not in seen, f"duplicate artifact path: {relative}")
            seen.add(relative)
            expected_sha = str(item.get("sha256") or "").strip().lower()
            require(len(expected_sha) == 64 and all(ch in "0123456789abcdef" for ch in expected_sha), "invalid sha256")
            expected_size = int(item.get("size_bytes"))
            path = (app_root / relative).resolve()
            require(path.is_relative_to(app_root), f"artifact escapes app root: {relative}")
            require(path.is_file(), "file missing")
            actual_size = path.stat().st_size
            actual_sha = artifact_digest(path)
            require(actual_size == expected_size, f"size mismatch expected={expected_size} actual={actual_size}")
            require(actual_sha == expected_sha, "sha256 mismatch")
        except Exception as exc:
            failures.append({"path": str(item.get("path") if isinstance(item, dict) else "<invalid>"), "reason": str(exc)})
    return {
        "mode": "postgres-cutover-artifact-manifest-verify",
        "artifact_count": len(artifacts),
        "manifest_sha256": manifest_digest(manifest),
        "verified": not failures,
        "failures": failures,
        "non_secret_report": True,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="Create a manifest from the current app root")
    create.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    create.add_argument("--manifest", required=True)
    verify = subparsers.add_parser("verify", help="Verify an app root against a manifest")
    verify.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--report", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "create":
            manifest = build_manifest(Path(args.app_root))
            output = stable_json(manifest) + "\n"
            manifest_path = Path(args.manifest)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(output, encoding="utf-8")
            print("postgres cutover artifact manifest created")
            return 0
        manifest = load_manifest(Path(args.manifest))
        report = verify_manifest(Path(args.app_root), manifest)
        output = stable_json(report) + "\n"
        if args.report:
            report_path = Path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        if report["verified"]:
            print("postgres cutover artifact manifest verification passed")
            return 0
        print("postgres cutover artifact manifest verification failed", file=sys.stderr)
        return 1
    except ManifestError as exc:
        print(f"postgres cutover artifact manifest error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
