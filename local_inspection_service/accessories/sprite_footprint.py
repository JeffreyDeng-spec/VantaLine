"""Sprite dimension metadata without application imports."""
from typing import Any

from .sprite_metadata_ports import SpritePhysicalPolicy, SpriteFootprintMetadataOperations


class SpriteFootprintMetadata:
    def __init__(self, policy: SpritePhysicalPolicy, operations: SpriteFootprintMetadataOperations) -> None:
        self._policy = policy
        self._operations = operations


    def object_physical_size_mm(self, size: dict[str, Any] | None) -> tuple[float, float, float]:
        size = size or {}
        return (
            float(size.get("length_mm") or self._policy.defaults()["length_mm"]),
            float(size.get("width_mm") or self._policy.defaults()["width_mm"]),
            float(size.get("height_mm") or self._policy.defaults()["height_mm"]),
        )

    def pose_family_is_top_view(self, pose_family: str, source_size_px: list[int] | tuple[int, int] | None = None) -> bool:
        family = self._operations.family()(pose_family)
        if family == "upright":
            return True
        if family == "lying":
            return False
        if source_size_px and len(source_size_px) >= 2:
            w, h = max(1, int(source_size_px[0])), max(1, int(source_size_px[1]))
            return max(w, h) / max(1, min(w, h)) < 1.35
        return False

    def oriented_long_short_pair_for_source(self, source_size_px: list[int] | tuple[int, int] | None, long_value: float, short_value: float) -> list[float]:
        metadata = self._operations.source()(source_size_px)
        if metadata["source_long_edge_axis"] == "width":
            return [long_value, short_value]
        return [short_value, long_value]

    def pose_render_footprint_metadata(self,
        pose_family: str,
        source_size_px: list[int] | tuple[int, int],
        physical_size: dict[str, Any] | None,
    ) -> dict[str, Any]:
        source_long_short = self._operations.source()(source_size_px)
        source_w = int(source_long_short["source_visible_width_px"])
        source_h = int(source_long_short["source_visible_height_px"])
        length_mm, width_mm, height_mm = self._operations.physical()(physical_size)
        length_to_cross_section = length_mm / max(width_mm, height_mm, 1.0)
        source_ratio = float(source_long_short["source_long_short_ratio"])
        source_is_elongated = source_ratio >= self._policy.elongated_min()
        if source_is_elongated:
            footprint_long_mm = max(length_mm, width_mm, height_mm)
            footprint_short_mm = max(1.0, footprint_long_mm / source_ratio)
            footprint_mm = self._operations.orient()([source_w, source_h], footprint_long_mm, footprint_short_mm)
            footprint_px = [
                max(16, int(round(footprint_mm[0] * self._policy.pixels_per_mm()))),
                max(16, int(round(footprint_mm[1] * self._policy.pixels_per_mm()))),
            ]
            basis = "source_visible_long_short_aspect"
            return {
                **source_long_short,
                "render_scale_basis": basis,
                "render_footprint_mm": [round(float(footprint_mm[0]), 2), round(float(footprint_mm[1]), 2)],
                "render_footprint_px": footprint_px,
                "render_size_hint_px": footprint_px,
                "canonical_width_px": footprint_px[0],
                "canonical_height_px": footprint_px[1],
                "physical_footprint_basis": basis,
                "render_footprint_mm_unoriented_long_short": [round(float(footprint_long_mm), 2), round(float(footprint_short_mm), 2)],
                "render_footprint_px_unoriented_long_short": [max(16, int(round(footprint_long_mm * self._policy.pixels_per_mm()))), max(16, int(round(footprint_short_mm * self._policy.pixels_per_mm())))],
                "render_source_aspect_preserved": True,
            }
        if length_to_cross_section <= 2.0:
            footprint_w_mm = length_mm
            footprint_h_mm = max(width_mm, height_mm)
            basis = "shared_length_width_physical_footprint"
        elif self._operations.top_view()(pose_family, [source_w, source_h]):
                diameter_mm = max(width_mm, height_mm)
                footprint_w_mm = diameter_mm
                footprint_h_mm = diameter_mm
                basis = "cap_outer_edge_diameter_mm"
        else:
            visible_side_mm = max(width_mm, height_mm * 0.72)
            footprint_w_mm = visible_side_mm
            footprint_h_mm = length_mm
            basis = "side_major_axis_length_mm"
        footprint_px = [
            max(16, int(round(footprint_w_mm * self._policy.pixels_per_mm()))),
            max(16, int(round(footprint_h_mm * self._policy.pixels_per_mm()))),
        ]
        return {
            **source_long_short,
            "render_scale_basis": basis,
            "render_footprint_mm": [round(float(footprint_w_mm), 2), round(float(footprint_h_mm), 2)],
            "render_footprint_px": footprint_px,
            "render_size_hint_px": footprint_px,
            "canonical_width_px": footprint_px[0],
            "canonical_height_px": footprint_px[1],
            "physical_footprint_basis": basis,
            "render_source_aspect_preserved": False,
        }
