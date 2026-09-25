"""Isolated PostgreSQL contract for unlocked label list reads and fenced writes."""
import json
import os
from pathlib import Path
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import ExitStack, closing
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector


def idle(connection):
    assert int(connection.info.transaction_status) == 0


def main():
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    schema = "label_reads_" + uuid.uuid4().hex[:12]
    stack = ExitStack()
    try:
        setup = stack.enter_context(closing(default_postgres_connector(dsn)))
        writer = stack.enter_context(closing(default_postgres_connector(dsn)))
        reader_connection = stack.enter_context(closing(default_postgres_connector(dsn)))
        probe = stack.enter_context(closing(default_postgres_connector(dsn)))
    except Exception:
        stack.close()
        raise
    try:
        with reader_connection.cursor() as c:
            c.execute("SET statement_timeout = '4000ms'")
            c.execute("SET lock_timeout = '3000ms'")
        reader_connection.commit()
        with setup.cursor() as c:
            c.execute(postgres_ddl(schema))
            c.execute(
                f'INSERT INTO "{schema}".label_inspection_objects '
                '(id,owner_user_id,task_id,kind,status,created_at,updated_at,idempotency_key,raw_json) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                ("task", "alice", "task", "task", "ready", 1, 1, "task-key",
                 json.dumps({"id": "task", "kind": "task", "name": "old", "revision": 1,
                             "assets": [], "created_at": 1, "updated_at": 1})),
            )
            c.execute(
                f'INSERT INTO "{schema}".label_inspection_objects '
                '(id,owner_user_id,task_id,kind,status,created_at,updated_at,idempotency_key,raw_json) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                ("run", "alice", "task", "run", "queued", 2, 2, "run-key",
                 json.dumps({"id": "run", "kind": "run", "task_id": "task",
                             "status": "queued", "created_at": 2})),
            )
            c.execute(
                f'INSERT INTO "{schema}".text_inspection_standards '
                '(id,owner_user_id,name,material_code,version_label,standard_type,status,'
                'source_sha256,created_at,updated_at,raw_json) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                ("standard", "alice", "old", "M", "1", "label", "ready", "sha", 1, 1,
                 json.dumps({"id": "standard", "name": "old", "standard_type": "label"})),
            )
        setup.commit()
        raw = PostgresRuntimeRepository(reader_connection, "<redacted>", schema_name=schema)
        repo = LabelRepository(raw)
        lock_sql = "SELECT pg_advisory_xact_lock(hashtextextended('label-inspection-v1',0))"
        try_lock_sql = "SELECT pg_try_advisory_xact_lock(hashtextextended('label-inspection-v1',0))"

        # A writer's uncommitted task version must not stall pure list reads.
        with writer.cursor() as c:
            c.execute(lock_sql)
            c.execute(
                f'UPDATE "{schema}".label_inspection_objects SET raw_json=%s::jsonb,updated_at=%s '
                "WHERE id='task' AND owner_user_id='alice'",
                (json.dumps({"id": "task", "kind": "task", "name": "new",
                             "revision": 1, "assets": [], "created_at": 1,
                             "updated_at": 3}), 3),
            )
            c.execute(
                f'UPDATE "{schema}".label_inspection_objects SET raw_json=%s::jsonb,status=%s '
                "WHERE id='run' AND owner_user_id='alice'",
                (json.dumps({"id": "run", "kind": "run", "task_id": "task",
                             "status": "succeeded", "created_at": 2}), "succeeded"),
            )
            c.execute(
                f'UPDATE "{schema}".text_inspection_standards SET raw_json=%s::jsonb,name=%s '
                "WHERE id='standard' AND owner_user_id='alice'",
                (json.dumps({"id": "standard", "name": "new", "standard_type": "label"}),
                 "new"),
            )
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(lambda: (
                repo.list("alice", "task"),
                repo.runs_for_tasks("alice", ["task"]),
                repo.legacy("alice", "standards"),
            ))
            try:
                tasks, runs, standards = future.result(timeout=5)
            except TimeoutError:
                reader_connection.cancel()
                raise AssertionError("pure list read waited for the write advisory lock")
        finally:
            writer.commit()
            pool.shutdown(wait=False, cancel_futures=True)
        assert tasks[0]["name"] == "old"
        assert runs["task"][0]["status"] == "queued"
        assert standards[0]["name"] == "old"
        idle(reader_connection)
        writer.commit()
        assert repo.list("alice", "task")[0]["name"] == "new"
        assert repo.runs_for_tasks("alice", ["task"])["task"][0]["status"] == "succeeded"
        assert repo.legacy("alice", "standards")[0]["name"] == "old"  # per-repo cache
        fresh = LabelRepository(raw)
        assert fresh.legacy("alice", "standards")[0]["name"] == "new"

        # request_run is deliberately excluded: it must wait for an in-flight
        # same-request insert before selecting the bound model snapshot.
        with reader_connection.cursor() as c:
            c.execute("SELECT pg_backend_pid()")
            reader_pid = c.fetchone()[0]
        reader_connection.commit()
        with writer.cursor() as c:
            c.execute(lock_sql)
            c.execute(
                f'INSERT INTO "{schema}".label_inspection_objects '
                '(id,owner_user_id,task_id,kind,status,created_at,updated_at,idempotency_key,raw_json) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                ("bound_run", "alice", "task", "run", "queued", 4, 4, "request-key",
                 json.dumps({"id": "bound_run", "kind": "run", "task_id": "task",
                             "status": "queued", "profile_snapshot": {"id": "old-profile"}})),
            )
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(repo.request_run, "alice", "request-key")
            waiting = False
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not future.done():
                with probe.cursor() as c:
                    c.execute("SELECT wait_event_type,wait_event FROM pg_stat_activity WHERE pid=%s",
                              (reader_pid,))
                    event = c.fetchone()
                probe.commit()
                if event == ("Lock", "advisory"):
                    waiting = True
                    break
                time.sleep(0.05)
            writer.commit()
            bound = future.result(timeout=5)
            assert waiting, "request_run did not wait for the write fence"
            assert bound["profile_snapshot"] == {"id": "old-profile"}
        finally:
            writer.rollback()
            pool.shutdown(wait=False, cancel_futures=True)
        idle(reader_connection)
        idle(writer)
        idle(reader_connection)

        # A second connection may take the advisory lock inside a read result
        # handler: none of these three reads acquires it implicitly.
        original_decode = PostgresRuntimeRepository._row_to_dict
        calls = []
        def unlocked(instance, cursor, row):
            with probe.cursor() as c:
                c.execute(try_lock_sql)
                assert c.fetchone()[0], "pure read retained the advisory lock"
            probe.commit()
            calls.append(1)
            return original_decode(instance, cursor, row)
        read_actions = (
            ("list", lambda: repo.list("alice", "task")),
            ("batch", lambda: repo.runs_for_tasks("alice", ["task"])),
            ("legacy", lambda: LabelRepository(raw).legacy("alice", "standards")),
        )
        for name, action in read_actions:
            before = len(calls)
            with patch.object(PostgresRuntimeRepository, "_row_to_dict", unlocked):
                assert action(), name
            assert len(calls) > before, name
            idle(reader_connection)
            idle(probe)

        # Every path must propagate the exact result failure, roll back and
        # leave its connection usable on the next read.
        failure = RuntimeError("injected result decode failure")
        def fail_decode(_instance, _cursor, _row):
            raise failure
        for name, action in read_actions:
            with patch.object(PostgresRuntimeRepository, "_row_to_dict", fail_decode):
                try:
                    action()
                except RuntimeError as error:
                    assert error is failure
                else:
                    raise AssertionError(f"{name} swallowed decode failure")
            idle(reader_connection)
            assert action(), name
        with probe.cursor() as c:
            c.execute(try_lock_sql)
            assert c.fetchone()[0]
        probe.commit()
        idle(probe)
        print("PASS unlocked list/batch/legacy reads, committed view, rollback/IDLE and write advisory fence")
    finally:
        active_error = sys.exc_info()[0] is not None
        cleanup_error = None
        for connection in (writer, reader_connection, probe, setup):
            try:
                connection.rollback()
            except Exception as error:
                cleanup_error = cleanup_error or error
        try:
            with setup.cursor() as c:
                c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            setup.commit()
        except Exception as error:
            cleanup_error = cleanup_error or error
        try:
            stack.close()
        except Exception as error:
            cleanup_error = cleanup_error or error
        if cleanup_error is not None and not active_error:
            raise cleanup_error


if __name__ == "__main__":
    main()