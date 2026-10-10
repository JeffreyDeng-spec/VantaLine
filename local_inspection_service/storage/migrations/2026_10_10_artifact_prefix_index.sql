BEGIN;
SET search_path TO vantaline, public;
CREATE INDEX IF NOT EXISTS idx_artifact_prefix_c
ON artifact_locations ((logical_path COLLATE "C"), generation DESC);
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json)
VALUES ('2026_10_10_artifact_prefix_index',EXTRACT(EPOCH FROM NOW())::BIGINT,'{"strategy":"expand","purpose":"literal-prefix reads"}'::jsonb)
ON CONFLICT(version) DO NOTHING;
COMMIT;
