"""Background set manifest persistence with unchanged JSON and filesystem error boundaries."""
from collections.abc import Callable
import json
from pathlib import Path
from ..storage.artifacts.files import BusinessFiles
_business_files = BusinessFiles()
from typing import Any


class BackgroundManifest:
    def __init__(self, directory: Callable[[], Path], path: Callable[[], Path]):
        self.directory, self.path = directory, path

    def load_background_sets_manifest(self) -> dict[str, Any]:
        try:
            return _business_files.read_json(self.path()) if _business_files.exists(self.path()) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def write_background_sets_manifest(self, manifest: dict[str, Any]) -> None:
        self.directory().mkdir(parents=True, exist_ok=True)
        _business_files.write_json(self.path(), manifest, indent=2)
