"""Authentication persistence; callers supply thread-owned repositories, never a connection."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any
import uuid
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from ..storage.runtime_records import auth_store_from_rows, auth_user_rows, auth_session_rows, row_raw_json_list, session_key_hash


@dataclass(frozen=True)
class AuthStoreDependencies:
    data_directory: Callable[[], Path]
    auth_path: Callable[[], Path]
    runtime_repository: Callable[[], PostgresRuntimeRepository | None]
    write_lock: Callable[[], AbstractContextManager]


def empty_auth_store() -> dict[str, Any]:
    return {"users": [], "sessions": {}}


def auth_user_row_for_user(user: dict[str, Any]) -> dict[str, Any] | None:
    rows = auth_user_rows({"users": [user]})
    return rows[0] if rows else None


def auth_session_key_candidates(session_id: str) -> tuple[str, ...]:
    clean_id = str(session_id or "").strip()
    if not clean_id:
        return ()
    return tuple(dict.fromkeys([clean_id, session_key_hash(clean_id)]))


def auth_session_from_store(store: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    sessions = store.get("sessions") if isinstance(store.get("sessions"), dict) else {}
    for candidate in auth_session_key_candidates(session_id):
        session = sessions.get(candidate)
        if isinstance(session, dict):
            return session
    return None


def auth_session_row_for_session(session_id: str, session: dict[str, Any]) -> dict[str, Any] | None:
    rows = auth_session_rows({"sessions": {session_id: session}})
    return rows[0] if rows else None


class AuthRepository:
    def __init__(self, dependencies: AuthStoreDependencies):
        self.dependencies = dependencies

    def load_auth_store(self) -> dict[str, Any]:
        self.dependencies.data_directory().mkdir(parents=True, exist_ok=True)
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            return auth_store_from_rows(repository.fetch_all("users"), repository.fetch_all("auth_sessions"))
        if not self.dependencies.auth_path().exists():
            return empty_auth_store()
        try:
            raw = json.loads(self.dependencies.auth_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return empty_auth_store()
        users = raw.get("users") if isinstance(raw.get("users"), list) else []
        sessions = raw.get("sessions") if isinstance(raw.get("sessions"), dict) else {}
        return {"users": users, "sessions": sessions}

    def save_auth_store(self, store: dict[str, Any]) -> None:
        self.dependencies.data_directory().mkdir(parents=True, exist_ok=True)
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            with self.dependencies.write_lock():
                repository.replace_tables({"users": auth_user_rows(store), "auth_sessions": auth_session_rows(store)})
            return
        payload = json.dumps(store, indent=2, ensure_ascii=False)
        # Serialize writes and use a unique temp file so concurrent request threads
        # cannot clobber a shared temp path mid-write (which corrupted the store and
        # surfaced as random FileNotFound/decode failures under load).
        with self.dependencies.write_lock():
            tmp_path = self.dependencies.auth_path().with_suffix(f".json.tmp.{uuid.uuid4().hex}")
            try:
                tmp_path.write_text(payload, encoding="utf-8")
                tmp_path.replace(self.dependencies.auth_path())
            finally:
                tmp_path.unlink(missing_ok=True)

    def save_auth_user(self, user: dict[str, Any]) -> bool:
        row = auth_user_row_for_user(user)
        if not row:
            return False
        repository = self.dependencies.runtime_repository()
        if repository is None:
            return False
        with self.dependencies.write_lock():
            repository.upsert_row("users", row)
        return True

    def delete_auth_user(self, user_id: str) -> bool:
        clean_user_id = str(user_id or "").strip()
        if not clean_user_id:
            return False
        repository = self.dependencies.runtime_repository()
        if repository is None:
            return False
        with self.dependencies.write_lock():
            if repository.fetch_by_primary_key("users", {"id": clean_user_id}) is None:
                return False
            repository.delete_by_primary_key("users", {"id": clean_user_id})
        return True

    def save_auth_session(self, session_id: str, session: dict[str, Any]) -> None:
        row = auth_session_row_for_session(session_id, session)
        if not row:
            return
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            with self.dependencies.write_lock():
                repository.upsert_row("auth_sessions", row)
            return
        store = self.load_auth_store()
        store.setdefault("sessions", {})[session_id] = dict(session)
        self.save_auth_store(store)

    def delete_auth_session(self, session_id: str) -> bool:
        candidates = auth_session_key_candidates(session_id)
        if not candidates:
            return False
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            deleted = False
            with self.dependencies.write_lock():
                for candidate in candidates:
                    if repository.fetch_by_primary_key("auth_sessions", {"id_hash": candidate}) is not None:
                        repository.delete_by_primary_key("auth_sessions", {"id_hash": candidate})
                        deleted = True
            return deleted
        store = self.load_auth_store()
        sessions = store.get("sessions") if isinstance(store.get("sessions"), dict) else {}
        deleted = False
        for candidate in candidates:
            deleted = sessions.pop(candidate, None) is not None or deleted
        if deleted:
            self.save_auth_store(store)
        return deleted

    def delete_expired_auth_sessions(self, now: int | None = None) -> int:
        repository = self.dependencies.runtime_repository()
        if repository is None:
            return 0
        cutoff = int(now or time.time())
        deleted = 0
        with self.dependencies.write_lock():
            for row in repository.fetch_all("auth_sessions"):
                try:
                    expires_at = int(row.get("expires_at") or 0)
                except (TypeError, ValueError):
                    expires_at = 0
                id_hash = str(row.get("id_hash") or "")
                if id_hash and expires_at <= cutoff:
                    repository.delete_by_primary_key("auth_sessions", {"id_hash": id_hash})
                    deleted += 1
        return deleted

    def delete_auth_sessions_for_user(self, user_id: str, *, keep_session_id: str = "") -> int:
        repository = self.dependencies.runtime_repository()
        if repository is None:
            return 0
        clean_user_id = str(user_id or "").strip()
        if not clean_user_id:
            return 0
        keep_hashes = set(auth_session_key_candidates(keep_session_id))
        deleted = 0
        with self.dependencies.write_lock():
            for row in repository.fetch_all("auth_sessions"):
                raw_sessions = row_raw_json_list([row])
                session = raw_sessions[0] if raw_sessions else {}
                id_hash = str(row.get("id_hash") or session.get("id_hash") or "")
                if (
                    id_hash
                    and id_hash not in keep_hashes
                    and str(session.get("user_id") or row.get("user_id") or "") == clean_user_id
                ):
                    repository.delete_by_primary_key("auth_sessions", {"id_hash": id_hash})
                    deleted += 1
        return deleted

    def save_login_session(self, store: dict[str, Any], session_id: str, user: dict[str, Any], revoked_sessions: int = 0) -> int:
        repository = self.dependencies.runtime_repository()
        if repository is None:
            self.save_auth_store(store)
            return revoked_sessions
        session = auth_session_from_store(store, session_id)
        if not session:
            return revoked_sessions
        with self.dependencies.write_lock():
            actual_revoked = self.delete_auth_sessions_for_user(str(user.get("id") or ""), keep_session_id=session_id)
            self.save_auth_session(session_id, session)
        return actual_revoked

    def save_auth_session_touch_or_prune(self, store: dict[str, Any], session_id: str, session: dict[str, Any] | None, *, prune_expired: bool) -> None:
        repository = self.dependencies.runtime_repository()
        if repository is None:
            self.save_auth_store(store)
            return
        if prune_expired:
            self.delete_expired_auth_sessions()
        if session:
            self.save_auth_session(session_id, session)
