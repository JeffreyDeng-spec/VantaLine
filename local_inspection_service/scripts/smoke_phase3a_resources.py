#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_phase3a_smoke_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from local_inspection_service import server  # noqa: E402

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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


def seed_accessory(accessory_id: str, name: str, owner: dict[str, str]) -> str:
    source_dir = server.UPLOAD_DIR / "accessories" / accessory_id
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.png"
    source_path.write_bytes(TINY_PNG)
    config = server.load_config()
    config["accessories"] = [
        item for item in config.get("accessories", []) if str(item.get("id") or server.accessory_uid(item)) != accessory_id
    ]
    config["accessories"].append(
        {
            "id": accessory_id,
            "class_id": 7000 + len(config["accessories"]),
            "name": name,
            "label": name,
            "material_type": "object",
            "material_alpha_policy": "opaque",
            "object_alpha_policy_label": "不透明",
            "training_role": "detect_and_classify",
            "detection_route": "yolo",
            "physical_size": server.physical_size_payload("object"),
            "status": "active",
            "source_files": [str(source_path)],
            "created_at": int(time.time()),
            "owner_user_id": owner["id"],
            "owner_username": owner["username"],
        }
    )
    server.save_config(config)
    return str(source_path)


def seed_dataset(dataset_id: str, owner: dict[str, str] | None, accessory_id: str) -> None:
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
    now = int(time.time())
    manifest = {
        "id": dataset_id,
        "task_id": dataset_id,
        "display_name": dataset_id,
        "created_at": now,
        "updated_at": now,
        "sample_count": 1,
        "selected_accessory_ids": [accessory_id],
        "samples": [
            {
                "image": str(image_path),
                "labels": str(label_path),
                "url": server.public_output_url(image_path),
                "split": "train",
                "is_true": True,
            }
        ],
    }
    if owner:
        manifest["owner_user_id"] = owner["id"]
        manifest["owner_username"] = owner["username"]
    (dataset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def seed_model_run(job_id: str, owner: dict[str, str], accessory_id: str, dataset_id: str) -> None:
    server.TRAINING_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    dataset_dir = server.OUTPUT_DIR / "users" / owner["id"] / "training_datasets" / dataset_id
    run_dir = server.OUTPUT_DIR / "users" / owner["id"] / "training_runs" / job_id
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    (weights_dir / "best.pt").write_bytes(b"placeholder model")
    (run_dir / "library_metadata.json").write_text(json.dumps({"display_name": f"model {job_id}"}), encoding="utf-8")
    now = int(time.time())
    task = {
        "job_id": job_id,
        "task_id": job_id,
        "action": "train_model",
        "status": "completed",
        "label": job_id,
        "dataset_dir": str(dataset_dir),
        "manifest_path": str(dataset_dir / "manifest.json"),
        "training_log_path": str(run_dir / "train.log"),
        "sample_count": 1,
        "completed_samples": 1,
        "epochs": 1,
        "current_epoch": 1,
        "total_epochs": 1,
        "image_size": 320,
        "model_variant": "yolo",
        "selected_accessory_ids": [accessory_id],
        "required_accessory_counts": {accessory_id: 1},
        "created_at": now,
        "updated_at": now,
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }
    server.training_task_path(job_id).write_text(json.dumps(task), encoding="utf-8")


def seed_ai_task(task_id: str, owner: dict[str, str], accessory_id: str, accessory_name: str) -> dict[str, object]:
    now = int(time.time())
    return {
        "id": task_id,
        "name": f"AI task {task_id}",
        "selected_accessory_ids": [accessory_id],
        "required_accessory_counts": {accessory_id: 1},
        "accessory_labels": {accessory_id: accessory_name},
        "created_at": now,
        "updated_at": now,
        "source": "smoke_phase3a",
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }


def assert_react_ai_task_delete_gated() -> None:
    source = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "features" / "training" / "TrainingLibraryPage.tsx").read_text(encoding="utf-8")
    expected = {
        "permission helper import": 'import { hasPermission } from "../../app/permissions";',
        "ai_detection permission check": 'const canDeleteAiTasks = hasPermission(auth.user, "ai_detection");',
        "card delete gate": "{canDeleteAiTasks ? (",
        "modal delete prop": "canDeleteAiTasks={canDeleteAiTasks}",
        "modal delete gate": "aiTask && canDeleteAiTasks",
    }
    missing = [label for label, snippet in expected.items() if snippet not in source]
    if missing:
        raise AssertionError("React AI task delete permission gate missing: " + ", ".join(missing))


def ids(items: list[dict], key: str = "id") -> set[str]:
    return {str(item.get(key)) for item in items}


def main() -> None:
    assert_react_ai_task_delete_gated()
    client = TestClient(server.app, base_url="https://testserver")
    response = client.post(
        "/api/auth/bootstrap",
        json={"username": "admin", "display_name": "Admin", "password": "admin-password-1"},
    )
    assert_status(response, 200, "bootstrap admin")
    operator_a = create_user(client, "operator_a", ["accessory_library", "model_library"])
    operator_b = create_user(client, "operator_b", ["accessory_library", "model_library"])

    source_a = seed_accessory("acc_a", "A private", operator_a)
    seed_accessory("acc_b", "B private", operator_b)
    seed_dataset("dataset_a", operator_a, "acc_a")
    seed_dataset("dataset_b", operator_b, "acc_b")
    seed_dataset("legacy_dataset", None, "legacy")
    seed_model_run("job_train_a", operator_a, "acc_a", "dataset_a")
    seed_model_run("job_train_b", operator_b, "acc_b", "dataset_b")
    server.save_ai_detection_tasks([
        seed_ai_task("aitask_a", operator_a, "acc_a", "A private"),
        seed_ai_task("aitask_b", operator_b, "acc_b", "B private"),
    ])

    logout(client, "admin logout")
    login(client, "operator_a", "operator_a-password-1")

    response = client.get("/api/accessories")
    assert_status(response, 200, "operator_a accessories")
    assert "acc_a" in ids(response.json()["items"])
    assert "acc_b" not in ids(response.json()["items"])

    response = client.get("/api/accessories/acc_a/detail")
    assert_status(response, 200, "operator_a accessory detail")
    detail = response.json()
    gallery_paths = {item.get("source_path") for item in detail["gallery"]}
    if source_a not in gallery_paths:
        raise AssertionError("operator_a detail gallery did not include seeded source image")

    response = client.get("/api/accessories/acc_b/detail")
    assert_status(response, 404, "operator_a cannot read operator_b accessory detail")

    response = client.post("/api/accessories/acc_a/ai-reference", json={"source_path": source_a})
    assert_status(response, 200, "operator_a set accessory AI reference")

    response = client.post("/api/accessories/acc_a/route", json={"route": "locate", "apply": False})
    assert_status(response, 200, "operator_a set accessory route")
    if response.json()["route"] != "locate":
        raise AssertionError("route update did not persist locate")

    response = client.get("/api/training/resources")
    assert_status(response, 200, "operator_a training resources")
    payload = response.json()
    assert "dataset_a" in ids(payload["datasets"])
    assert "dataset_b" not in ids(payload["datasets"])
    assert "job_train_a" in ids(payload["models"], "run_id")
    assert "job_train_b" not in ids(payload["models"], "run_id")
    assert "aitask_a" in ids(payload["ai_detection_tasks"])
    assert "aitask_b" not in ids(payload["ai_detection_tasks"])

    response = client.delete("/api/ai/tasks/aitask_a")
    assert_status(response, 403, "model-library user direct AI task delete denied")
    if response.json().get("permission") != "ai_detection":
        raise AssertionError(f"model-library AI task delete denied by unexpected permission: {response.text[:500]}")

    response = client.get("/api/training/resources/datasets/dataset_a/detail")
    assert_status(response, 200, "operator_a dataset detail")
    if not response.json()["dataset"].get("samples"):
        raise AssertionError("dataset detail did not include samples")

    response = client.patch("/api/training/resources/datasets/dataset_a", json={"display_name": "A renamed", "note": "phase3a"})
    assert_status(response, 200, "operator_a rename dataset")
    renamed = next(item for item in response.json()["datasets"] if item["id"] == "dataset_a")
    if renamed["display_name"] != "A renamed":
        raise AssertionError("dataset rename was not reflected")

    response = client.patch("/api/training/resources/models/job_train_a", json={"display_name": "A model", "note": "phase3a"})
    assert_status(response, 200, "operator_a rename model run")
    response = client.patch("/api/training/tasks/job_train_a", json={"label": "A model task", "note": "phase3a"})
    if response.status_code not in {200, 403}:
        raise AssertionError(f"operator_a best-effort training task rename: unexpected HTTP {response.status_code}: {response.text[:500]}")
    if response.status_code == 403 and response.json().get("permission") != "training_pipeline":
        raise AssertionError(f"operator_a training task rename denied by unexpected permission: {response.text[:500]}")

    logout(client, "operator_a logout")
    login(client, "operator_b", "operator_b-password-1")

    response = client.get("/api/training/resources/datasets/dataset_a/detail")
    assert_status(response, 404, "operator_b cannot read operator_a dataset detail")
    response = client.get("/api/accessories/acc_a/detail")
    assert_status(response, 404, "operator_b cannot read operator_a accessory detail")

    logout(client, "operator_b logout")
    login(client, "admin", "admin-password-1")

    response = client.get("/api/accessories")
    assert_status(response, 200, "admin accessories")
    assert {"acc_a", "acc_b"}.issubset(ids(response.json()["items"]))
    response = client.get(f"/api/accessories?user_id={operator_a['id']}")
    assert_status(response, 200, "admin scoped accessories")
    assert "acc_a" in ids(response.json()["items"])
    assert "acc_b" not in ids(response.json()["items"])

    response = client.get("/api/training/resources")
    assert_status(response, 200, "admin training resources")
    payload = response.json()
    assert {"dataset_a", "dataset_b", "legacy_dataset"}.issubset(ids(payload["datasets"]))
    assert {"job_train_a", "job_train_b"}.issubset(ids(payload["models"], "run_id"))
    assert {"aitask_a", "aitask_b"}.issubset(ids(payload["ai_detection_tasks"]))
    response = client.get(f"/api/training/resources?user_id={operator_a['id']}")
    assert_status(response, 200, "admin scoped training resources")
    scoped = response.json()
    assert "dataset_a" in ids(scoped["datasets"])
    assert "dataset_b" not in ids(scoped["datasets"])
    assert "job_train_a" in ids(scoped["models"], "run_id")
    assert "job_train_b" not in ids(scoped["models"], "run_id")
    assert "aitask_a" in ids(scoped["ai_detection_tasks"])
    assert "aitask_b" not in ids(scoped["ai_detection_tasks"])

    logout(client, "admin logout final")
    login(client, "operator_a", "operator_a-password-1")

    response = client.delete("/api/training/resources/datasets/dataset_a/samples/sample_000001.png")
    assert_status(response, 200, "operator_a delete dataset sample")
    response = client.delete("/api/training/resources/models/job_train_a")
    assert_status(response, 200, "operator_a delete model run")
    response = client.delete("/api/training/resources/datasets/dataset_a")
    assert_status(response, 200, "operator_a delete dataset")

    print("smoke_phase3a_resources: ok")


if __name__ == "__main__":
    main()
