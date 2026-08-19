#!/usr/bin/env python3
"""Focused Phase 1/2 cleanup smoke.

This intentionally avoids heavyweight model inference and generated training
fixtures. It verifies that the kept product shell/API surfaces still respond
and that retired Phase 1 fields/routes are blocked from public payloads.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = Path(__file__).resolve().parents[1]
SERVER_SOURCE_PATH = SERVICE_ROOT / "server.py"
CONFIG_BACKUP_PATH = SERVICE_ROOT / "data" / "config.last_good.json"
LOCATEANYTHING_LOCAL_CONFIG_PATH = SERVICE_ROOT / "data" / "locateanything_config.local.json"
sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_phase1_core_smoke_"))
APP_DIR = ROOT / "local_inspection_service"
DIST_DIR = APP_DIR / "frontend" / "dist-production"
(DIST_DIR / "assets").mkdir(parents=True, exist_ok=True)
(APP_DIR / "static").mkdir(parents=True, exist_ok=True)
(DIST_DIR / "index.html").write_text("<!doctype html><title>VantaLine</title><div id=\"root\"></div>\n", encoding="utf-8")

os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from local_inspection_service import auto_optimize_profiles, retired_features  # noqa: E402
from local_inspection_service import server  # noqa: E402


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text[:400]}")


def assert_absent(payload: object, needle: str, label: str) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if needle in encoded:
        raise AssertionError(f"{label}: unexpected {needle!r} in payload")


def assert_retired_locateanything_local_config() -> None:
    if not LOCATEANYTHING_LOCAL_CONFIG_PATH.exists():
        return
    try:
        payload = json.loads(LOCATEANYTHING_LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"retired LocateAnything local config is not valid JSON: {exc}") from exc
    enabled = payload.get("enabled") is True
    endpoint_url = str(payload.get("endpoint_url") or "").strip()
    if enabled or endpoint_url:
        raise AssertionError(
            "retired LocateAnything local config must be absent or disabled with an empty endpoint"
        )


def assert_retired_backend_helpers_pruned() -> None:
    source = SERVER_SOURCE_PATH.read_text(encoding="utf-8")
    forbidden_markers = (
        "from local_inspection_service.label_experiment import",
        "LOCATEANYTHING_DEFAULT_ENDPOINT",
        "LOCATEANYTHING_OUTPUT_DIR",
        "LABEL_SHEET_MATCH_THRESHOLD",
        "class LocateAnythingConfigRequest",
        "class DataAnalysisLocateRequest",
        "def normalize_locateanything_config",
        "def post_locateanything_endpoint",
        "def start_locateanything_runtime",
        "def match_label_sheet_to_references",
        "def analyze_bgr_label_sheet",
        "def run_locateanything_for_analysis_record",
        "def append_data_analysis_locate_run",
        "def ensure_config_locateanything_profiles",
        "def public_data_analysis_locate_run",
    )
    for marker in forbidden_markers:
        if marker in source:
            raise AssertionError(f"retired backend helper remains in server.py: {marker}")
    if (SERVICE_ROOT / "label_experiment.py").exists():
        raise AssertionError("retired Label Sheet helper module label_experiment.py still exists")


def assert_phase3_module_boundaries() -> None:
    if retired_features.REMOVED_PHASE1_PUBLIC_CONFIG_KEYS != server.REMOVED_PHASE1_PUBLIC_CONFIG_KEYS:
        raise AssertionError("retired feature policy import boundary drifted from server usage")
    if not callable(auto_optimize_profiles.build_mask_target_profile):
        raise AssertionError("auto-optimize profile module does not expose build_mask_target_profile")
    source = SERVER_SOURCE_PATH.read_text(encoding="utf-8")
    for expected in (
        "from local_inspection_service.auto_optimize_profiles import build_mask_target_profile",
        "from local_inspection_service.retired_features import REMOVED_PHASE1_PUBLIC_CONFIG_KEYS, removed_phase1_feature",
    ):
        if expected not in source:
            raise AssertionError(f"server.py missing Phase 3 module import boundary: {expected}")


def assert_retired_backup_payload_sanitized() -> None:
    if not CONFIG_BACKUP_PATH.exists():
        return
    try:
        payload = json.loads(CONFIG_BACKUP_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"config.last_good.json is not valid JSON: {exc}") from exc
    sanitized = server.public_path_sanitized(payload)
    for key in (
        "locateanything_profile",
        "locateanything_profile_status",
        "locateanything_profile_ready",
    ):
        assert_absent(sanitized, key, "sanitized config.last_good.json")


def assert_stale_locateanything_profile_not_runtime_fallback() -> None:
    profile = server.auto_optimize_mask_target_profile(
        {"accessory_id": "phase2-stale-profile-target"},
        {
            "phase2-stale-profile-target": {
                "id": "phase2-stale-profile-target",
                "name": "Current accessory name",
                "label": "Current accessory label",
                "material_type": "object",
                "ai_profile": {
                    "name": "Current AI name",
                    "material_type": "object",
                    "description": "Current AI description",
                    "visual_signature": "Current AI visual signature",
                    "tags": ["current-ai-tag"],
                    "negative_cues": ["current-ai-negative"],
                },
                "locateanything_profile": {
                    "name": "OLD LOCATE NAME",
                    "material_type": "text",
                    "positive_visual_prompt": "OLD LOCATE PROMPT",
                    "required_features": ["OLD LOCATE FEATURE"],
                    "optional_features": ["OLD LOCATE OPTIONAL"],
                    "reject_cues": ["OLD LOCATE REJECT"],
                    "packaging_exclusions": ["OLD LOCATE PACKAGE"],
                    "target_scope": "OLD LOCATE TARGET SCOPE",
                },
            }
        },
    )
    expected = {
        "label": "Current AI name",
        "material_type": "object",
        "visual_signature": "Current AI visual signature",
    }
    for key, value in expected.items():
        if profile.get(key) != value:
            raise AssertionError(f"stale LocateAnything profile affected auto-optimize {key}: {profile}")
    encoded = json.dumps(profile, ensure_ascii=False, sort_keys=True)
    for stale in (
        "OLD LOCATE NAME",
        "OLD LOCATE PROMPT",
        "OLD LOCATE FEATURE",
        "OLD LOCATE OPTIONAL",
        "OLD LOCATE REJECT",
        "OLD LOCATE PACKAGE",
        "OLD LOCATE TARGET SCOPE",
    ):
        if stale in encoded:
            raise AssertionError(f"stale LocateAnything profile leaked into auto-optimize target profile: {stale}")


def seed_stale_data_analysis_record() -> None:
    server.save_data_analysis_records(
        [
            {
                "record_id": "phase2-stale-locateanything-record",
                "owner_user_id": "legacy_admin",
                "owner_username": "admin",
                "created_at": 1,
                "updated_at": 1,
                "task": {"id": "ai_detection", "name": "AI 检测", "type": "ai_detection"},
                "source_image": {},
                "image_url": "",
                "ai_detection_result": {},
                "ai_summary": {},
                "comparison_summary": {
                    "locateanything_counts": {"phase1-accessory": 1},
                    "locateanything_passed": True,
                },
                "locateanything_runs": [{"run_id": "old-run"}],
                "image_processing_items": [],
            }
        ]
    )


def assert_zero_permission_retired_routes_denied(admin_client: TestClient) -> None:
    assert_status(
        admin_client.post(
            "/api/auth/users",
            json={
                "username": "phase2_zero",
                "password": "phase2-zero-pass",
                "display_name": "Phase 2 Zero",
                "role": "user",
                "permissions": [],
            },
        ),
        200,
        "create zero-permission user",
    )
    zero_client = TestClient(server.app)
    assert_status(
        zero_client.post("/api/auth/login", json={"username": "phase2_zero", "password": "phase2-zero-pass"}),
        200,
        "zero-permission login",
    )
    denied_checks = {
        "zero locate status": zero_client.get("/api/locateanything/status"),
        "zero locate inspect": zero_client.post("/api/locateanything/inspect"),
        "zero label references": zero_client.get("/api/label-sheets/references"),
        "zero label inspector": zero_client.post("/api/experimental/label-inspector/analyze"),
    }
    for label, response in denied_checks.items():
        assert_status(response, 403, label)


def main() -> None:
    assert_retired_locateanything_local_config()
    assert_retired_backend_helpers_pruned()
    assert_phase3_module_boundaries()
    assert_retired_backup_payload_sanitized()
    assert_stale_locateanything_profile_not_runtime_fallback()

    client = TestClient(server.app)

    for path in ("/", "/tasks", "/accessories", "/pipeline", "/inspect", "/data-analysis"):
        assert_status(client.get(path), 200, f"kept route {path}")

    for path in ("/legacy", "/label-sheet", "/locate-anything"):
        assert_status(client.get(path), 404, f"retired route {path}")

    assert_status(
        client.post(
            "/api/auth/bootstrap",
            json={"username": "admin", "password": "phase1-core-admin-pass", "display_name": "Phase 1 Admin"},
        ),
        200,
        "bootstrap admin",
    )
    assert_zero_permission_retired_routes_denied(client)

    config = server.load_config()
    config["accessories"] = [
        {
            "id": "phase1-accessory",
            "class_id": 101,
            "name": "Phase 1 accessory",
            "label": "Phase 1 accessory",
            "status": "active",
            "material_type": "object",
            "source_files": [],
            "detection_route": "yolo",
            "locateanything_profile": {"prompt": "stale"},
            "locateanything_profile_status": {"status": "ready"},
            "locateanything_profile_ready": True,
        }
    ]
    server.save_config(config)
    seed_stale_data_analysis_record()

    config_response = client.get("/api/config")
    assert_status(config_response, 200, "/api/config")
    config_payload = config_response.json()
    for key in (
        "locateanything_profile",
        "locateanything_profile_status",
        "locateanything_profile_ready",
    ):
        assert_absent(config_payload, key, "/api/config")

    preserved_api_checks = {
        "tasks": client.get("/api/ai/tasks"),
        "accessories": client.get("/api/accessories"),
        "training": client.get("/api/training/resources"),
        "inspection": client.get("/api/status"),
        "review": client.get("/api/data-analysis/records"),
    }
    for label, response in preserved_api_checks.items():
        assert_status(response, 200, f"preserved API {label}")

    review_payload = preserved_api_checks["review"].json()
    assert_absent(review_payload, "locateanything_counts", "stale data-analysis record")
    assert_absent(review_payload, "locateanything_passed", "stale data-analysis record")
    assert_absent(review_payload, "locateanything_runs", "stale data-analysis record")

    removed_api_checks = {
        "locate config get": client.get("/api/locateanything/config"),
        "locate config post": client.post("/api/locateanything/config", json={"enabled": True}),
        "locate status": client.get("/api/locateanything/status"),
        "locate runtime start": client.post("/api/locateanything/runtime/start"),
        "locate accessories": client.get("/api/locateanything/accessories"),
        "locate inspect": client.post("/api/locateanything/inspect"),
        "locate": client.post("/api/locateanything/locate"),
        "analysis locate": client.post("/api/data-analysis/locate", json={"record_ids": []}),
        "analysis record locate": client.post("/api/data-analysis/records/phase2-stale-locateanything-record/locate"),
        "label references": client.get("/api/label-sheets/references"),
        "label references post": client.post("/api/label-sheets/references"),
        "label match": client.post("/api/label-sheets/match"),
        "label inspector": client.post("/api/experimental/label-inspector/analyze"),
    }
    for label, response in removed_api_checks.items():
        assert_status(response, 410, f"retired API {label}")

    print("phase1 core cleanup smoke passed")


if __name__ == "__main__":
    main()
