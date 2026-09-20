"""Sprite dimension metadata without application imports."""
from typing import Any



def canonical_pose_family_name(pose_family: str | None) -> str | None:
    family = str(pose_family or "").strip().lower()
    if family in {"lying", "flat", "side", "side-facing"}:
        return "lying"
    if family in {"upright", "standing", "top", "top-view", "top_view", "cap", "endface", "end-face", "top-facing"}:
        return "upright"
    return family or None

def source_object_long_short_metadata(source_size_px: list[int] | tuple[int, int] | None) -> dict[str, Any]:
    try:
        source_w = max(1, int(source_size_px[0] if source_size_px and len(source_size_px) >= 1 else 1))
        source_h = max(1, int(source_size_px[1] if source_size_px and len(source_size_px) >= 2 else 1))
    except (TypeError, ValueError):
        source_w, source_h = 1, 1
    long_axis = "width" if source_w >= source_h else "height"
    short_axis = "height" if long_axis == "width" else "width"
    long_side = max(source_w, source_h)
    short_side = max(1, min(source_w, source_h))
    return {
        "source_visible_width_px": source_w,
        "source_visible_height_px": source_h,
        "source_long_side_px": int(long_side),
        "source_short_side_px": int(short_side),
        "source_long_edge_axis": long_axis,
        "source_short_edge_axis": short_axis,
        "source_long_short_ratio": round(float(long_side) / float(short_side), 6),
        "source_length_width_rule": "source_visible_long_side_is_length_short_side_is_width",
    }

def source_long_short_oriented_px(long_side: int, short_side: int, long_axis: Any) -> list[int]:
    if str(long_axis or "").strip().lower() == "height":
        return [int(short_side), int(long_side)]
    return [int(long_side), int(short_side)]

def canonical_sprite_canvas_size_px(asset: dict[str, Any]) -> tuple[int, int] | None:
    value = asset.get("canonical_asset_dimensions_px") or asset.get("canonical_canvas_size_px")
    if isinstance(value, list) and len(value) >= 2:
        try:
            return max(1, int(value[0])), max(1, int(value[1]))
        except (TypeError, ValueError):
            return None
    return None
