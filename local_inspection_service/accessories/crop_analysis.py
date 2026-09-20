"""Accessory crop-component analysis and selection without application imports."""
from typing import Any
import cv2
import numpy as np


def alpha_component_cutouts(image: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    if image.ndim != 3 or image.shape[2] < 4:
        return []
    bgr = image[:, :, :3]
    alpha = image[:, :, 3]
    binary = (alpha > 12).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    image_area = alpha.shape[0] * alpha.shape[1]
    cutouts: list[tuple[np.ndarray, np.ndarray]] = []
    for idx in range(1, num):
        x, y, w, h, area = stats[idx]
        if area < max(240, image_area * 0.0005) or w < 8 or h < 8:
            continue
        pad = max(4, int(max(w, h) * 0.04))
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(alpha.shape[1], x + w + pad), min(alpha.shape[0], y + h + pad)
        cutouts.append((bgr[y1:y2, x1:x2].copy(), alpha[y1:y2, x1:x2].copy()))
    return sorted(cutouts, key=lambda item: int((item[1] > 12).sum()), reverse=True)[:12]

def alpha_component_summary(alpha: np.ndarray, threshold: int = 28) -> tuple[int, int]:
    if alpha.size == 0:
        return 0, 0
    num, _, stats, _ = cv2.connectedComponentsWithStats((alpha > threshold).astype(np.uint8), connectivity=8)
    min_area = max(35, int(alpha.shape[0] * alpha.shape[1] * 0.002))
    count = 0
    area_sum = 0
    for idx in range(1, num):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        count += 1
        area_sum += area
    return count, area_sum
