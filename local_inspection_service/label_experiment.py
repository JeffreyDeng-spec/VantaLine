from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


MAX_SEGMENT_SIDE = 2600
COMPARE_MAX_SIDE = 560
JPEG_QUALITY = 88


@dataclass
class LabelCandidate:
    id: str
    source: str
    image_bgr: np.ndarray
    bbox: tuple[int, int, int, int] | None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())[:96].strip("._")
    return slug or "label_experiment"


def _url_for(output_url_prefix: str, path: Path) -> str:
    return f"{output_url_prefix.rstrip('/')}/{path.name}"


def _write_jpg(path: Path, image_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])


def _resize_limit_bgr(image_bgr: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    h, w = image_bgr.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return image_bgr.copy(), 1.0
    scale = max_side / float(longest)
    resized = cv2.resize(image_bgr, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    return resized, scale


def _border_median_bgr(image_bgr: np.ndarray) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    band = max(4, int(round(min(h, w) * 0.035)))
    samples = np.concatenate(
        [
            image_bgr[:band, :, :].reshape(-1, 3),
            image_bgr[-band:, :, :].reshape(-1, 3),
            image_bgr[:, :band, :].reshape(-1, 3),
            image_bgr[:, -band:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(samples, axis=0).astype(np.float32)


def _content_mask(image_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    border = _border_median_bgr(image_bgr)
    border_gray = float(np.mean(border))
    diff = np.linalg.norm(image_bgr.astype(np.float32) - border.reshape(1, 1, 3), axis=2)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    median = float(np.median(blur))
    lower = int(max(18, 0.55 * median))
    upper = int(min(220, max(lower + 30, 1.35 * median)))
    edges = cv2.Canny(blur, lower, upper)
    if border_gray > 168:
        ink = ((gray < 236) | (sat > 42) | (diff > 28) | (edges > 0)).astype(np.uint8) * 255
    else:
        ink = ((sat > 45) | (diff > 34) | (edges > 0)).astype(np.uint8) * 255
    ink = cv2.medianBlur(ink, 3)
    return ink


def _expand_box(box: tuple[int, int, int, int], pad: int, width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return max(0, x1 - pad), max(0, y1 - pad), min(width, x2 + pad), min(height, y2 + pad)


def _box_area(box: tuple[int, int, int, int]) -> int:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def _merge_boxes(boxes: list[tuple[int, int, int, int]], gap: int) -> list[tuple[int, int, int, int]]:
    merged = list(boxes)
    changed = True
    while changed:
        changed = False
        next_boxes: list[tuple[int, int, int, int]] = []
        used = [False] * len(merged)
        for i, a in enumerate(merged):
            if used[i]:
                continue
            ax1, ay1, ax2, ay2 = a
            current = a
            used[i] = True
            for j in range(i + 1, len(merged)):
                if used[j]:
                    continue
                bx1, by1, bx2, by2 = merged[j]
                gap_x = max(bx1 - ax2, ax1 - bx2, 0)
                gap_y = max(by1 - ay2, ay1 - by2, 0)
                overlap_x = min(ax2, bx2) - max(ax1, bx1)
                overlap_y = min(ay2, by2) - max(ay1, by1)
                nested = (ax1 <= bx1 <= bx2 <= ax2 and ay1 <= by1 <= by2 <= ay2) or (bx1 <= ax1 <= ax2 <= bx2 and by1 <= ay1 <= ay2 <= by2)
                touches = (gap_x <= gap and overlap_y > -gap) and (gap_y <= gap and overlap_x > -gap)
                if nested or touches:
                    current = (min(ax1, bx1), min(ay1, by1), max(ax2, bx2), max(ay2, by2))
                    ax1, ay1, ax2, ay2 = current
                    used[j] = True
                    changed = True
            next_boxes.append(current)
        merged = next_boxes
    return merged


def _boxes_from_mask(mask: np.ndarray, image_shape: tuple[int, int, int]) -> list[tuple[int, int, int, int]]:
    h, w = image_shape[:2]
    min_dim = min(h, w)
    image_area = float(h * w)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw < max(14, int(min_dim * 0.006)) or bh < max(14, int(min_dim * 0.006)):
            continue
        area_ratio = (bw * bh) / image_area
        if area_ratio < 0.00018 or area_ratio > 0.82:
            continue
        aspect = bw / float(max(1, bh))
        if aspect < 0.055 or aspect > 18:
            continue
        contour_area_ratio = cv2.contourArea(contour) / float(max(1, bw * bh))
        if contour_area_ratio < 0.015 and area_ratio < 0.002:
            continue
        boxes.append((x, y, x + bw, y + bh))
    pad = max(5, int(round(min_dim * 0.006)))
    boxes = [_expand_box(box, pad, w, h) for box in boxes]
    boxes = _merge_boxes(boxes, max(3, int(round(min_dim * 0.004))))
    boxes = [box for box in boxes if _box_area(box) / image_area >= 0.00022]
    return sorted(boxes, key=lambda b: (b[1] // max(1, int(h * 0.04)), b[0]))


def _candidate_boxes(image_bgr: np.ndarray, max_labels: int) -> list[tuple[int, int, int, int]]:
    h, w = image_bgr.shape[:2]
    min_dim = min(h, w)
    base = _content_mask(image_bgr)
    best_boxes: list[tuple[int, int, int, int]] = []
    best_score = -1e9
    image_area = float(h * w)
    scales = (0.006, 0.010, 0.016, 0.024, 0.034, 0.048)
    for scale in scales:
        kw = max(9, int(round(min_dim * scale * 1.55)))
        kh = max(7, int(round(min_dim * scale)))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw | 1, kh | 1))
        mask = cv2.morphologyEx(base, cv2.MORPH_CLOSE, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=1)
        boxes = _boxes_from_mask(mask, image_bgr.shape)
        if not boxes:
            continue
        if len(boxes) > max_labels * 2:
            boxes = sorted(boxes, key=_box_area, reverse=True)[: max_labels * 2]
            boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
        ratios = [_box_area(box) / image_area for box in boxes]
        coverage = min(0.85, sum(ratios))
        median_area = float(np.median(ratios)) if ratios else 0.0
        count = len(boxes)
        giant_penalty = 5.0 if count == 1 and ratios[0] > 0.55 else 0.0
        tiny_penalty = sum(1 for ratio in ratios if ratio < 0.0012) * 0.45
        too_many_penalty = max(0, count - max_labels) * 1.8
        count_score = min(count, max_labels) * 1.25
        if count == 1:
            count_score = 0.9
        elif 2 <= count <= max_labels:
            count_score += 3.0
        median_bonus = 2.5 if median_area >= 0.0025 else 0.0
        score = count_score + coverage * 7.0 + median_bonus - giant_penalty - tiny_penalty - too_many_penalty
        if score > best_score:
            best_score = score
            best_boxes = boxes
    if len(best_boxes) > max_labels:
        best_boxes = sorted(best_boxes, key=_box_area, reverse=True)[:max_labels]
        best_boxes = sorted(best_boxes, key=lambda b: (b[1], b[0]))
    return best_boxes


def _union_content_box(image_bgr: np.ndarray) -> tuple[int, int, int, int] | None:
    h, w = image_bgr.shape[:2]
    mask = _content_mask(image_bgr)
    min_dim = min(h, w)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, int(min_dim * 0.006)) | 1, max(5, int(min_dim * 0.006)) | 1))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        if cv2.contourArea(contour) < 12:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        boxes.append((x, y, x + bw, y + bh))
    if not boxes:
        return None
    x1 = min(box[0] for box in boxes)
    y1 = min(box[1] for box in boxes)
    x2 = max(box[2] for box in boxes)
    y2 = max(box[3] for box in boxes)
    return _expand_box((x1, y1, x2, y2), max(6, int(min_dim * 0.025)), w, h)


def crop_to_content_bgr(image_bgr: np.ndarray) -> np.ndarray:
    if image_bgr.size == 0:
        return image_bgr
    box = _union_content_box(image_bgr)
    if box is None:
        return image_bgr.copy()
    h, w = image_bgr.shape[:2]
    x1, y1, x2, y2 = box
    if (x2 - x1) < 12 or (y2 - y1) < 12:
        return image_bgr.copy()
    if (x2 - x1) * (y2 - y1) > 0.96 * w * h:
        return image_bgr.copy()
    return image_bgr[y1:y2, x1:x2].copy()


def segment_label_candidates_bgr(image_bgr: np.ndarray, source: str, max_labels: int = 32) -> tuple[np.ndarray, list[LabelCandidate]]:
    canvas, _ = _resize_limit_bgr(image_bgr, MAX_SEGMENT_SIDE)
    boxes = _candidate_boxes(canvas, max_labels=max_labels)
    candidates: list[LabelCandidate] = []
    for index, box in enumerate(boxes, 1):
        x1, y1, x2, y2 = box
        crop = canvas[y1:y2, x1:x2].copy()
        if crop.size == 0:
            continue
        candidates.append(LabelCandidate(id=f"{source[:1].upper()}{index:02d}", source=source, image_bgr=crop, bbox=box))
    if not candidates:
        candidates.append(LabelCandidate(id=f"{source[:1].upper()}01", source=source, image_bgr=crop_to_content_bgr(canvas), bbox=None))
    return canvas, candidates


def _reference_candidates(image_bgr: np.ndarray) -> tuple[np.ndarray, list[LabelCandidate]]:
    canvas, candidates = segment_label_candidates_bgr(image_bgr, "reference", max_labels=24)
    if len(candidates) <= 1:
        return canvas, [LabelCandidate(id="R01", source="reference", image_bgr=crop_to_content_bgr(canvas), bbox=None)]
    h, w = canvas.shape[:2]
    ratios = [_box_area(candidate.bbox) / float(h * w) for candidate in candidates if candidate.bbox]
    median_ratio = float(np.median(ratios)) if ratios else 0.0
    largest_ratio = max(ratios) if ratios else 0.0
    if median_ratio >= 0.0025 or largest_ratio >= 0.018:
        return canvas, candidates
    return canvas, [LabelCandidate(id="R01", source="reference", image_bgr=crop_to_content_bgr(canvas), bbox=None)]


def _fit_to_size(image_bgr: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    target_w, target_h = size
    if target_w <= 0 or target_h <= 0:
        return image_bgr.copy()
    return cv2.resize(image_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA if image_bgr.shape[1] > target_w else cv2.INTER_CUBIC)


def _normalize_pair(reference_bgr: np.ndarray, sample_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ref = crop_to_content_bgr(reference_bgr)
    sample = crop_to_content_bgr(sample_bgr)
    ref, _ = _resize_limit_bgr(ref, COMPARE_MAX_SIDE)
    h, w = ref.shape[:2]
    sample = _fit_to_size(sample, (w, h))
    return ref, sample


def _ssim_gray(a_gray: np.ndarray, b_gray: np.ndarray) -> float:
    a = a_gray.astype(np.float32)
    b = b_gray.astype(np.float32)
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_a = cv2.GaussianBlur(a, (11, 11), 1.5)
    mu_b = cv2.GaussianBlur(b, (11, 11), 1.5)
    mu_a2 = mu_a * mu_a
    mu_b2 = mu_b * mu_b
    mu_ab = mu_a * mu_b
    sigma_a2 = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu_a2
    sigma_b2 = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu_b2
    sigma_ab = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu_ab
    numerator = (2 * mu_ab + c1) * (2 * sigma_ab + c2)
    denominator = (mu_a2 + mu_b2 + c1) * (sigma_a2 + sigma_b2 + c2)
    value = numerator / np.maximum(denominator, 1e-6)
    return float(_clamp(float(np.mean(value)), 0.0, 1.0))


def _edge_similarity(a_gray: np.ndarray, b_gray: np.ndarray) -> float:
    a_edges = cv2.Canny(cv2.GaussianBlur(a_gray, (3, 3), 0), 55, 150)
    b_edges = cv2.Canny(cv2.GaussianBlur(b_gray, (3, 3), 0), 55, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    a_edges = cv2.dilate(a_edges, kernel, iterations=1) > 0
    b_edges = cv2.dilate(b_edges, kernel, iterations=1) > 0
    union = np.logical_or(a_edges, b_edges).sum()
    if union <= 0:
        return 1.0
    intersection = np.logical_and(a_edges, b_edges).sum()
    return float(intersection / union)


def _diff_overlay(reference_bgr: np.ndarray, sample_bgr: np.ndarray, diff_mask: np.ndarray) -> np.ndarray:
    overlay = sample_bgr.copy()
    red = np.zeros_like(overlay)
    red[:, :] = (30, 30, 235)
    mask = diff_mask > 0
    overlay[mask] = cv2.addWeighted(overlay, 0.38, red, 0.62, 0)[mask]
    separator = np.full((sample_bgr.shape[0], 8, 3), 245, dtype=np.uint8)
    return np.concatenate([reference_bgr, separator, overlay], axis=1)


def _score_pair(reference_bgr: np.ndarray, sample_bgr: np.ndarray, sensitivity: float) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    ref, sample = _normalize_pair(reference_bgr, sample_bgr)
    ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    sample_gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    ssim = _ssim_gray(ref_gray, sample_gray)
    diff = cv2.absdiff(ref_gray, sample_gray)
    threshold = int(round(34 - 16 * sensitivity))
    diff_mask = (diff > max(14, threshold)).astype(np.uint8) * 255
    diff_mask = cv2.medianBlur(diff_mask, 3)
    contours, _ = cv2.findContours(diff_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total_area = float(max(1, diff_mask.shape[0] * diff_mask.shape[1]))
    diff_ratio = float(np.count_nonzero(diff_mask) / total_area)
    largest_change_ratio = 0.0
    if contours:
        largest_change_ratio = max(float(cv2.contourArea(contour)) for contour in contours) / total_area
    edge_sim = _edge_similarity(ref_gray, sample_gray)
    diff_similarity = _clamp(1.0 - diff_ratio * (6.0 + 4.0 * sensitivity), 0.0, 1.0)
    score = _clamp(0.62 * ssim + 0.24 * diff_similarity + 0.14 * edge_sim, 0.0, 1.0)
    pass_score = 0.86 + 0.08 * sensitivity
    review_score = 0.75 + 0.10 * sensitivity
    hard_diff = 0.072 - 0.040 * sensitivity
    hard_largest = 0.021 - 0.012 * sensitivity
    pass_diff = 0.0009 + (1.0 - sensitivity) * 0.0010
    pass_largest = 0.0012 + (1.0 - sensitivity) * 0.0014
    pass_edge = 0.980 - (1.0 - sensitivity) * 0.018
    tiny_change = 0.00045 + (1.0 - sensitivity) * 0.00045
    if min(ref.shape[:2]) < 18 or min(sample.shape[:2]) < 18:
        status = "unknown"
        reason = "候选区域过小，无法稳定比较。"
    elif score >= pass_score and diff_ratio < pass_diff and largest_change_ratio < pass_largest and edge_sim >= pass_edge:
        status = "pass"
        reason = "与标准标签高度匹配。"
    elif score < review_score or diff_ratio > hard_diff or largest_change_ratio > hard_largest:
        status = "fail"
        reason = "与标准标签存在明显图案或文字差异。"
    elif diff_ratio > tiny_change or edge_sim < pass_edge:
        status = "review"
        reason = "发现局部差异，建议复核标点、R 标、符号或小字。"
    else:
        status = "pass"
        reason = "与标准标签匹配。"
    metrics = {
        "score": round(score, 4),
        "ssim": round(ssim, 4),
        "diff_ratio": round(diff_ratio, 5),
        "edge_similarity": round(edge_sim, 4),
        "largest_change_ratio": round(largest_change_ratio, 5),
        "status": status,
        "reason": reason,
    }
    return metrics, sample, _diff_overlay(ref, sample, diff_mask)


def compare_candidate_to_reference(candidate_bgr: np.ndarray, reference_bgr: np.ndarray, sensitivity: float) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    variants = [("0", candidate_bgr)]
    h, w = candidate_bgr.shape[:2]
    if h > 0 and w > 0:
        ref_h, ref_w = reference_bgr.shape[:2]
        candidate_aspect = w / float(h)
        reference_aspect = ref_w / float(max(1, ref_h))
        if candidate_aspect > 0 and reference_aspect > 0:
            rotated_aspect = h / float(w)
            if abs(math.log(rotated_aspect / reference_aspect)) + 0.08 < abs(math.log(candidate_aspect / reference_aspect)):
                variants.append(("90", cv2.rotate(candidate_bgr, cv2.ROTATE_90_CLOCKWISE)))
                variants.append(("270", cv2.rotate(candidate_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)))
    best: tuple[dict[str, Any], np.ndarray, np.ndarray] | None = None
    for rotation, variant in variants:
        metrics, aligned, diff = _score_pair(reference_bgr, variant, sensitivity)
        if rotation != "0":
            metrics = dict(metrics)
            metrics["rotation"] = rotation
        if best is None or metrics["score"] > best[0]["score"]:
            best = (metrics, aligned, diff)
    assert best is not None
    return best


def _bbox_payload(candidate: LabelCandidate) -> dict[str, int] | None:
    if candidate.bbox is None:
        return None
    x1, y1, x2, y2 = candidate.bbox
    return {"x": int(x1), "y": int(y1), "width": int(x2 - x1), "height": int(y2 - y1)}


def _bbox_text(candidate: LabelCandidate) -> str:
    box = _bbox_payload(candidate)
    if not box:
        return "整图候选"
    return f"x={box['x']}, y={box['y']}, w={box['width']}, h={box['height']}"


def draw_split_overlay(image_bgr: np.ndarray, candidates: list[LabelCandidate], title: str) -> np.ndarray:
    canvas = image_bgr.copy()
    h, w = canvas.shape[:2]
    thickness = max(2, int(round(min(h, w) / 500)))
    for candidate in candidates:
        if candidate.bbox is None:
            x1, y1, x2, y2 = 0, 0, w - 1, h - 1
        else:
            x1, y1, x2, y2 = candidate.bbox
        color = (42, 150, 45) if candidate.source == "incoming" else (214, 132, 32)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
        label = candidate.id
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.55, min(1.1, min(h, w) / 1200))
        (tw, th), _ = cv2.getTextSize(label, font, font_scale, max(1, thickness))
        tx = max(0, min(x1, w - tw - 12))
        ty = max(th + 8, y1)
        cv2.rectangle(canvas, (tx, ty - th - 8), (tx + tw + 12, ty + 6), (18, 20, 22), -1)
        cv2.putText(canvas, label, (tx + 6, ty), font, font_scale, (255, 255, 255), max(1, thickness), cv2.LINE_AA)
    cv2.putText(canvas, title, (14, max(28, int(h * 0.025))), cv2.FONT_HERSHEY_SIMPLEX, max(0.65, min(1.2, min(h, w) / 1100)), (18, 20, 22), max(2, thickness), cv2.LINE_AA)
    return canvas


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pass": 0, "review": 0, "fail": 0, "unknown": 0}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status if status in counts else "unknown"] += 1
    return counts


def run_label_experiment(
    reference_bgr: np.ndarray,
    incoming_bgr: np.ndarray,
    output_dir: Path,
    request_id: str,
    sensitivity: float = 0.72,
    output_url_prefix: str = "/outputs",
) -> dict[str, Any]:
    sensitivity = _clamp(float(sensitivity), 0.0, 1.0)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = _safe_slug(f"label_exp_{request_id}_{uuid.uuid4().hex[:8]}")

    reference_canvas, reference_candidates = _reference_candidates(reference_bgr)
    incoming_canvas, incoming_candidates = segment_label_candidates_bgr(incoming_bgr, "incoming", max_labels=32)

    reference_path = output_dir / f"{prefix}_reference.jpg"
    incoming_path = output_dir / f"{prefix}_incoming.jpg"
    reference_overlay_path = output_dir / f"{prefix}_reference_split.jpg"
    incoming_overlay_path = output_dir / f"{prefix}_incoming_split.jpg"
    _write_jpg(reference_path, reference_canvas)
    _write_jpg(incoming_path, incoming_canvas)
    _write_jpg(reference_overlay_path, draw_split_overlay(reference_canvas, reference_candidates, "standard candidates"))
    _write_jpg(incoming_overlay_path, draw_split_overlay(incoming_canvas, incoming_candidates, "incoming split candidates"))

    references_payload: list[dict[str, Any]] = []
    for ref in reference_candidates:
        ref_path = output_dir / f"{prefix}_{ref.id.lower()}_reference_crop.jpg"
        _write_jpg(ref_path, ref.image_bgr)
        references_payload.append(
            {
                "id": ref.id,
                "crop_url": _url_for(output_url_prefix, ref_path),
                "bbox": _bbox_payload(ref),
                "bbox_text": _bbox_text(ref),
            }
        )

    reference_best: dict[str, dict[str, Any]] = {
        ref.id: {"score": 0.0, "incoming_id": "", "status": "missing"} for ref in reference_candidates
    }
    items: list[dict[str, Any]] = []
    for candidate in incoming_candidates:
        best_ref: LabelCandidate | None = None
        best_metrics: dict[str, Any] | None = None
        best_aligned: np.ndarray | None = None
        best_diff: np.ndarray | None = None
        for ref in reference_candidates:
            metrics, aligned, diff = compare_candidate_to_reference(candidate.image_bgr, ref.image_bgr, sensitivity)
            current = reference_best[ref.id]
            if metrics["score"] > float(current["score"]):
                current.update({"score": metrics["score"], "incoming_id": candidate.id, "status": metrics["status"]})
            if best_metrics is None or metrics["score"] > best_metrics["score"]:
                best_ref = ref
                best_metrics = metrics
                best_aligned = aligned
                best_diff = diff
        assert best_ref is not None and best_metrics is not None and best_aligned is not None and best_diff is not None
        crop_path = output_dir / f"{prefix}_{candidate.id.lower()}_incoming_crop.jpg"
        aligned_path = output_dir / f"{prefix}_{candidate.id.lower()}_aligned.jpg"
        diff_path = output_dir / f"{prefix}_{candidate.id.lower()}_diff.jpg"
        _write_jpg(crop_path, candidate.image_bgr)
        _write_jpg(aligned_path, best_aligned)
        _write_jpg(diff_path, best_diff)
        items.append(
            {
                "id": candidate.id,
                "status": best_metrics["status"],
                "score": best_metrics["score"],
                "reason": best_metrics["reason"],
                "reference_id": best_ref.id,
                "reference_url": next((item["crop_url"] for item in references_payload if item["id"] == best_ref.id), ""),
                "bbox": _bbox_payload(candidate),
                "bbox_text": _bbox_text(candidate),
                "candidate_url": _url_for(output_url_prefix, crop_path),
                "aligned_url": _url_for(output_url_prefix, aligned_path),
                "diff_url": _url_for(output_url_prefix, diff_path),
                "metrics": best_metrics,
            }
        )

    pass_score = 0.86 + 0.08 * sensitivity
    missing_references: list[dict[str, Any]] = []
    for ref in reference_candidates:
        best = reference_best[ref.id]
        if float(best["score"]) < pass_score:
            missing_references.append(
                {
                    "reference_id": ref.id,
                    "best_incoming_id": best["incoming_id"],
                    "best_score": round(float(best["score"]), 4),
                    "status": "missing" if not best["incoming_id"] else "not_confirmed",
                }
            )

    counts = _status_counts(items)
    split_count = sum(1 for item in incoming_candidates if item.bbox is not None)
    if counts["fail"] > 0 or missing_references:
        result_status = "fail"
    elif counts["review"] > 0 or counts["unknown"] > 0:
        result_status = "review"
    else:
        result_status = "pass"

    return {
        "status": result_status,
        "request_id": prefix,
        "sensitivity": round(sensitivity, 3),
        "reference_count": len(reference_candidates),
        "incoming_candidate_count": len(incoming_candidates),
        "split_count": split_count,
        "reference_url": _url_for(output_url_prefix, reference_path),
        "incoming_url": _url_for(output_url_prefix, incoming_path),
        "reference_overlay_url": _url_for(output_url_prefix, reference_overlay_path),
        "incoming_overlay_url": _url_for(output_url_prefix, incoming_overlay_path),
        "references": references_payload,
        "items": items,
        "missing_references": missing_references,
        "summary": {
            **counts,
            "missing": len(missing_references),
            "total_candidates": len(incoming_candidates),
            "total_references": len(reference_candidates),
        },
    }
