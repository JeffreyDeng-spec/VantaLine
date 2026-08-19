"""Fail-closed package-label text inspection primitives.

This module deliberately keeps case and punctuation.  It never imports or
calls the legacy ``normalize_ocr_text`` helper used by accessory matching.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

import cv2
import numpy as np


PASS = "PASS"
FAIL = "FAIL"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
DECISIONS = frozenset({PASS, FAIL, REVIEW_REQUIRED})
MAX_REGEX_LENGTH = 160
MAX_EXACT_LENGTH = 500
MIN_AUTOMATIC_CONFIDENCE = 0.90
MIN_CRITICAL_MISMATCH_CONFIDENCE = 0.96


class IncomingTextValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TextObservation:
    text: str
    confidence: float
    polygon: tuple[tuple[float, float], ...] = ()
    corroborated: bool = False


def exact_text(value: Any, *, case_sensitive: bool = True) -> str:
    """Only NFC-normalize; do not trim, casefold or collapse punctuation."""
    text = unicodedata.normalize("NFC", str(value if value is not None else ""))
    return text if case_sensitive else text.casefold()


def comparison_text(value: Any, rule: dict[str, Any]) -> str:
    text = exact_text(value, case_sensitive=rule.get("case_sensitive", True))
    return re.sub(r"\s+", "", text) if rule.get("ignore_whitespace", False) else text


def _finite_number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IncomingTextValidationError(f"{name} 必须是数字") from exc
    if not math.isfinite(number):
        raise IncomingTextValidationError(f"{name} 必须是有限数字")
    return number


def normalize_region(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise IncomingTextValidationError("文字区域格式错误")
    x = _finite_number(value.get("x"), "x")
    y = _finite_number(value.get("y"), "y")
    width = _finite_number(value.get("width"), "width")
    height = _finite_number(value.get("height"), "height")
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
        raise IncomingTextValidationError("文字区域必须完整位于标准稿内")
    return {"x": x, "y": y, "width": width, "height": height}


def validate_safe_regex(pattern: str) -> None:
    if not pattern or len(pattern) > MAX_REGEX_LENGTH:
        raise IncomingTextValidationError(f"格式规则长度必须为 1–{MAX_REGEX_LENGTH}")
    # Disallow backreferences, lookarounds and nested quantified groups. This
    # intentionally accepts only the regular subset needed for lot/date codes.
    if re.search(r"\\[1-9]|\(\?|\||\([^)]*[+*{][^)]*\)[+*{]", pattern):
        raise IncomingTextValidationError("格式规则包含不安全的复杂表达式")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise IncomingTextValidationError("格式规则不是有效正则表达式") from exc


def normalize_field_rule(value: Any, *, index: int = 0) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IncomingTextValidationError("字段规则格式错误")
    mode = str(value.get("match_mode") or "exact").strip().lower()
    importance = str(value.get("importance") or "normal").strip().lower()
    if mode not in {"exact", "regex"}:
        raise IncomingTextValidationError("匹配方式只能是 exact 或 regex")
    if importance not in {"critical", "normal"}:
        raise IncomingTextValidationError("关键等级只能是 critical 或 normal")
    expected = exact_text(value.get("expected_text"), case_sensitive=True)
    if not expected:
        raise IncomingTextValidationError("正确文字不能为空")
    if len(expected) > MAX_EXACT_LENGTH:
        raise IncomingTextValidationError(f"正确文字不能超过 {MAX_EXACT_LENGTH} 个字符")
    if mode == "regex":
        validate_safe_regex(expected)
    name = str(value.get("name") or "").strip()
    if not name:
        raise IncomingTextValidationError("字段名称不能为空")
    field_id = str(value.get("field_id") or f"field_{index + 1}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", field_id):
        raise IncomingTextValidationError("字段 ID 只能包含字母、数字、点、横线或下划线，最多 64 位")
    case_sensitive = value.get("case_sensitive", True)
    if not isinstance(case_sensitive, bool):
        raise IncomingTextValidationError("区分大小写必须是布尔值")
    ignore_whitespace = value.get("ignore_whitespace", False)
    if not isinstance(ignore_whitespace, bool):
        raise IncomingTextValidationError("忽略空白必须是布尔值")
    if mode == "regex" and ignore_whitespace:
        raise IncomingTextValidationError("格式规则不能同时启用忽略空白")
    return {
        "field_id": field_id,
        "name": name[:80],
        "region_normalized": normalize_region(value.get("region_normalized")),
        "expected_text": expected,
        "match_mode": mode,
        "importance": importance,
        "case_sensitive": case_sensitive,
        "ignore_whitespace": ignore_whitespace,
    }


def normalize_field_rules(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list) or not values:
        raise IncomingTextValidationError("至少配置一个文字字段")
    if len(values) > 100:
        raise IncomingTextValidationError("单个标准最多配置 100 个文字字段")
    rules = [normalize_field_rule(value, index=index) for index, value in enumerate(values)]
    ids = [rule["field_id"] for rule in rules]
    if len(set(ids)) != len(ids):
        raise IncomingTextValidationError("字段 ID 不能重复")
    if not any(rule["importance"] == "critical" and rule["match_mode"] == "exact" for rule in rules):
        raise IncomingTextValidationError("启用前至少需要一个关键固定文字字段")
    return rules


def assess_image_quality(image: np.ndarray) -> dict[str, Any]:
    if image is None or image.size == 0 or image.ndim not in {2, 3}:
        return {"accepted": False, "reasons": ["image_decode_failed"], "metrics": {}}
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    dark_ratio = float(np.mean(gray <= 8))
    glare_ratio = float(np.mean(gray >= 248))
    reasons: list[str] = []
    if min(width, height) < 600:
        reasons.append("resolution_too_low")
    if sharpness < 55.0:
        reasons.append("blurred")
    if brightness < 35.0:
        reasons.append("underexposed")
    if brightness > 225.0 or glare_ratio > 0.18:
        reasons.append("overexposed_or_glare")
    return {
        "accepted": not reasons,
        "reasons": reasons,
        "metrics": {
            "width": width,
            "height": height,
            "sharpness": round(sharpness, 2),
            "brightness": round(brightness, 2),
            "dark_ratio": round(dark_ratio, 4),
            "glare_ratio": round(glare_ratio, 4),
        },
    }


def _order_quad(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(diffs)]
    ordered[3] = points[np.argmax(diffs)]
    return ordered


def rectify_label(image: np.ndarray, target_size: tuple[int, int]) -> tuple[np.ndarray, dict[str, Any]]:
    """Find a dominant quadrilateral and warp it to the electronic reference."""
    target_width, target_height = target_size
    if target_width < 32 or target_height < 32:
        return image, {"accepted": False, "reason": "invalid_reference_size"}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 45, 140)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(image.shape[0] * image.shape[1])
    candidates: list[tuple[float, np.ndarray]] = []
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        area = float(abs(cv2.contourArea(polygon)))
        if len(polygon) == 4 and area >= image_area * 0.12:
            candidates.append((area, polygon.reshape(4, 2).astype(np.float32)))
    if not candidates:
        return image, {"accepted": False, "reason": "label_geometry_not_found"}
    area, points = max(candidates, key=lambda item: item[0])
    source = _order_quad(points)
    top = float(np.linalg.norm(source[1] - source[0]))
    bottom = float(np.linalg.norm(source[2] - source[3]))
    left = float(np.linalg.norm(source[3] - source[0]))
    right = float(np.linalg.norm(source[2] - source[1]))
    observed_ratio = (top + bottom) / max(left + right, 1.0)
    target_ratio = target_width / target_height
    ratio_error = abs(math.log(max(observed_ratio, 0.001) / max(target_ratio, 0.001)))
    coverage = area / image_area
    if not cv2.isContourConvex(source.astype(np.int32)) or not 0.12 <= coverage <= 0.96 or ratio_error > 0.38:
        return image, {"accepted": False, "reason": "label_geometry_unstable", "coverage": round(coverage, 4)}
    destination = np.array(
        [[0, 0], [target_width - 1, 0], [target_width - 1, target_height - 1], [0, target_height - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(image, transform, (target_width, target_height))
    return warped, {
        "accepted": True,
        "coverage": round(coverage, 4),
        "aspect_ratio_error": round(ratio_error, 4),
        "source_quad": source.round(2).tolist(),
    }


def observation_center(observation: TextObservation, image_size: tuple[int, int]) -> tuple[float, float] | None:
    if not observation.polygon:
        return None
    width, height = image_size
    if width <= 0 or height <= 0:
        return None
    return (
        sum(point[0] for point in observation.polygon) / len(observation.polygon) / width,
        sum(point[1] for point in observation.polygon) / len(observation.polygon) / height,
    )


def observations_for_rule(
    rule: dict[str, Any], observations: Iterable[TextObservation], image_size: tuple[int, int]
) -> list[TextObservation]:
    region = rule["region_normalized"]
    x1, y1 = region["x"], region["y"]
    x2, y2 = x1 + region["width"], y1 + region["height"]
    matches: list[TextObservation] = []
    for observation in observations:
        center = observation_center(observation, image_size)
        if center and x1 <= center[0] <= x2 and y1 <= center[1] <= y2:
            matches.append(observation)
    width, height = image_size
    matches.sort(
        key=lambda item: (
            round(min((point[1] for point in item.polygon), default=0) / max(height * 0.025, 1)),
            min((point[0] for point in item.polygon), default=0),
        )
    )
    return matches


def compare_field(
    rule: dict[str, Any], observation: TextObservation | None, *, visual_similarity: float | None = None
) -> dict[str, Any]:
    expected = comparison_text(rule["expected_text"], rule)
    observed_raw = observation.text if observation else ""
    observed = comparison_text(observed_raw, rule)
    confidence = float(observation.confidence if observation else 0.0)
    corroborated = bool(observation and observation.corroborated)
    if rule["match_mode"] == "regex":
        matched = bool(re.fullmatch(expected, observed))
    else:
        matched = observed == expected
    reasons: list[str] = []
    outcome = PASS
    if not observation:
        reasons.append("field_missing")
        outcome = REVIEW_REQUIRED
    elif not observed and rule["importance"] == "critical" and confidence >= MIN_CRITICAL_MISMATCH_CONFIDENCE and corroborated:
        reasons.append("field_missing")
        outcome = FAIL
    elif confidence < MIN_AUTOMATIC_CONFIDENCE:
        reasons.append("ocr_confidence_low")
        outcome = REVIEW_REQUIRED
    elif rule["importance"] == "critical" and not corroborated:
        reasons.append("critical_text_not_corroborated")
        outcome = REVIEW_REQUIRED
    elif not matched:
        reasons.append("text_mismatch")
        # Line confidence is not character confidence. A critical mismatch is
        # automatic FAIL only when a second OCR pass corroborates it.
        if rule["importance"] == "critical" and confidence >= MIN_CRITICAL_MISMATCH_CONFIDENCE and corroborated:
            outcome = FAIL
        else:
            outcome = REVIEW_REQUIRED
    if matched and visual_similarity is not None and visual_similarity < 0.72:
        reasons.append("local_visual_difference")
        outcome = REVIEW_REQUIRED
    return {
        "field_id": rule["field_id"],
        "name": rule["name"],
        "importance": rule["importance"],
        "match_mode": rule["match_mode"],
        "ignore_whitespace": bool(rule.get("ignore_whitespace", False)),
        "expected_text": rule["expected_text"],
        "observed_text": observed_raw,
        "confidence": round(confidence, 4),
        "matched": matched,
        "outcome": outcome,
        "reasons": reasons,
        "region_normalized": rule["region_normalized"],
        "visual_similarity": None if visual_similarity is None else round(float(visual_similarity), 4),
    }


def decide_inspection(
    rules: list[dict[str, Any]],
    observations_by_field: dict[str, TextObservation | None],
    *,
    quality: dict[str, Any],
    alignment: dict[str, Any],
    visual_similarities: dict[str, float] | None = None,
) -> dict[str, Any]:
    field_results = [
        compare_field(
            rule,
            observations_by_field.get(rule["field_id"]),
            visual_similarity=(visual_similarities or {}).get(rule["field_id"]),
        )
        for rule in rules
    ]
    reasons: list[str] = []
    if not quality.get("accepted"):
        reasons.extend(str(item) for item in quality.get("reasons") or ["image_quality_rejected"])
    if not alignment.get("accepted"):
        reasons.append(str(alignment.get("reason") or "alignment_unstable"))
    if any(field["outcome"] == FAIL for field in field_results) and not reasons:
        decision = FAIL
    elif reasons or any(field["outcome"] == REVIEW_REQUIRED for field in field_results):
        decision = REVIEW_REQUIRED
    else:
        decision = PASS
    return {"decision": decision, "reasons": sorted(set(reasons)), "fields": field_results}


def apply_commissioning_gate(result: dict[str, Any], *, automatic_decisions_verified: bool) -> dict[str, Any]:
    """Downgrade automatic terminal decisions until the customer gate is signed."""
    gated = dict(result)
    if not automatic_decisions_verified and gated.get("decision") in {PASS, FAIL}:
        gated["candidate_decision"] = gated["decision"]
        gated["decision"] = REVIEW_REQUIRED
        gated["reasons"] = sorted({*(gated.get("reasons") or []), "commissioning_not_verified"})
    return gated


def local_visual_similarity(reference: np.ndarray, captured: np.ndarray, region: dict[str, float]) -> float | None:
    height, width = reference.shape[:2]
    if captured.shape[:2] != reference.shape[:2]:
        return None
    x1 = max(0, int(region["x"] * width))
    y1 = max(0, int(region["y"] * height))
    x2 = min(width, int((region["x"] + region["width"]) * width))
    y2 = min(height, int((region["y"] + region["height"]) * height))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    left = cv2.cvtColor(reference[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    right = cv2.cvtColor(captured[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    left = cv2.equalizeHist(left)
    right = cv2.equalizeHist(right)
    score = cv2.matchTemplate(left, right, cv2.TM_CCOEFF_NORMED)[0][0]
    return max(0.0, min(1.0, float((score + 1.0) / 2.0)))


def annotate_inspection(image: np.ndarray, field_results: list[dict[str, Any]]) -> np.ndarray:
    annotated = image.copy()
    height, width = annotated.shape[:2]
    colors = {PASS: (45, 168, 92), FAIL: (47, 65, 220), REVIEW_REQUIRED: (0, 166, 244)}
    for field in field_results:
        region = field["region_normalized"]
        x1, y1 = int(region["x"] * width), int(region["y"] * height)
        x2 = int((region["x"] + region["width"]) * width)
        y2 = int((region["y"] + region["height"]) * height)
        color = colors.get(field["outcome"], colors[REVIEW_REQUIRED])
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, max(2, width // 500))
        cv2.putText(annotated, str(field["name"])[:24], (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    return annotated
