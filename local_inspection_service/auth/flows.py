"""Account login/bootstrap/logout workflows with explicit service dependencies."""
from collections.abc import Callable
from typing import Any
from fastapi import HTTPException, Request
from .accounts import AccountService
from .sessions import SessionService
from .login_limits import LoginRateLimiter
from .ports import SessionStore
from .policy import FEATURE_PERMISSIONS, DEFAULT_USER_PERMISSIONS, public_user, find_user_by_username
from .repository import auth_session_key_candidates
from .credentials import verify_password
from ..schemas.auth import AuthBootstrapRequest, AuthLoginRequest

class AuthFlows:
    def __init__(self, store: SessionStore, accounts: AccountService, sessions: SessionService,
                 limits: LoginRateLimiter, postgres: Callable[[], bool], legacy_owner: Callable[[], str]):
        self.store, self.accounts, self.sessions = store, accounts, sessions
        self.limits, self.postgres, self.legacy_owner = limits, postgres, legacy_owner

    def auth_status(self, request: Request) -> dict[str, Any]:
        user, store, _ = self.sessions.authenticate_request(request)
        setup_required = not self.accounts.users_exist(store)
        if not user:
            return {
                "authenticated": False,
                "setup_required": setup_required,
                "user": None,
                "features": {},
                "default_user_permissions": [],
                "legacy_owner_id": "",
            }
        return {
            "authenticated": True,
            "setup_required": setup_required,
            "user": user,
            "features": FEATURE_PERMISSIONS,
            "default_user_permissions": DEFAULT_USER_PERMISSIONS,
            "legacy_owner_id": self.legacy_owner(),
        }

    def auth_bootstrap(self, payload: AuthBootstrapRequest) -> tuple[dict[str, Any], str]:
        store = self.store.load_auth_store()
        if self.accounts.users_exist(store):
            raise HTTPException(status_code=409, detail="First admin already exists")
        user = self.accounts.create_auth_user(
            store,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role="admin",
            permissions=sorted(FEATURE_PERMISSIONS),
        )
        session_id, _ = self.sessions.create_login_session(store, user)
        self.store.save_auth_store(store)
        return {"status": "created", "user": public_user(user), "features": FEATURE_PERMISSIONS}, session_id

    def auth_login(self, request: Request, payload: AuthLoginRequest) -> tuple[dict[str, Any], str]:
        store = self.store.load_auth_store()
        if self.accounts.bootstrap_admin_from_env(store):
            store = self.store.load_auth_store()
        if not self.accounts.users_exist(store):
            raise HTTPException(status_code=409, detail="First admin setup required")
        self.limits.enforce_login_rate_limit(request, payload.username)
        user = find_user_by_username(store, payload.username)
        if not user or not bool(user.get("active", True)) or not verify_password(payload.password, str(user.get("password_hash") or "")):
            self.limits.record_failed_login_attempt(request, payload.username)
            raise HTTPException(status_code=401, detail="Invalid username or password")
        self.limits.clear_failed_login_attempts(request, payload.username)
        session_id, revoked_sessions = self.sessions.create_login_session(store, user)
        revoked_sessions = self.store.save_login_session(store, session_id, user, revoked_sessions)
        return {
            "status": "authenticated",
            "user": public_user(user),
            "features": FEATURE_PERMISSIONS,
            "revoked_sessions": revoked_sessions,
        }, session_id

    def auth_logout(self, session_id: str) -> dict[str, Any]:
        store = self.store.load_auth_store()
        if session_id and isinstance(store.get("sessions"), dict):
            if self.postgres():
                self.store.delete_auth_session(session_id)
            else:
                for candidate in auth_session_key_candidates(session_id):
                    store["sessions"].pop(candidate, None)
                self.store.save_auth_store(store)
        return {"status": "logged_out"}
