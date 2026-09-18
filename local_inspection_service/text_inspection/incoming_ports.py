"""Narrow capabilities for legacy incoming-text workflows; no request state is cached."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from ..incoming_text_inspection import TextObservation
from .preparation_ports import Permission
from .incoming_store import IncomingPaths
from .standard_ports import Upload

Record = dict[str, Any]


class RequireTask(Protocol):
    def __call__(self, task_id: str, *, write: bool = False) -> Record: ...


class RequireRecord(Protocol):
    def __call__(self, record: Record, user: Record, *, write: bool = False) -> Any: ...


class SaveIncoming(Protocol):
    def __call__(self, record: Record, *, insert_only: bool = False) -> bool: ...


@dataclass(frozen=True)
class IncomingAccess:
    permission: Permission
    user: Callable[[], Record]
    task: Callable[[], RequireTask]
    record: Callable[[], RequireRecord]
    owner: Callable[[Record], str]
    task_allowed: Callable[[Record, Record], bool]


@dataclass(frozen=True)
class IncomingReferences:
    all: Callable[[], list[Record]]
    load: Callable[[str], Record | None]
    save: SaveIncoming


@dataclass(frozen=True)
class IncomingInspections:
    all: Callable[[], list[Record]]
    load: Callable[[str], Record | None]
    save: SaveIncoming
    duplicate: Callable[[str, str, str], Record | None]


@dataclass(frozen=True)
class IncomingTasks:
    all: Callable[[], list[Record]]
    save: Callable[[Record], Any]
    public: Callable[[], Callable[[Record, Record], Record]]
    config: Callable[[], Record]


@dataclass(frozen=True)
class IncomingMedia:
    output: Callable[[], Callable[[str, str], Path]]
    root: Callable[[], Path]
    under: Callable[[Path, Path], bool]
    decode: Callable[[], Callable[[bytes, str], tuple[np.ndarray, str]]]


@dataclass(frozen=True)
class IncomingWrites:
    repository: Callable[[], PostgresRuntimeRepository | None]
    guard: Callable[[], AbstractContextManager[Any]]


@dataclass(frozen=True)
class IncomingJSON:
    paths: IncomingPaths
    read: Callable[[Path], list[Record]]
    write: Callable[[Path, list[Record]], None]


@dataclass(frozen=True)
class IncomingOCR:
    observe: Callable[[np.ndarray], list[TextObservation]]
    corroborate: Callable[[np.ndarray, list[Record]], dict[str, list[TextObservation]]]
    field: Callable[[], Callable[[Record, list[TextObservation], list[TextObservation], np.ndarray, np.ndarray], TextObservation | None]]


@dataclass(frozen=True)
class IncomingImaging:
    quality: Callable[[np.ndarray], Record]
    rectify: Callable[[], Callable[[np.ndarray, tuple[int, int]], tuple[np.ndarray, Record]]]
    similarity: Callable[[], Callable[[np.ndarray, np.ndarray, Record], float | None]]
    annotate: Callable[[], Callable[[np.ndarray, list[Record]], np.ndarray]]
