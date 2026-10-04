"""Real PostgreSQL admission, pause, restart and generation fences with synthetic tasks."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.label_identity import LabelRuntimeIdentity, RuntimeUnavailable
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.label_runtime import LabelRuntimeStore, LabelMaintenance
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector

IDENTITY = LabelRuntimeIdentity("a"*40, "v2026.10.1", "embedded")
NEXT = LabelRuntimeIdentity("b"*40, "v2026.10.2", "embedded")
REVISION = "c"*32


def main():
    schema = "label_control_" + uuid.uuid4().hex[:12]
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    @contextmanager
    def session(identity=IDENTITY):
        connection = default_postgres_connector(dsn)
        try:
            with connection.cursor() as c:
                c.execute("SET statement_timeout='4000ms'; SET lock_timeout='3000ms'")
            connection.commit()
            raw = PostgresRuntimeRepository(connection, "<synthetic>", schema_name=schema)
            yield LabelRepository(raw, runtime_identity=identity), LabelRuntimeStore(raw)
        finally:
            connection.close()

    setup = default_postgres_connector(dsn)
    try:
        with setup.cursor() as cursor:
            cursor.execute(postgres_ddl(schema))
        setup.commit()
        with session() as (repo, store):
            initial = store.initialize(IDENTITY)
            assert initial["paused"] and initial["maintenance"]
            tasks = [repo.create("alice" if index % 2 else "bob", "task-"+str(index), "synthetic", [
                {"id": "asset", "enabled": True, "media": {"original": "synthetic"}}]) for index in range(6)]
            def submit(repository, index):
                task = tasks[index]
                return repository.submit(task["owner_user_id"], task["id"], "run-"+str(index), 1,
                                         "asset", {"original": "synthetic"}, "synthetic-model", "synthetic-prompt")
            try:
                submit(repo, 0)
            except LabelMaintenance:
                pass
            else:
                raise AssertionError("closed gate accepted a new run")
            assert store.snapshot(IDENTITY)[1]["queued_runs"] == 0
            store.change(IDENTITY, REVISION, maintenance=False, paused=False)
            assert store.initialize(IDENTITY) == store.snapshot(IDENTITY)[0]
            first = submit(repo, 0)
            # Idempotent acknowledged submission remains readable while closed.
            store.change(IDENTITY, REVISION, maintenance=True)
            assert submit(repo, 0) == first
            # Gate close and submit share the exact old write advisory fence.
            store.change(IDENTITY, REVISION, maintenance=False)
            entered = threading.Event()
            def close_gate():
                with session() as (_, other):
                    entered.set()
                    return other.change(IDENTITY, REVISION, maintenance=True)
            with ThreadPoolExecutor(1) as pool:
                # Hold the label transaction while enqueueing the competing close.
                with repo.tx() as cursor:
                    future = pool.submit(close_gate)
                    assert entered.wait(2)
                    time.sleep(.05)
                    assert not future.done(), "close must wait for the submit transaction fence"
                    # A submission accepted inside the earlier transaction precedes close.
                    store.require_admission(cursor, IDENTITY)
                assert future.result(3)["maintenance"] is True
            try:
                submit(repo, 1)
            except LabelMaintenance:
                pass
            else:
                raise AssertionError("submission after close acknowledgement was accepted")
            store.change(IDENTITY, REVISION, maintenance=False)
            for index in range(1, 6):
                submit(repo, index)
            # Maintenance blocks only admission: the existing queue keeps draining.
            store.change(IDENTITY, REVISION, maintenance=True)
            def claim(_):
                with session() as (other, _):
                    return other.claim()
            with ThreadPoolExecutor(8) as pool:
                claimed = [value for value in pool.map(claim, range(16)) if value]
            assert len(claimed) == 2 and len({item["id"] for item in claimed}) == 2
            assert store.snapshot(IDENTITY)[1]["active_runs"] == 2
            # Settle only synthetic runs, then pause blocks further claims.
            for run in claimed:
                repo.update_run(run["owner_user_id"], run["id"], status="completed")
            store.change(IDENTITY, REVISION, paused=True)
            assert repo.claim() is None
            assert store.snapshot(IDENTITY)[1]["queued_runs"] == 4
            before = store.snapshot(IDENTITY)[0]
            try:
                store.change(IDENTITY, "not-a-revision", maintenance=False)
            except RuntimeUnavailable:
                pass
            else:
                raise AssertionError("malformed state was persisted")
            assert store.snapshot(IDENTITY)[0] == before
            assert int(repo.repository.connection.info.transaction_status) == 0
            # New build/rollback always starts fenced; stale processes cannot claim/submit.
            new = store.initialize(NEXT)
            assert new["paused"] and new["maintenance"]
            try:
                repo.claim()
            except RuntimeUnavailable:
                pass
            else:
                raise AssertionError("old build continued claiming")
            rolled_back = store.initialize(IDENTITY)
            assert rolled_back["paused"] and rolled_back["maintenance"]
            assert repo.get(first["owner_user_id"], first["id"])["profile_snapshot"] is None
        print("label runtime PostgreSQL: admission/claim fences, restart, generation, two global claims and rollback passed")
    finally:
        setup.rollback()
        with setup.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        setup.commit()
        setup.close()


if __name__ == "__main__":
    main()
