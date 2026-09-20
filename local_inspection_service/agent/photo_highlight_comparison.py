"""Explicit photo-highlight image helpers without application imports."""
from typing import Any
import math
import numpy as np
from .photo_highlight_image_ports import PhotoMaskGeometry


class PhotoHighlightComparison:
    def __init__(self, geometry: PhotoMaskGeometry) -> None:
        self._geometry = geometry


    def photo_highlight_auto_compare(self, ai_roi_mask: np.ndarray, auto_roi_mask: np.ndarray | None) -> dict[str, Any]:
        if auto_roi_mask is None or auto_roi_mask.size == 0 or ai_roi_mask is None or ai_roi_mask.size == 0:
            return {"ok": True, "status": "skipped", "reason": "auto_mask_unavailable", "score": 0.0}
        ai_binary = ai_roi_mask > 8
        auto_binary = auto_roi_mask > 28
        ai_area = int(ai_binary.sum())
        auto_area = int(auto_binary.sum())
        if ai_area < 240 or auto_area < 240:
            return {
                "ok": True,
                "status": "skipped",
                "reason": "insufficient_mask_area",
                "ai_area_px": ai_area,
                "auto_area_px": auto_area,
                "score": 0.0,
            }
        intersection = int((ai_binary & auto_binary).sum())
        union = int((ai_binary | auto_binary).sum())
        mask_iou = float(intersection) / float(max(1, union))
        ai_bbox = self._geometry.alpha()(ai_roi_mask, threshold=8)
        auto_bbox = self._geometry.alpha()(auto_roi_mask, threshold=28)
        bbox_iou = self._geometry.iou()(ai_bbox, auto_bbox)
        area_ratio = float(ai_area) / float(max(1, auto_area))
        ai_cx = (ai_bbox[0] + ai_bbox[2]) / 2.0
        ai_cy = (ai_bbox[1] + ai_bbox[3]) / 2.0
        auto_cx = (auto_bbox[0] + auto_bbox[2]) / 2.0
        auto_cy = (auto_bbox[1] + auto_bbox[3]) / 2.0
        center_distance = math.hypot(ai_cx - auto_cx, ai_cy - auto_cy) / max(1.0, math.hypot(ai_roi_mask.shape[1], ai_roi_mask.shape[0]))
        ai_extra_fraction = float((ai_binary & ~auto_binary).sum()) / float(max(1, ai_area))
        auto_extra_fraction = float((auto_binary & ~ai_binary).sum()) / float(max(1, auto_area))
        ok = (
            0.55 <= area_ratio <= 1.65
            and bbox_iou >= 0.58
            and center_distance <= 0.18
            and not (mask_iou < 0.72 and ai_extra_fraction > 0.18)
            and not (mask_iou < 0.62 and auto_extra_fraction > 0.30)
        )
        score = (
            mask_iou * 0.45
            + bbox_iou * 0.30
            + max(0.0, 1.0 - abs(math.log(max(area_ratio, 1e-6)))) * 0.15
            + max(0.0, 1.0 - center_distance / 0.18) * 0.10
        )
        return {
            "ok": bool(ok),
            "status": "passed" if ok else "failed",
            "reason": "" if ok else "ai_mask_auto_crop_mismatch",
            "score": round(float(score), 6),
            "mask_iou": round(float(mask_iou), 6),
            "bbox_iou": round(float(bbox_iou), 6),
            "area_ratio_ai_to_auto": round(float(area_ratio), 6),
            "center_distance_ratio": round(float(center_distance), 6),
            "ai_extra_fraction": round(float(ai_extra_fraction), 6),
            "auto_extra_fraction": round(float(auto_extra_fraction), 6),
            "ai_bbox_xyxy_roi": ai_bbox,
            "auto_bbox_xyxy_roi": auto_bbox,
            "ai_area_px": ai_area,
            "auto_area_px": auto_area,
        }
