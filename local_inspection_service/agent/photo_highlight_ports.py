"""Explicit capabilities for photo-highlight source and task workflows."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from .pose_execution_ports import PoseStage, PosePause, PoseImageProvider
Record = dict[str, Any]

class PhotoSourcePaths(Protocol):
    def __call__(self, item: Record, *, limit: int = ...) -> list[Path]: ...
class PhotoMaskBuilder(Protocol):
    def __call__(self, task: Record, item: Record, provider: PoseImageProvider, model: str, *, force: bool = False) -> tuple[bool, str]: ...

@dataclass(frozen=True)
class PhotoSourceMedia:
    resolve: Callable[[], Callable[[Any], Path]]
    suffixes: Callable[[], set[str]]
@dataclass(frozen=True)
class PhotoSpriteLimits:
    minimum: Callable[[], int]
    version: Callable[[], int]
@dataclass(frozen=True)
class PhotoSpriteReadiness:
    assets: Callable[[], Callable[[Record], list[Record]]]
    complete: Callable[[], Callable[[Record, list[Record]], bool]]
@dataclass(frozen=True)
class PhotoObjectSelection:
    normalize: Callable[[], Callable[[str], str]]
    training: Callable[[], Callable[[str], bool]]
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    canonical: Callable[[], Callable[[Record, list[str]], list[str]]]
    material: Callable[[], Callable[[Record], str]]
@dataclass(frozen=True)
class PhotoWorkflowObjects:
    items: Callable[[], Callable[[Record, Record], list[Record]]]
    identifier: Callable[[], Callable[[Record], str]]
    sources: Callable[[], PhotoSourcePaths]
    signature: Callable[[], Callable[[Record], str]]
@dataclass(frozen=True)
class PhotoWorkflowState:
    now: Callable[[], Callable[[], int]]
    tool: Callable[[], str]
    stage: Callable[[], PoseStage]
    pause: Callable[[], PosePause]
    current: Callable[[], Callable[[Record], Record]]
    photo_flow: Callable[[], Callable[[Record, Record], bool]]
    skip_legacy: Callable[[], Callable[[Record, Record, Record], Record]]
    build_plan: Callable[[], Callable[[Record, Record], Record]]
@dataclass(frozen=True)
class PhotoWorkflowModels:
    configuration: Callable[[], Callable[[], Record]]
    settings: Callable[[], Callable[[], Record]]
    provider: Callable[[], Callable[[Record], PoseImageProvider]]
    build_sprites: Callable[[], PhotoMaskBuilder]
