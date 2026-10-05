"""Narrow, late-resolved collaborators for pose collection prompt text."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
Record = dict[str, Any]
Batch = tuple[str, str, list[str]]

class CameraText(Protocol):
    def __call__(self, item: Record, surface_mode: str = "white") -> str: ...

class CameraBatchText(Protocol):
    def __call__(self, item: Record, batch_key: str | None, surface_mode: str = "white") -> str: ...

@dataclass(frozen=True)
class PoseCollectionPromptDependencies:
    tabletop_scene_text: Callable[[], Callable[[str], str]]
    pose_collection_camera_grid_text: Callable[[], CameraText]
    pose_collection_position_specs: Callable[[], Callable[[Record], dict[str, str]]]
    POSE_COLLECTION_BATCHES: Callable[[], list[Batch]]
    pose_collection_dimension_text: Callable[[], Callable[[Record], str]]
    pose_collection_camera_batch_text: Callable[[], CameraBatchText]
    upright_spatial_relation_text: Callable[[], Callable[[], str]]
