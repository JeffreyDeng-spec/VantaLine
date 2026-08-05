#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_phase3b_detection_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)
os.environ["VANTALINE_YOLO_PREWARM"] = "0"
os.environ["INSPECTION_WORKER_WATCHER"] = "0"
os.environ["LOCAL_INSPECTION_AUTO_RESUME_WORKER"] = "0"

from local_inspection_service.scripts import testclient_threadpool_shim  # noqa: E402

testclient_threadpool_shim.install()

TestClient = testclient_threadpool_shim.SmokeASGIClient

from local_inspection_service import server  # noqa: E402


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text[:500]}")


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert_status(response, 200, f"{username} login")


def logout(client: TestClient, label: str) -> None:
    response = client.post("/api/auth/logout")
    assert_status(response, 200, label)


def create_user(client: TestClient, username: str, permissions: list[str]) -> dict[str, str]:
    response = client.post(
        "/api/auth/users",
        json={
            "username": username,
            "display_name": username,
            "password": f"{username}-password-1",
            "role": "user",
            "permissions": permissions,
        },
    )
    assert_status(response, 200, f"create {username}")
    return response.json()["user"]


def seed_ai_task(task_id: str, owner: dict[str, str]) -> dict[str, object]:
    now = int(time.time())
    return {
        "id": task_id,
        "name": "Phase 3B AI smoke task",
        "selected_accessory_ids": ["acc_phase3b"],
        "required_accessory_counts": {"acc_phase3b": 1},
        "accessory_labels": {"acc_phase3b": "Phase 3B accessory"},
        "created_at": now,
        "updated_at": now,
        "source": "smoke_phase3b",
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }


def assert_react_detection_routes() -> None:
    shell = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    page = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "features" / "detection" / "DetectionWorkbenchPage.tsx").read_text(encoding="utf-8")
    expected_shell = {
        "DetectionWorkbenchPage import": "DetectionWorkbenchPage",
        "inspect route": 'path="/inspect"',
        "ai-inspect route": 'path="/ai-inspect"',
        "inspect placeholder exclusion": '"inspect"',
        "aiInspect placeholder exclusion": '"aiInspect"',
    }
    missing_shell = [label for label, snippet in expected_shell.items() if snippet not in shell]
    if missing_shell:
        raise AssertionError("React detection route wiring missing: " + ", ".join(missing_shell))
    expected_page = {
        "image analyze upload": "analyzeImage(form, { signal:",
        "video analyze upload": "analyzeVideo(form, { signal:",
        "AI task query": "getAiTasks(auth)",
        "camera runtime": "navigator.mediaDevices?.getUserMedia",
        "result metrics": "DetectionMetrics",
    }
    missing_page = [label for label, snippet in expected_page.items() if snippet not in page]
    if missing_page:
        raise AssertionError("React detection workbench contract missing: " + ", ".join(missing_page))


def post_bad_image(client: TestClient, model_id: str | None = None):
    data = {"model_id": model_id} if model_id is not None else {}
    return client.post(
        "/api/analyze/image",
        data=data,
        files={"file": ("not-an-image.jpg", b"not an image", "image/jpeg")},
    )


def main() -> None:
    assert_react_detection_routes()
    if server.route_allowed_permissions("/api/analyze/image", "POST") != ("inspection", "ai_detection"):
        raise AssertionError("analyze image route must allow inspection or ai_detection before endpoint model guard")
    if server.route_allowed_permissions("/api/analyze/video", "POST") != ("inspection", "ai_detection"):
        raise AssertionError("analyze video route must allow inspection or ai_detection before endpoint model guard")

    client = TestClient(server.app, base_url="https://testserver")
    response = client.post(
        "/api/auth/bootstrap",
        json={"username": "admin", "display_name": "Admin", "password": "admin-password-1"},
    )
    assert_status(response, 200, "bootstrap admin")
    inspection_user = create_user(client, "inspection_user", ["inspection"])
    ai_user = create_user(client, "ai_user", ["ai_detection"])
    create_user(client, "zero_user", [])
    server.save_ai_detection_tasks([seed_ai_task("aitask_phase3b", ai_user)])

    logout(client, "admin logout")

    login(client, "ai_user", "ai_user-password-1")
    response = client.get("/api/ai/tasks")
    assert_status(response, 200, "ai user lists own AI tasks")
    if {item["id"] for item in response.json()["tasks"]} != {"aitask_phase3b"}:
        raise AssertionError("ai user did not receive own AI task")
    response = post_bad_image(client)
    assert_status(response, 403, "ai user cannot run default non-AI analyze model")
    response = post_bad_image(client, "ai_detection__task_aitask_phase3b")
    assert_status(response, 400, "ai user reaches image decoder with own AI task model")
    logout(client, "ai user logout")

    login(client, "inspection_user", "inspection_user-password-1")
    response = client.get("/api/ai/tasks")
    assert_status(response, 403, "inspection-only user cannot list AI tasks")
    response = post_bad_image(client)
    assert_status(response, 400, "inspection user reaches image decoder with default model")
    logout(client, "inspection user logout")

    login(client, "zero_user", "zero_user-password-1")
    response = post_bad_image(client, "ai_detection__task_aitask_phase3b")
    assert_status(response, 403, "zero-permission user cannot analyze with AI task")

    print("smoke_phase3b_detection: ok")


if __name__ == "__main__":
    main()
