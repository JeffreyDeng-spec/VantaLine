"""Explicit pipeline actions service without application imports."""
from typing import Any
from .pipeline_action_ports import AgentActionState, AgentActionAdvance, AgentActionJobs, AgentActionPolicy, AgentActionPose, AgentActionCalls


class AgentPipelineActions:
    def __init__(self, state: AgentActionState, advance: AgentActionAdvance, jobs: AgentActionJobs, policy: AgentActionPolicy, pose: AgentActionPose, calls: AgentActionCalls) -> None:
        self._state = state
        self._advance = advance
        self._jobs = jobs
        self._policy = policy
        self._pose = pose
        self._calls = calls

    def agent_safe_advance(self,
        task: dict[str, Any], config: dict[str, Any], pending_advances: list[str] | None = None
    ) -> None:
        """Request an advance for a task driven by an Agent decision. The actual work
    is handed to the async per-task runner so it never runs under
    _pipeline_tasks_lock; the caller schedules `pending_advances` after the lock
    is released. (A None collector keeps the old inline behavior as a fallback.)"""
        if pending_advances is not None:
            self._advance.mark()(task)
            task_id = str(task.get("id") or "")
            if task_id and task_id not in pending_advances:
                pending_advances.append(task_id)
            return
        try:
            self._advance.sync()(task)
            self._advance.advance()(task)
        except self._state.http_error_type() as exc:
            orchestration = self._state.orchestration()(task)
            self._state.pause()(
                task,
                orchestration,
                stage=str(orchestration.get("active_stage") or task.get("stage") or "pose_image_generation"),
                reason=self._state.bounded()(exc.detail, 240),
                suggested_actions=["retry_pose_image_generation", "replan", "cancel"],
            )

    def reset_pipeline_task_to_stage(self, task: dict[str, Any], target: str, user: dict[str, Any] | None) -> None:
        linked_job_ids = [
            str(item_id)
            for item_id in (task.get("samples_task_id"), task.get("training_task_id"))
            if str(item_id or "").strip()
        ]
        if user:
            for job_id in linked_job_ids:
                try:
                    self._jobs.delete()(job_id, user, missing_ok=True)
                except Exception:  # noqa: BLE001 - 清理失败不应阻塞回退
                    pass
        task.update(
            {
                "stage": "draft",
                "status": "ready",
                "progress": 0,
                "last_error": "",
                "job_note": "",
                "updated_at": self._state.now()(),
            }
        )
        for key in ("samples_task_id", "training_task_id", "dataset_id"):
            task.pop(key, None)
        orchestration = self._state.orchestration()(task)
        orchestration.update(
            {
                "pause": None,
                "state": "created",
                "active_stage": "created",
                "training_quality_ack": False,
                "last_auto_signature": "",
                "updated_at": self._state.now()(),
            }
        )

    def apply_agent_pipeline_decision(self,
        task: dict[str, Any],
        config: dict[str, Any],
        decision: dict[str, Any],
        user: dict[str, Any] | None,
        *,
        trigger: str = "chat",
        pending_advances: list[str] | None = None,
    ) -> None:
        action = str(decision.get("action") or "reply")
        detection_method = self._policy.normalize()(str(task.get("detection_method") or (task.get("params") or {}).get("train_mode") or ""))
        if not self._policy.uses_training()(detection_method) or action == "reply":
            return
        orchestration = self._state.orchestration()(task)
        now = self._state.now()()
        if action == "cancel":
            orchestration.update({"state": "cancelled", "active_stage": "cancelled", "pause": None, "updated_at": now})
            task.update({"status": "stopped", "progress": 100, "last_error": "", "job_note": "Agent 取消了本次流程。", "updated_at": now})
            return
        if action == "pause_and_ask":
            self._state.pause()(
                task,
                orchestration,
                stage=str(orchestration.get("active_stage") or task.get("stage") or "pose_image_generation"),
                reason=decision.get("message_to_user") or decision.get("reason") or "需要你确认后再继续。",
                suggested_actions=decision.get("suggested_actions") or ["continue_existing_assets", "replan", "cancel"],
            )
            return
        if action == "set_params":
            params = dict(task.get("params") or {})
            params.update(decision.get("params") or {})
            task["params"] = params
            task["updated_at"] = now
            if decision.get("advance_after"):
                self._calls.safe_advance()(task, config, pending_advances)
            return
        if action == "goto_stage":
            target = decision.get("target_stage") or "draft"
            self._calls.reset()(task, target, user)
            if decision.get("params"):
                params = dict(task.get("params") or {})
                params.update(decision.get("params") or {})
                task["params"] = params
            if target == "samples":
                self._calls.safe_advance()(task, config, pending_advances)
            return
        if action == "replan":
            if self._pose.photo_flow()(task, config):
                orchestration = self._pose.skip_legacy()(task, config, orchestration)
                orchestration["pause"] = None
                task["agent_mcp"] = orchestration
                task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": now})
                self._calls.safe_advance()(task, config, pending_advances)
                return
            orchestration = self._pose.plan()(task, config, force=True)
            task["agent_mcp"] = orchestration
            self._pose.ensure_calls()(task, config)
            tool_config = self._pose.config()()
            if tool_config.get("configured") and self._pose.execute()(task, config):
                task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": now})
            else:
                self._state.pause()(
                    task,
                    orchestration,
                    stage="pose_image_generation",
                    reason="姿态方案已重规划；" + str(tool_config.get("message") or "图片生成未配置。"),
                    suggested_actions=["configure_image_generation", "continue_existing_assets", "replan", "cancel"],
                )
            return
        if action == "retry":
            if self._pose.photo_flow()(task, config):
                orchestration = self._pose.skip_legacy()(task, config, orchestration)
                orchestration["pause"] = None
                task["agent_mcp"] = orchestration
                task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": now})
                self._calls.safe_advance()(task, config, pending_advances)
                return
            orchestration["skip_pose_image_generation"] = False
            orchestration["pause"] = None
            if self._pose.execute()(task, config):
                task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": now})
            elif not orchestration.get("pause"):
                tool_config = self._pose.config()()
                self._state.pause()(
                    task,
                    orchestration,
                    stage="pose_image_generation",
                    reason=str(tool_config.get("message") or "图片生成未配置。"),
                    suggested_actions=["configure_image_generation", "continue_existing_assets", "replan", "cancel"],
                )
            return
        if action == "continue_existing_assets":
            orchestration["skip_pose_image_generation"] = True
            orchestration["pause"] = None
            orchestration["updated_at"] = now
            if task.get("stage") == "samples" or orchestration.get("active_stage") == "model_training":
                orchestration["training_quality_ack"] = True
                if task.get("stage") == "samples":
                    task["status"] = "completed"
                self._calls.safe_advance()(task, config, pending_advances)
            else:
                task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": now})
                self._calls.safe_advance()(task, config, pending_advances)
            return
        if action == "continue_training":
            orchestration["training_quality_ack"] = True
            orchestration["pause"] = None
            if task.get("stage") == "samples":
                task["status"] = "completed"
                self._calls.safe_advance()(task, config, pending_advances)
            return
        if action == "advance":
            self._calls.safe_advance()(task, config, pending_advances)
            return
