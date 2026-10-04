BEGIN;
SET search_path TO vantaline, public;
CREATE TABLE IF NOT EXISTS label_runtime_state (
 id TEXT PRIMARY KEY, updated_at BIGINT NOT NULL, raw_json JSONB NOT NULL
);
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json)
VALUES ('2026_10_04_label_runtime_state',EXTRACT(EPOCH FROM NOW())::BIGINT,'{"strategy":"expand","consumer":"label-runtime"}'::jsonb)
ON CONFLICT(version) DO NOTHING;
COMMIT;
