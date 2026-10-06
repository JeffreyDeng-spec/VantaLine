"""Explicit bootstrap root selection and derived application locations."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path


class RootLocator:
    def __init__(self, environment: Mapping[str, str], entry_file: str,
                 is_dir: Callable[[Path], bool]):
        self.environment, self.entry_file, self.is_dir = environment, entry_file, is_dir

    def resolve(self) -> Path:
        override = (
            self.environment.get("LOCAL_INSPECTION_ROOT")
            or self.environment.get("INSPECTION_SERVICE_ROOT")
            or self.environment.get("VANTALINE_REPO_ROOT")
        )
        raw_root = Path(override).expanduser() if override else Path(self.entry_file).resolve().parents[1]
        if raw_root.name == "local_inspection_service":
            raw_root = raw_root.parent
        root = raw_root.resolve()
        if not self.is_dir(root / "local_inspection_service"):
            raise RuntimeError(f"Resolved service root {root} does not contain local_inspection_service")
        return root


@dataclass(frozen=True)
class RuntimeLocations:
    """Only path values; no services, connections, identity or mutable runtime state."""
    root: Path
    app_dir: Path
    static_dir: Path
    react_preview_dist_dir: Path
    react_preview_assets_dir: Path
    react_production_dist_dir: Path
    react_production_assets_dir: Path
    data_dir: Path
    upload_dir: Path
    output_dir: Path
    normalized_dir: Path
    training_jobs_dir: Path
    training_tasks_dir: Path
    accessory_candidates_dir: Path
    image_worker_log_dir: Path
    config_path: Path
    config_backup_path: Path
    plc_web_serial_state_path: Path
    ai_local_config_path: Path
    local_secret_env_path: Path
    ai_profile_cache_path: Path
    ai_detection_tasks_path: Path
    auth_path: Path
    data_analysis_records_path: Path
    incoming_text_references_path: Path
    incoming_text_inspections_path: Path
    incoming_text_audit_path: Path
    text_inspection_dir: Path
    text_inspection_json_dir: Path
    text_inspection_media_dir: Path

    @classmethod
    def from_root(cls, root: Path) -> "RuntimeLocations":
        app_dir = root / 'local_inspection_service'
        static_dir = app_dir / 'static'
        react_preview_dist_dir = app_dir / 'frontend' / 'dist'
        react_preview_assets_dir = react_preview_dist_dir / 'assets'
        react_production_dist_dir = app_dir / 'frontend' / 'dist-production'
        react_production_assets_dir = react_production_dist_dir / 'assets'
        data_dir = app_dir / 'data'
        upload_dir = data_dir / 'uploads'
        output_dir = data_dir / 'outputs'
        normalized_dir = data_dir / 'normalized_assets'
        training_jobs_dir = data_dir / 'training_jobs'
        training_tasks_dir = data_dir / 'training_tasks'
        accessory_candidates_dir = data_dir / 'accessory_candidates'
        image_worker_log_dir = data_dir / 'image_worker_logs'
        config_path = data_dir / 'config.json'
        config_backup_path = data_dir / 'config.last_good.json'
        plc_web_serial_state_path = data_dir / 'plc_web_serial_state.json'
        ai_local_config_path = data_dir / 'ai_config.local.json'
        local_secret_env_path = data_dir / 'runtime_secrets.local.env'
        ai_profile_cache_path = data_dir / 'ai_profile_cache.local.json'
        ai_detection_tasks_path = data_dir / 'ai_detection_tasks.json'
        auth_path = data_dir / 'auth.json'
        data_analysis_records_path = data_dir / 'data_analysis_records.json'
        incoming_text_references_path = data_dir / 'incoming_text_reference_versions.json'
        incoming_text_inspections_path = data_dir / 'incoming_text_inspections.json'
        incoming_text_audit_path = data_dir / 'incoming_text_audit_events.json'
        text_inspection_dir = data_dir / 'text_inspection_v2'
        text_inspection_json_dir = text_inspection_dir / 'records'
        text_inspection_media_dir = text_inspection_dir / 'media'
        return cls(root, app_dir, static_dir, react_preview_dist_dir, react_preview_assets_dir, react_production_dist_dir, react_production_assets_dir, data_dir, upload_dir, output_dir, normalized_dir, training_jobs_dir, training_tasks_dir, accessory_candidates_dir, image_worker_log_dir, config_path, config_backup_path, plc_web_serial_state_path, ai_local_config_path, local_secret_env_path, ai_profile_cache_path, ai_detection_tasks_path, auth_path, data_analysis_records_path, incoming_text_references_path, incoming_text_inspections_path, incoming_text_audit_path, text_inspection_dir, text_inspection_json_dir, text_inspection_media_dir)
