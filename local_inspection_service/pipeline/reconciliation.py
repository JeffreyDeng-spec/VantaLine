"""Synchronize pipeline state and identify tasks needing background scheduling."""
from typing import Any

from .reconciliation_ports import ReconciliationCalls, ReconciliationPolicy, ReconciliationRegistry


class PipelineReconciliation:
    def __init__(self, policy: ReconciliationPolicy, registry: ReconciliationRegistry, calls: ReconciliationCalls):
        self.policy = policy
        self.registry = registry
        self.calls = calls

    def pipeline_task_decision_signature(self, task: dict[str, Any]) -> str:
        return f"{task.get('stage')}|{task.get('status')}|{int(task.get('progress') or 0)}"

    def pipeline_task_needs_auto_agent(self, task: dict[str, Any]) -> bool:
        if str(task.get("task_kind") or "") == "incoming_material_text":
            return False
        if not task.get("auto_advance"):
            return False
        detection_method = self.policy.normalize()(str(task.get("detection_method") or (task.get("params") or {}).get("train_mode") or ""))
        if not self.policy.uses_training()(detection_method):
            return False
        stage = str(task.get("stage") or "")
        status = str(task.get("status") or "")
        if status == "completed" and stage in {"samples", "training"}:
            return True
        if status == "failed" and stage in {"draft", "samples", "training"}:
            return True
        return False

    def reap_pipeline_advance_zombie(self, task: dict[str, Any]) -> bool:
        """Reset a task left in the advancing state with no live worker thread (e.g.\n    the process restarted mid-advance) so the UI can distinguish working from\n    timed-out and the user can retry. Returns True if the task was modified."""
        if not task.get("advancing"):
            return False
        task_id = str(task.get("id") or "")
        with self.registry.lock():
            if task_id in self.registry.inflight():
                return False
        started = int(task.get("advance_started_at") or 0)
        if started and (int(self.registry.now()()) - started) < self.registry.timeout():
            return False
        task.pop("advancing", None)
        task.pop("advance_started_at", None)
        task["last_error"] = "推进任务超时或中断，已自动终止，请重试。"
        task["job_note"] = "推进已中断，请重试。"
        task["updated_at"] = int(self.registry.now()())
        return True

    def sync_and_auto_advance_pipeline(self, tasks: list[dict[str, Any]]) -> tuple[bool, list[str], list[str]]:
        agent_config = self.calls.load_agent_config()()
        llm_driven = self.calls.supported()(agent_config)
        changed = False
        auto_agent_ids: list[str] = []
        advance_ids: list[str] = []
        # One shared finder so syncing N active tasks does one training_tasks fetch
        # instead of a full-table scan per task.
        find_training_task_for_path = self.calls.training_finder()()
        for task in tasks:
            if self.calls.reap()(task):
                changed = True
            if self.calls.sync()(task, find_training_task_for_path):
                changed = True
            if not self.calls.needs_auto_agent()(task):
                continue
            if llm_driven:
                orchestration = self.calls.orchestration()(task)
                if orchestration.get("last_auto_signature") != self.calls.signature()(task):
                    auto_agent_ids.append(str(task.get("id")))
                continue
            if task.get("status") == "completed" and task.get("stage") in {"samples", "training"}:
                # Route auto-advance through the async runner: no heavy work (incl. the
                # worker upload) runs in the polling path or under _pipeline_tasks_lock.
                advance_ids.append(str(task.get("id")))
        return changed, auto_agent_ids, advance_ids