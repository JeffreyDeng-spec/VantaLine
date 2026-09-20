"""Narrow geometry capabilities for crop component selection."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
import numpy as np
class CropBounds(Protocol):
    def __call__(self, mask: np.ndarray, threshold: int = 8) -> list[int]: ...
class CropTrimmer(Protocol):
    def __call__(self, asset: np.ndarray, mask: np.ndarray, pad: int = 4) -> tuple[np.ndarray, np.ndarray]: ...
@dataclass(frozen=True)
class CropGeometry:
    bounds: Callable[[], CropBounds]
    trim: Callable[[], CropTrimmer]
