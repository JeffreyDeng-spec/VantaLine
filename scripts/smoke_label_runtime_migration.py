"""Expand-only runtime-state migration against real, isolated PostgreSQL schemas."""
import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026_10_04_label_runtime_state"


def columns(cursor, schema):
    cursor.execute("SELECT column_name,data_type,is_nullable FROM information_schema.columns "
                   "WHERE table_schema=%s AND table_name='label_runtime_state' ORDER BY ordinal_position", (schema,))
    return cursor.fetchall()


def primary_key(cursor, schema):
    cursor.execute("SELECT a.attname FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid "
                   "JOIN pg_namespace n ON n.oid=t.relnamespace "
                   "JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=ANY(i.indkey) "
                   "WHERE n.nspname=%s AND t.relname='label_runtime_state' AND i.indisprimary", (schema,))
    return cursor.fetchall()


def main():
    schema = "label_migration_" + uuid.uuid4().hex[:12]
    generated = "label_generated_" + uuid.uuid4().hex[:12]
    connection = default_postgres_connector(os.environ["VANTALINE_POSTGRES_DSN"])
    migration = (ROOT / "local_inspection_service/storage/migrations" / (VERSION + ".sql")).read_text(encoding="utf-8")
    # Production SQL is run unchanged except the schema name, which is generated here.
    migration = migration.replace("vantaline", schema)
    raw = PostgresRuntimeRepository(connection, "<synthetic>", schema_name=schema)
    repo = LabelRepository(raw)
    try:
        with connection.cursor() as c:
            c.execute(f'CREATE SCHEMA "{schema}"')
            c.execute(f'CREATE TABLE "{schema}".feature_migrations '
                      '(version TEXT PRIMARY KEY,applied_at BIGINT NOT NULL,metadata_json JSONB NOT NULL)')
            prior = (ROOT / "local_inspection_service/storage/migrations/2026_09_15_label_inspection.sql").read_text(encoding="utf-8")
            c.execute(prior.replace("vantaline", schema))
            c.execute(postgres_ddl(generated))
        connection.commit()
        task = repo.create("alice", "old-task", "old task", [])
        with repo.tx() as c:
            call = repo.new("alice", task["id"], "call", "old-call", status="unknown",
                            evidence={"response": "synthetic evidence"},
                            profile_snapshot={"profile_id": "synthetic", "version": "v1", "secret_ref": "fake-ref"})
            repo.put(c, call, True)
        old_task, old_call = repo.get("alice", task["id"]), repo.get("alice", call["id"])
        with connection.cursor() as c:
            c.execute(migration)
            assert columns(c, schema) == columns(c, generated) == [
                ("id", "text", "NO"), ("updated_at", "bigint", "NO"), ("raw_json", "jsonb", "NO")]
            assert primary_key(c, schema) == primary_key(c, generated) == [("id",)]
            c.execute(f'SELECT count(*) FROM "{schema}".label_runtime_state')
            assert c.fetchone() == (0,), "Migration must not activate any runtime state"
        connection.commit()
        # Exercise registered primary-key upsert without introducing an application caller.
        raw.upsert_row("label_runtime_state", {"id": "control", "updated_at": 1,
                        "raw_json": {"maintenance": True, "paused": True, "git_commit": "a"*40}})
        with connection.cursor() as c:
            c.execute(f'SELECT id,updated_at,raw_json FROM "{schema}".label_runtime_state')
            before = c.fetchall()
            c.execute(migration)
            c.execute(migration)
            c.execute(f'SELECT id,updated_at,raw_json FROM "{schema}".label_runtime_state')
            assert c.fetchall() == before
            c.execute(f'SELECT count(*) FROM "{schema}".feature_migrations WHERE version=%s', (VERSION,))
            assert c.fetchone() == (1,)
        connection.commit()
        assert repo.get("alice", task["id"]) == old_task
        assert repo.get("alice", call["id"]) == old_call
        assert repo.get("bob", task["id"]) is None
        # Old read/write APIs continue to work after the additive migration.
        later = repo.create("bob", "new-task", "new task", [])
        assert repo.get("bob", later["id"])["name"] == "new task"
        assert repo.get("alice", later["id"]) is None
        print("label runtime migration: real PostgreSQL parity, empty state, idempotency, evidence and old API compatibility passed")
    finally:
        connection.rollback()
        with connection.cursor() as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            c.execute(f'DROP SCHEMA IF EXISTS "{generated}" CASCADE')
        connection.commit()
        connection.close()


if __name__ == "__main__":
    main()
