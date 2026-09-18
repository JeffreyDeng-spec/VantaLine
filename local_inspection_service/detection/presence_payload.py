"""Presence request payloads through explicit, per-expression formatting capabilities."""
from collections.abc import Callable
from typing import Any, Protocol


class StringList(Protocol):
    def __call__(self, value: Any, fallback: list[str] | None = None, *,
                 max_items: int = 12, max_len: int = 96) -> list[str]: ...


BoundedText = Callable[[Any, int], str]


class PresencePayload:
    def __init__(self, strings: Callable[[], StringList], text: Callable[[], BoundedText]):
        self.strings, self.text = strings, text

    def ai_detection_task_payload(self, required_accessories: list[dict[str, Any]]) -> dict[str, Any]:
        payload_accessories = []
        for required in required_accessories:
            try:
                expected_count = max(1, int(required.get("expected_count") or 1))
            except (TypeError, ValueError):
                expected_count = 1
            profile = required.get("profile") if isinstance(required.get("profile"), dict) else {}
            text_cues = self.strings()(profile.get("distinguishing_text"), max_items=6, max_len=64)
            tags = self.strings()(profile.get("tags"), max_items=5, max_len=40)
            visual_signature = self.text()(profile.get("visual_signature") or profile.get("description"), 180)
            payload_accessories.append(
                {
                    "accessory_id": str(required.get("accessory_id") or ""),
                    "name": self.text()(required.get("name") or required.get("label") or required.get("accessory_id"), 80),
                    "expected_count": expected_count,
                    "material_type": self.text()(required.get("material_type") or profile.get("material_type"), 32),
                    "visual_cue": visual_signature,
                    "text_cues": text_cues,
                    "tags": tags,
                }
            )
        return {
            "task": {
                "policy": "presence_by_accessory_profile",
                "expected_latency_seconds": 5,
                "decision_rule": "passed is true only when every required accessory is present at exactly expected_count; undercounts and overcounts fail.",
                "output_mode": "compact",
                "required_accessories": payload_accessories,
            },
            "output_contract": {
                "detections": "Array of {accessory_id,label,present,confidence,count,evidence}. Count is optional unless multiple visible instances matter.",
                "rule": "Object with counts keyed by accessory_id.",
            },
        }
