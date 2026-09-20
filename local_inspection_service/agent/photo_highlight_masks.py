"""Explicit photo-highlight image helpers without application imports."""
from typing import Any
import math
import cv2
import numpy as np


def decode_photo_highlight_mask(mask_bgr: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    if mask_bgr is None or mask_bgr.ndim != 3:
        return np.zeros((0, 0), dtype=np.uint8), {"ok": False, "reason": "mask_unreadable"}
    height, width = mask_bgr.shape[:2]
    blue, green, red = cv2.split(mask_bgr.astype(np.int16))
    hsv = cv2.cvtColor(mask_bgr, cv2.COLOR_BGR2HSV)
    _hue, sat, val = cv2.split(hsv)
    highlight = (
        (green >= 145)
        & (red <= 145)
        & (blue <= 145)
        & ((green - np.maximum(red, blue)) >= 35)
        & (sat >= 45)
        & (val >= 70)
    )
    mask = highlight.astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
    num, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
    components: list[tuple[int, int, int, int, int, int, float]] = []
    for idx in range(1, num):
        x, y, comp_w, comp_h, area = [int(value) for value in stats[idx]]
        if area < max(80, int(width * height * 0.0005)):
            continue
        aspect = max(comp_w, comp_h) / float(max(1, min(comp_w, comp_h)))
        components.append((area, idx, x, y, comp_w, comp_h, aspect))
    if not components:
        return np.zeros((height, width), dtype=np.uint8), {"ok": False, "reason": "no_highlight_component", "component_count": 0}
    components.sort(reverse=True)
    main_area, main_idx, x, y, comp_w, comp_h, aspect = components[0]
    kept = (labels == main_idx).astype(np.uint8) * 255
    contours, _ = cv2.findContours(kept, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(kept)
    if contours:
        cv2.drawContours(filled, contours, -1, 255, cv2.FILLED)
    mask_fraction = float((filled > 0).mean()) if filled.size else 0.0
    if mask_fraction < 0.002 or mask_fraction > 0.75:
        return filled, {
            "ok": False,
            "reason": "mask_area_out_of_range",
            "mask_area_fraction": round(mask_fraction, 6),
            "component_count": len(components),
        }
    return filled, {
        "ok": True,
        "bbox_xyxy_ai": [int(x), int(y), int(x + comp_w), int(y + comp_h)],
        "mask_area_fraction": round(mask_fraction, 6),
        "component_count": len(components),
        "main_component_area": int(main_area),
        "main_component_aspect": round(float(aspect), 4),
    }

def photo_highlight_auto_roi_mask(roi_bgr: np.ndarray, ai_roi_mask: np.ndarray) -> tuple[np.ndarray | None, dict[str, Any]]:
    if roi_bgr is None or roi_bgr.ndim != 3 or ai_roi_mask is None or ai_roi_mask.size == 0:
        return None, {"status": "unavailable", "reason": "empty_roi"}
    roi_h, roi_w = roi_bgr.shape[:2]
    if roi_h < 12 or roi_w < 12:
        return None, {"status": "unavailable", "reason": "roi_too_small"}
    ai_binary = ai_roi_mask > 8
    border = np.zeros((roi_h, roi_w), dtype=bool)
    border_size = max(3, min(roi_h, roi_w) // 20)
    border[:border_size, :] = True
    border[-border_size:, :] = True
    border[:, :border_size] = True
    border[:, -border_size:] = True
    bg_pixels = roi_bgr[~ai_binary]
    if bg_pixels.shape[0] < 64:
        bg_pixels = roi_bgr[border]
    if bg_pixels.shape[0] < 64:
        return None, {"status": "unavailable", "reason": "insufficient_background_pixels"}
    bg = np.median(bg_pixels.reshape(-1, 3), axis=0).astype(np.float32)
    diff = np.linalg.norm(roi_bgr.astype(np.float32) - bg, axis=2)
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    _hue, sat, val = cv2.split(hsv)
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 45, 135), np.ones((3, 3), np.uint8), iterations=1) > 0
    seed = (
        (diff > 22)
        | ((val < 122) & (diff > 10))
        | ((sat > 72) & (diff > 12))
        | (edges & (diff > 10))
    ).astype(np.uint8) * 255
    seed = cv2.morphologyEx(seed, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
    seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    num, labels, stats, centroids = cv2.connectedComponentsWithStats((seed > 0).astype(np.uint8), connectivity=8)
    roi_area = roi_h * roi_w
    components: list[dict[str, Any]] = []
    for idx in range(1, num):
        x, y, comp_w, comp_h, area = [int(value) for value in stats[idx]]
        if area < max(80, int(roi_area * 0.002)) or comp_w < 4 or comp_h < 4:
            continue
        component = labels == idx
        overlap = int((component & ai_binary).sum())
        aspect = max(comp_w, comp_h) / float(max(1, min(comp_w, comp_h)))
        # Thin, low-overlap branches are usually straps, cords, or loose tags.
        if aspect > 7.0 and area < roi_area * 0.16 and overlap < area * 0.72:
            continue
        cx, cy = centroids[idx]
        center_distance = math.hypot(float(cx - roi_w / 2.0), float(cy - roi_h / 2.0)) / max(1.0, math.hypot(roi_w, roi_h))
        score = overlap * 2.0 + area * 0.45 - center_distance * roi_area * 0.08
        components.append(
            {
                "idx": int(idx),
                "area": int(area),
                "overlap": int(overlap),
                "aspect": round(float(aspect), 4),
                "bbox": [int(x), int(y), int(x + comp_w), int(y + comp_h)],
                "score": float(score),
            }
        )
    if not components:
        return None, {"status": "unavailable", "reason": "no_auto_foreground_component"}
    components.sort(key=lambda item: item["score"], reverse=True)
    keep = np.zeros((roi_h, roi_w), dtype=np.uint8)
    kept: list[dict[str, Any]] = []
    for component in components[:4]:
        if kept and component["overlap"] < max(64, component["area"] * 0.12):
            continue
        keep[labels == component["idx"]] = 255
        kept.append(component)
    if int((keep > 0).sum()) < max(120, int(roi_area * 0.003)):
        return None, {"status": "unavailable", "reason": "auto_foreground_too_small"}
    keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=1)
    keep = cv2.GaussianBlur(keep, (3, 3), 0)
    return keep, {
        "status": "available",
        "kept_component_count": len(kept),
        "candidate_component_count": len(components),
        "kept_components": [
            {
                "bbox": component["bbox"],
                "area": component["area"],
                "overlap": component["overlap"],
                "aspect": component["aspect"],
            }
            for component in kept[:4]
        ],
    }
