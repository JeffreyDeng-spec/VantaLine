"""Background set manifest persistence with unchanged JSON and filesystem error boundaries."""
from collections.abc import Callable
import json
from pathlib import Path
from typing import Any
from .background_file_ports import BackgroundManifestFiles


class BackgroundManifest:
    def __init__(self, directory: Callable[[], Path], path: Callable[[], Path], *, files: BackgroundManifestFiles):
        self.directory, self.path = directory, path
        if files is None:
            raise TypeError("explicit background files are required")
        self.files = files

    def load_background_sets_manifest(self) -> dict[str, Any]:
        try:
            return self.files.read_json(self.path()) if self.files.exists(self.path()) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def write_background_sets_manifest(self, manifest: dict[str, Any]) -> None:
        self.directory().mkdir(parents=True, exist_ok=True)
        self.files.write_json(self.path(), manifest, indent=2)
