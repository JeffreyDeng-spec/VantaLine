"""Background set manifest persistence with unchanged JSON and filesystem error boundaries."""
from collections.abc import Callable
import json
from pathlib import Path
from typing import Any


class BackgroundManifest:
    def __init__(self, directory: Callable[[], Path], path: Callable[[], Path]):
        self.directory, self.path = directory, path

    def load_background_sets_manifest(self) -> dict[str, Any]:
        try:
            return json.loads(self.path().read_text(encoding="utf-8")) if self.path().exists() else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def write_background_sets_manifest(self, manifest: dict[str, Any]) -> None:
        self.directory().mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps(manifest, indent=2), encoding="utf-8")
