"""Capabilities needed by the PLC connection-lease HTTP boundary."""
from dataclasses import dataclass
from typing import Any, Callable

Getter = Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class LeaseAccess:
    require_station: Getter
    require_model_permission: Getter


@dataclass(frozen=True)
class LeaseMutation:
    claim: Getter
    activate: Getter
    heartbeat: Getter
    rebind_model: Getter
    disconnect: Getter


@dataclass(frozen=True)
class LeaseErrors:
    config_error: Callable[[], type[Exception]]
    http_error: Callable[[], type[Exception]]
