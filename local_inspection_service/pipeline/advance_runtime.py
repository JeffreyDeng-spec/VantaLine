"""Run, queue and cancel pipeline advances with caller-owned task storage and registry."""
import threading
from typing import Any

from .advance_runtime_ports import AdvanceExecution, AdvancePolicy, AdvanceScheduling, AdvanceTasks


class PipelineAdvanceRuntime:
    def __init__(
        self,
        tasks: AdvanceTasks,
        policy: AdvancePolicy,
        execution: AdvanceExecution,
        scheduling: AdvanceScheduling,
    ) -> None:
        self.tasks = tasks
        self.policy = policy
        self.execution = execution
        self.scheduling = scheduling

    def guarded(
        self, task: dict[str, Any], config: dict[str, Any], cancel_event: "threading.Event | None" = None
    ) -> None:
        'Advance one stage, converting precondition/runtime failures into a paused\n    state with a clear reason (mirrors the previous agent_safe_advance UX) so the\n    async runner never crashes and the user always sees why a task stopped.'
        try:
            self.tasks.sync()(task)
            self.policy.advance()(task, cancel_event=cancel_event)
        except self.policy.cancelled_error():
            raise
        except self.policy.http_error() as exc:
            orchestration = self.policy.orchestration()(task)
            self.policy.pause()(
                task,
                orchestration,
                stage=str(orchestration.get("active_stage") or task.get("stage") or "pose_image_generation"),
                reason=self.policy.bounded_text()(exc.detail, 240),
                suggested_actions=["retry_pose_image_generation", "replan", "cancel"],
            )

    def run(self, task_id: str, user: dict[str, Any] | None) -> None:
        token = self.execution.identity().set(user) if user else None
        try:
            with self.scheduling.registry_lock():
                cancel_event = self.scheduling.cancel_events().get(task_id) or self.scheduling.event()()
            with self.tasks.lock():
                task = self.tasks.load()(task_id)
                if not task:
                    return
                self.tasks.sync()(task)
                task["advancing"] = True
                if not task.get("advance_started_at"):
                    task["advance_started_at"] = int(self.execution.clock()())
                snapshot = self.tasks.deepcopy()(task)
                self.tasks.save()(task)
            config = self.execution.scope_config()(self.execution.load_config()(), user)
            try:
                self.policy.guarded()(snapshot, config, cancel_event)
            except self.policy.cancelled_error():
                self.execution.print()(f"[pipeline.advance] task={task_id} cancelled mid-advance", flush=True)
                with self.tasks.lock():
                    stored = self.tasks.load()(task_id)
                    if stored:
                        stored.pop("advancing", None)
                        stored.pop("advance_started_at", None)
                        stored.pop("pause_requested", None)
                        stored["auto_advance"] = False
                        stored["status"] = "stopped" if stored.get("stage") == "draft" else stored.get("status", "stopped")
                        stored["job_note"] = "已暂停，自动推进已关闭。"
                        stored["last_error"] = ""
                        stored["updated_at"] = int(self.execution.clock()())
                        self.tasks.save()(stored)
                return
            except Exception:  # noqa: BLE001 - failed advance remains retryable
                self.execution.traceback()(file=self.execution.stderr())
                snapshot["last_error"] = "推进任务时发生内部错误，请稍后重试。"
                snapshot["updated_at"] = int(self.execution.clock()())
            snapshot.pop("advancing", None)
            snapshot.pop("advance_started_at", None)
            if cancel_event.is_set():
                snapshot.pop("pause_requested", None)
                snapshot["auto_advance"] = False
                snapshot["job_note"] = "已在当前步骤完成后暂停，自动推进已关闭。"
                snapshot["last_error"] = ""
            with self.tasks.lock():
                stored = self.tasks.load()(task_id)
                if not stored:
                    return
                stored.clear()
                stored.update(snapshot)
                self.tasks.save()(stored)
        except Exception:  # noqa: BLE001 - background advance only records failures
            self.execution.traceback()(file=self.execution.stderr())
        finally:
            if token is not None:
                self.execution.identity().reset(token)
            with self.scheduling.registry_lock():
                self.scheduling.inflight().discard(task_id)
                self.scheduling.cancel_events().pop(task_id, None)

    def schedule(self, task_id: str, user: dict[str, Any] | None) -> bool:
        'Enqueue an async advance for a task. Idempotent: if a thread is already\n    advancing this task, returns False without stacking a second one.'
        if not task_id:
            return False
        with self.scheduling.registry_lock():
            if task_id in self.scheduling.inflight():
                return False
            self.scheduling.inflight().add(task_id)
            self.scheduling.cancel_events()[task_id] = self.scheduling.event()()
        self.scheduling.thread()(target=self.scheduling.runner(), args=(task_id, user), daemon=True).start()
        return True

    def cancel(self, task_id: str) -> bool:
        'Signal a running advance worker to stop at the next checkpoint. Returns True\n    if a worker was inflight.'
        if not task_id:
            return False
        with self.scheduling.registry_lock():
            event = self.scheduling.cancel_events().get(task_id)
            inflight = task_id in self.scheduling.inflight()
            if event is not None:
                event.set()
        return inflight
