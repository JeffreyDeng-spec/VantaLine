"""Narrow cutout session and image dependencies; no application imports."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
import numpy as np
@dataclass(frozen=True)
class CutoutRuntimeOperations:
    session: Callable[[], Callable[[], Any | None]]
    lock: Callable[[], AbstractContextManager[Any]]
@dataclass(frozen=True)
class CutoutGreenOperations:
    mask: Callable[[], Callable[[np.ndarray], np.ndarray]]
    spill: Callable[[], Callable[[np.ndarray], np.ndarray]]
