BEGIN;
CREATE TABLE IF NOT EXISTS vantaline.text_sheet_elements (
    id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, root_id TEXT NOT NULL,
    created_at BIGINT NOT NULL, raw_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_text_sheet_elements_root
    ON vantaline.text_sheet_elements (owner_user_id, root_id, created_at);
INSERT INTO vantaline.feature_migrations (version, applied_at, metadata_json)
VALUES ('2026_09_08_sheet_elements', EXTRACT(EPOCH FROM NOW())::BIGINT,
        '{"feature":"sheet_elements","strategy":"expand"}'::jsonb)
ON CONFLICT (version) DO NOTHING;
COMMIT;
