#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_plc_phase1_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)
os.environ["VANTALINE_YOLO_PREWARM"] = "0"
os.environ["INSPECTION_WORKER_WATCHER"] = "0"
os.environ["LOCAL_INSPECTION_AUTO_RESUME_WORKER"] = "0"

from local_inspection_service.plc_fx_ascii import (  # noqa: E402
    ACK,
    CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT,
    NAK,
    DEFAULT_PLC_CONFIG,
    FxAsciiClient,
    PlcTransportError,
    build_d206_frame,
    build_y04_frame,
    checksum,
    clear_memory_dispatches,
    dispatch_detection_result,
    normalize_config,
)
from local_inspection_service.scripts import testclient_threadpool_shim  # noqa: E402

testclient_threadpool_shim.install()
TestClient = testclient_threadpool_shim.SmokeASGIClient

from local_inspection_service import server  # noqa: E402


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class FakeTransport:
    def __init__(self, response: bytes | BaseException, writes: list[bytes]) -> None:
        self.response = response
        self.writes = writes
        self.closed = False

    def write(self, frame: bytes) -> int:
        self.writes.append(frame)
        return len(frame)

    def flush(self) -> None:
        return None

    def read(self, size: int) -> bytes:
        assert size == 1
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    def close(self) -> None:
        self.closed = True


class SequenceFactory:
    def __init__(self, responses: list[bytes | BaseException]) -> None:
        self.responses = list(responses)
        self.writes: list[bytes] = []
        self.opens = 0

    def __call__(self, _config: dict[str, Any]) -> FakeTransport:
        self.opens += 1
        response = self.responses.pop(0) if self.responses else ACK
        if isinstance(response, PlcTransportError):
            raise response
        return FakeTransport(response, self.writes)


def enabled_config(**overrides: Any) -> dict[str, Any]:
    return normalize_config({**DEFAULT_PLC_CONFIG, "enabled": True, "serial_port": "COM3", **overrides})


def save_plc(config_value: dict[str, Any]) -> None:
    server.mutate_app_config_atomically(lambda config: config.__setitem__("plc", config_value))


def expect_transport_error(code: str, factory: SequenceFactory, *, retries: int = 0) -> PlcTransportError:
    try:
        FxAsciiClient(enabled_config(retries=retries), transport_factory=factory).sync_result(True)
    except PlcTransportError as exc:
        assert exc.code == code, (code, exc.code)
        return exc
    raise AssertionError(f"expected PlcTransportError({code})")


def test_golden_frames_and_checksum() -> None:
    assert build_d206_frame("119C", False) == b"\x021119C0000\x03CF"
    assert build_d206_frame("119C", True) == b"\x021119C0001\x03D0"
    assert build_y04_frame("0108", False) == b"\x0280108\x0301"
    assert build_y04_frame("0108", True) == b"\x0270108\x0300"
    assert checksum(b"1119C0001\x03") == b"D0"
    assert build_d206_frame("119C", False, CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT) == b"\x021119C0000\x03D2"
    assert build_d206_frame("119C", True, CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT) == b"\x021119C0001\x03D3"
    assert build_y04_frame("0108", False, CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT) == b"\x0280108\x0304"
    assert build_y04_frame("0108", True, CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT) == b"\x0270108\x0303"
    assert checksum(b"1119C0001\x03", CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT) == b"D3"


def test_ack_nak_short_timeout_retry_and_open_failure() -> None:
    ack = SequenceFactory([ACK])
    receipts = FxAsciiClient(enabled_config(retries=0), transport_factory=ack).sync_result(True)
    assert receipts[0].target == "D206"
    assert ack.writes == [build_d206_frame("119C", True)]

    expect_transport_error("nak", SequenceFactory([NAK]))
    empty_read = expect_transport_error("timeout", SequenceFactory([b""]))
    assert empty_read.diagnostic_source == "empty_read"
    short = expect_transport_error("short_response", SequenceFactory([b"?"]))
    assert short.diagnostic_source == "non_ack_control_byte"
    explicit_timeout = expect_transport_error("timeout", SequenceFactory([TimeoutError("fake timeout")]))
    assert explicit_timeout.diagnostic_source == "read_timeout_exception"
    open_error = PlcTransportError("serial_open_failed", "serial port could not be opened")
    expect_transport_error("serial_open_failed", SequenceFactory([open_error]))

    retry = SequenceFactory([NAK, ACK])
    receipt = FxAsciiClient(enabled_config(retries=1), transport_factory=retry).sync_result(False)[0]
    assert retry.opens == 2
    assert receipt.attempts == 2
    assert retry.writes == [build_d206_frame("119C", False), build_d206_frame("119C", False)]


def test_disabled_mapping_y04_idempotence_and_failure_isolation() -> None:
    clear_memory_dispatches()
    opens = 0

    def forbidden_factory(_config: dict[str, Any]) -> Any:
        nonlocal opens
        opens += 1
        raise AssertionError("disabled dispatch opened serial")

    disabled = dispatch_detection_result(
        dispatch_id="disabled-1",
        source="image",
        request_id="img-disabled",
        passed=True,
        config=DEFAULT_PLC_CONFIG,
        transport_factory=forbidden_factory,
    )
    assert disabled["status"] == "disabled"
    assert disabled["attempted"] is False
    assert opens == 0

    clear_memory_dispatches()
    open_failure = SequenceFactory([PlcTransportError("serial_open_failed", "serial port could not be opened")])
    open_failed = dispatch_detection_result(
        dispatch_id="open-failed-1",
        source="image",
        request_id="img-open-failed",
        passed=True,
        config=enabled_config(retries=0),
        transport_factory=open_failure,
    )
    assert open_failed["status"] == "failed"
    assert open_failed["attempted"] is False
    assert open_failed["physical_status"] == "not_attempted"
    assert [item["status"] for item in open_failed["history"]] == ["queued", "attempting", "failed"]
    assert "sent" not in [item["status"] for item in open_failed["history"]]
    assert open_failure.opens == 1
    assert open_failure.writes == []

    clear_memory_dispatches()
    no_y = SequenceFactory([ACK])
    passed = dispatch_detection_result(
        dispatch_id="pass-1",
        source="image",
        request_id="img-pass",
        passed=True,
        config=enabled_config(write_y04=False, retries=0),
        transport_factory=no_y,
    )
    assert passed["status"] == "acknowledged"
    assert passed["targets"] == ["D206"]
    assert no_y.writes == [build_d206_frame("119C", True)]
    duplicate = dispatch_detection_result(
        dispatch_id="pass-1",
        source="image",
        request_id="img-pass",
        passed=True,
        config=enabled_config(write_y04=False, retries=0),
        transport_factory=no_y,
    )
    assert duplicate["duplicate"] is True
    assert len(no_y.writes) == 1

    clear_memory_dispatches()
    with_y = SequenceFactory([ACK, ACK])
    failed_mapping = dispatch_detection_result(
        dispatch_id="fail-1",
        source="video",
        request_id="vid-fail",
        passed=False,
        config=enabled_config(write_y04=True, retries=0),
        transport_factory=with_y,
    )
    assert failed_mapping["targets"] == ["D206", "Y04"]
    assert with_y.writes == [build_d206_frame("119C", False), build_y04_frame("0108", False)]
    assert [item["status"] for item in failed_mapping["history"]] == ["queued", "attempting", "sent", "sent", "acknowledged"]

    persistent = SequenceFactory([ACK])
    server._plc_transport_factory = persistent
    save_plc(enabled_config(retries=0, write_y04=False))
    first_server_dispatch = server.dispatch_plc_for_detection(
        {"request_id": "persistent-result", "passed": True},
        source="image",
        fingerprint="same-upload-sha",
    )
    second_server_dispatch = server.dispatch_plc_for_detection(
        {"request_id": "persistent-result", "passed": True},
        source="image",
        fingerprint="same-upload-sha",
    )
    assert first_server_dispatch["plc_sync"]["status"] == "acknowledged"
    assert second_server_dispatch["plc_sync"]["duplicate"] is True
    assert persistent.writes == [build_d206_frame("119C", True)]
    server._plc_transport_factory = None

    clear_memory_dispatches()
    main_result = {"request_id": "keep-result", "passed": False, "rule": {"passed": False}}
    original = {"request_id": main_result["request_id"], "passed": main_result["passed"], "rule": dict(main_result["rule"])}
    server._plc_transport_factory = SequenceFactory([NAK])
    save_plc(enabled_config(retries=0))
    enriched = server.dispatch_plc_for_detection(main_result, source="image", fingerprint="failure-isolation")
    assert enriched["passed"] is original["passed"]
    assert enriched["rule"] == original["rule"]
    assert enriched["plc_sync"]["status"] == "failed"
    assert enriched["plc_sync"]["error_code"] == "nak"
    assert [item["status"] for item in enriched["plc_sync"]["history"]] == ["queued", "attempting", "sent", "failed"]
    server._plc_transport_factory = None


def test_acknowledged_write_with_final_audit_failure_is_never_reported_unattempted() -> None:
    clear_memory_dispatches()
    physical = SequenceFactory([ACK])
    save_plc(enabled_config(retries=0, write_y04=False))
    original_finalize = server.plc_finalize_dispatch

    def fail_final_ack_persist(dispatch_id: str, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("reason") == "":
            raise OSError("injected final audit persistence failure")
        return original_finalize(dispatch_id, **kwargs)

    server._plc_transport_factory = physical
    server.plc_finalize_dispatch = fail_final_ack_persist
    try:
        result = server.dispatch_plc_for_detection(
            {"request_id": "ack-audit-failure", "passed": True, "rule": {"passed": True}},
            source="image",
            fingerprint="ack-audit-failure-sha",
        )
    finally:
        server.plc_finalize_dispatch = original_finalize
        server._plc_transport_factory = None

    sync = result["plc_sync"]
    assert result["passed"] is True
    assert result["rule"] == {"passed": True}
    assert physical.opens == 1
    assert physical.writes == [build_d206_frame("119C", True)]
    assert sync["status"] == "failed", sync
    assert sync["attempted"] is True
    assert sync["physical_status"] == "acknowledged"
    assert sync["audit_status"] == "persist_failed"
    assert sync["outcome"] == "acknowledged_audit_unpersisted"
    assert sync["error_code"] == "audit_persist_failed_after_ack"
    assert [item["status"] for item in sync["history"]] == ["queued", "attempting", "sent", "acknowledged", "failed"]


def assert_status(response: Any, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected {expected}, got {response.status_code}: {response.text[:500]}")


def test_settings_api_persistence_roundtrip_permissions_and_validation() -> None:
    admin = TestClient(server.app)
    unauth = TestClient(server.app)
    viewer = TestClient(server.app)

    bootstrap = admin.post(
        "/api/auth/bootstrap",
        json={"username": "plc_admin", "password": "plc-admin-password-123", "display_name": "PLC Admin"},
    )
    assert_status(bootstrap, 200, "bootstrap admin")
    assert_status(unauth.get("/api/plc/config"), 401, "unauthenticated PLC config")
    create_viewer = admin.post(
        "/api/auth/users",
        json={
            "username": "plc_viewer",
            "password": "plc-viewer-password-123",
            "display_name": "PLC Viewer",
            "role": "user",
            "permissions": ["inspection"],
            "active": True,
        },
    )
    assert_status(create_viewer, 200, "create viewer")
    assert_status(viewer.post("/api/auth/login", json={"username": "plc_viewer", "password": "plc-viewer-password-123"}), 200, "viewer login")
    assert_status(viewer.get("/api/plc/config"), 403, "viewer PLC GET permission")
    assert_status(viewer.post("/api/plc/config", json={"enabled": False}), 403, "viewer PLC POST permission")

    saved_payload = {
        "enabled": True,
        "protocol": "fx_programming_port_ascii",
        "checksum_mode": "exclude_etx_legacy_vb",
        "serial_port": "/dev/ttyUSB0",
        "baudrate": 19200,
        "parity": "O",
        "data_bits": 8,
        "stop_bits": 2,
        "d206_address": "11AA",
        "y04_address": "01B0",
        "write_y04": True,
        "timeout": 2.5,
        "retries": 3,
    }
    saved = admin.post("/api/plc/config", json=saved_payload)
    assert_status(saved, 200, "save PLC config")
    assert saved.json()["config"] == saved_payload
    reloaded = admin.get("/api/plc/config")
    assert_status(reloaded, 200, "reload PLC config")
    assert reloaded.json()["config"] == saved_payload
    assert server.load_config()["plc"] == saved_payload
    assert server.route_required_permission("/api/plc/config", "GET") == "system_settings"
    assert server.route_required_permission("/api/plc/config", "POST") == "system_settings"

    invalid_payloads = [
        {"protocol": "modbus_rtu"},
        {"checksum_mode": "not_a_mode"},
        {"serial_port": "../../dev/ttyUSB0"},
        {"baudrate": 12345},
        {"parity": "MARK"},
        {"data_bits": 6},
        {"stop_bits": 3},
        {"d206_address": "XYZ1"},
        {"timeout": 0.01},
        {"retries": 99},
    ]
    for index, payload in enumerate(invalid_payloads):
        assert_status(admin.post("/api/plc/config", json=payload), 400, f"invalid PLC config {index}")

    strict_invalid_payloads = [
        {"enabled": "false"},
        {"enabled": 1},
        {"retries": "2"},
        {"unknown_field": True},
    ]
    for index, payload in enumerate(strict_invalid_payloads):
        response = admin.post("/api/plc/config", json=payload)
        assert 400 <= response.status_code < 500, (index, response.status_code, response.text)

    disabled = admin.post("/api/plc/config", json={**saved_payload, "enabled": False, "serial_port": ""})
    assert_status(disabled, 200, "disable PLC config")
    assert disabled.json()["config"]["enabled"] is False
    assert disabled.json()["config"]["serial_port"] == ""
    assert_status(admin.post("/api/plc/config", json={"enabled": True}), 400, "enabled PLC requires serial port")


def test_image_endpoint_dispatches_once_after_final_result() -> None:
    admin = TestClient(server.app)
    assert_status(admin.post("/api/auth/login", json={"username": "plc_admin", "password": "plc-admin-password-123"}), 200, "admin relogin")
    writes = SequenceFactory([ACK])
    server._plc_transport_factory = writes
    save_plc(enabled_config(retries=0, write_y04=False))
    original_analyze = server.analyze_bgr
    server.analyze_bgr = lambda _image, request_id, _model_id=None, **_kwargs: {
        "request_id": request_id,
        "passed": True,
        "rule": {"passed": True},
        "detections": [],
        "annotated_url": "/outputs/fake.jpg",
    }
    try:
        response = admin.post("/api/analyze/image", files={"file": ("plc-image.png", TINY_PNG, "image/png")})
    finally:
        server.analyze_bgr = original_analyze
        server._plc_transport_factory = None
    assert_status(response, 200, "image detection PLC dispatch")
    payload = response.json()
    assert payload["passed"] is True
    assert payload["plc_sync"]["status"] == "acknowledged"
    assert writes.writes == [build_d206_frame("119C", True)]


def test_video_endpoint_dispatches_once_after_aggregate_result() -> None:
    admin = TestClient(server.app)
    assert_status(admin.post("/api/auth/login", json={"username": "plc_admin", "password": "plc-admin-password-123"}), 200, "admin video login")
    writes = SequenceFactory([ACK])
    server._plc_transport_factory = writes
    save_plc(enabled_config(retries=0, write_y04=False))

    class FakeCapture:
        def __init__(self, _path: str) -> None:
            self.index = 0

        def isOpened(self) -> bool:
            return True

        def get(self, _key: int) -> float:
            return 1.0

        def read(self) -> tuple[bool, Any]:
            if self.index >= 2:
                return False, None
            self.index += 1
            return True, server.np.zeros((2, 2, 3), dtype=server.np.uint8)

        def release(self) -> None:
            return None

    original_capture = server.cv2.VideoCapture
    original_analyze = server.analyze_bgr
    server.cv2.VideoCapture = FakeCapture
    server.analyze_bgr = lambda _image, request_id, _model_id=None, **_kwargs: {
        "request_id": request_id,
        "passed": True,
        "rule": {"passed": True, "missing": []},
        "detections": [],
        "annotated_url": "/outputs/fake-frame.jpg",
    }
    try:
        response = admin.post("/api/analyze/video", files={"file": ("plc-video.mp4", b"fake-video", "video/mp4")})
    finally:
        server.cv2.VideoCapture = original_capture
        server.analyze_bgr = original_analyze
        server._plc_transport_factory = None
    assert_status(response, 200, "video detection PLC dispatch")
    payload = response.json()
    assert payload["passed"] is True
    assert payload["sampled_frames"] == 2
    assert payload["plc_sync"]["source"] == "video"
    assert payload["plc_sync"]["status"] == "acknowledged"
    assert writes.writes == [build_d206_frame("119C", True)], "video must dispatch once after aggregation"


def main() -> None:
    test_golden_frames_and_checksum()
    test_ack_nak_short_timeout_retry_and_open_failure()
    test_disabled_mapping_y04_idempotence_and_failure_isolation()
    test_acknowledged_write_with_final_audit_failure_is_never_reported_unattempted()
    test_settings_api_persistence_roundtrip_permissions_and_validation()
    test_image_endpoint_dispatches_once_after_final_result()
    test_video_endpoint_dispatches_once_after_aggregate_result()
    print("smoke_plc_phase1: ok")


if __name__ == "__main__":
    main()
