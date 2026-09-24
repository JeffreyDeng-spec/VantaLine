"""Late-resolved capabilities for workstation management HTTP flows."""
from dataclasses import dataclass
from typing import Any, Callable

Getter = Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class WorkstationAccess:
    require_permission: Getter
    station_from_request: Getter
    require_station: Getter


@dataclass(frozen=True)
class WorkstationProjection:
    station_payload: Getter
    unpaired_payload: Getter
    list_workstations: Getter


@dataclass(frozen=True)
class WorkstationMutation:
    pair: Getter
    update_config: Getter
    set_verified: Getter


@dataclass(frozen=True)
class WorkstationErrors:
    config_error: Callable[[], type[Exception]]
    http_error: Callable[[], type[Exception]]
