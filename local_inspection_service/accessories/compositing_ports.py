"""Narrow capabilities for asset canvas composition."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
import numpy as np
from .crop_component_ports import CropTrimmer
Record = dict[str, Any]
class MaskedAssetPaste(Protocol):
    def __call__(self, canvas: np.ndarray, asset: np.ndarray, mask: np.ndarray, center: tuple[int, int], target_size: tuple[int, int], angle: float, trim_before_paste: bool = True, return_visible_mask: bool = False, resize_to_target: bool = True) -> np.ndarray | tuple[np.ndarray, np.ndarray]: ...
@dataclass(frozen=True)
class CompositionGeometry:
    trim: Callable[[], CropTrimmer]
    resize_footprint: Callable[[], Callable[[np.ndarray, np.ndarray, tuple[int, int], bool], tuple[np.ndarray, np.ndarray, Record]]]
    visible_size: Callable[[], Callable[[np.ndarray], list[int]]]
@dataclass(frozen=True)
class CompositionOperations:
    paste_masked: Callable[[], MaskedAssetPaste]
    trim_rect: Callable[[], Callable[[np.ndarray], np.ndarray]]
    physical_mask: Callable[[], Callable[[np.ndarray], np.ndarray]]
