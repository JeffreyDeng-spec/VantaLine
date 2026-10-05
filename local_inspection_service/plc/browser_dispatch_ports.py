"""Explicit persistence, ownership, immutable-plan and receipt capabilities."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from ..plc_fx_ascii import PlcConfigError
Record = dict[str, Any]
DispatchState = dict[str, Record | None]

class PlcWebSerialAttemptRequest(Protocol):
    session_id: str
    lease_epoch: int
    config_generation: int

class ReceiptOperation(Protocol):
    def model_dump(self) -> Record: ...

class PlcWebSerialReceiptRequest(Protocol):
    session_id: str
    lease_epoch: int
    attempt_token: str
    outcome: str
    operations: Sequence[ReceiptOperation]

class MutateDispatch(Protocol):
    def __call__(self, station_id: str, dispatch_id: str | None, mutator: Callable[[DispatchState], None]) -> DispatchState: ...

class ActiveLease(Protocol):
    def __call__(self, state: DispatchState, session_id: str, lease_epoch: int | None = None) -> tuple[Record, Record, int]: ...

class VerifyDispatch(Protocol):
    def __call__(self, record: Record, station: Record, *, require_frames: bool = True, require_current_config: bool = True) -> None: ...

@dataclass(frozen=True)
class BrowserDispatchStorage:
    _plc_web_serial_record: Callable[[], Callable[[Any], Record | None]]
    _plc_web_serial_mutate: Callable[[], MutateDispatch]
    _plc_web_serial_dispatch_row: Callable[[], Callable[[Record], Record]]
    _plc_workstation_lease_row: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class BrowserDispatchIdentity:
    _plc_web_serial_require_active_lease: Callable[[], ActiveLease]
    _plc_web_serial_token_hash: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class BrowserDispatchPolicy:
    PlcConfigError: Callable[[], type[PlcConfigError]]
    LEGACY_WEB_SERIAL_PROTOCOL_VERSION: Callable[[], str]
    WEB_SERIAL_PROTOCOL_VERSION: Callable[[], str]
    WEB_SERIAL_PLAN_DEADLINE_SECONDS: Callable[[], float]
    PLC_PROTOCOL_ID: Callable[[], str]
    build_legacy_web_serial_plan: Callable[[], Callable[[Record, bool], list[Record]]]
    build_web_serial_plan: Callable[[], Callable[[Record, bool], list[Record]]]
    normalize_legacy_web_serial_config: Callable[[], Callable[[Record], Record]]
    normalize_web_serial_config: Callable[[], Callable[[Record], Record]]
    migrate_web_serial_config: Callable[[], Callable[[Record], Record]]
    legacy_web_serial_config_fingerprint: Callable[[], Callable[[Record], str]]
    web_serial_config_fingerprint: Callable[[], Callable[[Record], str]]

@dataclass(frozen=True)
class BrowserDispatchProjection:
    verify_plc_web_serial_dispatch: Callable[[], VerifyDispatch]
    _plc_web_serial_receipt_outcome: Callable[[], Callable[[list[Record], list[Record]], str]]
    plc_web_serial_dispatch_public: Callable[[], Callable[[Record], Record]]
