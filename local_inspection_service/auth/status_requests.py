"""Service status and configuration-summary request orchestration."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .status_requests_ports import StatusRequestAccess, StatusRequestCatalog, StatusRequestRuntime

@dataclass(frozen=True)
class ServiceStatusRequests:
    access: StatusRequestAccess
    catalog: StatusRequestCatalog
    runtime: StatusRequestRuntime

    def status(self, user_id: str | None = None) -> dict[str, Any]:
        user = self.access.current_auth_user()()
        target_user_id = user_id if self.access.user_is_admin()(user) else None
        config = self.access.scope_config_for_user()(self.catalog.load_config()(), user, target_user_id)
        active_spec = self.catalog.selected_model_spec()(None, config)
        active_path = Path(active_spec["path"]) if active_spec.get("path") else None
        accessory_names_by_id = {
            str(item.get("id") or self.catalog.accessory_uid()(item)): str(item.get("name") or item.get("label") or self.catalog.accessory_uid()(item))
            for item in config.get("accessories", [])
        }
        training_tasks = self.catalog.list_training_tasks()(user=user, target_user_id=target_user_id)
        trained_specs = [spec for spec in self.catalog.list_trained_model_specs()() if self.access.record_visible_to_user()(spec, user, target_user_id)]
        ai_detection_status = self.runtime.public_ai_detection_status()()

        def task_accessory_names(task: dict[str, Any]) -> list[str]:
            names = [accessory_names_by_id.get(str(item_id), str(item_id)) for item_id in task.get("selected_accessory_ids") or []]
            return [name for name in names if name]

        available_models = []
        for spec in self.catalog.legacy_model_specs()():
            path = Path(spec["path"]) if spec.get("path") else None
            exists = bool(spec.get("is_ai_detection")) or bool(path and self.catalog._business_files().exists(path))
            available_models.append(
                {
                    "id": spec["id"],
                    "label": spec["label"],
                    "description": spec["description"],
                    "variant": spec.get("variant"),
                    "uses_ocr": bool(spec.get("uses_ocr", False)),
                    "is_legacy": bool(spec.get("is_legacy", False)),
                    "is_ai_detection": bool(spec.get("is_ai_detection", False)),
                    "provider_status": ai_detection_status if spec.get("is_ai_detection") else None,
                    "path": str(path or ""),
                    "exists": exists,
                }
            )
        specialized_specs = [*trained_specs, *self.catalog.list_ai_detection_specialized_model_specs()(config, trained_specs, target_user_id)]
        specialized_models = [
            {
                "id": spec["id"],
                "run_id": spec["run_id"],
                "task_id": spec["task_id"],
                "task_label": spec.get("task_label") or "",
                "task_source": spec.get("task_source") or "",
                "variant": spec["variant"],
                "label": spec["label"],
                "description": spec["description"],
                "uses_ocr": bool(spec.get("uses_ocr", False)),
                "is_ai_detection": bool(spec.get("is_ai_detection", False)),
                "provider_status": ai_detection_status if spec.get("is_ai_detection") else None,
                "confidence_threshold": spec.get("confidence_threshold", config.get("confidence_threshold")),
                "required_accessory_counts": spec.get("required_accessory_counts") or {},
                "accessory_labels": spec.get("accessory_labels") or {},
                "accessory_class_map": spec.get("accessory_class_map") or {},
                "ocr_accessory_ids": spec.get("ocr_accessory_ids") or [],
                "artifact_path": str(spec.get("artifact_path") or spec["path"]),
                "metadata_path": str(spec.get("metadata_path") or ""),
                "path": str(spec["path"]),
                "exists": bool(spec.get("is_ai_detection")) or self.catalog._business_files().exists(Path(spec["path"])),
                "accessory_names": spec.get("accessory_names") or [],
                "selected_accessory_ids": spec.get("selected_accessory_ids") or [],
                "missing_accessory_ids": spec.get("missing_accessory_ids") or [],
                "created_at": spec.get("created_at") or 0,
                "updated_at": spec.get("updated_at") or spec.get("created_at") or 0,
                "owner_user_id": spec.get("owner_user_id") or self.runtime.LEGACY_OWNER_ID(),
                "owner_username": spec.get("owner_username") or self.runtime.record_owner_username()(spec),
            }
            for spec in specialized_specs
        ]
        task_labels = {
            str(task.get("job_id")): str(task.get("label") or task.get("candidate_name") or task.get("job_id"))
            for task in training_tasks
        }
        task_accessories = {
            str(task.get("job_id")): task_accessory_names(task)
            for task in training_tasks
        }
        specialized_model_tasks: dict[str, dict[str, Any]] = {}
        for spec in specialized_models:
            if spec.get("task_source") == "ai_detection_task_config":
                continue
            task_id = str(spec.get("task_id") or spec.get("run_id"))
            accessory_names = task_accessories.get(task_id) or spec.get("accessory_names") or []
            task = specialized_model_tasks.setdefault(
                task_id,
                {
                    "task_id": task_id,
                    "label": " + ".join(accessory_names) if accessory_names else task_labels.get(task_id, task_id),
                    "accessory_names": accessory_names,
                    "accessory_labels": spec.get("accessory_labels") or {},
                    "required_accessory_counts": spec.get("required_accessory_counts") or {},
                    "confidence_threshold": spec.get("confidence_threshold", config.get("confidence_threshold")),
                    "models": [],
                },
            )
            if accessory_names and not task.get("accessory_names"):
                task["accessory_names"] = accessory_names
                task["label"] = " + ".join(accessory_names)
            if spec.get("accessory_labels") and not task.get("accessory_labels"):
                task["accessory_labels"] = spec.get("accessory_labels") or {}
            if spec.get("required_accessory_counts") and not task.get("required_accessory_counts"):
                task["required_accessory_counts"] = spec.get("required_accessory_counts") or {}
            if spec.get("confidence_threshold") is not None:
                task["confidence_threshold"] = spec.get("confidence_threshold")
            task["models"].append(spec)
        training_execution = self.runtime.training_execution_status()(include_worker_probe=False)
        cursor_image2 = self.runtime.public_cursor_image2_status()()
        if not self.access.user_has_permission()(user, "worker_settings"):
            training_execution = {"status": "restricted", "executor": ""}
        if not self.access.user_has_permission()(user, "ai_config"):
            cursor_image2 = {"status": "restricted", "configured": False}
        payload = {
            "service": "running",
            "model_exists": bool(active_spec.get("is_ai_detection")) or bool(active_path and self.catalog._business_files().exists(active_path)),
            "model_path": str(active_spec.get("path") or ""),
            "active_model_id": active_spec["id"],
            "available_models": available_models,
            "specialized_models": specialized_models,
            "specialized_model_tasks": list(specialized_model_tasks.values()),
            "ai_detection_tasks": self.catalog.ai_detection_tasks_response()(config, user=user, target_user_id=target_user_id)["tasks"],
            "ai_detection": ai_detection_status,
            "yolo_warmup": self.runtime.public_yolo_warmup_status()(config),
            "training_execution": training_execution,
            "cursor_image2": cursor_image2,
            "classes": [{"class_id": k, "name": v, "label": self.runtime.CLASS_LABELS()[k]} for k, v in self.runtime.CLASS_NAMES().items()],
            "rule": {
                "confidence_threshold": config["confidence_threshold"],
                "required_classes": config["required_classes"],
                "min_counts": config["min_counts"],
            },
            "ocr": config.get("ocr", {}),
        }
        return self.access.redact_status_payload_for_user()(payload, user)


    def get_config_summary(self, user_id: str | None = None) -> dict[str, Any]:
        user = self.access.current_auth_user()()
        config = self.access.scope_config_for_user()(self.catalog.load_config()(), user, user_id if self.access.user_is_admin()(user) else None)
        payload = self.access.public_path_sanitized()(
            {
                "confidence_threshold": config["confidence_threshold"],
                "required_classes": config["required_classes"],
                "min_counts": config["min_counts"],
                "task_rules": config.get("task_rules", {}),
                "training": config.get("training", {}),
                "video": config.get("video", {}),
                "stream": config.get("stream", {}),
                "ocr": config.get("ocr", {}),
            }
        )
        return self.access.redact_config_summary_for_user()(payload, user)
