"""Material alpha without application imports."""
from typing import Any
import cv2
import numpy as np


def transparent_object_alpha(asset: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    stats = {
        "transparent_alpha_policy": "preserve_glass_body_weak_alpha",
        "glass_fraction": 0.0,
        "opaque_anchor_fraction": 0.0,
        "edge_fraction": 0.0,
        "transparent_alpha_applied": False,
    }
    if asset.size == 0 or mask.size == 0:
        return mask, stats
    hsv = cv2.cvtColor(asset, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(asset, cv2.COLOR_BGR2GRAY)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    edges = cv2.dilate(cv2.Canny(gray, 36, 116), np.ones((3, 3), np.uint8), iterations=1) > 0
    dark_or_colored = ((val < 118) & (sat > 24)) | (sat > 92)
    glass_body = (mask > 20) & (sat < 72) & (val > 108) & ~edges & ~dark_or_colored
    masked_pixels = max(1, int((mask > 20).sum()))
    opaque_anchor_fraction = float((dark_or_colored & (mask > 20)).sum()) / masked_pixels
    edge_fraction = float((edges & (mask > 20)).sum()) / masked_pixels
    glass_fraction = float(glass_body.sum()) / masked_pixels
    stats.update(
        {
            "glass_fraction": round(float(glass_fraction), 5),
            "opaque_anchor_fraction": round(float(opaque_anchor_fraction), 5),
            "edge_fraction": round(float(edge_fraction), 5),
        }
    )
    has_transparency_evidence = (
        glass_fraction > 0.12
        and opaque_anchor_fraction < 0.55
        and (opaque_anchor_fraction > 0.006 or edge_fraction > 0.025)
    )
    adjusted = mask.copy()
    if has_transparency_evidence and int(glass_body.sum()) > 80:
        adjusted[glass_body] = np.minimum(adjusted[glass_body], 92)
        highlight = (mask > 20) & (sat < 62) & (val > 185)
        adjusted[highlight] = np.maximum(adjusted[highlight], 126)
        adjusted[edges | dark_or_colored] = np.maximum(adjusted[edges | dark_or_colored], mask[edges | dark_or_colored])
        stats["transparent_alpha_applied"] = True
    return cv2.GaussianBlur(adjusted, (3, 3), 0), stats

def solid_object_alpha(mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    stats = {
        "transparent_alpha_policy": "solid_foreground_opaque_mask",
        "glass_fraction": 0.0,
        "opaque_anchor_fraction": 1.0,
        "edge_fraction": 0.0,
        "transparent_alpha_applied": False,
        "solid_alpha_applied": True,
    }
    if mask.size == 0:
        return mask, stats
    binary = (mask > 20).astype(np.uint8) * 255
    if int((binary > 0).sum()) == 0:
        return mask, stats
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    softened = cv2.GaussianBlur(binary, (3, 3), 0)
    softened[binary == 255] = 255
    return softened, stats
