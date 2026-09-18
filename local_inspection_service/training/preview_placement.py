"""Preview placement search; callbacks preserve the existing late-bound call chain."""
from collections.abc import Callable
from typing import Any
import cv2
import numpy as np

Point = tuple[int, int]
Size = tuple[int, int]
Region = tuple[int, int, int, int]
Rectangle = tuple[tuple[float, float], tuple[float, float], float]
PlacedObjects = list[dict[str, Any]]


class PreviewPlacement:
    def __init__(self, canvas: Callable[[], Size],
                 constrained: Callable[[], Callable[[int, int, int], tuple[int, int]]],
                 rectangle: Callable[[Point, Size, float], Rectangle],
                 intersection: Callable[[], Callable[[Rectangle, Rectangle], float]],
                 random_center: Callable[[np.random.Generator, Size, float, Region], Point],
                 overlap: Callable[[Point, Size, float, PlacedObjects], float]):
        self.canvas, self.constrained = canvas, constrained
        self.rectangle, self.intersection = rectangle, intersection
        self.random_center, self.overlap = random_center, overlap

    def random_center_inside_background(self,
        rng: np.random.Generator,
        target_size: tuple[int, int],
        angle: float,
        roi: tuple[int, int, int, int],
    ) -> tuple[int, int]:
        target_w, target_h = target_size
        radians = np.deg2rad(angle)
        cos_a = abs(float(np.cos(radians)))
        sin_a = abs(float(np.sin(radians)))
        half_w = int(np.ceil((target_w * cos_a + target_h * sin_a) / 2)) + 12
        half_h = int(np.ceil((target_w * sin_a + target_h * cos_a) / 2)) + 12
        x1, y1, x2, y2 = roi
        min_x, max_x = x1 + half_w, x2 - half_w
        min_y, max_y = y1 + half_h, y2 - half_h
        if min_x >= max_x:
            min_x, max_x = self.constrained()(0, self.canvas()[0], half_w)
        if min_y >= max_y:
            min_y, max_y = self.constrained()(0, self.canvas()[1], half_h)
        return (int(rng.integers(min_x, max_x + 1)), int(rng.integers(min_y, max_y + 1)))

    def object_placement_overlap_area(self,
        center: tuple[int, int],
        target_size: tuple[int, int],
        angle: float,
        placed_objects: list[dict[str, Any]],
    ) -> float:
        candidate = self.rectangle(center, target_size, angle)
        total = 0.0
        for placed in placed_objects:
            total += self.intersection()(candidate, placed["rect"])
        return total

    def choose_object_center_inside_background(self,
        rng: np.random.Generator,
        target_size: tuple[int, int],
        angle: float,
        placed_objects: list[dict[str, Any]],
        roi: tuple[int, int, int, int],
    ) -> tuple[tuple[int, int], dict[str, Any]]:
        best_center = self.random_center(rng, target_size, angle, roi)
        best_overlap = self.overlap(best_center, target_size, angle, placed_objects)
        attempts = 1
        if best_overlap <= 0.5:
            return best_center, {"object_non_overlap_attempts": attempts, "object_overlap_area_px": 0.0, "object_non_overlap_pass": True}
        for attempts in range(2, 181):
            center = self.random_center(rng, target_size, angle, roi)
            overlap = self.overlap(center, target_size, angle, placed_objects)
            if overlap < best_overlap:
                best_center = center
                best_overlap = overlap
            if overlap <= 0.5:
                return center, {"object_non_overlap_attempts": attempts, "object_overlap_area_px": 0.0, "object_non_overlap_pass": True}
        return best_center, {
            "object_non_overlap_attempts": attempts,
            "object_overlap_area_px": round(float(best_overlap), 3),
            "object_non_overlap_pass": bool(best_overlap <= 0.5),
        }

    def placement_box_points(self, center: tuple[int, int], target_size: tuple[int, int], angle: float) -> list[list[int]]:
        points = cv2.boxPoints(self.rectangle(center, target_size, angle))
        return [[int(round(x)), int(round(y))] for x, y in points.tolist()]
