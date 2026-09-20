"""Sprite artifact publication without application imports."""
from typing import Any
import numpy as np
from .sprite_publication_ports import SpriteCanvasGeometry, SpriteCanvasImageReads, SpriteResampling, SpriteImageEncoder


class SpriteCanvasNormalizer:
    def __init__(self, geometry: SpriteCanvasGeometry, images: SpriteCanvasImageReads, sampling: SpriteResampling, encoder: SpriteImageEncoder) -> None:
        self._geometry = geometry
        self._images = images
        self._sampling = sampling
        self._encoder = encoder


    def normalize_sprite_family_canvases(self, generated: list[dict[str, Any]]) -> None:
        groups: dict[str, list[dict[str, Any]]] = {"all_pose_families": generated}
        for family_assets in groups.values():
            loaded: list[tuple[dict[str, Any], np.ndarray, np.ndarray]] = []
            visible_major_axes = []
            for asset in family_assets:
                path = self._images.resolve()(asset.get("path"))
                image = self._images.decode()(str(path), self._images.unchanged_mode())
                if image is None or image.ndim != 3 or image.shape[2] < 4:
                    continue
                asset["path"] = str(path)
                alpha = image[:, :, 3]
                bbox = self._geometry.bounds()(alpha)
                visible_w = int(bbox[2] - bbox[0])
                visible_h = int(bbox[3] - bbox[1])
                visible_major = max(visible_w, visible_h)
                if visible_major <= 0:
                    continue
                visible_major_axes.append(visible_major)
                loaded.append((asset, image[:, :, :3], alpha))
            if not loaded:
                continue
            canonical_visible_major_axis = max(visible_major_axes)
            for asset, bgr, alpha in loaded:
                asset_bgr, asset_alpha = self._geometry.trim()(bgr, alpha, pad=8)
                for _ in range(3):
                    bbox = self._geometry.bounds()(asset_alpha)
                    visible_w = max(1, int(bbox[2] - bbox[0]))
                    visible_h = max(1, int(bbox[3] - bbox[1]))
                    visible_major = max(visible_w, visible_h)
                    scale = canonical_visible_major_axis / visible_major
                    if abs(scale - 1.0) <= 0.006:
                        break
                    resized_size = (
                        max(1, int(round(asset_bgr.shape[1] * scale))),
                        max(1, int(round(asset_bgr.shape[0] * scale))),
                    )
                    asset_bgr = self._sampling.resize()(asset_bgr, resized_size, interpolation=self._sampling.cubic() if scale > 1 else self._sampling.area())
                    asset_alpha = self._sampling.resize()(asset_alpha, resized_size, interpolation=self._sampling.linear())
                margin = max(18, int(round(max(asset_bgr.shape[:2]) * 0.08)))
                asset_bgr, asset_alpha = self._geometry.margin()(asset_bgr, asset_alpha, margin)
                bbox = self._geometry.bounds()(asset_alpha)
                rgba = self._encoder.convert()(asset_bgr, self._encoder.bgra_mode())
                rgba[:, :, 3] = asset_alpha
                self._encoder.write()(str(self._images.resolve()(asset.get("path"))), rgba)
                edge_max = self._geometry.edge_max()(asset_alpha)
                asset.update(
                    {
                        "width": int(asset_bgr.shape[1]),
                        "height": int(asset_bgr.shape[0]),
                        "normalized_asset_size_px": [int(asset_bgr.shape[1]), int(asset_bgr.shape[0])],
                        "normalized_asset_dimensions_px": [int(asset_bgr.shape[1]), int(asset_bgr.shape[0])],
                        "canonical_asset_dimensions_px": [int(asset_bgr.shape[1]), int(asset_bgr.shape[0])],
                        "canonical_canvas_size_px": [int(asset_bgr.shape[1]), int(asset_bgr.shape[0])],
                        "normalized_bbox_xyxy": bbox,
                        "canonical_visible_width_px": int(bbox[2] - bbox[0]),
                        "canonical_visible_major_axis_px": int(canonical_visible_major_axis),
                        "visible_width_px": int(bbox[2] - bbox[0]),
                        "visible_height_px": int(bbox[3] - bbox[1]),
                        "canonical_family_width_normalized": True,
                        "canonical_all_pose_family_size_normalized": True,
                        "post_rotation_safety_margin_px": int(margin),
                        "edge_alpha_max": edge_max,
                        "edge_alpha_pass": edge_max <= 12,
                        "alpha_edge_stats": self._geometry.edge_stats()(asset_alpha),
                    }
                )
