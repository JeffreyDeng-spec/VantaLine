"""Explicit photo highlight selection service without application imports."""
from typing import Any
from .photo_highlight_ports import PhotoObjectSelection


class PhotoHighlightSelection:
    def __init__(self, selection: PhotoObjectSelection) -> None:
        self._selection = selection

    def pipeline_photo_highlight_object_items(self, task: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
        detection_method = self._selection.normalize()(
            str(task.get("detection_method") or (task.get("params") or {}).get("train_mode") or "")
        )
        if not self._selection.training()(detection_method):
            return []
        accessories_by_id = self._selection.lookup()(config)
        accessory_ids = self._selection.canonical()(config, [str(item_id) for item_id in task.get("accessory_ids") or []])
        return [
            accessories_by_id[item_id]
            for item_id in accessory_ids
            if item_id in accessories_by_id and self._selection.material()(accessories_by_id[item_id]) != "text"
        ]
