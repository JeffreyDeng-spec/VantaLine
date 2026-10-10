"""Bounded distinct text-list policy; no application dependency."""
from typing import Any
from ..runtime.text_policy import bounded_text

def string_list(value: Any, fallback: list[str] | None=None, *, max_items: int=12, max_len: int=96) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = fallback or []
    items: list[str] = []
    seen = set()
    for raw in raw_items:
        item = bounded_text(raw, max_len)
        key = item.lower()
        if not item or key in seen:
            continue
        items.append(item)
        seen.add(key)
        if len(items) >= max_items:
            break
    return items
