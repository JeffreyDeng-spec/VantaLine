"""RunPod input construction and single submission through explicit settings and transport."""
import base64
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]


RUNPOD_YOLO_BASE_MODEL_ENV = "VANTALINE_RUNPOD_YOLO_BASE_MODEL"
RUNPOD_YOLO_BASE_MODEL_SHA256_ENV = "VANTALINE_RUNPOD_YOLO_BASE_MODEL_SHA256"
RUNPOD_YOLO_BASE_MODEL_URL_ENV = "VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL"
RUNPOD_YOLO_BASE_MODEL_URL_SHA256_ENV = "VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL_SHA256"


class RunPodRequest(Protocol):
    def __call__(self, method: str, path: str, *, json_body: Record | None = None,
                 timeout_seconds: float | None = None) -> Record: ...


class RunPodPayload:
    def __init__(self, upload: Callable[[str, Record], Record], timeout: Callable[[], int],
                 inline_limit: Callable[[], int], environment: Callable[[], Mapping[str, str]]):
        self.upload, self.timeout = upload, timeout
        self.inline_limit, self.environment = inline_limit, environment

    def runpod_training_input_payload(self, job_id: str, task: dict[str, Any], archive: dict[str, Any]) -> dict[str, Any]:
        artifact_upload = self.upload(job_id, task)
        payload: dict[str, Any] = {
            "job_id": job_id,
            "train_mode": str(task.get("train_mode") or task.get("mode") or task.get("model_variant") or "yolo"),
            "epochs": max(1, min(500, int(task.get("epochs") or 1))),
            "imgsz": max(320, min(1280, int(task.get("image_size") or 640))),
            "dataset_sha256": str(archive["sha256"]),
            "return_artifact_b64": False,
            "artifact_upload_url": str(artifact_upload["url"]),
            "inference_smoke": True,
            "timeout_seconds": self.timeout(),
        }
        archive_path = Path(str(archive.get("path") or ""))
        inline_limit = self.inline_limit()
        if inline_limit and archive_path.exists() and archive_path.stat().st_size <= inline_limit:
            payload["dataset_archive_b64"] = base64.b64encode(archive_path.read_bytes()).decode("ascii")
        else:
            payload["dataset_url"] = str(archive["url"])
        base_model_url = str(self.environment().get(RUNPOD_YOLO_BASE_MODEL_URL_ENV, "") or "").strip()
        if base_model_url:
            base_model_sha = str(self.environment().get(RUNPOD_YOLO_BASE_MODEL_URL_SHA256_ENV, "") or "").strip()
            if not base_model_sha:
                raise RuntimeError(f"{RUNPOD_YOLO_BASE_MODEL_URL_SHA256_ENV} is required when {RUNPOD_YOLO_BASE_MODEL_URL_ENV} is configured")
            payload["base_model_url"] = base_model_url
            payload["base_model_sha256"] = base_model_sha
        else:
            payload["base_model"] = str(self.environment().get(RUNPOD_YOLO_BASE_MODEL_ENV, "") or "/models/vantaline-yolo-base.pt").strip()
            base_model_sha = str(self.environment().get(RUNPOD_YOLO_BASE_MODEL_SHA256_ENV, "") or "").strip()
            if base_model_sha:
                payload["base_model_sha256"] = base_model_sha
        device = str(self.environment().get("VANTALINE_RUNPOD_YOLO_DEVICE", "") or "").strip()
        if device:
            payload["device"] = device
        return payload

class RunPodSubmission:
    def __init__(self, timeout: Callable[[], int], ttl: Callable[[], int], request: RunPodRequest):
        self.timeout, self.ttl, self.request = timeout, ttl, request

    def submit_runpod_yolo_training(self, payload: dict[str, Any]) -> dict[str, Any]:
        timeout_ms = self.timeout() * 1000
        ttl_ms = min(7 * 24 * 3600 * 1000, timeout_ms + self.ttl() * 1000)
        body = {
            "input": payload,
            "policy": {
                "executionTimeout": timeout_ms,
                "ttl": ttl_ms,
            },
        }
        return self.request("POST", "run", json_body=body)
