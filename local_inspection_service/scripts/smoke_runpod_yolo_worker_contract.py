#!/usr/bin/env python3
"""Offline contract smoke for the RunPod YOLO training worker."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import requests


SERVICE_DIR = Path(__file__).resolve().parents[1]
WORKER_HANDLER = SERVICE_DIR / "workers" / "vantaline_yolo_train_worker" / "handler.py"
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_worker(work_root: Path):
    os.environ["VANTALINE_RUNPOD_YOLO_ALLOW_MOCK"] = "1"
    os.environ["VANTALINE_RUNPOD_YOLO_WORK_ROOT"] = str(work_root)
    spec = importlib.util.spec_from_file_location("vantaline_runpod_yolo_worker_handler", WORKER_HANDLER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load worker handler from {WORKER_HANDLER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_split(dataset_dir: Path, split: str) -> None:
    image_dir = dataset_dir / "images" / split
    label_dir = dataset_dir / "labels" / split
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / f"{split}_sample.png").write_bytes(ONE_PIXEL_PNG)
    (label_dir / f"{split}_sample.txt").write_text("0 0.500000 0.500000 0.750000 0.750000\n", encoding="utf-8")


def make_dataset_zip(root: Path) -> tuple[bytes, str]:
    dataset_dir = root / "dataset_src"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset.yaml").write_text(
        "\n".join(
            [
                "path: .",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "names:",
                "  0: part",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for split in ("train", "val", "test"):
        write_split(dataset_dir, split)
    archive_path = root / "dataset.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dataset_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(dataset_dir).as_posix())
    payload = archive_path.read_bytes()
    return payload, sha256_bytes(payload)


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def flatten_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            strings.extend(flatten_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(flatten_strings(item))
    return strings


def assert_secret_not_leaked(response: dict[str, Any], label: str) -> None:
    combined = "\n".join(flatten_strings(response))
    forbidden = [
        "SECRET_",
        "X-Amz-Signature",
        "signature=",
        "/private/",
        "/upload?",
        "/base?",
    ]
    for marker in forbidden:
        assert_true(marker not in combined, f"{label} leaked forbidden marker {marker}: {combined}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vantaline_runpod_yolo_smoke_") as tmp:
        tmp_path = Path(tmp)
        worker = load_worker(tmp_path / "worker")
        archive_payload, archive_sha = make_dataset_zip(tmp_path)
        event: dict[str, Any] = {
            "input": {
                "job_id": "smoke_runpod_yolo",
                "train_mode": "yolo",
                "epochs": 1,
                "imgsz": 320,
                "base_model": "yolo11n.pt",
                "dataset_archive_b64": base64.b64encode(archive_payload).decode("ascii"),
                "dataset_sha256": archive_sha,
                "return_artifact_b64": True,
                "mock_train": True,
            }
        }
        result = worker.handler(event)
        assert_true(result.get("ok") is True, f"expected ok result, got {result}")
        assert_true(result.get("status") == "completed", "expected completed status")
        assert_true(result.get("worker") == "vantaline-yolo-train-worker", "worker name mismatch")
        assert_true(result.get("dataset", {}).get("archive_sha256") == archive_sha, "dataset sha mismatch")
        assert_true(result.get("dataset", {}).get("image_count") == 3, "image count mismatch")
        assert_true(result.get("dataset", {}).get("label_count") == 3, "label count mismatch")
        assert_true(result.get("training", {}).get("mock") is True, "mock flag missing")
        assert_true(result.get("inference_smoke", {}).get("status") == "mocked", "mock inference status missing")
        best = result.get("artifacts", {}).get("best_pt", {})
        best_payload = base64.b64decode(str(best.get("artifact_b64") or ""), validate=True)
        assert_true(sha256_bytes(best_payload) == best.get("sha256"), "best.pt inline sha mismatch")

        bad_event = json.loads(json.dumps(event))
        bad_event["input"]["dataset_sha256"] = "0" * 64
        bad = worker.handler(bad_event)
        assert_true(bad.get("ok") is False, "bad checksum should fail")
        assert_true("checksum mismatch" in str(bad.get("error")), "bad checksum error should be explicit")

        bare_model_event = json.loads(json.dumps(event))
        bare_model_event["input"].pop("mock_train", None)
        bare_model_event["input"].pop("return_artifact_b64", None)
        bare_model_event["input"]["base_model"] = "yolo11n.pt"
        bare_model = worker.handler(bare_model_event)
        assert_true(bare_model.get("ok") is False, "bare model name should fail outside mock smoke")
        assert_true("baked container path" in str(bare_model.get("error")), "bare model error should require controlled checkpoint")

        original_get = worker.requests.get
        original_put = worker.requests.put

        def fake_get(url: str, *args: Any, **kwargs: Any) -> Any:
            raise requests.ConnectionError(f"failed to connect to {url}")

        def fake_put(url: str, *args: Any, **kwargs: Any) -> Any:
            raise requests.ConnectionError(f"failed to upload to {url}")

        dataset_url_event = {
            "input": {
                "job_id": "smoke_secret_dataset_url",
                "train_mode": "yolo",
                "epochs": 1,
                "imgsz": 320,
                "base_model": "yolo11n.pt",
                "dataset_url": "https://example.invalid/private/dataset.zip?X-Amz-Signature=SECRET_DATASET_TOKEN",
                "dataset_sha256": archive_sha,
                "mock_train": True,
            }
        }
        worker.requests.get = fake_get
        try:
            dataset_url_result = worker.handler(dataset_url_event)
        finally:
            worker.requests.get = original_get
        assert_true(dataset_url_result.get("ok") is False, "dataset URL network failure should fail")
        assert_secret_not_leaked(dataset_url_result, "dataset_url_result")
        assert_true("download failed for dataset_url" in str(dataset_url_result.get("error")), "dataset URL error should be classified")

        base_model_url_event = {
            "input": {
                "job_id": "smoke_secret_base_model_url",
                "train_mode": "yolo",
                "epochs": 1,
                "imgsz": 320,
                "base_model_url": "https://example.invalid/base?signature=SECRET_BASE_TOKEN",
                "base_model_sha256": "1" * 64,
                "dataset_archive_b64": base64.b64encode(archive_payload).decode("ascii"),
                "dataset_sha256": archive_sha,
            }
        }
        worker.requests.get = fake_get
        try:
            base_model_url_result = worker.handler(base_model_url_event)
        finally:
            worker.requests.get = original_get
        assert_true(base_model_url_result.get("ok") is False, "base model URL network failure should fail")
        assert_secret_not_leaked(base_model_url_result, "base_model_url_result")
        assert_true("download failed for base_model_url" in str(base_model_url_result.get("error")), "base model URL error should be classified")

        artifact_upload_event = json.loads(json.dumps(event))
        artifact_upload_event["input"]["artifact_upload_url"] = "https://example.invalid/upload?signature=SECRET_UPLOAD_TOKEN"
        worker.requests.put = fake_put
        try:
            artifact_upload_result = worker.handler(artifact_upload_event)
        finally:
            worker.requests.put = original_put
        assert_true(artifact_upload_result.get("ok") is False, "artifact upload network failure should fail")
        assert_secret_not_leaked(artifact_upload_result, "artifact_upload_result")
        assert_true("artifact upload failed" in str(artifact_upload_result.get("error")), "artifact upload error should be classified")

        print(
            json.dumps(
                {
                    "ok": True,
                    "worker": result.get("worker"),
                    "job_id": result.get("job_id"),
                    "best_pt_sha256": best.get("sha256"),
                    "negative_checksum_failure": bad.get("error"),
                    "bare_model_guardrail": bare_model.get("error"),
                    "url_error_redaction": {
                        "dataset_url": dataset_url_result.get("error"),
                        "base_model_url": base_model_url_result.get("error"),
                        "artifact_upload_url": artifact_upload_result.get("error"),
                    },
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
