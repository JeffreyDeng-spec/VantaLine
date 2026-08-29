BEGIN;

CREATE TABLE IF NOT EXISTS vantaline.text_inspection_standards (
    id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, name TEXT NOT NULL,
    material_code TEXT NOT NULL, version_label TEXT NOT NULL,
    standard_type TEXT NOT NULL, status TEXT NOT NULL, source_sha256 TEXT NOT NULL,
    created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, raw_json JSONB NOT NULL,
    UNIQUE (owner_user_id, material_code, version_label, standard_type)
);
CREATE INDEX IF NOT EXISTS idx_text_inspection_standards_owner
    ON vantaline.text_inspection_standards (owner_user_id, created_at);

CREATE TABLE IF NOT EXISTS vantaline.text_inspection_assets (
    id TEXT PRIMARY KEY, standard_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
    asset_kind TEXT NOT NULL, ordinal BIGINT NOT NULL, status TEXT NOT NULL,
    sha256 TEXT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
    raw_json JSONB NOT NULL, UNIQUE (standard_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_text_inspection_assets_standard
    ON vantaline.text_inspection_assets (owner_user_id, standard_id, ordinal);

CREATE TABLE IF NOT EXISTS vantaline.text_inspection_records (
    id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, standard_id TEXT NOT NULL,
    comparison_id TEXT NOT NULL, status TEXT NOT NULL, auto_decision TEXT NOT NULL,
    final_decision TEXT NOT NULL, source_sha256 TEXT NOT NULL,
    created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, raw_json JSONB NOT NULL,
    UNIQUE (owner_user_id, comparison_id)
);
CREATE INDEX IF NOT EXISTS idx_text_inspection_records_owner
    ON vantaline.text_inspection_records (owner_user_id, created_at);

CREATE TABLE IF NOT EXISTS vantaline.text_inspection_manual_sessions (
    id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, standard_id TEXT NOT NULL,
    status TEXT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
    raw_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_text_manual_sessions_owner
    ON vantaline.text_inspection_manual_sessions (owner_user_id, updated_at);

CREATE TABLE IF NOT EXISTS vantaline.text_inspection_manual_pages (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
    capture_id TEXT NOT NULL, standard_asset_id TEXT NOT NULL, status TEXT NOT NULL,
    created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, raw_json JSONB NOT NULL,
    UNIQUE (owner_user_id, session_id, capture_id)
);
CREATE INDEX IF NOT EXISTS idx_text_manual_pages_session
    ON vantaline.text_inspection_manual_pages (owner_user_id, session_id, created_at);

CREATE TABLE IF NOT EXISTS vantaline.text_inspection_classification_feedback (
    id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, standard_id TEXT NOT NULL,
    asset_id TEXT NOT NULL, action TEXT NOT NULL, created_at BIGINT NOT NULL,
    raw_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_text_classification_feedback
    ON vantaline.text_inspection_classification_feedback (owner_user_id, standard_id, created_at);

CREATE TABLE IF NOT EXISTS vantaline.feature_migrations (
    version TEXT PRIMARY KEY, applied_at BIGINT NOT NULL, metadata_json JSONB NOT NULL
);
INSERT INTO vantaline.feature_migrations (version, applied_at, metadata_json)
VALUES ('2026_08_29_text_inspection_v2', EXTRACT(EPOCH FROM NOW())::BIGINT,
        '{"feature":"text_inspection_v2","strategy":"expand","rollback":"disable v2 routes; v1 remains intact"}'::jsonb)
ON CONFLICT (version) DO NOTHING;

COMMIT;
