"""Owner assignment, hidden denial and concurrent request identity contracts."""
import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anyio
from fastapi import FastAPI, HTTPException, Request
import httpx
from local_inspection_service.auth.access import AccessControl
from local_inspection_service.records.access import RecordAccess
from local_inspection_service.records.ownership import RecordOwnership
from local_inspection_service.runtime.identity import RequestIdentity


def account(name, role="user"):
    return {"id": name, "username": name, "role": role}


class RecordAccessContract(unittest.TestCase):
    def test_assignment_is_lazy_and_preserves_special_ids(self):
        identity = RequestIdentity()
        calls = []
        users = {"bob": account("bob"), "legacy": account("legacy")}
        def lookup(target):
            calls.append(target)
            return users.get(target)
        access = RecordAccess(identity, RecordOwnership("legacy_admin", "system"),
                              AccessControl(identity).current_auth_user, lookup)
        self.assertEqual(access.current_owner_fields(), {})
        with identity.bind({"id": "alice", "username": None}):
            self.assertEqual(access.current_owner_fields(), {"owner_user_id": "alice", "owner_username": ""})
        self.assertEqual(access.current_owner_fields(), {})
        for target in (None, "", "bob", "legacy_admin", "system", "missing"):
            self.assertEqual(access.owner_fields_for_new_record(account("alice"), target),
                             {"owner_user_id": "alice", "owner_username": "alice"})
        admin = account("admin", " ADMIN ")
        for target, expected in ((None, "admin"), ("  ", "admin"), (" legacy_admin ", "legacy_admin"), (" system ", "system")):
            self.assertEqual(access.owner_fields_for_new_record(admin, target)["owner_user_id"], expected)
        self.assertEqual(calls, [])
        self.assertEqual(access.owner_fields_for_new_record(admin, " bob ")["owner_username"], "bob")
        users["bob"]["username"] = "renamed"
        users["bob"]["active"] = False
        self.assertEqual(access.owner_fields_for_new_record(admin, "bob")["owner_username"], "renamed")
        self.assertEqual(access.owner_fields_for_new_record(admin, "legacy")["owner_user_id"], "legacy")
        del users["legacy"]
        with self.assertRaises(HTTPException) as caught:
            access.owner_fields_for_new_record(admin, "legacy")
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (404, "目标用户不存在"))
        self.assertEqual(calls, ["bob", "bob", "legacy", "legacy"])
        def unavailable(_):
            raise HTTPException(status_code=503, detail="synthetic store unavailable")
        failed = RecordAccess(identity, access.ownership, access.current_user, unavailable)
        with self.assertRaises(HTTPException) as caught:
            failed.owner_fields_for_new_record(admin, "bob")
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (503, "synthetic store unavailable"))
        alternate = RecordAccess(RequestIdentity(), RecordOwnership("archive", "robot"), lambda: admin, lookup)
        self.assertEqual(alternate.owner_fields_for_new_record(admin, "robot"), {"owner_user_id": "robot", "owner_username": "system"})
        self.assertEqual(alternate.owner_fields_for_new_record(admin, "archive"), {"owner_user_id": "archive", "owner_username": "archive"})
        self.assertEqual(calls, ["bob", "bob", "legacy", "legacy"])

    def test_explicit_identity_read_write_and_hidden_denial(self):
        identity = RequestIdentity()
        calls = []
        def current():
            calls.append("current")
            return AccessControl(identity).current_auth_user()
        def unexpected(_):
            raise AssertionError("record guard must not read user storage")
        access = RecordAccess(identity, RecordOwnership("legacy_admin", "system"), current, unexpected)
        record = {"owner_user_id": "alice", "shared_with_user_ids": ["bob"]}
        access.require_record_access(record, account("alice"), write=True)
        access.require_record_access(record, account("bob"))
        access.require_record_access(record, account("admin", "admin"), write=True)
        self.assertEqual(calls, [])
        for user, write in ((account("bob"), True), (account("stranger"), False)):
            with self.assertRaises(HTTPException) as caught:
                access.require_record_access(record, user, write=write)
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (404, "Resource not found"))
        for user in (None, {}):
            with self.assertRaises(HTTPException) as caught:
                access.require_record_access(record, user)
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (401, "Authentication required"))
        with identity.bind(account("alice")):
            access.require_record_access(record, {}, write=True)
            with self.assertRaises(HTTPException):
                access.require_record_access(record, account("bob"), write=True)
            with self.assertRaises(RuntimeError):
                with identity.bind(account("bob")):
                    self.assertEqual(access.current_owner_fields()["owner_user_id"], "bob")
                    raise RuntimeError("synthetic nested context failure")
            self.assertEqual(access.current_owner_fields()["owner_user_id"], "alice")
        self.assertEqual(access.current_owner_fields(), {})
        self.assertEqual(calls, ["current", "current", "current"])

    def test_real_http_concurrent_thread_dispatch_and_failure_restore(self):
        async def scenario():
            def composition():
                identity = RequestIdentity()
                access = RecordAccess(identity, RecordOwnership("legacy_admin", "system"),
                                      AccessControl(identity).current_auth_user, lambda _: None)
                app = FastAPI()
                @app.middleware("http")
                async def bind(request: Request, call_next):
                    name = request.headers.get("x-fixture-user")
                    with identity.bind(account(name) if name else None):
                        return await call_next(request)
                @app.get("/owner")
                async def owner():
                    await asyncio.sleep(0)
                    def read_and_guard():
                        fields = access.current_owner_fields()
                        if fields:
                            access.require_record_access(fields, write=True)
                        return fields
                    return await anyio.to_thread.run_sync(read_and_guard)
                @app.get("/record")
                def record(write: bool = False, fail: bool = False):
                    access.require_record_access({"owner_user_id": "alice", "shared_with_user_ids": ["bob"]}, write=write)
                    if fail:
                        raise RuntimeError("synthetic failure")
                    return access.current_owner_fields()
                return app, identity
            app, identity = composition()
            other, other_identity = composition()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://fixture") as client, httpx.AsyncClient(transport=httpx.ASGITransport(app=other), base_url="http://fixture") as second:
                requests = [(client, "alice"), (client, "bob"), (second, "carol")]
                responses = await asyncio.gather(*(c.get("/owner", headers={"x-fixture-user": name}) for c, name in requests))
                self.assertEqual([r.json()["owner_user_id"] for r in responses], ["alice", "bob", "carol"])
                for name, query, status in ((None, "", 401), ("bob", "", 200), ("bob", "?write=true", 404), ("stranger", "", 404), ("alice", "?fail=true", 500), ("alice", "?write=true", 200)):
                    response = await client.get("/record" + query, headers={"x-fixture-user": name} if name else {})
                    self.assertEqual(response.status_code, status)
                    if status == 404:
                        self.assertEqual(response.json(), {"detail": "Resource not found"})
                self.assertEqual((await client.get("/owner")).json(), {})
            self.assertIsNone(identity.get())
            self.assertIsNone(other_identity.get())
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
