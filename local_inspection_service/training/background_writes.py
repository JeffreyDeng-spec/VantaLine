"""Background identifier allocation and manifest updates, preserving aliases and write order."""
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID


class UpdateBackgroundManifest(Protocol):
    def __call__(self, set_id: str, **updates: Any) -> dict[str, Any]: ...


class BackgroundWrites:
    def __init__(self, safe: Callable[[str], str], load: Callable[[], Any], write: Callable[[Any], None],
                 sets: Callable[[], Path], uuid: Callable[[], UUID], clock: Callable[[], float]):
        self.safe, self.load, self.write = safe, load, write
        self.sets, self.uuid, self.clock = sets, uuid, clock

    def unique_background_set_id(self, base_id: str) -> str:
        clean_id = self.safe(base_id)
        manifest = self.load()
        sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
        if clean_id not in sets and not (self.sets() / clean_id).exists():
            return clean_id
        for _ in range(50):
            candidate = f"{clean_id}_{self.uuid().hex[:6]}"
            if candidate not in sets and not (self.sets() / candidate).exists():
                return candidate
        return f"{clean_id}_{int(self.clock())}"

    def update_background_set_manifest(self, set_id: str, **updates: Any) -> dict[str, Any]:
        manifest = self.load()
        sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
        current = sets.get(set_id, {"id": set_id, "name": set_id.replace("_", " ")})
        current.update(updates)
        sets[set_id] = current
        manifest["sets"] = sets
        manifest.setdefault("default_set_id", "green_conveyor")
        self.write(manifest)
        return current
