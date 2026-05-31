#!/usr/bin/env python3
"""Smoke test LAN-style multipart uploads without shared filesystem paths."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]


def local_lan_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def wait_for_server(base_url: str, timeout_seconds: float = 40.0) -> None:
    deadline = time.time() + timeout_seconds
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with opener.open(f"{base_url}/api/config", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready at {base_url}: {last_error}")


def encode_multipart(fields: dict[str, str], files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    boundary = f"----alook-smoke-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode())
        chunks.append(b"\r\n")
    for field_name, filename, content_type, payload in files:
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
        )
        chunks.append(payload)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def make_png_bytes(color: tuple[int, int, int]) -> bytes:
    image = np.full((96, 128, 3), color, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("could not encode png smoke image")
    return encoded.tobytes()


def make_video_bytes() -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "remote-browser-video.avi"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (96, 72))
        if not writer.isOpened():
            raise RuntimeError("could not create smoke video")
        for idx in range(8):
            frame = np.full((72, 96, 3), (20 + idx * 20, 80, 180), dtype=np.uint8)
            writer.write(frame)
        writer.release()
        return path.read_bytes()


def request_json(url: str, data: bytes, content_type: str, origin: str | None, expect_cors: str) -> dict:
    headers = {
        "Content-Type": content_type,
        "User-Agent": "remote-browser-upload-smoke/1.0",
    }
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers=headers,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            cors_origin = response.headers.get("access-control-allow-origin")
            if expect_cors == "allowed" and cors_origin != origin:
                raise RuntimeError(f"CORS origin was not allowed: got {cors_origin!r}, expected {origin!r}")
            if expect_cors == "denied":
                raise RuntimeError("untrusted cross-origin POST unexpectedly succeeded")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        if expect_cors == "denied" and exc.code == 403:
            return {"status": "denied"}
        raise


def preflight(url: str, origin: str, expect_cors: str) -> None:
    request = urllib.request.Request(
        url,
        method="OPTIONS",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=10) as response:
            if expect_cors == "allowed" and response.status != 200:
                raise RuntimeError(f"preflight failed with {response.status}")
            cors_origin = response.headers.get("access-control-allow-origin")
            if expect_cors == "allowed" and cors_origin != origin:
                raise RuntimeError(f"preflight did not allow origin: got {cors_origin!r}, expected {origin!r}")
            if expect_cors == "denied" and cors_origin:
                raise RuntimeError(f"preflight origin should have been denied, got {cors_origin!r}")
    except urllib.error.HTTPError as exc:
        if expect_cors != "denied":
            raise
        if exc.code != 400:
            raise RuntimeError(f"denied preflight returned unexpected status {exc.code}") from exc


def run_smoke(base_url: str, origin: str | None, expect_cors: str) -> None:
    upload_url = f"{base_url}/api/accessories/preview"
    if origin and expect_cors != "none":
        preflight(upload_url, origin, expect_cors)
    payload, content_type = encode_multipart(
        {
            "name": "remote-browser-smoke",
            "material_type": "text",
            "training_role": "detect_then_ocr",
            "paper_preset": "A4",
        },
        [
            ("files", "mac-photo-one.png", "image/png", make_png_bytes((240, 240, 240))),
            ("files", "mac-photo-two.png", "image/png", make_png_bytes((220, 230, 250))),
            ("files", "mac-rotation-video.avi", "video/x-msvideo", make_video_bytes()),
        ],
    )
    result = request_json(upload_url, payload, content_type, origin, expect_cors)
    if expect_cors == "denied":
        print(json.dumps({"base_url": base_url, "origin": origin, "expect_cors": expect_cors, "status": "denied"}, indent=2))
        return
    candidate = result.get("candidate") or {}
    source_files = candidate.get("original_source_files") or candidate.get("source_files") or []
    if result.get("status") != "candidate_ready" or len(source_files) < 3:
        raise RuntimeError(f"unexpected upload response: {result}")
    print(json.dumps({"base_url": base_url, "origin": origin, "expect_cors": expect_cors, "candidate_id": candidate.get("id"), "uploaded_files": len(source_files)}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--origin", default=None, help="Optional Origin header to simulate a cross-origin browser frontend.")
    parser.add_argument("--expect-cors", choices=["none", "allowed", "denied"], default="none")
    parser.add_argument("--use-existing", action="store_true")
    args = parser.parse_args()

    lan_ip = local_lan_ip()
    base_url = f"http://{lan_ip if lan_ip != '127.0.0.1' else '127.0.0.1'}:{args.port}"
    process: subprocess.Popen[str] | None = None
    if not args.use_existing:
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "local_inspection_service.server:app", "--host", args.host, "--port", str(args.port)],
            cwd=ROOT,
            env=env,
            text=True,
        )
    try:
        wait_for_server(base_url)
        run_smoke(base_url, args.origin, args.expect_cors)
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
