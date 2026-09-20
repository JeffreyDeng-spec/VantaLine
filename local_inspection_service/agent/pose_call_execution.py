"""Explicit pose call execution service without application imports."""
from typing import Any
from .pose_execution_ports import PoseWorkflowState, PoseWorkflowModels, PoseCallRegistry, PoseCallContent, PoseCallPresentation


class PoseCallExecution:
    def __init__(self, state: PoseWorkflowState, models: PoseWorkflowModels, registry: PoseCallRegistry, content: PoseCallContent, presentation: PoseCallPresentation) -> None:
        self._state = state
        self._models = models
        self._registry = registry
        self._content = content
        self._presentation = presentation

    def execute_agent_mcp_pose_tool_calls(self, task: dict[str, Any], config: dict[str, Any]) -> bool:
        orchestration = self._state.plan()(task, config)
        if self._state.photo_flow()(task, config):
            self._state.skip_legacy()(task, config, orchestration)
            self._state.stage()(
                orchestration,
                "pose_image_generation",
                "skipped",
                100,
                detail="Legacy AI pose-image generation disabled for real-photo training flow.",
            )
            return True
        tool_config = self._models.configuration()()
        orchestration.setdefault("tool_config", {})["pose_image_generation"] = tool_config
        if not tool_config.get("configured"):
            return False
        settings = self._models.settings()()
        settings["model"] = tool_config["model"]
        settings["timeout_seconds"] = tool_config["timeout_seconds"]
        provider = self._models.provider()(settings)
        accessories_by_id = self._registry.lookup()(config)
        calls = [
            call
            for call in orchestration.get("tool_calls") or []
            if call.get("tool") == self._registry.tool() and call.get("status") not in {"completed", "skipped"}
        ]
        if not calls:
            return True
        completed = 0
        total = len(calls)
        provider_label = str(tool_config.get("provider_label") or "image provider")
        provider_key = str(tool_config.get("provider") or "image_generation")
        self._state.stage()(orchestration, "pose_image_generation", "running", 5, detail=f"Generating {total} pose images with {provider_label}.")
        for call in calls:
            accessory_id = str(call.get("accessory_id") or "")
            item = accessories_by_id.get(accessory_id)
            plan = next(
                (plan for plan in (orchestration.get("pose_plan") or {}).get("accessories") or [] if str(plan.get("accessory_id") or "") == accessory_id),
                {},
            )
            pose = next((pose for pose in plan.get("poses") or [] if str(pose.get("pose_id") or "") == str(call.get("pose_id") or "")), {})
            reference_content, reference_assets = self._content.references()(item or {}, max_images=3)
            chroma_screen = self._content.chroma()(item or {})
            prompt = self._content.prompt()(task, plan, pose, chroma_screen)
            call.update(
                {
                    "status": "running",
                    "provider": provider_key,
                    "model": tool_config["model"],
                    "prompt": prompt,
                    "chroma_screen": chroma_screen,
                    "source_reference_assets": reference_assets,
                    "updated_at": self._presentation.now()(),
                    "error": "",
                }
            )
            try:
                result = provider.generate_image(prompt, reference_content, model=tool_config["model"])
                artifact = self._content.artifact()(task, call, result, prompt=prompt, reference_assets=reference_assets)
            except self._models.error() as exc:
                call.update({"status": "failed", "error": self._presentation.bounded()(str(exc), 240), "updated_at": self._presentation.now()()})
                self._state.pause()(
                    task,
                    orchestration,
                    stage="pose_image_generation",
                    reason=f"{provider_label} image generation failed: {self._presentation.bounded()(exc, 200)}",
                    suggested_actions=["retry_pose_image_generation", "continue_existing_assets", "replan", "cancel"],
                )
                self._state.stage()(orchestration, "pose_image_generation", "failed", max(5, int(completed * 100 / max(total, 1))), detail=str(exc)[:220])
                return False
            call.update(
                {
                    "status": "completed",
                    "output_path": artifact["output_path"],
                    "output_url": artifact["output_url"],
                    "metadata_path": artifact["metadata_path"],
                    "metadata_url": artifact["metadata_url"],
                    "artifact_refs": [artifact["output_url"], artifact["metadata_url"]],
                    "sha256": artifact["sha256"],
                    "latency_ms": artifact["latency_ms"],
                    "usage_metadata": artifact["usage_metadata"],
                    "chroma_screen": artifact.get("chroma_screen") or chroma_screen,
                    "proxy_used": bool((artifact.get("proxy") or {}).get("used")),
                    "proxy_source_name": (artifact.get("proxy") or {}).get("source_name") or "",
                    "proxy_url": (artifact.get("proxy") or {}).get("url") or "",
                    "proxy_auto_local": bool((artifact.get("proxy") or {}).get("auto_local")),
                    "generated_source_metadata": artifact["generated_source_metadata"],
                    "updated_at": self._presentation.now()(),
                    "error": "",
                }
            )
            completed += 1
            self._state.stage()(orchestration, "pose_image_generation", "running", min(99, int(completed * 100 / max(total, 1))), detail=f"{completed}/{total} pose images generated.")
        orchestration["state"] = "pose_image_generation_completed"
        orchestration["active_stage"] = "sample_generation"
        orchestration["pause"] = None
        self._state.stage()(orchestration, "pose_image_generation", "completed", 100, detail=f"{completed} pose images generated with {provider_label}.")
        return True
