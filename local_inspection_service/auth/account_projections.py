"""Account-visible configuration, model permission and media projections."""
import copy
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from fastapi import HTTPException
from .account_projection_ports import AccountAccess, AccountConfig, AccountModels, AccountMedia

@dataclass(frozen=True)
class AccountProjections:
    access: AccountAccess
    config: AccountConfig
    models: AccountModels
    media: AccountMedia

    def merge_scoped_accessory_updates(self, full_config: dict[str, Any], scoped_config: dict[str, Any], user: dict[str, Any]) -> None:
        scoped_by_id = {
            self.config.accessory_uid()(item): item
            for item in scoped_config.get("accessories", [])
            if isinstance(item, dict)
        }
        merged = []
        for item in full_config.get("accessories", []):
            if not isinstance(item, dict):
                merged.append(item)
                continue
            uid = self.config.accessory_uid()(item)
            if uid in scoped_by_id and self.access.record_mutable_by_user()(item, user):
                merged.append(scoped_by_id[uid])
            else:
                merged.append(item)
        full_config["accessories"] = merged


    def scope_config_for_user(self, config: dict[str, Any], user: dict[str, Any] | None = None, target_user_id: str | None = None) -> dict[str, Any]:
        user = user or self.access.current_auth_user()()
        scoped = json.loads(json.dumps(config))
        scoped.pop("plc_runtime_coordination", None)
        scoped.pop(self.config.PLC_CAPTURE_RESULTS_KEY(), None)
        scoped["accessories"] = [
            item
            for item in scoped.get("accessories", [])
            if isinstance(item, dict) and self.access.record_visible_to_user()(item, user, target_user_id)
        ]
        selected_ids = {self.config.accessory_uid()(item) for item in scoped.get("accessories", [])}
        training = self.config.training_state_for_user()(scoped, user, selected_ids, target_user_id)
        if isinstance(training.get("selected_accessory_ids"), list):
            training["selected_accessory_ids"] = [item_id for item_id in training["selected_accessory_ids"] if str(item_id) in selected_ids]
        scoped["training"] = training
        return scoped


    def require_analyze_model_permission(self, model_id: str | None) -> None:
        user = self.access.current_auth_user()()
        if self.access.user_has_permission()(user, "inspection"):
            return
        if self.access.user_has_permission()(user, "ai_detection"):
            spec = self.models.selected_model_spec()(model_id, self.config.scope_config_for_user()(self.config.load_config()(), user))
            if spec.get("is_ai_detection"):
                return
        raise HTTPException(status_code=403, detail="Inspection permission required for non-AI detection models")


    def output_path_visible_to_user(self, request_path: str, user: dict[str, Any]) -> bool:
        if self.access.user_is_admin()(user):
            return True
        relative = request_path.removeprefix("/outputs/").lstrip("/")
        candidate = (self.media.OUTPUT_DIR() / PurePosixPath(relative)).resolve()
        try:
            rel_parts = candidate.relative_to(self.media.OUTPUT_DIR().resolve()).parts
        except ValueError:
            return False
        # Per-user subtree (outputs/users/<id>/...) is private to its owner.
        if len(rel_parts) >= 2 and rel_parts[0] == "users":
            return rel_parts[1] == str(user["id"])
        # Shared/legacy outputs written to the OUTPUT_DIR root are visible to any
        # authenticated user (the /api permission gate already protects who can
        # create pipeline artifacts); this keeps pose/sample images loadable when a
        # task was owned by a legacy/empty owner instead of a per-user subtree.
        return True


    def redact_status_payload_for_user(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        if self.access.include_internal_runtime_details()(user):
            return payload
        redacted = copy.deepcopy(payload)
        redacted.pop("model_path", None)
        redacted["ai_detection"] = self.models.public_ai_detection_status_for_user()(user)
        redacted["training_execution"] = {"status": "restricted", "executor": ""}
        redacted["cursor_image2"] = {"status": "restricted", "configured": False}
        redacted["ocr"] = {}
        for model in redacted.get("available_models", []) or []:
            if isinstance(model, dict):
                model.pop("path", None)
                model.pop("provider_status", None)
        for model in redacted.get("specialized_models", []) or []:
            if isinstance(model, dict):
                model.pop("path", None)
                model.pop("artifact_path", None)
                model.pop("metadata_path", None)
                model.pop("provider_status", None)
        return redacted


    def redact_config_summary_for_user(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        if self.access.include_internal_runtime_details()(user):
            return payload
        return {
            "confidence_threshold": payload.get("confidence_threshold"),
            "required_classes": payload.get("required_classes"),
            "min_counts": payload.get("min_counts"),
        }


    def redact_accessory_payload_for_user(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        if self.access.include_internal_runtime_details()(user):
            return payload
        redacted = copy.deepcopy(payload)
        if isinstance(redacted.get("source_files"), list):
            redacted["source_files"] = []
        if isinstance(redacted.get("original_source_files"), list):
            redacted["original_source_files"] = []
        return redacted
