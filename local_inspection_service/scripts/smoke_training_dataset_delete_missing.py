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

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_delete_missing_dataset_"))
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


def user_dataset_dir(user: dict[str, str], dataset_id: str) -> Path:
    return server.OUTPUT_DIR / "users" / user["id"] / "training_datasets" / dataset_id


def seed_dataset(dataset_id: str, owner: dict[str, str], *, missing_sample_file: bool = False) -> Path:
    dataset_dir = user_dataset_dir(owner, dataset_id)
    image_dir = dataset_dir / "images" / "train"
    label_dir = dataset_dir / "labels" / "train"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / "sample_000001.png"
    label_path = label_dir / "sample_000001.txt"
    if not missing_sample_file:
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        label_path.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    manifest = {
        "id": dataset_id,
        "display_name": dataset_id,
        "sample_count": 1,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
        "samples": [{"image": str(image_path), "labels": str(label_path), "split": "train"}],
    }
    (dataset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return dataset_dir


def seed_training_task(job_id: str, dataset_dir: Path, owner: dict[str, str], action: str = "generate_samples") -> None:
    server.TRAINING_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    task = {
        "job_id": job_id,
        "task_id": job_id,
        "action": action,
        "status": "completed",
        "progress": 100,
        "label": job_id,
        "dataset_dir": str(dataset_dir),
        "manifest_path": str(dataset_dir / "manifest.json"),
        "sample_count": 1,
        "completed_samples": 1,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }
    server.training_task_path(job_id).write_text(json.dumps(task), encoding="utf-8")


def dataset_ids(payload: dict[str, object]) -> set[str]:
    return {str(item.get("id") or "") for item in payload.get("datasets", []) if isinstance(item, dict)}


def dataset_by_id(payload: dict[str, object], dataset_id: str) -> dict[str, object] | None:
    return next(
        (
            item
            for item in payload.get("datasets", [])
            if isinstance(item, dict) and str(item.get("id") or "") == dataset_id
        ),
        None,
    )


def main() -> None:
    client = TestClient(server.app, base_url="https://testserver")
    admin = bootstrap_admin(client)

    missing_dataset_id = "missing_dataset_smoke"
    missing_dataset_dir = user_dataset_dir(admin, missing_dataset_id)
    seed_training_task("missing_task_smoke", missing_dataset_dir, admin)

    response = client.get("/api/training/resources")
    assert_status(response, 200, "resources before missing delete")
    missing_dataset = dataset_by_id(response.json(), missing_dataset_id)
    if not missing_dataset or not missing_dataset.get("missing_files"):
        raise AssertionError("missing training task dataset was not listed as missing")

    response = client.delete(f"/api/training/resources/datasets/{missing_dataset_id}")
    assert_status(response, 200, "delete missing dataset")
    if missing_dataset_id in dataset_ids(response.json()):
        raise AssertionError("missing dataset still listed after delete")
    task = server.load_training_task(server.training_task_path("missing_task_smoke")) or {}
    if task.get("dataset_status") != "deleted":
        raise AssertionError("training task was not marked deleted for missing dataset")

    actual_dataset_id = "actual_dataset_smoke"
    actual_dataset_dir = seed_dataset(actual_dataset_id, admin)
    seed_training_task("actual_task_smoke", actual_dataset_dir, admin)
    response = client.delete(f"/api/training/resources/datasets/{actual_dataset_id}")
    assert_status(response, 200, "delete actual dataset")
    if actual_dataset_dir.exists():
        raise AssertionError("actual dataset directory still exists after delete")
    if actual_dataset_id in dataset_ids(response.json()):
        raise AssertionError("actual deleted dataset reappeared as a missing dataset")

    orphan_sample_dataset_id = "orphan_sample_dataset_smoke"
    seed_dataset(orphan_sample_dataset_id, admin, missing_sample_file=True)
    response = client.delete(f"/api/training/resources/datasets/{orphan_sample_dataset_id}/samples/sample_000001.png")
    assert_status(response, 200, "delete manifest-only sample")
    manifest = json.loads((user_dataset_dir(admin, orphan_sample_dataset_id) / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("samples") or manifest.get("sample_count") != 0:
        raise AssertionError("manifest-only sample was not removed from the dataset manifest")

    print("smoke_training_dataset_delete_missing: ok")


if __name__ == "__main__":
    main()
