"""Request-scoped owner assignment and hidden-resource access checks."""
from collections.abc import Callable
from typing import Any
from fastapi import HTTPException
from ..auth.policy import user_is_admin
from ..runtime.identity import RequestIdentity
from .ownership import RecordOwnership


class RecordAccess:
    def __init__(self, identity: RequestIdentity, ownership: RecordOwnership,
                 current_user: Callable[[], dict[str, Any]],
                 find_user: Callable[[str], dict[str, Any] | None]):
        self.identity = identity
        self.ownership = ownership
        self.current_user = current_user
        self.find_user = find_user

    def current_owner_fields(self) -> dict[str, Any]:
        user = self.identity.get()
        if not user:
            return {}
        return {"owner_user_id": user["id"], "owner_username": user.get("username") or ""}

    def owner_fields_for_new_record(self, user: dict[str, Any], target_user_id: str | None = None) -> dict[str, Any]:
        target = str(target_user_id or "").strip()
        if user_is_admin(user) and target:
            if target == self.ownership.legacy_owner:
                return {"owner_user_id": self.ownership.legacy_owner, "owner_username": self.ownership.legacy_owner}
            if target == self.ownership.system_owner:
                return {"owner_user_id": self.ownership.system_owner, "owner_username": "system"}
            target_user = self.find_user(target)
            if not target_user:
                raise HTTPException(status_code=404, detail="目标用户不存在")
            return {"owner_user_id": target_user["id"], "owner_username": target_user.get("username") or ""}
        return {"owner_user_id": user["id"], "owner_username": user.get("username") or ""}

    def require_record_access(self, record: dict[str, Any], user: dict[str, Any] | None = None, *, write: bool = False) -> None:
        user = user or self.current_user()
        allowed = self.ownership.record_mutable_by_user(record, user) if write else self.ownership.record_visible_to_user(record, user)
        if not allowed:
            raise HTTPException(status_code=404, detail="Resource not found")
