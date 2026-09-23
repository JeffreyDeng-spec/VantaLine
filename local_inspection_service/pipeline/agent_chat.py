"""Pipeline Agent chat orchestration; decision runs once between two task reads."""
from typing import Any
from .agent_chat_ports import AgentChatAccess, AgentChatRuntime


class PipelineAgentChat:
    def __init__(self, access: AgentChatAccess, runtime: AgentChatRuntime):
        self.access = access
        self.runtime = runtime

    def chat(self, task_id: str, request: Any) -> dict[str, Any]:
        user = self.access.current_user()()
        config = self.access.scope_config()(self.access.load_config()(), user)
        message = self.access.bounded_text()(request.message, 1000)
        if not message:
            raise self.access.http_error()(status_code=400, detail="消息内容不能为空")
        with self.runtime.task_lock():
            task = self.access.load_task()(task_id)
            if not task:
                raise self.access.http_error()(status_code=404, detail="流水线任务不存在")
            self.access.require_record_access()(task, user, write=True)
            detection_method = self.runtime.normalize_method()(str(task.get("detection_method") or (task.get("params") or {}).get("train_mode") or ""))
            if not self.runtime.uses_training()(detection_method):
                raise self.access.http_error()(status_code=409, detail="该任务使用 AI 检测，建档完成即可直接使用，无需 Agent 训练编排。")
            snapshot = self.runtime.deepcopy()(task)
        decision = self.runtime.decide()(snapshot, config, user_message=message, trigger="chat")
        pending_advances: list[str] = []
        with self.runtime.task_lock():
            task = self.access.load_task()(task_id)
            if not task:
                raise self.access.http_error()(status_code=404, detail="流水线任务不存在")
            self.access.require_record_access()(task, user, write=True)
            self.runtime.commit_turn()(task, config, user, message, decision, "chat", pending_advances=pending_advances)
            self.runtime.save_task()(task)
            result = self.runtime.public_task()(task, config)
        for advance_id in pending_advances:
            self.runtime.schedule_advance()(advance_id, user)
        return result