"""Business capabilities for photo-highlight image input and comparison."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
import numpy as np
Record = dict[str, Any]
class PhotoMaskBounds(Protocol):
    def __call__(self, mask: np.ndarray, threshold: int = 8) -> list[int]: ...
@dataclass(frozen=True)
class PhotoHighlightImagePolicy:
    identifier: Callable[[], Callable[[Record], str]]
    max_side: Callable[[], int]
@dataclass(frozen=True)
class PhotoMaskGeometry:
    alpha: Callable[[], PhotoMaskBounds]
    iou: Callable[[], Callable[[list[int], list[int]], float]]
