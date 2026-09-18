"""Capabilities for preparation jobs, revision publication and history HTTP routes."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

Record = dict[str, Any]


class Permission(Protocol):
    def __call__(self, permission: str, *, detail: str) -> Any: ...


class ApplyRevision(Protocol):
    def __call__(self, standard: Record, assets: list[Record], *,
                 action: str, asset_id: str, now: int) -> Record: ...


class ReadVerified(Protocol):
    def __call__(self, path_value: str, owner: str, standard: str, *,
                 expected_sha256: str = '', max_bytes: int = 120*1024*1024) -> bytes: ...


@dataclass(frozen=True)
class PreparationAccess:
    require_permission: Permission
    owner: Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class PreparationRecords:
    repository: Callable[[], PostgresRuntimeRepository | None]
    guard: Callable[[], AbstractContextManager[Any]]
    owned: Callable[[str, str, str], Record | None]
    load: Callable[[str], list[Record]]
    save: Callable[[str, Record], bool]
    apply_revision: ApplyRevision


@dataclass(frozen=True)
class PreparationMedia:
    path: Callable[[str, str, str], Path]
    write: Callable[[Path, bytes], None]
    digest: Callable[[bytes], str]
    asset_bytes: Callable[[Record, str], bytes]
    data_url: Callable[[bytes, str], str]
    read_verified: ReadVerified


@dataclass(frozen=True)
class PreparationModels:
    settings: Callable[[str], Record]
    external_enabled: Callable[[], bool]
    call_tool: Callable[[str, Record], Record]
    diagnostics: Callable[[Record, Record], Record]


@dataclass(frozen=True)
class PreparationHistory:
    record_table: Callable[[], str]
    raw_rows: Callable[[list[Record]], list[Record]]
    public: Callable[[Record], Record]
    attempt_writer: Callable[[], Callable[[str, Record], bool]]
