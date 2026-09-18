"""Detection task identifiers, display names and legacy count normalization."""
import re
from typing import Any


def ai_detection_task_model_id(task_id: str, prefix: str) -> str:
    return f"{prefix}{task_id}"


def sanitize_ai_detection_task_id(value: Any) -> str:
    task_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_").lower()
    return task_id[:72]


def clean_ai_detection_task_name(value: Any, fallback: str) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    if not name:
        name = fallback
    return name[:96] or "AI 检测任务"


def normalize_ai_detection_task_counts(raw_counts: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw_id, raw_count in raw_counts.items():
        item_id = str(raw_id or "").strip()
        if not item_id:
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 1
        counts[item_id] = max(1, min(99, count))
    return counts
