"""Capabilities for standard import, retrieval and human revision workflows."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from .preparation_ports import Permission, ApplyRevision

Record = dict[str, Any]


class Upload(Protocol):
    filename: str | None
    async def read(self, size: int = -1) -> bytes: ...


class SaveRecord(Protocol):
    def __call__(self, kind: str, value: Record, *, insert_only: bool = False) -> bool: ...


@dataclass(frozen=True)
class StandardAccess:
    require_permission: Permission
    owner: Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class StandardRecords:
    load: Callable[[str], list[Record]]
    save: SaveRecord
    owned: Callable[[str, str, str], Record | None]
    public: Callable[[Record], Record]


@dataclass(frozen=True)
class StandardWrites:
    repository: Callable[[], PostgresRuntimeRepository | None]
    guard: Callable[[], AbstractContextManager[Any]]


@dataclass(frozen=True)
class StandardMedia:
    path: Callable[[str, str, str], Path]
    write: Callable[[Path, bytes], None]
    digest: Callable[[bytes], str]


@dataclass(frozen=True)
class StandardRevisions:
    expected: Callable[[Any], int | None]
    snapshot: Callable[[list[Record]], list[Record]]
    apply: ApplyRevision


@dataclass(frozen=True)
class StandardParsers:
    doc: Callable[[bytes], tuple[list[Record], list[bytes]]]
    docx: Callable[[bytes], tuple[list[Record], list[bytes]]]
    pdf: Callable[[bytes], Record]


@dataclass(frozen=True)
class StandardClassification:
    start: Callable[[str, str], Any]
    mark_unavailable: Callable[[str, str, str], Any]


@dataclass(frozen=True)
class StandardPreparation:
    start: Callable[[str, str], Any]
    enabled: Callable[[str], bool]
