"""Typed media codecs, rendering and reference-sheet capabilities."""
from collections.abc import Callable, MutableMapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .presence_payload import BoundedText
from .presence_inspection_ports import EncodeArray, EncodePath

Record = dict[str, Any]

class MediaImages(Protocol):
    INTER_AREA: int
    IMREAD_COLOR: int
    IMREAD_UNCHANGED: int
    IMWRITE_JPEG_QUALITY: int
    COLOR_GRAY2BGR: int
    FONT_HERSHEY_SIMPLEX: int
    LINE_AA: int
    def resize(self, image: np.ndarray, size: tuple[int, int], *, interpolation: int) -> np.ndarray: ...
    def imread(self, path: str, flags: int) -> np.ndarray | None: ...
    def imwrite(self, path: str, image: np.ndarray, params: list[int]) -> bool: ...
    def imencode(self, extension: str, image: np.ndarray, params: list[int]) -> tuple[bool, np.ndarray]: ...
    def cvtColor(self, image: np.ndarray, code: int) -> np.ndarray: ...
    def rectangle(self, image: np.ndarray, start: tuple[int, int], end: tuple[int, int], color: tuple[int, int, int], thickness: int) -> np.ndarray: ...
    def putText(self, image: np.ndarray, text: str, origin: tuple[int, int], font: int, scale: float, color: tuple[int, int, int], thickness: int, line_type: int) -> np.ndarray: ...

class MediaArrays(Protocol):
    uint8: Any
    float32: Any
    def full(self, shape: tuple[int, ...], value: float, dtype: Any) -> np.ndarray: ...
    def full_like(self, image: np.ndarray, value: float) -> np.ndarray: ...

@dataclass(frozen=True)
class InspectionImagePolicy:
    directory: Callable[[], Path]
    max_side: Callable[[], int]
    quality: Callable[[], int]

@dataclass(frozen=True)
class ReferenceCollectionPolicy:
    limit: Callable[[], int]
    max_side: Callable[[], int]
    quality: Callable[[], int]

@dataclass(frozen=True)
class ReferenceSheetPolicy:
    suffixes: Callable[[], set[str]]
    mode: Callable[[], str]
    quality: Callable[[], int]
    max_side: Callable[[], int]

@dataclass(frozen=True)
class ReferenceSheetCache:
    lock: Callable[[], AbstractContextManager[Any]]
    records: Callable[[], MutableMapping[str, Record]]

@dataclass(frozen=True)
class ReferenceSheetImages:
    images: Callable[[], MediaImages]
    arrays: Callable[[], MediaArrays]
    fit: Callable[[np.ndarray | None, int, int], np.ndarray]
    encode: Callable[[], EncodePath]
