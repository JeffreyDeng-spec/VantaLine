"""Accessory crop-component analysis and selection without application imports."""
from typing import Any
import math
import cv2
import numpy as np
from .crop_component_ports import CropGeometry


class CropSelection:
    def __init__(self, geometry: CropGeometry) -> None:
        self._geometry = geometry


    def filter_cutout_to_focus_cell(self,
        asset: np.ndarray,
        mask: np.ndarray,
        focus_bbox: tuple[int, int, int, int],
    ) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
        if asset.size == 0 or mask.size == 0:
            return None
        binary = (mask > 12).astype(np.uint8)
        num, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        if num <= 1:
            return None
        fx1, fy1, fx2, fy2 = focus_bbox
        focus_w = max(1, fx2 - fx1)
        focus_h = max(1, fy2 - fy1)
        margin_x = max(6, int(round(focus_w * 0.08)))
        margin_y = max(6, int(round(focus_h * 0.08)))
        keep_x1, keep_y1 = fx1 - margin_x, fy1 - margin_y
        keep_x2, keep_y2 = fx2 + margin_x, fy2 + margin_y
        focus_cx = (fx1 + fx2) / 2.0
        focus_cy = (fy1 + fy2) / 2.0
        max_center_distance = math.hypot(focus_w, focus_h) * 0.58
        kept = np.zeros_like(mask)
        mask_area = mask.shape[0] * mask.shape[1]
        for idx in range(1, num):
            x, y, w, h, area = stats[idx]
            if area < max(24, mask_area * 0.00008):
                continue
            cx, cy = centroids[idx]
            component_x2 = x + w
            component_y2 = y + h
            overlap_w = max(0, min(component_x2, fx2) - max(x, fx1))
            overlap_h = max(0, min(component_y2, fy2) - max(y, fy1))
            overlap_area = overlap_w * overlap_h
            center_in_focus = keep_x1 <= cx <= keep_x2 and keep_y1 <= cy <= keep_y2
            center_near_focus = math.hypot(float(cx - focus_cx), float(cy - focus_cy)) <= max_center_distance
            overlaps_focus = overlap_area >= max(12, area * 0.18)
            if center_in_focus or (center_near_focus and overlaps_focus):
                kept[labels == idx] = mask[labels == idx]
        if int((kept > 8).sum()) < 240:
            return None
        bbox = self._geometry.bounds()(kept)
        x1, y1, x2, y2 = bbox
        pad = max(4, int(round(max(x2 - x1, y2 - y1) * 0.025)))
        x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
        x2, y2 = min(mask.shape[1], x2 + pad), min(mask.shape[0], y2 + pad)
        return asset[y1:y2, x1:x2].copy(), kept[y1:y2, x1:x2].copy(), (int(x1), int(y1), int(x2), int(y2))

    def usable_object_cutout(self, cutout: tuple[np.ndarray, np.ndarray] | None, source_shape: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray] | None:
        if not cutout:
            return None
        cut_asset, cut_mask = self._geometry.trim()(cutout[0], cutout[1], pad=2)
        source_h, source_w = source_shape[:2]
        cut_h, cut_w = cut_asset.shape[:2]
        mask_fill = float((cut_mask > 8).sum()) / max(1, cut_mask.shape[0] * cut_mask.shape[1])
        if cut_w > source_w * 0.82 and cut_h > source_h * 0.82 and mask_fill > 0.72:
            return None
        return cut_asset, cut_mask

    def cleanup_crop_alpha_components(self,
        asset: np.ndarray,
        alpha: np.ndarray,
        anchor_xy: tuple[float, float] | None = None,
        min_area: int = 35,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        if asset.size == 0 or alpha.size == 0:
            return alpha, {
                "mask_strategy": "crop_local_component_cleanup_empty",
                "foreground_component_bbox_xyxy": [0, 0, 0, 0],
                "removed_stray_component_count": 0,
                "removed_stray_component_area_px": 0,
            }
        binary = (alpha > 28).astype(np.uint8)
        num, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        crop_area = alpha.shape[0] * alpha.shape[1]
        components = []
        for idx in range(1, num):
            x, y, w, h, area = stats[idx]
            if area < max(min_area, int(crop_area * 0.002)):
                continue
            cx, cy = centroids[idx]
            components.append(
                {
                    "idx": int(idx),
                    "bbox": [int(x), int(y), int(x + w), int(y + h)],
                    "area": int(area),
                    "center": [float(cx), float(cy)],
                }
            )
        if not components:
            return alpha, {
                "mask_strategy": "crop_local_component_cleanup_no_components",
                "foreground_component_bbox_xyxy": self._geometry.bounds()(alpha),
                "removed_stray_component_count": 0,
                "removed_stray_component_area_px": 0,
            }
        if anchor_xy is None:
            anchor_xy = (asset.shape[1] / 2.0, asset.shape[0] / 2.0)
        ax, ay = anchor_xy
        diagonal = max(1.0, math.hypot(asset.shape[1], asset.shape[0]))

        def score(component: dict[str, Any]) -> float:
            x1, y1, x2, y2 = component["bbox"]
            cx, cy = component["center"]
            contains_anchor = x1 <= ax <= x2 and y1 <= ay <= y2
            distance = math.hypot(float(cx) - ax, float(cy) - ay) / diagonal
            return (2.4 if contains_anchor else 0.0) + math.log1p(float(component["area"])) - distance * 5.0

        selected = max(components, key=score)
        sx1, sy1, sx2, sy2 = selected["bbox"]
        selected_w = max(1, sx2 - sx1)
        selected_h = max(1, sy2 - sy1)
        selected_diag = max(1.0, math.hypot(selected_w, selected_h))
        support_gap_limit = max(10.0, min(selected_w, selected_h) * 0.42)

        def interval_overlap_ratio(a1: int, a2: int, b1: int, b2: int) -> float:
            overlap = max(0, min(a2, b2) - max(a1, b1))
            return overlap / max(1, min(a2 - a1, b2 - b1))

        def bbox_gap(bbox: list[int]) -> float:
            x1, y1, x2, y2 = bbox
            gap_x = max(0, max(sx1, x1) - min(sx2, x2))
            gap_y = max(0, max(sy1, y1) - min(sy2, y2))
            return math.hypot(float(gap_x), float(gap_y))

        keep_components = [selected]
        for component in components:
            if component["idx"] == selected["idx"]:
                continue
            x1, y1, x2, y2 = component["bbox"]
            cx, cy = component["center"]
            area_ratio = float(component["area"]) / max(1.0, float(selected["area"]))
            gap = bbox_gap(component["bbox"])
            horizontal_overlap = interval_overlap_ratio(x1, x2, sx1, sx2)
            vertical_overlap = interval_overlap_ratio(y1, y2, sy1, sy2)
            center_distance = math.hypot(float(cx) - ax, float(cy) - ay)
            close_projected_detail = (
                gap <= support_gap_limit
                and area_ratio <= 0.42
                and max(horizontal_overlap, vertical_overlap) >= 0.42
            )
            anchored_detail = (
                center_distance <= selected_diag * 0.72
                and gap <= support_gap_limit * 1.25
                and area_ratio <= 0.24
                and (horizontal_overlap >= 0.22 or vertical_overlap >= 0.22)
            )
            if close_projected_detail or anchored_detail:
                keep_components.append(component)

        keep = np.zeros_like(alpha)
        for component in keep_components:
            keep[labels == component["idx"]] = 255
        cleaned = cv2.bitwise_and(alpha, keep)
        kept_indexes = {component["idx"] for component in keep_components}
        removed = [component for component in components if component["idx"] not in kept_indexes]
        kept_bbox = self._geometry.bounds()(cleaned)
        return cleaned, {
            "mask_strategy": "crop_local_alpha_center_anchored_components",
            "foreground_component_bbox_xyxy": kept_bbox,
            "foreground_component_area_px": int(sum(component["area"] for component in keep_components)),
            "foreground_component_anchor_xy": [round(float(ax), 2), round(float(ay), 2)],
            "removed_stray_component_count": int(len(removed)),
            "removed_stray_component_area_px": int(sum(component["area"] for component in removed)),
            "candidate_component_count": int(len(components)),
            "kept_component_count": int(len(keep_components)),
        }
