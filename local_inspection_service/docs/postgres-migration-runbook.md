# PostgreSQL Migration Packet

This packet prepares the next database phase after the accepted pre-SQL JSON-runtime online update. It does not authorize production apply, runtime switch, or `VANTALINE_DATA_STORE`.

## Gate Order

1. Fix the current `source_error_count=4`, isolate those sources as warning-only with code-reviewed proof, or obtain an explicit manager waiver.
2. Produce PostgreSQL DDL, import artifacts, and a redacted report from the same source snapshot.
3. Rehearse backup and restore before any cutover window.
4. Run Challenger review on data consistency, backup recoverability, source-error handling, secret redaction, and rollback.
5. Only after manager cutover gate: apply to PostgreSQL, enable the runtime switch, and run online smoke.

## Artifact Command

```bash
python3 local_inspection_service/scripts/prepare_json_to_postgres.py \
  --source local_inspection_service \
  --ddl /tmp/vantaline_postgres_schema.sql \
  --out-dir /tmp/vantaline_postgres_import \
  --report /tmp/vantaline_postgres_report.json \
  --allow-legacy-id-repair
```

If source parse errors exist, the script still emits DDL and a report, but it does not emit psql import CSV/load artifacts unless an explicit `--source-error-waiver-id <manager-msg-id>` is supplied. A waiver should be used only after manager approval; the report records the waiver id.

## Real Engine Import Smoke

When PostgreSQL binaries are available, run the generated DDL and CSV import
artifacts through a real PostgreSQL backend before treating the packet as ready
for cutover review. These smokes use PostgreSQL single-user mode, so they do not
open TCP or Unix sockets and do not replace live runtime smoke.

```bash
python3 local_inspection_service/scripts/smoke_postgres_schema_real_engine.py \
  --postgres-bin-dir /usr/lib/postgresql/16/bin

python3 local_inspection_service/scripts/smoke_postgres_import_real_engine.py \
  --postgres-bin-dir /usr/lib/postgresql/16/bin
```

If `initdb`/`postgres` need an unpacked library directory, pass
`--library-dir <path-containing-libpq.so.5>`. Passing the schema smoke proves
the DDL is accepted by a real PostgreSQL engine and that `schema_migrations` is
seeded. Passing the import smoke additionally proves emitted CSV artifacts load
through PostgreSQL `COPY` with expected row counts, and the import smoke report
records the exact `ddl_sha256` for the schema SQL it executed. Neither smoke proves
repository writes, service env, restart, or authenticated HTTP cutover.

## PostgreSQL Import Shape

- DDL creates an isolated `vantaline` schema by default.
- JSON payload columns use `JSONB`.
- timestamp-like integer fields use `BIGINT`.
- boolean flags use `BOOLEAN`.
- primary keys and indexes are generated from `storage/schema.py`.
- psql load artifacts use CSV plus `load_postgres.sql` with `\copy` commands.
- `\copy` commands force empty `TEXT` fields to empty strings, not PostgreSQL
  `NULL`, so legacy empty IDs/actor fields still satisfy `NOT NULL` text
  columns.
- `schema_migrations` is seeded by the DDL with `ON CONFLICT`; import artifacts intentionally do not `\copy` `schema_migrations.csv`.

The import stores metadata and path references only. Uploaded files, normalized assets, model outputs, worker logs, and backups remain on disk/object storage and are referenced by path.

## Backup And Restore Rehearsal

Before production apply:

```bash
BACKUP_ROOT=/opt/vantaline/backups/postgres-migration/$(date -u +%Y%m%d%H%M%S)
sudo mkdir -p "$BACKUP_ROOT"

# Code backup: excludes live data and local secret/env material.
sudo tar -C /opt/vantaline/app \
  --exclude='local_inspection_service/data' \
  --exclude='local_inspection_service/*.env' \
  --exclude='*.local.json' \
  --exclude='*.local.env' \
  --exclude='runtime_secrets.local.env*' \
  --exclude='ai_config.local.json*' \
  --exclude='agent_config.local.json*' \
  --exclude='*.sqlite3*' \
  -czf "$BACKUP_ROOT/app-code.tgz" .

# JSON data backup: separate restore decision because it can overwrite user data.
sudo tar -C /opt/vantaline/app/local_inspection_service/data \
  -czf "$BACKUP_ROOT/data-json.tgz" .
sudo chmod 600 "$BACKUP_ROOT/data-json.tgz"

# PostgreSQL backup after import rehearsal or production apply.
pg_dump --format=custom --file="$BACKUP_ROOT/vantaline.postgres.dump" "$DATABASE_URL"
```

Restore rehearsal must be done on a disposable database first:

```bash
createdb vantaline_restore_rehearsal
pg_restore --clean --if-exists --dbname=vantaline_restore_rehearsal "$BACKUP_ROOT/vantaline.postgres.dump"
psql "$RESTORE_REHEARSAL_DATABASE_URL" -c 'select count(*) from vantaline.accessories;'
```

Do not restore `data-json.tgz` onto production unless manager explicitly approves a data rollback.

## Runtime Switch Plan

Runtime switch is a later gate, not part of this packet.

1. Add a PostgreSQL repository implementation behind `VANTALINE_DATA_STORE=json|postgres`.
2. Keep default `json` until cutover gate.
3. In maintenance window, stop writes, run final JSON backup, generate final import report, import PostgreSQL, run consistency checks, then set the runtime env.
4. Restart service and run online smoke.
5. If smoke fails, revert env to JSON and restart. Code rollback is separate from data rollback.

## Online Smoke Checklist

- service active after restart.
- `VANTALINE_DATA_STORE=postgres` only after manager cutover gate.
- `/api/auth/status` 200 unauthenticated.
- unauthorized business APIs still return 401.
- authenticated admin smoke covers 配件 / 任务 / 训练 / 检测 / 结果复核.
- PostgreSQL row-count report matches migration report for users, accessories, candidates, AI tasks, data-analysis records, training tasks, pipeline tasks, pipeline state, and auto-optimize state.
- journal has no service errors.
- no runtime SQLite residue is created.

## Rollback

Default rollback is runtime-only:

```bash
sudo systemctl stop vantaline
sudo systemctl unset-environment VANTALINE_DATA_STORE DATABASE_URL
# restore previous systemd env/drop-in if one was changed
sudo systemctl daemon-reload
sudo systemctl start vantaline
```

PostgreSQL data rollback uses `pg_restore` into a replacement database and must be manager-approved. JSON data rollback from `data-json.tgz` also requires separate manager approval.
