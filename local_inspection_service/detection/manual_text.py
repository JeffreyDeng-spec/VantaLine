"""Manual text classification and in-place legacy detection projection."""
from collections.abc import Callable
from typing import Any
from .ocr_matching import normalize_ocr_text
from .results import DetectionLabels


class ManualClassifier:
    def __init__(self, keywords: Callable[[], dict[str, list[tuple[str, int]]]], labels: Callable[[], dict[str, str]]):
        self.keywords, self.labels = keywords, labels

    def classify(self, texts: list[str]) -> dict[str, Any]:
        joined = normalize_ocr_text(" ".join(texts))
        scores: dict[str, int] = {}
        matches: dict[str, list[str]] = {}
        for manual_type, keywords in self.keywords().items():
            score = 0
            hit_list = []
            for keyword, weight in keywords:
                key = normalize_ocr_text(keyword)
                if key and key in joined:
                    score += weight
                    hit_list.append(keyword)
            scores[manual_type] = score
            matches[manual_type] = hit_list

        best_type, best_score = max(scores.items(), key=lambda item: item[1])
        second_score = max((score for key, score in scores.items() if key != best_type), default=0)
        if best_score < 6 or best_score - second_score < 2:
            best_type = "unknown"
        confidence = 0.0 if best_type == "unknown" else min(1.0, best_score / max(best_score + second_score, 1))
        return {
            "manual_type": best_type,
            "manual_label": self.labels().get(best_type, "Unknown Manual"),
            "confidence": round(confidence, 4),
            "scores": scores,
            "matches": matches.get(best_type, []),
        }


class ManualProjection:
    def __init__(self, class_ids: Callable[[], dict[str, int]], labels: DetectionLabels):
        self.class_ids, self.labels = class_ids, labels

    def finalize(self, det: dict[str, Any], ocr_result: dict[str, Any], orientation: dict[str, Any], max_texts: int) -> None:
        classification = ocr_result["classification"]
        det["ocr"] = {
            **classification,
            "best_rotation": ocr_result["rotation"],
            "predicted_rotation": orientation["predicted_rotation"],
            "long_edge_angle": orientation["long_edge_angle"],
            "fallback_used": ocr_result.get("fallback_used", False),
            "mean_text_score": ocr_result["mean_text_score"],
            "texts": ocr_result["texts"][:max_texts],
        }
        if classification["manual_type"] != "unknown":
            manual_type = classification["manual_type"]
            class_id = self.class_ids()[manual_type]
            det["class_id"] = class_id
            det["class_name"] = self.labels.class_names()[class_id]
            det["label"] = self.labels.class_labels()[class_id]
            det["manual_type"] = manual_type
            det["manual_label"] = classification["manual_label"]
        else:
            det["class_id"] = 99
            det["class_name"] = self.labels.generic_names()[99]
            det["label"] = self.labels.generic_labels()[99]
