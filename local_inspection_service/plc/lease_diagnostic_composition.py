"""Compose browser lease and diagnostic transitions around one workstation owner."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from re import Match
from typing import Any
from uuid import UUID
from .workstation_composition import PlcWorkstationWorkflows
from .lease_acquisition import LeaseAcquisition
from .lease_acquisition_ports import LeaseAcquisitionPorts
from .lease_maintenance import LeaseMaintenance
from .lease_maintenance_ports import LeaseMaintenancePorts
from .diagnostic_state import DiagnosticState
from .diagnostic_state_ports import DiagnosticStatePorts
from ..schemas.plc import (PlcWorkstationLeaseRequest, PlcWorkstationLeaseActivateRequest,
    PlcWorkstationLeaseHeartbeatRequest, PlcWorkstationLeaseRebindRequest,
    PlcWebSerialAttemptRequest, PlcWebSerialDiagnosticConfirmRequest,
    PlcWebSerialDiagnosticReceiptRequest)
Record = dict[str, Any]

@dataclass(frozen=True)
class LeaseAdmission:
    current_user: Callable[[], Callable[[], Record | None]]
    release_version: Callable[[], Callable[[], Record]]
    fullmatch: Callable[[], Callable[[str, str], Match[str] | None]]
    protocol_version: Callable[[], str]
    require_model_permission: Callable[[], Callable[[str | None], None]]
    migrate_config: Callable[[], Callable[[Record], Record]]
    clock: Callable[[], Callable[[], float]]
    uuid4: Callable[[], Callable[[], UUID]]
    connecting_ttl: Callable[[], int]
    active_ttl: Callable[[], int]
    config_error: Callable[[], type[Exception]]

@dataclass(frozen=True)
class LeaseMaintenancePolicy:
    current_user: Callable[[], Callable[[], Record | None]]
    clock: Callable[[], Callable[[], float]]
    active_ttl: Callable[[], int]
    config_error: Callable[[], type[Exception]]

@dataclass(frozen=True)
class DiagnosticPolicy:
    token_hex: Callable[[], Callable[[int], str]]
    token_urlsafe: Callable[[], Callable[[int], str]]
    config_error: Callable[[], type[Exception]]
    clock: Callable[[], Callable[[], float]]
    ceil: Callable[[], Callable[[float], int]]
    protocol_version: Callable[[], str]
    frames: Callable[[], Callable[[], list[Record]]]
    compare_digest: Callable[[], Callable[[str, str], bool]]
    current_user: Callable[[], Callable[[], Record | None]]

class PlcLeaseDiagnosticWorkflows:
    """Inert assembly; ordinary callbacks select after arguments, lease binds once."""
    def __init__(self, *, workstation: PlcWorkstationWorkflows, admission: LeaseAdmission,
                 maintenance_policy: LeaseMaintenancePolicy, diagnostic_policy: DiagnosticPolicy):
        self.workstation = workstation
        self.require_active_lease = workstation.require_active_lease
        self.acquisition = LeaseAcquisition(
            LeaseAcquisitionPorts(
                current_user=admission.current_user,
                release_version=admission.release_version,
                fullmatch=admission.fullmatch,
                protocol_version=admission.protocol_version,
                require_model_permission=admission.require_model_permission,
                mutate=lambda: self._plc_web_serial_mutate,
                record=lambda: self._plc_web_serial_record,
                migrate_config=admission.migrate_config,
                clock=admission.clock,
                uuid4=admission.uuid4,
                connecting_ttl=admission.connecting_ttl,
                active_ttl=admission.active_ttl,
                lease_row=lambda: self._plc_workstation_lease_row,
                config_error=admission.config_error,
            )
        )
        self.maintenance = LeaseMaintenance(
            LeaseMaintenancePorts(
                mutate=lambda: self._plc_web_serial_mutate,
                record=lambda: self._plc_web_serial_record,
                lease_row=lambda: self._plc_workstation_lease_row,
                current_user=maintenance_policy.current_user,
                clock=maintenance_policy.clock,
                active_ttl=maintenance_policy.active_ttl,
                config_error=maintenance_policy.config_error,
                require_active_lease=lambda: self.require_active_lease,
            )
        )
        self.diagnostics = DiagnosticState(
            DiagnosticStatePorts(
                token_hex=diagnostic_policy.token_hex,
                token_urlsafe=diagnostic_policy.token_urlsafe,
                active_lease=lambda: self.require_active_lease,
                config_error=diagnostic_policy.config_error,
                clock=diagnostic_policy.clock,
                ceil=diagnostic_policy.ceil,
                token_hash=lambda: self._plc_web_serial_token_hash,
                lease_row=lambda: self._plc_workstation_lease_row,
                protocol_version=diagnostic_policy.protocol_version,
                frames=diagnostic_policy.frames,
                mutate=lambda: self._plc_web_serial_mutate,
                compare_digest=diagnostic_policy.compare_digest,
                record=lambda: self._plc_web_serial_record,
                current_user=diagnostic_policy.current_user,
            )
        )

    def _plc_web_serial_mutate(self, station_id: str, dispatch_id: str | None, mutator: Callable[[dict[str, dict[str, Any] | None]], None]) -> dict[str, dict[str, Any] | None]:
        return self.workstation._plc_web_serial_mutate(station_id, dispatch_id, mutator)

    def _plc_web_serial_record(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        return self.workstation._plc_web_serial_record(row)

    def _plc_workstation_lease_row(self, record: dict[str, Any]) -> dict[str, Any]:
        return self.workstation._plc_workstation_lease_row(record)

    def _plc_web_serial_token_hash(self, token: str) -> str:
        return self.workstation._plc_web_serial_token_hash(token)

    def plc_web_serial_claim_connecting_lease(self, station_id: str, request: PlcWorkstationLeaseRequest) -> dict[str, Any]:
        return self.acquisition.claim(station_id, request)

    def plc_web_serial_activate_lease(self, station_id: str, request: PlcWorkstationLeaseActivateRequest) -> dict[str, Any]:
        return self.acquisition.activate(station_id, request)

    def plc_web_serial_heartbeat(self, station_id: str, request: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
        return self.maintenance.heartbeat(station_id, request)

    def plc_web_serial_rebind_model(self, station_id: str, request: PlcWorkstationLeaseRebindRequest) -> dict[str, Any]:
        return self.maintenance.rebind_model(station_id, request)

    def plc_web_serial_release_lease(self, station_id: str, request: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
        return self.maintenance.release(station_id, request)

    def plc_web_serial_diagnostic_plan(self, station_id: str, request: PlcWebSerialAttemptRequest) -> dict[str, Any]:
        return self.diagnostics.plan(station_id, request)

    def plc_web_serial_confirm_diagnostic(self, station_id: str, request: PlcWebSerialDiagnosticConfirmRequest) -> dict[str, Any]:
        return self.diagnostics.confirm(station_id, request)

    def plc_web_serial_finish_diagnostic(self, station_id: str, request: PlcWebSerialDiagnosticReceiptRequest) -> dict[str, Any]:
        return self.diagnostics.finish(station_id, request)
