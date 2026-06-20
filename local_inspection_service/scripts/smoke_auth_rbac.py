#!/usr/bin/env python3
import base64
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_auth_smoke_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from local_inspection_service import server  # noqa: E402

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text[:400]}")


def assert_api_route_permissions() -> None:
    public_routes = {
        ("GET", "/api/auth/status"),
        ("POST", "/api/auth/bootstrap"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
    }
    authenticated_allowlist = {
        ("GET", "/api/status"),
        ("GET", "/api/config/summary"),
    }
    missing: list[str] = []
    invalid: list[str] = []
    for route in server.app.routes:
        path = str(getattr(route, "path", "") or "")
        if not path.startswith("/api/"):
            continue
        methods = sorted(getattr(route, "methods", set()) or set())
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, path)
            permission = server.route_required_permission(path, method)
            if key in public_routes or key in authenticated_allowlist:
                continue
            if permission is None:
                missing.append(f"{method} {path}")
            elif permission not in server.FEATURE_PERMISSIONS:
                invalid.append(f"{method} {path} -> {permission}")
    if missing:
        raise AssertionError("API routes missing RBAC mapping: " + ", ".join(missing))
    if invalid:
        raise AssertionError("API routes mapped to unknown permissions: " + ", ".join(invalid))


def assert_no_password_secrets(payload, label: str, *, allow_temporary: bool = False) -> None:
    def walk(value, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key).lower()
                child_path = f"{path}.{key}" if path else str(key)
                if key_text == "temporary_password":
                    if not allow_temporary:
                        raise AssertionError(f"{label}: unexpected temporary password at {child_path}")
                    if not isinstance(child, str) or len(child) < 12:
                        raise AssertionError(f"{label}: generated temporary password is missing/too short")
                    continue
                if "password" in key_text:
                    raise AssertionError(f"{label}: password field leaked at {child_path}")
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload, "")


def assert_timestamp_ui_hooks() -> None:
    app_js = (REPO_ROOT / "local_inspection_service" / "static" / "app.js").read_text(encoding="utf-8")
    expected = {
        "admin user list": "recordAuditText(user, { owner: false, includeUpdated: true })",
        "label reference cards": "<small>${escapeHtml(recordAuditText(item))}</small>",
        "accessory list cards": "<span>${escapeHtml(recordAuditText(item))}</span>",
        "accessory detail summary": "recordAuditText(item, { includeUpdated: true })",
        "asset file thumbnails": "recordAuditText(asset, { owner: false })",
        "dataset library cards": "recordAuditText(dataset)",
        "model library cards": "recordAuditText(auditRecord)",
        "AI task library cards": "recordAuditText(task, { includeUpdated: true })",
        "image job rows": "recordAuditText(summary, { includeUpdated: true })",
        "pipeline task cards": "recordAuditText(task, { includeUpdated: true })",
        "localized login error": "用户名或密码不正确。",
        "parsed API error body": "function apiErrorMessage(response, body = \"\", path = \"\")",
        "login 401 keeps login form": "!String(path).startsWith(\"/api/auth/login\")",
    }
    missing = [label for label, snippet in expected.items() if snippet not in app_js]
    if missing:
        raise AssertionError("UI timestamp hooks missing: " + ", ".join(missing))


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert_status(response, 200, f"{username} login")


def logout(client: TestClient, label: str) -> None:
    response = client.post("/api/auth/logout")
    assert_status(response, 200, label)


def seed_training_task(job_id: str, owner: dict[str, str], *, status: str = "completed", note: str = "") -> None:
    server.TRAINING_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    user_dataset_dir = server.OUTPUT_DIR / "users" / owner["id"] / "training_datasets" / job_id
    payload = {
        "job_id": job_id,
        "task_id": job_id,
        "action": "train_model",
        "status": status,
        "progress": 100 if status in {"completed", "failed", "stopped"} else 0,
        "label": job_id,
        "dataset_dir": str(user_dataset_dir),
        "manifest_path": "",
        "sample_count": 1,
        "completed_samples": 1,
        "note": note,
        "error": "Local training worker is no longer active. Delete and retry the task." if status == "stopped" else "",
        "created_at": int(time.time()),
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }
    (server.TRAINING_TASKS_DIR / f"{job_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def seed_config_accessory(accessory_id: str, name: str, owner: dict[str, str]) -> None:
    config = server.load_config()
    existing = [item for item in config.get("accessories", []) if item.get("id") != accessory_id]
    existing.append(
        {
            "id": accessory_id,
            "class_id": 9000 + len(existing),
            "name": name,
            "label": name,
            "material_type": "text",
            "training_role": "detect_and_classify",
            "physical_size": server.physical_size_payload("text"),
            "status": "seeded",
            "source_files": [],
            "created_at": int(time.time()),
            "owner_user_id": owner["id"],
            "owner_username": owner["username"],
        }
    )
    config["accessories"] = existing
    server.save_config(config)


def seed_training_status_for_owner(owner: dict[str, str], accessory_id: str, label: str) -> None:
    secret_url = f"/outputs/users/{owner['id']}/training_previews/secret.png"
    config = server.load_config()
    selected = server.selected_accessories(config, [accessory_id])
    config["training"] = {
        "status": "preview_ready",
        "last_preview_id": "preview_b_secret",
        "selected_accessory_ids": [accessory_id],
        "sample_count": 12,
        "mode": "yolo_ocr",
        "background_set_id": "",
        "preview_urls": [secret_url],
        "previews": [
            {
                "url": secret_url,
                "labels": [{"id": accessory_id, "name": label, "accessory_id": accessory_id}],
            }
        ],
        "preview_cache_key": server.preview_cache_key(selected),
        "active_training_task_id": "train_b_secret",
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }
    server.save_config(config)


def persisted_accessory_ids() -> set[str]:
    return {str(item.get("id") or server.accessory_uid(item)) for item in server.load_config().get("accessories", [])}


def assert_operator_a_training_hides_b(client: TestClient, operator_b: dict[str, str], label: str) -> None:
    response = client.get("/api/training/status")
    assert_status(response, 200, label)
    status_text = json.dumps(response.json(), ensure_ascii=False)
    assert "train_b_secret" not in status_text
    assert "acc_b_private" not in status_text
    assert "B private" not in status_text
    assert operator_b["id"] not in status_text
    assert "/outputs/users/" not in status_text or operator_b["id"] not in status_text


def assert_operator_b_training_preserved(client: TestClient, operator_b: dict[str, str], label: str) -> None:
    response = client.get("/api/training/status")
    assert_status(response, 200, label)
    status_text = json.dumps(response.json(), ensure_ascii=False)
    assert "preview_ready" in status_text
    assert "train_b_secret" in status_text
    assert "acc_b_private" in status_text
    if "B private" not in status_text:
        raise AssertionError(f"{label}: missing B private label in {status_text}")
    assert operator_b["id"] in status_text


def assert_training_status_hydrates_active_task(client: TestClient, operator_b: dict[str, str]) -> None:
    seed_training_task("train_b_secret", operator_b, status="stopped", note="本地训练任务已中断；请删除后重试。")
    try:
        response = client.get("/api/training/status")
        assert_status(response, 200, "active training task status hydration")
        payload = response.json()
        if payload.get("status") != "stopped":
            raise AssertionError(f"expected stopped active task status, got {payload}")
        assert payload.get("progress") == 100
        assert "本地训练任务已中断" in str(payload.get("note") or "")
    finally:
        (server.TRAINING_TASKS_DIR / "train_b_secret.json").unlink(missing_ok=True)
    config = server.load_config()
    state = config.get("training_by_user_id", {}).get(operator_b["id"])
    if state:
        state["status"] = "queued"
        state["note"] = "任务已加入队列。"
        server.save_config(config)
    response = client.get("/api/training/status")
    assert_status(response, 200, "missing active training task status hydration")
    payload = response.json()
    if payload.get("status") != "stopped":
        raise AssertionError(f"expected missing active task to stop stale state, got {payload}")
    assert payload.get("progress") == 100
    assert "任务记录已删除" in str(payload.get("note") or "")


def assert_training_status_does_not_hydrate_hidden_task(
    client: TestClient,
    operator_a: dict[str, str],
    operator_b: dict[str, str],
    accessory_id: str,
) -> None:
    hidden_task_id = "train_b_hidden_cross_owner"
    seed_training_task(hidden_task_id, operator_b, status="stopped", note="B private terminal note")
    hidden_task_path = server.TRAINING_TASKS_DIR / f"{hidden_task_id}.json"
    hidden_task = json.loads(hidden_task_path.read_text(encoding="utf-8"))
    hidden_task.update(
        {
            "error": "B private terminal error",
            "source_dataset_id": "dataset_b_private",
            "dataset_id": "dataset_b_private",
        }
    )
    hidden_task_path.write_text(json.dumps(hidden_task), encoding="utf-8")
    config = server.load_config()
    state = {
        **server.default_training_state(),
        "status": "queued",
        "note": "任务已加入队列。",
        "selected_accessory_ids": [accessory_id],
        "sample_count": 1,
        "mode": "yolo",
        "active_training_task_id": hidden_task_id,
        "owner_user_id": operator_a["id"],
        "owner_username": operator_a["username"],
    }
    config.setdefault("training_by_user_id", {})[operator_a["id"]] = state
    server.save_config(config)
    try:
        response = client.get("/api/training/status")
        assert_status(response, 200, "cross-owner active task is not hydrated")
        payload = response.json()
        status_text = json.dumps(payload, ensure_ascii=False)
        for forbidden in [
            "B private terminal note",
            "B private terminal error",
            "dataset_b_private",
            operator_b["id"],
            operator_b["username"],
        ]:
            if forbidden in status_text:
                raise AssertionError(f"hidden task field leaked through training status: {forbidden} in {payload}")
        if payload.get("status") != "stopped":
            raise AssertionError(f"expected safe stopped state for hidden active task, got {payload}")
        assert "任务记录已删除" in str(payload.get("note") or "")
    finally:
        hidden_task_path.unlink(missing_ok=True)


def assert_admin_aggregate_hydrates_child_training_state(
    client: TestClient,
    operator_a: dict[str, str],
    accessory_id: str,
) -> None:
    task_id = "train_a_done_aggregate"
    seed_training_task(task_id, operator_a, status="stopped", note="A terminal task note")
    config = server.load_config()
    original_state = json.loads(json.dumps(config.get("training_by_user_id", {}).get(operator_a["id"])))
    config.setdefault("training_by_user_id", {})[operator_a["id"]] = {
        **server.default_training_state(),
        "status": "queued",
        "note": "任务已加入队列。",
        "selected_accessory_ids": [accessory_id],
        "sample_count": 1,
        "mode": "yolo",
        "active_training_task_id": task_id,
        "owner_user_id": operator_a["id"],
        "owner_username": operator_a["username"],
    }
    server.save_config(config)
    try:
        response = client.get("/api/training/status")
        assert_status(response, 200, "admin aggregate hydrates child active task")
        states = response.json().get("training_states")
        if not isinstance(states, list):
            raise AssertionError(f"admin aggregate missing training_states: {response.json()}")
        child = next((state for state in states if state.get("active_training_task_id") == task_id), None)
        if not child:
            raise AssertionError(f"admin aggregate missing seeded child state: {states}")
        if child.get("status") != "stopped":
            raise AssertionError(f"expected hydrated child stopped state, got {child}")
        assert child.get("progress") == 100
        assert "A terminal task note" in str(child.get("note") or "")
    finally:
        (server.TRAINING_TASKS_DIR / f"{task_id}.json").unlink(missing_ok=True)
        config = server.load_config()
        if original_state is None:
            config.get("training_by_user_id", {}).pop(operator_a["id"], None)
        else:
            config.setdefault("training_by_user_id", {})[operator_a["id"]] = original_state
        server.save_config(config)


def install_fake_training_enqueue() -> None:
    def fake_enqueue_training_task(request, selected, action, dataset=None):
        job_id = f"fake_{action}_{int(time.time())}"
        return {
            "job_id": job_id,
            "task_id": job_id,
            "candidate_id": job_id,
            "candidate_name": action,
            "label": action,
            "action": action,
            "status": "queued",
            "progress": 0,
            "sample_count": int(dataset.get("sample_count") if dataset else request.sample_count),
            "mode": request.train_mode,
            "epochs": int(request.epochs),
            "image_size": int(request.image_size),
            "background_set_id": request.background_set_id or "",
            "approved_preview_id": request.approved_preview_id or "",
            "selected_accessory_ids": [item["id"] for item in selected],
            "note": "fake smoke enqueue",
            "estimated_minutes": 1,
            "estimated_gb": 0.01,
            "owner_user_id": server.current_auth_user()["id"],
            "owner_username": server.current_auth_user()["username"],
        }

    server.enqueue_training_task = fake_enqueue_training_task


def seed_dataset(dataset_id: str, owner: dict[str, str] | None) -> None:
    if owner:
        dataset_dir = server.OUTPUT_DIR / "users" / owner["id"] / "training_datasets" / dataset_id
    else:
        dataset_dir = server.OUTPUT_DIR / "training_datasets" / dataset_id
    image_dir = dataset_dir / "images" / "train"
    label_dir = dataset_dir / "labels" / "train"
    preview_dir = dataset_dir / "previews" / "train"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / "sample_000001.png"
    label_path = label_dir / "sample_000001.txt"
    image_path.write_bytes(TINY_PNG)
    label_path.write_text("", encoding="utf-8")
    (dataset_dir / "dataset.yaml").write_text("path: .\ntrain: images/train\nnames: ['part']\n", encoding="utf-8")
    created_at = int(time.time())
    manifest = {
        "id": dataset_id,
        "task_id": dataset_id,
        "display_name": dataset_id,
        "created_at": created_at,
        "sample_count": 1,
        "selected_accessory_ids": [],
        "samples": [
            {
                "image": str(image_path),
                "labels": str(label_path),
                "url": server.public_output_url(image_path),
                "split": "train",
            }
        ],
    }
    if owner:
        manifest["owner_user_id"] = owner["id"]
        manifest["owner_username"] = owner["username"]
    (dataset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def seed_model_run(job_id: str, owner: dict[str, str]) -> None:
    run_dir = server.OUTPUT_DIR / "users" / owner["id"] / "training_runs" / job_id
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    (weights_dir / "best.pt").write_bytes(b"placeholder model")
    (run_dir / "library_metadata.json").write_text(json.dumps({"display_name": f"model {job_id}"}), encoding="utf-8")


def seed_ai_task(task_id: str, owner: dict[str, str]) -> dict[str, object]:
    now = int(time.time())
    return {
        "id": task_id,
        "name": task_id,
        "selected_accessory_ids": [f"accessory_{task_id}"],
        "required_accessory_counts": {f"accessory_{task_id}": 1},
        "accessory_labels": {f"accessory_{task_id}": task_id},
        "created_at": now,
        "updated_at": now,
        "source": "smoke",
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }


def seed_candidate(candidate_id: str, owner: dict[str, str]) -> None:
    server.ACCESSORY_CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    payload = {
        "id": candidate_id,
        "class_id": -1,
        "name": candidate_id,
        "material_type": "object",
        "status": "candidate_review",
        "source_files": [],
        "created_at": now,
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
        "codex_image_jobs": [
            {
                "job_id": f"img_{candidate_id}",
                "status": "completed",
                "progress": 100,
                "created_at": now,
                "note": "seeded smoke job",
            }
        ],
    }
    (server.ACCESSORY_CANDIDATES_DIR / f"{candidate_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def seed_pipeline_task(task_id: str, owner: dict[str, str]) -> dict[str, object]:
    now = int(time.time())
    return {
        "id": task_id,
        "name": task_id,
        "accessory_ids": [],
        "accessory_counts": {},
        "detection_method": "ai",
        "stage": "draft",
        "status": "ready",
        "progress": 0,
        "params": {"route": "ai"},
        "auto_advance": False,
        "created_at": now,
        "updated_at": now,
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }


def assert_created_and_owned(items: list[dict], owner: dict[str, str] | None, label: str) -> None:
    for item in items:
        if not item.get("created_at"):
            raise AssertionError(f"{label}: missing created_at on {item}")
        if owner and item.get("owner_user_id") != owner["id"]:
            raise AssertionError(f"{label}: expected owner {owner['id']}, got {item.get('owner_user_id')}")


def main() -> None:
    assert_api_route_permissions()
    assert_timestamp_ui_hooks()
    client = TestClient(server.app, base_url="https://testserver")

    response = client.get("/api/auth/status")
    assert_status(response, 200, "initial auth status")
    assert response.json()["setup_required"] is True

    response = client.get("/api/status")
    assert_status(response, 503, "protected API before first admin")

    response = client.post(
        "/api/auth/bootstrap",
        json={"username": "admin", "display_name": "Admin", "password": "admin-password-1"},
    )
    assert_status(response, 200, "bootstrap admin")
    assert_no_password_secrets(response.json(), "bootstrap response")
    admin_user = response.json()["user"]
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie and "secure" in set_cookie and "samesite=lax" in set_cookie

    created_users: dict[str, dict[str, str]] = {}
    user_specs = {
        "operator_a": ["accessory_library", "training_pipeline", "label_sheet"],
        "operator_b": ["accessory_library", "training_pipeline", "label_sheet"],
        "zero_user": [],
        "locater": ["locate_anything"],
        "manager": ["user_management"],
    }
    for username, permissions in user_specs.items():
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
        assert_no_password_secrets(response.json(), f"create {username} response")
        created_users[username] = response.json()["user"]
        if username == "manager" and "user_management" in created_users[username].get("permissions", []):
            raise AssertionError("user_management must not be grantable to normal users")

    users_payload = client.get("/api/auth/users").json()
    assert_no_password_secrets(users_payload, "admin user list response")

    seed_training_task("job_train_a", created_users["operator_a"])
    seed_training_task("job_train_b", created_users["operator_b"])
    seed_config_accessory("acc_b_private", "B private", created_users["operator_b"])
    seed_dataset("dataset_a", created_users["operator_a"])
    seed_dataset("dataset_b", created_users["operator_b"])
    seed_dataset("legacy_dataset", None)
    seed_model_run("job_train_a", created_users["operator_a"])
    seed_model_run("job_train_b", created_users["operator_b"])
    server.save_ai_detection_tasks([
        seed_ai_task("aitask_a", created_users["operator_a"]),
        seed_ai_task("aitask_b", created_users["operator_b"]),
    ])
    seed_candidate("cand_a", created_users["operator_a"])
    seed_candidate("cand_b", created_users["operator_b"])
    server.save_pipeline_tasks([
        seed_pipeline_task("pipe_a", created_users["operator_a"]),
        seed_pipeline_task("pipe_b", created_users["operator_b"]),
    ])
    server.save_pipeline_state({"accessory_ids": [], "pending_candidate_ids": ["cand_a", "cand_b"]})

    logout(client, "admin logout")

    login(client, "zero_user", "zero_user-password-1")

    response = client.post(
        "/api/stream/config",
        json={"enabled": True, "source": "rtsp", "url": "rtsp://example.invalid/stream"},
    )
    assert_status(response, 403, "zero-permission user stream config mutation denied")

    response = client.post("/api/experimental/label-inspector/analyze")
    assert_status(response, 403, "zero-permission user experimental label inspector denied before validation")

    response = client.get("/api/backgrounds/not-a-set/not-an-image.png")
    assert_status(response, 403, "zero-permission user direct background image denied")

    logout(client, "zero_user logout")
    login(client, "locater", "locater-password-1")

    response = client.get("/api/locateanything/status")
    assert_status(response, 200, "locate user persisted status allowed")

    response = client.get("/api/locateanything/status?endpoint_url=http://127.0.0.1:1/secret")
    assert_status(response, 403, "locate user endpoint override status denied")

    response = client.post(
        "/api/locateanything/inspect",
        data={"rules": "[]", "endpoint_url": "http://127.0.0.1:1/secret"},
        files={"file": ("part.png", TINY_PNG, "image/png")},
    )
    assert_status(response, 403, "locate user endpoint override inspect denied")

    response = client.post(
        "/api/locateanything/locate",
        data={"prompt": "part", "endpoint_url": "http://127.0.0.1:1/secret"},
        files={"file": ("part.png", TINY_PNG, "image/png")},
    )
    assert_status(response, 403, "locate user endpoint override locate denied")

    logout(client, "locater logout")
    login(client, "manager", "manager-password-1")

    response = client.get("/api/auth/status")
    assert_status(response, 200, "manager auth status")
    manager_permissions = response.json().get("user", {}).get("permissions", [])
    if "user_management" in manager_permissions:
        raise AssertionError("manager unexpectedly retained user_management permission")

    response = client.get("/api/auth/users")
    assert_status(response, 403, "non-admin user_management list users denied")
    assert_no_password_secrets(response.json(), "non-admin user_management list users response")

    response = client.post(
        "/api/auth/users",
        json={
            "username": "manager_created_user",
            "display_name": "manager_created_user",
            "password": "manager-created-password-1",
            "role": "user",
            "permissions": ["inspection"],
        },
    )
    assert_status(response, 403, "non-admin user_management create user denied")
    assert_no_password_secrets(response.json(), "non-admin user_management create user response")

    response = client.patch(
        f"/api/auth/users/{created_users['operator_b']['id']}",
        json={"display_name": "manager renamed operator_b"},
    )
    assert_status(response, 403, "non-admin user_management update user denied")
    assert_no_password_secrets(response.json(), "non-admin user_management update user response")

    response = client.post(
        f"/api/auth/users/{created_users['operator_b']['id']}/password",
        json={"password": "operator_b-manager-reset-1", "revoke_sessions": True},
    )
    assert_status(response, 403, "non-admin user_management reset endpoint denied")
    assert_no_password_secrets(response.json(), "non-admin user_management reset denied response")

    response = client.patch(
        f"/api/auth/users/{created_users['operator_b']['id']}",
        json={"password": "operator_b-manager-patch-1"},
    )
    assert_status(response, 403, "non-admin user_management patch password denied")
    assert_no_password_secrets(response.json(), "non-admin user_management patch password response")

    response = client.post(
        f"/api/auth/users/{admin_user['id']}/password",
        json={"password": "admin-manager-reset-1", "revoke_sessions": True},
    )
    assert_status(response, 403, "non-admin user_management reset admin denied")
    assert_no_password_secrets(response.json(), "non-admin user_management reset admin response")

    response = client.delete(f"/api/auth/users/{created_users['operator_b']['id']}")
    assert_status(response, 403, "non-admin user_management delete user denied")
    assert_no_password_secrets(response.json(), "non-admin user_management delete user response")

    probe = TestClient(server.app, base_url="https://testserver")
    response = probe.post("/api/auth/login", json={"username": "operator_b", "password": "operator_b-password-1"})
    assert_status(response, 200, "operator_b old password still valid after manager denial")
    assert_no_password_secrets(response.json(), "operator_b old-password login after manager denial")
    logout(probe, "operator_b manager-denial probe logout")
    response = probe.post("/api/auth/login", json={"username": "admin", "password": "admin-password-1"})
    assert_status(response, 200, "admin old password still valid after manager denial")
    assert_no_password_secrets(response.json(), "admin old-password login after manager denial")
    logout(probe, "admin manager-denial probe logout")

    logout(client, "manager logout")
    login(client, "operator_a", "operator_a-password-1")

    response = client.post("/api/ai/config", json={"provider": "gemini"})
    assert_status(response, 403, "normal user direct AI config mutation denied")

    response = client.post(
        f"/api/auth/users/{created_users['operator_b']['id']}/password",
        json={"password": "operator_b-forbidden-reset-1", "revoke_sessions": True},
    )
    assert_status(response, 403, "normal user direct password reset denied")
    assert_no_password_secrets(response.json(), "normal user reset denied response")

    response = client.get("/api/config")
    assert_status(response, 403, "normal user full config denied")

    response = client.post(
        "/api/accessories",
        data={"name": "A owned label", "material_type": "text", "training_role": "detect_and_classify"},
        files=[],
    )
    assert_status(response, 200, "operator_a create accessory")
    accessory_id = response.json()["item"]["id"]

    response = client.post(
        "/api/label-sheets/references",
        data={"annotation": "operator a label"},
        files=[("files", ("operator_a_label.png", TINY_PNG, "image/png"))],
    )
    assert_status(response, 200, "operator_a create label reference")
    label_item = response.json()["item"]
    label_reference_id = label_item["id"]
    assert label_item["owner_user_id"] == created_users["operator_a"]["id"]
    assert all(reference["accessory_id"] == label_reference_id for reference in response.json()["references"])

    seed_training_status_for_owner(created_users["operator_b"], "acc_b_private", "B private")
    assert_operator_a_training_hides_b(client, created_users["operator_b"], "operator_a training status hides operator_b state")
    assert_training_status_does_not_hydrate_hidden_task(
        client,
        created_users["operator_a"],
        created_users["operator_b"],
        label_reference_id,
    )

    before_ids = persisted_accessory_ids()
    assert "acc_b_private" in before_ids
    response = client.post(
        "/api/training/preview",
        json={"selected_accessory_ids": [label_reference_id], "sample_count": 1, "preview_count": 1},
    )
    assert_status(response, 200, "operator_a training preview preserves other users")
    assert "acc_b_private" in persisted_accessory_ids()
    assert_operator_a_training_hides_b(client, created_users["operator_b"], "operator_a preview status does not inherit operator_b fields")
    logout(client, "operator_a logout after preview")
    login(client, "operator_b", "operator_b-password-1")
    assert_operator_b_training_preserved(client, created_users["operator_b"], "operator_b training state preserved after operator_a preview")
    logout(client, "operator_b logout after preview preservation check")
    login(client, "operator_a", "operator_a-password-1")

    install_fake_training_enqueue()
    response = client.post(
        "/api/training/generate",
        json={"selected_accessory_ids": [label_reference_id], "sample_count": 1},
    )
    assert_status(response, 200, "operator_a training generate preserves other users")
    assert "acc_b_private" in persisted_accessory_ids()
    assert_operator_a_training_hides_b(client, created_users["operator_b"], "operator_a generate status does not expose operator_b")
    logout(client, "operator_a logout after generate")
    login(client, "operator_b", "operator_b-password-1")
    assert_operator_b_training_preserved(client, created_users["operator_b"], "operator_b training state preserved after operator_a generate")
    logout(client, "operator_b logout after generate preservation check")
    login(client, "operator_a", "operator_a-password-1")

    response = client.post(
        "/api/training/start",
        json={"selected_accessory_ids": [label_reference_id], "sample_count": 1, "epochs": 1, "image_size": 320},
    )
    assert_status(response, 200, "operator_a training start preserves other users")
    assert "acc_b_private" in persisted_accessory_ids()
    assert_operator_a_training_hides_b(client, created_users["operator_b"], "operator_a start status does not expose operator_b")
    logout(client, "operator_a logout after start")
    login(client, "operator_b", "operator_b-password-1")
    assert_operator_b_training_preserved(client, created_users["operator_b"], "operator_b training state preserved after operator_a start")
    assert_training_status_hydrates_active_task(client, created_users["operator_b"])
    logout(client, "operator_b logout after start preservation check")
    login(client, "operator_a", "operator_a-password-1")

    response = client.get("/api/accessories")
    assert_status(response, 200, "operator_a list own accessories")
    assert {item["id"] for item in response.json()["items"]} == {accessory_id, label_reference_id}

    response = client.get("/api/training/resources")
    assert_status(response, 200, "operator_a training resources")
    payload = response.json()
    assert {task["job_id"] for task in payload["tasks"]} == {"job_train_a"}
    assert {task["job_id"] for task in payload["training_tasks"]} == {"job_train_a"}
    assert "dataset_a" in {item["id"] for item in payload["datasets"]}
    assert "dataset_b" not in {item["id"] for item in payload["datasets"]}
    assert "legacy_dataset" not in {item["id"] for item in payload["datasets"]}
    assert {item["run_id"] for item in payload["models"]} == {"job_train_a"}
    assert {item["id"] for item in payload["ai_detection_tasks"]} == {"aitask_a"}
    assert_created_and_owned(payload["datasets"], created_users["operator_a"], "operator_a datasets")
    assert_created_and_owned(payload["models"], created_users["operator_a"], "operator_a models")
    assert_created_and_owned(payload["ai_detection_tasks"], created_users["operator_a"], "operator_a ai tasks")

    response = client.get("/api/training/resources?include_samples=true")
    assert_status(response, 200, "operator_a training resources with samples")
    dataset_a = next(item for item in response.json()["datasets"] if item["id"] == "dataset_a")
    assert dataset_a["samples"][0]["created_at"], "dataset sample must include created_at"

    response = client.get("/api/image-jobs")
    assert_status(response, 200, "operator_a image jobs")
    image_payload = response.json()
    assert "cand_a" in {item.get("candidate_id") for item in image_payload["items"]}
    assert "cand_b" not in {item.get("candidate_id") for item in image_payload["items"]}
    assert_created_and_owned(image_payload["items"], created_users["operator_a"], "operator_a image jobs")

    response = client.get("/api/pipeline/tasks")
    assert_status(response, 200, "operator_a pipeline tasks")
    pipeline_payload = response.json()
    assert {item["id"] for item in pipeline_payload["items"]} == {"pipe_a"}
    assert {item["id"] for item in pipeline_payload["pending_candidates"]} == {"cand_a"}
    assert_created_and_owned(pipeline_payload["items"], created_users["operator_a"], "operator_a pipeline tasks")
    assert_created_and_owned(pipeline_payload["pending_candidates"], created_users["operator_a"], "operator_a pipeline candidates")

    response = client.request("DELETE", f"/api/accessories/{accessory_id}/files", json={"source_path": "/etc/passwd"})
    assert_status(response, 404, "path traversal/unregistered file delete denied")

    logout(client, "operator_a logout")
    login(client, "operator_b", "operator_b-password-1")

    response = client.get("/api/accessories")
    assert_status(response, 200, "operator_b list isolated accessories")
    assert {item["id"] for item in response.json()["items"]} == {"acc_b_private"}

    response = client.get("/api/label-sheets/references")
    assert_status(response, 200, "operator_b label references isolated")
    assert response.json()["references"] == []

    response = client.get("/api/training/resources")
    assert_status(response, 200, "operator_b training resources")
    payload = response.json()
    assert {task["job_id"] for task in payload["tasks"]} == {"job_train_b"}
    assert {task["job_id"] for task in payload["training_tasks"]} == {"job_train_b"}
    assert "dataset_b" in {item["id"] for item in payload["datasets"]}
    assert "dataset_a" not in {item["id"] for item in payload["datasets"]}
    assert "legacy_dataset" not in {item["id"] for item in payload["datasets"]}
    assert {item["run_id"] for item in payload["models"]} == {"job_train_b"}
    assert {item["id"] for item in payload["ai_detection_tasks"]} == {"aitask_b"}
    assert_created_and_owned(payload["datasets"], created_users["operator_b"], "operator_b datasets")
    assert_created_and_owned(payload["models"], created_users["operator_b"], "operator_b models")
    assert_created_and_owned(payload["ai_detection_tasks"], created_users["operator_b"], "operator_b ai tasks")

    response = client.get("/api/training/resources/datasets/dataset_a/detail")
    assert_status(response, 404, "operator_b cannot read operator_a dataset detail")

    response = client.get("/api/accessories/candidates/cand_a")
    assert_status(response, 404, "operator_b cannot read operator_a image candidate")

    response = client.get("/api/image-jobs")
    assert_status(response, 200, "operator_b image jobs")
    image_payload = response.json()
    assert "cand_b" in {item.get("candidate_id") for item in image_payload["items"]}
    assert "cand_a" not in {item.get("candidate_id") for item in image_payload["items"]}
    assert_created_and_owned(image_payload["items"], created_users["operator_b"], "operator_b image jobs")

    response = client.get("/api/pipeline/tasks")
    assert_status(response, 200, "operator_b pipeline tasks")
    pipeline_payload = response.json()
    assert {item["id"] for item in pipeline_payload["items"]} == {"pipe_b"}
    assert {item["id"] for item in pipeline_payload["pending_candidates"]} == {"cand_b"}
    assert_created_and_owned(pipeline_payload["items"], created_users["operator_b"], "operator_b pipeline tasks")
    assert_created_and_owned(pipeline_payload["pending_candidates"], created_users["operator_b"], "operator_b pipeline candidates")

    response = client.delete(f"/api/accessories/{accessory_id}")
    assert_status(response, 404, "operator_b cannot delete operator_a accessory")

    logout(client, "operator_b logout")
    login(client, "admin", "admin-password-1")

    response = client.get("/api/accessories")
    assert_status(response, 200, "admin sees all accessories")
    assert {accessory_id, label_reference_id, "acc_b_private"}.issubset({item["id"] for item in response.json()["items"]})

    response = client.get("/api/training/resources")
    assert_status(response, 200, "admin sees all training resources")
    payload = response.json()
    assert {"dataset_a", "dataset_b", "legacy_dataset"}.issubset({item["id"] for item in payload["datasets"]})
    assert {"job_train_a", "job_train_b"}.issubset({item["run_id"] for item in payload["models"]})
    assert {"aitask_a", "aitask_b"}.issubset({item["id"] for item in payload["ai_detection_tasks"]})
    assert all(item.get("created_at") for item in payload["datasets"]), "admin datasets must include created_at"

    response = client.get("/api/training/status")
    assert_status(response, 200, "admin sees aggregate training states")
    admin_status_text = json.dumps(response.json(), ensure_ascii=False)
    assert "training_states" in response.json()
    assert "train_b_secret" in admin_status_text
    assert "acc_b_private" in admin_status_text
    assert_admin_aggregate_hydrates_child_training_state(client, created_users["operator_a"], label_reference_id)

    response = client.get(f"/api/training/status?user_id={created_users['operator_b']['id']}")
    assert_status(response, 200, "admin filters training status to operator_b")
    operator_b_status_text = json.dumps(response.json(), ensure_ascii=False)
    assert "train_b_secret" in operator_b_status_text
    assert "acc_b_private" in operator_b_status_text
    assert created_users["operator_b"]["id"] in operator_b_status_text

    response = client.get(f"/api/training/status?user_id={created_users['operator_a']['id']}")
    assert_status(response, 200, "admin filters training status to operator_a")
    operator_a_status_text = json.dumps(response.json(), ensure_ascii=False)
    assert "train_b_secret" not in operator_a_status_text
    assert "acc_b_private" not in operator_a_status_text

    response = client.get(f"/api/training/resources?user_id={created_users['operator_a']['id']}")
    assert_status(response, 200, "admin filters training resources to operator_a")
    scoped = response.json()
    assert "dataset_a" in {item["id"] for item in scoped["datasets"]}
    assert "dataset_b" not in {item["id"] for item in scoped["datasets"]}
    assert "legacy_dataset" not in {item["id"] for item in scoped["datasets"]}
    assert {item["run_id"] for item in scoped["models"]} == {"job_train_a"}
    assert {item["id"] for item in scoped["ai_detection_tasks"]} == {"aitask_a"}
    assert_created_and_owned(scoped["datasets"], created_users["operator_a"], "admin scoped datasets")

    response = client.get("/api/training/resources?user_id=legacy_admin")
    assert_status(response, 200, "admin filters legacy training resources")
    legacy = response.json()
    assert {item["id"] for item in legacy["datasets"]} == {"legacy_dataset"}
    assert legacy["models"] == []
    assert legacy["ai_detection_tasks"] == []

    response = client.get(f"/api/image-jobs?user_id={created_users['operator_a']['id']}")
    assert_status(response, 200, "admin filters image jobs to operator_a")
    image_payload = response.json()
    assert "cand_a" in {item.get("candidate_id") for item in image_payload["items"]}
    assert "cand_b" not in {item.get("candidate_id") for item in image_payload["items"]}
    assert_created_and_owned(image_payload["items"], created_users["operator_a"], "admin scoped image jobs")

    response = client.get(f"/api/pipeline/tasks?user_id={created_users['operator_a']['id']}")
    assert_status(response, 200, "admin filters pipeline to operator_a")
    pipeline_payload = response.json()
    assert {item["id"] for item in pipeline_payload["items"]} == {"pipe_a"}
    assert {item["id"] for item in pipeline_payload["pending_candidates"]} == {"cand_a"}
    assert_created_and_owned(pipeline_payload["items"], created_users["operator_a"], "admin scoped pipeline tasks")
    assert_created_and_owned(pipeline_payload["pending_candidates"], created_users["operator_a"], "admin scoped pipeline candidates")

    users_response = client.get("/api/auth/users")
    assert_status(users_response, 200, "admin user list")
    assert_no_password_secrets(users_response.json(), "admin user list after data checks")
    users = users_response.json()["users"]
    operator_b = next(user for user in users if user["username"] == "operator_b")
    operator_a = next(user for user in users if user["username"] == "operator_a")

    new_operator_b_password = "operator_b-reset-password-1"
    response = client.post(
        f"/api/auth/users/{operator_b['id']}/password",
        json={"password": new_operator_b_password, "revoke_sessions": True},
    )
    assert_status(response, 200, "admin resets operator_b password")
    assert_no_password_secrets(response.json(), "admin reset response")
    if "temporary_password" in response.json():
        raise AssertionError("admin set-password response must not include temporary_password")

    probe = TestClient(server.app, base_url="https://testserver")
    response = probe.post("/api/auth/login", json={"username": "operator_b", "password": "operator_b-password-1"})
    assert_status(response, 401, "operator_b old password rejected after reset")
    response = probe.post("/api/auth/login", json={"username": "operator_b", "password": new_operator_b_password})
    assert_status(response, 200, "operator_b new password accepted after reset")
    assert_no_password_secrets(response.json(), "operator_b new-password login response")
    logout(probe, "operator_b probe logout")

    response = client.post(
        f"/api/auth/users/{operator_a['id']}/password",
        json={"generate": True, "revoke_sessions": True},
    )
    assert_status(response, 200, "admin generates operator_a temporary password")
    generated_payload = response.json()
    assert_no_password_secrets(generated_payload, "admin generated password response", allow_temporary=True)
    temporary_password = generated_payload.get("temporary_password")
    if not temporary_password:
        raise AssertionError("generated password response missing one-time temporary_password")

    probe = TestClient(server.app, base_url="https://testserver")
    response = probe.post("/api/auth/login", json={"username": "operator_a", "password": "operator_a-password-1"})
    assert_status(response, 401, "operator_a old password rejected after temp generation")
    response = probe.post("/api/auth/login", json={"username": "operator_a", "password": temporary_password})
    assert_status(response, 200, "operator_a generated temporary password accepted")
    assert_no_password_secrets(response.json(), "operator_a temp-password login response")
    logout(probe, "operator_a probe logout")

    users_response = client.get("/api/auth/users")
    assert_status(users_response, 200, "admin user list after password resets")
    assert_no_password_secrets(users_response.json(), "admin user list after password resets")

    response = client.patch(
        f"/api/auth/users/{operator_b['id']}",
        json={"permissions": ["accessory_library", "ai_config"]},
    )
    assert_status(response, 200, "admin updates permissions")

    print("auth/RBAC smoke passed")


if __name__ == "__main__":
    main()
