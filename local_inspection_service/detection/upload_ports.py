"""Narrow capabilities for ordinary image and video uploads."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol
import numpy as np
from .analysis_ports import AnalysisCall

Record = dict[str, Any]

class ImageArrays(Protocol):
    uint8: Any
    def frombuffer(self, buffer: bytes, dtype: Any) -> np.ndarray: ...

class ImageDecoder(Protocol):
    IMREAD_COLOR: int
    def imdecode(self, buffer: np.ndarray, flags: int) -> np.ndarray | None: ...

class VideoCapture(Protocol):
    def isOpened(self) -> bool: ...
    def get(self, key: int) -> float: ...
    def read(self) -> tuple[bool, np.ndarray | None]: ...
    def release(self) -> None: ...

class VideoBackend(Protocol):
    CAP_PROP_FPS: int
    def VideoCapture(self, path: str) -> VideoCapture: ...

class FileCopy(Protocol):
    def copyfileobj(self, source: BinaryIO, destination: BinaryIO) -> None: ...

@dataclass(frozen=True)
class UploadAccess:
    ensure: Callable[[], None]
    permit: Callable[[str | None], None]

@dataclass(frozen=True)
class UploadPaths:
    name: Callable[[], Callable[[str], str]]
    directory: Callable[[], Path]

@dataclass(frozen=True)
class VideoResults:
    frame: Callable[[Record, int, float], Record]
    summary: Callable[[list[Record]], Record | None]
