"""Presence response normalization with explicit formatting and metadata dependencies."""
from collections.abc import Callable
import math
from typing import Any
from .presence_payload import BoundedText, StringList

Record = dict[str, Any]
CountParser = Callable[[Any], int | None]


class PresenceResults:
    def __init__(self, count: Callable[[], CountParser], text: Callable[[], BoundedText],
                 strings: Callable[[], StringList], provider_meta: Callable[[Record], Record],
                 label: Callable[[], str]):
        self.count, self.text, self.strings = count, text, strings
        self.provider_meta, self.label = provider_meta, label

    def normalize_ai_detection_result(self,
        parsed: dict[str, Any],
        required_accessories: list[dict[str, Any]],
        latency_ms: int,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        raw_detections = parsed.get("detections") if isinstance(parsed.get("detections"), list) else []
        raw_by_id = {
            str(det.get("accessory_id")): det
            for det in raw_detections
            if isinstance(det, dict) and det.get("accessory_id") is not None
        }
        raw_rule = parsed.get("rule") if isinstance(parsed.get("rule"), dict) else {}
        raw_counts = raw_rule.get("counts") if isinstance(raw_rule.get("counts"), dict) else {}
        detections = []
        present_ids = []
        missing_ids = []
        counts: dict[str, int] = {}
        count_mismatches: dict[str, dict[str, Any]] = {}
        overcount_ids: list[str] = []
        for required in required_accessories:
            item_id = str(required.get("accessory_id") or "")
            if not item_id:
                continue
            try:
                expected_count = max(1, int(required.get("expected_count") or 1))
            except (TypeError, ValueError):
                expected_count = 1
            raw = raw_by_id.get(item_id, {})
            raw_confidence = raw.get("confidence", 0.5 if raw.get("present") is True else 0.0) if isinstance(raw, dict) else 0.0
            try:
                if isinstance(raw_confidence, bool):
                    raise ValueError("confidence must be numeric")
                confidence_value = float(raw_confidence)
                if not math.isfinite(confidence_value):
                    raise ValueError("confidence must be finite")
                confidence = max(0.0, min(1.0, confidence_value))
            except (TypeError, ValueError):
                confidence = 0.0
            provider_present = isinstance(raw, dict) and raw.get("present") is True
            present = provider_present and confidence > 0.0
            has_raw_count = item_id in raw_counts
            rule_count = self.count()(raw_counts.get(item_id)) if has_raw_count else None
            detection_count = self.count()(raw.get("count")) if isinstance(raw, dict) else None
            if has_raw_count:
                count = rule_count if rule_count is not None else 0
            elif detection_count is not None:
                count = detection_count
            else:
                count = 1 if present else 0
            if not present:
                count = 0
            counts[item_id] = count
            if present and count == expected_count:
                present_ids.append(item_id)
            else:
                missing_ids.append(item_id)
                if present or count != expected_count:
                    issue = "over_count" if count > expected_count else "under_count"
                    count_mismatches[item_id] = {
                        "expected": expected_count,
                        "found": count,
                        "issue": issue,
                    }
                    if count > expected_count:
                        overcount_ids.append(item_id)
            detection = {
                "accessory_id": item_id,
                "label": self.text()(raw.get("label") if isinstance(raw, dict) else required.get("name"), 120)
                or self.text()(required.get("name") or item_id, 120),
                "present": item_id in present_ids,
                "confidence": round(confidence, 4),
                "evidence": self.text()(raw.get("evidence") if isinstance(raw, dict) else "", 180),
                "observed_text": self.strings()(raw.get("observed_text") if isinstance(raw, dict) else [], max_items=6, max_len=80),
            }
            if count > 1 or expected_count > 1 or (isinstance(raw, dict) and "count" in raw):
                detection["count"] = count
            detections.append(detection)
        required_ids = {str(item.get("accessory_id") or "") for item in required_accessories}
        raw_extra = [item for item in raw_rule.get("extra", []) if str(item) not in required_ids] if isinstance(raw_rule.get("extra"), list) else []
        extra = self.strings()([*raw_extra, *overcount_ids], max_items=12)
        passed = len(missing_ids) == 0
        provider_meta = self.provider_meta(settings)
        return {
            "tool": "vision.inspect.presence",
            "passed": passed,
            "rule": {
                "match_policy": "ai_presence",
                "label": self.label(),
                "present": present_ids,
                "missing": missing_ids,
                "extra": extra,
                "counts": counts,
                "count_mismatches": count_mismatches,
            },
            "detections": detections,
            "ai": {
                "latency_ms": latency_ms,
                "timed_out": False,
                "provider_failure": False,
                "raw_summary": self.text()(parsed.get("raw_summary") or parsed.get("summary") or "", 240),
                "provider_status": settings.get("status") or "",
                **provider_meta,
            },
        }
