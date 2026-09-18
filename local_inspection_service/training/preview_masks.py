"""Preview mask conversion and explicitly composed visible-contour filtering."""
from collections.abc import Callable
import cv2
import numpy as np

Polygon = list[list[int]]


def mask_from_polygon(shape: tuple[int, int], polygon: list[list[int]]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    points = np.array(polygon or [], dtype=np.int32)
    if len(points) >= 3:
        cv2.fillPoly(mask, [points], 255)
    return mask


def contour_to_polygon(contour: np.ndarray, shape: tuple[int, int], epsilon_ratio: float = 0.0035) -> list[list[int]]:
    epsilon = max(1.0, cv2.arcLength(contour, True) * epsilon_ratio)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    if len(approx) < 3:
        rect = cv2.minAreaRect(contour)
        approx = cv2.boxPoints(rect).astype(np.int32).reshape(-1, 1, 2)
    height, width = shape[:2]
    points: list[list[int]] = []
    for point in approx.reshape(-1, 2):
        x = int(np.clip(point[0], 0, width - 1))
        y = int(np.clip(point[1], 0, height - 1))
        if not points or points[-1] != [x, y]:
            points.append([x, y])
    if len(points) > 2 and points[0] == points[-1]:
        points.pop()
    return points if len(points) >= 3 else []


class PreviewMasks:
    def __init__(self, contour: Callable[[], Callable[[np.ndarray, tuple[int, int], float], Polygon]],
                 polygons: Callable[[np.ndarray, float], list[Polygon]]):
        self.contour, self.polygons = contour, polygons

    def visible_polygons_from_mask(self, mask: np.ndarray, epsilon_ratio: float = 0.0035) -> list[list[list[int]]]:
        if mask is None or mask.size == 0:
            return []
        binary = (mask > 24).astype(np.uint8) * 255
        if int(cv2.countNonZero(binary)) < 12:
            return []
        kernel = np.ones((3, 3), dtype=np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        max_area = max(float(cv2.contourArea(contour)) for contour in contours)
        polygons = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < 12 or area < max_area * 0.015:
                continue
            polygon = self.contour()(contour, binary.shape, epsilon_ratio)
            if polygon:
                polygons.append(polygon)
        return polygons

    def visible_polygon_from_mask(self, mask: np.ndarray, epsilon_ratio: float = 0.0035) -> list[list[int]]:
        polygons = self.polygons(mask, epsilon_ratio)
        return polygons[0] if polygons else []
