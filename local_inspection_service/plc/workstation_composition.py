"""Own workstation persistence, station policy and browser dispatch collaborators."""
from __future__ import annotations
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from fastapi import Request, Response
from .workstation_repository import PlcWorkstationRepository
from .workstation_repository_ports import WorkstationRepositoryFiles, WorkstationRepositoryPolicy, WorkstationRepositoryStorage, PostgresRows
from .station_service import PlcStationService
from .station_ports import StationStorage, StationIdentity, StationPolicy, StationProjection, StationRepository
from .browser_dispatch import PlcBrowserDispatchService
from .browser_dispatch_ports import BrowserDispatchStorage, BrowserDispatchIdentity, BrowserDispatchPolicy, BrowserDispatchProjection, PlcWebSerialAttemptRequest, PlcWebSerialReceiptRequest
class WorkstationRows(PostgresRows, StationRepository, Protocol):
    """The shared adapter supports both transactional writes and station reads."""

Record = dict[str, Any]

@dataclass(frozen=True)
class WorkstationAccess:
    runtime_postgres_repository_or_none: Callable[[], Callable[[], WorkstationRows | None]]
    _config_io_lock: Callable[[], AbstractContextManager]

@dataclass(frozen=True)
class WorkstationIdentity:
    PLC_WORKSTATION_COOKIE: Callable[[], str]
    PLC_WORKSTATION_COOKIE_TTL_SECONDS: Callable[[], int]
    SYSTEM_OWNER_ID: Callable[[], str]
    current_auth_user: Callable[[], Callable[[], Record | None]]
    request_is_https: Callable[[], Callable[[Request], bool]]

@dataclass(frozen=True)
class WorkstationProjection:
    current_release_version: Callable[[], Callable[[], Record]]
    build_web_serial_capture_read_plan: Callable[[], Callable[[Record, int], Record]]
    web_serial_resolved_addresses: Callable[[], Callable[[Record], Record]]

class PlcWorkstationWorkflows:
    """Construction performs no I/O, identity, clock or repository selection."""
    def __init__(
        self, *,
        files: WorkstationRepositoryFiles,
        repository_policy: WorkstationRepositoryPolicy,
        storage: WorkstationAccess,
        identity: WorkstationIdentity,
        station_policy: StationPolicy,
        projection: WorkstationProjection,
        dispatch_policy: BrowserDispatchPolicy,
    ):
        self.repository = PlcWorkstationRepository(
            files=files,
            policy=repository_policy,
            storage=WorkstationRepositoryStorage(
                runtime_postgres_repository_or_none=storage.runtime_postgres_repository_or_none,
                _config_io_lock=storage._config_io_lock,
                _plc_web_serial_empty_state=lambda: self._plc_web_serial_empty_state,
                _plc_web_serial_load_local=lambda: self._plc_web_serial_load_local,
                _plc_web_serial_save_local=lambda: self._plc_web_serial_save_local,
            ),
        )
        self.station = PlcStationService(
            storage=StationStorage(
                runtime_postgres_repository_or_none=storage.runtime_postgres_repository_or_none,
                _config_io_lock=storage._config_io_lock,
                _plc_web_serial_load_local=lambda: self._plc_web_serial_load_local,
                _plc_web_serial_record=lambda: self._plc_web_serial_record,
                _plc_web_serial_mutate=lambda: self._plc_web_serial_mutate,
                _plc_web_serial_upsert_row=lambda: self._plc_web_serial_upsert_row,
                _plc_workstation_row=lambda: self._plc_workstation_row,
                _plc_workstation_lease_row=lambda: self._plc_workstation_lease_row,
                _plc_web_serial_dispatch_row=lambda: self._plc_web_serial_dispatch_row,
            ),
            identity=StationIdentity(
                PLC_WORKSTATION_COOKIE=identity.PLC_WORKSTATION_COOKIE,
                PLC_WORKSTATION_COOKIE_TTL_SECONDS=identity.PLC_WORKSTATION_COOKIE_TTL_SECONDS,
                SYSTEM_OWNER_ID=identity.SYSTEM_OWNER_ID,
                _plc_web_serial_token_hash=lambda: self._plc_web_serial_token_hash,
                current_auth_user=identity.current_auth_user,
                request_is_https=identity.request_is_https,
                plc_web_serial_station_from_request=lambda: self.plc_web_serial_station_from_request,
            ),
            policy=station_policy,
            projection=StationProjection(
                current_release_version=projection.current_release_version,
                build_web_serial_capture_read_plan=projection.build_web_serial_capture_read_plan,
                web_serial_resolved_addresses=projection.web_serial_resolved_addresses,
                plc_web_serial_current_lease=lambda: self.plc_web_serial_current_lease,
                plc_web_serial_recent_dispatches=lambda: self.plc_web_serial_recent_dispatches,
                plc_web_serial_ensure_current_station_contract=lambda: self.plc_web_serial_ensure_current_station_contract,
                plc_web_serial_station_payload=lambda: self.plc_web_serial_station_payload,
            ),
        )
        self.require_active_lease = self.station._plc_web_serial_require_active_lease
        self.browser = PlcBrowserDispatchService(
            storage=BrowserDispatchStorage(
                _plc_web_serial_record=lambda: self._plc_web_serial_record,
                _plc_web_serial_mutate=lambda: self._plc_web_serial_mutate,
                _plc_web_serial_dispatch_row=lambda: self._plc_web_serial_dispatch_row,
                _plc_workstation_lease_row=lambda: self._plc_workstation_lease_row,
            ),
            identity=BrowserDispatchIdentity(
                _plc_web_serial_require_active_lease=lambda: self.require_active_lease,
                _plc_web_serial_token_hash=lambda: self._plc_web_serial_token_hash,
            ),
            policy=dispatch_policy,
            projection=BrowserDispatchProjection(
                verify_plc_web_serial_dispatch=lambda: self.verify_plc_web_serial_dispatch,
                _plc_web_serial_receipt_outcome=lambda: self._plc_web_serial_receipt_outcome,
                plc_web_serial_dispatch_public=lambda: self.plc_web_serial_dispatch_public,
            ),
        )

    def _plc_web_serial_empty_state(self) -> dict[str, dict[str, Any]]:
        return self.repository._plc_web_serial_empty_state()

    def _plc_web_serial_load_local(self) -> dict[str, dict[str, Any]]:
        return self.repository._plc_web_serial_load_local()

    def _plc_web_serial_save_local(self, state: dict[str, dict[str, Any]]) -> None:
        return self.repository._plc_web_serial_save_local(state)

    def _plc_web_serial_record(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        return self.repository._plc_web_serial_record(row)

    def _plc_workstation_row(self, record: dict[str, Any]) -> dict[str, Any]:
        return self.repository._plc_workstation_row(record)

    def _plc_workstation_lease_row(self, record: dict[str, Any]) -> dict[str, Any]:
        return self.repository._plc_workstation_lease_row(record)

    def _plc_web_serial_dispatch_row(self, record: dict[str, Any]) -> dict[str, Any]:
        return self.repository._plc_web_serial_dispatch_row(record)

    def _plc_web_serial_upsert_row(self, table_name: str, row: dict[str, Any], local_key: str, row_id: str) -> None:
        return self.repository._plc_web_serial_upsert_row(table_name, row, local_key, row_id)

    def _plc_web_serial_mutate(self, station_id: str, dispatch_id: str | None, mutator: Callable[[dict[str, dict[str, Any] | None]], None]) -> dict[str, dict[str, Any] | None]:
        return self.repository._plc_web_serial_mutate(station_id, dispatch_id, mutator)

    def _plc_web_serial_token_hash(self, token: str) -> str:
        return self.station._plc_web_serial_token_hash(token)

    def plc_web_serial_station_from_request(self, request: Request) -> dict[str, Any] | None:
        return self.station.plc_web_serial_station_from_request(request)

    def require_plc_web_serial_station(self, request: Request) -> dict[str, Any]:
        return self.station.require_plc_web_serial_station(request)

    def plc_web_serial_current_lease(self, station_id: str) -> dict[str, Any] | None:
        return self.station.plc_web_serial_current_lease(station_id)

    def plc_web_serial_recent_dispatches(self, station_id: str, limit: int=20) -> list[dict[str, Any]]:
        return self.station.plc_web_serial_recent_dispatches(station_id, limit)

    def plc_web_serial_ensure_current_station_contract(self, station: dict[str, Any]) -> dict[str, Any]:
        return self.station.plc_web_serial_ensure_current_station_contract(station)

    def plc_web_serial_station_payload(self, station: dict[str, Any]) -> dict[str, Any]:
        return self.station.plc_web_serial_station_payload(station)

    def plc_web_serial_unpaired_payload(self) -> dict[str, Any]:
        return self.station.plc_web_serial_unpaired_payload()

    def plc_web_serial_list_workstations(self) -> list[dict[str, Any]]:
        return self.station.plc_web_serial_list_workstations()

    def plc_web_serial_pair(self, request: Request, response: Response, name: str, station_id: str | None=None) -> dict[str, Any]:
        return self.station.plc_web_serial_pair(request, response, name, station_id)

    def plc_web_serial_update_config(self, station_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
        return self.station.plc_web_serial_update_config(station_id, candidate)

    def plc_web_serial_set_verified(self, station_id: str, verified: bool) -> dict[str, Any]:
        return self.station.plc_web_serial_set_verified(station_id, verified)

    def plc_web_serial_begin_camera_detection(self, station_id: str, session_id: str, camera_request_id: str, model_id: str, fingerprint: str) -> tuple[dict[str, Any], bool]:
        return self.browser.plc_web_serial_begin_camera_detection(station_id, session_id, camera_request_id, model_id, fingerprint)

    def plc_web_serial_finish_camera_detection(self, station_id: str, dispatch_id: str, session_id: str, result: dict[str, Any] | None, error: str='') -> dict[str, Any]:
        return self.browser.plc_web_serial_finish_camera_detection(station_id, dispatch_id, session_id, result, error)

    def plc_web_serial_dispatch_public(self, record: dict[str, Any]) -> dict[str, Any]:
        return self.browser.plc_web_serial_dispatch_public(record)

    def verify_plc_web_serial_dispatch(self, record: dict[str, Any], station: dict[str, Any], *, require_frames: bool=True, require_current_config: bool=True) -> None:
        return self.browser.verify_plc_web_serial_dispatch(record, station, require_frames=require_frames, require_current_config=require_current_config)

    def plc_web_serial_declare_attempt(self, station_id: str, dispatch_id: str, request: PlcWebSerialAttemptRequest) -> dict[str, Any]:
        return self.browser.plc_web_serial_declare_attempt(station_id, dispatch_id, request)

    def _plc_web_serial_receipt_outcome(self, frames: list[dict[str, Any]], operations: list[dict[str, Any]]) -> str:
        return self.browser._plc_web_serial_receipt_outcome(frames, operations)

    def plc_web_serial_record_receipt(self, station_id: str, dispatch_id: str, request: PlcWebSerialReceiptRequest) -> dict[str, Any]:
        return self.browser.plc_web_serial_record_receipt(station_id, dispatch_id, request)
