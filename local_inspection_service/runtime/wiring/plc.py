"""Static application wiring; original narrow business ports remain the boundary.

Only the canonical assembler consumes this result. Business components receive
their existing narrow ports; no application-entry callback is used.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import MutableMapping
from typing import Any, Callable
import contextvars
import _thread
from ..application_values import ApplicationValues
from typing import Any
from local_inspection_service.plc.browser_dispatch_ports import BrowserDispatchPolicy
from typing import Callable
from local_inspection_service.plc.capture_composition import CapturePolicy
from local_inspection_service.plc.capture_composition import CaptureStorage
from local_inspection_service.plc_fx_ascii import DEFAULT_PLC_CONFIG
from local_inspection_service.plc_web_serial import DEFAULT_WEB_SERIAL_CONFIG
from local_inspection_service.plc.lease_diagnostic_composition import DiagnosticPolicy
from local_inspection_service.plc.dispatch_mutation_ports import DispatchMutationEvents
from local_inspection_service.plc.dispatch_mutation_ports import DispatchMutationEvidence
from local_inspection_service.plc.dispatch_mutation_ports import DispatchMutationPolicy
from local_inspection_service.plc.dispatch_mutation_ports import DispatchMutationStorage
from local_inspection_service.plc.legacy_records import DispatchRecordPolicy
from local_inspection_service.plc.legacy_records import DispatchRecordSources
from local_inspection_service.plc.dispatch_runtime_state_ports import DispatchRuntimePolicy
from local_inspection_service.plc.dispatch_runtime_state_ports import DispatchRuntimeRecords
from local_inspection_service.plc.dispatch_runtime_state_ports import DispatchRuntimeState
from fastapi import HTTPException
from local_inspection_service.plc_web_serial import LEGACY_WEB_SERIAL_PROTOCOL_VERSION
from local_inspection_service.plc.lease_diagnostic_composition import LeaseAdmission
from local_inspection_service.plc.lease_diagnostic_composition import LeaseMaintenancePolicy
from local_inspection_service.plc.legacy_activation import LegacyActivationChecks
from local_inspection_service.plc.legacy_activation import LegacyActivationPolicy
from local_inspection_service.plc.legacy_activation import LegacyActivationSources
from local_inspection_service.plc.legacy_operations import LegacyCaptureIteration
from local_inspection_service.plc.legacy_coordination import LegacyCoordinationPolicy
from local_inspection_service.plc.legacy_dispatch import LegacyDispatch
from local_inspection_service.plc.legacy_dispatch_ports import LegacyDispatchConfiguration
from local_inspection_service.plc.legacy_dispatch_ports import LegacyDispatchExecution
from local_inspection_service.plc.legacy_operations import LegacyDispatchIteration
from local_inspection_service.plc.legacy_dispatch_ports import LegacyDispatchPolicy
from local_inspection_service.plc.legacy_workers import LegacyHeartbeatCapabilities
from local_inspection_service.plc.legacy_workers import LegacyLoopCapabilities
from local_inspection_service.plc.legacy_operations import LegacyOperationConfiguration
from local_inspection_service.plc.legacy_operations import LegacyOperationOwnership
from local_inspection_service.plc.legacy_operations import LegacyPlcOperations
from local_inspection_service.plc.legacy_workers import LegacyPlcWorkers
from local_inspection_service.plc_fx_ascii import PLC_CONFIG_ABSENT
from local_inspection_service.plc.event_projection import PLC_FINALIZE_REASONS
from local_inspection_service.plc_fx_ascii import PROTOCOL_ID as PLC_PROTOCOL_ID
from local_inspection_service.plc_fx_ascii import PLC_TERMINAL_ALLOWED_PHASES
from local_inspection_service.plc_fx_ascii import PLC_TERMINAL_DIAGNOSTIC_SOURCES
from local_inspection_service.plc_fx_ascii import PLC_TERMINAL_RESULT_CODES
from local_inspection_service.plc_fx_ascii import PlcAttemptTerminalResult
from local_inspection_service.plc.capture_composition import PlcCaptureWorkflows
from local_inspection_service.plc_fx_ascii import PlcConfigError
from local_inspection_service.plc.dispatch_mutations import PlcDispatchMutations
from local_inspection_service.plc.dispatch_runtime_state import PlcDispatchRuntimeState
from local_inspection_service.plc.errors import PlcDispatchStateConflict
from local_inspection_service.plc.transition_policy import PlcDispatchTransitionKind
from local_inspection_service.plc.lease_diagnostic_composition import PlcLeaseDiagnosticWorkflows
from local_inspection_service.plc_fx_ascii import PlcTerminalResultCode
from local_inspection_service.plc_fx_ascii import PlcTransportError
from local_inspection_service.plc_fx_ascii import PlcTransportPhase
from local_inspection_service.schemas.plc import PlcWebSerialAttemptRequest
from local_inspection_service.schemas.plc import PlcWebSerialDiagnosticConfirmRequest
from local_inspection_service.schemas.plc import PlcWebSerialDiagnosticReceiptRequest
from local_inspection_service.schemas.plc import PlcWebSerialReceiptRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseActivateRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseHeartbeatRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseRebindRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseRequest
from local_inspection_service.plc.workstation_composition import PlcWorkstationWorkflows
from fastapi import Request
from fastapi import Response
from local_inspection_service.plc.station_ports import StationPolicy
from concurrent.futures import ThreadPoolExecutor
from local_inspection_service.plc_web_serial import WEB_SERIAL_ACTIVE_LEASE_SECONDS
from local_inspection_service.plc_web_serial import WEB_SERIAL_CONNECTING_LEASE_SECONDS
from local_inspection_service.plc_web_serial import WEB_SERIAL_HEARTBEAT_SECONDS
from local_inspection_service.plc_web_serial import WEB_SERIAL_PLAN_DEADLINE_SECONDS
from local_inspection_service.plc_web_serial import WEB_SERIAL_PROTOCOL_VERSION
from local_inspection_service.plc.workstation_composition import WorkstationAccess
from local_inspection_service.plc.workstation_composition import WorkstationIdentity
from local_inspection_service.plc.workstation_composition import WorkstationProjection
from local_inspection_service.plc.workstation_repository_ports import WorkstationRepositoryFiles
from local_inspection_service.plc.workstation_repository_ports import WorkstationRepositoryPolicy
from local_inspection_service.plc.config_diagnostics_ports import ConfigAccess as _ConfigAccess
from local_inspection_service.plc.config_diagnostics import ConfigDiagnostics as _ConfigDiagnostics
from local_inspection_service.plc.config_diagnostics_ports import ConfigDisplay as _ConfigDisplay
from local_inspection_service.plc.config_diagnostics_ports import ConfigErrors as _ConfigErrors
from local_inspection_service.plc.config_diagnostics_ports import ConfigRuntime as _ConfigRuntime
from local_inspection_service.plc.config_diagnostics_ports import ConfigSources as _ConfigSources
from local_inspection_service.plc.connection_lease import ConnectionLease as _ConnectionLease
from local_inspection_service.plc.dispatch_diagnostic_ports import DispatchAccess as _DispatchAccess
from local_inspection_service.plc.dispatch_diagnostic import DispatchDiagnostic as _DispatchDiagnostic
from local_inspection_service.plc.dispatch_diagnostic_ports import DispatchErrors as _DispatchErrors
from local_inspection_service.plc.dispatch_diagnostic_ports import DispatchMutation as _DispatchMutation
from local_inspection_service.plc.connection_lease_ports import LeaseAccess as _LeaseAccess
from local_inspection_service.plc.connection_lease_ports import LeaseErrors as _LeaseErrors
from local_inspection_service.plc.connection_lease_ports import LeaseMutation as _LeaseMutation
from local_inspection_service.plc.event_commands import _PLC_TYPED_EVENT_DERIVERS
from local_inspection_service.plc.event_commands import _PLC_TYPED_EVENT_FIELDS
from local_inspection_service.plc.workstation_management_ports import WorkstationAccess as _WorkstationAccess
from local_inspection_service.plc.workstation_management_ports import WorkstationErrors as _WorkstationErrors
from local_inspection_service.plc.workstation_management import WorkstationManagement as _WorkstationManagement
from local_inspection_service.plc.workstation_management_ports import WorkstationMutation as _WorkstationMutation
from local_inspection_service.plc.workstation_management_ports import WorkstationProjection as _WorkstationProjection
from local_inspection_service.plc.legacy_records import LegacyDispatchRecords as _native_LegacyDispatchRecords_2502
from local_inspection_service.plc.legacy_dispatch_ports import LegacyDispatchRecords as _native_LegacyDispatchRecords_2812
from local_inspection_service.plc.transition_policy import _plc_canonical
from local_inspection_service.plc_web_serial import build_legacy_web_serial_plan
from local_inspection_service.plc.persisted_validation import build_plc_dispatch_plan
from local_inspection_service.plc_web_serial import build_web_serial_capture_read_plan
from local_inspection_service.plc_web_serial import build_web_serial_diagnostic_plan
from local_inspection_service.plc_web_serial import build_web_serial_plan
from local_inspection_service.plc_fx_ascii import dispatch_detection_result as dispatch_fx_plc_detection_result
import hmac
from local_inspection_service.plc_web_serial import legacy_web_serial_config_fingerprint
from local_inspection_service.plc_fx_ascii import logical_device_address
import math
from local_inspection_service.plc_web_serial import migrate_web_serial_config
from local_inspection_service.plc_web_serial import normalize_legacy_web_serial_config
from local_inspection_service.plc_fx_ascii import normalize_config as normalize_plc_config
from local_inspection_service.plc_web_serial import normalize_web_serial_config
import os
from local_inspection_service.plc.event_projection import project_plc_dispatch_events
import re
from local_inspection_service.plc_fx_ascii import read_d_register_value
from local_inspection_service.release_version import release_version_status
from local_inspection_service.auth.sessions import request_is_https
import secrets
import socket
import threading
import time
import uuid
from local_inspection_service.plc.transition_policy import validate_plc_dispatch_transition
from local_inspection_service.plc.persisted_validation import verify_persisted_plc_dispatch
from local_inspection_service.plc_web_serial import web_serial_config_fingerprint
from local_inspection_service.plc_web_serial import web_serial_profile_fingerprint
from local_inspection_service.plc_web_serial import web_serial_resolved_addresses
import concurrent.futures.thread
import local_inspection_service.auth.account_projections
import local_inspection_service.config.application_composition
import local_inspection_service.plc.browser_dispatch
import local_inspection_service.plc.capture_composition
import local_inspection_service.plc.config_diagnostics
import local_inspection_service.plc.connection_lease
import local_inspection_service.plc.diagnostic_state
import local_inspection_service.plc.dispatch_diagnostic
import local_inspection_service.plc.dispatch_mutations
import local_inspection_service.plc.dispatch_runtime_state
import local_inspection_service.plc.lease_acquisition
import local_inspection_service.plc.lease_diagnostic_composition
import local_inspection_service.plc.lease_maintenance
import local_inspection_service.plc.legacy_activation
import local_inspection_service.plc.legacy_coordination
import local_inspection_service.plc.legacy_dispatch
import local_inspection_service.plc.legacy_operations
import local_inspection_service.plc.legacy_records
import local_inspection_service.plc.legacy_workers
import local_inspection_service.plc.plc_capture_state
import local_inspection_service.plc.station_service
import local_inspection_service.plc.workstation_composition
import local_inspection_service.plc.workstation_management
import local_inspection_service.plc.workstation_repository
import local_inspection_service.runtime.identity
import local_inspection_service.runtime.repository_access
import local_inspection_service.runtime.service_paths
import local_inspection_service.storage.artifacts.files
import threading

@dataclass(frozen=True)
class PlcWiringInputs:
    _account_projections: Callable[[], local_inspection_service.auth.account_projections.AccountProjections]
    _app_configuration: Callable[[], local_inspection_service.config.application_composition.ApplicationConfiguration]
    _business_files: Callable[[], local_inspection_service.storage.artifacts.files.BusinessFiles]
    _config_io_lock: Callable[[], _thread.RLock]
    _request_user: Callable[[], local_inspection_service.runtime.identity.RequestIdentity]
    _runtime_repository_access: Callable[[], local_inspection_service.runtime.repository_access.RuntimeRepositoryAccess]
    _service_paths: Callable[[], local_inspection_service.runtime.service_paths.ServicePaths]
    current_auth_user: Callable[[], Callable[..., Any]]
    mutate_app_config_atomically: Callable[[], Callable[..., Any]]
    require_permission: Callable[[], Callable[..., Any]]

@dataclass(frozen=True)
class PlcAssembly:
    _PLC_RUNTIME_LIMIT: int
    _legacy_capture_workflows: local_inspection_service.plc.capture_composition.PlcCaptureWorkflows
    _legacy_plc_activation: local_inspection_service.plc.legacy_activation.LegacyActivationPolicy
    _legacy_plc_coordination: local_inspection_service.plc.legacy_coordination.LegacyRuntimeCoordination
    _legacy_plc_operations: local_inspection_service.plc.legacy_operations.LegacyPlcOperations
    _legacy_plc_records: local_inspection_service.plc.legacy_records.LegacyDispatchRecords
    _legacy_plc_workers: local_inspection_service.plc.legacy_workers.LegacyPlcWorkers
    _mutate_plc_runtime_rows: Callable[..., Any]
    _plc_active_attempts: dict[str, dict[str, Any]]
    _plc_browser_dispatch: local_inspection_service.plc.browser_dispatch.PlcBrowserDispatchService
    _plc_capture_state: local_inspection_service.plc.plc_capture_state.PlcCaptureState
    _plc_config_diagnostics: local_inspection_service.plc.config_diagnostics.ConfigDiagnostics
    _plc_connection_lease: local_inspection_service.plc.connection_lease.ConnectionLease
    _plc_diagnostic_state: local_inspection_service.plc.diagnostic_state.DiagnosticState
    _plc_dispatch_diagnostic: local_inspection_service.plc.dispatch_diagnostic.DispatchDiagnostic
    _plc_dispatch_mutations: local_inspection_service.plc.dispatch_mutations.PlcDispatchMutations
    _plc_dispatch_runtime: dict[str, dict[str, Any]]
    _plc_dispatch_runtime_state: local_inspection_service.plc.dispatch_runtime_state.PlcDispatchRuntimeState
    _plc_dispatch_slots: threading.BoundedSemaphore
    _plc_io_executor: concurrent.futures.thread.ThreadPoolExecutor
    _plc_lease_acquisition: local_inspection_service.plc.lease_acquisition.LeaseAcquisition
    _plc_lease_diagnostic_workflows: local_inspection_service.plc.lease_diagnostic_composition.PlcLeaseDiagnosticWorkflows
    _plc_lease_maintenance: local_inspection_service.plc.lease_maintenance.LeaseMaintenance
    _plc_legacy_dispatch: local_inspection_service.plc.legacy_dispatch.LegacyDispatch
    _plc_process_owner_id: str
    _plc_station_service: local_inspection_service.plc.station_service.PlcStationService
    _plc_transport_factory: Callable[[dict[str, Any]], Any] | None
    _plc_web_serial_require_active_lease: Callable[..., Any]
    _plc_workstation_management: local_inspection_service.plc.workstation_management.WorkstationManagement
    _plc_workstation_repository: local_inspection_service.plc.workstation_repository.PlcWorkstationRepository
    _plc_workstation_workflows: local_inspection_service.plc.workstation_composition.PlcWorkstationWorkflows
    _plc_write_pending: threading.Event
    get_validated_idempotent_dispatch: Callable[..., Any]
    mutate_plc_runtime_coordination: Callable[..., Any]
    plc_activation_errors: Callable[..., Any]
    plc_capture_poll_once: Callable[..., Any]
    plc_claim_or_renew_io_owner: Callable[..., Any]
    plc_completed_capture_receipt: Callable[..., Any]
    plc_config_audit_snapshot: Callable[..., Any]
    plc_current_process_owns_io: Callable[..., Any]
    plc_device_profile_verified: Callable[..., Any]
    plc_dispatch_audit_records: Callable[..., Any]
    plc_dispatch_conflict_response: Callable[..., Any]
    plc_dispatch_existing: Callable[..., Any]
    plc_pg_coordination_available: Callable[..., Any]
    plc_profile_fingerprint: Callable[..., Any]
    plc_read_profile_verified: Callable[..., Any]
    plc_reconcile_pending_dispatches_once: Callable[..., Any]
    plc_serial_dependency_available: Callable[..., Any]
    plc_start_owner_heartbeat: Callable[..., Any]
    raw_plc_namespace: Callable[..., Any]
    start_plc_capture_poller: Callable[..., Any]
    start_plc_dispatch_reconciler: Callable[..., Any]

def assemble_plc(values: ApplicationValues, environment: MutableMapping[str, str], ports: PlcWiringInputs) -> PlcAssembly:
    def current_release_version() -> dict[str, Any]:
        return release_version_status(values.ROOT, WEB_SERIAL_PROTOCOL_VERSION)

    def runtime_postgres_repository_or_none() -> Any | None:
        """Return the explicit PostgreSQL repository, or None for JSON runtime."""
        return ports._runtime_repository_access().runtime_postgres_repository_or_none()

    def require_analyze_model_permission(model_id: str | None) -> None:
        return ports._account_projections().require_analyze_model_permission(model_id)

    def plc_web_serial_station_from_request(request: Request) -> dict[str, Any] | None:
        return _plc_station_service.plc_web_serial_station_from_request(request)

    def require_plc_web_serial_station(request: Request) -> dict[str, Any]:
        return _plc_station_service.require_plc_web_serial_station(request)

    def plc_web_serial_station_payload(station: dict[str, Any]) -> dict[str, Any]:
        return _plc_station_service.plc_web_serial_station_payload(station)

    def plc_web_serial_unpaired_payload() -> dict[str, Any]:
        return _plc_station_service.plc_web_serial_unpaired_payload()

    def plc_web_serial_list_workstations() -> list[dict[str, Any]]:
        return _plc_station_service.plc_web_serial_list_workstations()

    def plc_web_serial_pair(request: Request, response: Response, name: str, station_id: str | None=None) -> dict[str, Any]:
        return _plc_station_service.plc_web_serial_pair(request, response, name, station_id)

    def plc_web_serial_update_config(station_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
        return _plc_station_service.plc_web_serial_update_config(station_id, candidate)

    def plc_web_serial_set_verified(station_id: str, verified: bool) -> dict[str, Any]:
        return _plc_station_service.plc_web_serial_set_verified(station_id, verified)

    def plc_web_serial_claim_connecting_lease(station_id: str, request: PlcWorkstationLeaseRequest) -> dict[str, Any]:
        return _plc_lease_acquisition.claim(station_id, request)

    def plc_web_serial_activate_lease(station_id: str, request: PlcWorkstationLeaseActivateRequest) -> dict[str, Any]:
        return _plc_lease_acquisition.activate(station_id, request)

    def plc_web_serial_heartbeat(station_id: str, request: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
        return _plc_lease_maintenance.heartbeat(station_id, request)

    def plc_web_serial_rebind_model(station_id: str, request: PlcWorkstationLeaseRebindRequest) -> dict[str, Any]:
        return _plc_lease_maintenance.rebind_model(station_id, request)

    def plc_web_serial_release_lease(station_id: str, request: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
        return _plc_lease_maintenance.release(station_id, request)

    def plc_web_serial_diagnostic_plan(station_id: str, request: PlcWebSerialAttemptRequest) -> dict[str, Any]:
        return _plc_diagnostic_state.plan(station_id, request)

    def plc_web_serial_confirm_diagnostic(station_id: str, request: PlcWebSerialDiagnosticConfirmRequest) -> dict[str, Any]:
        return _plc_diagnostic_state.confirm(station_id, request)

    def plc_web_serial_finish_diagnostic(station_id: str, request: PlcWebSerialDiagnosticReceiptRequest) -> dict[str, Any]:
        return _plc_diagnostic_state.finish(station_id, request)

    def plc_web_serial_declare_attempt(station_id: str, dispatch_id: str, request: PlcWebSerialAttemptRequest) -> dict[str, Any]:
        return _plc_browser_dispatch.plc_web_serial_declare_attempt(station_id, dispatch_id, request)

    def plc_web_serial_record_receipt(station_id: str, dispatch_id: str, request: PlcWebSerialReceiptRequest) -> dict[str, Any]:
        return _plc_browser_dispatch.plc_web_serial_record_receipt(station_id, dispatch_id, request)

    def load_config() -> dict[str, Any]:
        return ports._app_configuration().load_config()

    def plc_capture_disarm(reason: str) -> None:
        return _plc_capture_state.plc_capture_disarm(reason)

    def plc_apply_capture_observation(value: int, *, generation: int, owner_epoch: int, trigger_value: int) -> dict[str, Any] | None:
        """Persist one read observation and atomically create at most one edge event."""
        return _plc_capture_state.plc_apply_capture_observation(value, generation=generation, owner_epoch=owner_epoch, trigger_value=trigger_value)

    def create_plc_dispatch(*, source: str, request_id: str, passed: bool, fingerprint: str, expected_generation: int | None=None) -> dict[str, Any]:
        """Atomically derive a queued v1 record from the authoritative PLC namespace."""
        return _plc_dispatch_mutations.create_plc_dispatch(source=source, request_id=request_id, passed=passed, fingerprint=fingerprint, expected_generation=expected_generation)

    def _apply_plc_dispatch_event(dispatch_id: str, *, expected_version: int, transition_kind: PlcDispatchTransitionKind, event_payload: dict[str, Any]) -> dict[str, Any]:
        return _plc_dispatch_mutations._apply_plc_dispatch_event(dispatch_id, expected_version=expected_version, transition_kind=transition_kind, event_payload=event_payload)

    def plc_transition_attempting(dispatch_id: str, *, expected_version: int) -> dict[str, Any]:
        return _plc_dispatch_mutations.plc_transition_attempting(dispatch_id, expected_version=expected_version)

    def plc_start_attempt(dispatch_id: str, *, expected_version: int, target: str) -> dict[str, Any]:
        return _plc_dispatch_mutations.plc_start_attempt(dispatch_id, expected_version=expected_version, target=target)

    def plc_advance_attempt(dispatch_id: str, *, expected_version: int, attempt_id: str, bytes_written: int, physical_status: str, outcome: str) -> dict[str, Any]:
        return _plc_dispatch_mutations.plc_advance_attempt(dispatch_id, expected_version=expected_version, attempt_id=attempt_id, bytes_written=bytes_written, physical_status=physical_status, outcome=outcome)

    def plc_finish_attempt(dispatch_id: str, *, expected_version: int, attempt_id: str, terminal_result: PlcAttemptTerminalResult) -> dict[str, Any]:
        return _plc_dispatch_mutations.plc_finish_attempt(dispatch_id, expected_version=expected_version, attempt_id=attempt_id, terminal_result=terminal_result)

    def plc_mark_deadline(dispatch_id: str, *, expected_version: int) -> dict[str, Any]:
        return _plc_dispatch_mutations.plc_mark_deadline(dispatch_id, expected_version=expected_version)

    def plc_finalize_dispatch(dispatch_id: str, *, expected_version: int, reason: str='') -> dict[str, Any]:
        return _plc_dispatch_mutations.plc_finalize_dispatch(dispatch_id, expected_version=expected_version, reason=reason)

    def _plc_runtime_entry(dispatch_id: str) -> dict[str, Any]:
        return _plc_dispatch_runtime_state._plc_runtime_entry(dispatch_id)

    def _hydrate_plc_runtime_entry(dispatch_id: str) -> dict[str, Any]:
        return _plc_dispatch_runtime_state._hydrate_plc_runtime_entry(dispatch_id)

    def _register_plc_dispatch_runtime(dispatch_id: str) -> None:
        return _plc_dispatch_runtime_state._register_plc_dispatch_runtime(dispatch_id)

    def _plc_deadline_snapshot(*, dispatch_id: str, source: str, request_id: str, passed: bool) -> dict[str, Any]:
        return _plc_dispatch_runtime_state._plc_deadline_snapshot(dispatch_id=dispatch_id, source=source, request_id=request_id, passed=passed)

    def _plc_active_attempts_snapshot() -> list[dict[str, Any]]:
        return _plc_dispatch_runtime_state._plc_active_attempts_snapshot()

    def plc_dispatch_identity(result: dict[str, Any], *, source: str, fingerprint: str) -> tuple[str, str, bool]:
        return _plc_dispatch_runtime_state.plc_dispatch_identity(result, source=source, fingerprint=fingerprint)

    def plc_dispatch_record_is_terminal(record: dict[str, Any]) -> bool:
        return _plc_dispatch_runtime_state.plc_dispatch_record_is_terminal(record)

    def plc_dispatch_is_pristine_queue(record: dict[str, Any]) -> bool:
        """Only a dispatch with proof that physical I/O never began may change owners."""
        return _plc_dispatch_runtime_state.plc_dispatch_is_pristine_queue(record)

    def plc_dispatch_adoption_blocker(record: dict[str, Any], *, settings: dict[str, Any], generation: int, now_ms: int | None=None) -> str:
        """Return a no-I/O reason when a queued record is unsafe or stale to adopt."""
        return _plc_dispatch_runtime_state.plc_dispatch_adoption_blocker(record, settings=settings, generation=generation, now_ms=now_ms)

    def dispatch_plc_for_detection(result: dict[str, Any], *, source: str, fingerprint: str, expected_generation: int | None=None) -> dict[str, Any]:
        """Attach PLC sync status without changing or invalidating the detection result."""
        return _plc_legacy_dispatch.dispatch_plc_for_detection(result, source=source, fingerprint=fingerprint, expected_generation=expected_generation)

    def _run_queued_plc_dispatch(result: dict[str, Any], *, source: str, fingerprint: str) -> dict[str, Any]:
        return _plc_legacy_dispatch._run_queued_plc_dispatch(result, source=source, fingerprint=fingerprint)

    def public_path_sanitized(value: Any) -> Any:
        return ports._service_paths().public_path_sanitized(value)

    _plc_workstation_workflows = PlcWorkstationWorkflows(files=WorkstationRepositoryFiles(_business_files=lambda: ports._business_files(), DATA_DIR=lambda: values.DATA_DIR, PLC_WEB_SERIAL_STATE_PATH=lambda: values.PLC_WEB_SERIAL_STATE_PATH), repository_policy=WorkstationRepositoryPolicy(PLC_WEB_SERIAL_JSON_TEST_ENV=lambda: values.PLC_WEB_SERIAL_JSON_TEST_ENV, PlcConfigError=lambda: PlcConfigError, SYSTEM_OWNER_ID=lambda: values.SYSTEM_OWNER_ID), storage=WorkstationAccess(runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none, _config_io_lock=lambda: ports._config_io_lock()), identity=WorkstationIdentity(PLC_WORKSTATION_COOKIE=lambda: values.PLC_WORKSTATION_COOKIE, PLC_WORKSTATION_COOKIE_TTL_SECONDS=lambda: values.PLC_WORKSTATION_COOKIE_TTL_SECONDS, SYSTEM_OWNER_ID=lambda: values.SYSTEM_OWNER_ID, current_auth_user=lambda: ports.current_auth_user(), request_is_https=lambda: request_is_https), station_policy=StationPolicy(clock=lambda: time.time, PlcConfigError=lambda: PlcConfigError, HTTPException=lambda: HTTPException, DEFAULT_WEB_SERIAL_CONFIG=lambda: DEFAULT_WEB_SERIAL_CONFIG, WEB_SERIAL_ACTIVE_LEASE_SECONDS=lambda: WEB_SERIAL_ACTIVE_LEASE_SECONDS, WEB_SERIAL_HEARTBEAT_SECONDS=lambda: WEB_SERIAL_HEARTBEAT_SECONDS, WEB_SERIAL_PROTOCOL_VERSION=lambda: WEB_SERIAL_PROTOCOL_VERSION, migrate_web_serial_config=lambda: migrate_web_serial_config, normalize_web_serial_config=lambda: normalize_web_serial_config, web_serial_profile_fingerprint=lambda: web_serial_profile_fingerprint), projection=WorkstationProjection(current_release_version=lambda: current_release_version, build_web_serial_capture_read_plan=lambda: build_web_serial_capture_read_plan, web_serial_resolved_addresses=lambda: web_serial_resolved_addresses), dispatch_policy=BrowserDispatchPolicy(PlcConfigError=lambda: PlcConfigError, LEGACY_WEB_SERIAL_PROTOCOL_VERSION=lambda: LEGACY_WEB_SERIAL_PROTOCOL_VERSION, WEB_SERIAL_PROTOCOL_VERSION=lambda: WEB_SERIAL_PROTOCOL_VERSION, WEB_SERIAL_PLAN_DEADLINE_SECONDS=lambda: WEB_SERIAL_PLAN_DEADLINE_SECONDS, PLC_PROTOCOL_ID=lambda: PLC_PROTOCOL_ID, build_legacy_web_serial_plan=lambda: build_legacy_web_serial_plan, build_web_serial_plan=lambda: build_web_serial_plan, normalize_legacy_web_serial_config=lambda: normalize_legacy_web_serial_config, normalize_web_serial_config=lambda: normalize_web_serial_config, migrate_web_serial_config=lambda: migrate_web_serial_config, legacy_web_serial_config_fingerprint=lambda: legacy_web_serial_config_fingerprint, web_serial_config_fingerprint=lambda: web_serial_config_fingerprint))
    _plc_workstation_repository = _plc_workstation_workflows.repository
    _plc_station_service = _plc_workstation_workflows.station
    _plc_lease_diagnostic_workflows = PlcLeaseDiagnosticWorkflows(workstation=_plc_workstation_workflows, admission=LeaseAdmission(current_user=lambda: ports.current_auth_user(), release_version=lambda: current_release_version, fullmatch=lambda: re.fullmatch, protocol_version=lambda: WEB_SERIAL_PROTOCOL_VERSION, require_model_permission=lambda: require_analyze_model_permission, migrate_config=lambda: migrate_web_serial_config, clock=lambda: time.time, uuid4=lambda: uuid.uuid4, connecting_ttl=lambda: WEB_SERIAL_CONNECTING_LEASE_SECONDS, active_ttl=lambda: WEB_SERIAL_ACTIVE_LEASE_SECONDS, config_error=lambda: PlcConfigError), maintenance_policy=LeaseMaintenancePolicy(current_user=lambda: ports.current_auth_user(), clock=lambda: time.time, active_ttl=lambda: WEB_SERIAL_ACTIVE_LEASE_SECONDS, config_error=lambda: PlcConfigError), diagnostic_policy=DiagnosticPolicy(token_hex=lambda: secrets.token_hex, token_urlsafe=lambda: secrets.token_urlsafe, config_error=lambda: PlcConfigError, clock=lambda: time.time, ceil=lambda: math.ceil, protocol_version=lambda: WEB_SERIAL_PROTOCOL_VERSION, frames=lambda: build_web_serial_diagnostic_plan, compare_digest=lambda: hmac.compare_digest, current_user=lambda: ports.current_auth_user()))
    _plc_lease_acquisition = _plc_lease_diagnostic_workflows.acquisition
    _plc_lease_maintenance = _plc_lease_diagnostic_workflows.maintenance
    _plc_web_serial_require_active_lease = _plc_station_service._plc_web_serial_require_active_lease
    _plc_diagnostic_state = _plc_lease_diagnostic_workflows.diagnostics
    _plc_browser_dispatch = _plc_workstation_workflows.browser
    _plc_transport_factory: Callable[[dict[str, Any]], Any] | None = None
    _plc_io_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='plc-io')
    _plc_dispatch_slots = threading.BoundedSemaphore(1)
    _plc_write_pending = threading.Event()
    _plc_active_attempts: dict[str, dict[str, Any]] = {}
    _plc_dispatch_runtime: dict[str, dict[str, Any]] = {}
    _PLC_RUNTIME_LIMIT = 200
    _plc_process_owner_id = f'{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}'
    _legacy_plc_workers = LegacyPlcWorkers(heartbeat=LegacyHeartbeatCapabilities(repository=lambda: runtime_postgres_repository_or_none, config=lambda: load_config, namespace=lambda: raw_plc_namespace, renew=lambda: plc_claim_or_renew_io_owner, seconds=lambda: values.PLC_IO_OWNER_HEARTBEAT_SECONDS), loops=LegacyLoopCapabilities(reconcile=lambda: plc_reconcile_pending_dispatches_once, poll=lambda: plc_capture_poll_once, seconds=lambda: values.PLC_CAPTURE_POLL_SECONDS))
    _legacy_plc_activation = LegacyActivationPolicy(sources=LegacyActivationSources(repository=lambda: runtime_postgres_repository_or_none, transport=lambda: _plc_transport_factory, identity=lambda: ports._request_user(), getenv=lambda: environment.get, canonical=lambda: _plc_canonical), checks=LegacyActivationChecks(coordination=lambda: plc_pg_coordination_available, fingerprint=lambda: plc_profile_fingerprint, device=lambda: plc_device_profile_verified, read=lambda: plc_read_profile_verified, serial=lambda: plc_serial_dependency_available))
    plc_pg_coordination_available = _legacy_plc_activation.plc_pg_coordination_available
    plc_profile_fingerprint = _legacy_plc_activation.plc_profile_fingerprint
    plc_device_profile_verified = _legacy_plc_activation.plc_device_profile_verified
    plc_read_profile_verified = _legacy_plc_activation.plc_read_profile_verified
    plc_serial_dependency_available = _legacy_plc_activation.plc_serial_dependency_available
    plc_activation_errors = _legacy_plc_activation.plc_activation_errors
    _legacy_capture_workflows = PlcCaptureWorkflows(storage=CaptureStorage(repository=lambda: runtime_postgres_repository_or_none, mutate_config=lambda: ports.mutate_app_config_atomically(), load_config=lambda: load_config, start_heartbeat=lambda: plc_start_owner_heartbeat), coordination_policy=LegacyCoordinationPolicy(runtime_key=lambda: values.PLC_RUNTIME_COORDINATION_KEY, receipts_key=lambda: values.PLC_CAPTURE_RESULTS_KEY, process_id=lambda: _plc_process_owner_id, lease_seconds=lambda: values.PLC_IO_OWNER_LEASE_SECONDS, quarantine_seconds=lambda: values.PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS, clock=lambda: time.time), capture_policy=CapturePolicy(_plc_canonical=lambda: _plc_canonical, PlcConfigError=lambda: PlcConfigError, PLC_CAPTURE_EVENT_TTL_SECONDS=lambda: values.PLC_CAPTURE_EVENT_TTL_SECONDS, PLC_CAPTURE_PROCESSING_TTL_SECONDS=lambda: values.PLC_CAPTURE_PROCESSING_TTL_SECONDS, PLC_CAPTURE_RESULTS_KEY=lambda: values.PLC_CAPTURE_RESULTS_KEY, PLC_CONTROL_GENERATION_KEY=lambda: values.PLC_CONTROL_GENERATION_KEY, PLC_RUNTIME_COORDINATION_KEY=lambda: values.PLC_RUNTIME_COORDINATION_KEY, PLC_WORKER_TOTAL_TIMEOUT_SECONDS=lambda: values.PLC_WORKER_TOTAL_TIMEOUT_SECONDS))
    _legacy_plc_coordination = _legacy_capture_workflows.coordination
    mutate_plc_runtime_coordination = _legacy_plc_coordination.mutate_plc_runtime_coordination
    plc_completed_capture_receipt = _legacy_plc_coordination.plc_completed_capture_receipt
    _mutate_plc_runtime_rows = _legacy_plc_coordination._mutate_plc_runtime_rows
    plc_claim_or_renew_io_owner = _legacy_plc_coordination.plc_claim_or_renew_io_owner
    plc_start_owner_heartbeat = _legacy_plc_workers.plc_start_owner_heartbeat
    plc_current_process_owns_io = _legacy_plc_coordination.plc_current_process_owns_io
    _plc_capture_state = _legacy_capture_workflows.capture
    _legacy_plc_operations = LegacyPlcOperations(configuration=LegacyOperationConfiguration(load=lambda: load_config, normalize=lambda: normalize_plc_config, namespace=lambda: raw_plc_namespace, error=lambda: PlcConfigError, activation=lambda: plc_activation_errors, generation_key=lambda: values.PLC_CONTROL_GENERATION_KEY), ownership=LegacyOperationOwnership(claim=lambda: plc_claim_or_renew_io_owner, owns=lambda: plc_current_process_owns_io), dispatch=LegacyDispatchIteration(records=lambda: plc_dispatch_audit_records, verify=lambda: verify_persisted_plc_dispatch, conflict=lambda: PlcDispatchStateConflict, pristine=lambda: plc_dispatch_is_pristine_queue, blocker=lambda: plc_dispatch_adoption_blocker, finalize=lambda: plc_finalize_dispatch, run=lambda: _run_queued_plc_dispatch), capture=LegacyCaptureIteration(pending=lambda: _plc_write_pending, slots=lambda: _plc_dispatch_slots, read=lambda: read_d_register_value, transport=lambda: _plc_transport_factory, disarm=lambda: plc_capture_disarm, observe=lambda: plc_apply_capture_observation))
    plc_reconcile_pending_dispatches_once = _legacy_plc_operations.plc_reconcile_pending_dispatches_once
    start_plc_dispatch_reconciler = _legacy_plc_workers.start_plc_dispatch_reconciler
    plc_capture_poll_once = _legacy_plc_operations.plc_capture_poll_once
    start_plc_capture_poller = _legacy_plc_workers.start_plc_capture_poller
    _legacy_plc_records = _native_LegacyDispatchRecords_2502(sources=DispatchRecordSources(config=lambda: load_config, namespace=lambda: raw_plc_namespace, sanitize=lambda: public_path_sanitized, records=lambda: plc_dispatch_audit_records, existing=lambda: plc_dispatch_existing, verify=lambda: verify_persisted_plc_dispatch), policy=DispatchRecordPolicy(absent=lambda: PLC_CONFIG_ABSENT, guard=lambda: ports._config_io_lock(), conflict=lambda: PlcDispatchStateConflict, clock=lambda: time.time))
    plc_dispatch_audit_records = _legacy_plc_records.plc_dispatch_audit_records
    raw_plc_namespace = _legacy_plc_records.raw_plc_namespace
    plc_config_audit_snapshot = _legacy_plc_records.plc_config_audit_snapshot
    plc_dispatch_existing = _legacy_plc_records.plc_dispatch_existing
    get_validated_idempotent_dispatch = _legacy_plc_records.get_validated_idempotent_dispatch
    plc_dispatch_conflict_response = _legacy_plc_records.plc_dispatch_conflict_response
    _plc_dispatch_mutations = PlcDispatchMutations(storage=DispatchMutationStorage(runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none, mutate_app_config_atomically=lambda: ports.mutate_app_config_atomically(), plc_dispatch_audit_records=lambda: plc_dispatch_audit_records, verify_persisted_plc_dispatch=lambda: verify_persisted_plc_dispatch, raw_plc_namespace=lambda: raw_plc_namespace, plc_pg_coordination_available=lambda: plc_pg_coordination_available, public_path_sanitized=lambda: public_path_sanitized, plc_dispatch_existing=lambda: plc_dispatch_existing), policy=DispatchMutationPolicy(PlcDispatchStateConflict=lambda: PlcDispatchStateConflict, PLC_CONFIG_ABSENT=lambda: PLC_CONFIG_ABSENT, normalize_plc_config=lambda: normalize_plc_config, PlcConfigError=lambda: PlcConfigError, PLC_CONTROL_GENERATION_KEY=lambda: values.PLC_CONTROL_GENERATION_KEY, build_plc_dispatch_plan=lambda: build_plc_dispatch_plan, PLC_RECORD_SCHEMA_VERSION=lambda: values.PLC_RECORD_SCHEMA_VERSION, PLC_PROTOCOL_CONTRACT_VERSION=lambda: values.PLC_PROTOCOL_CONTRACT_VERSION, PLC_QUEUE_WAIT_SECONDS=lambda: values.PLC_QUEUE_WAIT_SECONDS, PLC_FINALIZE_REASONS=lambda: PLC_FINALIZE_REASONS), events=DispatchMutationEvents(project_plc_dispatch_events=lambda: project_plc_dispatch_events, PlcDispatchTransitionKind=lambda: PlcDispatchTransitionKind, _PLC_TYPED_EVENT_DERIVERS=lambda: _PLC_TYPED_EVENT_DERIVERS, _PLC_TYPED_EVENT_FIELDS=lambda: _PLC_TYPED_EVENT_FIELDS, validate_plc_dispatch_transition=lambda: validate_plc_dispatch_transition, _apply_plc_dispatch_event=lambda: _apply_plc_dispatch_event, plc_finalize_dispatch=lambda: plc_finalize_dispatch), evidence=DispatchMutationEvidence(PlcAttemptTerminalResult=lambda: PlcAttemptTerminalResult, PlcTerminalResultCode=lambda: PlcTerminalResultCode, PLC_TERMINAL_RESULT_CODES=lambda: PLC_TERMINAL_RESULT_CODES, PlcTransportPhase=lambda: PlcTransportPhase, PLC_TERMINAL_ALLOWED_PHASES=lambda: PLC_TERMINAL_ALLOWED_PHASES, PLC_TERMINAL_DIAGNOSTIC_SOURCES=lambda: PLC_TERMINAL_DIAGNOSTIC_SOURCES))
    _plc_dispatch_runtime_state = PlcDispatchRuntimeState(state=DispatchRuntimeState(_plc_dispatch_runtime=lambda: _plc_dispatch_runtime, _PLC_RUNTIME_LIMIT=lambda: _PLC_RUNTIME_LIMIT, _config_io_lock=lambda: ports._config_io_lock(), _plc_active_attempts=lambda: _plc_active_attempts, _plc_runtime_entry=lambda: _plc_runtime_entry, _hydrate_plc_runtime_entry=lambda: _hydrate_plc_runtime_entry), records=DispatchRuntimeRecords(load_config=lambda: load_config, plc_dispatch_audit_records=lambda: plc_dispatch_audit_records, plc_mark_deadline=lambda: plc_mark_deadline), policy=DispatchRuntimePolicy(plc_dispatch_is_pristine_queue=lambda: plc_dispatch_is_pristine_queue, _plc_canonical=lambda: _plc_canonical))
    _plc_legacy_dispatch = LegacyDispatch(policy=LegacyDispatchPolicy(PLC_CONTROL_GENERATION_KEY=lambda: values.PLC_CONTROL_GENERATION_KEY, PLC_FINALIZE_REASONS=lambda: PLC_FINALIZE_REASONS, PLC_QUEUE_WAIT_SECONDS=lambda: values.PLC_QUEUE_WAIT_SECONDS, PLC_WORKER_TOTAL_TIMEOUT_SECONDS=lambda: values.PLC_WORKER_TOTAL_TIMEOUT_SECONDS, PLC_TERMINAL_ALLOWED_PHASES=lambda: PLC_TERMINAL_ALLOWED_PHASES, PLC_TERMINAL_DIAGNOSTIC_SOURCES=lambda: PLC_TERMINAL_DIAGNOSTIC_SOURCES, PlcAttemptTerminalResult=lambda: PlcAttemptTerminalResult, PlcConfigError=lambda: PlcConfigError, PlcDispatchStateConflict=lambda: PlcDispatchStateConflict, PlcTerminalResultCode=lambda: PlcTerminalResultCode, PlcTransportError=lambda: PlcTransportError, PlcTransportPhase=lambda: PlcTransportPhase), configuration=LegacyDispatchConfiguration(load_config=lambda: load_config, normalize_plc_config=lambda: normalize_plc_config, raw_plc_namespace=lambda: raw_plc_namespace, plc_activation_errors=lambda: plc_activation_errors, plc_config_audit_snapshot=lambda: plc_config_audit_snapshot, plc_claim_or_renew_io_owner=lambda: plc_claim_or_renew_io_owner, plc_current_process_owns_io=lambda: plc_current_process_owns_io), records=_native_LegacyDispatchRecords_2812(plc_dispatch_identity=lambda: plc_dispatch_identity, get_validated_idempotent_dispatch=lambda: get_validated_idempotent_dispatch, plc_dispatch_record_is_terminal=lambda: plc_dispatch_record_is_terminal, plc_dispatch_is_pristine_queue=lambda: plc_dispatch_is_pristine_queue, plc_dispatch_adoption_blocker=lambda: plc_dispatch_adoption_blocker, create_plc_dispatch=lambda: create_plc_dispatch, plc_transition_attempting=lambda: plc_transition_attempting, plc_advance_attempt=lambda: plc_advance_attempt, plc_finalize_dispatch=lambda: plc_finalize_dispatch, plc_start_attempt=lambda: plc_start_attempt, plc_finish_attempt=lambda: plc_finish_attempt, plc_dispatch_conflict_response=lambda: plc_dispatch_conflict_response), execution=LegacyDispatchExecution(_config_io_lock=lambda: ports._config_io_lock(), _plc_active_attempts=lambda: _plc_active_attempts, _plc_runtime_entry=lambda: _plc_runtime_entry, _register_plc_dispatch_runtime=lambda: _register_plc_dispatch_runtime, _plc_deadline_snapshot=lambda: _plc_deadline_snapshot, _plc_dispatch_slots=lambda: _plc_dispatch_slots, _plc_write_pending=lambda: _plc_write_pending, _plc_io_executor=lambda: _plc_io_executor, _plc_transport_factory=lambda: _plc_transport_factory, dispatch_fx_plc_detection_result=lambda: dispatch_fx_plc_detection_result, dispatch_plc_for_detection=lambda: dispatch_plc_for_detection, _run_queued_plc_dispatch=lambda: _run_queued_plc_dispatch))
    _plc_config_diagnostics = _ConfigDiagnostics(_ConfigSources(load=lambda: load_config, raw_namespace=lambda: raw_plc_namespace, normalize=lambda: normalize_plc_config, defaults=lambda: DEFAULT_PLC_CONFIG, activation_errors=lambda: plc_activation_errors, dispatch_audit=lambda: plc_dispatch_audit_records), _ConfigDisplay(logical_address=lambda: logical_device_address, device_verified=lambda: plc_device_profile_verified, read_verified=lambda: plc_read_profile_verified), _ConfigRuntime(active_attempts=lambda: _plc_active_attempts_snapshot, audit_limit=lambda: values.PLC_DISPATCH_AUDIT_LIMIT, protocol_id=lambda: PLC_PROTOCOL_ID, generation_key=lambda: values.PLC_CONTROL_GENERATION_KEY, queue_wait_seconds=lambda: values.PLC_QUEUE_WAIT_SECONDS, worker_total_timeout_seconds=lambda: values.PLC_WORKER_TOTAL_TIMEOUT_SECONDS), _ConfigAccess(require_permission=lambda: ports.require_permission()), _ConfigErrors(config_error=lambda: PlcConfigError, http_error=lambda: HTTPException))
    _plc_workstation_management = _WorkstationManagement(_WorkstationAccess(require_permission=lambda: ports.require_permission(), station_from_request=lambda: plc_web_serial_station_from_request, require_station=lambda: require_plc_web_serial_station), _WorkstationProjection(station_payload=lambda: plc_web_serial_station_payload, unpaired_payload=lambda: plc_web_serial_unpaired_payload, list_workstations=lambda: plc_web_serial_list_workstations), _WorkstationMutation(pair=lambda: plc_web_serial_pair, update_config=lambda: plc_web_serial_update_config, set_verified=lambda: plc_web_serial_set_verified), _WorkstationErrors(config_error=lambda: PlcConfigError, http_error=lambda: HTTPException))
    _plc_connection_lease = _ConnectionLease(_LeaseAccess(require_station=lambda: require_plc_web_serial_station, require_model_permission=lambda: require_analyze_model_permission), _LeaseMutation(claim=lambda: plc_web_serial_claim_connecting_lease, activate=lambda: plc_web_serial_activate_lease, heartbeat=lambda: plc_web_serial_heartbeat, rebind_model=lambda: plc_web_serial_rebind_model, disconnect=lambda: plc_web_serial_release_lease), _LeaseErrors(config_error=lambda: PlcConfigError, http_error=lambda: HTTPException))
    _plc_dispatch_diagnostic = _DispatchDiagnostic(_DispatchAccess(require_permission=lambda: ports.require_permission(), require_station=lambda: require_plc_web_serial_station), _DispatchMutation(declare_attempt=lambda: plc_web_serial_declare_attempt, diagnostic_plan=lambda: plc_web_serial_diagnostic_plan, diagnostic_receipt=lambda: plc_web_serial_finish_diagnostic, diagnostic_confirm=lambda: plc_web_serial_confirm_diagnostic, record_receipt=lambda: plc_web_serial_record_receipt), _DispatchErrors(config_error=lambda: PlcConfigError, http_error=lambda: HTTPException))
    return PlcAssembly(
        _PLC_RUNTIME_LIMIT=_PLC_RUNTIME_LIMIT,
        _legacy_capture_workflows=_legacy_capture_workflows,
        _legacy_plc_activation=_legacy_plc_activation,
        _legacy_plc_coordination=_legacy_plc_coordination,
        _legacy_plc_operations=_legacy_plc_operations,
        _legacy_plc_records=_legacy_plc_records,
        _legacy_plc_workers=_legacy_plc_workers,
        _mutate_plc_runtime_rows=_mutate_plc_runtime_rows,
        _plc_active_attempts=_plc_active_attempts,
        _plc_browser_dispatch=_plc_browser_dispatch,
        _plc_capture_state=_plc_capture_state,
        _plc_config_diagnostics=_plc_config_diagnostics,
        _plc_connection_lease=_plc_connection_lease,
        _plc_diagnostic_state=_plc_diagnostic_state,
        _plc_dispatch_diagnostic=_plc_dispatch_diagnostic,
        _plc_dispatch_mutations=_plc_dispatch_mutations,
        _plc_dispatch_runtime=_plc_dispatch_runtime,
        _plc_dispatch_runtime_state=_plc_dispatch_runtime_state,
        _plc_dispatch_slots=_plc_dispatch_slots,
        _plc_io_executor=_plc_io_executor,
        _plc_lease_acquisition=_plc_lease_acquisition,
        _plc_lease_diagnostic_workflows=_plc_lease_diagnostic_workflows,
        _plc_lease_maintenance=_plc_lease_maintenance,
        _plc_legacy_dispatch=_plc_legacy_dispatch,
        _plc_process_owner_id=_plc_process_owner_id,
        _plc_station_service=_plc_station_service,
        _plc_transport_factory=_plc_transport_factory,
        _plc_web_serial_require_active_lease=_plc_web_serial_require_active_lease,
        _plc_workstation_management=_plc_workstation_management,
        _plc_workstation_repository=_plc_workstation_repository,
        _plc_workstation_workflows=_plc_workstation_workflows,
        _plc_write_pending=_plc_write_pending,
        get_validated_idempotent_dispatch=get_validated_idempotent_dispatch,
        mutate_plc_runtime_coordination=mutate_plc_runtime_coordination,
        plc_activation_errors=plc_activation_errors,
        plc_capture_poll_once=plc_capture_poll_once,
        plc_claim_or_renew_io_owner=plc_claim_or_renew_io_owner,
        plc_completed_capture_receipt=plc_completed_capture_receipt,
        plc_config_audit_snapshot=plc_config_audit_snapshot,
        plc_current_process_owns_io=plc_current_process_owns_io,
        plc_device_profile_verified=plc_device_profile_verified,
        plc_dispatch_audit_records=plc_dispatch_audit_records,
        plc_dispatch_conflict_response=plc_dispatch_conflict_response,
        plc_dispatch_existing=plc_dispatch_existing,
        plc_pg_coordination_available=plc_pg_coordination_available,
        plc_profile_fingerprint=plc_profile_fingerprint,
        plc_read_profile_verified=plc_read_profile_verified,
        plc_reconcile_pending_dispatches_once=plc_reconcile_pending_dispatches_once,
        plc_serial_dependency_available=plc_serial_dependency_available,
        plc_start_owner_heartbeat=plc_start_owner_heartbeat,
        raw_plc_namespace=raw_plc_namespace,
        start_plc_capture_poller=start_plc_capture_poller,
        start_plc_dispatch_reconciler=start_plc_dispatch_reconciler,
    )
