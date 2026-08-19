BEGIN;

CREATE TABLE IF NOT EXISTS vantaline.plc_workstations (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    config_generation BIGINT NOT NULL,
    profile_verified BOOLEAN NOT NULL,
    created_by_user_id TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    raw_json JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plc_workstations_status
    ON vantaline.plc_workstations (status);

CREATE TABLE IF NOT EXISTS vantaline.plc_workstation_leases (
    station_id TEXT PRIMARY KEY REFERENCES vantaline.plc_workstations(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    state TEXT NOT NULL,
    lease_epoch BIGINT NOT NULL,
    owner_user_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    client_instance_id TEXT NOT NULL,
    bundle_version TEXT NOT NULL,
    config_generation BIGINT NOT NULL,
    heartbeat_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    raw_json JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plc_workstation_leases_expiry
    ON vantaline.plc_workstation_leases (expires_at);

CREATE TABLE IF NOT EXISTS vantaline.plc_web_serial_dispatches (
    id TEXT PRIMARY KEY,
    station_id TEXT NOT NULL REFERENCES vantaline.plc_workstations(id) ON DELETE RESTRICT,
    detection_request_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    lease_epoch BIGINT NOT NULL,
    config_generation BIGINT NOT NULL,
    status TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    deadline_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    raw_json JSONB NOT NULL,
    UNIQUE (station_id, detection_request_id)
);

CREATE INDEX IF NOT EXISTS idx_plc_web_serial_dispatch_status
    ON vantaline.plc_web_serial_dispatches (station_id, status, created_at);

CREATE TABLE IF NOT EXISTS vantaline.feature_migrations (
    version TEXT PRIMARY KEY,
    applied_at BIGINT NOT NULL,
    metadata_json JSONB NOT NULL
);

INSERT INTO vantaline.feature_migrations (version, applied_at, metadata_json)
VALUES (
    '2026_08_06_plc_web_serial_v3',
    EXTRACT(EPOCH FROM NOW())::BIGINT,
    '{"feature":"plc_web_serial_v3","rollback":"disable routes; preserve v3 audit rows"}'::jsonb
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
