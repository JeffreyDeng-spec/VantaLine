"""Sprite artifact publication without application imports."""
from typing import Any
from pathlib import Path
import numpy as np
from .sprite_publication_ports import SpriteArtifactGeometry, SpriteArtifactMetadata, SpriteImageEncoder


class SpriteArtifactWriter:
    def __init__(self, geometry: SpriteArtifactGeometry, metadata: SpriteArtifactMetadata, encoder: SpriteImageEncoder) -> None:
        self._geometry = geometry
        self._metadata = metadata
        self._encoder = encoder


    def write_clean_sprite(self, path: Path, asset: np.ndarray, mask: np.ndarray, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
        asset, mask, orientation_metadata = self._geometry.normalize()(asset, mask)
        if asset.size == 0 or mask.size == 0 or int((mask > 8).sum()) < 240:
            return None
        mask, alpha_policy_stats = self._metadata.alpha()(asset, mask, metadata)
        post_rotation_margin = max(18, int(round(max(asset.shape[:2]) * 0.08)))
        asset, mask = self._geometry.margin()(asset, mask, post_rotation_margin)
        bbox = self._geometry.bounds()(mask)
        edge_max = self._geometry.edge_max()(mask)
        edge_stats = self._geometry.edge_stats()(mask)
        if edge_max > 12:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        rgba = self._encoder.convert()(asset, self._encoder.bgra_mode())
        rgba[:, :, 3] = mask
        if not self._encoder.write()(str(path), rgba):
            return None
        payload = {
            "kind": "clean_object_sprite",
            "path": str(path),
            "method": "preprocessed_alpha_sprite",
            "width": int(asset.shape[1]),
            "height": int(asset.shape[0]),
            "normalized_asset_size_px": [int(asset.shape[1]), int(asset.shape[0])],
            "normalized_asset_dimensions_px": [int(asset.shape[1]), int(asset.shape[0])],
            "normalized_bbox_xyxy": bbox,
            "post_rotation_safety_margin_px": int(post_rotation_margin),
            "edge_alpha_max": edge_max,
            "edge_alpha_pass": True,
            "alpha_edge_stats": edge_stats,
            "mask_strategy": "provided_alpha_mask",
            "foreground_component_bbox_xyxy": bbox,
            "removed_stray_component_count": 0,
            "removed_stray_component_area_px": 0,
        }
        if metadata:
            payload.update(metadata)
        payload.update(alpha_policy_stats)
        payload.update(orientation_metadata)
        if (
            metadata
            and isinstance(metadata.get("physical_size_mm"), dict)
            and (not payload.get("render_footprint_px") or not payload.get("render_footprint_mm") or not payload.get("render_scale_basis"))
        ):
            pose_family = str(metadata.get("source_pose_family") or metadata.get("pose_family") or "")
            source_size = metadata.get("source_object_size_px") or payload["normalized_asset_size_px"]
            payload.update(self._metadata.footprint()(pose_family, source_size, metadata.get("physical_size_mm")))
        return payload
