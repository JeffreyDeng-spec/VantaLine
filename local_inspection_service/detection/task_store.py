"""Detection task persistence with lazy thread repositories and shared read-cache ports."""
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from .task_identity import sanitize_ai_detection_task_id, clean_ai_detection_task_name, normalize_ai_detection_task_counts

Record = dict[str, Any]


@dataclass(frozen=True)
class TaskStorePaths:
    data: Callable[[], Path]
    tasks: Callable[[], Path]
    ensure: Callable[[], None]


@dataclass(frozen=True)
class TaskReadCache:
    get: Callable[[str], tuple[bool, Any]]
    put: Callable[[str, Any], None]
    invalidate: Callable[[str], None]


@dataclass(frozen=True)
class TaskRows:
    encode: Callable[[Record], Record | None]
    decode: Callable[[], Callable[[list[Record]], list[Record]]]


class DetectionTaskStore:
    def __init__(self, repository: Callable[[], PostgresRuntimeRepository | None],
                 paths: TaskStorePaths, cache: TaskReadCache, rows: TaskRows,
                 normalize_background: Callable[[], Callable[[str], str]]):
        self.repository, self.paths, self.cache = repository, paths, cache
        self.rows, self.normalize_background = rows, normalize_background

    def load_ai_detection_tasks(self) -> list[dict[str, Any]]:
        cached, cached_tasks = self.cache.get("ai_detection_tasks")
        if cached:
            return list(cached_tasks)
        self.paths.ensure()
        repository = self.repository()
        if repository is not None:
            raw_tasks = self.rows.decode()(repository.fetch_all("ai_detection_tasks"))
        else:
            if not self.paths.tasks().exists():
                return []
            try:
                data = json.loads(self.paths.tasks().read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
            raw_tasks = data.get("tasks") if isinstance(data, dict) else data
        if not isinstance(raw_tasks, list):
            return []
        tasks: list[dict[str, Any]] = []
        for raw in raw_tasks:
            if not isinstance(raw, dict):
                continue
            task_id = sanitize_ai_detection_task_id(raw.get("id"))
            counts = normalize_ai_detection_task_counts(raw.get("required_accessory_counts") or {})
            selected_ids = [str(item_id) for item_id in raw.get("selected_accessory_ids") or counts.keys() if str(item_id) in counts]
            if not task_id or not counts:
                continue
            now = float(raw.get("updated_at") or raw.get("created_at") or time.time())
            task = {
                "id": task_id,
                "name": clean_ai_detection_task_name(raw.get("name"), "AI 检测任务"),
                "selected_accessory_ids": selected_ids or list(counts.keys()),
                "required_accessory_counts": counts,
                "accessory_labels": {
                    str(k): str(v)
                    for k, v in (raw.get("accessory_labels") or {}).items()
                    if str(k) in counts and str(v).strip()
                },
                "created_at": float(raw.get("created_at") or now),
                "updated_at": now,
                "source": str(raw.get("source") or "ai_detection_workbench"),
                "owner_user_id": str(raw.get("owner_user_id") or ""),
                "owner_username": str(raw.get("owner_username") or ""),
                "shared_with_user_ids": raw.get("shared_with_user_ids") if isinstance(raw.get("shared_with_user_ids"), list) else [],
            }
            environment_background = raw.get("environment_background") if isinstance(raw.get("environment_background"), dict) else {}
            background_set_id = self.normalize_background()(str(raw.get("background_set_id") or environment_background.get("background_set_id") or ""))
            if background_set_id and background_set_id != "green_conveyor":
                task["background_set_id"] = background_set_id
                task["environment_background"] = {**environment_background, "background_set_id": background_set_id}
            tasks.append(task)
        tasks.sort(key=lambda item: (float(item.get("updated_at") or 0), str(item.get("id") or "")), reverse=True)
        self.cache.put("ai_detection_tasks", tasks)
        return list(tasks)

    def save_ai_detection_tasks(self, tasks: list[dict[str, Any]]) -> None:
        self.cache.invalidate("ai_detection_tasks")
        self.paths.data().mkdir(parents=True, exist_ok=True)
        repository = self.repository()
        if repository is not None:
            rows = [row for task in tasks if isinstance(task, dict) for row in [self.rows.encode(task)] if row]
            repository.replace_all("ai_detection_tasks", rows)
            return
        payload = {"tasks": tasks}
        tmp_path = self.paths.tasks().with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.paths.tasks())

    def find_ai_detection_task(self, task_id: str) -> dict[str, Any] | None:
        clean_task_id = sanitize_ai_detection_task_id(task_id)
        if not clean_task_id:
            return None
        return next((item for item in self.load_ai_detection_tasks() if item.get("id") == clean_task_id), None)

    def save_ai_detection_task(self, task: dict[str, Any], *, prepend: bool = False) -> None:
        self.cache.invalidate("ai_detection_tasks")
        self.paths.data().mkdir(parents=True, exist_ok=True)
        repository = self.repository()
        if repository is not None:
            row = self.rows.encode(task)
            if row:
                repository.upsert_row("ai_detection_tasks", row)
            return
        clean_task_id = sanitize_ai_detection_task_id(task.get("id"))
        tasks = self.load_ai_detection_tasks()
        for index, existing in enumerate(tasks):
            if existing.get("id") == clean_task_id:
                tasks[index] = task
                self.save_ai_detection_tasks(tasks)
                return
        if prepend:
            tasks.insert(0, task)
        else:
            tasks.append(task)
        self.save_ai_detection_tasks(tasks)

