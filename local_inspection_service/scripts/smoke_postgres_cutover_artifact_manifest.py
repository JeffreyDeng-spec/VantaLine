#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.scripts.postgres_cutover_artifact_manifest import (  # noqa: E402
    DEFAULT_ARTIFACTS,
    ManifestError,
    build_manifest,
    verify_manifest,
)


def copy_artifacts(source_root: Path, target_root: Path) -> None:
    for relative in DEFAULT_ARTIFACTS:
        source = source_root / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def assert_manifest_round_trip_passes() -> dict[str, object]:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_cutover_manifest_pass_"))
    copy_artifacts(ROOT, temp_root)
    manifest = build_manifest(temp_root)
    report = verify_manifest(temp_root, manifest)
    if report.get("verified") is not True:
        raise AssertionError(f"expected manifest verification to pass, got {report}")
    manifest_sha = str(report.get("manifest_sha256") or "")
    if len(manifest_sha) != 64 or any(char not in "0123456789abcdef" for char in manifest_sha):
        raise AssertionError(f"manifest verification should report a stable manifest sha256: {report}")
    if manifest.get("artifact_count") != len(DEFAULT_ARTIFACTS):
        raise AssertionError(f"artifact_count mismatch: {manifest}")
    manifest_paths = {str(item.get("path") or "") for item in manifest.get("artifacts", []) if isinstance(item, dict)}
    required_paths = {
        "local_inspection_service/scripts/migrate_json_to_sqlite.py",
        "local_inspection_service/scripts/smoke_data_layer_migration.py",
        "local_inspection_service/scripts/smoke_postgres_schema_real_engine.py",
        "local_inspection_service/scripts/smoke_postgres_import_real_engine.py",
        "local_inspection_service/scripts/smoke_postgres_full_smoke_report_validator.py",
        "local_inspection_service/scripts/smoke_postgres_endpoint_source_contract.py",
        "local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py",
        "local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py",
        "local_inspection_service/scripts/smoke_postgres_local_preflight_suite_report_validator.py",
        "local_inspection_service/scripts/postgres_cutover_deploy_package.py",
        "local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py",
    }
    missing_paths = sorted(required_paths - manifest_paths)
    if missing_paths:
        raise AssertionError(f"manifest did not include required smoke artifacts: {missing_paths}")
    serialized = json.dumps(manifest, sort_keys=True)
    for forbidden in ("postgresql://", "DATABASE_URL=", "password=", "vantaline_session="):
        if forbidden.lower() in serialized.lower():
            raise AssertionError(f"manifest leaked forbidden marker: {forbidden}")
    return manifest


def assert_manifest_detects_changed_file(manifest: dict[str, object]) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="vantaline_cutover_manifest_changed_"))
    copy_artifacts(ROOT, temp_root)
    target = temp_root / "local_inspection_service/scripts/validate_postgres_full_smoke_report.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# changed by manifest smoke\n", encoding="utf-8")
    report = verify_manifest(temp_root, manifest)
    if report.get("verified") is not False:
        raise AssertionError(f"expected manifest verification to fail, got {report}")
    failures = report.get("failures")
    if not isinstance(failures, list) or not failures:
        raise AssertionError(f"manifest verification did not report failures: {report}")


def assert_manifest_rejects_forbidden_path() -> None:
    try:
        build_manifest(ROOT, artifacts=("local_inspection_service/data/secret.env",))
    except ManifestError as exc:
        if "forbidden" not in str(exc):
            raise AssertionError(f"unexpected forbidden-path error: {exc}") from exc
        return
    raise AssertionError("manifest unexpectedly accepted a forbidden artifact path")


def main() -> None:
    manifest = assert_manifest_round_trip_passes()
    assert_manifest_detects_changed_file(manifest)
    assert_manifest_rejects_forbidden_path()
    print("postgres cutover artifact manifest smoke passed")


if __name__ == "__main__":
    main()
