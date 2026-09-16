"""Narrow capabilities for preparing accessory sources and candidate records."""
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from .creation_ports import EnsureProfile

Record = dict[str, Any]


class GenerateProfile(Protocol):
    def __call__(self, item: Record, *, allow_provider: bool = True) -> Record: ...


@dataclass(frozen=True)
class PreparationPaths:
    normalized: Callable[[], Path]
    uploads: Callable[[], Path]
    image_suffixes: Callable[[], Collection[str]]
    video_suffixes: Callable[[], Collection[str]]


@dataclass(frozen=True)
class TextPreparation:
    is_rectified: Callable[[Path], bool]
    has_rectified: Callable[[Path, Sequence[Path]], bool]
    normalize: Callable[[Path, Path, Record], Record | None]
    max_images: Callable[[], int]


@dataclass(frozen=True)
class ReferenceMedia:
    extract_frames: Callable[[Path, Path], list[Record]]
    profile_paths: Callable[[Record], list[Path]]
    first_source: Callable[[Record], Path | None]


@dataclass(frozen=True)
class RefreshPreparation:
    normalize: Callable[[Record], Record]
    defer: Callable[[Record], None]
    ensure_reference: Callable[[Record], bool]


@dataclass(frozen=True)
class RefreshProfiles:
    fallback: Callable[[Record], Record]
    generate: GenerateProfile


@dataclass(frozen=True)
class CandidateMedia:
    expand_sources: Callable[[str, list[str]], tuple[list[str], list[Record]]]
    default_size: Callable[[str], Record]
    size_reference: Callable[[str | None], str]
    image_suffixes: Callable[[], Collection[str]]
    output_directory: Callable[[str], Path]
    thumbnail: Callable[[Any, Path, int], Record]


@dataclass(frozen=True)
class CandidatePreparation:
    defer: Callable[[Record], None]
    ensure_reference: Callable[[Record], bool]
    ensure_profile: EnsureProfile
    ensure_pose_jobs: Callable[[Record], bool]


@dataclass(frozen=True)
class CandidateStorage:
    owner_fields: Callable[[], Record]
    directory: Callable[[], Path]
    save: Callable[[Path, Record], None]
