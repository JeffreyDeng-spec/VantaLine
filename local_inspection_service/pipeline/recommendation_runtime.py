"""Run and schedule pipeline recommendation pre-generation with caller-owned state."""
from typing import Any

from .recommendation_runtime_ports import (
    RecommendationExecution, RecommendationScheduling, RecommendationTasks,
)


class PipelineRecommendationRuntime:
    def __init__(
        self,
        tasks: RecommendationTasks,
        execution: RecommendationExecution,
        scheduling: RecommendationScheduling,
    ) -> None:
        self.tasks = tasks
        self.execution = execution
        self.scheduling = scheduling

    def run(self, task_id: str, stage: str, user: dict[str, Any] | None) -> None:
        token = self.execution.identity().set(user) if user else None
        try:
            with self.tasks.lock():
                task = self.tasks.load()(task_id)
                if not task or self.tasks.next_stage()(task) != stage:
                    return
                if self.tasks.ready()(task, stage):
                    return
                accessory_ids = [str(item) for item in task.get("accessory_ids") or []]
                params = task.get("params") if isinstance(task.get("params"), dict) else {}
                sample_count = int(params.get("sample_count") or 0) or None
                signature = self.tasks.signature()(task, stage)
            recommendation = self.execution.recommend()(stage, accessory_ids, sample_count)
            with self.tasks.lock():
                task = self.tasks.load()(task_id)
                if not task or self.tasks.next_stage()(task) != stage:
                    return
                if self.tasks.signature()(task, stage) != signature:
                    return
                task["recommended_params"] = {
                    "stage": stage,
                    "params": recommendation.get("params") or {},
                    "reason": recommendation.get("reason") or "",
                    "source": recommendation.get("source") or "rules",
                    "signature": signature,
                    "created_at": int(self.execution.clock()()),
                }
                task["updated_at"] = int(self.execution.clock()())
                self.tasks.save()(task)
        except Exception:  # noqa: BLE001 - background pre-generation only records failures
            self.execution.traceback()(file=self.execution.stderr())
        finally:
            if token is not None:
                self.execution.identity().reset(token)
            with self.scheduling.lock():
                self.scheduling.inflight().discard(f"{task_id}|{stage}")

    def schedule(self, items: list[tuple[str, str]], user: dict[str, Any] | None) -> None:
        for task_id, stage in items:
            if not task_id or not stage:
                continue
            key = f"{task_id}|{stage}"
            with self.scheduling.lock():
                if key in self.scheduling.inflight():
                    continue
                self.scheduling.inflight().add(key)
            self.scheduling.thread()(
                target=self.scheduling.runner(), args=(task_id, stage, user), daemon=True
            ).start()
