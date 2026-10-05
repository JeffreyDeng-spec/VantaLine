"""Existing auto-optimization mask visuals with explicit dependency ownership."""
from dataclasses import dataclass
from typing import Any
from pathlib import Path
import cv2
import numpy as np

from .auto_optimization_mask_ports import AutoOptimizationMaskVisualPorts


@dataclass(frozen=True)
class AutoOptimizationMaskVisuals:
    ports: AutoOptimizationMaskVisualPorts

    def decode_multicolor_mask(self, mask_bgr: np.ndarray, assignments: list[dict[str, Any]]) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        if mask_bgr is None or mask_bgr.size == 0:
            return {}, {"ok": False, "reason": "generated_mask_unreadable"}
        work = mask_bgr.astype(np.float32)
        color_masks: dict[str, np.ndarray] = {}
        colors_meta: list[dict[str, Any]] = []
        tolerance = 84
        for item in assignments:
            candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
            palette = item.get("palette") if isinstance(item.get("palette"), dict) else {}
            accessory_id = str(candidate.get("accessory_id") or candidate.get("label") or palette.get("name") or "")
            bgr = np.array(palette.get("bgr") or (0, 255, 0), dtype=np.float32)
            distance = np.sqrt(np.sum((work - bgr) ** 2, axis=2))
            mask = (distance <= tolerance).astype(np.uint8) * 255
            if int(np.count_nonzero(mask)) > 0:
                num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
                cleaned = np.zeros(mask.shape, dtype=np.uint8)
                min_area = max(16, int(mask.shape[0] * mask.shape[1] * 0.00003))
                kept = 0
                for idx in range(1, num_labels):
                    area = int(stats[idx, cv2.CC_STAT_AREA])
                    if area < min_area:
                        continue
                    cleaned[labels == idx] = 255
                    kept += 1
                mask = cleaned
            color_masks[accessory_id] = mask
            colors_meta.append(
                {
                    "accessory_id": accessory_id,
                    "label": str(candidate.get("label") or accessory_id),
                    "color": palette.get("name"),
                    "hex": palette.get("hex"),
                    "area_px": int(np.count_nonzero(mask)),
                }
            )
        total_area = int(sum(item.get("area_px") or 0 for item in colors_meta))
        return color_masks, {"ok": True, "colors": colors_meta, "total_area_px": total_area}

    def draw_auto_optimize_review_overlay(self,
        image_bgr: np.ndarray,
        labels: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        output_path: Path,
    ) -> tuple[str, dict[str, Any]]:
        overlay = image_bgr.copy()
        translucent = overlay.copy()
        rows: list[dict[str, Any]] = []
        for passed, item in [(True, label) for label in labels] + [(False, failure) for failure in failures]:
            bbox = item.get("bbox_xyxy")
            if not isinstance(bbox, list) or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = [int(value) for value in bbox[:4]]
            x1 = max(0, min(x1, overlay.shape[1] - 1))
            x2 = max(x1 + 1, min(x2, overlay.shape[1]))
            y1 = max(0, min(y1, overlay.shape[0] - 1))
            y2 = max(y1 + 1, min(y2, overlay.shape[0]))
            color_bgr = item.get("color_bgr") if isinstance(item.get("color_bgr"), (list, tuple)) else (0, 220, 0)
            color = tuple(int(v) for v in color_bgr[:3])
            mask_path = item.get("full_mask")
            if isinstance(mask_path, np.ndarray):
                translucent[mask_path > 8] = color
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 4, cv2.LINE_AA)
            status_text = "PASS" if passed else "FAIL"
            raw_label = self.ports.bounded_text()(str(item.get("label") or item.get("accessory_id") or "target"), 44)
            label_text = raw_label.encode("ascii", errors="ignore").decode("ascii").strip()
            if not label_text:
                label_text = str(item.get("color") or item.get("color_hex") or item.get("accessory_id") or "target")
            cv2.putText(
                overlay,
                f"{status_text} {label_text}"[:72],
                (x1, max(26, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.78,
                color,
                2,
                cv2.LINE_AA,
            )
            rows.append({"passed": passed, "label": label_text, "bbox_xyxy": [x1, y1, x2, y2], "color": item.get("color_hex")})
        if rows:
            overlay = cv2.addWeighted(translucent, 0.22, overlay, 0.78, 0)
        else:
            cv2.rectangle(overlay, (0, 0), (overlay.shape[1] - 1, overlay.shape[0] - 1), (32, 60, 230), 8)
            cv2.putText(overlay, "FAIL no valid AI mask bbox", (32, 54), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (32, 60, 230), 3, cv2.LINE_AA)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.ports._image_files().imwrite(str(output_path), overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        return self.ports.public_output_url_for_existing()(output_path), {"boxes": rows, "box_count": len(rows)}

    def auto_optimize_text_mask_requires_document_gate(self, candidate: dict[str, Any], profile: dict[str, Any]) -> bool:
        material_type = str(profile.get("material_type") or "").strip().lower()
        if material_type != "text":
            return False
        values: list[str] = [
            str(candidate.get("label") or ""),
            str(profile.get("label") or ""),
            str(profile.get("description") or ""),
            str(profile.get("visual_signature") or ""),
            str(profile.get("mask_scope") or ""),
        ]
        for key in ("distinguishing_text", "positive_cues"):
            raw = profile.get(key)
            if isinstance(raw, list):
                values.extend(str(item or "") for item in raw)
        blob = " ".join(values).lower()
        return any(hint in blob for hint in self.ports.DOCUMENT_LIKE_TEXT_HINTS())

    def validate_auto_optimize_text_mask_region(self,
        image_bgr: np.ndarray,
        full_mask: np.ndarray,
        bbox: list[int],
        candidate: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.ports.auto_optimize_text_mask_requires_document_gate()(candidate, profile):
            return {"ok": True, "skipped": True}
        height, width = image_bgr.shape[:2]
        x1, y1, x2, y2 = [int(value) for value in bbox[:4]]
        x1 = max(0, min(x1, width - 1))
        x2 = max(x1 + 1, min(x2, width))
        y1 = max(0, min(y1, height - 1))
        y2 = max(y1 + 1, min(y2, height))
        roi = image_bgr[y1:y2, x1:x2]
        roi_mask = full_mask[y1:y2, x1:x2] > 8
        visible_pixels = int(np.count_nonzero(roi_mask))
        if roi.size == 0 or visible_pixels <= 0:
            return {"ok": False, "reason": "text_mask_region_empty", "visible_pixels": visible_pixels}
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
        masked_saturation = saturation[roi_mask]
        masked_value = value[roi_mask]
        paper_like = (masked_saturation < 90) & (masked_value > 145)
        light_pixels = masked_value > 145
        paper_like_ratio = float(np.count_nonzero(paper_like)) / max(1, visible_pixels)
        light_ratio = float(np.count_nonzero(light_pixels)) / max(1, visible_pixels)
        metrics = {
            "visible_pixels": visible_pixels,
            "bbox_xyxy": [x1, y1, x2, y2],
            "paper_like_ratio": round(paper_like_ratio, 4),
            "light_ratio": round(light_ratio, 4),
        }
        if paper_like_ratio < 0.18 or light_ratio < 0.22:
            return {
                "ok": False,
                "reason": "text_mask_region_not_document_like",
                **metrics,
            }
        return {"ok": True, **metrics}

    def auto_optimize_mask_verifier_overlay(self, image_bgr: np.ndarray, labels: list[dict[str, Any]]) -> np.ndarray:
        overlay = image_bgr.copy()
        translucent = overlay.copy()
        for label in labels:
            full_mask = label.get("full_mask")
            if not isinstance(full_mask, np.ndarray):
                continue
            color_bgr = label.get("color_bgr") if isinstance(label.get("color_bgr"), (list, tuple)) else (0, 220, 0)
            color = tuple(int(value) for value in color_bgr[:3])
            translucent[full_mask > 8] = color
            bbox = label.get("bbox_xyxy") if isinstance(label.get("bbox_xyxy"), list) else []
            if len(bbox) >= 4:
                x1, y1, x2, y2 = [int(value) for value in bbox[:4]]
                x1 = max(0, min(x1, overlay.shape[1] - 1))
                x2 = max(x1 + 1, min(x2, overlay.shape[1]))
                y1 = max(0, min(y1, overlay.shape[0] - 1))
                y2 = max(y1 + 1, min(y2, overlay.shape[0]))
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 4, cv2.LINE_AA)
                cv2.putText(
                    overlay,
                    self.ports.bounded_text()(str(label.get("label") or label.get("accessory_id") or "target"), 40),
                    (x1, max(26, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.72,
                    color,
                    2,
                    cv2.LINE_AA,
                )
        return cv2.addWeighted(translucent, 0.22, overlay, 0.78, 0)

    def auto_optimize_mask_verifier_crop(self, image_bgr: np.ndarray, label: dict[str, Any]) -> np.ndarray | None:
        bbox = label.get("bbox_xyxy") if isinstance(label.get("bbox_xyxy"), list) else []
        if len(bbox) < 4:
            return None
        x1, y1, x2, y2 = [int(value) for value in bbox[:4]]
        height, width = image_bgr.shape[:2]
        x1 = max(0, min(x1, width - 1))
        x2 = max(x1 + 1, min(x2, width))
        y1 = max(0, min(y1, height - 1))
        y2 = max(y1 + 1, min(y2, height))
        crop = image_bgr[y1:y2, x1:x2].copy()
        full_mask = label.get("full_mask")
        if isinstance(full_mask, np.ndarray):
            mask_crop = full_mask[y1:y2, x1:x2] > 8
            background = np.zeros_like(crop)
            crop = np.where(mask_crop[:, :, None], crop, background)
        return crop

    def clamp_unit_score(self, value: Any, default: float = 0.0) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default
