#!/usr/bin/env python3
"""RunPod serverless handler for VantaLine YOLO training."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests


WORKER_NAME = "vantaline-yolo-train-worker"
CONTRACT_VERSION = 1
WORK_ROOT = Path(os.environ.get("VANTALINE_RUNPOD_YOLO_WORK_ROOT", "/workspace/vantaline-yolo-worker")).resolve()
MAX_DATASET_BYTES = int(os.environ.get("VANTALINE_RUNPOD_YOLO_MAX_DATASET_BYTES", str(5 * 1024 * 1024 * 1024)))
MAX_INLINE_ARTIFACT_BYTES = int(os.environ.get("VANTALINE_RUNPOD_YOLO_RETURN_INLINE_MAX_BYTES", str(50 * 1024 * 1024)))
MAX_CONCURRENCY = max(1, int(os.environ.get("VANTALINE_RUNPOD_YOLO_MAX_CONCURRENCY", "1")))
JOB_TIMEOUT_SECONDS = max(60, int(float(os.environ.get("VANTALINE_RUNPOD_YOLO_JOB_TIMEOUT_SECONDS", "7200"))))
MAX_EPOCHS = max(1, int(os.environ.get("VANTALINE_RUNPOD_YOLO_MAX_EPOCHS", "300")))
MAX_IMGSZ = max(320, int(os.environ.get("VANTALINE_RUNPOD_YOLO_MAX_IMGSZ", "1280")))
DEFAULT_BASE_MODEL = os.environ.get("VANTALINE_RUNPOD_YOLO_BASE_MODEL", "/models/vantaline-yolo-base.pt").strip() or "/models/vantaline-yolo-base.pt"
DEFAULT_DEVICE = os.environ.get("VANTALINE_RUNPOD_YOLO_DEVICE", "0").strip() or "0"
ALLOW_MOCK = os.environ.get("VANTALINE_RUNPOD_YOLO_ALLOW_MOCK", "").strip().lower() in {"1", "true", "yes", "on"}

_TRAINING_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENCY)


class WorkerError(RuntimeError):
    """User-correctable request or runtime error."""


def safe_name(value: Any, fallback: str = "job") -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "")).strip("._")
    return clean[:120] or fallback


def bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tail_text(path: Path, *, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace")
    return data[-max_chars:]


def extract_input(event: dict[str, Any] | None) -> dict[str, Any]:
    event = event or {}
    body = event.get("input") if isinstance(event.get("input"), dict) else event
    if not isinstance(body, dict):
        raise WorkerError("event input must be a JSON object")
    return body


def redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    for item in command:
        value = str(item)
        if value.startswith(("artifact_upload_url=", "dataset_url=", "base_model_url=")):
            redacted.append(value.split("=", 1)[0] + "=<redacted>")
        else:
            redacted.append(value)
    return redacted


def private_url_filename(url: str, fallback: str) -> str:
    path = urlsplit(url).path
    name = safe_name(Path(path).name, fallback)
    if not name.endswith(".pt"):
        name = f"{name}.pt"
    return name


def private_url_host(url: str) -> str:
    return urlsplit(url).netloc or "unknown-host"


def request_failure_code(exc: requests.RequestException) -> str:
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.ConnectionError):
        return "connection_error"
    if isinstance(exc, requests.HTTPError):
        return "http_error"
    return "request_error"


def download_to_file(
    url: str,
    target: Path,
    *,
    purpose: str,
    headers: dict[str, str] | None = None,
    max_bytes: int | None = None,
) -> None:
    if not url:
        raise WorkerError("download URL is empty")
    target.parent.mkdir(parents=True, exist_ok=True)
    max_allowed = MAX_DATASET_BYTES if max_bytes is None else max_bytes
    total = 0
    try:
        with requests.get(url, headers=headers or {}, stream=True, timeout=60) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_allowed:
                        raise WorkerError("download exceeded configured byte limit")
                    handle.write(chunk)
    except requests.RequestException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        status_suffix = f" status={int(status_code)}" if isinstance(status_code, int) else ""
        raise WorkerError(
            f"download failed for {purpose}: {request_failure_code(exc)} host={private_url_host(url)}{status_suffix}"
        ) from None


def write_dataset_archive(payload: dict[str, Any], job_dir: Path) -> Path:
    archive_path = job_dir / "input" / "dataset.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if str(payload.get("dataset_archive_b64") or "").strip():
        try:
            raw = base64.b64decode(str(payload["dataset_archive_b64"]), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise WorkerError("dataset_archive_b64 is not valid base64") from exc
        if len(raw) > MAX_DATASET_BYTES:
            raise WorkerError("dataset archive exceeds configured byte limit")
        archive_path.write_bytes(raw)
    elif str(payload.get("dataset_url") or "").strip():
        headers = payload.get("dataset_headers") if isinstance(payload.get("dataset_headers"), dict) else None
        download_to_file(str(payload["dataset_url"]), archive_path, purpose="dataset_url", headers=headers)
    else:
        raise WorkerError("dataset_url or dataset_archive_b64 is required")
    expected_sha = str(payload.get("dataset_sha256") or payload.get("sha256") or "").strip().lower()
    if not expected_sha:
        raise WorkerError("dataset_sha256 is required")
    actual_sha = sha256_file(archive_path)
    if expected_sha != actual_sha:
        raise WorkerError("dataset_archive checksum mismatch")
    return archive_path


def safe_extract_zip(archive_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_root = target_dir.resolve()
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                member_path = (target_dir / member.filename).resolve()
                try:
                    member_path.relative_to(target_root)
                except ValueError as exc:
                    raise WorkerError("dataset archive contains unsafe paths") from exc
            archive.extractall(target_dir)
    except zipfile.BadZipFile as exc:
        raise WorkerError("dataset archive is not a valid zip") from exc


def find_dataset_root(extract_dir: Path) -> Path:
    direct = extract_dir / "dataset.yaml"
    if direct.exists():
        return extract_dir
    candidates = [path.parent for path in extract_dir.rglob("dataset.yaml") if path.is_file()]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise WorkerError("dataset archive is missing dataset.yaml")
    raise WorkerError("dataset archive contains multiple dataset.yaml files")


def rewrite_dataset_yaml_path(dataset_dir: Path) -> Path:
    yaml_path = dataset_dir / "dataset.yaml"
    lines = yaml_path.read_text(encoding="utf-8", errors="replace").splitlines()
    rewritten = False
    for idx, line in enumerate(lines):
        if line.strip().startswith("path:"):
            lines[idx] = f"path: {dataset_dir.as_posix()}"
            rewritten = True
            break
    if not rewritten:
        lines.insert(0, f"path: {dataset_dir.as_posix()}")
    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return yaml_path


def dataset_summary(dataset_dir: Path) -> dict[str, Any]:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    images = sorted(
        path
        for path in (dataset_dir / "images").rglob("*")
        if path.is_file() and path.suffix.lower() in image_exts
    )
    labels = sorted(path for path in (dataset_dir / "labels").rglob("*.txt") if path.is_file())
    if not images:
        raise WorkerError("dataset has no images under images/")
    if not labels:
        raise WorkerError("dataset has no YOLO label txt files under labels/")
    return {
        "dataset_dir": str(dataset_dir),
        "image_count": len(images),
        "label_count": len(labels),
        "smoke_image": str(images[0]),
    }


def prepare_dataset(payload: dict[str, Any], job_dir: Path) -> tuple[Path, Path, dict[str, Any]]:
    archive_path = write_dataset_archive(payload, job_dir)
    extract_dir = job_dir / "dataset"
    safe_extract_zip(archive_path, extract_dir)
    dataset_dir = find_dataset_root(extract_dir)
    yaml_path = rewrite_dataset_yaml_path(dataset_dir)
    summary = dataset_summary(dataset_dir)
    summary["archive_sha256"] = sha256_file(archive_path)
    summary["archive_size"] = archive_path.stat().st_size
    return dataset_dir, yaml_path, summary


def prepare_base_model(payload: dict[str, Any], job_dir: Path) -> tuple[str, dict[str, Any]]:
    base_model = str(payload.get("base_model") or DEFAULT_BASE_MODEL).strip() or DEFAULT_BASE_MODEL
    base_model_url = str(payload.get("base_model_url") or "").strip()
    if bool(payload.get("mock_train")):
        return base_model, {"source": "mock_base_model", "name": Path(base_model).name}
    if base_model_url:
        if not str(payload.get("base_model_sha256") or "").strip():
            raise WorkerError("base_model_sha256 is required when base_model_url is used")
        target = job_dir / "input" / "base_model" / private_url_filename(base_model_url, "base_model.pt")
        headers = payload.get("base_model_headers") if isinstance(payload.get("base_model_headers"), dict) else None
        download_to_file(base_model_url, target, purpose="base_model_url", headers=headers, max_bytes=1024 * 1024 * 1024)
        expected_sha = str(payload.get("base_model_sha256") or "").strip().lower()
        actual_sha = sha256_file(target)
        if expected_sha != actual_sha:
            raise WorkerError("base_model checksum mismatch")
        return str(target), {
            "source": "base_model_url",
            "filename": target.name,
            "sha256": actual_sha,
            "size": target.stat().st_size,
        }
    if urlsplit(base_model).scheme in {"http", "https"}:
        raise WorkerError("base_model URL must be passed as base_model_url with base_model_sha256")
    model_path = Path(base_model)
    if not model_path.exists() or not model_path.is_file():
        raise WorkerError("base_model must be a baked container path or use base_model_url with base_model_sha256")
    actual_sha = sha256_file(model_path)
    expected_sha = str(payload.get("base_model_sha256") or os.environ.get("VANTALINE_RUNPOD_YOLO_BASE_MODEL_SHA256") or "").strip().lower()
    if expected_sha and expected_sha != actual_sha:
        raise WorkerError("base_model checksum mismatch")
    return str(model_path), {
        "source": "baked_base_model",
        "filename": model_path.name,
        "sha256": actual_sha,
        "size": model_path.stat().st_size,
    }


def yolo_command() -> str:
    configured = os.environ.get("VANTALINE_RUNPOD_YOLO_COMMAND", "").strip()
    if configured:
        return configured
    discovered = shutil.which("yolo")
    if discovered:
        return discovered
    raise WorkerError("yolo CLI is not available; install ultralytics in the worker image")


def run_subprocess(command: list[str], *, cwd: Path, log_path: Path, timeout_seconds: int) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("$ " + " ".join(redact_command(command)) + "\n\n")
        log.flush()
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkerError(f"training exceeded timeout_seconds={timeout_seconds}") from exc
    return int(completed.returncode)


def mock_training(job_id: str, run_root: Path, log_path: Path) -> Path:
    if not ALLOW_MOCK:
        raise WorkerError("mock_train requires VANTALINE_RUNPOD_YOLO_ALLOW_MOCK=1")
    weights_dir = run_root / job_id / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    best = weights_dir / "best.pt"
    best.write_bytes(f"mock best.pt for {job_id}\n".encode("utf-8"))
    (run_root / job_id / "results.csv").write_text("epoch,metrics/mAP50(B)\n0,1.0\n", encoding="utf-8")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("mock training completed\n", encoding="utf-8")
    return best


def run_training(payload: dict[str, Any], job_id: str, yaml_path: Path, base_model: str, job_dir: Path) -> tuple[Path, dict[str, Any]]:
    epochs = bounded_int(payload.get("epochs"), default=1, minimum=1, maximum=MAX_EPOCHS)
    imgsz = bounded_int(payload.get("imgsz") or payload.get("image_size"), default=640, minimum=320, maximum=MAX_IMGSZ)
    device = str(payload.get("device") or DEFAULT_DEVICE).strip() or DEFAULT_DEVICE
    timeout_seconds = bounded_int(payload.get("timeout_seconds"), default=JOB_TIMEOUT_SECONDS, minimum=60, maximum=JOB_TIMEOUT_SECONDS)
    run_root = job_dir / "runs"
    log_path = job_dir / "logs" / "train.log"
    if bool(payload.get("mock_train")):
        best = mock_training(job_id, run_root, log_path)
        return best, {
            "mock": True,
            "return_code": 0,
            "epochs": epochs,
            "imgsz": imgsz,
            "device": device,
            "log_path": str(log_path),
            "log_tail": tail_text(log_path),
        }
    command = [
        yolo_command(),
        "detect",
        "train",
        f"model={base_model}",
        f"data={yaml_path}",
        f"imgsz={imgsz}",
        f"epochs={epochs}",
        "batch=0.72",
        f"device={device}",
        "cache=False",
        "workers=0",
        "patience=25",
        "optimizer=auto",
        "mosaic=0.0",
        "mixup=0.0",
        "copy_paste=0.0",
        "plots=True",
        f"project={run_root}",
        f"name={job_id}",
        "exist_ok=True",
    ]
    return_code = run_subprocess(command, cwd=job_dir, log_path=log_path, timeout_seconds=timeout_seconds)
    best = run_root / job_id / "weights" / "best.pt"
    if return_code != 0:
        raise WorkerError(f"YOLO training failed with return_code={return_code}")
    if not best.exists():
        raise WorkerError("YOLO training completed but weights/best.pt is missing")
    return best, {
        "mock": False,
        "return_code": return_code,
        "epochs": epochs,
        "imgsz": imgsz,
        "device": device,
        "command": redact_command(command),
        "log_path": str(log_path),
        "log_tail": tail_text(log_path),
    }


def run_inference_smoke(payload: dict[str, Any], best_pt: Path, dataset: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    if bool(payload.get("mock_train")):
        return {"ok": True, "status": "mocked", "reason": "mock_train contract smoke"}
    if str(payload.get("inference_smoke", "true")).strip().lower() in {"0", "false", "no", "off"}:
        return {"ok": True, "status": "skipped"}
    smoke_image = str(dataset.get("smoke_image") or "")
    if not smoke_image:
        return {"ok": False, "status": "failed", "error": "no smoke image available"}
    imgsz = bounded_int(payload.get("imgsz") or payload.get("image_size"), default=640, minimum=320, maximum=MAX_IMGSZ)
    device = str(payload.get("device") or DEFAULT_DEVICE).strip() or DEFAULT_DEVICE
    log_path = job_dir / "logs" / "predict.log"
    command = [
        yolo_command(),
        "detect",
        "predict",
        f"model={best_pt}",
        f"source={smoke_image}",
        f"imgsz={imgsz}",
        f"device={device}",
        "save=False",
        "verbose=False",
    ]
    try:
        return_code = run_subprocess(command, cwd=job_dir, log_path=log_path, timeout_seconds=600)
    except WorkerError as exc:
        return {"ok": False, "status": "failed", "error": str(exc), "log_tail": tail_text(log_path)}
    return {
        "ok": return_code == 0,
        "status": "passed" if return_code == 0 else "failed",
        "return_code": return_code,
        "log_tail": tail_text(log_path),
    }


def make_artifacts(payload: dict[str, Any], job_id: str, best_pt: Path, job_dir: Path) -> dict[str, Any]:
    artifact_dir = job_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    run_dir = best_pt.parents[1]
    archive_base = artifact_dir / f"{job_id}_artifacts"
    archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=str(run_dir)))
    best_summary: dict[str, Any] = {
        "filename": "best.pt",
        "size": best_pt.stat().st_size,
        "sha256": sha256_file(best_pt),
    }
    if bool(payload.get("return_artifact_b64")):
        if best_pt.stat().st_size > MAX_INLINE_ARTIFACT_BYTES:
            raise WorkerError("best.pt exceeds inline artifact byte limit")
        best_summary["artifact_b64"] = base64.b64encode(best_pt.read_bytes()).decode("ascii")
    result = {
        "best_pt": best_summary,
        "run_archive": {
            "filename": archive_path.name,
            "size": archive_path.stat().st_size,
            "sha256": sha256_file(archive_path),
        },
    }
    upload_url = str(payload.get("artifact_upload_url") or "").strip()
    if upload_url:
        headers = payload.get("artifact_upload_headers") if isinstance(payload.get("artifact_upload_headers"), dict) else {}
        try:
            with archive_path.open("rb") as handle:
                response = requests.put(upload_url, data=handle, headers=headers, timeout=120)
            if response.status_code >= 400:
                raise WorkerError(f"artifact upload failed HTTP {response.status_code}")
        except requests.RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            status_suffix = f" status={int(status_code)}" if isinstance(status_code, int) else ""
            raise WorkerError(
                f"artifact upload failed: {request_failure_code(exc)} host={private_url_host(upload_url)}{status_suffix}"
            ) from None
        result["upload"] = {
            "ok": True,
            "target": "artifact_upload_url",
            "status_code": response.status_code,
            "bytes": archive_path.stat().st_size,
        }
    return result


def train_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = safe_name(payload.get("job_id") or f"runpod_train_{uuid.uuid4().hex[:10]}", "runpod_train")
    train_mode = str(payload.get("train_mode") or payload.get("mode") or "yolo").strip() or "yolo"
    if train_mode not in {"yolo", "yolo_ocr"}:
        raise WorkerError("train_mode must be yolo or yolo_ocr")
    job_dir = WORK_ROOT / "jobs" / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir, yaml_path, dataset = prepare_dataset(payload, job_dir)
    base_model, base_model_summary = prepare_base_model(payload, job_dir)
    started = time.monotonic()
    best_pt, training = run_training(payload, job_id, yaml_path, base_model, job_dir)
    inference = run_inference_smoke(payload, best_pt, dataset, job_dir)
    artifacts = make_artifacts(payload, job_id, best_pt, job_dir)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "ok": True,
        "status": "completed",
        "job_id": job_id,
        "worker": WORKER_NAME,
        "contract_version": CONTRACT_VERSION,
        "train_mode": train_mode,
        "dataset": {
            key: value
            for key, value in dataset.items()
            if key in {"archive_sha256", "archive_size", "image_count", "label_count"}
        },
        "base_model": base_model_summary,
        "training": training,
        "inference_smoke": inference,
        "artifacts": artifacts,
        "elapsed_ms": elapsed_ms,
    }


def failed_response(payload: dict[str, Any] | None, exc: BaseException) -> dict[str, Any]:
    job_id = safe_name((payload or {}).get("job_id") if isinstance(payload, dict) else "", "unknown")
    return {
        "ok": False,
        "status": "failed",
        "job_id": job_id,
        "worker": WORKER_NAME,
        "contract_version": CONTRACT_VERSION,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def handler(event: dict[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] | None = None
    acquired = _TRAINING_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        return failed_response({}, WorkerError("worker concurrency limit reached"))
    try:
        payload = extract_input(event)
        return train_job(payload)
    except WorkerError as exc:
        return failed_response(payload, exc)
    except Exception as exc:  # noqa: BLE001 - RunPod jobs need structured failure output
        response = failed_response(payload, exc)
        response["traceback_tail"] = traceback.format_exc()[-4000:]
        return response
    finally:
        _TRAINING_SEMAPHORE.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="VantaLine RunPod YOLO training worker")
    parser.add_argument("--event-json", default="", help="Run one local event JSON instead of starting RunPod serverless")
    args = parser.parse_args()
    if args.event_json:
        event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
        print(json.dumps(handler(event), indent=2, ensure_ascii=False))
        return
    try:
        import runpod
    except ImportError as exc:
        raise SystemExit("runpod package is required when starting serverless mode") from exc
    runpod.serverless.start({"handler": handler})


if __name__ == "__main__":
    main()
