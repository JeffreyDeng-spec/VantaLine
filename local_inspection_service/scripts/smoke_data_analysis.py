#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = Path(tempfile.mkdtemp(prefix="vantaline_data_analysis_smoke_"))
(TMP_ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(TMP_ROOT)

sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from local_inspection_service import server  # noqa: E402


def assert_status(response: Any, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text[:500]}")


def encoded_image() -> bytes:
    image = np.full((96, 128, 3), 245, dtype=np.uint8)
    cv2.rectangle(image, (18, 22), (72, 78), (30, 120, 220), -1, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise AssertionError("could not encode smoke image")
    return encoded.tobytes()


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert_status(response, 200, f"{username} login")


def create_user(admin: TestClient, username: str) -> dict[str, Any]:
    response = admin.post(
        "/api/auth/users",
        json={
            "username": username,
            "password": "password-12345",
            "display_name": username.title(),
            "role": "user",
            "permissions": ["inspection", "ai_detection", "accessory_library"],
        },
    )
    assert_status(response, 200, f"create {username}")
    return response.json()["user"]


def seed_config(user_a: dict[str, Any], user_b: dict[str, Any]) -> None:
    config = json.loads(json.dumps(server.DEFAULT_CONFIG))
    config["required_classes"] = []
    config["min_counts"] = {}
    config["accessories"] = []
    for index, user in enumerate((user_a, user_b), start=1):
        accessory_id = f"acc_{user['username']}"
        name = f"{user['username']} smoke part"
        english_name = "Operator Alpha" if index == 1 else "Operator Beta"
        config["accessories"].append(
            {
                "id": accessory_id,
                "class_id": 8100 + index,
                "name": name,
                "english_name": english_name,
                "label": name,
                "material_type": "object",
                "status": "active",
                "source_files": [],
                "normalized_assets": [],
                "ai_profile": {
                    "accessory_id": accessory_id,
                    "name": name,
                    "english_name": english_name,
                    "material_type": "object",
                    "description": f"{name} visible smoke accessory",
                    "visual_signature": f"{name}; blue rectangle",
                    "tags": ["smoke"],
                    "distinguishing_text": [],
                    "expected_count": 1,
                },
                "owner_user_id": user["id"],
                "owner_username": user["username"],
            }
        )
    server.save_config(config)


def create_ai_task(client: TestClient, username: str) -> str:
    accessory_id = f"acc_{username}"
    response = client.post(
        "/api/ai/tasks",
        json={
            "name": f"{username} analysis task",
            "accessories": [{"accessory_id": accessory_id, "required_count": 1}],
        },
    )
    assert_status(response, 200, f"{username} AI task")
    return response.json()["task"]["model_id"]


def install_fake_ai() -> tuple[Any, Any]:
    original = server.call_ai_mcp_tool

    def fake_call(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool == "accessory.reference.collect":
            return {"references": [], "reference_count": 0}
        if tool == "accessory.profile.generate":
            item = payload.get("accessory") or {}
            accessory_id = str(item.get("id") or item.get("accessory_id") or "")
            return {
                "profile": {
                    "accessory_id": accessory_id,
                    "name": item.get("name") or accessory_id,
                    "material_type": item.get("material_type") or "object",
                    "description": "smoke profile",
                    "visual_signature": "blue rectangle",
                    "tags": ["smoke"],
                    "distinguishing_text": [],
                    "expected_count": int(payload.get("expected_count") or 1),
                },
                "status": {"ok": True},
            }
        if tool == "vision.inspect.presence":
            required = payload.get("required_accessories") or []
            detections = []
            counts = {}
            for item in required:
                accessory_id = str(item.get("accessory_id") or "")
                counts[accessory_id] = int(item.get("expected_count") or 1)
                detections.append(
                    {
                        "accessory_id": accessory_id,
                        "label": item.get("name") or accessory_id,
                        "present": True,
                        "confidence": 0.96,
                        "count": counts[accessory_id],
                        "evidence": "smoke image contains the required blue rectangle",
                    }
                )
            return {
                "passed": True,
                "rule": {"match_policy": "ai_presence", "present": list(counts), "missing": [], "extra": [], "counts": counts},
                "detections": detections,
                "ai": {"latency_ms": 5, "provider_status": "smoke"},
            }
        return original(tool, payload)

    server.call_ai_mcp_tool = fake_call
    return original, fake_call


def analyze_image(client: TestClient, model_id: str, filename: str) -> str:
    response = client.post(
        "/api/analyze/image",
        data={"model_id": model_id},
        files={"file": (filename, encoded_image(), "image/jpeg")},
    )
    assert_status(response, 200, f"analyze {filename}")
    records = client.get("/api/data-analysis/records")
    assert_status(records, 200, f"list after {filename}")
    items = records.json()["records"]
    if not items:
        raise AssertionError("analysis record was not created")
    return items[0]["record_id"]


def main() -> None:
    admin = TestClient(server.app)
    bootstrap = admin.post("/api/auth/bootstrap", json={"username": "admin", "password": "password-12345"})
    assert_status(bootstrap, 200, "bootstrap admin")
    user_a = create_user(admin, "operator_a")
    user_b = create_user(admin, "operator_b")
    seed_config(user_a, user_b)

    client_a = TestClient(server.app)
    client_b = TestClient(server.app)
    login(client_a, "operator_a", "password-12345")
    login(client_b, "operator_b", "password-12345")
    model_a = create_ai_task(client_a, "operator_a")
    model_b = create_ai_task(client_b, "operator_b")

    original_ai, _ = install_fake_ai()
    try:
        record_a = analyze_image(client_a, model_a, "operator_a.jpg")
        hidden_from_b = client_b.get("/api/data-analysis/records")
        assert_status(hidden_from_b, 200, "operator B initial list")
        if hidden_from_b.json()["records"]:
            raise AssertionError("operator B can see operator A analysis records")
        record_b = analyze_image(client_b, model_b, "operator_b.jpg")
    finally:
        server.call_ai_mcp_tool = original_ai

    all_records = admin.get("/api/data-analysis/records")
    assert_status(all_records, 200, "admin all records")
    if all_records.json()["total"] != 2:
        raise AssertionError(f"admin expected 2 records, got {all_records.json()}")
    filtered = admin.get("/api/data-analysis/records", params={"user_id": user_a["id"]})
    assert_status(filtered, 200, "admin filtered records")
    filtered_ids = {item["record_id"] for item in filtered.json()["records"]}
    if filtered_ids != {record_a}:
        raise AssertionError(f"admin user filter failed: {filtered.json()}")

    removed_batch = client_b.post("/api/data-analysis/locate", json={"record_ids": [record_a]})
    assert_status(removed_batch, 410, "removed data-analysis LocateAnything batch returns gone")
    removed_record = client_a.post(f"/api/data-analysis/records/{record_a}/locate", json={})
    assert_status(removed_record, 410, "removed data-analysis LocateAnything record returns gone")

    detail = client_a.get(f"/api/data-analysis/records/{record_a}")
    assert_status(detail, 200, "detail after removed locate")
    record = detail.json()["record"]
    serialized_normal_detail = json.dumps(record, ensure_ascii=False)
    for forbidden in ("diagnostic_url", "diagnostics", "raw_answer", "raw_answer_snippet", "prompt"):
        if forbidden in serialized_normal_detail:
            raise AssertionError(f"normal user detail leaked debug field {forbidden}: {record}")
    if "locateanything_run_count" in record or "locateanything_runs" in record or "latest_locateanything_run" in record:
        raise AssertionError(f"removed LocateAnything fields leaked in data-analysis detail: {record}")
    scope = record.get("required_accessory_scope", {}).get("required_accessories", [])
    if [item["accessory_id"] for item in scope] != ["acc_operator_a"]:
        raise AssertionError(f"data analysis scope should only include operator A required accessory: {scope}")

    if client_b.get(f"/api/data-analysis/records/{record_b}").json()["record"]["record_id"] != record_b:
        raise AssertionError("operator B could not read own data analysis record")
    print("data analysis smoke ok")


if __name__ == "__main__":
    main()
