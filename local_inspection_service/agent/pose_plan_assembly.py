"""Explicit pose plan assembly service without application imports."""
from typing import Any
from .pose_plan_ports import PosePlanIdentity, PosePlanRuntime, PosePlanTemplates, PosePlanCatalog


class PosePlanAssembly:
    def __init__(self, identity: PosePlanIdentity, runtime: PosePlanRuntime, templates: PosePlanTemplates, catalog: PosePlanCatalog) -> None:
        self._identity = identity
        self._runtime = runtime
        self._templates = templates
        self._catalog = catalog

    def build_agent_mcp_pose_plan(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        accessories_by_id = self._catalog.lookup()(config)
        counts = self._catalog.counts()(config, [str(item_id) for item_id in task.get("accessory_ids") or []], task.get("accessory_counts"))
        plans = []
        for item_id in self._catalog.canonical_ids()(config, [str(item_id) for item_id in task.get("accessory_ids") or []]):
            item = accessories_by_id.get(item_id)
            if not item:
                continue
            # Documents never go through pose-image generation: their canonical pages
            # are produced (crop + deskew + paper-size normalize) when the accessory is
            # created, so they are excluded from the pose plan entirely.
            if self._identity.material()(item) == "text":
                continue
            object_kind = self._identity.kind()(item)
            base_id = self._identity.sanitize()(item_id)
            pose_plan = self._catalog.ensure()(item)
            if isinstance(pose_plan, dict) and pose_plan.get("poses"):
                poses = [
                    {
                        "pose_id": str(pose.get("pose_id")),
                        "label": pose.get("label"),
                        "stable_contact": pose.get("stable_contact_surface") or pose.get("stable_contact"),
                        "gravity_basis": "object rests under gravity on its stable contact surface",
                        "conveyor_view": pose.get("camera_view") or "strict_vertical_top_down",
                        "generation_prompt": pose.get("generation_prompt") or "",
                        "negative_prompt": pose.get("negative_prompt") or "",
                        "confidence": pose.get("confidence"),
                        "request": pose.get("request") or self._templates.request()(),
                    }
                    for pose in pose_plan.get("poses") or []
                ]
                plan_source = pose_plan.get("pose_decision_source") or "vision_agent"
                object_kind = (pose_plan.get("estimated_geometry") or {}).get("kind") or object_kind
                needs_review = bool(pose_plan.get("needs_human_review"))
            else:
                poses = self._templates.poses()(base_id, object_kind)
                plan_source = "preview_agent_rules"
                needs_review = False
            plans.append(
                {
                    "accessory_id": item_id,
                    "accessory_name": str(item.get("name") or item_id),
                    "count": int(counts.get(item_id, 1)),
                    "object_kind": object_kind,
                    "plan_source": plan_source,
                    "pose_decision_source": plan_source,
                    "needs_human_review": needs_review,
                    "image_contract": "one_accessory_per_image",
                    "poses": poses,
                }
            )
        pose_count = sum(len(plan.get("poses") or []) for plan in plans)
        return {
            "task_id": task.get("id"),
            "generated_at": self._runtime.now()(),
            "agent": "pose_planner_agent",
            "accessories": plans,
            "pose_count": pose_count,
        }
