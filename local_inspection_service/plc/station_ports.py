"""Typed workstation storage, identity, policy and public projection capabilities."""
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from fastapi import HTTPException, Request
from ..plc_fx_ascii import PlcConfigError
Record = dict[str, Any]
StationState = dict[str, Record | None]

class StationRepository(Protocol):
    def fetch_one_by_columns(self, table: str, columns: Record) -> Record | None: ...
    def fetch_by_primary_key(self, table: str, primary_key: Record) -> Record | None: ...
    def fetch_all(self, table: str) -> list[Record]: ...

class MutateStation(Protocol):
    def __call__(self, station_id: str, dispatch_id: str | None, mutator: Callable[[StationState], None]) -> StationState: ...

class RecentDispatches(Protocol):
    def __call__(self, station_id: str, limit: int = 20) -> list[Record]: ...

@dataclass(frozen=True)
class StationStorage:
    runtime_postgres_repository_or_none: Callable[[], Callable[[], StationRepository | None]]
    _config_io_lock: Callable[[], AbstractContextManager]
    _plc_web_serial_load_local: Callable[[], Callable[[], dict[str, dict[str, Record]]]]
    _plc_web_serial_record: Callable[[], Callable[[Any], Record | None]]
    _plc_web_serial_mutate: Callable[[], MutateStation]
    _plc_web_serial_upsert_row: Callable[[], Callable[[str, Record, str, str], None]]
    _plc_workstation_row: Callable[[], Callable[[Record], Record]]
    _plc_workstation_lease_row: Callable[[], Callable[[Record], Record]]
    _plc_web_serial_dispatch_row: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class StationIdentity:
    PLC_WORKSTATION_COOKIE: Callable[[], str]
    PLC_WORKSTATION_COOKIE_TTL_SECONDS: Callable[[], int]
    SYSTEM_OWNER_ID: Callable[[], str]
    _plc_web_serial_token_hash: Callable[[], Callable[[str], str]]
    current_auth_user: Callable[[], Callable[[], Record | None]]
    request_is_https: Callable[[], Callable[[Request], bool]]
    plc_web_serial_station_from_request: Callable[[], Callable[[Request], Record | None]]

@dataclass(frozen=True)
class StationPolicy:
    clock: Callable[[], Callable[[], float]]
    PlcConfigError: Callable[[], type[PlcConfigError]]
    HTTPException: Callable[[], type[HTTPException]]
    DEFAULT_WEB_SERIAL_CONFIG: Callable[[], Mapping[str, Any]]
    WEB_SERIAL_ACTIVE_LEASE_SECONDS: Callable[[], int]
    WEB_SERIAL_HEARTBEAT_SECONDS: Callable[[], int]
    WEB_SERIAL_PROTOCOL_VERSION: Callable[[], str]
    migrate_web_serial_config: Callable[[], Callable[[Record], Record]]
    normalize_web_serial_config: Callable[[], Callable[[Record], Record]]
    web_serial_profile_fingerprint: Callable[[], Callable[[Record], str]]

@dataclass(frozen=True)
class StationProjection:
    current_release_version: Callable[[], Callable[[], Record]]
    build_web_serial_capture_read_plan: Callable[[], Callable[[Record, int], Record]]
    web_serial_resolved_addresses: Callable[[], Callable[[Record], Record]]
    plc_web_serial_current_lease: Callable[[], Callable[[str], Record | None]]
    plc_web_serial_recent_dispatches: Callable[[], RecentDispatches]
    plc_web_serial_ensure_current_station_contract: Callable[[], Callable[[Record], Record]]
    plc_web_serial_station_payload: Callable[[], Callable[[Record], Record]]
