"""Proposed local capabilities for single sprite publication and canvas normalization."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .crop_component_ports import CropBounds, CropTrimmer
from .sprite_geometry_ports import SpriteMargin
from .sprite_metadata_ports import SpriteFootprintProjector
Record = dict[str, Any]
class SpriteAlphaPolicy(Protocol):
    def __call__(self, asset: np.ndarray, mask: np.ndarray, metadata: Record | None = None) -> tuple[np.ndarray, Record]: ...
class SpriteArtifactPath(Protocol):
    def __call__(self, value: Any, *, for_write: bool = False) -> Path: ...
class SpriteImageResize(Protocol):
    def __call__(self, src: np.ndarray, dsize: tuple[int,int], *, interpolation: int) -> np.ndarray: ...
@dataclass(frozen=True)
class SpriteArtifactGeometry:
    normalize: Callable[[], Callable[[np.ndarray,np.ndarray],tuple[np.ndarray,np.ndarray,Record]]]
    margin: Callable[[], SpriteMargin]
    bounds: Callable[[], CropBounds]
    edge_max: Callable[[], Callable[[np.ndarray],int]]
    edge_stats: Callable[[], Callable[[np.ndarray],Record]]
@dataclass(frozen=True)
class SpriteArtifactMetadata:
    alpha: Callable[[], SpriteAlphaPolicy]
    footprint: Callable[[], SpriteFootprintProjector]
@dataclass(frozen=True)
class SpriteImageEncoder:
    convert: Callable[[], Callable[[np.ndarray,int],np.ndarray]]
    bgra_mode: Callable[[], int]
    write: Callable[[], Callable[[str,np.ndarray],bool]]
@dataclass(frozen=True)
class SpriteCanvasGeometry:
    trim: Callable[[], CropTrimmer]
    margin: Callable[[], SpriteMargin]
    bounds: Callable[[], CropBounds]
    edge_max: Callable[[], Callable[[np.ndarray],int]]
    edge_stats: Callable[[], Callable[[np.ndarray],Record]]
@dataclass(frozen=True)
class SpriteCanvasImageReads:
    resolve: Callable[[], SpriteArtifactPath]
    decode: Callable[[], Callable[[str,int],np.ndarray | None]]
    unchanged_mode: Callable[[], int]
@dataclass(frozen=True)
class SpriteResampling:
    resize: Callable[[], SpriteImageResize]
    cubic: Callable[[], int]
    area: Callable[[], int]
    linear: Callable[[], int]
