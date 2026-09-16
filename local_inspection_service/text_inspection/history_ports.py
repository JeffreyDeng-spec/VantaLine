"""Capabilities for read-only historical comparison routes."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

Record = dict[str, Any]


class HistoryPermission(Protocol):
    def __call__(self, permission: str, *, detail: str) -> Any: ...


class ReadEvidence(Protocol):
    def __call__(self, path_value: str, owner_user_id: str, standard_id: str, *,
                 expected_sha256: str = "", max_bytes: int = 120 * 1024 * 1024) -> bytes: ...


@dataclass(frozen=True)
class HistoryAccess:
    require_permission: HistoryPermission
    owner: Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class HistoryRecords:
    repository: Callable[[], PostgresRuntimeRepository | None]
    load: Callable[[str], list[Record]]
    owned: Callable[[str, str, str], Record | None]
    public: Callable[[Record], Record]


@dataclass(frozen=True)
class HistoryMedia:
    path: Callable[[str, str, str], Path]
    read_verified: ReadEvidence
