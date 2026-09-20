"""Masked sprite geometry without application imports."""
from typing import Any
import cv2
import numpy as np


def normalize_angle_180(angle: float) -> float:
    normalized = (float(angle) + 90.0) % 180.0 - 90.0
    return 90.0 if normalized <= -89.999 else normalized

def alpha_bbox(mask: np.ndarray, threshold: int = 8) -> list[int]:
    ys, xs = np.where(mask > threshold)
    if len(xs) == 0 or len(ys) == 0:
        return [0, 0, 0, 0]
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]

def alpha_edge_max(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
    edge = np.concatenate([mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]])
    return int(edge.max()) if edge.size else 0

def alpha_edge_stats(mask: np.ndarray) -> dict[str, Any]:
    if mask.size == 0:
        return {"max": 0, "nonzero_px": 0, "mean": 0.0}
    edge = np.concatenate([mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]])
    if edge.size == 0:
        return {"max": 0, "nonzero_px": 0, "mean": 0.0}
    return {
        "max": int(edge.max()),
        "nonzero_px": int((edge > 0).sum()),
        "mean": round(float(edge.mean()), 4),
    }

def alpha_component_count(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
    num, _, stats, _ = cv2.connectedComponentsWithStats((mask > 12).astype(np.uint8), connectivity=8)
    if num <= 1:
        return 0
    image_area = mask.shape[0] * mask.shape[1]
    return sum(1 for idx in range(1, num) if stats[idx, cv2.CC_STAT_AREA] >= max(24, image_area * 0.00008))

def add_sprite_safety_margin(asset: np.ndarray, mask: np.ndarray, margin: int = 10) -> tuple[np.ndarray, np.ndarray]:
    if asset.size == 0 or mask.size == 0:
        return asset, mask
    return (
        cv2.copyMakeBorder(asset, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=(0, 0, 0)),
        cv2.copyMakeBorder(mask, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=0),
    )

def trim_masked_asset(asset: np.ndarray, mask: np.ndarray, pad: int = 4) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.where(mask > 8)
    if len(xs) == 0 or len(ys) == 0:
        return asset, mask
    x1, x2 = max(0, int(xs.min()) - pad), min(mask.shape[1], int(xs.max()) + pad + 1)
    y1, y2 = max(0, int(ys.min()) - pad), min(mask.shape[0], int(ys.max()) + pad + 1)
    return asset[y1:y2, x1:x2].copy(), mask[y1:y2, x1:x2].copy()
