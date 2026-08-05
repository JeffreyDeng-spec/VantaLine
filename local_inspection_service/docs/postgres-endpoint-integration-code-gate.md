# PostgreSQL Endpoint-Integration Code Gate

This task #19 packet prepares the first endpoint-integration code gate required
before PostgreSQL cutover can be considered again. It does not authorize
production PostgreSQL connection, role/database/schema mutation, service
env/drop-in change, restart/reload, import, runtime switch, or data cleanup.

## Gate Objective

Prove that FastAPI can route an HTTP endpoint through runtime repository
selection while preserving JSON-default behavior and fail-closing under
PostgreSQL-selected mode.

This is not final business-route cutover readiness. It is the smallest safe
code gate after task #18:

- add one admin diagnostic endpoint wired to `build_runtime_repository()`;
- keep broad business endpoints on the existing JSON path;
- prove default JSON does not connect to PostgreSQL;
- prove `VANTALINE_DATA_STORE=postgres` without usable DB config fails closed
  and does not return a JSON fallback;
- keep all production PG/env/import/runtime-switch boundaries closed.

## Scoped Code

- `local_inspection_service/server.py`
- `local_inspection_service/scripts/smoke_endpoint_runtime_store_probe.py`
- `local_inspection_service/docs/postgres-endpoint-integration-code-gate.md`
- `local_inspection_service/docs/data-layer-migration.md`

No `requirements.txt`, data files, systemd files, migration artifacts, or
production env files are part of this packet.

## Exact Endpoint Allowlist

| Method | Path | Existing/new call site | Repository method | Read/write | Transaction boundary |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/admin/runtime-store/probe` | new `get_runtime_store_probe()` | `build_runtime_repository()` and, only when store is `postgres`, `count_rows(("schema_migrations",))` | read-only diagnostic | none; no mutation |

All other endpoints remain excluded from this gate, including:

- `/api/accessories`;
- `/api/accessories/{id}/detail`;
- `/api/pipeline/tasks`;
- `/api/training/status`;
- `/api/training/resources`;
- `/api/ai/tasks`;
- `/api/data-analysis/records`;
- every auth/session write path;
- every business `POST`, `PATCH`, `PUT`, and `DELETE` path.

## Behavior Contract

Default JSON:

- `VANTALINE_DATA_STORE` unset selects JSON.
- endpoint returns `store=json`, `repository_kind=json`,
  `postgres_count_probe=null`, and `json_fallback_used=false`.
- PostgreSQL connector is not called.

PostgreSQL selected without usable DB/env:

- `VANTALINE_DATA_STORE=postgres` without `DATABASE_URL` returns HTTP `503`.
- connector failure returns HTTP `503` with a redacted message.
- response includes `json_fallback_used=false`.
- response must not include raw `DATABASE_URL`, password, token, or secret query
  value.

PostgreSQL selected with an intentional future DB/env:

- endpoint may connect through the accepted selector.
- it may run a read-only `schema_migrations` count probe.
- any count/query failure returns HTTP `503` with exception type only, not raw
  connection details.

## Security Boundary

- Endpoint is under `/api/admin` and additionally calls `require_admin_role()`.
- It reports only store, repository kind, fallback boolean, and a
  `schema_migrations` count when PostgreSQL is explicitly selected.
- It does not expose env values or database URLs.
- It does not read or reuse live `auth.json` tokens.

## Smoke Evidence

Run:

```bash
python3 -m py_compile \
  local_inspection_service/server.py \
  local_inspection_service/scripts/smoke_endpoint_runtime_store_probe.py

python3 local_inspection_service/scripts/smoke_endpoint_runtime_store_probe.py
```

The smoke uses a temporary `LOCAL_INSPECTION_ROOT` and FastAPI `TestClient`.
It verifies:

- `/api/admin/runtime-store/probe` is protected before bootstrap and without
  auth;
- default JSON endpoint response is `store=json` / `repository_kind=json`;
- default JSON makes zero PostgreSQL connector calls;
- `VANTALINE_DATA_STORE=postgres` without `DATABASE_URL` fails closed with HTTP
  `503`;
- connector failure with a secret-bearing URL is redacted, fail-closed, and does
  not fall back to JSON.

## Cutover Relationship

This gate can satisfy the first part of task #18 Stage -1: proof that a
deployed HTTP endpoint is wired to runtime repository selection. It does not
satisfy broad business-route runtime effectiveness.

Before final PostgreSQL cutover, later endpoint-integration gates still must
allowlist and wire the business endpoints needed by the full smoke:

- 配件;
- 任务 / pipeline;
- 数据集训练;
- 检测;
- 结果复核;
- reversible write probes with PostgreSQL-visible SQL evidence.

## Rollback

Rollback is code-only:

- remove the new endpoint and helper from `server.py`;
- remove `smoke_endpoint_runtime_store_probe.py`;
- remove this doc and its index link.

No data restore, PostgreSQL cleanup, systemd reload, or env rollback is relevant
because this gate has no production mutation.

## Review Focus

- Importing `server.py` with JSON default still does not connect to PostgreSQL.
- The new endpoint is admin-only and read-only.
- JSON-default behavior remains unchanged for existing business endpoints.
- PostgreSQL-selected failures are explicit, redacted, and do not fall back to
  JSON.
- The gate is honest about scope: it is a first endpoint seam, not final cutover
  readiness.
