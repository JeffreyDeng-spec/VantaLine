"""Narrow capabilities for preview and rectified-document asset loading."""
from collections.abc import Callable, Container
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
Record = dict[str, Any]
LoadedAsset = tuple[np.ndarray, Record]
class DocumentCandidateSelector(Protocol):
    def __call__(self, candidates: list[LoadedAsset], rng: np.random.Generator | None, *, multi_policy: str, single_policy: str) -> LoadedAsset | None: ...
@dataclass(frozen=True)
class PreviewAssetPolicy:
    root: Callable[[], Path]
    suffixes: Callable[[], Container[str]]
@dataclass(frozen=True)
class PreviewAssetPaths:
    resolve: Callable[[], Callable[[Any], Path]]
@dataclass(frozen=True)
class PreviewAssetOperations:
    default: Callable[[], Callable[[Record], Path | None]]
    candidate: Callable[[], Callable[[Any, Record], LoadedAsset | None]]
    select: Callable[[], DocumentCandidateSelector]
    preview: Callable[[], Callable[[Record], LoadedAsset | None]]
