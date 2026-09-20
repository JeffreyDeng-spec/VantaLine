"""Narrow capabilities for materialized accessory assets."""
from collections.abc import Callable, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .sprite_metadata_ports import SpriteTopViewPredicate, SpriteFootprintProjector
Record = dict[str, Any]
@dataclass(frozen=True)
class MaterializedAssetPaths:
    resolve: Callable[[], Callable[[Any], Path]]
@dataclass(frozen=True)
class SpriteCatalogPoseOperations:
    top_view: Callable[[], SpriteTopViewPredicate]
    footprint: Callable[[], SpriteFootprintProjector]
    upright: Callable[[], Callable[[list[Record], Record | None], None]]
    laying: Callable[[], Callable[[list[Record]], None]]
@dataclass(frozen=True)
class SpriteCatalogMaterialPolicy:
    expected: Callable[[], Callable[[Record], str]]
    normalize: Callable[[], Callable[[Any], str | None]]
@dataclass(frozen=True)
class SpriteCatalogReadiness:
    assets: Callable[[], Callable[[Record], list[Record]]]
    metadata: Callable[[], Callable[[Record], bool]]
    material: Callable[[], Callable[[Record, Record], bool]]
@dataclass(frozen=True)
class TextCatalogOperations:
    suffixes: Callable[[], Set[str]]
    assets: Callable[[], Callable[[Record], list[Record]]]
