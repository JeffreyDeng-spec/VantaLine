#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = Path(tempfile.mkdtemp(prefix="vantaline_incoming_text_api_"))
(TMP_ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(TMP_ROOT)
os.environ["VANTALINE_DATA_STORE"] = "json"
os.environ["VANTALINE_INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED"] = "true"
sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service.scripts import testclient_threadpool_shim  # noqa: E402
from local_inspection_service import server  # noqa: E402
from local_inspection_service import text_compare_beta  # noqa: E402
from local_inspection_service.incoming_text_inspection import TextObservation  # noqa: E402

testclient_threadpool_shim.install()
TestClient = testclient_threadpool_shim.SmokeASGIClient


PASSWORD = "password-12345"


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected {expected}, got {response.status_code}: {response.text[:600]}")


def image_bytes(text: str = "MODEL: PPLBP-2020") -> bytes:
    image = np.full((900, 1400, 3), 145, dtype=np.uint8)
    cv2.rectangle(image, (80, 120), (1320, 780), (28, 31, 35), -1)
    cv2.putText(image, text, (170, 450), cv2.FONT_HERSHEY_SIMPLEX, 2.1, (245, 245, 245), 5, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 94])
    if not ok:
        raise AssertionError("could not encode test image")
    return encoded.tobytes()


def mock_ocr_result(text: str):
    def run(image: np.ndarray) -> list[TextObservation]:
        height, width = image.shape[:2]
        return [
            TextObservation(
                text=text,
                confidence=0.995,
                polygon=(
                    (width * 0.1, height * 0.25),
                    (width * 0.9, height * 0.25),
                    (width * 0.9, height * 0.75),
                    (width * 0.1, height * 0.75),
                ),
            )
        ]

    return run


def login(client: TestClient, username: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert_status(response, 200, f"login {username}")


def create_user(admin: TestClient, username: str, permissions: list[str]) -> dict:
    response = admin.post(
        "/api/auth/users",
        json={"username": username, "password": PASSWORD, "display_name": username, "role": "user", "permissions": permissions},
    )
    assert_status(response, 200, f"create {username}")
    return response.json()["user"]


def upload_reference(client: TestClient, task_id: str, version: str) -> dict:
    response = client.post(
        f"/api/incoming-text/tasks/{task_id}/references",
        data={"version_label": version},
        files={"file": (f"standard-{version}.jpg", image_bytes(), "image/jpeg")},
    )
    assert_status(response, 200, f"upload {version}")
    return response.json()


def activate_reference(client: TestClient, reference_id: str) -> dict:
    response = client.put(
        f"/api/incoming-text/references/{reference_id}/rules",
        json={
            "activate": True,
            "rules": [
                {
                    "field_id": "model",
                    "name": "产品型号",
                    "region_normalized": {"x": 0.08, "y": 0.25, "width": 0.84, "height": 0.35},
                    "expected_text": "MODEL: PPLBP-2020",
                    "match_mode": "exact",
                    "importance": "critical",
                    "case_sensitive": True,
                }
            ],
        },
    )
    assert_status(response, 200, "activate reference")
    return response.json()


def main() -> None:
    admin = TestClient(server.app, base_url="https://testserver")
    assert_status(admin.post("/api/auth/bootstrap", json={"username": "admin", "password": PASSWORD}), 200, "bootstrap")
    manager_user = create_user(admin, "manager", ["incoming_material_config", "inspection"])
    create_user(admin, "config_only", ["incoming_material_config"])
    inspector_user = create_user(admin, "inspector_only", ["inspection"])
    unassigned_user = create_user(admin, "unassigned_inspector", ["inspection"])
    manager = TestClient(server.app, base_url="https://testserver")
    config_only = TestClient(server.app, base_url="https://testserver")
    inspector_only = TestClient(server.app, base_url="https://testserver")
    unassigned_inspector = TestClient(server.app, base_url="https://testserver")
    login(manager, "manager")
    login(config_only, "config_only")
    login(inspector_only, "inspector_only")
    login(unassigned_inspector, "unassigned_inspector")

    beta_files = {
        "reference_file": ("reference.jpg", image_bytes(), "image/jpeg"),
        "captured_file": ("captured.jpg", image_bytes(), "image/jpeg"),
    }
    anonymous = TestClient(server.app, base_url="https://testserver")
    assert_status(anonymous.post("/api/text-compare-beta/analyze", data={"comparison_id": "cmp_anonymous_01"}, files=beta_files), 401, "beta requires login")
    assert_status(config_only.post("/api/text-compare-beta/analyze", data={"comparison_id": "cmp_no_permission_01"}, files=beta_files), 403, "beta requires inspection")
    original_ocr = server.incoming_text_ocr_observations
    original_quality = text_compare_beta.assess_image_quality
    original_rectify = text_compare_beta.rectify_label
    server.incoming_text_ocr_observations = mock_ocr_result("MODEL: PPLBP-2020")
    text_compare_beta.assess_image_quality = lambda _: {"accepted": True, "reasons": []}
    text_compare_beta.rectify_label = lambda image, size: (image.copy(), {"accepted": True})
    try:
        beta_response = manager.post("/api/text-compare-beta/analyze", data={"comparison_id": "cmp_manager_repeat_01"}, files=beta_files)
        assert_status(beta_response, 200, "beta compare")
        assert beta_response.json()["decision"] == "MATCH"
        beta_repeat = manager.post("/api/text-compare-beta/analyze", data={"comparison_id": "cmp_manager_repeat_01"}, files=beta_files)
        assert_status(beta_repeat, 200, "beta idempotent retry")
        assert beta_repeat.json() == beta_response.json()
        conflict_files = {
            "reference_file": ("reference.jpg", image_bytes(), "image/jpeg"),
            "captured_file": ("captured.jpg", image_bytes("MODEL: OTHER"), "image/jpeg"),
        }
        assert_status(manager.post("/api/text-compare-beta/analyze", data={"comparison_id": "cmp_manager_repeat_01"}, files=conflict_files), 409, "beta id conflict")
        server._text_compare_beta_cache.clear()
        ocr_calls = [0]

        def counted_ocr(image):
            ocr_calls[0] += 1
            return mock_ocr_result("MODEL: PPLBP-2020")(image)

        server.incoming_text_ocr_observations = counted_ocr
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(server._run_text_compare_beta, manager_user["id"], "cmp_concurrent_01", image_bytes(), image_bytes())
                for _ in range(2)
            ]
            concurrent_results = [future.result() for future in futures]
        assert concurrent_results[0] == concurrent_results[1]
        assert ocr_calls[0] == 2, f"same-ID concurrent request reran OCR: {ocr_calls[0]} calls"
    finally:
        server.incoming_text_ocr_observations = original_ocr
        text_compare_beta.assess_image_quality = original_quality
        text_compare_beta.rectify_label = original_rectify

    denied_create = inspector_only.post(
        "/api/pipeline/tasks",
        json={"name": "forbidden", "task_kind": "incoming_material_text", "material_code": "X", "material_name": "X"},
    )
    assert_status(denied_create, 403, "inspection-only cannot configure task")
    create = manager.post(
        "/api/pipeline/tasks",
        json={
            "name": "电池包底部标签",
            "task_kind": "incoming_material_text",
            "detection_method": "label_text_compare",
            "material_code": "PKG-BAT-001",
            "material_name": "电池包底部标签",
            "inspection_user_ids": [inspector_user["id"]],
            "auto_advance": False,
        },
    )
    assert_status(create, 200, "create incoming task")
    task = create.json()
    task_id = task["id"]
    assert task["task_kind"] == "incoming_material_text"
    assert task["detection_method"] == "label_text_compare"
    assert task["uses_training_flow"] is False
    assert task["auto_advance"] is False

    denied_reference = inspector_only.post(
        f"/api/incoming-text/tasks/{task_id}/references",
        data={"version_label": "bad"},
        files={"file": ("standard.jpg", image_bytes(), "image/jpeg")},
    )
    assert_status(denied_reference, 403, "inspection-only cannot upload standard")

    reference_v1 = upload_reference(manager, task_id, "V1")
    active_v1 = activate_reference(manager, reference_v1["id"])
    assert active_v1["status"] == "active"
    inspector_tasks = inspector_only.get("/api/pipeline/tasks")
    assert_status(inspector_tasks, 200, "assigned inspector can list task")
    assert task_id in {item["id"] for item in inspector_tasks.json()["items"]}
    shared_task = inspector_only.get(f"/api/incoming-text/tasks/{task_id}")
    assert_status(shared_task, 200, "assigned inspector can open task")
    assert shared_task.json()["active_reference"]["id"] == reference_v1["id"]
    assert shared_task.json()["automatic_decisions_verified"] is True
    hidden_task = unassigned_inspector.get(f"/api/incoming-text/tasks/{task_id}")
    assert_status(hidden_task, 404, "unassigned inspector cannot open task")
    immutable = manager.put(
        f"/api/incoming-text/references/{reference_v1['id']}/rules",
        json={"activate": False, "rules": active_v1["rules"]},
    )
    assert_status(immutable, 409, "active standard immutable")

    original_disk_usage = server.shutil.disk_usage
    server.shutil.disk_usage = lambda _path: type("DiskUsage", (), {"free": server.INCOMING_TEXT_MIN_FREE_BYTES - 1})()
    try:
        no_space = inspector_only.post(
            f"/api/incoming-text/tasks/{task_id}/inspect",
            data={"capture_id": "capture-no-space-0000"},
            files={"file": ("capture.jpg", image_bytes(), "image/jpeg")},
        )
        assert_status(no_space, 507, "low disk fails closed")
    finally:
        server.shutil.disk_usage = original_disk_usage

    original_rectify = server.rectify_label
    original_ocr = server.incoming_text_ocr_observations
    server.rectify_label = lambda image, target: (cv2.resize(image, target), {"accepted": True, "coverage": 0.7})
    server.incoming_text_ocr_observations = mock_ocr_result("MODEL: PPLBP-2020")
    try:
        capture_id = "capture-idempotent-0001"
        capture = image_bytes()
        first = inspector_only.post(
            f"/api/incoming-text/tasks/{task_id}/inspect",
            data={"capture_id": capture_id},
            files={"file": ("capture.jpg", capture, "image/jpeg")},
        )
        assert_status(first, 200, "first inspection")
        first_payload = first.json()
        assert first_payload["auto_decision"] == "PASS", first_payload

        reference_v2 = upload_reference(manager, task_id, "V2")
        activate_reference(manager, reference_v2["id"])
        retry = manager.post(
            f"/api/incoming-text/tasks/{task_id}/inspect",
            data={"capture_id": capture_id},
            files={"file": ("capture.jpg", capture, "image/jpeg")},
        )
        assert_status(retry, 200, "retry after standard switch")
        assert retry.json()["id"] == first_payload["id"]
        assert retry.json()["reference_id"] == reference_v1["id"]

        conflict = manager.post(
            f"/api/incoming-text/tasks/{task_id}/inspect",
            data={"capture_id": capture_id},
            files={"file": ("capture.jpg", image_bytes("DIFFERENT"), "image/jpeg")},
        )
        assert_status(conflict, 409, "capture payload conflict")

        server.incoming_text_ocr_observations = mock_ocr_result("MODEL: PPLBP-202o")
        mismatch = manager.post(
            f"/api/incoming-text/tasks/{task_id}/inspect",
            data={"capture_id": "capture-uppercase-o-0002"},
            files={"file": ("capture.jpg", capture, "image/jpeg")},
        )
        assert_status(mismatch, 200, "case mismatch inspection")
        assert mismatch.json()["auto_decision"] == "FAIL", mismatch.json()

        server.incoming_text_ocr_observations = lambda image: []
        review = inspector_only.post(
            f"/api/incoming-text/tasks/{task_id}/inspect",
            data={"capture_id": "capture-review-0003"},
            files={"file": ("capture.jpg", capture, "image/jpeg")},
        )
        assert_status(review, 200, "review inspection")
        review_payload = review.json()
        assert review_payload["auto_decision"] == "REVIEW_REQUIRED", review_payload
        reviewed = inspector_only.post(
            f"/api/incoming-text/inspections/{review_payload['id']}/review",
            json={"decision": "RELEASED", "reason": "现场复核确认标准文字正确"},
        )
        assert_status(reviewed, 200, "manual review")
        assert reviewed.json()["final_decision"] == "RELEASED"
        evidence = inspector_only.get(f"/api/incoming-text/inspections/{review_payload['id']}/evidence/source")
        assert_status(evidence, 200, "assigned inspector can read evidence")
        repeated = manager.post(
            f"/api/incoming-text/inspections/{review_payload['id']}/review",
            json={"decision": "RELEASED", "reason": "重复请求不得改写原因"},
        )
        assert_status(repeated, 200, "same review idempotent")
        opposite = manager.post(
            f"/api/incoming-text/inspections/{review_payload['id']}/review",
            json={"decision": "REJECTED", "reason": "冲突结论"},
        )
        assert_status(opposite, 409, "opposite review conflicts")
    finally:
        server.rectify_label = original_rectify
        server.incoming_text_ocr_observations = original_ocr

    listed = manager.get("/api/incoming-text/inspections", params={"task_id": task_id})
    assert_status(listed, 200, "list inspections")
    assert listed.json()["total"] >= 3
    hidden = config_only.get("/api/incoming-text/inspections")
    assert_status(hidden, 403, "config-only cannot list inspections")
    reassigned = manager.patch(
        f"/api/pipeline/tasks/{task_id}",
        json={"inspection_user_ids": [unassigned_user["id"]]},
    )
    assert_status(reassigned, 200, "configurator can reassign workstation")
    assert inspector_only.get(f"/api/incoming-text/tasks/{task_id}").status_code == 404
    assert_status(unassigned_inspector.get(f"/api/incoming-text/tasks/{task_id}"), 200, "newly assigned inspector can open task")
    assert_status(
        unassigned_inspector.get(f"/api/incoming-text/inspections/{review_payload['id']}/evidence/source"),
        200,
        "newly assigned inspector can read existing task evidence",
    )
    bad_upload = manager.post(
        f"/api/incoming-text/tasks/{task_id}/references",
        data={"version_label": "BAD"},
        files={"file": ("bad.jpg", b"not-an-image", "image/jpeg")},
    )
    assert_status(bad_upload, 400, "bad reference rejected")
    assert_status(manager.delete(f"/api/pipeline/tasks/{task_id}"), 200, "configurator can delete incoming task")
    print("incoming text endpoint smoke: PASS")


if __name__ == "__main__":
    main()
