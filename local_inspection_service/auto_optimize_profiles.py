"""Auto-optimize target profile construction.

The auto-optimize runtime is still part of the monolith, but profile assembly
is isolated here so stale retired feature state cannot leak back into mask
generation through incidental server.py fallbacks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


BoundedText = Callable[[Any, int], str]
MaterialTypeResolver = Callable[[dict[str, Any]], str]


TEXT_MASK_SCOPE = (
    "include the visible card/document/label body and printed surface; "
    "exclude anything outside the physical printed surface boundary"
)
OBJECT_MASK_SCOPE = (
    "include the visible physical object body; "
    "exclude shadows, reflections outside the object, and detachable loose parts"
)


def build_mask_target_profile(
    candidate: dict[str, Any],
    item: dict[str, Any],
    *,
    bounded_text: BoundedText,
    string_list: Callable[..., list[str]],
    accessory_material_type: MaterialTypeResolver,
) -> dict[str, Any]:
    accessory_id = str(candidate.get("accessory_id") or "").strip()
    profile = item.get("ai_profile") if isinstance(item.get("ai_profile"), dict) else {}
    label = bounded_text(
        candidate.get("label")
        or profile.get("name")
        or item.get("name")
        or item.get("label")
        or accessory_id
        or "target accessory",
        120,
    )
    material_type = bounded_text(
        item.get("material_type") or profile.get("material_type") or "",
        32,
    )
    if not material_type and item:
        material_type = accessory_material_type(item)
    visual_signature = bounded_text(
        profile.get("visual_signature")
        or profile.get("description")
        or "",
        360,
    )
    positive_cues = string_list(
        [
            visual_signature,
            *string_list(profile.get("tags"), max_items=4, max_len=80),
        ],
        max_items=8,
        max_len=140,
    )
    negative_cues = string_list(
        [
            *string_list(profile.get("negative_cues"), max_items=5, max_len=140),
        ],
        max_items=8,
        max_len=160,
    )
    default_scope = TEXT_MASK_SCOPE if material_type == "text" else OBJECT_MASK_SCOPE
    return {
        "accessory_id": accessory_id,
        "label": label,
        "material_type": material_type or "unknown",
        "description": bounded_text(profile.get("description") or "", 360),
        "visual_signature": visual_signature,
        "distinguishing_text": string_list(profile.get("distinguishing_text"), max_items=8, max_len=80),
        "positive_cues": positive_cues,
        "negative_cues": negative_cues,
        "mask_scope": bounded_text(default_scope, 220),
    }
