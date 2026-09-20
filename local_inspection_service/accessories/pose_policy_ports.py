"""Narrow typed dependencies for accessory pose policies."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class PoseLayoutValues:
    grid: Callable[[], Sequence[str]]
    upright: Callable[[], Sequence[str]]

@dataclass(frozen=True)
class PoseRotationOperations:
    normalize: Callable[[], Callable[[float], int]]
    row_col: Callable[[], Callable[[str | None], tuple[int, int] | None]]
    position: Callable[[], Callable[[int, int], str]]

@dataclass(frozen=True)
class PoseRenderOperations:
    is_top: Callable[[], Callable[[str], bool]]
    source: Callable[[], Callable[[str | None, float], str | None]]

@dataclass(frozen=True)
class PoseAssetOperations:
    canonical: Callable[[], Callable[[str | None], str | None]]
    assets: Callable[[], Callable[[dict[str, Any]], list[dict[str, Any]]]]
    footprint: Callable[[], Callable[[str, list[int] | tuple[int, int], dict[str, Any] | None], dict[str, Any]]]

@dataclass(frozen=True)
class PoseCandidateOperations:
    major_axis: Callable[[], Callable[[dict[str, Any]], int | None]]
    family: Callable[[], Callable[[dict[str, Any]], str]]
