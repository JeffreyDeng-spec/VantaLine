"""Actual isolated configuration owners, training propagation and PLC writes."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import sys
import tempfile
import threading
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.config.application_composition import (
    ApplicationConfiguration, ConfigurationFiles, ConfigurationPolicy,
)
from local_inspection_service.config.app_store import AppConfigStore
from local_inspection_service.config.app_store_ports import AppConfigRows
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.training.user_state import (
    TrainingUserState, TrainingStateAccess, TrainingStateStorage,
)


class ConfigurationComposition(unittest.TestCase):
    def owner(self, name, rows=None):
        temporary = tempfile.TemporaryDirectory(prefix="vl-config-owner-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        events = []
        files = BusinessFiles(runtime_provider=lambda: None)
        defaults = {"accessories": [], "marker": name}
        owner = ApplicationConfiguration(
            files=ConfigurationFiles(
                files=lambda: files, primary=lambda: root / "config.json",
                backup=lambda: root / "backup.json", directory=lambda: root,
                ensure=lambda: lambda: events.append("ensure"),
            ),
            rows=rows or AppConfigRows(
                runtime_postgres_repository_or_none=lambda: lambda: None,
                config_from_rows=lambda: lambda *args: self.fail("unexpected PostgreSQL"),
                app_config_rows=lambda: lambda *args, **kw: self.fail("unexpected rows"),
                accessory_rows=lambda: lambda *args: self.fail("unexpected accessories"),
            ),
            policy=ConfigurationPolicy(
                defaults=lambda: defaults, protected_keys=lambda: ("plc", "lease"),
                sanitize=lambda: lambda value: value,
            ),
        )
        return owner, root, events, defaults

    def training(self, owner, marker, events):
        task = {"job_id": "same-job", "owner_user_id": "alice",
                "owner_username": marker, "status": "completed", "progress": 100}
        return TrainingUserState(
            defaults=lambda: {}, legacy_owner=lambda: "legacy",
            access=TrainingStateAccess(
                owner=lambda value: str(value.get("owner_user_id", "alice")),
                visible=lambda *args: True, admin=lambda *args: False,
                current_owner=lambda: {"owner_user_id": "alice"},
            ),
            storage=TrainingStateStorage(
                find=lambda identifier: task if identifier == "same-job" else None,
                load=owner.load_config, save=owner.save_config,
            ),
            sync_pipeline=lambda value: events.append((marker, value["job_id"])),
        )

    def test_inert_constructor_and_owned_read_recovery(self):
        owner, root, events, defaults = self.owner("a")
        self.assertEqual(events, [])
        self.assertFalse((root / "config.json").exists())
        self.assertIs(owner.store.files._read_config_file().__self__, owner.store)
        self.assertIs(owner.store.files._config_io_lock(), owner.lock)
        with self.assertRaises(AttributeError):
            owner.lock = threading.RLock()
        result = owner.load_config()
        result["accessories"].append("poison")
        self.assertEqual(defaults["accessories"], [])

    def test_two_actual_training_and_protected_writers_do_not_cross(self):
        a, ar, ae, _ = self.owner("a")
        b, br, be, _ = self.owner("b")
        self.assertIsNot(a.lock, b.lock)
        self.assertIsNot(a.store.policy._plc_namespace_write_authorized(),
                         b.store.policy._plc_namespace_write_authorized())
        a.save_config({"marker": "a"})
        b.save_config({"marker": "b"})
        ta, tb = self.training(a, "a", ae), self.training(b, "b", be)
        barrier = threading.Barrier(4)
        def train(service):
            barrier.wait(timeout=3)
            service.sync_training_state_from_task("same-job")
        def mutate(owner, marker):
            barrier.wait(timeout=3)
            owner.mutate_app_config_atomically(lambda record: record.update(plc={"station": "same", "owner": marker}))
        with ThreadPoolExecutor(4) as pool:
            futures = [pool.submit(train, ta), pool.submit(train, tb),
                       pool.submit(mutate, a, "a"), pool.submit(mutate, b, "b")]
            for future in futures:
                future.result(timeout=5)
        for owner, root, events, marker in [(a, ar, ae, "a"), (b, br, be, "b")]:
            saved = json.loads((root / "config.json").read_text())
            self.assertEqual(saved["marker"], marker)
            self.assertEqual(saved["plc"]["owner"], marker)
            self.assertEqual(saved["training_by_user_id"]["alice"]["owner_username"], marker)
            self.assertEqual([x for x in events if isinstance(x, tuple)], [(marker, "same-job")])
            owner.save_config({**saved, "plc": {"owner": "unauthorized"}})
            self.assertEqual(owner.load_config()["plc"]["owner"], marker)

    def test_one_app_lock_cannot_block_other_app_training(self):
        a, _, _, _ = self.owner("a")
        b, _, events, _ = self.owner("b")
        a.save_config({"marker": "a"})
        b.save_config({"marker": "b"})
        attempted = threading.Event()
        def held_write():
            attempted.set()
            a.save_config({"marker": "a-new"})
        with ThreadPoolExecutor(2) as pool:
            with a.lock:
                blocked = pool.submit(held_write)
                self.assertTrue(attempted.wait(3))
                pool.submit(self.training(b, "b", events).sync_training_state_from_task,
                            "same-job").result(timeout=3)
                self.assertFalse(blocked.done())
            blocked.result(timeout=3)
        self.assertEqual(b.load_config()["training_by_user_id"]["alice"]["owner_username"], "b")

    def test_mutator_error_and_namespace_validation_leave_storage_unchanged(self):
        owner, root, _, _ = self.owner("a")
        owner.save_config({"marker": "a"})
        before = (root / "config.json").read_bytes()
        error = ValueError("synthetic mutation")
        def fail(record):
            record["plc"] = {"owner": "partial"}
            raise error
        with self.assertRaises(ValueError) as raised:
            owner.mutate_app_config_atomically(fail)
        self.assertIs(raised.exception, error)
        with self.assertRaisesRegex(ValueError, "unprotected"):
            owner.mutate_app_config_atomically(lambda record: record.update(marker="forbidden"))
        self.assertEqual((root / "config.json").read_bytes(), before)
        self.assertFalse(owner.store.policy._plc_namespace_write_authorized().get())
        with ThreadPoolExecutor(1) as pool:
            self.assertTrue(pool.submit(owner.lock.acquire, False).result(timeout=3))
            pool.submit(owner.lock.release).result(timeout=3)

    def test_failed_authorized_save_resets_flag_and_keeps_second_owner_live(self):
        a, ar, _, _ = self.owner("a")
        b, _, _, _ = self.owner("b")
        a.save_config({"marker": "a"})
        a.mutate_app_config_atomically(lambda record: record.update(plc={"owner": "a"}))
        original = AppConfigStore.save_app_config
        error = OSError("synthetic publication failure")
        def save(store, record):
            if store is a.store:
                self.assertTrue(store.policy._plc_namespace_write_authorized().get())
                raise error
            return original(store, record)
        with patch.object(AppConfigStore, "save_app_config", save):
            with self.assertRaises(OSError) as raised:
                a.mutate_app_config_atomically(lambda record: record.update(plc={"owner": "wrong"}))
            self.assertIs(raised.exception, error)
            b.mutate_app_config_atomically(lambda record: record.update(plc={"owner": "b"}))
        a.save_config({"marker": "a", "plc": {"owner": "unauthorized"}})
        self.assertEqual(json.loads((ar / "config.json").read_text())["plc"]["owner"], "a")
        self.assertEqual(b.load_config()["plc"]["owner"], "b")
        self.assertFalse(a.store.policy._plc_namespace_write_authorized().get())

    @unittest.skipUnless(os.environ.get("VANTALINE_POSTGRES_DSN"), "isolated PostgreSQL mode")
    def test_real_postgres_two_owners_thread_release_and_partial_namespace_rollback(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.runtime.connections import ThreadRepositoryFactory
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_records import app_config_rows, accessory_rows, config_from_rows
        dsn = os.environ["VANTALINE_POSTGRES_DSN"]
        schemas = ["app_owner_" + uuid.uuid4().hex for _ in range(2)]
        connections, owners, factories = [], [], []
        with psycopg.connect(dsn, autocommit=True) as control:
            try:
                for schema in schemas:
                    control.execute(postgres_ddl(schema))
                    def create(schema=schema):
                        connection = psycopg.connect(dsn)
                        connections.append(connection)
                        return SimpleNamespace(repository=PostgresRuntimeRepository(connection, "fixture", schema))
                    factory = ThreadRepositoryFactory(create, lambda schema=schema: schema)
                    factories.append(factory)
                    rows = AppConfigRows(
                        runtime_postgres_repository_or_none=lambda factory=factory: lambda: factory.selection().repository,
                        config_from_rows=lambda: config_from_rows,
                        app_config_rows=lambda: app_config_rows, accessory_rows=lambda: accessory_rows,
                    )
                    owner, root, events, _ = self.owner(schema, rows=rows)
                    owners.append((owner, root, events))
                    with factory.thread_scope():
                        owner.save_config({"marker": {"name": schema}})
                        owner.mutate_app_config_atomically(lambda record: record.update(plc={"count": 0}, lease={"id": "same"}))
                def increment(index):
                    owner = owners[index][0]
                    with factories[index].thread_scope():
                        for _ in range(8):
                            owner.mutate_app_config_atomically(lambda record: record["plc"].update(count=record["plc"]["count"] + 1))
                with ThreadPoolExecutor(4) as pool:
                    futures = [pool.submit(increment, index) for index in (0, 0, 1, 1)]
                    for future in futures:
                        future.result(timeout=20)
                for index, (owner, root, events) in enumerate(owners):
                    with factories[index].thread_scope():
                        self.training(owner, schemas[index], events).sync_training_state_from_task("same-job")
                        saved = owner.load_config()
                        self.assertEqual(saved["plc"]["count"], 16)
                        self.assertEqual(saved["marker"], {"name": schemas[index]})
                        self.assertEqual(saved["training_by_user_id"]["alice"]["owner_username"], schemas[index])
                        self.assertFalse((root / "config.json").exists())
                        error = RuntimeError("after first protected PostgreSQL write")
                        original = PostgresRuntimeRepository._upsert_sql_params
                        def fail(repository, table, row):
                            if table == "app_config" and row.get("config_key") == "lease":
                                raise error
                            return original(repository, table, row)
                        with patch.object(PostgresRuntimeRepository, "_upsert_sql_params", fail), self.assertRaises(RuntimeError) as raised:
                            owner.mutate_app_config_atomically(lambda record: record["plc"].update(count=99))
                        self.assertIs(raised.exception, error)
                        self.assertEqual(owner.load_config(), saved)
                        self.assertFalse(owner.store.policy._plc_namespace_write_authorized().get())
                self.assertTrue(all(connection.closed for connection in connections))
            finally:
                for factory in factories:
                    factory.clear()
                for schema in schemas:
                    control.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
