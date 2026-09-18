"""Required-item resolution retaining configured counts and missing-metadata fallback."""
from collections.abc import Callable, Mapping
from typing import Any

Record = dict[str, Any]


class RequiredAccessories:
    def __init__(self, uid: Callable[[Record], str], labels: Callable[[], Mapping[int, str]]):
        self.uid, self.labels = uid, labels

    def ai_required_accessories(self, config: dict[str, Any], spec: dict[str, Any]) -> list[tuple[dict[str, Any], int]]:
        accessories = config.get("accessories", [])
        by_id = {self.uid(item): item for item in accessories}
        required: list[tuple[dict[str, Any], int]] = []
        if spec.get("is_specialized"):
            counts = {
                str(k): max(1, int(v))
                for k, v in (spec.get("required_accessory_counts") or {}).items()
            }
            ids = [str(item_id) for item_id in spec.get("selected_accessory_ids") or counts.keys()]
            labels = {str(k): str(v) for k, v in (spec.get("accessory_labels") or {}).items()}
            for item_id in ids:
                item = by_id.get(item_id) or {
                    "id": item_id,
                    "class_id": -1,
                    "name": labels.get(item_id, item_id),
                    "material_type": "object",
                    "source_files": [],
                    "normalized_assets": [],
                }
                required.append((item, counts.get(item_id, 1)))
            return required

        required_classes = [int(x) for x in config.get("required_classes", [])]
        min_counts = {int(k): max(1, int(v)) for k, v in (config.get("min_counts") or {}).items()}
        by_class: dict[int, dict[str, Any]] = {}
        for item in accessories:
            try:
                by_class[int(item.get("class_id", -1))] = item
            except (TypeError, ValueError):
                continue
        for class_id in required_classes:
            item = by_class.get(class_id)
            if not item:
                item = {
                    "id": f"required_class_{class_id}",
                    "class_id": class_id,
                    "name": self.labels().get(class_id, f"Required Class {class_id}"),
                    "material_type": "object" if class_id == 0 else "text",
                    "status": "missing_accessory_metadata",
                    "description": "Configured required class has no matching accessory metadata; fail closed.",
                    "source_files": [],
                    "normalized_assets": [],
                }
            required.append((item, min_counts.get(class_id, 1)))
        if required:
            return required
        return []
