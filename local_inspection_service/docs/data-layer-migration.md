# VantaLine Data-Layer Migration PR1

PR1 is schema, dry-run migration tooling, smoke coverage, and runbook only. It does not switch the FastAPI runtime from JSON files to SQL and must not change endpoint read/write behavior.

Task #15 opens the PostgreSQL migration packet phase. PostgreSQL is the production database target; SQLite remains a local shadow/dry-run artifact only. See `postgres-migration-runbook.md` for PostgreSQL DDL/import artifacts, backup/restore rehearsal, runtime switch planning, and rollback gates.

The later runtime repository switch is plan-only until explicitly authorized. See `runtime-repository-switch-plan.md` for the proposed selector, PostgreSQL repository, shadow parity, cutover, smoke, and rollback sequence. See `postgres-precutover-execution-packet.md` for the reviewed pre-cutover execution packet and live read-only preflight summary. See `postgres-runtime-phase-b.md` for the disabled-default runtime selector packet. See `postgres-gate2-runtime-repository-packet.md` for the disabled-default PostgreSQL repository contract packet. See `postgres-gate3-dependency-endpoint-design.md` for the dependency and endpoint-integration design gate. See `postgres-gate4-dependency-packet.md` for the proposed PostgreSQL driver dependency gate. See `postgres-gate5-dependency-preflight-request.md` for the service-venv dependency preflight and no-op install request. See `postgres-gate6-temporary-db-preflight-request.md` for the temporary-DB real-connection preflight request.

After the first Gate 6 execution aborted safely on a missing production storage
module, see `postgres-gate7-code-deploy-packet.md` for the scoped
storage/schema code-only deploy packet required before any fresh Gate 6 retry.
See `postgres-gate7-execution-request.md` for the separate Gate 7 code-deploy
execution request; it is still not production deploy approval unless a manager
explicitly opens that execution gate.
After that request safely aborted on actual partial production state, see
`postgres-gate7-partial-baseline-execution-request.md` for the revised
partial-baseline request.
For the task #17 final acceptance target, see
`postgres-final-migration-cutover-execution-packet.md`; it is a review-only
packet for Gate6 retry, production PostgreSQL migration/cutover, runtime
effectiveness proof, full smoke, and rollback. It is not execution approval
until a manager explicitly opens that gate.
For the separate endpoint-integration prerequisite gate, see
`postgres-endpoint-integration-code-gate.md`; it adds the first admin HTTP
runtime-store probe endpoint and proves JSON-default/no-fallback behavior before
any broader business endpoint integration.
For the scoped deploy packet for that diagnostic seam, see
`postgres-endpoint-diagnostic-seam-deploy-packet.md`; it separates code-on-disk
deployment from any later live endpoint activation that would require explicit
restart/reload approval.
For the live activation execution packet for that diagnostic seam, see
`postgres-endpoint-live-activation-execution-packet.md`; it covers only
restart/reload, JSON-default env checks, protected diagnostic endpoint proof,
and restart-back/rollback planning.
For the accepted endpoint-integration code gate, see
`postgres-endpoint-integration-accepted.md`; it records the business endpoint
allowlist, runtime repository methods, transaction boundaries, local
PostgreSQL-visible write evidence, and the new
`scripts/smoke_postgres_cutover_full.py` local and deployed-postgres smoke
runner, including a local deployed-postgres contract mode for the final HTTP
plus PostgreSQL-visible write matrix and 10-disposable-account concurrent HTTP
smoke gate, plus `scripts/postgres_cutover_readiness.py` for read-only
pre-manager readiness, `scripts/validate_postgres_precutover_report.py` for
credential-free pre-cutover report validation, and
`scripts/validate_postgres_full_smoke_report.py` for final report validation.
The same accepted chain includes
`scripts/postgres_cutover_artifact_manifest.py` for creating or verifying a
non-secret manifest of reviewed cutover code/scripts/docs before the destructive
manager gate, plus `scripts/postgres_cutover_gate_report.py` for combining
manifest/readiness/pre-cutover/migration/import-row-count/full-smoke reports
without treating local contract evidence as production acceptance.
`scripts/smoke_postgres_schema_real_engine.py` adds an optional PostgreSQL
single-user smoke that runs the generated DDL through a real PostgreSQL backend
without opening sockets; it proves DDL parse/execution compatibility only, not
runtime cutover.
`scripts/smoke_postgres_import_real_engine.py` extends that real-engine path to
the generated CSV import artifacts and row-count checks, catching PostgreSQL
`COPY`/type/nullability issues before production import. Its report also
records the executed schema SQL `ddl_sha256` so the final gate can reject DDL
artifact drift.
This still does not authorize production import, env switch, service
restart/reload, or live cutover.

## Scope Boundary
- Runtime remains JSON-backed. `server.py` must not read `VANTALINE_DATA_STORE` in PR1.
- SQLite is a local dry-run/shadow artifact only. The schema uses portable `TEXT`/`INTEGER` columns and simple indexes so the repository layer can move to Postgres later.
- Source JSON is opened read-only. Default dry-run DB/report outputs go under `/tmp`; explicit paths must be ignored local artifacts.
- Raw local secrets are excluded. `ai_config.local.json`, `agent_config.local.json`, `runtime_secrets.local.env`, and retired LocateAnything local config are reported by presence/size only, without content checksums.

## Source-To-Table Mapping
- `auth.json:users` -> `users`
- `auth.json:sessions` -> `auth_sessions`, keyed by `sha256(raw_session_token)`
- `config.json` non-accessory keys -> `app_config`
- `config.json:accessories` -> `accessories`
- accessory and candidate path fields -> `accessory_assets`
- `accessory_candidates/*.json` -> `accessory_candidates`
- `ai_detection_tasks.json:tasks` -> `ai_detection_tasks`
- `data_analysis_records.json:records` -> `data_analysis_records`
- `training_tasks/*.json` -> `training_tasks`
- `pipeline_tasks.json` -> `pipeline_tasks`
- `pipeline_state.json` -> `pipeline_state`
- `auto_optimize/*.json` -> `auto_optimize_states`

Generated binaries, uploaded files, annotated outputs, normalized images, worker logs, model wheels, backups, and local runtime caches are not migrated as SQL payloads. SQL rows store metadata and path references only.

## Dry-Run Command
```bash
python3 local_inspection_service/scripts/migrate_json_to_sqlite.py \
  --source local_inspection_service \
  --db /tmp/vantaline_phase4_pr1.sqlite3 \
  --report /tmp/vantaline_phase4_pr1_report.json \
  --dry-run \
  --allow-legacy-id-repair
```

Run the command twice against the same snapshot and compare report checksums. The report is designed to be deterministic and redacted.

## Validation Policy
- Duplicate primary keys are blocking errors.
- Missing accessory IDs from legacy `config.json` are blocking unless `--allow-legacy-id-repair` is passed; repairs are deterministic and listed in the report.
- Missing owner fields are counted by table and classified through code-defined active/historical status sets. They are warnings in dry-run so legacy records can be inventoried before a runtime switch.
- Missing local paths are counted with small samples. Active runtime-dependent records with missing paths are blocking errors; historical/reference records are warning/count only. Generated assets stay on disk; the database keeps references only.
- Orphan references are code-defined and status-aware. Active AI task accessory links, active data-analysis task links, active pipeline task training/sample/dataset links, and active pipeline-state accessory/candidate links are blocking when the target is missing; historical links are warning/count only.
- Reports must not include raw session tokens, `password_hash`, provider keys, or env-file contents. `password_hash` may migrate into `users.password_hash` in the local DB.

## Apply-Local Guardrail
`--apply-local` is not part of the authorized PR1 handoff. The script contains a guarded path for future local-only use: it refuses source/blocking errors, creates an ignored metadata backup tarball, and writes `data/vantaline.sqlite3`. Do not run it for PR1 unless a manager explicitly changes scope.
