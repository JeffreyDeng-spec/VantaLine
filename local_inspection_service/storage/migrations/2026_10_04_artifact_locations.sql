BEGIN;
SET search_path TO vantaline, public;
CREATE TABLE IF NOT EXISTS artifact_locations (
 logical_path TEXT NOT NULL,
 generation BIGINT NOT NULL CHECK (generation > 0),
 object_key TEXT NOT NULL,
 sha256 TEXT NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
 size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
 state TEXT NOT NULL CHECK (state IN ('ready','deleted')),
 created_at BIGINT NOT NULL,
 mtime_ns BIGINT NOT NULL DEFAULT 0 CHECK (mtime_ns >= 0),
 PRIMARY KEY (logical_path,generation),
 CHECK (object_key = 'objects/sha256/' || left(sha256,2) || '/' || sha256)
);
CREATE INDEX IF NOT EXISTS idx_artifact_latest ON artifact_locations(logical_path,generation DESC);
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json)
VALUES ('2026_10_04_artifact_locations',EXTRACT(EPOCH FROM NOW())::BIGINT,'{"strategy":"expand"}'::jsonb)
ON CONFLICT(version) DO NOTHING;
COMMIT;
