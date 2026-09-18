"""Available-background selection preserving caller scope, short circuits and nullable results."""
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]


class BackgroundSetList(Protocol):
    def __call__(self, user: Record | None = None, target_user_id: str | None = None) -> list[Record]: ...


class BackgroundSelection:
    def __init__(self, safe: Callable[[], Callable[[str | None], str]], listing: BackgroundSetList, load: Callable[[], Any],
                 selected: Callable[[str | None], str | None], images: Callable[[], Callable[[Path], list[Path]]], sets: Callable[[], Path]):
        self.safe, self.list, self.load = safe, listing, load
        self.selected, self.images, self.sets = selected, images, sets

    def selected_background_set_id(self,
        background_set_id: str | None,
        user: dict[str, Any] | None = None,
        target_user_id: str | None = None,
    ) -> str | None:
        requested = self.safe()(background_set_id)
        available = {
            item["id"]
            for item in self.list(user, target_user_id)
            if item.get("image_count", 0) > 0 and str(item.get("status") or "ready") == "ready"
        }
        if requested in available:
            return requested
        manifest = self.load()
        default_id = self.safe()(manifest.get("default_set_id") or "green_conveyor")
        return default_id if default_id in available else (sorted(available)[0] if available else None)

    def background_set_image_files(self, background_set_id: str | None) -> list[Path]:
        selected_id = self.selected(background_set_id)
        if not selected_id:
            return []
        return self.images()(self.sets() / selected_id)
