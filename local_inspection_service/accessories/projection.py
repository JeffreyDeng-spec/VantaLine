"""Full and summary accessory projections with explicit media/access capabilities."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from .policy import accessory_uid, object_alpha_material_policy, accessory_ai_profile_ready

Record = dict[str, Any]


@dataclass(frozen=True)
class ProjectionDependencies:
    audit: Callable[[Record], Record]
    sanitize: Callable[[Any], Any]
    physical_size: Callable[[str], Record]
    size_reference: Callable[[Any], Record | None]
    text_source_count: Callable[[Record], int]
    text_preview_limit: Callable[[], int]
    current_user: Callable[[], Record]
    redact: Callable[[Record, Record], Record]


class AccessoryProjection:
    def __init__(self, dependencies: ProjectionDependencies):
        self.dependencies = dependencies

    def serialize_accessory(self, item: dict[str, Any]) -> dict[str, Any]:
        copy = self.dependencies.sanitize(self.dependencies.audit(item))
        copy["id"] = accessory_uid(item)
        material_type = copy.setdefault("material_type", "object" if int(copy.get("class_id", 0)) == 0 else "text")
        copy.setdefault("physical_size", self.dependencies.physical_size(str(material_type)))
        if str(material_type) == "object":
            copy.setdefault("material_alpha_policy", object_alpha_material_policy(item))
        copy.setdefault("source_files", [])
        copy.setdefault("normalized_assets", [])
        copy.setdefault("training_role", "detect_and_classify")
        copy.setdefault("detection_route", "yolo")
        if copy.get("detection_route") == "locate":
            copy["detection_route"] = "yolo"
        copy.pop("locateanything_profile", None)
        copy.pop("locateanything_profile_status", None)
        return copy

    def serialize_accessory_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        full = self.serialize_accessory(item)
        source_files = full.get("source_files") if isinstance(full.get("source_files"), list) else []
        is_text = str(full.get("material_type")) == "text"
        source_preview_limit = self.dependencies.text_preview_limit() if is_text else 4
        source_file_count = self.dependencies.text_source_count(full) if is_text else len(source_files)
        original_source_files = full.get("original_source_files") if isinstance(full.get("original_source_files"), list) else []
        thumbnails = full.get("thumbnails") if isinstance(full.get("thumbnails"), list) else []
        ai_status = full.get("ai_profile_status") if isinstance(full.get("ai_profile_status"), dict) else {}
        payload = {
            "id": full["id"],
            "class_id": full.get("class_id"),
            "name": full.get("name") or full["id"],
            "label": full.get("label") or full.get("name") or full["id"],
            "material_type": full.get("material_type"),
            "material_alpha_policy": full.get("material_alpha_policy"),
            "object_alpha_policy_label": full.get("object_alpha_policy_label"),
            "training_role": full.get("training_role"),
            "detection_route": full.get("detection_route"),
            "physical_size": full.get("physical_size"),
            "size_reference": full.get("size_reference"),
            "size_reference_label": (self.dependencies.size_reference(full.get("size_reference")) or {}).get("label"),
            "status": full.get("status"),
            "manual_crop_required": full.get("manual_crop_required"),
            "manual_crop_reason": full.get("manual_crop_reason"),
            "preprocess": full.get("preprocess"),
            "source_files": source_files[:source_preview_limit],
            "original_source_files": original_source_files[:source_preview_limit],
            "source_file_count": source_file_count,
            "normalized_asset_count": len(full.get("normalized_assets") or []),
            "clean_sprite_status": full.get("clean_sprite_status"),
            "clean_sprite_count": full.get("clean_sprite_count"),
            "clean_sprite_expected_count": full.get("clean_sprite_expected_count"),
            "clean_sprite_failed_cells": full.get("clean_sprite_failed_cells") or [],
            "ai_profile_status": {
                "status": ai_status.get("status"),
                "source": ai_status.get("source"),
                "message": ai_status.get("message"),
                "updated_at": ai_status.get("updated_at"),
            }
            if ai_status
            else full.get("ai_profile_status"),
            "ai_profile_ready": accessory_ai_profile_ready(full),
            "thumbnails": thumbnails[:2],
            "thumbnail_url": thumbnails[0].get("url") if thumbnails and isinstance(thumbnails[0], dict) else "",
            "created_at": full.get("created_at"),
            "updated_at": full.get("updated_at"),
            "confirmed_at": full.get("confirmed_at"),
            "owner_user_id": full.get("owner_user_id"),
            "owner_username": full.get("owner_username"),
        }
        return self.dependencies.redact(payload, self.dependencies.current_user())

    def serialize_accessory_items(self, items: list[dict[str, Any]], *, summary: bool = True) -> list[dict[str, Any]]:
        serializer = self.serialize_accessory_summary if summary else self.serialize_accessory
        return [serializer(item) for item in items]
