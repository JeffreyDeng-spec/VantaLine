#!/usr/bin/env python3
"""Private VantaLine worker gateway for Windows/WSL-side capabilities.

The gateway exposes a small allowlist of HTTP endpoints for the HK cloud
service over Tailscale. It intentionally does not execute arbitrary commands.
"""

from __future__ import annotations

import os
import re
import time
import base64
import hashlib
import io
import json
import shlex
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import requests
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw, ImageFilter
from pydantic import BaseModel, Field


LOCAL_VANTALINE_BASE_URL = os.environ.get("VANTALINE_LOCAL_BASE_URL", "http://127.0.0.1:8765").rstrip("/")
LOCATEANYTHING_BASE_URL = os.environ.get("VANTALINE_LOCATEANYTHING_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
QWEN_BASE_URL = os.environ.get("VANTALINE_QWEN_BASE_URL", "http://100.103.240.14:8080").rstrip("/")
WORKER_TOKEN = os.environ.get("VANTALINE_WORKER_TOKEN", "").strip()
LOCAL_VANTALINE_USERNAME_ENV = "VANTALINE_LOCAL_ADMIN_USERNAME"
LOCAL_VANTALINE_PASSWORD_ENV = "VANTALINE_LOCAL_ADMIN_PASSWORD"
LOCAL_VANTALINE_DEFAULT_USERNAME = "worker_admin"
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("VANTALINE_WORKER_REQUEST_TIMEOUT_SECONDS", "30"))
CODEX_IMAGE_TIMEOUT_SECONDS = float(os.environ.get("VANTALINE_CODEX_IMAGE_TIMEOUT_SECONDS", "900"))
CODEX_IMAGE_CONCURRENCY = max(1, int(os.environ.get("VANTALINE_CODEX_IMAGE_CONCURRENCY", "1")))
WORKER_REPO_ROOT = Path(os.environ.get("VANTALINE_WORKER_REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
WORKER_IMAGE_JOB_DIR = WORKER_REPO_ROOT / "local_inspection_service" / "data" / "worker_image_jobs"
WORKER_OUTPUT_DIR = WORKER_REPO_ROOT / "local_inspection_service" / "data" / "outputs"
WORKER_TRANSFER_DIR = WORKER_REPO_ROOT / "local_inspection_service" / "data" / "worker_training_transfers"
CODEX_IMAGE_SEMAPHORE = threading.BoundedSemaphore(CODEX_IMAGE_CONCURRENCY)
LOCAL_VANTALINE_SESSION = requests.Session()
LOCAL_VANTALINE_SESSION_LOCK = threading.RLock()

app = FastAPI(title="VantaLine Windows Worker Gateway", version="0.1")


class WorkerTrainingRequest(BaseModel):
    selected_accessory_ids: list[str] = Field(default_factory=list)
    sample_count: int = 1
    train_mode: str = "yolo_ocr"
    approved_preview_id: str | None = None
    dataset_id: str | None = None
    epochs: int = 1
    image_size: int = 640
    background_set_id: str | None = None


POSE_GRID_ANGLES = {
    "lying": [-18, 0, 18, -10, 0, 10, -18, 0, 18],
    "upright": [-8, 0, 8, -4, 0, 4, -8, 0, 8],
}


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not WORKER_TOKEN:
        return
    expected = f"Bearer {WORKER_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_codex_auth(authorization: str | None = Header(default=None)) -> None:
    if not WORKER_TOKEN:
        raise HTTPException(status_code=503, detail="VANTALINE_WORKER_TOKEN is required for Codex image generation")
    require_auth(authorization)


def summarize_service_body(body: Any) -> Any:
    if not isinstance(body, dict):
        return body
    if "available_models" in body and "ai_detection" in body:
        ai_detection = body.get("ai_detection") if isinstance(body.get("ai_detection"), dict) else {}
        return {
            "service": body.get("service"),
            "model_exists": body.get("model_exists"),
            "active_model_id": body.get("active_model_id"),
            "ai_detection": {
                "status": ai_detection.get("status"),
                "provider": ai_detection.get("provider"),
                "model": ai_detection.get("model"),
                "proxy_configured": ai_detection.get("proxy_configured"),
                "proxy_url": ai_detection.get("proxy_url"),
            },
            "training_execution": body.get("training_execution"),
        }
    if "loaded" in body and "model" in body:
        model = body.get("model")
        return {
            "ok": body.get("ok"),
            "loaded": body.get("loaded"),
            "model": str(model).replace("\\", "/").rstrip("/").split("/")[-1] if model else model,
            "device": body.get("device"),
        }
    return body


def service_get(url: str, *, timeout: float = 4.0) -> dict[str, Any]:
    start = time.monotonic()
    try:
        response = requests.get(url, timeout=timeout)
        latency_ms = int((time.monotonic() - start) * 1000)
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text[:300]
        body = summarize_service_body(body)
        return {
            "ok": response.status_code < 500,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "body": body,
        }
    except requests.RequestException as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"ok": False, "status_code": 0, "latency_ms": latency_ms, "error": str(exc)}


def local_vantaline_credentials() -> tuple[str, str]:
    username = os.environ.get(LOCAL_VANTALINE_USERNAME_ENV, "").strip() or LOCAL_VANTALINE_DEFAULT_USERNAME
    password = os.environ.get(LOCAL_VANTALINE_PASSWORD_ENV, "").strip() or WORKER_TOKEN
    if not password:
        raise RuntimeError(
            f"{LOCAL_VANTALINE_PASSWORD_ENV} or VANTALINE_WORKER_TOKEN is required for local VantaLine backend auth"
        )
    return username, password


def local_vantaline_url(path: str) -> str:
    return f"{LOCAL_VANTALINE_BASE_URL}{path if path.startswith('/') else f'/{path}'}"


def parse_response_body(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:500]


def ensure_local_vantaline_session(*, force_login: bool = False) -> None:
    with LOCAL_VANTALINE_SESSION_LOCK:
        if not force_login:
            response = LOCAL_VANTALINE_SESSION.get(local_vantaline_url("/api/auth/status"), timeout=REQUEST_TIMEOUT_SECONDS)
            body = parse_response_body(response)
            if response.status_code == 200 and isinstance(body, dict) and body.get("authenticated"):
                return
            if response.status_code == 200 and isinstance(body, dict) and body.get("setup_required"):
                username, password = local_vantaline_credentials()
                bootstrap = LOCAL_VANTALINE_SESSION.post(
                    local_vantaline_url("/api/auth/bootstrap"),
                    json={"username": username, "display_name": username, "password": password},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                if bootstrap.status_code == 200:
                    return
                if bootstrap.status_code != 409:
                    raise RuntimeError(f"Local VantaLine bootstrap failed HTTP {bootstrap.status_code}: {parse_response_body(bootstrap)}")
        username, password = local_vantaline_credentials()
        login = LOCAL_VANTALINE_SESSION.post(
            local_vantaline_url("/api/auth/login"),
            json={"username": username, "password": password},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if login.status_code != 200:
            raise RuntimeError(f"Local VantaLine login failed HTTP {login.status_code}: {parse_response_body(login)}")


def local_vantaline_request(method: str, path: str, *, json_body: dict[str, Any] | None = None, timeout: float | None = None) -> requests.Response:
    ensure_local_vantaline_session()
    response = LOCAL_VANTALINE_SESSION.request(
        method,
        local_vantaline_url(path),
        json=json_body,
        timeout=timeout or REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code == 401:
        ensure_local_vantaline_session(force_login=True)
        response = LOCAL_VANTALINE_SESSION.request(
            method,
            local_vantaline_url(path),
            json=json_body,
            timeout=timeout or REQUEST_TIMEOUT_SECONDS,
        )
    return response


def local_vantaline_status() -> dict[str, Any]:
    start = time.monotonic()
    try:
        response = local_vantaline_request("GET", "/api/status", timeout=4.0)
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "body": summarize_service_body(parse_response_body(response)),
        }
    except (RuntimeError, requests.RequestException) as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"ok": False, "status_code": 0, "latency_ms": latency_ms, "error": str(exc)}


def require_local_vantaline_ready(action: str) -> None:
    status = local_vantaline_status()
    if status.get("ok") and status.get("status_code") == 200:
        return
    reason = status.get("error") or status.get("body") or f"HTTP {status.get('status_code')}"
    raise HTTPException(
        status_code=503,
        detail=f"Local VantaLine backend is unavailable; cannot accept {action}: {reason}",
    )


def image_resample_filter() -> int:
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def image_rotate_filter() -> int:
    return getattr(getattr(Image, "Resampling", Image), "BICUBIC")


async def read_upload_image(upload: UploadFile) -> Image.Image:
    payload = await upload.read()
    if not payload:
        raise HTTPException(status_code=400, detail=f"{upload.filename or 'image'} is empty")
    try:
        return Image.open(io.BytesIO(payload)).convert("RGBA")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{upload.filename or 'image'} is not a readable image") from exc


def reference_object_cutout(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    arr = np.asarray(rgba).astype(np.int16)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3].astype(np.uint8)
    if int((alpha < 245).sum()) > max(32, alpha.size * 0.01):
        mask = alpha > 18
    else:
        h, w = rgb.shape[:2]
        corner = max(4, min(h, w) // 12)
        samples = np.concatenate(
            [
                rgb[:corner, :corner].reshape(-1, 3),
                rgb[:corner, -corner:].reshape(-1, 3),
                rgb[-corner:, :corner].reshape(-1, 3),
                rgb[-corner:, -corner:].reshape(-1, 3),
            ],
            axis=0,
        )
        bg = np.median(samples, axis=0)
        distance = np.sqrt(((rgb.astype(np.float32) - bg.astype(np.float32)) ** 2).sum(axis=2))
        threshold = max(22.0, min(58.0, float(np.percentile(distance, 88)) * 0.55))
        mask = distance > threshold
        if int(mask.sum()) < max(64, mask.size * 0.015):
            mask = distance > max(12.0, threshold * 0.62)
    mask_img = (
        Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
        .filter(ImageFilter.MedianFilter(5))
        .filter(ImageFilter.GaussianBlur(0.7))
    )
    bbox = mask_img.point(lambda value: 255 if value > 24 else 0).getbbox()
    if not bbox:
        w, h = rgba.size
        margin_x = max(1, int(w * 0.08))
        margin_y = max(1, int(h * 0.08))
        bbox = (margin_x, margin_y, w - margin_x, h - margin_y)
        mask_img = Image.new("L", rgba.size, 0)
        ImageDraw.Draw(mask_img).rectangle(bbox, fill=255)
    x1, y1, x2, y2 = bbox
    pad = max(4, int(max(x2 - x1, y2 - y1) * 0.06))
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(rgba.size[0], x2 + pad)
    y2 = min(rgba.size[1], y2 + pad)
    crop = rgba.crop((x1, y1, x2, y2))
    crop_alpha = mask_img.crop((x1, y1, x2, y2)).point(lambda value: 255 if value > 20 else 0)
    crop.putalpha(crop_alpha)
    return crop


def fit_cutout_to_cell(cutout: Image.Image, cell_size: int, pose_family: str, index: int) -> Image.Image:
    working = cutout.copy()
    clean_pose_family = "upright" if pose_family == "upright" else "lying"
    angle = POSE_GRID_ANGLES[clean_pose_family][index]
    if clean_pose_family == "lying":
        if working.size[1] > working.size[0]:
            working = working.rotate(90, expand=True, resample=image_rotate_filter())
        fit_ratio = 0.78
    else:
        if working.size[0] > working.size[1]:
            working = working.rotate(90, expand=True, resample=image_rotate_filter())
        fit_ratio = 0.58
    if angle:
        working = working.rotate(angle, expand=True, resample=image_rotate_filter())
    w, h = working.size
    scale = min((cell_size * fit_ratio) / max(1, w), (cell_size * fit_ratio) / max(1, h), 2.5)
    return working.resize((max(1, int(w * scale)), max(1, int(h * scale))), image_resample_filter())


def compose_pose_sheet(reference: Image.Image, pose_family: str, output_size: int = 1024) -> Image.Image:
    clean_pose_family = "upright" if pose_family == "upright" else "lying"
    cutout = reference_object_cutout(reference)
    canvas = Image.new("RGB", (output_size, output_size), (255, 255, 255))
    cell = output_size // 3
    for index in range(9):
        row, col = divmod(index, 3)
        sprite = fit_cutout_to_cell(cutout, cell, clean_pose_family, index)
        jitter_x = int((col - 1) * cell * 0.025)
        jitter_y = int((row - 1) * cell * 0.025)
        x = int(col * cell + (cell - sprite.size[0]) / 2 + jitter_x)
        y = int(row * cell + (cell - sprite.size[1]) / 2 + jitter_y)
        canvas.paste(sprite.convert("RGB"), (x, y), sprite.getchannel("A"))
    return canvas


def png_b64(image: Image.Image) -> str:
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return base64.b64encode(out.getvalue()).decode("ascii")


def safe_name(value: str, fallback: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value or fallback).strip("._")
    return clean or fallback


def path_for_wsl(path: Path) -> str:
    raw = str(path.resolve()).replace("\\", "/")
    if len(raw) >= 3 and raw[1:3] == ":/":
        return f"/mnt/{raw[0].lower()}/{raw[3:]}"
    return raw


def path_from_wsl_mount(raw: str) -> str:
    value = str(raw or "").replace("\\", "/")
    match = re.match(r"^/mnt/([a-zA-Z])/(.+)$", value)
    if not match:
        return value
    return f"{match.group(1).upper()}:/{match.group(2)}"


def path_for_windows_training(path: Path) -> str:
    return path_from_wsl_mount(str(path.resolve())).replace("\\", "/")


def codex_log_has_generated_image(log_path: Path) -> bool:
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "/.codex/generated_images/" in text or "/home/dministrator/.codex/generated_images/" in text


def build_codex_image_prompt(prompt: str, pose_family: str, input_count: int, output_path: str) -> str:
    clean_pose_family = "upright" if str(pose_family).strip().lower() == "upright" else "lying"
    pose_hint = (
        "Final image must contain exactly nine replacement objects matched to the nine anchor targets."
        if clean_pose_family == "upright"
        else "Final image must contain exactly nine horizontal replacement objects."
    )
    guide_hint = (
        "The second attached image, when present, is a circular end-face target guide. Preserve it as the round target reference "
        "for cylindrical or circular-top objects; do not ignore it."
        if clean_pose_family == "upright" and input_count >= 3
        else ""
    )
    return f"""
You are the ImageWorker for the local assembly-line inspection service.

Use all {input_count} attached images. The first attached image is a hidden backend anchor image. Use it only for layout, pose, scale, camera, and table/background.
{guide_hint}

Core prompt:
{prompt}

- Generate a realistic PNG with AI image generation; do not satisfy this with local drawing or script-only image editing.
- {pose_hint}
- Save the final PNG exactly here:
  {output_path}
""".strip()


async def save_uploads_for_codex(uploads: list[UploadFile], job_dir: Path) -> list[Path]:
    job_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, upload in enumerate(uploads[:12]):
        payload = await upload.read()
        if not payload:
            raise HTTPException(status_code=400, detail=f"{upload.filename or f'image_{index + 1}'} is empty")
        suffix = Path(upload.filename or "").suffix.lower() or ".png"
        path = job_dir / f"{index:02d}_{safe_name(Path(upload.filename or f'image_{index + 1}{suffix}').name, f'image_{index + 1}{suffix}')}"
        path.write_bytes(payload)
        paths.append(path)
    return paths


def codex_exec_command(input_paths: list[Path], output_path: Path) -> tuple[list[str], str, str]:
    configured = os.environ.get("VANTALINE_CODEX_COMMAND", "").strip()
    if configured:
        command = [
            configured,
            "exec",
            "--sandbox",
            "workspace-write",
            "-C",
            str(WORKER_REPO_ROOT),
        ]
        for path in input_paths:
            command.extend(["-i", str(path)])
        command.append("-")
        return command, str(WORKER_REPO_ROOT), str(output_path)

    wsl = shutil.which("wsl.exe")
    if os.name == "nt" and wsl:
        wsl_root = path_for_wsl(WORKER_REPO_ROOT)
        wsl_output = path_for_wsl(output_path)
        args = [
            "codex",
            "exec",
            "--sandbox",
            "workspace-write",
            "-C",
            wsl_root,
        ]
        for path in input_paths:
            args.extend(["-i", path_for_wsl(path)])
        args.append("-")
        script = "cd " + shlex.quote(wsl_root) + " && " + " ".join(shlex.quote(item) for item in args)
        return [wsl, "-e", "bash", "-lc", script], str(WORKER_REPO_ROOT), wsl_output

    native_codex = shutil.which("codex")
    if native_codex:
        command = [
            native_codex,
            "exec",
            "--sandbox",
            "workspace-write",
            "-C",
            str(WORKER_REPO_ROOT),
        ]
        for path in input_paths:
            command.extend(["-i", str(path)])
        command.append("-")
        return command, str(WORKER_REPO_ROOT), str(output_path)

    raise HTTPException(status_code=503, detail="codex CLI is not available to the Windows Worker")


async def run_codex_default_crops(
    uploads: list[UploadFile],
    *,
    pose_family: str,
    output_name: str,
    prompt: str,
) -> dict[str, Any]:
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required for local CodexImageWorker generation")
    if not CODEX_IMAGE_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="CodexImageWorker is already running at its configured concurrency limit")
    WORKER_IMAGE_JOB_DIR.mkdir(parents=True, exist_ok=True)
    try:
        job_root = Path(tempfile.mkdtemp(prefix="image_job_", dir=str(WORKER_IMAGE_JOB_DIR)))
        input_paths = await save_uploads_for_codex(uploads, job_root / "inputs")
        output_path = job_root / safe_name(output_name, "pose_collection.png")
        log_path = job_root / "codex_image_worker.log"
        command, cwd, output_path_for_prompt = codex_exec_command(input_paths, output_path)
        prompt_text = build_codex_image_prompt(prompt, pose_family, len(input_paths), output_path_for_prompt)
        started = time.monotonic()
        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as log:
                log.write("$ " + " ".join(str(item) for item in command) + "\n\n")
                log.flush()
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                try:
                    process.communicate(prompt_text + "\n", timeout=CODEX_IMAGE_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                    raise HTTPException(status_code=504, detail=f"CodexImageWorker exceeded {int(CODEX_IMAGE_TIMEOUT_SECONDS)} seconds")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"CodexImageWorker failed to start: {exc}") from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if process.returncode != 0:
            tail = log_path.read_text(encoding="utf-8", errors="ignore")[-1800:] if log_path.exists() else ""
            raise HTTPException(status_code=502, detail=f"CodexImageWorker exited {process.returncode}: {tail}")
        if not output_path.exists():
            tail = log_path.read_text(encoding="utf-8", errors="ignore")[-1800:] if log_path.exists() else ""
            raise HTTPException(status_code=502, detail=f"CodexImageWorker completed but did not create {output_path.name}: {tail}")
        if not codex_log_has_generated_image(log_path):
            raise HTTPException(status_code=502, detail="CodexImageWorker completed without a generated image artifact in the log")
        try:
            image = Image.open(output_path)
            width, height = image.size
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"CodexImageWorker output is not a readable image: {exc}") from exc
        return {
            "ok": True,
            "provider": "local_codex_image_worker",
            "method": "codex_exec_image_worker",
            "pose_family": "upright" if str(pose_family).strip().lower() == "upright" else "lying",
            "output_name": output_name,
            "width": width,
            "height": height,
            "elapsed_ms": elapsed_ms,
            "log_path": str(log_path),
            "b64_json": base64.b64encode(output_path.read_bytes()).decode("ascii"),
        }
    finally:
        CODEX_IMAGE_SEMAPHORE.release()


def proxy_json(method: str, url: str, *, json_body: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
    try:
        if url.startswith(LOCAL_VANTALINE_BASE_URL):
            local_path = url[len(LOCAL_VANTALINE_BASE_URL) :] or "/"
            response = local_vantaline_request(method, local_path, json_body=json_body, timeout=timeout or REQUEST_TIMEOUT_SECONDS)
        else:
            response = requests.request(method, url, json=json_body, timeout=timeout or REQUEST_TIMEOUT_SECONDS)
    except (RuntimeError, requests.RequestException) as exc:
        raise HTTPException(status_code=502, detail=f"Local VantaLine service unavailable: {exc}") from exc
    try:
        body: Any = response.json()
    except ValueError:
        body = {"message": response.text[:500]}
    if response.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else body
        raise HTTPException(status_code=response.status_code, detail=detail or "Local service request failed")
    if not isinstance(body, dict):
        return {"result": body}
    return body


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract_zip(archive_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_root = target_dir.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            member_path = (target_dir / member.filename).resolve()
            try:
                member_path.relative_to(target_root)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Dataset archive contains unsafe paths") from exc
        archive.extractall(target_dir)


def rewrite_dataset_yaml_path(dataset_dir: Path) -> None:
    yaml_path = dataset_dir / "dataset.yaml"
    if not yaml_path.exists():
        raise HTTPException(status_code=400, detail="Dataset archive is missing dataset.yaml")
    lines = yaml_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        raise HTTPException(status_code=400, detail="Dataset archive has an empty dataset.yaml")
    lines[0] = f"path: {path_for_windows_training(dataset_dir)}"
    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def worker_training_dataset_dir(dataset_id: str) -> Path:
    clean_id = safe_name(dataset_id, "imported_dataset")
    return WORKER_OUTPUT_DIR / "training_datasets" / clean_id


def worker_resolve_path(value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("/outputs/"):
        return (WORKER_OUTPUT_DIR / raw.removeprefix("/outputs/").lstrip("/")).resolve()
    translated = path_from_wsl_mount(raw)
    if translated != raw:
        path = Path(translated)
        if path.exists():
            return path.resolve()
    path = Path(raw)
    if path.exists():
        return path.resolve()
    return None


def artifact_with_payload(item: dict[str, Any]) -> dict[str, Any]:
    copy = dict(item)
    path = worker_resolve_path(copy.get("artifact_path") or copy.get("path"))
    if path and path.exists() and path.is_file() and path.stat().st_size <= 1024 * 1024 * 300:
        payload = path.read_bytes()
        copy.update(
            {
                "artifact_filename": path.name,
                "artifact_size": len(payload),
                "artifact_sha256": hashlib.sha256(payload).hexdigest(),
                "artifact_b64": base64.b64encode(payload).decode("ascii"),
            }
        )
    return copy


@app.get("/health")
def health(_: None = Depends(require_auth)) -> dict[str, Any]:
    local = local_vantaline_status()
    return {
        "ok": local["ok"],
        "worker": "vantaline-windows-gateway",
        "local_vantaline": {
            key: value
            for key, value in local.items()
            if key in {"ok", "status_code", "latency_ms", "error"}
        },
    }


@app.get("/services")
def services(_: None = Depends(require_auth)) -> dict[str, Any]:
    return {
        "ok": True,
        "services": {
            "vantaline": local_vantaline_status(),
            "qwen_model": service_get(f"{QWEN_BASE_URL}/health", timeout=4.0),
            "locateanything": service_get(f"{LOCATEANYTHING_BASE_URL}/health", timeout=4.0),
        },
    }


@app.post("/images/default-crops")
async def default_crop_images(
    pose_family: str = Form("lying"),
    output_name: str = Form("pose_collection.png"),
    prompt: str = Form(""),
    require_codex: str = Form("false"),
    reference_images: list[UploadFile] = File(default=[]),
    input_images: list[UploadFile] = File(default=[]),
    files: list[UploadFile] = File(default=[]),
    _: None = Depends(require_auth),
) -> dict[str, Any]:
    uploads = [upload for upload in [*reference_images, *input_images, *files] if upload is not None]
    if not uploads:
        raise HTTPException(status_code=400, detail="at least one reference image is required")
    if prompt.strip() or str(require_codex).strip().lower() in {"1", "true", "yes"}:
        raise HTTPException(status_code=400, detail="Codex image generation is disabled on /images/default-crops")
    reference = await read_upload_image(uploads[0])
    clean_pose_family = "upright" if str(pose_family).strip().lower() == "upright" else "lying"
    image = compose_pose_sheet(reference, clean_pose_family)
    return {
        "ok": True,
        "method": "pil_reference_grid_fallback",
        "pose_family": clean_pose_family,
        "output_name": output_name,
        "width": image.size[0],
        "height": image.size[1],
        "b64_json": png_b64(image),
    }


@app.post("/images/codex-default-crops")
async def codex_default_crop_images(
    pose_family: str = Form("lying"),
    output_name: str = Form("pose_collection.png"),
    prompt: str = Form(...),
    generation_step: str = Form(""),
    reference_images: list[UploadFile] = File(default=[]),
    input_images: list[UploadFile] = File(default=[]),
    files: list[UploadFile] = File(default=[]),
    _: None = Depends(require_codex_auth),
) -> dict[str, Any]:
    uploads = [upload for upload in [*reference_images, *input_images, *files] if upload is not None]
    if not uploads:
        raise HTTPException(status_code=400, detail="at least one reference image is required")
    result = await run_codex_default_crops(
        uploads,
        pose_family=pose_family,
        output_name=output_name,
        prompt=prompt,
    )
    result["generation_step"] = generation_step
    return result


@app.post("/locate-anything/infer")
async def locate_anything_infer(
    image: UploadFile | None = File(default=None),
    file: UploadFile | None = File(default=None),
    prompt: str = Form(...),
    generation_mode: str = Form("fast"),
    max_new_tokens: int = Form(512),
    _: None = Depends(require_auth),
) -> dict[str, Any]:
    upload = image or file
    if upload is None:
        raise HTTPException(status_code=400, detail="image file is required")
    payload = await upload.read()
    if not payload:
        raise HTTPException(status_code=400, detail="image file is empty")
    files = {
        "image": (
            upload.filename or "locateanything.jpg",
            payload,
            upload.content_type or "image/jpeg",
        )
    }
    data = {
        "prompt": prompt,
        "generation_mode": generation_mode,
        "max_new_tokens": str(max(64, min(8192, int(max_new_tokens)))),
    }
    try:
        response = requests.post(
            f"{LOCATEANYTHING_BASE_URL}/locate",
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"LocateAnything runtime unavailable: {exc}") from exc
    try:
        body: Any = response.json()
    except ValueError:
        body = {"message": response.text[:500]}
    if response.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else body
        raise HTTPException(status_code=response.status_code, detail=detail or "LocateAnything request failed")
    if not isinstance(body, dict):
        return {"result": body}
    return body


@app.post("/training/datasets/generate")
def training_dataset_generate(request: WorkerTrainingRequest, _: None = Depends(require_auth)) -> dict[str, Any]:
    require_local_vantaline_ready("dataset generation")
    payload = request.model_dump()
    payload.pop("dataset_id", None)
    return proxy_json("POST", f"{LOCAL_VANTALINE_BASE_URL}/api/training/generate", json_body=payload)


@app.post("/training/jobs/import")
async def training_job_import(
    metadata: str = Form(...),
    dataset_archive: UploadFile = File(...),
    _: None = Depends(require_auth),
) -> dict[str, Any]:
    require_local_vantaline_ready("training import")
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="metadata must be valid JSON") from exc
    if not isinstance(meta, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    job_id = safe_name(str(meta.get("job_id") or ""), "worker_training_job")
    archive_meta = meta.get("dataset_archive") if isinstance(meta.get("dataset_archive"), dict) else {}
    expected_sha = str(archive_meta.get("sha256") or "").strip().lower()
    transfer_dir = WORKER_TRANSFER_DIR / job_id
    transfer_dir.mkdir(parents=True, exist_ok=True)
    archive_path = transfer_dir / safe_name(dataset_archive.filename or f"{job_id}.zip", f"{job_id}.zip")
    payload = await dataset_archive.read()
    if not payload:
        raise HTTPException(status_code=400, detail="dataset_archive is empty")
    archive_path.write_bytes(payload)
    actual_sha = hashlib.sha256(payload).hexdigest()
    if expected_sha and actual_sha != expected_sha:
        raise HTTPException(status_code=400, detail="dataset_archive checksum mismatch")
    imported_dataset_id = safe_name(f"imported_{job_id}", f"imported_{int(time.time())}")
    dataset_dir = worker_training_dataset_dir(imported_dataset_id)
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)
    safe_extract_zip(archive_path, dataset_dir)
    rewrite_dataset_yaml_path(dataset_dir)
    manifest_path = dataset_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        if isinstance(manifest, dict):
            manifest.update(
                {
                    "worker_imported_from_job_id": job_id,
                    "worker_imported_at": int(time.time()),
                    "worker_archive_sha256": actual_sha,
                    "source_owner_user_id": str(meta.get("owner_user_id") or ""),
                    "source_dataset_id": str(meta.get("source_dataset_id") or ""),
                }
            )
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    request = WorkerTrainingRequest(
        selected_accessory_ids=[str(item) for item in meta.get("selected_accessory_ids") or []],
        sample_count=max(1, int(meta.get("sample_count") or 1)),
        train_mode=str(meta.get("train_mode") or "yolo_ocr"),
        dataset_id=imported_dataset_id,
        epochs=max(1, int(meta.get("epochs") or 1)),
        image_size=max(320, int(meta.get("image_size") or 640)),
    )
    body = proxy_json("POST", f"{LOCAL_VANTALINE_BASE_URL}/api/training/start", json_body=request.model_dump())
    remote_job_id = str(body.get("job_id") or body.get("task_id") or body.get("id") or "").strip()
    return {
        **body,
        "ok": True,
        "job_id": remote_job_id,
        "transfer": {
            "mode": "archive_upload",
            "source_job_id": job_id,
            "imported_dataset_id": imported_dataset_id,
            "archive_sha256": actual_sha,
            "dataset_dir": str(dataset_dir),
        },
    }


@app.post("/training/jobs")
def training_jobs(request: WorkerTrainingRequest, _: None = Depends(require_auth)) -> dict[str, Any]:
    require_local_vantaline_ready("training job")
    return proxy_json("POST", f"{LOCAL_VANTALINE_BASE_URL}/api/training/start", json_body=request.model_dump())


@app.get("/training/jobs/{job_id}")
def training_job_status(job_id: str, _: None = Depends(require_auth)) -> dict[str, Any]:
    return proxy_json("GET", f"{LOCAL_VANTALINE_BASE_URL}/api/image-jobs/{job_id}")


@app.get("/training/jobs/{job_id}/artifacts")
def training_job_artifacts(job_id: str, _: None = Depends(require_auth)) -> dict[str, Any]:
    job = proxy_json("GET", f"{LOCAL_VANTALINE_BASE_URL}/api/image-jobs/{job_id}")
    resources = proxy_json("GET", f"{LOCAL_VANTALINE_BASE_URL}/api/training/resources", timeout=60)
    models = [
        artifact_with_payload(item)
        for item in resources.get("models", [])
        if item.get("task_id") == job_id or item.get("run_id") == job_id
    ]
    datasets = [item for item in resources.get("datasets", []) if item.get("id") == job_id or item.get("id") == job.get("source_dataset_id")]
    return {
        "ok": True,
        "job_id": job_id,
        "job": job,
        "models": models,
        "datasets": datasets,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "detail": exc.detail})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("VANTALINE_WORKER_HOST", "0.0.0.0"),
        port=int(os.environ.get("VANTALINE_WORKER_PORT", "8766")),
    )
