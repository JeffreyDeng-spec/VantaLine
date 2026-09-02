BEGIN;

CREATE TABLE IF NOT EXISTS vantaline.text_inspection_standard_revisions (
    id TEXT PRIMARY KEY, standard_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
    revision_number BIGINT NOT NULL, action TEXT NOT NULL, asset_id TEXT NOT NULL,
    created_at BIGINT NOT NULL, raw_json JSONB NOT NULL,
    UNIQUE (standard_id, revision_number)
);
CREATE INDEX IF NOT EXISTS idx_text_inspection_standard_revisions
    ON vantaline.text_inspection_standard_revisions (owner_user_id, standard_id, revision_number);

INSERT INTO vantaline.feature_migrations (version, applied_at, metadata_json)
VALUES ('2026_09_02_text_inspection_standard_revisions', EXTRACT(EPOCH FROM NOW())::BIGINT,
        '{"feature":"text_inspection_standard_revisions","strategy":"expand","rollback":"previous release ignores additive revision table"}'::jsonb)
ON CONFLICT (version) DO NOTHING;

COMMIT;
