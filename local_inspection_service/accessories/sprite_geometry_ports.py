"""Narrow operations for masked sprite geometry."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
import numpy as np
from .crop_component_ports import CropBounds, CropTrimmer
class SpriteMargin(Protocol):
    def __call__(self, asset: np.ndarray, mask: np.ndarray, margin: int = 10) -> tuple[np.ndarray,np.ndarray]: ...
@dataclass(frozen=True)
class SpriteTransformOperations:
    normalize: Callable[[], Callable[[float],float]]
    axis: Callable[[], Callable[[np.ndarray],tuple[float,float]]]
    rotate: Callable[[], Callable[[np.ndarray,np.ndarray,float],tuple[np.ndarray,np.ndarray]]]
    trim: Callable[[], CropTrimmer]
    margin: Callable[[], SpriteMargin]
@dataclass(frozen=True)
class SpriteFootprintOperations:
    bounds: Callable[[], CropBounds]
    visible: Callable[[], Callable[[np.ndarray],list[int]]]
