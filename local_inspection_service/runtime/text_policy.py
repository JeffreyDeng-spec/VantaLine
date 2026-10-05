"""Text truncation used by status and model payload policies."""
import re
from typing import Any


def bounded_text(value: Any, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]
