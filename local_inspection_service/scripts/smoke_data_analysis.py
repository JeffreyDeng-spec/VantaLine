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
            "permissions": ["inspection", "ai_detection", "locate_anything", "accessory_library"],
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

    unauthorized = client_b.post("/api/data-analysis/locate", json={"record_ids": [record_a]})
    assert_status(unauthorized, 404, "batch rejects unauthorized record")

    server.save_locateanything_config(
        server.normalize_locateanything_config(
            {"enabled": True, "endpoint_url": "http://127.0.0.1:9999/locate", "generation_mode": "fast", "max_side": 640, "max_new_tokens": 128, "timeout_seconds": 5}
        )
    )
    original_post = server.post_locateanything_endpoint
    original_worker = server.locateanything_should_use_worker
    try:
        server.locateanything_should_use_worker = lambda _settings: False
        server.post_locateanything_endpoint = lambda *args, **kwargs: {
            "answer": (
                "<ref>operator_b smoke part</ref><box><10><10><120><120></box>\n"
                "<ref>operator_a smoke part</ref><box><100><100><650><700></box>"
            )
        }
        located = client_a.post(f"/api/data-analysis/records/{record_a}/locate", json={})
        assert_status(located, 200, "run LocateAnything")
    finally:
        server.post_locateanything_endpoint = original_post
        server.locateanything_should_use_worker = original_worker

    detail = client_a.get(f"/api/data-analysis/records/{record_a}")
    assert_status(detail, 200, "detail after locate")
    record = detail.json()["record"]
    if record["locateanything_run_count"] != 1:
        raise AssertionError(f"LocateAnything run was not stored: {record}")
    if not record["comparison_summary"].get("latest_run_id"):
        raise AssertionError(f"comparison summary missing latest run id: {record}")
    serialized_normal_detail = json.dumps(record, ensure_ascii=False)
    for forbidden in ("diagnostic_url", "diagnostics", "raw_answer", "raw_answer_snippet", "prompt"):
        if forbidden in serialized_normal_detail:
            raise AssertionError(f"normal user detail leaked debug field {forbidden}: {record}")
    latest_run = record["locateanything_runs"][-1]
    if latest_run["box_count"] != 1:
        raise AssertionError(f"non-required LocateAnything box affected final overlay count: {latest_run}")
    if record["comparison_summary"].get("difference_count") != 0 or record["comparison_summary"].get("status") != "same":
        raise AssertionError(f"non-required LocateAnything box affected comparison: {record['comparison_summary']}")
    scope = record.get("required_accessory_scope", {}).get("required_accessories", [])
    if [item["accessory_id"] for item in scope] != ["acc_operator_a"]:
        raise AssertionError(f"data analysis scope should only include operator A required accessory: {scope}")

    admin_detail = admin.get(f"/api/data-analysis/records/{record_a}")
    assert_status(admin_detail, 200, "admin detail after locate")
    admin_record = admin_detail.json()["record"]
    admin_latest_run = admin_record["locateanything_runs"][-1]
    if not admin_latest_run.get("diagnostic_url"):
        raise AssertionError(f"admin detail should preserve diagnostic URL: {admin_latest_run}")
    if admin_latest_run["items"][0].get("raw_box_count") != 2 or admin_latest_run["items"][0].get("filtered_out_box_count") != 1:
        raise AssertionError(f"admin LocateAnything diagnostic raw/filter counts missing: {admin_latest_run['items'][0]}")
    if admin_latest_run["items"][0].get("label") != "Operator Alpha":
        raise AssertionError(f"LocateAnything result detail should reuse profile English label: {admin_latest_run['items'][0]}")
    boxes = admin_latest_run["items"][0].get("boxes") or []
    if (
        not boxes
        or boxes[0].get("label") != "Operator Alpha"
        or boxes[0].get("display_label") != "Operator Alpha"
        or boxes[0].get("english_name") != "Operator Alpha"
        or boxes[0].get("native_label") != "operator_a smoke part"
    ):
        raise AssertionError(f"LocateAnything visible box labels should use required accessory names: {admin_latest_run['items'][0]}")

    request_token = server._request_user.set(user_a)
    try:
        rules = server.data_analysis_locate_rules(admin_record)
        rule_ids = {item["id"] for item in rules}
        if rule_ids != {"analysis:acc_operator_a"}:
            raise AssertionError(f"LocateAnything rules must stay scoped to required accessories: {rules}")
        if rules[0].get("expected_count") != 1 or rules[0].get("ai_detection_count") != 1:
            raise AssertionError(f"LocateAnything required/AI counts diverged from task scope: {rules}")
        if rules[0].get("display_label") != "Operator Alpha" or rules[0].get("label") != "operator_a smoke part":
            raise AssertionError(f"LocateAnything data-analysis labels should reuse profile English names: {rules}")

        polluted_record = json.loads(json.dumps(admin_record))
        polluted_rule = polluted_record["ai_detection_result"].setdefault("rule", {})
        polluted_rule.setdefault("counts", {})["acc_operator_b"] = 7
        polluted_record["ai_detection_result"].setdefault("detections", []).append(
            {
                "accessory_id": "acc_operator_b",
                "label": "operator_b smoke part",
                "present": True,
                "confidence": 0.99,
                "count": 7,
                "evidence": "synthetic unrelated LocateAnything-style class",
            }
        )
        polluted_rules = server.data_analysis_locate_rules(polluted_record)
        if {item["id"] for item in polluted_rules} != {"analysis:acc_operator_a"}:
            raise AssertionError(f"non-required AI/LA classes leaked into locate rules: {polluted_rules}")

        synthetic_extra_run = {
            "run_id": "synthetic_extra",
            "status": "completed",
            "overall_pass": False,
            "items": [
                {"id": "analysis:acc_operator_a", "label": "Operator Alpha", "box_count": 1, "status": "comparison_same_count", "passed": True},
                {"id": "analysis:acc_operator_b", "label": "Operator Beta", "box_count": 7, "status": "comparison_extra", "passed": False},
            ],
        }
        synthetic_comparison = server.compare_ai_and_locateanything(admin_record, synthetic_extra_run)
        if synthetic_comparison["status"] != "same" or synthetic_comparison["difference_count"] != 0:
            raise AssertionError(f"non-required LocateAnything item affected final comparison: {synthetic_comparison}")
        if set(synthetic_comparison["locateanything_counts"]) != {"acc_operator_a"}:
            raise AssertionError(f"non-required LocateAnything count was exposed as final count: {synthetic_comparison}")
    finally:
        server._request_user.reset(request_token)
    if client_b.get(f"/api/data-analysis/records/{record_b}").json()["record"]["record_id"] != record_b:
        raise AssertionError("operator B could not read own data analysis record")
    print("data analysis smoke ok")


if __name__ == "__main__":
    main()
