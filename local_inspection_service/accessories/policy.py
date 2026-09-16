"""Existing accessory identity, material and profile-readiness policy."""
import re
from typing import Any


TEXT_ACCESSORY_NAME_HINTS = ("说明", "说明书", "标签", "贴纸", "标牌", "铭牌", "文字", "卡片", "资料", "文档", "手册", "manual", "label", "card", "text")


TRANSPARENT_OBJECT_KEYWORDS = (
    "glass",
    "transparent",
    "translucent",
    "bottle",
    "jar",
    "vial",
    "玻璃",
    "透明",
    "透光",
    "瓶",
)


AI_PROFILE_PROVIDER_READY_STATUSES = {"generated", "ready"}


AI_PROFILE_REJECTED_STATUSES = {
    "missing_api_key",
    "provider_error",
    "timeout",
    "create_failed",
    "fallback",
    "unsupported_provider",
    "invalid_base_url",
}


def accessory_uid(item: dict[str, Any]) -> str:
    if item.get("id"):
        return str(item["id"])
    return accessory_legacy_uid(item)


def accessory_legacy_uid(item: dict[str, Any]) -> str:
    raw = f"{item.get('class_id', 'x')}_{item.get('name', 'accessory')}"
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_").lower()


def accessory_material_type(item: dict[str, Any]) -> str:
    return str(item.get("material_type") or ("object" if int(item.get("class_id", 0)) == 0 else "text"))


def accessory_uses_ocr(item: dict[str, Any]) -> bool:
    if accessory_material_type(item) == "text":
        return True
    role = str(item.get("training_role") or "").lower()
    if role in {"detect_then_ocr", "text_ocr", "ocr"}:
        return True
    route = str(item.get("detection_route") or item.get("optimization_route") or "").lower()
    if route == "yolo_ocr":
        return True
    name_blob = " ".join(
        str(item.get(key) or "")
        for key in ("name", "label", "description", "category", "material_type")
    ).lower()
    return any(hint in name_blob for hint in TEXT_ACCESSORY_NAME_HINTS)


def normalize_object_alpha_material_policy(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"transparent", "glass", "translucent", "preserve_transparency", "preserve_glass"}:
        return "transparent"
    if normalized in {"opaque", "solid", "foreground_opaque", "solid_foreground"}:
        return "opaque"
    return None


def object_alpha_material_policy(item: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> str:
    source = metadata or {}
    explicit = (
        source.get("material_alpha_policy")
        or source.get("alpha_policy")
        or (item or {}).get("material_alpha_policy")
        or (item or {}).get("alpha_policy")
        or (item or {}).get("object_alpha_policy")
    )
    explicit_policy = normalize_object_alpha_material_policy(explicit)
    if explicit_policy:
        return explicit_policy
    haystack = " ".join(
        str(value or "")
        for value in (
            (item or {}).get("name"),
            source.get("name"),
            (item or {}).get("material"),
            (item or {}).get("description"),
            source.get("source_pose_collection"),
        )
    ).lower()
    return "transparent" if any(keyword in haystack for keyword in TRANSPARENT_OBJECT_KEYWORDS) else "opaque"


def object_alpha_policy_label(policy: str) -> str:
    return "透明" if policy == "transparent" else "不透明"


def accessory_ai_profile_ready(item: dict[str, Any]) -> bool:
    profile = item.get("ai_profile") if isinstance(item.get("ai_profile"), dict) else None
    if not profile:
        return False
    if profile.get("accessory_id") != accessory_uid(item):
        return False
    if profile.get("material_type") != accessory_material_type(item):
        return False
    if not (profile.get("name") and (profile.get("visual_signature") or profile.get("description") or profile.get("reference_images"))):
        return False
    status = item.get("ai_profile_status") if isinstance(item.get("ai_profile_status"), dict) else {}
    source = str(status.get("source") or "").strip().lower()
    state = str(status.get("status") or "").strip().lower()
    if source == "fallback" or state in AI_PROFILE_REJECTED_STATUSES:
        return False
    return source == "provider" and state in AI_PROFILE_PROVIDER_READY_STATUSES


def accessory_ai_profile_rejected(item: dict[str, Any]) -> bool:
    status = item.get("ai_profile_status") if isinstance(item.get("ai_profile_status"), dict) else {}
    source = str(status.get("source") or "").strip().lower()
    state = str(status.get("status") or "").strip().lower()
    return source == "fallback" or state in AI_PROFILE_REJECTED_STATUSES
