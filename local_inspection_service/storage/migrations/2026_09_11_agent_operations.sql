BEGIN;
SET search_path TO vantaline, public;
CREATE TABLE IF NOT EXISTS "agent_policies" (
    "id" TEXT NOT NULL,
    "owner_user_id" TEXT NOT NULL,
    "created_at" BIGINT NOT NULL,
    "raw_json" JSONB NOT NULL,
    PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS idx_agent_policies_owner ON agent_policies (owner_user_id, created_at);
CREATE TABLE IF NOT EXISTS "agent_operations" (
    "id" TEXT NOT NULL,
    "owner_user_id" TEXT NOT NULL,
    "created_at" BIGINT NOT NULL,
    "raw_json" JSONB NOT NULL,
    "idempotency_key" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "updated_at" BIGINT NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("owner_user_id", "idempotency_key")
);
CREATE INDEX IF NOT EXISTS idx_agent_operations_owner ON agent_operations (owner_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_operations_queue ON agent_operations (owner_user_id, status, created_at);
CREATE TABLE IF NOT EXISTS "agent_operation_attempts" (
    "id" TEXT NOT NULL,
    "owner_user_id" TEXT NOT NULL,
    "created_at" BIGINT NOT NULL,
    "raw_json" JSONB NOT NULL,
    PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS idx_agent_operation_attempts_owner ON agent_operation_attempts (owner_user_id, created_at);
CREATE TABLE IF NOT EXISTS "agent_operation_audit" (
    "id" TEXT NOT NULL,
    "owner_user_id" TEXT NOT NULL,
    "created_at" BIGINT NOT NULL,
    "raw_json" JSONB NOT NULL,
    PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS idx_agent_operation_audit_owner ON agent_operation_audit (owner_user_id, created_at);
INSERT INTO vantaline.feature_migrations (version, applied_at, metadata_json) VALUES ('2026_09_11_agent_operations', EXTRACT(EPOCH FROM NOW())::BIGINT, '{"feature":"agent_operations","strategy":"expand"}'::jsonb) ON CONFLICT (version) DO NOTHING;
COMMIT;
