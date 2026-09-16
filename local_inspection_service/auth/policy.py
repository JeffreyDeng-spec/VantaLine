"""Existing account normalization, public projection and role policy."""
import re
from typing import Any


FEATURE_PERMISSIONS: dict[str, str] = {
    "inspection": "检测工作台",
    "ai_detection": "AI 检测",
    "accessory_library": "配件库",
    "training_pipeline": "任务流水线",
    "incoming_material_config": "包材文字标准配置",
    "model_library": "训练库 / 模型库",
    "system_settings": "通过规则 / API 服务设置",
    "ai_config": "AI 服务配置",
    "agent_config": "Agent 接入配置",
    "worker_settings": "RunPod / 远程执行设置",
    "user_management": "用户与权限管理",
}


ADMIN_ONLY_PERMISSIONS = {"user_management", "ai_config", "agent_config", "system_settings"}


DEFAULT_USER_PERMISSIONS = [
    "inspection",
    "ai_detection",
    "accessory_library",
    "training_pipeline",
    "model_library",
]


def clean_username(value: Any) -> str:
    username = re.sub(r"[^a-zA-Z0-9_.@-]+", "_", str(value or "").strip().lower())
    return username[:64]


def clean_display_name(value: Any, fallback: str) -> str:
    name = str(value or "").strip()
    return name[:80] if name else fallback


def normalize_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    return "admin" if role == "admin" else "user"


def normalize_permissions(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    permissions: list[str] = []
    for raw in values:
        permission = str(raw or "").strip()
        if permission in FEATURE_PERMISSIONS and permission not in ADMIN_ONLY_PERMISSIONS and permission not in seen:
            seen.add(permission)
            permissions.append(permission)
    return permissions


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    role = normalize_role(user.get("role"))
    permissions = sorted(FEATURE_PERMISSIONS) if role == "admin" else normalize_permissions(user.get("permissions"))
    return {
        "id": str(user.get("id") or ""),
        "username": str(user.get("username") or ""),
        "display_name": str(user.get("display_name") or user.get("username") or ""),
        "role": role,
        "permissions": permissions,
        "active": bool(user.get("active", True)),
        "created_at": int(user.get("created_at") or 0),
        "updated_at": int(user.get("updated_at") or 0),
    }


def find_user(store: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    for user in store.get("users", []):
        if isinstance(user, dict) and str(user.get("id") or "") == str(user_id or ""):
            return user
    return None


def find_user_by_username(store: dict[str, Any], username: str) -> dict[str, Any] | None:
    clean = clean_username(username)
    for user in store.get("users", []):
        if isinstance(user, dict) and clean_username(user.get("username")) == clean:
            return user
    return None


def user_is_admin(user: dict[str, Any] | None) -> bool:
    return normalize_role((user or {}).get("role")) == "admin"


def user_has_permission(user: dict[str, Any] | None, permission: str | None) -> bool:
    if not permission:
        return True
    if user_is_admin(user):
        return True
    return permission in normalize_permissions((user or {}).get("permissions"))
