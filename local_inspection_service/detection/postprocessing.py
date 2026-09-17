"""Original confidence/area filtering and stable detection deduplication."""
from typing import Any
from .geometry import polygon_area, polygon_bbox, bbox_overlap_ratio, bbox_gap


def filter_detections(
    detections: list[dict[str, Any]],
    image_shape: tuple[int, int],
    spec: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    height, width = image_shape
    image_area = max(height * width, 1)
    is_specialized = bool((spec or {}).get("is_specialized"))
    try:
        specialized_threshold = max(0.001, min(0.99, float((spec or {}).get("confidence_threshold", 0.25))))
    except (TypeError, ValueError):
        specialized_threshold = 0.25
    filtered = []
    for det in detections:
        area = polygon_area(det["polygon"])
        det["area_px"] = round(area, 2)
        cls_id = int(det["class_id"])
        confidence = float(det["confidence"])
        area_ratio = area / image_area
        if is_specialized:
            if confidence < specialized_threshold or area_ratio < 0.0005:
                continue
            filtered.append(det)
            continue
        if cls_id == 0 and (
            confidence < 0.55
            or area_ratio < 0.0015
            or (area_ratio < 0.003 and confidence < 0.85)
        ):
            continue
        if cls_id in (1, 2, 3, 4, 99) and (confidence < 0.30 or area_ratio < 0.006):
            continue
        filtered.append(det)
    return filtered


def dedupe_detections(
    detections: list[dict[str, Any]],
    overlap_threshold: float = 0.08,
    adjacent_gap_px: float = 42.0,
    absorb_area_ratio: float = 0.22,
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for det in sorted(detections, key=lambda item: float(item["confidence"]), reverse=True):
        cls_id = int(det["class_id"])
        det_area = polygon_area(det["polygon"])
        det_bbox = polygon_bbox(det["polygon"])
        duplicate = False
        for other in kept:
            if int(other["class_id"]) != cls_id:
                continue
            other_area = polygon_area(other["polygon"])
            other_bbox = polygon_bbox(other["polygon"])
            min_area = max(min(det_area, other_area), 1)
            max_area = max(det_area, other_area, 1)
            overlap = bbox_overlap_ratio(det_bbox, other_bbox)
            close = bbox_gap(det_bbox, other_bbox) <= adjacent_gap_px
            small_fragment = min_area / max_area <= absorb_area_ratio
            near_small_fragment = cls_id == 1 and small_fragment and (overlap >= overlap_threshold or close)
            low_conf_adjacent_manual = (
                cls_id == 1
                and close
                and max(det_area, other_area) < 250000
                and float(det["confidence"]) < 0.55
                and float(other["confidence"]) < 0.55
            )
            strong_overlap_duplicate = overlap >= 0.85
            near_duplicate = small_fragment and overlap >= 0.65
            if strong_overlap_duplicate or near_small_fragment or low_conf_adjacent_manual or near_duplicate:
                duplicate = True
                break
        if not duplicate:
            kept.append(det)
    return kept


def postprocess_detections(
    detections: list[dict[str, Any]],
    image_shape: tuple[int, int],
    spec: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return dedupe_detections(filter_detections(detections, image_shape, spec))
