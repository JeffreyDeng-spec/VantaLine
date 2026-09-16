"""Accessory policy, projection, real HTTP and isolated storage contracts."""
import argparse
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException, Request
import httpx
from local_inspection_service.accessories import policy
from local_inspection_service.accessories.api import register_catalog_api
from local_inspection_service.accessories.catalog import AccessoryCatalog, CatalogDependencies
from local_inspection_service.accessories.projection import AccessoryProjection, ProjectionDependencies
from local_inspection_service.accessories.repository import AccessoryRepository, AccessoryStoreDependencies
from local_inspection_service.auth.access import AccessControl
from local_inspection_service.records.access import RecordAccess
from local_inspection_service.records.audit import RecordAudit
from local_inspection_service.records.ownership import RecordOwnership
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_records import accessory_row


def projection(identity, events=None, limit=None):
    events = events if events is not None else []
    audit = RecordAudit(RecordOwnership("legacy_admin", "system"))
    def physical(kind):
        events.append(("physical", kind))
        return {"kind": kind}
    def current():
        events.append("current")
        return AccessControl(identity).current_auth_user()
    def redact(record, user):
        events.append(("redact", user["id"]))
        if user.get("role") != "admin":
            record = copy.deepcopy(record)
            record["source_files"] = []
            record["original_source_files"] = []
        return record
    return AccessoryProjection(ProjectionDependencies(
        audit.enrich_record_audit_fields, copy.deepcopy, physical,
        lambda key: {"label": "Fixture reference"} if key == "fixture" else None,
        lambda _: 9, lambda: (limit or [2])[0], current, redact))


class CatalogContracts(unittest.TestCase):
    def test_policy_edge_cases(self):
        self.assertEqual(policy.accessory_uid({"id": "  x  "}), "  x  ")
        self.assertEqual(policy.accessory_uid({"class_id": 2, "name": " A / B "}), "2__a_b")
        self.assertEqual(policy.accessory_material_type({"class_id": 1, "material_type": None}), "text")
        self.assertFalse(policy.accessory_uses_ocr({"training_role": " OCR ", "detection_route": " yolo_ocr "}))
        self.assertTrue(policy.accessory_uses_ocr({"training_role": "OCR"}))
        self.assertTrue(policy.accessory_uses_ocr({"description": "fixture LABEL"}))
        self.assertEqual(policy.object_alpha_material_policy({"material_alpha_policy": "transparent"}, {"material_alpha_policy": "invalid"}), "opaque")
        self.assertEqual(policy.object_alpha_material_policy({"name": "glass vial"}), "transparent")
        self.assertEqual(policy.object_alpha_material_policy({"name": "glass", "material_alpha_policy": "solid"}), "opaque")
        item = {"id": "a", "class_id": 0, "ai_profile": {"accessory_id": "a", "material_type": "object", "name": "a", "visual_signature": "fixture"}}
        for status, expected in (({"source": "provider", "status": "ready"}, True), ({"source": " PROVIDER ", "status": " GENERATED "}, True), ("ready", False), ({"source": "fallback", "status": "ready"}, False), ({"source": "provider", "status": "timeout"}, False)):
            item["ai_profile_status"] = status
            self.assertEqual(policy.accessory_ai_profile_ready(item), expected)
        item["ai_profile_status"] = {"source": "provider", "status": "ready"}
        item["ai_profile"]["accessory_id"] = "different"
        self.assertFalse(policy.accessory_ai_profile_ready(item))
        self.assertTrue(policy.accessory_ai_profile_rejected({"ai_profile_status": {"source": "fallback"}}))

    def test_projection_boundaries_and_eager_defaults(self):
        identity, events, limit = RequestIdentity(), [], [2]
        service = projection(identity, events, limit)
        item = {"id": "a", "class_id": 0, "name": "a", "source_files": list("abcdef"),
                "original_source_files": list("uvwxyz"), "physical_size": {"keep": True},
                "thumbnails": [{"url": "one"}, {"url": "two"}, {"url": "three"}],
                "normalized_assets": [1, 2], "detection_route": "locate", "locateanything_profile": {"old": True}}
        original = copy.deepcopy(item)
        full = service.serialize_accessory(item)
        self.assertEqual(events, [("physical", "object")])
        self.assertEqual(full["source_files"], list("abcdef"))
        self.assertEqual(full["physical_size"], {"keep": True})
        self.assertEqual(full["detection_route"], "yolo")
        self.assertNotIn("locateanything_profile", full)
        self.assertEqual(item, original)
        self.assertIsNone(service.serialize_accessory({"material_type": None})["material_type"])
        with self.assertRaises(ValueError):
            service.serialize_accessory({"material_type": "text", "class_id": "invalid"})
        events.clear()
        self.assertEqual(service.serialize_accessory_items([]), [])
        self.assertEqual(events, [])
        with identity.bind({"id": "admin", "role": "admin"}):
            summary = service.serialize_accessory_summary(item)
            self.assertEqual(summary["source_files"], list("abcd"))
            self.assertEqual(summary["source_file_count"], 6)
            self.assertEqual(summary["normalized_asset_count"], 2)
            self.assertEqual(summary["thumbnails"], item["thumbnails"][:2])
            self.assertEqual(summary["thumbnail_url"], "one")
            text_item = {**item, "material_type": "text", "size_reference": "fixture", "ai_profile_status": {"source": "provider", "status": "ready", "internal": "private"}}
            text = service.serialize_accessory_summary(text_item)
            self.assertEqual(text["source_files"], list("ab"))
            self.assertEqual(text["source_file_count"], 9)
            self.assertEqual(text["size_reference_label"], "Fixture reference")
            self.assertNotIn("internal", text["ai_profile_status"])
            limit[0] = 1
            self.assertEqual(service.serialize_accessory_summary(text_item)["source_files"], ["a"])
        with identity.bind({"id": "member", "role": "user"}):
            self.assertEqual(service.serialize_accessory_summary(item)["source_files"], [])
        self.assertEqual(events[-2:], ["current", ("redact", "member")])

    def test_json_mutation_id_mismatch_and_failure(self):
        events, config = [], {"accessories": [{"id": "a", "value": 1}, {"id": "a", "value": 2}]}
        def load():
            events.append("load")
            return config
        def save(value):
            self.assertIs(value, config)
            events.append("save")
        def unexpected():
            raise AssertionError("JSON helper must keep existing lock placement")
        service = AccessoryRepository(AccessoryStoreDependencies(lambda: None, unexpected, load, save))
        self.assertIsNone(service.save_accessory_item(None))
        self.assertFalse(service.delete_accessory_item(" "))
        self.assertEqual(events, [])
        item = {"id": "a", "nested": {"value": 3}}
        result = service.save_accessory_item(item, config)
        self.assertIsNot(result, item)
        self.assertIs(result["nested"], item["nested"])
        self.assertEqual(config["accessories"][1]["value"], 2)
        self.assertEqual(events, ["save"])
        self.assertTrue(service.delete_accessory_item(" a ", config))
        self.assertEqual(config["accessories"], [])
        for legacy in ({"id": " ", "class_id": 1, "name": "empty id"}, {"class_id": 2, "name": "legacy"}):
            service.save_accessory_item(legacy, config)
            service.save_accessory_item(legacy, config)
        self.assertEqual(len(config["accessories"]), 4)
        self.assertFalse(service.delete_accessory_item(accessory_row(config["accessories"][0])["id"], config))
        service.save_accessory_item({"id": "loaded"})
        self.assertEqual(events[-2:], ["load", "save"])
        def fail(value):
            raise OSError("synthetic save failure")
        failed = AccessoryRepository(AccessoryStoreDependencies(lambda: None, unexpected, load, fail))
        with self.assertRaises(OSError):
            failed.save_accessory_item({"id": "failure"}, config)
        self.assertEqual(config["accessories"][-1]["id"], "failure")
        with self.assertRaises(OSError):
            failed.delete_accessory_item("failure", config)
        self.assertFalse(any(item.get("id") == "failure" for item in config["accessories"]))

    def test_pg_capability_order_and_no_fallback_after_failure(self):
        events, lock = [], threading.RLock()
        @contextmanager
        def locked():
            with lock:
                events.append("enter")
                try: yield
                finally: events.append("exit")
        def unavailable(*args):
            raise AssertionError("PostgreSQL must not fall back to JSON")
        def fail(table, row):
            events.append(("upsert", table, row["id"]))
            raise RuntimeError("synthetic repository failure")
        repo = SimpleNamespace(upsert_row=fail,
            fetch_by_primary_key=lambda table, key: events.append(("fetch", key["id"])) or {},
            delete_by_primary_key=lambda table, key: events.append(("delete", key["id"])))
        selected = [repo]
        def runtime():
            events.append("repository")
            return selected[0]
        service = AccessoryRepository(AccessoryStoreDependencies(runtime, locked, unavailable, unavailable))
        self.assertEqual(events, [])
        supplied = {"accessories": []}
        with self.assertRaises(RuntimeError): service.save_accessory_item({"id": " x "}, supplied)
        self.assertEqual(events, ["repository", "enter", ("upsert", "accessories", "x"), "exit"])
        self.assertEqual(supplied, {"accessories": []})
        def other_thread():
            acquired = lock.acquire(timeout=1)
            if acquired: lock.release()
            return acquired
        with ThreadPoolExecutor(max_workers=1) as pool:
            self.assertTrue(pool.submit(other_thread).result())
        events.clear()
        self.assertTrue(service.delete_accessory_item(" x ", supplied))
        self.assertEqual(events, ["repository", "enter", ("fetch", "x"), ("delete", "x"), "exit"])
        selected[0] = SimpleNamespace(fetch_by_primary_key=lambda *args: None)
        events.clear()
        self.assertFalse(service.delete_accessory_item("missing"))
        self.assertEqual(events, ["repository", "enter", "exit"])

    def test_http_visibility_views_duplicate_ids_and_detail_side_effect(self):
        async def scenario():
            def composition():
                identity, events = RequestIdentity(), []
                ownership = RecordOwnership("legacy_admin", "system")
                auth = AccessControl(identity)
                access = RecordAccess(identity, ownership, auth.current_auth_user, lambda _: None)
                records = [{"id": "alice", "owner_user_id": "alice", "source_files": ["fixture"], "shared_with_user_ids": ["bob"]},
                           {"id": "bob", "owner_user_id": "bob"}, {"id": "dup", "owner_user_id": "bob"}, {"id": "dup", "owner_user_id": "alice"}]
                def scope(config, user, target):
                    events.append(("scope", user["id"], target))
                    return {"accessories": [r for r in config["accessories"] if ownership.record_visible_to_user(r, user, target)]}
                def detail(record):
                    events.append(("detail", record["id"]))
                    return {"item": record["id"]}
                catalog = AccessoryCatalog(CatalogDependencies(auth.current_auth_user, lambda: {"accessories": records}, scope,
                                                              access.require_record_access, detail), projection(identity))
                app = FastAPI()
                @app.middleware("http")
                async def bind(request: Request, call_next):
                    name = request.headers.get("x-fixture-user")
                    with identity.bind({"id": name, "role": "admin" if name == "admin" else "user"} if name else None):
                        return await call_next(request)
                register_catalog_api(app, catalog)
                return app, identity, events
            app, identity, events = composition()
            second, second_identity, second_events = composition()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client, httpx.AsyncClient(transport=httpx.ASGITransport(app=second), base_url="http://fixture") as other:
                a, b = await asyncio.gather(client.get("/api/accessories?user_id=bob", headers={"x-fixture-user": "alice"}), other.get("/api/accessories?user_id=bob", headers={"x-fixture-user": "admin"}))
                self.assertEqual([r["id"] for r in a.json()["items"]], ["alice", "dup"])
                self.assertEqual([r["id"] for r in b.json()["items"]], ["bob", "dup"])
                self.assertEqual(events[0], ("scope", "alice", None))
                self.assertEqual(second_events[0], ("scope", "admin", "bob"))
                for query in ("view=full", "view=%20DETAIL%20", "view=all", "summary=false"):
                    result = await client.get("/api/accessories?"+query, headers={"x-fixture-user": "alice"})
                    self.assertEqual(result.json()["items"][0]["source_files"], ["fixture"])
                before = len(events)
                for key, name, expected, detail in (("dup", "alice", 404, "Resource not found"), ("bob", "alice", 404, "Resource not found"), ("missing", "alice", 404, "Accessory not found"), ("alice", None, 401, "Authentication required")):
                    response = await client.get('/api/accessories/'+key+'/detail', headers={"x-fixture-user": name} if name else {})
                    self.assertEqual((response.status_code, response.json()), (expected, {"detail": detail}))
                self.assertEqual(len(events), before)
                response = await client.get('/api/accessories/alice/detail', headers={"x-fixture-user": "bob"})
                self.assertEqual(response.json(), {"item": "alice"})
                self.assertEqual(events[-1], ("detail", "alice"))
                self.assertEqual((await client.get('/api/accessories')).status_code, 401)
            self.assertIsNone(identity.get())
            self.assertIsNone(second_identity.get())
        asyncio.run(scenario())


def postgres_contract(dsn):
    import psycopg
    from psycopg import sql
    schema = "accessory_" + uuid.uuid4().hex
    connections = []
    def connect():
        connection = psycopg.connect(dsn)
        connections.append(connection)
        return SimpleNamespace(store="postgres", repository=PostgresRuntimeRepository(connection, "fixture", schema))
    factory, lock = ThreadRepositoryFactory(connect, lambda: schema), threading.RLock()
    def no_fallback(*args):
        raise AssertionError("PostgreSQL accessed JSON configuration")
    service = AccessoryRepository(AccessoryStoreDependencies(lambda: factory.selection().repository, lambda: lock, no_fallback, no_fallback))
    with psycopg.connect(dsn, autocommit=True) as control:
        control.execute(postgres_ddl(schema))
        try:
            def write(index):
                with factory.thread_scope():
                    item = {"id": f"fixture_{index}", "name": "Fixture", "owner_user_id": "alice", "created_at": 100}
                    service.save_accessory_item(item)
                    service.save_accessory_item({**item, "name": "Updated"})
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(write, range(24)))
            with factory.thread_scope():
                repository = factory.selection().repository
                rows = repository.fetch_all("accessories")
                assert len(rows) == 24 and all(r["raw_json"]["name"] == "Updated" for r in rows)
                legacy = {"class_id": 2, "name": "Legacy fixture"}
                assert service.save_accessory_item(legacy) == legacy
                row = repository.fetch_by_primary_key("accessories", {"id": accessory_row(legacy)["id"]})
                assert row["raw_json"] == legacy and "id" not in row["raw_json"]
                assert service.delete_accessory_item(" fixture_0 ")
                assert not service.delete_accessory_item("fixture_0")
                assert len(repository.fetch_all("accessories")) == 24
            assert all(connection.closed for connection in connections)
        finally:
            factory.clear()
            control.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    print("PASS isolated PostgreSQL accessory row writes/deletes and thread connection cleanup")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(CatalogContracts))
    if not result.wasSuccessful(): raise SystemExit(1)
    if args.postgres: postgres_contract(os.environ["VANTALINE_POSTGRES_DSN"])
