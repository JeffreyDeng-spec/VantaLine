"""Pure ownership, shared-read and administrator filtering rules."""
from dataclasses import dataclass
from typing import Any
from ..auth.policy import user_is_admin


@dataclass(frozen=True)
class RecordOwnership:
    legacy_owner: str
    system_owner: str

    def record_owner_id(self, record: dict[str, Any] | None) -> str:
        if not isinstance(record, dict):
            return self.legacy_owner
        owner = str(record.get("owner_user_id") or record.get("created_by_user_id") or "").strip()
        return owner or self.legacy_owner

    def record_owner_username(self, record: dict[str, Any] | None) -> str:
        if not isinstance(record, dict):
            return self.legacy_owner
        username = str(record.get("owner_username") or record.get("created_by_username") or "").strip()
        if username:
            return username
        owner = self.record_owner_id(record)
        if owner == self.legacy_owner:
            return self.legacy_owner
        if owner == self.system_owner:
            return "system"
        return owner

    def record_matches_owner_filter(self, record: dict[str, Any], target_user_id: str | None) -> bool:
        if not target_user_id:
            return True
        target = str(target_user_id).strip()
        owner = self.record_owner_id(record)
        if target in {self.legacy_owner, "legacy"}:
            return owner == self.legacy_owner
        if target in {self.system_owner, "system"}:
            return owner == self.system_owner
        return owner == target

    def record_visible_to_user(self, record: dict[str, Any], user: dict[str, Any], target_user_id: str | None = None) -> bool:
        if user_is_admin(user):
            return self.record_matches_owner_filter(record, target_user_id)
        owner = self.record_owner_id(record)
        shared = record.get("shared_with_user_ids") if isinstance(record.get("shared_with_user_ids"), list) else []
        return owner == user["id"] or user["id"] in {str(item) for item in shared} or "*" in shared

    def record_mutable_by_user(self, record: dict[str, Any], user: dict[str, Any]) -> bool:
        return user_is_admin(user) or self.record_owner_id(record) == user["id"]
