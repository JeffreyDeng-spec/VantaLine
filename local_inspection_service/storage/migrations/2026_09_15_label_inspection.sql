BEGIN;
SET search_path TO vantaline, public;
CREATE TABLE IF NOT EXISTS label_inspection_objects (
 id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, task_id TEXT NOT NULL,
 kind TEXT NOT NULL, status TEXT NOT NULL, created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL, idempotency_key TEXT NOT NULL, raw_json JSONB NOT NULL,
 UNIQUE(owner_user_id,kind,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_label_objects_owner ON label_inspection_objects(owner_user_id,kind,updated_at,id);
CREATE INDEX IF NOT EXISTS idx_label_objects_task ON label_inspection_objects(owner_user_id,task_id,kind,created_at,id);
CREATE INDEX IF NOT EXISTS idx_label_objects_queue ON label_inspection_objects(kind,status,created_at);
INSERT INTO vantaline.feature_migrations(version,applied_at,metadata_json) VALUES ('2026_09_15_label_inspection',EXTRACT(EPOCH FROM NOW())::BIGINT,'{"strategy":"expand"}'::jsonb) ON CONFLICT(version) DO NOTHING;
COMMIT;
