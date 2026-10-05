"""Capabilities for retained legacy dispatch compatibility; no service startup here."""
from collections.abc import Callable, Mapping, Set
from concurrent.futures import Executor
from contextlib import AbstractContextManager
from dataclasses import dataclass
from threading import Event, Semaphore
from typing import Any
from ..plc_fx_ascii import PlcAttemptTerminalResult, PlcConfigError, PlcTerminalResultCode, PlcTransportError, PlcTransportPhase
from .errors import PlcDispatchStateConflict
Record = dict[str, Any]

@dataclass(frozen=True)
class LegacyDispatchPolicy:
    PLC_CONTROL_GENERATION_KEY: Callable[[], str]
    PLC_FINALIZE_REASONS: Callable[[], Set[str]]
    PLC_QUEUE_WAIT_SECONDS: Callable[[], float]
    PLC_WORKER_TOTAL_TIMEOUT_SECONDS: Callable[[], float]
    PLC_TERMINAL_ALLOWED_PHASES: Callable[[], Mapping[PlcTerminalResultCode, Set[PlcTransportPhase]]]
    PLC_TERMINAL_DIAGNOSTIC_SOURCES: Callable[[], Mapping[PlcTerminalResultCode, Set[str]]]
    PlcAttemptTerminalResult: Callable[[], type[PlcAttemptTerminalResult]]
    PlcConfigError: Callable[[], type[PlcConfigError]]
    PlcDispatchStateConflict: Callable[[], type[PlcDispatchStateConflict]]
    PlcTerminalResultCode: Callable[[], type[PlcTerminalResultCode]]
    PlcTransportError: Callable[[], type[PlcTransportError]]
    PlcTransportPhase: Callable[[], type[PlcTransportPhase]]

@dataclass(frozen=True)
class LegacyDispatchConfiguration:
    load_config: Callable[[], Callable[[], Record]]
    normalize_plc_config: Callable[[], Callable[[Any], Record]]
    raw_plc_namespace: Callable[[], Callable[[Record], Any]]
    plc_activation_errors: Callable[[], Callable[[Record], list[dict[str, str]]]]
    plc_config_audit_snapshot: Callable[[], Callable[[Record], Record]]
    plc_claim_or_renew_io_owner: Callable[[], Callable[[], Record | None]]
    plc_current_process_owns_io: Callable[[], Callable[[int], bool]]

@dataclass(frozen=True)
class LegacyDispatchRecords:
    plc_dispatch_identity: Callable[[], Callable[..., tuple[str, str, bool]]]
    get_validated_idempotent_dispatch: Callable[[], Callable[..., Record | None]]
    plc_dispatch_record_is_terminal: Callable[[], Callable[[Record], bool]]
    plc_dispatch_is_pristine_queue: Callable[[], Callable[[Record], bool]]
    plc_dispatch_adoption_blocker: Callable[[], Callable[..., str]]
    create_plc_dispatch: Callable[[], Callable[..., Record]]
    plc_transition_attempting: Callable[[], Callable[..., Record]]
    plc_advance_attempt: Callable[[], Callable[..., Record]]
    plc_finalize_dispatch: Callable[[], Callable[..., Record]]
    plc_start_attempt: Callable[[], Callable[..., Record]]
    plc_finish_attempt: Callable[[], Callable[..., Record]]
    plc_dispatch_conflict_response: Callable[[], Callable[..., Record]]

@dataclass(frozen=True)
class LegacyDispatchExecution:
    _config_io_lock: Callable[[], AbstractContextManager]
    _plc_active_attempts: Callable[[], dict[str, Record]]
    _plc_runtime_entry: Callable[[], Callable[[str], Record]]
    _register_plc_dispatch_runtime: Callable[[], Callable[[str], None]]
    _plc_deadline_snapshot: Callable[[], Callable[..., Record]]
    _plc_dispatch_slots: Callable[[], Semaphore]
    _plc_write_pending: Callable[[], Event]
    _plc_io_executor: Callable[[], Executor]
    _plc_transport_factory: Callable[[], Callable[[Record], Any] | None]
    dispatch_fx_plc_detection_result: Callable[[], Callable[..., Record]]
    dispatch_plc_for_detection: Callable[[], Callable[..., Record]]
    _run_queued_plc_dispatch: Callable[[], Callable[..., Record]]
