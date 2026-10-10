"""Historical default-only forwarders. Production business ports use owned graphs."""
from __future__ import annotations
from ..runtime.default_application import default_application as _application
import os
from typing import Any
from typing import Callable
from local_inspection_service.plc_fx_ascii import PlcAttemptTerminalResult
from local_inspection_service.schemas.plc import PlcConfigRequest
from local_inspection_service.plc.transition_policy import PlcDispatchTransitionKind
from local_inspection_service.schemas.plc import PlcWebSerialAttemptRequest
from local_inspection_service.schemas.plc import PlcWebSerialConfigRequest
from local_inspection_service.schemas.plc import PlcWebSerialDiagnosticConfirmRequest
from local_inspection_service.schemas.plc import PlcWebSerialDiagnosticReceiptRequest
from local_inspection_service.schemas.plc import PlcWebSerialReceiptRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseActivateRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseHeartbeatRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseRebindRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseRequest
from local_inspection_service.schemas.plc import PlcWorkstationPairRequest
from local_inspection_service.schemas.plc import PlcWorkstationVerifyRequest
from fastapi import Request
from fastapi import Response
_plc_browser_dispatch = _application.plc._plc_browser_dispatch
_plc_capture_state = _application.plc._plc_capture_state
_plc_config_diagnostics = _application.plc._plc_config_diagnostics
_plc_connection_lease = _application.plc._plc_connection_lease
_plc_diagnostic_state = _application.plc._plc_diagnostic_state
_plc_dispatch_diagnostic = _application.plc._plc_dispatch_diagnostic
_plc_dispatch_mutations = _application.plc._plc_dispatch_mutations
_plc_dispatch_runtime_state = _application.plc._plc_dispatch_runtime_state
_plc_lease_acquisition = _application.plc._plc_lease_acquisition
_plc_lease_maintenance = _application.plc._plc_lease_maintenance
_plc_legacy_dispatch = _application.plc._plc_legacy_dispatch
_plc_station_service = _application.plc._plc_station_service
_plc_workstation_management = _application.plc._plc_workstation_management
_plc_workstation_repository = _application.plc._plc_workstation_repository

def _plc_web_serial_empty_state() -> dict[str, dict[str, Any]]:
    return _plc_workstation_repository._plc_web_serial_empty_state()

def _plc_web_serial_load_local() -> dict[str, dict[str, Any]]:
    return _plc_workstation_repository._plc_web_serial_load_local()

def _plc_web_serial_save_local(state: dict[str, dict[str, Any]]) -> None:
    return _plc_workstation_repository._plc_web_serial_save_local(state)

def _plc_web_serial_record(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return _plc_workstation_repository._plc_web_serial_record(row)

def _plc_workstation_row(record: dict[str, Any]) -> dict[str, Any]:
    return _plc_workstation_repository._plc_workstation_row(record)

def _plc_workstation_lease_row(record: dict[str, Any]) -> dict[str, Any]:
    return _plc_workstation_repository._plc_workstation_lease_row(record)

def _plc_web_serial_dispatch_row(record: dict[str, Any]) -> dict[str, Any]:
    return _plc_workstation_repository._plc_web_serial_dispatch_row(record)

def _plc_web_serial_upsert_row(table_name: str, row: dict[str, Any], local_key: str, row_id: str) -> None:
    return _plc_workstation_repository._plc_web_serial_upsert_row(table_name, row, local_key, row_id)

def _plc_web_serial_mutate(station_id: str, dispatch_id: str | None, mutator: Callable[[dict[str, dict[str, Any] | None]], None]) -> dict[str, dict[str, Any] | None]:
    return _plc_workstation_repository._plc_web_serial_mutate(station_id, dispatch_id, mutator)

def _plc_web_serial_token_hash(token: str) -> str:
    return _plc_station_service._plc_web_serial_token_hash(token)

def plc_web_serial_station_from_request(request: Request) -> dict[str, Any] | None:
    return _plc_station_service.plc_web_serial_station_from_request(request)

def require_plc_web_serial_station(request: Request) -> dict[str, Any]:
    return _plc_station_service.require_plc_web_serial_station(request)

def plc_web_serial_current_lease(station_id: str) -> dict[str, Any] | None:
    return _plc_station_service.plc_web_serial_current_lease(station_id)

def plc_web_serial_recent_dispatches(station_id: str, limit: int=20) -> list[dict[str, Any]]:
    return _plc_station_service.plc_web_serial_recent_dispatches(station_id, limit)

def plc_web_serial_ensure_current_station_contract(station: dict[str, Any]) -> dict[str, Any]:
    return _plc_station_service.plc_web_serial_ensure_current_station_contract(station)

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

def plc_web_serial_begin_camera_detection(station_id: str, session_id: str, camera_request_id: str, model_id: str, fingerprint: str) -> tuple[dict[str, Any], bool]:
    return _plc_browser_dispatch.plc_web_serial_begin_camera_detection(station_id, session_id, camera_request_id, model_id, fingerprint)

def plc_web_serial_finish_camera_detection(station_id: str, dispatch_id: str, session_id: str, result: dict[str, Any] | None, error: str='') -> dict[str, Any]:
    return _plc_browser_dispatch.plc_web_serial_finish_camera_detection(station_id, dispatch_id, session_id, result, error)

def plc_web_serial_dispatch_public(record: dict[str, Any]) -> dict[str, Any]:
    return _plc_browser_dispatch.plc_web_serial_dispatch_public(record)

def verify_plc_web_serial_dispatch(record: dict[str, Any], station: dict[str, Any], *, require_frames: bool=True, require_current_config: bool=True) -> None:
    return _plc_browser_dispatch.verify_plc_web_serial_dispatch(record, station, require_frames=require_frames, require_current_config=require_current_config)

def plc_web_serial_declare_attempt(station_id: str, dispatch_id: str, request: PlcWebSerialAttemptRequest) -> dict[str, Any]:
    return _plc_browser_dispatch.plc_web_serial_declare_attempt(station_id, dispatch_id, request)

def _plc_web_serial_receipt_outcome(frames: list[dict[str, Any]], operations: list[dict[str, Any]]) -> str:
    return _plc_browser_dispatch._plc_web_serial_receipt_outcome(frames, operations)

def plc_web_serial_record_receipt(station_id: str, dispatch_id: str, request: PlcWebSerialReceiptRequest) -> dict[str, Any]:
    return _plc_browser_dispatch.plc_web_serial_record_receipt(station_id, dispatch_id, request)

def _plc_capture_runtime(state: dict[str, Any]) -> dict[str, Any]:
    return _plc_capture_state._plc_capture_runtime(state)

def _plc_expire_capture_state(capture: dict[str, Any], now: float) -> None:
    return _plc_capture_state._plc_expire_capture_state(capture, now)

def plc_claim_capture_session(user_id: str, model_id: str) -> dict[str, Any]:
    return _plc_capture_state.plc_claim_capture_session(user_id, model_id)

def plc_heartbeat_capture_session(session_id: str, user_id: str) -> dict[str, Any]:
    return _plc_capture_state.plc_heartbeat_capture_session(session_id, user_id)

def plc_release_capture_session(session_id: str, user_id: str) -> None:
    return _plc_capture_state.plc_release_capture_session(session_id, user_id)

def plc_capture_disarm(reason: str) -> None:
    return _plc_capture_state.plc_capture_disarm(reason)

def plc_apply_capture_observation(value: int, *, generation: int, owner_epoch: int, trigger_value: int) -> dict[str, Any] | None:
    """Persist one read observation and atomically create at most one edge event."""
    return _plc_capture_state.plc_apply_capture_observation(value, generation=generation, owner_epoch=owner_epoch, trigger_value=trigger_value)

def plc_claim_next_capture_event(session_id: str, user_id: str) -> dict[str, Any] | None:
    return _plc_capture_state.plc_claim_next_capture_event(session_id, user_id)

def plc_begin_triggered_analysis(trigger_id: str, session_id: str, user_id: str, model_id: str, fingerprint: str) -> dict[str, Any] | None:
    return _plc_capture_state.plc_begin_triggered_analysis(trigger_id, session_id, user_id, model_id, fingerprint)

def plc_prepare_triggered_dispatch(trigger_id: str, session_id: str, user_id: str) -> None:
    """Atomically prove a fresh session/event immediately before any PLC dispatch."""
    return _plc_capture_state.plc_prepare_triggered_dispatch(trigger_id, session_id, user_id)

def plc_finish_triggered_analysis(trigger_id: str, session_id: str, user_id: str, result: dict[str, Any] | None, error: str='') -> None:
    return _plc_capture_state.plc_finish_triggered_analysis(trigger_id, session_id, user_id, result, error)

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

def plc_cancel_dispatch(dispatch_id: str, *, expected_version: int, reason: str) -> dict[str, Any]:
    return _plc_dispatch_mutations.plc_cancel_dispatch(dispatch_id, expected_version=expected_version, reason=reason)

def persist_plc_dispatch_record(record: dict[str, Any], *, expected_version: int | None=None, transition_kind: Any=None) -> dict[str, Any]:
    """Retired raw compatibility shim; all creates and mutations use typed handlers."""
    return _plc_dispatch_mutations.persist_plc_dispatch_record(record, expected_version=expected_version, transition_kind=transition_kind)

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

def plc_config_response(config: dict[str, Any] | None=None) -> dict[str, Any]:
    return _plc_config_diagnostics.response(config)

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

async def dispatch_plc_for_detection_async(result: dict[str, Any], *, source: str, fingerprint: str, inline_fake_transport: bool=False) -> dict[str, Any]:
    """Run bounded synchronous serial work off the ASGI event loop."""
    return await _plc_legacy_dispatch.dispatch_plc_for_detection_async(result, source=source, fingerprint=fingerprint, inline_fake_transport=inline_fake_transport)

def update_plc_config(request: PlcConfigRequest) -> dict[str, Any]:
    return _plc_config_diagnostics.update(request)

def get_plc_web_serial_workstation(request: Request) -> dict[str, Any]:
    return _plc_workstation_management.get(request)

def list_plc_web_serial_workstations() -> dict[str, Any]:
    return _plc_workstation_management.list()

def pair_plc_web_serial_workstation(request: Request, response: Response, payload: PlcWorkstationPairRequest) -> dict[str, Any]:
    return _plc_workstation_management.pair(request, response, payload)

def update_plc_web_serial_workstation_config(request: Request, payload: PlcWebSerialConfigRequest) -> dict[str, Any]:
    return _plc_workstation_management.update_config(request, payload)

def verify_plc_web_serial_workstation_profile(request: Request, payload: PlcWorkstationVerifyRequest) -> dict[str, Any]:
    return _plc_workstation_management.verify_profile(request, payload)

def claim_plc_web_serial_connection(request: Request, payload: PlcWorkstationLeaseRequest) -> dict[str, Any]:
    return _plc_connection_lease.claim(request, payload)

def activate_plc_web_serial_connection(request: Request, payload: PlcWorkstationLeaseActivateRequest) -> dict[str, Any]:
    return _plc_connection_lease.activate(request, payload)

def heartbeat_plc_web_serial_connection(request: Request, payload: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
    return _plc_connection_lease.heartbeat(request, payload)

def rebind_plc_web_serial_connection_model(request: Request, payload: PlcWorkstationLeaseRebindRequest) -> dict[str, Any]:
    return _plc_connection_lease.rebind_model(request, payload)

def disconnect_plc_web_serial_connection(request: Request, payload: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
    return _plc_connection_lease.disconnect(request, payload)

def declare_plc_web_serial_attempt(dispatch_id: str, request: Request, payload: PlcWebSerialAttemptRequest) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.declare_attempt(dispatch_id, request, payload)

def create_plc_web_serial_diagnostic_plan(request: Request, payload: PlcWebSerialAttemptRequest) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.diagnostic_plan(request, payload)

def finish_plc_web_serial_diagnostic(request: Request, payload: PlcWebSerialDiagnosticReceiptRequest) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.diagnostic_receipt(request, payload)

def confirm_plc_web_serial_diagnostic(request: Request, payload: PlcWebSerialDiagnosticConfirmRequest) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.diagnostic_confirm(request, payload)

def record_plc_web_serial_receipt_endpoint(dispatch_id: str, request: Request, payload: PlcWebSerialReceiptRequest) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.record_receipt(dispatch_id, request, payload)
