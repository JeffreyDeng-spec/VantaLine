"""Explicit pose plan generation service without application imports."""
from typing import Any
from .pose_plan_ports import PosePlanIdentity, PosePlanContent, PosePlanRuntime, PosePlanTemplates, PosePlanProvider, PosePlanMedia, PosePlanCalls


class PosePlanGeneration:
    def __init__(self, identity: PosePlanIdentity, content: PosePlanContent, runtime: PosePlanRuntime, templates: PosePlanTemplates, provider: PosePlanProvider, media: PosePlanMedia, calls: PosePlanCalls) -> None:
        self._identity = identity
        self._content = content
        self._runtime = runtime
        self._templates = templates
        self._provider = provider
        self._media = media
        self._calls = calls

    def generate_accessory_pose_plan(self, item: dict[str, Any], *, allow_provider: bool = True, force: bool = False) -> dict[str, Any] | None:
        """Run (and cache once per accessory) the Pose Planner Agent. Returns None for
    text accessories. The cached plan is reused across tasks so the downstream AI
    pose images are generated a single time and never re-accumulated."""
        if self._identity.material()(item) == "text":
            return None
        existing = item.get("agent_mcp_pose_plan")
        if (
            not force
            and isinstance(existing, dict)
            and existing.get("accessory_id") == self._identity.uid()(item)
            and existing.get("poses")
        ):
            return existing
        settings = self._provider.settings()("training_vision")
        if not allow_provider or not settings.get("configured"):
            plan = self._templates.fallback()(item)
            item["agent_mcp_pose_plan"] = plan
            item["agent_mcp_pose_plan_status"] = {
                "source": "rules_fallback",
                "status": "fallback",
                "message": "AI provider not configured; used rule templates.",
                "updated_at": int(self._runtime.clock()()),
            }
            return plan
        try:
            references = self._provider.call()(
                "accessory.reference.collect",
                {"accessory": item, "max_images": 4},
            )["references"]
        except Exception:
            references = []
        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": self._provider.dumps()(self._calls.payload()(item), ensure_ascii=False)},
        ]
        for ref in references:
            user_content.append(
                {
                    "type": "text",
                    "text": f"REFERENCE_IMAGE (raw photo) for accessory_id={ref['accessory_id']}.",
                }
            )
            user_content.append({"type": "image_url", "image_url": {"url": ref["data_url"], "detail": ref.get("detail", "low")}})
        for sprite in self._content.sprites()(item)[:1]:
            data_url = self._media.encode()(self._media.path()(sprite["path"]), max_side=self._media.max_side(), quality=self._media.quality())
            if data_url:
                user_content.append({"type": "text", "text": "TRANSPARENT_CUTOUT of the same part (background already removed)."})
                user_content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "low"}})
        result = self._provider.call()(
            "provider.gemini.generate_json",
            {
                "provider_config": settings,
                "system_prompt": self._calls.prompt()(),
                "user_content": user_content,
                "max_tokens": 1400,
            },
        )
        if result.get("ok"):
            plan = self._calls.normalize()(result.get("parsed") or {}, item)
            item["agent_mcp_pose_plan"] = plan
            item["agent_mcp_pose_plan_status"] = {
                "source": plan.get("pose_decision_source"),
                "status": "generated",
                "latency_ms": result.get("latency_ms", 0),
                "needs_human_review": plan.get("needs_human_review"),
                "updated_at": int(self._runtime.clock()()),
            }
            return plan
        plan = self._templates.fallback()(item)
        item["agent_mcp_pose_plan"] = plan
        item["agent_mcp_pose_plan_status"] = {
            "source": "rules_fallback",
            "status": "timeout" if result.get("timed_out") else "provider_error",
            "message": self._content.bounded()(result.get("error") or "Pose planner agent failed.", 240),
            "updated_at": int(self._runtime.clock()()),
        }
        return plan

    def ensure_accessory_pose_plan(self, item: dict[str, Any], *, force: bool = False) -> dict[str, Any] | None:
        if self._identity.material()(item) == "text":
            return None
        return self._calls.generate()(item, force=force)
