"""Task-backed environment selection without storing workflow state or identity."""
from collections.abc import Callable
from typing import Any
from .task_identity import sanitize_ai_detection_task_id

Record = dict[str, Any]


def ai_detection_task_background_record(task_id: str, *,
        find_task: Callable[[str], Record | None], normalize_background: Callable[[], Callable[[str], str]]) -> tuple[str, dict[str, Any]]:
    clean_task_id = sanitize_ai_detection_task_id(task_id)
    if not clean_task_id:
        return "", {}
    task = find_task(clean_task_id)
    if not task:
        return "", {}
    environment_background = task.get("environment_background") if isinstance(task.get("environment_background"), dict) else {}
    background_set_id = normalize_background()(str(task.get("background_set_id") or environment_background.get("background_set_id") or ""))
    if not background_set_id or background_set_id == "green_conveyor":
        return "", {}
    return background_set_id, {**environment_background, "background_set_id": background_set_id}


def hydrate_auto_optimize_background_from_ai_task(state: dict[str, Any], *,
        background_record: Callable[[], Callable[[str], tuple[str, Record]]], normalize_background: Callable[[], Callable[[str], str]]) -> bool:
    current_set_id = normalize_background()(str(state.get("background_set_id") or ""))
    if current_set_id and current_set_id != "green_conveyor":
        return False
    background_set_id, environment_background = background_record()(str(state.get("task_id") or ""))
    if not background_set_id:
        return False
    state["background_set_id"] = background_set_id
    state["environment_background"] = environment_background
    return True
