"""Account-owned task navigation preferences and original bounds."""
from typing import Any


TASK_NAVIGATION_PREFERENCES_KEY = "task_navigation_preferences"


MAX_TASK_NAVIGATION_IDS = 200


MAX_TASK_NAVIGATION_ID_LENGTH = 200


def normalize_task_navigation_ids(raw_ids: Any) -> list[str]:
    if not isinstance(raw_ids, list):
        return []
    clean_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        task_id = str(raw_id or "").strip()
        if not task_id or len(task_id) > MAX_TASK_NAVIGATION_ID_LENGTH or task_id in seen:
            continue
        seen.add(task_id)
        clean_ids.append(task_id)
        if len(clean_ids) >= MAX_TASK_NAVIGATION_IDS:
            break
    return clean_ids


def task_navigation_preferences_payload(user: dict[str, Any]) -> dict[str, Any]:
    raw_preferences = user.get(TASK_NAVIGATION_PREFERENCES_KEY)
    preferences = raw_preferences if isinstance(raw_preferences, dict) else {}
    return {
        "pinned_task_ids": normalize_task_navigation_ids(preferences.get("pinned_task_ids")),
        "archived_task_ids": normalize_task_navigation_ids(preferences.get("archived_task_ids")),
        "updated_at": int(preferences.get("updated_at") or 0),
        "exists": isinstance(raw_preferences, dict),
    }
