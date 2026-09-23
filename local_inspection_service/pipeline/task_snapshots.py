"""Current task accessory labels and display names for pipeline projections."""
from typing import Any

from .task_snapshot_ports import PipelineTaskSnapshotLinks


class PipelineTaskSnapshots:
    def __init__(self, links: PipelineTaskSnapshotLinks):
        self.links = links

    def pipeline_task_label_snapshot(self, task: dict[str, Any]) -> dict[str, str]:
        labels = {
            str(k): str(v)
            for k, v in (task.get("accessory_labels") or {}).items()
            if str(k).strip() and str(v).strip()
        }
        ai_task_id = str(task.get("ai_task_id") or "").strip()
        if ai_task_id:
            linked_ai_task = next((item for item in self.links.load_ai_tasks()() if item.get("id") == ai_task_id), None)
            if linked_ai_task:
                labels.update(
                    {
                        str(k): str(v)
                        for k, v in (linked_ai_task.get("accessory_labels") or {}).items()
                        if str(k).strip() and str(v).strip()
                    }
                )
        return labels

    def pipeline_task_accessory_snapshot(self, config: dict[str, Any], task: dict[str, Any], accessory_ids: list[str]) -> tuple[dict[str, str], list[str]]:
        accessories_by_id = self.links.accessory_lookup()(config)
        labels = self.links.label_snapshot()(task)
        raw_names = [str(item) for item in task.get("accessory_names") or [] if str(item).strip()]
        names: list[str] = []
        for index, item_id in enumerate(accessory_ids):
            item = accessories_by_id.get(item_id)
            names.append(str((item or {}).get("name") or (item or {}).get("label") or labels.get(item_id) or (raw_names[index] if index < len(raw_names) else "") or item_id))
        return labels, names