"""Isolated PostgreSQL: real read-only snapshots, fencing and sampling failures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
import sys
import time
import uuid
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from local_inspection_service.runtime.label_identity import LabelRuntimeIdentity, RuntimeUnavailable
from local_inspection_service.runtime.label_metrics import LabelRuntimeMetrics
from local_inspection_service.runtime.label_observation import read_observation, observe_progress
from local_inspection_service.storage.label_runtime import LabelRuntimeStore
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl


def main():
    schema = "observe_" + uuid.uuid4().hex[:12]
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    identity = LabelRuntimeIdentity("a"*40, "v2026.10.1", "external", "b"*64)
    options = "-c default_transaction_read_only=on -c default_transaction_isolation=repeatable\\ read -c statement_timeout=2000"
    setup = psycopg.connect(dsn)
    try:
        setup.execute(postgres_ddl(schema))
        setup.commit()
        store = LabelRuntimeStore(PostgresRuntimeRepository(setup, "synthetic", schema_name=schema))
        store.initialize(identity)
        def beat(role):
            store.heartbeat(identity, role, ("c" if role == "web" else "d")*32,
                            11 if role == "web" else 12,
                            {"state": "drained", "active_iterations": 0}, LabelRuntimeMetrics().snapshot())
        beat("web")
        with psycopg.connect(dsn, options=options) as connection:
            repository = PostgresRuntimeRepository(connection, "synthetic", schema_name=schema)
            def rejected(selected=identity, **kwargs):
                try:
                    read_observation(repository, selected, **kwargs)
                except RuntimeUnavailable:
                    return
                raise AssertionError("invalid runtime observation accepted")
            rejected()  # missing label heartbeat
            beat("label")
            first = read_observation(repository, identity)
            assert first.paused and first.maintenance and len(first.roles) == 2
            # Commit a new control/heartbeat generation between the observer's reads.
            # REPEATABLE READ must keep the entire original observation together.
            decode = repository._row_to_dict
            changed = False
            def interleave(cursor, raw):
                nonlocal changed
                value = decode(cursor, raw)
                if not changed:
                    changed = True
                    store.change(identity, "e"*32, maintenance=False, paused=False)
                    beat("web")
                    beat("label")
                return value
            with patch.object(PostgresRuntimeRepository, "_row_to_dict", side_effect=interleave):
                stable = read_observation(repository, identity)
            assert stable == first, "cross-transaction control/heartbeat sample was mixed"
            current = read_observation(repository, identity)
            assert current.revision == "e"*32 and not current.paused and not current.maintenance
            assert all(after[3] > before[3] for before, after in zip(stable.roles, current.roles))
            store.change(identity, first.revision, maintenance=True, paused=True)
            rejected(replace(identity, commit="e"*40))
            rejected(now=lambda: time.time() + 16)  # stale
            rejected(now=lambda: 0)  # future
            # A held write fence must not block the observer.
            with ThreadPoolExecutor(1) as pool:
                def read_other():
                    with psycopg.connect(dsn, options=options) as other:
                        return read_observation(PostgresRuntimeRepository(other, "synthetic", schema_name=schema), identity)
                with store.transaction() as cursor:
                    assert pool.submit(read_other).result(2).active == 0
            def tick(_):
                beat("web")
                beat("label")
            last = observe_progress(lambda: read_observation(repository, identity), sleep=tick).after
            assert all(after[3] > before[3] for before, after in zip(first.roles, last.roles))
            # The driver options actually prohibit mutation, not merely a test flag.
            try:
                connection.execute(f'DELETE FROM "{schema}".label_runtime_state')
            except psycopg.errors.ReadOnlySqlTransaction:
                connection.rollback()
            else:
                raise AssertionError("observer connection allowed writes")
        with psycopg.connect(dsn) as unsafe:
            try:
                read_observation(PostgresRuntimeRepository(unsafe, "synthetic", schema_name=schema), identity)
            except RuntimeUnavailable:
                pass
            else:
                raise AssertionError("write-capable connection accepted")
    finally:
        setup.rollback()
        setup.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        setup.commit()
        setup.close()
    print("PASS actual PostgreSQL observer read-only/snapshot/fence/progress contracts")


if __name__ == "__main__":
    main()
