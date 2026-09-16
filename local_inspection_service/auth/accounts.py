"""Account creation and bootstrap policy with explicit persistence and hashing."""
from collections.abc import Callable
from dataclasses import dataclass
import os
import time
from typing import Any
import uuid
from fastapi import HTTPException
from .policy import FEATURE_PERMISSIONS, clean_username, clean_display_name, normalize_role, normalize_permissions


@dataclass(frozen=True)
class AccountDependencies:
    load_store: Callable[[], dict[str, Any]]
    save_store: Callable[[dict[str, Any]], None]
    hash_password: Callable[[str], str]


class AccountService:
    def __init__(self, dependencies: AccountDependencies):
        self.dependencies = dependencies


    def users_exist(self, store: dict[str, Any] | None = None) -> bool:
        store = store or self.dependencies.load_store()
        return any(isinstance(user, dict) for user in store.get("users", []))


    def create_auth_user(self,
        store: dict[str, Any],
        *,
        username: str,
        password: str,
        display_name: str | None = None,
        role: str = "user",
        permissions: list[str] | None = None,
        active: bool = True,
    ) -> dict[str, Any]:
        clean = clean_username(username)
        if not clean:
            raise HTTPException(status_code=400, detail="Username is required")
        if any(clean_username(user.get("username")) == clean for user in store.get("users", []) if isinstance(user, dict)):
            raise HTTPException(status_code=409, detail="Username already exists")
        now = int(time.time())
        normalized_role = normalize_role(role)
        user = {
            "id": f"user_{uuid.uuid4().hex[:12]}",
            "username": clean,
            "display_name": clean_display_name(display_name, clean),
            "role": normalized_role,
            "permissions": sorted(FEATURE_PERMISSIONS) if normalized_role == "admin" else normalize_permissions(permissions or []),
            "password_hash": self.dependencies.hash_password(password),
            "active": bool(active),
            "created_at": now,
            "updated_at": now,
        }
        store.setdefault("users", []).append(user)
        return user


    def bootstrap_admin_from_env(self, store: dict[str, Any]) -> bool:
        if self.users_exist(store):
            return False
        username = os.environ.get("VANTALINE_BOOTSTRAP_ADMIN_USERNAME", "").strip()
        password = os.environ.get("VANTALINE_BOOTSTRAP_ADMIN_PASSWORD", "")
        if not username or not password:
            return False
        self.create_auth_user(store, username=username, password=password, display_name=username, role="admin", permissions=sorted(FEATURE_PERMISSIONS))
        self.dependencies.save_store(store)
        return True


    def set_user_password(self, user: dict[str, Any], password: str) -> None:
        user["password_hash"] = self.dependencies.hash_password(password)
        user["updated_at"] = int(time.time())
