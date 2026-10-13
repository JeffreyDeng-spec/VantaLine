BEGIN;
CREATE TABLE IF NOT EXISTS vantaline.billing_accounts (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    currency TEXT NOT NULL,
    alias TEXT NOT NULL,
    updated_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS vantaline.billing_snapshots (
    id TEXT PRIMARY KEY,
    publication_seq BIGSERIAL UNIQUE NOT NULL,
    account_id TEXT NOT NULL REFERENCES vantaline.billing_accounts(id),
    kind TEXT NOT NULL CHECK (kind IN ('balance','bills')),
    period TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS billing_snapshot_latest ON vantaline.billing_snapshots(account_id,kind,period,publication_seq DESC);
CREATE TABLE IF NOT EXISTS vantaline.billing_entries (
    snapshot_id TEXT NOT NULL REFERENCES vantaline.billing_snapshots(id),
    entry_id TEXT NOT NULL,
    day TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY(snapshot_id,entry_id)
);
CREATE INDEX IF NOT EXISTS billing_entry_page ON vantaline.billing_entries(snapshot_id,day DESC,entry_id DESC);
CREATE TABLE IF NOT EXISTS vantaline.billing_sync_state (
    lane TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES vantaline.billing_accounts(id),
    kind TEXT NOT NULL CHECK (kind IN ('balance','bills')),
    period TEXT NOT NULL,
    job_id TEXT NOT NULL,
    last_attempt BIGINT NOT NULL,
    lease_token TEXT,
    lease_until BIGINT NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS vantaline.billing_sync_jobs (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    period TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    finished_at BIGINT,
    error_code TEXT
);
CREATE INDEX IF NOT EXISTS billing_job_status ON vantaline.billing_sync_jobs(status,created_at);
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json)
VALUES ('2026_10_13_billing',extract(epoch from now())::bigint,'{"feature":"billing","rollback":"retain financial snapshots and entries"}'::jsonb)
ON CONFLICT(version) DO NOTHING;
COMMIT;
