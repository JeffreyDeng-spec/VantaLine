"""Existing auto-optimization mask prompts with explicit dependency ownership."""
from dataclasses import dataclass
from typing import Any
import json

from .auto_optimization_mask_ports import AutoOptimizationMaskPromptPorts


@dataclass(frozen=True)
class AutoOptimizationMaskPrompts:
    ports: AutoOptimizationMaskPromptPorts

    def auto_optimize_mask_system_prompt(self) -> str:
        return "\n".join(
            [
                "You are VantaLine's automatic dataset mask generator for production inspection images.",
                "Your only job is to convert the attached inspection image into a strict RGB segmentation mask for YOLO bbox labeling.",
                "Return exactly one RGB image with the same aspect ratio as the input image.",
                "Use only exact black RGB(0,0,0) plus the exact target colors specified in the user task JSON.",
                "Every non-target pixel must be exact black RGB(0,0,0).",
                "Do not output natural images, enhanced photos, labels, text, arrows, bounding boxes, outlines, gradients, feathering, shadows, or background colors.",
                "Never invent a target from its profile. The profile is only identification context for objects actually visible in the current image.",
                "If a target is absent or uncertain, leave its assigned color unused.",
                "Each pixel may belong to at most one target color.",
                "Keep masks tight to the visible physical outer contour of each target.",
            ]
        )

    def auto_optimize_mask_owner_user(self, sample: dict[str, Any]) -> dict[str, Any]:
        owner_id = str(sample.get("owner_user_id") or self.ports.LEGACY_OWNER_ID())
        return {
            "id": owner_id,
            "username": str(sample.get("owner_username") or owner_id),
            "role": "admin",
        }

    def auto_optimize_accessory_lookup_for_sample(self, sample: dict[str, Any]) -> dict[str, dict[str, Any]]:
        owner_user = self.ports.auto_optimize_mask_owner_user()(sample)
        try:
            config = self.ports.scope_config_for_user()(self.ports.load_config()(), owner_user)
            return self.ports.accessory_lookup_by_id()(config)
        except Exception:
            return self.ports.accessory_lookup_by_id()(self.ports.load_config()())

    def auto_optimize_mask_target_profile(self, candidate: dict[str, Any], accessories_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
        accessory_id = str(candidate.get("accessory_id") or "").strip()
        item = accessories_by_id.get(accessory_id) or {}
        return self.ports.build_mask_target_profile()(
            candidate,
            item,
            bounded_text=self.ports.bounded_text(),
            string_list=self.ports.string_list(),
            accessory_material_type=self.ports.accessory_material_type(),
        )

    def auto_optimize_mask_target_payload(self, item: dict[str, Any], index: int) -> dict[str, Any]:
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
        palette = item.get("palette") if isinstance(item.get("palette"), dict) else {}
        accessory_id = str(candidate.get("accessory_id") or profile.get("accessory_id") or "")
        label = self.ports.bounded_text()(candidate.get("label") or profile.get("label") or accessory_id or f"target {index}", 120)
        rgb = palette.get("rgb")
        if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
            rgb_payload = [int(max(0, min(255, value))) for value in rgb]
        else:
            rgb_payload = []
        return {
            "index": index,
            "accessory_id": accessory_id,
            "label": label,
            "assigned_color": {
                "name": str(palette.get("name") or ""),
                "hex": str(palette.get("hex") or ""),
                "rgb": rgb_payload,
            },
            "ai_profile": {
                "material_type": profile.get("material_type") or "unknown",
                "visual_signature": profile.get("visual_signature") or "",
                "distinguishing_text": profile.get("distinguishing_text") if isinstance(profile.get("distinguishing_text"), list) else [],
                "positive_cues": profile.get("positive_cues") if isinstance(profile.get("positive_cues"), list) else [],
                "negative_cues": profile.get("negative_cues") if isinstance(profile.get("negative_cues"), list) else [],
            },
            "mask_scope": profile.get("mask_scope") or "",
        }

    def auto_optimize_mask_user_prompt(self,
        assignments: list[dict[str, Any]],
        *,
        input_w: int,
        input_h: int,
        task_type: str = "multi_class_segmentation_mask",
    ) -> str:
        targets = [self.ports.auto_optimize_mask_target_payload()(item, index) for index, item in enumerate(assignments, 1)]
        task = {
            "task_type": task_type,
            "purpose": "automatic_yolo_bbox_labeling",
            "prompt_mode": self.ports.AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION(),
            "input_image": {
                "dimensions": f"{int(input_w)}x{int(input_h)}",
                "return_same_aspect_ratio": True,
            },
            "targets": targets,
            "instance_policy": {
                "if_multiple_instances": "mask only the clearest complete instance for each target",
                "if_absent_or_uncertain": "leave that target color unused",
            },
            "color_policy": {
                "background": "#000000",
                "strict_exact_colors_only": True,
                "no_color_mixing": True,
            },
        }
        return "\n".join(
            [
                "USER_TASK_JSON:",
                json.dumps(task, ensure_ascii=False, indent=2),
                "Generate the mask for the attached inspection image using the system rules and this JSON task only.",
            ]
        )

    def auto_optimize_multicolor_mask_prompt(self, assignments: list[dict[str, Any]], *, input_w: int = 0, input_h: int = 0) -> str:
        target_lines: list[str] = []
        for index, item in enumerate(assignments, 1):
            candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
            profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
            label = self.ports.bounded_text()(str(candidate.get("label") or candidate.get("accessory_id") or f"target {index}"), 120)
            palette = item.get("palette") if isinstance(item.get("palette"), dict) else {}
            target_lines.append(f"{index}. {label}: exact {palette.get('name')} {palette.get('hex')}")
            description = self.ports.bounded_text()(str(profile.get("description") or ""), 260)
            if description:
                target_lines.append(f"   description: {description}")
        return "\n".join(
            [
                "Create a strict multi-class segmentation highlight map for the attached production inspection photo.",
                "This is for automatic YOLO bbox labeling, not creative image generation.",
                "Preserve the exact input camera framing and aspect ratio.",
                "Output one RGB image using only black background plus the exact target colors listed below.",
                "Target color map:",
                *target_lines,
                "Rules:",
                "- pixels belonging to each visible target accessory must use only its assigned exact color;",
                "- every other pixel must be exact black RGB(0,0,0);",
                "- do not use gradients, feathering, text, boxes, labels, shadows, or background colors;",
                "- keep each mask tight to the visible physical outer contour;",
                "- highlight only the main rigid body of each target accessory;",
                "- do not highlight movable or detachable parts: straps, lanyards, strings, cords, cables, loose tags, packaging ties, or detachable accessories;",
                "- if a listed target is absent or uncertain, leave its color unused;",
                "- if multiple target instances are visible, highlight only the clearest complete instance for that target;",
                "- avoid color mixing between adjacent accessories; one pixel may belong to only one target color.",
            ]
        )
