"""Narrow dependencies for reusable pose assets and unchanged template policy."""
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Match, Protocol
Record = dict[str, Any]
class TextAssetsComplete(Protocol):
    def __call__(self, item: Record, assets: list[Record] | None = None) -> bool: ...
@dataclass(frozen=True)
class PoseAssetPaths:
    resolve: Callable[[], Callable[[Any], Path]]
    suffixes: Callable[[], Collection[str]]
@dataclass(frozen=True)
class PoseAssetMaterial:
    kind: Callable[[], Callable[[Record], str]]
    text_assets: Callable[[], Callable[[Record], list[Record]]]
    text_complete: Callable[[], TextAssetsComplete]
@dataclass(frozen=True)
class PoseAssetSprites:
    source_paths: Callable[[], Callable[[Record], list[Path]]]
    highlight_ready: Callable[[], Callable[[Record, list[Path]], bool]]
    assets: Callable[[], Callable[[Record], list[Record]]]
    complete: Callable[[], Callable[[Record, list[Record]], bool]]
    family: Callable[[], Callable[[str | None], str | None]]
    version: Callable[[], int]
@dataclass(frozen=True)
class PoseAssetCalls:
    references: Callable[[], Callable[[Record], list[Record]]]
    rebuild: Callable[[], Callable[[Record], bool]]
@dataclass(frozen=True)
class PoseAssetCatalog:
    uid: Callable[[], Callable[[Record], str]]
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    canonical_ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    has_asset: Callable[[], Callable[[Record, Record], bool]]
    pose_tool: Callable[[], str]
@dataclass(frozen=True)
class PoseTemplateIdentity:
    uid: Callable[[], Callable[[Record], str]]
    kind: Callable[[], Callable[[Record], str]]
    search: Callable[[], Callable[[str, str], Match[str] | None]]
@dataclass(frozen=True)
class PoseTemplateCalls:
    request: Callable[[], Callable[[], Record]]
