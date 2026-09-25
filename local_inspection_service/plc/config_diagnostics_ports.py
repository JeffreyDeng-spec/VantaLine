"""Explicit capabilities for legacy PLC configuration diagnostics."""
from dataclasses import dataclass
from typing import Any, Callable

Getter = Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class ConfigSources:
    load: Getter
    raw_namespace: Getter
    normalize: Getter
    defaults: Callable[[], dict[str, Any]]
    activation_errors: Getter
    dispatch_audit: Getter


@dataclass(frozen=True)
class ConfigDisplay:
    logical_address: Getter
    device_verified: Getter
    read_verified: Getter


@dataclass(frozen=True)
class ConfigRuntime:
    active_attempts: Getter
    audit_limit: Callable[[], int]
    protocol_id: Callable[[], str]
    generation_key: Callable[[], str]
    queue_wait_seconds: Callable[[], float]
    worker_total_timeout_seconds: Callable[[], float]


@dataclass(frozen=True)
class ConfigAccess:
    require_permission: Getter


@dataclass(frozen=True)
class ConfigErrors:
    config_error: Callable[[], type[Exception]]
    http_error: Callable[[], type[Exception]]
