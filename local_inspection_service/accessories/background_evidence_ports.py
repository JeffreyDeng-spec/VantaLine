"""Narrow capabilities for background plate and reference evidence."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Container, Protocol
import numpy as np
Record = dict[str, Any]
Box = tuple[int, int, int, int]
class ReferenceContexts(Protocol):
    def __call__(self, item: Record, *, max_images: int) -> list[Record]: ...
class HighlightPaths(Protocol):
    def __call__(self, item: Record, *, limit: int) -> list[Path]: ...
@dataclass(frozen=True)
class PlateSources:
    pose_assets: Callable[[], Callable[[Record], list[Record]]]
    contexts: Callable[[], ReferenceContexts]
    resolve: Callable[[], Callable[[Any], Path]]
    suffixes: Callable[[], Container[str]]
@dataclass(frozen=True)
class PlatePolicy:
    time_budget: Callable[[], float]
    max_side: Callable[[], int]
    max_radius: Callable[[], int]
    mask_fraction: Callable[[], float]
@dataclass(frozen=True)
class BackgroundMasks:
    foreground: Callable[[], Callable[[np.ndarray], np.ndarray]]
@dataclass(frozen=True)
class SignatureSources:
    paths: Callable[[], HighlightPaths]
    limit: Callable[[], int]
@dataclass(frozen=True)
class SignaturePolicy:
    max_patches: Callable[[], int]
@dataclass(frozen=True)
class SignatureProjections:
    boxes: Callable[[], Callable[[int, int], list[Box]]]
    signature: Callable[[], Callable[[np.ndarray], Record | None]]
