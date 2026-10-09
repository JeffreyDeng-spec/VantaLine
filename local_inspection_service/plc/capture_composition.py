"""Own retained capture state and coordination without activating physical I/O."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from .legacy_coordination import (LegacyRuntimeCoordination, LegacyCoordinationStorage,
    LegacyCoordinationPolicy, NamespaceRepository)
from .plc_capture_state import PlcCaptureState
from .plc_capture_state_ports import CaptureStateTransactions, CaptureStatePolicy
from ..plc_fx_ascii import PlcConfigError
Record = dict[str, Any]
Mutation = Callable[[Record], None]

@dataclass(frozen=True)
class CaptureStorage:
    repository: Callable[[], Callable[[], NamespaceRepository | None]]
    mutate_config: Callable[[], Callable[[Mutation], Record]]
    load_config: Callable[[], Callable[[], Record]]
    start_heartbeat: Callable[[], Callable[[int], None]]

@dataclass(frozen=True)
class CapturePolicy:
    _plc_canonical: Callable[[], Callable[[Any], str]]
    PlcConfigError: Callable[[], type[PlcConfigError]]
    PLC_CAPTURE_EVENT_TTL_SECONDS: Callable[[], float]
    PLC_CAPTURE_PROCESSING_TTL_SECONDS: Callable[[], float]
    PLC_CAPTURE_RESULTS_KEY: Callable[[], str]
    PLC_CONTROL_GENERATION_KEY: Callable[[], str]
    PLC_RUNTIME_COORDINATION_KEY: Callable[[], str]
    PLC_WORKER_TOTAL_TIMEOUT_SECONDS: Callable[[], float]

class PlcCaptureWorkflows:
    """Inert graph; retained legacy state remains distinct from browser leases."""
    def __init__(self, *, storage: CaptureStorage, coordination_policy: LegacyCoordinationPolicy,
                 capture_policy: CapturePolicy):
        self.coordination = LegacyRuntimeCoordination(
            LegacyCoordinationStorage(
                repository=storage.repository, mutate_config=storage.mutate_config,
                load_config=storage.load_config,
                mutate_rows=lambda: self._mutate_plc_runtime_rows,
                mutate_runtime=lambda: self.mutate_plc_runtime_coordination,
                start_heartbeat=storage.start_heartbeat,
            ), coordination_policy,
        )
        # These were direct root bound-method aliases; retain the selected receiver.
        self.mutate_plc_runtime_coordination = self.coordination.mutate_plc_runtime_coordination
        self.plc_completed_capture_receipt = self.coordination.plc_completed_capture_receipt
        self._mutate_plc_runtime_rows = self.coordination._mutate_plc_runtime_rows
        self.capture = PlcCaptureState(
            CaptureStateTransactions(
                load_config=storage.load_config, mutate_app_config_atomically=storage.mutate_config,
                mutate_plc_runtime_coordination=lambda: self.mutate_plc_runtime_coordination,
                plc_completed_capture_receipt=lambda: self.plc_completed_capture_receipt,
            ), CaptureStatePolicy(
                _plc_capture_runtime=lambda: self._plc_capture_runtime,
                _plc_expire_capture_state=lambda: self._plc_expire_capture_state,
                _plc_canonical=capture_policy._plc_canonical,
                PlcConfigError=capture_policy.PlcConfigError,
                PLC_CAPTURE_EVENT_TTL_SECONDS=capture_policy.PLC_CAPTURE_EVENT_TTL_SECONDS,
                PLC_CAPTURE_PROCESSING_TTL_SECONDS=capture_policy.PLC_CAPTURE_PROCESSING_TTL_SECONDS,
                PLC_CAPTURE_RESULTS_KEY=capture_policy.PLC_CAPTURE_RESULTS_KEY,
                PLC_CONTROL_GENERATION_KEY=capture_policy.PLC_CONTROL_GENERATION_KEY,
                PLC_RUNTIME_COORDINATION_KEY=capture_policy.PLC_RUNTIME_COORDINATION_KEY,
                PLC_WORKER_TOTAL_TIMEOUT_SECONDS=capture_policy.PLC_WORKER_TOTAL_TIMEOUT_SECONDS,
            ),
        )




    def plc_claim_or_renew_io_owner(self) -> dict[str, Any] | None:
        return self.coordination.plc_claim_or_renew_io_owner()

    def plc_current_process_owns_io(self, epoch: int | None=None) -> bool:
        return self.coordination.plc_current_process_owns_io(epoch)

    def _plc_capture_runtime(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.capture._plc_capture_runtime(state)

    def _plc_expire_capture_state(self, capture: dict[str, Any], now: float) -> None:
        return self.capture._plc_expire_capture_state(capture, now)

    def plc_claim_capture_session(self, user_id: str, model_id: str) -> dict[str, Any]:
        return self.capture.plc_claim_capture_session(user_id, model_id)

    def plc_heartbeat_capture_session(self, session_id: str, user_id: str) -> dict[str, Any]:
        return self.capture.plc_heartbeat_capture_session(session_id, user_id)

    def plc_release_capture_session(self, session_id: str, user_id: str) -> None:
        return self.capture.plc_release_capture_session(session_id, user_id)

    def plc_capture_disarm(self, reason: str) -> None:
        return self.capture.plc_capture_disarm(reason)

    def plc_apply_capture_observation(self, value: int, *, generation: int, owner_epoch: int, trigger_value: int) -> dict[str, Any] | None:
        return self.capture.plc_apply_capture_observation(value, generation=generation, owner_epoch=owner_epoch, trigger_value=trigger_value)

    def plc_claim_next_capture_event(self, session_id: str, user_id: str) -> dict[str, Any] | None:
        return self.capture.plc_claim_next_capture_event(session_id, user_id)

    def plc_begin_triggered_analysis(self, trigger_id: str, session_id: str, user_id: str, model_id: str, fingerprint: str) -> dict[str, Any] | None:
        return self.capture.plc_begin_triggered_analysis(trigger_id, session_id, user_id, model_id, fingerprint)

    def plc_prepare_triggered_dispatch(self, trigger_id: str, session_id: str, user_id: str) -> None:
        return self.capture.plc_prepare_triggered_dispatch(trigger_id, session_id, user_id)

    def plc_finish_triggered_analysis(self, trigger_id: str, session_id: str, user_id: str, result: dict[str, Any] | None, error: str='') -> None:
        return self.capture.plc_finish_triggered_analysis(trigger_id, session_id, user_id, result, error)
