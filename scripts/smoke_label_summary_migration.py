"""Real PostgreSQL contracts for empty, rollback-compatible summary state.

Synthetic data only. The test role has the old source-table DML grants, no cache
privileges. Candidate application code still neither publishes nor reads cache.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.label_summary_schema import VERSION, migration_sql
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector

ROOT = Path(__file__).resolve().parents[1]


def main():
    suffix = uuid.uuid4().hex[:12]
    schemas = ["summary_old_" + suffix, "summary_new_" + suffix,
               "summary_lock_" + suffix, "summary_fault_" + suffix]
    schema, generated, blocked, fault = schemas
    role = "summary_writer_" + suffix
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    connection = default_postgres_connector(dsn)
    writer = default_postgres_connector(dsn)
    table = f'"{schema}".label_inspection_objects'
    cache = f'"{schema}".label_run_projection'
    migration_path = ROOT / "local_inspection_service/storage/migrations" / (VERSION + ".sql")
    migration = migration_path.read_text(encoding="utf-8")
    assert migration == migration_sql()
    prior = (ROOT / "local_inspection_service/storage/migrations/2026_09_15_label_inspection.sql").read_text(encoding="utf-8")

    def execute(sql, params=(), *, conn=connection):
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall() if cursor.description else None

    def create_old(name):
        execute(f'CREATE SCHEMA "{name}"')
        execute(f'CREATE TABLE "{name}".feature_migrations '
                '(version TEXT PRIMARY KEY,applied_at BIGINT NOT NULL,metadata_json JSONB NOT NULL)')
        execute(prior.replace("vantaline", name))
        connection.commit()

    def put_source(identity, *, conn=writer):
        execute(f"INSERT INTO {table} VALUES (%s,'alice','task','run','completed',1,1,%s,%s::jsonb)",
                (identity, identity, json.dumps({"id": identity, "kind": "run", "evidence": "synthetic"})), conn=conn)
        conn.commit()

    def publish(identity, *, commit=True):
        # A future publisher must use this lock order and the returned source,
        # never an object read before locking or after releasing the lock.
        rows = execute(f"SELECT id,raw_json FROM {table} WHERE id=%s FOR UPDATE", (identity,))
        assert len(rows) == 1
        execute(f"INSERT INTO {cache} VALUES (%s,1,%s::jsonb) ON CONFLICT(id) DO UPDATE "
                "SET raw_json=EXCLUDED.raw_json", (rows[0][0], json.dumps(rows[0][1])))
        if commit:
            connection.commit()

    def cached(identity):
        result = execute(f"SELECT raw_json FROM {cache} WHERE id=%s", (identity,))
        connection.commit()
        return bool(result)

    def rejects(sql, state, *, conn=writer):
        try:
            execute(sql, conn=conn)
        except Exception as exc:
            conn.rollback()
            assert exc.sqlstate == state, (type(exc).__name__, exc.sqlstate, state)
        else:
            conn.rollback()
            raise AssertionError("Expected SQL rejection")

    try:
        for name in (schema, blocked, fault):
            create_old(name)
        execute(postgres_ddl(generated))
        connection.commit()
        put_source("retained", conn=connection)
        before = execute(f"SELECT * FROM {table}")
        connection.commit()
        execute(migration.replace("vantaline", schema))
        connection.commit()
        assert execute(f"SELECT * FROM {table}") == before
        assert execute(f"SELECT count(*) FROM {cache}") == [(0,)]
        columns = "SELECT column_name,data_type,is_nullable FROM information_schema.columns " \
                  "WHERE table_schema=%s AND table_name='label_run_projection' ORDER BY ordinal_position"
        assert execute(columns, (schema,)) == execute(columns, (generated,)) == [
            ("id", "text", "NO"), ("projection_version", "bigint", "NO"), ("raw_json", "jsonb", "NO")]
        keys = "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_namespace n " \
               "ON n.oid=c.connamespace WHERE n.nspname=%s AND c.contype='p' AND " \
               "c.conrelid=(quote_ident(%s)||'.label_run_projection')::regclass"
        assert execute(keys, (schema, schema)) == execute(keys, (generated, generated)) == [("PRIMARY KEY (id)",)]
        assert execute("SELECT prosecdef,proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                       "WHERE n.nspname=%s AND p.proname='invalidate_label_run_projection'", (schema,)) == [
                           (True, ["search_path=pg_catalog"])]
        connection.commit()
        print("schema parity, empty state, retained source and bounded definer configuration passed", flush=True)

        execute(f'CREATE ROLE "{role}" NOLOGIN')
        execute(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
        execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO "{role}"')
        connection.commit()
        execute(f'SET ROLE "{role}"', conn=writer)
        writer.commit()
        rejects(f"DELETE FROM {cache}", "42501")
        put_source("limited")
        publish("limited")
        assert cached("limited")
        execute(f"UPDATE {table} SET status='failed' WHERE id='limited'", conn=writer)
        writer.commit()
        assert not cached("limited")
        # An untrusted temp/search-path cache cannot intercept definer DELETE.
        execute("CREATE TEMP TABLE label_run_projection(id text)", conn=writer)
        execute("INSERT INTO label_run_projection VALUES ('limited')", conn=writer)
        writer.commit()
        publish("limited")
        execute(f"UPDATE {table} SET updated_at=2 WHERE id='limited'", conn=writer)
        writer.commit()
        assert not cached("limited")
        assert execute("SELECT id FROM label_run_projection", conn=writer) == [("limited",)]
        writer.commit()
        print("old restricted writer and hostile search-path compatibility passed", flush=True)

        updates = {
            "owner_user_id": "'bob'", "task_id": "'other'", "kind": "'call'",
            "status": "'unknown'", "created_at": "9", "updated_at": "10",
            "idempotency_key": "'changed'", "raw_json": "'{\"imported\":true}'::jsonb",
        }
        for index, (field, value) in enumerate(updates.items()):
            identity = f"column_{index}"
            put_source(identity)
            publish(identity)
            execute(f"UPDATE {table} SET {field}={value} WHERE id=%s", (identity,), conn=writer)
            writer.commit()
            assert not cached(identity), field
        put_source("rename")
        publish("rename")
        execute(f"INSERT INTO {cache} VALUES ('renamed',1,'{{}}')")
        connection.commit()
        execute(f"UPDATE {table} SET id='renamed' WHERE id='rename'", conn=writer)
        writer.commit()
        assert not cached("rename") and not cached("renamed")
        publish("renamed")
        execute(f"DELETE FROM {table} WHERE id='renamed'", conn=writer)
        writer.rollback()
        assert cached("renamed"), "rollback must restore the invalidated projection"
        execute(f"SAVEPOINT before_edit", conn=writer)
        execute(f"UPDATE {table} SET status='failed' WHERE id='renamed'", conn=writer)
        execute("ROLLBACK TO SAVEPOINT before_edit", conn=writer)
        writer.commit()
        assert cached("renamed")
        execute(f"DELETE FROM {table} WHERE id='renamed'", conn=writer)
        writer.commit()
        assert not cached("renamed")
        put_source("renamed")
        publish("renamed")
        execute(f"DELETE FROM {table} WHERE id='renamed'", conn=writer)
        execute(f"INSERT INTO {table} VALUES ('renamed','bob','new-task','run','failed',9,9,'new-key','{{}}')", conn=writer)
        writer.commit()
        assert not cached("renamed"), "same-ID delete/reinsert must invalidate"
        execute(f"INSERT INTO {cache} VALUES ('copy',1,'{{}}')")
        connection.commit()
        with writer.cursor() as cursor:
            with cursor.copy(f"COPY {table} FROM STDIN") as stream:
                stream.write_row(("copy", "alice", "task", "run", "completed", 1, 1, "copy", "{}"))
        writer.commit()
        assert not cached("copy")
        publish("copy")
        execute(f"INSERT INTO {table} VALUES ('copy','alice','task','run','failed',1,1,'copy','{{}}') "
                "ON CONFLICT(id) DO UPDATE SET status=EXCLUDED.status", conn=writer)
        writer.commit()
        assert not cached("copy")
        print("every source column, COPY/upsert, rollback/savepoint and same-ID replacement passed", flush=True)

        # The publication source lock serializes a previous-version writer.
        publish("copy", commit=False)
        execute("SET LOCAL lock_timeout='100ms'", conn=writer)
        rejects(f"UPDATE {table} SET status='late' WHERE id='copy'", "55P03")
        connection.commit()
        assert cached("copy")
        execute(f"UPDATE {table} SET status='late' WHERE id='copy'", conn=writer)
        writer.commit()
        assert not cached("copy")
        publish("copy")
        execute(migration.replace("vantaline", schema))
        execute(migration.replace("vantaline", schema))
        connection.commit()
        assert cached("copy"), "identical migration reentry must not clear existing cache"
        assert execute(f'SELECT count(*) FROM "{schema}".feature_migrations WHERE version=%s', (VERSION,)) == [(1,)]
        connection.commit()

        # A hostile user cannot attach the privileged function to their own rows.
        execute(f'CREATE TABLE "{schema}".untrusted_source(id text)')
        execute(f'GRANT INSERT,TRIGGER ON "{schema}".untrusted_source TO "{role}"')
        connection.commit()
        execute(f'CREATE TRIGGER malicious AFTER INSERT ON "{schema}".untrusted_source '
                f'FOR EACH ROW EXECUTE FUNCTION "{schema}".invalidate_label_run_projection()', conn=writer)
        writer.commit()
        rejects(f"INSERT INTO {schema}.untrusted_source VALUES ('copy')", "P0001")
        assert cached("copy")
        print("publication lock, idempotent reentry and foreign-trigger rejection passed", flush=True)

        # Real DDL lock timeout must leave neither cache, function nor ledger row.
        execute("RESET ROLE", conn=writer)
        writer.commit()
        execute(f'LOCK TABLE "{blocked}".label_inspection_objects IN ROW EXCLUSIVE MODE', conn=writer)
        rejects(migration.replace("vantaline", blocked), "55P03", conn=connection)
        writer.rollback()
        for name in (blocked, fault):
            if name == fault:
                damaged = migration.replace("vantaline", name).replace(
                    f"INSERT INTO {name}.feature_migrations", f"SELECT 1/0; INSERT INTO {name}.feature_migrations")
                rejects(damaged, "22012", conn=connection)
            assert execute("SELECT to_regclass(%s)", (f"{name}.label_run_projection",)) == [(None,)]
            assert execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                           "WHERE n.nspname=%s AND p.proname='invalidate_label_run_projection'", (name,)) == [(0,)]
            assert execute(f'SELECT count(*) FROM "{name}".feature_migrations WHERE version=%s', (VERSION,)) == [(0,)]
            connection.commit()
            execute(migration.replace("vantaline", name))
            connection.commit()
        print("real lock timeout, interrupted transaction rollback and successful retry passed", flush=True)
    finally:
        writer.rollback()
        # close() sends termination without waiting for the backend to remove
        # temporary objects. Drop this role-owned fixture and wait for COMMIT
        # before another session attempts DROP ROLE.
        execute("DROP TABLE IF EXISTS pg_temp.label_run_projection", conn=writer)
        writer.commit()
        writer.close()
        connection.rollback()
        for name in schemas:
            execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        execute(f'DROP ROLE IF EXISTS "{role}"')
        connection.commit()
        connection.close()


if __name__ == "__main__":
    main()
