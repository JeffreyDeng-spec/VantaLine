"""Run pipeline auto-Agent decisions without owning the Web process registry."""
from typing import Any

from .auto_agent_runtime_ports import (
    AutoAgentDecision, AutoAgentExecution, AutoAgentScheduling, AutoAgentTasks,
)


class PipelineAutoAgentRuntime:
    def __init__(
        self,
        tasks: AutoAgentTasks,
        decision: AutoAgentDecision,
        execution: AutoAgentExecution,
        scheduling: AutoAgentScheduling,
    ) -> None:
        self.tasks = tasks
        self.decision = decision
        self.execution = execution
        self.scheduling = scheduling

    def run(self, task_id: str, user: dict[str, Any] | None) -> None:
        token = self.execution.identity().set(user) if user else None
        try:
            with self.tasks.lock():
                task = self.tasks.load()(task_id)
                if not task or not self.tasks.needs_agent()(task):
                    return
                orchestration = self.tasks.orchestration()(task)
                signature = self.tasks.signature()(task)
                if orchestration.get("last_auto_signature") == signature:
                    return
                if int(orchestration.get("auto_steps") or 0) >= self.tasks.max_steps():
                    self.tasks.pause()(
                        task,
                        orchestration,
                        stage=str(task.get("stage") or "model_training"),
                        reason="自动编排已达到步数上限，请人工确认后再继续。",
                        suggested_actions=["continue_training", "replan", "cancel"],
                    )
                    orchestration["last_auto_signature"] = signature
                    self.tasks.append_conversation()(
                        task,
                        "agent",
                        "自动编排步数已达上限，已暂停等待人工确认。",
                        action="pause_and_ask",
                        source="rules",
                        needs_user=True,
                    )
                    self.tasks.save()(task)
                    return
                snapshot = self.tasks.deepcopy()(task)
            config = self.decision.scope_config()(self.decision.load_config()(), user)
            decision = self.decision.decide()(snapshot, config, user_message=None, trigger="auto")
            pending_advances: list[str] = []
            with self.tasks.lock():
                task = self.tasks.load()(task_id)
                if not task or not self.tasks.needs_agent()(task):
                    return
                orchestration = self.tasks.orchestration()(task)
                if orchestration.get("last_auto_signature") == signature:
                    return
                self.decision.commit()(task, config, user, None, decision, "auto", pending_advances=pending_advances)
                orchestration = self.tasks.orchestration()(task)
                orchestration["last_auto_signature"] = signature
                orchestration["auto_steps"] = int(orchestration.get("auto_steps") or 0) + 1
                orchestration["last_auto_step_at"] = self.decision.now()()
                self.tasks.save()(task)
            for advance_id in pending_advances:
                self.decision.schedule_advance()(advance_id, user)
        except Exception:  # noqa: BLE001 - background auto orchestration only records failures
            self.execution.traceback()(file=self.execution.stderr())
        finally:
            if token is not None:
                self.execution.identity().reset(token)
            with self.scheduling.lock():
                self.scheduling.inflight().discard(task_id)

    def schedule(self, task_ids: list[str], user: dict[str, Any] | None) -> None:
        for task_id in task_ids:
            if not task_id:
                continue
            with self.scheduling.lock():
                if task_id in self.scheduling.inflight():
                    continue
                self.scheduling.inflight().add(task_id)
            self.scheduling.thread()(target=self.scheduling.runner(), args=(task_id, user), daemon=True).start()
