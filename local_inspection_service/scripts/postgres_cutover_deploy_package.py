#!/usr/bin/env python3
"""Build and verify a non-secret PostgreSQL cutover deploy package.

The package is a transport wrapper around the reviewed cutover artifact
manifest. It contains only allowlisted code, scripts, docs, and package
metadata; it does not include runtime data, reports, backups, env files, or
credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import time
from pathlib import Path, PurePosixPath
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.postgres_cutover_artifact_manifest import (
    DEFAULT_ARTIFACTS,
    ManifestError,
    build_manifest,
    load_manifest,
    manifest_digest,
    normalize_artifact_path,
    stable_json,
    validate_non_secret_manifest,
    verify_manifest,
)


PACKAGE_KIND = "vantaline-postgres-cutover-deploy-package"
PACKAGE_VERSION = 1
PACKAGE_METADATA_DIR = ".vantaline_postgres_cutover_package"
PACKAGE_MANIFEST_NAME = f"{PACKAGE_METADATA_DIR}/manifest.json"
PACKAGE_INSTALL_NAME = f"{PACKAGE_METADATA_DIR}/INSTALL.md"
PACKAGE_SHA256SUMS_NAME = f"{PACKAGE_METADATA_DIR}/sha256sums.txt"
FORBIDDEN_PACKAGE_MARKERS = (
    "postgresql://",
    "DATABASE_URL=",
    "VANTALINE_SMOKE_PASSWORD=",
    "password=",
    "vantaline_session=",
)


class PackageError(AssertionError):
    """Raised when a deploy package cannot be created or verified safely."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def artifact_digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def artifact_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_member_name(relative: str) -> str:
    return normalize_artifact_path(relative)


def validate_package_member_name(name: str) -> str:
    raw = str(name or "").strip().replace("\\", "/")
    require(raw, "package member name is empty")
    path = PurePosixPath(raw)
    require(not path.is_absolute(), f"package member must be relative: {raw}")
    require(".." not in path.parts, f"package member must not contain '..': {raw}")
    normalized = "/".join(part for part in path.parts if part not in {"", "."})
    require(normalized, "package member name is empty after normalization")
    if normalized.startswith(f"{PACKAGE_METADATA_DIR}/"):
        return normalized
    return normalize_artifact_path(normalized)


def non_secret_report(value: Any) -> bool:
    text = stable_json(value).lower()
    return not any(marker.lower() in text for marker in FORBIDDEN_PACKAGE_MARKERS)


def install_notes(manifest: dict[str, Any]) -> str:
    artifact_count = int(manifest.get("artifact_count") or 0)
    return "\n".join(
        (
            "# Vantaline PostgreSQL Cutover Deploy Package",
            "",
            "This package contains reviewed PostgreSQL cutover code, scripts, and docs only.",
            "It intentionally excludes runtime data, reports, backups, env files, and credentials.",
            "",
            f"Artifact count: {artifact_count}",
            "",
            "Target-host install shape:",
            "",
            "```bash",
            "# Run this from the reviewed source/staging tree that contains the deploy package tool.",
            "PYTHONPATH=. python3 local_inspection_service/scripts/postgres_cutover_deploy_package.py extract \\",
            "  --package /tmp/vantaline-postgres-cutover-deploy-package.tar.gz \\",
            "  --app-root /opt/vantaline/app \\",
            "  --backup-dir /opt/vantaline/backups/postgres-cutover-code-deploy \\",
            "  --report /tmp/vantaline_postgres_cutover_deploy_package_extract.json",
            "cd /opt/vantaline/app",
            "PYTHONPATH=/opt/vantaline/app /opt/vantaline/venv/bin/python \\",
            "  local_inspection_service/scripts/postgres_cutover_readiness.py \\",
            "  --app-root /opt/vantaline/app \\",
            "  --target-py /opt/vantaline/venv/bin/python \\",
            "  --postgres-env-file /etc/vantaline/postgres.env \\",
            "  --service vantaline \\",
            "  --report /tmp/vantaline_postgres_cutover_readiness.json",
            "```",
            "",
            "Do not run the destructive final cutover stages until a manager opens the",
            "execution gate and provides the private runtime credential file on the target host.",
            "If code-deploy validation fails, restore this package's code backup with:",
            "PYTHONPATH=. python3 local_inspection_service/scripts/postgres_cutover_deploy_package.py restore \\",
            "  --app-root /opt/vantaline/app \\",
            "  --backup-dir /opt/vantaline/backups/postgres-cutover-code-deploy \\",
            "  --report /tmp/vantaline_postgres_cutover_deploy_package_restore.json",
            "",
        )
    )


def sha256sums(manifest: dict[str, Any]) -> str:
    lines = []
    for item in manifest.get("artifacts", []):
        if not isinstance(item, dict):
            continue
        lines.append(f"{item.get('sha256')}  {item.get('path')}")
    return "\n".join(lines) + "\n"


def add_bytes(tar: tarfile.TarFile, name: str, payload: bytes) -> None:
    member_name = validate_package_member_name(name)
    info = tarfile.TarInfo(member_name)
    info.size = len(payload)
    info.mode = 0o644
    info.mtime = 0
    tar.addfile(info, io.BytesIO(payload))


def create_package(app_root: Path, package_path: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    app_root = app_root.resolve()
    manifest = build_manifest(app_root)
    package_path = package_path.resolve()
    package_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path is not None:
        manifest_path = manifest_path.resolve()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(stable_json(manifest) + "\n", encoding="utf-8")

    manifest_bytes = (stable_json(manifest) + "\n").encode("utf-8")
    install_bytes = install_notes(manifest).encode("utf-8")
    sha_bytes = sha256sums(manifest).encode("utf-8")
    with tarfile.open(package_path, "w:gz") as tar:
        for relative in DEFAULT_ARTIFACTS:
            normalized = package_member_name(relative)
            source = (app_root / normalized).resolve()
            require(source.is_relative_to(app_root), f"artifact escapes app root: {normalized}")
            require(source.is_file(), f"artifact missing: {normalized}")
            info = tar.gettarinfo(str(source), arcname=normalized)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            with source.open("rb") as handle:
                tar.addfile(info, handle)
        add_bytes(tar, PACKAGE_MANIFEST_NAME, manifest_bytes)
        add_bytes(tar, PACKAGE_INSTALL_NAME, install_bytes)
        add_bytes(tar, PACKAGE_SHA256SUMS_NAME, sha_bytes)

    package_sha = artifact_digest(package_path)
    report: dict[str, Any] = {
        "mode": "postgres-cutover-deploy-package-create",
        "package_kind": PACKAGE_KIND,
        "package_version": PACKAGE_VERSION,
        "created_at": int(time.time()),
        "package_path": str(package_path),
        "package_sha256": package_sha,
        "manifest_sha256": manifest_digest(manifest),
        "manifest_path": str(manifest_path) if manifest_path is not None else f"embedded:{PACKAGE_MANIFEST_NAME}",
        "artifact_count": manifest["artifact_count"],
        "metadata_entries": [PACKAGE_MANIFEST_NAME, PACKAGE_INSTALL_NAME, PACKAGE_SHA256SUMS_NAME],
        "non_secret_report": True,
    }
    report["non_secret_report"] = non_secret_report(report) and validate_non_secret_manifest(manifest)
    require(report["non_secret_report"], "package create report contains forbidden secret marker")
    return report


def read_package_members(package_path: Path) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    with tarfile.open(package_path, "r:gz") as tar:
        for info in tar.getmembers():
            name = validate_package_member_name(info.name)
            require(info.isfile(), f"package member must be a regular file: {name}")
            require(name not in members, f"duplicate package member: {name}")
            handle = tar.extractfile(info)
            require(handle is not None, f"cannot read package member: {name}")
            members[name] = handle.read()
    return members


def embedded_manifest(members: dict[str, bytes]) -> dict[str, Any]:
    payload = members.get(PACKAGE_MANIFEST_NAME)
    require(payload is not None, f"package missing embedded manifest: {PACKAGE_MANIFEST_NAME}")
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PackageError("embedded manifest is not valid JSON") from exc
    require(isinstance(manifest, dict), "embedded manifest root must be an object")
    return manifest


def verify_package(package_path: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    package_path = package_path.resolve()
    require(package_path.is_file(), f"package not found: {package_path}")
    members = read_package_members(package_path)
    manifest = load_manifest(manifest_path) if manifest_path is not None else embedded_manifest(members)
    require(manifest.get("manifest_kind") == "vantaline-postgres-cutover-artifacts", "manifest kind mismatch")
    require(validate_non_secret_manifest(manifest), "manifest contains forbidden secret marker")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list) and artifacts, "manifest artifacts must be a non-empty list")
    expected_paths: set[str] = set()
    failures: list[dict[str, str]] = []
    for item in artifacts:
        if not isinstance(item, dict):
            failures.append({"path": "<invalid>", "reason": "artifact entry is not an object"})
            continue
        try:
            relative = normalize_artifact_path(str(item.get("path") or ""))
            expected_paths.add(relative)
            payload = members.get(relative)
            require(payload is not None, "artifact missing from package")
            expected_size = int(item.get("size_bytes"))
            require(len(payload) == expected_size, f"size mismatch expected={expected_size} actual={len(payload)}")
            expected_sha = str(item.get("sha256") or "").strip().lower()
            require(artifact_digest_bytes(payload) == expected_sha, "sha256 mismatch")
        except Exception as exc:
            failures.append({"path": str(item.get("path") or "<invalid>"), "reason": str(exc)})
    extra_artifacts = sorted(
        name
        for name in members
        if not name.startswith(f"{PACKAGE_METADATA_DIR}/") and name not in expected_paths
    )
    if extra_artifacts:
        failures.append({"path": ",".join(extra_artifacts), "reason": "extra non-metadata package members"})
    metadata_entries_present = all(
        name in members for name in (PACKAGE_MANIFEST_NAME, PACKAGE_INSTALL_NAME, PACKAGE_SHA256SUMS_NAME)
    )
    if not metadata_entries_present:
        missing_metadata = [
            name
            for name in (PACKAGE_MANIFEST_NAME, PACKAGE_INSTALL_NAME, PACKAGE_SHA256SUMS_NAME)
            if name not in members
        ]
        failures.append({"path": ",".join(missing_metadata), "reason": "missing package metadata entries"})
    report: dict[str, Any] = {
        "mode": "postgres-cutover-deploy-package-verify",
        "package_kind": PACKAGE_KIND,
        "package_version": PACKAGE_VERSION,
        "package_path": str(package_path),
        "package_sha256": artifact_digest(package_path),
        "manifest_sha256": manifest_digest(manifest),
        "artifact_count": len(artifacts),
        "metadata_entries_present": metadata_entries_present,
        "verified": not failures,
        "failures": failures,
        "non_secret_report": True,
    }
    report["non_secret_report"] = non_secret_report(report)
    if not report["non_secret_report"]:
        report["verified"] = False
        report["failures"].append({"path": "<report>", "reason": "report contains forbidden secret marker"})
    return report


def backup_existing_targets(
    *,
    app_root: Path,
    backup_dir: Path,
    paths: list[str],
) -> dict[str, Any]:
    backup_dir = backup_dir.resolve()
    require(not backup_dir.is_relative_to(app_root), "backup_dir must not be inside app_root")
    backup_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for relative in paths:
        normalized = validate_package_member_name(relative)
        source = (app_root / normalized).resolve()
        require(source.is_relative_to(app_root), f"backup source escapes app root: {normalized}")
        backup_target = (backup_dir / normalized).resolve()
        require(backup_target.is_relative_to(backup_dir), f"backup target escapes backup dir: {normalized}")
        if source.exists():
            require(source.is_file(), f"backup source is not a regular file: {normalized}")
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            payload = source.read_bytes()
            backup_target.write_bytes(payload)
            entries.append(
                {
                    "path": normalized,
                    "status": "backed_up",
                    "size_bytes": len(payload),
                    "sha256": artifact_digest_bytes(payload),
                }
            )
        else:
            entries.append({"path": normalized, "status": "absent"})
    manifest = {
        "manifest_kind": "vantaline-postgres-cutover-code-backup",
        "manifest_version": 1,
        "backup_dir": str(backup_dir),
        "entry_count": len(entries),
        "entries": entries,
        "non_secret_manifest": True,
    }
    require(non_secret_report(manifest), "backup manifest contains forbidden secret marker")
    (backup_dir / "backup-manifest.json").write_text(stable_json(manifest) + "\n", encoding="utf-8")
    return manifest


def extract_package(
    package_path: Path,
    app_root: Path,
    manifest_path: Path | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    package_path = package_path.resolve()
    app_root = app_root.resolve()
    require(app_root.exists() and app_root.is_dir(), f"app root must already exist: {app_root}")
    members = read_package_members(package_path)
    embedded = embedded_manifest(members)
    manifest = embedded
    if manifest_path is not None:
        external = load_manifest(manifest_path)
        require(
            stable_json(external) == stable_json(embedded),
            "external manifest does not match embedded package manifest",
        )
        manifest = external
    verify_report = verify_package(package_path, manifest_path)
    require(verify_report.get("verified") is True, "package verification failed before extract")

    artifact_paths: list[str] = []
    for item in manifest.get("artifacts", []):
        if not isinstance(item, dict):
            raise PackageError("manifest artifact entry is not an object")
        artifact_paths.append(normalize_artifact_path(str(item.get("path") or "")))
    metadata_paths = [PACKAGE_MANIFEST_NAME, PACKAGE_INSTALL_NAME, PACKAGE_SHA256SUMS_NAME]
    backup_manifest: dict[str, Any] | None = None
    if backup_dir is not None:
        backup_manifest = backup_existing_targets(
            app_root=app_root,
            backup_dir=backup_dir,
            paths=[*artifact_paths, *metadata_paths],
        )

    written: list[str] = []
    for relative in artifact_paths:
        payload = members.get(relative)
        require(payload is not None, f"artifact missing from package: {relative}")
        target = (app_root / relative).resolve()
        require(target.is_relative_to(app_root), f"artifact target escapes app root: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        written.append(relative)
    for metadata_name in metadata_paths:
        payload = members.get(metadata_name)
        require(payload is not None, f"metadata missing from package: {metadata_name}")
        target = (app_root / metadata_name).resolve()
        require(target.is_relative_to(app_root), f"metadata target escapes app root: {metadata_name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    artifact_report = verify_manifest(app_root, manifest)
    require(artifact_report.get("verified") is True, "extracted app root does not satisfy artifact manifest")
    report: dict[str, Any] = {
        "mode": "postgres-cutover-deploy-package-extract",
        "package_kind": PACKAGE_KIND,
        "package_version": PACKAGE_VERSION,
        "package_path": str(package_path),
        "package_sha256": artifact_digest(package_path),
        "manifest_sha256": manifest_digest(manifest),
        "app_root": str(app_root),
        "artifact_count": len(written),
        "metadata_entries_written": [PACKAGE_MANIFEST_NAME, PACKAGE_INSTALL_NAME, PACKAGE_SHA256SUMS_NAME],
        "backup_performed": backup_manifest is not None,
        "backup_dir": str(backup_dir.resolve()) if backup_dir is not None else "",
        "backup_entry_count": int(backup_manifest.get("entry_count", 0)) if backup_manifest else 0,
        "backup_manifest": str((backup_dir.resolve() / "backup-manifest.json")) if backup_dir is not None else "",
        "artifact_manifest_verified_after_extract": True,
        "extracted": True,
        "non_secret_report": True,
    }
    report["non_secret_report"] = non_secret_report(report)
    require(report["non_secret_report"], "package extract report contains forbidden secret marker")
    return report


def load_backup_manifest(backup_dir: Path) -> dict[str, Any]:
    backup_dir = backup_dir.resolve()
    manifest_path = backup_dir / "backup-manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackageError(f"backup manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise PackageError(f"backup manifest is not valid JSON: {manifest_path}") from exc
    require(isinstance(payload, dict), "backup manifest root must be an object")
    require(payload.get("manifest_kind") == "vantaline-postgres-cutover-code-backup", "backup manifest kind mismatch")
    require(payload.get("manifest_version") == 1, "backup manifest version mismatch")
    require(non_secret_report(payload), "backup manifest contains forbidden secret marker")
    return payload


def restore_package_backup(app_root: Path, backup_dir: Path) -> dict[str, Any]:
    app_root = app_root.resolve()
    backup_dir = backup_dir.resolve()
    require(app_root.exists() and app_root.is_dir(), f"app root must already exist: {app_root}")
    require(backup_dir.exists() and backup_dir.is_dir(), f"backup dir must exist: {backup_dir}")
    require(not backup_dir.is_relative_to(app_root), "backup_dir must not be inside app_root")
    manifest = load_backup_manifest(backup_dir)
    entries = manifest.get("entries")
    require(isinstance(entries, list), "backup manifest entries must be a list")
    restored = 0
    removed_absent = 0
    skipped_absent = 0
    for item in entries:
        require(isinstance(item, dict), "backup manifest entry must be an object")
        relative = validate_package_member_name(str(item.get("path") or ""))
        status = str(item.get("status") or "")
        target = (app_root / relative).resolve()
        require(target.is_relative_to(app_root), f"restore target escapes app root: {relative}")
        if status == "backed_up":
            backup_source = (backup_dir / relative).resolve()
            require(backup_source.is_relative_to(backup_dir), f"restore source escapes backup dir: {relative}")
            require(backup_source.is_file(), f"backup source missing: {relative}")
            payload = backup_source.read_bytes()
            expected_sha = str(item.get("sha256") or "").strip().lower()
            require(artifact_digest_bytes(payload) == expected_sha, f"backup sha256 mismatch: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            restored += 1
        elif status == "absent":
            if target.exists():
                require(target.is_file(), f"absent restore target is not a regular file: {relative}")
                target.unlink()
                removed_absent += 1
            else:
                skipped_absent += 1
        else:
            raise PackageError(f"unknown backup entry status for {relative}: {status}")
    report: dict[str, Any] = {
        "mode": "postgres-cutover-deploy-package-restore",
        "package_kind": PACKAGE_KIND,
        "package_version": PACKAGE_VERSION,
        "app_root": str(app_root),
        "backup_dir": str(backup_dir),
        "backup_manifest": str(backup_dir / "backup-manifest.json"),
        "entry_count": len(entries),
        "restored_count": restored,
        "removed_absent_count": removed_absent,
        "skipped_absent_count": skipped_absent,
        "restored": True,
        "non_secret_report": True,
    }
    report["non_secret_report"] = non_secret_report(report)
    require(report["non_secret_report"], "package restore report contains forbidden secret marker")
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="Create a deploy tarball from the app root")
    create.add_argument("--app-root", default=".")
    create.add_argument("--package", required=True)
    create.add_argument("--manifest", default="")
    create.add_argument("--report", default="")
    verify = subparsers.add_parser("verify", help="Verify a deploy tarball without extracting it")
    verify.add_argument("--package", required=True)
    verify.add_argument("--manifest", default="")
    verify.add_argument("--report", default="")
    extract = subparsers.add_parser("extract", help="Verify and safely extract a deploy tarball into an existing app root")
    extract.add_argument("--package", required=True)
    extract.add_argument("--app-root", required=True)
    extract.add_argument("--manifest", default="")
    extract.add_argument("--backup-dir", default="")
    extract.add_argument("--report", default="")
    restore = subparsers.add_parser("restore", help="Restore files from a deploy package backup manifest")
    restore.add_argument("--app-root", required=True)
    restore.add_argument("--backup-dir", required=True)
    restore.add_argument("--report", default="")
    return parser.parse_args(argv)


def emit_report(report: dict[str, Any], path: str) -> None:
    output = stable_json(report) + "\n"
    if path:
        report_path = Path(path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "create":
            report = create_package(
                Path(args.app_root),
                Path(args.package),
                Path(args.manifest) if args.manifest else None,
            )
            emit_report(report, args.report)
            print("postgres cutover deploy package created")
            return 0
        if args.command == "extract":
            report = extract_package(
                Path(args.package),
                Path(args.app_root),
                Path(args.manifest) if args.manifest else None,
                Path(args.backup_dir) if args.backup_dir else None,
            )
            emit_report(report, args.report)
            print("postgres cutover deploy package extracted")
            return 0
        if args.command == "restore":
            report = restore_package_backup(
                Path(args.app_root),
                Path(args.backup_dir),
            )
            emit_report(report, args.report)
            print("postgres cutover deploy package backup restored")
            return 0
        report = verify_package(
            Path(args.package),
            Path(args.manifest) if args.manifest else None,
        )
        emit_report(report, args.report)
        if report["verified"]:
            print("postgres cutover deploy package verification passed")
            return 0
        print("postgres cutover deploy package verification failed")
        return 1
    except (ManifestError, PackageError) as exc:
        print(f"postgres cutover deploy package error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
