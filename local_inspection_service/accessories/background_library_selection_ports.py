"""Narrow capabilities for ordered background candidates and signature matching."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Container
import numpy as np
Record = dict[str, Any]
Box = tuple[int, int, int, int]
Candidate = tuple[str, Path, Record]
@dataclass(frozen=True)
class BackgroundOwnership:
    system: Callable[[], str]
    legacy: Callable[[], str]
@dataclass(frozen=True)
class BackgroundCatalogSources:
    manifest: Callable[[], Callable[[], Record]]
    directories: Callable[[], Callable[[], list[Path]]]
    sanitize: Callable[[], Callable[[str | None], str]]
    visible: Callable[[], Callable[[Record, str], bool]]
    images: Callable[[], Callable[[Path], list[Path]]]
    resolve: Callable[[], Callable[[Any], Path]]
@dataclass(frozen=True)
class BackgroundCatalogPolicy:
    directory: Callable[[], Path]
    suffixes: Callable[[], Container[str]]
    limit: Callable[[], int]
@dataclass(frozen=True)
class BackgroundMatchSources:
    references: Callable[[], Callable[[Record], list[Record]]]
    candidates: Callable[[], Callable[[str], list[Candidate]]]
@dataclass(frozen=True)
class BackgroundMatchFeatures:
    boxes: Callable[[], Callable[[int, int], list[Box]]]
    signature: Callable[[], Callable[[np.ndarray], Record | None]]
    distance: Callable[[], Callable[[Record, Record], float]]
