# PostgreSQL Runtime Phase B Packet

This packet adds a disabled-default runtime datastore selector. It does not wire FastAPI endpoints to PostgreSQL, connect to production PostgreSQL, import production data, create roles/databases, install systemd drop-ins, set `VANTALINE_DATA_STORE`, set `DATABASE_URL`, or switch runtime.

## Code Shape

- New module: `local_inspection_service/storage/runtime_selector.py`.
- New smoke: `local_inspection_service/scripts/smoke_runtime_store_selector.py`.
- Default datastore is JSON when `VANTALINE_DATA_STORE` is unset or explicitly `json`.
- Default JSON selection does not read `DATABASE_URL` and does not initialize a PostgreSQL connector.
- `VANTALINE_DATA_STORE=postgres` requires `DATABASE_URL` and initializes PostgreSQL through an explicit connector.
- If PostgreSQL connection initialization fails, selector raises `RuntimeStoreConnectionError` and does not return a JSON fallback.
- Error text redacts `DATABASE_URL` and should be safe for reports/logs/Slock.

## Driver Boundary

The local environment currently has no `psycopg`, `psycopg2`, or `asyncpg` module installed. The selector therefore supports an injectable connector for smoke/unit tests. A real PostgreSQL driver install is a separate code-deploy dependency decision before endpoint integration or env switch.

## Smoke Evidence

`smoke_runtime_store_selector.py` proves:

- Unset env selects JSON and does not call the PostgreSQL connector.
- Explicit `VANTALINE_DATA_STORE=json` ignores `DATABASE_URL` and does not connect.
- Invalid datastore values fail config validation.
- `VANTALINE_DATA_STORE=postgres` without `DATABASE_URL` fails config validation.
- Explicit postgres uses the supplied connector exactly once.
- Connector failure raises a fail-closed error and does not return JSON.
- Raw password-bearing `DATABASE_URL` values are not included in error messages.
- Peer-auth URL redaction preserves non-secret routing fields.

## Gate Separation

### Gate 1: Code Deploy

Allowed only after review:

- Deploy selector module and smoke coverage.
- Keep HTTP runtime JSON-backed.
- Keep production `VANTALINE_DATA_STORE` unset.
- Do not create production PostgreSQL role/database.
- Do not import PostgreSQL data.
- Do not install `/etc/vantaline/postgres.env` or a systemd PostgreSQL drop-in.

### Gate 2: Online Import

Allowed only after a later manager gate:

- Create/verify PostgreSQL role and empty database.
- Generate final artifacts from the frozen JSON snapshot.
- Run rehearsal import/restore.
- Run production import and row-count/parity checks.
- Keep HTTP runtime on JSON until the env switch gate.

### Gate 3: Env Switch

Allowed only after a later manager gate:

- Install `/etc/vantaline/postgres.env`.
- Install `40-postgres-runtime.conf`.
- Restart service with `VANTALINE_DATA_STORE=postgres`.
- Run public, authenticated, reversible-write, row-count, journal, and runtime-residue smoke.

## Review Focus

- Selector import has no side effects.
- JSON default cannot initialize PostgreSQL.
- PostgreSQL selection is explicit and requires `DATABASE_URL`.
- PostgreSQL connection failure fails closed, with no silent JSON fallback.
- `DATABASE_URL` is redacted in exceptions and reports.
- Phase B does not change endpoint behavior.
