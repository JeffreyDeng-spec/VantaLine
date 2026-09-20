"""Explicit pose plan policy service without application imports."""
from typing import Any
from .pose_plan_ports import PosePlanIdentity, PosePlanContent, PosePlanRuntime, PosePlanTemplates


class PosePlanPolicy:
    def __init__(self, identity: PosePlanIdentity, content: PosePlanContent, runtime: PosePlanRuntime, templates: PosePlanTemplates) -> None:
        self._identity = identity
        self._content = content
        self._runtime = runtime
        self._templates = templates

    def accessory_pose_plan_prompt_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        profile = item.get("ai_profile") if isinstance(item.get("ai_profile"), dict) else {}
        size = item.get("physical_size") if isinstance(item.get("physical_size"), dict) else {}
        length_mm, width_mm, height_mm = self._content.size()(size)
        sprites = self._content.sprites()(item)
        return {
            "accessory_id": self._identity.uid()(item),
            "object_name": str(item.get("name") or self._identity.uid()(item)),
            "english_name": str(profile.get("english_name") or item.get("english_name") or ""),
            "material_type": self._identity.material()(item),
            "ai_material_hint": str(profile.get("material_type") or ""),
            "description": self._content.bounded()(item.get("description") or profile.get("description") or "", 240),
            "physical_dimensions_mm": {
                "length_mm": round(float(length_mm), 1),
                "width_mm": round(float(width_mm), 1),
                "height_mm": round(float(height_mm), 1),
            },
            "top_view_aspect_ratio": profile.get("top_view_aspect_ratio"),
            "has_transparent_cutout": bool(sprites),
            "conveyor_constraints": (
                "The object rests on a flat horizontal solid chroma-key tabletop. "
            "Gravity points straight down: it cannot float, cannot be propped up by "
            "external supports, and cannot interpenetrate the tabletop."
            ),
            "camera_constraints": (
                "A fixed inspection camera is mounted about 700mm directly above the tabletop "
            "and looks straight down (strict vertical top-down, 90 degrees). Every pose "
            "must be renderable as that same top-down shot at a consistent scale."
            ),
            "single_image_inference_allowed": True,
            "max_poses": self._runtime.max_poses(),
        }

    def pose_plan_system_prompt(self) -> str:
        return (
            "You are a Pose Planner Agent for an industrial visual-inspection training "
        "pipeline. Given one accessory (name, physical dimensions, material, and "
        "reference images), decide the realistic set of STABLE resting poses the part "
        "can take on a flat top-down tabletop, and write an explicit image-"
        "generation instruction for each pose.\n"
        "Think in these steps before answering:\n"
        "1. Identify the object geometry type (e.g. rectangular_case, thin_sheet, "
        "cylinder, bottle, irregular_part).\n"
        "2. List the faces/edges that can naturally and stably contact the tabletop.\n"
        "3. Merge poses that look almost identical from a strict top-down camera into "
        "one.\n"
        "4. Exclude unstable or impossible poses (balancing on a corner/tip, standing "
        "on a knife edge, anything needing external support or that would topple).\n"
        "5. For each remaining pose, write a concrete top-down render instruction: "
        "which contact surface is down, which face is visible from above, orientation "
        "of the long axis, scale, and what to avoid.\n"
        "Rules: prefer 1 to 6 poses for a rigid part; only output poses you believe "
        "are physically stable; set a calibrated confidence (0-1) per pose; when a "
        "single image hides the back/side, you may make a reasonable inference but "
        "lower the confidence and set needs_human_review.\n"
        "Return ONLY a JSON object with this schema (no prose, no markdown):\n"
        "{\n"
        '  "accessory_id": string,\n'
        '  "object_name": string,\n'
        '  "pose_decision_source": "vision_agent",\n'
        '  "estimated_geometry": {"kind": string, "symmetry": [string], '
        '"visible_evidence": string, "uncertainty": "low"|"medium"|"high"},\n'
        '  "pose_count": integer,\n'
        '  "poses": [{"pose_id": string (unique, snake_case), "label": string, '
        '"stable_contact_surface": string, "camera_view": "strict_vertical_top_down", '
        '"generation_prompt": string, "negative_prompt": string, "confidence": number}],\n'
        '  "needs_human_review": boolean,\n'
        '  "review_reason": string\n'
        "}"
        )

    def fallback_accessory_pose_plan(self, item: dict[str, Any]) -> dict[str, Any]:
        base_id = self._identity.sanitize()(self._identity.uid()(item))
        object_kind = self._identity.kind()(item)
        poses: list[dict[str, Any]] = []
        for tmpl in self._templates.poses()(base_id, object_kind):
            poses.append(
                {
                    "pose_id": str(tmpl.get("pose_id")),
                    "label": str(tmpl.get("label")),
                    "stable_contact_surface": str(tmpl.get("stable_contact")),
                    "stable_contact": str(tmpl.get("stable_contact")),
                    "camera_view": "strict_vertical_top_down",
                    "generation_prompt": "",
                    "negative_prompt": "",
                    "confidence": 0.5,
                    "request": self._templates.request()(),
                }
            )
        return {
            "schema_version": self._runtime.version(),
            "accessory_id": self._identity.uid()(item),
            "object_name": str(item.get("name") or self._identity.uid()(item)),
            "pose_decision_source": "rules_fallback",
            "estimated_geometry": {"kind": object_kind, "symmetry": [], "visible_evidence": "", "uncertainty": "unknown"},
            "pose_count": len(poses),
            "poses": poses,
            "needs_human_review": False,
            "review_reason": "",
            "generated_at": self._runtime.now()(),
        }

    def normalize_accessory_pose_plan(self, raw: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        """Guardrail/validation for the Pose Planner Agent output: enforce the JSON
    schema, unique pose ids, pose-count bounds, a light physical-stability check
    and a confidence floor. Falls back to rule templates if nothing usable
    survives. (Agent decides; rules accept.)"""
        fallback = self._templates.fallback()(item)
        if not isinstance(raw, dict):
            return fallback
        poses_raw = raw.get("poses")
        if not isinstance(poses_raw, list) or not poses_raw:
            return fallback
        base_id = self._identity.sanitize()(self._identity.uid()(item))
        unstable = self._content.compile()(r"corner|tip|point|edge[_\s-]?point|balanc|knife|尖|角立|竖立")
        seen: set[str] = set()
        poses: list[dict[str, Any]] = []
        for idx, raw_pose in enumerate(poses_raw):
            if not isinstance(raw_pose, dict):
                continue
            gen = self._content.bounded()(raw_pose.get("generation_prompt") or "", 700)
            if not gen.strip():
                continue
            contact = self._content.bounded()(
                raw_pose.get("stable_contact_surface") or raw_pose.get("stable_contact") or "largest stable surface",
                160,
            )
            if unstable.search(contact.lower()):
                continue
            confidence = self._content.optional_number()(raw_pose.get("confidence"))
            confidence = 0.5 if confidence is None else max(0.0, min(1.0, confidence))
            if confidence < self._runtime.min_confidence():
                continue
            pose_id = self._identity.sanitize()(str(raw_pose.get("pose_id") or "")) or f"pose_{idx + 1}"
            if not pose_id.startswith(base_id):
                pose_id = f"{base_id}_{pose_id}"
            if pose_id in seen:
                continue
            seen.add(pose_id)
            poses.append(
                {
                    "pose_id": pose_id,
                    "label": self._content.bounded()(raw_pose.get("label") or pose_id, 80),
                    "stable_contact_surface": contact,
                    "stable_contact": contact,
                    "camera_view": self._content.bounded()(raw_pose.get("camera_view") or "strict_vertical_top_down", 60),
                    "generation_prompt": gen,
                    "negative_prompt": self._content.bounded()(raw_pose.get("negative_prompt") or "", 500),
                    "confidence": round(confidence, 3),
                    "request": self._templates.request()(),
                }
            )
            if len(poses) >= self._runtime.max_poses():
                break
        if not poses:
            return fallback
        geometry = raw.get("estimated_geometry") if isinstance(raw.get("estimated_geometry"), dict) else {}
        needs_review = bool(raw.get("needs_human_review")) or any(pose["confidence"] < 0.5 for pose in poses)
        return {
            "schema_version": self._runtime.version(),
            "accessory_id": self._identity.uid()(item),
            "object_name": self._content.bounded()(raw.get("object_name") or item.get("name") or self._identity.uid()(item), 120),
            "pose_decision_source": "vision_agent",
            "estimated_geometry": {
                "kind": self._content.bounded()(geometry.get("kind") or self._identity.kind()(item), 60),
                "symmetry": self._content.strings()(geometry.get("symmetry"), max_items=6),
                "visible_evidence": self._content.bounded()(geometry.get("visible_evidence") or "", 200),
                "uncertainty": self._content.bounded()(geometry.get("uncertainty") or "", 40),
            },
            "pose_count": len(poses),
            "poses": poses,
            "needs_human_review": needs_review,
            "review_reason": self._content.bounded()(raw.get("review_reason") or "", 240),
            "generated_at": self._runtime.now()(),
        }
