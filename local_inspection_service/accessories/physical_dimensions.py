"""Accessory physical sizes and profile dimensions."""
from typing import Any
from .physical_dimension_ports import DimensionValues, DimensionUpdates

class AccessoryDimensions:
    def __init__(self, values: DimensionValues, updates: DimensionUpdates) -> None:
        self._values = values
        self._updates = updates

    def physical_size_payload(self,
        material_type: str,
        paper_preset: str = "A4",
        paper_width_mm: Any = None,
        paper_height_mm: Any = None,
        object_length_mm: Any = None,
        object_width_mm: Any = None,
        object_height_mm: Any = None,
    ) -> dict[str, Any]:
        if material_type == "text":
            preset = paper_preset if paper_preset in self._values.papers() else "custom"
            default_w, default_h = self._values.papers().get(preset, self._values.papers()["A4"])
            if preset in self._values.papers():
                width_mm, height_mm = default_w, default_h
            else:
                width_mm = self._values.number()(paper_width_mm) or default_w
                height_mm = self._values.number()(paper_height_mm) or default_h
            return {
                "kind": "paper",
                "preset": preset,
                "width_mm": width_mm,
                "height_mm": height_mm,
            }
        return {
            "kind": "object",
            "length_mm": self._values.number()(object_length_mm) or self._values.objects()["length_mm"],
            "width_mm": self._values.number()(object_width_mm) or self._values.objects()["width_mm"],
            "height_mm": self._values.number()(object_height_mm) or self._values.objects()["height_mm"],
        }

    def ai_profile_dimensions_from_physical_size(self, physical_size: dict[str, Any] | None) -> dict[str, Any]:
        size = physical_size if isinstance(physical_size, dict) else {}
        if size.get("kind") == "paper":
            width = self._values.number()(size.get("width_mm")) or 210.0
            height = self._values.number()(size.get("height_mm")) or 297.0
            return {"length_mm": round(max(width, height), 2), "width_mm": round(min(width, height), 2), "height_mm": 0.3}
        length = self._values.number()(size.get("length_mm")) or self._values.objects()["length_mm"]
        width = self._values.number()(size.get("width_mm")) or self._values.objects()["width_mm"]
        height = self._values.number()(size.get("height_mm")) or self._values.objects()["height_mm"]
        return {"length_mm": round(length, 2), "width_mm": round(width, 2), "height_mm": round(height, 2)}

    def ai_profile_top_view_aspect_ratio(self, dimensions: dict[str, Any] | None) -> float:
        dims = dimensions if isinstance(dimensions, dict) else {}
        length = self._values.number()(dims.get("length_mm")) or 0.0
        width = self._values.number()(dims.get("width_mm")) or 0.0
        if length <= 0 or width <= 0:
            return 1.0
        return round(max(length, width) / max(1e-6, min(length, width)), 3)

    def normalize_ai_profile_dimensions(self, raw: Any, fallback: dict[str, Any]) -> dict[str, Any]:
        raw_dict = raw if isinstance(raw, dict) else {}
        fallback_dict = fallback if isinstance(fallback, dict) else {}
        result: dict[str, Any] = {}
        for key in ("length_mm", "width_mm", "height_mm"):
            value = self._values.number()(raw_dict.get(key))
            result[key] = round(value, 2) if value else float(fallback_dict.get(key) or 0.0)
        return result

    def apply_ai_profile_dimensions_to_physical_size(self, item: dict[str, Any], dimensions: dict[str, Any] | None) -> bool:
        'When the AI Profile judges real-world dimensions, feed them into the\n    accessory physical_size so the compositor renders a consistent footprint for\n    this accessory across every training set.'
        if self._updates.material()(item) != "object":
            return False
        dims = dimensions if isinstance(dimensions, dict) else {}
        length = self._values.number()(dims.get("length_mm"))
        width = self._values.number()(dims.get("width_mm"))
        height = self._values.number()(dims.get("height_mm"))
        if not (length and width and height):
            return False
        new_size = self._updates.payload()(
            "object",
            object_length_mm=length,
            object_width_mm=width,
            object_height_mm=height,
        )
        if isinstance(item.get("physical_size"), dict) and item.get("physical_size") == new_size:
            return False
        item["physical_size"] = new_size
        return True
