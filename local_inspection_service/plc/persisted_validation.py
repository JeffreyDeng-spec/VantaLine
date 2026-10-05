"""Pure frame binding and persisted historical PLC evidence validation.

Only validates saved evidence; never opens ports, claims leases or retries I/O.
"""
import copy
import hashlib
import json
import re
from typing import Any
from ..plc_fx_ascii import (
    DEFAULT_PLC_CONFIG, PlcConfigError, normalize_config as normalize_plc_config,
    build_d206_frame, build_y04_frame, logical_device_address,
)
from .errors import PlcDispatchStateConflict
from .event_projection import PLC_REDUCER_DERIVED_FIELDS, project_plc_dispatch_events
from .transition_policy import PLC_IMMUTABLE_BINDING_FIELDS, PLC_DISPATCH_KNOWN_FIELDS, _plc_canonical


PLC_LEGACY_IO_CONFIG_FIELDS = frozenset(
    {
        "enabled", "protocol", "checksum_mode", "serial_port", "baudrate", "parity",
        "data_bits", "stop_bits", "d206_address", "y04_address", "write_y04", "timeout", "retries",
    }
)

PLC_SUPPORTED_RECORD_VERSIONS = frozenset({1, 2})

def normalize_plc_v1_snapshot(raw: Any) -> dict[str, Any]:
    """Freeze the canonical Phase-1 snapshot shape for historical verification only."""
    if not isinstance(raw, dict):
        raise PlcConfigError("legacy PLC snapshot must be an object")
    if set(raw) != set(PLC_LEGACY_IO_CONFIG_FIELDS):
        raise PlcConfigError("legacy PLC snapshot fields are not canonical")
    common_probe = {
        key: raw[key]
        for key in (
            "enabled", "protocol", "checksum_mode", "serial_port", "baudrate",
            "parity", "data_bits", "stop_bits", "timeout", "retries",
        )
    }
    migrated = normalize_plc_config(
        {
            **DEFAULT_PLC_CONFIG,
            **common_probe,
            "result_register": "D206",
            "output_control_point": "",
            "capture_trigger_enabled": False,
            "capture_input_register": "",
            "capture_trigger_value": 1,
        }
    )
    d_address = str(raw.get("d206_address") or "").strip().upper()
    y_address = str(raw.get("y04_address") or "").strip().upper()
    if not re.fullmatch(r"[0-9A-F]{4}", d_address):
        raise PlcConfigError("legacy D address must contain four hexadecimal characters")
    if not re.fullmatch(r"[0-9A-F]{4}", y_address):
        raise PlcConfigError("legacy Y address must contain four hexadecimal characters")
    if type(raw.get("write_y04")) is not bool:
        raise PlcConfigError("legacy write_y04 must be a boolean")
    return {
        "enabled": migrated["enabled"],
        "protocol": migrated["protocol"],
        "checksum_mode": migrated["checksum_mode"],
        "serial_port": migrated["serial_port"],
        "baudrate": migrated["baudrate"],
        "parity": migrated["parity"],
        "data_bits": migrated["data_bits"],
        "stop_bits": migrated["stop_bits"],
        "d206_address": d_address,
        "y04_address": y_address,
        "write_y04": bool(raw["write_y04"]),
        "timeout": migrated["timeout"],
        "retries": migrated["retries"],
    }

def build_plc_v1_dispatch_plan(snapshot: dict[str, Any], passed: bool) -> tuple[list[str], list[dict[str, str]]]:
    targets = ["D206", "Y04"] if snapshot["write_y04"] else ["D206"]
    frames = [
        {
            "target": "D206",
            "frame_hex": build_d206_frame(
                snapshot["d206_address"], passed, snapshot["checksum_mode"]
            ).hex().upper(),
        }
    ]
    if snapshot["write_y04"]:
        frames.append(
            {
                "target": "Y04",
                "frame_hex": build_y04_frame(
                    snapshot["y04_address"], passed, snapshot["checksum_mode"]
                ).hex().upper(),
            }
        )
    return targets, frames

def build_plc_dispatch_plan(snapshot: dict[str, Any], passed: bool) -> tuple[list[str], list[dict[str, str]]]:
    result_register = snapshot["result_register"]
    output_control_point = snapshot["output_control_point"]
    targets = [result_register, *([output_control_point] if output_control_point else [])]
    frames = [
        {
            "target": result_register,
            "frame_hex": build_d206_frame(
                logical_device_address(result_register), passed, snapshot["checksum_mode"]
            ).hex().upper(),
        }
    ]
    if output_control_point:
        frames.append(
            {
                "target": output_control_point,
                "frame_hex": build_y04_frame(
                    logical_device_address(output_control_point), passed, snapshot["checksum_mode"]
                ).hex().upper(),
            }
        )
    return targets, frames

PLC_PERSISTED_DISPATCH_FIELDS = frozenset(
    {
        *PLC_IMMUTABLE_BINDING_FIELDS,
        *PLC_REDUCER_DERIVED_FIELDS,
        "enabled", "created_at", "duplicate", "message", "state_version",
    }
)

def verify_persisted_plc_dispatch(record: dict[str, Any]) -> dict[str, Any]:
    """Verify a stored record without rewriting or reinterpreting historical protocol versions."""
    authoritative = dict(record)
    schema_version = authoritative.get("record_schema_version")
    contract_version = authoritative.get("protocol_contract_version")
    if (
        type(schema_version) is not int
        or type(contract_version) is not int
        or schema_version not in PLC_SUPPORTED_RECORD_VERSIONS
        or contract_version != schema_version
    ):
        raise PlcDispatchStateConflict("dispatch_migration_required", authoritative)
    unknown = set(authoritative) - PLC_DISPATCH_KNOWN_FIELDS
    if unknown:
        raise PlcDispatchStateConflict(
            f"corrupt_persisted_dispatch:unknown_field:{sorted(unknown)[0]}", authoritative
        )
    response_only = set(authoritative) - PLC_PERSISTED_DISPATCH_FIELDS
    if response_only:
        raise PlcDispatchStateConflict(
            f"corrupt_persisted_dispatch:response_only_field:{sorted(response_only)[0]}",
            authoritative,
        )
    required = {
        "dispatch_id", "source", "request_id", "passed", "detection_identity",
        "control_generation", "config_snapshot", "protocol", "checksum_mode",
        "planned_targets", "planned_frames", "attempted", "status", "history",
        "worker_done", "state_version",
    }
    if not required.issubset(authoritative):
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:required_field_missing", authoritative)
    if type(authoritative.get("passed")) is not bool:
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:passed_invalid", authoritative)
    if (
        not isinstance(authoritative.get("dispatch_id"), str)
        or not isinstance(authoritative.get("source"), str)
        or not authoritative.get("source")
        or authoritative.get("source") != authoritative.get("source").strip()
        or not isinstance(authoritative.get("request_id"), str)
        or not isinstance(authoritative.get("detection_identity"), str)
        or not authoritative.get("detection_identity")
    ):
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:identity_type_invalid", authoritative)
    if authoritative.get("enabled") is not True:
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:enabled_binding_invalid", authoritative)
    if type(authoritative.get("control_generation")) is not int or int(authoritative["control_generation"]) < 0:
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:generation_invalid", authoritative)
    if type(authoritative.get("state_version")) is not int or int(authoritative["state_version"]) < 1:
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:state_version_invalid", authoritative)
    if "dispatch_deadline_at_ms" in authoritative and (
        type(authoritative.get("dispatch_deadline_at_ms")) is not int
        or int(authoritative["dispatch_deadline_at_ms"]) < int(authoritative.get("created_at") or 0) * 1000
    ):
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:dispatch_deadline_invalid", authoritative)
    try:
        snapshot = (
            normalize_plc_v1_snapshot(authoritative.get("config_snapshot"))
            if contract_version == 1
            else normalize_plc_config(authoritative.get("config_snapshot"))
        )
    except PlcConfigError as exc:
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:snapshot_invalid", authoritative) from exc
    if not snapshot["enabled"] or _plc_canonical(snapshot) != _plc_canonical(authoritative["config_snapshot"]):
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:snapshot_not_canonical", authoritative)
    expected_targets, expected_frames = (
        build_plc_v1_dispatch_plan(snapshot, bool(authoritative["passed"]))
        if contract_version == 1
        else build_plc_dispatch_plan(snapshot, bool(authoritative["passed"]))
    )
    if (
        authoritative.get("protocol") != snapshot["protocol"]
        or authoritative.get("checksum_mode") != snapshot["checksum_mode"]
        or _plc_canonical(authoritative.get("planned_targets")) != _plc_canonical(expected_targets)
        or _plc_canonical(authoritative.get("planned_frames")) != _plc_canonical(expected_frames)
    ):
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:plan_binding_invalid", authoritative)
    material = json.dumps(
        {
            "source": str(authoritative.get("source") or ""),
            "request_id": str(authoritative.get("request_id") or ""),
            "fingerprint": str(authoritative.get("detection_identity") or ""),
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    expected_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    if not authoritative.get("detection_identity") or authoritative.get("dispatch_id") != expected_id:
        raise PlcDispatchStateConflict("corrupt_persisted_dispatch:identity_binding_invalid", authoritative)

    events = authoritative.get("events")
    if not isinstance(events, list):
        raise PlcDispatchStateConflict("dispatch_migration_required", authoritative)
    try:
        projected = project_plc_dispatch_events(authoritative, copy.deepcopy(events))
    except PlcDispatchStateConflict as exc:
        if exc.reason.startswith("corrupt_persisted_dispatch:"):
            raise PlcDispatchStateConflict(exc.reason, authoritative) from exc
        raise
    if int(authoritative["state_version"]) != len(events):
        raise PlcDispatchStateConflict(
            "corrupt_persisted_dispatch:state_version_event_count_mismatch", authoritative
        )
    if authoritative.get("duplicate") is not False:
        raise PlcDispatchStateConflict(
            "corrupt_persisted_dispatch:persisted_duplicate_flag_invalid", authoritative
        )
    if authoritative.get("created_at") != events[0].get("at"):
        raise PlcDispatchStateConflict(
            "corrupt_persisted_dispatch:created_at_event_mismatch", authoritative
        )
    for field in sorted(PLC_REDUCER_DERIVED_FIELDS):
        if (field in authoritative) != (field in projected) or _plc_canonical(
            authoritative.get(field)
        ) != _plc_canonical(projected.get(field)):
            raise PlcDispatchStateConflict(
                f"corrupt_persisted_dispatch:projection_mismatch:{field}", authoritative
            )
    return authoritative
