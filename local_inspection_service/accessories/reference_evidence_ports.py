"""Narrow capabilities for accessory reference evidence."""
from collections.abc import Callable, Container, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
Record = dict[str, Any]
class ReferenceList(Protocol):
    def __call__(self, item: Record, *, max_images: int) -> list[Record]: ...
@dataclass(frozen=True)
class ReferencePolicy:
    suffixes: Callable[[], Container[str]]
    screens: Callable[[], Mapping[str, Record]]
@dataclass(frozen=True)
class ReferencePaths:
    resolve: Callable[[], Callable[[Any], Path]]
    jobs: Callable[[], Callable[[Record], list[Record]]]
    default: Callable[[], Callable[[Record], Path | None]]
    preferred: Callable[[], Callable[[Record], list[Path]]]
    first_source: Callable[[], Callable[[Record], Path | None]]
    inventory: Callable[[], Callable[[Record], list[Path]]]
@dataclass(frozen=True)
class ReferenceContexts:
    uid: Callable[[], Callable[[Record], str]]
    bounded: Callable[[], Callable[[Any, int], str]]
    context: Callable[[], Callable[[Path, str, int], Record | None]]
    references: Callable[[], ReferenceList]
@dataclass(frozen=True)
class ReferenceChroma:
    normalize: Callable[[], Callable[[Any], Record]]
    mask: Callable[[], Callable[[np.ndarray, Record], np.ndarray]]
