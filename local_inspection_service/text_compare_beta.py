"""Fail-closed primitives for the stateless quick text comparison Beta."""
from __future__ import annotations
import base64
from difflib import SequenceMatcher
from typing import Any, Callable
import cv2
import numpy as np
from local_inspection_service.incoming_text_inspection import TextObservation, assess_image_quality, rectify_label

def _ordered(items: list[TextObservation]) -> list[TextObservation]:
    return sorted(items, key=lambda item: (
        round(min([p[1] for p in item.polygon] or [0]) / 16),
        min([p[0] for p in item.polygon] or [0]),
    ))

def align_lines(left: list[TextObservation], right: list[TextObservation]):
    rows, cols = len(left), len(right)
    costs = [[0.0] * (cols + 1) for _ in range(rows + 1)]
    moves = [[""] * (cols + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1): costs[row][0], moves[row][0] = row * .72, "up"
    for col in range(1, cols + 1): costs[0][col], moves[0][col] = col * .72, "left"
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            similarity = SequenceMatcher(None, left[row-1].text, right[col-1].text, autojunk=False).ratio()
            costs[row][col], moves[row][col] = min(
                (costs[row-1][col-1] + 1 - similarity, "diag"),
                (costs[row-1][col] + .72, "up"),
                (costs[row][col-1] + .72, "left"),
                key=lambda item: item[0],
            )
    pairs, row, col = [], rows, cols
    while row or col:
        move = moves[row][col]
        if move == "diag": pairs.append((left[row-1], right[col-1])); row -= 1; col -= 1
        elif move == "up": pairs.append((left[row-1], None)); row -= 1
        else: pairs.append((None, right[col-1])); col -= 1
    return list(reversed(pairs))

def _region(item: TextObservation | None, image: np.ndarray, fallback: TextObservation | None = None):
    source = item or fallback
    if not source or not source.polygon: return None
    height, width = image.shape[:2]
    xs, ys = [p[0] for p in source.polygon], [p[1] for p in source.polygon]
    x1, x2 = max(0., min(xs)-8), min(float(width), max(xs)+8)
    y1, y2 = max(0., min(ys)-6), min(float(height), max(ys)+6)
    values = (x1/width, y1/height, (x2-x1)/width, (y2-y1)/height)
    if not all(np.isfinite(v) for v in values): return None
    return {"x": round(values[0], 6), "y": round(values[1], 6),
            "width": round(max(0., min(1-values[0], values[2])), 6),
            "height": round(max(0., min(1-values[1], values[3])), 6)}

def compare_images(reference: np.ndarray, captured: np.ndarray, comparison_id: str,
                   ocr: Callable[[np.ndarray], list[TextObservation]]) -> dict[str, Any]:
    ref_quality, cap_quality = assess_image_quality(reference), assess_image_quality(captured)
    # Electronic artwork often has a mostly white background. Exposure/glare is
    # a capture-only gate; the reference still must be large and sharp enough.
    ref_reasons = [reason for reason in ref_quality.get("reasons", []) if reason != "overexposed_or_glare"]
    ref_quality = {**ref_quality, "accepted": not ref_reasons, "reasons": ref_reasons}
    corrected, alignment = rectify_label(captured, (reference.shape[1], reference.shape[0]))
    working = corrected if alignment.get("accepted") else captured
    base = {"comparison_id": comparison_id, "reference_quality": ref_quality,
            "captured_quality": cap_quality, "alignment": alignment, "differences": []}
    if not ref_quality.get("accepted") or not cap_quality.get("accepted"):
        return {**base, "decision": "REVIEW_REQUIRED", "message": "图片质量不足，请重新拍摄或更换标准图。"}
    expected, actual = _ordered(ocr(reference)), _ordered(ocr(working))
    if not expected or not actual:
        return {**base, "decision": "REVIEW_REQUIRED", "message": "没有可靠识别到文字，请调整距离、清晰度或光线。"}
    differences, low_confidence = [], False
    same_space = working.shape[:2] == reference.shape[:2]
    for index, (left, right) in enumerate(align_lines(expected, actual), 1):
        ref_text, actual_text = left.text if left else "", right.text if right else ""
        confidence = min(left.confidence if left else 1., right.confidence if right else 1.)
        low_confidence = low_confidence or confidence < .90
        if left and right and ref_text == actual_text: continue
        differences.append({"id": f"difference_{index}", "reference_text": ref_text,
            "actual_text": actual_text, "confidence": round(confidence, 4),
            "type": "missing" if left and not right else "extra" if right and not left else "changed",
            "region_normalized": _region(right, working, left if same_space else None)})
    if differences: decision, message = "DIFFERENCES", f"发现 {len(differences)} 处疑似文字差异，请人工确认。"
    elif low_confidence or not alignment.get("accepted"):
        decision, message = "REVIEW_REQUIRED", "文字或版面定位置信度不足，请人工确认或重新拍照。"
    else: decision, message = "MATCH", "未发现文字差异。仍需人工检查颜色、材质和印刷质量。"
    annotated, height, width = working.copy(), working.shape[0], working.shape[1]
    for difference in differences:
        region = difference["region_normalized"]
        if not region: continue
        x1, y1 = int(region["x"]*width), int(region["y"]*height)
        x2, y2 = int((region["x"]+region["width"])*width), int((region["y"]+region["height"])*height)
        cv2.rectangle(annotated, (x1,y1), (x2,y2), (36,36,220), max(3,width//420))
    if max(annotated.shape[:2]) > 2000:
        scale = 2000 / max(annotated.shape[:2])
        annotated = cv2.resize(annotated, (int(annotated.shape[1] * scale), int(annotated.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return {**base, "decision": decision, "message": message, "differences": differences,
        "reference_lines": len(expected), "captured_lines": len(actual),
        "annotated_image_data_url": "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii") if ok else ""}
