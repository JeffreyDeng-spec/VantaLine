"""Background identifiers, image enumeration and ordered permission-aware catalog projection."""
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

Record = dict[str, Any]


def safe_background_set_id(value: str | None) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "").strip()).strip("_")
    return raw or "green_conveyor"




class BackgroundImageFiles:
    def __init__(self, suffixes: Callable[[], Collection[str]]):
        self.suffixes = suffixes

    def image_file_list(self, path: Path) -> list[Path]:
        if not path.exists() or not path.is_dir():
            return []
        return sorted(
            item
            for item in path.iterdir()
            if item.is_file() and item.suffix.lower() in self.suffixes()
        )


@dataclass(frozen=True)
class BackgroundCatalogPaths:
    sets: Callable[[], Path]
    output: Callable[[], Path]


@dataclass(frozen=True)
class BackgroundCatalogRecords:
    load: Callable[[], Any]
    directories: Callable[[], list[Path]]
    payload: Callable[[], Callable[[str, Record | None], Record]]


@dataclass(frozen=True)
class BackgroundCatalogAccess:
    system_owner: Callable[[], str]
    audit: Callable[[Record, Path], Record]
    visible: Callable[[Record, Record, str | None], bool]


class BackgroundCatalog:
    def __init__(self, paths: BackgroundCatalogPaths, records: BackgroundCatalogRecords, access: BackgroundCatalogAccess,
                 safe: Callable[[str | None], str], images: Callable[[Path], list[Path]], url: Callable[[Path], str]):
        self.paths, self.records, self.access = paths, records, access
        self.safe, self.images, self.url = safe, images, url

    def background_set_payload(self, set_id: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        clean_id = self.safe(set_id)
        set_dir = self.paths.sets() / clean_id
        images = self.images(set_dir)
        meta = dict(meta or {})
        if clean_id == "green_conveyor" and not meta.get("owner_user_id"):
            meta["owner_user_id"] = self.access.system_owner()
            meta["owner_username"] = "system"
            meta["shared_with_user_ids"] = ["*"]
        audit = self.access.audit(meta, set_dir)
        return {
            "id": clean_id,
            "name": meta.get("name") or clean_id.replace("_", " "),
            "description": meta.get("description") or "",
            "source": meta.get("source") or "",
            "created_at": audit["created_at"],
            "updated_at": audit["updated_at"],
            "owner_user_id": audit["owner_user_id"],
            "owner_username": audit["owner_username"],
            "shared_with_user_ids": meta.get("shared_with_user_ids") if isinstance(meta.get("shared_with_user_ids"), list) else [],
            "generation_method": meta.get("generation_method") or "",
            "status": meta.get("status") or ("ready" if images else "empty"),
            "image_count": len(images),
            "images": [
                {
                    "name": path.name,
                    "path": str(path),
                    "url": self.url(path) if str(path).startswith(str(self.paths.output())) else f"/api/backgrounds/{clean_id}/{path.name}",
                }
                for path in images
            ],
        }

    def list_background_sets(self, user: dict[str, Any] | None = None, target_user_id: str | None = None) -> list[dict[str, Any]]:
        manifest = self.records.load()
        meta_sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
        ids = {path.name for path in self.records.directories()} | {self.safe(item) for item in meta_sets.keys()}
        items = [
            self.records.payload()(set_id, meta_sets.get(set_id) or meta_sets.get(self.safe(set_id)) or {})
            for set_id in sorted(ids)
        ]
        if user:
            items = [item for item in items if self.access.visible(item, user, target_user_id)]
        return items
