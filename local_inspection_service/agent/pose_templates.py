"""Explicit pose templates service without application imports."""
from typing import Any
from .pose_asset_ports import PoseTemplateIdentity, PoseTemplateCalls


class AgentPoseTemplates:
    def __init__(self, identity: PoseTemplateIdentity, calls: PoseTemplateCalls) -> None:
        self._identity = identity
        self._calls = calls

    def agent_mcp_object_kind(self, item: dict[str, Any]) -> str:
        text = f"{item.get('name') or ''} {item.get('label') or ''} {self._identity.uid()(item)}".lower()
        if self._identity.search()(r"bottle|vial|jar|flask|瓶|罐", text):
            return "bottle"
        if self._identity.search()(r"cube|block|dice|方块|立方|积木", text):
            return "cube"
        if self._identity.kind()(item) == "text" or self._identity.search()(r"thin|card|label|sheet|manual|tag|片|纸|标签|说明书|卡", text):
            return "thin_object"
        return "generic_object"

    def agent_mcp_pose_request(self) -> dict[str, Any]:
        return {
            "subject_count": 1,
            "target_paper": False,
            "grid_layout": False,
            "background": "solid_chroma_key_tabletop_top_down",
            "camera": "strict_vertical_top_down_90deg",
            "output_contract": "one_accessory_per_image",
        }

    def agent_mcp_pose_templates(self, base_id: str, object_kind: str) -> list[dict[str, Any]]:
        templates: dict[str, list[tuple[str, str, str, str, str]]] = {
            "cube": [
                ("face_a_down", "one square face flat on tabletop", "cube rests stably on any face", "top face visible with slight side edge", "face_a_down"),
                ("face_b_down", "adjacent square face flat on tabletop", "rotated cube exposes a different face", "alternate face visible", "face_b_down"),
                ("face_c_down", "third square face flat on tabletop", "third axis face can contact tabletop", "third face visible", "face_c_down"),
            ],
            "bottle": [
                ("upright", "base on tabletop", "flat base can stand vertically", "cap/top footprint visible", "upright_base_down"),
                ("horizontal_side", "curved side contacts tabletop", "bottle can lie on side after falling", "long body silhouette visible", "horizontal_side_down"),
            ],
            "thin_object": [
                ("face_up", "back face on tabletop", "thin object settles flat", "front face visible", "face_up"),
                ("face_down", "front face on tabletop", "thin object may flip but remains flat", "back face visible", "face_down"),
            ],
            "generic_object": [
                ("primary_rest", "largest stable surface on tabletop", "object settles on broadest support area", "primary silhouette visible", "primary_resting_pose"),
                ("side_rest", "secondary side surface on tabletop", "secondary plausible rest pose", "side silhouette visible", "side_resting_pose"),
            ],
        }
        result = []
        for suffix, stable_contact, gravity_basis, conveyor_view, label in templates.get(object_kind, templates["generic_object"]):
            result.append(
                {
                    "pose_id": f"{base_id}_{suffix}",
                    "label": label,
                    "stable_contact": stable_contact,
                    "gravity_basis": gravity_basis,
                    "conveyor_view": conveyor_view,
                    "request": self._calls.request()(),
                }
            )
        return result
