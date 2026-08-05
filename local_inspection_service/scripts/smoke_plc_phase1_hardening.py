#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import copy
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_plc_hardening_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)
os.environ["VANTALINE_YOLO_PREWARM"] = "0"
os.environ["INSPECTION_WORKER_WATCHER"] = "0"
os.environ["LOCAL_INSPECTION_AUTO_RESUME_WORKER"] = "0"

from local_inspection_service.plc_fx_ascii import (  # noqa: E402
    ACK,
    NAK,
    DEFAULT_PLC_CONFIG,
    PlcAttemptTerminalResult,
    PlcTerminalResultCode,
    PlcTransportPhase,
    PlcTransportError,
    build_d206_frame,
    build_y04_frame,
    clear_memory_dispatches,
    dispatch_detection_result,
    normalize_config,
    plc_terminal_result_is_retryable,
)
from local_inspection_service.scripts import testclient_threadpool_shim  # noqa: E402

testclient_threadpool_shim.install()
TestClient = testclient_threadpool_shim.SmokeASGIClient

from local_inspection_service import server  # noqa: E402


def enabled_config(**overrides: Any) -> dict[str, Any]:
    return normalize_config({**DEFAULT_PLC_CONFIG, "enabled": True, "serial_port": "COM3", **overrides})


class ScriptedTransport:
    def __init__(
        self,
        writes: list[bytes],
        *,
        response: bytes = ACK,
        write_count: int | None = None,
        write_returns_none: bool = False,
        write_error: BaseException | None = None,
        flush_error: BaseException | None = None,
        read_error: BaseException | None = None,
        write_started: threading.Event | None = None,
        write_release: threading.Event | None = None,
        read_started: threading.Event | None = None,
        read_release: threading.Event | None = None,
    ) -> None:
        self.writes = writes
        self.response = response
        self.write_count = write_count
        self.write_returns_none = write_returns_none
        self.write_error = write_error
        self.flush_error = flush_error
        self.read_error = read_error
        self.write_started = write_started
        self.write_release = write_release
        self.read_started = read_started
        self.read_release = read_release

    def write(self, frame: bytes) -> int:
        self.writes.append(frame)
        if self.write_started:
            self.write_started.set()
        if self.write_release:
            assert self.write_release.wait(5), "write barrier timed out"
        if self.write_error:
            raise self.write_error
        if self.write_returns_none:
            return None  # type: ignore[return-value]
        return len(frame) if self.write_count is None else self.write_count

    def flush(self) -> None:
        if self.flush_error:
            raise self.flush_error

    def read(self, size: int) -> bytes:
        assert size == 1
        if self.read_started:
            self.read_started.set()
        if self.read_release:
            assert self.read_release.wait(5), "read barrier timed out"
        if self.read_error:
            raise self.read_error
        return self.response

    def close(self) -> None:
        return None


class ScriptedFactory:
    def __init__(self, builders: list[Callable[[list[bytes]], ScriptedTransport]]) -> None:
        self.builders = list(builders)
        self.writes: list[bytes] = []
        self.opens = 0

    def __call__(self, _config: dict[str, Any]) -> ScriptedTransport:
        self.opens += 1
        builder = self.builders.pop(0) if self.builders else (lambda writes: ScriptedTransport(writes))
        return builder(self.writes)


class SharedPgBackend:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.values: dict[str, Any] = {}


class FakeIndependentPgRepository:
    kind = "postgres"

    def __init__(self, backend: SharedPgBackend) -> None:
        self.backend = backend

    def fetch_all(self, table_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        if table_name == "accessories":
            return []
        assert table_name == "app_config"
        with self.backend.lock:
            rows = [
                {
                    "config_key": key,
                    "config_value_json": value,
                    "source_file": "config.json",
                    "updated_at": 1,
                }
                for key, value in sorted(self.backend.values.items())
            ]
        return rows[:limit] if limit else rows

    def mutate_app_config_namespace(
        self,
        protected_keys: tuple[str, ...],
        mutator: Callable[[dict[str, Any]], None],
        *,
        updated_at: int,
    ) -> dict[str, Any]:
        del updated_at
        with self.backend.lock:
            values = {key: self.backend.values[key] for key in protected_keys if key in self.backend.values}
            mutator(values)
            for key in protected_keys:
                if key in values:
                    self.backend.values[key] = values[key]
            return dict(values)

    def replace_app_config_preserving_keys(
        self,
        rows: list[dict[str, Any]],
        protected_keys: tuple[str, ...],
        *,
        additional_tables: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        del additional_tables
        with self.backend.lock:
            preserved = {key: self.backend.values[key] for key in protected_keys if key in self.backend.values}
            self.backend.values = {
                str(row["config_key"]): row["config_value_json"]
                for row in rows
                if str(row.get("config_key") or "") not in protected_keys
            }
            self.backend.values.update(preserved)


def save_enabled(*, generation: int | None = None, **overrides: Any) -> None:
    def mutate(config: dict[str, Any]) -> None:
        config["plc"] = enabled_config(**overrides)
        if generation is not None:
            config[server.PLC_CONTROL_GENERATION_KEY] = generation

    server.mutate_app_config_atomically(mutate)


def disable_direct() -> None:
    def mutate(config: dict[str, Any]) -> None:
        current = config.get("plc") if isinstance(config.get("plc"), dict) else {}
        config["plc"] = normalize_config({**current, "enabled": False})
        config[server.PLC_CONTROL_GENERATION_KEY] = int(config.get(server.PLC_CONTROL_GENERATION_KEY) or 0) + 1

    server.mutate_app_config_atomically(mutate)


def audit_for(dispatch_id: str) -> list[dict[str, Any]]:
    return [item for item in server.plc_dispatch_audit_records() if item.get("dispatch_id") == dispatch_id]


def seed_dispatch_fixture(record: dict[str, Any]) -> dict[str, Any]:
    """Test-only state seeding for validator/recovery fixtures; never used by runtime code."""
    seeded = {**record, "state_version": int(record.get("state_version") or 1)}

    def mutate(config: dict[str, Any]) -> None:
        records = [
            item for item in server.plc_dispatch_audit_records(config)
            if item.get("dispatch_id") != seeded.get("dispatch_id")
        ]
        config["plc_dispatches"] = [*records, seeded]

    server.mutate_app_config_atomically(mutate)
    return dict(seeded)


def apply_dispatch_fixture(
    candidate: dict[str, Any],
    *,
    expected_version: int,
    transition_kind: server.PlcDispatchTransitionKind,
) -> dict[str, Any]:
    """Test-only validator fixture for legacy/corrupt-state lattice cases."""
    persisted: dict[str, Any] = {}

    def mutate(config: dict[str, Any]) -> None:
        nonlocal persisted
        records = server.plc_dispatch_audit_records(config)
        existing = next(
            item for item in records if item.get("dispatch_id") == candidate.get("dispatch_id")
        )
        assert int(existing.get("state_version") or 0) == expected_version
        server.validate_plc_dispatch_transition(
            existing,
            candidate,
            transition_kind=transition_kind,
        )
        persisted = {**candidate, "state_version": expected_version + 1}
        config["plc_dispatches"] = [
            persisted if item.get("dispatch_id") == candidate.get("dispatch_id") else item
            for item in records
        ]

    server.mutate_app_config_atomically(mutate)
    return persisted


def wait_worker_done(dispatch_id: str) -> dict[str, Any]:
    deadline = time.time() + 5
    while time.time() < deadline:
        records = audit_for(dispatch_id)
        if records and records[0].get("worker_done"):
            return records[0]
        time.sleep(0.02)
    raise AssertionError(f"worker did not finish for {dispatch_id}")


def test_partial_write_and_full_write_flush_failure() -> None:
    clear_memory_dispatches()
    partial = ScriptedFactory([lambda writes: ScriptedTransport(writes, write_count=3)])
    result = dispatch_detection_result(
        dispatch_id="partial-write",
        source="image",
        request_id="partial-write",
        passed=True,
        config=enabled_config(retries=2),
        transport_factory=partial,
    )
    assert result["attempted"] is True
    assert result["physical_status"] == "partial_write"
    assert result["outcome"] == "outcome_uncertain"
    assert result["error_code"] == "short_write"
    assert partial.opens == 1
    assert "sent" not in [item["status"] for item in result["history"]]

    clear_memory_dispatches()
    flush = ScriptedFactory(
        [lambda writes: ScriptedTransport(writes, flush_error=OSError("injected flush failure"))]
    )
    result = dispatch_detection_result(
        dispatch_id="flush-failure",
        source="image",
        request_id="flush-failure",
        passed=True,
        config=enabled_config(retries=2),
        transport_factory=flush,
    )
    assert result["attempted"] is True
    assert result["physical_status"] == "full_frame_written"
    assert result["outcome"] == "outcome_uncertain"
    assert result["error_code"] == "flush_failed"
    assert flush.opens == 1
    assert "sent" in [item["status"] for item in result["history"]]


def test_multiframe_partial_success_preserves_receipts() -> None:
    for suffix, final_response, expected_error in (
        ("nak", NAK, "nak"),
        ("timeout", b"", "timeout"),
    ):
        clear_memory_dispatches()
        factory = ScriptedFactory(
            [
                lambda writes: ScriptedTransport(writes, response=ACK),
                lambda writes, response=final_response: ScriptedTransport(writes, response=response),
            ]
        )
        result = dispatch_detection_result(
            dispatch_id=f"partial-success-{suffix}",
            source="video",
            request_id=f"partial-success-{suffix}",
            passed=False,
            config=enabled_config(write_y04=True, retries=0),
            transport_factory=factory,
        )
        assert result["status"] == "failed"
        assert result["attempted"] is True
        assert result["outcome"] == "partial_failure"
        assert result["acknowledged_targets"] == ["D206"]
        assert result["failed_target"] == "Y04"
        assert result["frames"][0]["target"] == "D206"
        assert result["failed_operation"]["target"] == "Y04"
        assert result["error_code"] == expected_error
        assert factory.writes == [build_d206_frame("119C", False), build_y04_frame("0108", False)]


def test_server_terminal_result_contract_matrix() -> None:
    observed_codes: set[str] = set()
    scenarios: list[tuple[str, Callable[[list[bytes]], ScriptedTransport], str, str, str, bool]] = [
        ("ack", lambda writes: ScriptedTransport(writes, response=ACK), "acknowledged", "response", "ack_byte", True),
        ("nak", lambda writes: ScriptedTransport(writes, response=NAK), "nak", "response", "nak_byte", False),
        ("empty", lambda writes: ScriptedTransport(writes, response=b""), "timeout", "read", "empty_read", False),
        (
            "read-timeout",
            lambda writes: ScriptedTransport(writes, read_error=TimeoutError("read timeout")),
            "timeout",
            "read",
            "read_timeout_exception",
            False,
        ),
        (
            "short-response",
            lambda writes: ScriptedTransport(writes, response=b"X"),
            "short_response",
            "response",
            "non_ack_control_byte",
            False,
        ),
        (
            "multi-response",
            lambda writes: ScriptedTransport(writes, response=b"XX"),
            "unexpected_response",
            "response",
            "multi_byte_response",
            False,
        ),
        (
            "zero-write",
            lambda writes: ScriptedTransport(writes, write_count=0),
            "short_write",
            "write",
            "write_length_mismatch",
            False,
        ),
        (
            "partial-write",
            lambda writes: ScriptedTransport(writes, write_count=3),
            "short_write",
            "write",
            "write_length_mismatch",
            False,
        ),
        (
            "unknown-write",
            lambda writes: ScriptedTransport(writes, write_returns_none=True),
            "write_result_unknown",
            "write",
            "write_returned_none",
            False,
        ),
        (
            "write-error",
            lambda writes: ScriptedTransport(writes, write_error=OSError("write failed")),
            "serial_io_failed",
            "write",
            "write_exception",
            False,
        ),
        (
            "flush-error",
            lambda writes: ScriptedTransport(writes, flush_error=OSError("flush failed")),
            "flush_failed",
            "flush",
            "flush_exception",
            False,
        ),
    ]
    for suffix, builder, expected_code, expected_phase, expected_diagnostic, acknowledged in scenarios:
        save_enabled(retries=0)
        factory = ScriptedFactory([builder])
        server._plc_transport_factory = factory
        try:
            sync = server.dispatch_plc_for_detection(
                {"request_id": f"terminal-{suffix}", "passed": True},
                source="image",
                fingerprint=f"terminal-{suffix}",
            )["plc_sync"]
        finally:
            server._plc_transport_factory = None
        records = audit_for(sync["dispatch_id"])
        assert len(records) == 1
        authoritative = records[0]
        assert authoritative == sync
        assert server.verify_persisted_plc_dispatch(authoritative) == authoritative
        assert authoritative.get("audit_status") != "persist_failed", authoritative
        assert authoritative["worker_done"] is True
        assert authoritative["state_version"] >= 5
        operation = authoritative["operations"][-1]
        observed_codes.add(operation["result_code"])
        assert operation["finished_at"] >= operation["started_at"]
        assert operation["result_code"] == expected_code
        assert operation["result_phase"] == expected_phase
        assert operation["diagnostic_source"] == expected_diagnostic
        assert authoritative["status"] == ("acknowledged" if acknowledged else "failed")
        if acknowledged:
            assert authoritative.get("error_code", "") == ""
        else:
            assert authoritative["error_code"] == expected_code
        if expected_code in {"acknowledged", "nak", "timeout", "short_response", "unexpected_response", "flush_failed"}:
            assert operation["bytes_written"] == operation["frame_bytes"]
        if operation["physical_status"] == "write_call_started":
            assert operation["write_count_known"] is False
            assert operation["reported_write_count"] is None
            assert authoritative["attempted"] is True
        elif operation["physical_status"] != "not_attempted":
            assert operation["write_count_known"] is True
            assert operation["reported_write_count"] == operation["bytes_written"]

    for suffix, invalid_result, expected_diagnostic in (
        ("bool", True, "write_returned_invalid_type"),
        ("negative", -1, "write_returned_out_of_range"),
        ("oversize", 10_000, "write_returned_out_of_range"),
        ("string", "13", "write_returned_invalid_type"),
    ):
        save_enabled(retries=2, write_y04=True)
        invalid_factory = ScriptedFactory(
            [lambda writes, value=invalid_result: ScriptedTransport(writes, write_count=value)]
        )
        server._plc_transport_factory = invalid_factory
        try:
            invalid_sync = server.dispatch_plc_for_detection(
                {"request_id": f"terminal-invalid-{suffix}", "passed": True},
                source="image",
                fingerprint=f"terminal-invalid-{suffix}",
            )["plc_sync"]
        finally:
            server._plc_transport_factory = None
        invalid_authority = audit_for(invalid_sync["dispatch_id"])[0]
        assert invalid_authority == invalid_sync
        assert invalid_authority.get("audit_status") != "persist_failed"
        assert invalid_authority["status"] == "failed"
        assert invalid_authority["attempted"] is True
        assert invalid_authority["error_code"] == "write_result_unknown"
        invalid_operation = invalid_authority["operations"][-1]
        assert invalid_operation["diagnostic_source"] == expected_diagnostic
        assert invalid_operation["write_count_known"] is False
        assert invalid_operation["reported_write_count"] is None
        assert invalid_operation["physical_status"] == "write_call_started"
        assert invalid_operation["outcome"] == "write_outcome_uncertain"
        assert invalid_factory.opens == 1
        assert invalid_factory.writes == [build_d206_frame("119C", True)]

    save_enabled(retries=0)
    server._plc_transport_factory = lambda _config: (_ for _ in ()).throw(OSError("open failed"))
    try:
        opened = server.dispatch_plc_for_detection(
            {"request_id": "terminal-open-error", "passed": True},
            source="image",
            fingerprint="terminal-open-error",
        )["plc_sync"]
    finally:
        server._plc_transport_factory = None
    operation = opened["operations"][-1]
    observed_codes.add(operation["result_code"])
    assert operation["result_code"] == PlcTerminalResultCode.SERIAL_OPEN_FAILED.value
    assert operation["result_phase"] == PlcTransportPhase.OPEN.value
    assert operation["diagnostic_source"] == "transport_factory_exception"
    assert operation["finished_at"] >= operation["started_at"]
    assert opened["error_code"] == PlcTerminalResultCode.SERIAL_OPEN_FAILED.value
    assert opened.get("audit_status") != "persist_failed"
    assert server.verify_persisted_plc_dispatch(opened) == opened

    save_enabled(retries=0)
    dependency_error = PlcTransportError(
        PlcTerminalResultCode.SERIAL_DEPENDENCY_MISSING,
        "pyserial unavailable",
        diagnostic_source="pyserial_import",
        phase=PlcTransportPhase.OPEN,
    )
    server._plc_transport_factory = lambda _config: (_ for _ in ()).throw(dependency_error)
    try:
        dependency = server.dispatch_plc_for_detection(
            {"request_id": "terminal-dependency-error", "passed": True},
            source="image",
            fingerprint="terminal-dependency-error",
        )["plc_sync"]
    finally:
        server._plc_transport_factory = None
    operation = dependency["operations"][-1]
    observed_codes.add(operation["result_code"])
    assert operation["result_code"] == PlcTerminalResultCode.SERIAL_DEPENDENCY_MISSING.value
    assert operation["result_phase"] == PlcTransportPhase.OPEN.value
    assert operation["diagnostic_source"] == "pyserial_import"
    assert dependency.get("audit_status") != "persist_failed"
    assert server.verify_persisted_plc_dispatch(dependency) == dependency

    save_enabled(retries=0)
    unknown_error = PlcTransportError(
        "evil_terminal_code", "injected unknown transport result", diagnostic_source="evil_source"
    )
    unknown_factory = ScriptedFactory(
        [lambda writes: ScriptedTransport(writes, read_error=unknown_error)]
    )
    server._plc_transport_factory = unknown_factory
    try:
        unknown = server.dispatch_plc_for_detection(
            {"request_id": "terminal-unknown-error", "passed": True},
            source="image",
            fingerprint="terminal-unknown-error",
        )["plc_sync"]
    finally:
        server._plc_transport_factory = None
    operation = unknown["operations"][-1]
    observed_codes.add(operation["result_code"])
    assert operation["result_code"] == PlcTerminalResultCode.INTERNAL_TRANSITION_ERROR.value
    assert operation["result_phase"] == PlcTransportPhase.INTERNAL.value
    assert operation["diagnostic_source"] == "unknown_client_terminal_code"
    assert operation["bytes_written"] == operation["frame_bytes"]
    assert unknown["error_code"] == PlcTerminalResultCode.INTERNAL_TRANSITION_ERROR.value
    assert unknown.get("audit_status") != "persist_failed"
    assert server.verify_persisted_plc_dispatch(unknown) == unknown
    assert observed_codes == {item.value for item in PlcTerminalResultCode}


def test_shared_retry_policy_actual_server_matrix() -> None:
    expected_retryable = {
        (PlcTerminalResultCode.NAK, PlcTransportPhase.RESPONSE),
        (PlcTerminalResultCode.TIMEOUT, PlcTransportPhase.READ),
        (PlcTerminalResultCode.SHORT_RESPONSE, PlcTransportPhase.RESPONSE),
        (PlcTerminalResultCode.UNEXPECTED_RESPONSE, PlcTransportPhase.RESPONSE),
    }
    for code in PlcTerminalResultCode:
        for phase in PlcTransportPhase:
            assert plc_terminal_result_is_retryable(code, phase) is (
                (code, phase) in expected_retryable
            )
    assert plc_terminal_result_is_retryable("evil_terminal_code", "read") is False

    unknown_error = PlcTransportError(
        "evil_terminal_code", "injected unknown transport result", diagnostic_source="evil_source"
    )
    scenarios: list[
        tuple[str, Callable[[list[bytes]], ScriptedTransport], str, str, bool]
    ] = [
        ("ack", lambda writes: ScriptedTransport(writes, response=ACK), "acknowledged", "response", False),
        ("nak", lambda writes: ScriptedTransport(writes, response=NAK), "nak", "response", True),
        ("read-timeout", lambda writes: ScriptedTransport(writes, response=b""), "timeout", "read", True),
        ("short-response", lambda writes: ScriptedTransport(writes, response=b"X"), "short_response", "response", True),
        ("unexpected-response", lambda writes: ScriptedTransport(writes, response=b"XX"), "unexpected_response", "response", True),
        ("write-timeout", lambda writes: ScriptedTransport(writes, write_error=TimeoutError("write timeout")), "timeout", "write", False),
        ("flush-timeout", lambda writes: ScriptedTransport(writes, flush_error=TimeoutError("flush timeout")), "timeout", "flush", False),
        ("short-write", lambda writes: ScriptedTransport(writes, write_count=3), "short_write", "write", False),
        ("unknown-write", lambda writes: ScriptedTransport(writes, write_returns_none=True), "write_result_unknown", "write", False),
        ("write-io", lambda writes: ScriptedTransport(writes, write_error=OSError("write failed")), "serial_io_failed", "write", False),
        ("read-io", lambda writes: ScriptedTransport(writes, read_error=OSError("read failed")), "serial_io_failed", "read", False),
        ("flush-io", lambda writes: ScriptedTransport(writes, flush_error=OSError("flush failed")), "flush_failed", "flush", False),
        ("internal-write", lambda writes: ScriptedTransport(writes, write_error=unknown_error), "internal_transition_error", "internal", False),
        ("internal-read", lambda writes: ScriptedTransport(writes, read_error=unknown_error), "internal_transition_error", "internal", False),
    ]
    for suffix, builder, expected_code, expected_phase, retryable in scenarios:
        save_enabled(retries=2, write_y04=suffix != "ack")
        factory = ScriptedFactory([builder, builder, builder])
        server._plc_transport_factory = factory
        try:
            sync = server.dispatch_plc_for_detection(
                {"request_id": f"retry-policy-{suffix}", "passed": True},
                source="image",
                fingerprint=f"retry-policy-{suffix}",
            )["plc_sync"]
        finally:
            server._plc_transport_factory = None
        authority = audit_for(sync["dispatch_id"])[0]
        assert authority == sync
        assert authority.get("audit_status") != "persist_failed"
        assert server.verify_persisted_plc_dispatch(authority) == authority
        expected_operations = 3 if retryable else 1
        assert len(authority["operations"]) == expected_operations, (suffix, authority)
        assert factory.opens == expected_operations
        assert len(factory.writes) == expected_operations
        assert {item["target"] for item in authority["operations"]} == {"D206"}
        operation = authority["operations"][-1]
        assert operation["result_code"] == expected_code
        assert operation["result_phase"] == expected_phase
        internal_projection = {
            "internal-write": ("write_call_started", "write_outcome_uncertain", True),
            "internal-read": ("full_frame_written", "outcome_uncertain", True),
        }.get(suffix)
        if internal_projection:
            expected_physical, expected_outcome, expected_attempted = internal_projection
            assert operation["physical_status"] == expected_physical
            assert operation["outcome"] == expected_outcome
            assert authority["physical_status"] == expected_physical
            assert authority["outcome"] == expected_outcome
            assert authority["failed_operation"]["outcome"] == expected_outcome
            assert authority["attempted"] is expected_attempted

    for suffix, raised, expected_code, expected_diagnostic in (
        ("open", OSError("open failed"), "serial_open_failed", "transport_factory_exception"),
        (
            "dependency",
            PlcTransportError(
                PlcTerminalResultCode.SERIAL_DEPENDENCY_MISSING,
                "pyserial unavailable",
                diagnostic_source="pyserial_import",
                phase=PlcTransportPhase.OPEN,
            ),
            "serial_dependency_missing",
            "pyserial_import",
        ),
        (
            "internal-open",
            PlcTransportError(
                "evil_terminal_code", "injected unknown open result", diagnostic_source="evil_source"
            ),
            "internal_transition_error",
            "unknown_client_terminal_code",
        ),
    ):
        save_enabled(retries=2, write_y04=True)
        opens = 0

        def failing_open(_config: dict[str, Any], error: BaseException = raised) -> Any:
            nonlocal opens
            opens += 1
            raise error

        server._plc_transport_factory = failing_open
        try:
            sync = server.dispatch_plc_for_detection(
                {"request_id": f"retry-policy-{suffix}", "passed": True},
                source="image",
                fingerprint=f"retry-policy-{suffix}",
            )["plc_sync"]
        finally:
            server._plc_transport_factory = None
        authority = audit_for(sync["dispatch_id"])[0]
        assert authority == sync and opens == 1
        assert len(authority["operations"]) == 1
        operation = authority["operations"][0]
        assert operation["result_code"] == expected_code
        assert operation["diagnostic_source"] == expected_diagnostic
        assert authority["attempted"] is False
        if suffix == "internal-open":
            assert operation["physical_status"] == "not_attempted"
            assert operation["outcome"] == "not_attempted"
            assert authority["physical_status"] == "not_attempted"
            assert authority["outcome"] == "not_attempted"
            assert authority["failed_operation"]["outcome"] == "not_attempted"
        assert server.verify_persisted_plc_dispatch(authority) == authority


def test_atomic_config_audit_read_modify_write() -> None:
    save_enabled(retries=0)
    generic = server.load_config()
    generic["unrelated_marker"] = "preserved"
    server.save_app_config(generic)
    original_records = server.plc_dispatch_audit_records
    audit_paused = threading.Event()
    audit_release = threading.Event()

    def paused_records(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        records = original_records(config)
        if config is not None and not audit_paused.is_set():
            audit_paused.set()
            assert audit_release.wait(5)
        return records

    server.plc_dispatch_audit_records = paused_records
    audit_thread = threading.Thread(
        target=seed_dispatch_fixture,
        args=({"dispatch_id": "atomic-audit-first", "status": "queued"},),
    )
    audit_thread.start()
    assert audit_paused.wait(2)
    disable_thread = threading.Thread(target=disable_direct)
    disable_thread.start()
    time.sleep(0.05)
    assert disable_thread.is_alive(), "disable should wait for the atomic audit mutation"
    audit_release.set()
    audit_thread.join(5)
    disable_thread.join(5)
    server.plc_dispatch_audit_records = original_records
    final = server.load_config()
    assert final["plc"]["enabled"] is False
    assert any(item.get("dispatch_id") == "atomic-audit-first" for item in final["plc_dispatches"])

    config_paused = threading.Event()
    config_release = threading.Event()

    def slow_config_mutate(config: dict[str, Any]) -> None:
        current = config.get("plc") if isinstance(config.get("plc"), dict) else {}
        config["plc"] = normalize_config({**current, "enabled": True, "serial_port": "COM3", "retries": 2})
        config_paused.set()
        assert config_release.wait(5)

    config_thread = threading.Thread(target=server.mutate_app_config_atomically, args=(slow_config_mutate,))
    config_thread.start()
    assert config_paused.wait(2)
    audit_thread = threading.Thread(
        target=seed_dispatch_fixture,
        args=({"dispatch_id": "atomic-config-first", "status": "queued"},),
    )
    audit_thread.start()
    time.sleep(0.05)
    assert audit_thread.is_alive(), "audit should wait for the atomic config mutation"
    config_release.set()
    config_thread.join(5)
    audit_thread.join(5)
    final = server.load_config()
    assert final["plc"]["retries"] == 2
    assert final["unrelated_marker"] == "preserved"
    assert any(item.get("dispatch_id") == "atomic-config-first" for item in final["plc_dispatches"])

    disable_direct()
    opens = 0

    def forbidden(_config: dict[str, Any]) -> Any:
        nonlocal opens
        opens += 1
        raise AssertionError("disabled dispatch opened transport")

    server._plc_transport_factory = forbidden
    try:
        result = server.dispatch_plc_for_detection(
            {"request_id": "after-atomic-disable", "passed": True},
            source="image",
            fingerprint="after-atomic-disable",
        )
    finally:
        server._plc_transport_factory = None
    assert result["plc_sync"]["status"] == "disabled"
    assert opens == 0


def test_protected_namespace_rejects_stale_generic_saves_json_and_pg() -> None:
    save_enabled(retries=0)
    seed_dispatch_fixture({"dispatch_id": "namespace-audit", "status": "queued"})
    stale = server.load_config()
    disable_direct()
    disabled = server.load_config()
    disabled_generation = disabled[server.PLC_CONTROL_GENERATION_KEY]
    stale["stream"] = {"enabled": True, "source": "camera", "url": ""}
    server.save_app_config(stale)
    final = server.load_config()
    assert final["plc"]["enabled"] is False
    assert final[server.PLC_CONTROL_GENERATION_KEY] == disabled_generation
    assert any(item.get("dispatch_id") == "namespace-audit" for item in final["plc_dispatches"])

    stale_disabled = server.load_config()
    save_enabled(retries=2)
    enabled = server.load_config()
    stale_disabled["video"] = {**stale_disabled["video"], "max_frames": 3}
    server.save_config(stale_disabled)
    final = server.load_config()
    assert final["plc"] == enabled["plc"]
    assert final[server.PLC_CONTROL_GENERATION_KEY] == enabled[server.PLC_CONTROL_GENERATION_KEY]

    backend = SharedPgBackend()
    repo_a = FakeIndependentPgRepository(backend)
    repo_b = FakeIndependentPgRepository(backend)
    original_repo = server.runtime_postgres_repository_or_none
    original_coordination = server.plc_pg_coordination_available
    current_repo = repo_a
    server.runtime_postgres_repository_or_none = lambda: current_repo
    try:
        save_enabled(retries=0)
        capability = server.plc_config_response()
        assert capability["effective_enabled"] is False
        assert capability["validation_errors"][0]["code"] == "plc_pg_coordination_unavailable"
        pg_opens = 0

        def pg_forbidden(_config: dict[str, Any]) -> Any:
            nonlocal pg_opens
            pg_opens += 1
            raise AssertionError("PG capability-blocked dispatch opened transport")

        server._plc_transport_factory = pg_forbidden
        blocked = server.dispatch_plc_for_detection(
            {"request_id": "pg-capability-block", "passed": True},
            source="image",
            fingerprint="pg-capability-block",
        )["plc_sync"]
        server._plc_transport_factory = None
        assert blocked["error_code"] == "plc_pg_coordination_unavailable"
        assert blocked["attempted"] is False
        assert pg_opens == 0
        assert not audit_for(blocked["dispatch_id"])
        before_count = len(server.plc_dispatch_audit_records())
        try:
            server.create_plc_dispatch(
                source="image", request_id="pg-create-no-coordination", passed=True,
                fingerprint="pg-create-no-coordination",
            )
        except server.PlcDispatchStateConflict as exc:
            assert exc.reason == "plc_pg_coordination_unavailable"
        else:
            raise AssertionError("PG create succeeded without coordination capability")
        assert len(server.plc_dispatch_audit_records()) == before_count
        for suffix, namespace, expected_reason in (
            ("absent", server.PLC_CONFIG_ABSENT, "create_plc_namespace_absent"),
            ("null", None, "create_plc_namespace_invalid"),
            ("invalid", {**enabled_config(retries=0), "d206_address": 4508}, "create_plc_namespace_invalid"),
            ("disabled", dict(DEFAULT_PLC_CONFIG), "create_plc_disabled"),
        ):
            with backend.lock:
                if namespace is server.PLC_CONFIG_ABSENT:
                    backend.values.pop("plc", None)
                else:
                    backend.values["plc"] = namespace
            count_before = len(server.plc_dispatch_audit_records())
            try:
                server.create_plc_dispatch(
                    source="video", request_id=f"pg-create-{suffix}", passed=False,
                    fingerprint=f"pg-create-{suffix}",
                )
            except server.PlcDispatchStateConflict as exc:
                assert exc.reason == expected_reason
            else:
                raise AssertionError(f"PG create accepted {suffix} authoritative namespace")
            assert len(server.plc_dispatch_audit_records()) == count_before
        save_enabled(retries=0)
        try:
            server.update_plc_config(server.PlcConfigRequest(**enabled_config(retries=0)))
        except server.HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail == "plc_pg_coordination_unavailable"
        else:
            raise AssertionError("PG PLC enable did not fail closed")

        server.mutate_app_config_atomically(
            lambda config: config.__setitem__("plc", {**enabled_config(retries=0), "d206_address": 4508})
        )
        polluted = server.plc_config_response()
        assert polluted["effective_enabled"] is False
        assert polluted["validation_errors"][0]["code"] == "invalid_plc_config"
        server.mutate_app_config_atomically(lambda config: config.__setitem__("plc", None))
        malformed = server.plc_config_response()
        assert malformed["effective_enabled"] is False
        assert malformed["validation_errors"][0]["code"] == "invalid_plc_config"
        repaired_pg = server.update_plc_config(
            server.PlcConfigRequest(**{**DEFAULT_PLC_CONFIG, "enabled": False, "serial_port": ""})
        )
        assert repaired_pg["validation_errors"] == []
        save_enabled(retries=0)

        seed_dispatch_fixture({"dispatch_id": "pg-namespace-audit", "status": "queued"})
        current_repo = repo_b
        stale = server.load_config()
        current_repo = repo_a
        disable_direct()
        disabled = server.load_config()
        current_repo = repo_b
        stale["stream"] = {"enabled": True, "source": "camera", "url": ""}
        server.save_app_config(stale)
        final = server.load_config()
        assert final["plc"]["enabled"] is False
        assert final[server.PLC_CONTROL_GENERATION_KEY] == disabled[server.PLC_CONTROL_GENERATION_KEY]
        assert any(item.get("dispatch_id") == "pg-namespace-audit" for item in final["plc_dispatches"])

        current_repo = repo_a
        seed_dispatch_fixture({"dispatch_id": "pg-cas", "status": "queued"})
        current_repo = repo_b
        try:
            server.persist_plc_dispatch_record(
                {"dispatch_id": "pg-cas", "status": "attempting"}, expected_version=0
            )
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("independent PG repository stale CAS write was accepted")
        record = next(item for item in server.plc_dispatch_audit_records() if item.get("dispatch_id") == "pg-cas")
        assert record["state_version"] == 1
        assert record["status"] == "queued"
        pg_typed_seed = seed_dispatch_fixture(
            {
                "dispatch_id": "pg-typed-bypass",
                "source": "image",
                "request_id": "pg-typed-bypass",
                "passed": True,
                "status": "attempting",
                "attempted": False,
                "worker_done": False,
                "control_generation": 1,
                "config_snapshot": enabled_config(retries=1),
                "planned_targets": ["D206"],
                "planned_frames": [{"target": "D206", "frame_hex": "AA"}],
            },
        )
        pg_valid_start = {
            "attempt_id": "pg-typed-bypass:D206:1",
            "target": "D206",
            "attempt": 1,
            "frame_hex": "AA",
            "frame_bytes": 1,
            "bytes_written": 0,
            "physical_status": "not_attempted",
            "outcome": "not_attempted",
            "started_at": 1,
        }
        pg_piggyback = {
            **pg_typed_seed,
            "status": "acknowledged",
            "operations": [pg_valid_start],
            "attempt_ids": [pg_valid_start["attempt_id"]],
            "acknowledged_targets": ["Y99"],
            "frames": [{"target": "Y99", "frame_hex": "DEADBEEF", "attempts": 77}],
            "bytes_written": 999,
            "attempts": 999,
            "target": "Y99",
        }
        for transition_kind in ["evil", *[item.value for item in server.PlcDispatchTransitionKind]]:
            try:
                server.persist_plc_dispatch_record(
                    dict(pg_piggyback),
                    expected_version=pg_typed_seed["state_version"],
                    transition_kind=transition_kind,
                )
            except server.PlcDispatchStateConflict as exc:
                assert exc.reason == "public_raw_transition_kind_not_allowed"
            else:
                raise AssertionError(f"PG public raw transition-kind bypass was accepted: {transition_kind}")
            authoritative = next(
                item
                for item in server.plc_dispatch_audit_records()
                if item.get("dispatch_id") == "pg-typed-bypass"
            )
            assert authoritative["state_version"] == pg_typed_seed["state_version"]
        try:
            server.persist_plc_dispatch_record(
                dict(pg_piggyback), expected_version=pg_typed_seed["state_version"]
            )
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("PG public whole-record projection bypass was accepted")
        authoritative = next(
            item
            for item in server.plc_dispatch_audit_records()
            if item.get("dispatch_id") == "pg-typed-bypass"
        )
        assert authoritative["state_version"] == pg_typed_seed["state_version"]

        server.plc_pg_coordination_available = lambda: True
        save_enabled(generation=9, retries=1)
        pg_created = server.create_plc_dispatch(
            source="image",
            request_id="strict-create-pg",
            passed=True,
            fingerprint="strict-create-pg",
            expected_generation=9,
        )
        pg_duplicate = server.create_plc_dispatch(
            source="image",
            request_id="strict-create-pg",
            passed=True,
            fingerprint="strict-create-pg",
            expected_generation=9,
        )
        assert pg_created["state_version"] == pg_duplicate["state_version"] == 1
        try:
            server.create_plc_dispatch(
                source="image",
                request_id="strict-create-pg",
                passed=False,
                fingerprint="strict-create-pg",
                expected_generation=9,
            )
        except server.PlcDispatchStateConflict as exc:
            assert exc.reason == "create_dispatch_identity_conflict"
        else:
            raise AssertionError("PG conflicting idempotent create was accepted")
        try:
            server.persist_plc_dispatch_record(
                {**pg_created, "status": "acknowledged", "state_version": 999}
            )
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("PG existing-ID no-version overwrite was accepted")
        pg_authoritative = next(
            item
            for item in server.plc_dispatch_audit_records()
            if item.get("dispatch_id") == pg_created["dispatch_id"]
        )
        assert pg_authoritative["state_version"] == 1 and pg_authoritative["status"] == "queued"
        forged_pg_id = "forged-create-pg"
        try:
            server.persist_plc_dispatch_record(
                {
                    "dispatch_id": forged_pg_id,
                    "status": "acknowledged",
                    "attempted": True,
                    "acknowledged_targets": ["Y99"],
                    "operations": [pg_valid_start],
                    "state_version": 999,
                    "unexpected": True,
                },
                expected_version=0,
            )
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("PG forged final-at-create was accepted")
        assert not any(item.get("dispatch_id") == forged_pg_id for item in server.plc_dispatch_audit_records())
        pg_race_results: list[dict[str, Any]] = []
        pg_race_failures: list[Exception] = []
        save_enabled(generation=10, retries=1)

        def create_pg_concurrently() -> None:
            try:
                pg_race_results.append(
                    server.create_plc_dispatch(
                        source="video",
                        request_id="strict-create-pg-race",
                        passed=False,
                        fingerprint="strict-create-pg-race",
                        expected_generation=10,
                    )
                )
            except Exception as exc:
                pg_race_failures.append(exc)

        pg_threads = [threading.Thread(target=create_pg_concurrently) for _ in range(2)]
        for thread in pg_threads:
            thread.start()
        for thread in pg_threads:
            thread.join(5)
        assert not pg_race_failures and len(pg_race_results) == 2
        assert {item["state_version"] for item in pg_race_results} == {1}
        assert sum(
            1
            for item in server.plc_dispatch_audit_records()
            if item.get("dispatch_id") == pg_race_results[0]["dispatch_id"]
        ) == 1
        current_repo = repo_a
        terminal = seed_dispatch_fixture(
            {
                "dispatch_id": "pg-terminal",
                "source": "image",
                "request_id": "pg-terminal",
                "passed": True,
                "status": "acknowledged",
                "attempted": True,
                "worker_done": True,
                "physical_status": "acknowledged",
                "acknowledged_targets": ["D206"],
            },
        )
        try:
            server.persist_plc_dispatch_record(
                {**terminal, "status": "queued", "attempted": False, "worker_done": False},
                expected_version=terminal["state_version"],
            )
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("PG terminal downgrade was accepted")
        assert next(item for item in server.plc_dispatch_audit_records() if item.get("dispatch_id") == "pg-terminal")["state_version"] == 1
        try:
            apply_dispatch_fixture(
                {**terminal, "passed": False},
                expected_version=terminal["state_version"],
                transition_kind=server.PlcDispatchTransitionKind.RECORD_UPDATE,
            )
        except server.PlcDispatchStateConflict as exc:
            assert exc.reason == "immutable_identity_conflict:passed"
        else:
            raise AssertionError("PG immutable verdict rewrite was accepted")
        try:
            apply_dispatch_fixture(
                {**terminal, "unexpected_mutation": True},
                expected_version=terminal["state_version"],
                transition_kind=server.PlcDispatchTransitionKind.RECORD_UPDATE,
            )
        except server.PlcDispatchStateConflict as exc:
            assert exc.reason == "unknown_field_addition:unexpected_mutation"
        else:
            raise AssertionError("PG unknown field addition was accepted")
        for mutation in (
            {**terminal, "namespace_present": False},
            {**terminal, "active_attempts": [{"target": "D206", "attempt": 99}]},
            {**terminal, "history": [{"status": "acknowledged", "at": 1}]},
            {**terminal, "duplicate": True},
            {**terminal, "acknowledged_targets": ["D206", "Y99"]},
            {**terminal, "frames": [{"target": "Y99", "frame_hex": "DEADBEEF", "attempts": 77}]},
            {**terminal, "bytes_written": 999},
            {**terminal, "attempts": 999},
            {**terminal, "target": "Y99"},
        ):
            try:
                server.persist_plc_dispatch_record(
                    mutation, expected_version=terminal["state_version"]
                )
            except server.PlcDispatchStateConflict:
                pass
            else:
                raise AssertionError("PG known-but-nonmutable field mutation was accepted")
            authoritative = next(
                item
                for item in server.plc_dispatch_audit_records()
                if item.get("dispatch_id") == "pg-terminal"
            )
            assert authoritative["state_version"] == terminal["state_version"]
            assert authoritative.get("namespace_present") is None
            assert authoritative.get("active_attempts") is None
            assert authoritative.get("history") is None
            assert authoritative.get("duplicate") is None
            assert authoritative["acknowledged_targets"] == ["D206"]
            assert authoritative.get("frames") is None
            assert authoritative.get("bytes_written") is None
            assert authoritative.get("attempts") is None
            assert authoritative.get("target") is None
        pg_forged_operation = {
            "attempt_id": "pg-terminal:Y99:77",
            "target": "Y99",
            "attempt": 77,
            "frame_hex": "DEADBEEF",
            "frame_bytes": 4,
            "bytes_written": 4,
            "physical_status": "acknowledged",
            "outcome": "acknowledged",
            "result_code": "acknowledged",
            "diagnostic_source": "forged",
            "started_at": 1,
            "finished_at": 2,
        }
        try:
            server.persist_plc_dispatch_record(
                {**terminal, "operations": [pg_forged_operation]},
                expected_version=terminal["state_version"],
            )
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("PG forged operation append was accepted")
        authoritative = next(
            item
            for item in server.plc_dispatch_audit_records()
            if item.get("dispatch_id") == "pg-terminal"
        )
        assert authoritative["state_version"] == terminal["state_version"]
        assert authoritative.get("operations") is None
    finally:
        server.plc_pg_coordination_available = original_coordination
        server.runtime_postgres_repository_or_none = original_repo


def test_restart_hydration_cas_and_no_replay() -> None:
    save_enabled(generation=50, retries=0)
    opens = 0

    def forbidden(_config: dict[str, Any]) -> Any:
        nonlocal opens
        opens += 1
        raise AssertionError("restart duplicate replayed physical I/O")

    terminal_result = {"request_id": "restart-terminal", "passed": True}
    terminal_id, _, _ = server.plc_dispatch_identity(
        terminal_result, source="image", fingerprint="restart-terminal"
    )
    initial_factory = ScriptedFactory([lambda writes: ScriptedTransport(writes, response=ACK)])
    server._plc_transport_factory = initial_factory
    try:
        initial_terminal = server.dispatch_plc_for_detection(
            dict(terminal_result), source="image", fingerprint="restart-terminal"
        )["plc_sync"]
    finally:
        server._plc_transport_factory = None
    assert initial_terminal["status"] == "acknowledged"
    terminal_version = initial_terminal["state_version"]
    server._plc_dispatch_runtime.clear()
    server._plc_transport_factory = forbidden
    try:
        duplicate = server.dispatch_plc_for_detection(
            dict(terminal_result), source="image", fingerprint="restart-terminal"
        )["plc_sync"]
    finally:
        server._plc_transport_factory = None
    assert duplicate["duplicate"] is True
    assert duplicate["state_version"] == terminal_version
    assert duplicate["status"] == "acknowledged"
    assert duplicate["acknowledged_targets"] == ["D206"]
    assert opens == 0
    assert audit_for(terminal_id)[0]["state_version"] == terminal_version

    nonterminal_result = {"request_id": "restart-nonterminal", "passed": False}
    nonterminal_id, _, _ = server.plc_dispatch_identity(
        nonterminal_result, source="video", fingerprint="restart-nonterminal"
    )

    queued_nonterminal = server.create_plc_dispatch(
        source="video", request_id="restart-nonterminal", passed=False,
        fingerprint="restart-nonterminal", expected_generation=50,
    )
    server._plc_dispatch_runtime.clear()
    server._plc_transport_factory = forbidden
    try:
        recovered = server.dispatch_plc_for_detection(
            dict(nonterminal_result), source="video", fingerprint="restart-nonterminal"
        )["plc_sync"]
    finally:
        server._plc_transport_factory = None
    assert recovered["state_version"] == queued_nonterminal["state_version"] + 1, recovered
    assert recovered["error_code"] == "restart_recovery_required"
    assert recovered["attempted"] is False
    assert opens == 0

    stale_id, _, _ = server.plc_dispatch_identity(
        {"request_id": "restart-stale-cas", "passed": True},
        source="image",
        fingerprint="restart-stale-cas",
    )
    queued = server.create_plc_dispatch(
        source="image",
        request_id="restart-stale-cas",
        passed=True,
        fingerprint="restart-stale-cas",
        expected_generation=50,
    )
    server._plc_dispatch_runtime.clear()
    authoritative = server.plc_transition_attempting(
        stale_id,
        expected_version=queued["state_version"],
    )
    assert authoritative["state_version"] == 2
    try:
        server.plc_transition_attempting(stale_id, expected_version=queued["state_version"])
    except server.PlcDispatchStateConflict:
        pass
    else:
        raise AssertionError("stale runtime write was accepted after a newer CAS state")
    assert audit_for(stale_id)[0]["status"] == "attempting"

    try:
        terminal_authority = audit_for(terminal_id)[0]
        server.persist_plc_dispatch_record(
            {
                **terminal_authority,
                "status": "queued",
                "attempted": False,
                "worker_done": False,
            },
            expected_version=7,
        )
    except server.PlcDispatchStateConflict as exc:
        assert exc.authoritative["acknowledged_targets"] == ["D206"]
    else:
        raise AssertionError("JSON terminal downgrade was accepted")
    assert audit_for(terminal_id)[0]["state_version"] == 7

    provisional = seed_dispatch_fixture(
        {
            "dispatch_id": "legal-provisional",
            "status": "failed",
            "attempted": True,
            "worker_done": False,
            "provisional": True,
            "physical_status": "write_outcome_uncertain",
            "outcome": "outcome_uncertain",
            "acknowledged_targets": [],
        },
    )
    finalized = apply_dispatch_fixture(
        {
            **provisional,
            "status": "failed",
            "attempted": True,
            "worker_done": True,
            "provisional": False,
            "physical_status": "write_outcome_uncertain",
            "outcome": "outcome_uncertain",
        },
        expected_version=provisional["state_version"],
        transition_kind=server.PlcDispatchTransitionKind.WORKER_FINALIZE,
    )
    assert finalized["state_version"] == 2
    assert finalized["worker_done"] is True
    assert finalized["acknowledged_targets"] == []


def test_control_state_failures_preserve_ack_evidence() -> None:
    full = ScriptedFactory([lambda writes: ScriptedTransport(writes, response=ACK)])
    result = dispatch_detection_result(
        dispatch_id="control-fail-after-ack",
        source="image",
        request_id="control-fail-after-ack",
        passed=True,
        config=enabled_config(retries=0),
        transport_factory=full,
        dispatch_cancel_reason=lambda: (_ for _ in ()).throw(OSError("control read failed")),
    )
    assert result["error_code"] == "control_state_check_failed_after_ack"
    assert result["attempted"] is True
    assert result["physical_status"] == "acknowledged"
    assert result["outcome"] == "acknowledged_control_state_unknown"
    assert result["acknowledged_targets"] == ["D206"]

    calls = 0

    def fail_before_second_target(_target: str, _attempt: int) -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("control read failed between targets")
        return True

    partial = ScriptedFactory([lambda writes: ScriptedTransport(writes, response=ACK)])
    result = dispatch_detection_result(
        dispatch_id="control-fail-after-partial-ack",
        source="video",
        request_id="control-fail-after-partial-ack",
        passed=False,
        config=enabled_config(retries=0, write_y04=True),
        transport_factory=partial,
        before_attempt=fail_before_second_target,
    )
    assert result["error_code"] == "control_state_check_failed_after_partial_ack"
    assert result["acknowledged_targets"] == ["D206"]
    assert result["failed_target"] == "Y04"
    assert partial.writes == [build_d206_frame("119C", False)]


def test_strict_create_boundary_json() -> None:
    def replace_namespace(value: Any = server.PLC_CONFIG_ABSENT, *, generation: int = 0) -> None:
        def mutate(config: dict[str, Any]) -> None:
            if value is server.PLC_CONFIG_ABSENT:
                config.pop("plc", None)
            else:
                config["plc"] = value
            config[server.PLC_CONTROL_GENERATION_KEY] = generation

        server.mutate_app_config_atomically(mutate)

    for suffix, namespace, expected_reason in (
        ("absent", server.PLC_CONFIG_ABSENT, "create_plc_namespace_absent"),
        ("null", None, "create_plc_namespace_invalid"),
        ("invalid", {**enabled_config(retries=1), "d206_address": 4508}, "create_plc_namespace_invalid"),
        ("disabled", dict(DEFAULT_PLC_CONFIG), "create_plc_disabled"),
    ):
        replace_namespace(namespace)
        before_ids = {item.get("dispatch_id") for item in server.plc_dispatch_audit_records()}
        try:
            server.create_plc_dispatch(
                source="image", request_id=f"strict-create-{suffix}", passed=True,
                fingerprint=f"strict-create-{suffix}",
            )
        except server.PlcDispatchStateConflict as exc:
            assert exc.reason == expected_reason
        else:
            raise AssertionError(f"create accepted {suffix} authoritative PLC namespace")
        assert {item.get("dispatch_id") for item in server.plc_dispatch_audit_records()} == before_ids

    save_enabled(generation=7, retries=1)
    before_ids = {item.get("dispatch_id") for item in server.plc_dispatch_audit_records()}
    try:
        server.create_plc_dispatch(
            source="image", request_id="strict-create-forged-plan", passed=True,
            fingerprint="strict-create-forged-plan",
            config=enabled_config(write_y04=True),  # type: ignore[call-arg]
        )
    except TypeError:
        pass
    else:
        raise AssertionError("create accepted caller-supplied config/plan intent")
    assert {item.get("dispatch_id") for item in server.plc_dispatch_audit_records()} == before_ids
    try:
        server.create_plc_dispatch(
            source="image", request_id="strict-create-stale-generation", passed=True,
            fingerprint="strict-create-stale-generation", expected_generation=6,
        )
    except server.PlcDispatchStateConflict as exc:
        assert exc.reason == "create_generation_mismatch"
    else:
        raise AssertionError("create accepted stale expected generation")
    created = server.create_plc_dispatch(
        source="image",
        request_id="strict-create-json",
        passed=True,
        fingerprint="strict-create-json",
        expected_generation=7,
    )
    assert created["state_version"] == 1
    assert created["status"] == "queued"
    assert created["attempted"] is False
    assert created.get("operations") is None
    assert created.get("acknowledged_targets") is None
    duplicate = server.create_plc_dispatch(
        source="image",
        request_id="strict-create-json",
        passed=True,
        fingerprint="strict-create-json",
        expected_generation=7,
    )
    assert duplicate["state_version"] == 1
    assert len(audit_for(created["dispatch_id"])) == 1
    disable_direct()
    duplicate_after_change = server.create_plc_dispatch(
        source="image", request_id="strict-create-json", passed=True,
        fingerprint="strict-create-json", expected_generation=999,
    )
    assert duplicate_after_change == created
    assert len(audit_for(created["dispatch_id"])) == 1
    try:
        server.create_plc_dispatch(
            source="image",
            request_id="strict-create-json",
            passed=False,
            fingerprint="strict-create-json",
            expected_generation=7,
        )
    except server.PlcDispatchStateConflict as exc:
        assert exc.reason == "create_dispatch_identity_conflict"
    else:
        raise AssertionError("conflicting idempotent create was accepted")
    authoritative = audit_for(created["dispatch_id"])[0]
    assert authoritative["state_version"] == 1 and authoritative["passed"] is True

    forged_id = "forged-create-json"
    forged = {
        "dispatch_id": forged_id,
        "source": "image",
        "request_id": forged_id,
        "passed": True,
        "status": "acknowledged",
        "attempted": True,
        "acknowledged_targets": ["Y99"],
        "frames": [{"target": "Y99", "frame_hex": "DEADBEEF", "attempts": 77}],
        "bytes_written": 999,
        "attempts": 999,
        "state_version": 999,
        "unexpected": True,
    }
    for kwargs in ({}, {"expected_version": 0}):
        try:
            server.persist_plc_dispatch_record(dict(forged), **kwargs)
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("public forged final-at-create was accepted")
    assert not audit_for(forged_id)
    try:
        server.persist_plc_dispatch_record({**created, "status": "acknowledged", "state_version": 999})
    except server.PlcDispatchStateConflict:
        pass
    else:
        raise AssertionError("existing-ID no-version overwrite was accepted")
    authoritative = audit_for(created["dispatch_id"])[0]
    assert authoritative["state_version"] == 1 and authoritative["status"] == "queued"

    results: list[dict[str, Any]] = []
    failures: list[Exception] = []
    save_enabled(generation=8, retries=1)

    def create_concurrently() -> None:
        try:
            results.append(
                server.create_plc_dispatch(
                    source="video",
                    request_id="strict-create-race",
                    passed=False,
                    fingerprint="strict-create-race",
                    expected_generation=8,
                )
            )
        except Exception as exc:
            failures.append(exc)

    threads = [threading.Thread(target=create_concurrently) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert not failures and len(results) == 2
    assert {item["state_version"] for item in results} == {1}
    assert len(audit_for(results[0]["dispatch_id"])) == 1

    # Config transaction linearizes first: create sees the new epoch and two-target plan.
    save_enabled(generation=20, retries=0, write_y04=False)
    config_locked = threading.Event()
    config_release = threading.Event()

    def change_before_create(config_values: dict[str, Any]) -> None:
        config_values["plc"] = enabled_config(retries=0, write_y04=True)
        config_values[server.PLC_CONTROL_GENERATION_KEY] = 21
        config_locked.set()
        assert config_release.wait(5)

    changer = threading.Thread(target=server.mutate_app_config_atomically, args=(change_before_create,))
    changer.start()
    assert config_locked.wait(2)
    after_change: list[dict[str, Any]] = []
    create_after = threading.Thread(
        target=lambda: after_change.append(
            server.create_plc_dispatch(
                source="image", request_id="linearized-config-first", passed=True,
                fingerprint="linearized-config-first", expected_generation=21,
            )
        )
    )
    create_after.start()
    time.sleep(0.05)
    assert create_after.is_alive()
    config_release.set()
    changer.join(5)
    create_after.join(5)
    assert after_change[0]["control_generation"] == 21
    assert after_change[0]["planned_targets"] == ["D206", "Y04"]

    # Create transaction linearizes first: a later config mutation cannot alter its v1 binding.
    save_enabled(generation=30, retries=0, write_y04=False)
    original_records = server.plc_dispatch_audit_records
    create_locked = threading.Event()
    create_release = threading.Event()

    def pause_create_records(config_values: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        records = original_records(config_values)
        if config_values is not None and not create_locked.is_set():
            create_locked.set()
            assert create_release.wait(5)
        return records

    server.plc_dispatch_audit_records = pause_create_records
    before_change: list[dict[str, Any]] = []
    create_before = threading.Thread(
        target=lambda: before_change.append(
            server.create_plc_dispatch(
                source="image", request_id="linearized-create-first", passed=True,
                fingerprint="linearized-create-first", expected_generation=30,
            )
        )
    )
    create_before.start()
    assert create_locked.wait(2)
    change_after = threading.Thread(
        target=lambda: save_enabled(generation=31, retries=0, write_y04=True)
    )
    change_after.start()
    time.sleep(0.05)
    assert change_after.is_alive()
    create_release.set()
    create_before.join(5)
    change_after.join(5)
    server.plc_dispatch_audit_records = original_records
    assert before_change[0]["control_generation"] == 30
    assert before_change[0]["planned_targets"] == ["D206"]
    assert server.load_config()[server.PLC_CONTROL_GENERATION_KEY] == 31


def test_actual_typed_handler_boundary_json_and_pg() -> None:
    original_repo = server.runtime_postgres_repository_or_none
    original_coordination = server.plc_pg_coordination_available

    def run_case(label: str) -> None:
        save_enabled(generation=41, retries=1)
        created = server.create_plc_dispatch(
            source="image", request_id=f"typed-{label}", passed=True,
            fingerprint=f"typed-{label}", expected_generation=41,
        )
        assert created["state_version"] == 1 and created["status"] == "queued"
        duplicate = server.create_plc_dispatch(
            source="image", request_id=f"typed-{label}", passed=True,
            fingerprint=f"typed-{label}", expected_generation=41,
        )
        assert duplicate == created
        current = server.plc_transition_attempting(
            created["dispatch_id"], expected_version=created["state_version"]
        )
        current = server.plc_start_attempt(
            created["dispatch_id"], expected_version=current["state_version"], target="D206"
        )
        first = current["operations"][-1]
        stable_version = current["state_version"]
        forged_payloads = [
            (
                server.PlcDispatchTransitionKind.ADVANCE_ATTEMPT,
                {
                    "attempt_id": first["attempt_id"], "bytes_written": 0,
                    "physical_status": "write_call_started", "outcome": "write_outcome_uncertain",
                    "acknowledged_targets": ["Y99"],
                },
            ),
            (server.PlcDispatchTransitionKind.DEADLINE, {"frames": [{"target": "Y99"}]}),
            (
                server.PlcDispatchTransitionKind.FINALIZE,
                {"reason": "", "attempts": 999, "target": "Y99"},
            ),
        ]
        for kind, payload in forged_payloads:
            try:
                server._apply_plc_dispatch_event(
                    created["dispatch_id"], expected_version=stable_version,
                    transition_kind=kind, event_payload=payload,
                )
            except server.PlcDispatchStateConflict as exc:
                assert exc.reason.startswith("transition_payload_extra_field:")
            else:
                raise AssertionError(f"{label} accepted projection smuggling for {kind.value}")
            authoritative = audit_for(created["dispatch_id"])[0]
            assert authoritative["state_version"] == stable_version
            assert authoritative.get("target") != "Y99"
            assert authoritative.get("acknowledged_targets") in (None, [])
        try:
            server._apply_plc_dispatch_event(
                created["dispatch_id"], expected_version=stable_version,
                transition_kind="evil", event_payload={},  # type: ignore[arg-type]
            )
        except server.PlcDispatchStateConflict as exc:
            assert exc.reason == "unknown_transition_kind"
        else:
            raise AssertionError(f"{label} accepted unknown transition kind")

        current = server.plc_advance_attempt(
            created["dispatch_id"], expected_version=stable_version,
            attempt_id=first["attempt_id"], bytes_written=0,
            physical_status="write_call_started", outcome="write_outcome_uncertain",
        )
        current = server.plc_advance_attempt(
            created["dispatch_id"], expected_version=current["state_version"],
            attempt_id=first["attempt_id"], bytes_written=first["frame_bytes"],
            physical_status="full_frame_written", outcome="awaiting_acknowledgement",
        )
        current = server.plc_finish_attempt(
            created["dispatch_id"], expected_version=current["state_version"],
            attempt_id=first["attempt_id"],
            terminal_result=PlcAttemptTerminalResult(
                code=PlcTerminalResultCode.NAK,
                phase=PlcTransportPhase.RESPONSE,
                bytes_written=first["frame_bytes"],
                diagnostic_source="nak_byte",
            ),
        )
        premature_version = current["state_version"]
        premature_snapshot = dict(audit_for(created["dispatch_id"])[0])
        try:
            server.plc_finalize_dispatch(
                created["dispatch_id"], expected_version=premature_version
            )
        except server.PlcDispatchStateConflict as exc:
            assert exc.reason == "corrupt_persisted_dispatch:retry_budget_not_exhausted"
        else:
            raise AssertionError(f"{label} accepted premature retryable finalize")
        assert audit_for(created["dispatch_id"])[0] == premature_snapshot
        current = server.plc_start_attempt(
            created["dispatch_id"], expected_version=current["state_version"], target="D206"
        )
        retry = current["operations"][-1]
        current = server.plc_advance_attempt(
            created["dispatch_id"], expected_version=current["state_version"],
            attempt_id=retry["attempt_id"], bytes_written=0,
            physical_status="write_call_started", outcome="write_outcome_uncertain",
        )
        current = server.plc_advance_attempt(
            created["dispatch_id"], expected_version=current["state_version"],
            attempt_id=retry["attempt_id"], bytes_written=retry["frame_bytes"],
            physical_status="full_frame_written", outcome="awaiting_acknowledgement",
        )
        current = server.plc_finish_attempt(
            created["dispatch_id"], expected_version=current["state_version"],
            attempt_id=retry["attempt_id"],
            terminal_result=PlcAttemptTerminalResult(
                code=PlcTerminalResultCode.ACKNOWLEDGED,
                phase=PlcTransportPhase.RESPONSE,
                bytes_written=retry["frame_bytes"],
                diagnostic_source="ack_byte",
            ),
        )
        final = server.plc_finalize_dispatch(
            created["dispatch_id"], expected_version=current["state_version"]
        )
        assert final["status"] == "acknowledged"
        assert final["acknowledged_targets"] == ["D206"]
        assert final["frames"] == [
            {"target": "D206", "frame_hex": retry["frame_hex"], "attempts": 2}
        ]
        assert [item["result_code"] for item in final["operations"]] == ["nak", "acknowledged"]
        assert final["worker_done"] is True and len(audit_for(created["dispatch_id"])) == 1

        exhausted = server.create_plc_dispatch(
            source="image", request_id=f"typed-exhausted-{label}", passed=True,
            fingerprint=f"typed-exhausted-{label}", expected_generation=41,
        )
        exhausted = server.plc_transition_attempting(
            exhausted["dispatch_id"], expected_version=exhausted["state_version"]
        )
        for _attempt in range(2):
            exhausted = server.plc_start_attempt(
                exhausted["dispatch_id"], expected_version=exhausted["state_version"], target="D206"
            )
            failed_attempt = exhausted["operations"][-1]
            exhausted = server.plc_advance_attempt(
                exhausted["dispatch_id"], expected_version=exhausted["state_version"],
                attempt_id=failed_attempt["attempt_id"], bytes_written=0,
                physical_status="write_call_started", outcome="write_outcome_uncertain",
            )
            exhausted = server.plc_advance_attempt(
                exhausted["dispatch_id"], expected_version=exhausted["state_version"],
                attempt_id=failed_attempt["attempt_id"], bytes_written=failed_attempt["frame_bytes"],
                physical_status="full_frame_written", outcome="awaiting_acknowledgement",
            )
            exhausted = server.plc_finish_attempt(
                exhausted["dispatch_id"], expected_version=exhausted["state_version"],
                attempt_id=failed_attempt["attempt_id"],
                terminal_result=PlcAttemptTerminalResult(
                    code=PlcTerminalResultCode.NAK,
                    phase=PlcTransportPhase.RESPONSE,
                    bytes_written=failed_attempt["frame_bytes"],
                    diagnostic_source="nak_byte",
                ),
            )
        exhausted = server.plc_finalize_dispatch(
            exhausted["dispatch_id"], expected_version=exhausted["state_version"]
        )
        assert exhausted["status"] == "failed"
        assert exhausted["error_code"] == "nak"
        assert exhausted["attempts"] == 2
        assert len(exhausted["operations"]) == 2
        assert server.verify_persisted_plc_dispatch(exhausted) == exhausted

        non_retryable_cases = (
            (PlcTerminalResultCode.WRITE_RESULT_UNKNOWN, PlcTransportPhase.WRITE, "write_returned_none", "started"),
            (PlcTerminalResultCode.TIMEOUT, PlcTransportPhase.WRITE, "write_timeout_exception", "started"),
            (PlcTerminalResultCode.TIMEOUT, PlcTransportPhase.FLUSH, "flush_timeout_exception", "full"),
            (PlcTerminalResultCode.SHORT_WRITE, PlcTransportPhase.WRITE, "write_length_mismatch", "partial"),
            (PlcTerminalResultCode.SERIAL_IO_FAILED, PlcTransportPhase.WRITE, "write_exception", "started"),
            (PlcTerminalResultCode.SERIAL_IO_FAILED, PlcTransportPhase.READ, "read_exception", "full"),
            (PlcTerminalResultCode.FLUSH_FAILED, PlcTransportPhase.FLUSH, "flush_exception", "full"),
            (PlcTerminalResultCode.SERIAL_OPEN_FAILED, PlcTransportPhase.OPEN, "transport_factory_exception", "none"),
            (PlcTerminalResultCode.SERIAL_DEPENDENCY_MISSING, PlcTransportPhase.OPEN, "pyserial_import", "none"),
            (PlcTerminalResultCode.INTERNAL_TRANSITION_ERROR, PlcTransportPhase.INTERNAL, "unknown_client_terminal_code", "full"),
        )
        for index, (code, phase, diagnostic, progress) in enumerate(non_retryable_cases):
            blocked = server.create_plc_dispatch(
                source="image", request_id=f"typed-no-retry-{label}-{index}", passed=True,
                fingerprint=f"typed-no-retry-{label}-{index}", expected_generation=41,
            )
            blocked = server.plc_transition_attempting(
                blocked["dispatch_id"], expected_version=blocked["state_version"]
            )
            blocked = server.plc_start_attempt(
                blocked["dispatch_id"], expected_version=blocked["state_version"], target="D206"
            )
            blocked_operation = blocked["operations"][-1]
            if progress != "none":
                blocked = server.plc_advance_attempt(
                    blocked["dispatch_id"], expected_version=blocked["state_version"],
                    attempt_id=blocked_operation["attempt_id"], bytes_written=0,
                    physical_status="write_call_started", outcome="write_outcome_uncertain",
                )
            if progress in {"partial", "full"}:
                write_count = 1 if progress == "partial" else blocked_operation["frame_bytes"]
                blocked = server.plc_advance_attempt(
                    blocked["dispatch_id"], expected_version=blocked["state_version"],
                    attempt_id=blocked_operation["attempt_id"], bytes_written=write_count,
                    physical_status="partial_write" if progress == "partial" else "full_frame_written",
                    outcome="outcome_uncertain" if progress == "partial" else "awaiting_acknowledgement",
                )
            terminal_bytes = int(blocked["operations"][-1]["bytes_written"])
            blocked = server.plc_finish_attempt(
                blocked["dispatch_id"], expected_version=blocked["state_version"],
                attempt_id=blocked_operation["attempt_id"],
                terminal_result=PlcAttemptTerminalResult(
                    code=code, phase=phase, bytes_written=terminal_bytes,
                    diagnostic_source=diagnostic,
                ),
            )
            blocked_before = dict(audit_for(blocked["dispatch_id"])[0])
            try:
                server.plc_start_attempt(
                    blocked["dispatch_id"], expected_version=blocked["state_version"], target="D206"
                )
            except server.PlcDispatchStateConflict as exc:
                assert exc.reason in {
                    "previous_attempt_result_is_not_retryable",
                    "corrupt_persisted_dispatch:retry_chain_invalid",
                }
            else:
                raise AssertionError(f"{label} allowed retry after {code.value}/{phase.value}")
            assert audit_for(blocked["dispatch_id"])[0] == blocked_before
            blocked_final = server.plc_finalize_dispatch(
                blocked["dispatch_id"], expected_version=blocked["state_version"]
            )
            assert blocked_final["status"] == "failed"
            assert server.verify_persisted_plc_dispatch(blocked_final) == blocked_final
            if code is PlcTerminalResultCode.INTERNAL_TRANSITION_ERROR:
                forged_internal = copy.deepcopy(blocked_final)
                forged_internal["outcome"] = "awaiting_acknowledgement"
                forged_internal["operations"][-1]["outcome"] = "awaiting_acknowledgement"
                forged_internal["failed_operation"]["outcome"] = "awaiting_acknowledgement"
                forged_internal = seed_dispatch_fixture(forged_internal)
                forged_before = dict(audit_for(blocked["dispatch_id"])[0])
                try:
                    server.verify_persisted_plc_dispatch(forged_internal)
                except server.PlcDispatchStateConflict as exc:
                    assert exc.reason == "corrupt_persisted_dispatch:projection_mismatch:failed_operation"
                else:
                    raise AssertionError(f"{label} accepted forged internal awaiting-ack projection")
                assert audit_for(blocked["dispatch_id"])[0] == forged_before == forged_internal

        retryable_cases = (
            (PlcTerminalResultCode.NAK, PlcTransportPhase.RESPONSE, "nak_byte"),
            (PlcTerminalResultCode.TIMEOUT, PlcTransportPhase.READ, "empty_read"),
            (PlcTerminalResultCode.SHORT_RESPONSE, PlcTransportPhase.RESPONSE, "non_ack_control_byte"),
            (PlcTerminalResultCode.UNEXPECTED_RESPONSE, PlcTransportPhase.RESPONSE, "multi_byte_response"),
        )
        for index, (code, phase, diagnostic) in enumerate(retryable_cases):
            retryable = server.create_plc_dispatch(
                source="image", request_id=f"typed-retry-{label}-{index}", passed=True,
                fingerprint=f"typed-retry-{label}-{index}", expected_generation=41,
            )
            retryable = server.plc_transition_attempting(
                retryable["dispatch_id"], expected_version=retryable["state_version"]
            )
            retryable = server.plc_start_attempt(
                retryable["dispatch_id"], expected_version=retryable["state_version"], target="D206"
            )
            first_retryable = retryable["operations"][-1]
            retryable = server.plc_advance_attempt(
                retryable["dispatch_id"], expected_version=retryable["state_version"],
                attempt_id=first_retryable["attempt_id"], bytes_written=0,
                physical_status="write_call_started", outcome="write_outcome_uncertain",
            )
            retryable = server.plc_advance_attempt(
                retryable["dispatch_id"], expected_version=retryable["state_version"],
                attempt_id=first_retryable["attempt_id"], bytes_written=first_retryable["frame_bytes"],
                physical_status="full_frame_written", outcome="awaiting_acknowledgement",
            )
            retryable = server.plc_finish_attempt(
                retryable["dispatch_id"], expected_version=retryable["state_version"],
                attempt_id=first_retryable["attempt_id"],
                terminal_result=PlcAttemptTerminalResult(
                    code=code, phase=phase, bytes_written=first_retryable["frame_bytes"],
                    diagnostic_source=diagnostic,
                ),
            )
            retryable = server.plc_start_attempt(
                retryable["dispatch_id"], expected_version=retryable["state_version"], target="D206"
            )
            assert len(retryable["operations"]) == 2
            assert retryable["operations"][-1]["attempt"] == 2
            assert server.verify_persisted_plc_dispatch(retryable) == retryable

        original_display_limit = server.PLC_DISPATCH_AUDIT_LIMIT
        server.PLC_DISPATCH_AUDIT_LIMIT = 3
        try:
            retained = server.create_plc_dispatch(
                source="image", request_id=f"retained-{label}", passed=True,
                fingerprint=f"retained-{label}", expected_generation=41,
            )
            for index in range(server.PLC_DISPATCH_AUDIT_LIMIT + 1):
                server.create_plc_dispatch(
                    source="image", request_id=f"retention-fill-{label}-{index}", passed=True,
                    fingerprint=f"retention-fill-{label}-{index}", expected_generation=41,
                )
            retained_records = audit_for(retained["dispatch_id"])
            assert retained_records == [retained]
            retained_duplicate = server.create_plc_dispatch(
                source="image", request_id=f"retained-{label}", passed=True,
                fingerprint=f"retained-{label}", expected_generation=41,
            )
            assert retained_duplicate == retained
            try:
                server.create_plc_dispatch(
                    source="image", request_id=f"retained-{label}", passed=False,
                    fingerprint=f"retained-{label}", expected_generation=41,
                )
            except server.PlcDispatchStateConflict as exc:
                assert exc.reason == "create_dispatch_identity_conflict"
                assert exc.authoritative == retained
            else:
                raise AssertionError(f"{label} accepted retained idempotency identity conflict")
            assert audit_for(retained["dispatch_id"]) == [retained]

            uncertain = server.create_plc_dispatch(
                source="video", request_id=f"retained-uncertain-{label}", passed=False,
                fingerprint=f"retained-uncertain-{label}", expected_generation=41,
            )
            uncertain = server.plc_transition_attempting(
                uncertain["dispatch_id"], expected_version=uncertain["state_version"]
            )
            uncertain = server.plc_start_attempt(
                uncertain["dispatch_id"], expected_version=uncertain["state_version"], target="D206"
            )
            uncertain_operation = uncertain["operations"][-1]
            uncertain = server.plc_advance_attempt(
                uncertain["dispatch_id"], expected_version=uncertain["state_version"],
                attempt_id=uncertain_operation["attempt_id"], bytes_written=0,
                physical_status="write_call_started", outcome="write_outcome_uncertain",
            )
            for index in range(server.PLC_DISPATCH_AUDIT_LIMIT + 1):
                server.create_plc_dispatch(
                    source="video", request_id=f"uncertain-fill-{label}-{index}", passed=False,
                    fingerprint=f"uncertain-fill-{label}-{index}", expected_generation=41,
                )
            assert audit_for(uncertain["dispatch_id"]) == [uncertain]
            assert len(server.plc_config_response()["recent_dispatches"]) == 3
        finally:
            server.PLC_DISPATCH_AUDIT_LIMIT = original_display_limit

        cancel = server.create_plc_dispatch(
            source="video", request_id=f"typed-cancel-{label}", passed=False,
            fingerprint=f"typed-cancel-{label}", expected_generation=41,
        )
        cancelled = server.plc_cancel_dispatch(
            cancel["dispatch_id"], expected_version=cancel["state_version"],
            reason="cancelled_after_config_change",
        )
        assert cancelled["status"] == "failed" and cancelled["attempted"] is False
        assert cancelled["cancelled_after_config_change"] is True
        deadline = server.create_plc_dispatch(
            source="video", request_id=f"typed-deadline-{label}", passed=False,
            fingerprint=f"typed-deadline-{label}", expected_generation=41,
        )
        marked = server.plc_mark_deadline(
            deadline["dispatch_id"], expected_version=deadline["state_version"]
        )
        assert marked["provisional"] is True and marked["deadline_exceeded"] is True
        closed = server.plc_finalize_dispatch(
            deadline["dispatch_id"], expected_version=marked["state_version"],
            reason="deadline_exceeded",
        )
        assert closed["status"] == "failed" and closed["provisional"] is False

    server.runtime_postgres_repository_or_none = lambda: None
    run_case("json")
    backend = SharedPgBackend()
    server.runtime_postgres_repository_or_none = lambda: FakeIndependentPgRepository(backend)
    server.plc_pg_coordination_available = lambda: True
    try:
        run_case("pg")
    finally:
        server.plc_pg_coordination_available = original_coordination
        server.runtime_postgres_repository_or_none = original_repo


def test_persisted_duplicate_verifier_and_runtime_paths() -> None:
    original_repo = server.runtime_postgres_repository_or_none
    original_coordination = server.plc_pg_coordination_available

    def run_corrupt_matrix(label: str) -> None:
        save_enabled(generation=70, retries=0)
        variants: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any]], str]] = [
            (
                "plan",
                lambda record: {
                    **record,
                    "planned_targets": ["Y99"],
                    "planned_frames": [{"target": "Y99", "frame_hex": "DEADBEEF"}],
                },
                "corrupt_persisted_dispatch:plan_binding_invalid",
            ),
            (
                "final",
                lambda record: {
                    **record,
                    "status": "acknowledged",
                    "history": [*record["history"], {"status": "acknowledged", "at": int(time.time())}],
                    "attempted": True,
                    "worker_done": True,
                    "physical_status": "acknowledged",
                    "outcome": "acknowledged",
                    "acknowledged_targets": ["Y99"],
                    "targets": ["Y99"],
                    "frames": [{"target": "Y99", "frame_hex": "DEADBEEF", "attempts": 1}],
                },
                "corrupt_persisted_dispatch:projection_mismatch:acknowledged_targets",
            ),
            (
                "chain",
                lambda record: {
                    **record,
                    "status": "attempting",
                    "history": [*record["history"], {"status": "attempting", "at": int(time.time())}],
                    "operations": [
                        {
                            "attempt_id": f"{record['dispatch_id']}:Y99:1",
                            "target": "Y99", "attempt": 1, "frame_hex": "DEADBEEF",
                            "frame_bytes": 4, "bytes_written": 0,
                            "physical_status": "not_attempted", "outcome": "not_attempted",
                            "started_at": int(time.time()),
                        }
                    ],
                    "attempt_ids": [f"{record['dispatch_id']}:Y99:1"],
                },
                "corrupt_persisted_dispatch:projection_mismatch:attempt_ids",
            ),
            (
                "schema-version",
                lambda record: {**record, "record_schema_version": 99},
                "dispatch_migration_required",
            ),
            (
                "schema-bool",
                lambda record: {
                    **record,
                    "record_schema_version": True,
                    "protocol_contract_version": True,
                },
                "dispatch_migration_required",
            ),
            (
                "contract-version",
                lambda record: {**record, "protocol_contract_version": 99},
                "dispatch_migration_required",
            ),
            (
                "identity-types",
                lambda record: {
                    **record,
                    "source": 123,
                    "request_id": 456,
                    "detection_identity": 789,
                },
                "corrupt_persisted_dispatch:identity_type_invalid",
            ),
            (
                "event-bool-time",
                lambda record: {
                    **record,
                    "created_at": True,
                    "events": [{"seq": True, "kind": "create", "at": True}],
                },
                "corrupt_persisted_dispatch:create_event_invalid",
            ),
        ]
        for suffix, mutate_record, expected_reason in variants:
            request_id = f"duplicate-{label}-{suffix}"
            base = server.create_plc_dispatch(
                source="image", request_id=request_id, passed=True,
                fingerprint=request_id, expected_generation=70,
            )
            forged = seed_dispatch_fixture(mutate_record(base))
            before = dict(audit_for(base["dispatch_id"])[0])
            corrupt_calls = (
                lambda: server.plc_transition_attempting(
                    base["dispatch_id"], expected_version=forged["state_version"]
                ),
                lambda: server.plc_start_attempt(
                    base["dispatch_id"], expected_version=forged["state_version"], target="D206"
                ),
                lambda: server.plc_finish_attempt(
                    base["dispatch_id"], expected_version=forged["state_version"],
                    attempt_id="forged-attempt",
                    terminal_result=PlcAttemptTerminalResult(
                        code=PlcTerminalResultCode.ACKNOWLEDGED,
                        phase=PlcTransportPhase.RESPONSE,
                        bytes_written=0,
                        diagnostic_source="ack_byte",
                    ),
                ),
                lambda: server.plc_finalize_dispatch(
                    base["dispatch_id"], expected_version=forged["state_version"]
                ),
            )
            for corrupt_call in corrupt_calls:
                try:
                    corrupt_call()
                except server.PlcDispatchStateConflict as exc:
                    assert exc.reason == expected_reason, (suffix, exc.reason)
                else:
                    raise AssertionError(f"{label} typed handler advanced corrupt {suffix}")
                assert audit_for(base["dispatch_id"])[0] == before
            try:
                server.create_plc_dispatch(
                    source="image", request_id=request_id, passed=True,
                    fingerprint=request_id, expected_generation=70,
                )
            except server.PlcDispatchStateConflict as exc:
                assert exc.reason == expected_reason, (suffix, exc.reason)
            else:
                raise AssertionError(f"{label} accepted corrupt duplicate {suffix}")
            assert audit_for(base["dispatch_id"])[0] == before == forged

        def canonical_ack(request_id: str) -> dict[str, Any]:
            current = server.create_plc_dispatch(
                source="image",
                request_id=request_id,
                passed=True,
                fingerprint=request_id,
                expected_generation=70,
            )
            current = server.plc_transition_attempting(
                current["dispatch_id"], expected_version=current["state_version"]
            )
            current = server.plc_start_attempt(
                current["dispatch_id"], expected_version=current["state_version"], target="D206"
            )
            operation = current["operations"][-1]
            current = server.plc_advance_attempt(
                current["dispatch_id"], expected_version=current["state_version"],
                attempt_id=operation["attempt_id"], bytes_written=0,
                physical_status="write_call_started", outcome="write_outcome_uncertain",
            )
            current = server.plc_advance_attempt(
                current["dispatch_id"], expected_version=current["state_version"],
                attempt_id=operation["attempt_id"], bytes_written=operation["frame_bytes"],
                physical_status="full_frame_written", outcome="awaiting_acknowledgement",
            )
            current = server.plc_finish_attempt(
                current["dispatch_id"], expected_version=current["state_version"],
                attempt_id=operation["attempt_id"],
                terminal_result=PlcAttemptTerminalResult(
                    code=PlcTerminalResultCode.ACKNOWLEDGED,
                    phase=PlcTransportPhase.RESPONSE,
                    bytes_written=operation["frame_bytes"],
                    diagnostic_source="ack_byte",
                ),
            )
            return server.plc_finalize_dispatch(
                current["dispatch_id"], expected_version=current["state_version"]
            )

        projection_variants: list[
            tuple[str, Callable[[dict[str, Any]], dict[str, Any]], str]
        ] = [
            ("bytes", lambda record: {**record, "bytes_written": 999}, "projection_mismatch:bytes_written"),
            ("attempts", lambda record: {**record, "attempts": 999}, "projection_mismatch:attempts"),
            ("target", lambda record: {**record, "target": "Y99"}, "projection_mismatch:target"),
            (
                "failed-summary",
                lambda record: {
                    **record,
                    "failed_target": "Y99",
                    "failed_operation": {
                        "attempt_id": "forged", "target": "Y99", "frame_hex": "DEADBEEF",
                        "frame_bytes": 4, "bytes_written": 4, "write_count_known": True,
                        "reported_write_count": 4, "physical_status": "acknowledged",
                        "outcome": "acknowledged", "diagnostic_source": "ack_byte",
                        "attempts": 999, "error_code": "forged",
                    },
                },
                "projection_mismatch:failed_operation",
            ),
            (
                "history",
                lambda record: {
                    **record,
                    "history": [
                        record["history"][0],
                        {"status": "sent", "at": record["history"][0]["at"], "target": "Y99"},
                        *record["history"][1:],
                    ],
                },
                "projection_mismatch:history",
            ),
            ("all-ack-failed", lambda record: {**record, "status": "failed"}, "projection_mismatch:status"),
        ]
        event_variants: list[
            tuple[str, Callable[[dict[str, Any]], dict[str, Any]], str]
        ] = [
            (
                "event-seq",
                lambda record: {
                    **record,
                    "events": [record["events"][0], {**record["events"][1], "seq": 99}, *record["events"][2:]],
                },
                "event_sequence_invalid",
            ),
            (
                "event-time",
                lambda record: {
                    **record,
                    "events": [
                        record["events"][0],
                        {**record["events"][1], "at": record["events"][0]["at"] - 1},
                        *record["events"][2:],
                    ],
                },
                "event_time_regression",
            ),
            (
                "event-unknown",
                lambda record: {
                    **record,
                    "events": [record["events"][0], {**record["events"][1], "kind": "evil"}, *record["events"][2:]],
                },
                "unknown_event_kind",
            ),
            (
                "event-after-terminal",
                lambda record: {
                    **record,
                    "events": [
                        *record["events"],
                        {"seq": len(record["events"]) + 1, "kind": "attempting", "at": int(time.time())},
                    ],
                    "state_version": len(record["events"]) + 1,
                },
                "event_after_terminal",
            ),
            (
                "unfinished-finalize",
                lambda record: {
                    **record,
                    "events": [
                        *[
                            {**event, "seq": index}
                            for index, event in enumerate(
                                [item for item in record["events"] if item["kind"] != "finish_attempt"],
                                start=1,
                            )
                        ]
                    ],
                    "state_version": len(record["events"]) - 1,
                },
                "finalize_event_invalid",
            ),
            (
                "ack-bytes",
                lambda record: {
                    **record,
                    "events": [
                        {**event, "bytes_written": 0} if event["kind"] == "finish_attempt" else event
                        for event in record["events"]
                    ],
                },
                "terminal_result_invalid",
            ),
            (
                "target-order",
                lambda record: {
                    **record,
                    "events": [
                        {**event, "target": "Y99"} if event["kind"] == "start_attempt" else event
                        for event in record["events"]
                    ],
                },
                "attempt_target_order_invalid",
            ),
        ]
        for suffix, mutate_record, reason_suffix in [*projection_variants, *event_variants]:
            request_id = f"reducer-{label}-{suffix}"
            terminal = canonical_ack(request_id)
            assert server.verify_persisted_plc_dispatch(terminal) == terminal
            forged = seed_dispatch_fixture(mutate_record(terminal))
            before = dict(audit_for(terminal["dispatch_id"])[0])
            try:
                server.verify_persisted_plc_dispatch(forged)
            except server.PlcDispatchStateConflict as exc:
                assert exc.reason == f"corrupt_persisted_dispatch:{reason_suffix}", (suffix, exc.reason)
            else:
                raise AssertionError(f"{label} reducer accepted forged {suffix}")
            opens = 0

            def forbidden_transport(_config: dict[str, Any]) -> Any:
                nonlocal opens
                opens += 1
                raise AssertionError(f"{label} forged {suffix} reached physical I/O")

            server._plc_transport_factory = forbidden_transport
            try:
                direct = server.dispatch_plc_for_detection(
                    {"request_id": request_id, "passed": True},
                    source="image",
                    fingerprint=request_id,
                )["plc_sync"]
                queued = server._run_queued_plc_dispatch(
                    {"request_id": request_id, "passed": True},
                    source="image",
                    fingerprint=request_id,
                )["plc_sync"]
            finally:
                server._plc_transport_factory = None
            expected_error = f"corrupt_persisted_dispatch:{reason_suffix}"
            assert direct["error_code"] == expected_error, (suffix, direct)
            assert queued["error_code"] == expected_error, (suffix, queued)
            assert direct["audit_status"] == queued["audit_status"] == "state_conflict"
            assert opens == 0
            assert audit_for(terminal["dispatch_id"])[0] == before == forged

    server.runtime_postgres_repository_or_none = lambda: None
    run_corrupt_matrix("json")
    backend = SharedPgBackend()
    server.runtime_postgres_repository_or_none = lambda: FakeIndependentPgRepository(backend)
    server.plc_pg_coordination_available = lambda: True
    try:
        run_corrupt_matrix("pg")
    finally:
        server.plc_pg_coordination_available = original_coordination
        server.runtime_postgres_repository_or_none = original_repo

    save_enabled(generation=80, retries=0)
    terminal_request = "duplicate-valid-terminal"
    ack_factory = ScriptedFactory([lambda writes: ScriptedTransport(writes, response=ACK)])
    server._plc_transport_factory = ack_factory
    try:
        terminal = server.dispatch_plc_for_detection(
            {"request_id": terminal_request, "passed": True},
            source="image", fingerprint=terminal_request,
        )["plc_sync"]
    finally:
        server._plc_transport_factory = None
    assert terminal["status"] == "acknowledged"
    disable_direct()
    terminal_duplicate = server.create_plc_dispatch(
        source="image", request_id=terminal_request, passed=True,
        fingerprint=terminal_request, expected_generation=999,
    )
    assert terminal_duplicate == terminal

    save_enabled(generation=81, retries=0)
    corrupt_request = "runtime-corrupt-terminal"
    corrupt = server.create_plc_dispatch(
        source="image", request_id=corrupt_request, passed=True,
        fingerprint=corrupt_request, expected_generation=81,
    )
    corrupt = seed_dispatch_fixture(
        {
            **corrupt,
            "status": "acknowledged",
            "history": [*corrupt["history"], {"status": "acknowledged", "at": int(time.time())}],
            "attempted": True,
            "worker_done": True,
            "physical_status": "acknowledged",
            "outcome": "acknowledged",
            "acknowledged_targets": ["Y99"],
            "targets": ["Y99"],
            "frames": [{"target": "Y99", "frame_hex": "DEADBEEF", "attempts": 1}],
        }
    )
    before = dict(audit_for(corrupt["dispatch_id"])[0])
    opens = 0

    def forbidden(_config: dict[str, Any]) -> Any:
        nonlocal opens
        opens += 1
        raise AssertionError("corrupt duplicate reached physical I/O")

    server._plc_transport_factory = forbidden
    try:
        direct = server.dispatch_plc_for_detection(
            {"request_id": corrupt_request, "passed": True},
            source="image", fingerprint=corrupt_request,
        )["plc_sync"]
        queued_path = server._run_queued_plc_dispatch(
            {"request_id": corrupt_request, "passed": True},
            source="image", fingerprint=corrupt_request,
        )["plc_sync"]
    finally:
        server._plc_transport_factory = None
    assert direct["error_code"] == "corrupt_persisted_dispatch:projection_mismatch:acknowledged_targets"
    assert queued_path["error_code"] == "corrupt_persisted_dispatch:projection_mismatch:acknowledged_targets"
    assert direct["audit_status"] == queued_path["audit_status"] == "state_conflict"
    assert opens == 0
    assert audit_for(corrupt["dispatch_id"])[0] == before


def test_identity_and_nested_evidence_lattice() -> None:
    bound = seed_dispatch_fixture(
        {
            "record_schema_version": 1,
            "dispatch_id": "identity-bound",
            "source": "image",
            "request_id": "req-a",
            "passed": True,
            "control_generation": 4,
            "config_snapshot": enabled_config(retries=0),
            "protocol": "fx_programming_port_ascii",
            "checksum_mode": "exclude_etx_legacy_vb",
            "planned_targets": ["D206"],
            "planned_frames": [{"target": "D206", "frame_hex": "AA"}],
            "status": "acknowledged",
            "attempted": True,
            "worker_done": True,
            "physical_status": "acknowledged",
            "outcome": "acknowledged",
            "acknowledged_targets": ["D206"],
            "frames": [{"target": "D206", "frame_hex": "AA", "attempts": 1}],
        },
    )
    for field, changed in (
        ("source", "video"),
        ("request_id", "req-b"),
        ("passed", False),
        ("control_generation", 5),
        ("config_snapshot", {**enabled_config(retries=0), "d206_address": "119D"}),
        ("protocol", "other"),
        ("checksum_mode", "include_etx_documented_comment"),
        ("planned_frames", [{"target": "D206", "frame_hex": "BB"}]),
    ):
        try:
            apply_dispatch_fixture(
                {**bound, field: changed},
                expected_version=bound["state_version"],
                transition_kind=server.PlcDispatchTransitionKind.RECORD_UPDATE,
            )
        except server.PlcDispatchStateConflict as exc:
            assert exc.reason.startswith("immutable_identity_conflict")
        else:
            raise AssertionError(f"immutable field {field} was rewritten")
        assert audit_for("identity-bound")[0]["state_version"] == bound["state_version"]
        assert audit_for("identity-bound")[0]["passed"] is True

    enriched = apply_dispatch_fixture(
        {**bound, "message": "allowlisted diagnostic clarification"},
        expected_version=bound["state_version"],
        transition_kind=server.PlcDispatchTransitionKind.RECORD_UPDATE,
    )
    assert enriched["state_version"] == bound["state_version"] + 1
    assert enriched["message"] == "allowlisted diagnostic clarification"
    for mutation in (
        {**enriched, "namespace_present": False},
        {**enriched, "active_attempts": [{"target": "D206", "attempt": 99}]},
        {**enriched, "history": [{"status": "acknowledged", "at": 1}]},
        {**enriched, "duplicate": True},
        {**enriched, "acknowledged_targets": ["D206", "Y99"]},
        {**enriched, "frames": [*enriched["frames"], {"target": "Y99", "frame_hex": "DEADBEEF", "attempts": 77}]},
        {**enriched, "bytes_written": 999},
        {**enriched, "attempts": 999},
        {**enriched, "target": "Y99"},
    ):
        try:
            server.persist_plc_dispatch_record(mutation, expected_version=enriched["state_version"])
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("JSON known-but-nonmutable field mutation was accepted")
        authoritative = audit_for("identity-bound")[0]
        assert authoritative["state_version"] == enriched["state_version"]
        assert authoritative.get("namespace_present") is None
        assert authoritative.get("active_attempts") is None
        assert authoritative.get("history") is None
        assert authoritative.get("duplicate") is None
        assert authoritative["acknowledged_targets"] == ["D206"]
        assert authoritative["frames"] == [{"target": "D206", "frame_hex": "AA", "attempts": 1}]
        assert authoritative.get("bytes_written") is None
        assert authoritative.get("attempts") is None
        assert authoritative.get("target") is None

    forged_operation = {
        "attempt_id": "identity-bound:Y99:77",
        "target": "Y99",
        "attempt": 77,
        "frame_hex": "DEADBEEF",
        "frame_bytes": 4,
        "bytes_written": 4,
        "physical_status": "acknowledged",
        "outcome": "acknowledged",
        "result_code": "acknowledged",
        "diagnostic_source": "forged",
        "started_at": 1,
        "finished_at": 2,
    }
    try:
        server.persist_plc_dispatch_record(
            {**enriched, "operations": [forged_operation]},
            expected_version=enriched["state_version"],
        )
    except server.PlcDispatchStateConflict:
        pass
    else:
        raise AssertionError("JSON forged operation append was accepted")
    assert audit_for("identity-bound")[0]["state_version"] == enriched["state_version"]

    start_seed = seed_dispatch_fixture(
        {
            "dispatch_id": "typed-start-guards",
            "source": "image",
            "request_id": "typed-start-guards",
            "passed": True,
            "status": "attempting",
            "attempted": False,
            "worker_done": False,
            "control_generation": 1,
            "config_snapshot": enabled_config(retries=1),
            "planned_targets": ["D206"],
            "planned_frames": [{"target": "D206", "frame_hex": "AA"}],
        },
    )
    valid_start = {
        "attempt_id": "typed-start-guards:D206:1",
        "target": "D206",
        "attempt": 1,
        "frame_hex": "AA",
        "frame_bytes": 1,
        "bytes_written": 0,
        "physical_status": "not_attempted",
        "outcome": "not_attempted",
        "started_at": 1,
    }
    invalid_attempt_transitions = (
        ({**start_seed, "operations": [{**valid_start, "target": "Y99", "attempt_id": "typed-start-guards:Y99:1"}]}, "start_attempt"),
        ({**start_seed, "operations": [{**valid_start, "frame_hex": "BB"}]}, "start_attempt"),
        ({**start_seed, "operations": [{**valid_start, "attempt": 2, "attempt_id": "typed-start-guards:D206:2"}]}, "start_attempt"),
        ({**start_seed, "operations": [{**valid_start, "finished_at": 2, "result_code": "acknowledged"}]}, "finish_attempt"),
    )
    for mutation, transition_kind in invalid_attempt_transitions:
        try:
            server.persist_plc_dispatch_record(
                mutation,
                expected_version=start_seed["state_version"],
                transition_kind=transition_kind,
            )
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("invalid typed attempt transition was accepted")
        assert audit_for("typed-start-guards")[0]["state_version"] == start_seed["state_version"]
    piggyback = {
        **start_seed,
        "status": "acknowledged",
        "operations": [valid_start],
        "attempt_ids": [valid_start["attempt_id"]],
        "acknowledged_targets": ["Y99"],
        "frames": [{"target": "Y99", "frame_hex": "DEADBEEF", "attempts": 77}],
        "bytes_written": 999,
        "attempts": 999,
        "target": "Y99",
    }
    for transition_kind in ["evil", *[item.value for item in server.PlcDispatchTransitionKind]]:
        try:
            server.persist_plc_dispatch_record(
                dict(piggyback),
                expected_version=start_seed["state_version"],
                transition_kind=transition_kind,
            )
        except server.PlcDispatchStateConflict as exc:
            assert exc.reason == "public_raw_transition_kind_not_allowed"
        else:
            raise AssertionError(f"public raw transition-kind bypass was accepted: {transition_kind}")
        assert audit_for("typed-start-guards")[0]["state_version"] == start_seed["state_version"]
    try:
        server.persist_plc_dispatch_record(
            dict(piggyback), expected_version=start_seed["state_version"]
        )
    except server.PlcDispatchStateConflict:
        pass
    else:
        raise AssertionError("public whole-record projection bypass was accepted")
    assert audit_for("typed-start-guards")[0]["state_version"] == start_seed["state_version"]

    failed = seed_dispatch_fixture(
        {
            "dispatch_id": "nested-failure",
            "source": "image",
            "request_id": "nested-failure",
            "passed": True,
            "status": "failed",
            "attempted": True,
            "worker_done": True,
            "physical_status": "partial_write",
            "outcome": "outcome_uncertain",
            "error_code": "short_write",
            "failed_target": "D206",
            "failed_operation": {
                "attempt_id": "nested-failure:D206:1",
                "target": "D206",
                "frame_hex": "AABB",
                "frame_bytes": 2,
                "bytes_written": 1,
                "attempts": 1,
                "physical_status": "partial_write",
                "outcome": "outcome_uncertain",
                "diagnostic_source": "fake",
            },
            "operations": [
                {
                    "attempt_id": "nested-failure:D206:1",
                    "target": "D206",
                    "attempt": 1,
                    "frame_hex": "AABB",
                    "frame_bytes": 2,
                    "bytes_written": 1,
                    "physical_status": "partial_write",
                    "outcome": "outcome_uncertain",
                    "result_code": "short_write",
                    "diagnostic_source": "fake",
                }
            ],
        },
    )
    corruptions = [
        {**failed, "failed_target": ""},
        {**failed, "failed_operation": {}},
        {**failed, "failed_operation": {**failed["failed_operation"], "bytes_written": 0}},
        {**failed, "failed_operation": {**failed["failed_operation"], "frame_bytes": 999}},
        {**failed, "failed_operation": {**failed["failed_operation"], "target": "Y04"}},
        {**failed, "failed_operation": {**failed["failed_operation"], "outcome": "not_written"}},
        {**failed, "operations": []},
        {
            **failed,
            "operations": [{**failed["operations"][0], "physical_status": "not_written"}],
        },
        {
            **failed,
            "operations": [{**failed["operations"][0], "unexpected_nested": True}],
        },
        {**failed, "unexpected_mutation": True},
    ]
    for corruption in corruptions:
        try:
            apply_dispatch_fixture(
                corruption,
                expected_version=failed["state_version"],
                transition_kind=server.PlcDispatchTransitionKind.RECORD_UPDATE,
            )
        except server.PlcDispatchStateConflict:
            pass
        else:
            raise AssertionError("nested physical evidence corruption was accepted")
        assert audit_for("nested-failure")[0]["state_version"] == failed["state_version"]

    legacy = seed_dispatch_fixture(
        {
            "dispatch_id": "legacy-opaque",
            "status": "queued",
            "attempted": False,
            "worker_done": False,
            "legacy_vendor_field": {"keep": True},
        },
    )
    legacy_next = apply_dispatch_fixture(
        {**legacy, "status": "attempting"},
        expected_version=legacy["state_version"],
        transition_kind=server.PlcDispatchTransitionKind.DISPATCH_TRANSITION,
    )
    assert legacy_next["legacy_vendor_field"] == {"keep": True}
    try:
        without_legacy = {key: value for key, value in legacy_next.items() if key != "legacy_vendor_field"}
        apply_dispatch_fixture(
            without_legacy,
            expected_version=legacy_next["state_version"],
            transition_kind=server.PlcDispatchTransitionKind.RECORD_UPDATE,
        )
    except server.PlcDispatchStateConflict as exc:
        assert exc.reason == "legacy_unknown_field_is_immutable:legacy_vendor_field"
    else:
        raise AssertionError("legacy opaque field deletion was accepted")

    retry = ScriptedFactory(
        [
            lambda writes: ScriptedTransport(writes, response=NAK),
            lambda writes: ScriptedTransport(writes, response=ACK),
        ]
    )
    retried = dispatch_detection_result(
        dispatch_id="retry-operation-evidence",
        source="image",
        request_id="retry-operation-evidence",
        passed=True,
        config=enabled_config(retries=1),
        transport_factory=retry,
    )
    assert retried["status"] == "acknowledged"
    assert len(retried["operations"]) == 2
    assert retried["operations"][0]["outcome"] == "rejected"
    assert retried["operations"][1]["outcome"] == "acknowledged"

    save_enabled(retries=1)
    typed_retry_factory = ScriptedFactory(
        [
            lambda writes: ScriptedTransport(writes, response=NAK),
            lambda writes: ScriptedTransport(writes, response=ACK),
        ]
    )
    server._plc_transport_factory = typed_retry_factory
    try:
        typed_result = server.dispatch_plc_for_detection(
            {"request_id": "typed-retry-evidence", "passed": True},
            source="image",
            fingerprint="typed-retry-evidence",
        )["plc_sync"]
    finally:
        server._plc_transport_factory = None
    assert typed_result["status"] == "acknowledged", typed_result
    assert [item["attempt"] for item in typed_result["operations"]] == [1, 2]
    assert [item["outcome"] for item in typed_result["operations"]] == ["rejected", "acknowledged"]
    assert all(item.get("started_at") is not None and item.get("finished_at") is not None for item in typed_result["operations"])


def test_strict_persisted_config_pollution_and_recovery(admin: Any) -> None:
    bad_values = {
        "baudrate": "9600",
        "data_bits": "7",
        "stop_bits": True,
        "timeout": float("nan"),
        "retries": "1",
        "protocol": 7,
        "checksum_mode": False,
        "serial_port": 3,
        "parity": 0,
        "d206_address": 4508,
        "y04_address": 108,
    }
    for index, (field, bad) in enumerate(bad_values.items()):
        opens = 0

        def forbidden(_config: dict[str, Any]) -> Any:
            nonlocal opens
            opens += 1
            raise AssertionError("polluted config opened transport")

        polluted = {**enabled_config(retries=0), field: bad}
        result = dispatch_detection_result(
            dispatch_id=f"polluted-direct-{index}",
            source="image",
            request_id=f"polluted-direct-{index}",
            passed=True,
            config=polluted,
            transport_factory=forbidden,
        )
        assert result["error_code"] == "invalid_config"
        assert result["attempted"] is False
        assert opens == 0

    polluted = {**enabled_config(retries=0), "timeout": float("inf")}
    server.mutate_app_config_atomically(lambda config: config.__setitem__("plc", polluted))
    diagnostic = server.plc_config_response()
    assert diagnostic["effective_enabled"] is False
    assert diagnostic["validation_errors"]
    opens = 0

    def forbidden(_config: dict[str, Any]) -> Any:
        nonlocal opens
        opens += 1
        raise AssertionError("persisted polluted config opened transport")

    server._plc_transport_factory = forbidden
    try:
        dispatched = server.dispatch_plc_for_detection(
            {"request_id": "polluted-json", "passed": True},
            source="image",
            fingerprint="polluted-json",
        )
    finally:
        server._plc_transport_factory = None
    assert dispatched["plc_sync"]["error_code"] == "invalid_config"
    assert dispatched["plc_sync"]["attempted"] is False
    assert opens == 0

    generation_before = int(server.load_config().get(server.PLC_CONTROL_GENERATION_KEY) or 0)
    legal = enabled_config(retries=0)
    repaired = admin.post("/api/plc/config", json=legal)
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["effective_enabled"] is True
    assert repaired.json()["control_generation"] > generation_before

    for index, malformed in enumerate((None, [], "bad", 7, False)):
        server.mutate_app_config_atomically(lambda config, value=malformed: config.__setitem__("plc", value))
        diagnostic = server.plc_config_response()
        assert diagnostic["effective_enabled"] is False
        assert diagnostic["validation_errors"], (index, diagnostic)
        opens = 0

        def forbidden_namespace(_config: dict[str, Any]) -> Any:
            nonlocal opens
            opens += 1
            raise AssertionError("malformed namespace opened transport")

        server._plc_transport_factory = forbidden_namespace
        try:
            result = server.dispatch_plc_for_detection(
                {"request_id": f"malformed-namespace-{index}", "passed": True},
                source="image",
                fingerprint=f"malformed-namespace-{index}",
            )
        finally:
            server._plc_transport_factory = None
        assert result["plc_sync"]["error_code"] == "invalid_config"
        assert result["plc_sync"]["attempted"] is False
        assert opens == 0
        repair = admin.post("/api/plc/config", json=enabled_config(retries=0))
        assert repair.status_code == 200, repair.text

    server.mutate_app_config_atomically(lambda config: config.pop("plc", None))
    absent = server.plc_config_response()
    assert absent["config"] == DEFAULT_PLC_CONFIG
    assert absent["validation_errors"] == []
    assert absent["effective_enabled"] is False


def bootstrap_admin() -> Any:
    client = TestClient(server.app)
    response = client.post(
        "/api/auth/bootstrap",
        json={"username": "hardening_admin", "password": "hardening-password-123", "display_name": "Hardening Admin"},
    )
    if response.status_code != 200:
        login = client.post(
            "/api/auth/login",
            json={"username": "hardening_admin", "password": "hardening-password-123"},
        )
        assert login.status_code == 200, login.text
    return client


async def test_disable_barriers_and_event_loop(admin: Any) -> None:
    # Disable between retry attempts.
    save_enabled(retries=1)
    read_started = threading.Event()
    read_release = threading.Event()
    retry_factory = ScriptedFactory(
        [lambda writes: ScriptedTransport(writes, response=NAK, read_started=read_started, read_release=read_release)]
    )
    server._plc_transport_factory = retry_factory
    task = asyncio.create_task(
        server.dispatch_plc_for_detection_async(
            {"request_id": "disable-between-retries", "passed": True},
            source="image",
            fingerprint="disable-between-retries",
        )
    )
    assert await asyncio.to_thread(read_started.wait, 2)
    disabled = await asyncio.to_thread(admin.post, "/api/plc/config", json={"enabled": False})
    assert disabled.status_code == 200
    read_release.set()
    result = await task
    assert result["plc_sync"].get("error_code") == "cancelled_after_disable", result["plc_sync"]
    assert retry_factory.writes == [build_d206_frame("119C", True)]

    # Disable after D206 ACK but before Y04 starts.
    save_enabled(retries=0, write_y04=True)
    read_started = threading.Event()
    read_release = threading.Event()
    target_factory = ScriptedFactory(
        [lambda writes: ScriptedTransport(writes, response=ACK, read_started=read_started, read_release=read_release)]
    )
    server._plc_transport_factory = target_factory
    task = asyncio.create_task(
        server.dispatch_plc_for_detection_async(
            {"request_id": "disable-before-y04", "passed": False},
            source="video",
            fingerprint="disable-before-y04",
        )
    )
    assert await asyncio.to_thread(read_started.wait, 2)
    disabled = await asyncio.to_thread(admin.post, "/api/plc/config", json={"enabled": False})
    assert disabled.status_code == 200
    read_release.set()
    result = await task
    sync = result["plc_sync"]
    assert sync["error_code"] == "cancelled_after_disable"
    assert sync["acknowledged_targets"] == ["D206"]
    assert sync["failed_target"] == "Y04"
    assert target_factory.writes == [build_d206_frame("119C", False)]

    # Disable and status calls remain responsive while a write already started.
    save_enabled(retries=0, write_y04=True)
    write_started = threading.Event()
    write_release = threading.Event()
    blocking = ScriptedFactory(
        [lambda writes: ScriptedTransport(writes, response=ACK, write_started=write_started, write_release=write_release)]
    )
    server._plc_transport_factory = blocking
    task = asyncio.create_task(
        server.dispatch_plc_for_detection_async(
            {"request_id": "disable-during-write", "passed": True},
            source="image",
            fingerprint="disable-during-write",
        )
    )
    assert await asyncio.to_thread(write_started.wait, 2)
    started = time.monotonic()
    status = await asyncio.to_thread(admin.get, "/api/plc/config")
    disabled = await asyncio.to_thread(admin.post, "/api/plc/config", json={"enabled": False})
    elapsed = time.monotonic() - started
    assert status.status_code == 200 and status.json()["in_flight_attempts"]
    assert disabled.status_code == 200
    assert elapsed < 1.0, elapsed
    write_release.set()
    result = await task
    sync = result["plc_sync"]
    assert sync["attempted"] is True
    assert sync["error_code"] == "cancelled_after_disable"
    assert blocking.writes == [build_d206_frame("119C", True)]

    opens_before = blocking.opens
    after = await server.dispatch_plc_for_detection_async(
        {"request_id": "new-after-disable", "passed": True},
        source="image",
        fingerprint="new-after-disable",
    )
    assert after["plc_sync"]["status"] == "disabled"
    assert blocking.opens == opens_before
    server._plc_transport_factory = None


async def test_generation_epoch_cancels_old_config(admin: Any) -> None:
    save_enabled(retries=1, d206_address="119C")
    read_started = threading.Event()
    read_release = threading.Event()
    retry = ScriptedFactory(
        [lambda writes: ScriptedTransport(writes, response=NAK, read_started=read_started, read_release=read_release)]
    )
    server._plc_transport_factory = retry
    task = asyncio.create_task(
        server.dispatch_plc_for_detection_async(
            {"request_id": "config-change-between-retries", "passed": True},
            source="image",
            fingerprint="config-change-between-retries",
        )
    )
    assert await asyncio.to_thread(read_started.wait, 2)
    generation_before = int(server.load_config().get(server.PLC_CONTROL_GENERATION_KEY) or 0)
    changed = await asyncio.to_thread(admin.post, "/api/plc/config", json={"d206_address": "119D"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["control_generation"] == generation_before + 1
    read_release.set()
    result = await task
    assert result["plc_sync"]["error_code"] == "cancelled_after_config_change"
    assert retry.writes == [build_d206_frame("119C", True)]

    save_enabled(retries=0, write_y04=True, checksum_mode="exclude_etx_legacy_vb")
    read_started = threading.Event()
    read_release = threading.Event()
    targets = ScriptedFactory(
        [lambda writes: ScriptedTransport(writes, response=ACK, read_started=read_started, read_release=read_release)]
    )
    server._plc_transport_factory = targets
    task = asyncio.create_task(
        server.dispatch_plc_for_detection_async(
            {"request_id": "config-change-between-targets", "passed": False},
            source="video",
            fingerprint="config-change-between-targets",
        )
    )
    assert await asyncio.to_thread(read_started.wait, 2)
    generation_before = int(server.load_config().get(server.PLC_CONTROL_GENERATION_KEY) or 0)
    changed = await asyncio.to_thread(
        admin.post,
        "/api/plc/config",
        json={"checksum_mode": "include_etx_documented_comment", "write_y04": False},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["control_generation"] == generation_before + 1
    read_release.set()
    result = await task
    sync = result["plc_sync"]
    assert sync["error_code"] == "cancelled_after_config_change"
    assert sync["acknowledged_targets"] == ["D206"]
    assert sync["config_snapshot"]["checksum_mode"] == "exclude_etx_legacy_vb"
    assert targets.writes == [build_d206_frame("119C", False)]

    generation_before = int(server.load_config().get(server.PLC_CONTROL_GENERATION_KEY) or 0)
    same_address = server.load_config()["plc"]["d206_address"]
    equal = await asyncio.to_thread(admin.post, "/api/plc/config", json={"d206_address": same_address})
    assert equal.status_code == 200
    assert equal.json()["control_generation"] == generation_before
    server._plc_transport_factory = None


async def test_queue_timeout_and_queue_disable(admin: Any) -> None:
    original_queue_timeout = server.PLC_QUEUE_WAIT_SECONDS
    server.PLC_QUEUE_WAIT_SECONDS = 0.08
    opens = 0

    def forbidden(_config: dict[str, Any]) -> Any:
        nonlocal opens
        opens += 1
        raise AssertionError("queue-timeout dispatch opened transport")

    server._plc_transport_factory = forbidden
    try:
        save_enabled(retries=0)
        assert server._plc_dispatch_slots.acquire(timeout=1)
        try:
            pure = await server.dispatch_plc_for_detection_async(
                {"request_id": "pure-queue-timeout", "passed": True},
                source="image",
                fingerprint="pure-queue-timeout",
            )
        finally:
            server._plc_dispatch_slots.release()
        sync = pure["plc_sync"]
        assert sync["error_code"] == "plc_dispatch_queue_timeout"
        assert sync["attempted"] is False
        assert len(audit_for(sync["dispatch_id"])) == 1

        save_enabled(retries=0)
        assert server._plc_dispatch_slots.acquire(timeout=1)
        try:
            pending = asyncio.create_task(
                server.dispatch_plc_for_detection_async(
                    {"request_id": "queue-disable", "passed": True},
                    source="image",
                    fingerprint="queue-disable",
                )
            )
            queue_disable_id, _, _ = server.plc_dispatch_identity(
                {"request_id": "queue-disable", "passed": True},
                source="image",
                fingerprint="queue-disable",
            )

            def wait_until_queued() -> bool:
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    if audit_for(queue_disable_id):
                        return True
                    time.sleep(0.005)
                return False

            assert await asyncio.to_thread(wait_until_queued)
            disabled = await asyncio.to_thread(admin.post, "/api/plc/config", json={"enabled": False})
            assert disabled.status_code == 200
            queued = await pending
        finally:
            server._plc_dispatch_slots.release()
        sync = queued["plc_sync"]
        assert sync["status"] == "disabled"
        assert sync["error_code"] == "cancelled_after_disable"
        assert sync["attempted"] is False
        assert len(audit_for(sync["dispatch_id"])) == 1
        assert opens == 0
    finally:
        server.PLC_QUEUE_WAIT_SECONDS = original_queue_timeout
        server._plc_transport_factory = None


async def test_attempt_declaration_linearization(admin: Any) -> None:
    original_dispatch = server.dispatch_fx_plc_detection_result

    # Config commits first: the start callback rechecks under the same lock as typed start.
    save_enabled(generation=90, retries=0, d206_address="119C")
    before_start = threading.Event()
    start_release = threading.Event()
    config_first_factory = ScriptedFactory(
        [lambda writes: ScriptedTransport(writes, response=ACK)]
    )

    def config_first_dispatch(**kwargs: Any) -> dict[str, Any]:
        original_start = kwargs["on_attempt_started"]

        def pause_before_start(target: str, attempt: int, frame: bytes) -> dict[str, Any]:
            before_start.set()
            assert start_release.wait(5)
            return original_start(target, attempt, frame)

        return original_dispatch(**{**kwargs, "on_attempt_started": pause_before_start})

    server.dispatch_fx_plc_detection_result = config_first_dispatch
    server._plc_transport_factory = config_first_factory
    try:
        pending = asyncio.create_task(
            server.dispatch_plc_for_detection_async(
                {"request_id": "config-first-linearization", "passed": True},
                source="image",
                fingerprint="config-first-linearization",
            )
        )
        assert await asyncio.to_thread(before_start.wait, 2)
        changed = await asyncio.to_thread(
            admin.post, "/api/plc/config", json={"d206_address": "119D"}
        )
        assert changed.status_code == 200
        assert changed.json()["control_generation"] == 91
        start_release.set()
        result = await pending
    finally:
        start_release.set()
        server.dispatch_fx_plc_detection_result = original_dispatch
        server._plc_transport_factory = None
    sync = result["plc_sync"]
    assert sync["error_code"] == "cancelled_after_config_change", sync
    assert sync["attempted"] is False
    assert config_first_factory.opens == 0
    assert config_first_factory.writes == []

    # Attempt declaration commits first: config response observes in-flight; exactly that attempt may finish.
    save_enabled(generation=100, retries=0, d206_address="119C", write_y04=True)
    after_start = threading.Event()
    attempt_release = threading.Event()
    attempt_first_factory = ScriptedFactory(
        [lambda writes: ScriptedTransport(writes, response=ACK)]
    )

    def attempt_first_dispatch(**kwargs: Any) -> dict[str, Any]:
        original_start = kwargs["on_attempt_started"]

        def pause_after_start(target: str, attempt: int, frame: bytes) -> dict[str, Any]:
            operation = original_start(target, attempt, frame)
            after_start.set()
            assert attempt_release.wait(5)
            return operation

        return original_dispatch(**{**kwargs, "on_attempt_started": pause_after_start})

    server.dispatch_fx_plc_detection_result = attempt_first_dispatch
    server._plc_transport_factory = attempt_first_factory
    try:
        pending = asyncio.create_task(
            server.dispatch_plc_for_detection_async(
                {"request_id": "attempt-first-linearization", "passed": True},
                source="image",
                fingerprint="attempt-first-linearization",
            )
        )
        assert await asyncio.to_thread(after_start.wait, 2)
        changed = await asyncio.to_thread(
            admin.post,
            "/api/plc/config",
            json={"d206_address": "119D", "write_y04": False},
        )
        assert changed.status_code == 200
        payload = changed.json()
        assert payload["control_generation"] == 101
        assert any(
            item.get("dispatch_id") == server.plc_dispatch_identity(
                {"request_id": "attempt-first-linearization", "passed": True},
                source="image",
                fingerprint="attempt-first-linearization",
            )[0]
            for item in payload["in_flight_attempts"]
        )
        attempt_release.set()
        result = await pending
    finally:
        attempt_release.set()
        server.dispatch_fx_plc_detection_result = original_dispatch
        server._plc_transport_factory = None
    sync = result["plc_sync"]
    assert sync["error_code"] == "cancelled_after_config_change", sync
    assert sync["attempted"] is True
    assert sync["acknowledged_targets"] == ["D206"]
    assert attempt_first_factory.opens == 1
    assert attempt_first_factory.writes == [build_d206_frame("119C", True)]


async def test_total_deadline_before_and_after_attempt() -> None:
    original_total = server.PLC_WORKER_TOTAL_TIMEOUT_SECONDS
    original_dispatch = server.dispatch_plc_for_detection
    server.PLC_WORKER_TOTAL_TIMEOUT_SECONDS = 0.5
    try:
        # Deadline before transport: background cleanup must not start I/O later.
        save_enabled(retries=0)
        before_gate = threading.Event()
        gate_release = threading.Event()
        worker_finished = threading.Event()
        opens = 0

        def forbidden(_config: dict[str, Any]) -> Any:
            nonlocal opens
            opens += 1
            raise AssertionError("deadline-before-attempt opened transport")

        def paused_dispatch(*args: Any, **kwargs: Any) -> dict[str, Any]:
            before_gate.set()
            assert gate_release.wait(5)
            try:
                return original_dispatch(*args, **kwargs)
            finally:
                worker_finished.set()

        server._plc_transport_factory = forbidden
        server.dispatch_plc_for_detection = paused_dispatch
        pending = asyncio.create_task(
            server.dispatch_plc_for_detection_async(
                {"request_id": "deadline-before-attempt", "passed": True},
                source="image",
                fingerprint="deadline-before-attempt",
            )
        )
        assert await asyncio.to_thread(before_gate.wait, 2)
        response = await pending
        snapshot = response["plc_sync"]
        assert snapshot["attempted"] is False
        assert snapshot["physical_status"] == "not_attempted"
        assert snapshot["deadline_exceeded"] is True
        assert snapshot["worker_continues"] is False
        snapshot_version = snapshot["state_version"]
        gate_release.set()
        assert await asyncio.to_thread(worker_finished.wait, 2)
        final = wait_worker_done(snapshot["dispatch_id"])
        assert final["attempted"] is False
        assert final["state_version"] > snapshot_version
        assert len(audit_for(snapshot["dispatch_id"])) == 1
        assert opens == 0

        # Deadline after a blocking write began: snapshot is uncertain, final is newer.
        server.dispatch_plc_for_detection = original_dispatch
        save_enabled(retries=0)
        write_started = threading.Event()
        write_release = threading.Event()
        blocking = ScriptedFactory(
            [lambda writes: ScriptedTransport(writes, response=ACK, write_started=write_started, write_release=write_release)]
        )
        server._plc_transport_factory = blocking
        pending = asyncio.create_task(
            server.dispatch_plc_for_detection_async(
                {"request_id": "deadline-during-attempt", "passed": True},
                source="image",
                fingerprint="deadline-during-attempt",
            )
        )
        assert await asyncio.to_thread(write_started.wait, 2)
        response = await pending
        snapshot = response["plc_sync"]
        assert snapshot["attempted"] is True, snapshot
        assert snapshot["outcome"] == "outcome_uncertain"
        assert snapshot["worker_continues"] is True, snapshot
        assert snapshot["active_attempts"]
        snapshot_version = snapshot["state_version"]
        write_release.set()
        final = wait_worker_done(snapshot["dispatch_id"])
        assert final["attempted"] is True
        assert final["deadline_exceeded"] is True
        assert final["worker_continues"] is False
        assert final["state_version"] > snapshot_version
        assert len(audit_for(snapshot["dispatch_id"])) == 1
        assert blocking.writes == [build_d206_frame("119C", True)]
    finally:
        server.PLC_WORKER_TOTAL_TIMEOUT_SECONDS = original_total
        server.dispatch_plc_for_detection = original_dispatch
        server._plc_transport_factory = None


def main() -> None:
    admin = bootstrap_admin()
    test_partial_write_and_full_write_flush_failure()
    test_multiframe_partial_success_preserves_receipts()
    test_server_terminal_result_contract_matrix()
    test_shared_retry_policy_actual_server_matrix()
    test_atomic_config_audit_read_modify_write()
    test_protected_namespace_rejects_stale_generic_saves_json_and_pg()
    test_restart_hydration_cas_and_no_replay()
    test_control_state_failures_preserve_ack_evidence()
    test_strict_create_boundary_json()
    test_actual_typed_handler_boundary_json_and_pg()
    test_persisted_duplicate_verifier_and_runtime_paths()
    test_identity_and_nested_evidence_lattice()
    test_strict_persisted_config_pollution_and_recovery(admin)
    asyncio.run(test_disable_barriers_and_event_loop(admin))
    asyncio.run(test_generation_epoch_cancels_old_config(admin))
    asyncio.run(test_attempt_declaration_linearization(admin))
    asyncio.run(test_queue_timeout_and_queue_disable(admin))
    asyncio.run(test_total_deadline_before_and_after_attempt())
    print("smoke_plc_phase1_hardening: ok")


if __name__ == "__main__":
    main()
