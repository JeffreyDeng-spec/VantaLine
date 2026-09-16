BEGIN;
SET search_path TO vantaline, public;
CREATE TABLE IF NOT EXISTS model_profile_objects (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, created_at BIGINT NOT NULL, raw_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_model_profile_kind ON model_profile_objects(kind,created_at);
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json)
VALUES ('2026_09_16_model_profiles',EXTRACT(EPOCH FROM NOW())::BIGINT,'{"strategy":"expand"}'::jsonb)
ON CONFLICT(version) DO NOTHING;
COMMIT;
