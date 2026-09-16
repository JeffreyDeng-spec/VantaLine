"""Authentication services and real ASGI security contracts using synthetic identities."""
import asyncio
import copy
from http.cookies import SimpleCookie
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anyio
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
import httpx
from local_inspection_service.auth.accounts import AccountDependencies, AccountService
from local_inspection_service.auth.access import AccessControl
from local_inspection_service.auth.middleware import SecurityDependencies, register_security_middleware
from local_inspection_service.auth.sessions import SessionDependencies, SessionService, SessionSettings
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.storage.runtime_records import session_key_hash


def identity(name):
    return {"id": name, "username": name, "role": "user", "permissions": [], "active": True}


class AuthContracts(unittest.TestCase):
    def test_dynamic_accounts_and_session_persistence(self):
        persisted = {"users": [], "sessions": {}}
        def save(store):
            persisted.clear()
            persisted.update(copy.deepcopy(store))
        accounts = AccountService(AccountDependencies(lambda: copy.deepcopy(persisted), save, lambda _: "synthetic-hash"))
        settings = [SessionSettings("fixture", 500, 30)]
        writes = []
        def touch(store, session_id, session, *, prune_expired):
            writes.append((session_id, copy.deepcopy(session), prune_expired))
            save(store)
        sessions = SessionService(lambda: settings[0], SessionDependencies(
            lambda: None, lambda: copy.deepcopy(persisted), accounts.bootstrap_admin_from_env, touch))
        with patch.dict(os.environ, {"VANTALINE_BOOTSTRAP_ADMIN_USERNAME": "", "VANTALINE_BOOTSTRAP_ADMIN_PASSWORD": ""}):
            self.assertFalse(accounts.bootstrap_admin_from_env(persisted))
            os.environ["VANTALINE_BOOTSTRAP_ADMIN_USERNAME"] = "fixture-admin"
            os.environ["VANTALINE_BOOTSTRAP_ADMIN_PASSWORD"] = "synthetic-password-only"
            with patch("local_inspection_service.auth.sessions.time.time", return_value=100):
                self.assertIsNone(sessions.authenticate_request(SimpleNamespace(cookies={}))[0])
            self.assertEqual(persisted["users"][0]["username"], "fixture-admin")
        persisted["users"] = [identity("alice")]
        persisted["sessions"] = {session_key_hash("cookie"): {
            "user_id": "alice", "created_at": 90, "last_seen_at": 100, "expires_at": 1000}}
        request = SimpleNamespace(cookies={"fixture": "cookie"})
        with patch("local_inspection_service.auth.sessions.time.time", return_value=110):
            self.assertEqual(sessions.authenticate_request(request)[0]["id"], "alice")
        self.assertEqual(writes, [])
        with patch("local_inspection_service.auth.sessions.time.time", return_value=130):
            sessions.authenticate_request(request)
        self.assertEqual(writes[-1], ("cookie", {"user_id": "alice", "created_at": 90,
            "last_seen_at": 130, "expires_at": 630}, False))
        persisted["sessions"]["expired"] = {"user_id": "alice", "expires_at": 140}
        with patch("local_inspection_service.auth.sessions.time.time", return_value=140):
            sessions.authenticate_request(request)
        self.assertTrue(writes[-1][2])
        self.assertNotIn("expired", persisted["sessions"])
        settings[0] = SessionSettings("changed-cookie", 900, 30)
        with patch("local_inspection_service.auth.sessions.time.time", return_value=180):
            self.assertEqual(sessions.authenticate_request(SimpleNamespace(cookies={"changed-cookie": "cookie"}))[0]["id"], "alice")
        self.assertEqual(writes[-1][1]["expires_at"], 1080)

    def test_indexed_fallback_and_cookie_attributes(self):
        events = []
        store = {"users": [], "sessions": {}}
        def load():
            events.append("load")
            return copy.deepcopy(store)
        def bootstrap(value):
            events.append("bootstrap")
            return False
        repository = SimpleNamespace(authenticate_session=lambda *args, **kwargs: (None, None, False))
        sessions = SessionService(lambda: SessionSettings("fixture", 500, 30), SessionDependencies(
            lambda: repository, load, bootstrap, lambda *a, **k: self.fail("unexpected write")))
        self.assertEqual(sessions.authenticate_request(SimpleNamespace(cookies={}), indexed=True), (None, store, False))
        self.assertEqual(events, ["load", "bootstrap"])
        events.clear()
        repository.authenticate_session = lambda *args, **kwargs: (None, None, True)
        self.assertEqual(sessions.authenticate_request(SimpleNamespace(cookies={}), indexed=True)[1]["users"], [{"id": "existing-account"}])
        self.assertEqual(events, [])
        app = FastAPI()
        @app.post("/cookie")
        def set_cookie(request: Request, response: Response):
            sessions.set_session_cookie(response, request, "synthetic-cookie")
            return {}
        @app.delete("/cookie")
        def clear_cookie(request: Request, response: Response):
            sessions.clear_session_cookie(response, request)
            return {}
        with TestClient(app, base_url="http://testserver") as client:
            plain = SimpleCookie(client.post("/cookie").headers["set-cookie"])["fixture"]
            self.assertEqual(plain["max-age"], "500")
            self.assertEqual((plain["path"], plain["samesite"], plain["httponly"], plain["secure"]), ("/", "lax", True, ""))
            secure = SimpleCookie(client.post("/cookie", headers={"x-forwarded-proto": "https, http"}).headers["set-cookie"])["fixture"]
            self.assertTrue(secure["secure"])
            deleted = SimpleCookie(client.delete("/cookie", headers={"x-forwarded-proto": "https"}).headers["set-cookie"])["fixture"]
            self.assertEqual((deleted["max-age"], deleted["path"], deleted["samesite"], deleted["secure"]), ("0", "/", "lax", True))
        with TestClient(app, base_url="https://testserver") as secure_client:
            for response in (secure_client.post("/cookie"), secure_client.delete("/cookie")):
                self.assertTrue(SimpleCookie(response.headers["set-cookie"])["fixture"]["secure"])

    def test_middleware_real_asgi_isolation_headers_and_public_exceptions(self):
        def create():
            app = FastAPI()
            current = RequestIdentity()
            access = AccessControl(current)
            calls = []
            def authenticate(request, *, indexed=False):
                calls.append((request.url.path, indexed))
                who = request.cookies.get("fixture")
                return identity(who) if who else None, {"users": [{"id": "existing"}]}, False
            register_security_middleware(app, SecurityDependencies(
                authenticate, lambda store: bool(store["users"]), current,
                lambda path, user: path.startswith("/outputs/" + user["id"] + "/"),
                lambda origin, host: origin == "https://" + host,
                lambda origin: origin == "https://allowed.invalid"))
            @app.get("/api/probe/{mode}")
            async def probe(mode: str, request: Request):
                before = access.current_auth_user()["id"]
                await asyncio.sleep(0)
                threaded = await anyio.to_thread.run_sync(lambda: access.current_auth_user()["id"])
                if mode == "failure":
                    raise RuntimeError("synthetic endpoint failure")
                return [before, threaded, current.get()["id"], request.state.user["id"]]
            @app.get("/api/synchronous")
            def synchronous():
                return access.current_auth_user()["id"]
            @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT"])
            def fallback(path: str):
                return {"path": path, "user": current.get()}
            return app, current, calls
        first, first_identity, calls = create()
        second, second_identity, _ = create()
        self.assertIsNot(first_identity, second_identity)
        self.assertEqual(len(first.user_middleware), 1)
        self.assertEqual(len(second.user_middleware), 1)
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=first, raise_app_exceptions=False), base_url="https://testserver") as a, httpx.AsyncClient(transport=httpx.ASGITransport(app=second), base_url="https://testserver") as b:
                async def get(client, path, user):
                    return await client.get(path, headers={"cookie": "fixture=" + user})
                responses = await asyncio.gather(get(a, "/api/probe/ok", "alice"), get(a, "/api/probe/ok", "bob"), get(b, "/api/probe/ok", "carol"))
                self.assertEqual([r.json() for r in responses], [[name] * 4 for name in ("alice", "bob", "carol")])
                self.assertEqual((await get(a, "/api/probe/failure", "alice")).status_code, 500)
                self.assertEqual((await get(a, "/api/synchronous", "bob")).json(), "bob")
                self.assertIsNone(first_identity.get())
                self.assertIsNone(second_identity.get())
        asyncio.run(exercise())
        with TestClient(first, base_url="https://testserver") as client:
            denied = client.get("/api/synchronous")
            self.assertEqual(denied.status_code, 401)
            self.assertNotIn("X-Frame-Options", denied.headers)  # Preserve early-return order.
            client.cookies.set("fixture", "alice")
            allowed = client.get("/api/synchronous")
            for key, value in {"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer", "Cache-Control": "no-store",
                    "Strict-Transport-Security": "max-age=31536000; includeSubDomains"}.items():
                self.assertEqual(allowed.headers[key], value)
            self.assertIn("serial=(self)", allowed.headers["Permissions-Policy"])
            self.assertIn("frame-ancestors 'none'", allowed.headers["Content-Security-Policy"])
            self.assertEqual(client.get("/outputs/bob/private.png").status_code, 404)
            self.assertEqual(client.get("/outputs/alice/private.png").headers["Cache-Control"], "private, max-age=600, stale-while-revalidate=86400")
            self.assertEqual(client.get("/static/image.png").headers["Cache-Control"], "public, max-age=604800, immutable")
            self.assertEqual(client.get("/react-preview").headers["Cache-Control"], "no-store, no-cache, must-revalidate, max-age=0")
            self.assertEqual(client.post("/api/auth/logout", headers={"origin": "https://blocked.invalid"}).status_code, 403)
            self.assertEqual(client.post("/api/auth/logout", headers={"origin": "https://allowed.invalid"}).status_code, 200)
            client.cookies.clear()
            before = len(calls)
            for method, path in [("GET", "/api/training/runpod/datasets/a/b/dataset.zip"), ("HEAD", "/api/training/runpod/datasets/a/b/dataset.zip"), ("PUT", "/api/training/runpod/artifacts/a/b/run.zip")]:
                self.assertEqual(client.request(method, path).status_code, 200)
            self.assertEqual(len(calls), before)
            for method, path in [("POST", "/api/training/runpod/datasets/a/b/dataset.zip"), ("GET", "/api/training/runpod/datasets/a/b/dataset.zip/extra"), ("GET", "/api/training/runpod/artifacts/a/b/run.zip"), ("PUT", "/api/training/runpod/artifacts/a/b/run.zip/extra")]:
                self.assertEqual(client.request(method, path).status_code, 401)


if __name__ == "__main__":
    unittest.main()
