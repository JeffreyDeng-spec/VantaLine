"""Explicit pose call registration service without application imports."""
from typing import Any
from .pose_execution_ports import PoseWorkflowState, PoseWorkflowModels, PoseCallRegistry


class PoseCallRegistration:
    def __init__(self, state: PoseWorkflowState, models: PoseWorkflowModels, registry: PoseCallRegistry) -> None:
        self._state = state
        self._models = models
        self._registry = registry

    def ensure_agent_mcp_pose_tool_calls(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        orchestration = self._state.plan()(task, config)
        if self._state.photo_flow()(task, config):
            self._state.stage()(
                orchestration,
                "pose_image_generation",
                "skipped",
                100,
                detail="Legacy AI pose-image generation skipped; using real-photo photo-highlight sprites.",
            )
            return orchestration
        tool_config = self._models.configuration()()
        status = "pending" if tool_config["configured"] else "missing_configuration"
        accessories_by_id = self._registry.lookup()(config)
        for plan in (orchestration.get("pose_plan") or {}).get("accessories") or []:
            accessory_id = str(plan.get("accessory_id") or "")
            # One-set policy: if an accessory already has its AI pose images (from any
            # earlier task) we never generate them again — even when the local clean
            # sprites still need a (cheap, offline) rebuild. This is what stops the
            # same accessory from re-generating AI images on every task.
            cached_item = accessories_by_id.get(accessory_id)
            if cached_item is not None and self._registry.cached()(cached_item):
                continue
            for pose in plan.get("poses") or []:
                pose_id = str(pose.get("pose_id") or "")
                call_id = self._registry.identifier()(str(task.get("id") or ""), self._registry.tool(), accessory_id, pose_id)
                existing = next(
                    (
                        item
                        for item in orchestration.get("tool_calls") or []
                        if str(item.get("call_id") or "") == call_id and item.get("status") in {"completed", "running"}
                    ),
                    None,
                )
                if existing:
                    continue
                self._registry.upsert()(
                    orchestration,
                    {
                        "call_id": call_id,
                        "tool": self._registry.tool(),
                        "task_id": task.get("id"),
                        "accessory_id": accessory_id,
                        "pose_id": pose_id,
                        "request": pose.get("request") or {},
                        "status": status,
                        "provider": tool_config["provider"],
                        "model": tool_config.get("model") or "",
                        "prompt": "",
                        "source_reference_assets": [],
                        "output_path": "",
                        "output_url": "",
                        "metadata_path": "",
                        "metadata_url": "",
                        "artifact_refs": [],
                        "error": "" if tool_config["configured"] else tool_config["message"],
                    },
                )
        pose_count = int((orchestration.get("pose_plan") or {}).get("pose_count") or 0)
        self._state.stage()(
            orchestration,
            "pose_image_generation",
            "pending" if tool_config["configured"] else "needs_user_action" if not orchestration.get("skip_pose_image_generation") else "skipped",
            0 if not orchestration.get("skip_pose_image_generation") else 100,
            detail=f"{pose_count} pose-image calls logged as {status}.",
        )
        return orchestration
