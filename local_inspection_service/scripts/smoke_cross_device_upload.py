#!/usr/bin/env python3
"""Smoke test LAN-style multipart uploads without shared filesystem paths."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
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


def wait_for_server(base_url: str, opener: urllib.request.OpenerDirector, timeout_seconds: float = 40.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with opener.open(f"{base_url}/api/auth/status", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready at {base_url}: {last_error}")


def post_json(opener: urllib.request.OpenerDirector, url: str, payload: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def ensure_authenticated(
    base_url: str,
    opener: urllib.request.OpenerDirector,
    *,
    allow_bootstrap: bool,
    username: str = "",
    password: str = "",
) -> None:
    with opener.open(f"{base_url}/api/auth/status", timeout=5) as response:
        status = json.loads(response.read().decode("utf-8"))
    if status.get("authenticated") is True:
        return
    if status.get("setup_required") is True and allow_bootstrap:
        post_json(
            opener,
            f"{base_url}/api/auth/bootstrap",
            {"username": "cross_device_smoke_admin", "password": "cross-device-smoke-password-1", "display_name": "Cross Device Smoke"},
        )
        return
    if username and password:
        post_json(opener, f"{base_url}/api/auth/login", {"username": username, "password": password})
        return
    raise RuntimeError("existing-instance smoke requires --username and --password-env; automatic bootstrap is isolated-mode only")


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


def request_json(opener: urllib.request.OpenerDirector, url: str, data: bytes, content_type: str, origin: str | None, expect_cors: str) -> dict:
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
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"upload failed with HTTP {exc.code}: {response_body}") from exc


def preflight(opener: urllib.request.OpenerDirector, url: str, origin: str, expect_cors: str) -> None:
    request = urllib.request.Request(
        url,
        method="OPTIONS",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
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


def run_smoke(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    origin: str | None,
    expect_cors: str,
    *,
    name: str = "remote-browser-smoke",
) -> tuple[str, list[str]]:
    upload_url = f"{base_url}/api/accessories/preview"
    if origin and expect_cors != "none":
        preflight(opener, upload_url, origin, expect_cors)
    payload, content_type = encode_multipart(
        {
            "name": name,
            "material_type": "object",
            "material_alpha_policy": "opaque",
            "training_role": "detect_and_classify",
            "object_length_mm": "120",
            "object_width_mm": "80",
            "object_height_mm": "40",
            "size_reference": "manual_measurement",
        },
        [
            ("files", "mac-photo-one.png", "image/png", make_png_bytes((240, 240, 240))),
            ("files", "mac-photo-two.png", "image/png", make_png_bytes((220, 230, 250))),
            ("files", "mac-rotation-video.avi", "video/x-msvideo", make_video_bytes()),
        ],
    )
    result = request_json(opener, upload_url, payload, content_type, origin, expect_cors)
    if expect_cors == "denied":
        print(json.dumps({"base_url": base_url, "origin": origin, "expect_cors": expect_cors, "status": "denied"}, indent=2))
        return "", []
    candidate = result.get("candidate") or {}
    source_files = candidate.get("original_source_files") or candidate.get("source_files") or []
    if result.get("status") != "candidate_ready" or len(source_files) < 3:
        raise RuntimeError(f"unexpected upload response: {result}")
    print(json.dumps({"base_url": base_url, "origin": origin, "expect_cors": expect_cors, "candidate_id": candidate.get("id"), "uploaded_files": len(source_files)}, indent=2))
    return str(candidate.get("id") or ""), [str(path) for path in source_files]


def delete_candidate(opener: urllib.request.OpenerDirector, base_url: str, candidate_id: str) -> dict:
    if not candidate_id:
        return {}
    request = urllib.request.Request(
        f"{base_url}/api/image-job-candidates/{urllib.parse.quote(candidate_id, safe='')}",
        method="DELETE",
    )
    with opener.open(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"candidate cleanup failed with {response.status}")
        return json.loads(response.read().decode("utf-8"))


def confirm_candidate(opener: urllib.request.OpenerDirector, base_url: str, candidate_id: str) -> dict:
    request = urllib.request.Request(
        f"{base_url}/api/accessories/confirm/{urllib.parse.quote(candidate_id, safe='')}",
        data=b"",
        method="POST",
    )
    with opener.open(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"candidate confirmation failed with {response.status}")
        return json.loads(response.read().decode("utf-8"))


def isolated_service_root(temp_root: Path) -> Path:
    source_service = ROOT / "local_inspection_service"
    isolated_service = temp_root / "local_inspection_service"
    isolated_service.mkdir(parents=True)
    for child in source_service.iterdir():
        if child.name in {"data", "uploads", "outputs", "__pycache__"}:
            continue
        (isolated_service / child.name).symlink_to(child, target_is_directory=child.is_dir())
    return temp_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--origin", default=None, help="Optional Origin header to simulate a cross-origin browser frontend.")
    parser.add_argument("--expect-cors", choices=["none", "allowed", "denied"], default="none")
    parser.add_argument("--use-existing", action="store_true")
    parser.add_argument("--username", default="", help="Existing-instance smoke username; required with --use-existing.")
    parser.add_argument("--password-env", default="", help="Environment variable containing the existing-instance password.")
    args = parser.parse_args()

    password = os.environ.get(args.password_env, "") if args.password_env else ""
    if args.use_existing and (not args.username or not args.password_env or not password):
        parser.error("--use-existing requires --username and a populated --password-env")

    lan_ip = local_lan_ip()
    connect_host = lan_ip if args.host in {"0.0.0.0", "::"} else args.host
    if connect_host == "localhost":
        connect_host = "127.0.0.1"
    base_url = f"http://{connect_host}:{args.port}"
    process: subprocess.Popen[str] | None = None
    isolated_root_context: tempfile.TemporaryDirectory[str] | None = None
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookie_jar))
    if not args.use_existing:
        isolated_root_context = tempfile.TemporaryDirectory(prefix="vantaline_cross_device_root_", dir="/tmp")
        server_root = isolated_service_root(Path(isolated_root_context.name))
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["LOCAL_INSPECTION_ROOT"] = str(server_root)
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "local_inspection_service.server:app", "--host", args.host, "--port", str(args.port)],
            cwd=server_root,
            env=env,
            text=True,
        )
    candidate_id = ""
    source_files: list[str] = []
    cleanup_error: BaseException | None = None
    try:
        wait_for_server(base_url, opener)
        ensure_authenticated(
            base_url,
            opener,
            allow_bootstrap=not args.use_existing,
            username=args.username,
            password=password,
        )
        candidate_id, source_files = run_smoke(opener, base_url, args.origin, args.expect_cors)
        if candidate_id and not args.use_existing:
            cleanup_result = delete_candidate(opener, base_url, candidate_id)
            if not cleanup_result.get("deleted_artifacts"):
                raise RuntimeError("unconfirmed candidate cleanup did not report any deleted artifact directory")
            leftover = [path for path in source_files if Path(path).exists()]
            if leftover:
                raise RuntimeError(f"unconfirmed candidate cleanup left source files behind: {leftover}")
            candidate_id = ""
            source_files = []

            candidate_id, source_files = run_smoke(
                opener,
                base_url,
                args.origin,
                args.expect_cors,
                name="remote-browser-confirmed-smoke",
            )
            confirmation = confirm_candidate(opener, base_url, candidate_id)
            if confirmation.get("status") not in {"saved", "already_saved"}:
                raise RuntimeError(f"unexpected candidate confirmation response: {confirmation}")
            cleanup_result = delete_candidate(opener, base_url, candidate_id)
            if cleanup_result.get("deleted_artifacts"):
                raise RuntimeError("confirmed candidate cleanup deleted shared accessory artifacts")
            missing = [path for path in source_files if not Path(path).exists()]
            if missing:
                raise RuntimeError(f"confirmed accessory source files were deleted: {missing}")
            candidate_id = ""
            source_files = []
    finally:
        try:
            if candidate_id:
                cleanup_result = delete_candidate(opener, base_url, candidate_id)
                if not args.use_existing:
                    status = str(cleanup_result.get("status") or "")
                    if status != "deleted":
                        raise RuntimeError(f"candidate cleanup returned unexpected result: {cleanup_result}")
        except BaseException as exc:  # noqa: BLE001 - teardown must continue before surfacing cleanup failure
            cleanup_error = exc
        finally:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            if isolated_root_context is not None:
                isolated_root_context.cleanup()
        if cleanup_error is not None:
            raise cleanup_error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
