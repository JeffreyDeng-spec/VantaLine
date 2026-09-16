"""Deterministic, bounded black-label quality gate. Analysis never edits input bytes."""

import io
import time
import cv2
import numpy as np
from PIL import Image
from ..codex_compare.contracts import digest

VERSION = "black-label-quality-v1"
# Release-owned configuration: freeze this hash at submission; no browser override.
CONFIG = {
    "detection_edge": 1000,
    "score_edge": 300,
    "min_area_ratio": 0.015,
    "min_fill": 0.70,
    "min_solidity": 0.90,
    "min_contrast": 20,
    "min_short_side": 200,
    "min_focus": 1000,
    "max_candidates": 16,
    "min_active_blocks": 4,
    "block_std": 8,
    "inset": 0.08,
}
POLICY = {"version": VERSION, "config_hash": digest(CONFIG)}
MESSAGES = {
    "QUALITY_UNLOCATABLE": "无法可靠确定标签范围，请将标签完整拍入画面并调整拍摄角度",
    "QUALITY_TOO_SMALL": "标签有效像素不足，请靠近标签重新拍摄",
    "QUALITY_BLURRED": "标签文字整体不够清晰，请重新对焦并保持相机稳定后拍摄",
    "QUALITY_UNASSESSABLE": "无法可靠评估标签清晰度，请调整光线和拍摄角度后重拍",
    "QUALITY_TARGET_UNCERTAIN": "无法确认模型选中的标签范围，请单独拍摄该标签",
    "QUALITY_SELECTED_REJECTED": "模型选中的标签不够清晰，请单独拍摄该标签",
    "QUALITY_POLICY_CHANGED": "照片质量规则已更新，请重新提交检测",
    "QUALITY_UNAVAILABLE": "照片质量检查不可用，本次未完成比对，请稍后重新检测",
}


class Rejected(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES[code])


def _decode(data):
    with Image.open(io.BytesIO(data)) as im:
        return np.array(im.convert("RGB"))


def _resize(a, edge):
    h, w = a.shape[:2]
    scale = min(1.0, edge / max(h, w))
    return (
        cv2.resize(
            a, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA
        ),
        scale,
    )


def _score(gray, mask, box, native_scale):
    x, y, w, h = box
    roi = gray[y : y + h, x : x + w]
    inside = mask[y : y + h, x : x + w]
    roi, scale = _resize(roi, CONFIG["score_edge"])
    inside = cv2.resize(
        inside, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST
    )
    margin = max(2, round(min(roi.shape) * CONFIG["inset"]))
    inside = cv2.erode(inside, np.ones((margin * 2 + 1, margin * 2 + 1), np.uint8)) > 0
    lap = cv2.Laplacian(roi, cv2.CV_64F)
    values = []
    for row in range(4):
        for col in range(4):
            yy = slice(row * roi.shape[0] // 4, (row + 1) * roi.shape[0] // 4)
            xx = slice(col * roi.shape[1] // 4, (col + 1) * roi.shape[1] // 4)
            valid = inside[yy, xx]
            if valid.size == 0 or valid.mean() < 0.45:
                continue
            pixels = roi[yy, xx][valid]
            if pixels.std() < CONFIG["block_std"]:
                continue
            values.append(float(lap[yy, xx][valid].var()))
    pixels = roi[inside]
    overall = float(lap[inside].var()) if pixels.size else 0.0
    median = float(np.median(values)) if values else 0.0
    metrics = {
        "focus": round(overall, 2),
        "block_median": round(median, 2),
        "active_blocks": len(values),
        "block_scores": [round(v, 2) for v in values],
        "weak_fraction": (
            round(sum(v < CONFIG["min_focus"] for v in values) / len(values), 3)
            if values
            else None
        ),
        "dark_fraction": round(float((pixels < 10).mean()), 3) if pixels.size else None,
        "bright_fraction": (
            round(float((pixels > 245).mean()), 3) if pixels.size else None
        ),
        "native_box_size": [round(w * native_scale), round(h * native_scale)],
    }
    return metrics


def inspect(data, native_size=None):
    """Inspect exact prepared JPEG copy, return candidate coordinates in [x,y,w,h]."""
    started = time.monotonic()
    rgb = _decode(data)
    height, width = rgb.shape[:2]
    reduced, scale = _resize(rgb, CONFIG["detection_edge"])
    gray = cv2.cvtColor(reduced, cv2.COLOR_RGB2GRAY)
    _, mask = cv2.threshold(
        cv2.GaussianBlur(gray, (5, 5), 0),
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    gh, gw = gray.shape
    native_scale = (native_size[0] / width if native_size else 1.0) / scale
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < gh * gw * CONFIG["min_area_ratio"]:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        rect = cv2.minAreaRect(contour)
        rw, rh = rect[1]
        if not min(rw, rh) or not 0.2 <= rw / rh <= 5:
            continue
        if (
            area / (rw * rh) < CONFIG["min_fill"]
            or area / max(1, cv2.contourArea(cv2.convexHull(contour)))
            < CONFIG["min_solidity"]
        ):
            continue
        # Border-touching shapes are not reliable complete labels.
        if x < 2 or y < 2 or x + w > gw - 2 or y + h > gh - 2:
            continue
        region = np.zeros_like(gray)
        cv2.drawContours(region, [contour], -1, 255, -1)
        ring = (cv2.dilate(region, np.ones((17, 17), np.uint8)) > 0) & (region == 0)
        if (
            not ring.any()
            or float(np.median(gray[ring])) - float(np.median(gray[region > 0]))
            < CONFIG["min_contrast"]
        ):
            continue
        metrics = _score(gray, region, (x, y, w, h), native_scale)
        # Native and model-view short sides: enlarging a tiny source must not rescue it.
        short = min(rw, rh) / scale
        metrics["input_short_side"] = round(short, 1)
        metrics["native_short_side"] = round(min(rw, rh) * native_scale, 1)
        code = None
        if min(short, metrics["native_short_side"]) < CONFIG["min_short_side"]:
            code = "QUALITY_TOO_SMALL"
        elif metrics["active_blocks"] < CONFIG["min_active_blocks"]:
            code = "QUALITY_UNASSESSABLE"
        elif max(metrics["focus"], metrics["block_median"]) < CONFIG["min_focus"]:
            code = "QUALITY_BLURRED"
        candidates.append(
            {
                "box": [
                    round(x / gw, 6),
                    round(y / gh, 6),
                    round(w / gw, 6),
                    round(h / gh, 6),
                ],
                "passed": code is None,
                "code": code,
                "metrics": metrics,
            }
        )
        if len(candidates) > CONFIG["max_candidates"]:
            break
    overflow = len(candidates) > CONFIG["max_candidates"]
    passed = not overflow and any(c["passed"] for c in candidates)
    reason = (
        None
        if passed
        else (
            "QUALITY_UNLOCATABLE"
            if not candidates or overflow
            else candidates[0]["code"]
        )
    )
    return {
        "passed": passed,
        "code": reason,
        "candidates": candidates[: CONFIG["max_candidates"]],
        "input_size": [width, height],
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
    }


def selected(preflight, crop, actual_size):
    """Require one complete, unambiguous candidate in the model's selected extent."""
    rows = preflight["candidates"]
    if not crop:
        return rows[0] if len(rows) == 1 else None
    width, height = actual_size
    x, y, w, h = [v / d for v, d in zip(crop, (width, height, width, height))]
    overlaps = []
    for candidate in rows:
        a, b, c, d = candidate["box"]
        area = max(0, min(x + w, a + c) - max(x, a)) * max(
            0, min(y + h, b + d) - max(y, b)
        )
        if area / (c * d) > 0.10:
            overlaps.append((candidate, area / (c * d)))
    if len(overlaps) != 1 or overlaps[0][1] < 0.90:
        return None
    return overlaps[0][0]


def recheck(data, candidate, crop, actual_size):
    """Measure the selected candidate inside the unchanged second-call JPEG."""
    started = time.monotonic()
    rgb = _decode(data)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    a, b, c, d = candidate["box"]
    ow, oh = actual_size
    x, y, w, h = crop
    sx, sy = gray.shape[1] / w, gray.shape[0] / h
    left, top = max(0, round((a * ow - x) * sx)), max(0, round((b * oh - y) * sy))
    right, bottom = min(gray.shape[1], round(((a + c) * ow - x) * sx)), min(
        gray.shape[0], round(((b + d) * oh - y) * sy)
    )
    if right <= left or bottom <= top:
        return {"passed": False, "code": "QUALITY_TARGET_UNCERTAIN", "elapsed_ms": 0}
    mask = np.zeros_like(gray)
    mask[top:bottom, left:right] = 255
    metrics = _score(gray, mask, (left, top, right - left, bottom - top), 1 / sx)
    passed = (
        metrics["active_blocks"] >= CONFIG["min_active_blocks"]
        and max(metrics["focus"], metrics["block_median"]) >= CONFIG["min_focus"]
    )
    return {
        "passed": passed,
        "metrics": metrics,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
    }
