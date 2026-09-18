"""Visible background media lookup and ordered catalog/default projection."""
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any, Protocol
from fastapi import HTTPException
from fastapi.responses import FileResponse
from .background_selection import BackgroundSetList

Record = dict[str, Any]


class SelectBackgroundSet(Protocol):
    def __call__(self, background_set_id: str | None, user: Record | None = None,
                 target_user_id: str | None = None) -> str | None: ...


class BackgroundQuery:
    def __init__(self, current: Callable[[], Record], admin: Callable[[Record], bool], safe: Callable[[str], str],
                 listing: BackgroundSetList, load: Callable[[], Any], selected: Callable[[], SelectBackgroundSet],
                 sets: Callable[[], Path], suffixes: Callable[[], Collection[str]]):
        self.current, self.admin, self.safe = current, admin, safe
        self.list, self.load, self.selected = listing, load, selected
        self.sets, self.suffixes = sets, suffixes

    def background_image(self, set_id: str, image_name: str) -> FileResponse:
        user = self.current()
        clean_id = self.safe(set_id)
        if not any(item.get("id") == clean_id for item in self.list(user)):
            raise HTTPException(status_code=404, detail="Background image not found")
        clean_name = Path(image_name).name
        path = self.sets() / clean_id / clean_name
        if not path.exists() or path.suffix.lower() not in self.suffixes():
            raise HTTPException(status_code=404, detail="Background image not found")
        return FileResponse(path)

    def training_background_sets(self, user_id: str | None = None) -> dict[str, Any]:
        user = self.current()
        target_user_id = user_id if self.admin(user) else None
        sets = self.list(user, target_user_id)
        manifest = self.load()
        default_id = self.selected()(manifest.get("default_set_id") or None, user, target_user_id)
        return {"background_sets": sets, "default_set_id": default_id}
