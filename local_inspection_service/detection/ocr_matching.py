"""Detection-only text normalization and accessory keyword matching policies."""
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


def normalize_ocr_text(text: str) -> str:
    text = text.lower()
    replacements = {
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "ß": "ss",
        "é": "e",
        "è": "e",
        "ê": "e",
        "á": "a",
        "à": "a",
        "í": "i",
        "ó": "o",
        "ç": "c",
        "ğ": "g",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9@./+ -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class MatchThresholds:
    text_score: Callable[[], float]
    confidence: Callable[[], float]
    margin: Callable[[], float]


class OCRMatching:
    def __init__(self, stopwords: Callable[[], set[str]], uid: Callable[[dict[str, Any]], str], thresholds: MatchThresholds):
        self.stopwords, self.uid, self.thresholds = stopwords, uid, thresholds

    def keywords(self, value: Any, *, weight: float = 1.0) -> list[dict[str, Any]]:
        terms: list[dict[str, Any]] = []
        if value is None:
            return terms
        if isinstance(value, dict):
            for nested in value.values():
                terms.extend(self.keywords(nested, weight=weight))
            return terms
        if isinstance(value, list):
            for nested in value:
                terms.extend(self.keywords(nested, weight=weight))
            return terms
        normalized = normalize_ocr_text(str(value))
        if not normalized:
            return terms
        if len(normalized) >= 3 and normalized not in self.stopwords():
            terms.append({"text": normalized, "weight": weight})
        for token in normalized.split():
            if len(token) >= 3 and token not in self.stopwords():
                terms.append({"text": token, "weight": weight})
        return terms

    def profiles(self, items: list[dict[str, Any]], accessory_labels: dict[str, str]) -> dict[str, dict[str, Any]]:
        profiles: dict[str, dict[str, Any]] = {}
        for item in items:
            if not item:
                continue
            accessory_id = str(item.get("id") or self.uid(item) or "").strip()
            if not accessory_id:
                continue
            profile = item.get("ai_profile") if isinstance(item.get("ai_profile"), dict) else {}
            label = str(accessory_labels.get(accessory_id) or item.get("name") or item.get("label") or accessory_id)
            raw_terms: list[dict[str, Any]] = []
            raw_terms.extend(self.keywords(label, weight=2.0))
            raw_terms.extend(self.keywords(item.get("name"), weight=2.0))
            raw_terms.extend(self.keywords(item.get("label"), weight=2.0))
            raw_terms.extend(self.keywords(profile.get("english_name"), weight=2.0))
            raw_terms.extend(self.keywords(profile.get("distinguishing_text"), weight=3.0))
            raw_terms.extend(self.keywords(profile.get("tags"), weight=1.0))
            keywords: dict[str, float] = {}
            for term in raw_terms:
                text = str(term.get("text") or "").strip()
                if not text:
                    continue
                keywords[text] = max(float(term.get("weight") or 1.0), keywords.get(text, 0.0))
            profiles[accessory_id] = {
                "accessory_id": accessory_id,
                "label": label,
                "keywords": [{"text": text, "weight": weight} for text, weight in sorted(keywords.items())],
            }
        return profiles

    def match(self, texts: list[str], mean_text_score: float, spec: dict[str, Any]) -> dict[str, Any]:
        joined = normalize_ocr_text(" ".join(texts))
        profiles = spec.get("ocr_accessory_profiles") if isinstance(spec.get("ocr_accessory_profiles"), dict) else {}
        if not joined or not profiles:
            return {"accepted": False, "reason": "no_ocr_text_or_profiles", "confidence": 0.0, "margin": 0.0}
        scores: list[dict[str, Any]] = []
        for accessory_id, profile in profiles.items():
            hits = []
            score = 0.0
            for keyword in profile.get("keywords") or []:
                text = str(keyword.get("text") or "").strip()
                if text and text in joined:
                    weight = float(keyword.get("weight") or 1.0)
                    score += weight
                    hits.append(text)
            confidence = min(1.0, score / 6.0) if score > 0 else 0.0
            scores.append(
                {
                    "accessory_id": str(accessory_id),
                    "label": str(profile.get("label") or accessory_id),
                    "score": round(score, 4),
                    "confidence": round(confidence, 4),
                    "matched_keywords": hits[:12],
                }
            )
        ranked = sorted(scores, key=lambda item: (float(item["confidence"]), float(item["score"])), reverse=True)
        best = ranked[0] if ranked else {"confidence": 0.0, "score": 0.0}
        second_confidence = float(ranked[1]["confidence"]) if len(ranked) > 1 else 0.0
        margin = round(float(best.get("confidence") or 0.0) - second_confidence, 4)
        accepted = (
            float(mean_text_score) >= self.thresholds.text_score()
            and float(best.get("confidence") or 0.0) >= self.thresholds.confidence()
            and margin >= self.thresholds.margin()
        )
        reason = "accepted" if accepted else "low_ocr_confidence"
        if float(mean_text_score) < self.thresholds.text_score():
            reason = "low_text_score"
        elif float(best.get("confidence") or 0.0) < self.thresholds.confidence():
            reason = "low_match_confidence"
        elif margin < self.thresholds.margin():
            reason = "low_match_margin"
        return {
            "accepted": accepted,
            "reason": reason,
            "accessory_id": best.get("accessory_id"),
            "label": best.get("label"),
            "confidence": best.get("confidence", 0.0),
            "margin": margin,
            "mean_text_score": round(float(mean_text_score), 4),
            "matched_keywords": best.get("matched_keywords", []),
            "candidates": ranked[:5],
        }
