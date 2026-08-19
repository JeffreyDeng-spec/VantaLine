#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_plc_phase2_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)
os.environ["VANTALINE_YOLO_PREWARM"] = "0"
os.environ["INSPECTION_WORKER_WATCHER"] = "0"
os.environ["LOCAL_INSPECTION_AUTO_RESUME_WORKER"] = "0"

from local_inspection_service.plc_fx_ascii import (  # noqa: E402
    ACK,
    DEFAULT_PLC_CONFIG,
    PlcConfigError,
    build_d206_frame,
    build_d_register_read_frame,
    canonical_logical_device,
    checksum,
    dispatch_detection_result,
    legacy_protocol_address_to_device,
    logical_device_address,
    normalize_config,
    parse_d_register_read_response,
)
from local_inspection_service import server  # noqa: E402


class AckTransport:
    def __init__(self, writes: list[bytes]) -> None:
        self.writes = writes

    def write(self, frame: bytes) -> int:
        self.writes.append(frame)
        return len(frame)

    def flush(self) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return ACK

    def close(self) -> None:
        return None


def test_logical_address_contract() -> None:
    assert logical_device_address("D0") == "1000"
    assert logical_device_address("D110") == "10DC"
    assert logical_device_address("D206") == "119C"
    assert logical_device_address("D30719") == "FFFE"
    assert canonical_logical_device("y4") == "Y04"
    assert canonical_logical_device("Y004") == "Y04"
    assert logical_device_address("Y04") == "0108"
    assert logical_device_address("Y10") == "0110"
    assert legacy_protocol_address_to_device("119C", "D") == "D206"
    assert legacy_protocol_address_to_device("0108", "Y") == "Y04"
    for invalid in ("119C", "Y08", "Y09", "D30720", "M10", "D-1"):
        try:
            logical_device_address(invalid)
        except PlcConfigError:
            pass
        else:
            raise AssertionError(f"invalid logical address accepted: {invalid}")


def test_config_migration_and_dynamic_targets() -> None:
    legacy = normalize_config(
        {
            "d206_address": "11AA",
            "y04_address": "01B0",
            "write_y04": True,
        }
    )
    assert legacy["result_register"] == "D213"
    assert legacy["output_control_point"] == "Y130"
    historical_v1 = server.normalize_plc_v1_snapshot(
        {
            "enabled": True,
            "protocol": "fx_programming_port_ascii",
            "checksum_mode": "exclude_etx_legacy_vb",
            "serial_port": "COM3",
            "baudrate": 9600,
            "parity": "E",
            "data_bits": 7,
            "stop_bits": 1,
            "d206_address": "119D",
            "y04_address": "0109",
            "write_y04": True,
            "timeout": 1.0,
            "retries": 1,
        }
    )
    assert historical_v1["d206_address"] == "119D"
    assert historical_v1["y04_address"] == "0109"

    config = normalize_config(
        {
            **DEFAULT_PLC_CONFIG,
            "enabled": True,
            "serial_port": "COM3",
            "result_register": "D110",
            "output_control_point": "",
        }
    )
    writes: list[bytes] = []
    result = dispatch_detection_result(
        dispatch_id="phase2-dynamic-target",
        source="image",
        request_id="phase2",
        passed=True,
        config=config,
        transport_factory=lambda _config: AckTransport(writes),
    )
    assert result["planned_targets"] == ["D110"]
    assert writes == [build_d206_frame("10DC", True)]
    assert all(not item.get("target", "").startswith("Y") for item in result.get("operations", []))

    try:
        normalize_config({**DEFAULT_PLC_CONFIG, "capture_trigger_enabled": True, "capture_input_register": "D206"})
    except PlcConfigError as exc:
        assert "different" in str(exc)
    else:
        raise AssertionError("input/result register conflict accepted")

    try:
        normalize_config({**DEFAULT_PLC_CONFIG, "d206_address": "119C"})
    except PlcConfigError as exc:
        assert "cannot be mixed" in str(exc)
    else:
        raise AssertionError("legacy and v2 address fields were mixed")


def test_read_frame_and_response_contract() -> None:
    assert build_d_register_read_frame("119C").startswith(b"\x020119C02\x03")
    body = b"0001\x03"
    assert parse_d_register_read_response(b"\x02" + body + checksum(body)) == 1
    for invalid in (b"", b"\x020001\x03FF", b"\x02ZZZZ\x0300"):
        try:
            parse_d_register_read_response(invalid)
        except Exception:
            pass
        else:
            raise AssertionError(f"invalid read response accepted: {invalid!r}")


def test_capture_edge_session_and_idempotency() -> None:
    server.mutate_app_config_atomically(
        lambda config: config.update(
            {
                "plc": normalize_config(DEFAULT_PLC_CONFIG),
                server.PLC_CONTROL_GENERATION_KEY: 7,
                server.PLC_RUNTIME_COORDINATION_KEY: {},
            }
        )
    )
    session = server.plc_claim_capture_session("operator-1", "model-a")
    try:
        server.plc_claim_capture_session("operator-1", "model-b")
    except PlcConfigError as exc:
        assert "session_in_use" in str(exc)
    else:
        raise AssertionError("second browser tab replaced an active capture lease")
    assert server.plc_apply_capture_observation(1, generation=7, owner_epoch=3, trigger_value=1) is None
    assert server.plc_apply_capture_observation(0, generation=7, owner_epoch=3, trigger_value=1) is None
    first = server.plc_apply_capture_observation(1, generation=7, owner_epoch=3, trigger_value=1)
    assert first and first["status"] == "pending"
    assert server.plc_apply_capture_observation(1, generation=7, owner_epoch=3, trigger_value=1) is None

    claimed = server.plc_claim_next_capture_event(session["session_id"], "operator-1")
    assert claimed and claimed["trigger_id"] == first["trigger_id"]
    assert server.plc_begin_triggered_analysis(
        first["trigger_id"], session["session_id"], "operator-1", "model-a", "sha256-a"
    ) is None
    expected = {"request_id": "plc-trigger", "passed": True}
    server.plc_finish_triggered_analysis(first["trigger_id"], session["session_id"], "operator-1", expected)
    duplicate = server.plc_begin_triggered_analysis(
        first["trigger_id"], session["session_id"], "operator-1", "model-a", "sha256-a"
    )
    assert duplicate == expected
    try:
        server.plc_begin_triggered_analysis(
            first["trigger_id"], session["session_id"], "operator-1", "model-a", "sha256-b"
        )
    except PlcConfigError as exc:
        assert "payload_conflict" in str(exc)
    else:
        raise AssertionError("same trigger accepted a different image")

    server.plc_apply_capture_observation(0, generation=7, owner_epoch=3, trigger_value=1)
    second = server.plc_apply_capture_observation(1, generation=7, owner_epoch=3, trigger_value=1)
    assert second and second["trigger_id"] != first["trigger_id"]
    second_claim = server.plc_claim_next_capture_event(session["session_id"], "operator-1")
    assert second_claim and second_claim["trigger_id"] == second["trigger_id"]
    assert server.plc_begin_triggered_analysis(
        second["trigger_id"], session["session_id"], "operator-1", "model-a", "sha256-c"
    ) is None

    def expire_processing(state: dict[str, Any]) -> None:
        capture = state["capture"]
        event = next(item for item in capture["events"] if item["trigger_id"] == second["trigger_id"])
        event["processing_expires_at"] = time.time() - 1

    server.mutate_plc_runtime_coordination(expire_processing)
    server.plc_heartbeat_capture_session(session["session_id"], "operator-1")
    server.plc_finish_triggered_analysis(
        second["trigger_id"], session["session_id"], "operator-1", {"passed": True}
    )
    runtime = server.load_config()[server.PLC_RUNTIME_COORDINATION_KEY]["capture"]
    expired = next(item for item in runtime["events"] if item["trigger_id"] == second["trigger_id"])
    assert expired["status"] == "expired"
    assert server.plc_apply_capture_observation(1, generation=8, owner_epoch=3, trigger_value=1) is None


def main() -> None:
    test_logical_address_contract()
    test_config_migration_and_dynamic_targets()
    test_read_frame_and_response_contract()
    test_capture_edge_session_and_idempotency()
    print("smoke_plc_phase2: ok")


if __name__ == "__main__":
    main()
