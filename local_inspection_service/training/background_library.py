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
from .background_file_ports import BackgroundLibraryFiles


class TrainingBackgroundLibrary:
    def __init__(self, paths: BackgroundPaths, lookup: BackgroundSetLookup, *, files: BackgroundLibraryFiles):
        self.paths, self.lookup = paths, lookup
        if files is None:
            raise TypeError("explicit background files are required")
        self.files = files

    def load_training_background_manifest(self) -> dict[str, Any]:
        manifest_path = self.paths.directory() / "background_manifest.json"
        try:
            return json.loads(self.files.read_text(manifest_path, encoding="utf-8")) if self.files.exists(manifest_path) else {}
        except json.JSONDecodeError:
            return {}

    def training_background_library(self, background_set_id: str | None = None) -> list[dict[str, Any]]:
        manifest = self.lookup.manifest()
        set_id = self.lookup.selected(background_set_id)
        files = self.lookup.files(set_id)
        if not files:
            files = sorted(
                path
                for path in self.files.iterdir(self.paths.directory())
                if self.files.is_file(path) and path.suffix.lower() in self.paths.suffixes()
            ) if self.files.exists(self.paths.directory()) else []
            if self.files.exists(self.paths.default_image()) and self.paths.default_image() not in files:
                files.insert(0, self.paths.default_image())
        elif set_id == "green_conveyor" and self.files.exists(self.paths.default_image()) and self.paths.default_image() not in files:
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
