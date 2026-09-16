"""Real auth services/HTTP contracts with synthetic stores, failures and clocks."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
from http.cookies import SimpleCookie
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.auth.access import AccessControl
from local_inspection_service.auth.accounts import AccountDependencies, AccountService
from local_inspection_service.auth.api import register_auth_api, register_user_api
from local_inspection_service.auth.credentials import PasswordHasher
from local_inspection_service.auth.flows import AuthFlows
from local_inspection_service.auth.login_limits import LoginLimitSettings, LoginRateLimiter
from local_inspection_service.auth.middleware import SecurityDependencies, register_security_middleware
from local_inspection_service.auth.repository import AuthRepository, AuthStoreDependencies
from local_inspection_service.auth.sessions import SessionDependencies, SessionService, SessionSettings
from local_inspection_service.auth.users import UserService
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.schemas.auth import UserPasswordResetRequest, UserUpdateRequest

PASSWORD = "synthetic-password-only"


@contextmanager
def application(cookie):
    with tempfile.TemporaryDirectory(prefix="auth-api-") as temporary, patch.dict(os.environ, {
            "VANTALINE_BOOTSTRAP_ADMIN_USERNAME": "", "VANTALINE_BOOTSTRAP_ADMIN_PASSWORD": ""}):
        root = Path(temporary)
        lock = threading.RLock()
        repository = AuthRepository(AuthStoreDependencies(lambda: root, lambda: root / "auth.json", lambda: None, lambda: lock))
        account = AccountService(AccountDependencies(repository.load_auth_store, repository.save_auth_store, PasswordHasher(lambda: 120000).password_hash))
        settings = [SessionSettings(cookie, 500, 30)]
        limits = [LoginLimitSettings(60, 10, 120)]
        current = RequestIdentity()
        access = AccessControl(current)
        sessions = SessionService(lambda: settings[0], SessionDependencies(lambda: None,
            repository.load_auth_store, account.bootstrap_admin_from_env, repository.save_auth_session_touch_or_prune))
        limiter = LoginRateLimiter(lambda: limits[0])
        postgres = [False]
        users = UserService(repository, account, access, lambda: postgres[0], lambda: lock)
        flows = AuthFlows(repository, account, sessions, limiter, lambda: postgres[0], lambda: "legacy")
        app = FastAPI()
        register_security_middleware(app, SecurityDependencies(sessions.authenticate_request, account.users_exist,
            current, lambda *_: False, lambda *_: True, lambda *_: False))
        register_auth_api(app, flows, sessions, users)
        register_user_api(app, sessions, users)
        with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as client:
            yield SimpleNamespace(client=client, app=app, repository=repository, limiter=limiter,
                                  settings=settings, limits=limits, postgres=postgres, identity=current)


def bootstrap(fixture, username="admin"):
    response = fixture.client.post("/api/auth/bootstrap", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response


class AuthApiContracts(unittest.TestCase):
    def test_two_applications_and_no_private_token_in_responses(self):
        with application("first-cookie") as first, application("second-cookie") as second:
            response = bootstrap(first, "first-admin")
            token = SimpleCookie(response.headers["set-cookie"])["first-cookie"].value
            self.assertNotIn(token, response.text)
            self.assertTrue(second.client.get("/api/auth/status").json()["setup_required"])
            bootstrap(second, "second-admin")
            self.assertEqual(first.client.get("/api/auth/users").json()["users"][0]["username"], "first-admin")
            self.assertEqual(second.client.get("/api/auth/users").json()["users"][0]["username"], "second-admin")
            second.client.cookies.clear()
            second.client.cookies.set("second-cookie", token)
            self.assertEqual(second.client.get("/api/auth/users").status_code, 401)
            first.limiter.failures["user:fixture"] = [100]
            self.assertEqual(second.limiter.failures, {})
            self.assertEqual(len(first.app.routes), len(second.app.routes))
            self.assertIsNone(first.identity.get())

    def test_persistence_failure_never_sets_or_clears_cookie(self):
        with application("fixture-cookie") as fixture:
            with patch.object(fixture.repository, "save_auth_store", side_effect=RuntimeError("synthetic write failure")):
                failed = fixture.client.post("/api/auth/bootstrap", json={"username": "admin", "password": PASSWORD})
                self.assertEqual(failed.status_code, 500)
                self.assertNotIn("set-cookie", failed.headers)
            bootstrap(fixture)
            before = fixture.repository.load_auth_store()
            with patch.object(fixture.repository, "save_login_session", side_effect=RuntimeError("synthetic write failure")):
                failed = fixture.client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
                self.assertEqual(failed.status_code, 500)
                self.assertNotIn("set-cookie", failed.headers)
            self.assertEqual(fixture.repository.load_auth_store(), before)
            fixture.postgres[0] = True
            with patch.object(fixture.repository, "delete_auth_session", side_effect=RuntimeError("synthetic delete failure")):
                failed = fixture.client.post("/api/auth/logout")
                self.assertEqual(failed.status_code, 500)
                self.assertNotIn("set-cookie", failed.headers)
            self.assertEqual(fixture.repository.load_auth_store(), before)
            fixture.postgres[0] = False
            with patch.object(fixture.repository, "save_auth_store", wraps=fixture.repository.save_auth_store) as save:
                fixture.client.cookies.clear()
                self.assertEqual(fixture.client.post("/api/auth/logout").status_code, 200)
                save.assert_not_called()
                fixture.client.cookies.set("fixture-cookie", "unknown-synthetic-cookie")
                self.assertEqual(fixture.client.post("/api/auth/logout").status_code, 200)
                self.assertEqual(save.call_count, 1)

    def test_rate_limit_boundaries_and_login_failure_success(self):
        settings = [LoginLimitSettings(10, 2, 20)]
        limiter = LoginRateLimiter(lambda: settings[0])
        request = SimpleNamespace(headers={"x-forwarded-for": "192.0.2.1, 192.0.2.2"}, client=None)
        with patch("local_inspection_service.auth.login_limits.time.time", return_value=100):
            limiter.record_failed_login_attempt(request, " Alice ")
            limiter.record_failed_login_attempt(request, "alice")
        self.assertEqual(set(limiter.failures), {"user:alice", "ip:192.0.2.1"})
        with patch("local_inspection_service.auth.login_limits.time.time", return_value=100.25):
            with self.assertRaises(HTTPException) as captured:
                limiter.enforce_login_rate_limit(request, "alice")
            self.assertEqual((captured.exception.status_code, captured.exception.headers), (429, {"Retry-After": "20"}))
        limiter.prune_login_rate_limit_state(110)
        self.assertEqual(limiter.failures["user:alice"], [100, 100])
        limiter.prune_login_rate_limit_state(111)
        self.assertEqual(limiter.failures, {})
        with patch("local_inspection_service.auth.login_limits.time.time", return_value=120):
            limiter.enforce_login_rate_limit(request, "alice")
        self.assertEqual(limiter.blocked_until, {})
        settings[0] = LoginLimitSettings(10, 1, 20)
        with patch("local_inspection_service.auth.login_limits.time.time", return_value=130):
            limiter.record_failed_login_attempt(request, "alice")
            with self.assertRaises(HTTPException):
                limiter.enforce_login_rate_limit(request, "alice")
            limiter.clear_failed_login_attempts(request, "alice")
            limiter.enforce_login_rate_limit(request, "alice")
        with application("fixture-cookie") as fixture:
            bootstrap(fixture)
            created = fixture.client.post("/api/auth/users", json={"username": "inactive", "password": PASSWORD, "active": False})
            self.assertEqual(created.status_code, 200)
            for username in ("unknown", "inactive"):
                result = fixture.client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
                self.assertEqual(result.status_code, 401)
                self.assertEqual(len(fixture.limiter.failures["user:" + username]), 1)
            self.assertEqual(len(fixture.limiter.failures["ip:testclient"]), 2)
            fixture.client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
            logged_in = fixture.client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
            self.assertEqual(logged_in.status_code, 200)
            self.assertNotIn("user:admin", fixture.limiter.failures)
            self.assertNotIn("ip:testclient", fixture.limiter.failures)
            self.assertIn("user:unknown", fixture.limiter.failures)

    def test_user_revocation_matrix_and_reentrant_delete_failure(self):
        admin = {"id": "admin", "username": "admin", "role": "admin", "active": True}
        other = {"id": "other", "username": "other", "role": "user", "active": True}
        store = {"users": [admin, other], "sessions": {}}
        calls = []
        lock = threading.RLock()
        @contextmanager
        def outer_lock():
            with lock:
                calls.append(("lock", "enter"))
                try:
                    yield
                finally:
                    calls.append(("lock", "exit"))
        def revoke(user_id, *, keep_session_id=""):
            with lock:
                calls.append(("revoke", user_id, keep_session_id))
            return 2
        def save(user):
            calls.append(("save", user["id"]))
            return True
        def delete(user_id):
            with lock:
                calls.append(("delete", user_id))
                raise RuntimeError("synthetic delete failure")
        repository = SimpleNamespace(load_auth_store=lambda: copy.deepcopy(store), save_auth_user=save,
            delete_auth_sessions_for_user=revoke, delete_auth_user=delete,
            save_auth_store=lambda _: self.fail("unexpected full-store save"))
        accounts = AccountService(AccountDependencies(repository.load_auth_store, repository.save_auth_store, lambda _: "synthetic-hash"))
        identity = RequestIdentity()
        access = AccessControl(identity)
        users = UserService(repository, accounts, access, lambda: True, outer_lock)
        with identity.bind(admin):
            users.update_user("admin", UserUpdateRequest(password=PASSWORD), "current-cookie")
            self.assertEqual(calls, [("revoke", "admin", "current-cookie"), ("save", "admin")])
            calls.clear()
            users.update_user("other", UserUpdateRequest(password=PASSWORD), "actor-cookie")
            self.assertEqual(calls, [("revoke", "other", ""), ("save", "other")])
            calls.clear()
            users.reset_user_password("other", UserPasswordResetRequest(password=PASSWORD, revoke_sessions=False), "actor-cookie")
            self.assertEqual(calls, [("save", "other")])
            calls.clear()
            users.reset_user_password("admin", UserPasswordResetRequest(password=PASSWORD, revoke_sessions=True), "current-cookie")
            self.assertEqual(calls, [("revoke", "admin", "current-cookie"), ("save", "admin")])
            calls.clear()
            with self.assertRaises(HTTPException) as rejected, patch("local_inspection_service.auth.users.generate_temporary_password", side_effect=AssertionError("must reject before generation")):
                users.reset_user_password("admin", UserPasswordResetRequest(generate=True), "current-cookie")
            self.assertEqual(rejected.exception.status_code, 400)
            self.assertEqual(calls, [])
            with self.assertRaises(RuntimeError):
                users.delete_user("other")
            self.assertEqual(calls, [("lock", "enter"), ("revoke", "other", ""), ("delete", "other"), ("lock", "exit")])
        def acquire():
            got = lock.acquire(timeout=2)
            if got:
                lock.release()
            return got
        with ThreadPoolExecutor(max_workers=1) as pool:
            self.assertTrue(pool.submit(acquire).result(timeout=3))

    def test_http_self_password_changes_preserve_current_and_other_account(self):
        with application("fixture-cookie") as fixture:
            admin = bootstrap(fixture).json()["user"]
            response = fixture.client.post("/api/auth/users", json={"username": "other", "password": PASSWORD})
            self.assertEqual(response.status_code, 200)
            with TestClient(fixture.app, base_url="https://testserver") as other:
                self.assertEqual(other.post("/api/auth/login", json={"username": "other", "password": PASSWORD}).status_code, 200)
                response = fixture.client.patch("/api/auth/users/" + admin["id"], json={"password": "synthetic-updated-password"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(fixture.client.get("/api/auth/status").json()["user"]["id"], admin["id"])
                self.assertEqual(other.get("/api/auth/status").json()["user"]["username"], "other")
                response = fixture.client.post("/api/auth/users/" + admin["id"] + "/password",
                    json={"password": "synthetic-reset-password", "revoke_sessions": True})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(fixture.client.get("/api/auth/status").json()["user"]["id"], admin["id"])
                self.assertEqual(other.get("/api/auth/status").json()["user"]["username"], "other")


if __name__ == "__main__":
    unittest.main()
