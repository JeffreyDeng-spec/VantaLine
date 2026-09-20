"""Narrow typed dependencies for accessory cutout geometry."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
import numpy as np

Crop = tuple[np.ndarray, np.ndarray]
BoundedCrop = tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]

@dataclass(frozen=True)
class SelectionOperations:
    foreground: Callable[[], Callable[[np.ndarray], np.ndarray]]
    object_fallback: Callable[[], Callable[[np.ndarray, np.random.Generator], Crop | None]]
    bounded_ai: Callable[[], Callable[[np.ndarray], BoundedCrop | None]]
    bounded_green: Callable[[], Callable[[np.ndarray, np.random.Generator], BoundedCrop | None]]

@dataclass(frozen=True)
class ChromaPolicyOperations:
    normalize: Callable[[], Callable[[Any], dict[str, Any]]]
    saturated: Callable[[], Callable[[np.ndarray, dict[str, Any]], np.ndarray]]
    green_spill: Callable[[], Callable[[np.ndarray], np.ndarray]]

@dataclass(frozen=True)
class ChromaMatteOperations:
    background: Callable[[], Callable[[np.ndarray, dict[str, Any] | None], np.ndarray]]
    distance: Callable[[], Callable[[np.ndarray, dict[str, Any] | None], np.ndarray]]
    spill: Callable[[], Callable[[np.ndarray, dict[str, Any] | None], np.ndarray]]
