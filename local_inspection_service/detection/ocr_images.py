"""Original masked crops, quarter turns and bounded OCR image resizing."""
from typing import Any
import cv2
import numpy as np


def rotate_quarter_turn(image_bgr: np.ndarray, angle: int) -> np.ndarray:
    normalized = int(angle) % 360
    if normalized == 0:
        return image_bgr
    if normalized == 90:
        return cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE)
    if normalized == 180:
        return cv2.rotate(image_bgr, cv2.ROTATE_180)
    if normalized == 270:
        return cv2.rotate(image_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"angle must be a quarter turn, got {angle}")


def resize_for_ocr(crop_bgr: np.ndarray, max_long_side: int) -> np.ndarray:
    if max_long_side <= 0:
        return crop_bgr
    height, width = crop_bgr.shape[:2]
    long_side = max(height, width)
    if long_side <= max_long_side:
        return crop_bgr
    scale = max_long_side / long_side
    return cv2.resize(
        crop_bgr,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def crop_detection_region(
    image_bgr: np.ndarray,
    polygon: list[list[float]],
    padding: int = 20,
    max_long_side: int = 750,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    height, width = image_bgr.shape[:2]
    pts = np.array(polygon, dtype=np.float32)
    if len(pts) < 3:
        return None
    x1 = max(0, int(np.floor(pts[:, 0].min())) - padding)
    y1 = max(0, int(np.floor(pts[:, 1].min())) - padding)
    x2 = min(width, int(np.ceil(pts[:, 0].max())) + padding)
    y2 = min(height, int(np.ceil(pts[:, 1].max())) + padding)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = image_bgr[y1:y2, x1:x2]
    shifted = pts.copy()
    shifted[:, 0] -= x1
    shifted[:, 1] -= y1
    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [np.round(shifted).astype(np.int32)], 255)
    white = np.full_like(crop, 255)
    masked = np.where(mask[:, :, None] > 0, crop, white)

    rect = cv2.minAreaRect(shifted)
    rect_width, rect_height = rect[1]
    long_edge_angle = 0.0
    if rect_width > 0 and rect_height > 0:
        box = cv2.boxPoints(rect)
        edges = []
        for idx in range(4):
            p1 = box[idx]
            p2 = box[(idx + 1) % 4]
            vector = p2 - p1
            length = float(np.linalg.norm(vector))
            angle = float(np.degrees(np.arctan2(vector[1], vector[0])))
            edges.append((length, angle))
        long_edge_angle = max(edges, key=lambda item: item[0])[1]

    # Manuals are portrait documents. Rotate to make the long edge vertical,
    # using only a single quarter-turn before the default OCR pass.
    correction = int(round((90.0 - long_edge_angle) / 90.0) * 90) % 360
    if correction == 0 and 35.0 <= abs(long_edge_angle) <= 75.0:
        correction = 180
    oriented = rotate_quarter_turn(masked, correction)
    oriented = resize_for_ocr(oriented, max_long_side)
    return oriented, {
        "long_edge_angle": round(long_edge_angle, 2),
        "predicted_rotation": correction,
        "fallback_rotations": [(correction + 180) % 360],
    }
