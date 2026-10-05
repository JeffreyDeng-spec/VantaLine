"""Focused transaction, policy, event and evidence capabilities for dispatch records."""
from collections.abc import Callable, Collection, Mapping, Set
from dataclasses import dataclass
from typing import Any, Protocol
from ..plc_fx_ascii import PlcConfigError, PlcAttemptTerminalResult, PlcTerminalResultCode, PlcTransportPhase
from .errors import PlcDispatchStateConflict
from .transition_policy import PlcDispatchTransitionKind
Record = dict[str, Any]

class ApplyEvent(Protocol):
    def __call__(self, dispatch_id: str, *, expected_version: int, transition_kind: PlcDispatchTransitionKind, event_payload: Record) -> Record: ...

class ValidateTransition(Protocol):
    def __call__(self, existing: Record, candidate: Record, *, transition_kind: PlcDispatchTransitionKind) -> None: ...

class FinalizeDispatch(Protocol):
    def __call__(self, dispatch_id: str, *, expected_version: int, reason: str = "") -> Record: ...

@dataclass(frozen=True)
class DispatchMutationStorage:
    runtime_postgres_repository_or_none: Callable[[], Callable[[], object | None]]
    mutate_app_config_atomically: Callable[[], Callable[[Callable[[Record], None]], Any]]
    plc_dispatch_audit_records: Callable[[], Callable[[Record], list[Record]]]
    verify_persisted_plc_dispatch: Callable[[], Callable[[Record], Record]]
    raw_plc_namespace: Callable[[], Callable[[Record], Any]]
    plc_pg_coordination_available: Callable[[], Callable[[], bool]]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]
    plc_dispatch_existing: Callable[[], Callable[[str], Record | None]]

@dataclass(frozen=True)
class DispatchMutationPolicy:
    PlcDispatchStateConflict: Callable[[], type[PlcDispatchStateConflict]]
    PLC_CONFIG_ABSENT: Callable[[], object]
    normalize_plc_config: Callable[[], Callable[[Any], Record]]
    PlcConfigError: Callable[[], type[PlcConfigError]]
    PLC_CONTROL_GENERATION_KEY: Callable[[], str]
    build_plc_dispatch_plan: Callable[[], Callable[[Record, bool], tuple[list[str], list[Record]]]]
    PLC_RECORD_SCHEMA_VERSION: Callable[[], int]
    PLC_PROTOCOL_CONTRACT_VERSION: Callable[[], int]
    PLC_QUEUE_WAIT_SECONDS: Callable[[], float]
    PLC_FINALIZE_REASONS: Callable[[], Collection[str]]

@dataclass(frozen=True)
class DispatchMutationEvents:
    project_plc_dispatch_events: Callable[[], Callable[[Record, list[Record]], Record]]
    PlcDispatchTransitionKind: Callable[[], type[PlcDispatchTransitionKind]]
    _PLC_TYPED_EVENT_DERIVERS: Callable[[], Mapping[PlcDispatchTransitionKind, Callable[[Record, Record], Record]]]
    _PLC_TYPED_EVENT_FIELDS: Callable[[], Mapping[PlcDispatchTransitionKind, Set[str]]]
    validate_plc_dispatch_transition: Callable[[], ValidateTransition]
    _apply_plc_dispatch_event: Callable[[], ApplyEvent]
    plc_finalize_dispatch: Callable[[], FinalizeDispatch]

@dataclass(frozen=True)
class DispatchMutationEvidence:
    PlcAttemptTerminalResult: Callable[[], type[PlcAttemptTerminalResult]]
    PlcTerminalResultCode: Callable[[], type[PlcTerminalResultCode]]
    PLC_TERMINAL_RESULT_CODES: Callable[[], Collection[PlcTerminalResultCode]]
    PlcTransportPhase: Callable[[], type[PlcTransportPhase]]
    PLC_TERMINAL_ALLOWED_PHASES: Callable[[], Mapping[PlcTerminalResultCode, Collection[PlcTransportPhase]]]
    PLC_TERMINAL_DIAGNOSTIC_SOURCES: Callable[[], Mapping[PlcTerminalResultCode, Collection[str]]]
