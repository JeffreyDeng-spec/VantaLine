"""Explicit pose render content service without application imports."""
from typing import Any
from .pose_render_ports import PoseRenderReferences, PoseRenderPresentation


class PoseRenderContent:
    def __init__(self, references: PoseRenderReferences, presentation: PoseRenderPresentation) -> None:
        self._references = references
        self._presentation = presentation

    def agent_mcp_pose_reference_content(self, item: dict[str, Any], *, max_images: int = 3) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        content: list[dict[str, Any]] = []
        refs: list[dict[str, Any]] = []
        for ref in self._references.contexts()(item, max_images=max_images):
            if not isinstance(ref, dict):
                continue
            path = self._references.resolve()(ref.get("source_path"))
            if not path.exists():
                continue
            mime_type = str(ref.get("mime_type") or self._references.mime()(path.name)[0] or "image/png")
            data_url = f"data:{mime_type};base64,{self._references.encode()(path.read_bytes()).decode('ascii')}"
            content.append({"type": "image_url", "image_url": {"url": data_url}})
            refs.append(
                {
                    "source_path": str(path),
                    "source_url": self._references.public_url()(path),
                    "sha256": ref.get("sha256") or self._references.digest()(path),
                    "mime_type": mime_type,
                    "width": ref.get("width"),
                    "height": ref.get("height"),
                    "ordinal": ref.get("ordinal"),
                }
            )
        return content, refs

    def agent_mcp_pose_prompt(self, task: dict[str, Any], plan: dict[str, Any], pose: dict[str, Any], chroma_screen: dict[str, Any] | None = None) -> str:
        request = pose.get("request") if isinstance(pose.get("request"), dict) else {}
        screen = self._presentation.screen()(chroma_screen)
        screen_rgb = screen["rgb"]
        screen_hex = str(screen["hex"])
        screen_label = str(screen.get("label") or screen.get("name") or "pure green")
        generation_prompt = str(pose.get("generation_prompt") or "").strip()
        negative_prompt = str(pose.get("negative_prompt") or "").strip()
        parts = [
            "Generate one realistic product-training image for VantaLine visual inspection.",
            f"Accessory: {plan.get('accessory_name') or plan.get('accessory_id')}.",
            f"Object kind: {plan.get('object_kind') or 'generic_object'}.",
            f"Pose id: {pose.get('pose_id')}; label: {pose.get('label')}.",
            f"Stable contact: {pose.get('stable_contact')}.",
        ]
        if generation_prompt:
            # The pose-planner agent already decided the contact surface, visible face
            # and orientation for this pose; render exactly that.
            parts.append(f"Pose plan (decided by the pose-planner agent): {generation_prompt}")
        else:
            parts.append(f"Gravity basis: {pose.get('gravity_basis')}.")
            parts.append(f"Top-down view: {pose.get('conveyor_view')}.")
        parts.append(f"Task: {task.get('name') or task.get('id')}.")
        parts.extend(
            [
                "Scene: place the single accessory on a flat solid chroma-key tabletop with the same solid chroma color filling the entire background.",
                f"Chroma color: exact {screen_label} RGB{tuple(screen_rgb)} / {screen_hex}. The tabletop and all visible background pixels must use this same flat color.",
                "Camera: STRICTLY vertical top-down (bird's-eye), lens pointing straight down at 90 degrees, optical axis perpendicular to the tabletop. No tilt, no perspective, no oblique angle.",
                "The accessory must lie flat on the tabletop obeying gravity in the requested stable rest pose; show only the face that is naturally visible from directly above.",
                "Even, diffuse lighting on the object only. Do not add cast shadows, contact shadows, reflections, gradients, texture, seams, belts, rollers, props, or environment details on the chroma tabletop/background.",
                f"Show exactly one accessory instance, centered, fully inside the frame, on the solid {screen_hex} chroma background.",
                # Keep scale comparable across every pose so the cut-out sprites stay a
                # consistent size for the same accessory.
                "Frame the object so its longest dimension spans roughly 65-75% of the image width; keep this scale consistent across all poses of this accessory.",
                "Do not create a grid, collage, calibration target, target paper, labels, captions, rulers, perspective view, side view, or multiple accessories.",
                "Exclude all movable or detachable secondary components: straps, cords, strings, lanyards, loose cables, tags, labels, packaging ties, and detachable accessories. Render only the main rigid product body.",
            ]
        )
        if negative_prompt:
            parts.append(f"Avoid (negative constraints): {negative_prompt}")
        if request.get("background"):
            parts.append(f"Background style: {request['background']}.")
        if request.get("output_contract"):
            parts.append(f"Output contract: {request['output_contract']}.")
        return "\n".join(str(part) for part in parts if str(part or "").strip())
