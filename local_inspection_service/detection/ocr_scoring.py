"""Local OCR scoring with original single/batch exception and fallback boundaries."""
from collections.abc import Callable
from typing import Any
import cv2
import numpy as np
from .ocr_images import rotate_quarter_turn


def is_confident_manual_classification(ocr_result: dict[str, Any], min_confidence: float) -> bool:
    classification = ocr_result["classification"]
    return classification["manual_type"] != "unknown" and float(classification["confidence"]) >= min_confidence


def better_ocr_result(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    current_class_score = max(current["classification"]["scores"].values(), default=0)
    candidate_class_score = max(candidate["classification"]["scores"].values(), default=0)
    if (
        candidate_class_score,
        len(candidate["texts"]),
        candidate["mean_text_score"],
    ) > (
        current_class_score,
        len(current["texts"]),
        current["mean_text_score"],
    ):
        return candidate
    return current


class OCRScoring:
    def __init__(self, engine: Callable[[], Any], classify: Callable[[list[str]], dict[str, Any]]):
        self.engine, self.classify = engine, classify

    def build(self, result: dict[str, Any], rotation: int) -> dict[str, Any]:
        texts = [str(x) for x in result.get("rec_texts", []) if str(x).strip()]
        rec_scores = [float(x) for x in result.get("rec_scores", [])]
        mean_score = sum(rec_scores) / len(rec_scores) if rec_scores else 0.0
        return {
            "texts": texts,
            "mean_text_score": round(mean_score, 4),
            "rotation": int(rotation) % 360,
            "classification": self.classify(texts),
        }

    def variant(self, crop_bgr: np.ndarray, rotation: int) -> dict[str, Any]:
        try:
            result = self.engine().predict(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))[0]
        except Exception:
            result = {}
        return self.build(result, rotation)

    def variants(self, crops_bgr: list[np.ndarray], rotations: list[int]) -> list[dict[str, Any]]:
        if not crops_bgr:
            return []
        try:
            batch = [cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) for crop in crops_bgr]
            results = self.engine().predict(batch)
            return [self.build(result or {}, rotation) for result, rotation in zip(results, rotations)]
        except Exception:
            return [self.variant(crop, rotation) for crop, rotation in zip(crops_bgr, rotations)]

    def run_crop(self, crop_bgr: np.ndarray, orientation: dict[str, Any], fallback_min_confidence: float) -> dict[str, Any]:
        best = self.variant(crop_bgr, int(orientation["predicted_rotation"]))
        fallback_used = False
        if not is_confident_manual_classification(best, fallback_min_confidence):
            for fallback_rotation in orientation.get("fallback_rotations", []):
                fallback_crop = rotate_quarter_turn(crop_bgr, 180)
                candidate = self.variant(fallback_crop, int(fallback_rotation))
                fallback_used = True
                best = better_ocr_result(best, candidate)
                if is_confident_manual_classification(best, fallback_min_confidence):
                    break
        best["fallback_used"] = fallback_used
        best["orientation"] = orientation
        return best
