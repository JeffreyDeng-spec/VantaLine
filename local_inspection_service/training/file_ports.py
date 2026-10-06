"""File capabilities used by training inputs, generation and preview metadata."""
from pathlib import Path
from typing import Any, Protocol


class TrainingInputFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def read_text(self, path: Path, *, encoding: str) -> str: ...


class TrainingTextWriter(Protocol):
    def write_text(self, path: Path, text: str, *, encoding: str) -> int: ...


class TrainingFileStat(Protocol):
    @property
    def st_mtime_ns(self) -> int: ...
    @property
    def st_size(self) -> int: ...


class TrainingStatFiles(Protocol):
    def stat(self, path: Path) -> TrainingFileStat: ...


class TrainingImageWriter(Protocol):
    def imwrite(self, filename: str, image: Any, params: list[int] = ...) -> bool: ...


class TrainingImageIO(TrainingImageWriter, Protocol):
    def imread(self, filename: str, flags: int) -> Any: ...
