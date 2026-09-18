"""Normalize the two ordered pipeline state lists without changing their input policy."""
from typing import Any


def normalize_pipeline_state(raw: Any) -> dict[str, list[str]]:
    data = raw if isinstance(raw, dict) else {}
    result: dict[str, list[str]] = {"accessory_ids": [], "pending_candidate_ids": []}
    for key in result:
        seen: set[str] = set()
        for value in data.get(key) or []:
            item_id = str(value or "").strip()
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            result[key].append(item_id)
    return result
