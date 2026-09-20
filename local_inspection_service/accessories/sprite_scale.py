"""Sprite dimension metadata without application imports."""
from typing import Any
import numpy as np
from .sprite_metadata_ports import SpriteScalePolicy, SpriteScaleOperations


class SpriteScaleMetadata:
    def __init__(self, policy: SpriteScalePolicy, operations: SpriteScaleOperations) -> None:
        self._policy = policy
        self._operations = operations


    def median_source_major_axis_px(self, assets: list[dict[str, Any]], canonical_family: str) -> float | None:
        values: list[int] = []
        for asset in assets:
            if self._operations.family()(asset.get("source_pose_family") or asset.get("pose_family")) != canonical_family:
                continue
            size = asset.get("source_object_size_px")
            if not isinstance(size, list) or len(size) < 2:
                continue
            try:
                values.append(max(1, max(int(size[0]), int(size[1]))))
            except (TypeError, ValueError):
                continue
        if not values:
            return None
        return float(np.median(values))

    def upright_scale_correction_for_assets(self,
        assets: list[dict[str, Any]],
        physical_size: dict[str, Any] | None,
    ) -> dict[str, Any]:
        lying_major = self._operations.median()(assets, "lying")
        upright_major = self._operations.median()(assets, "upright")
        length_mm, width_mm, height_mm = self._operations.physical()(physical_size)
        physical_ratio = length_mm / max(width_mm, height_mm, 1.0)
        if lying_major and upright_major:
            raw_ratio = lying_major / max(upright_major, 1.0)
            physical_min = max(self._policy.minimum(), physical_ratio * 0.75)
            physical_max = min(self._policy.maximum(), physical_ratio * 1.25)
            if physical_min > physical_max:
                physical_min, physical_max = self._policy.minimum(), self._policy.maximum()
            base_ratio = min(max(raw_ratio, physical_min), physical_max)
            ratio = min(
                max(base_ratio * self._policy.visual(), self._policy.minimum()),
                self._policy.maximum(),
            )
            basis = "pose_collection_source_major_axis_ratio_clamped_to_physical_ratio"
            source_dimensions = {
                "lying_source_major_axis_px_median": round(float(lying_major), 3),
                "upright_source_major_axis_px_median": round(float(upright_major), 3),
                "physical_ratio_min": round(float(physical_min), 3),
                "physical_ratio_max": round(float(physical_max), 3),
            }
        else:
            raw_ratio = physical_ratio
            base_ratio = min(max(raw_ratio, 1.0), self._policy.maximum())
            ratio = min(
                max(base_ratio * self._policy.visual(), self._policy.minimum()),
                self._policy.maximum(),
            )
            basis = "canonical_physical_length_to_diameter_ratio"
            source_dimensions = {
                "length_mm": round(float(length_mm), 3),
                "diameter_mm": round(float(max(width_mm, height_mm)), 3),
            }
        return {
            "upright_scale_correction": round(float(ratio), 6),
            "upright_scale_correction_raw": round(float(raw_ratio), 6),
            "upright_scale_correction_before_visual_adjustment": round(float(base_ratio), 6),
            "upright_scale_visual_adjustment": round(float(self._policy.visual()), 6),
            "upright_scale_adjustment_percent": round(float((self._policy.visual() - 1.0) * 100.0), 2),
            "upright_scale_adjustment_reason": "owner_followup_reduce_upright_top_view_10_to_20_percent",
            "upright_scale_visually_adjusted": bool(abs(float(self._policy.visual()) - 1.0) > 0.0005),
            "upright_scale_correction_basis": basis,
            "upright_scale_correction_source_dimensions": source_dimensions,
            "upright_scale_correction_physical_ratio": round(float(physical_ratio), 6),
            "upright_scale_correction_clamped": bool(abs(float(raw_ratio) - float(base_ratio)) > 0.0005),
        }

    def apply_upright_scale_correction_metadata(self, assets: list[dict[str, Any]], physical_size: dict[str, Any] | None) -> None:
        correction = self._operations.correction()(assets, physical_size)
        ratio = float(correction["upright_scale_correction"])
        for asset in assets:
            if self._operations.family()(asset.get("source_pose_family") or asset.get("pose_family")) != "upright":
                asset.setdefault("upright_scale_correction", 1.0)
                continue
            before = asset.get("render_footprint_px")
            if not (isinstance(before, list) and len(before) >= 2):
                continue
            try:
                before_px = [max(1, int(before[0])), max(1, int(before[1]))]
            except (TypeError, ValueError):
                continue
            basis_before = str(asset.get("render_scale_basis") or "cap_outer_edge_diameter_mm")
            if basis_before in {"top_view_length_width_physical_footprint", "shared_length_width_physical_footprint", "source_visible_long_short_aspect"}:
                asset.update(
                    {
                        "render_footprint_px_before_correction": before_px,
                        "render_footprint_px_after_correction": before_px,
                        "render_size_hint_px_before_correction": before_px,
                        "render_size_hint_px": before_px,
                        "render_footprint_px": before_px,
                        "canonical_width_px": before_px[0],
                        "canonical_height_px": before_px[1],
                        "render_scale_basis_before_correction": basis_before,
                        "render_scale_basis": basis_before,
                        "upright_scale_correction": 1.0,
                        "upright_scale_correction_raw": correction["upright_scale_correction_raw"],
                        "upright_scale_correction_before_visual_adjustment": 1.0,
                        "upright_scale_visual_adjustment": 1.0,
                        "upright_scale_adjustment_percent": 0.0,
                        "upright_scale_adjustment_reason": "source_visible_long_short_aspect_uses_no_visual_adjustment",
                        "upright_scale_visually_adjusted": False,
                        "upright_scale_correction_basis": "source_visible_long_short_aspect",
                        "upright_scale_correction_source_dimensions": correction["upright_scale_correction_source_dimensions"],
                        "upright_scale_correction_physical_ratio": correction["upright_scale_correction_physical_ratio"],
                        "upright_scale_correction_clamped": False,
                    }
                )
                continue
            after_px = [max(16, int(round(before_px[0] * ratio))), max(16, int(round(before_px[1] * ratio)))]
            asset.update(correction)
            asset.update(
                {
                    "render_footprint_px_before_correction": before_px,
                    "render_footprint_px_after_correction": after_px,
                    "render_size_hint_px_before_correction": before_px,
                    "render_size_hint_px": after_px,
                    "render_footprint_px": after_px,
                    "canonical_width_px": after_px[0],
                    "canonical_height_px": after_px[1],
                    "render_scale_basis_before_correction": basis_before,
                    "render_scale_basis": f"{basis_before}_scaled_by_{correction['upright_scale_correction_basis']}",
                }
            )
