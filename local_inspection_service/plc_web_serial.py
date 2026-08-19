"""Browser-owned Mitsubishi FX serial configuration and dispatch plans.

The server never opens a serial port in this transport mode.  It validates the
station profile and signs the exact bytes a foreground Edge/Chrome page may
write through Web Serial.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

try:
    from local_inspection_service.plc_fx_ascii import (
        CHECKSUM_EXCLUDE_ETX_LEGACY_VB,
        CHECKSUM_INCLUDE_ETX,
        CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT,
        CHECKSUM_MODES,
        PROTOCOL_ID,
        PlcConfigError,
        build_d206_frame,
        build_d_register_write_frame,
        build_y04_frame,
        build_y_force_frame,
        logical_device_address,
        logical_force_y_address,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script imports
    from plc_fx_ascii import (  # type: ignore[no-redef]
        CHECKSUM_EXCLUDE_ETX_LEGACY_VB,
        CHECKSUM_INCLUDE_ETX,
        CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT,
        CHECKSUM_MODES,
        PROTOCOL_ID,
        PlcConfigError,
        build_d206_frame,
        build_d_register_write_frame,
        build_y04_frame,
        build_y_force_frame,
        logical_device_address,
        logical_force_y_address,
    )


LEGACY_WEB_SERIAL_SCHEMA_VERSION = 3
LEGACY_WEB_SERIAL_PROFILE_ID = "fx_ascii_16x16_test"
LEGACY_WEB_SERIAL_PROTOCOL_VERSION = "plc-web-serial-v3"
WEB_SERIAL_SCHEMA_VERSION = 4
WEB_SERIAL_TRANSPORT_MODE = "web_serial"
WEB_SERIAL_PROFILE_ID = "fx_ascii_16x16_spec_v1"
WEB_SERIAL_PROTOCOL_VERSION = "plc-web-serial-v4"
WEB_SERIAL_PLAN_DEADLINE_SECONDS = 2.0
WEB_SERIAL_ACK_TIMEOUT_MS = 500
WEB_SERIAL_CONNECTING_LEASE_SECONDS = 60
WEB_SERIAL_ACTIVE_LEASE_SECONDS = 15
WEB_SERIAL_HEARTBEAT_SECONDS = 5

DEFAULT_WEB_SERIAL_CONFIG: dict[str, Any] = {
    "schema_version": WEB_SERIAL_SCHEMA_VERSION,
    "transport_mode": WEB_SERIAL_TRANSPORT_MODE,
    "profile_id": WEB_SERIAL_PROFILE_ID,
    "enabled": False,
    "protocol": PROTOCOL_ID,
    "checksum_mode": CHECKSUM_INCLUDE_ETX,
    "baudrate": 9600,
    "parity": "E",
    "data_bits": 7,
    "stop_bits": 1,
    "result_register": "D206",
    "output_control_point": "Y04",
    "ack_timeout_ms": WEB_SERIAL_ACK_TIMEOUT_MS,
    "retries": 0,
}

LEGACY_WEB_SERIAL_CONFIG: dict[str, Any] = {
    **DEFAULT_WEB_SERIAL_CONFIG,
    "schema_version": LEGACY_WEB_SERIAL_SCHEMA_VERSION,
    "profile_id": LEGACY_WEB_SERIAL_PROFILE_ID,
    "checksum_mode": CHECKSUM_EXCLUDE_ETX_LEGACY_VB,
}

WEB_SERIAL_CONFIG_FIELDS = frozenset(DEFAULT_WEB_SERIAL_CONFIG)
_D_RE = re.compile(r"D(?:0|[1-9][0-9]{0,2})", re.IGNORECASE)
_Y_RE = re.compile(r"Y(?:0[0-7]|1[0-7])", re.IGNORECASE)


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise PlcConfigError(f"{field} must be boolean")
    return value


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlcConfigError(f"{field} must be an integer")
    return value


def _normalize_web_serial_config(
    raw: Mapping[str, Any] | None,
    *,
    defaults: Mapping[str, Any],
    schema_version: int,
    profile_id: str,
    checksum_modes: frozenset[str],
) -> dict[str, Any]:
    source = dict(raw or {})
    unknown = set(source) - WEB_SERIAL_CONFIG_FIELDS
    if unknown:
        raise PlcConfigError(f"unknown Web Serial PLC fields: {sorted(unknown)}")
    config = {**defaults, **source}
    if _strict_int(config["schema_version"], "schema_version") != schema_version:
        raise PlcConfigError(f"schema_version must be {schema_version}")
    if config["transport_mode"] != WEB_SERIAL_TRANSPORT_MODE:
        raise PlcConfigError("transport_mode must be web_serial")
    if config["profile_id"] != profile_id:
        raise PlcConfigError("profile_id is not supported")
    if config["protocol"] != PROTOCOL_ID:
        raise PlcConfigError("protocol is not supported")
    if config["checksum_mode"] not in checksum_modes:
        raise PlcConfigError("checksum_mode is not allowed")
    if _strict_bool(config["enabled"], "enabled") not in {True, False}:
        raise PlcConfigError("enabled must be boolean")
    if _strict_int(config["baudrate"], "baudrate") != 9600:
        raise PlcConfigError("test profile requires baudrate 9600")
    if config["parity"] != "E":
        raise PlcConfigError("test profile requires even parity")
    if _strict_int(config["data_bits"], "data_bits") != 7:
        raise PlcConfigError("test profile requires 7 data bits")
    if _strict_int(config["stop_bits"], "stop_bits") != 1:
        raise PlcConfigError("test profile requires 1 stop bit")
    if _strict_int(config["ack_timeout_ms"], "ack_timeout_ms") != WEB_SERIAL_ACK_TIMEOUT_MS:
        raise PlcConfigError("test profile requires a 500ms ACK timeout")
    if _strict_int(config["retries"], "retries") != 0:
        raise PlcConfigError("Web Serial physical writes cannot be retried automatically")

    result_register = str(config["result_register"] or "").strip().upper()
    if not _D_RE.fullmatch(result_register):
        raise PlcConfigError("result_register must be D0 through D255")
    result_number = int(result_register[1:], 10)
    if not 0 <= result_number <= 255:
        raise PlcConfigError("result_register must be D0 through D255")
    result_register = f"D{result_number}"

    output_control_point = str(config["output_control_point"] or "").strip().upper()
    if output_control_point:
        if not _Y_RE.fullmatch(output_control_point):
            raise PlcConfigError("output_control_point must be Y00 through Y17 using octal digits")
        output_control_point = f"Y{int(output_control_point[1:], 8):02o}"

    return {
        **config,
        "result_register": result_register,
        "output_control_point": output_control_point,
    }


def normalize_web_serial_config(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    return _normalize_web_serial_config(
        raw,
        defaults=DEFAULT_WEB_SERIAL_CONFIG,
        schema_version=WEB_SERIAL_SCHEMA_VERSION,
        profile_id=WEB_SERIAL_PROFILE_ID,
        checksum_modes=frozenset({CHECKSUM_INCLUDE_ETX}),
    )


def normalize_legacy_web_serial_config(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    return _normalize_web_serial_config(
        raw,
        defaults=LEGACY_WEB_SERIAL_CONFIG,
        schema_version=LEGACY_WEB_SERIAL_SCHEMA_VERSION,
        profile_id=LEGACY_WEB_SERIAL_PROFILE_ID,
        checksum_modes=frozenset({
            CHECKSUM_EXCLUDE_ETX_LEGACY_VB,
            CHECKSUM_INCLUDE_ETX_DOCUMENTED_COMMENT,
        }),
    )


def migrate_web_serial_config(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Fail-closed migration from the obsolete v3 frame contract to v4."""
    source = dict(raw or {})
    if not source:
        return dict(DEFAULT_WEB_SERIAL_CONFIG)
    if (
        source.get("schema_version") == LEGACY_WEB_SERIAL_SCHEMA_VERSION
        or source.get("profile_id") == LEGACY_WEB_SERIAL_PROFILE_ID
    ):
        legacy = normalize_legacy_web_serial_config(source)
        return normalize_web_serial_config({
            **DEFAULT_WEB_SERIAL_CONFIG,
            "enabled": False,
            "result_register": legacy["result_register"],
            "output_control_point": legacy["output_control_point"],
        })
    return normalize_web_serial_config(source)


def web_serial_resolved_addresses(config: Mapping[str, Any]) -> dict[str, str]:
    normalized = normalize_web_serial_config(config)
    return {
        "result_register": logical_device_address(normalized["result_register"]),
        "output_control_point": (
            logical_force_y_address(normalized["output_control_point"])
            if normalized["output_control_point"]
            else ""
        ),
    }


def _frame_item(target: str, frame: bytes, operation: str) -> dict[str, Any]:
    frame_hex = frame.hex().upper()
    return {
        "target": target,
        "operation": operation,
        "frame_hex": frame_hex,
        "frame_sha256": hashlib.sha256(frame).hexdigest(),
        "expected_response_hex": "06",
    }


def build_web_serial_plan(config: Mapping[str, Any], passed: bool) -> list[dict[str, Any]]:
    normalized = normalize_web_serial_config(config)
    checksum_mode = normalized["checksum_mode"]
    result_register = normalized["result_register"]
    frames = [
        _frame_item(
            result_register,
            build_d_register_write_frame(
                logical_device_address(result_register),
                1 if passed else 0,
                checksum_mode,
            ),
            "write_result",
        )
    ]
    output_control_point = normalized["output_control_point"]
    if output_control_point:
        frames.append(
            _frame_item(
                output_control_point,
                build_y_force_frame(output_control_point, bool(passed), checksum_mode),
                "set_output_on" if passed else "set_output_off",
            )
        )
    return frames


def build_legacy_web_serial_plan(config: Mapping[str, Any], passed: bool) -> list[dict[str, Any]]:
    """Rebuild v3 frames solely for immutable historical verification."""
    normalized = normalize_legacy_web_serial_config(config)
    checksum_mode = normalized["checksum_mode"]
    result_register = normalized["result_register"]
    frames = [
        _frame_item(
            result_register,
            build_d206_frame(logical_device_address(result_register), bool(passed), checksum_mode),
            "write_result",
        )
    ]
    output_control_point = normalized["output_control_point"]
    if output_control_point:
        frames.append(
            _frame_item(
                output_control_point,
                build_y04_frame(logical_device_address(output_control_point), bool(passed), checksum_mode),
                "set_output_on" if passed else "set_output_off",
            )
        )
    return frames


def web_serial_config_fingerprint(config: Mapping[str, Any]) -> str:
    normalized = normalize_web_serial_config(config)
    material = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(material.encode("ascii")).hexdigest()


def legacy_web_serial_config_fingerprint(config: Mapping[str, Any]) -> str:
    normalized = normalize_legacy_web_serial_config(config)
    material = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(material.encode("ascii")).hexdigest()


def web_serial_profile_fingerprint(config: Mapping[str, Any]) -> str:
    normalized = normalize_web_serial_config(config)
    normalized["enabled"] = False
    material = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(material.encode("ascii")).hexdigest()
