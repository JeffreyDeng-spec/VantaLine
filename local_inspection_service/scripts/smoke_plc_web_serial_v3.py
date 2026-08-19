#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_plc_web_serial_v3_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)
os.environ["VANTALINE_YOLO_PREWARM"] = "0"
os.environ["INSPECTION_WORKER_WATCHER"] = "0"
os.environ["LOCAL_INSPECTION_AUTO_RESUME_WORKER"] = "0"
os.environ["VANTALINE_PLC_WEB_SERIAL_ALLOW_JSON_TEST"] = "1"

from local_inspection_service.plc_fx_ascii import (  # noqa: E402
    PlcConfigError,
    build_d_register_write_frame,
    build_y_force_frame,
    encode_fx_word,
    logical_device_address,
)
from local_inspection_service.plc_web_serial import (  # noqa: E402
    DEFAULT_WEB_SERIAL_CONFIG,
    build_web_serial_plan,
    normalize_web_serial_config,
    web_serial_resolved_addresses,
)
from local_inspection_service.scripts import testclient_threadpool_shim  # noqa: E402

testclient_threadpool_shim.install()
TestClient = testclient_threadpool_shim.SmokeASGIClient

from local_inspection_service import server  # noqa: E402


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def assert_status(response, expected: int, label: str) -> None:
    assert response.status_code == expected, f"{label}: {response.status_code} {response.text[:500]}"


def test_address_and_plan_contract() -> None:
    assert web_serial_resolved_addresses({**DEFAULT_WEB_SERIAL_CONFIG, "result_register": "D0"})["result_register"] == "1000"
    assert web_serial_resolved_addresses({**DEFAULT_WEB_SERIAL_CONFIG, "result_register": "D110"})["result_register"] == "10DC"
    assert web_serial_resolved_addresses(DEFAULT_WEB_SERIAL_CONFIG)["result_register"] == "119C"
    assert web_serial_resolved_addresses({**DEFAULT_WEB_SERIAL_CONFIG, "output_control_point": "Y10"})["output_control_point"] == "0805"
    assert [item["target"] for item in build_web_serial_plan({**DEFAULT_WEB_SERIAL_CONFIG, "output_control_point": ""}, True)] == ["D206"]
    assert [item["target"] for item in build_web_serial_plan(DEFAULT_WEB_SERIAL_CONFIG, False)] == ["D206", "Y04"]
    for value in ("119C", "D256", "M1"):
        try:
            normalize_web_serial_config({**DEFAULT_WEB_SERIAL_CONFIG, "result_register": value})
        except PlcConfigError:
            pass
        else:
            raise AssertionError(f"invalid D address accepted: {value}")
    for value in ("0108", "Y08", "Y09", "Y20"):
        try:
            normalize_web_serial_config({**DEFAULT_WEB_SERIAL_CONFIG, "output_control_point": value})
        except PlcConfigError:
            pass
        else:
            raise AssertionError(f"invalid Y address accepted: {value}")
    assert encode_fx_word(0x1234) == "3412"
    expected_d = {
        ("D0", True): "023131303030303230313030033138",
        ("D0", False): "023131303030303230303030033137",
        ("D110", True): "023131304443303230313030033346",
        ("D110", False): "023131304443303230303030033345",
        ("D206", True): "023131313943303230313030033335",
        ("D206", False): "023131313943303230303030033334",
    }
    for (device, value), frame_hex in expected_d.items():
        assert build_d_register_write_frame(logical_device_address(device), int(value)).hex().upper() == frame_hex
    expected_y = {
        ("Y00", True): "023730303035034646",
        ("Y00", False): "023830303035033030",
        ("Y04", True): "023730343035033033",
        ("Y04", False): "023830343035033034",
        ("Y10", True): "023730383035033037",
        ("Y10", False): "023830383035033038",
        ("Y17", True): "023730463035033135",
        ("Y17", False): "023830463035033136",
    }
    for (device, value), frame_hex in expected_y.items():
        assert build_y_force_frame(device, value).hex().upper() == frame_hex


def test_workstation_api_rbac_persistence_and_dispatch() -> None:
    client = TestClient(server.app, base_url="https://testserver")
    outsider = TestClient(server.app, base_url="https://testserver")
    assert_status(
        client.post("/api/auth/bootstrap", json={"username": "admin", "password": "admin-password-123", "display_name": "Admin"}),
        200,
        "bootstrap",
    )
    created = client.post(
        "/api/auth/users",
        json={
            "username": "inspector",
            "password": "inspector-password-123",
            "display_name": "Inspector",
            "role": "user",
            "permissions": ["inspection"],
            "active": True,
        },
    )
    assert_status(created, 200, "create inspector")
    assert_status(client.post("/api/plc/config", json={"enabled": True}), 410, "legacy POST is read-only")
    paired = client.post("/api/plc/workstations/pair", json={"name": "一号流水线电脑"})
    assert_status(paired, 200, "pair")
    assert paired.json()["config"]["enabled"] is False
    station_cookie = client.cookies.get(server.PLC_WORKSTATION_COOKIE)
    assert station_cookie

    enabled = {**DEFAULT_WEB_SERIAL_CONFIG, "enabled": True, "output_control_point": ""}
    saved = client.post("/api/plc/workstation/config", json=enabled)
    assert_status(saved, 200, "save workstation config")
    assert saved.json()["config"]["output_control_point"] == ""
    assert saved.json()["effective_enabled"] is False

    assert_status(client.post("/api/auth/logout"), 200, "logout")
    assert client.cookies.get(server.PLC_WORKSTATION_COOKIE) == station_cookie
    assert_status(client.post("/api/auth/login", json={"username": "inspector", "password": "inspector-password-123"}), 200, "inspector login")
    reloaded = client.get("/api/plc/workstation")
    assert_status(reloaded, 200, "reload workstation after login")
    assert "serial=(self)" in reloaded.headers.get("permissions-policy", "")
    assert "script-src 'self'" in reloaded.headers.get("content-security-policy", "")
    assert reloaded.json()["station"]["name"] == "一号流水线电脑"
    assert reloaded.json()["config"]["output_control_point"] == ""
    assert_status(client.post("/api/plc/workstation/config", json=enabled), 403, "inspector cannot configure")
    assert_status(outsider.get("/api/plc/workstation"), 401, "unauthenticated read")

    obsolete = client.post(
        "/api/plc/workstation/connect",
        json={"client_instance_id": "tab_12345678", "model_id": "", "bundle_version": "plc-web-serial-v3"},
    )
    assert_status(obsolete, 409, "obsolete v3 bundle rejected")
    lease = client.post(
        "/api/plc/workstation/connect",
        json={"client_instance_id": "tab_12345678", "model_id": "", "bundle_version": "plc-web-serial-v4"},
    )
    assert_status(lease, 200, "claim lease")
    lease_payload = lease.json()
    active = client.post(
        "/api/plc/workstation/connect/activate",
        json={"session_id": lease_payload["session_id"], "lease_epoch": lease_payload["lease_epoch"]},
    )
    assert_status(active, 200, "activate lease")

    original_analyze = server.analyze_bgr
    server.analyze_bgr = lambda _image, request_id, _model_id=None, **_kwargs: {
        "request_id": request_id,
        "passed": True,
        "rule": {"passed": True},
        "detections": [],
        "annotated_url": "/outputs/fake.jpg",
    }
    try:
        ordinary = client.post("/api/analyze/image", files={"file": ("ordinary.png", TINY_PNG, "image/png")})
        camera = client.post(
            "/api/analyze/camera",
            data={"model_id": "", "plc_session_id": lease_payload["session_id"], "camera_request_id": "camera_request_0001"},
            files={"file": ("camera.png", TINY_PNG, "image/png")},
        )
    finally:
        server.analyze_bgr = original_analyze
    assert_status(ordinary, 200, "ordinary image")
    assert "plc_sync" not in ordinary.json()
    assert_status(camera, 200, "camera image")
    plan = camera.json()["plc_sync"]
    assert plan["status"] == "planned"
    duplicate = client.post(
        "/api/analyze/camera",
        data={"model_id": "", "plc_session_id": lease_payload["session_id"], "camera_request_id": "camera_request_0001"},
        files={"file": ("camera.png", TINY_PNG, "image/png")},
    )
    assert_status(duplicate, 200, "duplicate camera request")
    assert duplicate.json()["plc_sync"]["dispatch_id"] == plan["dispatch_id"]
    original_analyze = server.analyze_bgr
    server.analyze_bgr = lambda _image, request_id, _model_id=None, **_kwargs: {"request_id": request_id, "passed": False, "detections": []}
    try:
        second_camera = client.post(
            "/api/analyze/camera",
            data={"model_id": "", "plc_session_id": lease_payload["session_id"], "camera_request_id": "camera_request_0002"},
            files={"file": ("camera-2.png", TINY_PNG, "image/png")},
        )
    finally:
        server.analyze_bgr = original_analyze
    assert_status(second_camera, 200, "second camera plan")
    second_plan = second_camera.json()["plc_sync"]

    attempt = client.post(
        f"/api/plc/workstation/dispatches/{plan['dispatch_id']}/attempt",
        json={
            "session_id": lease_payload["session_id"],
            "lease_epoch": lease_payload["lease_epoch"],
            "config_generation": reloaded.json()["config_generation"],
        },
    )
    assert_status(attempt, 200, "declare attempt")
    attempt_payload = attempt.json()
    assert len(attempt_payload["frames"]) == 1
    second_attempt = client.post(
        f"/api/plc/workstation/dispatches/{second_plan['dispatch_id']}/attempt",
        json={
            "session_id": lease_payload["session_id"],
            "lease_epoch": lease_payload["lease_epoch"],
            "config_generation": reloaded.json()["config_generation"],
        },
    )
    assert_status(second_attempt, 409, "one in-flight attempt per lease")
    draining = client.post(
        "/api/plc/workstation/lease/disconnect",
        json={"session_id": lease_payload["session_id"], "lease_epoch": lease_payload["lease_epoch"]},
    )
    assert_status(draining, 200, "disconnect while attempt is in flight")
    assert draining.json()["state"] == "draining"
    takeover = client.post(
        "/api/plc/workstation/connect",
        json={"client_instance_id": "tab_87654321", "model_id": "", "bundle_version": "plc-web-serial-v4"},
    )
    assert_status(takeover, 409, "takeover waits for in-flight deadline")
    operation = {
        "target": attempt_payload["frames"][0]["target"],
        "frame_sha256": attempt_payload["frames"][0]["frame_sha256"],
        "status": "acknowledged",
        "response_hex": "06",
        "completed_at": 1,
    }
    receipt_body = {
        "session_id": lease_payload["session_id"],
        "lease_epoch": lease_payload["lease_epoch"],
        "attempt_token": attempt_payload["attempt_token"],
        "outcome": "acknowledged",
        "operations": [operation],
    }
    receipt = client.post(f"/api/plc/workstation/dispatches/{plan['dispatch_id']}/receipt", json=receipt_body)
    assert_status(receipt, 200, "receipt")
    assert receipt.json()["status"] == "acknowledged"
    assert_status(client.post(f"/api/plc/workstation/dispatches/{plan['dispatch_id']}/receipt", json=receipt_body), 200, "idempotent receipt")
    assert_status(client.post(f"/api/plc/workstation/dispatches/{plan['dispatch_id']}/attempt", json={"session_id": lease_payload["session_id"], "lease_epoch": lease_payload["lease_epoch"], "config_generation": reloaded.json()["config_generation"]}), 409, "duplicate attempt")

    assert server.route_required_permission("/api/plc/workstations/pair", "POST") == "system_settings"
    assert server.route_required_permission("/api/plc/workstation/config", "POST") == "system_settings"
    assert server.route_allowed_permissions("/api/plc/workstation/connect", "POST") == ("inspection", "ai_detection")
    assert server.route_allowed_permissions("/api/plc/workstation/dispatches/x/receipt", "POST") == ("inspection", "ai_detection")
    two_frames = build_web_serial_plan(DEFAULT_WEB_SERIAL_CONFIG, True)
    try:
        server._plc_web_serial_receipt_outcome(
            two_frames,
            [
                {"target": "D206", "frame_sha256": two_frames[0]["frame_sha256"], "status": "nak", "response_hex": "15"},
                {"target": "Y04", "frame_sha256": two_frames[1]["frame_sha256"], "status": "acknowledged", "response_hex": "06"},
            ],
        )
    except PlcConfigError as exc:
        assert "y_without_d_ack" in str(exc)
    else:
        raise AssertionError("receipt accepted Y operation without D ACK")
    assert server._plc_web_serial_receipt_outcome(
        two_frames,
        [
            {"target": "D206", "frame_sha256": two_frames[0]["frame_sha256"], "status": "acknowledged", "response_hex": "06"},
            {"target": "Y04", "frame_sha256": two_frames[1]["frame_sha256"], "status": "timeout", "response_hex": ""},
        ],
    ) == "uncertain"

    replacement = TestClient(server.app, base_url="https://testserver")
    assert_status(replacement.post("/api/auth/login", json={"username": "admin", "password": "admin-password-123"}), 200, "replacement admin login")
    stations = replacement.get("/api/plc/workstations")
    assert_status(stations, 200, "list workstations")
    station_id = stations.json()["items"][0]["id"]
    rebound = replacement.post("/api/plc/workstations/pair", json={"name": "一号流水线电脑", "station_id": station_id})
    assert_status(rebound, 200, "rebind existing workstation")
    assert rebound.json()["station"]["id"] == station_id
    assert client.get("/api/plc/workstation").json()["paired"] is False
    assert replacement.get("/api/plc/workstation").json()["paired"] is True

    os.environ.pop("VANTALINE_PLC_WEB_SERIAL_ALLOW_JSON_TEST", None)
    try:
        server._plc_web_serial_mutate(station_id, None, lambda _state: None)
    except PlcConfigError as exc:
        assert "postgres_coordination_unavailable" in str(exc)
    else:
        raise AssertionError("JSON fallback authorized physical Web Serial coordination")


def main() -> int:
    test_address_and_plan_contract()
    test_workstation_api_rbac_persistence_and_dispatch()
    print("PLC Web Serial v4 smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
