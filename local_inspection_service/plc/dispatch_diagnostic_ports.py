"""Late-resolved capabilities for PLC dispatch and diagnostic HTTP flows."""
from dataclasses import dataclass
from typing import Any, Callable

Getter = Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class DispatchAccess:
    require_permission: Getter
    require_station: Getter


@dataclass(frozen=True)
class DispatchMutation:
    declare_attempt: Getter
    diagnostic_plan: Getter
    diagnostic_receipt: Getter
    diagnostic_confirm: Getter
    record_receipt: Getter


@dataclass(frozen=True)
class DispatchErrors:
    config_error: Callable[[], type[Exception]]
    http_error: Callable[[], type[Exception]]
