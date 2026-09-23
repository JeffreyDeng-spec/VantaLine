"""Pipeline list reconciliation and projection with the historical GET write path."""
from typing import Any
from .task_list_ports import TaskListAccess, TaskListReconciliation, TaskListPresentation


class PipelineTaskList:
    def __init__(self, access: TaskListAccess, reconciliation: TaskListReconciliation, presentation: TaskListPresentation):
        self.access = access
        self.reconciliation = reconciliation
        self.presentation = presentation

    def list_tasks(self, user_id: str | None = None) -> dict[str, Any]:
        user = self.access.current_user()()
        target_user_id = user_id if self.access.is_admin()(user) else None
        full_config = self.access.load_config()()
        config = self.access.scope_config()(full_config, user, target_user_id)
        ai_detection_tasks = self.access.load_ai_tasks()()
        auto_agent_ids: list[str] = []
        advance_ids: list[str] = []
        with self.reconciliation.task_lock():
            tasks = self.reconciliation.load_tasks()()
            now = self.reconciliation.monotonic()()
            if now - self.reconciliation.last_sync_at() >= self.reconciliation.min_interval():
                self.reconciliation.set_last_sync_at(now)
                if self.reconciliation.ensure_accessories()(full_config, tasks):
                    self.reconciliation.save_config()(full_config)
                    config = self.access.scope_config()(full_config, user, target_user_id)
                ai_tasks_changed = self.reconciliation.sync_ai_tasks()(tasks, config, user, target_user_id, ai_tasks=ai_detection_tasks)
                ready_ai_tasks_changed = self.reconciliation.sync_ready_ai_tasks()(tasks, config, user, target_user_id)
                auto_defaults_changed = self.reconciliation.normalize_auto_defaults()(tasks)
                changed, auto_agent_ids, advance_ids = self.reconciliation.sync_and_advance()(tasks)
                if changed or ai_tasks_changed or ready_ai_tasks_changed or auto_defaults_changed:
                    self.reconciliation.save_tasks()(tasks)
            visible_tasks = [task for task in tasks if self.access.visible()(task, user, target_user_id)]
            visible_tasks = [
                task
                for task in visible_tasks
                if str(task.get("task_kind") or "") != "incoming_material_text"
                or self.access.incoming_allowed()(task, user)
            ]
            if not self.access.has_permission()(user, "training_pipeline"):
                visible_tasks = [task for task in visible_tasks if str(task.get("task_kind") or "") == "incoming_material_text"]
            recommendation_pregen = self.reconciliation.collect_pregen()(visible_tasks)
        if auto_agent_ids:
            self.presentation.schedule_agent()(auto_agent_ids, user)
        for advance_id in advance_ids:
            self.presentation.schedule_advance()(advance_id, user)
        if recommendation_pregen:
            self.presentation.schedule_pregen()(recommendation_pregen, user)
        ai_task_ids = {str(item.get("id") or "") for item in ai_detection_tasks if str(item.get("id") or "")}
        trained_model_specs = self.presentation.trained_specs()(config)
        auto_optimize_states = self.presentation.optimize_states()()
        auto_optimize_states_by_id = self.presentation.optimize_by_id()(auto_optimize_states)
        return self.presentation.sanitize()({
            "items": [
                self.presentation.public_task()(
                    task,
                    config,
                    ai_task_ids=ai_task_ids,
                    trained_model_specs=trained_model_specs,
                    auto_optimize_states=auto_optimize_states,
                    auto_optimize_states_by_id=auto_optimize_states_by_id,
                    sanitize=False,
                )
                for task in visible_tasks
            ],
            "agent": self.presentation.public_agent_config()(),
            **self.presentation.accessories_payload()(config, user, target_user_id),
        })