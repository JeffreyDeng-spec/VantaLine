"""Narrow file and metadata publication dependencies for mask sprites."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .auto_optimization_label_generation_ports import ImageFiles
Record = dict[str, Any]

class SpriteFiles(Protocol):
    def exists(self, path: Path) -> bool: ...

class CleanSprite(Protocol):
    def __call__(self, path: Path, image: np.ndarray, mask: np.ndarray, metadata: Record) -> Record | None: ...

@dataclass(frozen=True)
class SpritePublication:
    safe_record_id: Callable[[], Callable[[str], str]]
    _image_files: Callable[[], ImageFiles]
    write_clean_sprite: Callable[[], CleanSprite]
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _business_files: Callable[[], SpriteFiles]
    public_output_url_for_existing: Callable[[], Callable[[Path], str]]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]
