BEGIN;
CREATE TABLE IF NOT EXISTS vantaline.plc_diagnostic_events (
    owner_user_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    station_id TEXT,
    received_at BIGINT NOT NULL,
    step TEXT NOT NULL,
    result TEXT NOT NULL,
    code TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (owner_user_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_plc_diag_owner_time ON vantaline.plc_diagnostic_events(owner_user_id, received_at DESC, event_id);
CREATE INDEX IF NOT EXISTS idx_plc_diag_attempt ON vantaline.plc_diagnostic_events(owner_user_id, attempt_id, received_at, event_id);
CREATE INDEX IF NOT EXISTS idx_plc_diag_time ON vantaline.plc_diagnostic_events(received_at DESC, event_id);
CREATE INDEX IF NOT EXISTS idx_plc_diag_station_time ON vantaline.plc_diagnostic_events(station_id, received_at DESC);
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json)
VALUES ('2026_10_12_plc_diagnostic_events',extract(epoch from now())::bigint,'{"feature":"plc_diagnostic_events","rollback":"preserve additive diagnostic table"}'::jsonb)
ON CONFLICT(version) DO NOTHING;
COMMIT;
