"""Explicit native legacy PLC fixture; no application namespace mutation.

All dispatch, coordination, evidence and state algorithms are current native
services. The finite fake capabilities below preserve the old adversarial
matrices while the real factory is validated separately.
"""
from dataclasses import replace
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import os
import threading
from local_inspection_service.plc.capture_composition import CapturePolicy
from local_inspection_service.plc.capture_composition import CaptureStorage
from local_inspection_service.plc.dispatch_mutation_ports import DispatchMutationEvents
from local_inspection_service.plc.dispatch_mutation_ports import DispatchMutationEvidence
from local_inspection_service.plc.dispatch_mutation_ports import DispatchMutationPolicy
from local_inspection_service.plc.dispatch_mutation_ports import DispatchMutationStorage
from local_inspection_service.plc.legacy_records import DispatchRecordPolicy
from local_inspection_service.plc.legacy_records import DispatchRecordSources
from local_inspection_service.plc.dispatch_runtime_state_ports import DispatchRuntimePolicy
from local_inspection_service.plc.dispatch_runtime_state_ports import DispatchRuntimeRecords
from local_inspection_service.plc.dispatch_runtime_state_ports import DispatchRuntimeState
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
from local_inspection_service.plc.capture_composition import PlcCaptureWorkflows
from local_inspection_service.plc.dispatch_mutations import PlcDispatchMutations
from local_inspection_service.plc.dispatch_runtime_state import PlcDispatchRuntimeState
from local_inspection_service.plc.legacy_records import LegacyDispatchRecords as _native_LegacyDispatchRecords_2502
from local_inspection_service.plc.legacy_dispatch_ports import LegacyDispatchRecords as _native_LegacyDispatchRecords_2812


def build(default):
    api = SimpleNamespace(
        PLC_CAPTURE_EVENT_TTL_SECONDS=default.PLC_CAPTURE_EVENT_TTL_SECONDS,
        PLC_CAPTURE_POLL_SECONDS=default.PLC_CAPTURE_POLL_SECONDS,
        PLC_CAPTURE_PROCESSING_TTL_SECONDS=default.PLC_CAPTURE_PROCESSING_TTL_SECONDS,
        PLC_CAPTURE_RESULTS_KEY=default.PLC_CAPTURE_RESULTS_KEY,
        PLC_CONFIG_ABSENT=default.PLC_CONFIG_ABSENT,
        PLC_CONTROL_GENERATION_KEY=default.PLC_CONTROL_GENERATION_KEY,
        PLC_DISPATCH_AUDIT_LIMIT=default.PLC_DISPATCH_AUDIT_LIMIT,
        DEFAULT_PLC_CONFIG=default.DEFAULT_PLC_CONFIG,
        PLC_PROTOCOL_ID=default.PLC_PROTOCOL_ID,
        PLC_FINALIZE_REASONS=default.PLC_FINALIZE_REASONS,
        PLC_IO_OWNER_HEARTBEAT_SECONDS=default.PLC_IO_OWNER_HEARTBEAT_SECONDS,
        PLC_IO_OWNER_LEASE_SECONDS=default.PLC_IO_OWNER_LEASE_SECONDS,
        PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS=default.PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS,
        PLC_PROTOCOL_CONTRACT_VERSION=default.PLC_PROTOCOL_CONTRACT_VERSION,
        PLC_QUEUE_WAIT_SECONDS=default.PLC_QUEUE_WAIT_SECONDS,
        PLC_RECORD_SCHEMA_VERSION=default.PLC_RECORD_SCHEMA_VERSION,
        PLC_RUNTIME_COORDINATION_KEY=default.PLC_RUNTIME_COORDINATION_KEY,
        PLC_TERMINAL_ALLOWED_PHASES=default.PLC_TERMINAL_ALLOWED_PHASES,
        PLC_TERMINAL_DIAGNOSTIC_SOURCES=default.PLC_TERMINAL_DIAGNOSTIC_SOURCES,
        PLC_TERMINAL_RESULT_CODES=default.PLC_TERMINAL_RESULT_CODES,
        PLC_WORKER_TOTAL_TIMEOUT_SECONDS=default.PLC_WORKER_TOTAL_TIMEOUT_SECONDS,
        PlcAttemptTerminalResult=default.PlcAttemptTerminalResult,
        PlcConfigError=default.PlcConfigError,
        HTTPException=default.HTTPException,
        PlcDispatchStateConflict=default.PlcDispatchStateConflict,
        PlcDispatchTransitionKind=default.PlcDispatchTransitionKind,
        PlcTerminalResultCode=default.PlcTerminalResultCode,
        PlcTransportError=default.PlcTransportError,
        PlcTransportPhase=default.PlcTransportPhase,
        _PLC_RUNTIME_LIMIT=default._PLC_RUNTIME_LIMIT,
        _PLC_TYPED_EVENT_DERIVERS=default._PLC_TYPED_EVENT_DERIVERS,
        _PLC_TYPED_EVENT_FIELDS=default._PLC_TYPED_EVENT_FIELDS,
        _config_io_lock=default._config_io_lock,
        _plc_active_attempts=default._plc_active_attempts,
        _plc_canonical=default._plc_canonical,
        _plc_dispatch_runtime=default._plc_dispatch_runtime,
        _plc_dispatch_slots=default._plc_dispatch_slots,
        _plc_io_executor=default._plc_io_executor,
        _plc_process_owner_id=default._plc_process_owner_id,
        _plc_transport_factory=default._plc_transport_factory,
        _plc_write_pending=default._plc_write_pending,
        _request_user=default._request_user,
        _service_paths=default._service_paths,
        build_plc_dispatch_plan=default.build_plc_dispatch_plan,
        dispatch_fx_plc_detection_result=default.dispatch_fx_plc_detection_result,
        load_config=default.load_config,
        logical_device_address=default.logical_device_address,
        mutate_app_config_atomically=default.mutate_app_config_atomically,
        normalize_plc_config=default.normalize_plc_config,
        project_plc_dispatch_events=default.project_plc_dispatch_events,
        read_d_register_value=default.read_d_register_value,
        require_permission=default.require_permission,
        runtime_postgres_repository_or_none=default.runtime_postgres_repository_or_none,
        time=default.time,
        validate_plc_dispatch_transition=default.validate_plc_dispatch_transition,
        verify_persisted_plc_dispatch=default.verify_persisted_plc_dispatch,
        environment=os.environ,
    )
    api._plc_dispatch_runtime = {}
    api._plc_active_attempts = {}
    api._plc_write_pending = threading.Event()
    api._plc_dispatch_slots = threading.BoundedSemaphore(1)
    config = default._app_config_store
    config = replace(config, rows=replace(config.rows,
        runtime_postgres_repository_or_none=lambda: api.runtime_postgres_repository_or_none))
    api.load_config = config.load_config
    api.save_config = config.save_config
    api.save_app_config = config.save_app_config
    api.mutate_app_config_atomically = config.mutate_app_config_atomically
    def plc_capture_disarm(reason):
        return api._plc_capture_state.plc_capture_disarm(reason)
    api.plc_capture_disarm = plc_capture_disarm
    def plc_apply_capture_observation(value, *, generation, owner_epoch, trigger_value):
        """Persist one read observation and atomically create at most one edge event."""
        return api._plc_capture_state.plc_apply_capture_observation(value, generation=generation, owner_epoch=owner_epoch, trigger_value=trigger_value)
    api.plc_apply_capture_observation = plc_apply_capture_observation
    def create_plc_dispatch(*, source, request_id, passed, fingerprint, expected_generation=None):
        """Atomically derive a queued v1 record from the authoritative PLC namespace."""
        return api._plc_dispatch_mutations.create_plc_dispatch(source=source, request_id=request_id, passed=passed, fingerprint=fingerprint, expected_generation=expected_generation)
    api.create_plc_dispatch = create_plc_dispatch
    def _apply_plc_dispatch_event(dispatch_id, *, expected_version, transition_kind, event_payload):
        return api._plc_dispatch_mutations._apply_plc_dispatch_event(dispatch_id, expected_version=expected_version, transition_kind=transition_kind, event_payload=event_payload)
    api._apply_plc_dispatch_event = _apply_plc_dispatch_event
    def plc_transition_attempting(dispatch_id, *, expected_version):
        return api._plc_dispatch_mutations.plc_transition_attempting(dispatch_id, expected_version=expected_version)
    api.plc_transition_attempting = plc_transition_attempting
    def plc_start_attempt(dispatch_id, *, expected_version, target):
        return api._plc_dispatch_mutations.plc_start_attempt(dispatch_id, expected_version=expected_version, target=target)
    api.plc_start_attempt = plc_start_attempt
    def plc_advance_attempt(dispatch_id, *, expected_version, attempt_id, bytes_written, physical_status, outcome):
        return api._plc_dispatch_mutations.plc_advance_attempt(dispatch_id, expected_version=expected_version, attempt_id=attempt_id, bytes_written=bytes_written, physical_status=physical_status, outcome=outcome)
    api.plc_advance_attempt = plc_advance_attempt
    def plc_finish_attempt(dispatch_id, *, expected_version, attempt_id, terminal_result):
        return api._plc_dispatch_mutations.plc_finish_attempt(dispatch_id, expected_version=expected_version, attempt_id=attempt_id, terminal_result=terminal_result)
    api.plc_finish_attempt = plc_finish_attempt
    def plc_mark_deadline(dispatch_id, *, expected_version):
        return api._plc_dispatch_mutations.plc_mark_deadline(dispatch_id, expected_version=expected_version)
    api.plc_mark_deadline = plc_mark_deadline
    def plc_finalize_dispatch(dispatch_id, *, expected_version, reason=''):
        return api._plc_dispatch_mutations.plc_finalize_dispatch(dispatch_id, expected_version=expected_version, reason=reason)
    api.plc_finalize_dispatch = plc_finalize_dispatch
    def _plc_runtime_entry(dispatch_id):
        return api._plc_dispatch_runtime_state._plc_runtime_entry(dispatch_id)
    api._plc_runtime_entry = _plc_runtime_entry
    def _hydrate_plc_runtime_entry(dispatch_id):
        return api._plc_dispatch_runtime_state._hydrate_plc_runtime_entry(dispatch_id)
    api._hydrate_plc_runtime_entry = _hydrate_plc_runtime_entry
    def _register_plc_dispatch_runtime(dispatch_id):
        return api._plc_dispatch_runtime_state._register_plc_dispatch_runtime(dispatch_id)
    api._register_plc_dispatch_runtime = _register_plc_dispatch_runtime
    def _plc_deadline_snapshot(*, dispatch_id, source, request_id, passed):
        return api._plc_dispatch_runtime_state._plc_deadline_snapshot(dispatch_id=dispatch_id, source=source, request_id=request_id, passed=passed)
    api._plc_deadline_snapshot = _plc_deadline_snapshot
    def _plc_active_attempts_snapshot():
        return api._plc_dispatch_runtime_state._plc_active_attempts_snapshot()
    api._plc_active_attempts_snapshot = _plc_active_attempts_snapshot
    def plc_dispatch_identity(result, *, source, fingerprint):
        return api._plc_dispatch_runtime_state.plc_dispatch_identity(result, source=source, fingerprint=fingerprint)
    api.plc_dispatch_identity = plc_dispatch_identity
    def plc_dispatch_record_is_terminal(record):
        return api._plc_dispatch_runtime_state.plc_dispatch_record_is_terminal(record)
    api.plc_dispatch_record_is_terminal = plc_dispatch_record_is_terminal
    def plc_dispatch_is_pristine_queue(record):
        """Only a dispatch with proof that physical I/O never began may change owners."""
        return api._plc_dispatch_runtime_state.plc_dispatch_is_pristine_queue(record)
    api.plc_dispatch_is_pristine_queue = plc_dispatch_is_pristine_queue
    def plc_dispatch_adoption_blocker(record, *, settings, generation, now_ms=None):
        """Return a no-I/O reason when a queued record is unsafe or stale to adopt."""
        return api._plc_dispatch_runtime_state.plc_dispatch_adoption_blocker(record, settings=settings, generation=generation, now_ms=now_ms)
    api.plc_dispatch_adoption_blocker = plc_dispatch_adoption_blocker
    def dispatch_plc_for_detection(result, *, source, fingerprint, expected_generation=None):
        """Attach PLC sync status without changing or invalidating the detection result."""
        return api._plc_legacy_dispatch.dispatch_plc_for_detection(result, source=source, fingerprint=fingerprint, expected_generation=expected_generation)
    api.dispatch_plc_for_detection = dispatch_plc_for_detection
    def _run_queued_plc_dispatch(result, *, source, fingerprint):
        return api._plc_legacy_dispatch._run_queued_plc_dispatch(result, source=source, fingerprint=fingerprint)
    api._run_queued_plc_dispatch = _run_queued_plc_dispatch
    def public_path_sanitized(value):
        return api._service_paths.public_path_sanitized(value)
    api.public_path_sanitized = public_path_sanitized
    api._legacy_plc_workers = LegacyPlcWorkers(heartbeat=LegacyHeartbeatCapabilities(repository=lambda: api.runtime_postgres_repository_or_none, config=lambda: api.load_config, namespace=lambda: api.raw_plc_namespace, renew=lambda: api.plc_claim_or_renew_io_owner, seconds=lambda: api.PLC_IO_OWNER_HEARTBEAT_SECONDS), loops=LegacyLoopCapabilities(reconcile=lambda: api.plc_reconcile_pending_dispatches_once, poll=lambda: api.plc_capture_poll_once, seconds=lambda: api.PLC_CAPTURE_POLL_SECONDS))
    api._legacy_plc_activation = LegacyActivationPolicy(sources=LegacyActivationSources(repository=lambda: api.runtime_postgres_repository_or_none, transport=lambda: api._plc_transport_factory, identity=lambda: api._request_user, getenv=lambda: api.environment.get, canonical=lambda: api._plc_canonical), checks=LegacyActivationChecks(coordination=lambda: api.plc_pg_coordination_available, fingerprint=lambda: api.plc_profile_fingerprint, device=lambda: api.plc_device_profile_verified, read=lambda: api.plc_read_profile_verified, serial=lambda: api.plc_serial_dependency_available))
    api.plc_pg_coordination_available = api._legacy_plc_activation.plc_pg_coordination_available
    api.plc_profile_fingerprint = api._legacy_plc_activation.plc_profile_fingerprint
    api.plc_device_profile_verified = api._legacy_plc_activation.plc_device_profile_verified
    api.plc_read_profile_verified = api._legacy_plc_activation.plc_read_profile_verified
    api.plc_serial_dependency_available = api._legacy_plc_activation.plc_serial_dependency_available
    api.plc_activation_errors = api._legacy_plc_activation.plc_activation_errors
    api._legacy_capture_workflows = PlcCaptureWorkflows(storage=CaptureStorage(repository=lambda: api.runtime_postgres_repository_or_none, mutate_config=lambda: api.mutate_app_config_atomically, load_config=lambda: api.load_config, start_heartbeat=lambda: api.plc_start_owner_heartbeat), coordination_policy=LegacyCoordinationPolicy(runtime_key=lambda: api.PLC_RUNTIME_COORDINATION_KEY, receipts_key=lambda: api.PLC_CAPTURE_RESULTS_KEY, process_id=lambda: api._plc_process_owner_id, lease_seconds=lambda: api.PLC_IO_OWNER_LEASE_SECONDS, quarantine_seconds=lambda: api.PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS, clock=lambda: api.time.time), capture_policy=CapturePolicy(_plc_canonical=lambda: api._plc_canonical, PlcConfigError=lambda: api.PlcConfigError, PLC_CAPTURE_EVENT_TTL_SECONDS=lambda: api.PLC_CAPTURE_EVENT_TTL_SECONDS, PLC_CAPTURE_PROCESSING_TTL_SECONDS=lambda: api.PLC_CAPTURE_PROCESSING_TTL_SECONDS, PLC_CAPTURE_RESULTS_KEY=lambda: api.PLC_CAPTURE_RESULTS_KEY, PLC_CONTROL_GENERATION_KEY=lambda: api.PLC_CONTROL_GENERATION_KEY, PLC_RUNTIME_COORDINATION_KEY=lambda: api.PLC_RUNTIME_COORDINATION_KEY, PLC_WORKER_TOTAL_TIMEOUT_SECONDS=lambda: api.PLC_WORKER_TOTAL_TIMEOUT_SECONDS))
    api._legacy_plc_coordination = api._legacy_capture_workflows.coordination
    api.mutate_plc_runtime_coordination = api._legacy_plc_coordination.mutate_plc_runtime_coordination
    api.plc_completed_capture_receipt = api._legacy_plc_coordination.plc_completed_capture_receipt
    api._mutate_plc_runtime_rows = api._legacy_plc_coordination._mutate_plc_runtime_rows
    api.plc_claim_or_renew_io_owner = api._legacy_plc_coordination.plc_claim_or_renew_io_owner
    api.plc_start_owner_heartbeat = api._legacy_plc_workers.plc_start_owner_heartbeat
    api.plc_current_process_owns_io = api._legacy_plc_coordination.plc_current_process_owns_io
    api._plc_capture_state = api._legacy_capture_workflows.capture
    api._legacy_plc_operations = LegacyPlcOperations(configuration=LegacyOperationConfiguration(load=lambda: api.load_config, normalize=lambda: api.normalize_plc_config, namespace=lambda: api.raw_plc_namespace, error=lambda: api.PlcConfigError, activation=lambda: api.plc_activation_errors, generation_key=lambda: api.PLC_CONTROL_GENERATION_KEY), ownership=LegacyOperationOwnership(claim=lambda: api.plc_claim_or_renew_io_owner, owns=lambda: api.plc_current_process_owns_io), dispatch=LegacyDispatchIteration(records=lambda: api.plc_dispatch_audit_records, verify=lambda: api.verify_persisted_plc_dispatch, conflict=lambda: api.PlcDispatchStateConflict, pristine=lambda: api.plc_dispatch_is_pristine_queue, blocker=lambda: api.plc_dispatch_adoption_blocker, finalize=lambda: api.plc_finalize_dispatch, run=lambda: api._run_queued_plc_dispatch), capture=LegacyCaptureIteration(pending=lambda: api._plc_write_pending, slots=lambda: api._plc_dispatch_slots, read=lambda: api.read_d_register_value, transport=lambda: api._plc_transport_factory, disarm=lambda: api.plc_capture_disarm, observe=lambda: api.plc_apply_capture_observation))
    api.plc_reconcile_pending_dispatches_once = api._legacy_plc_operations.plc_reconcile_pending_dispatches_once
    api.start_plc_dispatch_reconciler = api._legacy_plc_workers.start_plc_dispatch_reconciler
    api.plc_capture_poll_once = api._legacy_plc_operations.plc_capture_poll_once
    api.start_plc_capture_poller = api._legacy_plc_workers.start_plc_capture_poller
    api._legacy_plc_records = _native_LegacyDispatchRecords_2502(sources=DispatchRecordSources(config=lambda: api.load_config, namespace=lambda: api.raw_plc_namespace, sanitize=lambda: api.public_path_sanitized, records=lambda: api.plc_dispatch_audit_records, existing=lambda: api.plc_dispatch_existing, verify=lambda: api.verify_persisted_plc_dispatch), policy=DispatchRecordPolicy(absent=lambda: api.PLC_CONFIG_ABSENT, guard=lambda: api._config_io_lock, conflict=lambda: api.PlcDispatchStateConflict, clock=lambda: api.time.time))
    api.plc_dispatch_audit_records = api._legacy_plc_records.plc_dispatch_audit_records
    api.raw_plc_namespace = api._legacy_plc_records.raw_plc_namespace
    api.plc_config_audit_snapshot = api._legacy_plc_records.plc_config_audit_snapshot
    api.plc_dispatch_existing = api._legacy_plc_records.plc_dispatch_existing
    api.get_validated_idempotent_dispatch = api._legacy_plc_records.get_validated_idempotent_dispatch
    api.plc_dispatch_conflict_response = api._legacy_plc_records.plc_dispatch_conflict_response
    api._plc_dispatch_mutations = PlcDispatchMutations(storage=DispatchMutationStorage(runtime_postgres_repository_or_none=lambda: api.runtime_postgres_repository_or_none, mutate_app_config_atomically=lambda: api.mutate_app_config_atomically, plc_dispatch_audit_records=lambda: api.plc_dispatch_audit_records, verify_persisted_plc_dispatch=lambda: api.verify_persisted_plc_dispatch, raw_plc_namespace=lambda: api.raw_plc_namespace, plc_pg_coordination_available=lambda: api.plc_pg_coordination_available, public_path_sanitized=lambda: api.public_path_sanitized, plc_dispatch_existing=lambda: api.plc_dispatch_existing), policy=DispatchMutationPolicy(PlcDispatchStateConflict=lambda: api.PlcDispatchStateConflict, PLC_CONFIG_ABSENT=lambda: api.PLC_CONFIG_ABSENT, normalize_plc_config=lambda: api.normalize_plc_config, PlcConfigError=lambda: api.PlcConfigError, PLC_CONTROL_GENERATION_KEY=lambda: api.PLC_CONTROL_GENERATION_KEY, build_plc_dispatch_plan=lambda: api.build_plc_dispatch_plan, PLC_RECORD_SCHEMA_VERSION=lambda: api.PLC_RECORD_SCHEMA_VERSION, PLC_PROTOCOL_CONTRACT_VERSION=lambda: api.PLC_PROTOCOL_CONTRACT_VERSION, PLC_QUEUE_WAIT_SECONDS=lambda: api.PLC_QUEUE_WAIT_SECONDS, PLC_FINALIZE_REASONS=lambda: api.PLC_FINALIZE_REASONS), events=DispatchMutationEvents(project_plc_dispatch_events=lambda: api.project_plc_dispatch_events, PlcDispatchTransitionKind=lambda: api.PlcDispatchTransitionKind, _PLC_TYPED_EVENT_DERIVERS=lambda: api._PLC_TYPED_EVENT_DERIVERS, _PLC_TYPED_EVENT_FIELDS=lambda: api._PLC_TYPED_EVENT_FIELDS, validate_plc_dispatch_transition=lambda: api.validate_plc_dispatch_transition, _apply_plc_dispatch_event=lambda: api._apply_plc_dispatch_event, plc_finalize_dispatch=lambda: api.plc_finalize_dispatch), evidence=DispatchMutationEvidence(PlcAttemptTerminalResult=lambda: api.PlcAttemptTerminalResult, PlcTerminalResultCode=lambda: api.PlcTerminalResultCode, PLC_TERMINAL_RESULT_CODES=lambda: api.PLC_TERMINAL_RESULT_CODES, PlcTransportPhase=lambda: api.PlcTransportPhase, PLC_TERMINAL_ALLOWED_PHASES=lambda: api.PLC_TERMINAL_ALLOWED_PHASES, PLC_TERMINAL_DIAGNOSTIC_SOURCES=lambda: api.PLC_TERMINAL_DIAGNOSTIC_SOURCES))
    api._plc_dispatch_runtime_state = PlcDispatchRuntimeState(state=DispatchRuntimeState(_plc_dispatch_runtime=lambda: api._plc_dispatch_runtime, _PLC_RUNTIME_LIMIT=lambda: api._PLC_RUNTIME_LIMIT, _config_io_lock=lambda: api._config_io_lock, _plc_active_attempts=lambda: api._plc_active_attempts, _plc_runtime_entry=lambda: api._plc_runtime_entry, _hydrate_plc_runtime_entry=lambda: api._hydrate_plc_runtime_entry), records=DispatchRuntimeRecords(load_config=lambda: api.load_config, plc_dispatch_audit_records=lambda: api.plc_dispatch_audit_records, plc_mark_deadline=lambda: api.plc_mark_deadline), policy=DispatchRuntimePolicy(plc_dispatch_is_pristine_queue=lambda: api.plc_dispatch_is_pristine_queue, _plc_canonical=lambda: api._plc_canonical))
    api._plc_legacy_dispatch = LegacyDispatch(policy=LegacyDispatchPolicy(PLC_CONTROL_GENERATION_KEY=lambda: api.PLC_CONTROL_GENERATION_KEY, PLC_FINALIZE_REASONS=lambda: api.PLC_FINALIZE_REASONS, PLC_QUEUE_WAIT_SECONDS=lambda: api.PLC_QUEUE_WAIT_SECONDS, PLC_WORKER_TOTAL_TIMEOUT_SECONDS=lambda: api.PLC_WORKER_TOTAL_TIMEOUT_SECONDS, PLC_TERMINAL_ALLOWED_PHASES=lambda: api.PLC_TERMINAL_ALLOWED_PHASES, PLC_TERMINAL_DIAGNOSTIC_SOURCES=lambda: api.PLC_TERMINAL_DIAGNOSTIC_SOURCES, PlcAttemptTerminalResult=lambda: api.PlcAttemptTerminalResult, PlcConfigError=lambda: api.PlcConfigError, PlcDispatchStateConflict=lambda: api.PlcDispatchStateConflict, PlcTerminalResultCode=lambda: api.PlcTerminalResultCode, PlcTransportError=lambda: api.PlcTransportError, PlcTransportPhase=lambda: api.PlcTransportPhase), configuration=LegacyDispatchConfiguration(load_config=lambda: api.load_config, normalize_plc_config=lambda: api.normalize_plc_config, raw_plc_namespace=lambda: api.raw_plc_namespace, plc_activation_errors=lambda: api.plc_activation_errors, plc_config_audit_snapshot=lambda: api.plc_config_audit_snapshot, plc_claim_or_renew_io_owner=lambda: api.plc_claim_or_renew_io_owner, plc_current_process_owns_io=lambda: api.plc_current_process_owns_io), records=_native_LegacyDispatchRecords_2812(plc_dispatch_identity=lambda: api.plc_dispatch_identity, get_validated_idempotent_dispatch=lambda: api.get_validated_idempotent_dispatch, plc_dispatch_record_is_terminal=lambda: api.plc_dispatch_record_is_terminal, plc_dispatch_is_pristine_queue=lambda: api.plc_dispatch_is_pristine_queue, plc_dispatch_adoption_blocker=lambda: api.plc_dispatch_adoption_blocker, create_plc_dispatch=lambda: api.create_plc_dispatch, plc_transition_attempting=lambda: api.plc_transition_attempting, plc_advance_attempt=lambda: api.plc_advance_attempt, plc_finalize_dispatch=lambda: api.plc_finalize_dispatch, plc_start_attempt=lambda: api.plc_start_attempt, plc_finish_attempt=lambda: api.plc_finish_attempt, plc_dispatch_conflict_response=lambda: api.plc_dispatch_conflict_response), execution=LegacyDispatchExecution(_config_io_lock=lambda: api._config_io_lock, _plc_active_attempts=lambda: api._plc_active_attempts, _plc_runtime_entry=lambda: api._plc_runtime_entry, _register_plc_dispatch_runtime=lambda: api._register_plc_dispatch_runtime, _plc_deadline_snapshot=lambda: api._plc_deadline_snapshot, _plc_dispatch_slots=lambda: api._plc_dispatch_slots, _plc_write_pending=lambda: api._plc_write_pending, _plc_io_executor=lambda: api._plc_io_executor, _plc_transport_factory=lambda: api._plc_transport_factory, dispatch_fx_plc_detection_result=lambda: api.dispatch_fx_plc_detection_result, dispatch_plc_for_detection=lambda: api.dispatch_plc_for_detection, _run_queued_plc_dispatch=lambda: api._run_queued_plc_dispatch))
    api.persist_plc_dispatch_record = api._plc_dispatch_mutations.persist_plc_dispatch_record
    api.plc_cancel_dispatch = api._plc_dispatch_mutations.plc_cancel_dispatch
    api.dispatch_plc_for_detection_async = api._plc_legacy_dispatch.dispatch_plc_for_detection_async
    from local_inspection_service.plc.config_diagnostics import ConfigDiagnostics
    from local_inspection_service.plc.config_diagnostics_ports import (
        ConfigAccess, ConfigDisplay, ConfigErrors, ConfigRuntime, ConfigSources)
    api._plc_config_diagnostics = ConfigDiagnostics(
        ConfigSources(lambda: api.load_config, lambda: api.raw_plc_namespace,
                      lambda: api.normalize_plc_config, lambda: api.DEFAULT_PLC_CONFIG,
                      lambda: api.plc_activation_errors, lambda: api.plc_dispatch_audit_records),
        ConfigDisplay(lambda: api.logical_device_address,
                      lambda: api.plc_device_profile_verified, lambda: api.plc_read_profile_verified),
        ConfigRuntime(lambda: api._plc_active_attempts_snapshot,
                      lambda: api.PLC_DISPATCH_AUDIT_LIMIT, lambda: api.PLC_PROTOCOL_ID,
                      lambda: api.PLC_CONTROL_GENERATION_KEY, lambda: api.PLC_QUEUE_WAIT_SECONDS,
                      lambda: api.PLC_WORKER_TOTAL_TIMEOUT_SECONDS),
        ConfigAccess(lambda: api.require_permission),
        ConfigErrors(lambda: api.PlcConfigError, lambda: api.HTTPException))
    api.plc_config_response = api._plc_config_diagnostics.response
    # Constructors above do not select lazy inputs or submit work. Allocate
    # the fixture executor only once construction has successfully completed.
    api._plc_io_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='test-plc-io')
    return api
