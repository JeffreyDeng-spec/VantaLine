BEGIN;
CREATE TABLE IF NOT EXISTS vantaline.text_label_extractions (
    id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL,
    created_at BIGINT NOT NULL, raw_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_text_label_extractions_owner
    ON vantaline.text_label_extractions (owner_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_text_label_extractions_root
    ON vantaline.text_label_extractions (owner_user_id, (raw_json->>'root_id'));
INSERT INTO vantaline.feature_migrations (version, applied_at, metadata_json)
VALUES ('2026_09_06_text_label_extractions', EXTRACT(EPOCH FROM NOW())::BIGINT,
        '{"feature":"single_label_extraction","strategy":"expand"}'::jsonb)
ON CONFLICT (version) DO NOTHING;
COMMIT;
