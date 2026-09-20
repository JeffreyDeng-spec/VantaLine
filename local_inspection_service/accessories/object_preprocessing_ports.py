"""Domain-local capabilities for object sprite preprocessing."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .crop_component_ports import CropBounds
Record = dict[str, Any]
Cutout = tuple[np.ndarray, np.ndarray]
BoundedCutout = tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]
class PoseRegions(Protocol):
    def __call__(self, image: np.ndarray, padded: bool = True) -> list[tuple[int, int, int, int]]: ...
class ComponentCleanup(Protocol):
    def __call__(self, asset: np.ndarray, alpha: np.ndarray, anchor_xy: tuple[float, float] | None = None, min_area: int = 35) -> tuple[np.ndarray, Record]: ...
class ComponentSummary(Protocol):
    def __call__(self, alpha: np.ndarray, threshold: int = 28) -> tuple[int, int]: ...
class SpriteWriter(Protocol):
    def __call__(self, path: Path, asset: np.ndarray, mask: np.ndarray, metadata: Record | None = None) -> Record | None: ...
@dataclass(frozen=True)
class ObjectSpritePolicy:
    material: Callable[[], Callable[[Record], str]]
    alpha: Callable[[], Callable[[Record], str]]
    existing: Callable[[], Callable[[Record], list[Record]]]
    complete: Callable[[], Callable[[Record, list[Record]], bool]]
@dataclass(frozen=True)
class ObjectSpriteSources:
    jobs: Callable[[], Callable[[Record], list[Record]]]
    images: Callable[[], Callable[[Record], list[Path]]]
    positions: Callable[[], list[str]]
    regions: Callable[[], PoseRegions]
@dataclass(frozen=True)
class ObjectSpriteRuntime:
    identifier: Callable[[], Callable[[Record], str]]
    root: Callable[[], Path]
    now: Callable[[], Callable[[], float]]
    rng: Callable[[], Callable[[int], np.random.Generator]]
@dataclass(frozen=True)
class ObjectSpriteCutouts:
    ai_bounded: Callable[[], Callable[[np.ndarray], BoundedCutout | None]]
    green: Callable[[], Callable[[np.ndarray, np.random.Generator], BoundedCutout | None]]
    ai_plain: Callable[[], Callable[[np.ndarray], Cutout | None]]
    lightweight: Callable[[], Callable[[np.ndarray, np.random.Generator], Cutout | None]]
    usable: Callable[[], Callable[[Cutout | None, tuple[int, ...]], Cutout | None]]
@dataclass(frozen=True)
class ObjectSpriteComponents:
    cutouts: Callable[[], Callable[[np.ndarray], list[Cutout]]]
    focus: Callable[[], Callable[[np.ndarray, np.ndarray, tuple[int,int,int,int]], BoundedCutout | None]]
    cleanup: Callable[[], ComponentCleanup]
    summary: Callable[[], ComponentSummary]
    bounds: Callable[[], CropBounds]
@dataclass(frozen=True)
class ObjectSpriteMetadata:
    footprint: Callable[[], Callable[[str, list[int] | tuple[int,int], Record | None], Record]]
    normalize: Callable[[], Callable[[list[Record]], None]]
    scale: Callable[[], Callable[[list[Record], Record | None], None]]
    laying: Callable[[], Callable[[list[Record]], None]]
    top_view: Callable[[], Callable[[str, list[int] | tuple[int,int] | None], bool]]
    task_id: Callable[[], Callable[[Record, Record], str]]
@dataclass(frozen=True)
class ObjectSpriteArtifacts:
    write: Callable[[], SpriteWriter]
