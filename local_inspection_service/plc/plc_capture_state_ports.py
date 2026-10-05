"""Explicit transaction and policy capabilities for retained capture state."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from ..plc_fx_ascii import PlcConfigError
Record = dict[str, Any]

@dataclass(frozen=True)
class CaptureStateTransactions:
    load_config: Callable[[], Callable[[], Record]]
    mutate_app_config_atomically: Callable[[], Callable[[Callable[[Record], None]], Any]]
    mutate_plc_runtime_coordination: Callable[[], Callable[[Callable[[Record], None]], Any]]
    plc_completed_capture_receipt: Callable[[], Callable[[str], Record | None]]

@dataclass(frozen=True)
class CaptureStatePolicy:
    _plc_capture_runtime: Callable[[], Callable[[Record], Record]]
    _plc_expire_capture_state: Callable[[], Callable[[Record, float], None]]
    _plc_canonical: Callable[[], Callable[[Any], str]]
    PlcConfigError: Callable[[], type[PlcConfigError]]
    PLC_CAPTURE_EVENT_TTL_SECONDS: Callable[[], float]
    PLC_CAPTURE_PROCESSING_TTL_SECONDS: Callable[[], float]
    PLC_CAPTURE_RESULTS_KEY: Callable[[], str]
    PLC_CONTROL_GENERATION_KEY: Callable[[], str]
    PLC_RUNTIME_COORDINATION_KEY: Callable[[], str]
    PLC_WORKER_TOTAL_TIMEOUT_SECONDS: Callable[[], float]
