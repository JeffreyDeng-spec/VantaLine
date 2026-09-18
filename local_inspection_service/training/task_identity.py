"""Training record identifiers and the existing timestamp ordering policy."""
from collections.abc import Callable
from pathlib import Path
import re
from typing import Any


def training_task_path(task_id: str, *, directory: Callable[[], Path]) -> Path:
    safe_task_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(task_id)).strip("._") or "training_task"
    return directory() / f"{safe_task_id}.json"


def training_task_identity_values(task: dict[str, Any], row: dict[str, Any] | None = None) -> set[str]:
    values: set[str] = set()
    if row:
        for key in ("id", "job_id"):
            value = str(row.get(key) or "").strip()
            if value:
                values.add(value)
    for key in ("id", "job_id", "task_id", "remote_training_job_id"):
        value = str(task.get(key) or "").strip()
        if value:
            values.add(value)
    return values


def training_task_matches_identifier(
    task: dict[str, Any],
    requested: str,
    row: dict[str, Any] | None = None,
) -> bool:
    clean_requested = str(requested or "").strip()
    return bool(clean_requested and clean_requested in training_task_identity_values(task, row))


def training_task_sort_key(task: dict[str, Any]) -> tuple[float, str]:
    updated_at = task.get("updated_at") or task.get("created_at") or task.get("completed_at") or task.get("started_at") or 0
    try:
        timestamp = float(updated_at)
    except (TypeError, ValueError):
        timestamp = 0.0
    return timestamp, str(task.get("job_id") or task.get("task_id") or task.get("id") or "")
