"""Training state hydration; visible task refresh retains its existing settlement writes."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class StatusTasks:
    find: Callable[[str], Record | None]
    refresh: Callable[[Record], Record]


@dataclass(frozen=True)
class StatusAccess:
    visible: Callable[[Record, Record, str | None], bool]
    is_admin: Callable[[Record], bool]
    owner: Callable[[Record], str]


@dataclass(frozen=True)
class StatusPreview:
    selected: Callable[[], Callable[[Record, list[str]], list[Record]]]
    cache: Callable[[list[Record]], str]
    missing: Callable[[Record, list[Record]], bool]


class TrainingStatusProjection:
    def __init__(self, tasks: StatusTasks, access: StatusAccess, preview: StatusPreview):
        self.tasks, self.access, self.preview = tasks, access, preview

    def filtered_training_state(self,
        config: dict[str, Any],
        user: dict[str, Any] | None = None,
        target_user_id: str | None = None,
    ) -> dict[str, Any]:
        training = config["training"]
        def hydrate_active_task(state: dict[str, Any], scoped_target_user_id: str | None = None) -> None:
            active_task_id = str(state.get("active_training_task_id") or "").strip()
            if not active_task_id:
                return
            task = self.tasks.find(active_task_id)
            task_visible = bool(task) and (user is None or self.access.visible(task, user, scoped_target_user_id))
            if task and task_visible:
                task = self.tasks.refresh(task)
                for key in (
                    "status",
                    "progress",
                    "note",
                    "error",
                    "current_epoch",
                    "total_epochs",
                    "completed_at",
                    "stopped_at",
                    "cancelled_at",
                    "return_code",
                    "training_executor",
                    "worker_sample_generation_bypassed",
                    "worker_training_bypassed",
                    "remote_training_status",
                    "remote_training_poll_error",
                ):
                    if key in task:
                        state[key] = task.get(key)
                if task.get("dataset_dir"):
                    state["dataset_id"] = task.get("dataset_id") or task.get("source_dataset_id") or task.get("job_id")
                if task.get("action"):
                    state["active_training_action"] = task.get("action")
            elif state.get("status") in {"queued", "running"}:
                state["status"] = "stopped"
                state["progress"] = 100
                state["note"] = "训练任务记录已删除或不可用；请重新发起任务。"
                state["error"] = "Active training task record is missing. Start a new task."

        hydrate_active_task(training, target_user_id)
        if isinstance(training.get("training_states"), list):
            for child in training["training_states"]:
                if not isinstance(child, dict):
                    continue
                child_target_user_id = target_user_id
                if user and self.access.is_admin(user) and not child_target_user_id:
                    child_target_user_id = self.access.owner(child)
                hydrate_active_task(child, child_target_user_id)
        selected = self.preview.selected()(config, training.get("selected_accessory_ids", []))
        current_cache_key = self.preview.cache(selected) if selected else None
        stale_reason = None
        if self.preview.missing(training, selected):
            stale_reason = "missing_preview_sprite_version"
        elif training.get("preview_cache_key") and current_cache_key and training.get("preview_cache_key") != current_cache_key:
            stale_reason = "clean_sprite_version_changed"
        if stale_reason:
            training = dict(training)
            training.update(
                {
                    "preview_urls": [],
                    "previews": [],
                    "preview_stale_reason": stale_reason,
                    "current_preview_cache_key": current_cache_key,
                }
            )
        return training
