"""Minimal media-writing capability shared by evidence producers."""
from pathlib import Path
from typing import Protocol


class MediaWriter(Protocol):
    def path(self, owner: str, standard: str, name: str) -> Path: ...
    def write(self, path: Path, data: bytes) -> None: ...
