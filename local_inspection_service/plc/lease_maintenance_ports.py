"""Narrow late-bound capabilities for PLC lease maintenance transitions."""
from dataclasses import dataclass
from typing import Any, Callable

Getter = Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class LeaseMaintenancePorts:
    mutate: Getter
    record: Getter
    lease_row: Getter
    current_user: Getter
    clock: Getter
    active_ttl: Callable[[], int]
    config_error: Callable[[], type[Exception]]
