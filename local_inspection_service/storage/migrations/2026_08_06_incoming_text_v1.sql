BEGIN;

CREATE TABLE IF NOT EXISTS vantaline.incoming_text_reference_versions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    version_label TEXT NOT NULL,
    material_code TEXT NOT NULL,
    status TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    activated_at BIGINT NOT NULL,
    raw_json JSONB NOT NULL,
    UNIQUE (owner_user_id, task_id, version_label)
);

CREATE INDEX IF NOT EXISTS idx_incoming_text_reference_task
    ON vantaline.incoming_text_reference_versions (owner_user_id, task_id);
CREATE INDEX IF NOT EXISTS idx_incoming_text_reference_status
    ON vantaline.incoming_text_reference_versions (status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_incoming_text_reference_active
    ON vantaline.incoming_text_reference_versions (owner_user_id, task_id)
    WHERE status = 'active';

CREATE TABLE IF NOT EXISTS vantaline.incoming_text_inspections (
    id TEXT PRIMARY KEY,
    capture_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    material_code TEXT NOT NULL,
    status TEXT NOT NULL,
    auto_decision TEXT NOT NULL,
    final_decision TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    raw_json JSONB NOT NULL,
    UNIQUE (owner_user_id, task_id, capture_id)
);

CREATE INDEX IF NOT EXISTS idx_incoming_text_inspection_task
    ON vantaline.incoming_text_inspections (owner_user_id, task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_incoming_text_inspection_material
    ON vantaline.incoming_text_inspections (material_code, created_at);
CREATE INDEX IF NOT EXISTS idx_incoming_text_inspection_decision
    ON vantaline.incoming_text_inspections (auto_decision, final_decision);

-- Feature migrations are tracked separately so the legacy bootstrap validator can
-- continue to require exactly one row in schema_migrations.
CREATE TABLE IF NOT EXISTS vantaline.feature_migrations (
    version TEXT PRIMARY KEY,
    applied_at BIGINT NOT NULL,
    metadata_json JSONB NOT NULL
);

INSERT INTO vantaline.feature_migrations (version, applied_at, metadata_json)
VALUES (
    '2026_08_06_incoming_text_v1',
    EXTRACT(EPOCH FROM NOW())::BIGINT,
    '{"feature":"incoming_material_text","rollback":"drop feature tables after disabling routes"}'::jsonb
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
