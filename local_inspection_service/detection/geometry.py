"""Original polygon and bounding-box measurements, without implicit normalization."""
import cv2
import numpy as np


def polygon_overlap_ratio(poly_a: list[list[float]], poly_b: list[list[float]]) -> float:
    pts_a = np.array(poly_a, dtype=np.float32)
    pts_b = np.array(poly_b, dtype=np.float32)
    area_a = float(cv2.contourArea(pts_a))
    area_b = float(cv2.contourArea(pts_b))
    if area_a <= 0 or area_b <= 0:
        return 0.0
    intersection_area, _ = cv2.intersectConvexConvex(pts_a, pts_b)
    return float(intersection_area) / min(area_a, area_b)


def polygon_area(poly: list[list[float]]) -> float:
    return abs(float(cv2.contourArea(np.array(poly, dtype=np.float32))))


def polygon_bbox(poly: list[list[float]]) -> tuple[float, float, float, float]:
    pts = np.array(poly, dtype=np.float32)
    xs = pts[:, 0]
    ys = pts[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def bbox_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = max(bx1 - ax2, ax1 - bx2, 0)
    dy = max(by1 - ay2, ay1 - by2, 0)
    return float((dx * dx + dy * dy) ** 0.5)


def bbox_overlap_ratio(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(ix2 - ix1, 0), max(iy2 - iy1, 0)
    inter = iw * ih
    area_a = max((ax2 - ax1) * (ay2 - ay1), 1)
    area_b = max((bx2 - bx1) * (by2 - by1), 1)
    return float(inter / min(area_a, area_b))


def bbox_iou_xyxy(a: list[int], b: list[int]) -> float:
    if len(a) < 4 or len(b) < 4:
        return 0.0
    ax1, ay1, ax2, ay2 = [int(value) for value in a[:4]]
    bx1, by1, bx2, by2 = [int(value) for value in b[:4]]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return float(inter) / float(union) if union > 0 else 0.0
