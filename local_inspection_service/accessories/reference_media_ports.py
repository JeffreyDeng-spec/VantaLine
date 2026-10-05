"""Image writing and analysis dependencies for accessory reference media."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import numpy as np

class ReferenceImageWriter(Protocol):
    def imwrite(self, path: str, image: np.ndarray, params: list[int] | None = None) -> bool: ...

@dataclass(frozen=True)
class ReferenceMediaDependencies:
    frame_detail_score: Callable[[], Callable[[np.ndarray], float]]
    frame_histogram: Callable[[], Callable[[np.ndarray], np.ndarray]]
    _image_files: Callable[[], ReferenceImageWriter]
    public_output_url: Callable[[], Callable[[Path], str]]
