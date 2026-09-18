"""Approved-preview validation preserving exact matching and stale-state mutation order."""
from collections.abc import Callable
import json
from pathlib import Path
from typing import Any
from fastapi import HTTPException
from ..schemas.training import TrainingStartRequest

Record = dict[str, Any]


class TrainingPreviewApproval:
    def __init__(self, jobs: Callable[[], Path],
                 background: Callable[[], Callable[[str | None, Record | None], str | None]],
                 cache: Callable[[list[Record]], str]):
        self.jobs, self.background, self.cache = jobs, background, cache

    def validate_approved_preview(self,
        config: dict[str, Any],
        request: TrainingStartRequest,
        selected: list[dict[str, Any]],
        user: dict[str, Any] | None = None,
    ) -> None:
        if not request.approved_preview_id:
            return
        preview_path = self.jobs() / f"{request.approved_preview_id}.json"
        if not preview_path.exists():
            raise HTTPException(status_code=409, detail="Approved preview is no longer available. Generate a fresh preview.")
        try:
            preview = json.loads(preview_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail="Approved preview metadata is unreadable. Generate a fresh preview.") from exc

        selected_ids = [item["id"] for item in selected]
        preview_ids = [item.get("id") for item in preview.get("selected_accessories", []) if isinstance(item, dict)]
        if preview_ids != selected_ids:
            raise HTTPException(status_code=409, detail="Approved preview does not match the selected accessories.")
        requested_background_set_id = self.background()(request.background_set_id, user)
        if preview.get("background_set_id") != requested_background_set_id:
            raise HTTPException(status_code=409, detail="Approved preview does not match the selected background set. Generate a fresh preview.")

        current_cache_key = self.cache(selected) if selected else None
        if preview.get("preview_cache_key") != current_cache_key:
            config["training"].update(
                {
                    "preview_urls": [],
                    "previews": [],
                    "preview_stale_reason": "clean_sprite_version_changed",
                    "current_preview_cache_key": current_cache_key,
                }
            )
            raise HTTPException(status_code=409, detail="Approved preview is stale. Generate a fresh preview.")
