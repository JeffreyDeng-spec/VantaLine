"""Narrow capabilities for preview sprite selection and orientation."""
from collections.abc import Callable, Container
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .sprite_metadata_ports import SpriteTopViewPredicate
Record = dict[str, Any]
class PreviewSpritePreprocessor(Protocol):
    def __call__(self, item: Record, allow_ai_cutout: bool = True, force: bool = False) -> bool: ...
@dataclass(frozen=True)
class PreviewSpriteInventory:
    assets: Callable[[], Callable[[Record], list[Record]]]
    preprocess: Callable[[], PreviewSpritePreprocessor]
    version: Callable[[], Callable[[Record], str]]
@dataclass(frozen=True)
class PreviewSpritePoses:
    canonical: Callable[[], Callable[[str | None], str | None]]
    family: Callable[[], Callable[[Record], str]]
    top_view: Callable[[], SpriteTopViewPredicate]
    complete: Callable[[], Callable[[list[Record], str | None], list[Record]]]
    upright_positions: Callable[[], Container[str]]
@dataclass(frozen=True)
class PreviewSpriteMedia:
    resolve: Callable[[], Callable[[Any], Path]]
    decode: Callable[[], Callable[[Path], tuple[np.ndarray, np.ndarray] | None]]
@dataclass(frozen=True)
class PreviewSpriteGeometry:
    rotate: Callable[[], Callable[[np.ndarray, np.ndarray, float], tuple[np.ndarray, np.ndarray]]]
