"""Frozen b2d6f07 root/path bootstrap for exact differential checks."""
import os
from pathlib import Path

def resolve_service_root() -> Path:
    override = (
        os.environ.get("LOCAL_INSPECTION_ROOT")
        or os.environ.get("INSPECTION_SERVICE_ROOT")
        or os.environ.get("VANTALINE_REPO_ROOT")
    )
    raw_root = Path(override).expanduser() if override else Path(__file__).resolve().parents[1]
    if raw_root.name == "local_inspection_service":
        raw_root = raw_root.parent
    root = raw_root.resolve()
    if not _business_files.is_dir(root / "local_inspection_service"):
        raise RuntimeError(f"Resolved service root {root} does not contain local_inspection_service")
    return root


def original_locations(root):
    ROOT = root
    APP_DIR = ROOT / "local_inspection_service"
    STATIC_DIR = APP_DIR / "static"
    REACT_PREVIEW_DIST_DIR = APP_DIR / "frontend" / "dist"
    REACT_PREVIEW_ASSETS_DIR = REACT_PREVIEW_DIST_DIR / "assets"
    REACT_PRODUCTION_DIST_DIR = APP_DIR / "frontend" / "dist-production"
    REACT_PRODUCTION_ASSETS_DIR = REACT_PRODUCTION_DIST_DIR / "assets"
    DATA_DIR = APP_DIR / "data"
    UPLOAD_DIR = DATA_DIR / "uploads"
    OUTPUT_DIR = DATA_DIR / "outputs"
    NORMALIZED_DIR = DATA_DIR / "normalized_assets"
    TRAINING_JOBS_DIR = DATA_DIR / "training_jobs"
    TRAINING_TASKS_DIR = DATA_DIR / "training_tasks"
    ACCESSORY_CANDIDATES_DIR = DATA_DIR / "accessory_candidates"
    IMAGE_WORKER_LOG_DIR = DATA_DIR / "image_worker_logs"
    CONFIG_PATH = DATA_DIR / "config.json"
    CONFIG_BACKUP_PATH = DATA_DIR / "config.last_good.json"
    PLC_WEB_SERIAL_STATE_PATH = DATA_DIR / "plc_web_serial_state.json"
    AI_LOCAL_CONFIG_PATH = DATA_DIR / "ai_config.local.json"
    LOCAL_SECRET_ENV_PATH = DATA_DIR / "runtime_secrets.local.env"
    AI_PROFILE_CACHE_PATH = DATA_DIR / "ai_profile_cache.local.json"
    AI_DETECTION_TASKS_PATH = DATA_DIR / "ai_detection_tasks.json"
    AUTH_PATH = DATA_DIR / "auth.json"
    DATA_ANALYSIS_RECORDS_PATH = DATA_DIR / "data_analysis_records.json"
    INCOMING_TEXT_REFERENCES_PATH = DATA_DIR / "incoming_text_reference_versions.json"
    INCOMING_TEXT_INSPECTIONS_PATH = DATA_DIR / "incoming_text_inspections.json"
    INCOMING_TEXT_AUDIT_PATH = DATA_DIR / "incoming_text_audit_events.json"
    TEXT_INSPECTION_DIR = DATA_DIR / "text_inspection_v2"
    TEXT_INSPECTION_JSON_DIR = TEXT_INSPECTION_DIR / "records"
    TEXT_INSPECTION_MEDIA_DIR = TEXT_INSPECTION_DIR / "media"
    return locals()
