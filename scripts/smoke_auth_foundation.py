"""Real authentication foundations with synthetic credentials and isolated storage."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from local_inspection_service.auth.credentials import PasswordHasher, generate_temporary_password, verify_password
from local_inspection_service.auth.policy import normalize_permissions, public_user, user_has_permission
from local_inspection_service.auth.preferences import normalize_task_navigation_ids
from local_inspection_service.auth.repository import AuthRepository, AuthStoreDependencies, auth_session_from_store
from local_inspection_service.auth.repository import auth_session_row_for_session
from local_inspection_service.storage.runtime_records import session_key_hash
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl


def user(identity):
    return {"id": identity, "username": identity, "role": "user", "permissions": ["inspection"],
            "password_hash": "synthetic-hash", "active": True, "created_at": 1, "updated_at": 1}


def session(identity, expires=1000):
    return {"user_id": identity, "created_at": 1, "last_seen_at": 1, "expires_at": expires}


def policy_contract():
    hasher = PasswordHasher(lambda: 120000)
    first = hasher.password_hash("synthetic-password-only")
    second = hasher.password_hash("synthetic-password-only")
    assert first != second and first.startswith("pbkdf2_sha256$120000$")
    assert verify_password("synthetic-password-only", first)
    assert not verify_password("wrong-synthetic-password", first)
    for malformed in ("invalid", "sha256$1$aa$bb", "pbkdf2_sha256$bad$aa$bb", "pbkdf2_sha256$1$zz$zz"):
        assert not verify_password("fixture", malformed)
    try: hasher.password_hash("short")
    except HTTPException as exc: assert exc.status_code == 400
    else: raise AssertionError("short password accepted")
    assert len(generate_temporary_password(1)) == 12
    assert len(generate_temporary_password(99)) == 48
    assert normalize_permissions(["inspection", "inspection", "user_management", "ai_config", "unknown"]) == ["inspection"]
    assert not user_has_permission({**user("member"), "permissions": ["ai_config"]}, "ai_config")
    assert user_has_permission({"role": "admin"}, "ai_config")
    assert "password_hash" not in public_user(user("member"))
    assert normalize_task_navigation_ids(["same", "same", "", "x" * 201]) == ["same"]
    assert len(normalize_task_navigation_ids([str(i) for i in range(250)])) == 200


def json_contract():
    with tempfile.TemporaryDirectory(prefix="auth-json-") as temporary:
        root = Path(temporary)
        path = root / "auth.json"
        lock = threading.RLock()
        repository = AuthRepository(AuthStoreDependencies(lambda: root, lambda: path, lambda: None, lambda: lock))
        assert repository.load_auth_store() == {"users": [], "sessions": {}}
        path.write_text("{invalid", encoding="utf-8")
        assert repository.load_auth_store() == {"users": [], "sessions": {}}
        store = {"users": [user("alice"), user("bob")], "sessions": {"cookie": session("alice")}}
        repository.save_auth_store(store)
        assert repository.load_auth_store() == store
        assert not repository.save_auth_user({**user("alice"), "active": False})
        assert repository.load_auth_store() == store  # JSON caller must explicitly save the full store.
        repository.save_auth_session("bob-cookie", session("bob"))
        assert auth_session_from_store(repository.load_auth_store(), "bob-cookie")["user_id"] == "bob"
        assert repository.delete_auth_session("cookie")
        assert not repository.delete_auth_session("cookie")
        assert auth_session_from_store(repository.load_auth_store(), "bob-cookie") is not None
        repository.save_auth_store({"users": store["users"], "sessions": {
            "mixed": session("alice"), session_key_hash("mixed"): session("alice"), "bob-cookie": session("bob")}})
        assert repository.delete_auth_session("mixed")
        assert set(repository.load_auth_store()["sessions"]) == {"bob-cookie"}
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: repository.save_auth_store({"users": [user(f"complete-{i}")], "sessions": {}}), range(20)))
        final = json.loads(path.read_text(encoding="utf-8"))
        assert len(final["users"]) == 1 and final["users"][0]["id"].startswith("complete-")
        assert not list(root.glob("auth.json.tmp.*"))


def postgres_contract(dsn):
    import psycopg
    from psycopg import sql
    schema = "auth_foundation_" + uuid.uuid4().hex
    connections = []
    def create():
        connection = psycopg.connect(dsn)
        connections.append(connection)
        return SimpleNamespace(repository=PostgresRuntimeRepository(connection, "fixture", schema), store="postgres")
    factory = ThreadRepositoryFactory(create, lambda: schema)
    with tempfile.TemporaryDirectory(prefix="auth-pg-") as temporary, psycopg.connect(dsn, autocommit=True) as control:
        root = Path(temporary)
        path = root / "must-not-exist.json"
        lock = threading.RLock()
        repository = AuthRepository(AuthStoreDependencies(lambda: root, lambda: path,
            lambda: factory.selection().repository, lambda: lock))
        control.execute(postgres_ddl(schema))
        try:
            with factory.thread_scope():
                repository.save_auth_store({"users": [user("alice"), user("bob")], "sessions": {
                    "old-alice": session("alice"), "keep-bob": session("bob"),
                    "expired": session("alice", 50), "boundary": session("alice", 100)}})
                assert repository.delete_expired_auth_sessions(100) == 2
                assert repository.save_auth_user({**user("alice"), "display_name": "Changed"})
                users = repository.load_auth_store()["users"]
                assert len(users) == 2 and next(u for u in users if u["id"] == "alice")["display_name"] == "Changed"
                assert auth_session_from_store(repository.load_auth_store(), "keep-bob")["user_id"] == "bob"
                loaded = repository.load_auth_store()
                loaded["sessions"]["new-alice"] = session("alice")
                assert repository.save_login_session(loaded, "new-alice", user("alice"), revoked_sessions=99) == 1
                active = repository.load_auth_store()
                assert auth_session_from_store(active, "old-alice") is None
                assert auth_session_from_store(active, "new-alice")["user_id"] == "alice"
                assert auth_session_from_store(active, "keep-bob")["user_id"] == "bob"
                assert repository.delete_auth_session("new-alice")
                assert not repository.delete_auth_session("new-alice")
                # Seed legacy raw keys directly: the regular adapter deliberately hashes them.
                raw_repository = factory.selection().repository
                for cookie in ("mixed", "retire-mixed"):
                    repository.save_auth_session(cookie, session("alice", 1000))
                    row = auth_session_row_for_session(cookie, session("alice", 1000))
                    row["id_hash"] = cookie
                    row["raw_json"]["id_hash"] = cookie
                    raw_repository.upsert_row("auth_sessions", row)
                assert repository.save_login_session(repository.load_auth_store(), "mixed", user("alice")) == 2
                active = repository.load_auth_store()["sessions"]
                assert {"mixed", session_key_hash("mixed"), session_key_hash("keep-bob")} <= set(active)
                assert "retire-mixed" not in active and session_key_hash("retire-mixed") not in active
                assert repository.delete_auth_session("mixed")
                assert auth_session_from_store(repository.load_auth_store(), "mixed") is None
                repository.save_auth_session("boundary-touch", session("alice", 100))
                with patch("local_inspection_service.auth.repository.time.time", return_value=100):
                    repository.save_auth_session_touch_or_prune({}, "boundary-touch", session("alice", 200), prune_expired=True)
                assert auth_session_from_store(repository.load_auth_store(), "boundary-touch")["expires_at"] == 200
                # Exercise the actual reentrant path, then prove exception unwinding releases it.
                with patch.object(repository, "save_auth_session", side_effect=RuntimeError("synthetic write failure")):
                    try:
                        repository.save_login_session({"sessions": {"failed": session("alice")}}, "failed", user("alice"))
                    except RuntimeError as exc:
                        assert str(exc) == "synthetic write failure"
                    else:
                        raise AssertionError("write failure swallowed")
                def acquire_after_failure():
                    acquired = lock.acquire(timeout=2)
                    if acquired:
                        lock.release()
                    return acquired
                with ThreadPoolExecutor(max_workers=1) as pool:
                    assert pool.submit(acquire_after_failure).result(timeout=3)
                assert auth_session_from_store(repository.load_auth_store(), "keep-bob")["user_id"] == "bob"
                repository.save_auth_session_touch_or_prune({}, "touched-bob", session("bob", 10000000000), prune_expired=True)
                assert auth_session_from_store(repository.load_auth_store(), "touched-bob") is not None
            def write(index):
                with factory.thread_scope():
                    repository.save_auth_session(f"parallel-{index}", session("alice", 10000000000))
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(write, range(30)))
            with factory.thread_scope():
                loaded = repository.load_auth_store()
                assert all(auth_session_from_store(loaded, f"parallel-{index}") is not None for index in range(30))
                assert repository.delete_auth_sessions_for_user("alice", keep_session_id="parallel-0") == 29
                assert auth_session_from_store(repository.load_auth_store(), "parallel-0") is not None
                assert repository.delete_auth_user("alice")
                assert not repository.delete_auth_user("alice")
                assert [u["id"] for u in repository.load_auth_store()["users"]] == ["bob"]
            assert not path.exists()
            assert all(connection.closed for connection in connections)
        finally:
            factory.clear()
            control.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()
    policy_contract()
    json_contract()
    if args.postgres:
        postgres_contract(os.environ["VANTALINE_POSTGRES_DSN"])
    print("PASS auth policy/passwords, atomic JSON and optional PostgreSQL account/session isolation")
