"""Media lookup, output storage and display capabilities for accessory galleries."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class GalleryAssets:
    sources: Callable[[Record], list[Path]]
    default_reference: Callable[[Record], Path | None]
    clean_sprites: Callable[[Record], list[Record]]
    image_jobs: Callable[[Record], list[Record]]
    resolve_path: Callable[[Any], Path]
    derived_paths: Callable[[Record], list[Path]]


@dataclass(frozen=True)
class GalleryStorage:
    output_directory: Callable[[], Path]
    write_directory: Callable[[str], Path]
    public_url: Callable[[Path], str]


@dataclass(frozen=True)
class GalleryDisplay:
    public_text: Callable[[Any], str]
    audit: Callable[[Record, Path], Record]
    current_user: Callable[[], Record]
    redact: Callable[[Record, Record], Record]
