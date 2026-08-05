#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import tarfile
import tempfile
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.postgres_cutover_artifact_manifest import (  # noqa: E402
    load_manifest,
    verify_manifest,
)
from local_inspection_service.scripts.postgres_cutover_deploy_package import (  # noqa: E402
    PACKAGE_INSTALL_NAME,
    PACKAGE_MANIFEST_NAME,
    PackageError,
    create_package,
    extract_package,
    restore_package_backup,
    verify_package,
)


def assert_package_round_trip_passes() -> tuple[Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_cutover_package_pass_"))
    package_path = temp_root / "vantaline-postgres-cutover-deploy-package.tar.gz"
    manifest_path = temp_root / "manifest.json"
    report = create_package(ROOT, package_path, manifest_path)
    if report.get("non_secret_report") is not True:
        raise AssertionError(f"create report should be non-secret: {report}")
    manifest_sha = str(report.get("manifest_sha256") or "")
    if len(manifest_sha) != 64 or any(char not in "0123456789abcdef" for char in manifest_sha):
        raise AssertionError(f"create report should include manifest_sha256: {report}")
    if report.get("artifact_count", 0) <= 0:
        raise AssertionError(f"package should include artifacts: {report}")
    verify_report = verify_package(package_path, manifest_path)
    if verify_report.get("verified") is not True:
        raise AssertionError(f"expected package verify to pass: {verify_report}")
    if verify_report.get("manifest_sha256") != manifest_sha:
        raise AssertionError(f"package verify report should match create manifest sha: {verify_report}")
    embedded_verify_report = verify_package(package_path)
    if embedded_verify_report.get("verified") is not True:
        raise AssertionError(f"expected embedded-manifest package verify to pass: {embedded_verify_report}")
    if embedded_verify_report.get("manifest_sha256") != manifest_sha:
        raise AssertionError(f"embedded package verify report should match create manifest sha: {embedded_verify_report}")

    extract_root = temp_root / "extracted_app"
    extract_root.mkdir(parents=True)
    old_server = extract_root / "local_inspection_service" / "server.py"
    old_server.parent.mkdir(parents=True, exist_ok=True)
    old_payload = b"# old server before package extract\n"
    old_server.write_bytes(old_payload)
    backup_dir = temp_root / "backup"
    extract_report = extract_package(package_path, extract_root, manifest_path, backup_dir)
    if extract_report.get("extracted") is not True:
        raise AssertionError(f"expected package extract to pass: {extract_report}")
    if extract_report.get("backup_performed") is not True:
        raise AssertionError(f"expected package extract backup to run: {extract_report}")
    if extract_report.get("manifest_sha256") != manifest_sha:
        raise AssertionError(f"extract report should match package manifest sha: {extract_report}")
    backup_manifest_path = backup_dir / "backup-manifest.json"
    if not backup_manifest_path.is_file():
        raise AssertionError(f"expected backup manifest: {backup_manifest_path}")
    backup_manifest = json.loads(backup_manifest_path.read_text(encoding="utf-8"))
    backup_entries = {
        str(item.get("path")): item
        for item in backup_manifest.get("entries", [])
        if isinstance(item, dict)
    }
    server_backup = backup_entries.get("local_inspection_service/server.py")
    if not server_backup or server_backup.get("status") != "backed_up":
        raise AssertionError(f"server.py backup entry missing: {backup_manifest}")
    if (backup_dir / "local_inspection_service" / "server.py").read_bytes() != old_payload:
        raise AssertionError("server.py backup did not preserve previous content")
    manifest = load_manifest(extract_root / PACKAGE_MANIFEST_NAME)
    artifact_report = verify_manifest(extract_root, manifest)
    if artifact_report.get("verified") is not True:
        raise AssertionError(f"extracted package did not satisfy artifact manifest: {artifact_report}")
    package_only_path = extract_root / "local_inspection_service" / "storage" / "postgres_schema.py"
    if not package_only_path.is_file():
        raise AssertionError(f"expected package-only file after extract: {package_only_path}")
    restore_report = restore_package_backup(extract_root, backup_dir)
    if restore_report.get("restored") is not True:
        raise AssertionError(f"expected package backup restore to pass: {restore_report}")
    if old_server.read_bytes() != old_payload:
        raise AssertionError("restore did not recover previous server.py content")
    if package_only_path.exists():
        raise AssertionError("restore did not remove file that was absent before extract")
    return package_path, manifest_path


def assert_package_detects_manifest_mismatch(package_path: Path, manifest_path: Path) -> None:
    manifest = load_manifest(manifest_path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise AssertionError(f"fixture manifest missing artifacts: {manifest}")
    first = artifacts[0]
    if not isinstance(first, dict):
        raise AssertionError(f"fixture manifest artifact is invalid: {first}")
    first["sha256"] = "0" * 64
    mismatch_path = manifest_path.parent / "manifest-mismatch.json"
    mismatch_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    report = verify_package(package_path, mismatch_path)
    if report.get("verified") is not False:
        raise AssertionError(f"expected package manifest mismatch to fail: {report}")
    failures = report.get("failures")
    if not isinstance(failures, list) or not failures:
        raise AssertionError(f"manifest mismatch did not report failures: {report}")


def assert_package_rejects_missing_metadata(package_path: Path, manifest_path: Path) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_cutover_package_missing_metadata_"))
    broken_path = temp_root / "missing-metadata.tar.gz"
    with tarfile.open(package_path, "r:gz") as source, tarfile.open(broken_path, "w:gz") as target:
        for member in source.getmembers():
            if member.name == PACKAGE_INSTALL_NAME:
                continue
            handle = source.extractfile(member)
            if handle is None:
                raise AssertionError(f"cannot read fixture package member: {member.name}")
            payload = handle.read()
            info = tarfile.TarInfo(member.name)
            info.size = len(payload)
            info.mode = member.mode
            info.mtime = member.mtime
            target.addfile(info, io.BytesIO(payload))
    report = verify_package(broken_path, manifest_path)
    if report.get("verified") is not False:
        raise AssertionError(f"expected missing metadata to fail package verify: {report}")
    failures = report.get("failures")
    if not isinstance(failures, list) or not any("metadata" in str(item.get("reason", "")) for item in failures if isinstance(item, dict)):
        raise AssertionError(f"missing metadata failure was not reported: {report}")


def assert_package_rejects_unsafe_member() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_cutover_package_unsafe_"))
    package_path = temp_root / "unsafe.tar.gz"
    with tarfile.open(package_path, "w:gz") as tar:
        payload = b"nope"
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    try:
        verify_package(package_path)
    except PackageError as exc:
        if "must not contain '..'" not in str(exc):
            raise AssertionError(f"unexpected unsafe-member error: {exc}") from exc
        return
    raise AssertionError("unsafe package member was unexpectedly accepted")


def main() -> None:
    package_path, manifest_path = assert_package_round_trip_passes()
    assert_package_detects_manifest_mismatch(package_path, manifest_path)
    assert_package_rejects_missing_metadata(package_path, manifest_path)
    assert_package_rejects_unsafe_member()
    print("postgres cutover deploy package smoke passed")


if __name__ == "__main__":
    main()
