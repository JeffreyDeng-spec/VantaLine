"""Explicit pose sample preparation service without application imports."""
from typing import Any
from .pose_execution_ports import PoseWorkflowState, PoseWorkflowModels, PoseSampleSteps, PoseWorkflowDiagnostics


class PoseSamplePreparation:
    def __init__(self, state: PoseWorkflowState, models: PoseWorkflowModels, steps: PoseSampleSteps, diagnostics: PoseWorkflowDiagnostics) -> None:
        self._state = state
        self._models = models
        self._steps = steps
        self._diagnostics = diagnostics

    def prepare_agent_mcp_before_sample_generation(self, task: dict[str, Any], config: dict[str, Any]) -> bool:
        orchestration = self._state.current()(task)
        # Select or generate a fixed top-down background plate from the first
        # accessory's environment and reuse it for sample backgrounds.
        try:
            self._steps.background()(task, config)
        except Exception:
            self._diagnostics.print_exception()(file=self._diagnostics.stderr())
        photo_ready, photo_changed = self._steps.photos()(task, config, orchestration)
        if photo_ready:
            if photo_changed:
                self._steps.save()(config)
            return True
        if (orchestration.get("pause") or {}).get("stage") == "pose_image_generation":
            if photo_changed:
                self._steps.save()(config)
            return False
        if self._state.photo_flow()(task, config):
            reason = "实拍高亮抠图素材尚未准备完成；任务流水线不会回退到旧 AI 姿态生成。"
            self._state.pause()(
                task,
                orchestration,
                stage="pose_image_generation",
                reason=reason,
                suggested_actions=["retry_pose_image_generation", "upload_more_reference_photos", "cancel"],
            )
            self._state.stage()(orchestration, "pose_image_generation", "needs_user_action", 0, detail=reason)
            if photo_changed:
                self._steps.save()(config)
            return False
        orchestration = self._steps.register()(task, config)
        if orchestration.get("skip_pose_image_generation"):
            self._steps.materialize()(task, config)
            missing_assets = self._steps.missing()(task, config, orchestration)
            if missing_assets:
                orchestration["skip_pose_image_generation"] = False
                if self._steps.execute()(task, config):
                    self._steps.materialize()(task, config)
                    missing_assets = self._steps.missing()(task, config, orchestration)
                    if not missing_assets:
                        orchestration["state"] = "sample_generation"
                        orchestration["active_stage"] = "sample_generation"
                        orchestration["pause"] = None
                        return True
                if not (orchestration.get("pause") or {}).get("stage") == "pose_image_generation":
                    reason = "继续沿用素材失败：缺少可用于样本生成的规范化/参考素材：" + "、".join(missing_assets[:4])
                    self._state.pause()(
                        task,
                        orchestration,
                        stage="pose_image_generation",
                        reason=reason,
                        suggested_actions=["retry_pose_image_generation", "replan", "cancel"],
                    )
                    self._state.stage()(orchestration, "pose_image_generation", "needs_user_action", 0, detail=reason)
                return False
            orchestration["state"] = "sample_generation"
            orchestration["active_stage"] = "sample_generation"
            orchestration["pause"] = None
            self._state.stage()(orchestration, "pose_image_generation", "skipped", 100, detail="User chose to continue with existing assets.")
            return True
        if self._steps.execute()(task, config):
            self._steps.materialize()(task, config)
            orchestration["state"] = "sample_generation"
            orchestration["active_stage"] = "sample_generation"
            orchestration["pause"] = None
            return True
        if (orchestration.get("pause") or {}).get("stage") == "pose_image_generation":
            return False
        tool_config = self._models.configuration()()
        reason = tool_config.get("message") or "Image generation is not configured; pose-image tool calls are logged but not executed."
        self._state.pause()(
            task,
            orchestration,
            stage="pose_image_generation",
            reason=reason,
            suggested_actions=["configure_image_generation", "continue_existing_assets", "replan", "cancel"],
        )
        return False
