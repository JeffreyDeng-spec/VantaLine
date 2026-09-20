"""Narrow numeric defaults and item-update capabilities for accessory dimensions."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
Record = dict[str, Any]
class BuildPhysicalSize(Protocol):
    def __call__(self, material_type: str, paper_preset: str = 'A4', paper_width_mm: Any = None, paper_height_mm: Any = None, object_length_mm: Any = None, object_width_mm: Any = None, object_height_mm: Any = None) -> Record: ...
@dataclass(frozen=True)
class DimensionValues:
    number: Callable[[], Callable[[Any], float | None]]
    papers: Callable[[], Mapping[str, tuple[float, float]]]
    objects: Callable[[], Mapping[str, float]]
@dataclass(frozen=True)
class DimensionUpdates:
    material: Callable[[], Callable[[Record], str]]
    payload: Callable[[], BuildPhysicalSize]
