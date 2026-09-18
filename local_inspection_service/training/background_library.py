"""Background manifest/library lookup; selection keeps its existing seed and ownership behavior."""
from collections.abc import Callable, Set
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class BackgroundPaths:
    directory: Callable[[], Path]
    default_image: Callable[[], Path]
    suffixes: Callable[[], Set[str]]


@dataclass(frozen=True)
class BackgroundSetLookup:
    manifest: Callable[[], Any]
    selected: Callable[[str | None], str | None]
    files: Callable[[str | None], list[Path]]


class TrainingBackgroundLibrary:
    def __init__(self, paths: BackgroundPaths, lookup: BackgroundSetLookup):
        self.paths, self.lookup = paths, lookup

    def load_training_background_manifest(self) -> dict[str, Any]:
        manifest_path = self.paths.directory() / "background_manifest.json"
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        except json.JSONDecodeError:
            return {}

    def training_background_library(self, background_set_id: str | None = None) -> list[dict[str, Any]]:
        manifest = self.lookup.manifest()
        set_id = self.lookup.selected(background_set_id)
        files = self.lookup.files(set_id)
        if not files:
            files = sorted(
                path
                for path in self.paths.directory().iterdir()
                if path.is_file() and path.suffix.lower() in self.paths.suffixes()
            ) if self.paths.directory().exists() else []
            if self.paths.default_image().exists() and self.paths.default_image() not in files:
                files.insert(0, self.paths.default_image())
        elif set_id == "green_conveyor" and self.paths.default_image().exists() and self.paths.default_image() not in files:
            files.insert(0, self.paths.default_image())
        library: list[dict[str, Any]] = []
        for index, path in enumerate(files):
            background_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", path.stem).strip("_") or f"background_{index + 1}"
            source = str(path)
            if path.name == manifest.get("asset"):
                source = str(manifest.get("reference_photo") or manifest.get("workspace_path") or path)
            library.append(
                {
                    "id": background_id,
                    "path": path,
                    "source": source,
                    "source_asset": path.name,
                    "background_set_id": set_id,
                    "library_index": index,
                    "library_size": len(files),
                }
            )
        return library
