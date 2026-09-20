"""Draft narrow pose materialization capabilities."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
Record = dict[str, Any]
Cutout = tuple[np.ndarray, np.ndarray]
BoundedCutout = tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]

class SpriteBuilder(Protocol):
    def __call__(self, item: Record, *, force: bool = False) -> bool: ...

@dataclass(frozen=True)
class PoseChromaSources:
    fraction: Callable[[], Callable[[Record, str], float]]
    screen: Callable[[], Callable[[Any], Record]]
    threshold: Callable[[], float]

@dataclass(frozen=True)
class PoseCutoutSources:
    chroma: Callable[[], Callable[[np.ndarray, Record | None], BoundedCutout | None]]
    precise: Callable[[], Callable[[np.ndarray], BoundedCutout | None]]
    green: Callable[[], Callable[[np.ndarray], BoundedCutout | None]]
    background: Callable[[], Callable[[np.ndarray], BoundedCutout | None]]
    generic: Callable[[], Callable[[np.ndarray, np.random.Generator], Cutout | None]]
    final_green: Callable[[], Callable[[np.ndarray, np.random.Generator], BoundedCutout | None]]
    usable: Callable[[], Callable[[Cutout | None, tuple[int, ...]], Cutout | None]]

@dataclass(frozen=True)
class PoseSpritePolicy:
    material: Callable[[], Callable[[Record], str]]
    deduplicate: Callable[[], Callable[[Record], bool]]
    references: Callable[[], Callable[[Record], list[Record]]]
    existing: Callable[[], Callable[[Record], list[Record]]]
    complete: Callable[[], Callable[[Record, list[Record]], bool]]
    alpha: Callable[[], Callable[[Record], str]]

@dataclass(frozen=True)
class PoseSpriteRuntime:
    root: Callable[[], Path]
    identifier: Callable[[], Callable[[Record], str]]
    rng: Callable[[], Callable[[int], np.random.Generator]]
    now: Callable[[], Callable[[], float]]
    version: Callable[[], int]
    safe_id: Callable[[], Callable[[Any], str]]

@dataclass(frozen=True)
class PoseSpriteImages:
    read: Callable[[], Callable[[str, int], np.ndarray | None]]
    read_mode: Callable[[], int]
    segment: Callable[[], Callable[[np.ndarray, np.random.Generator, Record | None], BoundedCutout | None]]
    write: Callable[[], Callable[[Path, np.ndarray, np.ndarray, Record], Record | None]]

@dataclass(frozen=True)
class PoseSpriteMetadata:
    footprint: Callable[[], Callable[[str, list[int] | tuple[int, int], Record | None], Record]]
    normalize: Callable[[], Callable[[list[Record]], None]]
    scale: Callable[[], Callable[[list[Record], Record | None], None]]
    laying: Callable[[], Callable[[list[Record]], None]]

@dataclass(frozen=True)
class PoseMaterializationState:
    current: Callable[[], Callable[[Record], Record]]
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    now: Callable[[], Callable[[], int]]
    tool: Callable[[], str]

@dataclass(frozen=True)
class PoseAssetMedia:
    resolve: Callable[[], Callable[[Any], Path]]
    public_url: Callable[[], Callable[[Path], str]]
    digest: Callable[[], Callable[[Path], str | None]]
    suffixes: Callable[[], set[str]]

@dataclass(frozen=True)
class PoseMaterializationSprites:
    sources: Callable[[], Callable[[Record], list[Path]]]
    ready: Callable[[], Callable[[Record, list[Path]], bool]]
    build: Callable[[], SpriteBuilder]
