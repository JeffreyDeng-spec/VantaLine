"""Pipeline task response metadata, resource flags and automatic-training projection."""
from dataclasses import dataclass
from typing import Any
from .task_projection_ports import ProjectionMetadata, ProjectionResources

@dataclass(frozen=True)
class PipelineTaskProjection:
    metadata: ProjectionMetadata
    resources: ProjectionResources

    def pipeline_task_public(self,
        task: dict[str, Any],
        config: dict[str, Any],
        *,
        ai_task_ids: set[str] | None = None,
        trained_model_specs: list[dict[str, Any]] | None = None,
        auto_optimize_states: list[dict[str, Any]] | None = None,
        auto_optimize_states_by_id: dict[str, dict[str, Any]] | None = None,
        sanitize: bool = True,
    ) -> dict[str, Any]:
        accessories_by_id = self.metadata.accessory_lookup_by_id()(config)
        copy = self.metadata.enrich_record_audit_fields()(task)
        copy.pop("model_profiles", None)
        params = copy.get("params") if isinstance(copy.get("params"), dict) else {}
        copy["detection_method"] = self.metadata.normalize_pipeline_detection_method()(str(copy.get("detection_method") or params.get("train_mode") or params.get("route") or ""))
        copy["uses_training_flow"] = self.metadata.pipeline_method_uses_training()(str(copy.get("detection_method") or ""))
        raw_accessory_ids = [str(item_id) for item_id in copy.get("accessory_ids") or [] if str(item_id).strip()]
        accessory_ids: list[str] = []
        seen_ids: set[str] = set()
        for raw_id in raw_accessory_ids:
            resolved = self.metadata.resolve_accessory_id()(config, raw_id)
            item_id = resolved[0] if resolved else raw_id
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                accessory_ids.append(item_id)
        copy["accessory_ids"] = accessory_ids
        copy["accessory_counts"] = self.metadata.normalize_pipeline_accessory_counts()(config, copy["accessory_ids"], copy.get("accessory_counts"))
        labels, names = self.metadata.pipeline_task_accessory_snapshot()(config, task, copy["accessory_ids"])
        copy["accessory_labels"] = {item_id: labels.get(item_id, names[index]) for index, item_id in enumerate(copy["accessory_ids"])}
        copy["accessory_names"] = names
        copy["accessories"] = [
            {
                "id": item_id,
                "name": names[index],
                "material_type": self.metadata.accessory_material_type()(accessories_by_id.get(item_id, {})),
                "count": int(copy["accessory_counts"].get(item_id, 1)),
            }
            for index, item_id in enumerate(copy.get("accessory_ids") or [])
        ]
        copy["dataset_status"] = self.resources.pipeline_task_dataset_status()(copy)
        copy["dataset_exists"] = copy["dataset_status"] == "available"
        copy["model_status"] = self.resources.pipeline_task_model_status()(
            copy,
            ai_task_ids=ai_task_ids,
            trained_model_specs=trained_model_specs,
        )
        copy["model_exists"] = copy["model_status"] == "available"
        auto_optimize_link = self.resources.pipeline_task_auto_optimize_link()(
            copy,
            config,
            auto_optimize_states=auto_optimize_states,
            auto_optimize_states_by_id=auto_optimize_states_by_id,
        )
        if auto_optimize_link:
            copy["auto_optimize_task_id"] = auto_optimize_link["task_id"]
            copy["ai_baseline_task_id"] = auto_optimize_link["task_id"]
            copy["ai_baseline_model_id"] = auto_optimize_link["ai_model_id"]
            copy["auto_optimize_link"] = auto_optimize_link
        return self.resources.public_path_sanitized()(copy) if sanitize else copy
