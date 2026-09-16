"""Session and request authentication; runtime repositories are resolved per call."""
from collections.abc import Callable
from dataclasses import dataclass
import secrets
import time
from typing import Any, Protocol
from fastapi import Request, Response
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from ..storage.runtime_records import auth_store_from_rows, session_key_hash
from .policy import find_user, public_user


@dataclass(frozen=True)
class SessionSettings:
    cookie: str
    ttl: int
    persist_interval: int


class SaveSessionTouch(Protocol):
    def __call__(self, store: dict[str, Any], session_id: str, session: dict[str, Any] | None, *, prune_expired: bool) -> None: ...


@dataclass(frozen=True)
class SessionDependencies:
    runtime_repository: Callable[[], PostgresRuntimeRepository | None]
    load_store: Callable[[], dict[str, Any]]
    bootstrap_admin: Callable[[dict[str, Any]], bool]
    save_touch_or_prune: SaveSessionTouch


def prune_expired_sessions(store: dict[str, Any]) -> bool:
    now = int(time.time())
    sessions = store.get("sessions") if isinstance(store.get("sessions"), dict) else {}
    active = {
        session_id: session
        for session_id, session in sessions.items()
        if isinstance(session, dict) and int(session.get("expires_at") or 0) > now
    }
    changed = len(active) != len(sessions)
    store["sessions"] = active
    return changed


def request_is_https(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return request.url.scheme == "https" or forwarded_proto == "https"


def revoke_user_sessions(store: dict[str, Any], user_id: str, *, keep_session_id: str = "") -> int:
    sessions = store.get("sessions") if isinstance(store.get("sessions"), dict) else {}
    keep_session_ids = {keep_session_id, session_key_hash(keep_session_id)} if keep_session_id else set()
    revoked = 0
    kept: dict[str, Any] = {}
    for session_id, session in sessions.items():
        if (
            isinstance(session, dict)
            and str(session.get("user_id") or "") == str(user_id or "")
            and session_id not in keep_session_ids
        ):
            revoked += 1
            continue
        kept[session_id] = session
    store["sessions"] = kept
    return revoked


class SessionService:
    def __init__(self, settings: Callable[[], SessionSettings], dependencies: SessionDependencies):
        self.settings = settings
        self.dependencies = dependencies

    def set_session_cookie(self, response: Response, request: Request, session_id: str) -> None:
        response.set_cookie(
            self.settings().cookie,
            session_id,
            max_age=self.settings().ttl,
            httponly=True,
            secure=request_is_https(request),
            samesite="lax",
            path="/",
        )

    def clear_session_cookie(self, response: Response, request: Request) -> None:
        response.delete_cookie(self.settings().cookie, path="/", secure=request_is_https(request), samesite="lax")

    def create_session(self, store: dict[str, Any], user: dict[str, Any]) -> str:
        session_id = secrets.token_urlsafe(32)
        now = int(time.time())
        store.setdefault("sessions", {})[session_id] = {
            "user_id": user["id"],
            "created_at": now,
            "last_seen_at": now,
            "expires_at": now + self.settings().ttl,
        }
        return session_id

    def create_login_session(self, store: dict[str, Any], user: dict[str, Any]) -> tuple[str, int]:
        session_id = self.create_session(store, user)
        revoked_sessions = revoke_user_sessions(store, str(user.get("id") or ""), keep_session_id=session_id)
        return session_id, revoked_sessions

    def authenticate_request(self, request: Request, *, indexed: bool = False) -> tuple[dict[str, Any] | None, dict[str, Any], bool]:
        # Protected hot paths never load every account/session. Auth management keeps
        # the existing full-store path, including first-admin bootstrap semantics.
        repository = self.dependencies.runtime_repository() if indexed else None
        if repository is not None:
            session_id = request.cookies.get(self.settings().cookie, "")
            user_row, session_row, has_users = repository.authenticate_session(
                session_key_hash(session_id) if session_id else "",
                now=int(time.time()), ttl=self.settings().ttl,
                persist_interval=self.settings().persist_interval,
            )
            store = auth_store_from_rows([user_row] if user_row else [], [session_row] if session_row else [])
            session = store["sessions"].get(str((session_row or {}).get("id_hash") or ""))
            identity = str((session or {}).get("user_id") or "")
            selected_user = find_user(store, identity) if identity else None
            if selected_user and identity == str((session_row or {}).get("user_id") or "") and bool(selected_user.get("active", True)):
                return public_user(selected_user), store, False
            if not has_users:
                return self.authenticate_request(request)
            if has_users:
                # Used only by middleware's setup-required check; never persisted.
                store["users"] = [{"id": "existing-account"}]
            return None, store, False
        store = self.dependencies.load_store()
        changed = prune_expired_sessions(store)
        expired_sessions_pruned = changed
        if self.dependencies.bootstrap_admin(store):
            store = self.dependencies.load_store()
        session_id = request.cookies.get(self.settings().cookie, "")
        sessions = store.get("sessions", {}) if isinstance(store.get("sessions"), dict) else {}
        session = sessions.get(session_id) if session_id else None
        if session is None and session_id:
            session = sessions.get(session_key_hash(session_id))
        user = find_user(store, str((session or {}).get("user_id") or "")) if isinstance(session, dict) else None
        if not user or not bool(user.get("active", True)):
            if expired_sessions_pruned:
                self.dependencies.save_touch_or_prune(store, "", None, prune_expired=True)
            return None, store, changed
        now = int(time.time())
        prev_seen = int(session.get("last_seen_at") or 0)
        session["last_seen_at"] = now
        session["expires_at"] = now + self.settings().ttl
        # Throttle disk writes: only persist the slid expiry when something else
        # changed (pruned sessions) or enough time has elapsed since the last write.
        if expired_sessions_pruned or (now - prev_seen) >= self.settings().persist_interval:
            changed = True
            self.dependencies.save_touch_or_prune(store, session_id, session, prune_expired=expired_sessions_pruned)
        return public_user(user), store, changed
