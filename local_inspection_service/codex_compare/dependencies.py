"""Narrow account, standard-library and media capabilities for Codex HTTP APIs."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from ..storage.codex_comparisons import CodexComparisonsRepository
from .media import MediaStore

Record = dict[str, Any]
Result = TypeVar("Result")
RepositoryFactory = Callable[[], PostgresRuntimeRepository | None]
Context = Callable[[], tuple[str, CodexComparisonsRepository, MediaStore]]
OwnedTask = Callable[[CodexComparisonsRepository, str, str], Record]


class MapErrors(Protocol):
    def __call__(self, operation: Callable[[], Result]) -> Result: ...


class SaveStandard(Protocol):
    def __call__(self, kind: str, value: Record, *, insert_only: bool = False) -> bool: ...


@dataclass(frozen=True)
class ComparisonAccess:
    require_permission: Callable[[str], Any]
    owner: Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class StandardLibrary:
    owned: Callable[[str, str, str], Record | None]
    load: Callable[[str], list[Record]]
    save: SaveStandard


@dataclass(frozen=True)
class ComparisonMedia:
    data_directory: Callable[[], Path]
    asset_bytes: Callable[[Record, str], bytes]
    media_path: Callable[[str, str, str], Path]
    write: Callable[[Path, bytes], None]


@dataclass(frozen=True)
class DocumentImports:
    # Codex intentionally uses the default extraction mode, unlike the label API.
    docx: Callable[[bytes], tuple[list[Record], list[bytes]]]
    doc: Callable[[bytes], tuple[list[Record], list[bytes]]]
