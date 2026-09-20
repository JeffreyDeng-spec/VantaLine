"""Preview sprite decoding, selection and source orientation."""
from typing import Any
from pathlib import Path
import cv2
import numpy as np
from .preview_sprite_ports import PreviewSpriteInventory, PreviewSpritePoses, PreviewSpriteMedia, PreviewSpriteGeometry

def load_clean_sprite(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    if image.ndim != 3 or image.shape[2] < 4:
        return None
    alpha = image[:, :, 3]
    if int((alpha > 8).sum()) < 240:
        return None
    bgr = image[:, :, :3]
    return bgr.copy(), alpha.copy()

class PreviewSpriteRenderer:
    def __init__(self, inventory: PreviewSpriteInventory, poses: PreviewSpritePoses, media: PreviewSpriteMedia, geometry: PreviewSpriteGeometry) -> None:
        self._inventory = inventory
        self._poses = poses
        self._media = media
        self._geometry = geometry

    def restore_object_sprite_source_orientation_for_render(self,
        asset: np.ndarray,
        mask: np.ndarray,
        sprite_meta: dict[str, Any],
        *,
        top_view_pose: bool,
    ) -> tuple[np.ndarray, np.ndarray, float, float]:
        try:
            requested = float(sprite_meta.get("source_restore_rotation_degrees") or 0.0)
        except (TypeError, ValueError):
            requested = 0.0
        if top_view_pose or abs(requested) < 0.05:
            sprite_meta["source_orientation_restored_for_render"] = False
            sprite_meta["source_restore_rotation_degrees_requested"] = round(float(requested), 2)
            return asset, mask, 0.0, requested if abs(requested) >= 0.05 else 0.0
        restored_asset, restored_mask = self._geometry.rotate()(asset, mask, requested)
        sprite_meta["source_orientation_restored_for_render"] = True
        sprite_meta["source_restore_rotation_degrees_requested"] = round(float(requested), 2)
        return restored_asset, restored_mask, requested, 0.0

    def load_object_preview_sprite(self,
        item: dict[str, Any],
        rng: np.random.Generator,
        target_position: str | None = None,
        pose_family: str | None = None,
        source_position: str | None = None,
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]] | None:
        sprites = self._inventory.assets()(item)
        if not sprites:
            self._inventory.preprocess()(item, allow_ai_cutout=False)
            sprites = self._inventory.assets()(item)
        if sprites:
            candidates = sprites
            if pose_family:
                requested_canonical = self._poses.canonical()(pose_family)
                family_candidates = [
                    asset
                    for asset in candidates
                    if (
                        self._poses.family()(asset) == pose_family
                        or (
                            requested_canonical in {"lying", "upright"}
                            and self._poses.canonical()(self._poses.family()(asset)) == requested_canonical
                        )
                    )
                ]
                if family_candidates:
                    candidates = family_candidates
            if self._poses.top_view()(pose_family or ""):
                upright_candidates = [
                    asset
                    for asset in candidates
                    if (asset.get("source_position") or asset.get("pose_position")) in self._poses.upright_positions()
                ]
                if not upright_candidates:
                    return None
                candidates = upright_candidates
            candidates = self._poses.complete()(candidates, pose_family)
            wanted_position = source_position or target_position
            if wanted_position:
                position_candidates = [
                    asset
                    for asset in candidates
                    if (asset.get("source_position") or asset.get("pose_position")) == wanted_position
                ]
                if (
                    source_position
                    and not position_candidates
                    and not any(
                        asset.get("source_pose_collection_job_id") in {"legacy_clean_sprite", "real_photo_direct_source"}
                        for asset in candidates
                    )
                ):
                    return None
                if position_candidates:
                    candidates = position_candidates
            elif target_position:
                position_candidates = [asset for asset in candidates if asset.get("pose_position") == target_position]
                if position_candidates:
                    candidates = position_candidates
            if not candidates:
                candidates = sprites
            asset = candidates[int(rng.integers(0, len(candidates)))]
            sprite = self._media.decode()(self._media.resolve()(asset.get("path")))
            if sprite:
                meta = dict(asset)
                all_sprites = self._inventory.assets()(item)
                meta["sprite_index"] = next(
                    (
                        idx + 1
                        for idx, candidate in enumerate(all_sprites)
                        if str(candidate.get("path", "")) == str(asset.get("path", ""))
                    ),
                    None,
                )
                meta["sprite_path"] = str(asset.get("path", ""))
                meta["clean_sprite_preprocessed_at"] = item.get("clean_sprite_preprocessed_at")
                meta["clean_sprite_version"] = self._inventory.version()(item)
                return sprite[0], sprite[1], meta
        return None
