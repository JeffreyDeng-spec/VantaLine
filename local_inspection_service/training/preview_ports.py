"""Typed capabilities used only by the preview renderer; no request or process state."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np

Record = dict[str, Any]
Point = tuple[int, int]
Size = tuple[int, int]
Polygon = list[list[int]]
Rectangle = tuple[tuple[float, float], tuple[float, float], float]
ImageAsset = tuple[np.ndarray, Record]
SpriteAsset = tuple[np.ndarray, np.ndarray, Record]


class ObjectSprite(Protocol):
    def __call__(self, item: Record, rng: np.random.Generator, target_position: str, *,
                 pose_family: str | None, source_position: str | None) -> SpriteAsset | None: ...


class RestoreOrientation(Protocol):
    def __call__(self, image: np.ndarray, mask: np.ndarray, metadata: Record, *,
                 top_view_pose: bool) -> tuple[np.ndarray, np.ndarray, float, float]: ...


class PasteObject(Protocol):
    def __call__(self, canvas: np.ndarray, image: np.ndarray, mask: np.ndarray, center: Point,
                 long_px: int, short_px: int, angle: float, *, preserve_aspect_ratio: bool) -> Record: ...


class TopView(Protocol):
    def __call__(self, family: str, source_size: list[int] | tuple[int, int] | None = None) -> bool: ...


@dataclass(frozen=True)
class PreviewSurface:
    background: Callable[[np.random.Generator, str | None, str | None], ImageAsset]
    public_url: Callable[[Path], str]


@dataclass(frozen=True)
class PreviewAssets:
    document: Callable[[Record, np.random.Generator], ImageAsset | None]
    generic: Callable[[Record], ImageAsset | None]
    sprites: Callable[[Record], list[Record]]
    object_sprite: Callable[[], ObjectSprite]
    restore: Callable[[], RestoreOrientation]
    paste_document: Callable[[np.ndarray, np.ndarray, Point, Size, float], Record]
    paste_object: PasteObject


@dataclass(frozen=True)
class PreviewSizes:
    physical: Callable[[Record, str], Size]
    sprite: Callable[[Record, str, Record], Size]
    pose: Callable[[], Callable[[Record, str | None], Size]]
    visible: Callable[[np.ndarray], list[int]]
    unified: Callable[[], Callable[[int, int, int, int], Size]]


@dataclass(frozen=True)
class PreviewPoses:
    available: Callable[[Record], list[str]]
    choose: Callable[[list[Record], np.random.Generator], str | None]
    policy: Callable[[str | None, np.random.Generator], Record]
    top_view: Callable[[], TopView]
    position: Callable[[Point], str]
    source: Callable[[str, float, str | None, np.random.Generator], str | None]
    reason: Callable[[str, str | None, float], str]


@dataclass(frozen=True)
class PreviewLayout:
    random_center: Callable[[np.random.Generator, Size, float], Point]
    choose_center: Callable[[np.random.Generator, Size, float, list[Record]], tuple[Point, Record]]
    mask: Callable[[], Callable[[tuple[int, int], Polygon], np.ndarray]]
    box: Callable[[Point, Size, float], Polygon]
    rectangle: Callable[[Point, Size, float], Rectangle]
    polygon: Callable[[np.ndarray], Polygon]
    max_distance: Callable[[Polygon | None], float]


@dataclass(frozen=True)
class PreviewThresholds:
    min_visible_area: Callable[[], int]
    max_occlusion: Callable[[], float]
