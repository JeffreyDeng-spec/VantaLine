"""Pipeline Agent feedback actions; branch mutations remain inside the task lock."""
from typing import Any
from ..schemas.pipeline import PipelineAgentFeedbackRequest
from .agent_feedback_ports import AgentFeedbackAccess, AgentFeedbackPolicy, AgentFeedbackRuntime


class PipelineAgentFeedback:
    def __init__(self, access: AgentFeedbackAccess, policy: AgentFeedbackPolicy, runtime: AgentFeedbackRuntime):
        self.access = access
        self.policy = policy
        self.runtime = runtime
    def feedback(self, task_id: str, request: PipelineAgentFeedbackRequest) -> dict[str, Any]:
        user = self.access.current_user()()
        config = self.access.scope_config()(self.access.load_config()(), user)
        action = str(request.action or "").strip().lower()
        decision = str(request.decision or action).strip().lower()
        pending_advances: list[str] = []
        with self.runtime.task_lock():
            task = self.access.load_task()(task_id)
            if not task:
                raise self.access.http_error()(status_code=404, detail="流水线任务不存在")
            self.access.require_record_access()(task, user, write=True)
            detection_method = self.policy.normalize_method()(str(task.get("detection_method") or (task.get("params") or {}).get("train_mode") or ""))
            if not self.policy.uses_training()(detection_method):
                raise self.access.http_error()(status_code=409, detail="Only YOLO/YOLO+OCR tasks use Agent/MCP orchestration")
            orchestration = self.runtime.ensure_plan()(task, config)
            feedback_entry = {
                "action": action,
                "decision": decision,
                "message": str(request.message or "").strip()[:500],
                "created_at": self.runtime.now()(),
            }
            orchestration.setdefault("feedback", []).append(feedback_entry)
            if action in {"cancel", "cancelled"} or decision in {"cancel", "cancelled"}:
                orchestration.update({"state": "cancelled", "active_stage": "cancelled", "pause": None, "updated_at": self.runtime.now()()})
                task.update({"status": "stopped", "progress": 100, "last_error": "", "job_note": "Agent/MCP preview flow cancelled.", "updated_at": self.runtime.now()()})
            elif action == "replan" or decision == "replan":
                if self.policy.sprite_flow()(task, config):
                    orchestration = self.runtime.skip_legacy()(task, config, orchestration)
                    orchestration["pause"] = None
                    task["agent_mcp"] = orchestration
                    task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": self.runtime.now()()})
                    self.runtime.mark_advancing()(task)
                    pending_advances.append(task_id)
                else:
                    orchestration = self.runtime.ensure_plan()(task, config, force=True)
                    task["agent_mcp"] = orchestration
                    orchestration = self.runtime.pose_calls()(task, config)
                    tool_config = self.runtime.image_config()()
                    if tool_config.get("configured") and self.runtime.execute_calls()(task, config):
                        task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": self.runtime.now()()})
                    else:
                        self.runtime.pause_task()(
                            task,
                            orchestration,
                            stage="pose_image_generation",
                            reason="Pose plan regenerated; " + str(tool_config.get("message") or "Image generation is not configured."),
                            suggested_actions=["configure_image_generation", "continue_existing_assets", "replan", "cancel"],
                        )
            elif action in {"update_plan", "update"}:
                if self.policy.sprite_flow()(task, config):
                    raise self.access.http_error()(status_code=409, detail="当前训练流程使用实拍高亮抠图，不再支持旧姿态计划编辑")
                if not isinstance(request.updated_plan, dict):
                    raise self.access.http_error()(status_code=400, detail="updated_plan is required")
                orchestration["pose_plan"] = request.updated_plan
                orchestration["state"] = "needs_user_action"
                orchestration["active_stage"] = "pose_image_generation"
                orchestration["updated_at"] = self.runtime.now()()
                self.runtime.pause_task()(
                    task,
                    orchestration,
                    stage="pose_image_generation",
                    reason="Pose plan updated by user; confirm how to proceed.",
                    suggested_actions=["continue_existing_assets", "replan", "cancel"],
                )
            elif action in {"retry_pose_image_generation", "retry"} or decision == "retry_pose_image_generation":
                if self.policy.sprite_flow()(task, config):
                    orchestration = self.runtime.skip_legacy()(task, config, orchestration)
                    orchestration["pause"] = None
                    task["agent_mcp"] = orchestration
                    task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": self.runtime.now()()})
                    self.runtime.mark_advancing()(task)
                    pending_advances.append(task_id)
                else:
                    orchestration["skip_pose_image_generation"] = False
                    orchestration["pause"] = None
                    if self.runtime.execute_calls()(task, config):
                        task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": self.runtime.now()()})
                    elif not orchestration.get("pause"):
                        tool_config = self.runtime.image_config()()
                        self.runtime.pause_task()(
                            task,
                            orchestration,
                            stage="pose_image_generation",
                            reason=str(tool_config.get("message") or "Image generation is not configured."),
                            suggested_actions=["configure_image_generation", "continue_existing_assets", "replan", "cancel"],
                        )
            elif action in {"resume", "continue", "continue_existing_assets"} or decision in {"continue_existing_assets", "use_existing_assets"}:
                orchestration["skip_pose_image_generation"] = True
                orchestration["pause"] = None
                orchestration["updated_at"] = self.runtime.now()()
                if task.get("stage") == "samples" or orchestration.get("active_stage") == "model_training" or decision == "continue_training":
                    orchestration["training_quality_ack"] = True
                    if task.get("stage") == "samples":
                        task["status"] = "completed"
                    self.runtime.mark_advancing()(task)
                    pending_advances.append(task_id)
                else:
                    task.update({"status": "ready", "progress": 0, "last_error": "", "job_note": "", "updated_at": self.runtime.now()()})
                    self.runtime.mark_advancing()(task)
                    pending_advances.append(task_id)
            elif action in {"continue_training", "resume_training"} or decision == "continue_training":
                orchestration["training_quality_ack"] = True
                orchestration["pause"] = None
                if task.get("stage") != "samples":
                    raise self.access.http_error()(status_code=409, detail="Task is not waiting at model training gate")
                task["status"] = "completed"
                self.runtime.mark_advancing()(task)
                pending_advances.append(task_id)
            else:
                raise self.access.http_error()(status_code=400, detail="Unknown Agent/MCP feedback action")
            self.runtime.save_task()(task)
            result = self.runtime.public_task()(task, config)
        for advance_id in pending_advances:
            self.runtime.schedule_advance()(advance_id, user)
        return result
