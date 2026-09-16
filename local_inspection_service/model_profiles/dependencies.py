"""Narrow model-profile ports; providers return services, never live connections."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

Record = dict[str, Any]


class ModelResolver(Protocol):
    def current_snapshot(self) -> Record | None: ...
    def snapshot_for_record(self, record: Record) -> Record: ...
    def scope(self, snapshot: Record | None = None) -> AbstractContextManager: ...
    def record_call(self, settings: Record, elapsed_ms: int, ok: bool, usage: Record) -> None: ...


ResolverProvider = Callable[[], ModelResolver]
RecordLoader = Callable[[Any], Record | None]


def require_resolver(provider: ResolverProvider) -> ModelResolver:
    service = provider()
    if service is None:
        raise RuntimeError("Model profile resolver is not configured")
    return service


@dataclass(frozen=True)
class ProfileDependencies:
    runtime_repository: Callable[[], PostgresRuntimeRepository | None]
    write_secret: Callable[[str, str], Any]
    read_secret: Callable[[str], str]
    legacy_sources: Callable[[], list[tuple[str, Record, list[str]]]]
    validate_model: Callable[[str], Any]
    validate_base_url: Callable[[str], Any]
    mask_secret: Callable[[str], str]


@dataclass(frozen=True)
class ProfileApiDependencies:
    require_admin: Callable[[], Record]
    cost_from_usage: Callable[[str, Record], tuple[float, int, bool]]
    cursor_api_url: Callable[[str, str], str]
    cursor_auth_headers: Callable[[str], dict[str, str]]
    model_options_from_items: Callable[..., list[Record]]
