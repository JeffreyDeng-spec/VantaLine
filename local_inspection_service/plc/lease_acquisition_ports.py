"""Late-bound capabilities for workstation lease claim and activation."""
from dataclasses import dataclass
from typing import Any, Callable

Getter = Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class LeaseAcquisitionPorts:
    current_user: Getter
    release_version: Getter
    fullmatch: Getter
    protocol_version: Callable[[], str]
    require_model_permission: Getter
    mutate: Getter
    record: Getter
    migrate_config: Getter
    clock: Getter
    uuid4: Getter
    connecting_ttl: Callable[[], int]
    active_ttl: Callable[[], int]
    lease_row: Getter
    config_error: Callable[[], type[Exception]]
