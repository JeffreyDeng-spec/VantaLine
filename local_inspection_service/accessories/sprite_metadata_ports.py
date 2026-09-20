"""Draft narrow capabilities for sprite dimension metadata."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .crop_component_ports import CropBounds
Record = dict[str, Any]
SourceSize = list[int] | tuple[int, int] | None
class SpriteTopViewPredicate(Protocol):
    def __call__(self, pose_family: str, source_size_px: SourceSize = None) -> bool: ...
class SpriteFootprintProjector(Protocol):
    def __call__(self, pose_family: str, source_size_px: list[int] | tuple[int, int], physical_size: Record | None) -> Record: ...
@dataclass(frozen=True)
class SpritePhysicalPolicy:
    defaults: Callable[[], dict[str, float]]
    elongated_min: Callable[[], float]
    pixels_per_mm: Callable[[], float]
@dataclass(frozen=True)
class SpriteFootprintMetadataOperations:
    family: Callable[[], Callable[[str | None], str | None]]
    physical: Callable[[], Callable[[Record | None], tuple[float,float,float]]]
    source: Callable[[], Callable[[SourceSize], Record]]
    orient: Callable[[], Callable[[SourceSize,float,float], list[float]]]
    top_view: Callable[[], SpriteTopViewPredicate]
@dataclass(frozen=True)
class SpriteScalePolicy:
    minimum: Callable[[], float]
    maximum: Callable[[], float]
    visual: Callable[[], float]
@dataclass(frozen=True)
class SpriteScaleOperations:
    family: Callable[[], Callable[[str | None], str | None]]
    median: Callable[[], Callable[[list[Record],str], float | None]]
    physical: Callable[[], Callable[[Record | None], tuple[float,float,float]]]
    correction: Callable[[], Callable[[list[Record],Record | None], Record]]
@dataclass(frozen=True)
class SpriteRenderOperations:
    bounds: Callable[[], CropBounds]
    family: Callable[[], Callable[[str | None], str | None]]
    visible: Callable[[], Callable[[Record], tuple[int,int] | None]]
    orient: Callable[[], Callable[[int,int,Any], list[int]]]
    footprint: Callable[[], SpriteFootprintProjector]
    physical: Callable[[], Callable[[Record,str], tuple[int,int]]]
@dataclass(frozen=True)
class SpriteImageReads:
    path: Callable[[], Callable[[str],Path]]
    decode: Callable[[], Callable[[str,int],np.ndarray | None]]
    unchanged_mode: Callable[[], int]
