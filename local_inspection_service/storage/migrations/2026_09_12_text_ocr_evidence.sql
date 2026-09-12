BEGIN;
CREATE TABLE IF NOT EXISTS vantaline.text_ocr_evidence (
    id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, status TEXT NOT NULL,
    created_at BIGINT NOT NULL, raw_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_text_ocr_evidence_owner
    ON vantaline.text_ocr_evidence (owner_user_id, created_at);
INSERT INTO vantaline.feature_migrations (version, applied_at, metadata_json)
VALUES ('2026_09_12_text_ocr_evidence', EXTRACT(EPOCH FROM NOW())::BIGINT,
        '{"feature":"qwen_ocr_evidence","strategy":"expand"}'::jsonb)
ON CONFLICT (version) DO NOTHING;
COMMIT;
