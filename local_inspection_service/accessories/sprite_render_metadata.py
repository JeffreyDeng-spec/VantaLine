"""Sprite dimension metadata without application imports."""
from typing import Any
import numpy as np
from .sprite_metadata_ports import SpriteRenderOperations, SpriteImageReads


class SpriteRenderMetadata:
    def __init__(self, operations: SpriteRenderOperations, images: SpriteImageReads) -> None:
        self._operations = operations
        self._images = images


    def asset_visible_shape_px(self, asset: dict[str, Any]) -> tuple[int, int] | None:
        for width_key, height_key in (
            ("visible_width_px", "visible_height_px"),
            ("canonical_visible_width_px", "canonical_visible_height_px"),
        ):
            try:
                width = int(asset.get(width_key) or 0)
                height = int(asset.get(height_key) or 0)
            except (TypeError, ValueError):
                width, height = 0, 0
            if width > 0 and height > 0:
                return width, height
        bbox = asset.get("normalized_bbox_xyxy")
        if isinstance(bbox, list) and len(bbox) >= 4:
            try:
                width = int(bbox[2]) - int(bbox[0])
                height = int(bbox[3]) - int(bbox[1])
                if width > 0 and height > 0:
                    return width, height
            except (TypeError, ValueError):
                pass
        path = self._images.path()(str(asset.get("path") or ""))
        if path.exists():
            image = self._images.decode()(str(path), self._images.unchanged_mode())
            if image is not None and image.ndim == 3 and image.shape[2] >= 4:
                bbox = self._operations.bounds()(image[:, :, 3])
                width = int(bbox[2] - bbox[0])
                height = int(bbox[3] - bbox[1])
                if width > 0 and height > 0:
                    return width, height
        size = asset.get("source_object_size_px")
        if isinstance(size, list) and len(size) >= 2:
            try:
                width = int(size[0])
                height = int(size[1])
                if width > 0 and height > 0:
                    return width, height
            except (TypeError, ValueError):
                pass
        return None

    def apply_laying_standard_render_size_hints(self, assets: list[dict[str, Any]]) -> None:
        lying_shapes = [
            shape
            for asset in assets
            if self._operations.family()(asset.get("source_pose_family") or asset.get("pose_family")) == "lying"
            for shape in [self._operations.visible()(asset)]
            if shape is not None
        ]
        reference_shapes = lying_shapes or [shape for asset in assets for shape in [self._operations.visible()(asset)] if shape is not None]
        if not reference_shapes:
            return
        median_w = float(np.median([shape[0] for shape in reference_shapes]))
        median_h = float(np.median([shape[1] for shape in reference_shapes]))
        long_axis = "height" if median_h >= median_w else "width"
        for asset in assets:
            footprint = asset.get("render_footprint_px") or asset.get("render_size_hint_px")
            if not (isinstance(footprint, list) and len(footprint) >= 2):
                continue
            try:
                first = max(1, int(footprint[0]))
                second = max(1, int(footprint[1]))
            except (TypeError, ValueError):
                continue
            long_side = max(first, second)
            short_side = min(first, second)
            is_source_aspect = str(asset.get("render_scale_basis") or "") == "source_visible_long_short_aspect"
            if is_source_aspect:
                asset_long_axis = str(asset.get("source_long_edge_axis") or "").strip().lower()
                oriented = self._operations.orient()(long_side, short_side, asset_long_axis)
                orientation_basis = "source_visible_long_short_aspect_preserve_source_axis"
                render_long_edge_axis = asset_long_axis or ("height" if oriented[1] >= oriented[0] else "width")
            else:
                oriented = [long_side, short_side] if long_axis == "width" else [short_side, long_side]
                orientation_basis = "lying_pose_collection_visible_bbox"
                render_long_edge_axis = long_axis
            asset.update(
                {
                    "render_footprint_px_unoriented_long_short": [int(long_side), int(short_side)],
                    "render_footprint_px_before_laying_standard_orientation": [int(first), int(second)],
                    "render_footprint_px": oriented,
                    "render_size_hint_px": oriented,
                    "canonical_width_px": oriented[0],
                    "canonical_height_px": oriented[1],
                    "render_long_short_orientation_basis": orientation_basis,
                    "render_long_edge_axis": render_long_edge_axis,
                    "render_laying_standard_reference_visible_size_px": [round(median_w, 3), round(median_h, 3)],
                }
            )

    def sprite_render_size_px(self, item: dict[str, Any], sprite_meta: dict[str, Any] | None, material_type: str) -> tuple[int, int]:
        if material_type == "text":
            return self._operations.physical()(item, material_type)
        meta = sprite_meta or {}
        hint = meta.get("render_size_hint_px") or meta.get("render_footprint_px")
        if isinstance(hint, list) and len(hint) >= 2:
            try:
                return max(16, int(hint[0])), max(16, int(hint[1]))
            except (TypeError, ValueError):
                pass
        source_size = meta.get("source_object_size_px") or [int(meta.get("width") or 1), int(meta.get("height") or 1)]
        footprint = self._operations.footprint()(str(meta.get("source_pose_family") or meta.get("pose_family") or ""), source_size, item.get("physical_size"))
        return int(footprint["render_footprint_px"][0]), int(footprint["render_footprint_px"][1])
