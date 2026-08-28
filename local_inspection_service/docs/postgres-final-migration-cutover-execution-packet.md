> **Status: Historical / Do not implement**
> Cutover evidence only; it is not the current operating procedure.
> Current replacement: [`docs/postgresql-runtime.md`](../../docs/postgresql-runtime.md).

# PostgreSQL Final Migration And Cutover Execution Packet

This packet is for task #17 review before a later manager execution gate. It
does not authorize or perform PostgreSQL connection, role/database/schema
mutation, service env/drop-in change, restart/reload, production import,
endpoint/runtime switch, or data cleanup.

Final acceptance target:

- PostgreSQL runtime is actually effective for the running service.
- Full smoke passes after cutover.
- Rollback remains available and tested at decision checkpoints.

## Current Accepted Starting Point

Known accepted state from prior gates:

- Gate7 revised partial-baseline code-only deploy was final accepted.
- Production service still defaults to JSON runtime.
- `VANTALINE_DATA_STORE` and `DATABASE_URL` must remain absent until the final
  manager gate opens.
- PostgreSQL dependency in the service venv was previously proven as
  `psycopg==3.3.4` and `psycopg-binary==3.3.4`, but must be rechecked live.
- The durable PostgreSQL role `vantaline` may already exist from the accepted
  Gate6 path; this packet still rechecks role state and treats any mismatch as
  fail-closed.
- A production PostgreSQL database named `vantaline` must not be reused unless
  live preflight proves it is empty and manager explicitly accepts that state.

Important prerequisite:

- Gate7 storage/selector code alone is not enough to prove PostgreSQL runtime.
  If the deployed HTTP runtime still writes directly to JSON, env switch can
  start successfully while business endpoints remain JSON-backed.
- Therefore this packet requires runtime-effectiveness proof from service
  behavior: authenticated HTTP write probes must be visible in PostgreSQL row
  checks, not only in service env or one-shot selector probes.
- If endpoint integration is not deployed or the write probes do not affect
  PostgreSQL, abort and roll back to JSON runtime. Do not accept a cutover based
  on code deployment or env presence alone.

## Manager Gate Boundary

Before the manager execution gate opens, none of the commands below may be run.

Closed before gate:

- no PostgreSQL connection;
- no role/database/schema mutation;
- no production import;
- no service env/drop-in change;
- no service restart/reload;
- no endpoint/runtime switch;
- no data cleanup;
- no reading or reusing live `auth.json` session tokens.

The future gate, if opened, must explicitly authorize one continuous execution
window containing the stages below. Each stage has a hard abort point.

Before asking for that gate, run the read-only readiness preflight. It does not
connect to PostgreSQL, restart services, read secret files, or mutate host
state; it only reports whether the production host has the required app paths,
scripts, docs, clean pre-cutover env, and local tooling.

## Shared Variables

Use these values in the execution window. Do not print secret-bearing
environment values.

```bash
set -euo pipefail

APP_ROOT=/opt/vantaline/app
TARGET_PY=/opt/vantaline/venv/bin/python
SERVICE=vantaline
DB_NAME=vantaline
DB_ROLE=vantaline
DB_URL='postgresql:///vantaline?host=/var/run/postgresql&user=vantaline'
CUTOVER_UTC="$(date -u +%Y%m%d%H%M%S)"
BACKUP_ROOT="/opt/vantaline/backups/postgres-cutover/$CUTOVER_UTC"
SCHEMA_PATH="$BACKUP_ROOT/vantaline_postgres_schema.sql"
IMPORT_DIR="$BACKUP_ROOT/vantaline_postgres_import"
REPORT_PATH="$BACKUP_ROOT/vantaline_postgres_report.json"
IMPORT_ROW_COUNT_REPORT="$BACKUP_ROOT/import-row-count-report.json"
IMPORT_ENGINE_REPORT="$BACKUP_ROOT/import-real-engine-report.json"
POSTGRES_BIN_DIR="${POSTGRES_BIN_DIR:-/usr/lib/postgresql/16/bin}"
```

This packet assumes local Unix-socket peer auth. If password auth is required,
pause and request a separate private secret-handling variant. Do not retrofit a
password URL into public reports.

## Reviewed Deploy Package Handoff

If the accepted code is not already present on `/opt/vantaline/app`, create a
non-secret deploy package from the reviewed source tree and transfer it through
the manager-approved artifact channel before Stage -1:

```bash
PYTHONPATH=. python3 local_inspection_service/scripts/postgres_cutover_deploy_package.py create \
  --app-root . \
  --package /tmp/vantaline-postgres-cutover-deploy-package.tar.gz \
  --manifest /tmp/vantaline-postgres-cutover-deploy-package-manifest.json \
  --report /tmp/vantaline-postgres-cutover-deploy-package-create-report.json
PYTHONPATH=. python3 local_inspection_service/scripts/postgres_cutover_deploy_package.py verify \
  --package /tmp/vantaline-postgres-cutover-deploy-package.tar.gz \
  --manifest /tmp/vantaline-postgres-cutover-deploy-package-manifest.json \
  --report /tmp/vantaline-postgres-cutover-deploy-package-verify-report.json
PYTHONPATH=. python3 local_inspection_service/scripts/postgres_cutover_deploy_package.py extract \
  --package /tmp/vantaline-postgres-cutover-deploy-package.tar.gz \
  --app-root /opt/vantaline/app \
  --manifest /tmp/vantaline-postgres-cutover-deploy-package-manifest.json \
  --backup-dir "/opt/vantaline/backups/postgres-cutover-code-deploy/$CUTOVER_UTC" \
  --report /tmp/vantaline-postgres-cutover-deploy-package-extract-report.json
python3 local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py
sha256sum /tmp/vantaline-postgres-cutover-deploy-package.tar.gz
```

The package contains only the artifact-manifest allowlist plus embedded
metadata. It excludes runtime data, reports, backups, env files, and credential
material. Installing the package on the target host is a code deploy action only;
it still does not authorize PostgreSQL connection, import, env switch, service
restart/reload, or final smoke.
The extract report must show `backup_performed=true`,
`artifact_manifest_verified_after_extract=true`, and a non-empty
`backup_manifest` before Stage -1 can continue. Its `manifest_sha256` must match
the artifact verification report's `manifest_sha256`; otherwise the final gate
must treat the code deploy and artifact verification as coming from different
reviewed packages.
If code deploy validation fails before PostgreSQL import/env switch, restore the
previous code state from the package backup:

```bash
PYTHONPATH=. python3 local_inspection_service/scripts/postgres_cutover_deploy_package.py restore \
  --app-root /opt/vantaline/app \
  --backup-dir "/opt/vantaline/backups/postgres-cutover-code-deploy/$CUTOVER_UTC" \
  --report /tmp/vantaline-postgres-cutover-deploy-package-restore-report.json
```

The restore report must show `restored=true` and a non-secret report. This is a
code-deploy rollback only; after PostgreSQL import/env switch, use the later
database/service rollback stages in this packet as well.

## Stage -1: Endpoint-Integration Gate Prerequisite

This is a hard prerequisite before any PostgreSQL catalog read, service stop,
production import, env/drop-in change, or restart.

The current Gate7 code-only state is known to be insufficient: the accepted
storage and selector modules can prove `build_runtime_repository()` works, but
they do not prove FastAPI endpoints are wired to the runtime repository. If this
stage fails, stop and submit a separate endpoint-integration code gate before
revisiting this migration/cutover packet.

The endpoint-integration gate must provide and deploy all of the following
before this final cutover packet can enter manager execution review:

- exact endpoint allowlist with method, path, repository method, read/write
  classification, transaction boundary, rollback evidence, and smoke coverage;
  the allowlist must include auth, runtime probe, `/api/accessories*`,
  `/api/image-jobs* and /api/image-job-candidates*`, `/api/ai/tasks*`,
  `/api/ai/tasks/*/auto-optimize*`, `/api/data-analysis/records*`,
  `/api/training/*`, `/api/pipeline/tasks*`, and
  `/api/pipeline/accessories*`;
- deployed code proof that `local_inspection_service/server.py` imports and
  uses the approved runtime repository facade for every allowlisted endpoint;
- default JSON parity smoke proving existing endpoint behavior is unchanged
  when `VANTALINE_DATA_STORE` is unset;
- explicit PostgreSQL-selected failure smoke proving repository errors are
  redacted, fail closed, and do not write through JSON as fallback;
- an executable full-smoke runner:
  `local_inspection_service/scripts/smoke_postgres_cutover_full.py`;
- non-secret deploy package tooling:
  `local_inspection_service/scripts/postgres_cutover_deploy_package.py` and
  `local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py`;
- non-secret endpoint-integration report:
  `local_inspection_service/docs/postgres-endpoint-integration-accepted.md`
  or an equivalent reviewed packet named by the manager gate.

Fail-closed pre-cutover proof:

```bash
cd "$APP_ROOT"

ENDPOINT_GATE_DOC=local_inspection_service/docs/postgres-endpoint-integration-accepted.md
ENDPOINT_SMOKE=local_inspection_service/scripts/smoke_postgres_cutover_full.py
ENDPOINT_PRECUTOVER_VALIDATOR=local_inspection_service/scripts/validate_postgres_precutover_report.py
ENDPOINT_REPORT_VALIDATOR=local_inspection_service/scripts/validate_postgres_full_smoke_report.py
MIGRATION_REPORT_VALIDATOR=local_inspection_service/scripts/validate_postgres_migration_report.py
IMPORT_ROW_COUNT_REPORTER=local_inspection_service/scripts/postgres_import_row_count_report.py
DATA_LAYER_MIGRATOR=local_inspection_service/scripts/migrate_json_to_sqlite.py
DATA_LAYER_MIGRATION_SMOKE=local_inspection_service/scripts/smoke_data_layer_migration.py
CUTOVER_READINESS=local_inspection_service/scripts/postgres_cutover_readiness.py
CUTOVER_MANIFEST=local_inspection_service/scripts/postgres_cutover_artifact_manifest.py
CUTOVER_DEPLOY_PACKAGE=local_inspection_service/scripts/postgres_cutover_deploy_package.py
CUTOVER_DEPLOY_PACKAGE_SMOKE=local_inspection_service/scripts/smoke_postgres_cutover_deploy_package.py
CUTOVER_GATE_REPORT=local_inspection_service/scripts/postgres_cutover_gate_report.py
ENDPOINT_SOURCE_CONTRACT=local_inspection_service/scripts/smoke_postgres_endpoint_source_contract.py
LOCAL_PREFLIGHT_SUITE=local_inspection_service/scripts/smoke_postgres_local_preflight_suite.py
LOCAL_PREFLIGHT_SUITE_VALIDATOR=local_inspection_service/scripts/validate_postgres_local_preflight_suite_report.py
SCHEMA_ENGINE_SMOKE=local_inspection_service/scripts/smoke_postgres_schema_real_engine.py
IMPORT_ENGINE_SMOKE=local_inspection_service/scripts/smoke_postgres_import_real_engine.py
SERVER_FILE=local_inspection_service/server.py
ENDPOINT_PREFLIGHT_REPORT="/tmp/vantaline_endpoint_integration_preflight_$CUTOVER_UTC.json"
CUTOVER_READINESS_REPORT="/tmp/vantaline_cutover_readiness_$CUTOVER_UTC.json"
LOCAL_PREFLIGHT_SUITE_REPORT="/tmp/vantaline_local_preflight_suite_$CUTOVER_UTC.json"
ARTIFACT_VERIFY_REPORT="/tmp/vantaline_cutover_artifacts_verify_$CUTOVER_UTC.json"
DEPLOY_PACKAGE_EXTRACT_REPORT="/tmp/vantaline-postgres-cutover-deploy-package-extract-report.json"

test -s "$ENDPOINT_GATE_DOC"
test -s "$ENDPOINT_SMOKE"
test -s "$ENDPOINT_PRECUTOVER_VALIDATOR"
test -s "$ENDPOINT_REPORT_VALIDATOR"
test -s "$MIGRATION_REPORT_VALIDATOR"
test -s "$IMPORT_ROW_COUNT_REPORTER"
test -s "$DATA_LAYER_MIGRATOR"
test -s "$DATA_LAYER_MIGRATION_SMOKE"
test -s "$CUTOVER_READINESS"
test -s "$CUTOVER_MANIFEST"
test -s "$CUTOVER_DEPLOY_PACKAGE"
test -s "$CUTOVER_DEPLOY_PACKAGE_SMOKE"
test -s "$CUTOVER_GATE_REPORT"
test -s "$ENDPOINT_SOURCE_CONTRACT"
test -s "$LOCAL_PREFLIGHT_SUITE"
test -s "$LOCAL_PREFLIGHT_SUITE_VALIDATOR"
test -s "$SCHEMA_ENGINE_SMOKE"
test -s "$IMPORT_ENGINE_SMOKE"
test -s "$SERVER_FILE"

grep -q 'build_runtime_repository' "$SERVER_FILE"
grep -q 'VANTALINE_DATA_STORE' "$SERVER_FILE"
grep -q 'runtime repository' "$ENDPOINT_GATE_DOC"
grep -q 'PostgreSQL-visible write evidence' "$ENDPOINT_GATE_DOC"

if [ -n "${REVIEWED_ARTIFACT_MANIFEST:-}" ]; then
  PYTHONPATH="$APP_ROOT" "$TARGET_PY" "$CUTOVER_MANIFEST" verify \
    --app-root "$APP_ROOT" \
    --manifest "$REVIEWED_ARTIFACT_MANIFEST" \
    --report "$ARTIFACT_VERIFY_REPORT"
else
  ARTIFACT_MANIFEST="/tmp/vantaline_cutover_artifacts_$CUTOVER_UTC.json"
  PYTHONPATH="$APP_ROOT" "$TARGET_PY" "$CUTOVER_MANIFEST" create \
    --app-root "$APP_ROOT" \
    --manifest "$ARTIFACT_MANIFEST"
  PYTHONPATH="$APP_ROOT" "$TARGET_PY" "$CUTOVER_MANIFEST" verify \
    --app-root "$APP_ROOT" \
    --manifest "$ARTIFACT_MANIFEST" \
    --report "$ARTIFACT_VERIFY_REPORT"
fi

PYTHONPATH="$APP_ROOT" "$TARGET_PY" "$CUTOVER_READINESS" \
  --app-root "$APP_ROOT" \
  --target-py "$TARGET_PY" \
  --postgres-env-file /etc/vantaline/postgres.env \
  --service "$SERVICE" \
  --report "$CUTOVER_READINESS_REPORT"

SUITE_ENGINE_ARGS=()
if [ -n "${POSTGRES_BIN_DIR:-}" ]; then
  SUITE_ENGINE_ARGS+=(--postgres-bin-dir "$POSTGRES_BIN_DIR")
fi
if [ -n "${POSTGRES_LIBRARY_DIR:-}" ]; then
  SUITE_ENGINE_ARGS+=(--library-dir "$POSTGRES_LIBRARY_DIR")
fi
PYTHONPATH="$APP_ROOT" "$TARGET_PY" "$LOCAL_PREFLIGHT_SUITE" "${SUITE_ENGINE_ARGS[@]}" \
  --require-real-engine \
  --report "$LOCAL_PREFLIGHT_SUITE_REPORT"

PYTHONPATH="$APP_ROOT" "$TARGET_PY" "$LOCAL_PREFLIGHT_SUITE_VALIDATOR" \
  --report "$LOCAL_PREFLIGHT_SUITE_REPORT"

PYTHONPATH="$APP_ROOT" "$TARGET_PY" "$ENDPOINT_SMOKE" \
  --mode deployed-precutover \
  --base-url http://127.0.0.1:8765 \
  --expect-store json \
  --require-no-postgres-service-env \
  --report "$ENDPOINT_PREFLIGHT_REPORT"

"$TARGET_PY" "$ENDPOINT_PRECUTOVER_VALIDATOR" \
  --report "$ENDPOINT_PREFLIGHT_REPORT" \
  --expected-mode deployed-precutover

test -x "$POSTGRES_BIN_DIR/initdb"
test -x "$POSTGRES_BIN_DIR/postgres"
SCHEMA_ENGINE_ARGS=(--postgres-bin-dir "$POSTGRES_BIN_DIR")
if [ -n "${POSTGRES_LIBRARY_DIR:-}" ]; then
  SCHEMA_ENGINE_ARGS+=(--library-dir "$POSTGRES_LIBRARY_DIR")
fi
PYTHONPATH="$APP_ROOT" "$TARGET_PY" "$SCHEMA_ENGINE_SMOKE" "${SCHEMA_ENGINE_ARGS[@]}"
echo "endpoint_integration_preflight_pass=true"
```

The local preflight suite is socket-free and reports
`production_cutover_proof=false`; it is a bundle of local contract smokes only
and cannot satisfy final production acceptance by itself. In this final packet,
`--require-real-engine` is mandatory because Stage -1 must prove the reviewed
PostgreSQL DDL/import artifacts through real PostgreSQL single-user binaries
before any destructive manager gate.
The suite report must also pass
`validate_postgres_local_preflight_suite_report.py` so the final gate only
consumes a report with the required local smoke names and real-engine evidence.
Required suite results include `postgres endpoint source contract`, which
statically verifies the reviewed `server.py` runtime repository seam, including
helper-level `runtime_postgres_repository_or_none()` coverage for the main
business storage helpers, before the HTTP full-smoke gate runs.

The `POSTGRES_BIN_DIR` branch is a non-network, non-socket DDL engine smoke. It
proves PostgreSQL can run generated schema DDL on this host; it does not prove
the final production CSV artifacts, service runtime, repository writes,
authenticated HTTP behavior, or cutover.

If a manager provides `REVIEWED_ARTIFACT_MANIFEST`, that manifest is the
preferred code-on-disk proof because it pins the production tree to a previously
reviewed artifact set. If it is absent, the local create/verify branch only
records a non-secret audit manifest for the current production tree; it does not
replace review approval or prove PostgreSQL cutover success.

If the production server has not deployed the accepted endpoint-integration
packet, this stage must fail before any destructive work. That failure is
correct and must be reported as:

```text
endpoint_integration_preflight_pass=false
next_required_action=separate_endpoint_integration_code_gate
```

## Stage 0: Fail-Closed Live Preflight

Run only after the manager gate opens. This stage is read-only except for normal
PostgreSQL catalog reads.

```bash
cd "$APP_ROOT"

hostname
systemctl is-active "$SERVICE"
systemctl is-active postgresql
test -x "$TARGET_PY"
"$TARGET_PY" --version
"$TARGET_PY" - <<'PY'
import importlib.metadata as metadata
import psycopg

expected = "3.3.4"
versions = {
    "psycopg_import_version": psycopg.__version__,
    "dist_psycopg": metadata.version("psycopg"),
    "dist_psycopg_binary": metadata.version("psycopg-binary"),
}
for key, value in versions.items():
    print(f"{key}={value}")
    if value != expected:
        raise SystemExit(f"{key}_mismatch expected={expected} actual={value}")
print("psycopg_version_ok=true")
PY

SERVICE_WORKING_DIRECTORY="$(systemctl show "$SERVICE" -p WorkingDirectory --value --no-pager)"
SERVICE_EXEC_START="$(systemctl show "$SERVICE" -p ExecStart --value --no-pager)"
SERVICE_USER="$(systemctl show "$SERVICE" -p User --value --no-pager)"
SERVICE_GROUP="$(systemctl show "$SERVICE" -p Group --value --no-pager)"
test "$SERVICE_WORKING_DIRECTORY" = "$APP_ROOT"
test "$SERVICE_USER" = "vantaline"
test "$SERVICE_GROUP" = "vantaline"
case "$SERVICE_EXEC_START" in
  *"$TARGET_PY"*) echo 'service_exec_start_contains_target_python=true' ;;
  *) echo 'service_exec_start_contains_target_python=false'; exit 1 ;;
esac
echo 'service_binding_preflight_pass=true'

if systemctl show "$SERVICE" -p Environment --value --no-pager | tr ' ' '\n' | grep -q '^VANTALINE_DATA_STORE='; then
  echo 'VANTALINE_DATA_STORE_present_before=true'
  exit 1
else
  echo 'VANTALINE_DATA_STORE_present_before=false'
fi
if systemctl show "$SERVICE" -p Environment --value --no-pager | tr ' ' '\n' | grep -q '^DATABASE_URL='; then
  echo 'DATABASE_URL_present_before=true'
  exit 1
else
  echo 'DATABASE_URL_present_before=false'
fi
if test -f /etc/vantaline/postgres.env; then
  echo 'postgres_env_file_present_before=true'
  exit 1
else
  echo 'postgres_env_file_present_before=false'
fi
if systemctl show "$SERVICE" -p EnvironmentFiles --value --no-pager | grep -q '/etc/vantaline/postgres.env'; then
  echo 'postgres_env_file_referenced_before=true'
  exit 1
else
  echo 'postgres_env_file_referenced_before=false'
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 -tAc 'select 1' postgres
PG_LISTEN="$(sudo -u postgres psql -v ON_ERROR_STOP=1 -tAc "show listen_addresses" postgres)"
printf 'pg_listen_addresses=%s\n' "$PG_LISTEN"
case "$PG_LISTEN" in
  ''|'localhost'|'127.0.0.1'|'::1') echo 'postgres_local_only=true' ;;
  *) echo 'postgres_local_only=false'; exit 1 ;;
esac

ROLE_STATE="$(sudo -u postgres psql -v ON_ERROR_STOP=1 -F '|' -At postgres <<'SQL'
SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication
FROM pg_roles
WHERE rolname = 'vantaline';
SQL
)"
if [ -n "$ROLE_STATE" ]; then
  IFS='|' read -r ROLE_LOGIN ROLE_SUPER ROLE_CREATEDB ROLE_CREATEROLE ROLE_REPLICATION <<EOF
$ROLE_STATE
EOF
  test "$ROLE_LOGIN" = "t"
  test "$ROLE_SUPER" = "f"
  test "$ROLE_CREATEDB" = "f"
  test "$ROLE_CREATEROLE" = "f"
  test "$ROLE_REPLICATION" = "f"
  echo 'role_preexisted=t'
  echo 'role_privileges_preflight_ok=true'
else
  echo 'role_preexisted=f'
  echo 'role_privileges_preflight_ok=pending_manager_approved_creation'
fi

PROD_DB_EXISTS_PREFLIGHT="$(sudo -u postgres psql -v ON_ERROR_STOP=1 -At \
  -c "select exists (select 1 from pg_database where datname = 'vantaline')" \
  postgres)"
printf 'prod_db_preexisted_preflight=%s\n' "$PROD_DB_EXISTS_PREFLIGHT"
if [ "$PROD_DB_EXISTS_PREFLIGHT" = "t" ]; then
  PROD_DB_OWNER="$(sudo -u postgres psql -v ON_ERROR_STOP=1 -At \
    -c "select pg_get_userbyid(datdba) from pg_database where datname = 'vantaline'" \
    postgres)"
  test "$PROD_DB_OWNER" = "vantaline"
  PROD_TABLE_COUNT="$(sudo -u vantaline psql "$DB_URL" -v ON_ERROR_STOP=1 -tAc \
    "select count(*) from information_schema.tables where table_schema='vantaline'")"
  printf 'prod_db_existing_table_count_preflight=%s\n' "$PROD_TABLE_COUNT"
  test "${PROD_TABLE_COUNT:-0}" = "0"
  if [ "${MANAGER_PREACCEPT_EXISTING_EMPTY_DB:-false}" != "true" ]; then
    echo 'prod_db_existing_empty_requires_manager_acceptance=true'
    exit 1
  fi
  echo 'prod_db_existing_empty_manager_preaccepted=true'
fi
```

The `MANAGER_PREACCEPT_EXISTING_EMPTY_DB=true` branch is valid only if the
future manager execution gate explicitly names and accepts reuse of an existing
empty production database. Without that explicit pre-acceptance, an existing
database stops the run before import:

```text
prod_db_existing_empty_requires_manager_acceptance=true
next_required_action=manager_decision_on_existing_empty_db
```

Abort if:

- service or PostgreSQL is inactive;
- the service is not bound to `/opt/vantaline/app` and
  `/opt/vantaline/venv/bin/python`;
- PostgreSQL is not local-only;
- `VANTALINE_DATA_STORE`, `DATABASE_URL`, or `/etc/vantaline/postgres.env`
  already exists before the gate;
- existing role `vantaline` has any attribute outside LOGIN + NOSUPERUSER +
  NOCREATEDB + NOCREATEROLE + NOREPLICATION;
- `psycopg` or `psycopg-binary` is not exactly `3.3.4`;
- production database `vantaline` exists and either is not empty or was not
  explicitly pre-accepted by the manager execution gate.

## Stage 1: Gate6 Retry / Disposable PostgreSQL Schema Smoke

This stage proves the deployed selector/repository can connect to PostgreSQL and
load the reviewed schema in a disposable database. It must not change the
running service env.

```bash
SMOKE_DB="vantaline_smoke_$(date -u +%Y%m%d%H%M%S)"
SMOKE_URL="postgresql:///$SMOKE_DB?host=/var/run/postgresql&user=vantaline"
SMOKE_SCHEMA="/tmp/${SMOKE_DB}_schema.sql"
SMOKE_DB_CREATED=false

case "$SMOKE_DB" in
  vantaline_smoke_[0-9]*) ;;
  *) echo "unsafe_smoke_db_name=$SMOKE_DB"; exit 1 ;;
esac

cleanup_smoke_db() {
  cleanup_failed=false
  if [ "${SMOKE_DB_CREATED:-false}" = "true" ]; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 postgres \
      -tAc "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$SMOKE_DB' and pid <> pg_backend_pid()" >/dev/null || cleanup_failed=true
    sudo -u postgres dropdb --force --if-exists "$SMOKE_DB" || cleanup_failed=true
    if sudo -u postgres psql -v ON_ERROR_STOP=1 -tAc "select 1 from pg_database where datname = '$SMOKE_DB'" postgres | grep -q 1; then
      echo 'smoke_db_present_after_cleanup=true'
      cleanup_failed=true
    else
      echo 'smoke_db_present_after_cleanup=false'
    fi
  fi
  sudo rm -f "$SMOKE_SCHEMA" || cleanup_failed=true
  if test -e "$SMOKE_SCHEMA"; then
    echo 'temp_schema_file_present_after_cleanup=true'
    cleanup_failed=true
  else
    echo 'temp_schema_file_present_after_cleanup=false'
  fi
  if [ "$cleanup_failed" = "true" ]; then
    echo 'smoke_cleanup_failed=true'
    return 1
  fi
  echo 'smoke_cleanup_failed=false'
}
trap cleanup_smoke_db EXIT

ROLE_PREEXISTED="$(sudo -u postgres psql -v ON_ERROR_STOP=1 -At \
  -c "select exists (select 1 from pg_roles where rolname = 'vantaline')" \
  postgres)"
printf 'role_preexisted=%s\n' "$ROLE_PREEXISTED"

sudo -u postgres psql -v ON_ERROR_STOP=1 postgres <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vantaline') THEN
    CREATE ROLE vantaline
      LOGIN
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOREPLICATION;
  END IF;
END
$$;
SQL

if [ "$ROLE_PREEXISTED" = "f" ]; then
  echo 'role_created_by_gate=true'
else
  echo 'role_created_by_gate=false'
fi
echo 'role_retained=true'
echo 'role_retained_reason=approved_future_peer_auth_role'

ROLE_STATE_AFTER="$(sudo -u postgres psql -v ON_ERROR_STOP=1 -F '|' -At postgres <<'SQL'
SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication
FROM pg_roles
WHERE rolname = 'vantaline';
SQL
)"
IFS='|' read -r ROLE_LOGIN ROLE_SUPER ROLE_CREATEDB ROLE_CREATEROLE ROLE_REPLICATION <<EOF
$ROLE_STATE_AFTER
EOF
test "$ROLE_LOGIN" = "t"
test "$ROLE_SUPER" = "f"
test "$ROLE_CREATEDB" = "f"
test "$ROLE_CREATEROLE" = "f"
test "$ROLE_REPLICATION" = "f"
echo 'role_privileges_after_prep_ok=true'

sudo -u postgres createdb --owner=vantaline "$SMOKE_DB"
SMOKE_DB_CREATED=true
sudo -u vantaline psql "$SMOKE_URL" \
  -v ON_ERROR_STOP=1 \
  -tAc 'select current_user, current_database()'

cd "$APP_ROOT"
sudo -u vantaline PYTHONPATH="$APP_ROOT" "$TARGET_PY" - <<'PY' > "$SMOKE_SCHEMA"
from local_inspection_service.storage.postgres_schema import postgres_ddl
print(postgres_ddl())
PY
sudo -u vantaline psql "$SMOKE_URL" -v ON_ERROR_STOP=1 -f "$SMOKE_SCHEMA"

sudo -u vantaline VANTALINE_DATA_STORE=postgres DATABASE_URL="$SMOKE_URL" \
  PYTHONPATH="$APP_ROOT" "$TARGET_PY" - <<'PY'
from local_inspection_service.storage.runtime_selector import build_runtime_repository
selection = build_runtime_repository()
print(f"selected_store={selection.store}")
print(f"repository_kind={selection.repository.kind}")
counts = selection.repository.count_rows(("schema_migrations",))
print(f"schema_migrations_count={counts.get('schema_migrations', 0)}")
PY

cleanup_smoke_db
SMOKE_DB_CREATED=false
trap - EXIT

systemctl is-active "$SERVICE"
if systemctl show "$SERVICE" -p Environment --value --no-pager | tr ' ' '\n' | grep -q '^VANTALINE_DATA_STORE='; then
  echo 'VANTALINE_DATA_STORE_present_after_gate6=true'
  exit 1
else
  echo 'VANTALINE_DATA_STORE_present_after_gate6=false'
fi
if systemctl show "$SERVICE" -p Environment --value --no-pager | tr ' ' '\n' | grep -q '^DATABASE_URL='; then
  echo 'DATABASE_URL_present_after_gate6=true'
  exit 1
else
  echo 'DATABASE_URL_present_after_gate6=false'
fi
```

Expected:

- `selected_store=postgres`;
- `repository_kind=postgres`;
- `schema_migrations_count=1`;
- disposable DB and temp schema file are removed;
- service remains active;
- service env still has no `VANTALINE_DATA_STORE` or `DATABASE_URL`.

Abort if cleanup fails. Do not proceed to production import with disposable DB
residue.

## Stage 2: Stop Service And Create Backups

This is the write-freeze point. It stops the app before the final JSON snapshot.
Systemd reload is not required here.

```bash
sudo systemctl stop "$SERVICE"
if systemctl is-active "$SERVICE" >/dev/null; then
  echo 'service_stop_failed=true'
  exit 1
fi

sudo install -d -m 0750 -o root -g vantaline "$BACKUP_ROOT"
sudo install -d -m 0750 -o root -g vantaline "$BACKUP_ROOT/service"

cd "$APP_ROOT"
sudo tar -C "$APP_ROOT" \
  --exclude='local_inspection_service/data' \
  --exclude='local_inspection_service/*.env' \
  --exclude='*.local.json' \
  --exclude='*.local.env' \
  --exclude='runtime_secrets.local.env*' \
  --exclude='ai_config.local.json*' \
  --exclude='agent_config.local.json*' \
  --exclude='*.sqlite3*' \
  -czf "$BACKUP_ROOT/app-code.tgz" .

sudo tar -C "$APP_ROOT/local_inspection_service/data" \
  -czf "$BACKUP_ROOT/data-json.tgz" .
sudo chown root:vantaline "$BACKUP_ROOT/app-code.tgz" "$BACKUP_ROOT/data-json.tgz"
sudo chmod 0640 "$BACKUP_ROOT/app-code.tgz" "$BACKUP_ROOT/data-json.tgz"

systemctl show "$SERVICE" \
  -p FragmentPath -p DropInPaths -p WorkingDirectory -p User -p Group \
  --no-pager | sudo tee "$BACKUP_ROOT/service/systemd-service-nonsecret.txt" >/dev/null
sudo cp -a /etc/systemd/system/vantaline.service.d "$BACKUP_ROOT/service/dropins.before" 2>/dev/null || true

test -s "$BACKUP_ROOT/app-code.tgz"
test -s "$BACKUP_ROOT/data-json.tgz"
echo "backup_root=$BACKUP_ROOT"
echo 'app_code_backup_pass=true'
echo 'data_json_backup_pass=true'
```

Restricted sensitive artifacts:

- `data-json.tgz`;
- PostgreSQL CSV import artifacts;
- PostgreSQL dumps;
- any future password-auth env file.

Do not attach these artifacts to public Slock.

## Stage 3: Generate Final Migration Artifacts

Artifacts are generated from the stopped service snapshot.

```bash
cd "$APP_ROOT"
sudo -u vantaline PYTHONPATH="$APP_ROOT" "$TARGET_PY" \
  local_inspection_service/scripts/prepare_json_to_postgres.py \
  --source "$APP_ROOT/local_inspection_service" \
  --ddl "$SCHEMA_PATH" \
  --out-dir "$IMPORT_DIR" \
  --report "$REPORT_PATH" \
  --allow-legacy-id-repair

sudo chown -R root:vantaline "$SCHEMA_PATH" "$IMPORT_DIR" "$REPORT_PATH"
sudo find "$IMPORT_DIR" -type d -exec chmod 0750 {} +
sudo find "$IMPORT_DIR" -type f -exec chmod 0640 {} +
sudo chmod 0640 "$SCHEMA_PATH" "$REPORT_PATH"

sudo -u vantaline "$TARGET_PY" - "$REPORT_PATH" "$IMPORT_DIR" <<'PY'
import json
import hashlib
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
import_dir = Path(sys.argv[2])
ddl_path = Path(report["ddl_path"])
assert report["target"] == "postgresql"
assert report["source_error_count"] == 0, report["source_error_count"]
assert len(report["blocking_errors"]) == 0, len(report["blocking_errors"])
assert report["cutover_allowed"] is True
assert report["ddl_sha256"] == hashlib.sha256(ddl_path.read_bytes()).hexdigest()
assert report["postgres_import_artifacts"]["emitted"] is True
assert "schema_migrations" not in report["postgres_import_artifacts"].get("csv_files", {})
assert not (import_dir / "tables" / "schema_migrations.csv").exists()
print(f"report_schema_version={report['schema_version']}")
print(f"source_error_count={report['source_error_count']}")
print(f"blocking_error_count={len(report['blocking_errors'])}")
print("cutover_allowed=true")
print("import_artifact_emitted=true")
print(f"ddl_sha256={report['ddl_sha256']}")
print("schema_migrations_csv_exists=false")
print("row_counts=" + json.dumps(report["row_counts"], sort_keys=True, ensure_ascii=False))
PY

"$TARGET_PY" local_inspection_service/scripts/validate_postgres_migration_report.py \
  --report "$REPORT_PATH"

test -x "$POSTGRES_BIN_DIR/initdb"
test -x "$POSTGRES_BIN_DIR/postgres"
SCHEMA_ENGINE_ARGS=(--postgres-bin-dir "$POSTGRES_BIN_DIR")
if [ -n "${POSTGRES_LIBRARY_DIR:-}" ]; then
  SCHEMA_ENGINE_ARGS+=(--library-dir "$POSTGRES_LIBRARY_DIR")
fi
sudo -u vantaline PYTHONPATH="$APP_ROOT" "$TARGET_PY" "$IMPORT_ENGINE_SMOKE" "${SCHEMA_ENGINE_ARGS[@]}" \
  --ddl "$SCHEMA_PATH" \
  --migration-report "$REPORT_PATH" \
  --report "$IMPORT_ENGINE_REPORT"
```

Abort if:

- `source_error_count` is not zero;
- `blocking_error_count` is not zero;
- `cutover_allowed` is not true;
- import artifacts are not emitted;
- `schema_migrations.csv` exists;
- report/log redaction scan finds raw session tokens, provider keys, bearer
  tokens, password verifier values in public report text, env file contents, or
  full secret-bearing URLs.

The row-count values are generated from the frozen snapshot. Do not hardcode old
counts as acceptance criteria; compare PostgreSQL counts to this final report.

## Stage 4: Backup/Restore Rehearsal

Use disposable rehearsal databases before touching the production database.

```bash
REHEARSAL_DB="vantaline_import_rehearsal_$CUTOVER_UTC"
RESTORE_DB="vantaline_restore_rehearsal_$CUTOVER_UTC"
REHEARSAL_URL="postgresql:///$REHEARSAL_DB?host=/var/run/postgresql&user=vantaline"
RESTORE_URL="postgresql:///$RESTORE_DB?host=/var/run/postgresql&user=vantaline"
REHEARSAL_DB_CREATED=false
RESTORE_DB_CREATED=false

cleanup_rehearsal_dbs() {
  cleanup_failed=false
  for db in "$REHEARSAL_DB" "$RESTORE_DB"; do
    sudo -u postgres psql -v ON_ERROR_STOP=1 postgres \
      -tAc "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$db' and pid <> pg_backend_pid()" >/dev/null || cleanup_failed=true
    sudo -u postgres dropdb --force --if-exists "$db" || cleanup_failed=true
    if sudo -u postgres psql -v ON_ERROR_STOP=1 -tAc "select 1 from pg_database where datname = '$db'" postgres | grep -q 1; then
      printf 'rehearsal_db_present_after_cleanup=true db=%s\n' "$db"
      cleanup_failed=true
    else
      printf 'rehearsal_db_present_after_cleanup=false db=%s\n' "$db"
    fi
  done
  if [ "$cleanup_failed" = "true" ]; then
    echo 'rehearsal_cleanup_failed=true'
    return 1
  fi
  echo 'rehearsal_cleanup_failed=false'
}
trap cleanup_rehearsal_dbs EXIT

sudo -u postgres dropdb --force --if-exists "$REHEARSAL_DB"
sudo -u postgres createdb --owner=vantaline "$REHEARSAL_DB"
REHEARSAL_DB_CREATED=true
sudo -u vantaline psql "$REHEARSAL_URL" -v ON_ERROR_STOP=1 -f "$SCHEMA_PATH"
sudo -u vantaline bash -c 'cd "$1" && psql "$2" -v ON_ERROR_STOP=1 -f load_postgres.sql' _ \
  "$IMPORT_DIR" "$REHEARSAL_URL"

sudo -u vantaline pg_dump --format=custom \
  --file="$BACKUP_ROOT/vantaline.rehearsal.postgres.dump" \
  "$REHEARSAL_URL"
sudo chown root:vantaline "$BACKUP_ROOT/vantaline.rehearsal.postgres.dump"
sudo chmod 0640 "$BACKUP_ROOT/vantaline.rehearsal.postgres.dump"

sudo -u postgres dropdb --force --if-exists "$RESTORE_DB"
sudo -u postgres createdb --owner=vantaline "$RESTORE_DB"
RESTORE_DB_CREATED=true
sudo -u vantaline pg_restore \
  --clean \
  --if-exists \
  --dbname="$RESTORE_URL" \
  "$BACKUP_ROOT/vantaline.rehearsal.postgres.dump"

sudo -u vantaline psql "$RESTORE_URL" -v ON_ERROR_STOP=1 -tAc \
  "select count(*) from vantaline.schema_migrations"
sudo -u vantaline psql "$RESTORE_URL" -v ON_ERROR_STOP=1 -tAc \
  "select count(*) from vantaline.accessories"

echo 'restore_rehearsal_pass=true'
if cleanup_rehearsal_dbs; then
  trap - EXIT
else
  trap - EXIT
  exit 1
fi
```

Abort before production import if import, dump, restore, or sanity counts fail.

If the manager explicitly wants to retain rehearsal DBs for forensics, the
future execution gate must say so before the run and set a separate
manager-approved retention branch. Without that branch, rehearsal and restore
rehearsal DBs must report residue-free cleanup before production import.

## Stage 5: Production Schema And Data Migration

The production database must be empty before import. Never drop an existing
production database implicitly.

```bash
PROD_DB_EXISTS="$(sudo -u postgres psql -v ON_ERROR_STOP=1 -At \
  -c "select exists (select 1 from pg_database where datname = 'vantaline')" \
  postgres)"
printf 'prod_db_preexisted=%s\n' "$PROD_DB_EXISTS"

if [ "$PROD_DB_EXISTS" = "f" ]; then
  sudo -u postgres createdb --owner=vantaline vantaline
  echo 'prod_db_created_by_gate=true'
else
  TABLE_COUNT="$(sudo -u vantaline psql "$DB_URL" -v ON_ERROR_STOP=1 -tAc \
    "select count(*) from information_schema.tables where table_schema='vantaline'")"
  printf 'prod_db_existing_table_count=%s\n' "$TABLE_COUNT"
  test "${TABLE_COUNT:-0}" = "0"
  if [ "${MANAGER_PREACCEPT_EXISTING_EMPTY_DB:-false}" != "true" ]; then
    echo 'prod_db_existing_empty_requires_manager_acceptance=true'
    exit 1
  fi
  echo 'prod_db_existing_empty_manager_preaccepted=true'
  echo 'prod_db_created_by_gate=false'
fi

sudo -u vantaline psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$SCHEMA_PATH"
sudo -u vantaline bash -c 'cd "$1" && psql "$2" -v ON_ERROR_STOP=1 -f load_postgres.sql' _ \
  "$IMPORT_DIR" "$DB_URL"

sudo -u vantaline pg_dump --format=custom \
  --file="$BACKUP_ROOT/vantaline.postgres.dump" \
  "$DB_URL"
sudo chown root:vantaline "$BACKUP_ROOT/vantaline.postgres.dump"
sudo chmod 0640 "$BACKUP_ROOT/vantaline.postgres.dump"
```

Verify row counts against the final migration report.

```bash
sudo -u vantaline "$TARGET_PY" - "$REPORT_PATH" "$DB_URL" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
db_url = sys.argv[2]
expected = report["row_counts"]
for table, expected_count in sorted(expected.items()):
    sql = f"select count(*) from vantaline.{table}"
    actual_text = subprocess.check_output(
        ["psql", db_url, "-v", "ON_ERROR_STOP=1", "-tAc", sql],
        text=True,
    ).strip()
    actual = int(actual_text)
    if actual != int(expected_count):
        raise SystemExit(f"row_count_mismatch table={table} expected={expected_count} actual={actual}")
print("row_count_parity_pass=true")
PY

sudo -u vantaline "$TARGET_PY" \
  local_inspection_service/scripts/postgres_import_row_count_report.py \
  --migration-report "$REPORT_PATH" \
  --db-url "$DB_URL" \
  --report "$IMPORT_ROW_COUNT_REPORT"
```

Abort before env switch if:

- production DB was non-empty without explicit manager acceptance;
- schema load or import fails;
- dump fails;
- any row count differs from the report;
- `schema_migrations` is not exactly the DDL-owned seeded row expected by the
  accepted schema.

## Stage 6: Runtime Env/Drop-In Switch

Service was stopped in Stage 2. A systemd daemon reload is required because a
drop-in is created. A service start is required to apply the new env. A reload
alone is not sufficient for env changes.

```bash
sudo install -d -m 0750 -o root -g vantaline /etc/vantaline
sudo tee /etc/vantaline/postgres.env >/dev/null <<'EOF'
VANTALINE_DATA_STORE=postgres
DATABASE_URL=postgresql:///vantaline?host=/var/run/postgresql&user=vantaline
EOF
sudo chown root:vantaline /etc/vantaline/postgres.env
sudo chmod 0640 /etc/vantaline/postgres.env

sudo install -d /etc/systemd/system/vantaline.service.d
sudo tee /etc/systemd/system/vantaline.service.d/40-postgres-runtime.conf >/dev/null <<'EOF'
[Service]
EnvironmentFile=/etc/vantaline/postgres.env
EOF

sudo systemctl daemon-reload
sudo systemctl start "$SERVICE"
systemctl is-active "$SERVICE"
```

Post-start non-secret env proof:

```bash
MAIN_PID="$(systemctl show "$SERVICE" -p MainPID --value --no-pager)"
test "${MAIN_PID:-0}" != "0"
sudo test -r "/proc/$MAIN_PID/environ"
sudo sh -c 'tr "\0" "\n" < "/proc/$1/environ"' sh "$MAIN_PID" | grep -qx 'VANTALINE_DATA_STORE=postgres'
sudo sh -c 'tr "\0" "\n" < "/proc/$1/environ"' sh "$MAIN_PID" | grep -q '^DATABASE_URL='
systemctl show "$SERVICE" -p EnvironmentFiles --value --no-pager | tr ' ' '\n' | grep -q '^/etc/vantaline/postgres.env'
echo 'service_env_postgres_present=true'
echo 'postgres_env_file_referenced=true'
```

Do not print raw `/proc/$MAIN_PID/environ` or `/etc/vantaline/postgres.env`.

Service-local repository proof without printing the database URL:

```bash
sudo -u vantaline bash -c '
set -euo pipefail
set -a
. /etc/vantaline/postgres.env
set +a
PYTHONPATH=/opt/vantaline/app /opt/vantaline/venv/bin/python - <<'"'"'PY'"'"'
from local_inspection_service.storage.runtime_selector import build_runtime_repository
selection = build_runtime_repository()
print(f"selected_store={selection.store}")
print(f"repository_kind={selection.repository.kind}")
counts = selection.repository.count_rows(("schema_migrations", "accessories", "auth_sessions"))
print("postgres_repository_count_probe_pass=true")
print("schema_migrations_count=" + str(counts.get("schema_migrations", 0)))
PY
'
```

Expected:

- `selected_store=postgres`;
- `repository_kind=postgres`;
- count probe succeeds.

This proof is necessary but not sufficient. Full runtime effectiveness still
requires HTTP smoke plus PostgreSQL-visible write evidence.

## Stage 7: Full Smoke And PostgreSQL Runtime Effectiveness Proof

Smoke executor requirements:

- Use a private/authorized admin test credential. Do not read or reuse live
  `auth.json` session tokens.
- The credential handoff path is a root-created, restricted runtime file:
  `/run/vantaline-smoke/admin.env`, mode `0640`, owner `root:vantaline`, with
  `VANTALINE_SMOKE_USERNAME` and `VANTALINE_SMOKE_PASSWORD`.
- Do not paste credentials into public channels, shell history, reports, or
  logs. Delete the runtime credential file after smoke.
- If no valid credential path exists, rollback to JSON or stop at manager
  decision before claiming final acceptance.
- The executable runner is mandatory:
  `local_inspection_service/scripts/smoke_postgres_cutover_full.py`.

Required smoke command:

```bash
CUTOVER_START_ISO="$(date -u -d "@$(date +%s)" +%Y-%m-%dT%H:%M:%SZ)"
SMOKE_PREFIX="pg-cutover-$CUTOVER_UTC"
SMOKE_REPORT="$BACKUP_ROOT/full-smoke-report.json"
FINAL_GATE_REPORT="$BACKUP_ROOT/cutover-gate-report.json"
SMOKE_CREDENTIAL_FILE=/run/vantaline-smoke/admin.env
READ_ONLY_WRITE_WAIVER_ID="${READ_ONLY_WRITE_WAIVER_ID:?manager-approved read-only write waiver id required}"
DATA_ANALYSIS_WRITE_FLAG="${RUN_DATA_ANALYSIS_WRITE:-0}"

sudo test -s "$SMOKE_CREDENTIAL_FILE"
sudo stat -c '%U:%G %a %n' "$SMOKE_CREDENTIAL_FILE" | grep -qx 'root:vantaline 640 /run/vantaline-smoke/admin.env'

cleanup_smoke_credential() {
  sudo rm -f "$SMOKE_CREDENTIAL_FILE"
}
trap cleanup_smoke_credential EXIT

sudo -u vantaline bash -c '
set -euo pipefail
set -a
. /etc/vantaline/postgres.env
. /run/vantaline-smoke/admin.env
set +a
DATA_ANALYSIS_WRITE_ARGS=()
if [ "${4:-0}" = "1" ]; then
  DATA_ANALYSIS_WRITE_ARGS+=(--run-data-analysis-write)
fi
PYTHONPATH=/opt/vantaline/app /opt/vantaline/venv/bin/python \
  local_inspection_service/scripts/smoke_postgres_cutover_full.py \
  --base-url http://127.0.0.1:8765 \
  --db-url-env DATABASE_URL \
  --username-env VANTALINE_SMOKE_USERNAME \
  --password-env VANTALINE_SMOKE_PASSWORD \
  --test-prefix "$1" \
  --concurrent-accounts 10 \
  --report "$2" \
  --expect-store postgres \
  --require-postgres-visible-writes \
  --read-only-write-waiver-id "$3" \
  "${DATA_ANALYSIS_WRITE_ARGS[@]}" \
  --cleanup
PYTHONPATH=/opt/vantaline/app /opt/vantaline/venv/bin/python \
  local_inspection_service/scripts/validate_postgres_full_smoke_report.py \
  --report "$2" \
  --expected-mode deployed-postgres \
  --expected-concurrent-accounts 10
' _ "$SMOKE_PREFIX" "$SMOKE_REPORT" "$READ_ONLY_WRITE_WAIVER_ID" "$DATA_ANALYSIS_WRITE_FLAG"

PYTHONPATH="$APP_ROOT" "$TARGET_PY" \
  local_inspection_service/scripts/postgres_cutover_gate_report.py \
  --artifact-verify-report "$ARTIFACT_VERIFY_REPORT" \
  --readiness-report "$CUTOVER_READINESS_REPORT" \
  --deploy-package-extract-report "$DEPLOY_PACKAGE_EXTRACT_REPORT" \
  --local-preflight-suite-report "$LOCAL_PREFLIGHT_SUITE_REPORT" \
  --migration-report "$REPORT_PATH" \
  --row-count-report "$IMPORT_ROW_COUNT_REPORT" \
  --import-engine-report "$IMPORT_ENGINE_REPORT" \
  --precutover-report "$ENDPOINT_PREFLIGHT_REPORT" \
  --full-smoke-report "$SMOKE_REPORT" \
  --expected-concurrent-accounts 10 \
  --report "$FINAL_GATE_REPORT" \
  --strict-final

cleanup_smoke_credential
trap - EXIT
```

The runner must implement this exact endpoint and verification matrix:

| Area | Method / path | Payload or query | Expected | PostgreSQL-visible verification |
| --- | --- | --- | --- | --- |
| Login | `POST /api/auth/login` | `{"username": env, "password": env}` | `200`, token kept only in memory | none; token not logged |
| Public root | `GET /` | none | `200` | none |
| Auth status | `GET /api/auth/status` | none | `200`, no retired sensitive fields | none |
| Static bundle | `GET` first app JS asset from `/` | none | `200` | none |
| Removed legacy | `GET /legacy`, `/label-sheet`, `/locate-anything` | none | `404` | none |
| Docs boundary | `GET /docs`, `/openapi.json`, `/redoc` without auth | none | `404` or accepted closed status | none |
| Unauthorized API | `GET /api/status`, `/api/accessories`, `/api/data-analysis/records` without auth | none | `401` or accepted closed status | none |
| 配件 read | `GET /api/accessories?summary=true` | bearer token | `200`, list payload | `select count(*) from vantaline.accessories` succeeds |
| 配件 detail | `GET /api/accessories/{id}/detail` | bearer token; use first existing ID if present | `200` or skip with `no_existing_accessory=true` | selected ID exists in `vantaline.accessories` if not skipped |
| 任务 read | `GET /api/pipeline/tasks` | bearer token | `200` | `select count(*) from vantaline.pipeline_tasks` succeeds |
| 数据集训练 read | `GET /api/training/status`, `/api/training/resources` | bearer token | `200` | `select count(*) from vantaline.training_tasks` succeeds |
| 检测 read | `GET /api/ai/tasks` | bearer token | `200` | `select count(*) from vantaline.ai_detection_tasks` succeeds |
| 结果复核 read | `GET /api/data-analysis/records` | bearer token | `200` | `select count(*) from vantaline.data_analysis_records` succeeds |
| 10-account concurrent smoke | create 10 disposable admin users, then parallel `POST /api/auth/login`, `GET /api/auth/status`, `/api/admin/runtime-store/probe`, `/api/accessories?summary=true`, `/api/pipeline/tasks`, `/api/training/status`, `/api/ai/tasks`, `/api/data-analysis/records` | generated credentials kept only in memory | all 10 sessions pass; 10 worker threads and 10 unique thread-local runtime probe connections observed | each disposable user exists before login, each disposable session is visible in `vantaline.auth_sessions`, then all disposable users and their sessions are absent after cleanup |
| Disposable accessory create | `POST /api/accessories` multipart form | `name=$SMOKE_PREFIX accessory`, `material_type=object`, `material_alpha_policy=opaque`, `training_role=detect_and_classify` | `200`, returns `accessory_id` | `select count(*) from vantaline.accessories where id = :accessory_id and name like :prefix` returns `1` |
| Disposable AI task create | `POST /api/ai/tasks` | `{"name":"$SMOKE_PREFIX ai task","required_accessory_counts":{"<accessory_id>":1}}` | `200`, returns `task.id` | `select count(*) from vantaline.ai_detection_tasks where id = :ai_task_id and name like :prefix` returns `1` |
| Disposable AI task update | `PUT /api/ai/tasks/{ai_task_id}` | `{"name":"$SMOKE_PREFIX ai task updated","required_accessory_counts":{"<accessory_id>":1}}` | `200` | `select count(*) from vantaline.ai_detection_tasks where id = :ai_task_id and name like '%updated'` returns `1` |
| Disposable AI task delete | `DELETE /api/ai/tasks/{ai_task_id}` | none | `200` | `select count(*) from vantaline.ai_detection_tasks where id = :ai_task_id` returns `0` |
| Disposable pipeline create | `POST /api/pipeline/tasks` | `{"name":"$SMOKE_PREFIX pipeline","accessory_ids":[accessory_id],"detection_method":"yolo_ocr","auto_advance":false}` | `200`, returns `task_id` | `select count(*) from vantaline.pipeline_tasks where id = :task_id and name like :prefix` returns `1` |
| Disposable pipeline update | `PATCH /api/pipeline/tasks/{task_id}` | `{"name":"$SMOKE_PREFIX pipeline updated","auto_advance":false}` | `200` | `select count(*) from vantaline.pipeline_tasks where id = :task_id and name like '%updated'` returns `1` |
| Disposable pipeline delete | `DELETE /api/pipeline/tasks/{task_id}` | none | `200` | `select count(*) from vantaline.pipeline_tasks where id = :task_id` returns `0` |
| Disposable accessory delete | `DELETE /api/accessories/{accessory_id}` | none | `200` | `select count(*) from vantaline.accessories where id = :accessory_id` returns `0` |
| Optional data-analysis write | `POST /api/analyze/image`, then `DELETE /api/data-analysis/records/{record_id}` | tiny disposable PNG, `model_id=<ai_task_id>` | `200` and cleanup when `RUN_DATA_ANALYSIS_WRITE=1`, or `data_analysis_write_skipped_reason=<manager-approved reason>` | `select count(*) from vantaline.data_analysis_records where record_id = :record_id` returns `1`, then `0`, if run |

Runner report requirements:

- `login_pass=true`;
- `base_url=http://127.0.0.1:8765`;
- one boolean per endpoint row above;
- `runtime_probe.store=postgres`;
- `runtime_probe.repository_kind=postgres`;
- `runtime_probe.json_fallback_used=false`;
- `runtime_probe.repository_connection_scope=thread-local`;
- `runtime_probe.repository_connection_id=<16-char-non-secret-fingerprint>`;
- `runtime_probe.postgres_count_probe.schema_migrations>=1`;
- `runtime_env.data_store_env_name=VANTALINE_DATA_STORE`;
- `runtime_env.data_store_env_value=postgres`;
- `runtime_env.db_url_env_name=DATABASE_URL`;
- `runtime_env.db_url_present=true`;
- `schema_migration_versions=[2026_07_01_phase4_pr1]`;
- `concurrent_account_http_pass=true`;
- `concurrent_account_cleanup_pass=true`;
- `concurrent_account_count=10`;
- `concurrent_successful_sessions=10`;
- `concurrent_postgres_visible_sessions=10`;
- `concurrent_worker_threads=10`;
- `concurrent_runtime_probe_count=10`;
- `concurrent_thread_local_connections=<1..10>`;
- `concurrent_runtime_probe_unique_connections=<same-as-concurrent_thread_local_connections>`;
- `concurrent_runtime_probe_connection_observations=<10-16-hex-ids-duplicates-allowed>`;
- `concurrent_runtime_probe_connection_ids=<1..10-unique-16-hex-ids>`;
- `concurrent_runtime_probe_connection_reuse_observed=<true iff unique connections < 10>`;
- `app_config_write_pass=true`;
- `app_config_cleanup_pass=true`;
- `accessory_candidate_create_pass=true`;
- `accessory_candidate_delete_pass=true`;
- `ai_task_create_pass=true`;
- `ai_task_update_pass=true`;
- `auto_optimize_write_pass=true`;
- `auto_optimize_cleanup_pass=true`;
- `ai_task_delete_pass=true`;
- `pipeline_state_write_pass=true`;
- `pipeline_state_cleanup_pass=true`;
- `allowlist_state_tables_read_pass=true`;
- one disposable ID list with all IDs redacted to generated smoke IDs only;
- `postgres_visible_write_proof_pass=true`;
- `postgres_visible_read_tables` includes `schema_migrations`, `app_config`,
  `accessories`, `accessory_candidates`, `pipeline_tasks`, `pipeline_state`,
  `training_tasks`, `ai_detection_tasks`, `auto_optimize_states`, and
  `data_analysis_records` with non-negative counts;
- `postgres_visible_write_tables` marks `users`, `auth_sessions`,
  `app_config`, `accessories`, `accessory_candidates`, `ai_detection_tasks`,
  `auto_optimize_states`, `pipeline_tasks`, and `pipeline_state` as true; when
  `RUN_DATA_ANALYSIS_WRITE=1`, it also marks `data_analysis_records=true`;
- `postgres_visible_cleanup_tables` marks `users`, `auth_sessions`,
  `app_config`, `accessories`, `accessory_candidates`, `ai_detection_tasks`,
  `auto_optimize_states`, `pipeline_tasks`, and `pipeline_state` as true; when
  `RUN_DATA_ANALYSIS_WRITE=1`, it also marks `data_analysis_records=true`;
- if `RUN_DATA_ANALYSIS_WRITE=1`, `data_analysis_write_pass=true` and
  `disposable_ids.data_analysis_record_id=<analysis_...>`;
- if `RUN_DATA_ANALYSIS_WRITE` is not `1`,
  `data_analysis_write_skipped_reason=<manager-approved reason>`;
- `read_only_write_waiver_required=true`;
- `read_only_write_waiver_id=<manager-approved non-secret id>`;
- `write_coverage_exceptions` records `training_tasks` with a non-empty reason
  unless the report also proves PostgreSQL-visible write and cleanup for that
  table; it also records `data_analysis_records` when the optional
  data-analysis write probe is not run; it must not contain stale entries for
  tables whose PostgreSQL-visible write and cleanup proof passed;
- `cleanup_pass=true`;
- `cleanup_residual_rows.accessories=0`;
- `cleanup_residual_rows.accessory_candidates=0`;
- `cleanup_residual_rows.ai_detection_tasks=0`;
- `cleanup_residual_rows.auto_optimize_states=0`;
- `cleanup_residual_rows.pipeline_tasks=0`;
- `cleanup_residual_rows.pipeline_state_accessory_ids=0`;
- `cleanup_residual_rows.data_analysis_records=0`;
- `row_count_after_smoke_expected=true`;
- `deleted_feature_boundary_pass=true`;
- `credential_source=runtime_file`;
- `auth_json_token_read=false`;
- `non_secret_report=true`.

The mandatory
`local_inspection_service/scripts/validate_postgres_full_smoke_report.py`
check must pass against `full-smoke-report.json`; do not manually waive missing
concurrency, cleanup, PostgreSQL-visible write, or non-secret report fields.
For read-only-only write probes, the validator also requires the manager
approved `read_only_write_waiver_id` and table-specific
`write_coverage_exceptions` instead of silently treating read coverage as write
coverage. If the optional data-analysis write probe is enabled with
`--run-data-analysis-write`, the validator requires PostgreSQL-visible
`data_analysis_records` write and cleanup evidence instead of accepting a
data-analysis waiver.
The mandatory `cutover-gate-report.json` generated by
`local_inspection_service/scripts/postgres_cutover_gate_report.py --strict-final`
must also report:

- `production_cutover_evidence_pass=true`;
- `final_acceptance_pass=true`;
- `code_deploy.passed=true`;
- `code_deploy.manifest_sha256=<artifact_manifest.manifest_sha256>`;
- `code_deploy.backup_performed=true`;
- `code_deploy.artifact_manifest_verified_after_extract=true`;
- `local_preflight_suite.passed=true`;
- `local_preflight_suite.real_engine_required=true`;
- `local_preflight_suite.real_engine_pass=true`;
- `migration_report.import_artifact_emitted=true`;
- `import_row_counts.row_count_parity_pass=true`;
- `import_real_engine.artifact_source=existing-migration-packet`;
- `import_real_engine.migration_report_sha256=<sha256-of-migration-report>`;
- `import_real_engine.ddl_sha256=<sha256-of-schema-sql>`;
- `import_real_engine.csv_import_real_engine_pass=true`;
- `full_smoke.evidence_kind=production`;
- `full_smoke.base_url=http://127.0.0.1:8765`;
- `full_smoke.runtime_probe.store=postgres`;
- `full_smoke.runtime_probe.repository_kind=postgres`;
- `full_smoke.runtime_probe.json_fallback_used=false`;
- `full_smoke.runtime_probe.postgres_count_probe.schema_migrations>=1`;
- `full_smoke.runtime_env.data_store_env_value=postgres`;
- `full_smoke.runtime_env.db_url_present=true`;
- `full_smoke.schema_migration_versions=[2026_07_01_phase4_pr1]`;
- `full_smoke.cleanup_residual_rows.accessories=0`;
- `full_smoke.cleanup_residual_rows.accessory_candidates=0`;
- `full_smoke.cleanup_residual_rows.ai_detection_tasks=0`;
- `full_smoke.cleanup_residual_rows.auto_optimize_states=0`;
- `full_smoke.cleanup_residual_rows.pipeline_tasks=0`;
- `full_smoke.cleanup_residual_rows.pipeline_state_accessory_ids=0`;
- `full_smoke.cleanup_residual_rows.data_analysis_records=0`;
- `full_smoke.concurrent_successful_sessions=10`;
- `full_smoke.concurrent_postgres_visible_sessions=10`;
- `full_smoke.concurrent_worker_threads=10`;
- `full_smoke.concurrent_runtime_probe_count=10`;
- `full_smoke.concurrent_thread_local_connections=<1..10>`;
- `full_smoke.concurrent_runtime_probe_unique_connections=<same-as-concurrent_thread_local_connections>`;
- `full_smoke.concurrent_runtime_probe_connection_observations=<10-16-hex-ids-duplicates-allowed>`;
- `full_smoke.concurrent_runtime_probe_connection_ids=<1..10-unique-16-hex-ids>`;
- `full_smoke.concurrent_runtime_probe_connection_reuse_observed=<true iff unique connections < 10>`;
- `full_smoke.postgres_visible_write_proof_pass=true`;
- `full_smoke.read_only_write_waiver_required=true`;
- `non_secret_report=true`.

Post-run non-secret service checks:

```bash
sudo test ! -e "$SMOKE_CREDENTIAL_FILE"

sudo -u vantaline psql "$DB_URL" -v ON_ERROR_STOP=1 -tAc \
  "select count(*) from vantaline.accessories"
sudo -u vantaline psql "$DB_URL" -v ON_ERROR_STOP=1 -tAc \
  "select count(*) from vantaline.pipeline_tasks"
sudo -u vantaline psql "$DB_URL" -v ON_ERROR_STOP=1 -tAc \
  "select count(*) from vantaline.data_analysis_records"

journalctl -u "$SERVICE" --since "$CUTOVER_START_ISO" -p err --no-pager
test ! -e "$APP_ROOT/local_inspection_service/data/vantaline.sqlite3"
echo 'runtime_sqlite_artifact_absent=true'
```

PostgreSQL runtime-effectiveness rules:

- Every disposable HTTP write must have a matching SQL check before and after
  cleanup.
- The expected create/update/delete effects must be visible in PostgreSQL.
- JSON file mtimes or checksums must not be the sole proof.
- If a write appears only in JSON and not PostgreSQL, runtime effectiveness
  failed and rollback is required.
- PostgreSQL row counts after cleanup must return to the imported baseline or
  match the expected net delta in `full-smoke-report.json`.

Full smoke passes only when:

- public/unauthenticated smoke passes;
- authenticated main-flow read smoke passes;
- reversible write smoke passes or a manager explicitly approves read-only-only
  acceptance for a specific unavailable write probe;
- PostgreSQL-visible write evidence passes;
- import row-count parity matches the migration report;
- service journal has no new cutover errors;
- no runtime SQLite artifact appears;
- `cutover-gate-report.json` reports `final_acceptance_pass=true`;
- no deleted product boundary regresses.

## Rollback

Rollback prefers runtime/env rollback before data restore.

### Before Service Stop

Abort with no runtime change. No rollback needed.

### After Service Stop, Before Env Switch

```bash
sudo systemctl start "$SERVICE"
systemctl is-active "$SERVICE"
echo 'rollback_to_json_runtime_performed=true'
```

Production DB/import artifacts may exist only if the abort happened after Stage
5. Keep them for forensics unless manager approves cleanup.

### After Env Switch Or Smoke Failure

```bash
sudo systemctl stop "$SERVICE" || true
sudo install -d /etc/systemd/system/vantaline.service.d/disabled
if test -e /etc/systemd/system/vantaline.service.d/40-postgres-runtime.conf; then
  sudo mv /etc/systemd/system/vantaline.service.d/40-postgres-runtime.conf \
    "/etc/systemd/system/vantaline.service.d/disabled/40-postgres-runtime.conf.$(date -u +%Y%m%d%H%M%S)"
fi
if test -e /etc/vantaline/postgres.env; then
  sudo mv /etc/vantaline/postgres.env \
    "/etc/vantaline/postgres.env.disabled.$(date -u +%Y%m%d%H%M%S)"
fi
sudo systemctl daemon-reload
sudo systemctl start "$SERVICE"
systemctl is-active "$SERVICE"

MAIN_PID="$(systemctl show "$SERVICE" -p MainPID --value --no-pager)"
if sudo sh -c 'tr "\0" "\n" < "/proc/$1/environ"' sh "$MAIN_PID" | grep -q '^VANTALINE_DATA_STORE='; then
  echo 'rollback_env_store_absent=false'
  exit 1
else
  echo 'rollback_env_store_absent=true'
fi
if sudo sh -c 'tr "\0" "\n" < "/proc/$1/environ"' sh "$MAIN_PID" | grep -q '^DATABASE_URL='; then
  echo 'rollback_database_url_absent=false'
  exit 1
else
  echo 'rollback_database_url_absent=true'
fi
```

Then rerun public smoke and the authenticated read smoke on JSON runtime. Keep
the PostgreSQL database and artifacts for forensic comparison unless manager
approves deletion.

### Data Restore

Do not restore `data-json.tgz` by default. Data restore is a separate
manager-approved action only if:

- runtime rollback is insufficient;
- there is confirmed JSON data corruption or unacceptable disposable smoke
  residue;
- the exact restore target and expected data loss window are accepted.

Possible data restore command shape after explicit approval:

```bash
sudo systemctl stop "$SERVICE"
sudo tar -C "$APP_ROOT/local_inspection_service/data" -xzf "$BACKUP_ROOT/data-json.tgz"
sudo chown -R vantaline:vantaline "$APP_ROOT/local_inspection_service/data"
sudo systemctl start "$SERVICE"
```

### PostgreSQL Restore

PostgreSQL dump restore is for DB-side recovery only and still requires manager
approval before replacing production DB contents.

```bash
sudo systemctl stop "$SERVICE"
sudo -u postgres dropdb --force --if-exists vantaline
sudo -u postgres createdb --owner=vantaline vantaline
sudo -u vantaline pg_restore \
  --clean \
  --if-exists \
  --dbname="$DB_URL" \
  "$BACKUP_ROOT/vantaline.postgres.dump"
```

## Non-Secret Execution Report Template

Do not include raw `DATABASE_URL` if it contains credentials, env-file contents,
session tokens, bearer tokens, cookies, password verifier values, provider
keys, raw data payloads, or attachment copies of restricted artifacts.

```text
task=17
subtask=18
execution_window_utc=<start>..<end>
backup_root=<path>

endpoint_integration_preflight_performed=<true|false>
endpoint_integration_preflight_pass=<true|false>
endpoint_allowlist_count=<n>
json_default_http_parity_pass=<true|false>
postgres_selected_failure_no_json_fallback_pass=<true|false>
endpoint_smoke_runner_present=<true|false>
next_required_action=<none|separate_endpoint_integration_code_gate|manager_decision_on_existing_empty_db|rollback>

preflight_performed=<true|false>
service_active_before=<active|not-active>
service_binding_preflight_pass=<true|false>
postgres_local_only=<true|false>
service_target_py=<path>
psycopg_version_ok=<true|false>
VANTALINE_DATA_STORE_present_before=<true|false>
DATABASE_URL_present_before=<true|false>
postgres_env_file_present_before=<true|false>
postgres_env_file_referenced_before=<true|false>
role_preexisted=<t|f>
role_privileges_preflight_ok=<true|pending_manager_approved_creation>
role_created_by_gate=<true|false>
role_privileges_after_prep_ok=<true|false>
role_retained=<true|false>
prod_db_preexisted=<t|f>
prod_db_created_by_gate=<true|false>
prod_db_existing_table_count=<n|n/a>
prod_db_existing_empty_manager_preaccepted=<true|false|n/a>

gate6_retry_performed=<true|false>
gate6_selected_store=postgres
gate6_repository_kind=postgres
gate6_schema_migrations_count=<n>
gate6_smoke_db_present_after_cleanup=<true|false>
gate6_temp_schema_present_after_cleanup=<true|false>

service_stop_performed=<true|false>
app_code_backup_pass=<true|false>
data_json_backup_pass=<true|false>
artifact_generation_performed=<true|false>
source_error_count=<n>
blocking_error_count=<n>
cutover_allowed=<true|false>
import_artifact_emitted=<true|false>
schema_migrations_csv_exists=<true|false>
row_counts=<redacted-count-json>
migration_report_validation_pass=<true|false>
local_preflight_suite_report=<path|not-created>
local_preflight_suite_real_engine_required=<true|false>
local_preflight_suite_real_engine_pass=<true|false>
import_real_engine_report=<path|not-created>

restore_rehearsal_performed=<true|false>
restore_rehearsal_pass=<true|false>
rehearsal_cleanup_failed=<true|false>
rehearsal_import_db_present_after_cleanup=<true|false>
rehearsal_restore_db_present_after_cleanup=<true|false>
rehearsal_retained_by_manager=<true|false>
production_import_performed=<true|false>
row_count_parity_pass=<true|false>
import_row_count_report=<path|not-created>
postgres_dump_created=<true|false>

env_file_created=<true|false>
dropin_created=<true|false>
daemon_reload_performed=<true|false>
service_start_or_restart_performed=<true|false>
service_env_postgres_present=<true|false>
postgres_env_file_referenced=<true|false>
selector_selected_store=postgres
selector_repository_kind=postgres

full_smoke_performed=<true|false>
full_smoke_runner_present=<true|false>
credential_source=<runtime_file|human_browser|none>
smoke_credential_file_removed=<true|false|n/a>
public_unauth_smoke_pass=<true|false>
deleted_feature_boundary_pass=<true|false>
authenticated_read_smoke_pass=<true|false>
authenticated_write_smoke_pass=<true|false|waived-by-manager>
disposable_accessory_id=<smoke-id|not-run>
disposable_pipeline_task_id=<smoke-id|not-run>
accessory_create_pg_visible=<true|false|not-run>
pipeline_create_pg_visible=<true|false|not-run>
pipeline_update_pg_visible=<true|false|not-run>
pipeline_delete_pg_visible=<true|false|not-run>
accessory_delete_pg_visible=<true|false|not-run>
data_analysis_write_skipped_reason=<reason|not-skipped>
data_analysis_write_pass=<true|false|not-run>
disposable_data_analysis_record_id=<analysis-id|not-run>
read_only_write_waiver_required=<true|false>
read_only_write_waiver_id=<manager-approved-non-secret-id|none>
write_coverage_exceptions=<table-reason-json>
postgres_visible_write_proof_pass=<true|false>
postgres_visible_read_tables=<redacted-count-json>
postgres_visible_write_tables=<table-bool-json>
postgres_visible_cleanup_tables=<table-bool-json>
cleanup_pass=<true|false>
row_count_after_smoke_expected=<true|false>
journal_error_check_pass=<true|false>
runtime_sqlite_artifact_absent=<true|false>
full_smoke_pass=<true|false>
cutover_gate_report_final_acceptance_pass=<true|false>
cutover_gate_report_production_evidence_pass=<true|false>

rollback_performed=<true|false>
rollback_stage=<none|pre-env|post-env|data-restore|db-restore>
rollback_to_json_runtime_pass=<true|false|n/a>
data_restore_performed=<true|false>
postgres_db_cleanup_performed=<true|false>

boundary_no_secret_report=<true|false>
boundary_no_raw_env_print=<true|false>
boundary_no_live_auth_token_read=<true|false>
boundary_no_unapproved_data_cleanup=<true|false>
final_acceptance_candidate=<true|false>
```

Final acceptance candidate can be true only if:

- rollback was not required, or rollback was required and manager explicitly
  accepted the post-rollback state;
- endpoint integration preflight passed before any destructive stage;
- PostgreSQL runtime effectiveness is proven by HTTP plus PostgreSQL-visible
  evidence;
- migration report validation, real-engine import smoke, and import row-count
  parity all passed;
- rehearsal DB cleanup reported no residue unless a manager-approved retention
  branch was explicitly used;
- full smoke passed;
- `cutover-gate-report.json` reports final acceptance and production evidence;
- the report is non-secret.
