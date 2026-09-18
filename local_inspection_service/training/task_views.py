"""Training task projection and visibility-filtered refresh without request-global identity."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from .task_lifecycle import training_task_uses_worker

Record = dict[str, Any]


@dataclass(frozen=True)
class TrainingViewAccess:
    enrich: Callable[[Record], Record]
    sanitize: Callable[[], Callable[[Record], Record]]
    visible: Callable[[Record, Record, str | None], bool]


class TrainingTaskViews:
    def __init__(self, records: Callable[[], list[Record]], refresh: Callable[[Record], Record], access: TrainingViewAccess):
        self.records, self.refresh, self.access = records, refresh, access

    def public_training_task(self, task: dict[str, Any]) -> dict[str, Any]:
        copy = self.access.sanitize()(self.access.enrich(task))
        command = copy.get("training_command") if isinstance(copy.get("training_command"), list) else []
        if not copy.get("epochs"):
            epoch_arg = next((str(item).split("=", 1)[1] for item in command if str(item).startswith("epochs=")), None)
            if epoch_arg:
                try:
                    copy["epochs"] = int(epoch_arg)
                except ValueError:
                    pass
        if not copy.get("image_size"):
            image_size_arg = next((str(item).split("=", 1)[1] for item in command if str(item).startswith("imgsz=")), None)
            if image_size_arg:
                try:
                    copy["image_size"] = int(image_size_arg)
                except ValueError:
                    pass
        copy.setdefault("candidate_id", copy.get("job_id"))
        copy.setdefault("candidate_name", copy.get("label") or "训练任务")
        copy.setdefault("task_id", copy.get("job_id"))
        copy.setdefault("progress", 0)
        copy.setdefault("total_epochs", copy.get("epochs") or 0)
        copy.setdefault("current_epoch", copy.get("epochs") if copy.get("status") == "completed" and copy.get("action") == "train_model" else 0)
        copy.setdefault("label", copy.get("label") or "训练任务")
        copy["queue_kind"] = "training"
        return copy

    def public_refreshed_training_task(self, task: dict[str, Any], *, allow_remote_refresh: bool = False) -> dict[str, Any]:
        if training_task_uses_worker(task):
            public = self.public_training_task(task)
            public["executor_retired"] = True
            public["remote_refresh_retired"] = True
            public.setdefault("note", "历史 Windows-worker 训练记录仅保留只读展示；生产训练执行已切换为 RunPod。")
            return public
        task = self.refresh(task)
        return self.public_training_task(task)

    def list_training_tasks(self,
        user: dict[str, Any] | None = None,
        target_user_id: str | None = None,
        *,
        allow_remote_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for task in self.records():
            if user and not self.access.visible(task, user, target_user_id):
                continue
            tasks.append(self.public_refreshed_training_task(task, allow_remote_refresh=allow_remote_refresh))
        return tasks
