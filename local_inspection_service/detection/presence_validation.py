"""Provider coverage and count validation without runtime dependencies."""
from typing import Any


def ai_detection_parsed_covers_required(parsed: Any, required_ids: set[str]) -> bool:
    """True when the provider response mentions at least one required accessory
    id, either as a detection entry or a rule count. An empty or unrelated
    response is a provider contract failure, not an all-missing verdict."""
    if not required_ids:
        return True
    if not isinstance(parsed, dict):
        return False
    mentioned: set[str] = set()
    detections = parsed.get("detections") if isinstance(parsed.get("detections"), list) else []
    for det in detections:
        if isinstance(det, dict) and det.get("accessory_id") is not None:
            mentioned.add(str(det.get("accessory_id")))
    rule = parsed.get("rule") if isinstance(parsed.get("rule"), dict) else {}
    counts = rule.get("counts") if isinstance(rule.get("counts"), dict) else {}
    mentioned.update(str(key) for key in counts.keys())
    return bool(mentioned & required_ids)


def coerce_detection_count(value: Any) -> int | None:
    """Tolerant count parsing: JSON-mode providers may serialize whole numbers
    as floats (1.0). Booleans, negatives, fractional floats, and strings are
    rejected so ambiguous counts keep failing closed (see smoke_ai_detection)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    return None
