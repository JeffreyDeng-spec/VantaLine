"""Per-submission capabilities; never a connection or current-user container."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]
UsageRecorder = Callable[[Record, int, bool, Record], None]
EnvironmentReader = Callable[[str, str], str]


class SaveRecord(Protocol):
    def __call__(self, kind: str, record: Record, *, insert_only: bool = False) -> bool: ...


@dataclass(frozen=True)
class ComparisonRecords:
    load: Callable[[str], list[Record]]
    save: SaveRecord
    owned: Callable[[str, str, str], Record | None]
    update_attempt: Callable[[str, Record], bool]
    public: Callable[[Record], Record]


@dataclass(frozen=True)
class ComparisonMedia:
    path: Callable[[str, str, str], Path]
    write: Callable[[Path, bytes], None]
    digest: Callable[[bytes], str]


@dataclass(frozen=True)
class ComparisonModels:
    settings: Callable[[str], Record]
    external_enabled: bool
    record_usage: UsageRecorder | None
