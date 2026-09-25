"""Synthetic isolated-PostgreSQL old/new label-run query and memory comparison."""
import gc
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.label_inspection import LabelRepository, RUN_BATCH_SIZE
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.runtime_selector import default_postgres_connector


def chunks(values, size):
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def signature(rows):
    return tuple((row["id"], row.get("status"), row.get("decision"))
                 for row in rows)


def measure(fn):
    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, peak


def main():
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    schema = "label_batch_" + uuid.uuid4().hex[:12]
    connection = default_postgres_connector(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(postgres_ddl(schema))
        connection.commit()
        table = f'"{schema}"."label_inspection_objects"'
        with connection.cursor() as cursor:
            with cursor.copy(
                f"COPY {table} (id,owner_user_id,task_id,kind,status,created_at,"
                "updated_at,idempotency_key,raw_json) FROM STDIN"
            ) as stream:
                for index in range(10000):
                    task_id = f"task_{index:05}"
                    task = {"id": task_id, "task_id": task_id, "kind": "task",
                            "revision": 1, "name": f"Order {index}", "assets": [],
                            "created_at": index, "updated_at": index, "status": "ready"}
                    stream.write_row((task_id, "alice", task_id, "task", "ready",
                                      index, index, "task:" + task_id,
                                      json.dumps(task, separators=(",", ":"))))
                    run_count = 30 if index % 200 == 0 else (0 if index % 7 == 0 else 1)
                    for ordinal in range(run_count):
                        run_id = f"run_{index:05}_{ordinal}"
                        run = {"id": run_id, "task_id": task_id, "kind": "run",
                               "status": "succeeded", "decision": "MATCH",
                               "created_at": index + ordinal / 10,
                               "evidence": "synthetic-" + "x" * 2048}
                        stream.write_row((run_id, "alice", task_id, "run",
                                          "succeeded", index, index,
                                          "run:" + run_id,
                                          json.dumps(run, separators=(",", ":"))))
                # Neighbor-account and SQL-vs-JSON task-id mismatch are deliberate.
                stream.write_row(("other_run", "bob", "task_00001", "run",
                                  "succeeded", 2, 2, "other_run",
                                  json.dumps({"id": "other_run", "task_id": "task_00001",
                                              "status": "succeeded", "created_at": 2})))
                stream.write_row(("mismatch_run", "alice", "task_00002", "run",
                                  "succeeded", 2, 2, "mismatch_run",
                                  json.dumps({"id": "mismatch_run", "task_id": "wrong_json_id",
                                              "status": "succeeded", "created_at": 2})))
        connection.commit()
        raw = PostgresRuntimeRepository(connection, "<redacted>", schema_name=schema)
        repo = LabelRepository(raw)
        assert repo.runs_for_tasks("alice", []) == {}
        assert len(repo.runs_for_tasks("alice", ["task_00002"])["task_00002"]) == 2
        assert all(not values for values in repo.runs_for_tasks("bob", ["task_00002"]).values())
        try:
            repo.runs_for_tasks("alice", ["x"] * (RUN_BATCH_SIZE + 1))
        except ValueError as error:
            assert str(error) == "run batch exceeds limit"
        else:
            raise AssertionError("oversized batch accepted")

        # The batch must hold the old advisory fence until its own transaction
        # commits, and failures during row handling must roll it back.
        second = default_postgres_connector(dsn)
        try:
            original_decode = PostgresRuntimeRepository._row_to_dict
            lock_sql = "SELECT pg_try_advisory_xact_lock(hashtextextended('label-inspection-v1',0))"
            def check_lock(instance, cursor, row):
                with second.cursor() as probe:
                    probe.execute(lock_sql)
                    assert not probe.fetchone()[0], "batch released advisory fence too early"
                second.commit()
                return original_decode(instance, cursor, row)
            with patch.object(PostgresRuntimeRepository, "_row_to_dict", check_lock):
                assert repo.runs_for_tasks("alice", ["task_00002"])
            with second.cursor() as probe:
                probe.execute(lock_sql)
                assert probe.fetchone()[0], "batch retained advisory fence after commit"
            second.commit()

            failure = RuntimeError("injected batch row failure")
            def fail_decode(_instance, _cursor, _row):
                raise failure
            with patch.object(PostgresRuntimeRepository, "_row_to_dict", fail_decode):
                try:
                    repo.runs_for_tasks("alice", ["task_00002"])
                except RuntimeError as error:
                    assert error is failure
                else:
                    raise AssertionError("batch row failure was swallowed")
            assert int(connection.info.transaction_status) == 0
            with second.cursor() as probe:
                probe.execute(lock_sql)
                assert probe.fetchone()[0], "failed batch retained advisory fence"
            second.commit()
            assert repo.runs_for_tasks("alice", ["task_00002"])
        finally:
            second.close()

        metrics = []
        for size in (1000, 10000):
            task_ids = [f"task_{index:05}" for index in range(size)]
            expected_batches = math.ceil(size / RUN_BATCH_SIZE)
            def old():
                return {task_id: signature(repo.list("alice", "run", task_id))
                        for task_id in task_ids}
            def new():
                result = {}
                for task_batch in chunks(task_ids, RUN_BATCH_SIZE):
                    grouped = repo.runs_for_tasks("alice", task_batch)
                    for task_id in task_batch:
                        values = grouped[task_id]
                        decoded = [json.loads(row) if isinstance(row, str) else row
                                   for row in values]
                        result[task_id] = signature(decoded)
                    del grouped
                return result
            old_times, new_times, old_peaks, new_peaks = [], [], [], []
            old()  # warm both query shapes before timed samples
            new()
            for iteration in range(5):
                if iteration % 2:
                    new_result, new_elapsed, new_peak = measure(new)
                    old_result, old_elapsed, old_peak = measure(old)
                else:
                    old_result, old_elapsed, old_peak = measure(old)
                    new_result, new_elapsed, new_peak = measure(new)
                assert new_result == old_result
                old_times.append(old_elapsed)
                new_times.append(new_elapsed)
                old_peaks.append(old_peak)
                new_peaks.append(new_peak)
            assert all(item[0] != "other_run"
                       for ids in new_result.values() for item in ids)
            assert "mismatch_run" in [item[0] for item in new_result["task_00002"]]
            def p95(values):
                return sorted(values)[math.ceil(0.95 * len(values)) - 1]
            old_p95, new_p95 = p95(old_times), p95(new_times)
            metrics.append({
                "tasks": size, "old_transactions_expected": size,
                "new_transactions_expected": expected_batches,
                "samples": 5,
                "old_p50_seconds": round(statistics.median(old_times), 3),
                "new_p50_seconds": round(statistics.median(new_times), 3),
                "old_p95_seconds": round(old_p95, 3),
                "new_p95_seconds": round(new_p95, 3),
                "old_peak_mib": round(max(old_peaks) / (1024 * 1024), 2),
                "new_peak_mib": round(max(new_peaks) / (1024 * 1024), 2),
            })
            assert new_p95 <= max(old_p95 * 1.25, old_p95 + 0.25)
            # Repository-level memory omits API task/snapshot allocations; report
            # this comparison for review rather than treating it as API peak.
            assert max(new_peaks) <= max(max(old_peaks) * 1.5,
                                         max(old_peaks) + 8 * 1024 * 1024)
        status = getattr(getattr(connection, "info", None), "transaction_status", None)
        if status is None:
            status = connection.get_transaction_status()
        assert int(status) == 0, status
        print(json.dumps({"label_run_batch_benchmark": metrics}, sort_keys=True))
    finally:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        connection.commit()
        connection.close()


if __name__ == "__main__":
    main()