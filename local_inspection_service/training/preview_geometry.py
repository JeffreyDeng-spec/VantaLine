"""Pure preview geometry with the existing rounding and intersection conventions."""
import math
import cv2


def constrained_center_range(axis_min: int, axis_max: int, half_extent: int) -> tuple[int, int]:
    low = int(axis_min) + int(half_extent)
    high = int(axis_max) - int(half_extent)
    if low <= high:
        return low, high
    center = int(round((int(axis_min) + int(axis_max)) / 2))
    return center, center


def rotated_rect_tuple(
    center: tuple[int, int],
    target_size: tuple[int, int],
    angle: float,
) -> tuple[tuple[float, float], tuple[float, float], float]:
    return (
        (float(center[0]), float(center[1])),
        (max(1.0, float(target_size[0])), max(1.0, float(target_size[1]))),
        float(angle),
    )


def rotated_rect_overlap_area(
    a: tuple[tuple[float, float], tuple[float, float], float],
    b: tuple[tuple[float, float], tuple[float, float], float],
) -> float:
    status, points = cv2.rotatedRectangleIntersection(a, b)
    if status == cv2.INTERSECT_NONE or points is None:
        return 0.0
    return abs(float(cv2.contourArea(points)))


def polygon_max_pair_distance_px(polygon: list[list[int]] | None) -> float:
    if not polygon:
        return 0.0
    best = 0.0
    for index, point_a in enumerate(polygon):
        for point_b in polygon[index + 1 :]:
            best = max(
                best,
                math.hypot(float(point_a[0]) - float(point_b[0]), float(point_a[1]) - float(point_b[1])),
            )
    return best
