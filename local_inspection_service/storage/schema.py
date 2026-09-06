"""Postgres-portable storage schema for the VantaLine JSON migration dry run.

The current application runtime still reads and writes JSON files. These
definitions are intentionally script-only so PR 1 can validate a relational
shape without changing endpoint behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


SCHEMA_VERSION = "2026_07_01_phase4_pr1"
INCOMING_TEXT_SCHEMA_VERSION = "2026_08_06_incoming_text_v1"
TEXT_INSPECTION_SCHEMA_VERSION = "2026_08_29_text_inspection_v2"
TEXT_INSPECTION_STANDARD_REVISIONS_SCHEMA_VERSION = "2026_09_02_text_inspection_standard_revisions"
PLC_WEB_SERIAL_SCHEMA_VERSION = "2026_08_06_plc_web_serial_v3"

ACTIVE_RUNTIME_STATUSES = frozenset(
    {
        "active",
        "approved",
        "capturing",
        "collecting",
        "confirming",
        "pending",
        "processing",
        "queued",
        "running",
        "starting",
        "training",
        "uploading",
    }
)

HISTORICAL_RUNTIME_STATUSES = frozenset(
    {
        "",
        "archived",
        "canceled",
        "cancelled",
        "completed",
        "disabled",
        "done",
        "failed",
        "idle",
        "legacy",
        "rejected",
        "retired",
        "skipped",
        "stopped",
        "succeeded",
    }
)

OWNER_REQUIRED_TABLES = frozenset(
    {
        "text_label_extractions",
        "accessories",
        "accessory_candidates",
        "ai_detection_tasks",
        "data_analysis_records",
        "training_tasks",
        "pipeline_tasks",
        "auto_optimize_states",
        "incoming_text_reference_versions",
        "incoming_text_inspections",
        "text_inspection_standards",
        "text_inspection_assets",
        "text_inspection_standard_revisions",
        "text_inspection_records",
        "text_inspection_manual_sessions",
        "text_inspection_manual_pages",
        "text_inspection_classification_feedback",
    }
)

LEGACY_OWNER_OK_STATUSES = HISTORICAL_RUNTIME_STATUSES

SENSITIVE_LOCAL_SOURCES = (
    "ai_config.local.json",
    "agent_config.local.json",
    "runtime_secrets.local.env",
    "locateanything_config.local.json",
)

IGNORED_DATA_SUBTREES = (
    "uploads",
    "outputs",
    "normalized_assets",
    "image_worker_logs",
    "worker_image_jobs",
    "cu126wheels",
    "backups",
)

SOURCE_TO_TABLE_MAPPING = {
    "auth.json:users": "users",
    "auth.json:sessions": "auth_sessions",
    "config.json:non_accessory_keys": "app_config",
    "config.json:accessories": "accessories",
    "config.json:accessory_source_paths": "accessory_assets",
    "accessory_candidates/*.json": "accessory_candidates",
    "accessory_candidates/*.json:asset_paths": "accessory_assets",
    "ai_detection_tasks.json:tasks": "ai_detection_tasks",
    "data_analysis_records.json:records": "data_analysis_records",
    "training_tasks/*.json": "training_tasks",
    "pipeline_tasks.json": "pipeline_tasks",
    "pipeline_state.json": "pipeline_state",
    "auto_optimize/*.json": "auto_optimize_states",
    "incoming_text_reference_versions.json": "incoming_text_reference_versions",
    "incoming_text_inspections.json": "incoming_text_inspections",
}


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: tuple[str, ...]
    ddl: str
    indexes: tuple[str, ...] = ()


TABLES = (
    TableSchema(
        "schema_migrations",
        ("version", "applied_at", "metadata_json"),
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at INTEGER NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """,
    ),
    TableSchema(
        "users",
        (
            "id",
            "username",
            "display_name",
            "role",
            "permissions_json",
            "password_hash",
            "active",
            "created_at",
            "updated_at",
            "raw_json",
        ),
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            permissions_json TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            active INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
    ),
    TableSchema(
        "auth_sessions",
        ("id_hash", "user_id", "created_at", "last_seen_at", "expires_at", "raw_json"),
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        (
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions (user_id)",
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions (expires_at)",
        ),
    ),
    TableSchema(
        "app_config",
        ("config_key", "config_value_json", "source_file", "updated_at"),
        """
        CREATE TABLE IF NOT EXISTS app_config (
            config_key TEXT PRIMARY KEY,
            config_value_json TEXT NOT NULL,
            source_file TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """,
    ),
    TableSchema(
        "accessories",
        (
            "id",
            "class_id",
            "name",
            "status",
            "material_type",
            "owner_user_id",
            "owner_username",
            "created_at",
            "updated_at",
            "raw_json",
        ),
        """
        CREATE TABLE IF NOT EXISTS accessories (
            id TEXT PRIMARY KEY,
            class_id TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            material_type TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        ("CREATE INDEX IF NOT EXISTS idx_accessories_status ON accessories (status)",),
    ),
    TableSchema(
        "accessory_assets",
        ("id", "parent_table", "parent_id", "asset_kind", "source_field", "path", "path_exists", "raw_json"),
        """
        CREATE TABLE IF NOT EXISTS accessory_assets (
            id TEXT PRIMARY KEY,
            parent_table TEXT NOT NULL,
            parent_id TEXT NOT NULL,
            asset_kind TEXT NOT NULL,
            source_field TEXT NOT NULL,
            path TEXT NOT NULL,
            path_exists INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        (
            "CREATE INDEX IF NOT EXISTS idx_accessory_assets_parent ON accessory_assets (parent_table, parent_id)",
            "CREATE INDEX IF NOT EXISTS idx_accessory_assets_path_exists ON accessory_assets (path_exists)",
        ),
    ),
    TableSchema(
        "accessory_candidates",
        (
            "id",
            "name",
            "class_id",
            "status",
            "owner_user_id",
            "owner_username",
            "created_at",
            "updated_at",
            "raw_json",
        ),
        """
        CREATE TABLE IF NOT EXISTS accessory_candidates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            class_id TEXT NOT NULL,
            status TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        ("CREATE INDEX IF NOT EXISTS idx_accessory_candidates_status ON accessory_candidates (status)",),
    ),
    TableSchema(
        "ai_detection_tasks",
        ("id", "name", "status", "source", "owner_user_id", "owner_username", "created_at", "updated_at", "raw_json"),
        """
        CREATE TABLE IF NOT EXISTS ai_detection_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            source TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        ("CREATE INDEX IF NOT EXISTS idx_ai_detection_tasks_status ON ai_detection_tasks (status)",),
    ),
    TableSchema(
        "data_analysis_records",
        ("record_id", "task_id", "owner_user_id", "owner_username", "created_at", "updated_at", "image_path", "raw_json"),
        """
        CREATE TABLE IF NOT EXISTS data_analysis_records (
            record_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        (
            "CREATE INDEX IF NOT EXISTS idx_data_analysis_records_task_id ON data_analysis_records (task_id)",
            "CREATE INDEX IF NOT EXISTS idx_data_analysis_records_owner ON data_analysis_records (owner_user_id)",
        ),
    ),
    TableSchema(
        "training_tasks",
        (
            "id",
            "job_id",
            "action",
            "status",
            "queue_kind",
            "owner_user_id",
            "owner_username",
            "created_at",
            "updated_at",
            "raw_json",
        ),
        """
        CREATE TABLE IF NOT EXISTS training_tasks (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            queue_kind TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        ("CREATE INDEX IF NOT EXISTS idx_training_tasks_status ON training_tasks (status)",),
    ),
    TableSchema(
        "pipeline_tasks",
        ("id", "name", "status", "stage", "owner_user_id", "owner_username", "created_at", "updated_at", "raw_json"),
        """
        CREATE TABLE IF NOT EXISTS pipeline_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        ("CREATE INDEX IF NOT EXISTS idx_pipeline_tasks_status ON pipeline_tasks (status)",),
    ),
    TableSchema(
        "pipeline_state",
        ("state_key", "state_value_json", "updated_at"),
        """
        CREATE TABLE IF NOT EXISTS pipeline_state (
            state_key TEXT PRIMARY KEY,
            state_value_json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """,
    ),
    TableSchema(
        "auto_optimize_states",
        ("task_id", "status", "owner_user_id", "owner_username", "created_at", "updated_at", "raw_json"),
        """
        CREATE TABLE IF NOT EXISTS auto_optimize_states (
            task_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        ("CREATE INDEX IF NOT EXISTS idx_auto_optimize_states_status ON auto_optimize_states (status)",),
    ),
    TableSchema(
        "audit_events",
        ("id", "event_type", "created_at", "actor_user_id", "payload_json"),
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            actor_user_id TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """,
        ("CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events (created_at)",),
    ),
    TableSchema(
        "incoming_text_reference_versions",
        (
            "id",
            "task_id",
            "version_label",
            "material_code",
            "status",
            "owner_user_id",
            "owner_username",
            "source_path",
            "source_sha256",
            "created_at",
            "activated_at",
            "raw_json",
        ),
        """
        CREATE TABLE IF NOT EXISTS incoming_text_reference_versions (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            version_label TEXT NOT NULL,
            material_code TEXT NOT NULL,
            status TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            activated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL,
            UNIQUE (owner_user_id, task_id, version_label)
        )
        """,
        (
            "CREATE INDEX IF NOT EXISTS idx_incoming_text_reference_task ON incoming_text_reference_versions (owner_user_id, task_id)",
            "CREATE INDEX IF NOT EXISTS idx_incoming_text_reference_status ON incoming_text_reference_versions (status)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_incoming_text_reference_active ON incoming_text_reference_versions (owner_user_id, task_id) WHERE status = 'active'",
        ),
    ),
    TableSchema(
        "incoming_text_inspections",
        (
            "id",
            "capture_id",
            "task_id",
            "reference_id",
            "material_code",
            "status",
            "auto_decision",
            "final_decision",
            "owner_user_id",
            "owner_username",
            "source_path",
            "source_sha256",
            "created_at",
            "updated_at",
            "raw_json",
        ),
        """
        CREATE TABLE IF NOT EXISTS incoming_text_inspections (
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
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL,
            UNIQUE (owner_user_id, task_id, capture_id)
        )
        """,
        (
            "CREATE INDEX IF NOT EXISTS idx_incoming_text_inspection_task ON incoming_text_inspections (owner_user_id, task_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_incoming_text_inspection_material ON incoming_text_inspections (material_code, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_incoming_text_inspection_decision ON incoming_text_inspections (auto_decision, final_decision)",
        ),
    ),
    # Text inspection v2 is additive so the previous release can still run on
    # the expanded schema during the rollback window.
    TableSchema(
        "text_inspection_standards",
        ("id", "owner_user_id", "name", "material_code", "version_label", "standard_type", "status", "source_sha256", "created_at", "updated_at", "raw_json"),
        """CREATE TABLE IF NOT EXISTS text_inspection_standards (
            id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, name TEXT NOT NULL,
            material_code TEXT NOT NULL, version_label TEXT NOT NULL,
            standard_type TEXT NOT NULL, status TEXT NOT NULL,
            source_sha256 TEXT NOT NULL, created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL, raw_json TEXT NOT NULL,
            UNIQUE (owner_user_id, material_code, version_label, standard_type)
        )""",
        ("CREATE INDEX IF NOT EXISTS idx_text_inspection_standards_owner ON text_inspection_standards (owner_user_id, created_at)",),
    ),
    TableSchema(
        "text_inspection_assets",
        ("id", "standard_id", "owner_user_id", "asset_kind", "ordinal", "status", "sha256", "created_at", "updated_at", "raw_json"),
        """CREATE TABLE IF NOT EXISTS text_inspection_assets (
            id TEXT PRIMARY KEY, standard_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
            asset_kind TEXT NOT NULL, ordinal INTEGER NOT NULL, status TEXT NOT NULL,
            sha256 TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL, UNIQUE (standard_id, ordinal)
        )""",
        ("CREATE INDEX IF NOT EXISTS idx_text_inspection_assets_standard ON text_inspection_assets (owner_user_id, standard_id, ordinal)",),
    ),
    TableSchema(
        "text_inspection_standard_revisions",
        ("id", "standard_id", "owner_user_id", "revision_number", "action", "asset_id", "created_at", "raw_json"),
        """CREATE TABLE IF NOT EXISTS text_inspection_standard_revisions (
            id TEXT PRIMARY KEY, standard_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
            revision_number INTEGER NOT NULL, action TEXT NOT NULL, asset_id TEXT NOT NULL,
            created_at INTEGER NOT NULL, raw_json TEXT NOT NULL,
            UNIQUE (standard_id, revision_number)
        )""",
        ("CREATE INDEX IF NOT EXISTS idx_text_inspection_standard_revisions ON text_inspection_standard_revisions (owner_user_id, standard_id, revision_number)",),
    ),
    TableSchema(
        "text_inspection_records",
        ("id", "owner_user_id", "standard_id", "comparison_id", "status", "auto_decision", "final_decision", "source_sha256", "created_at", "updated_at", "raw_json"),
        """CREATE TABLE IF NOT EXISTS text_inspection_records (
            id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, standard_id TEXT NOT NULL,
            comparison_id TEXT NOT NULL, status TEXT NOT NULL, auto_decision TEXT NOT NULL,
            final_decision TEXT NOT NULL, source_sha256 TEXT NOT NULL,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, raw_json TEXT NOT NULL,
            UNIQUE (owner_user_id, comparison_id)
        )""",
        ("CREATE INDEX IF NOT EXISTS idx_text_inspection_records_owner ON text_inspection_records (owner_user_id, created_at)",),
    ),
    TableSchema(
        "text_label_extractions",
        ("id", "owner_user_id", "created_at", "raw_json"),
        """CREATE TABLE IF NOT EXISTS text_label_extractions (
            id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL,
            created_at INTEGER NOT NULL, raw_json TEXT NOT NULL
        )""",
        ("CREATE INDEX IF NOT EXISTS idx_text_label_extractions_owner ON text_label_extractions (owner_user_id, created_at)",),
    ),
    TableSchema(
        "text_inspection_manual_sessions",
        ("id", "owner_user_id", "standard_id", "status", "created_at", "updated_at", "raw_json"),
        """CREATE TABLE IF NOT EXISTS text_inspection_manual_sessions (
            id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, standard_id TEXT NOT NULL,
            status TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )""",
        ("CREATE INDEX IF NOT EXISTS idx_text_manual_sessions_owner ON text_inspection_manual_sessions (owner_user_id, updated_at)",),
    ),
    TableSchema(
        "text_inspection_manual_pages",
        ("id", "session_id", "owner_user_id", "capture_id", "standard_asset_id", "status", "created_at", "updated_at", "raw_json"),
        """CREATE TABLE IF NOT EXISTS text_inspection_manual_pages (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
            capture_id TEXT NOT NULL, standard_asset_id TEXT NOT NULL, status TEXT NOT NULL,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, raw_json TEXT NOT NULL,
            UNIQUE (owner_user_id, session_id, capture_id)
        )""",
        ("CREATE INDEX IF NOT EXISTS idx_text_manual_pages_session ON text_inspection_manual_pages (owner_user_id, session_id, created_at)",),
    ),
    TableSchema(
        "text_inspection_classification_feedback",
        ("id", "owner_user_id", "standard_id", "asset_id", "action", "created_at", "raw_json"),
        """CREATE TABLE IF NOT EXISTS text_inspection_classification_feedback (
            id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, standard_id TEXT NOT NULL,
            asset_id TEXT NOT NULL, action TEXT NOT NULL, created_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )""",
        ("CREATE INDEX IF NOT EXISTS idx_text_classification_feedback ON text_inspection_classification_feedback (owner_user_id, standard_id, created_at)",),
    ),
    TableSchema(
        "plc_workstations",
        ("id", "token_hash", "name", "status", "config_generation", "profile_verified", "created_by_user_id", "created_at", "updated_at", "raw_json"),
        """
        CREATE TABLE IF NOT EXISTS plc_workstations (
            id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            config_generation INTEGER NOT NULL,
            profile_verified BOOLEAN NOT NULL,
            created_by_user_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_plc_workstations_token_hash ON plc_workstations (token_hash)",
            "CREATE INDEX IF NOT EXISTS idx_plc_workstations_status ON plc_workstations (status)",
        ),
    ),
    TableSchema(
        "plc_workstation_leases",
        ("station_id", "session_id", "state", "lease_epoch", "owner_user_id", "model_id", "client_instance_id", "bundle_version", "config_generation", "heartbeat_at", "expires_at", "raw_json"),
        """
        CREATE TABLE IF NOT EXISTS plc_workstation_leases (
            station_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            state TEXT NOT NULL,
            lease_epoch INTEGER NOT NULL,
            owner_user_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            client_instance_id TEXT NOT NULL,
            bundle_version TEXT NOT NULL,
            config_generation INTEGER NOT NULL,
            heartbeat_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )
        """,
        ("CREATE INDEX IF NOT EXISTS idx_plc_workstation_leases_expiry ON plc_workstation_leases (expires_at)",),
    ),
    TableSchema(
        "plc_web_serial_dispatches",
        ("id", "station_id", "detection_request_id", "session_id", "lease_epoch", "config_generation", "status", "passed", "deadline_at", "created_at", "updated_at", "raw_json"),
        """
        CREATE TABLE IF NOT EXISTS plc_web_serial_dispatches (
            id TEXT PRIMARY KEY,
            station_id TEXT NOT NULL,
            detection_request_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            lease_epoch INTEGER NOT NULL,
            config_generation INTEGER NOT NULL,
            status TEXT NOT NULL,
            passed BOOLEAN NOT NULL,
            deadline_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL,
            UNIQUE (station_id, detection_request_id)
        )
        """,
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_plc_web_serial_dispatch_detection ON plc_web_serial_dispatches (station_id, detection_request_id)",
            "CREATE INDEX IF NOT EXISTS idx_plc_web_serial_dispatch_status ON plc_web_serial_dispatches (station_id, status, created_at)",
        ),
    ),
)

TABLE_BY_NAME = {table.name: table for table in TABLES}


def table_names() -> tuple[str, ...]:
    return tuple(table.name for table in TABLES)


def columns_for_table(table_name: str) -> tuple[str, ...]:
    return TABLE_BY_NAME[table_name].columns


def is_active_status(value: object) -> bool:
    return str(value or "").strip().lower() in ACTIVE_RUNTIME_STATUSES


def is_historical_status(value: object) -> bool:
    return str(value or "").strip().lower() in HISTORICAL_RUNTIME_STATUSES
