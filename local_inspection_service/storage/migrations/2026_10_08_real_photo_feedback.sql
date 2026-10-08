BEGIN;
SET search_path TO vantaline, public;
CREATE TABLE IF NOT EXISTS real_photo_states (owner_user_id TEXT NOT NULL, task_id TEXT NOT NULL, raw_json JSONB NOT NULL, PRIMARY KEY(owner_user_id,task_id));
CREATE TABLE IF NOT EXISTS real_photo_jobs (id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, task_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, raw_json JSONB NOT NULL, UNIQUE(owner_user_id,task_id,idempotency_key));
CREATE INDEX IF NOT EXISTS idx_real_photo_queue ON real_photo_jobs(kind,status,created_at);
CREATE TABLE IF NOT EXISTS real_photo_events (id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, task_id TEXT NOT NULL, job_id TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, raw_json JSONB NOT NULL);
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json) VALUES ('2026_10_08_real_photo_feedback',EXTRACT(EPOCH FROM NOW())::BIGINT,'{"strategy":"expand"}'::jsonb) ON CONFLICT(version) DO NOTHING;
COMMIT;
