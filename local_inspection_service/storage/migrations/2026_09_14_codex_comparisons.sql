BEGIN;
SET search_path TO vantaline, public;
CREATE TABLE IF NOT EXISTS codex_comparison_tasks (id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT NOT NULL, raw_json JSONB NOT NULL, UNIQUE(owner_user_id,idempotency_key));
CREATE INDEX IF NOT EXISTS idx_codex_tasks_owner ON codex_comparison_tasks(owner_user_id,id);
CREATE INDEX IF NOT EXISTS idx_codex_tasks_queue ON codex_comparison_tasks(status,id);
CREATE TABLE IF NOT EXISTS codex_comparison_events (id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, task_id TEXT NOT NULL, sequence BIGINT NOT NULL, idempotency_key TEXT NOT NULL, created_at BIGINT NOT NULL, raw_json JSONB NOT NULL, UNIQUE(task_id,idempotency_key), UNIQUE(task_id,sequence));
CREATE INDEX IF NOT EXISTS idx_codex_events_task ON codex_comparison_events(owner_user_id,task_id,sequence);
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json) VALUES ('2026_09_14_codex_comparisons', EXTRACT(EPOCH FROM NOW())::BIGINT, '{"strategy":"expand"}'::jsonb) ON CONFLICT(version) DO NOTHING;
COMMIT;
