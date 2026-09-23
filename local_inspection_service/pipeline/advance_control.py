"""Manual pipeline advance/cancel requests; runner and registry ownership stay external."""
from typing import Any
from .advance_control_ports import AdvanceControlAccess, AdvanceControlRuntime


class PipelineAdvanceController:
    def __init__(self, access: AdvanceControlAccess, runtime: AdvanceControlRuntime):
        self.access = access
        self.runtime = runtime

    def advance(self, task_id: str) -> dict[str, Any]:
        user = self.access.current_user()()
        config = self.access.scope_config()(self.access.load_config()(), user)
        # Validate + mark the task as advancing, then hand the heavy/bounded work to
        # the async per-task runner so this request returns immediately (no global
        # lock, no 504). The runner persists sub-step progress; the UI polls for it.
        with self.runtime.task_lock():
            task = self.access.load_task()(task_id)
            if not task:
                raise self.access.http_error()(status_code=404, detail="流水线任务不存在")
            self.access.require_record_access()(task, user, write=True)
            self.runtime.sync_task()(task)
            already = False
            with self.runtime.registry_lock():
                already = task_id in self.runtime.inflight()
            if not already:
                task["advancing"] = True
                task["advance_started_at"] = int(self.runtime.now()())
                task["job_note"] = "正在推进…"
                task["last_error"] = ""
                task["updated_at"] = int(self.runtime.now()())
                self.runtime.save_task()(task)
            result = self.runtime.public_task()(task, config)
        if not already:
            self.runtime.schedule_advance()(task_id, user)
        return result

    def cancel(self, task_id: str) -> dict[str, Any]:
        user = self.access.current_user()()
        config = self.access.scope_config()(self.access.load_config()(), user)
        with self.runtime.task_lock():
            task = self.access.load_task()(task_id)
            if not task:
                raise self.access.http_error()(status_code=404, detail="流水线任务不存在")
            self.access.require_record_access()(task, user, write=True)
        inflight = self.runtime.cancel_advance()(task_id)
        with self.runtime.task_lock():
            task = self.access.load_task()(task_id)
            if not task:
                raise self.access.http_error()(status_code=404, detail="流水线任务不存在")
            task["auto_advance"] = False
            task["last_error"] = ""
            if inflight:
                task["pause_requested"] = True
                task["job_note"] = "暂停请求已记录；如果当前步骤不可中断，会在当前步骤完成后的检查点停止。"
            else:
                task.pop("advancing", None)
                task.pop("advance_started_at", None)
                task.pop("pause_requested", None)
                if task.get("stage") == "draft" and task.get("status") in {"ready", "running"}:
                    task["status"] = "stopped"
                task["job_note"] = "已暂停，自动推进已关闭。"
            task["updated_at"] = int(self.runtime.now()())
            self.runtime.save_task()(task)
            result = self.runtime.public_task()(task, config)
        return result
