# PostgreSQL Endpoint Integration Accepted

Status: code-on-disk endpoint integration gate passed for local, credential-free
runtime repository PostgreSQL-visible write evidence. This document does not authorize production
PostgreSQL import, service env switch, service restart/reload, or live cutover.

## Runtime Rule

- Default runtime remains JSON when `VANTALINE_DATA_STORE` is unset or `json`.
- `VANTALINE_DATA_STORE=postgres` requires `DATABASE_URL`.
- PostgreSQL selection fails closed through `HTTPException(503)` and does not
  fall back to JSON.
- Runtime session IDs are stored in PostgreSQL as `sha256(cookie_token)` keys;
  raw cookie tokens are not written to `auth_sessions`.
- PostgreSQL runtime connections are cached per worker thread. A single request
  thread reuses its connection across repository calls, while concurrent request
  threads do not share a DB-API connection object. The local smoke covers 10
  concurrent pre-existing accounts reading the main allowlisted runtime paths.
- If a cached PostgreSQL connection reports `closed`, the next runtime
  repository selection evicts it and opens a new connection for that thread.
  `reset_runtime_repository_cache()` and
  `clear_thread_runtime_repository_selection()` close the current thread
  selection before the next selection reconnects.
- PostgreSQL repository read helpers explicitly end read transactions after
  `SELECT` cursors are closed, so thread-local runtime connections do not keep
  idle read transactions open between requests.

## Exact Allowlist

| Method / path family | Repository tables | Repository method | Read/write | Transaction boundary |
| --- | --- | --- | --- | --- |
| Auth store used by `/api/auth/*` and middleware | `users`, `auth_sessions` | `fetch_all`, `replace_tables`, `upsert_row`, `delete_by_primary_key` | read/write | `users` upsert/delete per admin user transaction; `auth_sessions` upsert/delete per session; `replace_tables` retained for full auth-store replace |
| `GET /api/admin/runtime-store/probe` | `schema_migrations` | `count_rows` | read | single read-only count probe |
| Config/accessory endpoints under `/api/accessories*` | `app_config`, `accessories` | `fetch_all`, `replace_tables`, `fetch_by_primary_key`, `upsert_row`, `delete_by_primary_key` | read/write | app config replace; direct accessories upsert/delete per row |
| Accessory candidate endpoints under `/api/accessories/candidates*` and candidate mutation helpers | `accessory_candidates` | `fetch_by_primary_key`, `upsert_row`, `delete_by_primary_key` | read/write | single candidate row upsert/delete |
| Image job endpoints under `/api/image-jobs*` and `/api/image-job-candidates*` | `training_tasks`, `accessory_candidates`, `accessories` | `fetch_all`, `fetch_by_primary_key`, `upsert_row`, `delete_by_primary_key`, `replace_tables` | read/write | training job reads; candidate image job list/action/worker queue upserts `accessory_candidates`; accessory image jobs write through `accessories` |
| AI task endpoints under `/api/ai/tasks*` and dashboard route helper | `ai_detection_tasks` | `fetch_all`, `upsert_row`, `delete_by_primary_key` | read/write | single AI task row upsert/delete; dashboard route upserts one AI task row |
| Auto-optimize state under `/api/ai/tasks/*/auto-optimize*` and pipeline auto-link helpers | `auto_optimize_states` | `fetch_all`, `fetch_by_primary_key`, `upsert_row` | read/write | single state row upsert; pipeline accessory-match reads PostgreSQL states |
| Data-analysis records under `/api/data-analysis/records*` | `data_analysis_records` | `fetch_all`, `fetch_by_primary_key`, `upsert_row`, `delete_by_primary_key` | read/write | single data-analysis record row upsert/delete |
| Training task helpers used by `/api/training/*` | `training_tasks` | `fetch_all`, `upsert_row`, `delete_by_primary_key` | read/write | single training task row upsert/delete |
| Pipeline endpoints under `/api/pipeline/tasks*` | `pipeline_tasks` | `fetch_all`, `fetch_by_primary_key`, `upsert_row`, `delete_by_primary_key`, `replace_all` | read/write | single pipeline task row for direct/link-status mutations; `replace_all` retained for batch sync |
| Pipeline accessory/state helpers used by `/api/pipeline/accessories*` and candidate confirmation | `pipeline_state` | `fetch_all`, `upsert_row`, `replace_all` | read/write | changed state keys upsert per row; `replace_all` retained for full state saves |

`accessory_assets` remains populated by the offline import artifacts in this
gate. Online incremental asset-row syncing is intentionally not part of this
allowlist.

## Smoke Evidence

Passed locally:

```bash
python3 local_inspection_service/scripts/smoke_runtime_store_selector.py
python3 local_inspection_service/scripts/smoke_postgres_runtime_repository.py
python3 local_inspection_service/scripts/smoke_endpoint_runtime_store_probe.py
python3 local_inspection_service/scripts/smoke_postgres_cutover_readiness.py
python3 local_inspection_service/scripts/smoke_postgres_cutover_artifact_manifest.py
python3 local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py
python3 local_inspection_service/scripts/smoke_postgres_cutover_gate_report.py
python3 local_inspection_service/scripts/smoke_postgres_import_row_count_report.py
python3 local_inspection_service/scripts/smoke_postgres_final_cutover_packet_docs.py
python3 local_inspection_service/scripts/smoke_postgres_precutover_report_validator.py
python3 local_inspection_service/scripts/smoke_postgres_full_smoke_report_validator.py
python3 local_inspection_service/scripts/smoke_postgres_local_preflight_suite_report_validator.py
python3 local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py \
  --require-real-engine \
  --report /tmp/vantaline_postgres_local_preflight_suite.json
python3 local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py \
  --report /tmp/vantaline_postgres_local_preflight_suite.json
python3 local_inspection_service/scripts/smoke_postgres_cutover_full.py
python3 local_inspection_service/scripts/postgres_cutover_artifact_manifest.py create \
  --app-root . \
  --manifest /tmp/vantaline_postgres_cutover_artifacts_manifest.json
python3 local_inspection_service/scripts/postgres_cutover_artifact_manifest.py verify \
  --app-root . \
  --manifest /tmp/vantaline_postgres_cutover_artifacts_manifest.json \
  --report /tmp/vantaline_postgres_cutover_artifacts_verify.json
python3 local_inspection_service/scripts/smoke_postgres_cutover_full.py \
  --mode deployed-precutover-contract \
  --report /tmp/vantaline_endpoint_integration_preflight_contract.json
python3 local_inspection_service/scripts/validate_postgres_precutover_report.py \
  --report /tmp/vantaline_endpoint_integration_preflight_contract.json \
  --expected-mode deployed-precutover-contract
python3 local_inspection_service/scripts/smoke_postgres_cutover_full.py \
  --mode deployed-postgres-contract \
  --report /tmp/vantaline_deployed_postgres_contract_report.json
python3 local_inspection_service/scripts/validate_postgres_full_smoke_report.py \
  --report /tmp/vantaline_deployed_postgres_contract_report.json \
  --expected-mode deployed-postgres-contract \
  --expected-concurrent-accounts 10
python3 local_inspection_service/scripts/postgres_cutover_gate_report.py \
  --artifact-verify-report /tmp/vantaline_postgres_cutover_artifacts_verify.json \
  --readiness-report /tmp/vantaline_postgres_cutover_readiness_current.json \
  --deploy-package-extract-report /tmp/vantaline-postgres-cutover-deploy-package-extract-report.json \
  --local-preflight-suite-report /tmp/vantaline_postgres_local_preflight_suite.json \
  --migration-report /tmp/vantaline_postgres_report.json \
  --row-count-report /tmp/vantaline_import_row_count_report.json \
  --import-engine-report /tmp/vantaline_existing_packet_import_real_engine_report.json \
  --precutover-report /tmp/vantaline_endpoint_integration_preflight_contract.json \
  --full-smoke-report /tmp/vantaline_deployed_postgres_contract_report.json \
  --expected-concurrent-accounts 10 \
  --report /tmp/vantaline_postgres_cutover_gate_report_current.json
python3 local_inspection_service/scripts/smoke_postgres_migration_packet.py
python3 local_inspection_service/scripts/smoke_data_layer_migration.py
PYTHONPYCACHEPREFIX=/tmp/vantaline_pycache python3 -m py_compile \
  local_inspection_service/server.py \
  local_inspection_service/storage/postgres_runtime_repository.py \
  local_inspection_service/storage/runtime_records.py \
  local_inspection_service/scripts/postgres_cutover_artifact_manifest.py \
  local_inspection_service/scripts/smoke_postgres_cutover_artifact_manifest.py \
  local_inspection_service/scripts/postgres_cutover_readiness.py \
  local_inspection_service/scripts/smoke_postgres_cutover_readiness.py \
  local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py \
  local_inspection_service/scripts/smoke_postgres_cutover_full.py \
  local_inspection_service/scripts/postgres_cutover_gate_report.py \
  local_inspection_service/scripts/smoke_postgres_cutover_gate_report.py \
  local_inspection_service/scripts/validate_postgres_migration_report.py \
  local_inspection_service/scripts/postgres_import_row_count_report.py \
  local_inspection_service/scripts/smoke_postgres_import_row_count_report.py \
  local_inspection_service/scripts/smoke_postgres_schema_real_engine.py \
  local_inspection_service/scripts/smoke_postgres_import_real_engine.py \
  local_inspection_service/scripts/smoke_postgres_final_cutover_packet_docs.py \
  local_inspection_service/scripts/validate_postgres_precutover_report.py \
  local_inspection_service/scripts/smoke_postgres_precutover_report_validator.py \
  local_inspection_service/scripts/validate_postgres_full_smoke_report.py \
  local_inspection_service/scripts/smoke_postgres_full_smoke_report_validator.py \
  local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py \
  local_inspection_service/scripts/smoke_postgres_local_preflight_suite_report_validator.py \
  local_inspection_service/scripts/smoke_endpoint_runtime_store_probe.py \
  local_inspection_service/scripts/smoke_postgres_runtime_repository.py \
  local_inspection_service/scripts/smoke_runtime_store_selector.py
```

The cutover smoke uses an in-memory DB-API fake with
`VANTALINE_DATA_STORE=postgres` and verifies PostgreSQL-visible writes for:
auth, config/accessories, admin probe, AI tasks, pipeline tasks, training tasks,
pipeline state, accessory candidates, candidate image jobs, data-analysis records, and auto-optimize state. It also
verifies the target 10-account concurrent read/probe scenario with per-thread
PostgreSQL connection ownership checks and read-transaction rollback evidence.
The endpoint runtime-store probe smoke verifies JSON-default/no-connect,
PostgreSQL fail-closed/no-fallback behavior, same-thread connection reuse,
closed cached-connection rebuild, and reset/clear reconnect behavior.
The cutover readiness smoke verifies the read-only readiness report can pass
against a complete temporary app root and fails closed without leaking raw env
values when required artifacts or pre-cutover env hygiene are missing.
The cutover artifact manifest tool creates and verifies a non-secret manifest
covering reviewed code, scripts, and docs only. It excludes runtime data,
backups, reports, env files, and secret-like paths, and its smoke verifies that
missing/hash-changed artifacts fail closed.
The cutover deploy package tool wraps that manifest allowlist in a non-secret
tarball with embedded install notes and package verification. It is a code
handoff artifact only; it does not prove service activation, PostgreSQL import,
runtime env switch, or final smoke.
The cutover gate report tool consumes the manifest verification, readiness,
pre-cutover, migration, real-engine import, import row-count parity, and
full-smoke reports and emits a non-secret final gate summary.
It deliberately keeps `deployed-postgres-contract` evidence separate from real
`deployed-postgres` evidence, so local contract smoke with 10 concurrent
sessions cannot be mistaken for production cutover acceptance.

The deployed-postgres runner has a local contract mode:

```bash
python3 local_inspection_service/scripts/smoke_postgres_cutover_full.py \
  --mode deployed-postgres-contract \
  --report /tmp/vantaline_deployed_postgres_contract_report.json
```

That mode starts a temporary local fake HTTP service and fake PostgreSQL
repository, then exercises the final full-smoke HTTP/cookie/multipart/JSON
request matrix, 10 disposable-account concurrent HTTP login/read checks,
PostgreSQL-visible write checks, cleanup checks, and non-secret report
validation. The report validator rejects missing concurrency evidence,
non-final modes, failed write/cleanup booleans, malformed disposable IDs, and
secret-bearing report markers. It also rejects reports whose endpoint allowlist
does not cover auth, runtime probe, accessories, image jobs, AI tasks,
auto-optimize, data-analysis, training, pipeline task, and pipeline accessory
path families, or whose PostgreSQL-visible read/write/cleanup table evidence
does not cover the required runtime tables.
For the accepted read-only-only write probes, it also rejects missing
`read_only_write_waiver_id`, `read_only_write_waiver_required=true`, or
table-specific `write_coverage_exceptions`. `training_tasks` remains a
read-only-only waiver. `data_analysis_records` defaults to a waiver unless the
final smoke is explicitly run with `--run-data-analysis-write`, which performs
a disposable `POST /api/analyze/image` followed by
`DELETE /api/data-analysis/records/{record_id}` and requires PostgreSQL-visible
write/cleanup proof. AI task write coverage is now a reversible
PostgreSQL-visible create/update/delete smoke, not a read-only waiver.
It does not prove production service activation.

`smoke_postgres_full_smoke_report_validator.py` is a socket-free unit smoke for
the final report validator only. It proves the validator rejects missing
PostgreSQL-visible concurrent sessions, missing table evidence, missing
allowlist families, and secret-like markers; it does not replace the HTTP
contract or deployed smoke.
`smoke_postgres_local_preflight_suite.py` runs the socket-free local PostgreSQL
migration preflight bundle and emits `production_cutover_proof=false`; it is a
convenience wrapper for local contract evidence, not deployed-postgres final
acceptance.
`validate_postgres_local_preflight_suite_report.py` independently validates
that bundle report, including mandatory real-engine schema/import smokes and
the required local smoke names, before the final gate consumes it.

The same runner also supports the final cutover packet preflight shape:

```bash
python3 local_inspection_service/scripts/smoke_postgres_cutover_full.py \
  --mode deployed-precutover \
  --base-url http://127.0.0.1:8765 \
  --expect-store json \
  --require-no-postgres-service-env \
  --report /tmp/vantaline_endpoint_integration_preflight.json
```

That mode is credential-free, requires `--base-url`, fetches the public root and
first static JavaScript asset from the live service, and emits the reviewed
allowlist/report booleans required before the destructive cutover stages. It is
not the authenticated live route proof and does not use unauthenticated `/api/*`
responses as route-dispatch evidence. A local `deployed-precutover-contract`
mode covers the same public-root/static report shape without requiring a real
service on port 8765.
The pre-cutover report validator rejects final full-smoke reports, missing
public root/static evidence, missing allowlist metadata, dirty PostgreSQL env
signals, missing required allowlist path families, and secret-bearing report
markers.

For the final post-switch gate, the same runner now also supports the
authenticated deployed PostgreSQL mode used by
`postgres-final-migration-cutover-execution-packet.md`: it logs in from private
runtime credential env vars, runs public/authenticated main-flow HTTP checks,
creates 10 disposable admin smoke accounts for concurrent HTTP login/read
coverage, creates/updates/deletes disposable accessory, AI task, and pipeline
rows, optionally creates/deletes a disposable data-analysis record when
`--run-data-analysis-write` is enabled, and verifies those writes directly
through the PostgreSQL runtime repository before cleanup. The final report must
show all 10 concurrent sessions as
PostgreSQL-visible via `concurrent_postgres_visible_sessions=10` and all 10
runtime probes as PostgreSQL runtime observations via
`concurrent_runtime_probe_count=10` and
`concurrent_runtime_probe_connection_observations=<10-16-hex-ids>`. The unique
thread-local connection count may be lower than 10 when the deployed service
reuses worker connections, and that reuse must be reported explicitly; HTTP-only
success is not enough. Concurrent account cleanup verifies the disposable users and their
sessions are removed without relying on global auth row counts. That mode
refuses to run without both `--cleanup` and
`--require-postgres-visible-writes`. If a custom `--db-url-env` is used, the
runner passes that value to the runtime selector through a copied environment
mapping and does not rewrite the process `DATABASE_URL`. On success and
best-effort failure cleanup, it rolls back/closes its own PostgreSQL repository
connection and reports `postgres_repository_close_pass=true` on the success
path.

## Remaining Live Gate

Production cutover still requires an explicit manager execution window,
authenticated live admin proof, real PostgreSQL role/database/schema/import,
service env/drop-in switch, service restart/reload, and full live smoke. This
document is the endpoint-integration code gate evidence only. Concurrent writes
that replace whole JSON-equivalent collections retain the existing JSON-era
last-writer-wins semantics and should not be broadened without a separate
business conflict policy.
