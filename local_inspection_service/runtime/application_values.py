"""Composition-time values; no services, request identity or database connection.

Only application wiring consumes this result. Business components continue to
receive their existing narrow policy ports and individual value suppliers.
Filesystem model fallback selection is deliberately evaluated during bootstrap.
"""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import logging
from .bootstrap_locations import RuntimeLocations
from ..storage.artifacts.files import BusinessFiles
from typing import Any
from local_inspection_service.plc_fx_ascii import DEFAULT_PLC_CONFIG
from local_inspection_service.plc_fx_ascii import MAX_DISPATCH_WALL_SECONDS
from pathlib import Path
import logging

@dataclass(frozen=True)
class ApplicationValues:
    ROOT: Path
    APP_DIR: Path
    STATIC_DIR: Path
    REACT_PREVIEW_DIST_DIR: Path
    REACT_PREVIEW_ASSETS_DIR: Path
    REACT_PRODUCTION_DIST_DIR: Path
    REACT_PRODUCTION_ASSETS_DIR: Path
    DATA_DIR: Path
    UPLOAD_DIR: Path
    OUTPUT_DIR: Path
    NORMALIZED_DIR: Path
    TRAINING_JOBS_DIR: Path
    TRAINING_TASKS_DIR: Path
    ACCESSORY_CANDIDATES_DIR: Path
    IMAGE_WORKER_LOG_DIR: Path
    CONFIG_PATH: Path
    CONFIG_BACKUP_PATH: Path
    PLC_WEB_SERIAL_STATE_PATH: Path
    AI_LOCAL_CONFIG_PATH: Path
    LOCAL_SECRET_ENV_PATH: Path
    AI_PROFILE_CACHE_PATH: Path
    AI_DETECTION_TASKS_PATH: Path
    AUTH_PATH: Path
    DATA_ANALYSIS_RECORDS_PATH: Path
    INCOMING_TEXT_REFERENCES_PATH: Path
    INCOMING_TEXT_INSPECTIONS_PATH: Path
    INCOMING_TEXT_AUDIT_PATH: Path
    TEXT_INSPECTION_DIR: Path
    TEXT_INSPECTION_JSON_DIR: Path
    TEXT_INSPECTION_MEDIA_DIR: Path
    TEXT_INSPECTION_EXTERNAL_VLM_ENABLED: bool
    TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED: bool
    TEXT_INSPECTION_MANUAL_PASS_VERIFIED: bool
    TEXT_INSPECTION_DIAGNOSTIC_LOGGER: logging.Logger
    TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE: int
    TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY: int
    TEXT_INSPECTION_PROVIDER_TIMEOUT_SECONDS: float
    TEXT_INSPECTION_PROMPT_VERSION: str
    INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED: bool
    INCOMING_TEXT_MIN_FREE_BYTES: int
    AUTO_OPTIMIZE_DIR: Path
    AI_SUPPORTED_PROVIDERS: set[str]
    AI_DEFAULT_PROVIDER: str
    AI_DEFAULT_MODELS: dict[str, str]
    AI_DEFAULT_MODEL: str
    AI_MODEL_OPTIONS: list[dict[str, str]]
    AI_DEFAULT_BASE_URLS: dict[str, str]
    AI_PROVIDER_LABELS: dict[str, str]
    AI_DEFAULT_TIMEOUT_SECONDS: float
    IMAGE_GENERATION_SUPPORTED_PROVIDERS: set[str]
    IMAGE_GENERATION_DEFAULT_PROVIDER: str
    IMAGE_GENERATION_DEFAULT_MODELS: dict[str, str]
    IMAGE_GENERATION_DEFAULT_BASE_URLS: dict[str, str]
    IMAGE_GENERATION_DEFAULT_API_KEY_ENVS: dict[str, str]
    IMAGE_GENERATION_MODEL_OPTIONS: list[dict[str, str]]
    IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS: float
    IMAGE_GENERATION_PROVIDER_KEYS: dict[str, str]
    IMAGE_GENERATION_PROVIDER_LABELS: dict[str, str]
    IMAGE_GENERATION_MODEL_ENV: str
    IMAGE_GENERATION_PROVIDER_ENV: str
    IMAGE_GENERATION_BASE_URL_ENV: str
    IMAGE_GENERATION_API_KEY_ENV: str
    IMAGE_GENERATION_NAMED_API_KEY_ENV: str
    IMAGE_GENERATION_TIMEOUT_ENV: str
    AI_PROXY_ENV_NAMES: tuple[str, ...]
    AI_AUTO_LOCAL_PROXY_ENV: str
    CURSOR_IMAGE2_PROVIDER: str
    WINDOWS_WORKER_IMAGE_PROVIDER: str
    LOCAL_CODEX_IMAGE_PROVIDER: str
    CURSOR_IMAGE2_QUEUE_STATUS: str
    CODEX_IMAGE_WORKER_QUEUE_STATUS: str
    CURSOR_IMAGE2_API_KEY_ENV: str
    CURSOR_IMAGE2_BASE_URL_ENV: str
    CURSOR_IMAGE2_ENDPOINT_ENV: str
    CURSOR_IMAGE2_MODEL_ENV: str
    CURSOR_IMAGE2_DEFAULT_MODEL: str
    CURSOR_IMAGE_MODEL_KEYWORDS: tuple[str, ...]
    CURSOR_IMAGE_MODEL_PRIORITY: tuple[str, ...]
    STALE_REPO_PATH_PREFIXES: tuple[str, ...]
    IMAGE_JOB_ACTIVE_STATUSES: set[str]
    IMAGE_JOB_QUEUED_STATUSES: set[str]
    LEGACY_MODEL_PATH: Path
    REPO_MODEL_PATH: Path
    MODEL_PATH: Path
    FIVE_CLASS_MODEL_PATH: Path
    DETECT_BASE_MODEL_OVERRIDE: str
    MODEL_CLASS_NAMES: dict[int, str]
    MODEL_TO_BUSINESS_CLASS: dict[int, int]
    CLASS_NAMES: dict[int, str]
    CLASS_LABELS: dict[int, str]
    GENERIC_DETECTION_CLASS_NAMES: dict[int, str]
    GENERIC_DETECTION_LABELS: dict[int, str]
    DEFAULT_MODEL_ID: str
    AI_DETECTION_MODEL_ID: str
    AI_DETECTION_TASK_PREFIX: str
    AI_DETECTION_LABEL: str
    AI_DETECTION_SYSTEM_PROMPT: str
    AI_INSPECTION_IMAGE_MAX_SIDE: int
    AI_INSPECTION_IMAGE_QUALITY: int
    AI_REFERENCE_IMAGES_PER_ACCESSORY: int
    AI_REFERENCE_IMAGE_MAX_SIDE: int
    AI_REFERENCE_IMAGE_QUALITY: int
    AI_PROFILE_REFERENCE_IMAGES: int
    AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE: int
    AI_PROFILE_REFERENCE_IMAGE_QUALITY: int
    AI_PROFILE_REFERENCE_MODE: str
    AI_PROFILE_REFERENCE_SHEET_MAX_SIDE: int
    AI_PROFILE_REFERENCE_SHEET_QUALITY: int
    AI_PROFILE_CACHE_TTL_SECONDS: int
    AI_PROFILE_CACHE_VERSION: int
    AI_MCP_INSPECTION_IMAGE_DIR: Path
    INSPECTION_PREVIEW_MAX_SIDE: int
    INSPECTION_PREVIEW_JPEG_QUALITY: int
    DATA_ANALYSIS_BATCH_LIMIT: int
    AI_DETECTION_OUTPUT_SCHEMA: dict[str, Any]
    AI_MCP_EXTRACTION_POINT: str
    AI_PROVIDER_MAX_ATTEMPTS: int
    AI_PROVIDER_RETRY_BACKOFF_SECONDS: float
    AI_MCP_TOOL_DEFINITIONS: dict[str, dict[str, Any]]
    MODEL_REGISTRY: dict[str, dict[str, Any]]
    DEFAULT_CONFIG: dict[str, Any]
    DEFAULT_AI_CONFIG: dict[str, Any]
    AUTH_SESSION_COOKIE: str
    PLC_WORKSTATION_COOKIE: str
    PLC_WORKSTATION_COOKIE_TTL_SECONDS: int
    PLC_WEB_SERIAL_JSON_TEST_ENV: str
    AUTH_SESSION_TTL_SECONDS: int
    AUTH_SESSION_PERSIST_INTERVAL_SECONDS: int
    PASSWORD_HASH_ITERATIONS: int
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int
    LOGIN_RATE_LIMIT_LOCKOUT_SECONDS: int
    LEGACY_OWNER_ID: str
    SYSTEM_OWNER_ID: str
    AUTO_OPTIMIZE_MASK_MAX_PARALLEL: int
    AUTO_OPTIMIZE_MASK_MAX_ATTEMPTS: int
    AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS: float
    AUTO_OPTIMIZE_MASK_RETRY_MAX_SECONDS: float
    AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT: int
    AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE: int
    MAX_PARALLEL_IMAGE_WORKERS: int
    IMAGE_WORKER_STALE_SECONDS: int
    IMAGE_WORKER_LOG_TAIL_BYTES: int
    WINDOWS_WORKER_STATUS_CACHE_SECONDS: float
    IMAGE_REFERENCE_SUFFIXES: set[str]
    VIDEO_REFERENCE_SUFFIXES: set[str]
    MAX_TEXT_ACCESSORY_IMAGES: int
    MAX_IMAGE_WORKER_INPUTS: int
    MAX_VIDEO_REFERENCE_FRAMES: int
    PREVIEW_CACHE_SCHEMA_VERSION: str
    ANCHOR_POLICY_VERSION: str
    POSE_ANCHOR_DIR: Path
    POSE_ANCHOR_IMAGES: dict[str, Path]
    POSE_TARGET_GUIDE_IMAGES: dict[str, Any]
    POSE_COLLECTION_BATCHES: list[tuple[str, str, list[str]]]
    MANUAL_TYPE_LABELS: dict[str, str]
    MANUAL_TYPE_CLASS_IDS: dict[str, int]
    MANUAL_TYPE_KEYWORDS: dict[str, list[tuple[str, int]]]
    STANDARD_PAPER_SIZES_MM: dict[str, tuple[float, ...]]
    INSPECTION_CAMERA_HEIGHT_MM: float
    INSPECTION_CAMERA_FRAME_WIDTH_MM: float
    MM_TO_PREVIEW_PX: float
    DEFAULT_OBJECT_SIZE_MM: dict[str, float]
    SIZE_REFERENCE_OBJECTS: dict[str, dict[str, Any]]
    DEFAULT_SIZE_REFERENCE: str
    POSE_COLLECTION_GRID_ENABLED: bool
    AGENT_MCP_SPRITE_BUILD_VERSION: int
    PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION: int
    PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES: int
    PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES: int
    PHOTO_HIGHLIGHT_MASK_MAX_SIDE: int
    PHOTO_HIGHLIGHT_MASK_RGB: tuple[int, ...]
    PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS: int
    CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD: float
    CHROMA_SCREEN_OPTIONS: dict[str, dict[str, Any]]
    AGENT_MCP_POSE_PLAN_VERSION: int
    AGENT_MCP_POSE_PLAN_MIN_POSES: int
    AGENT_MCP_POSE_PLAN_MAX_POSES: int
    AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE: float
    SOURCE_ASPECT_ELONGATED_MIN_RATIO: float
    UPRIGHT_SCALE_CORRECTION_MIN_RATIO: float
    UPRIGHT_SCALE_CORRECTION_MAX_RATIO: float
    UPRIGHT_SCALE_VISUAL_ADJUSTMENT: float
    PREVIEW_CANVAS_SIZE_PX: tuple[int, ...]
    DETECTION_MAX_OCCLUSION_FRACTION: float
    DETECTION_MIN_VISIBLE_AREA_PX: int
    PIPELINE_BG_PLATE_MAX_SIDE: int
    PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS: int
    PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC: float
    PIPELINE_BG_PLATE_TIME_BUDGET_S: float
    PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES: int
    PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES: int
    PIPELINE_BG_MATCH_DISTANCE_THRESHOLD: float
    BACKGROUND_ROI_PX: tuple[int, ...]
    BACKGROUND_DIR: Path
    BACKGROUND_SETS_DIR: Path
    BACKGROUND_SETS_MANIFEST: Path
    DEFAULT_BACKGROUND_IMAGE: Path
    STANDARDIZED_MANUALS_DIR: Path
    PRECISE_MANUALS_DIR: Path
    BACKGROUND_SIZE_MM: dict[str, float]
    PLC_CONTROL_GENERATION_KEY: str
    PLC_RUNTIME_COORDINATION_KEY: str
    PLC_CAPTURE_RESULTS_KEY: str
    PLC_PROTECTED_CONFIG_KEYS: tuple[str, ...]
    PLC_IO_CONFIG_FIELDS: frozenset[str]
    PLC_DISPATCH_AUDIT_LIMIT: int
    PLC_QUEUE_WAIT_SECONDS: float
    PLC_WORKER_TOTAL_TIMEOUT_SECONDS: float
    PLC_IO_OWNER_HEARTBEAT_SECONDS: float
    PLC_IO_OWNER_LEASE_SECONDS: float
    PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS: float
    PLC_CAPTURE_POLL_SECONDS: float
    PLC_CAPTURE_EVENT_TTL_SECONDS: float
    PLC_CAPTURE_PROCESSING_TTL_SECONDS: float
    PLC_RECORD_SCHEMA_VERSION: int
    PLC_PROTOCOL_CONTRACT_VERSION: int
    ACCESSORY_ENGLISH_NAME_FALLBACKS: dict[str, str]
    ACCESSORY_ENGLISH_PHRASES: tuple[tuple[str, ...], ...]
    ACCESSORY_ENGLISH_NAME_FIELDS: tuple[str, ...]
    GENERIC_ENGLISH_NAME_TOKENS: set[str]
    STORE_READ_CACHE_TTL_SECONDS: float
    AUTO_OPTIMIZE_MASK_PROMPT_MODE: str
    AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION: str
    AUTO_OPTIMIZE_MASK_PALETTE: list[dict[str, Any]]
    DOCUMENT_LIKE_TEXT_HINTS: tuple[str, ...]
    MASK_VERIFIER_SYSTEM_PROMPT: str
    AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY: str
    AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE: tuple[int, ...]
    AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE: float
    STATUS_MODEL_PUBLIC_KEYS: set[str]
    POSE_COLLECTION_GRID_POSITIONS: list[str]
    UPRIGHT_TOP_VIEW_SOURCE_POSITIONS: tuple[str, ...]
    CODEX_IMAGE_JOB_PERSISTED_KEYS: tuple[str, ...]
    WORKER_BUNDLE_SKIP_DIRS: set[str]
    WORKER_BUNDLE_JPEG_QUALITY: int
    OCR_ACCESSORY_MATCH_MIN_TEXT_SCORE: float
    OCR_ACCESSORY_MATCH_MIN_CONFIDENCE: float
    OCR_ACCESSORY_MATCH_MIN_MARGIN: float
    OCR_ACCESSORY_PROFILE_STOPWORDS: set[str]
    PIPELINE_TASKS_PATH: Path
    AGENT_LOCAL_CONFIG_PATH: Path
    PIPELINE_STATE_PATH: Path
    AGENT_PROVIDER_OPENAI_COMPATIBLE: str
    AGENT_PROVIDER_CURSOR: str
    AGENT_SUPPORTED_PROVIDERS: set[str]
    AGENT_CURSOR_DEFAULT_BASE_URL: str
    AGENT_CONNECTION_STATUSES: set[str]
    AGENT_CURSOR_RECOMMENDATION_MESSAGE: str
    DEFAULT_AGENT_CONFIG: dict[str, Any]
    ACCESSORY_DETECTION_ROUTES: set[str]
    PIPELINE_DETECTION_METHODS: set[str]
    PIPELINE_TRAINING_METHODS: set[str]
    PIPELINE_STAGE_ORDER: list[str]
    PIPELINE_DASHBOARD_AI_TASK_SOURCE: str
    AGENT_MCP_ORCHESTRATION_VERSION: str
    AGENT_MCP_GEMINI_IMAGE_MODEL_ENV: str
    AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV: str
    AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL: str
    AGENT_MCP_GEMINI_IMAGE_HIGH_FIDELITY_MODEL: str
    AGENT_MCP_GEMINI_IMAGE_DEFAULT_TIMEOUT_SECONDS: float
    AGENT_MCP_TOOL_POSE_IMAGE: str
    AGENT_MCP_TOOL_SAMPLES: str
    AGENT_MCP_TOOL_TRAINING: str
    AGENT_MCP_CONVERSATION_LIMIT: int
    AGENT_MCP_AUTO_MAX_STEPS: int
    AGENT_PIPELINE_ACTIONS: set[str]
    AGENT_PIPELINE_STAGE_TARGETS: set[str]
    PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S: int
    AGENT_PIPELINE_SYSTEM_PROMPT: str
    PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS: float
    TEXT_COMPARE_BETA_MAX_BYTES: int
    TEXT_COMPARE_BETA_MAX_PIXELS: int
    TEXT_COMPARE_BETA_CACHE_TTL_SECONDS: int
    TEXT_COMPARE_BETA_CACHE_MAX_BYTES: int
    DASHBOARD_AI_TASK_NAME: str
    REACT_PRODUCTION_ROUTE_SEGMENTS: set[str]
    REACT_PRODUCTION_BLOCKED_PREFIXES: tuple[str, ...]

def build_application_values(environment: Mapping[str, str], locations: RuntimeLocations, files: BusinessFiles) -> ApplicationValues:
    ROOT = locations.root
    APP_DIR = locations.app_dir
    STATIC_DIR = locations.static_dir
    REACT_PREVIEW_DIST_DIR = locations.react_preview_dist_dir
    REACT_PREVIEW_ASSETS_DIR = locations.react_preview_assets_dir
    REACT_PRODUCTION_DIST_DIR = locations.react_production_dist_dir
    REACT_PRODUCTION_ASSETS_DIR = locations.react_production_assets_dir
    DATA_DIR = locations.data_dir
    UPLOAD_DIR = locations.upload_dir
    OUTPUT_DIR = locations.output_dir
    NORMALIZED_DIR = locations.normalized_dir
    TRAINING_JOBS_DIR = locations.training_jobs_dir
    TRAINING_TASKS_DIR = locations.training_tasks_dir
    ACCESSORY_CANDIDATES_DIR = locations.accessory_candidates_dir
    IMAGE_WORKER_LOG_DIR = locations.image_worker_log_dir
    CONFIG_PATH = locations.config_path
    CONFIG_BACKUP_PATH = locations.config_backup_path
    PLC_WEB_SERIAL_STATE_PATH = locations.plc_web_serial_state_path
    AI_LOCAL_CONFIG_PATH = locations.ai_local_config_path
    LOCAL_SECRET_ENV_PATH = locations.local_secret_env_path
    AI_PROFILE_CACHE_PATH = locations.ai_profile_cache_path
    AI_DETECTION_TASKS_PATH = locations.ai_detection_tasks_path
    AUTH_PATH = locations.auth_path
    DATA_ANALYSIS_RECORDS_PATH = locations.data_analysis_records_path
    INCOMING_TEXT_REFERENCES_PATH = locations.incoming_text_references_path
    INCOMING_TEXT_INSPECTIONS_PATH = locations.incoming_text_inspections_path
    INCOMING_TEXT_AUDIT_PATH = locations.incoming_text_audit_path
    TEXT_INSPECTION_DIR = locations.text_inspection_dir
    TEXT_INSPECTION_JSON_DIR = locations.text_inspection_json_dir
    TEXT_INSPECTION_MEDIA_DIR = locations.text_inspection_media_dir
    TEXT_INSPECTION_EXTERNAL_VLM_ENABLED = str(environment.get('VANTALINE_TEXT_INSPECTION_EXTERNAL_VLM_ENABLED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
    TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED = str(environment.get('VANTALINE_TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
    TEXT_INSPECTION_MANUAL_PASS_VERIFIED = str(environment.get('VANTALINE_TEXT_INSPECTION_MANUAL_PASS_VERIFIED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
    TEXT_INSPECTION_DIAGNOSTIC_LOGGER = logging.getLogger('uvicorn.error')
    TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE = 2048
    TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY = 90
    TEXT_INSPECTION_PROVIDER_TIMEOUT_SECONDS = 30.0
    TEXT_INSPECTION_PROMPT_VERSION = 'text-compare-v2-prompt-2'
    INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED = str(environment.get('VANTALINE_INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
    try:
        INCOMING_TEXT_MIN_FREE_BYTES = max(512 * 1024 * 1024, int(environment.get('VANTALINE_INCOMING_TEXT_MIN_FREE_BYTES', str(2 * 1024 * 1024 * 1024))))
    except (TypeError, ValueError):
        INCOMING_TEXT_MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024
    AUTO_OPTIMIZE_DIR = DATA_DIR / 'auto_optimize'
    AI_SUPPORTED_PROVIDERS = {'gemini', 'qwen', 'doubao'}
    AI_DEFAULT_PROVIDER = 'gemini'
    AI_DEFAULT_MODELS = {'gemini': 'gemini-2.5-flash', 'qwen': 'qwen3-vl-flash'}
    AI_DEFAULT_MODEL = AI_DEFAULT_MODELS[AI_DEFAULT_PROVIDER]
    AI_MODEL_OPTIONS = [{'id': 'gemini-2.5-flash-lite', 'label': 'Gemini 2.5 Flash-Lite'}, {'id': 'gemini-2.5-flash', 'label': 'Gemini 2.5 Flash'}, {'id': 'gemini-2.5-pro', 'label': 'Gemini 2.5 Pro'}, {'id': 'gemini-2.0-flash', 'label': 'Gemini 2.0 Flash'}, {'id': 'gemini-3.5-flash', 'label': 'Gemini 3.5 Flash'}, {'id': 'gemini-3.1-flash-image', 'label': 'Gemini 3.1 Flash Image'}, {'id': 'gemini-3-pro-image', 'label': 'Gemini 3 Pro Image'}, {'id': 'qwen3.7-plus', 'label': 'Qwen 3.7 Plus'}, {'id': 'qwen3.7-plus-2026-05-26', 'label': 'Qwen 3.7 Plus 2026-05-26'}, {'id': 'qwen3.6-flash', 'label': 'Qwen 3.6 Flash'}, {'id': 'qwen3.6-flash-2026-04-16', 'label': 'Qwen 3.6 Flash 2026-04-16'}, {'id': 'qwen3-vl-flash', 'label': 'Qwen3 VL Flash'}, {'id': 'qwen3-vl-plus', 'label': 'Qwen3 VL Plus'}, {'id': 'qwen3.7-max', 'label': 'Qwen 3.7 Max'}]
    AI_DEFAULT_BASE_URLS = {'gemini': 'https://generativelanguage.googleapis.com/v1beta', 'qwen': 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions'}
    AI_PROVIDER_LABELS = {'gemini': 'Gemini', 'qwen': 'Qwen'}
    AI_DEFAULT_TIMEOUT_SECONDS = 10.0
    IMAGE_GENERATION_SUPPORTED_PROVIDERS = {'gemini', 'agnes', 'qwen_image'}
    IMAGE_GENERATION_DEFAULT_PROVIDER = 'gemini'
    IMAGE_GENERATION_DEFAULT_MODELS = {'gemini': 'gemini-3.1-flash-image', 'agnes': 'agnes-image-2.0-flash', 'qwen_image': 'qwen-image-2.0-pro'}
    IMAGE_GENERATION_DEFAULT_BASE_URLS = {'gemini': AI_DEFAULT_BASE_URLS['gemini'], 'agnes': 'https://apihub.agnes-ai.com/v1/images/generations', 'qwen_image': 'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'}
    IMAGE_GENERATION_DEFAULT_API_KEY_ENVS = {'gemini': 'GEMINI_IMAGE_API_KEY', 'agnes': 'AGNES_API_KEY', 'qwen_image': 'QWEN_IMAGE_API_KEY'}
    IMAGE_GENERATION_MODEL_OPTIONS = [{'id': 'gemini-3.1-flash-image', 'label': 'Gemini 3.1 Flash Image'}, {'id': 'gemini-3-pro-image', 'label': 'Gemini 3 Pro Image'}, {'id': 'agnes-image-2.0-flash', 'label': 'Agnes Image 2.0 Flash'}, {'id': 'agnes-image-2.1-flash', 'label': 'Agnes Image 2.1 Flash'}, {'id': 'qwen-image-2.0', 'label': 'Qwen Image 2.0'}, {'id': 'qwen-image-2.0-pro', 'label': 'Qwen Image 2.0 Pro'}]
    IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS = 120.0
    IMAGE_GENERATION_PROVIDER_KEYS = {'gemini': 'gemini_native_image_generation', 'agnes': 'agnes_image_generation', 'qwen_image': 'qwen_image_generation'}
    IMAGE_GENERATION_PROVIDER_LABELS = {'gemini': 'Gemini', 'agnes': 'Agnes Image', 'qwen_image': 'Qwen Image'}
    IMAGE_GENERATION_MODEL_ENV = 'VANTALINE_IMAGE_MODEL'
    IMAGE_GENERATION_PROVIDER_ENV = 'VANTALINE_IMAGE_PROVIDER'
    IMAGE_GENERATION_BASE_URL_ENV = 'VANTALINE_IMAGE_BASE_URL'
    IMAGE_GENERATION_API_KEY_ENV = 'VANTALINE_IMAGE_API_KEY'
    IMAGE_GENERATION_NAMED_API_KEY_ENV = 'VANTALINE_IMAGE_API_KEY_ENV'
    IMAGE_GENERATION_TIMEOUT_ENV = 'VANTALINE_IMAGE_TIMEOUT_SECONDS'
    AI_PROXY_ENV_NAMES = ('INSPECTION_AI_PROXY_URL', 'AI_PROVIDER_PROXY_URL', 'HTTPS_PROXY', 'ALL_PROXY')
    AI_AUTO_LOCAL_PROXY_ENV = 'INSPECTION_AI_AUTO_LOCAL_PROXY'
    CURSOR_IMAGE2_PROVIDER = 'cursor_image2'
    WINDOWS_WORKER_IMAGE_PROVIDER = 'windows_worker_image_fallback'
    LOCAL_CODEX_IMAGE_PROVIDER = 'local_codex_image_worker'
    CURSOR_IMAGE2_QUEUE_STATUS = 'queued_for_cursor_image2'
    CODEX_IMAGE_WORKER_QUEUE_STATUS = 'queued_for_codex_image_worker'
    CURSOR_IMAGE2_API_KEY_ENV = 'INSPECTION_CURSOR_IMAGE2_API_KEY'
    CURSOR_IMAGE2_BASE_URL_ENV = 'INSPECTION_CURSOR_IMAGE2_BASE_URL'
    CURSOR_IMAGE2_ENDPOINT_ENV = 'INSPECTION_CURSOR_IMAGE2_ENDPOINT'
    CURSOR_IMAGE2_MODEL_ENV = 'INSPECTION_CURSOR_IMAGE2_MODEL'
    CURSOR_IMAGE2_DEFAULT_MODEL = ''
    CURSOR_IMAGE_MODEL_KEYWORDS = ('image', 'imagen', 'gpt-image', 'dall-e', 'dalle', 'flux', 'stable-diffusion', 'sdxl', 'banana')
    CURSOR_IMAGE_MODEL_PRIORITY = ('nano-banana-pro', 'gpt-image-2', 'gpt-image-1', 'imagen', 'flux')
    STALE_REPO_PATH_PREFIXES = ('/mnt/f/CodexWorkspace/assembly_line_optimize', 'F:/CodexWorkspace/assembly_line_optimize', '/opt/vantalane/app')
    IMAGE_JOB_ACTIVE_STATUSES = {CODEX_IMAGE_WORKER_QUEUE_STATUS, CURSOR_IMAGE2_QUEUE_STATUS, 'queued', 'running'}
    IMAGE_JOB_QUEUED_STATUSES = {CODEX_IMAGE_WORKER_QUEUE_STATUS, CURSOR_IMAGE2_QUEUE_STATUS, 'queued'}
    LEGACY_MODEL_PATH = ROOT / 'yolo26_seg_2class_visible_polygon_4000_full_rotation_trial' / 'runs' / 'yolo26s_seg_2class_visible_polygon_full_rotation_100e_img640_workers0' / 'weights' / 'best.pt'
    REPO_MODEL_PATH = ROOT / 'models' / 'current_2class_yolo26s_seg_best.pt'
    MODEL_PATH = Path(environment.get('INSPECTION_MODEL_PATH', REPO_MODEL_PATH if files.exists(REPO_MODEL_PATH) else LEGACY_MODEL_PATH))
    FIVE_CLASS_MODEL_PATH = ROOT / 'models' / 'current_5class_yolo26s_seg_best.pt'
    DETECT_BASE_MODEL_OVERRIDE = environment.get('INSPECTION_DETECT_BASE_MODEL', '').strip()
    MODEL_CLASS_NAMES = {0: 'bottle', 1: 'manual'}
    MODEL_TO_BUSINESS_CLASS = {0: 0, 1: 1}
    CLASS_NAMES = {0: 'bottle', 1: 'warranty_service_manual', 2: 'battery_instruction_manual', 3: 'download_service_manual', 4: 'service_qr_manual'}
    CLASS_LABELS = {0: 'Bottle', 1: 'Warranty Service Manual', 2: 'Battery Instruction Manual', 3: 'Download Service Manual', 4: 'Service QR Manual'}
    GENERIC_DETECTION_CLASS_NAMES = {0: 'bottle', 1: 'manual', 99: 'manual_unknown'}
    GENERIC_DETECTION_LABELS = {0: 'Bottle', 1: 'Manual', 99: 'Unknown Manual'}
    DEFAULT_MODEL_ID = 'yolo26_2class_ocr'
    AI_DETECTION_MODEL_ID = 'ai_detection'
    AI_DETECTION_TASK_PREFIX = 'ai_detection__task_'
    AI_DETECTION_LABEL = 'AI 检测'
    AI_DETECTION_SYSTEM_PROMPT = 'You are a stateless visual inspection agent for an assembly-line image.\nYou receive one inspection image, a JSON list of required accessory profiles, and optional reference images for those accessories.\nDo not use memory from previous calls. Do not infer from prior images.\nDecide whether each required accessory is visible in this image.\nCount an accessory as present when a substantial, visually identifiable portion is visible, even if the full object is partly outside the frame or mildly occluded.\nOnly mark present=false for partial views when the visible evidence is too small or ambiguous to identify the configured accessory.\nFocus on concrete visual evidence: object shape, material, color, printed text, QR/logo/text fragments, and relative size.\nIf two accessories have the same size or shape, distinguish them by profile-specific visible text, markings, material, color, or geometry.\nUse reference accessory images only to understand what each required accessory looks like; do not count a reference image as presence in the inspection image.\nReturn only JSON that matches the provided schema.\nFor every required accessory, return present=true or present=false.\nUse confidence from 0 to 1. If uncertain, mark present=false unless clear evidence exists.\nInclude count when multiple visible instances are relevant or count is otherwise known.\nIf expected_count is provided, the count must match exactly; visible undercounts and overcounts both fail the rule.\nReturn only compact QA JSON: {"detections":[{"accessory_id":"...","label":"...","present":true,"confidence":0.0,"count":1,"evidence":"..."}],"rule":{"counts":{"...":0}}}.\nDo not include narrative, markdown, summaries, or annotated images.\nDo not invent accessories that are not visible.'
    AI_INSPECTION_IMAGE_MAX_SIDE = int(environment.get('INSPECTION_AI_IMAGE_MAX_SIDE', '960'))
    AI_INSPECTION_IMAGE_QUALITY = int(environment.get('INSPECTION_AI_IMAGE_QUALITY', '72'))
    AI_REFERENCE_IMAGES_PER_ACCESSORY = int(environment.get('INSPECTION_AI_REFERENCE_IMAGES_PER_ACCESSORY', '0'))
    AI_REFERENCE_IMAGE_MAX_SIDE = 512
    AI_REFERENCE_IMAGE_QUALITY = 68
    AI_PROFILE_REFERENCE_IMAGES = 3
    AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE = 1024
    AI_PROFILE_REFERENCE_IMAGE_QUALITY = 78
    AI_PROFILE_REFERENCE_MODE = 'sheet_v1'
    AI_PROFILE_REFERENCE_SHEET_MAX_SIDE = 1600
    AI_PROFILE_REFERENCE_SHEET_QUALITY = 86
    AI_PROFILE_CACHE_TTL_SECONDS = max(300, int(environment.get('INSPECTION_AI_PROFILE_CACHE_TTL_SECONDS', '3600')))
    AI_PROFILE_CACHE_VERSION = 1
    AI_MCP_INSPECTION_IMAGE_DIR = Path(environment.get('INSPECTION_AI_MCP_IMAGE_DIR', '/tmp/alook-inspection-mcp-images'))
    INSPECTION_PREVIEW_MAX_SIDE = max(640, min(2560, int(environment.get('VANTALINE_INSPECTION_PREVIEW_MAX_SIDE', '1280'))))
    INSPECTION_PREVIEW_JPEG_QUALITY = max(50, min(95, int(environment.get('VANTALINE_INSPECTION_PREVIEW_JPEG_QUALITY', '78'))))
    DATA_ANALYSIS_BATCH_LIMIT = 25
    AI_DETECTION_OUTPUT_SCHEMA: dict[str, Any] = {'type': 'object', 'required': ['detections', 'rule'], 'properties': {'rule': {'type': 'object', 'required': ['counts'], 'properties': {'counts': {'type': 'object', 'additionalProperties': {'type': 'integer'}}}}, 'detections': {'type': 'array', 'items': {'type': 'object', 'required': ['accessory_id', 'present', 'confidence'], 'properties': {'accessory_id': {'type': 'string'}, 'label': {'type': 'string'}, 'present': {'type': 'boolean'}, 'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}, 'count': {'type': 'integer', 'minimum': 0}, 'evidence': {'type': 'string'}, 'observed_text': {'type': 'array', 'items': {'type': 'string'}}}}}}}
    AI_MCP_EXTRACTION_POINT = 'call_ai_mcp_tool dispatches in process by default. Set INSPECTION_AI_MCP_RUNTIME=stdio for the legacy stdio MCP subprocess while keeping tool payloads/results unchanged.'
    AI_PROVIDER_MAX_ATTEMPTS = max(1, min(3, int(environment.get('INSPECTION_AI_PROVIDER_MAX_ATTEMPTS', '3'))))
    AI_PROVIDER_RETRY_BACKOFF_SECONDS = max(0.0, min(2.0, float(environment.get('INSPECTION_AI_RETRY_BACKOFF_SECONDS', '0.35'))))
    AI_MCP_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {'accessory.profile.generate': {'description': 'Normalize or provider-generate a reusable accessory profile.', 'input': {'accessory': 'Accessory metadata dict.', 'reference_image_paths': 'Optional image paths. Defaults to bounded accessory images.', 'provider_config': 'Internal AI provider settings.', 'allow_provider': 'False returns deterministic local fallback.'}, 'output': {'profile': 'Normalized profile JSON.', 'status': 'Generation status/debug metadata.'}}, 'accessory.reference.collect': {'description': 'Collect bounded reference image payload descriptors for one accessory.', 'input': {'accessory': 'Accessory metadata dict.', 'accessory_id': 'Optional explicit accessory id.', 'max_images': 'Upper bound for descriptors.'}, 'output': {'references': 'List of image payload descriptors.', 'reference_count': 'Descriptor count.'}}, 'vision.inspect.presence': {'description': 'Inspect one image against required accessory profiles using stateless provider JSON.', 'input': {'inspection_image_bgr': 'In-process image array; remote MCP extraction should pass an image descriptor.', 'required_accessories': 'Normalized required accessory profile payloads.', 'reference_descriptors': 'Descriptors returned by accessory.reference.collect.', 'provider_config': 'Internal AI provider settings.'}, 'output': {'passed': 'Boolean.', 'rule': 'Presence rule JSON.', 'detections': 'Normalized detections.', 'ai': 'Debug metadata.'}}, 'provider.gemini.generate_json': {'description': 'Provider JSON gateway used by profile and inspection tools.', 'input': {'system_prompt': 'Provider system instruction.', 'user_content': 'OpenAI-style text/image parts.', 'provider_config': 'Internal AI provider settings.', 'max_tokens': 'Provider output cap.', 'schema_hint': 'Optional expected output schema.'}, 'output': {'ok': 'Boolean.', 'parsed': 'Parsed JSON on success.', 'latency_ms': 'Provider latency.', 'error': 'Bounded error on failure.'}}}
    MODEL_REGISTRY: dict[str, dict[str, Any]] = {'yolo26_5class_direct': {'id': 'yolo26_5class_direct', 'label': 'YOLO26', 'description': '直接检测 Bottle 和四类说明书，不经过 OCR。', 'path': FIVE_CLASS_MODEL_PATH, 'uses_ocr': False, 'model_class_names': CLASS_NAMES, 'model_to_business_class': {idx: idx for idx in CLASS_NAMES}}, DEFAULT_MODEL_ID: {'id': DEFAULT_MODEL_ID, 'label': 'YOLO26 + PaddleOCR', 'description': '先检测 bottle/manual，再用 PaddleOCR 将说明书分成四类。', 'path': MODEL_PATH, 'uses_ocr': True, 'model_class_names': MODEL_CLASS_NAMES, 'model_to_business_class': MODEL_TO_BUSINESS_CLASS}, AI_DETECTION_MODEL_ID: {'id': AI_DETECTION_MODEL_ID, 'label': AI_DETECTION_LABEL, 'description': '调用无状态多模态代理，按配件画像判断是否存在；不绘制检测框。', 'path': APP_DIR, 'uses_ocr': True, 'variant': 'ai_detection', 'is_ai_detection': True, 'model_class_names': {}, 'model_to_business_class': {}}}
    DEFAULT_CONFIG: dict[str, Any] = {'model_path': str(MODEL_PATH), 'active_model_id': DEFAULT_MODEL_ID, 'image_size': 640, 'confidence_threshold': 0.25, 'required_classes': [0, 1, 2, 3, 4], 'min_counts': {'0': 1, '1': 1, '2': 1, '3': 1, '4': 1}, 'task_rules': {}, 'ocr': {'enabled': True, 'require_manual_types': False, 'manual_types': ['warranty_service', 'battery_instruction', 'download_service', 'service_qr'], 'max_texts_per_manual': 16, 'max_crop_long_side': 750, 'fallback_min_confidence': 0.55}, 'video': {'sample_every_seconds': 1.0, 'max_frames': 80}, 'stream': {'enabled': False, 'source': 'camera', 'url': '', 'status': 'reserved'}, 'accessories': [{'class_id': idx, 'name': CLASS_LABELS[idx], 'status': 'active', 'source_files': []} for idx in CLASS_NAMES], 'training': {'status': 'idle', 'last_requested_at': None, 'note': 'Prototype hook. Dataset generation and training can be wired to the existing synthetic pipeline.', 'selected_accessory_ids': [], 'sample_count': 4000, 'mode': 'yolo_ocr', 'preview_urls': []}}
    DEFAULT_AI_CONFIG: dict[str, Any] = {'provider': AI_DEFAULT_PROVIDER, 'model': AI_DEFAULT_MODEL, 'base_url': AI_DEFAULT_BASE_URLS[AI_DEFAULT_PROVIDER], 'timeout_seconds': AI_DEFAULT_TIMEOUT_SECONDS, 'api_key_env': '', 'api_key': '', 'api_keys': [], 'active_key_id': '', 'proxy_url': '', 'auto_local_proxy': True, 'image_provider': IMAGE_GENERATION_DEFAULT_PROVIDER, 'image_model': IMAGE_GENERATION_DEFAULT_MODELS[IMAGE_GENERATION_DEFAULT_PROVIDER], 'image_base_url': IMAGE_GENERATION_DEFAULT_BASE_URLS[IMAGE_GENERATION_DEFAULT_PROVIDER], 'image_timeout_seconds': IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS, 'image_api_key_env': '', 'image_api_key': '', 'image_api_keys': [], 'image_active_key_id': ''}
    AUTH_SESSION_COOKIE = 'vantaline_session'
    PLC_WORKSTATION_COOKIE = 'vantaline_plc_workstation'
    PLC_WORKSTATION_COOKIE_TTL_SECONDS = 365 * 24 * 60 * 60
    PLC_WEB_SERIAL_JSON_TEST_ENV = 'VANTALINE_PLC_WEB_SERIAL_ALLOW_JSON_TEST'
    AUTH_SESSION_TTL_SECONDS = max(900, int(environment.get('VANTALINE_SESSION_TTL_SECONDS', str(12 * 60 * 60))))
    AUTH_SESSION_PERSIST_INTERVAL_SECONDS = max(30, int(environment.get('VANTALINE_SESSION_PERSIST_INTERVAL_SECONDS', '120')))
    PASSWORD_HASH_ITERATIONS = max(120000, int(environment.get('VANTALINE_PASSWORD_HASH_ITERATIONS', '260000')))
    LOGIN_RATE_LIMIT_WINDOW_SECONDS = max(10, int(environment.get('VANTALINE_LOGIN_RATE_LIMIT_WINDOW_SECONDS', '60')))
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS = max(3, int(environment.get('VANTALINE_LOGIN_RATE_LIMIT_MAX_ATTEMPTS', '5')))
    LOGIN_RATE_LIMIT_LOCKOUT_SECONDS = max(30, int(environment.get('VANTALINE_LOGIN_RATE_LIMIT_LOCKOUT_SECONDS', '300')))
    LEGACY_OWNER_ID = 'legacy_admin'
    SYSTEM_OWNER_ID = 'system'
    AUTO_OPTIMIZE_MASK_MAX_PARALLEL = max(1, min(8, int(environment.get('VANTALINE_AUTO_OPT_MASK_MAX_PARALLEL', '3'))))
    AUTO_OPTIMIZE_MASK_MAX_ATTEMPTS = max(1, min(6, int(environment.get('VANTALINE_AUTO_OPT_MASK_MAX_ATTEMPTS', '3'))))
    AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS = max(0.0, float(environment.get('VANTALINE_AUTO_OPT_MASK_RETRY_BASE_SECONDS', '5')))
    AUTO_OPTIMIZE_MASK_RETRY_MAX_SECONDS = max(AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS, float(environment.get('VANTALINE_AUTO_OPT_MASK_RETRY_MAX_SECONDS', '45')))
    AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT = max(1, min(10, int(environment.get('VANTALINE_AUTO_OPT_REAL_BBOX_SAMPLE_WEIGHT', '3'))))
    AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE = max(0, min(20, int(environment.get('VANTALINE_AUTO_OPT_NEGATIVES_PER_REAL_IMAGE', '3'))))
    MAX_PARALLEL_IMAGE_WORKERS = 2
    IMAGE_WORKER_STALE_SECONDS = max(30, int(environment.get('LOCAL_INSPECTION_IMAGE_WORKER_STALE_SECONDS', '180')))
    IMAGE_WORKER_LOG_TAIL_BYTES = 64000
    WINDOWS_WORKER_STATUS_CACHE_SECONDS = max(2.0, float(environment.get('VANTALINE_WORKER_STATUS_CACHE_SECONDS', '15')))
    IMAGE_REFERENCE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
    VIDEO_REFERENCE_SUFFIXES = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm'}
    MAX_TEXT_ACCESSORY_IMAGES = 2
    MAX_IMAGE_WORKER_INPUTS = 10
    MAX_VIDEO_REFERENCE_FRAMES = 6
    PREVIEW_CACHE_SCHEMA_VERSION = 'preview-cache-v4-object-overlap-material-alpha-scale'
    ANCHOR_POLICY_VERSION = 'anchor-replacement-2026-05-27'
    POSE_ANCHOR_DIR = DATA_DIR / 'anchor_pose_guides'
    POSE_ANCHOR_IMAGES = {'upright': POSE_ANCHOR_DIR / 'endface_9bar_anchor.png', 'lying': POSE_ANCHOR_DIR / 'flat_9bar_anchor.png'}
    POSE_TARGET_GUIDE_IMAGES = {'upright': [POSE_ANCHOR_DIR / 'circle_endface_9target_guide.png'], 'lying': []}
    POSE_COLLECTION_BATCHES: list[tuple[str, str, list[str]]] = [('top_row', '上排三视角', ['top-left', 'top-center', 'top-right']), ('middle_row', '中排三视角', ['middle-left', 'center', 'middle-right']), ('bottom_row', '下排三视角', ['bottom-left', 'bottom-center', 'bottom-right'])]
    MANUAL_TYPE_LABELS = {'warranty_service': 'Warranty Service Manual', 'battery_instruction': 'Battery Instruction Manual', 'download_service': 'Download Service Manual', 'service_qr': 'Service QR Manual'}
    MANUAL_TYPE_CLASS_IDS = {'warranty_service': 1, 'battery_instruction': 2, 'download_service': 3, 'service_qr': 4}
    MANUAL_TYPE_KEYWORDS: dict[str, list[tuple[str, int]]] = {'warranty_service': [('warranty', 8), ('service conditions', 8), ('garantie', 5), ('garantia', 5), ('garancija', 5), ('garanti', 4), ('warunki gwarancji', 5), ('servicebetingelser', 5), ('condiciones de servicio', 5)], 'battery_instruction': [('ge-ps', 10), ('cordless', 7), ('branch chainsaw', 9), ('chainsaw', 6), ('akku', 6), ('battery', 6), ('operating instructions', 5), ('original operating', 5), ('motosega', 5), ('potatura', 4), ('batteridriven', 5), ('podadora', 4), ('elagueuse', 4)], 'download_service': [('download', 10), ('downloading', 10), ('download bereit', 8), ('full operating instructions', 9), ('detailed', 7), ('detailed instruction', 8), ('detailed manual', 8), ('telechargeable', 6), ('scaricabili', 6), ('descargarse', 6), ('ladda ned', 6), ('allalaadimiseks', 5), ('descargat', 5)], 'service_qr': [('larger format', 10), ('larger', 7), ('bigger', 7), ('einhell service', 9), ('eschenstrabe', 10), ('eschenstrasse', 10), ('landau', 8), ('09951', 10), ('service-de', 10), ('larger instructions', 8), ('larger manual', 8), ('format plus grand', 6), ('grobere anleitung', 8), ('gröbere anleitung', 8)]}
    STANDARD_PAPER_SIZES_MM = {'A4': (210.0, 297.0), 'A5': (148.0, 210.0), 'A6': (105.0, 148.0)}
    INSPECTION_CAMERA_HEIGHT_MM = 700.0
    INSPECTION_CAMERA_FRAME_WIDTH_MM = 600.0
    MM_TO_PREVIEW_PX = 1280.0 / INSPECTION_CAMERA_FRAME_WIDTH_MM
    DEFAULT_OBJECT_SIZE_MM = {'length_mm': 170.0, 'width_mm': 38.0, 'height_mm': 38.0}
    SIZE_REFERENCE_OBJECTS: dict[str, dict[str, Any]] = {'a4': {'id': 'a4', 'label': 'A4 纸', 'kind': 'paper', 'long_mm': 297.0, 'short_mm': 210.0, 'note': 'A4 打印纸，长边 297mm、短边 210mm。'}, 'a5': {'id': 'a5', 'label': 'A5 纸', 'kind': 'paper', 'long_mm': 210.0, 'short_mm': 148.0, 'note': 'A5 打印纸，长边 210mm、短边 148mm。'}, 'b5': {'id': 'b5', 'label': 'B5 纸', 'kind': 'paper', 'long_mm': 250.0, 'short_mm': 176.0, 'note': 'B5 打印纸，长边 250mm、短边 176mm。'}, 'ruler': {'id': 'ruler', 'label': '直尺/卷尺', 'kind': 'ruler', 'note': '直尺或卷尺：直接读取其厘米/毫米刻度作为比例尺（1 大格=10mm）。'}}
    DEFAULT_SIZE_REFERENCE = 'a4'
    POSE_COLLECTION_GRID_ENABLED = False
    AGENT_MCP_SPRITE_BUILD_VERSION = 4
    PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION = 2
    PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES = 3
    PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES = 3
    PHOTO_HIGHLIGHT_MASK_MAX_SIDE = 1024
    PHOTO_HIGHLIGHT_MASK_RGB = (0, 255, 0)
    PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS = 3
    CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD = 0.05
    CHROMA_SCREEN_OPTIONS: dict[str, dict[str, Any]] = {'green': {'name': 'green', 'rgb': (0, 255, 0), 'hex': '#00FF00', 'label': 'pure green'}, 'blue': {'name': 'blue', 'rgb': (0, 0, 255), 'hex': '#0000FF', 'label': 'pure blue'}, 'red': {'name': 'red', 'rgb': (255, 0, 0), 'hex': '#FF0000', 'label': 'pure red'}}
    AGENT_MCP_POSE_PLAN_VERSION = 1
    AGENT_MCP_POSE_PLAN_MIN_POSES = 1
    AGENT_MCP_POSE_PLAN_MAX_POSES = 6
    AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE = 0.35
    SOURCE_ASPECT_ELONGATED_MIN_RATIO = 1.35
    UPRIGHT_SCALE_CORRECTION_MIN_RATIO = 1.01
    UPRIGHT_SCALE_CORRECTION_MAX_RATIO = 3.25
    UPRIGHT_SCALE_VISUAL_ADJUSTMENT = 0.8
    PREVIEW_CANVAS_SIZE_PX = (1280, 900)
    DETECTION_MAX_OCCLUSION_FRACTION = 0.85
    DETECTION_MIN_VISIBLE_AREA_PX = 220
    PIPELINE_BG_PLATE_MAX_SIDE = 1280
    PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS = 10
    PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC = 0.35
    PIPELINE_BG_PLATE_TIME_BUDGET_S = 20.0
    PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES = 12
    PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES = 48
    PIPELINE_BG_MATCH_DISTANCE_THRESHOLD = 0.22
    BACKGROUND_ROI_PX = (70, 100, 1210, 800)
    BACKGROUND_DIR = DATA_DIR / 'backgrounds'
    BACKGROUND_SETS_DIR = BACKGROUND_DIR / 'sets'
    BACKGROUND_SETS_MANIFEST = BACKGROUND_DIR / 'background_sets.json'
    DEFAULT_BACKGROUND_IMAGE = BACKGROUND_DIR / 'conveyor_surface_topdown_ai_reference5.png'
    STANDARDIZED_MANUALS_DIR = ROOT / 'standardized_manuals'
    PRECISE_MANUALS_DIR = ROOT / 'manuals_from_individual_sources_precise'
    BACKGROUND_SIZE_MM = {'width_mm': round((BACKGROUND_ROI_PX[2] - BACKGROUND_ROI_PX[0]) / MM_TO_PREVIEW_PX, 2), 'height_mm': round((BACKGROUND_ROI_PX[3] - BACKGROUND_ROI_PX[1]) / MM_TO_PREVIEW_PX, 2), 'mm_per_px': round(1 / MM_TO_PREVIEW_PX, 4), 'px_per_mm': MM_TO_PREVIEW_PX}
    PLC_CONTROL_GENERATION_KEY = 'plc_control_generation'
    PLC_RUNTIME_COORDINATION_KEY = 'plc_runtime_coordination'
    PLC_CAPTURE_RESULTS_KEY = 'plc_capture_results'
    PLC_PROTECTED_CONFIG_KEYS = ('plc', PLC_CONTROL_GENERATION_KEY, 'plc_dispatches', PLC_RUNTIME_COORDINATION_KEY, PLC_CAPTURE_RESULTS_KEY)
    PLC_IO_CONFIG_FIELDS = frozenset(DEFAULT_PLC_CONFIG)
    PLC_DISPATCH_AUDIT_LIMIT = 100
    PLC_QUEUE_WAIT_SECONDS = 2.0
    PLC_WORKER_TOTAL_TIMEOUT_SECONDS = MAX_DISPATCH_WALL_SECONDS + 2.0
    PLC_IO_OWNER_HEARTBEAT_SECONDS = 1.0
    PLC_IO_OWNER_LEASE_SECONDS = 5.0
    PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS = PLC_WORKER_TOTAL_TIMEOUT_SECONDS + 2.0
    PLC_CAPTURE_POLL_SECONDS = 0.2
    PLC_CAPTURE_EVENT_TTL_SECONDS = 1.0
    PLC_CAPTURE_PROCESSING_TTL_SECONDS = max(180.0, PLC_WORKER_TOTAL_TIMEOUT_SECONDS + 60.0)
    PLC_RECORD_SCHEMA_VERSION = 2
    PLC_PROTOCOL_CONTRACT_VERSION = 2
    ACCESSORY_ENGLISH_NAME_FALLBACKS = {'玻璃瓶': 'Glass Bottle', '管子': 'Tube', '耳机': 'Earbuds', '手表': 'Watch', '卷尺': 'Tape Measure', '护目镜': 'Goggles', '记号笔': 'Marker', '剪刀': 'Scissors', '说明书': 'Manual', '充电器': 'Charger', '电池': 'Battery'}
    ACCESSORY_ENGLISH_PHRASES = (('glass bottle', 'Glass Bottle'), ('bottle', 'Bottle'), ('tube', 'Tube'), ('pipe', 'Tube'), ('earbuds', 'Earbuds'), ('earpod', 'Earbuds'), ('earphone', 'Earbuds'), ('headphone', 'Headphones'), ('smartwatch', 'Watch'), ('watch', 'Watch'), ('tape measure', 'Tape Measure'), ('goggles', 'Goggles'), ('marker', 'Marker'), ('scissors', 'Scissors'), ('manual', 'Manual'), ('charger', 'Charger'), ('adapter', 'Charger'), ('battery', 'Battery'))
    ACCESSORY_ENGLISH_NAME_FIELDS = ('english_name', 'display_label', 'display_name_en', 'english_display_name', 'short_english_name', 'box_display_label')
    GENERIC_ENGLISH_NAME_TOKENS = {'a', 'an', 'and', 'accessory', 'clear', 'complete', 'configured', 'cylindrical', 'detect', 'detection', 'for', 'image', 'object', 'physical', 'required', 'target', 'the', 'visible', 'with'}
    STORE_READ_CACHE_TTL_SECONDS = 5.0
    AUTO_OPTIMIZE_MASK_PROMPT_MODE = 'plain_description_v1'
    AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION = 'structured_profile_v1'
    AUTO_OPTIMIZE_MASK_PALETTE = [{'name': 'green', 'hex': '#00FF00', 'rgb': (0, 255, 0), 'bgr': (0, 255, 0)}, {'name': 'blue', 'hex': '#0000FF', 'rgb': (0, 0, 255), 'bgr': (255, 0, 0)}, {'name': 'red', 'hex': '#FF0000', 'rgb': (255, 0, 0), 'bgr': (0, 0, 255)}, {'name': 'yellow', 'hex': '#FFFF00', 'rgb': (255, 255, 0), 'bgr': (0, 255, 255)}, {'name': 'magenta', 'hex': '#FF00FF', 'rgb': (255, 0, 255), 'bgr': (255, 0, 255)}, {'name': 'cyan', 'hex': '#00FFFF', 'rgb': (0, 255, 255), 'bgr': (255, 255, 0)}, {'name': 'orange', 'hex': '#FF8000', 'rgb': (255, 128, 0), 'bgr': (0, 128, 255)}, {'name': 'white', 'hex': '#FFFFFF', 'rgb': (255, 255, 255), 'bgr': (255, 255, 255)}]
    DOCUMENT_LIKE_TEXT_HINTS = ('manual', 'instruction', 'document', 'paper', 'sheet', 'card', '说明', '说明书', '文档', '资料', '卡')
    MASK_VERIFIER_SYSTEM_PROMPT = 'You are VantaLine\'s mask verifier for production inspection training data.\nYou do not generate masks. You inspect whether each colored mask region actually covers the intended target accessory.\nBe strict: a region that covers a sibling accessory, a handle/cap, background, shadow, package, or visually related but wrong object must be rejected.\nUse the target profile and negative candidates. Do not accept a region only because it is near the target or has a similar color.\nReturn only compact JSON with this shape:\n{"targets":[{"accessory_id":"...","mask_region_matches_target":true,"identity_score":0.0,"localization_score":0.0,"negative_match_score":0.0,"wrong_object_evidence":[],"decision":"accept|review|reject","reason":"..."}],"overall_decision":"accept|review|reject"}.\n'
    AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY = 'canonical_real_mask_bbox_canvas_scale_v3'
    AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE = (1280, 900)
    AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE = max(1.0, float(environment.get('VANTALINE_AUTO_OPT_SYNTHETIC_MAX_UPSCALE', '3.0')))
    STATUS_MODEL_PUBLIC_KEYS = {'id', 'label', 'description', 'variant', 'uses_ocr', 'is_legacy', 'is_ai_detection', 'is_label_sheet_match', 'exists', 'run_id', 'task_id', 'task_label', 'task_source', 'confidence_threshold', 'required_accessory_counts', 'accessory_labels', 'accessory_class_map', 'ocr_accessory_ids', 'accessory_names', 'selected_accessory_ids', 'missing_accessory_ids', 'created_at', 'updated_at', 'owner_user_id', 'owner_username'}
    POSE_COLLECTION_GRID_POSITIONS = ['top-left', 'top-center', 'top-right', 'middle-left', 'center', 'middle-right', 'bottom-left', 'bottom-center', 'bottom-right']
    UPRIGHT_TOP_VIEW_SOURCE_POSITIONS = ('center', 'bottom-center')
    CODEX_IMAGE_JOB_PERSISTED_KEYS = ('status', 'progress', 'completed_at', 'failed_at', 'stopped_at', 'error', 'output_path', 'output_url', 'log_path', 'provider', 'generation_method', 'generation_step', 'queue_kind', 'note', 'task_id', 'job_id', 'candidate_id')
    WORKER_BUNDLE_SKIP_DIRS = {'previews', 'preview', 'debug', 'thumbnails', 'thumbs'}
    WORKER_BUNDLE_JPEG_QUALITY = 90
    OCR_ACCESSORY_MATCH_MIN_TEXT_SCORE = 0.65
    OCR_ACCESSORY_MATCH_MIN_CONFIDENCE = 0.6
    OCR_ACCESSORY_MATCH_MIN_MARGIN = 0.15
    OCR_ACCESSORY_PROFILE_STOPWORDS = {'accessory', 'document', 'documentation', 'instruction', 'instructions', 'label', 'manual', 'paper', 'product', 'text', 'and', 'back', 'cover', 'for', 'from', 'image', 'images', 'shows', 'the', 'that', 'this', 'white', 'with'}
    PIPELINE_TASKS_PATH = DATA_DIR / 'pipeline_tasks.json'
    AGENT_LOCAL_CONFIG_PATH = DATA_DIR / 'agent_config.local.json'
    PIPELINE_STATE_PATH = DATA_DIR / 'pipeline_state.json'
    AGENT_PROVIDER_OPENAI_COMPATIBLE = 'openai_compatible'
    AGENT_PROVIDER_CURSOR = 'cursor'
    AGENT_SUPPORTED_PROVIDERS = {AGENT_PROVIDER_OPENAI_COMPATIBLE, AGENT_PROVIDER_CURSOR}
    AGENT_CURSOR_DEFAULT_BASE_URL = 'https://api.cursor.com'
    AGENT_CONNECTION_STATUSES = {'untested', 'connected', 'failed'}
    AGENT_CURSOR_RECOMMENDATION_MESSAGE = 'Cursor 已连接；参数推荐需要 Cursor Cloud Agent run 配置，当前使用规则推荐'
    DEFAULT_AGENT_CONFIG: dict[str, Any] = {'enabled': True, 'provider': AGENT_PROVIDER_OPENAI_COMPATIBLE, 'base_url': '', 'api_key_env': '', 'api_keys': [], 'active_key_id': '', 'api_key': '', 'model': '', 'model_options': [], 'timeout_seconds': 45.0, 'auto_advance_default': True, 'connection_status': 'untested', 'connection_message': '', 'last_tested_at': 0, 'last_model_count': 0}
    ACCESSORY_DETECTION_ROUTES = {'yolo', 'ai', 'archive_only'}
    PIPELINE_DETECTION_METHODS = {'yolo', 'yolo_ocr', 'ai', 'label_text_compare'}
    PIPELINE_TRAINING_METHODS = {'yolo', 'yolo_ocr'}
    PIPELINE_STAGE_ORDER = ['draft', 'samples', 'training', 'library']
    PIPELINE_DASHBOARD_AI_TASK_SOURCE = 'pipeline_dashboard'
    AGENT_MCP_ORCHESTRATION_VERSION = 'agent-mcp-yolo-preview-v1'
    AGENT_MCP_GEMINI_IMAGE_MODEL_ENV = 'VANTALINE_GEMINI_IMAGE_MODEL'
    AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV = 'VANTALINE_GEMINI_IMAGE_TIMEOUT_SECONDS'
    AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL = 'gemini-3.1-flash-image'
    AGENT_MCP_GEMINI_IMAGE_HIGH_FIDELITY_MODEL = 'gemini-3-pro-image'
    AGENT_MCP_GEMINI_IMAGE_DEFAULT_TIMEOUT_SECONDS = 120.0
    AGENT_MCP_TOOL_POSE_IMAGE = 'generate_accessory_pose_image'
    AGENT_MCP_TOOL_SAMPLES = 'generate_training_samples'
    AGENT_MCP_TOOL_TRAINING = 'start_model_training'
    AGENT_MCP_CONVERSATION_LIMIT = 60
    AGENT_MCP_AUTO_MAX_STEPS = 12
    AGENT_PIPELINE_ACTIONS = {'advance', 'set_params', 'goto_stage', 'retry', 'replan', 'pause_and_ask', 'continue_existing_assets', 'continue_training', 'cancel', 'reply'}
    AGENT_PIPELINE_STAGE_TARGETS = {'draft', 'samples'}
    PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S = 600
    AGENT_PIPELINE_SYSTEM_PROMPT = '你是工业视觉质检平台的任务流水线主导 Agent。目标：除上传素材与指定任务外，让用户尽量不手动调参，由你自主推动 draft→samples→training→library 全流程，并在合适时机用自然语言与用户沟通。你会收到任务当前状态、配件信息、编排阶段、质量信号、最近对话以及用户最新消息（可能为空，表示自动巡检触发）。请只输出一个 JSON 对象，不要输出多余文本。可用 action 含义：advance=推进到下一阶段（仅当前阶段已完成）；set_params=调整训练参数(sample_count/epochs/image_size/train_mode)，可带 advance_after=true 立即推进；goto_stage=回退到更早阶段重做(target_stage 取 draft 改配件/参数, samples 重新生成样本)；retry=重试实拍高亮抠图素材生成；replan=重新准备实拍高亮抠图素材；pause_and_ask=暂停并主动联系用户(仅当任务复杂、有风险或质量存疑时使用，必须给出 message_to_user 与 suggested_actions)；continue_existing_assets=沿用现有实拍抠图素材继续；continue_training=确认样本质量进入训练；cancel=取消任务；reply=仅回答用户、不改变状态。尽量自主决策、保持流程推进；只有真正需要用户决定时才 pause_and_ask。JSON 字段：{"action": str, "params": {"sample_count": int, "epochs": int, "image_size": int, "train_mode": "yolo"|"yolo_ocr"}, "advance_after": bool, "target_stage": "draft"|"samples", "needs_user": bool, "message_to_user": "面向用户的中文回复", "reason": "一句话中文决策理由", "suggested_actions": [str]}。message_to_user 与 reason 必填，参数需落在给定 constraints 范围内。'
    PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS = 5.0
    TEXT_COMPARE_BETA_MAX_BYTES = 10 * 1024 * 1024
    TEXT_COMPARE_BETA_MAX_PIXELS = 16000000
    TEXT_COMPARE_BETA_CACHE_TTL_SECONDS = 3600
    TEXT_COMPARE_BETA_CACHE_MAX_BYTES = 32 * 1024 * 1024
    DASHBOARD_AI_TASK_NAME = 'Dashboard 快捷 AI 检测'
    REACT_PRODUCTION_ROUTE_SEGMENTS = {'workspace', 'docs', 'text-compare-beta', 'login', 'status', 'inspect', 'ai-inspect', 'accessories', 'training-library', 'tasks', 'pipeline', 'rules', 'users', 'data-analysis'}
    REACT_PRODUCTION_BLOCKED_PREFIXES = ('/api/', '/static/', '/outputs/', '/react-preview', '/legacy', '/favicon', '/apple-touch-icon', '/site.webmanifest')
    return ApplicationValues(
        ROOT=ROOT,
        APP_DIR=APP_DIR,
        STATIC_DIR=STATIC_DIR,
        REACT_PREVIEW_DIST_DIR=REACT_PREVIEW_DIST_DIR,
        REACT_PREVIEW_ASSETS_DIR=REACT_PREVIEW_ASSETS_DIR,
        REACT_PRODUCTION_DIST_DIR=REACT_PRODUCTION_DIST_DIR,
        REACT_PRODUCTION_ASSETS_DIR=REACT_PRODUCTION_ASSETS_DIR,
        DATA_DIR=DATA_DIR,
        UPLOAD_DIR=UPLOAD_DIR,
        OUTPUT_DIR=OUTPUT_DIR,
        NORMALIZED_DIR=NORMALIZED_DIR,
        TRAINING_JOBS_DIR=TRAINING_JOBS_DIR,
        TRAINING_TASKS_DIR=TRAINING_TASKS_DIR,
        ACCESSORY_CANDIDATES_DIR=ACCESSORY_CANDIDATES_DIR,
        IMAGE_WORKER_LOG_DIR=IMAGE_WORKER_LOG_DIR,
        CONFIG_PATH=CONFIG_PATH,
        CONFIG_BACKUP_PATH=CONFIG_BACKUP_PATH,
        PLC_WEB_SERIAL_STATE_PATH=PLC_WEB_SERIAL_STATE_PATH,
        AI_LOCAL_CONFIG_PATH=AI_LOCAL_CONFIG_PATH,
        LOCAL_SECRET_ENV_PATH=LOCAL_SECRET_ENV_PATH,
        AI_PROFILE_CACHE_PATH=AI_PROFILE_CACHE_PATH,
        AI_DETECTION_TASKS_PATH=AI_DETECTION_TASKS_PATH,
        AUTH_PATH=AUTH_PATH,
        DATA_ANALYSIS_RECORDS_PATH=DATA_ANALYSIS_RECORDS_PATH,
        INCOMING_TEXT_REFERENCES_PATH=INCOMING_TEXT_REFERENCES_PATH,
        INCOMING_TEXT_INSPECTIONS_PATH=INCOMING_TEXT_INSPECTIONS_PATH,
        INCOMING_TEXT_AUDIT_PATH=INCOMING_TEXT_AUDIT_PATH,
        TEXT_INSPECTION_DIR=TEXT_INSPECTION_DIR,
        TEXT_INSPECTION_JSON_DIR=TEXT_INSPECTION_JSON_DIR,
        TEXT_INSPECTION_MEDIA_DIR=TEXT_INSPECTION_MEDIA_DIR,
        TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=TEXT_INSPECTION_EXTERNAL_VLM_ENABLED,
        TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED=TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED,
        TEXT_INSPECTION_MANUAL_PASS_VERIFIED=TEXT_INSPECTION_MANUAL_PASS_VERIFIED,
        TEXT_INSPECTION_DIAGNOSTIC_LOGGER=TEXT_INSPECTION_DIAGNOSTIC_LOGGER,
        TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE=TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE,
        TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY=TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY,
        TEXT_INSPECTION_PROVIDER_TIMEOUT_SECONDS=TEXT_INSPECTION_PROVIDER_TIMEOUT_SECONDS,
        TEXT_INSPECTION_PROMPT_VERSION=TEXT_INSPECTION_PROMPT_VERSION,
        INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED=INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED,
        INCOMING_TEXT_MIN_FREE_BYTES=INCOMING_TEXT_MIN_FREE_BYTES,
        AUTO_OPTIMIZE_DIR=AUTO_OPTIMIZE_DIR,
        AI_SUPPORTED_PROVIDERS=AI_SUPPORTED_PROVIDERS,
        AI_DEFAULT_PROVIDER=AI_DEFAULT_PROVIDER,
        AI_DEFAULT_MODELS=AI_DEFAULT_MODELS,
        AI_DEFAULT_MODEL=AI_DEFAULT_MODEL,
        AI_MODEL_OPTIONS=AI_MODEL_OPTIONS,
        AI_DEFAULT_BASE_URLS=AI_DEFAULT_BASE_URLS,
        AI_PROVIDER_LABELS=AI_PROVIDER_LABELS,
        AI_DEFAULT_TIMEOUT_SECONDS=AI_DEFAULT_TIMEOUT_SECONDS,
        IMAGE_GENERATION_SUPPORTED_PROVIDERS=IMAGE_GENERATION_SUPPORTED_PROVIDERS,
        IMAGE_GENERATION_DEFAULT_PROVIDER=IMAGE_GENERATION_DEFAULT_PROVIDER,
        IMAGE_GENERATION_DEFAULT_MODELS=IMAGE_GENERATION_DEFAULT_MODELS,
        IMAGE_GENERATION_DEFAULT_BASE_URLS=IMAGE_GENERATION_DEFAULT_BASE_URLS,
        IMAGE_GENERATION_DEFAULT_API_KEY_ENVS=IMAGE_GENERATION_DEFAULT_API_KEY_ENVS,
        IMAGE_GENERATION_MODEL_OPTIONS=IMAGE_GENERATION_MODEL_OPTIONS,
        IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS=IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS,
        IMAGE_GENERATION_PROVIDER_KEYS=IMAGE_GENERATION_PROVIDER_KEYS,
        IMAGE_GENERATION_PROVIDER_LABELS=IMAGE_GENERATION_PROVIDER_LABELS,
        IMAGE_GENERATION_MODEL_ENV=IMAGE_GENERATION_MODEL_ENV,
        IMAGE_GENERATION_PROVIDER_ENV=IMAGE_GENERATION_PROVIDER_ENV,
        IMAGE_GENERATION_BASE_URL_ENV=IMAGE_GENERATION_BASE_URL_ENV,
        IMAGE_GENERATION_API_KEY_ENV=IMAGE_GENERATION_API_KEY_ENV,
        IMAGE_GENERATION_NAMED_API_KEY_ENV=IMAGE_GENERATION_NAMED_API_KEY_ENV,
        IMAGE_GENERATION_TIMEOUT_ENV=IMAGE_GENERATION_TIMEOUT_ENV,
        AI_PROXY_ENV_NAMES=AI_PROXY_ENV_NAMES,
        AI_AUTO_LOCAL_PROXY_ENV=AI_AUTO_LOCAL_PROXY_ENV,
        CURSOR_IMAGE2_PROVIDER=CURSOR_IMAGE2_PROVIDER,
        WINDOWS_WORKER_IMAGE_PROVIDER=WINDOWS_WORKER_IMAGE_PROVIDER,
        LOCAL_CODEX_IMAGE_PROVIDER=LOCAL_CODEX_IMAGE_PROVIDER,
        CURSOR_IMAGE2_QUEUE_STATUS=CURSOR_IMAGE2_QUEUE_STATUS,
        CODEX_IMAGE_WORKER_QUEUE_STATUS=CODEX_IMAGE_WORKER_QUEUE_STATUS,
        CURSOR_IMAGE2_API_KEY_ENV=CURSOR_IMAGE2_API_KEY_ENV,
        CURSOR_IMAGE2_BASE_URL_ENV=CURSOR_IMAGE2_BASE_URL_ENV,
        CURSOR_IMAGE2_ENDPOINT_ENV=CURSOR_IMAGE2_ENDPOINT_ENV,
        CURSOR_IMAGE2_MODEL_ENV=CURSOR_IMAGE2_MODEL_ENV,
        CURSOR_IMAGE2_DEFAULT_MODEL=CURSOR_IMAGE2_DEFAULT_MODEL,
        CURSOR_IMAGE_MODEL_KEYWORDS=CURSOR_IMAGE_MODEL_KEYWORDS,
        CURSOR_IMAGE_MODEL_PRIORITY=CURSOR_IMAGE_MODEL_PRIORITY,
        STALE_REPO_PATH_PREFIXES=STALE_REPO_PATH_PREFIXES,
        IMAGE_JOB_ACTIVE_STATUSES=IMAGE_JOB_ACTIVE_STATUSES,
        IMAGE_JOB_QUEUED_STATUSES=IMAGE_JOB_QUEUED_STATUSES,
        LEGACY_MODEL_PATH=LEGACY_MODEL_PATH,
        REPO_MODEL_PATH=REPO_MODEL_PATH,
        MODEL_PATH=MODEL_PATH,
        FIVE_CLASS_MODEL_PATH=FIVE_CLASS_MODEL_PATH,
        DETECT_BASE_MODEL_OVERRIDE=DETECT_BASE_MODEL_OVERRIDE,
        MODEL_CLASS_NAMES=MODEL_CLASS_NAMES,
        MODEL_TO_BUSINESS_CLASS=MODEL_TO_BUSINESS_CLASS,
        CLASS_NAMES=CLASS_NAMES,
        CLASS_LABELS=CLASS_LABELS,
        GENERIC_DETECTION_CLASS_NAMES=GENERIC_DETECTION_CLASS_NAMES,
        GENERIC_DETECTION_LABELS=GENERIC_DETECTION_LABELS,
        DEFAULT_MODEL_ID=DEFAULT_MODEL_ID,
        AI_DETECTION_MODEL_ID=AI_DETECTION_MODEL_ID,
        AI_DETECTION_TASK_PREFIX=AI_DETECTION_TASK_PREFIX,
        AI_DETECTION_LABEL=AI_DETECTION_LABEL,
        AI_DETECTION_SYSTEM_PROMPT=AI_DETECTION_SYSTEM_PROMPT,
        AI_INSPECTION_IMAGE_MAX_SIDE=AI_INSPECTION_IMAGE_MAX_SIDE,
        AI_INSPECTION_IMAGE_QUALITY=AI_INSPECTION_IMAGE_QUALITY,
        AI_REFERENCE_IMAGES_PER_ACCESSORY=AI_REFERENCE_IMAGES_PER_ACCESSORY,
        AI_REFERENCE_IMAGE_MAX_SIDE=AI_REFERENCE_IMAGE_MAX_SIDE,
        AI_REFERENCE_IMAGE_QUALITY=AI_REFERENCE_IMAGE_QUALITY,
        AI_PROFILE_REFERENCE_IMAGES=AI_PROFILE_REFERENCE_IMAGES,
        AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE=AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE,
        AI_PROFILE_REFERENCE_IMAGE_QUALITY=AI_PROFILE_REFERENCE_IMAGE_QUALITY,
        AI_PROFILE_REFERENCE_MODE=AI_PROFILE_REFERENCE_MODE,
        AI_PROFILE_REFERENCE_SHEET_MAX_SIDE=AI_PROFILE_REFERENCE_SHEET_MAX_SIDE,
        AI_PROFILE_REFERENCE_SHEET_QUALITY=AI_PROFILE_REFERENCE_SHEET_QUALITY,
        AI_PROFILE_CACHE_TTL_SECONDS=AI_PROFILE_CACHE_TTL_SECONDS,
        AI_PROFILE_CACHE_VERSION=AI_PROFILE_CACHE_VERSION,
        AI_MCP_INSPECTION_IMAGE_DIR=AI_MCP_INSPECTION_IMAGE_DIR,
        INSPECTION_PREVIEW_MAX_SIDE=INSPECTION_PREVIEW_MAX_SIDE,
        INSPECTION_PREVIEW_JPEG_QUALITY=INSPECTION_PREVIEW_JPEG_QUALITY,
        DATA_ANALYSIS_BATCH_LIMIT=DATA_ANALYSIS_BATCH_LIMIT,
        AI_DETECTION_OUTPUT_SCHEMA=AI_DETECTION_OUTPUT_SCHEMA,
        AI_MCP_EXTRACTION_POINT=AI_MCP_EXTRACTION_POINT,
        AI_PROVIDER_MAX_ATTEMPTS=AI_PROVIDER_MAX_ATTEMPTS,
        AI_PROVIDER_RETRY_BACKOFF_SECONDS=AI_PROVIDER_RETRY_BACKOFF_SECONDS,
        AI_MCP_TOOL_DEFINITIONS=AI_MCP_TOOL_DEFINITIONS,
        MODEL_REGISTRY=MODEL_REGISTRY,
        DEFAULT_CONFIG=DEFAULT_CONFIG,
        DEFAULT_AI_CONFIG=DEFAULT_AI_CONFIG,
        AUTH_SESSION_COOKIE=AUTH_SESSION_COOKIE,
        PLC_WORKSTATION_COOKIE=PLC_WORKSTATION_COOKIE,
        PLC_WORKSTATION_COOKIE_TTL_SECONDS=PLC_WORKSTATION_COOKIE_TTL_SECONDS,
        PLC_WEB_SERIAL_JSON_TEST_ENV=PLC_WEB_SERIAL_JSON_TEST_ENV,
        AUTH_SESSION_TTL_SECONDS=AUTH_SESSION_TTL_SECONDS,
        AUTH_SESSION_PERSIST_INTERVAL_SECONDS=AUTH_SESSION_PERSIST_INTERVAL_SECONDS,
        PASSWORD_HASH_ITERATIONS=PASSWORD_HASH_ITERATIONS,
        LOGIN_RATE_LIMIT_WINDOW_SECONDS=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        LOGIN_RATE_LIMIT_MAX_ATTEMPTS=LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
        LOGIN_RATE_LIMIT_LOCKOUT_SECONDS=LOGIN_RATE_LIMIT_LOCKOUT_SECONDS,
        LEGACY_OWNER_ID=LEGACY_OWNER_ID,
        SYSTEM_OWNER_ID=SYSTEM_OWNER_ID,
        AUTO_OPTIMIZE_MASK_MAX_PARALLEL=AUTO_OPTIMIZE_MASK_MAX_PARALLEL,
        AUTO_OPTIMIZE_MASK_MAX_ATTEMPTS=AUTO_OPTIMIZE_MASK_MAX_ATTEMPTS,
        AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS=AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS,
        AUTO_OPTIMIZE_MASK_RETRY_MAX_SECONDS=AUTO_OPTIMIZE_MASK_RETRY_MAX_SECONDS,
        AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT=AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT,
        AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE=AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE,
        MAX_PARALLEL_IMAGE_WORKERS=MAX_PARALLEL_IMAGE_WORKERS,
        IMAGE_WORKER_STALE_SECONDS=IMAGE_WORKER_STALE_SECONDS,
        IMAGE_WORKER_LOG_TAIL_BYTES=IMAGE_WORKER_LOG_TAIL_BYTES,
        WINDOWS_WORKER_STATUS_CACHE_SECONDS=WINDOWS_WORKER_STATUS_CACHE_SECONDS,
        IMAGE_REFERENCE_SUFFIXES=IMAGE_REFERENCE_SUFFIXES,
        VIDEO_REFERENCE_SUFFIXES=VIDEO_REFERENCE_SUFFIXES,
        MAX_TEXT_ACCESSORY_IMAGES=MAX_TEXT_ACCESSORY_IMAGES,
        MAX_IMAGE_WORKER_INPUTS=MAX_IMAGE_WORKER_INPUTS,
        MAX_VIDEO_REFERENCE_FRAMES=MAX_VIDEO_REFERENCE_FRAMES,
        PREVIEW_CACHE_SCHEMA_VERSION=PREVIEW_CACHE_SCHEMA_VERSION,
        ANCHOR_POLICY_VERSION=ANCHOR_POLICY_VERSION,
        POSE_ANCHOR_DIR=POSE_ANCHOR_DIR,
        POSE_ANCHOR_IMAGES=POSE_ANCHOR_IMAGES,
        POSE_TARGET_GUIDE_IMAGES=POSE_TARGET_GUIDE_IMAGES,
        POSE_COLLECTION_BATCHES=POSE_COLLECTION_BATCHES,
        MANUAL_TYPE_LABELS=MANUAL_TYPE_LABELS,
        MANUAL_TYPE_CLASS_IDS=MANUAL_TYPE_CLASS_IDS,
        MANUAL_TYPE_KEYWORDS=MANUAL_TYPE_KEYWORDS,
        STANDARD_PAPER_SIZES_MM=STANDARD_PAPER_SIZES_MM,
        INSPECTION_CAMERA_HEIGHT_MM=INSPECTION_CAMERA_HEIGHT_MM,
        INSPECTION_CAMERA_FRAME_WIDTH_MM=INSPECTION_CAMERA_FRAME_WIDTH_MM,
        MM_TO_PREVIEW_PX=MM_TO_PREVIEW_PX,
        DEFAULT_OBJECT_SIZE_MM=DEFAULT_OBJECT_SIZE_MM,
        SIZE_REFERENCE_OBJECTS=SIZE_REFERENCE_OBJECTS,
        DEFAULT_SIZE_REFERENCE=DEFAULT_SIZE_REFERENCE,
        POSE_COLLECTION_GRID_ENABLED=POSE_COLLECTION_GRID_ENABLED,
        AGENT_MCP_SPRITE_BUILD_VERSION=AGENT_MCP_SPRITE_BUILD_VERSION,
        PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION=PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION,
        PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES=PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES,
        PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES=PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES,
        PHOTO_HIGHLIGHT_MASK_MAX_SIDE=PHOTO_HIGHLIGHT_MASK_MAX_SIDE,
        PHOTO_HIGHLIGHT_MASK_RGB=PHOTO_HIGHLIGHT_MASK_RGB,
        PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS=PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS,
        CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD=CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD,
        CHROMA_SCREEN_OPTIONS=CHROMA_SCREEN_OPTIONS,
        AGENT_MCP_POSE_PLAN_VERSION=AGENT_MCP_POSE_PLAN_VERSION,
        AGENT_MCP_POSE_PLAN_MIN_POSES=AGENT_MCP_POSE_PLAN_MIN_POSES,
        AGENT_MCP_POSE_PLAN_MAX_POSES=AGENT_MCP_POSE_PLAN_MAX_POSES,
        AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE=AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE,
        SOURCE_ASPECT_ELONGATED_MIN_RATIO=SOURCE_ASPECT_ELONGATED_MIN_RATIO,
        UPRIGHT_SCALE_CORRECTION_MIN_RATIO=UPRIGHT_SCALE_CORRECTION_MIN_RATIO,
        UPRIGHT_SCALE_CORRECTION_MAX_RATIO=UPRIGHT_SCALE_CORRECTION_MAX_RATIO,
        UPRIGHT_SCALE_VISUAL_ADJUSTMENT=UPRIGHT_SCALE_VISUAL_ADJUSTMENT,
        PREVIEW_CANVAS_SIZE_PX=PREVIEW_CANVAS_SIZE_PX,
        DETECTION_MAX_OCCLUSION_FRACTION=DETECTION_MAX_OCCLUSION_FRACTION,
        DETECTION_MIN_VISIBLE_AREA_PX=DETECTION_MIN_VISIBLE_AREA_PX,
        PIPELINE_BG_PLATE_MAX_SIDE=PIPELINE_BG_PLATE_MAX_SIDE,
        PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS=PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS,
        PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC=PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC,
        PIPELINE_BG_PLATE_TIME_BUDGET_S=PIPELINE_BG_PLATE_TIME_BUDGET_S,
        PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES=PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES,
        PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES=PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES,
        PIPELINE_BG_MATCH_DISTANCE_THRESHOLD=PIPELINE_BG_MATCH_DISTANCE_THRESHOLD,
        BACKGROUND_ROI_PX=BACKGROUND_ROI_PX,
        BACKGROUND_DIR=BACKGROUND_DIR,
        BACKGROUND_SETS_DIR=BACKGROUND_SETS_DIR,
        BACKGROUND_SETS_MANIFEST=BACKGROUND_SETS_MANIFEST,
        DEFAULT_BACKGROUND_IMAGE=DEFAULT_BACKGROUND_IMAGE,
        STANDARDIZED_MANUALS_DIR=STANDARDIZED_MANUALS_DIR,
        PRECISE_MANUALS_DIR=PRECISE_MANUALS_DIR,
        BACKGROUND_SIZE_MM=BACKGROUND_SIZE_MM,
        PLC_CONTROL_GENERATION_KEY=PLC_CONTROL_GENERATION_KEY,
        PLC_RUNTIME_COORDINATION_KEY=PLC_RUNTIME_COORDINATION_KEY,
        PLC_CAPTURE_RESULTS_KEY=PLC_CAPTURE_RESULTS_KEY,
        PLC_PROTECTED_CONFIG_KEYS=PLC_PROTECTED_CONFIG_KEYS,
        PLC_IO_CONFIG_FIELDS=PLC_IO_CONFIG_FIELDS,
        PLC_DISPATCH_AUDIT_LIMIT=PLC_DISPATCH_AUDIT_LIMIT,
        PLC_QUEUE_WAIT_SECONDS=PLC_QUEUE_WAIT_SECONDS,
        PLC_WORKER_TOTAL_TIMEOUT_SECONDS=PLC_WORKER_TOTAL_TIMEOUT_SECONDS,
        PLC_IO_OWNER_HEARTBEAT_SECONDS=PLC_IO_OWNER_HEARTBEAT_SECONDS,
        PLC_IO_OWNER_LEASE_SECONDS=PLC_IO_OWNER_LEASE_SECONDS,
        PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS=PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS,
        PLC_CAPTURE_POLL_SECONDS=PLC_CAPTURE_POLL_SECONDS,
        PLC_CAPTURE_EVENT_TTL_SECONDS=PLC_CAPTURE_EVENT_TTL_SECONDS,
        PLC_CAPTURE_PROCESSING_TTL_SECONDS=PLC_CAPTURE_PROCESSING_TTL_SECONDS,
        PLC_RECORD_SCHEMA_VERSION=PLC_RECORD_SCHEMA_VERSION,
        PLC_PROTOCOL_CONTRACT_VERSION=PLC_PROTOCOL_CONTRACT_VERSION,
        ACCESSORY_ENGLISH_NAME_FALLBACKS=ACCESSORY_ENGLISH_NAME_FALLBACKS,
        ACCESSORY_ENGLISH_PHRASES=ACCESSORY_ENGLISH_PHRASES,
        ACCESSORY_ENGLISH_NAME_FIELDS=ACCESSORY_ENGLISH_NAME_FIELDS,
        GENERIC_ENGLISH_NAME_TOKENS=GENERIC_ENGLISH_NAME_TOKENS,
        STORE_READ_CACHE_TTL_SECONDS=STORE_READ_CACHE_TTL_SECONDS,
        AUTO_OPTIMIZE_MASK_PROMPT_MODE=AUTO_OPTIMIZE_MASK_PROMPT_MODE,
        AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION=AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION,
        AUTO_OPTIMIZE_MASK_PALETTE=AUTO_OPTIMIZE_MASK_PALETTE,
        DOCUMENT_LIKE_TEXT_HINTS=DOCUMENT_LIKE_TEXT_HINTS,
        MASK_VERIFIER_SYSTEM_PROMPT=MASK_VERIFIER_SYSTEM_PROMPT,
        AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY=AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY,
        AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE=AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE,
        AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE=AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE,
        STATUS_MODEL_PUBLIC_KEYS=STATUS_MODEL_PUBLIC_KEYS,
        POSE_COLLECTION_GRID_POSITIONS=POSE_COLLECTION_GRID_POSITIONS,
        UPRIGHT_TOP_VIEW_SOURCE_POSITIONS=UPRIGHT_TOP_VIEW_SOURCE_POSITIONS,
        CODEX_IMAGE_JOB_PERSISTED_KEYS=CODEX_IMAGE_JOB_PERSISTED_KEYS,
        WORKER_BUNDLE_SKIP_DIRS=WORKER_BUNDLE_SKIP_DIRS,
        WORKER_BUNDLE_JPEG_QUALITY=WORKER_BUNDLE_JPEG_QUALITY,
        OCR_ACCESSORY_MATCH_MIN_TEXT_SCORE=OCR_ACCESSORY_MATCH_MIN_TEXT_SCORE,
        OCR_ACCESSORY_MATCH_MIN_CONFIDENCE=OCR_ACCESSORY_MATCH_MIN_CONFIDENCE,
        OCR_ACCESSORY_MATCH_MIN_MARGIN=OCR_ACCESSORY_MATCH_MIN_MARGIN,
        OCR_ACCESSORY_PROFILE_STOPWORDS=OCR_ACCESSORY_PROFILE_STOPWORDS,
        PIPELINE_TASKS_PATH=PIPELINE_TASKS_PATH,
        AGENT_LOCAL_CONFIG_PATH=AGENT_LOCAL_CONFIG_PATH,
        PIPELINE_STATE_PATH=PIPELINE_STATE_PATH,
        AGENT_PROVIDER_OPENAI_COMPATIBLE=AGENT_PROVIDER_OPENAI_COMPATIBLE,
        AGENT_PROVIDER_CURSOR=AGENT_PROVIDER_CURSOR,
        AGENT_SUPPORTED_PROVIDERS=AGENT_SUPPORTED_PROVIDERS,
        AGENT_CURSOR_DEFAULT_BASE_URL=AGENT_CURSOR_DEFAULT_BASE_URL,
        AGENT_CONNECTION_STATUSES=AGENT_CONNECTION_STATUSES,
        AGENT_CURSOR_RECOMMENDATION_MESSAGE=AGENT_CURSOR_RECOMMENDATION_MESSAGE,
        DEFAULT_AGENT_CONFIG=DEFAULT_AGENT_CONFIG,
        ACCESSORY_DETECTION_ROUTES=ACCESSORY_DETECTION_ROUTES,
        PIPELINE_DETECTION_METHODS=PIPELINE_DETECTION_METHODS,
        PIPELINE_TRAINING_METHODS=PIPELINE_TRAINING_METHODS,
        PIPELINE_STAGE_ORDER=PIPELINE_STAGE_ORDER,
        PIPELINE_DASHBOARD_AI_TASK_SOURCE=PIPELINE_DASHBOARD_AI_TASK_SOURCE,
        AGENT_MCP_ORCHESTRATION_VERSION=AGENT_MCP_ORCHESTRATION_VERSION,
        AGENT_MCP_GEMINI_IMAGE_MODEL_ENV=AGENT_MCP_GEMINI_IMAGE_MODEL_ENV,
        AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV=AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV,
        AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL=AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL,
        AGENT_MCP_GEMINI_IMAGE_HIGH_FIDELITY_MODEL=AGENT_MCP_GEMINI_IMAGE_HIGH_FIDELITY_MODEL,
        AGENT_MCP_GEMINI_IMAGE_DEFAULT_TIMEOUT_SECONDS=AGENT_MCP_GEMINI_IMAGE_DEFAULT_TIMEOUT_SECONDS,
        AGENT_MCP_TOOL_POSE_IMAGE=AGENT_MCP_TOOL_POSE_IMAGE,
        AGENT_MCP_TOOL_SAMPLES=AGENT_MCP_TOOL_SAMPLES,
        AGENT_MCP_TOOL_TRAINING=AGENT_MCP_TOOL_TRAINING,
        AGENT_MCP_CONVERSATION_LIMIT=AGENT_MCP_CONVERSATION_LIMIT,
        AGENT_MCP_AUTO_MAX_STEPS=AGENT_MCP_AUTO_MAX_STEPS,
        AGENT_PIPELINE_ACTIONS=AGENT_PIPELINE_ACTIONS,
        AGENT_PIPELINE_STAGE_TARGETS=AGENT_PIPELINE_STAGE_TARGETS,
        PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S=PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S,
        AGENT_PIPELINE_SYSTEM_PROMPT=AGENT_PIPELINE_SYSTEM_PROMPT,
        PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS=PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS,
        TEXT_COMPARE_BETA_MAX_BYTES=TEXT_COMPARE_BETA_MAX_BYTES,
        TEXT_COMPARE_BETA_MAX_PIXELS=TEXT_COMPARE_BETA_MAX_PIXELS,
        TEXT_COMPARE_BETA_CACHE_TTL_SECONDS=TEXT_COMPARE_BETA_CACHE_TTL_SECONDS,
        TEXT_COMPARE_BETA_CACHE_MAX_BYTES=TEXT_COMPARE_BETA_CACHE_MAX_BYTES,
        DASHBOARD_AI_TASK_NAME=DASHBOARD_AI_TASK_NAME,
        REACT_PRODUCTION_ROUTE_SEGMENTS=REACT_PRODUCTION_ROUTE_SEGMENTS,
        REACT_PRODUCTION_BLOCKED_PREFIXES=REACT_PRODUCTION_BLOCKED_PREFIXES,
    )
