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

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_unique_names_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from local_inspection_service import server  # noqa: E402


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text[:500]}")


def bootstrap_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/bootstrap",
        json={"username": "admin", "display_name": "Admin", "password": "admin-password-1"},
    )
    assert_status(response, 200, "bootstrap admin")
    return response.json()["user"]


def create_accessory(client: TestClient, name: str):
    return client.post(
        "/api/accessories",
        data={
            "name": name,
            "material_type": "object",
            "material_alpha_policy": "opaque",
            "training_role": "detect_and_classify",
        },
    )


def seed_dataset(dataset_id: str, display_name: str, owner: dict[str, str], accessory_id: str) -> Path:
    dataset_dir = server.output_write_dir_for_owner("training_datasets", owner["id"]) / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": dataset_id,
        "task_id": dataset_id,
        "display_name": display_name,
        "sample_count": 0,
        "selected_accessory_ids": [accessory_id],
        "samples": [],
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }
    (dataset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return dataset_dir


def seed_model(run_id: str, display_name: str, owner: dict[str, str], accessory_id: str) -> None:
    dataset_dir = seed_dataset(f"dataset_for_{run_id}", f"dataset {run_id}", owner, accessory_id)
    run_dir = server.output_write_dir_for_owner("training_runs", owner["id"]) / run_id
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    (weights_dir / "best.pt").write_bytes(b"placeholder")
    (run_dir / "library_metadata.json").write_text(json.dumps({"display_name": display_name}), encoding="utf-8")
    task = {
        "job_id": run_id,
        "task_id": run_id,
        "action": "train_model",
        "status": "completed",
        "label": display_name,
        "dataset_dir": str(dataset_dir),
        "manifest_path": str(dataset_dir / "manifest.json"),
        "training_run_dir": str(run_dir),
        "selected_accessory_ids": [accessory_id],
        "required_accessory_counts": {accessory_id: 1},
        "model_variant": "yolo",
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }
    server.save_training_task(task)


def main() -> None:
    client = TestClient(server.app, base_url="https://testserver")
    admin = bootstrap_admin(client)
    common_name = "同名资源"

    response = create_accessory(client, common_name)
    assert_status(response, 200, "create first accessory")
    accessory_id = response.json()["item"]["id"]
    assert_status(create_accessory(client, common_name), 409, "reject duplicate accessory name")

    response = client.post("/api/pipeline/tasks", json={"name": common_name, "accessory_ids": []})
    assert_status(response, 200, "allow same name across accessory and task categories")
    pipeline_task_id = response.json()["id"]
    assert_status(client.post("/api/pipeline/tasks", json={"name": common_name, "accessory_ids": []}), 409, "reject duplicate pipeline task name")

    ai_payload = {"name": common_name, "required_accessory_counts": {accessory_id: 1}}
    assert_status(client.post("/api/ai/tasks", json=ai_payload), 409, "reject duplicate AI task name against task library")
    response = client.post("/api/ai/tasks", json={"name": "AI 唯一任务", "required_accessory_counts": {accessory_id: 1}})
    assert_status(response, 200, "create unique AI task")
    ai_task_id = response.json()["task"]["id"]
    assert_status(client.get("/api/pipeline/tasks"), 200, "sync AI task into pipeline library")
    assert_status(
        client.put(f"/api/ai/tasks/{ai_task_id}", json={"name": "AI 唯一任务", "required_accessory_counts": {accessory_id: 1}}),
        200,
        "allow AI task update with its own pipeline mirror",
    )
    assert_status(client.put(f"/api/ai/tasks/{ai_task_id}", json=ai_payload), 409, "reject AI rename to duplicate task name")

    response = client.patch(f"/api/pipeline/tasks/{pipeline_task_id}", json={"name": "流水线唯一任务"})
    assert_status(response, 200, "rename pipeline task to unique name")
    pipeline_ai_payload = {"name": "AI 流水线唯一任务", "accessory_ids": [accessory_id], "detection_method": "ai"}
    assert_status(client.post("/api/pipeline/tasks", json=pipeline_ai_payload), 200, "create unique AI pipeline task")
    assert_status(client.post("/api/pipeline/tasks", json=pipeline_ai_payload), 409, "reject duplicate AI pipeline task name")

    seed_dataset("dataset_a", "样本 A", admin, accessory_id)
    seed_dataset("dataset_b", "样本 B", admin, accessory_id)
    assert_status(
        client.patch("/api/training/resources/datasets/dataset_b", json={"display_name": "样本 A"}),
        409,
        "reject duplicate dataset display name",
    )
    assert_status(
        client.patch("/api/training/resources/datasets/dataset_b", json={"display_name": common_name}),
        200,
        "allow same name across dataset and other categories",
    )

    seed_model("model_a", "模型 A", admin, accessory_id)
    seed_model("model_b", "模型 B", admin, accessory_id)
    assert_status(
        client.patch("/api/training/resources/models/model_b", json={"display_name": "模型 A"}),
        409,
        "reject duplicate model display name",
    )
    assert_status(
        client.patch("/api/training/resources/models/model_b", json={"display_name": common_name}),
        200,
        "allow same name across model and other categories",
    )

    print("smoke_unique_resource_names: ok")


if __name__ == "__main__":
    main()
