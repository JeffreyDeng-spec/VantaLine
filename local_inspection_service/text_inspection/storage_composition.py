"""Allocate the two text record stores and their shared per-domain write lock."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import threading

from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from .incoming_store import IncomingPaths, IncomingRows, IncomingTextStore, Record
from .record_store import TextRecordDependencies, TextRecordStore


@dataclass(frozen=True)
class TextStoragePaths:
    records: Callable[[], Path]
    incoming: IncomingPaths


@dataclass(frozen=True)
class TextStorageJSON:
    reader: Callable[[], Callable[[Path], list[Record]]]
    writer: Callable[[], Callable[[Path, list[Record]], None]]


class TextStorage:
    """Construction does no I/O; repository selection stays on the caller thread.

    A composition owns its lock and stores, not a connection or request identity.
    The supplied paths and adapters remain operation-time dependencies.
    """
    def __init__(
        self, *, repository: Callable[[], PostgresRuntimeRepository | None],
        paths: TextStoragePaths, rows: IncomingRows, json_io: TextStorageJSON,
        tables: Callable[[], dict[str, str]],
    ):
        self._lock = threading.RLock()
        self.records = TextRecordStore(TextRecordDependencies(
            runtime_repository=repository,
            guard=lambda: self.lock,
            directory=paths.records,
            tables=tables,
            json_reader=json_io.reader,
            json_writer=json_io.writer,
            row_decoder=rows.decode,
        ))
        self.incoming = IncomingTextStore(
            repository=repository,
            guard=lambda: self.lock,
            paths=paths.incoming,
            rows=rows,
            read_json=lambda path: json_io.reader()(path),
            write_json=lambda path, values: json_io.writer()(path, values),
        )

    @property
    def lock(self):
        """The shared lock identity is fixed for this storage composition."""
        return self._lock
