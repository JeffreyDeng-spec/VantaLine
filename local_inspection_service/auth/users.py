"""User administration and preferences, separated from HTTP transport."""
from collections.abc import Callable
from contextlib import AbstractContextManager
import time
from typing import Any
from fastapi import HTTPException
from .accounts import AccountService
from .access import AccessControl
from .credentials import generate_temporary_password
from .policy import FEATURE_PERMISSIONS, DEFAULT_USER_PERMISSIONS, public_user, find_user, clean_display_name, normalize_role, normalize_permissions
from .preferences import TASK_NAVIGATION_PREFERENCES_KEY, task_navigation_preferences_payload, normalize_task_navigation_ids
from .ports import UserStore
from .sessions import revoke_user_sessions
from ..schemas.auth import TaskNavigationPreferencesRequest, UserCreateRequest, UserUpdateRequest, UserPasswordResetRequest

class UserService:
    def __init__(self, store: UserStore, accounts: AccountService, access: AccessControl,
                 postgres: Callable[[], bool], write_lock: Callable[[], AbstractContextManager]):
        self.store, self.accounts, self.access = store, accounts, access
        self.postgres, self.write_lock = postgres, write_lock

    def get_task_navigation_preferences(self) -> dict[str, Any]:
        current_user = self.access.current_auth_user()
        store = self.store.load_auth_store()
        user = find_user(store, str(current_user.get("id") or ""))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return task_navigation_preferences_payload(user)

    def update_task_navigation_preferences(self, payload: TaskNavigationPreferencesRequest) -> dict[str, Any]:
        current_user = self.access.current_auth_user()
        store = self.store.load_auth_store()
        user = find_user(store, str(current_user.get("id") or ""))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        now = int(time.time())
        user[TASK_NAVIGATION_PREFERENCES_KEY] = {
            "pinned_task_ids": normalize_task_navigation_ids(payload.pinned_task_ids),
            "archived_task_ids": normalize_task_navigation_ids(payload.archived_task_ids),
            "updated_at": now,
        }
        user["updated_at"] = now
        if not self.store.save_auth_user(user):
            self.store.save_auth_store(store)
        return task_navigation_preferences_payload(user)

    def list_users(self) -> dict[str, Any]:
        self.access.require_admin_role()
        store = self.store.load_auth_store()
        return {
            "users": [public_user(user) for user in store.get("users", []) if isinstance(user, dict)],
            "features": FEATURE_PERMISSIONS,
            "default_user_permissions": DEFAULT_USER_PERMISSIONS,
        }

    def create_user(self, payload: UserCreateRequest) -> dict[str, Any]:
        self.access.require_admin_role()
        store = self.store.load_auth_store()
        user = self.accounts.create_auth_user(
            store,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
            permissions=payload.permissions,
            active=payload.active,
        )
        if not self.store.save_auth_user(user):
            self.store.save_auth_store(store)
        return {"status": "created", "user": public_user(user), "users": [public_user(item) for item in store.get("users", [])]}

    def update_user(self, user_id: str, payload: UserUpdateRequest, session_id: str) -> dict[str, Any]:
        actor = self.access.require_admin_role()
        store = self.store.load_auth_store()
        user = find_user(store, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["id"] == actor["id"] and payload.active is False:
            raise HTTPException(status_code=400, detail="Cannot deactivate the current session user")
        if payload.display_name is not None:
            user["display_name"] = clean_display_name(payload.display_name, str(user.get("username") or "user"))
        if payload.password is not None and payload.password.strip():
            self.accounts.set_user_password(user, payload.password)
            keep_session_id = session_id if user["id"] == actor["id"] else ""
            if self.postgres():
                self.store.delete_auth_sessions_for_user(user["id"], keep_session_id=keep_session_id)
            else:
                revoke_user_sessions(store, user["id"], keep_session_id=keep_session_id)
        if payload.role is not None:
            user["role"] = normalize_role(payload.role)
        if payload.permissions is not None:
            user["permissions"] = sorted(FEATURE_PERMISSIONS) if normalize_role(user.get("role")) == "admin" else normalize_permissions(payload.permissions)
        if payload.active is not None:
            user["active"] = bool(payload.active)
        user["updated_at"] = int(time.time())
        if not any(normalize_role(item.get("role")) == "admin" and bool(item.get("active", True)) for item in store.get("users", []) if isinstance(item, dict)):
            raise HTTPException(status_code=400, detail="At least one active admin is required")
        if not self.store.save_auth_user(user):
            self.store.save_auth_store(store)
        return {"status": "updated", "user": public_user(user), "users": [public_user(item) for item in store.get("users", [])]}

    def reset_user_password(self, user_id: str, payload: UserPasswordResetRequest, session_id: str) -> dict[str, Any]:
        actor = self.access.require_admin_role()
        store = self.store.load_auth_store()
        user = find_user(store, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if payload.generate and user["id"] == actor["id"]:
            raise HTTPException(
                status_code=400,
                detail="Cannot generate a temporary password for the current signed-in user. Enter a new password explicitly instead.",
            )
        generated_password = generate_temporary_password() if payload.generate else ""
        new_password = generated_password or str(payload.password or "")
        if not new_password:
            raise HTTPException(status_code=400, detail="Password is required unless generate is true")
        self.accounts.set_user_password(user, new_password)
        revoked_sessions = 0
        if payload.revoke_sessions:
            keep_session_id = session_id if user["id"] == actor["id"] else ""
            if self.postgres():
                revoked_sessions = self.store.delete_auth_sessions_for_user(user["id"], keep_session_id=keep_session_id)
            else:
                revoked_sessions = revoke_user_sessions(store, user["id"], keep_session_id=keep_session_id)
        if not self.store.save_auth_user(user):
            self.store.save_auth_store(store)
        response = {
            "status": "password_reset",
            "user": public_user(user),
            "users": [public_user(item) for item in store.get("users", []) if isinstance(item, dict)],
            "revoked_sessions": revoked_sessions,
        }
        if generated_password:
            response["temporary_password"] = generated_password
        return response

    def delete_user(self, user_id: str) -> dict[str, Any]:
        actor = self.access.require_admin_role()
        if user_id == actor["id"]:
            raise HTTPException(status_code=400, detail="Cannot delete the current session user")
        store = self.store.load_auth_store()
        users = [user for user in store.get("users", []) if isinstance(user, dict)]
        target = next((user for user in users if user.get("id") == user_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        remaining = [user for user in users if user.get("id") != user_id]
        if not any(normalize_role(user.get("role")) == "admin" and bool(user.get("active", True)) for user in remaining):
            raise HTTPException(status_code=400, detail="At least one active admin is required")
        store["users"] = remaining
        if self.postgres():
            with self.write_lock():
                self.store.delete_auth_sessions_for_user(user_id)
                self.store.delete_auth_user(user_id)
        elif isinstance(store.get("sessions"), dict):
            store["sessions"] = {
                session_id: session
                for session_id, session in store["sessions"].items()
                if not isinstance(session, dict) or session.get("user_id") != user_id
            }
            self.store.save_auth_store(store)
        else:
            self.store.save_auth_store(store)
        return {"status": "deleted", "deleted_user_id": user_id, "users": [public_user(item) for item in remaining]}
