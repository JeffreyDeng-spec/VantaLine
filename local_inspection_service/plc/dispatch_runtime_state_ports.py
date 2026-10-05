"""State, record and policy capabilities for retained dispatch evidence."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
Record = dict[str, Any]

@dataclass(frozen=True)
class DispatchRuntimeState:
    _plc_dispatch_runtime: Callable[[], dict[str, Record]]
    _PLC_RUNTIME_LIMIT: Callable[[], int]
    _config_io_lock: Callable[[], AbstractContextManager]
    _plc_active_attempts: Callable[[], dict[str, Record]]
    _plc_runtime_entry: Callable[[], Callable[[str], Record]]
    _hydrate_plc_runtime_entry: Callable[[], Callable[[str], Record]]

@dataclass(frozen=True)
class DispatchRuntimeRecords:
    load_config: Callable[[], Callable[[], Record]]
    plc_dispatch_audit_records: Callable[[], Callable[[Record], list[Record]]]
    plc_mark_deadline: Callable[[], Callable[..., Record]]

@dataclass(frozen=True)
class DispatchRuntimePolicy:
    plc_dispatch_is_pristine_queue: Callable[[], Callable[[Record], bool]]
    _plc_canonical: Callable[[], Callable[[Any], str]]
