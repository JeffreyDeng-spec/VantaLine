"""Narrow material-alpha dispatch dependencies; no application imports."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
import numpy as np
Record = dict[str, Any]
class MaterialAlphaPolicyResolver(Protocol):
    def __call__(self, item: Record | None = None, metadata: Record | None = None) -> str: ...
@dataclass(frozen=True)
class MaterialAlphaOperations:
    policy: Callable[[], MaterialAlphaPolicyResolver]
    transparent: Callable[[], Callable[[np.ndarray,np.ndarray],tuple[np.ndarray,Record]]]
    solid: Callable[[], Callable[[np.ndarray],tuple[np.ndarray,Record]]]
