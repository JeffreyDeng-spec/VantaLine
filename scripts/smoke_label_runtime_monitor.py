"""Real isolated PostgreSQL metrics, heartbeat fencing and unlocked monitor reads."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.label_identity import LabelRuntimeIdentity, RuntimeUnavailable
from local_inspection_service.runtime.label_metrics import LabelRuntimeMetrics
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.label_runtime import LabelRuntimeStore
from local_inspection_service.storage.agent_operations import OperationConflict
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector


def main():
    schema = "label_monitor_" + uuid.uuid4().hex[:12]
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    identity = LabelRuntimeIdentity("a" * 40, "v2026.10.1", "external", "b" * 64)
    metrics = LabelRuntimeMetrics()
    @contextmanager
    def session():
        connection = default_postgres_connector(dsn)
        try:
            raw = PostgresRuntimeRepository(connection, "<synthetic>", schema_name=schema)
            yield LabelRepository(raw, runtime_identity=identity, metrics=metrics), LabelRuntimeStore(raw, metrics=metrics)
        finally:
            connection.close()
    setup = default_postgres_connector(dsn)
    try:
        with setup.cursor() as cursor:
            cursor.execute(postgres_ddl(schema))
        setup.commit()
        with session() as (repo, store):
            store.initialize(identity)
            assert not store.monitor(identity)["healthy"]
            def heartbeat(role="web", selected=identity):
                store.heartbeat(selected, role, "c" * 32, os.getpid(),
                    {"state": "drained", "active_iterations": 0}, metrics.snapshot())
            heartbeat()
            assert not store.monitor(identity)["healthy"]  # external requires both roles
            heartbeat("label")
            assert store.monitor(identity)["healthy"]
            # Read-only monitoring does not acquire the shared mutation fence.
            def monitor():
                with session() as (_, other):
                    return other.monitor(identity)
            with ThreadPoolExecutor(1) as pool:
                with repo.tx():
                    assert pool.submit(monitor).result(2)["healthy"]
            # Measure a real blocked acquisition, including the eventual release.
            started = threading.Event()
            def blocked_write():
                with session() as (other, _):
                    started.set()
                    with other.tx():
                        pass
            with ThreadPoolExecutor(1) as pool:
                with repo.tx():
                    future = pool.submit(blocked_write)
                    assert started.wait(2)
                    time.sleep(.12)
                    assert not future.done()
                future.result(2)
            assert metrics.snapshot()["lock_wait_ms_max"] >= 100
            store.change(identity, "d" * 32, maintenance=False, paused=False)
            task = repo.create("alice", "fixture-task", "synthetic", [
                {"id": "asset", "enabled": True, "media": {"original": "synthetic"}}])
            def submit(key):
                return repo.submit("alice", task["id"], key, 1, "asset", {"original": "synthetic"}, "model", "prompt")
            run = submit("first")
            assert submit("first")["id"] == run["id"]  # replay is not a rejected duplicate
            try:
                submit("second")
            except OperationConflict:
                pass
            else:
                raise AssertionError("duplicate accepted")
            run = repo.claim()
            repo.begin_call("alice", run["id"], "layout", {"synthetic": True}, [])
            try:
                repo.begin_call("alice", run["id"], "layout", {}, [])
            except OperationConflict:
                pass
            else:
                raise AssertionError("duplicate paid call accepted")
            heartbeat("label")
            value = store.monitor(identity)
            assert value["active_runs"] == 1 and value["queued_runs"] == 0
            counters = value["roles"]["label"]["metrics"]
            assert counters["duplicate_submissions"] == counters["duplicate_calls"] == 1
            # An old generation cannot publish even a well-formed heartbeat.
            try:
                heartbeat(selected=replace(identity, commit="e" * 40))
            except RuntimeUnavailable:
                pass
            else:
                raise AssertionError("old generation heartbeat accepted")
            original = value["roles"]["label"]["instance"]
            def replace_sample(transform):
                with store.transaction() as cursor:
                    cursor.execute(f"SELECT raw_json FROM {store.table} WHERE id='heartbeat:label'")
                    value = cursor.fetchone()[0]
                    transform(value)
                    cursor.execute(f"UPDATE {store.table} SET raw_json=%s::jsonb WHERE id='heartbeat:label'", (json.dumps(value),))
            replace_sample(lambda v: v.update(sampled_at=time.time() - 16))
            assert not store.monitor(identity)["healthy"]
            heartbeat("label")
            replace_sample(lambda v: v.update(git_commit="f" * 40))
            value = store.monitor(identity)
            assert not value["healthy"] and value["roles"]["label"] == {"fresh": False, "reason": "generation_mismatch"}
            heartbeat("label")
            replace_sample(lambda v: v.update(metrics={"secret": "customer-media"}))
            value = store.monitor(identity)
            assert not value["healthy"] and "customer-media" not in json.dumps(value)
            heartbeat("label")
            metrics.error("worker_iteration_failed")
            heartbeat("label")
            assert store.monitor(identity)["roles"]["label"]["metrics"]["recent_error"]["code"] == "worker_iteration_failed"
            assert int(repo.repository.connection.info.transaction_status) == 0
        print("label monitor: unlocked reads, real lock wait, duplicate refusals, two-role heartbeat, stale/build fencing and redaction passed")
    finally:
        setup.rollback()
        with setup.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        setup.commit()
        setup.close()


if __name__ == "__main__":
    main()
