"""Narrow capabilities for document classification jobs and their HTTP entry points."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

Record = dict[str, Any]


class Permission(Protocol):
    def __call__(self, permission: str, *, detail: str) -> Any: ...


class ModelTransport(Protocol):
    def __call__(self, request: Request, settings: Record, *, timeout: int) -> Any: ...


@dataclass(frozen=True)
class DocumentAccess:
    require_permission: Permission
    owner: Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class DocumentRecords:
    repository: Callable[[], PostgresRuntimeRepository | None]
    guard: Callable[[], AbstractContextManager[Any]]
    owned: Callable[[str, str, str], Record | None]
    load: Callable[[str], list[Record]]
    save: Callable[[str, Record], bool]
    public: Callable[[Record], Record]


@dataclass(frozen=True)
class DocumentModels:
    external_enabled: Callable[[], bool]
    settings: Callable[[str], Record]
    transport: ModelTransport
    record_usage: Callable[[Record, int, bool, Record], None]
