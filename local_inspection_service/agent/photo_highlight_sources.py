"""Explicit photo highlight sources service without application imports."""
from typing import Any
from .photo_highlight_ports import PhotoSourceMedia, PhotoSpriteLimits, PhotoSpriteReadiness
from pathlib import Path


class PhotoHighlightSources:
    def __init__(self, media: PhotoSourceMedia, limits: PhotoSpriteLimits, sprites: PhotoSpriteReadiness) -> None:
        self._media = media
        self._limits = limits
        self._sprites = sprites

    def object_photo_highlight_source_paths(self, item: dict[str, Any], *, limit: int) -> list[Path]:
        paths: list[Path] = []
        seen: set[Path] = set()
        for raw_path in item.get("source_files") or []:
            path = self._media.resolve()(raw_path)
            if path in seen or path.suffix.lower() not in self._media.suffixes():
                continue
            if path.stem.endswith("_rectified"):
                continue
            if not path.exists():
                continue
            paths.append(path)
            seen.add(path)
            if len(paths) >= limit:
                break
        return paths

    def photo_highlight_clean_sprites_ready(self, item: dict[str, Any], source_paths: list[Path]) -> bool:
        required_sources = {str(path) for path in source_paths[:self._limits.minimum()]}
        if len(required_sources) < self._limits.minimum():
            return False
        sprites = [
            asset
            for asset in self._sprites.assets()(item)
            if asset.get("method") == "real_photo_highlight_mask_sprite"
            and int(asset.get("photo_highlight_sprite_build") or 0) >= self._limits.version()
        ]
        if len(sprites) < self._limits.minimum():
            return False
        sprite_sources = {str(self._media.resolve()(asset.get("source_photo_path") or asset.get("source_path"))) for asset in sprites}
        return required_sources.issubset(sprite_sources) and self._sprites.complete()(item, sprites)
