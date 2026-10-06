import base64
import asyncio
import binascii
import contextlib
import copy
import io
import ipaddress
import json
import logging
import math
import mimetypes
import os
import re
import signal
import hashlib
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import ctypes
import contextvars
import hmac
import secrets
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit
import urllib.error
import urllib.request
import zipfile

os.environ.setdefault("NUMBA_NUM_THREADS", "1")

import cv2
import numpy as np
import requests
from PIL import Image, ImageOps
from .storage.artifacts.images import ImageFiles
from .storage.artifacts.files import BusinessFiles
_business_files = BusinessFiles()
_image_files = ImageFiles(lambda: cv2, lambda: Image)

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi import Response
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictBool, StrictFloat, StrictInt, StrictStr
from .schemas.accessories import (
    AccessoryFileDeleteRequest,
    AccessoryAiReferenceRequest,
    AccessoryTextCropRequest,
    AccessoryRouteRequest,
)
from .schemas.auth import (
    AuthBootstrapRequest,
    AuthLoginRequest,
    UserCreateRequest,
    UserUpdateRequest,
    UserPasswordResetRequest,
    TaskNavigationPreferencesRequest,
)
from .schemas.configuration import (
    StreamConfig,
    AiConfigRequest,
    AgentConfigRequest,
)
from .schemas.detection import (
    RuleConfig,
    TaskRuleConfig,
    AiDetectionTaskAccessory,
    AiDetectionTaskRequest,
    ModelWarmupRequest,
)
from .schemas.pipeline import (
    AgentRecommendRequest,
    PipelineTaskCreateRequest,
    PipelineTaskUpdateRequest,
    PipelineAgentFeedbackRequest,
    PipelineAgentChatRequest,
)
from .schemas.text_inspection import (
    IncomingTextRulesRequest,
    IncomingTextReviewRequest,
)
from .schemas.training import (
    AutoOptimizeSettingsRequest,
    AutoOptimizeSampleApproveRequest,
    TrainingPreviewRequest,
    TrainingStartRequest,
    TrainingTaskUpdateRequest,
    TrainingResourceUpdateRequest,
)
from starlette.middleware.gzip import GZipMiddleware
from ultralytics import YOLO

try:
    from local_inspection_service.auto_optimize_profiles import build_mask_target_profile
    from local_inspection_service.plc_fx_ascii import (
        DEFAULT_PLC_CONFIG,
        MAX_DISPATCH_WALL_SECONDS,
        PLC_CONFIG_ABSENT,
        PLC_TERMINAL_ALLOWED_PHASES,
        PLC_TERMINAL_DIAGNOSTIC_SOURCES,
        PLC_TERMINAL_RESULT_CODES,
        PROTOCOL_ID as PLC_PROTOCOL_ID,
        PlcConfigError,
        PlcAttemptTerminalResult,
        PlcTerminalResultCode,
        PlcTransportError,
        PlcTransportPhase,
        build_d206_frame,
        build_d_register_read_frame,
        build_y04_frame,
        dispatch_detection_result as dispatch_fx_plc_detection_result,
        legacy_protocol_address_to_device,
        logical_device_address,
        normalize_config as normalize_plc_config,
        plc_terminal_result_is_retryable,
        read_d_register_value,
    )
    from local_inspection_service.plc_web_serial import (
        DEFAULT_WEB_SERIAL_CONFIG,
        LEGACY_WEB_SERIAL_PROTOCOL_VERSION,
        WEB_SERIAL_ACTIVE_LEASE_SECONDS,
        WEB_SERIAL_CONFIG_FIELDS,
        WEB_SERIAL_CONNECTING_LEASE_SECONDS,
        WEB_SERIAL_HEARTBEAT_SECONDS,
        WEB_SERIAL_PLAN_DEADLINE_SECONDS,
        WEB_SERIAL_PROFILE_ID,
        WEB_SERIAL_PROTOCOL_VERSION,
        WEB_SERIAL_SCHEMA_VERSION,
        build_legacy_web_serial_plan,
        build_web_serial_capture_read_plan,
        build_web_serial_diagnostic_plan,
        build_web_serial_plan,
        legacy_web_serial_config_fingerprint,
        migrate_web_serial_config,
        normalize_legacy_web_serial_config,
        normalize_web_serial_config,
        web_serial_config_fingerprint,
        web_serial_profile_fingerprint,
        web_serial_resolved_addresses,
    )
    from local_inspection_service.release_version import release_version_status
    from local_inspection_service.retired_features import REMOVED_PHASE1_PUBLIC_CONFIG_KEYS, removed_phase1_feature
except ModuleNotFoundError as exc:
    if exc.name not in {
        "local_inspection_service",
        "local_inspection_service.auto_optimize_profiles",
        "local_inspection_service.plc_fx_ascii",
        "local_inspection_service.retired_features",
    }:
        raise
    from auto_optimize_profiles import build_mask_target_profile
    from plc_fx_ascii import (
        DEFAULT_PLC_CONFIG,
        MAX_DISPATCH_WALL_SECONDS,
        PLC_CONFIG_ABSENT,
        PLC_TERMINAL_ALLOWED_PHASES,
        PLC_TERMINAL_DIAGNOSTIC_SOURCES,
        PLC_TERMINAL_RESULT_CODES,
        PROTOCOL_ID as PLC_PROTOCOL_ID,
        PlcConfigError,
        PlcAttemptTerminalResult,
        PlcTerminalResultCode,
        PlcTransportError,
        PlcTransportPhase,
        build_d206_frame,
        build_d_register_read_frame,
        build_y04_frame,
        dispatch_detection_result as dispatch_fx_plc_detection_result,
        legacy_protocol_address_to_device,
        logical_device_address,
        normalize_config as normalize_plc_config,
        plc_terminal_result_is_retryable,
        read_d_register_value,
    )
    from plc_web_serial import (
        DEFAULT_WEB_SERIAL_CONFIG,
        LEGACY_WEB_SERIAL_PROTOCOL_VERSION,
        WEB_SERIAL_ACTIVE_LEASE_SECONDS,
        WEB_SERIAL_CONFIG_FIELDS,
        WEB_SERIAL_CONNECTING_LEASE_SECONDS,
        WEB_SERIAL_HEARTBEAT_SECONDS,
        WEB_SERIAL_PLAN_DEADLINE_SECONDS,
        WEB_SERIAL_PROFILE_ID,
        WEB_SERIAL_PROTOCOL_VERSION,
        WEB_SERIAL_SCHEMA_VERSION,
        build_legacy_web_serial_plan,
        build_web_serial_capture_read_plan,
        build_web_serial_diagnostic_plan,
        build_web_serial_plan,
        legacy_web_serial_config_fingerprint,
        migrate_web_serial_config,
        normalize_legacy_web_serial_config,
        normalize_web_serial_config,
        web_serial_config_fingerprint,
        web_serial_profile_fingerprint,
        web_serial_resolved_addresses,
    )
    from release_version import release_version_status
    from retired_features import REMOVED_PHASE1_PUBLIC_CONFIG_KEYS, removed_phase1_feature

try:
    from local_inspection_service.storage.runtime_selector import (
        POSTGRES_STORE,
        RuntimeStoreConfigError,
        RuntimeStoreConnectionError,
        build_runtime_repository,
    )
    from local_inspection_service.storage.runtime_records import (
        audit_event_row,
        accessory_candidate_row,
        accessory_row,
        accessory_rows,
        ai_detection_task_row,
        app_config_rows,
        auth_session_rows,
        auth_store_from_rows,
        auth_user_rows,
        auto_optimize_state_row,
        config_from_rows,
        data_analysis_record_row,
        file_stem_identifier,
        incoming_text_inspection_row,
        incoming_text_reference_row,
        pipeline_state_from_rows,
        pipeline_state_rows,
        pipeline_task_row,
        row_raw_json_list,
        session_key_hash,
        training_task_row,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "local_inspection_service",
        "local_inspection_service.storage",
        "local_inspection_service.storage.runtime_selector",
        "local_inspection_service.storage.runtime_records",
    }:
        raise
    from storage.runtime_selector import (
        POSTGRES_STORE,
        RuntimeStoreConfigError,
        RuntimeStoreConnectionError,
        build_runtime_repository,
    )
    from storage.runtime_records import (
        audit_event_row,
        accessory_candidate_row,
        accessory_row,
        accessory_rows,
        ai_detection_task_row,
        app_config_rows,
        auth_session_rows,
        auth_store_from_rows,
        auth_user_rows,
        auto_optimize_state_row,
        config_from_rows,
        data_analysis_record_row,
        file_stem_identifier,
        incoming_text_inspection_row,
        incoming_text_reference_row,
        pipeline_state_from_rows,
        pipeline_state_rows,
        pipeline_task_row,
        row_raw_json_list,
        session_key_hash,
        training_task_row,
    )

try:
    from local_inspection_service.incoming_text_inspection import (
        FAIL as INCOMING_TEXT_FAIL,
        PASS as INCOMING_TEXT_PASS,
        REVIEW_REQUIRED as INCOMING_TEXT_REVIEW_REQUIRED,
        IncomingTextValidationError,
        TextObservation,
        apply_commissioning_gate,
        annotate_inspection,
        assess_image_quality,
        comparison_text,
        decide_inspection,
        local_visual_similarity,
        normalize_field_rules,
        observations_for_rule,
        rectify_label,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {"local_inspection_service", "local_inspection_service.incoming_text_inspection"}:
        raise
    from incoming_text_inspection import (
        FAIL as INCOMING_TEXT_FAIL,
        PASS as INCOMING_TEXT_PASS,
        REVIEW_REQUIRED as INCOMING_TEXT_REVIEW_REQUIRED,
        IncomingTextValidationError,
        TextObservation,
        apply_commissioning_gate,
        annotate_inspection,
        assess_image_quality,
        comparison_text,
        decide_inspection,
        local_visual_similarity,
        normalize_field_rules,
        observations_for_rule,
        rectify_label,
    )

try:
    from local_inspection_service.document_images import extract_doc_images, DocImageError, DocImageUnavailable
    from local_inspection_service.text_inspection_v2 import (
        UnsafeDocument,
        extract_docx_candidates,
        inspect_pdf,
        normalize_vlm_provider_result,
        sha256_bytes,
        strict_compare_prompt,
        validate_vlm_result,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {"local_inspection_service", "local_inspection_service.text_inspection_v2"}:
        raise
    from text_inspection_v2 import UnsafeDocument, extract_docx_candidates, inspect_pdf, normalize_vlm_provider_result, sha256_bytes, strict_compare_prompt, validate_vlm_result
    from document_images import extract_doc_images, DocImageError, DocImageUnavailable


from .runtime.bootstrap_locations import RootLocator, RuntimeLocations
_root_locator = RootLocator(os.environ, __file__, _business_files.is_dir)
resolve_service_root = _root_locator.resolve
ROOT = resolve_service_root()
_runtime_locations = RuntimeLocations.from_root(ROOT)
APP_DIR = _runtime_locations.app_dir
STATIC_DIR = _runtime_locations.static_dir
REACT_PREVIEW_DIST_DIR = _runtime_locations.react_preview_dist_dir
REACT_PREVIEW_ASSETS_DIR = _runtime_locations.react_preview_assets_dir
REACT_PRODUCTION_DIST_DIR = _runtime_locations.react_production_dist_dir
REACT_PRODUCTION_ASSETS_DIR = _runtime_locations.react_production_assets_dir
DATA_DIR = _runtime_locations.data_dir
UPLOAD_DIR = _runtime_locations.upload_dir
OUTPUT_DIR = _runtime_locations.output_dir
NORMALIZED_DIR = _runtime_locations.normalized_dir
TRAINING_JOBS_DIR = _runtime_locations.training_jobs_dir
TRAINING_TASKS_DIR = _runtime_locations.training_tasks_dir
ACCESSORY_CANDIDATES_DIR = _runtime_locations.accessory_candidates_dir
IMAGE_WORKER_LOG_DIR = _runtime_locations.image_worker_log_dir
CONFIG_PATH = _runtime_locations.config_path
CONFIG_BACKUP_PATH = _runtime_locations.config_backup_path
PLC_WEB_SERIAL_STATE_PATH = _runtime_locations.plc_web_serial_state_path
AI_LOCAL_CONFIG_PATH = _runtime_locations.ai_local_config_path
LOCAL_SECRET_ENV_PATH = _runtime_locations.local_secret_env_path
AI_PROFILE_CACHE_PATH = _runtime_locations.ai_profile_cache_path
AI_DETECTION_TASKS_PATH = _runtime_locations.ai_detection_tasks_path
AUTH_PATH = _runtime_locations.auth_path
DATA_ANALYSIS_RECORDS_PATH = _runtime_locations.data_analysis_records_path
INCOMING_TEXT_REFERENCES_PATH = _runtime_locations.incoming_text_references_path
INCOMING_TEXT_INSPECTIONS_PATH = _runtime_locations.incoming_text_inspections_path
INCOMING_TEXT_AUDIT_PATH = _runtime_locations.incoming_text_audit_path
TEXT_INSPECTION_DIR = _runtime_locations.text_inspection_dir
TEXT_INSPECTION_JSON_DIR = _runtime_locations.text_inspection_json_dir
TEXT_INSPECTION_MEDIA_DIR = _runtime_locations.text_inspection_media_dir
TEXT_INSPECTION_EXTERNAL_VLM_ENABLED = str(os.getenv("VANTALINE_TEXT_INSPECTION_EXTERNAL_VLM_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED = str(os.getenv("VANTALINE_TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED", "")).strip().lower() in {"1", "true", "yes", "on"}
TEXT_INSPECTION_MANUAL_PASS_VERIFIED = str(os.getenv("VANTALINE_TEXT_INSPECTION_MANUAL_PASS_VERIFIED", "")).strip().lower() in {"1", "true", "yes", "on"}
TEXT_INSPECTION_DIAGNOSTIC_LOGGER = logging.getLogger("uvicorn.error")
TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE = 2048
TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY = 90
TEXT_INSPECTION_PROVIDER_TIMEOUT_SECONDS = 30.0
TEXT_INSPECTION_PROMPT_VERSION = "text-compare-v2-prompt-2"


def current_release_version() -> dict[str, Any]:
    return release_version_status(ROOT, WEB_SERIAL_PROTOCOL_VERSION)
INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED = str(
    os.getenv("VANTALINE_INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED", "")
).strip().lower() in {"1", "true", "yes", "on"}
try:
    INCOMING_TEXT_MIN_FREE_BYTES = max(
        512 * 1024 * 1024,
        int(os.getenv("VANTALINE_INCOMING_TEXT_MIN_FREE_BYTES", str(2 * 1024 * 1024 * 1024))),
    )
except (TypeError, ValueError):
    INCOMING_TEXT_MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024
AUTO_OPTIMIZE_DIR = DATA_DIR / "auto_optimize"
AI_SUPPORTED_PROVIDERS = {"gemini", "qwen", "doubao"}
AI_DEFAULT_PROVIDER = "gemini"
AI_DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "qwen": "qwen3-vl-flash",
}
AI_DEFAULT_MODEL = AI_DEFAULT_MODELS[AI_DEFAULT_PROVIDER]
AI_MODEL_OPTIONS = [
    {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash-Lite"},
    {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
    {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
    {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
    {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash"},
    {"id": "gemini-3.1-flash-image", "label": "Gemini 3.1 Flash Image"},
    {"id": "gemini-3-pro-image", "label": "Gemini 3 Pro Image"},
    {"id": "qwen3.7-plus", "label": "Qwen 3.7 Plus"},
    {"id": "qwen3.7-plus-2026-05-26", "label": "Qwen 3.7 Plus 2026-05-26"},
    {"id": "qwen3.6-flash", "label": "Qwen 3.6 Flash"},
    {"id": "qwen3.6-flash-2026-04-16", "label": "Qwen 3.6 Flash 2026-04-16"},
    {"id": "qwen3-vl-flash", "label": "Qwen3 VL Flash"},
    {"id": "qwen3-vl-plus", "label": "Qwen3 VL Plus"},
    {"id": "qwen3.7-max", "label": "Qwen 3.7 Max"},
]
AI_DEFAULT_BASE_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
}
AI_PROVIDER_LABELS = {
    "gemini": "Gemini",
    "qwen": "Qwen",
}
AI_DEFAULT_TIMEOUT_SECONDS = 10.0
IMAGE_GENERATION_SUPPORTED_PROVIDERS = {"gemini", "agnes", "qwen_image"}
IMAGE_GENERATION_DEFAULT_PROVIDER = "gemini"
IMAGE_GENERATION_DEFAULT_MODELS = {
    "gemini": "gemini-3.1-flash-image",
    "agnes": "agnes-image-2.0-flash",
    "qwen_image": "qwen-image-2.0-pro",
}
IMAGE_GENERATION_DEFAULT_BASE_URLS = {
    "gemini": AI_DEFAULT_BASE_URLS["gemini"],
    "agnes": "https://apihub.agnes-ai.com/v1/images/generations",
    "qwen_image": "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
}
IMAGE_GENERATION_DEFAULT_API_KEY_ENVS = {
    "gemini": "GEMINI_IMAGE_API_KEY",
    "agnes": "AGNES_API_KEY",
    "qwen_image": "QWEN_IMAGE_API_KEY",
}
IMAGE_GENERATION_MODEL_OPTIONS = [
    {"id": "gemini-3.1-flash-image", "label": "Gemini 3.1 Flash Image"},
    {"id": "gemini-3-pro-image", "label": "Gemini 3 Pro Image"},
    {"id": "agnes-image-2.0-flash", "label": "Agnes Image 2.0 Flash"},
    {"id": "agnes-image-2.1-flash", "label": "Agnes Image 2.1 Flash"},
    {"id": "qwen-image-2.0", "label": "Qwen Image 2.0"},
    {"id": "qwen-image-2.0-pro", "label": "Qwen Image 2.0 Pro"},
]
IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS = 120.0
IMAGE_GENERATION_PROVIDER_KEYS = {
    "gemini": "gemini_native_image_generation",
    "agnes": "agnes_image_generation",
    "qwen_image": "qwen_image_generation",
}
IMAGE_GENERATION_PROVIDER_LABELS = {
    "gemini": "Gemini",
    "agnes": "Agnes Image",
    "qwen_image": "Qwen Image",
}
IMAGE_GENERATION_MODEL_ENV = "VANTALINE_IMAGE_MODEL"
IMAGE_GENERATION_PROVIDER_ENV = "VANTALINE_IMAGE_PROVIDER"
IMAGE_GENERATION_BASE_URL_ENV = "VANTALINE_IMAGE_BASE_URL"
IMAGE_GENERATION_API_KEY_ENV = "VANTALINE_IMAGE_API_KEY"
IMAGE_GENERATION_NAMED_API_KEY_ENV = "VANTALINE_IMAGE_API_KEY_ENV"
IMAGE_GENERATION_TIMEOUT_ENV = "VANTALINE_IMAGE_TIMEOUT_SECONDS"
AI_PROXY_ENV_NAMES = ("INSPECTION_AI_PROXY_URL", "AI_PROVIDER_PROXY_URL", "HTTPS_PROXY", "ALL_PROXY")
from .model_providers.proxy_runtime import AI_LOCAL_PROXY_URL
AI_AUTO_LOCAL_PROXY_ENV = "INSPECTION_AI_AUTO_LOCAL_PROXY"
from .training.executor_settings import (
    REMOTE_TRAINING_API_KEY_ENV,
    REMOTE_TRAINING_DEFAULT_TIMEOUT_SECONDS,
    REMOTE_TRAINING_ENDPOINT_ENV,
    REMOTE_TRAINING_EXECUTOR_ENV,
    REMOTE_TRAINING_TIMEOUT_ENV,
    RUNPOD_YOLO_API_BASE_ENV,
    RUNPOD_YOLO_API_KEY_ENV,
    RUNPOD_YOLO_ARTIFACT_MAX_BYTES_ENV,
    RUNPOD_YOLO_AUTH_SCHEME_ENV,
    RUNPOD_YOLO_CLIENT_TIMEOUT_ENV,
    RUNPOD_YOLO_DATASET_TOKEN_TTL_ENV,
    RUNPOD_YOLO_ENDPOINT_ID_ENV,
    RUNPOD_YOLO_INLINE_DATASET_MAX_BYTES_ENV,
    RUNPOD_YOLO_JOB_TIMEOUT_ENV,
    RUNPOD_YOLO_POLL_INTERVAL_ENV,
    RUNPOD_YOLO_PUBLIC_BASE_URL_ENV,
    WINDOWS_WORKER_BASE_URL_ENV,
    WINDOWS_WORKER_DEFAULT_TIMEOUT_SECONDS,
    WINDOWS_WORKER_TIMEOUT_ENV,
    WINDOWS_WORKER_TOKEN_ENV,
    ExecutorSettings, host_is_private_or_tailnet,
)
from .training.runpod_submission import (
    RUNPOD_YOLO_BASE_MODEL_ENV,
    RUNPOD_YOLO_BASE_MODEL_SHA256_ENV,
    RUNPOD_YOLO_BASE_MODEL_URL_ENV,
    RUNPOD_YOLO_BASE_MODEL_URL_SHA256_ENV,
)
CURSOR_IMAGE2_PROVIDER = "cursor_image2"
WINDOWS_WORKER_IMAGE_PROVIDER = "windows_worker_image_fallback"
LOCAL_CODEX_IMAGE_PROVIDER = "local_codex_image_worker"
CURSOR_IMAGE2_QUEUE_STATUS = "queued_for_cursor_image2"
CODEX_IMAGE_WORKER_QUEUE_STATUS = "queued_for_codex_image_worker"
CURSOR_IMAGE2_API_KEY_ENV = "INSPECTION_CURSOR_IMAGE2_API_KEY"
CURSOR_IMAGE2_BASE_URL_ENV = "INSPECTION_CURSOR_IMAGE2_BASE_URL"
CURSOR_IMAGE2_ENDPOINT_ENV = "INSPECTION_CURSOR_IMAGE2_ENDPOINT"
CURSOR_IMAGE2_MODEL_ENV = "INSPECTION_CURSOR_IMAGE2_MODEL"
CURSOR_IMAGE2_DEFAULT_MODEL = ""
CURSOR_IMAGE_MODEL_KEYWORDS = ("image", "imagen", "gpt-image", "dall-e", "dalle", "flux", "stable-diffusion", "sdxl", "banana")
CURSOR_IMAGE_MODEL_PRIORITY = ("nano-banana-pro", "gpt-image-2", "gpt-image-1", "imagen", "flux")
STALE_REPO_PATH_PREFIXES = (
    "/mnt/f/CodexWorkspace/assembly_line_optimize",
    "F:/CodexWorkspace/assembly_line_optimize",
    "/opt/vantalane/app",
)
IMAGE_JOB_ACTIVE_STATUSES = {CODEX_IMAGE_WORKER_QUEUE_STATUS, CURSOR_IMAGE2_QUEUE_STATUS, "queued", "running"}
IMAGE_JOB_QUEUED_STATUSES = {CODEX_IMAGE_WORKER_QUEUE_STATUS, CURSOR_IMAGE2_QUEUE_STATUS, "queued"}
LEGACY_MODEL_PATH = (
    ROOT
    / "yolo26_seg_2class_visible_polygon_4000_full_rotation_trial"
    / "runs"
    / "yolo26s_seg_2class_visible_polygon_full_rotation_100e_img640_workers0"
    / "weights"
    / "best.pt"
)
REPO_MODEL_PATH = ROOT / "models" / "current_2class_yolo26s_seg_best.pt"
MODEL_PATH = Path(os.environ.get("INSPECTION_MODEL_PATH", REPO_MODEL_PATH if _business_files.exists(REPO_MODEL_PATH) else LEGACY_MODEL_PATH))
FIVE_CLASS_MODEL_PATH = ROOT / "models" / "current_5class_yolo26s_seg_best.pt"
# Base checkpoint for NEW detection-model training. We train a bbox-only detector
# (no masks). Override with INSPECTION_DETECT_BASE_MODEL; otherwise transfer-learn
# from a COCO-pretrained YOLO detector (downloaded/cached by Ultralytics).
DETECT_BASE_MODEL_OVERRIDE = os.environ.get("INSPECTION_DETECT_BASE_MODEL", "").strip()

MODEL_CLASS_NAMES = {
    0: "bottle",
    1: "manual",
}

MODEL_TO_BUSINESS_CLASS = {
    0: 0,
    1: 1,
}

CLASS_NAMES = {
    0: "bottle",
    1: "warranty_service_manual",
    2: "battery_instruction_manual",
    3: "download_service_manual",
    4: "service_qr_manual",
}

CLASS_LABELS = {
    0: "Bottle",
    1: "Warranty Service Manual",
    2: "Battery Instruction Manual",
    3: "Download Service Manual",
    4: "Service QR Manual",
}

GENERIC_DETECTION_CLASS_NAMES = {
    0: "bottle",
    1: "manual",
    99: "manual_unknown",
}

GENERIC_DETECTION_LABELS = {
    0: "Bottle",
    1: "Manual",
    99: "Unknown Manual",
}

DEFAULT_MODEL_ID = "yolo26_2class_ocr"
AI_DETECTION_MODEL_ID = "ai_detection"
AI_DETECTION_TASK_PREFIX = "ai_detection__task_"
AI_DETECTION_LABEL = "AI 检测"
AI_DETECTION_SYSTEM_PROMPT = """You are a stateless visual inspection agent for an assembly-line image.
You receive one inspection image, a JSON list of required accessory profiles, and optional reference images for those accessories.
Do not use memory from previous calls. Do not infer from prior images.
Decide whether each required accessory is visible in this image.
Count an accessory as present when a substantial, visually identifiable portion is visible, even if the full object is partly outside the frame or mildly occluded.
Only mark present=false for partial views when the visible evidence is too small or ambiguous to identify the configured accessory.
Focus on concrete visual evidence: object shape, material, color, printed text, QR/logo/text fragments, and relative size.
If two accessories have the same size or shape, distinguish them by profile-specific visible text, markings, material, color, or geometry.
Use reference accessory images only to understand what each required accessory looks like; do not count a reference image as presence in the inspection image.
Return only JSON that matches the provided schema.
For every required accessory, return present=true or present=false.
Use confidence from 0 to 1. If uncertain, mark present=false unless clear evidence exists.
Include count when multiple visible instances are relevant or count is otherwise known.
If expected_count is provided, the count must match exactly; visible undercounts and overcounts both fail the rule.
Return only compact QA JSON: {"detections":[{"accessory_id":"...","label":"...","present":true,"confidence":0.0,"count":1,"evidence":"..."}],"rule":{"counts":{"...":0}}}.
Do not include narrative, markdown, summaries, or annotated images.
Do not invent accessories that are not visible."""
AI_INSPECTION_IMAGE_MAX_SIDE = int(os.environ.get("INSPECTION_AI_IMAGE_MAX_SIDE", "960"))
AI_INSPECTION_IMAGE_QUALITY = int(os.environ.get("INSPECTION_AI_IMAGE_QUALITY", "72"))
AI_REFERENCE_IMAGES_PER_ACCESSORY = int(os.environ.get("INSPECTION_AI_REFERENCE_IMAGES_PER_ACCESSORY", "0"))
AI_REFERENCE_IMAGE_MAX_SIDE = 512
AI_REFERENCE_IMAGE_QUALITY = 68
AI_PROFILE_REFERENCE_IMAGES = 3
AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE = 1024
AI_PROFILE_REFERENCE_IMAGE_QUALITY = 78
AI_PROFILE_REFERENCE_MODE = "sheet_v1"
AI_PROFILE_REFERENCE_SHEET_MAX_SIDE = 1600
AI_PROFILE_REFERENCE_SHEET_QUALITY = 86
AI_PROFILE_CACHE_TTL_SECONDS = max(300, int(os.environ.get("INSPECTION_AI_PROFILE_CACHE_TTL_SECONDS", "3600")))
AI_PROFILE_CACHE_VERSION = 1
AI_MCP_INSPECTION_IMAGE_DIR = Path(os.environ.get("INSPECTION_AI_MCP_IMAGE_DIR", "/tmp/alook-inspection-mcp-images"))
INSPECTION_PREVIEW_MAX_SIDE = max(640, min(2560, int(os.environ.get("VANTALINE_INSPECTION_PREVIEW_MAX_SIDE", "1280"))))
INSPECTION_PREVIEW_JPEG_QUALITY = max(50, min(95, int(os.environ.get("VANTALINE_INSPECTION_PREVIEW_JPEG_QUALITY", "78"))))
DATA_ANALYSIS_BATCH_LIMIT = 25
_REFERENCE_SHEET_DESCRIPTOR_CACHE: dict[str, dict[str, Any]] = {}
_REFERENCE_SHEET_DESCRIPTOR_CACHE_LOCK = threading.RLock()
AI_DETECTION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["detections", "rule"],
    "properties": {
        "rule": {
            "type": "object",
            "required": ["counts"],
            "properties": {
                "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
            },
        },
        "detections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["accessory_id", "present", "confidence"],
                "properties": {
                    "accessory_id": {"type": "string"},
                    "label": {"type": "string"},
                    "present": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "count": {"type": "integer", "minimum": 0},
                    "evidence": {"type": "string"},
                    "observed_text": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}
from .model_providers.mcp_runtime import (AI_MCP_RUNTIME_ENV, AI_MCP_LEGACY_ENABLED_ENV, AI_MCP_RUNTIME_IN_PROCESS, AI_MCP_RUNTIME_STDIO)
AI_MCP_EXTRACTION_POINT = (
    "call_ai_mcp_tool dispatches in process by default. Set INSPECTION_AI_MCP_RUNTIME=stdio "
    "for the legacy stdio MCP subprocess while keeping tool payloads/results unchanged."
)
AI_PROVIDER_MAX_ATTEMPTS = max(1, min(3, int(os.environ.get("INSPECTION_AI_PROVIDER_MAX_ATTEMPTS", "3"))))
AI_PROVIDER_RETRY_BACKOFF_SECONDS = max(0.0, min(2.0, float(os.environ.get("INSPECTION_AI_RETRY_BACKOFF_SECONDS", "0.35"))))
AI_MCP_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "accessory.profile.generate": {
        "description": "Normalize or provider-generate a reusable accessory profile.",
        "input": {
            "accessory": "Accessory metadata dict.",
            "reference_image_paths": "Optional image paths. Defaults to bounded accessory images.",
            "provider_config": "Internal AI provider settings.",
            "allow_provider": "False returns deterministic local fallback.",
        },
        "output": {"profile": "Normalized profile JSON.", "status": "Generation status/debug metadata."},
    },
    "accessory.reference.collect": {
        "description": "Collect bounded reference image payload descriptors for one accessory.",
        "input": {
            "accessory": "Accessory metadata dict.",
            "accessory_id": "Optional explicit accessory id.",
            "max_images": "Upper bound for descriptors.",
        },
        "output": {"references": "List of image payload descriptors.", "reference_count": "Descriptor count."},
    },
    "vision.inspect.presence": {
        "description": "Inspect one image against required accessory profiles using stateless provider JSON.",
        "input": {
            "inspection_image_bgr": "In-process image array; remote MCP extraction should pass an image descriptor.",
            "required_accessories": "Normalized required accessory profile payloads.",
            "reference_descriptors": "Descriptors returned by accessory.reference.collect.",
            "provider_config": "Internal AI provider settings.",
        },
        "output": {"passed": "Boolean.", "rule": "Presence rule JSON.", "detections": "Normalized detections.", "ai": "Debug metadata."},
    },
    "provider.gemini.generate_json": {
        "description": "Provider JSON gateway used by profile and inspection tools.",
        "input": {
            "system_prompt": "Provider system instruction.",
            "user_content": "OpenAI-style text/image parts.",
            "provider_config": "Internal AI provider settings.",
            "max_tokens": "Provider output cap.",
            "schema_hint": "Optional expected output schema.",
        },
        "output": {"ok": "Boolean.", "parsed": "Parsed JSON on success.", "latency_ms": "Provider latency.", "error": "Bounded error on failure."},
    },
}
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "yolo26_5class_direct": {
        "id": "yolo26_5class_direct",
        "label": "YOLO26",
        "description": "直接检测 Bottle 和四类说明书，不经过 OCR。",
        "path": FIVE_CLASS_MODEL_PATH,
        "uses_ocr": False,
        "model_class_names": CLASS_NAMES,
        "model_to_business_class": {idx: idx for idx in CLASS_NAMES},
    },
    DEFAULT_MODEL_ID: {
        "id": DEFAULT_MODEL_ID,
        "label": "YOLO26 + PaddleOCR",
        "description": "先检测 bottle/manual，再用 PaddleOCR 将说明书分成四类。",
        "path": MODEL_PATH,
        "uses_ocr": True,
        "model_class_names": MODEL_CLASS_NAMES,
        "model_to_business_class": MODEL_TO_BUSINESS_CLASS,
    },
    AI_DETECTION_MODEL_ID: {
        "id": AI_DETECTION_MODEL_ID,
        "label": AI_DETECTION_LABEL,
        "description": "调用无状态多模态代理，按配件画像判断是否存在；不绘制检测框。",
        "path": APP_DIR,
        "uses_ocr": True,
        "variant": "ai_detection",
        "is_ai_detection": True,
        "model_class_names": {},
        "model_to_business_class": {},
    },
}


def legacy_model_specs() -> list[dict[str, Any]]:
    specs = []
    for spec in MODEL_REGISTRY.values():
        variant = spec.get("variant") or ("yolo_ocr" if spec.get("uses_ocr") else "yolo")
        specs.append({**spec, "is_legacy": not bool(spec.get("is_ai_detection") or spec.get("is_label_sheet_match")), "variant": variant})
    return specs

DEFAULT_CONFIG: dict[str, Any] = {
    "model_path": str(MODEL_PATH),
    "active_model_id": DEFAULT_MODEL_ID,
    "image_size": 640,
    "confidence_threshold": 0.25,
    "required_classes": [0, 1, 2, 3, 4],
    "min_counts": {"0": 1, "1": 1, "2": 1, "3": 1, "4": 1},
    "task_rules": {},
    "ocr": {
        "enabled": True,
        "require_manual_types": False,
        "manual_types": [
            "warranty_service",
            "battery_instruction",
            "download_service",
            "service_qr",
        ],
        "max_texts_per_manual": 16,
        "max_crop_long_side": 750,
        "fallback_min_confidence": 0.55,
    },
    "video": {"sample_every_seconds": 1.0, "max_frames": 80},
    "stream": {"enabled": False, "source": "camera", "url": "", "status": "reserved"},
    "accessories": [
        {"class_id": idx, "name": CLASS_LABELS[idx], "status": "active", "source_files": []}
        for idx in CLASS_NAMES
    ],
    "training": {
        "status": "idle",
        "last_requested_at": None,
        "note": "Prototype hook. Dataset generation and training can be wired to the existing synthetic pipeline.",
        "selected_accessory_ids": [],
        "sample_count": 4000,
        "mode": "yolo_ocr",
        "preview_urls": [],
    },
}

DEFAULT_AI_CONFIG: dict[str, Any] = {
    "provider": AI_DEFAULT_PROVIDER,
    "model": AI_DEFAULT_MODEL,
    "base_url": AI_DEFAULT_BASE_URLS[AI_DEFAULT_PROVIDER],
    "timeout_seconds": AI_DEFAULT_TIMEOUT_SECONDS,
    "api_key_env": "",
    "api_key": "",
    "api_keys": [],
    "active_key_id": "",
    "proxy_url": "",
    "auto_local_proxy": True,
    "image_provider": IMAGE_GENERATION_DEFAULT_PROVIDER,
    "image_model": IMAGE_GENERATION_DEFAULT_MODELS[IMAGE_GENERATION_DEFAULT_PROVIDER],
    "image_base_url": IMAGE_GENERATION_DEFAULT_BASE_URLS[IMAGE_GENERATION_DEFAULT_PROVIDER],
    "image_timeout_seconds": IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS,
    "image_api_key_env": "",
    "image_api_key": "",
    "image_api_keys": [],
    "image_active_key_id": "",
}

AUTH_SESSION_COOKIE = "vantaline_session"
PLC_WORKSTATION_COOKIE = "vantaline_plc_workstation"
PLC_WORKSTATION_COOKIE_TTL_SECONDS = 365 * 24 * 60 * 60
PLC_WEB_SERIAL_JSON_TEST_ENV = "VANTALINE_PLC_WEB_SERIAL_ALLOW_JSON_TEST"
AUTH_SESSION_TTL_SECONDS = max(900, int(os.environ.get("VANTALINE_SESSION_TTL_SECONDS", str(12 * 60 * 60))))
# Sliding-expiry persistence is throttled: a valid session is only rewritten to
# disk at most once per this interval. Avoids rewriting the whole auth store on
# every request (including bursts of /outputs image fetches), which previously
# caused write amplification, lock contention, and apparent server hangs.
AUTH_SESSION_PERSIST_INTERVAL_SECONDS = max(30, int(os.environ.get("VANTALINE_SESSION_PERSIST_INTERVAL_SECONDS", "120")))
PASSWORD_HASH_ITERATIONS = max(120000, int(os.environ.get("VANTALINE_PASSWORD_HASH_ITERATIONS", "260000")))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = max(10, int(os.environ.get("VANTALINE_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")))
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = max(3, int(os.environ.get("VANTALINE_LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "5")))
LOGIN_RATE_LIMIT_LOCKOUT_SECONDS = max(30, int(os.environ.get("VANTALINE_LOGIN_RATE_LIMIT_LOCKOUT_SECONDS", "300")))
LEGACY_OWNER_ID = "legacy_admin"
SYSTEM_OWNER_ID = "system"
from .runtime.connections import ThreadRepositoryFactory, close_selection, selection_is_usable
from .runtime.repository_composition import RuntimeRepositories


from .auth.policy import (
    FEATURE_PERMISSIONS, ADMIN_ONLY_PERMISSIONS, DEFAULT_USER_PERMISSIONS,
    clean_username, clean_display_name, normalize_role, normalize_permissions,
    public_user, find_user, find_user_by_username, user_is_admin, user_has_permission,
)
from .auth.credentials import PasswordHasher, verify_password, generate_temporary_password, TEMP_PASSWORD_ALPHABET
from .auth.preferences import (
    TASK_NAVIGATION_PREFERENCES_KEY, MAX_TASK_NAVIGATION_IDS, MAX_TASK_NAVIGATION_ID_LENGTH,
    normalize_task_navigation_ids, task_navigation_preferences_payload,
)
from .auth.repository import (
    AuthStoreDependencies, AuthRepository, empty_auth_store, auth_user_row_for_user,
    auth_session_key_candidates, auth_session_from_store, auth_session_row_for_session,
)

from .auth.composition import AuthenticationServices, AuthenticationStorage, AuthenticationSettings
from .auth.application import AuthenticationDomain
from .auth.sessions import SessionSettings
from .auth.login_limits import LoginLimitSettings

from .runtime.application_foundation import FoundationInputs, build_foundation
_foundation = build_foundation(FoundationInputs(
    environment=os.environ,
    data_directory=DATA_DIR, auth_path=AUTH_PATH,
    legacy_owner=LEGACY_OWNER_ID, system_owner=SYSTEM_OWNER_ID,
    authentication=AuthenticationSettings(
        password_iterations=lambda iterations=PASSWORD_HASH_ITERATIONS: iterations,
        sessions=lambda cookie=AUTH_SESSION_COOKIE, ttl=AUTH_SESSION_TTL_SECONDS,
                        persist=AUTH_SESSION_PERSIST_INTERVAL_SECONDS: SessionSettings(cookie, ttl, persist),
        login_limits=lambda window=LOGIN_RATE_LIMIT_WINDOW_SECONDS, attempts=LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
                            lockout=LOGIN_RATE_LIMIT_LOCKOUT_SECONDS: LoginLimitSettings(window, attempts, lockout),
        legacy_owner=lambda owner=LEGACY_OWNER_ID: owner,
    ),
))
_runtime_repository_owner = _foundation.repositories
_runtime_repositories = _runtime_repository_owner.factory
_runtime_repository_access = _runtime_repository_owner.access
runtime_repository_cache_key = _runtime_repository_owner.cache_key
_authentication_domain = _foundation.authentication
_authentication = _authentication_domain.services
_request_user = _authentication_domain.identity
_password_hasher = _authentication.hasher
password_hash = _password_hasher.password_hash
_auth_repository = _authentication.repository
load_auth_store = _auth_repository.load_auth_store
save_auth_store = _auth_repository.save_auth_store
save_auth_user = _auth_repository.save_auth_user
delete_auth_user = _auth_repository.delete_auth_user
save_auth_session = _auth_repository.save_auth_session
delete_auth_session = _auth_repository.delete_auth_session
delete_expired_auth_sessions = _auth_repository.delete_expired_auth_sessions
delete_auth_sessions_for_user = _auth_repository.delete_auth_sessions_for_user
save_login_session = _auth_repository.save_login_session
save_auth_session_touch_or_prune = _auth_repository.save_auth_session_touch_or_prune


for path in (UPLOAD_DIR, OUTPUT_DIR, DATA_DIR, NORMALIZED_DIR, TRAINING_JOBS_DIR, TRAINING_TASKS_DIR, ACCESSORY_CANDIDATES_DIR, IMAGE_WORKER_LOG_DIR):
    path.mkdir(parents=True, exist_ok=True)

from .runtime.http_application import (
    create_http_application, LOCAL_CORS_ORIGIN_REGEX, LAN_CORS_ORIGIN_REGEX,
)
_http_application = create_http_application(os.environ, upload_runtime_provider=lambda: _business_files.runtime_provider())
app = _http_application.app
CORS_ORIGINS = _http_application.cors_origins
CORS_ORIGIN_REGEX = _http_application.cors_origin_regex

from .auth.public_network import PublicNetworkPolicy
from .auth.public_network_ports import OriginPolicy, PublicEndpointPolicy, RuntimeDetailAccess

_public_network_policy = PublicNetworkPolicy(
    origins=OriginPolicy(
        normalize_origin=lambda: normalize_origin,
        CORS_ORIGINS=lambda: CORS_ORIGINS,
        CORS_ORIGIN_REGEX=lambda: CORS_ORIGIN_REGEX,
    ),
    endpoints=PublicEndpointPolicy(
        is_private_or_local_host=lambda: is_private_or_local_host,
        masked_url_for_status=lambda: masked_url_for_status,
    ),
    access=RuntimeDetailAccess(
        user_is_admin=lambda: user_is_admin,
        user_has_permission=lambda: user_has_permission,
    ),
)


def normalize_origin(value: str) -> str:
    return _public_network_policy.normalize_origin(value)


def same_origin(origin: str, host: str) -> bool:
    return _public_network_policy.same_origin(origin, host)


def cors_origin_allowed(origin: str) -> bool:
    return _public_network_policy.cors_origin_allowed(origin)


from .auth.accounts import AccountDependencies, AccountService
from .auth.sessions import (
    SessionDependencies, SessionService, SessionSettings,
    prune_expired_sessions, request_is_https, revoke_user_sessions,
)
from .auth.access import AccessControl
from .auth.route_permissions import route_required_permission, route_allowed_permissions

_account_service = _authentication.accounts
_session_service = _authentication.sessions
_access_control = _authentication.access

users_exist = _account_service.users_exist


create_auth_user = _account_service.create_auth_user


bootstrap_admin_from_env = _account_service.bootstrap_admin_from_env


set_session_cookie = _session_service.set_session_cookie


clear_session_cookie = _session_service.clear_session_cookie


create_session = _session_service.create_session


create_login_session = _session_service.create_login_session


set_user_password = _account_service.set_user_password


authenticate_request = _session_service.authenticate_request


current_auth_user = _access_control.current_auth_user


require_admin_role = _access_control.require_admin_role



def reset_runtime_repository_cache() -> None:
    _runtime_repositories.reset()


def close_runtime_repository_selection(selection: Any) -> None:
    close_selection(selection)


def runtime_repository_selection_is_usable(selection: Any) -> bool:
    return selection_is_usable(selection)


def clear_thread_runtime_repository_selection() -> None:
    _runtime_repositories.clear()


def current_runtime_repository_generation() -> int:
    return _runtime_repositories.generation()



def runtime_repository_selection() -> Any:
    """Build the explicit runtime repository selection with HTTP-safe errors."""
    return _runtime_repository_access.runtime_repository_selection()

def runtime_postgres_repository_or_none() -> Any | None:
    """Return the explicit PostgreSQL repository, or None for JSON runtime."""
    return _runtime_repository_access.runtime_postgres_repository_or_none()


from .runtime.repository_access import runtime_repository_connection_probe_id


def runtime_store_probe_payload() -> dict[str, Any]:
    """Return a non-secret runtime-store probe for an admin HTTP endpoint."""
    return _runtime_repository_access.runtime_store_probe_payload()


from .analytics.cost_pricing import (
    API_COST_PRICING_USD_PER_MILLION, API_COST_CATEGORY_LABELS,
    RUNPOD_GPU_USD_PER_SECOND_DEFAULT, RUNPOD_GPU_USD_PER_SECOND_ENV,
    runpod_gpu_usd_per_second, api_cost_pricing_for_model, api_cost_usage_token_count,
    api_cost_detail_tokens, api_cost_from_usage, api_cost_day, api_cost_classify,
)
from .analytics.cost_repository import CostPaths, CostStoreDependencies
from .analytics.cost_composition import CostServices
from .analytics.cost_api import register_cost_api

from .records.ownership import RecordOwnership
from .records.access import RecordAccess
from .records.audit import (
    RecordAudit,
    coerce_record_timestamp as _coerce_record_timestamp,
    path_mtime_timestamp as _path_mtime_timestamp,
    record_created_at as _record_created_at,
    record_updated_at as _record_updated_at,
)
from .records.composition import RecordServices
_record_services = _foundation.records
_record_ownership = _record_services.ownership
_record_audit = _record_services.audit
_record_access = _record_services.access


record_owner_id = _record_ownership.record_owner_id


current_owner_fields = _record_access.current_owner_fields


owner_fields_for_new_record = _record_access.owner_fields_for_new_record


coerce_record_timestamp = _coerce_record_timestamp


path_mtime_timestamp = _path_mtime_timestamp


record_created_at = _record_created_at


record_updated_at = _record_updated_at


record_owner_username = _record_ownership.record_owner_username


record_audit_fields = _record_audit.record_audit_fields


enrich_record_audit_fields = _record_audit.enrich_record_audit_fields


record_matches_owner_filter = _record_ownership.record_matches_owner_filter


record_visible_to_user = _record_ownership.record_visible_to_user


record_mutable_by_user = _record_ownership.record_mutable_by_user


from .records.resource_names import ResourceNames
from .records.resource_name_ports import NamePolicy, NameCatalogs

_resource_names = ResourceNames(
    policy=NamePolicy(
        resource_name_key=lambda: resource_name_key,
        LEGACY_OWNER_ID=lambda: LEGACY_OWNER_ID,
        accessory_uid=lambda: accessory_uid,
        record_owner_id=lambda: record_owner_id,
        duplicate_name_error=lambda: duplicate_name_error,
        task_matches_excluded_identity=lambda: task_matches_excluded_identity,
        task_record_name=lambda: task_record_name,
    ),
    catalogs=NameCatalogs(
        load_pipeline_tasks=lambda: load_pipeline_tasks,
        load_ai_detection_tasks=lambda: load_ai_detection_tasks,
        training_resources_payload=lambda: training_resources_payload,
        list_trained_model_specs=lambda: list_trained_model_specs,
    ),
)


def resource_name_key(value: Any) -> str:
    return _resource_names.resource_name_key(value)


def resource_owner_id_for_new_record(user: dict[str, Any]) -> str:
    return _resource_names.resource_owner_id_for_new_record(user)


def duplicate_name_error(resource_label: str) -> None:
    return _resource_names.duplicate_name_error(resource_label)


def assert_unique_accessory_name(config: dict[str, Any], name: Any, owner_user_id: str, *, exclude_id: str = "") -> None:
    return _resource_names.assert_unique_accessory_name(config, name, owner_user_id, exclude_id=exclude_id)


def task_record_name(record: dict[str, Any]) -> str:
    return _resource_names.task_record_name(record)


def task_matches_excluded_identity(
    task: dict[str, Any],
    *,
    excluded_pipeline_task_ids: set[str],
    excluded_ai_task_ids: set[str],
) -> bool:
    return _resource_names.task_matches_excluded_identity(task, excluded_pipeline_task_ids=excluded_pipeline_task_ids, excluded_ai_task_ids=excluded_ai_task_ids)


def assert_unique_task_name(
    name: Any,
    owner_user_id: str,
    *,
    exclude_pipeline_task_id: str = "",
    exclude_ai_task_id: str = "",
) -> None:
    return _resource_names.assert_unique_task_name(name, owner_user_id, exclude_pipeline_task_id=exclude_pipeline_task_id, exclude_ai_task_id=exclude_ai_task_id)


def assert_unique_dataset_name(name: Any, owner_user_id: str, user: dict[str, Any], *, exclude_dataset_id: str = "") -> None:
    return _resource_names.assert_unique_dataset_name(name, owner_user_id, user, exclude_dataset_id=exclude_dataset_id)


def assert_unique_model_name(name: Any, owner_user_id: str, *, exclude_run_id: str = "") -> None:
    return _resource_names.assert_unique_model_name(name, owner_user_id, exclude_run_id=exclude_run_id)


from .training.user_state import TrainingUserState, TrainingStateAccess, TrainingStateStorage, clear_training_private_state
from .training.task_models import TrainingTaskModels, training_task_model_variant
from .pipeline.training_sync import PipelineTrainingSync, PipelineTrainingRecords, PipelineTrainingModels
from .detection.training_candidate_sync import TrainingCandidateSync, CandidateTrainingRecords

_training_user_state = TrainingUserState(
    defaults=lambda: DEFAULT_CONFIG["training"], legacy_owner=lambda: LEGACY_OWNER_ID,
    access=TrainingStateAccess(owner=lambda record: record_owner_id(record),
        visible=lambda record, user, target=None: record_visible_to_user(record, user, target),
        admin=lambda user: user_is_admin(user), current_owner=lambda: current_owner_fields()),
    storage=TrainingStateStorage(find=lambda job_id: find_training_task(job_id), load=lambda: load_config(), save=lambda config: save_config(config)),
    sync_pipeline=lambda task: sync_pipeline_training_state_from_task(task),
)
_training_task_models = TrainingTaskModels(specs=lambda: list_trained_model_specs())
_pipeline_training_sync = PipelineTrainingSync(
    guard=lambda: _pipeline_tasks_lock,
    records=PipelineTrainingRecords(load=lambda task_id: load_pipeline_task(task_id), save=lambda task: save_pipeline_task(task)),
    models=PipelineTrainingModels(resolve=lambda task, job_id: training_task_model_id(task, job_id), link=lambda task: link_pipeline_trained_model(task)),
    normalize_method=lambda: normalize_pipeline_detection_method, clean_id=lambda: sanitize_ai_detection_task_id,
    sync_candidate=lambda task, **kwargs: sync_auto_optimize_training_candidate_from_task(task, **kwargs),
)
_training_candidate_sync = TrainingCandidateSync(
    guard=lambda: _auto_optimize_lock,
    records=CandidateTrainingRecords(load=lambda task_id: load_auto_optimize_state(task_id), save=lambda state: save_auto_optimize_state(state)),
    clean_id=lambda value: sanitize_ai_detection_task_id(value),
    stop_capture=lambda state, model_id, **kwargs: auto_optimize_stop_capture_for_model_locked(state, model_id, **kwargs),
)


def default_training_state() -> dict[str, Any]:
    return _training_user_state.default_training_state()




def normalize_training_owner_key(owner_user_id: Any) -> str:
    return _training_user_state.normalize_training_owner_key(owner_user_id)


def training_state_store(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _training_user_state.training_state_store(config)


def sanitize_training_state_for_user(
    training: dict[str, Any] | None,
    user: dict[str, Any],
    selected_ids: set[str],
    target_user_id: str | None = None,
) -> dict[str, Any]:
    return _training_user_state.sanitize_training_state_for_user(training, user, selected_ids, target_user_id)


def training_state_for_user(
    config: dict[str, Any],
    user: dict[str, Any],
    selected_ids: set[str],
    target_user_id: str | None = None,
) -> dict[str, Any]:
    return _training_user_state.training_state_for_user(config, user, selected_ids, target_user_id)


def set_training_state_for_user(config: dict[str, Any], user: dict[str, Any], training_state: dict[str, Any]) -> None:
    return _training_user_state.set_training_state_for_user(config, user, training_state)


def sync_training_state_from_task(job_id: str) -> None:
    return _training_user_state.sync_training_state_from_task(job_id)




def training_task_model_id(task: dict[str, Any], job_id: str) -> str:
    return _training_task_models.training_task_model_id(task, job_id)


def auto_optimize_task_id_from_pipeline_task(pipeline_task_id: str, pipeline_task: dict[str, Any] | None = None) -> str:
    return _pipeline_training_sync.auto_optimize_task_id_from_pipeline_task(pipeline_task_id, pipeline_task)


def sync_auto_optimize_training_candidate_from_task(
    task: dict[str, Any],
    *,
    ai_task_id: str,
    model_id: str,
) -> None:
    return _training_candidate_sync.sync_auto_optimize_training_candidate_from_task(task, ai_task_id=ai_task_id, model_id=model_id)


def sync_pipeline_training_state_from_task(task: dict[str, Any]) -> None:
    return _pipeline_training_sync.sync_pipeline_training_state_from_task(task)


from .auth.account_projections import AccountProjections
from .auth.account_projection_ports import AccountAccess, AccountConfig, AccountModels, AccountMedia

_account_projections = AccountProjections(
    access=AccountAccess(
        current_auth_user=lambda: current_auth_user,
        user_is_admin=lambda: user_is_admin,
        user_has_permission=lambda: user_has_permission,
        include_internal_runtime_details=lambda: include_internal_runtime_details,
        record_mutable_by_user=lambda: record_mutable_by_user,
        record_visible_to_user=lambda: record_visible_to_user,
    ),
    config=AccountConfig(
        accessory_uid=lambda: accessory_uid,
        training_state_for_user=lambda: training_state_for_user,
        PLC_CAPTURE_RESULTS_KEY=lambda: PLC_CAPTURE_RESULTS_KEY,
        scope_config_for_user=lambda: scope_config_for_user,
        load_config=lambda: load_config,
    ),
    models=AccountModels(
        selected_model_spec=lambda: selected_model_spec,
        public_ai_detection_status_for_user=lambda: public_ai_detection_status_for_user,
    ),
    media=AccountMedia(
        OUTPUT_DIR=lambda: OUTPUT_DIR,
    ),
)


def merge_scoped_accessory_updates(full_config: dict[str, Any], scoped_config: dict[str, Any], user: dict[str, Any]) -> None:
    return _account_projections.merge_scoped_accessory_updates(full_config, scoped_config, user)


def scope_config_for_user(config: dict[str, Any], user: dict[str, Any] | None = None, target_user_id: str | None = None) -> dict[str, Any]:
    return _account_projections.scope_config_for_user(config, user, target_user_id)


require_record_access = _record_access.require_record_access


require_permission = _access_control.require_permission


def require_analyze_model_permission(model_id: str | None) -> None:
    return _account_projections.require_analyze_model_permission(model_id)


def output_path_visible_to_user(request_path: str, user: dict[str, Any]) -> bool:
    return _account_projections.output_path_visible_to_user(request_path, user)


from .auth.login_limits import LoginLimitSettings, LoginRateLimiter, request_client_ip, login_rate_limit_keys
_login_limiter = _authentication.limits
_login_rate_limit_lock = _login_limiter.lock
_login_failures = _login_limiter.failures
_login_blocked_until = _login_limiter.blocked_until


prune_login_rate_limit_state = _login_limiter.prune_login_rate_limit_state


enforce_login_rate_limit = _login_limiter.enforce_login_rate_limit


record_failed_login_attempt = _login_limiter.record_failed_login_attempt


clear_failed_login_attempts = _login_limiter.clear_failed_login_attempts


from .auth.http_composition import AuthenticationHttp, AuthenticationHttpPolicy

_authentication_http = _authentication_domain.http(
    AuthenticationHttpPolicy(
        output_visible=_account_projections.output_path_visible_to_user,
        same_origin=_public_network_policy.same_origin,
        cors_origin_allowed=_public_network_policy.cors_origin_allowed,
    ),
)
_documentation_access = _authentication_http.documentation
require_docs_admin = _documentation_access.require_docs_admin


def is_private_or_local_host(hostname: str) -> bool:
    return _public_network_policy.is_private_or_local_host(hostname)


def sanitize_url_for_public_user(value: Any) -> str:
    return _public_network_policy.sanitize_url_for_public_user(value)


def sanitize_path_for_public_user(value: Any) -> str:
    return _public_network_policy.sanitize_path_for_public_user(value)


def include_internal_runtime_details(user: dict[str, Any] | None) -> bool:
    return _public_network_policy.include_internal_runtime_details(user)


reject_untrusted_cross_origin_writes = _authentication_http.register_security(app)

app.mount(
    "/static/assets",
    StaticFiles(directory=REACT_PRODUCTION_ASSETS_DIR, check_dir=False),
    name="react-production-assets",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount(
    "/react-preview/assets",
    StaticFiles(directory=REACT_PREVIEW_ASSETS_DIR, check_dir=False),
    name="react-preview-assets",
)
from local_inspection_service.storage.artifacts.http import ArtifactStaticFiles

app.mount("/outputs", ArtifactStaticFiles(directory=OUTPUT_DIR, runtime_provider=lambda: _business_files.runtime_provider()), name="outputs")

from .detection.model_selection import ModelSelection
from .detection.local_models import LocalModels

_model_selection = ModelSelection(
    specialized=lambda config: list_ai_detection_specialized_model_specs(config),
    trained=lambda *args: list_trained_model_specs(*args), registry=lambda: MODEL_REGISTRY,
    default_id=lambda: DEFAULT_MODEL_ID, removed=lambda feature: removed_phase1_feature(feature),
)
_local_models = LocalModels(
    select=lambda model_id, config: selected_model_spec(model_id, config), factory=lambda: YOLO,
    legacy_specs=lambda: legacy_model_specs(), trained_specs=lambda *args: list_trained_model_specs(*args),
    files=_business_files,
)
# Compatibility objects for existing maintenance scripts; state belongs to LocalModels.
_models = _local_models.models
_model_paths = _local_models.paths
from .detection.warmup_policy import (
    yolo_warmup_enabled, yolo_warmup_limit, WarmupPipeline, WarmupModels, WarmupCandidates,
)
from .detection.warmup_prediction import WarmupPrediction
from .runtime.yolo_warmup import YoloWarmup, WarmupOperations

_warmup_candidates = WarmupCandidates(
    pipeline=WarmupPipeline(tasks=lambda: load_pipeline_tasks(), method=lambda: normalize_pipeline_detection_method,
                            status=lambda task: pipeline_task_model_status(task), model_id=lambda task: pipeline_task_model_id(task)),
    models=WarmupModels(default_id=lambda: DEFAULT_MODEL_ID, trained=lambda *args: list_trained_model_specs(*args),
                        resolve=lambda: resolve_service_path), limit=lambda: yolo_warmup_limit(),
)
_warmup_prediction = WarmupPrediction(
    select=lambda model_id, config: selected_model_spec(model_id, config),
    load=lambda: model, device=lambda: yolo_inference_device(),
)
_yolo_warmup_runtime = YoloWarmup(WarmupOperations(
    enabled=lambda: yolo_warmup_enabled(), config=lambda: load_config(),
    candidates=lambda config: yolo_warmup_configured_model_ids(config),
    warm=lambda model_id, config: warm_yolo_model_once(model_id, config),
    loaded_ids=lambda config: yolo_loaded_model_ids(config), error_text=lambda: bounded_text,
), scope=_runtime_repositories.thread_scope)
_yolo_warmup_lock = _yolo_warmup_runtime.lock
_yolo_warmup_state = _yolo_warmup_runtime.state
_incoming_text_store_lock = threading.RLock()
from .accessories.cutout_runtime import RembgSessionRuntime as _RembgSessionRuntime
_rembg_runtime = _RembgSessionRuntime()
from .runtime.image_worker import ImageWorkerRuntime
_image_worker_runtime = ImageWorkerRuntime(
    target=lambda: image_worker_loop, threads=lambda: threading.Thread,
    scope=_runtime_repositories.thread_scope,
)
_candidate_store_lock = threading.RLock()
from .runtime.training_tasks import TrainingTaskRuntime, TrainingThreadLifecycle
_training_task_runtime = TrainingTaskRuntime(scope=_runtime_repositories.thread_scope)
_training_task_lock = _training_task_runtime.lock
_image_worker_processes = _image_worker_runtime.processes
_training_task_threads = _training_task_runtime.threads
_training_task_delete_tombstones = _training_task_runtime.tombstones
from .training.auto_optimization_runtime_state import AutoOptimizationRuntimeState
_auto_optimization_runtime = AutoOptimizationRuntimeState()
_auto_optimize_lock = _auto_optimization_runtime.lock
_auto_optimize_label_threads = _auto_optimization_runtime.label_threads
_auto_optimize_shadow_threads = _auto_optimization_runtime.shadow_threads
AUTO_OPTIMIZE_MASK_MAX_PARALLEL = max(1, min(8, int(os.environ.get("VANTALINE_AUTO_OPT_MASK_MAX_PARALLEL", "3"))))
AUTO_OPTIMIZE_MASK_MAX_ATTEMPTS = max(1, min(6, int(os.environ.get("VANTALINE_AUTO_OPT_MASK_MAX_ATTEMPTS", "3"))))
AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS = max(0.0, float(os.environ.get("VANTALINE_AUTO_OPT_MASK_RETRY_BASE_SECONDS", "5")))
AUTO_OPTIMIZE_MASK_RETRY_MAX_SECONDS = max(
    AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS,
    float(os.environ.get("VANTALINE_AUTO_OPT_MASK_RETRY_MAX_SECONDS", "45")),
)
AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT = max(1, min(10, int(os.environ.get("VANTALINE_AUTO_OPT_REAL_BBOX_SAMPLE_WEIGHT", "3"))))
from .training.auto_optimization_settings import AutoOptimizationSettings, normalize_expected_production_count

AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE = max(0, min(20, int(os.environ.get("VANTALINE_AUTO_OPT_NEGATIVES_PER_REAL_IMAGE", "3"))))
_auto_optimization_settings = AutoOptimizationSettings(AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE)
_auto_optimize_image_request_semaphore = threading.BoundedSemaphore(AUTO_OPTIMIZE_MASK_MAX_PARALLEL)
_windows_worker_status_lock = threading.RLock()
_windows_worker_status_cache: dict[str, Any] = {}
_windows_worker_status_cache_at = 0.0
MAX_PARALLEL_IMAGE_WORKERS = 2
IMAGE_WORKER_STALE_SECONDS = max(30, int(os.environ.get("LOCAL_INSPECTION_IMAGE_WORKER_STALE_SECONDS", "180")))
IMAGE_WORKER_LOG_TAIL_BYTES = 64000
WINDOWS_WORKER_STATUS_CACHE_SECONDS = max(2.0, float(os.environ.get("VANTALINE_WORKER_STATUS_CACHE_SECONDS", "15")))
IMAGE_REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_REFERENCE_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
MAX_TEXT_ACCESSORY_IMAGES = 2
MAX_IMAGE_WORKER_INPUTS = 10
MAX_VIDEO_REFERENCE_FRAMES = 6
PREVIEW_CACHE_SCHEMA_VERSION = "preview-cache-v4-object-overlap-material-alpha-scale"
ANCHOR_POLICY_VERSION = "anchor-replacement-2026-05-27"
from .accessories.policy import TRANSPARENT_OBJECT_KEYWORDS
POSE_ANCHOR_DIR = DATA_DIR / "anchor_pose_guides"
POSE_ANCHOR_IMAGES = {
    "upright": POSE_ANCHOR_DIR / "endface_9bar_anchor.png",
    "lying": POSE_ANCHOR_DIR / "flat_9bar_anchor.png",
}
POSE_TARGET_GUIDE_IMAGES = {
    "upright": [POSE_ANCHOR_DIR / "circle_endface_9target_guide.png"],
    "lying": [],
}

POSE_COLLECTION_BATCHES: list[tuple[str, str, list[str]]] = [
    ("top_row", "上排三视角", ["top-left", "top-center", "top-right"]),
    ("middle_row", "中排三视角", ["middle-left", "center", "middle-right"]),
    ("bottom_row", "下排三视角", ["bottom-left", "bottom-center", "bottom-right"]),
]

MANUAL_TYPE_LABELS = {
    "warranty_service": "Warranty Service Manual",
    "battery_instruction": "Battery Instruction Manual",
    "download_service": "Download Service Manual",
    "service_qr": "Service QR Manual",
}

MANUAL_TYPE_CLASS_IDS = {
    "warranty_service": 1,
    "battery_instruction": 2,
    "download_service": 3,
    "service_qr": 4,
}

MANUAL_TYPE_KEYWORDS: dict[str, list[tuple[str, int]]] = {
    "warranty_service": [
        ("warranty", 8),
        ("service conditions", 8),
        ("garantie", 5),
        ("garantia", 5),
        ("garancija", 5),
        ("garanti", 4),
        ("warunki gwarancji", 5),
        ("servicebetingelser", 5),
        ("condiciones de servicio", 5),
    ],
    "battery_instruction": [
        ("ge-ps", 10),
        ("cordless", 7),
        ("branch chainsaw", 9),
        ("chainsaw", 6),
        ("akku", 6),
        ("battery", 6),
        ("operating instructions", 5),
        ("original operating", 5),
        ("motosega", 5),
        ("potatura", 4),
        ("batteridriven", 5),
        ("podadora", 4),
        ("elagueuse", 4),
    ],
    "download_service": [
        ("download", 10),
        ("downloading", 10),
        ("download bereit", 8),
        ("full operating instructions", 9),
        ("detailed", 7),
        ("detailed instruction", 8),
        ("detailed manual", 8),
        ("telechargeable", 6),
        ("scaricabili", 6),
        ("descargarse", 6),
        ("ladda ned", 6),
        ("allalaadimiseks", 5),
        ("descargat", 5),
    ],
    "service_qr": [
        ("larger format", 10),
        ("larger", 7),
        ("bigger", 7),
        ("einhell service", 9),
        ("eschenstrabe", 10),
        ("eschenstrasse", 10),
        ("landau", 8),
        ("09951", 10),
        ("service-de", 10),
        ("larger instructions", 8),
        ("larger manual", 8),
        ("format plus grand", 6),
        ("grobere anleitung", 8),
        ("gröbere anleitung", 8),
    ],
}


from .schemas.plc import (
    PlcConfigRequest,
    PlcCaptureSessionRequest,
    PlcCaptureSessionHeartbeatRequest,
    PlcWebSerialConfigRequest,
    PlcWorkstationPairRequest,
    PlcWorkstationVerifyRequest,
    PlcWorkstationLeaseRequest,
    PlcWorkstationLeaseActivateRequest,
    PlcWorkstationLeaseHeartbeatRequest,
    PlcWorkstationLeaseRebindRequest,
    PlcWebSerialAttemptRequest,
    PlcWebSerialDiagnosticReceiptRequest,
    PlcWebSerialDiagnosticConfirmRequest,
    PlcWebSerialReceiptOperation,
    PlcWebSerialReceiptRequest,
)






























STANDARD_PAPER_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
}

# Physical-to-pixel scale models a top-down inspection camera mounted ~70cm
# above the belt. At that height a moderate industrial lens frames roughly a
# 600mm-wide field of view, so a 1280px-wide canvas yields ~2.13 px/mm. This
# makes parts read at a realistic, prominent size while keeping every
# accessory's relative size physically consistent.
INSPECTION_CAMERA_HEIGHT_MM = 700.0
INSPECTION_CAMERA_FRAME_WIDTH_MM = 600.0
MM_TO_PREVIEW_PX = 1280.0 / INSPECTION_CAMERA_FRAME_WIDTH_MM
# Default object size is calibrated to the real reference photo ratio:
# bottle long side ~= 0.55-0.60 of an A4 manual long side in the 1280x900 preview.
DEFAULT_OBJECT_SIZE_MM = {"length_mm": 170.0, "width_mm": 38.0, "height_mm": 38.0}
# Object accessories no longer carry hand-entered dimensions. Instead the user
# picks a known-size reference object (and includes one photo of the part next to
# it); the size-inference agent calibrates the part's real dimensions from that
# reference. The catalog below provides the ground-truth scale for each option.
SIZE_REFERENCE_OBJECTS: dict[str, dict[str, Any]] = {
    "a4": {"id": "a4", "label": "A4 纸", "kind": "paper", "long_mm": 297.0, "short_mm": 210.0,
           "note": "A4 打印纸，长边 297mm、短边 210mm。"},
    "a5": {"id": "a5", "label": "A5 纸", "kind": "paper", "long_mm": 210.0, "short_mm": 148.0,
           "note": "A5 打印纸，长边 210mm、短边 148mm。"},
    "b5": {"id": "b5", "label": "B5 纸", "kind": "paper", "long_mm": 250.0, "short_mm": 176.0,
           "note": "B5 打印纸，长边 250mm、短边 176mm。"},
    "ruler": {"id": "ruler", "label": "直尺/卷尺", "kind": "ruler",
              "note": "直尺或卷尺：直接读取其厘米/毫米刻度作为比例尺（1 大格=10mm）。"},
}
DEFAULT_SIZE_REFERENCE = "a4"


from .accessories.physical_dimensions import ReferenceDimensions
from .accessories.physical_dimension_ports import ReferenceDimensionValues

_reference_dimensions = ReferenceDimensions(ReferenceDimensionValues(
    SIZE_REFERENCE_OBJECTS=lambda: SIZE_REFERENCE_OBJECTS,
    normalize_size_reference=lambda: normalize_size_reference,
    MM_TO_PREVIEW_PX=lambda: MM_TO_PREVIEW_PX,
    DEFAULT_OBJECT_SIZE_MM=lambda: DEFAULT_OBJECT_SIZE_MM,
))


def normalize_size_reference(value: Any) -> str:
    return _reference_dimensions.normalize_size_reference(value)


def size_reference_payload(reference_key: str) -> dict[str, Any] | None:
    return _reference_dimensions.size_reference_payload(reference_key)
# Legacy anchor/grid "pose collection" generation (the source of the old
# black-stick/anchor sprites) is disabled. Object standard images are now
# generated inside the training pipeline as single-object top-down photos and
# segmented into clean sprites.
POSE_COLLECTION_GRID_ENABLED = False
# Bump when the agent-MCP sprite build pipeline changes (segmentation method,
# render scale, metadata) so cached sprites on existing accessories are rebuilt
# on the next task instead of being reused stale.
AGENT_MCP_SPRITE_BUILD_VERSION = 4
PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION = 2
PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES = 3
PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES = 3
PHOTO_HIGHLIGHT_MASK_MAX_SIDE = 1024
PHOTO_HIGHLIGHT_MASK_RGB = (0, 255, 0)
PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS = 3
CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD = 0.05
CHROMA_SCREEN_OPTIONS: dict[str, dict[str, Any]] = {
    "green": {"name": "green", "rgb": (0, 255, 0), "hex": "#00FF00", "label": "pure green"},
    "blue": {"name": "blue", "rgb": (0, 0, 255), "hex": "#0000FF", "label": "pure blue"},
    "red": {"name": "red", "rgb": (255, 0, 0), "hex": "#FF0000", "label": "pure red"},
}
# Pose Planner Agent: a multimodal agent analyses each accessory's material and
# decides the structured pose set (count + per-pose generation instructions) as
# strict JSON. Rules only act as guardrail/validation (schema, bounds, physics,
# dedup) and as a fallback when the provider is unavailable. The plan is cached
# once per accessory so AI pose images are generated a single time and reused.
AGENT_MCP_POSE_PLAN_VERSION = 1
AGENT_MCP_POSE_PLAN_MIN_POSES = 1
AGENT_MCP_POSE_PLAN_MAX_POSES = 6
AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE = 0.35
SOURCE_ASPECT_ELONGATED_MIN_RATIO = 1.35
UPRIGHT_SCALE_CORRECTION_MIN_RATIO = 1.01
UPRIGHT_SCALE_CORRECTION_MAX_RATIO = 3.25
UPRIGHT_SCALE_VISUAL_ADJUSTMENT = 0.8
PREVIEW_CANVAS_SIZE_PX = (1280, 900)
# Detection (bbox) label policy. Each object/document keeps its FULL (amodal)
# bounding box even when another part is pasted on top of it, so an occluded part
# is never truncated to a half-box. A part is only dropped from the labels when it
# is almost entirely hidden (and therefore not learnably visible).
DETECTION_MAX_OCCLUSION_FRACTION = 0.85
DETECTION_MIN_VISIBLE_AREA_PX = 220
# Background-plate derivation guards. A raw capture can be 4096x3072+, which makes
# cv2.inpaint(TELEA) on a large mask pathologically slow (the original incident
# pegged a core for 50+ min). We therefore downscale to a bounded working size,
# cap the inpaint radius, skip inpaint entirely when the hole is too large (cheap
# median+noise fill instead), and enforce a wall-clock budget. The plate is only
# an auxiliary background, so mild blur from up/downscaling is acceptable.
PIPELINE_BG_PLATE_MAX_SIDE = 1280
PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS = 10
PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC = 0.35
PIPELINE_BG_PLATE_TIME_BUDGET_S = 20.0
PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES = 12
PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES = 48
PIPELINE_BG_MATCH_DISTANCE_THRESHOLD = 0.22
BACKGROUND_ROI_PX = (70, 100, 1210, 800)
# Background sets are mutable runtime data.  Keep them below DATA_DIR so an
# immutable release never needs write access to its own source tree.
BACKGROUND_DIR = DATA_DIR / "backgrounds"
BACKGROUND_SETS_DIR = BACKGROUND_DIR / "sets"
BACKGROUND_SETS_MANIFEST = BACKGROUND_DIR / "background_sets.json"
DEFAULT_BACKGROUND_IMAGE = BACKGROUND_DIR / "conveyor_surface_topdown_ai_reference5.png"
STANDARDIZED_MANUALS_DIR = ROOT / "standardized_manuals"
PRECISE_MANUALS_DIR = ROOT / "manuals_from_individual_sources_precise"
BACKGROUND_SIZE_MM = {
    "width_mm": round((BACKGROUND_ROI_PX[2] - BACKGROUND_ROI_PX[0]) / MM_TO_PREVIEW_PX, 2),
    "height_mm": round((BACKGROUND_ROI_PX[3] - BACKGROUND_ROI_PX[1]) / MM_TO_PREVIEW_PX, 2),
    "mm_per_px": round(1 / MM_TO_PREVIEW_PX, 4),
    "px_per_mm": MM_TO_PREVIEW_PX,
}


def optional_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


from .accessories.physical_dimensions import AccessoryDimensions as _AccessoryDimensions
from .accessories.physical_dimension_ports import DimensionValues as _DimensionValues, DimensionUpdates as _DimensionUpdates
_accessory_dimensions = _AccessoryDimensions(
    _DimensionValues(number=lambda: optional_float, papers=lambda: STANDARD_PAPER_SIZES_MM, objects=lambda: DEFAULT_OBJECT_SIZE_MM),
    _DimensionUpdates(material=lambda: accessory_material_type, payload=lambda: physical_size_payload),
)

def physical_size_payload(
    material_type: str,
    paper_preset: str = "A4",
    paper_width_mm: Any = None,
    paper_height_mm: Any = None,
    object_length_mm: Any = None,
    object_width_mm: Any = None,
    object_height_mm: Any = None,
) -> dict[str, Any]:
    return _accessory_dimensions.physical_size_payload(material_type, paper_preset, paper_width_mm, paper_height_mm, object_length_mm, object_width_mm, object_height_mm)


def ai_profile_dimensions_from_physical_size(physical_size: dict[str, Any] | None) -> dict[str, Any]:
    return _accessory_dimensions.ai_profile_dimensions_from_physical_size(physical_size)


def ai_profile_top_view_aspect_ratio(dimensions: dict[str, Any] | None) -> float:
    return _accessory_dimensions.ai_profile_top_view_aspect_ratio(dimensions)


def normalize_ai_profile_dimensions(raw: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    return _accessory_dimensions.normalize_ai_profile_dimensions(raw, fallback)


def apply_ai_profile_dimensions_to_physical_size(item: dict[str, Any], dimensions: dict[str, Any] | None) -> bool:
    """When the AI Profile judges real-world dimensions, feed them into the
    accessory physical_size so the compositor renders a consistent footprint for
    this accessory across every training set."""
    return _accessory_dimensions.apply_ai_profile_dimensions_to_physical_size(item, dimensions)


from .runtime.directories import ServiceDirectories, LocalPathMigration

_service_directories = ServiceDirectories(
    paths=lambda: (UPLOAD_DIR, OUTPUT_DIR, DATA_DIR, NORMALIZED_DIR, TRAINING_JOBS_DIR,
                   TRAINING_TASKS_DIR, ACCESSORY_CANDIDATES_DIR, AUTO_OPTIMIZE_DIR,
                   IMAGE_WORKER_LOG_DIR, BACKGROUND_DIR, BACKGROUND_SETS_DIR),
    config_path=lambda: CONFIG_PATH,
    defaults=lambda: DEFAULT_CONFIG,
    files=lambda: _business_files,
    save_config=lambda: save_config,
    migrate=lambda: migrate_persisted_local_paths_once,
)
ensure_dirs = _service_directories.ensure


_config_io_lock = threading.RLock()
PLC_CONTROL_GENERATION_KEY = "plc_control_generation"
PLC_RUNTIME_COORDINATION_KEY = "plc_runtime_coordination"
PLC_CAPTURE_RESULTS_KEY = "plc_capture_results"
PLC_PROTECTED_CONFIG_KEYS = (
    "plc",
    PLC_CONTROL_GENERATION_KEY,
    "plc_dispatches",
    PLC_RUNTIME_COORDINATION_KEY,
    PLC_CAPTURE_RESULTS_KEY,
)
PLC_IO_CONFIG_FIELDS = frozenset(DEFAULT_PLC_CONFIG)
from .plc.persisted_validation import (
    PLC_LEGACY_IO_CONFIG_FIELDS,
    PLC_PERSISTED_DISPATCH_FIELDS,
    PLC_SUPPORTED_RECORD_VERSIONS,
    build_plc_dispatch_plan,
    build_plc_v1_dispatch_plan,
    normalize_plc_v1_snapshot,
    verify_persisted_plc_dispatch,
)
_plc_namespace_write_authorized: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "plc_namespace_write_authorized", default=False
)


from .plc.workstation_repository import PlcWorkstationRepository
from .plc.workstation_repository_ports import WorkstationRepositoryFiles, WorkstationRepositoryPolicy, WorkstationRepositoryStorage

_plc_workstation_repository = PlcWorkstationRepository(
    files=WorkstationRepositoryFiles(
        _business_files=lambda: _business_files,
        DATA_DIR=lambda: DATA_DIR,
        PLC_WEB_SERIAL_STATE_PATH=lambda: PLC_WEB_SERIAL_STATE_PATH,
    ),
    policy=WorkstationRepositoryPolicy(
        PLC_WEB_SERIAL_JSON_TEST_ENV=lambda: PLC_WEB_SERIAL_JSON_TEST_ENV,
        PlcConfigError=lambda: PlcConfigError,
        SYSTEM_OWNER_ID=lambda: SYSTEM_OWNER_ID,
    ),
    storage=WorkstationRepositoryStorage(
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        _config_io_lock=lambda: _config_io_lock,
        _plc_web_serial_empty_state=lambda: _plc_web_serial_empty_state,
        _plc_web_serial_load_local=lambda: _plc_web_serial_load_local,
        _plc_web_serial_save_local=lambda: _plc_web_serial_save_local,
    ),
)


def _plc_web_serial_empty_state() -> dict[str, dict[str, Any]]:
    return _plc_workstation_repository._plc_web_serial_empty_state()


def _plc_web_serial_load_local() -> dict[str, dict[str, Any]]:
    return _plc_workstation_repository._plc_web_serial_load_local()


def _plc_web_serial_save_local(state: dict[str, dict[str, Any]]) -> None:
    return _plc_workstation_repository._plc_web_serial_save_local(state)


def _plc_web_serial_record(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return _plc_workstation_repository._plc_web_serial_record(row)


def _plc_workstation_row(record: dict[str, Any]) -> dict[str, Any]:
    return _plc_workstation_repository._plc_workstation_row(record)


def _plc_workstation_lease_row(record: dict[str, Any]) -> dict[str, Any]:
    return _plc_workstation_repository._plc_workstation_lease_row(record)


def _plc_web_serial_dispatch_row(record: dict[str, Any]) -> dict[str, Any]:
    return _plc_workstation_repository._plc_web_serial_dispatch_row(record)


def _plc_web_serial_upsert_row(table_name: str, row: dict[str, Any], local_key: str, row_id: str) -> None:
    return _plc_workstation_repository._plc_web_serial_upsert_row(table_name, row, local_key, row_id)


def _plc_web_serial_mutate(
    station_id: str,
    dispatch_id: str | None,
    mutator: Callable[[dict[str, dict[str, Any] | None]], None],
) -> dict[str, dict[str, Any] | None]:
    return _plc_workstation_repository._plc_web_serial_mutate(station_id, dispatch_id, mutator)


from .plc.station_service import PlcStationService
from .plc.station_ports import StationStorage, StationIdentity, StationPolicy, StationProjection

_plc_station_service = PlcStationService(
    storage=StationStorage(
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        _config_io_lock=lambda: _config_io_lock,
        _plc_web_serial_load_local=lambda: _plc_web_serial_load_local,
        _plc_web_serial_record=lambda: _plc_web_serial_record,
        _plc_web_serial_mutate=lambda: _plc_web_serial_mutate,
        _plc_web_serial_upsert_row=lambda: _plc_web_serial_upsert_row,
        _plc_workstation_row=lambda: _plc_workstation_row,
        _plc_workstation_lease_row=lambda: _plc_workstation_lease_row,
        _plc_web_serial_dispatch_row=lambda: _plc_web_serial_dispatch_row,
    ),
    identity=StationIdentity(
        PLC_WORKSTATION_COOKIE=lambda: PLC_WORKSTATION_COOKIE,
        PLC_WORKSTATION_COOKIE_TTL_SECONDS=lambda: PLC_WORKSTATION_COOKIE_TTL_SECONDS,
        SYSTEM_OWNER_ID=lambda: SYSTEM_OWNER_ID,
        _plc_web_serial_token_hash=lambda: _plc_web_serial_token_hash,
        current_auth_user=lambda: current_auth_user,
        request_is_https=lambda: request_is_https,
        plc_web_serial_station_from_request=lambda: plc_web_serial_station_from_request,
    ),
    policy=StationPolicy(
        clock=lambda: time.time,
        PlcConfigError=lambda: PlcConfigError,
        HTTPException=lambda: HTTPException,
        DEFAULT_WEB_SERIAL_CONFIG=lambda: DEFAULT_WEB_SERIAL_CONFIG,
        WEB_SERIAL_ACTIVE_LEASE_SECONDS=lambda: WEB_SERIAL_ACTIVE_LEASE_SECONDS,
        WEB_SERIAL_HEARTBEAT_SECONDS=lambda: WEB_SERIAL_HEARTBEAT_SECONDS,
        WEB_SERIAL_PROTOCOL_VERSION=lambda: WEB_SERIAL_PROTOCOL_VERSION,
        migrate_web_serial_config=lambda: migrate_web_serial_config,
        normalize_web_serial_config=lambda: normalize_web_serial_config,
        web_serial_profile_fingerprint=lambda: web_serial_profile_fingerprint,
    ),
    projection=StationProjection(
        current_release_version=lambda: current_release_version,
        build_web_serial_capture_read_plan=lambda: build_web_serial_capture_read_plan,
        web_serial_resolved_addresses=lambda: web_serial_resolved_addresses,
        plc_web_serial_current_lease=lambda: plc_web_serial_current_lease,
        plc_web_serial_recent_dispatches=lambda: plc_web_serial_recent_dispatches,
        plc_web_serial_ensure_current_station_contract=lambda: plc_web_serial_ensure_current_station_contract,
        plc_web_serial_station_payload=lambda: plc_web_serial_station_payload,
    ),
)


def _plc_web_serial_token_hash(token: str) -> str:
    return _plc_station_service._plc_web_serial_token_hash(token)


def plc_web_serial_station_from_request(request: Request) -> dict[str, Any] | None:
    return _plc_station_service.plc_web_serial_station_from_request(request)


def require_plc_web_serial_station(request: Request) -> dict[str, Any]:
    return _plc_station_service.require_plc_web_serial_station(request)


def plc_web_serial_current_lease(station_id: str) -> dict[str, Any] | None:
    return _plc_station_service.plc_web_serial_current_lease(station_id)


def plc_web_serial_recent_dispatches(station_id: str, limit: int = 20) -> list[dict[str, Any]]:
    return _plc_station_service.plc_web_serial_recent_dispatches(station_id, limit)


def plc_web_serial_ensure_current_station_contract(station: dict[str, Any]) -> dict[str, Any]:
    return _plc_station_service.plc_web_serial_ensure_current_station_contract(station)


def plc_web_serial_station_payload(station: dict[str, Any]) -> dict[str, Any]:
    return _plc_station_service.plc_web_serial_station_payload(station)


def plc_web_serial_unpaired_payload() -> dict[str, Any]:
    return _plc_station_service.plc_web_serial_unpaired_payload()


def plc_web_serial_list_workstations() -> list[dict[str, Any]]:
    return _plc_station_service.plc_web_serial_list_workstations()


def plc_web_serial_pair(request: Request, response: Response, name: str, station_id: str | None = None) -> dict[str, Any]:
    return _plc_station_service.plc_web_serial_pair(request, response, name, station_id)


def plc_web_serial_update_config(station_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    return _plc_station_service.plc_web_serial_update_config(station_id, candidate)


def plc_web_serial_set_verified(station_id: str, verified: bool) -> dict[str, Any]:
    return _plc_station_service.plc_web_serial_set_verified(station_id, verified)


from .plc.lease_acquisition import LeaseAcquisition as _LeaseAcquisition
from .plc.lease_acquisition_ports import LeaseAcquisitionPorts as _LeaseAcquisitionPorts

_plc_lease_acquisition = _LeaseAcquisition(
    _LeaseAcquisitionPorts(
        current_user=lambda: current_auth_user,
        release_version=lambda: current_release_version,
        fullmatch=lambda: re.fullmatch,
        protocol_version=lambda: WEB_SERIAL_PROTOCOL_VERSION,
        require_model_permission=lambda: require_analyze_model_permission,
        mutate=lambda: _plc_web_serial_mutate,
        record=lambda: _plc_web_serial_record,
        migrate_config=lambda: migrate_web_serial_config,
        clock=lambda: time.time,
        uuid4=lambda: uuid.uuid4,
        connecting_ttl=lambda: WEB_SERIAL_CONNECTING_LEASE_SECONDS,
        active_ttl=lambda: WEB_SERIAL_ACTIVE_LEASE_SECONDS,
        lease_row=lambda: _plc_workstation_lease_row,
        config_error=lambda: PlcConfigError,
    )
)


def plc_web_serial_claim_connecting_lease(station_id: str, request: PlcWorkstationLeaseRequest) -> dict[str, Any]:
    return _plc_lease_acquisition.claim(station_id, request)


def plc_web_serial_activate_lease(station_id: str, request: PlcWorkstationLeaseActivateRequest) -> dict[str, Any]:
    return _plc_lease_acquisition.activate(station_id, request)


from .plc.lease_maintenance import LeaseMaintenance as _LeaseMaintenance
from .plc.lease_maintenance_ports import LeaseMaintenancePorts as _LeaseMaintenancePorts

_plc_lease_maintenance = _LeaseMaintenance(
    _LeaseMaintenancePorts(
        mutate=lambda: _plc_web_serial_mutate,
        record=lambda: _plc_web_serial_record,
        lease_row=lambda: _plc_workstation_lease_row,
        current_user=lambda: current_auth_user,
        clock=lambda: time.time,
        active_ttl=lambda: WEB_SERIAL_ACTIVE_LEASE_SECONDS,
        config_error=lambda: PlcConfigError,
        require_active_lease=lambda: _plc_web_serial_require_active_lease,
    )
)


def plc_web_serial_heartbeat(station_id: str, request: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
    return _plc_lease_maintenance.heartbeat(station_id, request)


def plc_web_serial_rebind_model(station_id: str, request: PlcWorkstationLeaseRebindRequest) -> dict[str, Any]:
    return _plc_lease_maintenance.rebind_model(station_id, request)


def plc_web_serial_release_lease(station_id: str, request: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
    return _plc_lease_maintenance.release(station_id, request)


_plc_web_serial_require_active_lease = _plc_station_service._plc_web_serial_require_active_lease


from .plc.diagnostic_state import DiagnosticState as _PlcDiagnosticState
from .plc.diagnostic_state_ports import DiagnosticStatePorts as _PlcDiagnosticStatePorts

_plc_diagnostic_state = _PlcDiagnosticState(
    _PlcDiagnosticStatePorts(
        token_hex=lambda: secrets.token_hex,
        token_urlsafe=lambda: secrets.token_urlsafe,
        active_lease=lambda: _plc_web_serial_require_active_lease,
        config_error=lambda: PlcConfigError,
        clock=lambda: time.time,
        ceil=lambda: math.ceil,
        token_hash=lambda: _plc_web_serial_token_hash,
        lease_row=lambda: _plc_workstation_lease_row,
        protocol_version=lambda: WEB_SERIAL_PROTOCOL_VERSION,
        frames=lambda: build_web_serial_diagnostic_plan,
        mutate=lambda: _plc_web_serial_mutate,
        compare_digest=lambda: hmac.compare_digest,
        record=lambda: _plc_web_serial_record,
        current_user=lambda: current_auth_user,
    )
)


def plc_web_serial_diagnostic_plan(
    station_id: str,
    request: PlcWebSerialAttemptRequest,
) -> dict[str, Any]:
    return _plc_diagnostic_state.plan(station_id, request)

def plc_web_serial_confirm_diagnostic(
    station_id: str,
    request: PlcWebSerialDiagnosticConfirmRequest,
) -> dict[str, Any]:
    return _plc_diagnostic_state.confirm(station_id, request)


def plc_web_serial_finish_diagnostic(
    station_id: str,
    request: PlcWebSerialDiagnosticReceiptRequest,
) -> dict[str, Any]:
    return _plc_diagnostic_state.finish(station_id, request)


from .plc.browser_dispatch import PlcBrowserDispatchService
from .plc.browser_dispatch_ports import BrowserDispatchStorage, BrowserDispatchIdentity, BrowserDispatchPolicy, BrowserDispatchProjection

_plc_browser_dispatch = PlcBrowserDispatchService(
    storage=BrowserDispatchStorage(
        _plc_web_serial_record=lambda: _plc_web_serial_record,
        _plc_web_serial_mutate=lambda: _plc_web_serial_mutate,
        _plc_web_serial_dispatch_row=lambda: _plc_web_serial_dispatch_row,
        _plc_workstation_lease_row=lambda: _plc_workstation_lease_row,
    ),
    identity=BrowserDispatchIdentity(
        _plc_web_serial_require_active_lease=lambda: _plc_web_serial_require_active_lease,
        _plc_web_serial_token_hash=lambda: _plc_web_serial_token_hash,
    ),
    policy=BrowserDispatchPolicy(
        PlcConfigError=lambda: PlcConfigError,
        LEGACY_WEB_SERIAL_PROTOCOL_VERSION=lambda: LEGACY_WEB_SERIAL_PROTOCOL_VERSION,
        WEB_SERIAL_PROTOCOL_VERSION=lambda: WEB_SERIAL_PROTOCOL_VERSION,
        WEB_SERIAL_PLAN_DEADLINE_SECONDS=lambda: WEB_SERIAL_PLAN_DEADLINE_SECONDS,
        PLC_PROTOCOL_ID=lambda: PLC_PROTOCOL_ID,
        build_legacy_web_serial_plan=lambda: build_legacy_web_serial_plan,
        build_web_serial_plan=lambda: build_web_serial_plan,
        normalize_legacy_web_serial_config=lambda: normalize_legacy_web_serial_config,
        normalize_web_serial_config=lambda: normalize_web_serial_config,
        migrate_web_serial_config=lambda: migrate_web_serial_config,
        legacy_web_serial_config_fingerprint=lambda: legacy_web_serial_config_fingerprint,
        web_serial_config_fingerprint=lambda: web_serial_config_fingerprint,
    ),
    projection=BrowserDispatchProjection(
        verify_plc_web_serial_dispatch=lambda: verify_plc_web_serial_dispatch,
        _plc_web_serial_receipt_outcome=lambda: _plc_web_serial_receipt_outcome,
        plc_web_serial_dispatch_public=lambda: plc_web_serial_dispatch_public,
    ),
)


def plc_web_serial_begin_camera_detection(
    station_id: str,
    session_id: str,
    camera_request_id: str,
    model_id: str,
    fingerprint: str,
) -> tuple[dict[str, Any], bool]:
    return _plc_browser_dispatch.plc_web_serial_begin_camera_detection(station_id, session_id, camera_request_id, model_id, fingerprint)


def plc_web_serial_finish_camera_detection(
    station_id: str,
    dispatch_id: str,
    session_id: str,
    result: dict[str, Any] | None,
    error: str = "",
) -> dict[str, Any]:
    return _plc_browser_dispatch.plc_web_serial_finish_camera_detection(station_id, dispatch_id, session_id, result, error)


def plc_web_serial_dispatch_public(record: dict[str, Any]) -> dict[str, Any]:
    return _plc_browser_dispatch.plc_web_serial_dispatch_public(record)


def verify_plc_web_serial_dispatch(
    record: dict[str, Any],
    station: dict[str, Any],
    *,
    require_frames: bool = True,
    require_current_config: bool = True,
) -> None:
    return _plc_browser_dispatch.verify_plc_web_serial_dispatch(record, station, require_frames=require_frames, require_current_config=require_current_config)


def plc_web_serial_declare_attempt(
    station_id: str,
    dispatch_id: str,
    request: PlcWebSerialAttemptRequest,
) -> dict[str, Any]:
    return _plc_browser_dispatch.plc_web_serial_declare_attempt(station_id, dispatch_id, request)


def _plc_web_serial_receipt_outcome(frames: list[dict[str, Any]], operations: list[dict[str, Any]]) -> str:
    return _plc_browser_dispatch._plc_web_serial_receipt_outcome(frames, operations)


def plc_web_serial_record_receipt(
    station_id: str,
    dispatch_id: str,
    request: PlcWebSerialReceiptRequest,
) -> dict[str, Any]:
    return _plc_browser_dispatch.plc_web_serial_record_receipt(station_id, dispatch_id, request)


from .config.app_store import AppConfigStore
from .config.app_store_ports import AppConfigFiles, AppConfigRows, AppConfigPolicy

_app_config_store = AppConfigStore(
    files=AppConfigFiles(
        _business_files=lambda: _business_files,
        CONFIG_PATH=lambda: CONFIG_PATH,
        CONFIG_BACKUP_PATH=lambda: CONFIG_BACKUP_PATH,
        DATA_DIR=lambda: DATA_DIR,
        _config_io_lock=lambda: _config_io_lock,
        ensure_dirs=lambda: ensure_dirs,
        _read_config_file=lambda: _read_config_file,
    ),
    rows=AppConfigRows(
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        config_from_rows=lambda: config_from_rows,
        app_config_rows=lambda: app_config_rows,
        accessory_rows=lambda: accessory_rows,
    ),
    policy=AppConfigPolicy(
        DEFAULT_CONFIG=lambda: DEFAULT_CONFIG,
        PLC_PROTECTED_CONFIG_KEYS=lambda: PLC_PROTECTED_CONFIG_KEYS,
        _plc_namespace_write_authorized=lambda: _plc_namespace_write_authorized,
        public_path_sanitized=lambda: public_path_sanitized,
    ),
)


def _read_config_file() -> dict[str, Any] | None:
    'Read config.json, retrying briefly on transient partial/empty reads.\n\n    Returns the parsed dict, an empty dict when the file legitimately does not\n    exist, or ``None`` when the file is present but could not be parsed cleanly\n    (e.g. mid-write). Callers must NOT treat ``None`` as "no accessories" — doing\n    so would silently drop every persisted record whenever a concurrent writer\n    is in the middle of replacing the file.\n    '
    return _app_config_store._read_config_file()


def load_config() -> dict[str, Any]:
    return _app_config_store.load_config()


def save_config(config: dict[str, Any]) -> None:
    return _app_config_store.save_config(config)


save_app_config = _app_config_store.save_app_config


# Presentation-only window. Durable idempotency/state authority is never trimmed by this value.
PLC_DISPATCH_AUDIT_LIMIT = 100
PLC_QUEUE_WAIT_SECONDS = 2.0
PLC_WORKER_TOTAL_TIMEOUT_SECONDS = MAX_DISPATCH_WALL_SECONDS + 2.0
_plc_transport_factory: Callable[[dict[str, Any]], Any] | None = None
_plc_io_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="plc-io")
_plc_dispatch_slots = threading.BoundedSemaphore(1)
_plc_write_pending = threading.Event()
_plc_active_attempts: dict[str, dict[str, Any]] = {}
_plc_dispatch_runtime: dict[str, dict[str, Any]] = {}
_PLC_RUNTIME_LIMIT = 200
PLC_IO_OWNER_HEARTBEAT_SECONDS = 1.0
PLC_IO_OWNER_LEASE_SECONDS = 5.0
PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS = PLC_WORKER_TOTAL_TIMEOUT_SECONDS + 2.0
PLC_CAPTURE_POLL_SECONDS = 0.2
PLC_CAPTURE_EVENT_TTL_SECONDS = 1.0
PLC_CAPTURE_PROCESSING_TTL_SECONDS = max(180.0, PLC_WORKER_TOTAL_TIMEOUT_SECONDS + 60.0)
_plc_process_owner_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
from .plc.legacy_workers import LegacyPlcWorkers, LegacyHeartbeatCapabilities, LegacyLoopCapabilities

_legacy_plc_workers = LegacyPlcWorkers(
    heartbeat=LegacyHeartbeatCapabilities(
        repository=lambda: runtime_postgres_repository_or_none,
        config=lambda: load_config,
        namespace=lambda: raw_plc_namespace,
        renew=lambda: plc_claim_or_renew_io_owner,
        seconds=lambda: PLC_IO_OWNER_HEARTBEAT_SECONDS,
    ),
    loops=LegacyLoopCapabilities(
        reconcile=lambda: plc_reconcile_pending_dispatches_once,
        poll=lambda: plc_capture_poll_once,
        seconds=lambda: PLC_CAPTURE_POLL_SECONDS,
    ),
)


from .plc.legacy_activation import LegacyActivationPolicy, LegacyActivationSources, LegacyActivationChecks

_legacy_plc_activation = LegacyActivationPolicy(
    sources=LegacyActivationSources(
        repository=lambda: runtime_postgres_repository_or_none,
        transport=lambda: _plc_transport_factory,
        identity=lambda: _request_user,
        getenv=lambda: os.getenv,
        canonical=lambda: _plc_canonical,
    ),
    checks=LegacyActivationChecks(
        coordination=lambda: plc_pg_coordination_available,
        fingerprint=lambda: plc_profile_fingerprint,
        device=lambda: plc_device_profile_verified,
        read=lambda: plc_read_profile_verified,
        serial=lambda: plc_serial_dependency_available,
    ),
)

plc_pg_coordination_available = _legacy_plc_activation.plc_pg_coordination_available


plc_profile_fingerprint = _legacy_plc_activation.plc_profile_fingerprint


plc_device_profile_verified = _legacy_plc_activation.plc_device_profile_verified


plc_read_profile_verified = _legacy_plc_activation.plc_read_profile_verified


plc_serial_dependency_available = _legacy_plc_activation.plc_serial_dependency_available


plc_activation_errors = _legacy_plc_activation.plc_activation_errors


from .plc.legacy_coordination import LegacyRuntimeCoordination, LegacyCoordinationStorage, LegacyCoordinationPolicy

_legacy_plc_coordination = LegacyRuntimeCoordination(
    storage=LegacyCoordinationStorage(
        repository=lambda: runtime_postgres_repository_or_none,
        mutate_config=lambda: mutate_app_config_atomically,
        load_config=lambda: load_config,
        mutate_rows=lambda: _mutate_plc_runtime_rows,
        mutate_runtime=lambda: mutate_plc_runtime_coordination,
        start_heartbeat=lambda: plc_start_owner_heartbeat,
    ),
    policy=LegacyCoordinationPolicy(
        runtime_key=lambda: PLC_RUNTIME_COORDINATION_KEY,
        receipts_key=lambda: PLC_CAPTURE_RESULTS_KEY,
        process_id=lambda: _plc_process_owner_id,
        lease_seconds=lambda: PLC_IO_OWNER_LEASE_SECONDS,
        quarantine_seconds=lambda: PLC_IO_OWNER_TAKEOVER_QUARANTINE_SECONDS,
        clock=lambda: time.time,
    ),
)


mutate_plc_runtime_coordination = _legacy_plc_coordination.mutate_plc_runtime_coordination


plc_completed_capture_receipt = _legacy_plc_coordination.plc_completed_capture_receipt


_mutate_plc_runtime_rows = _legacy_plc_coordination._mutate_plc_runtime_rows


plc_claim_or_renew_io_owner = _legacy_plc_coordination.plc_claim_or_renew_io_owner


plc_start_owner_heartbeat = _legacy_plc_workers.plc_start_owner_heartbeat


plc_current_process_owns_io = _legacy_plc_coordination.plc_current_process_owns_io


from .plc.plc_capture_state import PlcCaptureState
from .plc.plc_capture_state_ports import CaptureStateTransactions, CaptureStatePolicy

_plc_capture_state = PlcCaptureState(
    transactions=CaptureStateTransactions(
        load_config=lambda: load_config,
        mutate_app_config_atomically=lambda: mutate_app_config_atomically,
        mutate_plc_runtime_coordination=lambda: mutate_plc_runtime_coordination,
        plc_completed_capture_receipt=lambda: plc_completed_capture_receipt,
    ),
    policy=CaptureStatePolicy(
        _plc_capture_runtime=lambda: _plc_capture_runtime,
        _plc_expire_capture_state=lambda: _plc_expire_capture_state,
        _plc_canonical=lambda: _plc_canonical,
        PlcConfigError=lambda: PlcConfigError,
        PLC_CAPTURE_EVENT_TTL_SECONDS=lambda: PLC_CAPTURE_EVENT_TTL_SECONDS,
        PLC_CAPTURE_PROCESSING_TTL_SECONDS=lambda: PLC_CAPTURE_PROCESSING_TTL_SECONDS,
        PLC_CAPTURE_RESULTS_KEY=lambda: PLC_CAPTURE_RESULTS_KEY,
        PLC_CONTROL_GENERATION_KEY=lambda: PLC_CONTROL_GENERATION_KEY,
        PLC_RUNTIME_COORDINATION_KEY=lambda: PLC_RUNTIME_COORDINATION_KEY,
        PLC_WORKER_TOTAL_TIMEOUT_SECONDS=lambda: PLC_WORKER_TOTAL_TIMEOUT_SECONDS,
    ),
)


def _plc_capture_runtime(state: dict[str, Any]) -> dict[str, Any]:
    return _plc_capture_state._plc_capture_runtime(state)


def _plc_expire_capture_state(capture: dict[str, Any], now: float) -> None:
    return _plc_capture_state._plc_expire_capture_state(capture, now)


def plc_claim_capture_session(user_id: str, model_id: str) -> dict[str, Any]:
    return _plc_capture_state.plc_claim_capture_session(user_id, model_id)


def plc_heartbeat_capture_session(session_id: str, user_id: str) -> dict[str, Any]:
    return _plc_capture_state.plc_heartbeat_capture_session(session_id, user_id)


def plc_release_capture_session(session_id: str, user_id: str) -> None:
    return _plc_capture_state.plc_release_capture_session(session_id, user_id)


def plc_capture_disarm(reason: str) -> None:
    return _plc_capture_state.plc_capture_disarm(reason)


def plc_apply_capture_observation(value: int, *, generation: int, owner_epoch: int, trigger_value: int) -> dict[str, Any] | None:
    'Persist one read observation and atomically create at most one edge event.'
    return _plc_capture_state.plc_apply_capture_observation(value, generation=generation, owner_epoch=owner_epoch, trigger_value=trigger_value)


def plc_claim_next_capture_event(session_id: str, user_id: str) -> dict[str, Any] | None:
    return _plc_capture_state.plc_claim_next_capture_event(session_id, user_id)


def plc_begin_triggered_analysis(trigger_id: str, session_id: str, user_id: str, model_id: str, fingerprint: str) -> dict[str, Any] | None:
    return _plc_capture_state.plc_begin_triggered_analysis(trigger_id, session_id, user_id, model_id, fingerprint)


def plc_prepare_triggered_dispatch(trigger_id: str, session_id: str, user_id: str) -> None:
    'Atomically prove a fresh session/event immediately before any PLC dispatch.'
    return _plc_capture_state.plc_prepare_triggered_dispatch(trigger_id, session_id, user_id)


def plc_finish_triggered_analysis(trigger_id: str, session_id: str, user_id: str, result: dict[str, Any] | None, error: str = "") -> None:
    return _plc_capture_state.plc_finish_triggered_analysis(trigger_id, session_id, user_id, result, error)




from .plc.legacy_operations import (
    LegacyPlcOperations, LegacyOperationConfiguration, LegacyOperationOwnership,
    LegacyDispatchIteration, LegacyCaptureIteration,
)

_legacy_plc_operations = LegacyPlcOperations(
    configuration=LegacyOperationConfiguration(
        load=lambda: load_config,
        normalize=lambda: normalize_plc_config,
        namespace=lambda: raw_plc_namespace,
        error=lambda: PlcConfigError,
        activation=lambda: plc_activation_errors,
        generation_key=lambda: PLC_CONTROL_GENERATION_KEY,
    ),
    ownership=LegacyOperationOwnership(
        claim=lambda: plc_claim_or_renew_io_owner,
        owns=lambda: plc_current_process_owns_io,
    ),
    dispatch=LegacyDispatchIteration(
        records=lambda: plc_dispatch_audit_records,
        verify=lambda: verify_persisted_plc_dispatch,
        conflict=lambda: PlcDispatchStateConflict,
        pristine=lambda: plc_dispatch_is_pristine_queue,
        blocker=lambda: plc_dispatch_adoption_blocker,
        finalize=lambda: plc_finalize_dispatch,
        run=lambda: _run_queued_plc_dispatch,
    ),
    capture=LegacyCaptureIteration(
        pending=lambda: _plc_write_pending,
        slots=lambda: _plc_dispatch_slots,
        read=lambda: read_d_register_value,
        transport=lambda: _plc_transport_factory,
        disarm=lambda: plc_capture_disarm,
        observe=lambda: plc_apply_capture_observation,
    ),
)


plc_reconcile_pending_dispatches_once = _legacy_plc_operations.plc_reconcile_pending_dispatches_once


start_plc_dispatch_reconciler = _legacy_plc_workers.start_plc_dispatch_reconciler


plc_capture_poll_once = _legacy_plc_operations.plc_capture_poll_once


start_plc_capture_poller = _legacy_plc_workers.start_plc_capture_poller


@app.on_event("startup")
def start_plc_runtime_workers() -> None:
    # v3 physical I/O belongs exclusively to a foreground Edge/Chrome page.
    # Keep legacy v1/v2 workers defined for read-only history verification, but
    # never start a server-side pyserial dispatcher or PLC input poller.
    return None


def plc_config_request_payload(request: PlcConfigRequest) -> dict[str, Any]:
    if hasattr(request, "model_dump"):
        return request.model_dump(exclude_none=True)  # type: ignore[attr-defined,no-any-return]
    return request.dict(exclude_none=True)


from .plc.legacy_records import LegacyDispatchRecords, DispatchRecordSources, DispatchRecordPolicy

_legacy_plc_records = LegacyDispatchRecords(
    sources=DispatchRecordSources(
        config=lambda: load_config,
        namespace=lambda: raw_plc_namespace,
        sanitize=lambda: public_path_sanitized,
        records=lambda: plc_dispatch_audit_records,
        existing=lambda: plc_dispatch_existing,
        verify=lambda: verify_persisted_plc_dispatch,
    ),
    policy=DispatchRecordPolicy(
        absent=lambda: PLC_CONFIG_ABSENT,
        guard=lambda: _config_io_lock,
        conflict=lambda: PlcDispatchStateConflict,
        clock=lambda: time.time,
    ),
)


plc_dispatch_audit_records = _legacy_plc_records.plc_dispatch_audit_records


raw_plc_namespace = _legacy_plc_records.raw_plc_namespace


plc_config_audit_snapshot = _legacy_plc_records.plc_config_audit_snapshot


plc_dispatch_existing = _legacy_plc_records.plc_dispatch_existing


mutate_app_config_atomically = _app_config_store.mutate_app_config_atomically


from .plc.errors import PlcDispatchStateConflict
from .plc.event_projection import (
    PLC_REDUCER_DERIVED_FIELDS,
    PLC_FINALIZE_REASONS,
    project_plc_dispatch_events,
)


from .plc.transition_policy import (
    PLC_DISPATCH_STATE_ORDER,
    PLC_DISPATCH_FINAL_STATES,
    PLC_MONOTONIC_LIST_FIELDS,
    PLC_IMMUTABLE_BINDING_FIELDS,
    PLC_DISPATCH_KNOWN_FIELDS,
    PLC_DISPATCH_IMMUTABLE_ONCE_BOUND_FIELDS,
    PLC_DISPATCH_TRANSITION_MUTABLE_FIELDS,
    PLC_DISPATCH_PHYSICAL_PROJECTION_FIELDS,
    PlcDispatchTransitionKind,
    PLC_TRANSITION_PROJECTION_ALLOWLIST,
    _plc_canonical,
    _plc_evidence_list_contains,
    PLC_OPERATION_STATUS_ALLOWED,
    PLC_OPERATION_OUTCOME_ALLOWED,
    PLC_OPERATION_KNOWN_FIELDS,
    validate_plc_operation_evidence,
    validate_plc_attempt_start,
    validate_plc_dispatch_transition,
)


PLC_RECORD_SCHEMA_VERSION = 2
PLC_PROTOCOL_CONTRACT_VERSION = 2








from .plc.event_commands import (
    _PLC_TYPED_EVENT_DERIVERS,
    _PLC_TYPED_EVENT_FIELDS,
    _derive_plc_advance_attempt,
    _derive_plc_attempting,
    _derive_plc_deadline,
    _derive_plc_finalize,
    _derive_plc_finish_attempt,
    _derive_plc_start_attempt,
    append_plc_typed_event,
)






get_validated_idempotent_dispatch = _legacy_plc_records.get_validated_idempotent_dispatch


plc_dispatch_conflict_response = _legacy_plc_records.plc_dispatch_conflict_response


from .plc.dispatch_mutations import PlcDispatchMutations
from .plc.dispatch_mutation_ports import DispatchMutationStorage, DispatchMutationPolicy, DispatchMutationEvents, DispatchMutationEvidence

_plc_dispatch_mutations = PlcDispatchMutations(
    storage=DispatchMutationStorage(
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        mutate_app_config_atomically=lambda: mutate_app_config_atomically,
        plc_dispatch_audit_records=lambda: plc_dispatch_audit_records,
        verify_persisted_plc_dispatch=lambda: verify_persisted_plc_dispatch,
        raw_plc_namespace=lambda: raw_plc_namespace,
        plc_pg_coordination_available=lambda: plc_pg_coordination_available,
        public_path_sanitized=lambda: public_path_sanitized,
        plc_dispatch_existing=lambda: plc_dispatch_existing,
    ),
    policy=DispatchMutationPolicy(
        PlcDispatchStateConflict=lambda: PlcDispatchStateConflict,
        PLC_CONFIG_ABSENT=lambda: PLC_CONFIG_ABSENT,
        normalize_plc_config=lambda: normalize_plc_config,
        PlcConfigError=lambda: PlcConfigError,
        PLC_CONTROL_GENERATION_KEY=lambda: PLC_CONTROL_GENERATION_KEY,
        build_plc_dispatch_plan=lambda: build_plc_dispatch_plan,
        PLC_RECORD_SCHEMA_VERSION=lambda: PLC_RECORD_SCHEMA_VERSION,
        PLC_PROTOCOL_CONTRACT_VERSION=lambda: PLC_PROTOCOL_CONTRACT_VERSION,
        PLC_QUEUE_WAIT_SECONDS=lambda: PLC_QUEUE_WAIT_SECONDS,
        PLC_FINALIZE_REASONS=lambda: PLC_FINALIZE_REASONS,
    ),
    events=DispatchMutationEvents(
        project_plc_dispatch_events=lambda: project_plc_dispatch_events,
        PlcDispatchTransitionKind=lambda: PlcDispatchTransitionKind,
        _PLC_TYPED_EVENT_DERIVERS=lambda: _PLC_TYPED_EVENT_DERIVERS,
        _PLC_TYPED_EVENT_FIELDS=lambda: _PLC_TYPED_EVENT_FIELDS,
        validate_plc_dispatch_transition=lambda: validate_plc_dispatch_transition,
        _apply_plc_dispatch_event=lambda: _apply_plc_dispatch_event,
        plc_finalize_dispatch=lambda: plc_finalize_dispatch,
    ),
    evidence=DispatchMutationEvidence(
        PlcAttemptTerminalResult=lambda: PlcAttemptTerminalResult,
        PlcTerminalResultCode=lambda: PlcTerminalResultCode,
        PLC_TERMINAL_RESULT_CODES=lambda: PLC_TERMINAL_RESULT_CODES,
        PlcTransportPhase=lambda: PlcTransportPhase,
        PLC_TERMINAL_ALLOWED_PHASES=lambda: PLC_TERMINAL_ALLOWED_PHASES,
        PLC_TERMINAL_DIAGNOSTIC_SOURCES=lambda: PLC_TERMINAL_DIAGNOSTIC_SOURCES,
    ),
)


def create_plc_dispatch(
    *,
    source: str,
    request_id: str,
    passed: bool,
    fingerprint: str,
    expected_generation: int | None = None,
) -> dict[str, Any]:
    'Atomically derive a queued v1 record from the authoritative PLC namespace.'
    return _plc_dispatch_mutations.create_plc_dispatch(source=source, request_id=request_id, passed=passed, fingerprint=fingerprint, expected_generation=expected_generation)


def _apply_plc_dispatch_event(
    dispatch_id: str,
    *,
    expected_version: int,
    transition_kind: PlcDispatchTransitionKind,
    event_payload: dict[str, Any],
) -> dict[str, Any]:
    return _plc_dispatch_mutations._apply_plc_dispatch_event(dispatch_id, expected_version=expected_version, transition_kind=transition_kind, event_payload=event_payload)




def plc_transition_attempting(dispatch_id: str, *, expected_version: int) -> dict[str, Any]:
    return _plc_dispatch_mutations.plc_transition_attempting(dispatch_id, expected_version=expected_version)




def plc_start_attempt(dispatch_id: str, *, expected_version: int, target: str) -> dict[str, Any]:
    return _plc_dispatch_mutations.plc_start_attempt(dispatch_id, expected_version=expected_version, target=target)




def plc_advance_attempt(
    dispatch_id: str,
    *,
    expected_version: int,
    attempt_id: str,
    bytes_written: int,
    physical_status: str,
    outcome: str,
) -> dict[str, Any]:
    return _plc_dispatch_mutations.plc_advance_attempt(dispatch_id, expected_version=expected_version, attempt_id=attempt_id, bytes_written=bytes_written, physical_status=physical_status, outcome=outcome)




def plc_finish_attempt(
    dispatch_id: str,
    *,
    expected_version: int,
    attempt_id: str,
    terminal_result: PlcAttemptTerminalResult,
) -> dict[str, Any]:
    return _plc_dispatch_mutations.plc_finish_attempt(dispatch_id, expected_version=expected_version, attempt_id=attempt_id, terminal_result=terminal_result)




def plc_mark_deadline(dispatch_id: str, *, expected_version: int) -> dict[str, Any]:
    return _plc_dispatch_mutations.plc_mark_deadline(dispatch_id, expected_version=expected_version)








def plc_finalize_dispatch(
    dispatch_id: str, *, expected_version: int, reason: str = ""
) -> dict[str, Any]:
    return _plc_dispatch_mutations.plc_finalize_dispatch(dispatch_id, expected_version=expected_version, reason=reason)


def plc_cancel_dispatch(
    dispatch_id: str, *, expected_version: int, reason: str
) -> dict[str, Any]:
    return _plc_dispatch_mutations.plc_cancel_dispatch(dispatch_id, expected_version=expected_version, reason=reason)


def persist_plc_dispatch_record(
    record: dict[str, Any], *, expected_version: int | None = None, transition_kind: Any = None
) -> dict[str, Any]:
    'Retired raw compatibility shim; all creates and mutations use typed handlers.'
    return _plc_dispatch_mutations.persist_plc_dispatch_record(record, expected_version=expected_version, transition_kind=transition_kind)


from .plc.dispatch_runtime_state import PlcDispatchRuntimeState
from .plc.dispatch_runtime_state_ports import DispatchRuntimeState, DispatchRuntimeRecords, DispatchRuntimePolicy

_plc_dispatch_runtime_state = PlcDispatchRuntimeState(
    state=DispatchRuntimeState(
        _plc_dispatch_runtime=lambda: _plc_dispatch_runtime,
        _PLC_RUNTIME_LIMIT=lambda: _PLC_RUNTIME_LIMIT,
        _config_io_lock=lambda: _config_io_lock,
        _plc_active_attempts=lambda: _plc_active_attempts,
        _plc_runtime_entry=lambda: _plc_runtime_entry,
        _hydrate_plc_runtime_entry=lambda: _hydrate_plc_runtime_entry,
    ),
    records=DispatchRuntimeRecords(
        load_config=lambda: load_config,
        plc_dispatch_audit_records=lambda: plc_dispatch_audit_records,
        plc_mark_deadline=lambda: plc_mark_deadline,
    ),
    policy=DispatchRuntimePolicy(
        plc_dispatch_is_pristine_queue=lambda: plc_dispatch_is_pristine_queue,
        _plc_canonical=lambda: _plc_canonical,
    ),
)


def _plc_runtime_entry(dispatch_id: str) -> dict[str, Any]:
    return _plc_dispatch_runtime_state._plc_runtime_entry(dispatch_id)


def _hydrate_plc_runtime_entry(dispatch_id: str) -> dict[str, Any]:
    return _plc_dispatch_runtime_state._hydrate_plc_runtime_entry(dispatch_id)


def _register_plc_dispatch_runtime(dispatch_id: str) -> None:
    return _plc_dispatch_runtime_state._register_plc_dispatch_runtime(dispatch_id)


def _plc_deadline_snapshot(
    *, dispatch_id: str, source: str, request_id: str, passed: bool
) -> dict[str, Any]:
    return _plc_dispatch_runtime_state._plc_deadline_snapshot(dispatch_id=dispatch_id, source=source, request_id=request_id, passed=passed)


def _plc_active_attempts_snapshot() -> list[dict[str, Any]]:
    return _plc_dispatch_runtime_state._plc_active_attempts_snapshot()


def plc_config_response(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _plc_config_diagnostics.response(config)


def plc_dispatch_identity(result: dict[str, Any], *, source: str, fingerprint: str) -> tuple[str, str, bool]:
    return _plc_dispatch_runtime_state.plc_dispatch_identity(result, source=source, fingerprint=fingerprint)


def plc_dispatch_record_is_terminal(record: dict[str, Any]) -> bool:
    return _plc_dispatch_runtime_state.plc_dispatch_record_is_terminal(record)


def plc_dispatch_is_pristine_queue(record: dict[str, Any]) -> bool:
    'Only a dispatch with proof that physical I/O never began may change owners.'
    return _plc_dispatch_runtime_state.plc_dispatch_is_pristine_queue(record)


def plc_dispatch_adoption_blocker(
    record: dict[str, Any],
    *,
    settings: dict[str, Any],
    generation: int,
    now_ms: int | None = None,
) -> str:
    'Return a no-I/O reason when a queued record is unsafe or stale to adopt.'
    return _plc_dispatch_runtime_state.plc_dispatch_adoption_blocker(record, settings=settings, generation=generation, now_ms=now_ms)


from .plc.legacy_dispatch import LegacyDispatch
from .plc.legacy_dispatch_ports import LegacyDispatchPolicy, LegacyDispatchConfiguration, LegacyDispatchRecords, LegacyDispatchExecution

_plc_legacy_dispatch = LegacyDispatch(
    policy=LegacyDispatchPolicy(
        PLC_CONTROL_GENERATION_KEY=lambda: PLC_CONTROL_GENERATION_KEY,
        PLC_FINALIZE_REASONS=lambda: PLC_FINALIZE_REASONS,
        PLC_QUEUE_WAIT_SECONDS=lambda: PLC_QUEUE_WAIT_SECONDS,
        PLC_WORKER_TOTAL_TIMEOUT_SECONDS=lambda: PLC_WORKER_TOTAL_TIMEOUT_SECONDS,
        PLC_TERMINAL_ALLOWED_PHASES=lambda: PLC_TERMINAL_ALLOWED_PHASES,
        PLC_TERMINAL_DIAGNOSTIC_SOURCES=lambda: PLC_TERMINAL_DIAGNOSTIC_SOURCES,
        PlcAttemptTerminalResult=lambda: PlcAttemptTerminalResult,
        PlcConfigError=lambda: PlcConfigError,
        PlcDispatchStateConflict=lambda: PlcDispatchStateConflict,
        PlcTerminalResultCode=lambda: PlcTerminalResultCode,
        PlcTransportError=lambda: PlcTransportError,
        PlcTransportPhase=lambda: PlcTransportPhase,
    ),
    configuration=LegacyDispatchConfiguration(
        load_config=lambda: load_config,
        normalize_plc_config=lambda: normalize_plc_config,
        raw_plc_namespace=lambda: raw_plc_namespace,
        plc_activation_errors=lambda: plc_activation_errors,
        plc_config_audit_snapshot=lambda: plc_config_audit_snapshot,
        plc_claim_or_renew_io_owner=lambda: plc_claim_or_renew_io_owner,
        plc_current_process_owns_io=lambda: plc_current_process_owns_io,
    ),
    records=LegacyDispatchRecords(
        plc_dispatch_identity=lambda: plc_dispatch_identity,
        get_validated_idempotent_dispatch=lambda: get_validated_idempotent_dispatch,
        plc_dispatch_record_is_terminal=lambda: plc_dispatch_record_is_terminal,
        plc_dispatch_is_pristine_queue=lambda: plc_dispatch_is_pristine_queue,
        plc_dispatch_adoption_blocker=lambda: plc_dispatch_adoption_blocker,
        create_plc_dispatch=lambda: create_plc_dispatch,
        plc_transition_attempting=lambda: plc_transition_attempting,
        plc_advance_attempt=lambda: plc_advance_attempt,
        plc_finalize_dispatch=lambda: plc_finalize_dispatch,
        plc_start_attempt=lambda: plc_start_attempt,
        plc_finish_attempt=lambda: plc_finish_attempt,
        plc_dispatch_conflict_response=lambda: plc_dispatch_conflict_response,
    ),
    execution=LegacyDispatchExecution(
        _config_io_lock=lambda: _config_io_lock,
        _plc_active_attempts=lambda: _plc_active_attempts,
        _plc_runtime_entry=lambda: _plc_runtime_entry,
        _register_plc_dispatch_runtime=lambda: _register_plc_dispatch_runtime,
        _plc_deadline_snapshot=lambda: _plc_deadline_snapshot,
        _plc_dispatch_slots=lambda: _plc_dispatch_slots,
        _plc_write_pending=lambda: _plc_write_pending,
        _plc_io_executor=lambda: _plc_io_executor,
        _plc_transport_factory=lambda: _plc_transport_factory,
        dispatch_fx_plc_detection_result=lambda: dispatch_fx_plc_detection_result,
        dispatch_plc_for_detection=lambda: dispatch_plc_for_detection,
        _run_queued_plc_dispatch=lambda: _run_queued_plc_dispatch,
    ),
)


def dispatch_plc_for_detection(
    result: dict[str, Any],
    *,
    source: str,
    fingerprint: str,
    expected_generation: int | None = None,
) -> dict[str, Any]:
    'Attach PLC sync status without changing or invalidating the detection result.'
    return _plc_legacy_dispatch.dispatch_plc_for_detection(result, source=source, fingerprint=fingerprint, expected_generation=expected_generation)


def _run_queued_plc_dispatch(result: dict[str, Any], *, source: str, fingerprint: str) -> dict[str, Any]:
    return _plc_legacy_dispatch._run_queued_plc_dispatch(result, source=source, fingerprint=fingerprint)


async def dispatch_plc_for_detection_async(
    result: dict[str, Any], *, source: str, fingerprint: str, inline_fake_transport: bool = False
) -> dict[str, Any]:
    'Run bounded synchronous serial work off the ASGI event loop.'
    return await _plc_legacy_dispatch.dispatch_plc_for_detection_async(result, source=source, fingerprint=fingerprint, inline_fake_transport=inline_fake_transport)


from .accessories import policy as _accessory_policy
from .accessories.projection import AccessoryProjection, ProjectionDependencies as AccessoryProjectionDependencies
from .accessories.repository import AccessoryRepository, AccessoryStoreDependencies

_accessory_repository = AccessoryRepository(AccessoryStoreDependencies(
    runtime_repository=lambda: runtime_postgres_repository_or_none(),
    lock=lambda: _config_io_lock, load_config=lambda: load_config(),
    save_config=lambda config: save_config(config),
))
_accessory_projection = AccessoryProjection(AccessoryProjectionDependencies(
    audit=lambda item: enrich_record_audit_fields(item),
    sanitize=lambda item: public_path_sanitized(item),
    physical_size=lambda kind: physical_size_payload(kind),
    size_reference=lambda key: size_reference_payload(key),
    text_source_count=lambda item: text_accessory_source_count(item),
    text_preview_limit=lambda: MAX_TEXT_ACCESSORY_IMAGES,
    current_user=lambda: current_auth_user(),
    redact=lambda payload, user: redact_accessory_payload_for_user(payload, user),
))


def save_accessory_item(item: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return _accessory_repository.save_accessory_item(item, config)


def delete_accessory_item(accessory_id: str, config: dict[str, Any] | None = None) -> bool:
    return _accessory_repository.delete_accessory_item(accessory_id, config)


def task_rule_id(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9_.@-]+", "_", str(value or "").strip()).strip("_")[:96]



def task_rule_overrides(config: dict[str, Any], task_id: Any) -> dict[str, Any]:
    return _detection_rule_requests.task_rule_overrides(config, task_id)


def apply_task_rule_override_to_spec(spec: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _detection_rule_requests.apply_task_rule_override_to_spec(spec, config)


def accessory_uid(item: dict[str, Any]) -> str:
    return _accessory_policy.accessory_uid(item)


def accessory_legacy_uid(item: dict[str, Any]) -> str:
    return _accessory_policy.accessory_legacy_uid(item)


def serialize_accessory(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_projection.serialize_accessory(item)


def serialize_accessory_summary(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_projection.serialize_accessory_summary(item)


def serialize_accessory_items(items: list[dict[str, Any]], *, summary: bool = True) -> list[dict[str, Any]]:
    return _accessory_projection.serialize_accessory_items(items, summary=summary)


def accessory_material_type(item: dict[str, Any]) -> str:
    return _accessory_policy.accessory_material_type(item)


from .accessories.policy import TEXT_ACCESSORY_NAME_HINTS


def accessory_uses_ocr(item: dict[str, Any]) -> bool:
    return _accessory_policy.accessory_uses_ocr(item)


def normalize_object_alpha_material_policy(value: Any) -> str | None:
    return _accessory_policy.normalize_object_alpha_material_policy(value)


def object_alpha_material_policy(item: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> str:
    return _accessory_policy.object_alpha_material_policy(item, metadata)


def object_alpha_policy_label(policy: str) -> str:
    return _accessory_policy.object_alpha_policy_label(policy)


from .runtime.service_paths import ServicePaths
from .runtime.service_path_ports import ServicePathSettings, PathProjectionPolicy, PathCalls, PathFiles, PathIdentity

_service_paths = ServicePaths(
    settings=ServicePathSettings(
        ROOT=lambda: ROOT,
        APP_DIR=lambda: APP_DIR,
        OUTPUT_DIR=lambda: OUTPUT_DIR,
    ),
    policy=PathProjectionPolicy(
        STALE_REPO_PATH_PREFIXES=lambda: STALE_REPO_PATH_PREFIXES,
        REMOVED_PHASE1_PUBLIC_CONFIG_KEYS=lambda: REMOVED_PHASE1_PUBLIC_CONFIG_KEYS,
        LEGACY_OWNER_ID=lambda: LEGACY_OWNER_ID,
        SYSTEM_OWNER_ID=lambda: SYSTEM_OWNER_ID,
    ),
    calls=PathCalls(
        rebase_stale_local_path_text=lambda: rebase_stale_local_path_text,
        rebase_stale_local_payload_text=lambda: rebase_stale_local_payload_text,
        public_path_sanitized=lambda: public_path_sanitized,
        service_rebased_path=lambda: service_rebased_path,
        resolve_service_path=lambda: resolve_service_path,
        path_is_under=lambda: path_is_under,
        public_output_url=lambda: public_output_url,
        output_write_dir_for_owner=lambda: output_write_dir_for_owner,
    ),
    files=PathFiles(
        _business_files=lambda: _business_files,
    ),
    identity=PathIdentity(
        _request_user=lambda: _request_user,
        user_is_admin=lambda: user_is_admin,
    ),
)


def service_rebased_path(path: Path) -> Path | None:
    return _service_paths.service_rebased_path(path)


def rebase_stale_local_path_text(value: str) -> str:
    return _service_paths.rebase_stale_local_path_text(value)


def rebase_stale_local_payload_text(text: str) -> str:
    return _service_paths.rebase_stale_local_payload_text(text)


def public_path_sanitized(value: Any) -> Any:
    return _service_paths.public_path_sanitized(value)


def public_auth_features(user: dict[str, Any] | None) -> dict[str, str]:
    return FEATURE_PERMISSIONS if user else {}


def public_default_permissions(user: dict[str, Any] | None) -> list[str]:
    return DEFAULT_USER_PERMISSIONS if user else []


def public_legacy_owner_id(user: dict[str, Any] | None) -> str:
    return LEGACY_OWNER_ID if user else ""


def migrate_json_file_paths(path: Path) -> bool:
    return _service_paths.migrate_json_file_paths(path)


_local_path_migration = LocalPathMigration(
    config_path=lambda: CONFIG_PATH,
    roots=lambda: (DATA_DIR, BACKGROUND_DIR, STANDARDIZED_MANUALS_DIR, PRECISE_MANUALS_DIR),
    files=lambda: _business_files,
    migrate_file=lambda: migrate_json_file_paths,
)
migrate_persisted_local_paths_once = _local_path_migration.run


def resolve_service_path(value: Any, *, for_write: bool = False) -> Path:
    return _service_paths.resolve_service_path(value, for_write=for_write)


def path_is_under(path: Path, root: Path) -> bool:
    return _service_paths.path_is_under(path, root)


def public_output_url(path: Path) -> str:
    return _service_paths.public_output_url(path)


def public_output_url_for_existing(path: Path) -> str:
    return _service_paths.public_output_url_for_existing(path)


def output_write_dir(kind: str = "") -> Path:
    return _service_paths.output_write_dir(kind)


def output_write_dir_for_owner(kind: str = "", owner_user_id: str = "") -> Path:
    return _service_paths.output_write_dir_for_owner(kind, owner_user_id)


def output_url(path: Path) -> str:
    return _service_paths.output_url(path)


from .accessories.text_preparation import AccessoryTextPreparation
from .accessories.text_preparation_ports import TextGeometry, TextSources, TextMedia

_accessory_text_preparation = AccessoryTextPreparation(
    geometry=TextGeometry(
        order_points=lambda: order_points,
        ratio_close=lambda: ratio_close,
        quad_is_axis_aligned=lambda: quad_is_axis_aligned,
        best_document_quad=lambda: best_document_quad,
        target_paper_pixel_size=lambda: target_paper_pixel_size,
        detect_document_quad=lambda: detect_document_quad,
        document_quad_mean_size=lambda: document_quad_mean_size,
        resize_document_to_paper=lambda: resize_document_to_paper,
    ),
    sources=TextSources(
        is_text_rectified_path=lambda: is_text_rectified_path,
        stable_text_crop_stem=lambda: stable_text_crop_stem,
        text_raw_crop_prefix=lambda: text_raw_crop_prefix,
        text_image_paths_for_upload_limit=lambda: text_image_paths_for_upload_limit,
        IMAGE_REFERENCE_SUFFIXES=lambda: IMAGE_REFERENCE_SUFFIXES,
        MAX_TEXT_ACCESSORY_IMAGES=lambda: MAX_TEXT_ACCESSORY_IMAGES,
        HTTPException=lambda: HTTPException,
    ),
    media=TextMedia(
        optional_float=lambda: optional_float,
        STANDARD_PAPER_SIZES_MM=lambda: STANDARD_PAPER_SIZES_MM,
        _image_files=lambda: _image_files,
    ),
)


def order_points(points: np.ndarray) -> np.ndarray:
    return _accessory_text_preparation.order_points(points)


def target_paper_pixel_size(physical_size: dict[str, Any] | None) -> tuple[int, int]:
    return _accessory_text_preparation.target_paper_pixel_size(physical_size)


def ratio_close(value: float, target: float, tolerance: float = 0.08) -> bool:
    return _accessory_text_preparation.ratio_close(value, target, tolerance)


def quad_is_axis_aligned(rect: np.ndarray, image_shape: tuple[int, ...]) -> bool:
    return _accessory_text_preparation.quad_is_axis_aligned(rect, image_shape)


def best_document_quad(image: np.ndarray, target_aspect: float | None = None) -> np.ndarray | None:
    return _accessory_text_preparation.best_document_quad(image, target_aspect)


def document_quad_mean_size(quad: np.ndarray) -> tuple[float, float]:
    "Mean width / height (px) of an ordered tl,tr,br,bl quad — used to recover\n    the document's true (deskewed) proportions."
    return _accessory_text_preparation.document_quad_mean_size(quad)


def detect_document_quad(image: np.ndarray, target_aspect: float | None = None) -> np.ndarray | None:
    'Robustly auto-crop the document/manual body. Tries edge contours first, then\n    bright-paper (Otsu) and low-saturation paper segmentation, so a manual shot on\n    a darker tabletop is still found even when its edges are weak. Returns an\n    ordered tl,tr,br,bl quad or None.'
    return _accessory_text_preparation.detect_document_quad(image, target_aspect)


def letterbox_document_onto_paper(
    image: np.ndarray,
    target_w: int,
    target_h: int,
    pad_value: tuple[int, int, int] = (255, 255, 255),
) -> np.ndarray:
    'Place a document image onto a clean paper-sized canvas preserving aspect\n    (white letterbox). Never stretches the content non-uniformly.'
    return _accessory_text_preparation.letterbox_document_onto_paper(image, target_w, target_h, pad_value)


def resize_document_to_paper(image: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    'Resize a document image directly to the chosen paper pixel size.'
    return _accessory_text_preparation.resize_document_to_paper(image, target_w, target_h)


def is_text_rectified_path(path: Path | str) -> bool:
    return _accessory_text_preparation.is_text_rectified_path(path)


def stable_text_crop_stem(path: Path | str) -> str:
    return _accessory_text_preparation.stable_text_crop_stem(path)


def text_raw_crop_prefix(path: Path | str) -> str:
    return _accessory_text_preparation.text_raw_crop_prefix(path)


def text_raw_has_rectified(raw_path: Path | str, rectified_sources: list[Path]) -> bool:
    return _accessory_text_preparation.text_raw_has_rectified(raw_path, rectified_sources)


def text_image_paths_for_upload_limit(item: dict[str, Any]) -> list[Path]:
    return _accessory_text_preparation.text_image_paths_for_upload_limit(item)


def text_accessory_source_count(item: dict[str, Any]) -> int:
    return _accessory_text_preparation.text_accessory_source_count(item)


def validate_text_accessory_uploads(files: list[UploadFile], *, existing_count: int = 0) -> None:
    return _accessory_text_preparation.validate_text_accessory_uploads(files, existing_count=existing_count)


def normalize_text_image(src: Path, target_dir: Path, physical_size: dict[str, Any] | None = None) -> dict[str, Any] | None:
    'Lightweight document pipeline (no image generation): auto-crop the document\n    body, deskew/perspective-correct any tilt, then normalize onto the chosen paper\n    page (A4/A5/...). The output is always exactly the paper pixel size.'
    return _accessory_text_preparation.normalize_text_image(src, target_dir, physical_size)


from .accessories.preparation import (
    AccessoryPreparation, AccessoryRefresh,
    build_object_view_plan as _preparation_view_plan,
    defer_accessory_normalization as _preparation_defer,
)
from .accessories.preparation_ports import (
    PreparationPaths, TextPreparation, ReferenceMedia, RefreshPreparation, RefreshProfiles,
    CandidateMedia, CandidatePreparation, CandidateStorage,
)
from .accessories.candidate_factory import CandidateFactory
_accessory_preparation = AccessoryPreparation(
    PreparationPaths(
        normalized=lambda: NORMALIZED_DIR,
        uploads=lambda: UPLOAD_DIR,
        image_suffixes=lambda: IMAGE_REFERENCE_SUFFIXES,
        video_suffixes=lambda: VIDEO_REFERENCE_SUFFIXES,
    ),
    TextPreparation(
        is_rectified=lambda path: is_text_rectified_path(path),
        has_rectified=lambda path, sources: text_raw_has_rectified(path, sources),
        normalize=lambda source, directory, size: normalize_text_image(source, directory, size),
        max_images=lambda: MAX_TEXT_ACCESSORY_IMAGES,
    ),
    ReferenceMedia(
        extract_frames=lambda path, directory: extract_video_reference_frames(path, directory),
        profile_paths=lambda item: ai_profile_reference_paths(item),
        first_source=lambda item: first_source_ai_reference_path(item),
    ),
)
_accessory_refresh = AccessoryRefresh(
    RefreshPreparation(
        normalize=lambda item: normalize_accessory_assets(item),
        defer=lambda item: defer_accessory_normalization(item),
        ensure_reference=lambda item: ensure_default_ai_profile_reference(item),
    ),
    RefreshProfiles(
        fallback=lambda item: fallback_accessory_ai_profile(item),
        generate=lambda item, **kwargs: generate_accessory_ai_profile(item, **kwargs),
    ),
)
_accessory_image_io = ImageFiles(lambda: cv2, files=_business_files)
_candidate_factory = CandidateFactory(
    CandidateMedia(
        expand_sources=lambda identifier, sources: expand_accessory_reference_sources(identifier, sources),
        default_size=lambda material_type: physical_size_payload(material_type),
        size_reference=lambda value: normalize_size_reference(value),
        image_suffixes=lambda: IMAGE_REFERENCE_SUFFIXES,
        output_directory=lambda category: output_write_dir(category),
        thumbnail=lambda image, path, angle: write_thumbnail(image, path, angle),
    ),
    CandidatePreparation(
        defer=lambda item: defer_accessory_normalization(item),
        ensure_reference=lambda item: ensure_default_ai_profile_reference(item),
        ensure_profile=lambda item, **kwargs: ensure_accessory_ai_profile(item, **kwargs),
        ensure_pose_jobs=lambda item: ensure_pose_collection_image_jobs(item),
    ),
    CandidateStorage(
        owner_fields=lambda: current_owner_fields(),
        directory=lambda: ACCESSORY_CANDIDATES_DIR,
        save=lambda path, item: save_accessory_candidate(path, item),
    ), images=_accessory_image_io
)


def build_object_view_plan(name: str) -> list[dict[str, Any]]:
    return _preparation_view_plan(name)


from .accessories.preview_assets import select_document_image_candidate as _select_document_image_candidate_impl
from .accessories.preview_assets import PreviewAssetLoader as _PreviewAssetLoader
from .accessories.preview_asset_ports import PreviewAssetPolicy as _PreviewAssetPolicy, PreviewAssetPaths as _PreviewAssetPaths, PreviewAssetOperations as _PreviewAssetOperations
_preview_asset_loader = _PreviewAssetLoader(
    _PreviewAssetPolicy(root=lambda: ROOT, suffixes=lambda: IMAGE_REFERENCE_SUFFIXES),
    _PreviewAssetPaths(resolve=lambda: resolve_service_path),
    _PreviewAssetOperations(default=lambda: default_asset_for_accessory, candidate=lambda: load_document_image_candidate, select=lambda: select_document_image_candidate, preview=lambda: load_preview_asset_with_metadata), files=_business_files, images=_accessory_image_io
)

def default_asset_for_accessory(item: dict[str, Any]) -> Path | None:
    return _preview_asset_loader.default_asset_for_accessory(item)


def load_preview_asset_with_metadata(item: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]] | None:
    return _preview_asset_loader.load_preview_asset_with_metadata(item)


def load_document_image_candidate(path_value: Any, metadata: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]] | None:
    return _preview_asset_loader.load_document_image_candidate(path_value, metadata)


def select_document_image_candidate(
    candidates: list[tuple[np.ndarray, dict[str, Any]]],
    rng: np.random.Generator | None,
    *,
    multi_policy: str,
    single_policy: str,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    return _select_document_image_candidate_impl(candidates, rng, multi_policy=multi_policy, single_policy=single_policy)


def load_rectified_document_asset_with_metadata(
    item: dict[str, Any],
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    return _preview_asset_loader.load_rectified_document_asset_with_metadata(item, rng)








































def load_preview_asset(item: dict[str, Any]) -> np.ndarray | None:
    return _preview_asset_loader.load_preview_asset(item)


from .accessories.image_job_metadata import (
    ImageJobMetadata, ProvenanceDependencies,
    candidate_image_jobs as _image_metadata_jobs,
    deterministic_task_id as _image_metadata_task_id,
    ensure_image_job_task_id as _image_metadata_ensure_id,
)
_image_job_metadata = ImageJobMetadata(
    ProvenanceDependencies(
        hash_file=lambda path: file_sha256(path),
        policy_version=lambda: ANCHOR_POLICY_VERSION,
        guide_images=lambda: POSE_TARGET_GUIDE_IMAGES,
        max_inputs=lambda: MAX_IMAGE_WORKER_INPUTS,
    ),
    lambda: resolve_model_profiles(), files=_business_files
)


def candidate_image_jobs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return _image_metadata_jobs(candidate)


def deterministic_task_id(candidate: dict[str, Any], job: dict[str, Any]) -> str:
    return _image_metadata_task_id(candidate, job)


def ensure_image_job_task_id(candidate: dict[str, Any], job: dict[str, Any]) -> bool:
    return _image_metadata_ensure_id(candidate, job)


from .accessories.image_job_metadata import image_job_matches


from .storage.artifacts.files import FileDigest

_file_digest = FileDigest(files=lambda: _business_files)


def file_sha256(path: Path) -> str | None:
    return _file_digest.file_sha256(path)


def ensure_anchor_image_provenance(job: dict[str, Any]) -> bool:
    return _image_job_metadata.ensure_anchor_image_provenance(job)


def ensure_image_job_target_guides(job: dict[str, Any]) -> bool:
    return _image_job_metadata.ensure_image_job_target_guides(job)


def ensure_candidate_image_job_task_ids(candidate: dict[str, Any]) -> bool:
    return _image_job_metadata.ensure_candidate_image_job_task_ids(candidate)


from .model_profiles.snapshots import freeze_record as freeze_model_record, pinned as pinned_model_profiles


def resolve_model_profiles():
    """Composition-only late binding; domain decorators receive this callable."""
    return model_profile_service


def record_model_call(settings, elapsed_ms, ok, usage):
    return resolve_model_profiles().record_call(settings, elapsed_ms, ok, usage)


def store_candidate_image_job(candidate: dict[str, Any], updated_job: dict[str, Any]) -> None:
    return _image_job_metadata.store_candidate_image_job(candidate, updated_job)


from .accessories.reference_evidence import saturated_chroma_mask as _saturated_chroma_mask_impl
from .accessories.reference_evidence import ReferenceEvidence as _ReferenceEvidence
from .accessories.reference_evidence_ports import ReferencePolicy as _ReferencePolicy, ReferencePaths as _ReferencePaths, ReferenceContexts as _ReferenceContexts, ReferenceChroma as _ReferenceChroma
_reference_evidence = _ReferenceEvidence(
    _ReferencePolicy(suffixes=lambda: IMAGE_REFERENCE_SUFFIXES, screens=lambda: CHROMA_SCREEN_OPTIONS),
    _ReferencePaths(resolve=lambda: resolve_service_path, jobs=lambda: candidate_image_jobs, default=lambda: default_asset_for_accessory, preferred=lambda: ai_profile_reference_paths, first_source=lambda: first_source_ai_reference_path, inventory=lambda: accessory_image_paths),
    _ReferenceContexts(uid=lambda: accessory_uid, bounded=lambda: bounded_text, context=lambda: image_reference_context, references=lambda: accessory_reference_image_contexts),
    _ReferenceChroma(normalize=lambda: normalize_chroma_screen, mask=lambda: saturated_chroma_mask), files=_business_files, images=_accessory_image_io
)

def accessory_image_paths(item: dict[str, Any]) -> list[Path]:
    return _reference_evidence.accessory_image_paths(item)


def ai_profile_reference_paths(item: dict[str, Any]) -> list[Path]:
    return _reference_evidence.ai_profile_reference_paths(item)


from .config.environment import env_flag


from .runtime.text_policy import bounded_text


def string_list(value: Any, fallback: list[str] | None = None, *, max_items: int = 12, max_len: int = 96) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = fallback or []
    items: list[str] = []
    seen = set()
    for raw in raw_items:
        item = bounded_text(raw, max_len)
        key = item.lower()
        if not item or key in seen:
            continue
        items.append(item)
        seen.add(key)
        if len(items) >= max_items:
            break
    return items


ACCESSORY_ENGLISH_NAME_FALLBACKS = {
    "玻璃瓶": "Glass Bottle",
    "管子": "Tube",
    "耳机": "Earbuds",
    "手表": "Watch",
    "卷尺": "Tape Measure",
    "护目镜": "Goggles",
    "记号笔": "Marker",
    "剪刀": "Scissors",
    "说明书": "Manual",
    "充电器": "Charger",
    "电池": "Battery",
}

ACCESSORY_ENGLISH_PHRASES = (
    ("glass bottle", "Glass Bottle"),
    ("bottle", "Bottle"),
    ("tube", "Tube"),
    ("pipe", "Tube"),
    ("earbuds", "Earbuds"),
    ("earpod", "Earbuds"),
    ("earphone", "Earbuds"),
    ("headphone", "Headphones"),
    ("smartwatch", "Watch"),
    ("watch", "Watch"),
    ("tape measure", "Tape Measure"),
    ("goggles", "Goggles"),
    ("marker", "Marker"),
    ("scissors", "Scissors"),
    ("manual", "Manual"),
    ("charger", "Charger"),
    ("adapter", "Charger"),
    ("battery", "Battery"),
)

ACCESSORY_ENGLISH_NAME_FIELDS = (
    "english_name",
    "display_label",
    "display_name_en",
    "english_display_name",
    "short_english_name",
    "box_display_label",
)

GENERIC_ENGLISH_NAME_TOKENS = {
    "a",
    "an",
    "and",
    "accessory",
    "clear",
    "complete",
    "configured",
    "cylindrical",
    "detect",
    "detection",
    "for",
    "image",
    "object",
    "physical",
    "required",
    "target",
    "the",
    "visible",
    "with",
}


from .accessories.display_labels import profile_size_text as _profile_size_text_impl
from .accessories.display_labels import AccessoryLabels as _AccessoryLabels
from .accessories.display_label_ports import DisplayLabelPolicy as _DisplayLabelPolicy, DisplayLabelText as _DisplayLabelText
_accessory_labels = _AccessoryLabels(
    _DisplayLabelPolicy(generic_tokens=lambda: GENERIC_ENGLISH_NAME_TOKENS, fields=lambda: ACCESSORY_ENGLISH_NAME_FIELDS, fallbacks=lambda: ACCESSORY_ENGLISH_NAME_FALLBACKS, phrases=lambda: ACCESSORY_ENGLISH_PHRASES),
    _DisplayLabelText(bounded=lambda: bounded_text, strings=lambda: string_list, compact=lambda: compact_english_accessory_name, preferred=lambda: preferred_english_accessory_name),
)

def compact_english_accessory_name(value: Any, *, max_words: int = 6) -> str:
    return _accessory_labels.compact_english_accessory_name(value, max_words=max_words)


def preferred_english_accessory_name(item: dict[str, Any]) -> str:
    return _accessory_labels.preferred_english_accessory_name(item)


def ensure_accessory_english_name(item: dict[str, Any]) -> bool:
    return _accessory_labels.ensure_accessory_english_name(item)


def accessory_display_label(item: dict[str, Any]) -> str:
    return _accessory_labels.accessory_display_label(item)


def profile_size_text(size: dict[str, Any] | None) -> str:
    return _profile_size_text_impl(size)


def image_reference_context(path: Path, accessory_id: str, ordinal: int) -> dict[str, Any] | None:
    return _reference_evidence.image_reference_context(path, accessory_id, ordinal)


def accessory_reference_image_contexts(item: dict[str, Any], *, max_images: int = AI_PROFILE_REFERENCE_IMAGES) -> list[dict[str, Any]]:
    return _reference_evidence.accessory_reference_image_contexts(item, max_images=max_images)


def normalize_chroma_screen(value: Any) -> dict[str, Any]:
    return _reference_evidence.normalize_chroma_screen(value)


def saturated_chroma_mask(image_bgr: np.ndarray, screen: dict[str, Any]) -> np.ndarray:
    return _saturated_chroma_mask_impl(image_bgr, screen)


def accessory_reference_chroma_fraction(item: dict[str, Any], screen_name: str, *, max_images: int = 3) -> float:
    return _reference_evidence.accessory_reference_chroma_fraction(item, screen_name, max_images=max_images)


from .agent.pose_chroma_policy import PoseChromaPolicy as _PoseChromaPolicy
from .agent.pose_cutout_pipeline import PoseCutoutPipeline as _PoseCutoutPipeline
from .agent.pose_sprite_builder import PoseSpriteBuilder as _PoseSpriteBuilder
from .agent.pose_asset_materialization import PoseAssetMaterialization as _PoseAssetMaterialization
from .agent.pose_materialization_ports import PoseChromaSources as _PoseChromaSources, PoseCutoutSources as _PoseCutoutSources, PoseSpritePolicy as _PoseSpritePolicy, PoseSpriteRuntime as _PoseSpriteRuntime, PoseSpriteImages as _PoseSpriteImages, PoseSpriteMetadata as _PoseSpriteMetadata, PoseAssetMedia as _PoseAssetMedia, PoseMaterializationState as _PoseMaterializationState, PoseMaterializationSprites as _PoseMaterializationSprites
_pose_chroma_policy = _PoseChromaPolicy(
    _PoseChromaSources(threshold=lambda: CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD, fraction=lambda: accessory_reference_chroma_fraction, screen=lambda: normalize_chroma_screen),
)
_pose_cutout_pipeline = _PoseCutoutPipeline(
    _PoseCutoutSources(background=lambda: ai_background_cutout_with_bbox, chroma=lambda: chroma_screen_object_cutout, green=lambda: green_conveyor_object_cutout, final_green=lambda: green_screen_object_cutout_with_bbox, generic=lambda: object_cutout_from_image, precise=lambda: precise_green_plate_cutout, usable=lambda: usable_object_cutout),
)
_pose_sprite_builder = _PoseSpriteBuilder(
    _PoseChromaSources(threshold=lambda: CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD, fraction=lambda: accessory_reference_chroma_fraction, screen=lambda: normalize_chroma_screen),
    _PoseSpritePolicy(material=lambda: accessory_material_type, references=lambda: agent_mcp_pose_reference_assets, existing=lambda: clean_sprite_assets, complete=lambda: clean_sprites_policy_complete, deduplicate=lambda: dedup_agent_mcp_pose_references, alpha=lambda: object_alpha_material_policy),
    _PoseSpriteRuntime(version=lambda: AGENT_MCP_SPRITE_BUILD_VERSION, root=lambda: NORMALIZED_DIR, identifier=lambda: accessory_uid, rng=lambda: np.random.default_rng, safe_id=lambda: safe_record_id, now=lambda: time.time),
    _PoseSpriteImages(read_mode=lambda: cv2.IMREAD_COLOR, read=lambda: cv2.imread if _business_files.runtime_provider() is None else _image_files.imread, segment=lambda: segment_agent_mcp_pose_object, write=lambda: write_clean_sprite),
    _PoseSpriteMetadata(laying=lambda: apply_laying_standard_render_size_hints, scale=lambda: apply_upright_scale_correction_metadata, normalize=lambda: normalize_sprite_family_canvases, footprint=lambda: pose_render_footprint_metadata),
    _PoseAssetMedia(resolve=lambda: resolve_service_path, suffixes=lambda: IMAGE_REFERENCE_SUFFIXES, digest=lambda: file_sha256, public_url=lambda: public_output_url),
)
_pose_asset_materialization = _PoseAssetMaterialization(
    _PoseChromaSources(threshold=lambda: CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD, fraction=lambda: accessory_reference_chroma_fraction, screen=lambda: normalize_chroma_screen),
    _PoseMaterializationState(tool=lambda: AGENT_MCP_TOOL_POSE_IMAGE, lookup=lambda: accessory_lookup_by_id, now=lambda: agent_mcp_now, current=lambda: agent_mcp_orchestration),
    _PoseAssetMedia(resolve=lambda: resolve_service_path, suffixes=lambda: IMAGE_REFERENCE_SUFFIXES, digest=lambda: file_sha256, public_url=lambda: public_output_url),
    _PoseMaterializationSprites(build=lambda: build_clean_sprites_from_agent_mcp_poses, sources=lambda: object_photo_highlight_source_paths, ready=lambda: photo_highlight_clean_sprites_ready),
)

def choose_agent_mcp_chroma_screen(item: dict[str, Any]) -> dict[str, Any]:
    return _pose_chroma_policy.choose_agent_mcp_chroma_screen(item)


from .accessories.profile_projection import AccessoryProfileProjection as _AccessoryProfileProjection
from .accessories.profile_projection_ports import ProfileIdentity as _ProfileIdentity, ProfileText as _ProfileText, ProfileDimensions as _ProfileDimensions, ProfileReferences as _ProfileReferences
_accessory_profile_projection = _AccessoryProfileProjection(
    _ProfileIdentity(uid=lambda: accessory_uid, material=lambda: accessory_material_type, alpha=lambda: object_alpha_material_policy),
    _ProfileText(bounded=lambda: bounded_text, strings=lambda: string_list, preferred=lambda: preferred_english_accessory_name, compact=lambda: compact_english_accessory_name, size=lambda: profile_size_text),
    _ProfileDimensions(physical=lambda: ai_profile_dimensions_from_physical_size, normalize=lambda: normalize_ai_profile_dimensions, ratio=lambda: ai_profile_top_view_aspect_ratio, number=lambda: optional_float),
    _ProfileReferences(contexts=lambda: accessory_reference_image_contexts, fallback=lambda: fallback_accessory_ai_profile, limit=lambda: AI_PROFILE_REFERENCE_IMAGES),
)

def fallback_accessory_ai_profile(item: dict[str, Any], reference_images: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return _accessory_profile_projection.fallback_accessory_ai_profile(item, reference_images)


def normalize_accessory_ai_profile(raw: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_profile_projection.normalize_accessory_ai_profile(raw, item)






from local_inspection_service.model_providers.configuration_ports import JsonDefaults, ImageDefaults, ValidationCapabilities, PublicUrlCapabilities
from local_inspection_service.model_providers.configuration_defaults import ProviderDefaults
from local_inspection_service.model_providers.configuration_validation import ProviderValidation
from local_inspection_service.model_providers.public_urls import PublicProviderURLs
_provider_configuration_defaults = ProviderDefaults(
    JsonDefaults(lambda: AI_DEFAULT_MODELS, lambda: AI_DEFAULT_MODEL, lambda: AI_DEFAULT_BASE_URLS, lambda: AI_DEFAULT_PROVIDER, lambda: AI_PROVIDER_LABELS),
    ImageDefaults(lambda: IMAGE_GENERATION_DEFAULT_MODELS, lambda: IMAGE_GENERATION_DEFAULT_BASE_URLS, lambda: IMAGE_GENERATION_DEFAULT_PROVIDER, lambda: IMAGE_GENERATION_DEFAULT_API_KEY_ENVS, lambda: IMAGE_GENERATION_API_KEY_ENV, lambda: IMAGE_GENERATION_PROVIDER_KEYS, lambda: IMAGE_GENERATION_PROVIDER_LABELS),
)
_provider_configuration_validation = ProviderValidation(
    ValidationCapabilities(lambda: AI_SUPPORTED_PROVIDERS, lambda: IMAGE_GENERATION_SUPPORTED_PROVIDERS, lambda: HTTPException, lambda: re.fullmatch, lambda: urlsplit),
)
_provider_public_urls = PublicProviderURLs(
    PublicUrlCapabilities(lambda: urlsplit, lambda: urlunsplit, lambda: bounded_text),
)

def default_ai_model(provider: str) -> str:
    return _provider_configuration_defaults.default_ai_model(provider)


def default_ai_base_url(provider: str) -> str:
    return _provider_configuration_defaults.default_ai_base_url(provider)


def ai_provider_label(provider: str) -> str:
    return _provider_configuration_defaults.ai_provider_label(provider)


def default_image_generation_model(provider: str) -> str:
    return _provider_configuration_defaults.default_image_generation_model(provider)


def default_image_generation_base_url(provider: str) -> str:
    return _provider_configuration_defaults.default_image_generation_base_url(provider)


def default_image_generation_api_key_env(provider: str) -> str:
    return _provider_configuration_defaults.default_image_generation_api_key_env(provider)


def image_generation_provider_key(provider: str) -> str:
    return _provider_configuration_defaults.image_generation_provider_key(provider)


def image_generation_provider_label(provider: str) -> str:
    return _provider_configuration_defaults.image_generation_provider_label(provider)


from .model_providers.key_identity import KeyIdentity as _KeyIdentity
from .model_providers.local_secret_store import LocalSecretStore as _LocalSecretStore
from .model_providers.key_material_ports import KeyIdentityRuntime as _KeyIdentityRuntime, SecretPaths as _SecretPaths, SecretCodec as _SecretCodec, SecretFileOperations as _SecretFileOperations, SecretEnvironment as _SecretEnvironment, SecretPolicy as _SecretPolicy, SecretStoreAccess as _SecretStoreAccess
_key_identity = _KeyIdentity(
    _KeyIdentityRuntime(sha256=lambda: hashlib.sha256, time_ns=lambda: time.time_ns, substitute=lambda: re.sub, fullmatch=lambda: re.fullmatch, key_id=lambda: ai_key_id),
)
_local_secret_store = _LocalSecretStore(
    _SecretPaths(directory=lambda: DATA_DIR, file=lambda: LOCAL_SECRET_ENV_PATH),
    _SecretCodec(loads=lambda: json.loads, dumps=lambda: json.dumps, decode_error=lambda: json.JSONDecodeError),
    _SecretFileOperations(chmod=lambda: os.chmod, replace=lambda: os.replace),
    _SecretEnvironment(values=lambda: os.environ),
    _SecretPolicy(fullmatch=lambda: re.fullmatch, validate=lambda: validate_ai_key_env, default_environment=lambda: default_secret_env_name, identity=lambda: secret_key_item_id, text=lambda: bounded_text),
    _SecretStoreAccess(load=lambda: load_local_secret_env, save=lambda: save_local_secret_env, set=lambda: set_local_secret_env),
)

def mask_secret(value: str) -> str:
    return _key_identity.mask_secret(value)


def ai_key_id(secret: str) -> str:
    return _key_identity.ai_key_id(secret)


def secret_key_item_id(env_name: str, secret: str = "") -> str:
    return _key_identity.secret_key_item_id(env_name, secret)


def default_secret_env_name(prefix: str, secret: str = "", *, provider: str = "") -> str:
    return _key_identity.default_secret_env_name(prefix, secret, provider=provider)


def load_local_secret_env() -> dict[str, str]:
    return _local_secret_store.load_local_secret_env()


def save_local_secret_env(values: dict[str, str]) -> None:
    return _local_secret_store.save_local_secret_env(values)


def local_secret_env_value(name: str) -> str:
    return _local_secret_store.local_secret_env_value(name)


def set_local_secret_env(name: str, value: str) -> None:
    return _local_secret_store.set_local_secret_env(name, value)


def delete_local_secret_env(name: str) -> None:
    return _local_secret_store.delete_local_secret_env(name)


def persist_secret_key_items(items: list[dict[str, str]], default_prefix: str) -> list[dict[str, str]]:
    return _local_secret_store.persist_secret_key_items(items, default_prefix)


from .model_providers.key_registry import ProviderKeyRegistry as _ProviderKeyRegistry
from .model_providers.key_registry_ports import KeyMaterial as _KeyMaterial, KeyPresentation as _KeyPresentation, JsonKeyPolicy as _JsonKeyPolicy, ImageKeyPolicy as _ImageKeyPolicy, AgentKeyPolicy as _AgentKeyPolicy
_provider_key_registry = _ProviderKeyRegistry(
    _KeyMaterial(environment=lambda: local_secret_env_value, identity=lambda: secret_key_item_id, default_environment=lambda: default_secret_env_name),
    _KeyPresentation(text=lambda: bounded_text, mask=lambda: mask_secret, json_label=lambda: ai_provider_label, image_label=lambda: image_generation_provider_label, agent_label=lambda: agent_provider_label),
    _JsonKeyPolicy(default_provider=lambda: AI_DEFAULT_PROVIDER, supported=lambda: AI_SUPPORTED_PROVIDERS),
    _ImageKeyPolicy(default_provider=lambda: IMAGE_GENERATION_DEFAULT_PROVIDER, supported=lambda: IMAGE_GENERATION_SUPPORTED_PROVIDERS, validate=lambda: validate_image_generation_provider),
    _AgentKeyPolicy(supported=lambda: AGENT_SUPPORTED_PROVIDERS, normalize=lambda: normalize_agent_provider),
)

def normalize_ai_key_items(config: dict[str, Any], provider: str | None = None) -> list[dict[str, str]]:
    return _provider_key_registry.normalize_ai_key_items(config, provider)


def public_ai_key_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return _provider_key_registry.public_ai_key_items(items)


def ai_keys_for_provider(items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
    return _provider_key_registry.ai_keys_for_provider(items, provider)


def normalize_image_key_items(config: dict[str, Any], provider: str) -> list[dict[str, str]]:
    return _provider_key_registry.normalize_image_key_items(config, provider)


def normalize_agent_key_items(config: dict[str, Any]) -> list[dict[str, str]]:
    return _provider_key_registry.normalize_agent_key_items(config)


def image_keys_for_provider(items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
    return _provider_key_registry.image_keys_for_provider(items, provider)


def agent_keys_for_provider(items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
    return _provider_key_registry.agent_keys_for_provider(items, provider)


def validate_ai_provider(value: Any) -> str:
    return _provider_configuration_validation.validate_ai_provider(value)


def validate_image_generation_provider(value: Any) -> str:
    return _provider_configuration_validation.validate_image_generation_provider(value)


def validate_ai_model(value: Any) -> str:
    return _provider_configuration_validation.validate_ai_model(value)


def validate_ai_base_url(value: Any) -> str:
    return _provider_configuration_validation.validate_ai_base_url(value)


def public_ai_base_url(value: Any) -> str:
    return _provider_public_urls.public_ai_base_url(value)


def masked_url_for_status(value: Any) -> str:
    return _provider_public_urls.masked_url_for_status(value)


def validate_ai_proxy_url(value: Any) -> str:
    return _provider_configuration_validation.validate_ai_proxy_url(value)


from .model_providers.proxy_runtime import ProviderProxyRuntime
from .model_providers.proxy_runtime_ports import ProxySettings, ProxyCalls, ProxyTransports

_provider_proxy_runtime = ProviderProxyRuntime(
    settings=ProxySettings(
        AI_PROXY_ENV_NAMES=lambda: AI_PROXY_ENV_NAMES,
        AI_LOCAL_PROXY_URL=lambda: AI_LOCAL_PROXY_URL,
        AI_AUTO_LOCAL_PROXY_ENV=lambda: AI_AUTO_LOCAL_PROXY_ENV,
    ),
    calls=ProxyCalls(
        validate_ai_proxy_url=lambda: validate_ai_proxy_url,
        ai_proxy_url_from_environment=lambda: ai_proxy_url_from_environment,
        env_flag_enabled=lambda: env_flag_enabled,
        local_proxy_available=lambda: local_proxy_available,
    ),
    transports=ProxyTransports(
        os=lambda: os,
        socket=lambda: socket,
        urllib=lambda: urllib,
    ),
)


def ai_proxy_url_from_environment() -> tuple[str, str]:
    return _provider_proxy_runtime.ai_proxy_url_from_environment()


def local_proxy_available(proxy_url: str = AI_LOCAL_PROXY_URL) -> bool:
    return _provider_proxy_runtime.local_proxy_available(proxy_url)


def env_flag_enabled(name: str, default: bool = True) -> bool:
    return _provider_proxy_runtime.env_flag_enabled(name, default)


def ai_proxy_url_from_config(local: dict[str, Any], provider: str) -> tuple[str, str, bool]:
    return _provider_proxy_runtime.ai_proxy_url_from_config(local, provider)


def ai_urlopen(request: urllib.request.Request, settings: dict[str, Any], *, timeout: float):
    return _provider_proxy_runtime.ai_urlopen(request, settings, timeout=timeout)


def validate_ai_timeout(value: Any) -> float:
    return _provider_configuration_validation.validate_ai_timeout(value)


def validate_image_generation_timeout(value: Any) -> float:
    return _provider_configuration_validation.validate_image_generation_timeout(value)


def validate_ai_key_env(value: Any) -> str:
    return _provider_configuration_validation.validate_ai_key_env(value)


from .model_providers.local_model_config import LocalModelConfig
from .model_providers.local_model_config_ports import LocalModelConfigFiles, LocalJsonModelPolicy, LocalImageModelPolicy

_local_model_config = LocalModelConfig(
    files=LocalModelConfigFiles(
        ensure_dirs=lambda: ensure_dirs,
        _business_files=lambda: _business_files,
        AI_LOCAL_CONFIG_PATH=lambda: AI_LOCAL_CONFIG_PATH,
        DATA_DIR=lambda: DATA_DIR,
        ai_local_config_temp_path=lambda: ai_local_config_temp_path,
        DEFAULT_AI_CONFIG=lambda: DEFAULT_AI_CONFIG,
        HTTPException=lambda: HTTPException,
    ),
    json_policy=LocalJsonModelPolicy(
        AI_DEFAULT_PROVIDER=lambda: AI_DEFAULT_PROVIDER,
        AI_SUPPORTED_PROVIDERS=lambda: AI_SUPPORTED_PROVIDERS,
        AI_DEFAULT_TIMEOUT_SECONDS=lambda: AI_DEFAULT_TIMEOUT_SECONDS,
        default_ai_model=lambda: default_ai_model,
        default_ai_base_url=lambda: default_ai_base_url,
        validate_ai_proxy_url=lambda: validate_ai_proxy_url,
        validate_ai_timeout=lambda: validate_ai_timeout,
        normalize_ai_key_items=lambda: normalize_ai_key_items,
        ai_keys_for_provider=lambda: ai_keys_for_provider,
    ),
    image_policy=LocalImageModelPolicy(
        IMAGE_GENERATION_DEFAULT_PROVIDER=lambda: IMAGE_GENERATION_DEFAULT_PROVIDER,
        IMAGE_GENERATION_SUPPORTED_PROVIDERS=lambda: IMAGE_GENERATION_SUPPORTED_PROVIDERS,
        IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS=lambda: IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS,
        default_image_generation_model=lambda: default_image_generation_model,
        default_image_generation_base_url=lambda: default_image_generation_base_url,
        validate_ai_base_url=lambda: validate_ai_base_url,
        validate_image_generation_timeout=lambda: validate_image_generation_timeout,
        normalize_image_key_items=lambda: normalize_image_key_items,
        image_keys_for_provider=lambda: image_keys_for_provider,
    ),
)


def load_ai_local_config() -> dict[str, Any]:
    return _local_model_config.load_ai_local_config()


def ai_local_config_temp_path() -> Path:
    return _local_model_config.ai_local_config_temp_path()


def save_ai_local_config(config: dict[str, Any]) -> None:
    return _local_model_config.save_ai_local_config(config)






















def redact_status_payload_for_user(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    return _account_projections.redact_status_payload_for_user(payload, user)


def redact_config_summary_for_user(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    return _account_projections.redact_config_summary_for_user(payload, user)




def redact_accessory_payload_for_user(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    return _account_projections.redact_accessory_payload_for_user(payload, user)






from .detection.image_geometry import resize_bgr_max_side
























































































from .analytics.analysis_records import AnalysisNormalization, AnalysisNormalizer, sanitize_data_analysis_record_id
from .analytics.analysis_repository import AnalysisStoreDependencies, AnalysisRepository
from .analytics.analysis_service import AnalysisAccess, AnalysisRecords
from .analytics.analysis_queries import AnalysisPresentation, AnalysisQueries
from .analytics.analysis_api import register_analysis_api

from .analytics.analysis_processing import (
    ProcessingDependencies, ProcessingProjection, image_processing_status,
    image_processing_type_label, image_processing_summary,
)
from .analytics.analysis_scope import ScopeDependencies, AnalysisScope, data_analysis_scope_match_key, data_analysis_count_for_scope_item
from .analytics.analysis_projection import ProjectionDependencies, AnalysisProjection, public_data_analysis_ai_result
from .analytics.analysis_publication import PublicationDependencies, AnalysisPublisher
from .analytics.analysis_composition import AnalysisServices, AnalysisStorage

_analysis = AnalysisServices(
    normalization=AnalysisNormalization(
    default_task_id=AI_DETECTION_MODEL_ID, default_task_label=AI_DETECTION_LABEL,
    clean_task_name=lambda value, fallback: clean_ai_detection_task_name(value, fallback),
    created_at=lambda record: record_created_at(record), updated_at=lambda record: record_updated_at(record),
    owner_id=lambda record: record_owner_id(record), owner_username=lambda record: record_owner_username(record),
),
    storage=AnalysisStorage(
    path=lambda: DATA_ANALYSIS_RECORDS_PATH, runtime_repository=lambda: runtime_postgres_repository_or_none(),
    ensure_dirs=lambda: ensure_dirs(),
),
    access=AnalysisAccess(
    is_admin=lambda user: user_is_admin(user),
    visible=lambda record, user, target: record_visible_to_user(record, user, target),
    require_access=lambda record, user, *, write=False: require_record_access(record, user, write=write),
),
    processing=ProcessingDependencies(
    safe_id=lambda value: safe_record_id(value), bounded_text=lambda value, length: bounded_text(value, length),
    sanitize_paths=lambda value: public_path_sanitized(value),
    output_url=lambda path: public_output_url_for_existing(path), resolve_path=lambda path: resolve_service_path(path),
    load_json=lambda path: load_json_file_mtime_cached(path), current_cache=lambda: _read_path_cache.get(),
    created_at=lambda record: record_created_at(record), updated_at=lambda record: record_updated_at(record),
    auto_state=lambda task_id: load_auto_optimize_state(task_id),
),
    scope=ScopeDependencies(
    current_user=lambda: current_auth_user(), load_config=lambda: load_config(),
    scope_config=lambda config, user: scope_config_for_user(config, user),
    accessory_lookup=lambda config: accessory_lookup_by_id(config), detection_tasks=lambda: load_ai_detection_tasks(),
    serialize_task=lambda task, config: serialize_ai_detection_task(task, config),
    normalize_counts=lambda counts: normalize_ai_detection_task_counts(counts),
    accessory_id=lambda item: accessory_uid(item), accessory_aliases=lambda item: accessory_id_aliases(item),
    english_name=lambda value: compact_english_accessory_name(value), bounded_text=lambda value, length: bounded_text(value, length),
),
    projection=ProjectionDependencies(
    created_at=lambda record: record_created_at(record), updated_at=lambda record: record_updated_at(record),
    owner_id=lambda record: record_owner_id(record), owner_username=lambda record: record_owner_username(record),
    default_task_label=AI_DETECTION_LABEL, output_directory=lambda: OUTPUT_DIR,
    resolve_path=lambda path: resolve_service_path(path), path_is_under=lambda path, root: path_is_under(path, root),
),
    publication=PublicationDependencies(
    current_user=lambda: _request_user.get(), owner_fields=lambda: current_owner_fields(),
    owner_id=lambda record: record_owner_id(record), owner_username=lambda record: record_owner_username(record),
    default_task_id=AI_DETECTION_MODEL_ID, default_task_label=AI_DETECTION_LABEL,
    clean_task_name=lambda value, fallback: clean_ai_detection_task_name(value, fallback),
    string_list=lambda value, **kwargs: string_list(value, **kwargs),
    resolve_path=lambda path: resolve_service_path(path), safe_name=lambda value: safe_name(value),
    output_url=lambda path: public_output_url_for_existing(path),
    capture=lambda record, result, request_id, path: record_auto_optimize_capture(record, result, request_id, path),
),
    cache_scope=lambda: read_path_cache_scope(), batch_limit=DATA_ANALYSIS_BATCH_LIMIT,
)
_analysis_normalizer = _analysis.normalizer
_analysis_repository = _analysis.repository
_analysis_records = _analysis.records
_analysis_queries = _analysis.queries

normalize_data_analysis_record = _analysis_normalizer.normalize_data_analysis_record
data_analysis_records_temp_path = _analysis_repository.data_analysis_records_temp_path
load_data_analysis_records = _analysis_repository.load_data_analysis_records
save_data_analysis_records = _analysis_repository.save_data_analysis_records
load_data_analysis_record = _analysis_repository.load_data_analysis_record
save_data_analysis_record = _analysis_repository.save_data_analysis_record
delete_data_analysis_record = _analysis_records.delete_data_analysis_record
data_analysis_records_for_user = _analysis_records.data_analysis_records_for_user
find_data_analysis_record = _analysis_records.find_data_analysis_record



_analysis_processing = _analysis.processing
_analysis_scope = _analysis.scope
_analysis_projection = _analysis.projection
_analysis_publisher = _analysis.publisher

image_processing_public_url = _analysis_processing.image_processing_public_url
image_processing_item = _analysis_processing.image_processing_item
merge_image_processing_items = _analysis_processing.merge_image_processing_items
auto_optimize_dataset_processing_items_for_sample = _analysis_processing.auto_optimize_dataset_processing_items_for_sample
auto_optimize_sample_processing_items = _analysis_processing.auto_optimize_sample_processing_items
data_analysis_image_processing_items = _analysis_processing.data_analysis_image_processing_items
data_analysis_record_required_scope = _analysis_scope.data_analysis_record_required_scope
data_analysis_scoped_ai_summary = _analysis_scope.data_analysis_scoped_ai_summary
public_data_analysis_scope_payload = _analysis_scope.public_data_analysis_scope_payload
public_data_analysis_record = _analysis_projection.public_data_analysis_record
data_analysis_task_groups = _analysis_projection.data_analysis_task_groups
data_analysis_record_image_path = _analysis_projection.data_analysis_record_image_path
ai_detection_summary_for_analysis = _analysis_publisher.ai_detection_summary_for_analysis
persist_data_analysis_record_for_ai_detection = _analysis_publisher.persist_data_analysis_record_for_ai_detection
upsert_data_analysis_image_processing_record = _analysis_publisher.upsert_data_analysis_image_processing_record


from .training.auto_optimization_state_store import AutoOptimizationStateStore
from .training.auto_optimization_state_ports import AutoOptimizationStateStorage, AutoOptimizationStatePolicy, AutoOptimizationStateCache

_auto_optimization_state_store = AutoOptimizationStateStore(
    storage=AutoOptimizationStateStorage(
        AUTO_OPTIMIZE_DIR=lambda: AUTO_OPTIMIZE_DIR,
        AI_DETECTION_MODEL_ID=lambda: AI_DETECTION_MODEL_ID,
        _business_files=lambda: _business_files,
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        auto_optimize_task_path=lambda: auto_optimize_task_path,
    ),
    policy=AutoOptimizationStatePolicy(
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        safe_record_id=lambda: safe_record_id,
        row_raw_json_list=lambda: row_raw_json_list,
        auto_optimize_state_row=lambda: auto_optimize_state_row,
        default_auto_optimize_settings=_auto_optimization_settings.default_auto_optimize_settings,
        resolve_model_profiles=lambda: resolve_model_profiles,
    ),
    cache=AutoOptimizationStateCache(
        _read_path_cache=lambda: _read_path_cache,
        store_read_cache_get=lambda: store_read_cache_get,
        store_read_cache_put=lambda: store_read_cache_put,
        store_read_cache_invalidate=lambda: store_read_cache_invalidate,
    ),
)


def auto_optimize_task_path(task_id: str) -> Path:
    return _auto_optimization_state_store.auto_optimize_task_path(task_id)


default_auto_optimize_settings = _auto_optimization_settings.default_auto_optimize_settings


auto_optimize_negative_samples_per_real_image = _auto_optimization_settings.auto_optimize_negative_samples_per_real_image


auto_optimize_positive_derivatives_per_real_image = _auto_optimization_settings.auto_optimize_positive_derivatives_per_real_image


auto_optimize_training_requirements = _auto_optimization_settings.auto_optimize_training_requirements


auto_optimize_samples_per_real_image = _auto_optimization_settings.auto_optimize_samples_per_real_image


auto_optimize_training_parameters = _auto_optimization_settings.auto_optimize_training_parameters




from .training.auto_optimization_recommendations import AutoOptimizationRecommendations

_auto_optimization_recommendations = AutoOptimizationRecommendations(
    settings=_auto_optimization_settings,
    accessory_lookup_by_id=lambda config: accessory_lookup_by_id(config),
    accessory_material_type=lambda item: accessory_material_type(item),
    bounded_text=lambda: bounded_text,
)


def auto_optimize_complexity_rule_recommendation(
    config: dict[str, Any],
    accessory_ids: list[str],
    expected_production_count: int,
) -> dict[str, Any]:
    return _auto_optimization_recommendations.auto_optimize_complexity_rule_recommendation(config, accessory_ids, expected_production_count)


def clamp_auto_optimize_initialization_recommendation(
    raw: dict[str, Any],
    fallback: dict[str, Any],
    expected_production_count: int,
) -> dict[str, Any]:
    return _auto_optimization_recommendations.clamp_auto_optimize_initialization_recommendation(raw, fallback, expected_production_count)


def public_auto_optimize_initialization_payload(state: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_recommendations.public_auto_optimize_initialization_payload(state, settings)


from .training.auto_optimization_initialization import AutoOptimizationInitialization
from .training.auto_optimization_initialization_ports import AutoOptimizationAdvisorPorts, AutoOptimizationTaskInitializationPorts

_auto_optimization_initialization = AutoOptimizationInitialization(
    negative_samples_default=AUTO_OPTIMIZE_NEGATIVES_PER_REAL_IMAGE,
    advisor=AutoOptimizationAdvisorPorts(
        ai_detection_settings=lambda: ai_detection_settings,
        accessory_lookup_by_id=lambda: accessory_lookup_by_id,
        accessory_material_type=lambda: accessory_material_type,
        bounded_text=lambda: bounded_text,
        generate_provider_json_with_fallback=lambda: generate_provider_json_with_fallback,
        clamp_auto_optimize_initialization_recommendation=lambda: clamp_auto_optimize_initialization_recommendation,
    ),
    task=AutoOptimizationTaskInitializationPorts(
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        canonical_pipeline_accessory_ids=lambda: canonical_pipeline_accessory_ids,
        auto_optimize_complexity_rule_recommendation=lambda: auto_optimize_complexity_rule_recommendation,
        agent_auto_optimize_initialization_recommendation=lambda: agent_auto_optimize_initialization_recommendation,
        _auto_optimize_lock=lambda: _auto_optimize_lock,
        load_auto_optimize_state=lambda: load_auto_optimize_state,
        default_auto_optimize_settings=_auto_optimization_settings.default_auto_optimize_settings,
        save_auto_optimize_state=lambda: save_auto_optimize_state,
        start_auto_optimize_label_worker=lambda: start_auto_optimize_label_worker,
    ),
)


def agent_auto_optimize_initialization_recommendation(
    config: dict[str, Any],
    accessory_ids: list[str],
    expected_production_count: int,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    return _auto_optimization_initialization.agent_auto_optimize_initialization_recommendation(config, accessory_ids, expected_production_count, fallback)


def initialize_auto_optimize_for_pipeline_task(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_initialization.initialize_auto_optimize_for_pipeline_task(task, config)


# Cache instances belong to this application composition; no request identity
# or database connection is retained in shared cache state.
from .runtime.read_caches import RequestReadCache, StoreReadCache, JsonFileReadCache

_request_read_cache = RequestReadCache()
_read_path_cache = _request_read_cache.current
read_path_cache_scope = _request_read_cache.scope

# The unchanged TTL bounds cross-process writes; local writers invalidate keys.
STORE_READ_CACHE_TTL_SECONDS = 5.0
_store_cache = StoreReadCache(lambda: STORE_READ_CACHE_TTL_SECONDS, lambda: time.monotonic())
store_read_cache_get = _store_cache.get
store_read_cache_put = _store_cache.put
store_read_cache_invalidate = _store_cache.invalidate

_json_cache = JsonFileReadCache(lambda: _business_files)
load_json_file_mtime_cached = _json_cache.load


def load_auto_optimize_state(task_id: str) -> dict[str, Any]:
    return _auto_optimization_state_store.load_auto_optimize_state(task_id)


def save_auto_optimize_state(state: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_state_store.save_auto_optimize_state(state)


def list_auto_optimize_states() -> list[dict[str, Any]]:
    return _auto_optimization_state_store.list_auto_optimize_states()


from .training.auto_optimization_status import AutoOptimizationStatus
from .training.auto_optimization_status_ports import AutoOptimizationStatusState, AutoOptimizationStatusPolicy

_auto_optimization_status = AutoOptimizationStatus(
    AutoOptimizationStatusState(
        _auto_optimize_lock=lambda: _auto_optimize_lock,
        load_auto_optimize_state=lambda: load_auto_optimize_state,
        save_auto_optimize_state=lambda: save_auto_optimize_state,
        hydrate_auto_optimize_background_from_ai_task=lambda: hydrate_auto_optimize_background_from_ai_task,
        auto_optimize_completed_model_id=lambda: auto_optimize_completed_model_id,
        auto_optimize_stop_capture_for_model_locked=lambda: auto_optimize_stop_capture_for_model_locked,
        find_training_task=lambda: find_training_task,
        record_visible_to_user=lambda: record_visible_to_user,
        current_auth_user=lambda: current_auth_user,
        start_auto_optimize_label_worker=lambda: start_auto_optimize_label_worker,
        public_auto_optimize_state=lambda: public_auto_optimize_state,
    ),
    AutoOptimizationStatusPolicy(
        default_auto_optimize_settings=_auto_optimization_settings.default_auto_optimize_settings,
        auto_optimize_public_sprite_pool=lambda: auto_optimize_public_sprite_pool,
        background_set_payload=lambda: background_set_payload,
        auto_optimize_samples_per_real_image=_auto_optimization_settings.auto_optimize_samples_per_real_image,
        auto_optimize_training_parameters=_auto_optimization_settings.auto_optimize_training_parameters,
        auto_optimize_training_requirements=_auto_optimization_settings.auto_optimize_training_requirements,
        auto_optimize_negative_samples_per_real_image=_auto_optimization_settings.auto_optimize_negative_samples_per_real_image,
        auto_optimize_positive_derivatives_per_real_image=_auto_optimization_settings.auto_optimize_positive_derivatives_per_real_image,
        AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT=lambda: AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT,
        public_path_sanitized=lambda: public_path_sanitized,
        auto_optimize_phase_name=lambda: auto_optimize_phase_name,
        normalize_expected_production_count=lambda: normalize_expected_production_count,
        public_auto_optimize_initialization_payload=lambda: public_auto_optimize_initialization_payload,
    ),
)


def public_auto_optimize_state(task_id: str, *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    return _auto_optimization_status.public_auto_optimize_state(task_id, user=user)


from .training.auto_optimization_readiness import AutoOptimizationReadiness
from .training.auto_optimization_readiness_ports import AutoOptimizationReadinessPorts

_auto_optimization_readiness = AutoOptimizationReadiness(AutoOptimizationReadinessPorts(
    find_training_task=lambda: find_training_task,
    auto_optimize_linked_pipeline_model_id=lambda: auto_optimize_linked_pipeline_model_id,
    load_config=lambda: load_config,
    canonical_pipeline_accessory_ids=lambda: canonical_pipeline_accessory_ids,
    normalize_pipeline_accessory_counts=lambda: normalize_pipeline_accessory_counts,
    load_pipeline_tasks=lambda: load_pipeline_tasks,
    normalize_pipeline_detection_method=lambda: normalize_pipeline_detection_method,
    pipeline_task_model_status=lambda: pipeline_task_model_status,
    pipeline_task_model_id=lambda: pipeline_task_model_id,
    default_auto_optimize_settings=_auto_optimization_settings.default_auto_optimize_settings,
    auto_optimize_completed_model_id=lambda: auto_optimize_completed_model_id,
))


def auto_optimize_phase_name(state: dict[str, Any]) -> str:
    return _auto_optimization_readiness.auto_optimize_phase_name(state)


def auto_optimize_completed_model_id(state: dict[str, Any]) -> str:
    return _auto_optimization_readiness.auto_optimize_completed_model_id(state)


def auto_optimize_linked_pipeline_model_id(state: dict[str, Any]) -> str:
    return _auto_optimization_readiness.auto_optimize_linked_pipeline_model_id(state)


from .pipeline.task_metadata import PipelineTaskMetadata
from .pipeline.task_metadata_ports import MetadataPolicy, MetadataSnapshots

_pipeline_task_metadata = PipelineTaskMetadata(
    policy=MetadataPolicy(
        PIPELINE_DETECTION_METHODS=lambda: PIPELINE_DETECTION_METHODS,
        PIPELINE_TRAINING_METHODS=lambda: PIPELINE_TRAINING_METHODS,
        normalize_pipeline_detection_method=lambda: normalize_pipeline_detection_method,
    ),
    snapshots=MetadataSnapshots(
        accessory_lookup_by_id=lambda: accessory_lookup_by_id,
        pipeline_task_label_snapshot=lambda: pipeline_task_label_snapshot,
        LEGACY_OWNER_ID=lambda: LEGACY_OWNER_ID,
        record_owner_username=lambda: record_owner_username,
        accessory_id_aliases=lambda: accessory_id_aliases,
    ),
)


def pipeline_task_model_id(task: dict[str, Any]) -> str:
    return _pipeline_task_metadata.pipeline_task_model_id(task)


def auto_optimize_stop_capture_for_model_locked(state: dict[str, Any], model_id: str, *, reason: str) -> bool:
    return _auto_optimization_readiness.auto_optimize_stop_capture_for_model_locked(state, model_id, reason=reason)


def auto_optimize_capture_enabled(state: dict[str, Any]) -> bool:
    return _auto_optimization_readiness.auto_optimize_capture_enabled(state)


def auto_optimize_update_settings(task_id: str, request: Any) -> dict[str, Any]:
    return _auto_optimization_status.auto_optimize_update_settings(task_id, request)


from .training.auto_optimization_capture import AutoOptimizationCapture
from .training.auto_optimization_capture_ports import AutoOptimizationCapturePorts

_auto_optimization_capture = AutoOptimizationCapture(AutoOptimizationCapturePorts(
    _auto_optimize_lock=lambda: _auto_optimize_lock,
    load_auto_optimize_state=lambda: load_auto_optimize_state,
    save_auto_optimize_state=lambda: save_auto_optimize_state,
    sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
    auto_optimize_completed_model_id=lambda: auto_optimize_completed_model_id,
    auto_optimize_stop_capture_for_model_locked=lambda: auto_optimize_stop_capture_for_model_locked,
    auto_optimize_capture_enabled=lambda: auto_optimize_capture_enabled,
    resolve_service_path=lambda: resolve_service_path,
    bounded_text=lambda: bounded_text,
    current_owner_fields=lambda: current_owner_fields,
    start_auto_optimize_label_worker=lambda: start_auto_optimize_label_worker,
    start_auto_optimize_shadow_worker=lambda: start_auto_optimize_shadow_worker,
    auto_optimize_detection_candidates=lambda: auto_optimize_detection_candidates,
))


def auto_optimize_detection_candidates(result: dict[str, Any]) -> list[dict[str, Any]]:
    return _auto_optimization_capture.auto_optimize_detection_candidates(result)


def record_auto_optimize_capture(record: dict[str, Any] | None, result: dict[str, Any], request_id: str, image_path: Path | None) -> None:
    return _auto_optimization_capture.record_auto_optimize_capture(record, result, request_id, image_path)


AUTO_OPTIMIZE_MASK_PROMPT_MODE = "plain_description_v1"
AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION = "structured_profile_v1"


from .training.auto_optimization_mask_prompts import AutoOptimizationMaskPrompts
from .training.auto_optimization_mask_visuals import AutoOptimizationMaskVisuals
from .training.auto_optimization_mask_ports import AutoOptimizationMaskPromptPorts, AutoOptimizationMaskVisualPorts

_auto_optimization_mask_prompts = AutoOptimizationMaskPrompts(AutoOptimizationMaskPromptPorts(
    LEGACY_OWNER_ID=lambda: LEGACY_OWNER_ID,
    AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION=lambda: AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION,
    bounded_text=lambda: bounded_text,
    string_list=lambda: string_list,
    accessory_material_type=lambda: accessory_material_type,
    load_config=lambda: load_config,
    scope_config_for_user=lambda: scope_config_for_user,
    accessory_lookup_by_id=lambda: accessory_lookup_by_id,
    build_mask_target_profile=lambda: build_mask_target_profile,
    auto_optimize_mask_owner_user=lambda: auto_optimize_mask_owner_user,
    auto_optimize_mask_target_payload=lambda: auto_optimize_mask_target_payload,
))

_auto_optimization_mask_visuals = AutoOptimizationMaskVisuals(AutoOptimizationMaskVisualPorts(
    DOCUMENT_LIKE_TEXT_HINTS=lambda: DOCUMENT_LIKE_TEXT_HINTS,
    bounded_text=lambda: bounded_text,
    _image_files=lambda: _image_files,
    public_output_url_for_existing=lambda: public_output_url_for_existing,
    auto_optimize_text_mask_requires_document_gate=lambda: auto_optimize_text_mask_requires_document_gate,
))


def auto_optimize_mask_system_prompt() -> str:
    return _auto_optimization_mask_prompts.auto_optimize_mask_system_prompt()


def auto_optimize_mask_owner_user(sample: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_mask_prompts.auto_optimize_mask_owner_user(sample)


def auto_optimize_accessory_lookup_for_sample(sample: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _auto_optimization_mask_prompts.auto_optimize_accessory_lookup_for_sample(sample)


def auto_optimize_mask_target_profile(candidate: dict[str, Any], accessories_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return _auto_optimization_mask_prompts.auto_optimize_mask_target_profile(candidate, accessories_by_id)


AUTO_OPTIMIZE_MASK_PALETTE = [
    {"name": "green", "hex": "#00FF00", "rgb": (0, 255, 0), "bgr": (0, 255, 0)},
    {"name": "blue", "hex": "#0000FF", "rgb": (0, 0, 255), "bgr": (255, 0, 0)},
    {"name": "red", "hex": "#FF0000", "rgb": (255, 0, 0), "bgr": (0, 0, 255)},
    {"name": "yellow", "hex": "#FFFF00", "rgb": (255, 255, 0), "bgr": (0, 255, 255)},
    {"name": "magenta", "hex": "#FF00FF", "rgb": (255, 0, 255), "bgr": (255, 0, 255)},
    {"name": "cyan", "hex": "#00FFFF", "rgb": (0, 255, 255), "bgr": (255, 255, 0)},
    {"name": "orange", "hex": "#FF8000", "rgb": (255, 128, 0), "bgr": (0, 128, 255)},
    {"name": "white", "hex": "#FFFFFF", "rgb": (255, 255, 255), "bgr": (255, 255, 255)},
]


def auto_optimize_mask_target_payload(item: dict[str, Any], index: int) -> dict[str, Any]:
    return _auto_optimization_mask_prompts.auto_optimize_mask_target_payload(item, index)


def auto_optimize_mask_user_prompt(
    assignments: list[dict[str, Any]],
    *,
    input_w: int,
    input_h: int,
    task_type: str = "multi_class_segmentation_mask",
) -> str:
    return _auto_optimization_mask_prompts.auto_optimize_mask_user_prompt(assignments, input_w=input_w, input_h=input_h, task_type=task_type)


def auto_optimize_multicolor_mask_prompt(assignments: list[dict[str, Any]], *, input_w: int = 0, input_h: int = 0) -> str:
    return _auto_optimization_mask_prompts.auto_optimize_multicolor_mask_prompt(assignments, input_w=input_w, input_h=input_h)


def decode_multicolor_mask(mask_bgr: np.ndarray, assignments: list[dict[str, Any]]) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    return _auto_optimization_mask_visuals.decode_multicolor_mask(mask_bgr, assignments)


def draw_auto_optimize_review_overlay(
    image_bgr: np.ndarray,
    labels: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    output_path: Path,
) -> tuple[str, dict[str, Any]]:
    return _auto_optimization_mask_visuals.draw_auto_optimize_review_overlay(image_bgr, labels, failures, output_path)


DOCUMENT_LIKE_TEXT_HINTS = (
    "manual",
    "instruction",
    "document",
    "paper",
    "sheet",
    "card",
    "说明",
    "说明书",
    "文档",
    "资料",
    "卡",
)


def auto_optimize_text_mask_requires_document_gate(candidate: dict[str, Any], profile: dict[str, Any]) -> bool:
    return _auto_optimization_mask_visuals.auto_optimize_text_mask_requires_document_gate(candidate, profile)


def validate_auto_optimize_text_mask_region(
    image_bgr: np.ndarray,
    full_mask: np.ndarray,
    bbox: list[int],
    candidate: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    return _auto_optimization_mask_visuals.validate_auto_optimize_text_mask_region(image_bgr, full_mask, bbox, candidate, profile)


MASK_VERIFIER_SYSTEM_PROMPT = """You are VantaLine's mask verifier for production inspection training data.
You do not generate masks. You inspect whether each colored mask region actually covers the intended target accessory.
Be strict: a region that covers a sibling accessory, a handle/cap, background, shadow, package, or visually related but wrong object must be rejected.
Use the target profile and negative candidates. Do not accept a region only because it is near the target or has a similar color.
Return only compact JSON with this shape:
{"targets":[{"accessory_id":"...","mask_region_matches_target":true,"identity_score":0.0,"localization_score":0.0,"negative_match_score":0.0,"wrong_object_evidence":[],"decision":"accept|review|reject","reason":"..."}],"overall_decision":"accept|review|reject"}.
"""


def auto_optimize_mask_verifier_overlay(image_bgr: np.ndarray, labels: list[dict[str, Any]]) -> np.ndarray:
    return _auto_optimization_mask_visuals.auto_optimize_mask_verifier_overlay(image_bgr, labels)


def auto_optimize_mask_verifier_crop(image_bgr: np.ndarray, label: dict[str, Any]) -> np.ndarray | None:
    return _auto_optimization_mask_visuals.auto_optimize_mask_verifier_crop(image_bgr, label)


def clamp_unit_score(value: Any, default: float = 0.0) -> float:
    return _auto_optimization_mask_visuals.clamp_unit_score(value, default)


from .training.auto_optimization_mask_verification import AutoOptimizationMaskVerification
from .training.auto_optimization_mask_verification_ports import AutoOptimizationMaskVerificationPorts

_auto_optimization_mask_verification = AutoOptimizationMaskVerification(AutoOptimizationMaskVerificationPorts(
    ai_detection_settings=lambda: ai_detection_settings,
    bounded_text=lambda: bounded_text,
    string_list=lambda: string_list,
    image_bgr_data_url=lambda: image_bgr_data_url,
    auto_optimize_mask_verifier_overlay=lambda: auto_optimize_mask_verifier_overlay,
    auto_optimize_mask_verifier_crop=lambda: auto_optimize_mask_verifier_crop,
    generate_provider_json_with_fallback=lambda: generate_provider_json_with_fallback,
    MASK_VERIFIER_SYSTEM_PROMPT=lambda: MASK_VERIFIER_SYSTEM_PROMPT,
    AiProviderError=lambda: AiProviderError,
    clamp_unit_score=lambda: clamp_unit_score,
))


def verify_auto_optimize_mask_sample(sample: dict[str, Any], image_bgr: np.ndarray, labels: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    return _auto_optimization_mask_verification.verify_auto_optimize_mask_sample(sample, image_bgr, labels)


from .training.auto_optimization_sprite_publication import AutoOptimizationSpritePublication
from .training.auto_optimization_sprite_publication_ports import SpritePublication

_auto_optimization_sprite_publication = AutoOptimizationSpritePublication(
    publication=SpritePublication(
        safe_record_id=lambda: safe_record_id,
        _image_files=lambda: _image_files,
        write_clean_sprite=lambda: write_clean_sprite,
        resolve_service_path=lambda: resolve_service_path,
        _business_files=lambda: _business_files,
        public_output_url_for_existing=lambda: public_output_url_for_existing,
        public_path_sanitized=lambda: public_path_sanitized,
    ),
)


def auto_optimize_write_sprite_artifact(
    *,
    image_bgr: np.ndarray,
    full_mask: np.ndarray,
    bbox: list[int],
    sample_id: str,
    accessory_id: str,
    label_name: str,
    artifact_dir: Path,
    source_image_path: Path,
) -> dict[str, Any]:
    return _auto_optimization_sprite_publication.auto_optimize_write_sprite_artifact(image_bgr=image_bgr, full_mask=full_mask, bbox=bbox, sample_id=sample_id, accessory_id=accessory_id, label_name=label_name, artifact_dir=artifact_dir, source_image_path=source_image_path)


from .training.auto_optimization_label_generation import AutoOptimizationLabelGeneration
from .training.auto_optimization_label_generation_ports import LabelGenerationArtifacts, LabelGenerationPolicy, LabelGenerationModels

_auto_optimization_label_generation = AutoOptimizationLabelGeneration(
    LabelGenerationArtifacts(
        resolve_service_path=lambda: resolve_service_path,
        _image_files=lambda: _image_files,
        _business_files=lambda: _business_files,
        public_output_url_for_existing=lambda: public_output_url_for_existing,
        safe_record_id=lambda: safe_record_id,
        auto_optimize_write_sprite_artifact=lambda: auto_optimize_write_sprite_artifact,
    ),
    LabelGenerationPolicy(
        photo_highlight_input_data_url=lambda: photo_highlight_input_data_url,
        auto_optimize_accessory_lookup_for_sample=lambda: auto_optimize_accessory_lookup_for_sample,
        auto_optimize_mask_target_profile=lambda: auto_optimize_mask_target_profile,
        AUTO_OPTIMIZE_MASK_PALETTE=lambda: AUTO_OPTIMIZE_MASK_PALETTE,
        AUTO_OPTIMIZE_MASK_PROMPT_MODE=lambda: AUTO_OPTIMIZE_MASK_PROMPT_MODE,
        auto_optimize_multicolor_mask_prompt=lambda: auto_optimize_multicolor_mask_prompt,
        bounded_text=lambda: bounded_text,
        decode_multicolor_mask=lambda: decode_multicolor_mask,
        alpha_bbox=lambda: alpha_bbox,
        validate_auto_optimize_text_mask_region=lambda: validate_auto_optimize_text_mask_region,
        draw_auto_optimize_review_overlay=lambda: draw_auto_optimize_review_overlay,
        decode_photo_highlight_mask=lambda: decode_photo_highlight_mask,
        photo_highlight_auto_roi_mask=lambda: photo_highlight_auto_roi_mask,
        photo_highlight_auto_compare=lambda: photo_highlight_auto_compare,
    ),
    LabelGenerationModels(
        auto_optimize_generate_image_with_retry=lambda: auto_optimize_generate_image_with_retry,
        AiProviderError=lambda: AiProviderError,
        auto_optimize_generate_label_for_candidate=lambda: auto_optimize_generate_label_for_candidate,
        verify_auto_optimize_mask_sample=lambda: verify_auto_optimize_mask_sample,
    ),
)


def auto_optimize_generate_labels_for_sample(sample: dict[str, Any], provider_settings: dict[str, Any], model: str, artifact_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    return _auto_optimization_label_generation.auto_optimize_generate_labels_for_sample(sample, provider_settings, model, artifact_dir)


def auto_optimize_generate_label_for_candidate(sample: dict[str, Any], candidate: dict[str, Any], provider_settings: dict[str, Any], model: str, artifact_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    return _auto_optimization_label_generation.auto_optimize_generate_label_for_candidate(sample, candidate, provider_settings, model, artifact_dir)


from .training.auto_optimization_label_processing import AutoOptimizationLabelProcessing
from .training.auto_optimization_label_processing_ports import ProcessingState, ProcessingArtifacts, ProcessingExecution

_auto_optimization_label_processing = AutoOptimizationLabelProcessing(
    state=ProcessingState(
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        _auto_optimize_lock=lambda: _auto_optimize_lock,
        _auto_optimize_label_threads=lambda: _auto_optimize_label_threads,
        auto_optimize_label_worker=lambda: auto_optimize_label_worker,
        load_auto_optimize_state=lambda: load_auto_optimize_state,
        save_auto_optimize_state=lambda: save_auto_optimize_state,
        auto_optimize_completed_model_id=lambda: auto_optimize_completed_model_id,
        auto_optimize_stop_capture_for_model_locked=lambda: auto_optimize_stop_capture_for_model_locked,
        default_auto_optimize_settings=_auto_optimization_settings.default_auto_optimize_settings,
        maybe_start_auto_optimize_training_locked=lambda: maybe_start_auto_optimize_training_locked,
    ),
    artifacts=ProcessingArtifacts(
        output_write_dir_for_owner=lambda: output_write_dir_for_owner,
        safe_record_id=lambda: safe_record_id,
        auto_optimize_generate_labels_for_sample=lambda: auto_optimize_generate_labels_for_sample,
        bounded_text=lambda: bounded_text,
        auto_optimize_generate_synthetic_batch_for_sample=lambda: auto_optimize_generate_synthetic_batch_for_sample,
    ),
    execution=ProcessingExecution(
        image_generation_settings=lambda: image_generation_settings,
        AUTO_OPTIMIZE_MASK_MAX_PARALLEL=lambda: AUTO_OPTIMIZE_MASK_MAX_PARALLEL,
        ThreadPoolExecutor=lambda: ThreadPoolExecutor,
        as_completed=lambda: as_completed,
        auto_optimize_process_label_sample=lambda: auto_optimize_process_label_sample,
    ),
    runtime=TrainingThreadLifecycle(scope=_runtime_repositories.thread_scope),
    model_resolver=resolve_model_profiles,
)


def start_auto_optimize_label_worker(task_id: str) -> None:
    return _auto_optimization_label_processing.start_auto_optimize_label_worker(task_id)


def auto_optimize_process_label_sample(
    task_id: str,
    pending: dict[str, Any],
    provider_settings: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    return _auto_optimization_label_processing.auto_optimize_process_label_sample(task_id, pending, provider_settings, model)


@pinned_model_profiles(resolve_model_profiles, lambda identity: load_auto_optimize_state(identity))
def auto_optimize_label_worker(task_id: str) -> None:
    return _auto_optimization_label_processing.auto_optimize_label_worker(task_id)


from .training.auto_optimization_training_scheduling import AutoOptimizationTrainingScheduling
from .training.auto_optimization_training_scheduling_ports import SchedulingPolicy, SchedulingSubmission, SchedulingState

_auto_optimization_training_scheduling = AutoOptimizationTrainingScheduling(
    policy=SchedulingPolicy(
        auto_optimize_completed_model_id=lambda: auto_optimize_completed_model_id,
        auto_optimize_stop_capture_for_model_locked=lambda: auto_optimize_stop_capture_for_model_locked,
        default_auto_optimize_settings=_auto_optimization_settings.default_auto_optimize_settings,
        auto_optimize_training_requirements=_auto_optimization_settings.auto_optimize_training_requirements,
        auto_optimize_samples_per_real_image=_auto_optimization_settings.auto_optimize_samples_per_real_image,
        auto_optimize_positive_derivatives_per_real_image=_auto_optimization_settings.auto_optimize_positive_derivatives_per_real_image,
        auto_optimize_negative_samples_per_real_image=_auto_optimization_settings.auto_optimize_negative_samples_per_real_image,
        AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT=lambda: AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT,
        auto_optimize_training_parameters=_auto_optimization_settings.auto_optimize_training_parameters,
    ),
    submission=SchedulingSubmission(
        build_auto_optimize_dataset=lambda: build_auto_optimize_dataset,
        LEGACY_OWNER_ID=lambda: LEGACY_OWNER_ID,
        _request_user=lambda: _request_user,
        scope_config_for_user=lambda: scope_config_for_user,
        load_config=lambda: load_config,
        selected_accessories=lambda: selected_accessories,
        TrainingStartRequest=lambda: TrainingStartRequest,
        pipeline_ai_task_id=lambda: pipeline_ai_task_id,
        enqueue_training_task=lambda: enqueue_training_task,
    ),
    state=SchedulingState(
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        _auto_optimize_lock=lambda: _auto_optimize_lock,
        load_auto_optimize_state=lambda: load_auto_optimize_state,
        save_auto_optimize_state=lambda: save_auto_optimize_state,
        maybe_start_auto_optimize_training_locked=lambda: maybe_start_auto_optimize_training_locked,
        bounded_text=lambda: bounded_text,
        auto_optimize_training_check_worker=lambda: auto_optimize_training_check_worker,
    ),
    runtime=TrainingThreadLifecycle(scope=_runtime_repositories.thread_scope),
)


def maybe_start_auto_optimize_training_locked(state: dict[str, Any]) -> None:
    return _auto_optimization_training_scheduling.maybe_start_auto_optimize_training_locked(state)


@pinned_model_profiles(resolve_model_profiles, lambda identity: load_auto_optimize_state(identity))
def auto_optimize_training_check_worker(task_id: str, delay_seconds: float = 0.0) -> None:
    return _auto_optimization_training_scheduling.auto_optimize_training_check_worker(task_id, delay_seconds)


def start_auto_optimize_training_check_worker(task_id: str, delay_seconds: float = 0.0) -> None:
    return _auto_optimization_training_scheduling.start_auto_optimize_training_check_worker(task_id, delay_seconds)


from .training.auto_optimization_sprites import AutoOptimizationSprites
from .training.auto_optimization_sprites_ports import SpriteFiles, SpriteGeometry

_auto_optimization_sprites = AutoOptimizationSprites(
    SpriteFiles(
        resolve_service_path=lambda: resolve_service_path,
        _image_files=lambda: _image_files,
        OUTPUT_DIR=lambda: OUTPUT_DIR,
        STATIC_DIR=lambda: STATIC_DIR,
        output_write_dir_for_owner=lambda: output_write_dir_for_owner,
        safe_record_id=lambda: safe_record_id,
        auto_optimize_write_sprite_artifact=lambda: auto_optimize_write_sprite_artifact,
        public_path_sanitized=lambda: public_path_sanitized,
        auto_optimize_resolve_artifact_path=lambda: auto_optimize_resolve_artifact_path,
    ),
    SpriteGeometry(
        alpha_bbox=lambda: alpha_bbox,
        AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE=lambda: AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE,
        AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE=lambda: AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE,
        auto_optimize_sprite_records_for_sample=lambda: auto_optimize_sprite_records_for_sample,
        auto_optimize_load_sprite=lambda: auto_optimize_load_sprite,
        auto_optimize_sprite_visible_size=lambda: auto_optimize_sprite_visible_size,
        auto_optimize_source_to_canvas_scale=lambda: auto_optimize_source_to_canvas_scale,
    ),
)


def auto_optimize_load_sprite(sprite: dict[str, Any]) -> tuple[np.ndarray, np.ndarray] | None:
    return _auto_optimization_sprites.auto_optimize_load_sprite(sprite)


def auto_optimize_sprite_records_for_sample(sample: dict[str, Any]) -> list[dict[str, Any]]:
    return _auto_optimization_sprites.auto_optimize_sprite_records_for_sample(sample)


def auto_optimize_resolve_artifact_path(value: Any) -> Path:
    return _auto_optimization_sprites.auto_optimize_resolve_artifact_path(value)


def auto_optimize_backfill_missing_sprites_for_sample(task_id: str, state: dict[str, Any], sample: dict[str, Any]) -> int:
    return _auto_optimization_sprites.auto_optimize_backfill_missing_sprites_for_sample(task_id, state, sample)


def auto_optimize_public_sprite_pool(state: dict[str, Any], limit: int = 80) -> list[dict[str, Any]]:
    return _auto_optimization_sprites.auto_optimize_public_sprite_pool(state, limit)


AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY = "canonical_real_mask_bbox_canvas_scale_v3"
AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE = (1280, 900)
AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE = max(1.0, float(os.environ.get("VANTALINE_AUTO_OPT_SYNTHETIC_MAX_UPSCALE", "3.0")))


def auto_optimize_sprite_visible_size(sprite_mask: np.ndarray) -> tuple[int, int] | None:
    return _auto_optimization_sprites.auto_optimize_sprite_visible_size(sprite_mask)


def auto_optimize_source_to_canvas_scale(source_path_value: Any, cache: dict[str, float]) -> float:
    return _auto_optimization_sprites.auto_optimize_source_to_canvas_scale(source_path_value, cache)


def auto_optimize_canonical_sprite_sizes(state: dict[str, Any], extra_sprites: list[dict[str, Any]] | None = None) -> dict[str, dict[str, int]]:
    return _auto_optimization_sprites.auto_optimize_canonical_sprite_sizes(state, extra_sprites)


def auto_optimize_sprite_target_size(
    sprite_mask: np.ndarray,
    canonical_size: dict[str, int] | None = None,
) -> tuple[int, int]:
    return _auto_optimization_sprites.auto_optimize_sprite_target_size(sprite_mask, canonical_size)


from .training.auto_optimization_rendering import AutoOptimizationRendering
from .training.auto_optimization_rendering_ports import SyntheticGeometry, SyntheticPublication

_auto_optimization_rendering = AutoOptimizationRendering(
    geometry=SyntheticGeometry(
        auto_optimize_load_sprite=lambda: auto_optimize_load_sprite,
        auto_optimize_sprite_target_size=lambda: auto_optimize_sprite_target_size,
        choose_object_center_inside_background=lambda: choose_object_center_inside_background,
        paste_masked_asset=lambda: paste_masked_asset,
        alpha_bbox=lambda: alpha_bbox,
        rotated_rect_tuple=lambda: rotated_rect_tuple,
        AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY=lambda: AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY,
    ),
    publication=SyntheticPublication(
        safe_background_set_id=lambda: safe_background_set_id,
        render_training_background=lambda: render_training_background,
        _image_files=lambda: _image_files,
        yolo_detection_label_line=lambda: yolo_detection_label_line,
        _business_files=lambda: _business_files,
        write_training_annotation_preview=lambda: write_training_annotation_preview,
        public_training_output_url=lambda: public_training_output_url,
    ),
)


def auto_optimize_render_synthetic_sample(
    *,
    sprites: list[dict[str, Any]],
    class_index: dict[str, int],
    accessories_by_id: dict[str, dict[str, Any]],
    output_path: Path,
    label_path: Path,
    annotated_path: Path,
    split: str,
    rng: np.random.Generator,
    canonical_sizes: dict[str, dict[str, int]] | None = None,
    background_set_id: str | None = None,
) -> dict[str, Any] | None:
    return _auto_optimization_rendering.auto_optimize_render_synthetic_sample(
        sprites=sprites,
        class_index=class_index,
        accessories_by_id=accessories_by_id,
        output_path=output_path,
        label_path=label_path,
        annotated_path=annotated_path,
        split=split,
        rng=rng,
        canonical_sizes=canonical_sizes,
        background_set_id=background_set_id,
    )


from .training.auto_optimization_synthetic_batch import AutoOptimizationSyntheticBatch
from .training.auto_optimization_synthetic_batch_ports import (
    SyntheticBatchConfiguration, SyntheticBatchSprites, SyntheticBatchPublication,
)

_auto_optimization_synthetic_batch = AutoOptimizationSyntheticBatch(
    configuration=SyntheticBatchConfiguration(
        safe_background_set_id=lambda: safe_background_set_id,
        default_auto_optimize_settings=_auto_optimization_settings.default_auto_optimize_settings,
        auto_optimize_positive_derivatives_per_real_image=_auto_optimization_settings.auto_optimize_positive_derivatives_per_real_image,
        AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY=lambda: AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY,
        _request_user=lambda: _request_user,
        LEGACY_OWNER_ID=lambda: LEGACY_OWNER_ID,
        scope_config_for_user=lambda: scope_config_for_user,
        load_config=lambda: load_config,
        accessory_lookup_by_id=lambda: accessory_lookup_by_id,
    ),
    sprites=SyntheticBatchSprites(
        auto_optimize_backfill_missing_sprites_for_sample=lambda: auto_optimize_backfill_missing_sprites_for_sample,
        auto_optimize_sprite_records_for_sample=lambda: auto_optimize_sprite_records_for_sample,
        auto_optimize_canonical_sprite_sizes=lambda: auto_optimize_canonical_sprite_sizes,
    ),
    publication=SyntheticBatchPublication(
        safe_record_id=lambda: safe_record_id,
        output_write_dir_for_owner=lambda: output_write_dir_for_owner,
        auto_optimize_render_synthetic_sample=lambda: auto_optimize_render_synthetic_sample,
    ),
)


def auto_optimize_generate_synthetic_batch_for_sample(
    task_id: str,
    state: dict[str, Any],
    sample: dict[str, Any],
) -> list[dict[str, Any]]:
    return _auto_optimization_synthetic_batch.auto_optimize_generate_synthetic_batch_for_sample(task_id, state, sample)


from .training.auto_optimization_dataset import AutoOptimizationDataset
from .training.auto_optimization_dataset_ports import (
    DatasetConfiguration, DatasetSources, DatasetPublication, DatasetLayout,
)

_auto_optimization_dataset = AutoOptimizationDataset(
    configuration=DatasetConfiguration(
        _request_user=lambda: _request_user,
        load_config=lambda: load_config,
        scope_config_for_user=lambda: scope_config_for_user,
        accessory_lookup_by_id=lambda: accessory_lookup_by_id,
        default_auto_optimize_settings=_auto_optimization_settings.default_auto_optimize_settings,
        auto_optimize_samples_per_real_image=_auto_optimization_settings.auto_optimize_samples_per_real_image,
        auto_optimize_positive_derivatives_per_real_image=_auto_optimization_settings.auto_optimize_positive_derivatives_per_real_image,
        auto_optimize_negative_samples_per_real_image=_auto_optimization_settings.auto_optimize_negative_samples_per_real_image,
        auto_optimize_training_requirements=_auto_optimization_settings.auto_optimize_training_requirements,
    ),
    sources=DatasetSources(
        auto_optimize_generate_synthetic_batch_for_sample=lambda: auto_optimize_generate_synthetic_batch_for_sample,
        auto_optimize_bbox_training_entries=lambda: auto_optimize_bbox_training_entries,
        AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT=lambda: AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT,
    ),
    publication=DatasetPublication(
        safe_record_id=lambda: safe_record_id,
        output_write_dir_for_owner=lambda: output_write_dir_for_owner,
        resolve_service_path=lambda: resolve_service_path,
        _image_files=lambda: _image_files,
        _business_files=lambda: _business_files,
    ),
    layout=DatasetLayout(
        safe_background_set_id=lambda: safe_background_set_id,
        split_counts=lambda: split_counts,
        render_training_background=lambda: render_training_background,
        yolo_detection_label_line=lambda: yolo_detection_label_line,
        write_training_annotation_preview=lambda: write_training_annotation_preview,
        public_training_output_url=lambda: public_training_output_url,
        write_dataset_yaml=lambda: write_dataset_yaml,
    ),
)


def auto_optimize_bbox_training_entries(sample: dict[str, Any]) -> list[dict[str, Any]]:
    return _auto_optimization_dataset.auto_optimize_bbox_training_entries(sample)


def build_auto_optimize_dataset(task_id: str, state: dict[str, Any], samples: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _auto_optimization_dataset.build_auto_optimize_dataset(task_id, state, samples)


from .training.auto_optimization_shadow_evaluation import AutoOptimizationShadowEvaluation
from .training.auto_optimization_shadow_evaluation_ports import ShadowState, ShadowObservation, ShadowPromotion

_auto_optimization_shadow_evaluation = AutoOptimizationShadowEvaluation(
    state=ShadowState(
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        _auto_optimize_lock=lambda: _auto_optimize_lock,
        _auto_optimize_shadow_threads=lambda: _auto_optimize_shadow_threads,
        auto_optimize_shadow_worker=lambda: auto_optimize_shadow_worker,
        load_auto_optimize_state=lambda: load_auto_optimize_state,
        save_auto_optimize_state=lambda: save_auto_optimize_state,
        bounded_text=lambda: bounded_text,
    ),
    observation=ShadowObservation(
        resolve_service_path=lambda: resolve_service_path,
        _image_files=lambda: _image_files,
        analyze_bgr=lambda: analyze_bgr,
        safe_record_id=lambda: safe_record_id,
    ),
    promotion=ShadowPromotion(
        maybe_promote_auto_optimize_model_locked=lambda: maybe_promote_auto_optimize_model_locked,
        default_auto_optimize_settings=_auto_optimization_settings.default_auto_optimize_settings,
        cleanup_auto_optimize_retired_candidate_locked=lambda: cleanup_auto_optimize_retired_candidate_locked,
        LEGACY_OWNER_ID=lambda: LEGACY_OWNER_ID,
        delete_training_task_record=lambda: delete_training_task_record,
        training_run_roots=lambda: training_run_roots,
        _business_files=lambda: _business_files,
    ),
    runtime=TrainingThreadLifecycle(scope=_runtime_repositories.thread_scope),
)


def start_auto_optimize_shadow_worker(task_id: str, sample_id: str) -> None:
    return _auto_optimization_shadow_evaluation.start_auto_optimize_shadow_worker(task_id, sample_id)


@pinned_model_profiles(resolve_model_profiles, lambda identity: load_auto_optimize_state(identity))
def auto_optimize_shadow_worker(task_id: str, sample_id: str) -> None:
    return _auto_optimization_shadow_evaluation.auto_optimize_shadow_worker(task_id, sample_id)


def maybe_promote_auto_optimize_model_locked(state: dict[str, Any]) -> None:
    return _auto_optimization_shadow_evaluation.maybe_promote_auto_optimize_model_locked(state)


def cleanup_auto_optimize_retired_candidate_locked(state: dict[str, Any], model_id: str, *, keep_model_id: str) -> None:
    return _auto_optimization_shadow_evaluation.cleanup_auto_optimize_retired_candidate_locked(state, model_id, keep_model_id=keep_model_id)


def ai_detection_settings(purpose: str = "pipeline") -> dict[str, Any]:
    return model_profile_service.resolve(purpose)


def image_generation_settings() -> dict[str, Any]:
    return model_profile_service.resolve("image")


def load_agent_config() -> dict[str, Any]:
    value = model_profile_service.resolve("training_assistant")
    return {**DEFAULT_AGENT_CONFIG, **value, "enabled": value.get("configured", False)}


from local_inspection_service.model_providers.legacy_settings_ports import LegacySettingsIO, LegacyPresentation, LegacyJsonPolicy, LegacyJsonCallbacks, LegacyImagePolicy, LegacyImageEnvironment, LegacyImageCallbacks
from local_inspection_service.model_providers.legacy_json_settings import LegacyJsonSettings
from local_inspection_service.model_providers.legacy_image_settings import LegacyImageSettings
_legacy_json_settings_service = LegacyJsonSettings(
    LegacySettingsIO(lambda: load_ai_local_config, lambda: os.environ, lambda: ai_proxy_url_from_config, lambda: validate_ai_base_url, lambda: HTTPException),
    LegacyPresentation(lambda: public_ai_key_items, lambda: mask_secret, lambda: public_ai_base_url, lambda: masked_url_for_status),
    LegacyJsonPolicy(lambda: AI_DEFAULT_PROVIDER, lambda: AI_DEFAULT_MODEL, lambda: AI_DEFAULT_TIMEOUT_SECONDS, lambda: AI_MODEL_OPTIONS, lambda: AI_SUPPORTED_PROVIDERS, lambda: AI_AUTO_LOCAL_PROXY_ENV),
    LegacyJsonCallbacks(lambda: default_ai_base_url, lambda: validate_ai_timeout, lambda: normalize_ai_key_items, lambda: ai_keys_for_provider, lambda: secret_key_item_id, lambda: bounded_text, lambda: ai_provider_label, lambda: env_flag_enabled),
)
_legacy_image_settings_service = LegacyImageSettings(
    LegacySettingsIO(lambda: load_ai_local_config, lambda: os.environ, lambda: ai_proxy_url_from_config, lambda: validate_ai_base_url, lambda: HTTPException),
    LegacyPresentation(lambda: public_ai_key_items, lambda: mask_secret, lambda: public_ai_base_url, lambda: masked_url_for_status),
    LegacyImagePolicy(lambda: IMAGE_GENERATION_DEFAULT_PROVIDER, lambda: IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS, lambda: IMAGE_GENERATION_MODEL_OPTIONS, lambda: IMAGE_GENERATION_SUPPORTED_PROVIDERS),
    LegacyImageEnvironment(lambda: IMAGE_GENERATION_PROVIDER_ENV, lambda: IMAGE_GENERATION_MODEL_ENV, lambda: IMAGE_GENERATION_BASE_URL_ENV, lambda: IMAGE_GENERATION_TIMEOUT_ENV, lambda: IMAGE_GENERATION_NAMED_API_KEY_ENV, lambda: IMAGE_GENERATION_API_KEY_ENV, lambda: AGENT_MCP_GEMINI_IMAGE_MODEL_ENV, lambda: AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV),
    LegacyImageCallbacks(lambda: default_image_generation_model, lambda: default_image_generation_base_url, lambda: default_image_generation_api_key_env, lambda: validate_image_generation_timeout, lambda: normalize_image_key_items, lambda: image_keys_for_provider, lambda: image_generation_provider_label, lambda: image_generation_provider_key),
)

def _legacy_ai_detection_settings() -> dict[str, Any]:
    return _legacy_json_settings_service._legacy_ai_detection_settings()


from local_inspection_service.auth.status_ports import StatusPolicy, StatusSources, StatusProjectionCalls
from local_inspection_service.auth.status import PublicStatusProjection
_public_status_projection = PublicStatusProjection(
    StatusPolicy(lambda: user_is_admin, lambda: user_has_permission, lambda: STATUS_MODEL_PUBLIC_KEYS, lambda: public_path_sanitized),
    StatusSources(lambda: ai_detection_settings, lambda: image_generation_settings),
    StatusProjectionCalls(lambda: public_ai_detection_status, lambda: public_image_generation_status, lambda: public_status_model_for_user, lambda: public_ai_detection_status_for_user),
)

def public_ai_detection_status() -> dict[str, Any]:
    return _public_status_projection.public_ai_detection_status()


def public_ai_detection_status_for_user(user: dict[str, Any] | None) -> dict[str, Any]:
    return _public_status_projection.public_ai_detection_status_for_user(user)


STATUS_MODEL_PUBLIC_KEYS = {
    "id",
    "label",
    "description",
    "variant",
    "uses_ocr",
    "is_legacy",
    "is_ai_detection",
    "is_label_sheet_match",
    "exists",
    "run_id",
    "task_id",
    "task_label",
    "task_source",
    "confidence_threshold",
    "required_accessory_counts",
    "accessory_labels",
    "accessory_class_map",
    "ocr_accessory_ids",
    "accessory_names",
    "selected_accessory_ids",
    "missing_accessory_ids",
    "created_at",
    "updated_at",
    "owner_user_id",
    "owner_username",
}


def public_status_model_for_user(model: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
    return _public_status_projection.public_status_model_for_user(model, user)


def public_service_status_for_user(user: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    return _public_status_projection.public_service_status_for_user(user, payload)


def public_config_summary_for_user(user: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    return _public_status_projection.public_config_summary_for_user(user, config)


def _legacy_image_generation_settings() -> dict[str, Any]:
    return _legacy_image_settings_service._legacy_image_generation_settings()


def public_image_generation_status() -> dict[str, Any]:
    return _public_status_projection.public_image_generation_status()


from .model_providers.errors import (
    AiProviderError,
    AiProviderNonRetryableError,
    AiProviderConfigError,
    AiProviderAuthError,
    AiProviderTimeout,
    AiProviderOverloaded,
)
from .model_providers.payloads import (
    ProviderPayloadParser,
    normalize_ai_json_root as _normalize_ai_json_root,
    ai_json_text_candidates as _ai_json_text_candidates,
)
from .model_providers.http_errors import (
    ProviderHttpErrors,
    ProviderErrorTypes,
)
_provider_payloads = ProviderPayloadParser(
    lambda: ai_json_text_candidates,
    lambda: normalize_ai_json_root,
    lambda: AiProviderError,
)
_provider_http_errors = ProviderHttpErrors(
    lambda: bounded_text,
    ProviderErrorTypes(
        lambda: AiProviderError,
        lambda: AiProviderAuthError,
        lambda: AiProviderOverloaded,
        lambda: AiProviderConfigError,
        lambda: AiProviderNonRetryableError,
    ),
)


def provider_http_error(message_prefix: str, exc: urllib.error.HTTPError) -> AiProviderError:
    return _provider_http_errors.provider_http_error(message_prefix, exc)


def normalize_ai_json_root(parsed: Any) -> dict[str, Any] | None:
    return _normalize_ai_json_root(parsed)


def ai_json_text_candidates(text: str) -> list[str]:
    return _ai_json_text_candidates(text)


def parse_ai_json_object(text: str) -> dict[str, Any]:
    return _provider_payloads.parse_ai_json_object(text)


from .model_profiles.audit import metered as metered_model_call


from .model_providers.openai_transport import (
    OpenAICompatibleAiProvider as _OpenAICompatibleAiProvider,
)
from .model_providers.openai_ports import OpenAITransportIO, OpenAITransportErrors

_openai_transport_io = OpenAITransportIO(
    lambda: ai_urlopen,
    lambda: parse_ai_json_object,
    lambda: bounded_text,
    lambda: sha256_bytes,
    lambda: provider_http_error,
)
_openai_transport_errors = OpenAITransportErrors(
    lambda: AiProviderConfigError,
    lambda: AiProviderTimeout,
    lambda: AiProviderError,
)
# Preserve the existing decorator's composition-time resolver selection.
_openai_profile_resolver = resolve_model_profiles

class OpenAICompatibleAiProvider(_OpenAICompatibleAiProvider):
    def __init__(self, settings: dict[str, Any]):
        super().__init__(
            settings, _openai_transport_io, _openai_transport_errors, _openai_profile_resolver,
        )


def data_url_payload(data_url: str) -> tuple[str, str]:
    return _provider_payloads.data_url_payload(data_url)


from .model_providers.gemini_transport import (
    GeminiAiProvider as _GeminiAiProvider,
)
from .model_providers.gemini_ports import GeminiTransportIO, GeminiTransportErrors

_gemini_transport_io = GeminiTransportIO(
    lambda: ai_urlopen,
    lambda: parse_ai_json_object,
    lambda: bounded_text,
    lambda: data_url_payload,
    lambda: decode_b64_image,
    lambda: masked_url_for_status,
    lambda: quote,
    lambda: provider_http_error,
)
_gemini_transport_errors = GeminiTransportErrors(
    lambda: AiProviderConfigError,
    lambda: AiProviderTimeout,
    lambda: AiProviderError,
    lambda: AiProviderAuthError,
    lambda: AiProviderOverloaded,
)
_gemini_profile_resolver = resolve_model_profiles

class GeminiAiProvider(_GeminiAiProvider):
    def __init__(self, settings: dict[str, Any]):
        super().__init__(
            settings, _gemini_transport_io, _gemini_transport_errors, _gemini_profile_resolver,
        )

    def create_cached_content(
        self,
        system_prompt: str,
        user_content: list[dict[str, Any]],
        *,
        display_name: str,
        ttl_seconds: int = AI_PROFILE_CACHE_TTL_SECONDS,
    ) -> dict[str, Any]:
        return super().create_cached_content(
            system_prompt, user_content, display_name=display_name, ttl_seconds=ttl_seconds,
        )


from .model_providers.image_ports import ImageTransportIO, ImageTransportErrors
from .model_providers.agnes_transport import AgnesImageProvider as _AgnesImageProvider
from .model_providers.qwen_image_transport import QwenImageProvider as _QwenImageProvider

_image_transport_io = ImageTransportIO(
    lambda: ai_urlopen,
    lambda: bounded_text,
    lambda: decode_b64_image,
    lambda: masked_url_for_status,
    lambda: requests.get,
)
_image_transport_errors = ImageTransportErrors(
    lambda: AiProviderConfigError,
    lambda: AiProviderTimeout,
    lambda: AiProviderError,
    lambda: AiProviderAuthError,
    lambda: AiProviderOverloaded,
    lambda: requests.RequestException,
)
_agnes_profile_resolver = resolve_model_profiles

class AgnesImageProvider(_AgnesImageProvider):
    def __init__(self, settings: dict[str, Any]):
        super().__init__(
            settings, _image_transport_io, _image_transport_errors, _agnes_profile_resolver,
            lambda: os.environ.get("VANTALINE_AGNES_IMAGE_SIZE", "1024x1024"),
            lambda: cursor_image2_response_candidates,
        )

_qwen_image_profile_resolver = resolve_model_profiles

class QwenImageProvider(_QwenImageProvider):
    def __init__(self, settings: dict[str, Any]):
        super().__init__(
            settings, _image_transport_io, _image_transport_errors, _qwen_image_profile_resolver,
            lambda: os.environ.get("VANTALINE_QWEN_IMAGE_SIZE", "1024*1024"),
        )


from .model_providers.orchestration_ports import (
    ProviderFactories, ProviderKeys, RetryErrors, ImageDelay, FailureEvidence,
    JsonProviderSelection, JsonRetryEvidence, JsonRetryTiming, ImageRetryCalls, ImageRetryTiming,
)
from .model_providers.selection import ProviderSelection, ProviderKeySelection
from .model_providers.retry_policy import ProviderRetryPolicy, ProviderFailureEvidence
from .model_providers.retry_flow import JsonRetryFlow, ImageRetryFlow

_provider_selection = ProviderSelection(ProviderFactories(
    lambda: GeminiAiProvider, lambda: OpenAICompatibleAiProvider,
    lambda: AgnesImageProvider, lambda: QwenImageProvider, lambda: AiProviderConfigError,
    lambda: ai_detection_settings, lambda: ai_provider_from_settings,
))
_provider_keys = ProviderKeySelection(ProviderKeys(
    lambda: secret_key_item_id, lambda: bounded_text, lambda: ai_provider_key_candidates,
))
_provider_retry_errors = RetryErrors(
    lambda: AiProviderError, lambda: AiProviderNonRetryableError,
    lambda: AiProviderOverloaded, lambda: AiProviderTimeout,
)
_provider_retry_policy = ProviderRetryPolicy(_provider_retry_errors, ImageDelay(
    lambda: AUTO_OPTIMIZE_MASK_MAX_ATTEMPTS, lambda: AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS,
    lambda: AUTO_OPTIMIZE_MASK_RETRY_MAX_SECONDS, lambda: random.uniform,
))
_provider_failure_evidence = ProviderFailureEvidence(FailureEvidence(lambda: AiProviderError, lambda: GeminiAiProvider))
_provider_json_retry = JsonRetryFlow(
    JsonProviderSelection(lambda: ai_settings_match_runtime, lambda: ai_provider,
                          lambda: ai_provider_from_settings, lambda: GeminiAiProvider,
                          lambda: rotate_ai_provider_key),
    JsonRetryEvidence(lambda: require_ai_json_object, lambda: provider_failure_usage_metadata,
                      lambda: provider_error_is_retryable, lambda: provider_error_needs_repair_prompt,
                      lambda: annotate_provider_failure, lambda: bounded_text),
    _provider_retry_errors,
    JsonRetryTiming(lambda: AI_PROVIDER_MAX_ATTEMPTS, lambda: AI_PROVIDER_RETRY_BACKOFF_SECONDS,
                    lambda: random.uniform, lambda: time.sleep),
)
_provider_image_retry = ImageRetryFlow(
    ImageRetryCalls(lambda: image_generation_provider_from_settings,
                    lambda: _auto_optimize_image_request_semaphore, lambda: image_provider_error_is_retryable,
                    lambda: bounded_text, lambda: auto_optimize_retry_delay_seconds),
    _provider_retry_errors,
    ImageRetryTiming(lambda: AUTO_OPTIMIZE_MASK_MAX_ATTEMPTS, lambda: time.time, lambda: time.sleep),
)


def ai_provider_from_settings(settings: dict[str, Any]) -> OpenAICompatibleAiProvider | GeminiAiProvider:
    return _provider_selection.ai_provider_from_settings(settings)


def ai_provider() -> OpenAICompatibleAiProvider | GeminiAiProvider:
    return _provider_selection.ai_provider()


def image_generation_provider_from_settings(settings: dict[str, Any]) -> GeminiAiProvider | AgnesImageProvider | QwenImageProvider:
    return _provider_selection.image_generation_provider_from_settings(settings)


def ai_settings_match_runtime(settings: dict[str, Any]) -> bool:
    return _provider_selection.ai_settings_match_runtime(settings)


def ai_provider_key_candidates(settings: dict[str, Any]) -> list[dict[str, str]]:
    return _provider_keys.ai_provider_key_candidates(settings)


def rotate_ai_provider_key(settings: dict[str, Any], used_key_ids: set[str]) -> dict[str, Any] | None:
    return _provider_keys.rotate_ai_provider_key(settings, used_key_ids)


def require_ai_json_object(parsed: Any) -> dict[str, Any]:
    return _provider_failure_evidence.require_ai_json_object(parsed)


def provider_error_is_retryable(exc: AiProviderError) -> bool:
    return _provider_retry_policy.provider_error_is_retryable(exc)


def image_provider_error_is_retryable(exc: AiProviderError) -> bool:
    return _provider_retry_policy.image_provider_error_is_retryable(exc)


def auto_optimize_retry_delay_seconds(attempt: int, exc: AiProviderError | None=None) -> float:
    return _provider_retry_policy.auto_optimize_retry_delay_seconds(attempt, exc)


def auto_optimize_generate_image_with_retry(settings: dict[str, Any], model: str, prompt: str, user_content: list[dict[str, Any]], *, system_prompt: str='') -> dict[str, Any]:
    return _provider_image_retry.auto_optimize_generate_image_with_retry(settings, model, prompt, user_content, system_prompt=system_prompt)


def provider_error_needs_repair_prompt(exc: AiProviderError) -> bool:
    return _provider_failure_evidence.provider_error_needs_repair_prompt(exc)


def provider_failure_usage_metadata(provider: OpenAICompatibleAiProvider | GeminiAiProvider | None, exc: AiProviderError) -> dict[str, Any]:
    return _provider_failure_evidence.provider_failure_usage_metadata(provider, exc)


def annotate_provider_failure(exc: AiProviderError, *, attempt: int, errors: list[str], failed_usage_metadata: list[dict[str, Any]], usage_metadata: dict[str, Any] | None=None, fallback_model: str='', fallback_reason: str='') -> AiProviderError:
    return _provider_failure_evidence.annotate_provider_failure(exc, attempt=attempt, errors=errors, failed_usage_metadata=failed_usage_metadata, usage_metadata=usage_metadata, fallback_model=fallback_model, fallback_reason=fallback_reason)


def generate_provider_json_with_fallback(settings: dict[str, Any], system_prompt: str, user_content: list[dict[str, Any]], *, max_tokens: int, cached_content: str='', max_attempts: int | None=None, overloaded_retry_delay_seconds: float | None=None, allow_overloaded_model_fallback: bool=True) -> tuple[dict[str, Any], int, dict[str, Any]]:
    return _provider_json_retry.generate_provider_json_with_fallback(settings, system_prompt, user_content, max_tokens=max_tokens, cached_content=cached_content, max_attempts=max_attempts, overloaded_retry_delay_seconds=overloaded_retry_delay_seconds, allow_overloaded_model_fallback=allow_overloaded_model_fallback)


def generate_ai_detection_json(settings: dict[str, Any], user_content: list[dict[str, Any]], *, max_tokens: int) -> tuple[dict[str, Any], int, dict[str, Any]]:
    return generate_provider_json_with_fallback(settings, AI_DETECTION_SYSTEM_PROMPT, user_content, max_tokens=max_tokens)


from .detection.media_ports import InspectionImagePolicy, ReferenceCollectionPolicy, ReferenceSheetPolicy, ReferenceSheetCache, ReferenceSheetImages
from .detection.image_encoding import ImageEncoding
from .detection.inspection_image_store import InspectionImageStore
from .detection.reference_images import ReferenceCollection, ReferenceTileRenderer
from .detection.reference_sheet import ReferenceSheet
_image_encoding = ImageEncoding(
    lambda: cv2,
    lambda message: AiProviderError(message),
    lambda image, max_side=1280, quality=82: image_bgr_data_url(image, max_side=max_side, quality=quality),
    runtime_provider=lambda: _business_files.runtime_provider(),
)
_inspection_image_store = InspectionImageStore(
    lambda: cv2,
    InspectionImagePolicy(
        lambda: AI_MCP_INSPECTION_IMAGE_DIR,
        lambda: AI_INSPECTION_IMAGE_MAX_SIDE,
        lambda: AI_INSPECTION_IMAGE_QUALITY,
    ),
    lambda: time.time_ns(),
    lambda name: safe_name(name),
    runtime_provider=lambda: _business_files.runtime_provider(),
)
_reference_collection = ReferenceCollection(
    lambda: bounded_text,
    lambda item: accessory_uid(item),
    lambda item: accessory_image_paths(item),
    lambda path, max_side=1024, quality=78: image_path_data_url(path, max_side=max_side, quality=quality),
    lambda value: data_url_payload(value),
    ReferenceCollectionPolicy(
        lambda: AI_REFERENCE_IMAGES_PER_ACCESSORY,
        lambda: AI_REFERENCE_IMAGE_MAX_SIDE,
        lambda: AI_REFERENCE_IMAGE_QUALITY,
    ),
)
_reference_tile_renderer = ReferenceTileRenderer(lambda: cv2, lambda: np)
_reference_sheet = ReferenceSheet(
    lambda: bounded_text,
    lambda name: output_write_dir(name),
    ReferenceSheetPolicy(
        lambda: IMAGE_REFERENCE_SUFFIXES,
        lambda: AI_PROFILE_REFERENCE_MODE,
        lambda: AI_PROFILE_REFERENCE_SHEET_QUALITY,
        lambda: AI_PROFILE_REFERENCE_SHEET_MAX_SIDE,
    ),
    ReferenceSheetCache(
        lambda: _REFERENCE_SHEET_DESCRIPTOR_CACHE_LOCK,
        lambda: _REFERENCE_SHEET_DESCRIPTOR_CACHE,
    ),
    ReferenceSheetImages(
        lambda: cv2,
        lambda: np,
        lambda image, width, height: fit_image_into_cell(image, width, height),
        lambda: image_path_data_url,
    ),
    files=lambda: _business_files,
)


def image_bgr_data_url(image_bgr: np.ndarray, max_side: int=1280, quality: int=82) -> str:
    return _image_encoding.image_bgr_data_url(image_bgr, max_side=max_side, quality=quality)


def write_mcp_inspection_image(image_bgr: np.ndarray, request_id: str) -> Path | None:
    return _inspection_image_store.write_mcp_inspection_image(image_bgr, request_id)


def image_path_data_url(path: Path, max_side: int=1024, quality: int=78) -> str | None:
    return _image_encoding.image_path_data_url(path, max_side=max_side, quality=quality)


from .accessories.profile_payloads import AccessoryProfilePayloads as _AccessoryProfilePayloads
from .accessories.profile_payload_ports import PayloadIdentity as _PayloadIdentity, PayloadProfiles as _PayloadProfiles, PayloadCatalog as _PayloadCatalog
_accessory_profile_payloads = _AccessoryProfilePayloads(
    _PayloadIdentity(uid=lambda: accessory_uid, material=lambda: accessory_material_type),
    _PayloadProfiles(fallback=lambda: fallback_accessory_ai_profile, normalize=lambda: normalize_accessory_ai_profile, required=lambda: required_accessory_profile_payload, reference=lambda: size_reference_payload),
    _PayloadCatalog(config=lambda: load_config, text=lambda: bounded_text),
)

def accessory_profile_prompt_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_profile_payloads.accessory_profile_prompt_payload(item)


def ai_tool_provider_meta(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": settings.get("provider") or "",
        "provider_model": settings.get("model") or "",
        "provider_status": settings.get("status") or "",
    }


def profile_generation_status(settings: dict[str, Any], *, source: str = "fallback") -> dict[str, Any]:
    return {
        "source": source,
        "provider": settings.get("provider") or "",
        "provider_model": settings.get("model") or "",
        "status": settings.get("status") or "unknown",
        "message": settings.get("message") or "",
        "updated_at": int(time.time()),
    }


def required_accessory_profile_payload(item: dict[str, Any], expected_count: int, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    return _accessory_profile_payloads.required_accessory_profile_payload(item, expected_count, profile)


def resolve_required_accessory_refs(required_refs: list[Any]) -> list[dict[str, Any]]:
    return _accessory_profile_payloads.resolve_required_accessory_refs(required_refs)


from .model_providers.tool_dispatch import ModelToolDispatch
from .model_providers.tool_dispatch_ports import ToolErrorPolicy, JsonToolExecution, McpToolTransport

_model_tool_dispatch = ModelToolDispatch(
    errors=ToolErrorPolicy(
        bounded_text=lambda: bounded_text,
        _text_v2_diagnostic_value=lambda: _text_v2_diagnostic_value,
        AiProviderError=lambda: AiProviderError,
        AiProviderTimeout=lambda: AiProviderTimeout,
        AiProviderOverloaded=lambda: AiProviderOverloaded,
        AI_DEFAULT_TIMEOUT_SECONDS=lambda: AI_DEFAULT_TIMEOUT_SECONDS,
    ),
    execution=JsonToolExecution(
        ai_detection_settings=lambda: ai_detection_settings,
        ai_tool_provider_meta=lambda: ai_tool_provider_meta,
        provider_generate_json_error_payload=lambda: provider_generate_json_error_payload,
        generate_provider_json_with_fallback=lambda: generate_provider_json_with_fallback,
    ),
    transport=McpToolTransport(
        admission=lambda: _ai_mcp_client.admission,
        ai_mcp_runtime=lambda: ai_mcp_runtime,
        AI_MCP_RUNTIME_STDIO=lambda: AI_MCP_RUNTIME_STDIO,
        AI_MCP_RUNTIME_IN_PROCESS=lambda: AI_MCP_RUNTIME_IN_PROCESS,
        _ai_mcp_client=lambda: _ai_mcp_client,
        prepare_ai_mcp_payload=lambda: prepare_ai_mcp_payload,
        AI_MCP_TOOL_HANDLERS=lambda: AI_MCP_TOOL_HANDLERS,
    ),
)


def provider_generate_json_error_payload(
    settings: dict[str, Any],
    meta: dict[str, Any],
    exc: BaseException | str,
    *,
    timed_out: bool = False,
    overloaded: bool = False,
    latency_ms: int = 0,
) -> dict[str, Any]:
    return _model_tool_dispatch.provider_generate_json_error_payload(settings, meta, exc, timed_out=timed_out, overloaded=overloaded, latency_ms=latency_ms)


def tool_provider_gemini_generate_json(payload: dict[str, Any]) -> dict[str, Any]:
    return _model_tool_dispatch.tool_provider_gemini_generate_json(payload)


def tool_accessory_reference_collect(payload: dict[str, Any]) -> dict[str, Any]:
    return _reference_collection.tool_accessory_reference_collect(payload)


from .detection.profile_cache_policy import ProfileCachePolicy
from .detection.profile_cache_store import ProfileCacheStore
from .detection.profile_cache import ProfileCacheFlow, CacheRecords, CacheEvidence, CacheProviders, CacheTiming

_profile_cache_policy = ProfileCachePolicy(
    lambda: string_list, lambda: AI_PROFILE_CACHE_VERSION, lambda: AI_PROFILE_REFERENCE_MODE,
    lambda: AI_DETECTION_SYSTEM_PROMPT, lambda required: ai_detection_task_payload(required),
    lambda required: build_reference_sheet_descriptor(required),
)
_profile_cache_store = ProfileCacheStore(lambda: DATA_DIR, lambda: AI_PROFILE_CACHE_PATH, lambda: os)
_profile_cache_flow = ProfileCacheFlow(
    CacheRecords(lambda: load_ai_profile_cache(), lambda cache: save_ai_profile_cache(cache)),
    CacheEvidence(lambda required, settings: required_accessory_cache_key(required, settings),
                  lambda required: profile_reference_descriptors(required),
                  lambda required, references: cached_profile_context_content(required, references)),
    CacheProviders(lambda settings: ai_provider_from_settings(settings), lambda: GeminiAiProvider, lambda: AiProviderError),
    CacheTiming(lambda: time.time(), lambda: AI_PROFILE_CACHE_TTL_SECONDS),
    lambda: AI_DETECTION_SYSTEM_PROMPT, lambda: bounded_text,
)


def load_ai_profile_cache() -> dict[str, Any]:
    return _profile_cache_store.load_ai_profile_cache()


def save_ai_profile_cache(cache: dict[str, Any]) -> None:
    return _profile_cache_store.save_ai_profile_cache(cache)


def required_accessory_cache_key(required_accessories: list[dict[str, Any]], settings: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    return _profile_cache_policy.required_accessory_cache_key(required_accessories, settings)


def fit_image_into_cell(image: np.ndarray, width: int, height: int) -> np.ndarray:
    return _reference_tile_renderer.fit_image_into_cell(image, width, height)


def build_reference_sheet_descriptor(required_accessories: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _reference_sheet.build_reference_sheet_descriptor(required_accessories)


def profile_reference_descriptors(required_accessories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _profile_cache_policy.profile_reference_descriptors(required_accessories)


def cached_profile_context_content(required_accessories: list[dict[str, Any]], references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _profile_cache_policy.cached_profile_context_content(required_accessories, references)


def ensure_required_profile_cache(required_accessories: list[dict[str, Any]], settings: dict[str, Any]) -> dict[str, Any]:
    return _profile_cache_flow.ensure_required_profile_cache(required_accessories, settings)


from .accessories.profile_generation import AccessoryProfileGeneration as _AccessoryProfileGeneration
from .accessories.profile_generation_ports import GenerationProfiles as _GenerationProfiles, GenerationCalls as _GenerationCalls, GenerationReferences as _GenerationReferences, GenerationUpdates as _GenerationUpdates
_accessory_profile_generation = _AccessoryProfileGeneration(
    _GenerationProfiles(fallback=lambda: fallback_accessory_ai_profile, normalize=lambda: normalize_accessory_ai_profile, prompt=lambda: accessory_profile_prompt_payload, generate=lambda: generate_accessory_ai_profile),
    _GenerationCalls(settings=lambda: ai_detection_settings, status=lambda: profile_generation_status, invoke=lambda: call_ai_mcp_tool),
    _GenerationReferences(contexts=lambda: accessory_reference_image_contexts, limit=lambda: AI_PROFILE_REFERENCE_IMAGES, max_side=lambda: AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE, quality=lambda: AI_PROFILE_REFERENCE_IMAGE_QUALITY),
    _GenerationUpdates(uid=lambda: accessory_uid, rename=lambda: ensure_accessory_english_name, dimensions=lambda: apply_ai_profile_dimensions_to_physical_size),
)

def tool_accessory_profile_generate(payload: dict[str, Any]) -> dict[str, Any]:
    return _accessory_profile_generation.tool_accessory_profile_generate(payload)


from .detection.presence_inspection import PresenceInspection
from .detection.presence_inspection_ports import PresenceInput, PresenceGeneration, PresenceOutput, PresencePolicy

_presence_inspection = PresenceInspection(
    PresenceInput(lambda: ai_detection_settings(), lambda: resolve_required_accessory_refs,
                  lambda: image_path_data_url, lambda: image_bgr_data_url),
    PresenceGeneration(lambda required: ai_detection_task_payload(required),
                       lambda required, settings: ensure_required_profile_cache(required, settings),
                       lambda: ai_detection_provider_output_token_budget, lambda: call_ai_mcp_tool,
                       lambda: ai_detection_parsed_covers_required),
    PresenceOutput(lambda: ai_presence_failure_payload, lambda: normalize_ai_detection_result),
    PresencePolicy(lambda: AI_INSPECTION_IMAGE_MAX_SIDE, lambda: AI_INSPECTION_IMAGE_QUALITY,
                   lambda: AI_PROVIDER_MAX_ATTEMPTS, lambda: AI_REFERENCE_IMAGES_PER_ACCESSORY,
                   lambda: AI_DETECTION_SYSTEM_PROMPT, lambda: AI_DETECTION_OUTPUT_SCHEMA),
    lambda: time.monotonic(),
)


def tool_vision_inspect_presence(payload: dict[str, Any]) -> dict[str, Any]:
    return _presence_inspection.tool_vision_inspect_presence(payload)


AI_MCP_TOOL_HANDLERS = {
    "accessory.profile.generate": tool_accessory_profile_generate,
    "accessory.reference.collect": tool_accessory_reference_collect,
    "vision.inspect.presence": tool_vision_inspect_presence,
    "provider.gemini.generate_json": tool_provider_gemini_generate_json,
}


from .model_providers.mcp_client import LocalAiMcpClient


_ai_mcp_client = LocalAiMcpClient(
    root=lambda: ROOT, error=lambda: AiProviderError, runtime=lambda: AI_MCP_RUNTIME_STDIO,
)


from .model_providers.mcp_runtime import ai_mcp_runtime, external_ai_mcp_enabled, McpPayloadPreparation, McpWarmup




_mcp_payload_preparation = McpPayloadPreparation(
    encoder=lambda: image_bgr_data_url,
    max_side=lambda: AI_INSPECTION_IMAGE_MAX_SIDE,
    quality=lambda: AI_INSPECTION_IMAGE_QUALITY,
)
prepare_ai_mcp_payload = _mcp_payload_preparation.prepare_ai_mcp_payload


def call_ai_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    # Extraction point for out-of-process MCP: default is an O(1) in-process tool dispatch.
    return _model_tool_dispatch.call_ai_mcp_tool(tool_name, payload)


_mcp_warmup = McpWarmup(
    enabled=external_ai_mcp_enabled, client=lambda: _ai_mcp_client,
    admission=lambda: _ai_mcp_client.admission(),
)
warm_ai_mcp_client = _mcp_warmup.warm_ai_mcp_client


@app.on_event("startup")
def start_ai_mcp_warmup() -> None:
    if external_ai_mcp_enabled():
        _ai_mcp_client.start_warmup(warm_ai_mcp_client, threads=threading.Thread)


def generate_accessory_ai_profile(item: dict[str, Any], *, allow_provider: bool = True) -> dict[str, Any]:
    return _accessory_profile_generation.generate_accessory_ai_profile(item, allow_provider=allow_provider)


def ensure_accessory_ai_profile(item: dict[str, Any], *, force: bool = False, allow_provider: bool = True) -> bool:
    return _accessory_profile_generation.ensure_accessory_ai_profile(item, force=force, allow_provider=allow_provider)










from .accessories.materialized_assets import clean_sprite_metadata_complete as _clean_sprite_metadata_complete_impl
from .accessories.materialized_assets import text_accessory_confirm_detail as _text_accessory_confirm_detail_impl
from .accessories.materialized_assets import SpriteAssetCatalog as _SpriteAssetCatalog
from .accessories.materialized_assets import TextAssetCatalog as _TextAssetCatalog
from .accessories.materialized_asset_ports import MaterializedAssetPaths as _MaterializedAssetPaths, SpriteCatalogPoseOperations as _SpriteCatalogPoseOperations, SpriteCatalogMaterialPolicy as _SpriteCatalogMaterialPolicy, SpriteCatalogReadiness as _SpriteCatalogReadiness, TextCatalogOperations as _TextCatalogOperations
_sprite_asset_catalog = _SpriteAssetCatalog(
    _MaterializedAssetPaths(resolve=lambda: resolve_service_path),
    _SpriteCatalogPoseOperations(top_view=lambda: pose_family_is_top_view, footprint=lambda: pose_render_footprint_metadata, upright=lambda: apply_upright_scale_correction_metadata, laying=lambda: apply_laying_standard_render_size_hints),
    _SpriteCatalogMaterialPolicy(expected=lambda: object_alpha_material_policy, normalize=lambda: normalize_object_alpha_material_policy),
    _SpriteCatalogReadiness(assets=lambda: clean_sprite_assets, metadata=lambda: clean_sprite_metadata_complete, material=lambda: clean_sprite_material_policy_matches), files=_business_files, images=_accessory_image_io
)
_text_asset_catalog = _TextAssetCatalog(
    _MaterializedAssetPaths(resolve=lambda: resolve_service_path),
    _TextCatalogOperations(suffixes=lambda: IMAGE_REFERENCE_SUFFIXES, assets=lambda: canonical_text_assets), files=_business_files, images=_accessory_image_io
)

def clean_sprite_assets(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _sprite_asset_catalog.clean_sprite_assets(item)


from .agent.pose_assets import AgentPoseAssets as _AgentPoseAssets
from .agent.pose_templates import AgentPoseTemplates as _AgentPoseTemplates
from .agent.pose_asset_ports import PoseAssetPaths as _PoseAssetPaths, PoseAssetMaterial as _PoseAssetMaterial, PoseAssetSprites as _PoseAssetSprites, PoseAssetCalls as _PoseAssetCalls, PoseAssetCatalog as _PoseAssetCatalog, PoseTemplateIdentity as _PoseTemplateIdentity, PoseTemplateCalls as _PoseTemplateCalls
_agent_pose_assets = _AgentPoseAssets(
    _PoseAssetPaths(resolve=lambda: resolve_service_path, suffixes=lambda: IMAGE_REFERENCE_SUFFIXES),
    _PoseAssetMaterial(kind=lambda: accessory_material_type, text_assets=lambda: canonical_text_assets, text_complete=lambda: canonical_text_assets_complete),
    _PoseAssetSprites(source_paths=lambda: object_photo_highlight_source_paths, highlight_ready=lambda: photo_highlight_clean_sprites_ready, assets=lambda: clean_sprite_assets, complete=lambda: clean_sprites_policy_complete, family=lambda: canonical_pose_family_name, version=lambda: AGENT_MCP_SPRITE_BUILD_VERSION),
    _PoseAssetCalls(references=lambda: agent_mcp_pose_reference_assets, rebuild=lambda: agent_mcp_clean_sprites_need_rebuild),
    _PoseAssetCatalog(uid=lambda: accessory_uid, lookup=lambda: accessory_lookup_by_id, canonical_ids=lambda: canonical_pipeline_accessory_ids, has_asset=lambda: agent_mcp_accessory_has_existing_or_pose_asset, pose_tool=lambda: AGENT_MCP_TOOL_POSE_IMAGE),
)
_agent_pose_templates = _AgentPoseTemplates(
    _PoseTemplateIdentity(uid=lambda: accessory_uid, kind=lambda: accessory_material_type, search=lambda: re.search),
    _PoseTemplateCalls(request=lambda: agent_mcp_pose_request),
)

def agent_mcp_pose_reference_assets(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _agent_pose_assets.agent_mcp_pose_reference_assets(item)


def agent_mcp_accessory_pose_images_exist(item: dict[str, Any]) -> bool:
    return _agent_pose_assets.agent_mcp_accessory_pose_images_exist(item)


def dedup_agent_mcp_pose_references(item: dict[str, Any]) -> bool:
    return _pose_sprite_builder.dedup_agent_mcp_pose_references(item)


def agent_mcp_accessory_standard_images_ready(item: dict[str, Any]) -> bool:
    return _agent_pose_assets.agent_mcp_accessory_standard_images_ready(item)


def agent_mcp_clean_sprites_need_rebuild(item: dict[str, Any]) -> bool:
    return _agent_pose_assets.agent_mcp_clean_sprites_need_rebuild(item)


def clean_sprite_metadata_complete(asset: dict[str, Any]) -> bool:
    return _clean_sprite_metadata_complete_impl(asset)


def clean_sprite_material_policy_matches(item: dict[str, Any], asset: dict[str, Any]) -> bool:
    return _sprite_asset_catalog.clean_sprite_material_policy_matches(item, asset)


def clean_sprites_policy_complete(item: dict[str, Any], assets: list[dict[str, Any]] | None = None) -> bool:
    return _sprite_asset_catalog.clean_sprites_policy_complete(item, assets)


def canonical_text_assets(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _text_asset_catalog.canonical_text_assets(item)


def canonical_text_assets_complete(item: dict[str, Any], assets: list[dict[str, Any]] | None = None) -> bool:
    return _text_asset_catalog.canonical_text_assets_complete(item, assets)


from .accessories.policy import AI_PROFILE_PROVIDER_READY_STATUSES
from .accessories.policy import AI_PROFILE_REJECTED_STATUSES


def accessory_ai_profile_ready(item: dict[str, Any]) -> bool:
    return _accessory_policy.accessory_ai_profile_ready(item)


def accessory_ai_profile_rejected(item: dict[str, Any]) -> bool:
    return _accessory_policy.accessory_ai_profile_rejected(item)




def text_accessory_confirm_detail(
    item: dict[str, Any],
    text_assets: list[dict[str, Any]],
    text_assets_complete: bool,
    profile_ready: bool,
) -> dict[str, Any]:
    return _text_accessory_confirm_detail_impl(item, text_assets, text_assets_complete, profile_ready)


from .training.preview_cache import SpriteVersionInputs, TrainingPreviewCache

_training_preview_cache = TrainingPreviewCache(
    SpriteVersionInputs(lambda item: clean_sprite_assets(item), lambda item: accessory_uid(item),
                        lambda item: accessory_material_type(item), lambda item: object_alpha_material_policy(item)),
    lambda: PREVIEW_CACHE_SCHEMA_VERSION, lambda: resolve_service_path,
    lambda item: accessory_sprite_version(item), files=_business_files
)


def accessory_sprite_version(item: dict[str, Any]) -> str:
    return _training_preview_cache.accessory_sprite_version(item)


def preview_cache_key(selected: list[dict[str, Any]]) -> str:
    return _training_preview_cache.preview_cache_key(selected)


def training_preview_metadata_missing(training: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    return _training_preview_cache.training_preview_metadata_missing(training, selected)


from .accessories.pose_policy import sprite_pose_family as _sprite_pose_family_impl
from .accessories.pose_policy import PreviewPosePolicy as _PreviewPosePolicy
from .accessories.pose_policy_ports import PreviewPoseAssetOperations as _PreviewPoseAssetOperations, PreviewPoseSelectionOperations as _PreviewPoseSelectionOperations, PreviewPoseErrors as _PreviewPoseErrors
_preview_pose_policy = _PreviewPosePolicy(

    _PreviewPoseAssetOperations(assets=lambda: clean_sprite_assets, material=lambda: accessory_material_type, sprite=lambda: sprite_pose_family),

    _PreviewPoseSelectionOperations(available=lambda: available_object_pose_families, normalize=lambda: normalize_preview_pose_family_policy, many=lambda: preview_pose_families_for_policy, canonical=lambda: canonical_pose_family_name),

    _PreviewPoseErrors(make=lambda: HTTPException),

)

def available_object_pose_families(item: dict[str, Any]) -> list[str]:
    return _preview_pose_policy.available_object_pose_families(item)


from .accessories.sprite_metadata_values import canonical_pose_family_name as _canonical_pose_family_name_impl
from .accessories.sprite_metadata_values import source_object_long_short_metadata as _source_object_long_short_metadata_impl
from .accessories.sprite_metadata_values import source_long_short_oriented_px as _source_long_short_oriented_px_impl
from .accessories.sprite_metadata_values import canonical_sprite_canvas_size_px as _canonical_sprite_canvas_size_px_impl
from .accessories.sprite_footprint import SpriteFootprintMetadata as _SpriteFootprintMetadata
from .accessories.sprite_scale import SpriteScaleMetadata as _SpriteScaleMetadata
from .accessories.sprite_render_metadata import SpriteRenderMetadata as _SpriteRenderMetadata
from .accessories.sprite_metadata_ports import SpritePhysicalPolicy as _SpritePhysicalPolicy, SpriteFootprintMetadataOperations as _SpriteFootprintMetadataOperations, SpriteScalePolicy as _SpriteScalePolicy, SpriteScaleOperations as _SpriteScaleOperations, SpriteRenderOperations as _SpriteRenderOperations, SpriteImageReads as _SpriteImageReads
_sprite_footprint = _SpriteFootprintMetadata(

    _SpritePhysicalPolicy(defaults=lambda: DEFAULT_OBJECT_SIZE_MM, elongated_min=lambda: SOURCE_ASPECT_ELONGATED_MIN_RATIO, pixels_per_mm=lambda: MM_TO_PREVIEW_PX),

    _SpriteFootprintMetadataOperations(family=lambda: canonical_pose_family_name, physical=lambda: object_physical_size_mm, source=lambda: source_object_long_short_metadata, orient=lambda: oriented_long_short_pair_for_source, top_view=lambda: pose_family_is_top_view),

)
_sprite_scale = _SpriteScaleMetadata(

    _SpriteScalePolicy(minimum=lambda: UPRIGHT_SCALE_CORRECTION_MIN_RATIO, maximum=lambda: UPRIGHT_SCALE_CORRECTION_MAX_RATIO, visual=lambda: UPRIGHT_SCALE_VISUAL_ADJUSTMENT),

    _SpriteScaleOperations(family=lambda: canonical_pose_family_name, median=lambda: median_source_major_axis_px, physical=lambda: object_physical_size_mm, correction=lambda: upright_scale_correction_for_assets),

)
_sprite_render_metadata = _SpriteRenderMetadata(

    _SpriteRenderOperations(bounds=lambda: alpha_bbox, family=lambda: canonical_pose_family_name, visible=lambda: asset_visible_shape_px, orient=lambda: source_long_short_oriented_px, footprint=lambda: pose_render_footprint_metadata, physical=lambda: physical_render_size_px),

    _SpriteImageReads(path=lambda: Path, decode=lambda: cv2.imread if _business_files.runtime_provider() is None else _image_files.imread, unchanged_mode=lambda: cv2.IMREAD_UNCHANGED), files=_business_files

)

def canonical_pose_family_name(pose_family: str | None) -> str | None:
    return _canonical_pose_family_name_impl(pose_family)


def normalize_preview_pose_family_policy(value: str | None) -> str:
    return _preview_pose_policy.normalize_preview_pose_family_policy(value)


def preview_pose_family_for_policy(accessories: list[dict[str, Any]], policy: str) -> str | None:
    return _preview_pose_policy.preview_pose_family_for_policy(accessories, policy)


def preview_pose_families_for_policy(accessories: list[dict[str, Any]], policy: str) -> list[str]:
    return _preview_pose_policy.preview_pose_families_for_policy(accessories, policy)


def preview_pose_family_sequence(accessories: list[dict[str, Any]], count: int, policy: str = "auto") -> list[str | None]:
    return _preview_pose_policy.preview_pose_family_sequence(accessories, count, policy)


def preview_pose_family_sequence_label(sequence: list[str | None]) -> str | None:
    return _preview_pose_policy.preview_pose_family_sequence_label(sequence)


from .accessories.preview_sprites import load_clean_sprite as _load_clean_sprite_impl
from .accessories.preview_sprites import PreviewSpriteRenderer as _PreviewSpriteRenderer
from .accessories.preview_sprite_ports import PreviewSpriteInventory as _PreviewSpriteInventory, PreviewSpritePoses as _PreviewSpritePoses, PreviewSpriteMedia as _PreviewSpriteMedia, PreviewSpriteGeometry as _PreviewSpriteGeometry
_preview_sprite_renderer = _PreviewSpriteRenderer(
    _PreviewSpriteInventory(assets=lambda: clean_sprite_assets, preprocess=lambda: preprocess_object_clean_sprites, version=lambda: accessory_sprite_version),
    _PreviewSpritePoses(canonical=lambda: canonical_pose_family_name, family=lambda: sprite_pose_family, top_view=lambda: pose_family_is_top_view, complete=lambda: filter_complete_pose_candidates, upright_positions=lambda: UPRIGHT_TOP_VIEW_SOURCE_POSITIONS),
    _PreviewSpriteMedia(resolve=lambda: resolve_service_path, decode=lambda: load_clean_sprite),
    _PreviewSpriteGeometry(rotate=lambda: rotate_masked_asset),
)

def load_clean_sprite(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    return _load_clean_sprite_impl(path, images=_accessory_image_io)


def object_physical_size_mm(size: dict[str, Any] | None) -> tuple[float, float, float]:
    return _sprite_footprint.object_physical_size_mm(size)


def pose_family_is_top_view(pose_family: str, source_size_px: list[int] | tuple[int, int] | None = None) -> bool:
    return _sprite_footprint.pose_family_is_top_view(pose_family, source_size_px)


def source_object_long_short_metadata(source_size_px: list[int] | tuple[int, int] | None) -> dict[str, Any]:
    return _source_object_long_short_metadata_impl(source_size_px)


def oriented_long_short_pair_for_source(source_size_px: list[int] | tuple[int, int] | None, long_value: float, short_value: float) -> list[float]:
    return _sprite_footprint.oriented_long_short_pair_for_source(source_size_px, long_value, short_value)


def source_long_short_oriented_px(long_side: int, short_side: int, long_axis: Any) -> list[int]:
    return _source_long_short_oriented_px_impl(long_side, short_side, long_axis)


def pose_render_footprint_metadata(
    pose_family: str,
    source_size_px: list[int] | tuple[int, int],
    physical_size: dict[str, Any] | None,
) -> dict[str, Any]:
    return _sprite_footprint.pose_render_footprint_metadata(pose_family, source_size_px, physical_size)


def median_source_major_axis_px(assets: list[dict[str, Any]], canonical_family: str) -> float | None:
    return _sprite_scale.median_source_major_axis_px(assets, canonical_family)


def upright_scale_correction_for_assets(
    assets: list[dict[str, Any]],
    physical_size: dict[str, Any] | None,
) -> dict[str, Any]:
    return _sprite_scale.upright_scale_correction_for_assets(assets, physical_size)


def apply_upright_scale_correction_metadata(assets: list[dict[str, Any]], physical_size: dict[str, Any] | None) -> None:
    return _sprite_scale.apply_upright_scale_correction_metadata(assets, physical_size)


def asset_visible_shape_px(asset: dict[str, Any]) -> tuple[int, int] | None:
    return _sprite_render_metadata.asset_visible_shape_px(asset)


def apply_laying_standard_render_size_hints(assets: list[dict[str, Any]]) -> None:
    return _sprite_render_metadata.apply_laying_standard_render_size_hints(assets)


def sprite_render_size_px(item: dict[str, Any], sprite_meta: dict[str, Any] | None, material_type: str) -> tuple[int, int]:
    return _sprite_render_metadata.sprite_render_size_px(item, sprite_meta, material_type)


def canonical_sprite_canvas_size_px(asset: dict[str, Any]) -> tuple[int, int] | None:
    return _canonical_sprite_canvas_size_px_impl(asset)


from .accessories.alpha_masks import transparent_object_alpha as _transparent_object_alpha_impl
from .accessories.alpha_masks import solid_object_alpha as _solid_object_alpha_impl
from .accessories.material_alpha import MaterialAlphaProcessor as _MaterialAlphaProcessor
from .accessories.material_alpha_ports import MaterialAlphaOperations as _MaterialAlphaOperations
_material_alpha = _MaterialAlphaProcessor(

    _MaterialAlphaOperations(policy=lambda: object_alpha_material_policy, transparent=lambda: transparent_object_alpha, solid=lambda: solid_object_alpha),

)

def transparent_object_alpha(asset: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    return _transparent_object_alpha_impl(asset, mask)


def solid_object_alpha(mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    return _solid_object_alpha_impl(mask)


def material_aware_object_alpha(
    asset: np.ndarray,
    mask: np.ndarray,
    metadata: dict[str, Any] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    return _material_alpha.material_aware_object_alpha(asset, mask, metadata)


from .accessories.mask_geometry import normalize_angle_180 as _normalize_angle_180_impl
from .accessories.mask_geometry import alpha_bbox as _alpha_bbox_impl
from .accessories.mask_geometry import alpha_edge_max as _alpha_edge_max_impl
from .accessories.mask_geometry import alpha_edge_stats as _alpha_edge_stats_impl
from .accessories.mask_geometry import alpha_component_count as _alpha_component_count_impl
from .accessories.mask_geometry import add_sprite_safety_margin as _add_sprite_safety_margin_impl
from .accessories.mask_geometry import trim_masked_asset as _trim_masked_asset_impl
from .accessories.sprite_geometry import SpriteGeometry as _SpriteGeometry
from .accessories.sprite_geometry_ports import SpriteTransformOperations as _SpriteTransformOperations, SpriteFootprintOperations as _SpriteFootprintOperations
_sprite_geometry = _SpriteGeometry(

    _SpriteTransformOperations(normalize=lambda: normalize_angle_180, axis=lambda: masked_major_axis_angle, rotate=lambda: rotate_masked_asset, trim=lambda: trim_masked_asset, margin=lambda: add_sprite_safety_margin),

    _SpriteFootprintOperations(bounds=lambda: alpha_bbox, visible=lambda: visible_mask_size_px),

)

def normalize_angle_180(angle: float) -> float:
    return _normalize_angle_180_impl(angle)


def masked_major_axis_angle(mask: np.ndarray) -> tuple[float, float]:
    return _sprite_geometry.masked_major_axis_angle(mask)


def rotate_masked_asset(
    asset: np.ndarray,
    mask: np.ndarray,
    angle: float,
) -> tuple[np.ndarray, np.ndarray]:
    return _sprite_geometry.rotate_masked_asset(asset, mask, angle)


def restore_object_sprite_source_orientation_for_render(
    asset: np.ndarray,
    mask: np.ndarray,
    sprite_meta: dict[str, Any],
    *,
    top_view_pose: bool,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    return _preview_sprite_renderer.restore_object_sprite_source_orientation_for_render(asset, mask, sprite_meta, top_view_pose=top_view_pose)


def alpha_bbox(mask: np.ndarray, threshold: int = 8) -> list[int]:
    return _alpha_bbox_impl(mask, threshold)


def alpha_edge_max(mask: np.ndarray) -> int:
    return _alpha_edge_max_impl(mask)


def alpha_edge_stats(mask: np.ndarray) -> dict[str, Any]:
    return _alpha_edge_stats_impl(mask)


def alpha_component_count(mask: np.ndarray) -> int:
    return _alpha_component_count_impl(mask)


def add_sprite_safety_margin(asset: np.ndarray, mask: np.ndarray, margin: int = 10) -> tuple[np.ndarray, np.ndarray]:
    return _add_sprite_safety_margin_impl(asset, mask, margin)


def normalize_sprite_upright(asset: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    return _sprite_geometry.normalize_sprite_upright(asset, mask)


from .accessories.sprite_artifact_writer import SpriteArtifactWriter as _SpriteArtifactWriter
from .accessories.sprite_canvas_normalization import SpriteCanvasNormalizer as _SpriteCanvasNormalizer
from .accessories.sprite_publication_ports import SpriteArtifactGeometry as _SpriteArtifactGeometry, SpriteArtifactMetadata as _SpriteArtifactMetadata, SpriteImageEncoder as _SpriteImageEncoder, SpriteCanvasGeometry as _SpriteCanvasGeometry, SpriteCanvasImageReads as _SpriteCanvasImageReads, SpriteResampling as _SpriteResampling
_sprite_artifact_writer = _SpriteArtifactWriter(

    _SpriteArtifactGeometry(normalize=lambda: normalize_sprite_upright, margin=lambda: add_sprite_safety_margin, bounds=lambda: alpha_bbox, edge_max=lambda: alpha_edge_max, edge_stats=lambda: alpha_edge_stats),

    _SpriteArtifactMetadata(alpha=lambda: material_aware_object_alpha, footprint=lambda: pose_render_footprint_metadata),

    _SpriteImageEncoder(convert=lambda: cv2.cvtColor, bgra_mode=lambda: cv2.COLOR_BGR2BGRA, write=lambda: cv2.imwrite if _business_files.runtime_provider() is None else _image_files.imwrite),

)
_sprite_canvas_normalizer = _SpriteCanvasNormalizer(

    _SpriteCanvasGeometry(trim=lambda: trim_masked_asset, margin=lambda: add_sprite_safety_margin, bounds=lambda: alpha_bbox, edge_max=lambda: alpha_edge_max, edge_stats=lambda: alpha_edge_stats),

    _SpriteCanvasImageReads(resolve=lambda: resolve_service_path, decode=lambda: cv2.imread if _business_files.runtime_provider() is None else _image_files.imread, unchanged_mode=lambda: cv2.IMREAD_UNCHANGED),

    _SpriteResampling(resize=lambda: cv2.resize, cubic=lambda: cv2.INTER_CUBIC, area=lambda: cv2.INTER_AREA, linear=lambda: cv2.INTER_LINEAR),

    _SpriteImageEncoder(convert=lambda: cv2.cvtColor, bgra_mode=lambda: cv2.COLOR_BGR2BGRA, write=lambda: cv2.imwrite if _business_files.runtime_provider() is None else _image_files.imwrite),

)

def write_clean_sprite(path: Path, asset: np.ndarray, mask: np.ndarray, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return _sprite_artifact_writer.write_clean_sprite(path, asset, mask, metadata)


def normalize_sprite_family_canvases(generated: list[dict[str, Any]]) -> None:
    return _sprite_canvas_normalizer.normalize_sprite_family_canvases(generated)


from .accessories.crop_analysis import alpha_component_cutouts as _alpha_component_cutouts_impl
from .accessories.crop_analysis import alpha_component_summary as _alpha_component_summary_impl
from .accessories.crop_selection import CropSelection as _CropSelection
from .accessories.crop_component_ports import CropGeometry as _CropGeometry
_crop_selection = _CropSelection(

    _CropGeometry(bounds=lambda: alpha_bbox, trim=lambda: trim_masked_asset),

)

def alpha_component_cutouts(image: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    return _alpha_component_cutouts_impl(image)


def filter_cutout_to_focus_cell(
    asset: np.ndarray,
    mask: np.ndarray,
    focus_bbox: tuple[int, int, int, int],
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    return _crop_selection.filter_cutout_to_focus_cell(asset, mask, focus_bbox)


def usable_object_cutout(cutout: tuple[np.ndarray, np.ndarray] | None, source_shape: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray] | None:
    return _crop_selection.usable_object_cutout(cutout, source_shape)


def cleanup_crop_alpha_components(
    asset: np.ndarray,
    alpha: np.ndarray,
    anchor_xy: tuple[float, float] | None = None,
    min_area: int = 35,
) -> tuple[np.ndarray, dict[str, Any]]:
    return _crop_selection.cleanup_crop_alpha_components(asset, alpha, anchor_xy, min_area)


def alpha_component_summary(alpha: np.ndarray, threshold: int = 28) -> tuple[int, int]:
    return _alpha_component_summary_impl(alpha, threshold)


from .accessories.object_preprocessing import ObjectSpritePreprocessor as _ObjectSpritePreprocessor
from .accessories.object_preprocessing_ports import ObjectSpritePolicy as _ObjectSpritePolicy, ObjectSpriteSources as _ObjectSpriteSources, ObjectSpriteRuntime as _ObjectSpriteRuntime, ObjectSpriteCutouts as _ObjectSpriteCutouts, ObjectSpriteComponents as _ObjectSpriteComponents, ObjectSpriteMetadata as _ObjectSpriteMetadata, ObjectSpriteArtifacts as _ObjectSpriteArtifacts
_object_sprite_preprocessor = _ObjectSpritePreprocessor(

    _ObjectSpritePolicy(material=lambda: accessory_material_type, alpha=lambda: object_alpha_material_policy, existing=lambda: clean_sprite_assets, complete=lambda: clean_sprites_policy_complete),

    _ObjectSpriteSources(jobs=lambda: candidate_image_jobs, images=lambda: accessory_image_paths, positions=lambda: POSE_COLLECTION_GRID_POSITIONS, regions=lambda: pose_collection_regions),

    _ObjectSpriteRuntime(identifier=lambda: accessory_uid, root=lambda: NORMALIZED_DIR, now=lambda: time.time, rng=lambda: np.random.default_rng),

    _ObjectSpriteCutouts(ai_bounded=lambda: ai_background_cutout_with_bbox, green=lambda: green_screen_object_cutout_with_bbox, ai_plain=lambda: ai_background_cutout, lightweight=lambda: object_cutout_from_image, usable=lambda: usable_object_cutout),

    _ObjectSpriteComponents(cutouts=lambda: alpha_component_cutouts, focus=lambda: filter_cutout_to_focus_cell, cleanup=lambda: cleanup_crop_alpha_components, summary=lambda: alpha_component_summary, bounds=lambda: alpha_bbox),

    _ObjectSpriteMetadata(footprint=lambda: pose_render_footprint_metadata, normalize=lambda: normalize_sprite_family_canvases, scale=lambda: apply_upright_scale_correction_metadata, laying=lambda: apply_laying_standard_render_size_hints, top_view=lambda: pose_family_is_top_view, task_id=lambda: deterministic_task_id),

    _ObjectSpriteArtifacts(write=lambda: write_clean_sprite),

)

def preprocess_object_clean_sprites(item: dict[str, Any], allow_ai_cutout: bool = True, force: bool = False) -> bool:
    return _object_sprite_preprocessor.preprocess_object_clean_sprites(item, allow_ai_cutout, force)


ensure_object_clean_sprites_ready = _object_sprite_preprocessor.ensure_object_clean_sprites_ready


from .accessories.cutout_masks import foreground_mask as _foreground_mask_impl
from .accessories.cutout_masks import suppress_green_spill as _suppress_green_spill_impl
from .accessories.cutout_masks import bright_green_conveyor_mask as _bright_green_conveyor_mask_impl
from .accessories.cutout_selection import ObjectCutoutSelection as _ObjectCutoutSelection
from .accessories.chroma_cutouts import ChromaCutoutProcessor as _ChromaCutoutProcessor
from .accessories.cutout_geometry_ports import SelectionOperations as _SelectionOperations, ChromaPolicyOperations as _ChromaPolicyOperations, ChromaMatteOperations as _ChromaMatteOperations
_cutout_selection = _ObjectCutoutSelection(

    _SelectionOperations(foreground=lambda: foreground_mask, object_fallback=lambda: object_cutout_from_image, bounded_ai=lambda: ai_background_cutout_with_bbox, bounded_green=lambda: green_screen_object_cutout_with_bbox),

)
_chroma_cutouts = _ChromaCutoutProcessor(

    _ChromaPolicyOperations(normalize=lambda: normalize_chroma_screen, saturated=lambda: saturated_chroma_mask, green_spill=lambda: suppress_green_spill),

    _ChromaMatteOperations(background=lambda: chroma_background_mask, distance=lambda: chroma_distance_alpha, spill=lambda: suppress_chroma_spill),

)

def foreground_mask(image: np.ndarray) -> np.ndarray:
    return _foreground_mask_impl(image)


def object_cutout_from_image(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
    return _cutout_selection.object_cutout_from_image(image, rng)


from .accessories.background_cutouts import BackgroundCutoutProcessor as _BackgroundCutoutProcessor
from .accessories.cutout_ports import CutoutRuntimeOperations as _CutoutRuntimeOperations, CutoutGreenOperations as _CutoutGreenOperations
_background_cutouts = _BackgroundCutoutProcessor(
    _CutoutRuntimeOperations(session=lambda: rembg_session, lock=lambda: _rembg_runtime.lock),
    _CutoutGreenOperations(mask=lambda: bright_green_conveyor_mask, spill=lambda: suppress_green_spill),
)

def rembg_session() -> Any | None:
    return _rembg_runtime.rembg_session()


def ai_background_cutout_with_bbox(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    return _background_cutouts.ai_background_cutout_with_bbox(image)


def ai_background_cutout(image: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    return _cutout_selection.ai_background_cutout(image)


def green_screen_object_cutout_with_bbox(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    return _cutout_selection.green_screen_object_cutout_with_bbox(image, rng)


def green_screen_object_cutout(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
    return _cutout_selection.green_screen_object_cutout(image, rng)


POSE_COLLECTION_GRID_POSITIONS = [
    "top-left",
    "top-center",
    "top-right",
    "middle-left",
    "center",
    "middle-right",
    "bottom-left",
    "bottom-center",
    "bottom-right",
]
UPRIGHT_TOP_VIEW_SOURCE_POSITIONS = ("center", "bottom-center")


from .accessories.pose_policy import pose_collection_regions as _pose_collection_regions_impl
from .accessories.pose_policy import normalize_cardinal_rotation_degrees as _normalize_cardinal_rotation_degrees_impl
from .accessories.pose_policy import source_object_major_axis_px as _source_object_major_axis_px_impl
from .accessories.pose_policy import PoseGridPolicy as _PoseGridPolicy
from .accessories.pose_policy import PoseCandidatePolicy as _PoseCandidatePolicy
from .accessories.pose_policy_ports import PoseLayoutValues as _PoseLayoutValues, PoseRotationOperations as _PoseRotationOperations, PoseRenderOperations as _PoseRenderOperations, PoseAssetOperations as _PoseAssetOperations, PoseCandidateOperations as _PoseCandidateOperations
_pose_grid_policy = _PoseGridPolicy(

    _PoseLayoutValues(grid=lambda: POSE_COLLECTION_GRID_POSITIONS, upright=lambda: UPRIGHT_TOP_VIEW_SOURCE_POSITIONS),

    _PoseRotationOperations(normalize=lambda: normalize_cardinal_rotation_degrees, row_col=lambda: grid_row_col, position=lambda: grid_position_from_row_col),

    _PoseRenderOperations(is_top=lambda: pose_family_is_top_view, source=lambda: source_position_for_rotated_target),

)
_pose_candidate_policy = _PoseCandidatePolicy(

    _PoseAssetOperations(canonical=lambda: canonical_pose_family_name, assets=lambda: clean_sprite_assets, footprint=lambda: pose_render_footprint_metadata),

    _PoseCandidateOperations(major_axis=lambda: source_object_major_axis_px, family=lambda: sprite_pose_family),

)

def pose_collection_regions(image: np.ndarray, padded: bool = True) -> list[tuple[int, int, int, int]]:
    return _pose_collection_regions_impl(image, padded)


def grid_position_for_center(center: tuple[int, int], roi: tuple[int, int, int, int] = BACKGROUND_ROI_PX) -> str:
    return _pose_grid_policy.grid_position_for_center(center, roi)


def grid_row_col(position: str | None) -> tuple[int, int] | None:
    return _pose_grid_policy.grid_row_col(position)


def grid_position_from_row_col(row: int, col: int) -> str:
    return _pose_grid_policy.grid_position_from_row_col(row, col)


def normalize_cardinal_rotation_degrees(angle: float) -> int:
    return _normalize_cardinal_rotation_degrees_impl(angle)


def source_position_for_rotated_target(target_position: str | None, rotation_degrees: float) -> str | None:
    """Pick the source grid cell that rotates into the requested target cell."""
    return _pose_grid_policy.source_position_for_rotated_target(target_position, rotation_degrees)


def source_position_for_render_policy(
    target_position: str | None,
    rotation_degrees: float,
    pose_family: str | None,
    rng: np.random.Generator,
) -> str | None:
    return _pose_grid_policy.source_position_for_render_policy(target_position, rotation_degrees, pose_family, rng)


def object_render_pose_policy(pose_family: str | None, rng: np.random.Generator) -> dict[str, Any]:
    return _pose_grid_policy.object_render_pose_policy(pose_family, rng)


def pose_selection_reason(target_position: str | None, source_position: str | None, rotation_degrees: float) -> str:
    return _pose_grid_policy.pose_selection_reason(target_position, source_position, rotation_degrees)


def object_pose_render_size_hint(item: dict[str, Any], pose_family: str | None) -> tuple[int, int]:
    return _pose_candidate_policy.object_pose_render_size_hint(item, pose_family)


def source_object_major_axis_px(asset: dict[str, Any]) -> int | None:
    return _source_object_major_axis_px_impl(asset)


def filter_complete_pose_candidates(candidates: list[dict[str, Any]], pose_family: str | None) -> list[dict[str, Any]]:
    return _pose_candidate_policy.filter_complete_pose_candidates(candidates, pose_family)


def sprite_pose_family(asset: dict[str, Any]) -> str:
    return _sprite_pose_family_impl(asset)


def choose_object_pose_family(sprites: list[dict[str, Any]], rng: np.random.Generator) -> str | None:
    return _pose_candidate_policy.choose_object_pose_family(sprites, rng)


def load_object_preview_sprite(
    item: dict[str, Any],
    rng: np.random.Generator,
    target_position: str | None = None,
    pose_family: str | None = None,
    source_position: str | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]] | None:
    return _preview_sprite_renderer.load_object_preview_sprite(item, rng, target_position, pose_family, source_position)


def trim_masked_asset(asset: np.ndarray, mask: np.ndarray, pad: int = 4) -> tuple[np.ndarray, np.ndarray]:
    return _trim_masked_asset_impl(asset, mask, pad)


from .accessories.compositing import physical_mask_for_rect_asset as _physical_mask_for_rect_asset_impl
from .accessories.compositing import trim_rect_asset as _trim_rect_asset_impl
from .accessories.compositing import long_axis_unified_render_box as _long_axis_unified_render_box_impl
from .accessories.compositing import paste_rectified_document_asset as _paste_rectified_document_asset_impl
from .accessories.compositing import AssetCompositor as _AssetCompositor
from .accessories.compositing_ports import CompositionGeometry as _CompositionGeometry, CompositionOperations as _CompositionOperations
_asset_compositor = _AssetCompositor(
    _CompositionGeometry(trim=lambda: trim_masked_asset, resize_footprint=lambda: resize_masked_asset_to_visible_footprint, visible_size=lambda: visible_mask_size_px),
    _CompositionOperations(paste_masked=lambda: paste_masked_asset, trim_rect=lambda: trim_rect_asset, physical_mask=lambda: physical_mask_for_rect_asset),
)

def physical_mask_for_rect_asset(asset: np.ndarray) -> np.ndarray:
    return _physical_mask_for_rect_asset_impl(asset)


def trim_rect_asset(asset: np.ndarray, pad: int = 0) -> np.ndarray:
    return _trim_rect_asset_impl(asset, pad)


def paste_masked_asset(
    canvas: np.ndarray,
    asset: np.ndarray,
    mask: np.ndarray,
    center: tuple[int, int],
    target_size: tuple[int, int],
    angle: float,
    trim_before_paste: bool = True,
    return_visible_mask: bool = False,
    resize_to_target: bool = True,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    return _asset_compositor.paste_masked_asset(canvas, asset, mask, center, target_size, angle, trim_before_paste, return_visible_mask, resize_to_target)


def visible_mask_size_px(mask: np.ndarray) -> list[int]:
    return _sprite_geometry.visible_mask_size_px(mask)


def resize_masked_asset_to_visible_footprint(
    asset: np.ndarray,
    mask: np.ndarray,
    target_size: tuple[int, int],
    preserve_aspect_ratio: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    return _sprite_geometry.resize_masked_asset_to_visible_footprint(asset, mask, target_size, preserve_aspect_ratio)


def long_axis_unified_render_box(
    visible_w: int,
    visible_h: int,
    target_long_px: int,
    target_short_px: int,
) -> tuple[int, int]:
    """Return a render box whose aspect equals the sprite's own visible aspect and
    whose LONG side equals the physical-footprint long side.

    The compositor pastes with preserve_aspect_ratio=min(w/vw, h/vh). When the
    footprint aspect (from physical dims) does not match a particular AI pose
    image's visible aspect, that min() clamps to the short side and the object
    shrinks to a fraction of its true size (the source of the 10x size spread).
    By matching the box aspect to the sprite, min() resolves to the long-axis
    scale, so every view of the same accessory renders at the same long-axis
    length and stays size-consistent without distortion."""
    return _long_axis_unified_render_box_impl(visible_w, visible_h, target_long_px, target_short_px)


def paste_physical_object_asset(
    canvas: np.ndarray,
    asset: np.ndarray,
    mask: np.ndarray,
    center: tuple[int, int],
    target_long_side_px: int,
    target_short_side_px: int,
    angle: float,
    preserve_aspect_ratio: bool = False,
) -> dict[str, Any]:
    return _asset_compositor.paste_physical_object_asset(canvas, asset, mask, center, target_long_side_px, target_short_side_px, angle, preserve_aspect_ratio)


def paste_rectified_document_asset(
    canvas: np.ndarray,
    asset: np.ndarray,
    center: tuple[int, int],
    target_size: tuple[int, int],
    angle: float,
) -> dict[str, Any]:
    return _paste_rectified_document_asset_impl(canvas, asset, center, target_size, angle)


def paste_rotated_asset(canvas: np.ndarray, asset: np.ndarray, center: tuple[int, int], target_size: tuple[int, int], angle: float) -> np.ndarray:
    return _asset_compositor.paste_rotated_asset(canvas, asset, center, target_size, angle)


def normalize_accessory_assets(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_preparation.normalize_accessory_assets(item)


def defer_accessory_normalization(item: dict[str, Any]) -> None:
    return _preparation_defer(item)


from .accessories.reference_media import AccessoryReferenceMedia
from .accessories.reference_media_ports import ReferenceMediaDependencies

_accessory_reference_media = AccessoryReferenceMedia(ReferenceMediaDependencies(
    frame_detail_score=lambda: frame_detail_score,
    frame_histogram=lambda: frame_histogram,
    _image_files=lambda: _image_files,
    public_output_url=lambda: public_output_url,
))


def frame_detail_score(frame: np.ndarray) -> float:
    return _accessory_reference_media.frame_detail_score(frame)


def frame_histogram(frame: np.ndarray) -> np.ndarray:
    return _accessory_reference_media.frame_histogram(frame)


def extract_video_reference_frames(video_path: Path, output_dir: Path, max_frames: int = MAX_VIDEO_REFERENCE_FRAMES) -> list[dict[str, Any]]:
    return _accessory_reference_media.extract_video_reference_frames(video_path, output_dir, max_frames)


def expand_accessory_reference_sources(candidate_id: str, source_files: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    return _accessory_preparation.expand_accessory_reference_sources(candidate_id, source_files)


def write_thumbnail(image: np.ndarray, out_path: Path, angle: float = 0.0, size: int = 360) -> dict[str, Any]:
    return _accessory_reference_media.write_thumbnail(image, out_path, angle, size)


from .accessories.pose_collection_prompts import PoseCollectionPrompts
from .accessories.pose_collection_prompt_ports import PoseCollectionPromptDependencies

_pose_collection_prompts = PoseCollectionPrompts(PoseCollectionPromptDependencies(
    tabletop_scene_text=lambda: tabletop_scene_text,
    pose_collection_camera_grid_text=lambda: pose_collection_camera_grid_text,
    pose_collection_position_specs=lambda: pose_collection_position_specs,
    POSE_COLLECTION_BATCHES=lambda: POSE_COLLECTION_BATCHES,
    pose_collection_dimension_text=lambda: pose_collection_dimension_text,
    pose_collection_camera_batch_text=lambda: pose_collection_camera_batch_text,
    upright_spatial_relation_text=lambda: upright_spatial_relation_text,
))


def pose_collection_dimension_text(item: dict[str, Any]) -> str:
    return _pose_collection_prompts.pose_collection_dimension_text(item)


def tabletop_scene_text(surface_mode: str = "white") -> str:
    return _pose_collection_prompts.tabletop_scene_text(surface_mode)


def pose_collection_camera_grid_text(item: dict[str, Any], surface_mode: str = "white") -> str:
    return _pose_collection_prompts.pose_collection_camera_grid_text(item, surface_mode)


def pose_collection_position_specs(item: dict[str, Any]) -> dict[str, str]:
    return _pose_collection_prompts.pose_collection_position_specs(item)


def pose_collection_camera_batch_text(item: dict[str, Any], batch_key: str | None, surface_mode: str = "white") -> str:
    return _pose_collection_prompts.pose_collection_camera_batch_text(item, batch_key, surface_mode)


def upright_spatial_relation_text() -> str:
    return _pose_collection_prompts.upright_spatial_relation_text()


def build_pose_collection_prompt(
    item: dict[str, Any],
    pose_family: str = "combined",
    batch_key: str | None = None,
    surface_mode: str = "reference",
) -> str:
    return _pose_collection_prompts.build_pose_collection_prompt(item, pose_family, batch_key, surface_mode)


def build_white_table_replacement_prompt(item: dict[str, Any], pose_family: str) -> str:
    return _pose_collection_prompts.build_white_table_replacement_prompt(item, pose_family)


def build_anchor_replacement_pose_prompt(item: dict[str, Any], pose_family: str) -> str:
    return _pose_collection_prompts.build_anchor_replacement_pose_prompt(item, pose_family)


from .accessories.pose_collection_jobs import PoseCollectionJobs
from .accessories.pose_collection_job_ports import PoseJobIdentity, PoseJobMedia, PoseJobWorkflow

_pose_collection_jobs = PoseCollectionJobs(
    identity=PoseJobIdentity(
        record_owner_id=lambda: record_owner_id,
        safe_record_id=lambda: safe_record_id,
        accessory_uid=lambda: accessory_uid,
        deterministic_task_id=lambda: deterministic_task_id,
        record_audit_fields=lambda: record_audit_fields,
        accessory_material_type=lambda: accessory_material_type,
    ),
    media=PoseJobMedia(
        output_write_dir_for_owner=lambda: output_write_dir_for_owner,
        POSE_ANCHOR_IMAGES=lambda: POSE_ANCHOR_IMAGES,
        _business_files=lambda: _business_files,
        existing_source_image_paths=lambda: existing_source_image_paths,
        MAX_IMAGE_WORKER_INPUTS=lambda: MAX_IMAGE_WORKER_INPUTS,
        pose_collection_output_dir=lambda: pose_collection_output_dir,
        pose_collection_output_name=lambda: pose_collection_output_name,
        public_output_url=lambda: public_output_url,
        source_reference_inputs_for_pose_job=lambda: source_reference_inputs_for_pose_job,
        image_job_output_path=lambda: image_job_output_path,
    ),
    workflow=PoseJobWorkflow(
        pose_collection_job_id=lambda: pose_collection_job_id,
        CODEX_IMAGE_WORKER_QUEUE_STATUS=lambda: CODEX_IMAGE_WORKER_QUEUE_STATUS,
        LOCAL_CODEX_IMAGE_PROVIDER=lambda: LOCAL_CODEX_IMAGE_PROVIDER,
        build_anchor_replacement_pose_prompt=lambda: build_anchor_replacement_pose_prompt,
        ensure_image_job_task_id=lambda: ensure_image_job_task_id,
        ensure_anchor_image_provenance=lambda: ensure_anchor_image_provenance,
        ensure_image_job_target_guides=lambda: ensure_image_job_target_guides,
        POSE_COLLECTION_GRID_ENABLED=lambda: POSE_COLLECTION_GRID_ENABLED,
        candidate_image_jobs=lambda: candidate_image_jobs,
        make_pose_collection_job=lambda: make_pose_collection_job,
    ),
)


def safe_record_id(value: Any) -> str:
    return _pose_collection_jobs.safe_record_id(value)


def pose_collection_output_dir(item: dict[str, Any]) -> Path:
    return _pose_collection_jobs.pose_collection_output_dir(item)


def pose_collection_output_name(pose_family: str) -> str:
    return _pose_collection_jobs.pose_collection_output_name(pose_family)


def pose_collection_job_id(item: dict[str, Any], pose_family: str) -> str:
    return _pose_collection_jobs.pose_collection_job_id(item, pose_family)


def source_reference_inputs_for_pose_job(item: dict[str, Any], pose_family: str) -> list[str]:
    return _pose_collection_jobs.source_reference_inputs_for_pose_job(item, pose_family)


def make_pose_collection_job(item: dict[str, Any], pose_family: str) -> dict[str, Any]:
    return _pose_collection_jobs.make_pose_collection_job(item, pose_family)


def ensure_pose_collection_image_jobs(item: dict[str, Any]) -> bool:
    return _pose_collection_jobs.ensure_pose_collection_image_jobs(item)


def pending_pose_collection_jobs(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _pose_collection_jobs.pending_pose_collection_jobs(item)


def pose_collection_pending_detail(item: dict[str, Any], pending: list[dict[str, Any]]) -> str:
    return _pose_collection_jobs.pose_collection_pending_detail(item, pending)


def create_accessory_candidate(
    name: str,
    material_type: str,
    training_role: str,
    source_files: list[str],
    physical_size: dict[str, Any] | None = None,
    material_alpha_policy: str | None = None,
    size_reference: str | None = None,
) -> dict[str, Any]:
    return _candidate_factory.create_accessory_candidate(name, material_type, training_role, source_files, physical_size, material_alpha_policy, size_reference)


from .accessories.candidate_repository import CandidateRepository, CandidateStoreDependencies
_candidate_repository = CandidateRepository(CandidateStoreDependencies(
    runtime_repository=lambda: runtime_postgres_repository_or_none(),
    directory=lambda: ACCESSORY_CANDIDATES_DIR, lock=lambda: _candidate_store_lock,
    ensure_task_ids=lambda candidate: ensure_candidate_image_job_task_ids(candidate),
    safe_id=lambda value: safe_record_id(value),
    created_at=lambda record, path: record_created_at(record, path),
    updated_at=lambda record, path: record_updated_at(record, path),
))


def load_accessory_candidate(candidate_id: str) -> dict[str, Any]:
    return _candidate_repository.load_accessory_candidate(candidate_id)


def save_accessory_candidate(path: Path, candidate: dict[str, Any]) -> None:
    return _candidate_repository.save_accessory_candidate(path, candidate)


def delete_accessory_candidate(candidate_id: str, path: Path | None = None) -> bool:
    return _candidate_repository.delete_accessory_candidate(candidate_id, path)


from .accessories.candidate_artifacts import CandidateArtifacts
from .accessories.candidate_artifact_ports import CandidateArtifactFiles, CandidateArtifactRecords

_candidate_artifacts = CandidateArtifacts(
    files=CandidateArtifactFiles(
        _business_files=lambda: _business_files,
        UPLOAD_DIR=lambda: UPLOAD_DIR,
        output_write_dir=lambda: output_write_dir,
        IMAGE_REFERENCE_SUFFIXES=lambda: IMAGE_REFERENCE_SUFFIXES,
    ),
    records=CandidateArtifactRecords(
        safe_record_id=lambda: safe_record_id,
        load_config=lambda: load_config,
        list_accessory_candidate_records=lambda: list_accessory_candidate_records,
    ),
)


def cleanup_accessory_candidate_artifacts(candidate: dict[str, Any]) -> list[str]:
    'Remove only directories that are unambiguously owned by a pending candidate.'
    return _candidate_artifacts.cleanup_accessory_candidate_artifacts(candidate)


def accessory_candidate_record_path(candidate: dict[str, Any], fallback_id: str = "candidate") -> Path:
    return _candidate_repository.accessory_candidate_record_path(candidate, fallback_id)


def list_accessory_candidate_records(*, reverse: bool = True) -> list[tuple[Path, dict[str, Any]]]:
    return _candidate_repository.list_accessory_candidate_records(reverse=reverse)


def write_accessory_candidate_file(path: Path, candidate: dict[str, Any]) -> None:
    return _candidate_repository.write_accessory_candidate_file(path, candidate)


from .accessories.image_job_queue import ImageJobQueue
from .accessories.image_job_queue_ports import ImageQueueStorage, ImageQueueMetadata, ImageQueueExecution

_image_job_queue = ImageJobQueue(
    storage=ImageQueueStorage(
        _candidate_store_lock=lambda: _candidate_store_lock,
        CONFIG_PATH=lambda: CONFIG_PATH,
        load_config=lambda: load_config,
        save_config=lambda: save_config,
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        load_accessory_candidate=lambda: load_accessory_candidate,
        save_accessory_candidate=lambda: save_accessory_candidate,
        list_accessory_candidate_records=lambda: list_accessory_candidate_records,
        _business_files=lambda: _business_files,
        HTTPException=lambda: HTTPException,
    ),
    metadata=ImageQueueMetadata(
        ensure_image_job_task_id=lambda: ensure_image_job_task_id,
        ensure_candidate_image_job_task_ids=lambda: ensure_candidate_image_job_task_ids,
        candidate_image_jobs=lambda: candidate_image_jobs,
        store_candidate_image_job=lambda: store_candidate_image_job,
        accessory_uid=lambda: accessory_uid,
        file_stem_identifier=lambda: file_stem_identifier,
        accessory_material_type=lambda: accessory_material_type,
        ensure_pose_collection_image_jobs=lambda: ensure_pose_collection_image_jobs,
        image_job_output_path=lambda: image_job_output_path,
        public_output_url=lambda: public_output_url,
        resolve_service_path=lambda: resolve_service_path,
        preprocess_object_clean_sprites=lambda: preprocess_object_clean_sprites,
    ),
    execution=ImageQueueExecution(
        _image_worker_runtime=lambda: _image_worker_runtime,
        IMAGE_JOB_QUEUED_STATUSES=lambda: IMAGE_JOB_QUEUED_STATUSES,
        MAX_PARALLEL_IMAGE_WORKERS=lambda: MAX_PARALLEL_IMAGE_WORKERS,
        next_queued_image_job=lambda: next_queued_image_job,
        update_image_worker_status=lambda: update_image_worker_status,
        run_image_generation_job=lambda: run_image_generation_job,
    ),
)


def mutate_candidate_image_job(
    path: Path,
    candidate: dict[str, Any],
    job: dict[str, Any],
    updates: dict[str, Any],
    *,
    preprocess_clean_sprites: bool = False,
) -> dict[str, Any]:
    return _image_job_queue.mutate_candidate_image_job(path, candidate, job, updates, preprocess_clean_sprites=preprocess_clean_sprites)


def candidate_has_active_image_jobs(candidate: dict[str, Any]) -> bool:
    return any(str(job.get("status", "")) in IMAGE_JOB_ACTIVE_STATUSES for job in candidate_image_jobs(candidate))


from .model_providers.image_provider_configuration import ImageProviderConfiguration
from .model_providers.image_provider_configuration_ports import ImageProviderSelection, ImageProviderSettings, ImageProviderPayload

_image_provider_configuration = ImageProviderConfiguration(
    selection=ImageProviderSelection(
        CURSOR_IMAGE_MODEL_PRIORITY=lambda: CURSOR_IMAGE_MODEL_PRIORITY,
        CURSOR_IMAGE_MODEL_KEYWORDS=lambda: CURSOR_IMAGE_MODEL_KEYWORDS,
        normalize_agent_model_options=lambda: normalize_agent_model_options,
        cursor_image_model_score=lambda: cursor_image_model_score,
        normalize_agent_provider=lambda: normalize_agent_provider,
        AGENT_PROVIDER_CURSOR=lambda: AGENT_PROVIDER_CURSOR,
        agent_connected=lambda: agent_connected,
    ),
    settings=ImageProviderSettings(
        load_agent_config=lambda: load_agent_config,
        inspect_cursor_image_models=lambda: inspect_cursor_image_models,
        CURSOR_IMAGE2_BASE_URL_ENV=lambda: CURSOR_IMAGE2_BASE_URL_ENV,
        AGENT_CURSOR_DEFAULT_BASE_URL=lambda: AGENT_CURSOR_DEFAULT_BASE_URL,
        CURSOR_IMAGE2_ENDPOINT_ENV=lambda: CURSOR_IMAGE2_ENDPOINT_ENV,
        CURSOR_IMAGE2_API_KEY_ENV=lambda: CURSOR_IMAGE2_API_KEY_ENV,
        CURSOR_IMAGE2_MODEL_ENV=lambda: CURSOR_IMAGE2_MODEL_ENV,
        CURSOR_IMAGE2_DEFAULT_MODEL=lambda: CURSOR_IMAGE2_DEFAULT_MODEL,
        masked_url_for_status=lambda: masked_url_for_status,
        cursor_image2_settings=lambda: cursor_image2_settings,
        LOCAL_CODEX_IMAGE_PROVIDER=lambda: LOCAL_CODEX_IMAGE_PROVIDER,
        CURSOR_IMAGE2_PROVIDER=lambda: CURSOR_IMAGE2_PROVIDER,
    ),
    payload=ImageProviderPayload(
        image_job_prompt=lambda: image_job_prompt,
        image_file_payload=lambda: image_file_payload,
        MAX_IMAGE_WORKER_INPUTS=lambda: MAX_IMAGE_WORKER_INPUTS,
        cursor_image2_response_candidates=lambda: cursor_image2_response_candidates,
        decode_b64_image=lambda: decode_b64_image,
    ),
)


def image_job_prompt(job: dict[str, Any]) -> str:
    return _image_provider_configuration.image_job_prompt(job)


from .accessories.image_worker_diagnostics import ImageWorkerDiagnostics
from .accessories.image_worker_diagnostic_ports import ImageDiagnosticMedia, ImageDiagnosticRuntime, ImageDiagnosticPolicy

_image_worker_diagnostics = ImageWorkerDiagnostics(
    media=ImageDiagnosticMedia(
        _business_files=lambda: _business_files,
        resolve_service_path=lambda: resolve_service_path,
        safe_name=lambda: safe_name,
        IMAGE_WORKER_LOG_DIR=lambda: IMAGE_WORKER_LOG_DIR,
        read_image_worker_log_tail=lambda: read_image_worker_log_tail,
    ),
    runtime=ImageDiagnosticRuntime(
        _image_worker_processes=lambda: _image_worker_processes,
        image_worker_process_alive=lambda: image_worker_process_alive,
        codex_process_has_log_open=lambda: codex_process_has_log_open,
        image_job_has_live_worker=lambda: image_job_has_live_worker,
    ),
    policy=ImageDiagnosticPolicy(
        IMAGE_JOB_ACTIVE_STATUSES=lambda: IMAGE_JOB_ACTIVE_STATUSES,
        IMAGE_WORKER_LOG_TAIL_BYTES=lambda: IMAGE_WORKER_LOG_TAIL_BYTES,
        IMAGE_WORKER_STALE_SECONDS=lambda: IMAGE_WORKER_STALE_SECONDS,
        LOCAL_CODEX_IMAGE_PROVIDER=lambda: LOCAL_CODEX_IMAGE_PROVIDER,
    ),
)


def image_job_is_active(status: str) -> bool:
    return _image_worker_diagnostics.image_job_is_active(status)


def codex_log_has_generated_image(log_path: Path) -> bool:
    return _image_worker_diagnostics.codex_log_has_generated_image(log_path)


def image_job_output_path(job: dict[str, Any], *, for_write: bool = False) -> Path:
    return _image_worker_diagnostics.image_job_output_path(job, for_write=for_write)


def image_job_log_path(job: dict[str, Any]) -> Path:
    return _image_worker_diagnostics.image_job_log_path(job)


def read_image_worker_log_tail(log_path: Path) -> str:
    return _image_worker_diagnostics.read_image_worker_log_tail(log_path)


def classify_image_worker_failure(log_path: Path, return_code: int | None, output_path: Path, *, stale: bool = False) -> str:
    return _image_worker_diagnostics.classify_image_worker_failure(log_path, return_code, output_path, stale=stale)


def image_worker_process_alive(job_id: str) -> bool:
    return _image_worker_diagnostics.image_worker_process_alive(job_id)


def codex_process_has_log_open(log_path: Path) -> bool:
    return _image_worker_diagnostics.codex_process_has_log_open(log_path)


def image_job_has_live_worker(job: dict[str, Any], log_path: Path) -> bool:
    return _image_worker_diagnostics.image_job_has_live_worker(job, log_path)


def running_image_job_is_stale(job: dict[str, Any], log_path: Path) -> bool:
    return _image_worker_diagnostics.running_image_job_is_stale(job, log_path)


def next_queued_image_job() -> tuple[Path, dict[str, Any], dict[str, Any]] | None:
    return _image_job_queue.next_queued_image_job()


update_image_worker_status = _image_job_queue.update_image_worker_status


def cursor_image_model_score(model_id: str) -> tuple[int, int]:
    return _image_provider_configuration.cursor_image_model_score(model_id)


def inspect_cursor_image_models(agent_config: dict[str, Any]) -> dict[str, Any]:
    return _image_provider_configuration.inspect_cursor_image_models(agent_config)


def cursor_image2_settings() -> dict[str, Any]:
    return _image_provider_configuration.cursor_image2_settings()


def public_cursor_image2_status() -> dict[str, Any]:
    return _image_provider_configuration.public_cursor_image2_status()


from .model_providers.payloads import ImagePayloadCodec

_image_payload_codec = ImagePayloadCodec(
    files=lambda: _business_files,
    decoder=lambda: decode_b64_image,
    candidates=lambda: cursor_image2_response_candidates,
)


def image_file_payload(path: Path) -> dict[str, str]:
    return _image_payload_codec.image_file_payload(path)


def cursor_image2_payload(job: dict[str, Any], input_files: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    return _image_provider_configuration.cursor_image2_payload(job, input_files, settings)


from .model_providers.payloads import decode_b64_image


def cursor_image2_response_candidates(payload: Any) -> list[dict[str, Any]]:
    return _image_provider_configuration.cursor_image2_response_candidates(payload)


def extract_cursor_image2_bytes(payload: dict[str, Any], settings: dict[str, Any]) -> bytes:
    return _image_provider_configuration.extract_cursor_image2_bytes(payload, settings)


def windows_worker_image_response_bytes(payload: dict[str, Any]) -> bytes:
    return _image_payload_codec.windows_worker_image_response_bytes(payload)


from .accessories.image_job_execution import ImageJobExecution
from .accessories.image_job_execution_ports import ImageExecutionFiles, ImageExecutionEvidence, ImageExecutionProviders

_image_job_execution = ImageJobExecution(
    files=ImageExecutionFiles(
        _business_files=lambda: _business_files,
        _image_files=lambda: _image_files,
        image_job_output_path=lambda: image_job_output_path,
        IMAGE_WORKER_LOG_DIR=lambda: IMAGE_WORKER_LOG_DIR,
        ROOT=lambda: ROOT,
        safe_name=lambda: safe_name,
        resolve_service_path=lambda: resolve_service_path,
        public_output_url=lambda: public_output_url,
    ),
    evidence=ImageExecutionEvidence(
        mutate_candidate_image_job=lambda: mutate_candidate_image_job,
        update_image_worker_status=lambda: update_image_worker_status,
        _image_worker_processes=lambda: _image_worker_processes,
        image_job_prompt=lambda: image_job_prompt,
        codex_log_has_generated_image=lambda: codex_log_has_generated_image,
        classify_image_worker_failure=lambda: classify_image_worker_failure,
        bounded_text=lambda: bounded_text,
    ),
    providers=ImageExecutionProviders(
        LOCAL_CODEX_IMAGE_PROVIDER=lambda: LOCAL_CODEX_IMAGE_PROVIDER,
        CURSOR_IMAGE2_PROVIDER=lambda: CURSOR_IMAGE2_PROVIDER,
        CURSOR_IMAGE2_QUEUE_STATUS=lambda: CURSOR_IMAGE2_QUEUE_STATUS,
        CODEX_IMAGE_WORKER_QUEUE_STATUS=lambda: CODEX_IMAGE_WORKER_QUEUE_STATUS,
        MAX_IMAGE_WORKER_INPUTS=lambda: MAX_IMAGE_WORKER_INPUTS,
        cursor_image2_settings=lambda: cursor_image2_settings,
        cursor_image2_payload=lambda: cursor_image2_payload,
        cursor_auth_headers=lambda: cursor_auth_headers,
        extract_cursor_image2_bytes=lambda: extract_cursor_image2_bytes,
        run_codex_image_job=lambda: run_codex_image_job,
        run_cursor_image2_job=lambda: run_cursor_image2_job,
        run_cos_codex_image_job=lambda: run_cos_codex_image_job,
        windows_worker_base_url=lambda: windows_worker_base_url,
        windows_worker_headers=lambda: windows_worker_headers,
        windows_worker_image_timeout_seconds=lambda: windows_worker_image_timeout_seconds,
        windows_worker_image_response_bytes=lambda: windows_worker_image_response_bytes,
        masked_url_for_status=lambda: masked_url_for_status,
    ),
)


def run_windows_worker_image_job(path: Path, candidate: dict[str, Any], job: dict[str, Any], *, reason: str) -> bool:
    return _image_job_execution.run_windows_worker_image_job(path, candidate, job, reason=reason)


def run_cursor_image2_job(path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
    return _image_job_execution.run_cursor_image2_job(path, candidate, job)


def run_cos_codex_image_job(path: Path, candidate: dict[str, Any], job: dict[str, Any], runtime) -> None:
    return _image_job_execution.run_cos_codex_image_job(path, candidate, job, runtime)


def run_codex_image_job(path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
    return _image_job_execution.run_codex_image_job(path, candidate, job)


@pinned_model_profiles(resolve_model_profiles, argument=2)
def run_image_generation_job(path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
    return _image_job_execution.run_image_generation_job(path, candidate, job)


def image_worker_loop() -> None:
    return _image_job_queue.image_worker_loop()


start_image_worker = _image_worker_runtime.start


from .accessories.image_job_management import ImageJobManagement
from .accessories.image_job_management_ports import ImageJobStorage, ImageJobAccess, ImageJobMetadata, ImageJobActions

_image_job_management = ImageJobManagement(
    storage=ImageJobStorage(
        _business_files=lambda: _business_files,
        _candidate_store_lock=lambda: _candidate_store_lock,
        ACCESSORY_CANDIDATES_DIR=lambda: ACCESSORY_CANDIDATES_DIR,
        list_accessory_candidate_records=lambda: list_accessory_candidate_records,
        load_accessory_candidate=lambda: load_accessory_candidate,
        save_accessory_candidate=lambda: save_accessory_candidate,
        delete_accessory_candidate=lambda: delete_accessory_candidate,
        cleanup_accessory_candidate_artifacts=lambda: cleanup_accessory_candidate_artifacts,
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        load_config=lambda: load_config,
        save_config=lambda: save_config,
    ),
    access=ImageJobAccess(
        _request_user=lambda: _request_user,
        record_visible_to_user=lambda: record_visible_to_user,
        record_mutable_by_user=lambda: record_mutable_by_user,
        require_record_access=lambda: require_record_access,
    ),
    metadata=ImageJobMetadata(
        IMAGE_JOB_ACTIVE_STATUSES=lambda: IMAGE_JOB_ACTIVE_STATUSES,
        LOCAL_CODEX_IMAGE_PROVIDER=lambda: LOCAL_CODEX_IMAGE_PROVIDER,
        WINDOWS_WORKER_IMAGE_PROVIDER=lambda: WINDOWS_WORKER_IMAGE_PROVIDER,
        CODEX_IMAGE_JOB_PERSISTED_KEYS=lambda: CODEX_IMAGE_JOB_PERSISTED_KEYS,
        CODEX_IMAGE_WORKER_QUEUE_STATUS=lambda: CODEX_IMAGE_WORKER_QUEUE_STATUS,
        image_job_output_path=lambda: image_job_output_path,
        image_job_log_path=lambda: image_job_log_path,
        public_output_url=lambda: public_output_url,
        public_output_url_for_existing=lambda: public_output_url_for_existing,
        classify_image_worker_failure=lambda: classify_image_worker_failure,
        running_image_job_is_stale=lambda: running_image_job_is_stale,
        public_text=lambda: public_text,
        accessory_uid=lambda: accessory_uid,
        accessory_material_type=lambda: accessory_material_type,
        candidate_image_jobs=lambda: candidate_image_jobs,
        deterministic_task_id=lambda: deterministic_task_id,
        ensure_candidate_image_job_task_ids=lambda: ensure_candidate_image_job_task_ids,
        ensure_image_job_task_id=lambda: ensure_image_job_task_id,
        ensure_pose_collection_image_jobs=lambda: ensure_pose_collection_image_jobs,
        store_candidate_image_job=lambda: store_candidate_image_job,
        image_job_matches=lambda: image_job_matches,
        record_created_at=lambda: record_created_at,
        record_updated_at=lambda: record_updated_at,
        record_owner_id=lambda: record_owner_id,
        record_owner_username=lambda: record_owner_username,
        enrich_record_audit_fields=lambda: enrich_record_audit_fields
    ),
    actions=ImageJobActions(
        _image_worker_processes=lambda: _image_worker_processes,
        start_image_worker=lambda: start_image_worker,
        refresh_codex_image_job=lambda: refresh_codex_image_job,
        public_image_job=lambda: public_image_job,
        refreshed_public_codex_jobs_for_record=lambda: refreshed_public_codex_jobs_for_record,
        apply_codex_image_job_action=lambda: apply_codex_image_job_action,
        stop_candidate_image_task=lambda: stop_candidate_image_task,
    ),
)


def refresh_codex_image_job(job: dict[str, Any]) -> dict[str, Any]:
    return _image_job_management.refresh_codex_image_job(job)


def public_text(value: Any) -> str:
    return (
        str(value)
        .replace("Pose Collection", "多角度视图")
        .replace("ImageWorker", "生成任务")
        .replace("Image worker", "生成任务")
        .replace("Codex CLI", "本地生成")
        .replace("Image tool", "生成工具")
    )


def public_image_job(job: dict[str, Any]) -> dict[str, Any]:
    return _image_job_management.public_image_job(job)


from .accessories.gallery import AccessoryGallery
from .accessories.gallery_ports import GalleryAssets, GalleryStorage, GalleryDisplay
_accessory_gallery = AccessoryGallery(
    GalleryAssets(
        sources=lambda item: existing_source_image_paths(item),
        default_reference=lambda item: first_source_ai_reference_path(item),
        clean_sprites=lambda item: clean_sprite_assets(item),
        image_jobs=lambda item: candidate_image_jobs(item),
        resolve_path=lambda path: resolve_service_path(path),
        derived_paths=lambda item: accessory_image_paths(item),
    ),
    GalleryStorage(
        output_directory=lambda: OUTPUT_DIR,
        write_directory=lambda name: output_write_dir(name),
        public_url=lambda path: public_output_url(path),
    ),
    GalleryDisplay(
        public_text=lambda value: public_text(value),
        audit=lambda item, path: record_audit_fields(item, path),
        current_user=lambda: current_auth_user(),
        redact=lambda item, user: redact_accessory_payload_for_user(item, user),
    ),
    _accessory_projection, files=_business_files, images=_accessory_image_io
)


def public_accessory_detail_item(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_gallery.public_accessory_detail_item(item)


CODEX_IMAGE_JOB_PERSISTED_KEYS = (
    "status",
    "progress",
    "completed_at",
    "failed_at",
    "stopped_at",
    "error",
    "output_path",
    "output_url",
    "log_path",
    "provider",
    "generation_method",
    "generation_step",
    "queue_kind",
    "note",
    "task_id",
    "job_id",
    "candidate_id",
)


def refreshed_public_codex_jobs_for_record(
    record: dict[str, Any],
    *,
    fallback_path: Path | None = None,
    job_store: str = "candidate",
) -> tuple[list[dict[str, Any]], bool]:
    return _image_job_management.refreshed_public_codex_jobs_for_record(record, fallback_path=fallback_path, job_store=job_store)


def list_codex_image_jobs(user: dict[str, Any] | None = None, target_user_id: str | None = None) -> list[dict[str, Any]]:
    return _image_job_management.list_codex_image_jobs(user, target_user_id)


from .training.task_identity import training_task_identity_values, training_task_matches_identifier, training_task_sort_key
from .training.record_store import TrainingRecordStore, TrainingRows

_training_records = TrainingRecordStore(
    repository=lambda: runtime_postgres_repository_or_none(), directory=lambda: TRAINING_TASKS_DIR,
    guard=lambda: _training_task_lock, resolver=lambda: resolve_model_profiles,
    invalidate=lambda key: store_read_cache_invalidate(key),
    rows=TrainingRows(encode=lambda: training_task_row,
                      decode=lambda: row_raw_json_list, identifier=lambda path: file_stem_identifier(path)),
    enrich=lambda *args: enrich_record_audit_fields(*args),
)


def training_task_path(task_id: str) -> Path:
    return _training_records.training_task_path(task_id)








def load_training_task_records() -> list[dict[str, Any]]:
    return _training_records.load_training_task_records()


def save_training_task(task: dict[str, Any]) -> None:
    return _training_records.save_training_task(task)


def load_training_task(path: Path) -> dict[str, Any] | None:
    return _training_records.load_training_task(path)


def find_training_task(job_id: str) -> dict[str, Any] | None:
    return _training_records.find_training_task(job_id)


from .training.task_lifecycle import (
    training_task_uses_worker, TrainingTaskLifecycle, TrainingTaskRecords, TrainingTaskWrites,
)
from .runtime.training_tasks import TrainingTaskState
from .training.task_views import TrainingTaskViews, TrainingViewAccess

_training_lifecycle = TrainingTaskLifecycle(
    state=TrainingTaskState(guard=lambda: _training_task_lock, threads=lambda: _training_task_threads,
                            tombstones=lambda: _training_task_delete_tombstones),
    records=TrainingTaskRecords(path=lambda job_id: training_task_path(job_id), load=lambda path: load_training_task(path),
        save=lambda task: save_training_task(task), find=lambda job_id: find_training_task(job_id)),
    writes=TrainingTaskWrites(repository=lambda: runtime_postgres_repository_or_none(),
        row=lambda task, **kwargs: training_task_row(task, **kwargs), invalidate=lambda key: store_read_cache_invalidate(key)),
    require_access=lambda record, user, write=False: require_record_access(record, user, write=write),
)
_training_views = TrainingTaskViews(
    records=lambda: load_training_task_records(), refresh=lambda task: refresh_interrupted_local_training_task(task),
    access=TrainingViewAccess(enrich=lambda task: enrich_record_audit_fields(task), sanitize=lambda: public_path_sanitized,
        visible=lambda record, user, target: record_visible_to_user(record, user, target)),
)


def local_training_task_is_active(task: dict[str, Any]) -> bool:
    return _training_lifecycle.local_training_task_is_active(task)


def refresh_interrupted_local_training_task(task: dict[str, Any]) -> dict[str, Any]:
    return _training_lifecycle.refresh_interrupted_local_training_task(task)


def public_refreshed_training_task(task: dict[str, Any], *, allow_remote_refresh: bool = False) -> dict[str, Any]:
    return _training_views.public_refreshed_training_task(task, allow_remote_refresh=allow_remote_refresh)


def list_training_tasks(
    user: dict[str, Any] | None = None,
    target_user_id: str | None = None,
    *,
    allow_remote_refresh: bool = False,
) -> list[dict[str, Any]]:
    return _training_views.list_training_tasks(user, target_user_id, allow_remote_refresh=allow_remote_refresh)


def public_training_task(task: dict[str, Any]) -> dict[str, Any]:
    return _training_views.public_training_task(task)


from .training.local_process import parse_yolo_epoch_progress, yolo_cli_command


def update_training_task(job_id: str, **updates: Any) -> dict[str, Any]:
    return _training_lifecycle.update_training_task(job_id, **updates)


def stop_training_task_process(task: dict[str, Any], *, note: str) -> dict[str, Any]:
    return _training_lifecycle.stop_training_task_process(task, note=note)


def delete_training_task_record(job_id: str, user: dict[str, Any], *, missing_ok: bool = False) -> dict[str, Any] | None:
    return _training_lifecycle.delete_training_task_record(job_id, user, missing_ok=missing_ok)


def apply_codex_image_job_action(record: dict[str, Any], job: dict[str, Any], lookup_id: str, action: str) -> dict[str, Any]:
    return _image_job_management.apply_codex_image_job_action(record, job, lookup_id, action)


def update_codex_image_job(job_id: str, action: str) -> dict[str, Any]:
    return _image_job_management.update_codex_image_job(job_id, action)


def stop_candidate_image_task(candidate: dict[str, Any]) -> int:
    return _image_job_management.stop_candidate_image_task(candidate)


def update_codex_image_candidate(candidate_id: str, action: str) -> dict[str, Any]:
    return _image_job_management.update_codex_image_candidate(candidate_id, action)


def write_gallery_preview(src: Path, out_path: Path, max_side: int = 1200) -> dict[str, Any] | None:
    return _accessory_gallery.write_gallery_preview(src, out_path, max_side)


def existing_source_image_paths(item: dict[str, Any]) -> list[Path]:
    return _candidate_artifacts.existing_source_image_paths(item)


first_source_ai_reference_path = _candidate_artifacts.first_source_ai_reference_path


def ensure_default_ai_profile_reference(item: dict[str, Any]) -> bool:
    return _accessory_preparation.ensure_default_ai_profile_reference(item)


def refresh_accessory_assets_after_source_change(item: dict[str, Any], *, force_profile: bool = True) -> None:
    return _accessory_refresh.refresh_accessory_assets_after_source_change(item, force_profile=force_profile)


def accessory_detail_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_gallery.accessory_detail_payload(item)


from .accessories.catalog import AccessorySelection
from .accessories.catalog import AccessorySelectionDependencies

_accessory_selection = AccessorySelection(AccessorySelectionDependencies(
    accessory_uid=lambda: accessory_uid,
    serialize_accessory=lambda: serialize_accessory,
    accessory_lookup_by_id=lambda: accessory_lookup_by_id,
))


def selected_accessories(config: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    return _accessory_selection.selected_accessories(config, ids)


from .training.training_asset_preparation import TrainingAssetPreparation
from .training.training_asset_preparation_ports import TrainingAssetPolicy, TrainingAssetPersistence

_training_asset_preparation = TrainingAssetPreparation(
    policy=TrainingAssetPolicy(
        accessory_uid=lambda: accessory_uid,
        accessory_material_type=lambda: accessory_material_type,
        clean_sprite_assets=lambda: clean_sprite_assets,
        candidate_image_jobs=lambda: candidate_image_jobs,
        _business_files=lambda: _business_files,
        POSE_COLLECTION_GRID_POSITIONS=lambda: POSE_COLLECTION_GRID_POSITIONS,
        clean_sprites_policy_complete=lambda: clean_sprites_policy_complete,
        preprocess_object_clean_sprites=lambda: preprocess_object_clean_sprites,
        canonical_text_assets=lambda: canonical_text_assets,
        canonical_text_assets_complete=lambda: canonical_text_assets_complete,
        normalize_accessory_assets=lambda: normalize_accessory_assets,
        object_photo_highlight_source_paths=lambda: object_photo_highlight_source_paths,
        photo_highlight_clean_sprites_ready=lambda: photo_highlight_clean_sprites_ready,
        PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES=lambda: PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES,
        HTTPException=lambda: HTTPException,
    ),
    persistence=TrainingAssetPersistence(
        ensure_training_normalized_assets_for_selection=lambda: ensure_training_normalized_assets_for_selection,
        merge_scoped_accessory_updates=lambda: merge_scoped_accessory_updates,
        save_config=lambda: save_config,
    ),
)


def ensure_object_clean_sprites_for_selection(config: dict[str, Any], ids: list[str]) -> bool:
    return _training_asset_preparation.ensure_object_clean_sprites_for_selection(config, ids)


def ensure_training_normalized_assets_for_selection(config: dict[str, Any], ids: list[str]) -> bool:
    return _training_asset_preparation.ensure_training_normalized_assets_for_selection(config, ids)


def ensure_training_assets_for_request(
    full_config: dict[str, Any],
    scoped_config: dict[str, Any],
    user: dict[str, Any],
    ids: list[str],
) -> bool:
    return _training_asset_preparation.ensure_training_assets_for_request(full_config, scoped_config, user, ids)


def physical_render_size_px(item: dict[str, Any], material_type: str) -> tuple[int, int]:
    return _reference_dimensions.physical_render_size_px(item, material_type)


def physical_render_size_for_sprite(item: dict[str, Any], material_type: str, sprite_meta: dict[str, Any] | None = None) -> tuple[int, int]:
    return sprite_render_size_px(item, sprite_meta, material_type)


from .training.preview_geometry import (constrained_center_range, polygon_max_pair_distance_px,
                                        rotated_rect_overlap_area, rotated_rect_tuple)
from .training.preview_masks import PreviewMasks, contour_to_polygon, mask_from_polygon
from .training.preview_placement import PreviewPlacement

_preview_masks = PreviewMasks(
    lambda: contour_to_polygon,
    lambda mask, ratio: visible_polygons_from_mask(mask, ratio),
)
_preview_placement = PreviewPlacement(
    lambda: PREVIEW_CANVAS_SIZE_PX,
    lambda: constrained_center_range,
    lambda center, size, angle: rotated_rect_tuple(center, size, angle),
    lambda: rotated_rect_overlap_area,
    lambda rng, size, angle, roi: random_center_inside_background(rng, size, angle, roi),
    lambda center, size, angle, placed: object_placement_overlap_area(center, size, angle, placed),
)


def random_center_inside_background(
    rng: np.random.Generator,
    target_size: tuple[int, int],
    angle: float,
    roi: tuple[int, int, int, int] = BACKGROUND_ROI_PX,
) -> tuple[int, int]:
    return _preview_placement.random_center_inside_background(rng, target_size, angle, roi)






def object_placement_overlap_area(
    center: tuple[int, int],
    target_size: tuple[int, int],
    angle: float,
    placed_objects: list[dict[str, Any]],
) -> float:
    return _preview_placement.object_placement_overlap_area(center, target_size, angle, placed_objects)


def choose_object_center_inside_background(
    rng: np.random.Generator,
    target_size: tuple[int, int],
    angle: float,
    placed_objects: list[dict[str, Any]],
    roi: tuple[int, int, int, int] = BACKGROUND_ROI_PX,
) -> tuple[tuple[int, int], dict[str, Any]]:
    return _preview_placement.choose_object_center_inside_background(rng, target_size, angle, placed_objects, roi)


def placement_box_points(center: tuple[int, int], target_size: tuple[int, int], angle: float) -> list[list[int]]:
    return _preview_placement.placement_box_points(center, target_size, angle)






def visible_polygons_from_mask(mask: np.ndarray, epsilon_ratio: float = 0.0035) -> list[list[list[int]]]:
    return _preview_masks.visible_polygons_from_mask(mask, epsilon_ratio)


def visible_polygon_from_mask(mask: np.ndarray, epsilon_ratio: float = 0.0035) -> list[list[int]]:
    return _preview_masks.visible_polygon_from_mask(mask, epsilon_ratio)




from .training.background_library import BackgroundPaths, BackgroundSetLookup, TrainingBackgroundLibrary
from .training.background_rendering import (TrainingBackgroundRenderer, augment_training_background,
                                          background_candidates_for_split, fit_training_background_to_canvas,
                                          synthetic_training_background)

_training_background_library = TrainingBackgroundLibrary(
    BackgroundPaths(lambda: BACKGROUND_DIR, lambda: DEFAULT_BACKGROUND_IMAGE,
                    lambda: IMAGE_REFERENCE_SUFFIXES),
    BackgroundSetLookup(lambda: load_training_background_manifest(),
                        lambda requested: selected_background_set_id(requested),
                        lambda selected: background_set_image_files(selected)),
    files=_business_files,
)
_background_image_io = ImageFiles(lambda: cv2, files=_business_files)
_training_background_renderer = TrainingBackgroundRenderer(
    lambda selected: training_background_library(selected),
    lambda library, split: background_candidates_for_split(library, split),
    lambda rng: synthetic_training_background(rng),
    lambda image, rng: fit_training_background_to_canvas(image, rng),
    lambda canvas, rng: augment_training_background(canvas, rng),
    images=_background_image_io,
)


def load_training_background_manifest() -> dict[str, Any]:
    return _training_background_library.load_training_background_manifest()


from .training.background_manifest import BackgroundManifest
from .training.background_catalog import (
    safe_background_set_id, BackgroundImageFiles, BackgroundCatalogPaths,
    BackgroundCatalogRecords, BackgroundCatalogAccess, BackgroundCatalog,
)
from .training.background_seeding import BackgroundSeedPaths, BackgroundSeeding
from .training.background_selection import BackgroundSelection

_background_manifest = BackgroundManifest(lambda: BACKGROUND_DIR, lambda: BACKGROUND_SETS_MANIFEST, files=_business_files)
_background_image_files = BackgroundImageFiles(lambda: IMAGE_REFERENCE_SUFFIXES, files=_business_files)
_background_seeding = BackgroundSeeding(
    BackgroundSeedPaths(lambda: DEFAULT_BACKGROUND_IMAGE, lambda: BACKGROUND_SETS_DIR),
    lambda: load_background_sets_manifest(), lambda manifest: write_background_sets_manifest(manifest),
    lambda identifier: ensure_background_set_minimum_images(identifier), lambda: seed_default_background_set(), lambda: time.time(),
    files=_business_files,
)
_background_catalog = BackgroundCatalog(
    BackgroundCatalogPaths(lambda: BACKGROUND_SETS_DIR, lambda: OUTPUT_DIR),
    BackgroundCatalogRecords(lambda: load_background_sets_manifest(), lambda: background_set_dirs(),
                             lambda: background_set_payload),
    BackgroundCatalogAccess(lambda: SYSTEM_OWNER_ID, lambda meta, path: record_audit_fields(meta, path),
                            lambda item, user, target: record_visible_to_user(item, user, target)),
    lambda identifier: safe_background_set_id(identifier), lambda path: image_file_list(path), lambda path: public_output_url(path),
)
_background_selection = BackgroundSelection(
    lambda: safe_background_set_id, lambda user, target: list_background_sets(user, target),
    lambda: load_background_sets_manifest(), lambda identifier: selected_background_set_id(identifier),
    lambda: image_file_list, lambda: BACKGROUND_SETS_DIR,
)
def load_background_sets_manifest() -> dict[str, Any]:
    return _background_manifest.load_background_sets_manifest()
def write_background_sets_manifest(manifest: dict[str, Any]) -> None:
    return _background_manifest.write_background_sets_manifest(manifest)
def image_file_list(path: Path) -> list[Path]:
    return _background_image_files.image_file_list(path)
def seed_default_background_set() -> None:
    return _background_seeding.seed_default_background_set()
def background_set_dirs() -> list[Path]:
    return _background_seeding.background_set_dirs()
def background_set_payload(set_id: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return _background_catalog.background_set_payload(set_id, meta)
def list_background_sets(user: dict[str, Any] | None = None, target_user_id: str | None = None) -> list[dict[str, Any]]:
    return _background_catalog.list_background_sets(user, target_user_id)
def selected_background_set_id(
    background_set_id: str | None,
    user: dict[str, Any] | None = None,
    target_user_id: str | None = None,
) -> str | None:
    return _background_selection.selected_background_set_id(background_set_id, user, target_user_id)
def background_set_image_files(background_set_id: str | None) -> list[Path]:
    return _background_selection.background_set_image_files(background_set_id)
from .training.background_variants import BackgroundVariants, BackgroundMinimumImages
from .training.background_writes import BackgroundWrites
from .training.task_background_store import (
    TaskBackgroundIdentity, TaskBackgroundPaths, TaskBackgroundRecords, TaskBackgroundStore,
)

_background_variants = BackgroundVariants(lambda: time.time(), images=_background_image_io)
_background_minimum_images = BackgroundMinimumImages(
    lambda identifier: safe_background_set_id(identifier), lambda: BACKGROUND_SETS_DIR,
    lambda path: image_file_list(path),
    lambda: create_background_variants_from_source,
)
_background_writes = BackgroundWrites(
    lambda identifier: safe_background_set_id(identifier), lambda: load_background_sets_manifest(),
    lambda manifest: write_background_sets_manifest(manifest), lambda: BACKGROUND_SETS_DIR,
    lambda: uuid.uuid4(), lambda: time.time(),
    files=_business_files,
)
_task_background_store = TaskBackgroundStore(
    TaskBackgroundIdentity(lambda identifier: sanitize_ai_detection_task_id(identifier),
                           lambda identifier: safe_record_id(identifier), lambda: safe_background_set_id,
                           lambda: LEGACY_OWNER_ID),
    TaskBackgroundPaths(lambda: BACKGROUND_SETS_DIR, lambda: IMAGE_REFERENCE_SUFFIXES),
    TaskBackgroundRecords(lambda: update_background_set_manifest,
                          lambda identifier, meta: background_set_payload(identifier, meta)),
    lambda source_path, set_dir, count=5: create_background_variants_from_source(source_path, set_dir, count=count),
    lambda path: image_file_list(path), lambda: time.time(), files=_business_files
)

def create_background_variants_from_source(source_path: Path, set_dir: Path, count: int = 5) -> list[Path]:
    return _background_variants.create_background_variants_from_source(source_path, set_dir, count)
from .training.background_codex import CodexBackgroundPaths, CodexBackgroundGeneration, CodexBackgroundThread
from .training.background_task_runner import BackgroundTaskRecords, BackgroundTaskGeneration, BackgroundTaskRunner
from .training.background_task_submission import BackgroundTaskSubmission
from .training.submission import TrainingSubmissionRecords, TrainingSubmissionThreads

_background_codex_generation = CodexBackgroundGeneration(
    lambda command: shutil.which(command), CodexBackgroundPaths(lambda: IMAGE_WORKER_LOG_DIR, lambda: ROOT),
    lambda identifier: safe_name(identifier), lambda: subprocess.Popen,
    files=_business_files,
)
_background_codex_thread = CodexBackgroundThread(
    lambda: threading.Thread, lambda: run_codex_background_generation, lambda identifier: safe_name(identifier),
    runtime=TrainingThreadLifecycle(scope=_runtime_repositories.thread_scope),
)
_background_task_runner = BackgroundTaskRunner(
    BackgroundTaskRecords(lambda identifier: find_training_task(identifier), lambda identifier: training_task_path(identifier),
                          lambda: load_training_task, lambda: update_training_task),
    BackgroundTaskGeneration(lambda: BACKGROUND_SETS_DIR, lambda identifier: safe_background_set_id(identifier),
                            lambda: update_background_set_manifest,
                            lambda source_path, set_dir, count=5: create_background_variants_from_source(source_path, set_dir, count),
                            lambda source_path, set_dir, set_id, count=5: run_codex_background_generation(source_path, set_dir, set_id, count), lambda path: image_file_list(path)),
    lambda: time.time(), resolve_model_profiles,
    files=_business_files,
)
_background_task_submission = BackgroundTaskSubmission(
    TrainingSubmissionRecords(lambda task: save_training_task(task), lambda task: public_training_task(task)),
    TrainingSubmissionThreads(lambda: run_background_set_task, lambda **kwargs: threading.Thread(**kwargs), lambda: _training_task_threads),
    lambda: current_owner_fields(), lambda: time.time(), lambda: uuid.uuid4(),
    runtime=_training_task_runtime,
)

def run_codex_background_generation(source_path: Path, set_dir: Path, set_id: str, count: int = 5) -> list[Path]:
    return _background_codex_generation.run_codex_background_generation(source_path, set_dir, set_id, count)
def start_codex_background_generation(source_path: Path, set_dir: Path, set_id: str, count: int = 5) -> None:
    return _background_codex_thread.start_codex_background_generation(source_path, set_dir, set_id, count)
def ensure_background_set_minimum_images(set_id: str, min_count: int = 6) -> None:
    return _background_minimum_images.ensure_background_set_minimum_images(set_id, min_count)
def unique_background_set_id(base_id: str) -> str:
    return _background_writes.unique_background_set_id(base_id)
def update_background_set_manifest(set_id: str, **updates: Any) -> dict[str, Any]:
    return _background_writes.update_background_set_manifest(set_id, **updates)
def save_task_environment_background_set(task_id: str, source_path: Path, user: dict[str, Any], display_name: str = "") -> dict[str, Any]:
    return _task_background_store.save_task_environment_background_set(task_id, source_path, user, display_name)
from .training.background_validation import BackgroundValidation

_background_validation = BackgroundValidation(
    lambda identifier: sanitize_ai_detection_task_id(identifier), lambda: AI_DETECTION_TASK_PREFIX,
    lambda: time.time(), lambda: uuid.uuid4(),
    lambda image, request_id, model_id=None, **kwargs: analyze_bgr(image, request_id, model_id, **kwargs),
    lambda: bounded_text,
    images=_background_image_io,
)

def validate_task_environment_background_image(task_id: str, task: dict[str, Any], source_path: Path) -> dict[str, Any]:
    return _background_validation.validate_task_environment_background_image(task_id, task, source_path)
def run_background_set_task(job_id: str) -> None:
    return _background_task_runner.run_background_set_task(job_id)
def enqueue_background_set_task(set_id: str, name: str, source_path: Path) -> dict[str, Any]:
    return _background_task_submission.enqueue_background_set_task(set_id, name, source_path)
def training_background_library(background_set_id: str | None = None) -> list[dict[str, Any]]:
    return _training_background_library.training_background_library(background_set_id)










def render_training_background(
    rng: np.random.Generator,
    split: str | None = None,
    background_set_id: str | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    return _training_background_renderer.render_training_background(rng, split, background_set_id)


from .training.preview_ports import (PreviewAssets, PreviewLayout, PreviewPoses, PreviewSizes,
                                     PreviewSurface, PreviewThresholds)
from .training.preview_renderer import PreviewRenderer

_training_image_io = ImageFiles(lambda: cv2, files=_business_files)
_training_preview_renderer = PreviewRenderer(
    material=lambda item: accessory_material_type(item),
    surface=PreviewSurface(
        background=lambda rng, split, selected: render_training_background(rng, split, selected),
        public_url=lambda path: public_output_url(path),
    ),
    assets=PreviewAssets(
        document=lambda item, rng: load_rectified_document_asset_with_metadata(item, rng),
        generic=lambda item: load_preview_asset_with_metadata(item),
        sprites=lambda item: clean_sprite_assets(item),
        object_sprite=lambda: load_object_preview_sprite,
        restore=lambda: restore_object_sprite_source_orientation_for_render,
        paste_document=lambda canvas, image, center, size, angle: paste_rectified_document_asset(canvas, image, center, size, angle),
        paste_object=lambda canvas, image, mask, center, long, short, angle, **kwargs: paste_physical_object_asset(canvas, image, mask, center, long, short, angle, **kwargs),
    ),
    sizes=PreviewSizes(
        physical=lambda item, material: physical_render_size_px(item, material),
        sprite=lambda item, material, metadata: physical_render_size_for_sprite(item, material, metadata),
        pose=lambda: object_pose_render_size_hint,
        visible=lambda mask: visible_mask_size_px(mask),
        unified=lambda: long_axis_unified_render_box,
    ),
    poses=PreviewPoses(
        available=lambda item: available_object_pose_families(item),
        choose=lambda sprites, rng: choose_object_pose_family(sprites, rng),
        policy=lambda family, rng: object_render_pose_policy(family, rng),
        top_view=lambda: pose_family_is_top_view,
        position=lambda center: grid_position_for_center(center),
        source=lambda target, angle, family, rng: source_position_for_render_policy(target, angle, family, rng),
        reason=lambda target, source, angle: pose_selection_reason(target, source, angle),
    ),
    layout=PreviewLayout(
        random_center=lambda rng, size, angle: random_center_inside_background(rng, size, angle),
        choose_center=lambda rng, size, angle, placed: choose_object_center_inside_background(rng, size, angle, placed),
        mask=lambda: mask_from_polygon,
        box=lambda center, size, angle: placement_box_points(center, size, angle),
        rectangle=lambda center, size, angle: rotated_rect_tuple(center, size, angle),
        polygon=lambda mask: visible_polygon_from_mask(mask),
        max_distance=lambda polygon: polygon_max_pair_distance_px(polygon),
    ),
    thresholds=PreviewThresholds(lambda: DETECTION_MIN_VISIBLE_AREA_PX, lambda: DETECTION_MAX_OCCLUSION_FRACTION), images=_training_image_io
)


def draw_training_preview(
    accessories: list[dict[str, Any]],
    output_path: Path,
    seed: int,
    pose_family_policy: str | None = None,
    split: str | None = None,
    background_set_id: str | None = None,
) -> dict[str, Any]:
    return _training_preview_renderer.draw_training_preview(accessories, output_path, seed, pose_family_policy, split, background_set_id)


from .training.estimates import training_estimate
from .training.annotations import (
    AnnotationMedia, AnnotationPreview, TrainingOutputLinks, yolo_label_line, yolo_detection_label_line, write_dataset_yaml as _write_dataset_yaml,
)
from .training.sample_plan import SamplePlanner, split_counts, missing_count_for_false_sample
from .training.dataset_generation import DatasetGenerator, DatasetRecords, DatasetPlanning, DatasetRendering

def write_dataset_yaml(path: Path, dataset_dir: Path, names: list[str]) -> None:
    return _write_dataset_yaml(path, dataset_dir, names, files=_business_files)


_training_output_links = TrainingOutputLinks(AnnotationMedia(
    output_root=lambda: OUTPUT_DIR, public_url=lambda path: public_output_url(path),
))
_training_annotation_preview = AnnotationPreview(public_url=lambda path: public_training_output_url(path), images=_training_image_io)
_training_sample_planner = SamplePlanner(
    split=lambda count: split_counts(count),
    missing=lambda count, rng: missing_count_for_false_sample(count, rng),
    poses=lambda selected, count, policy: preview_pose_family_sequence(selected, count, policy),
)
_training_dataset_generator = DatasetGenerator(
    DatasetRecords(
        load=lambda: load_config(), save=lambda config: save_config(config),
        normalize_assets=lambda config, ids: ensure_training_normalized_assets_for_selection(config, ids),
        select=lambda config, ids: selected_accessories(config, ids), uses_ocr=lambda item: accessory_uses_ocr(item),
    ),
    DatasetPlanning(
        normalize_pose=lambda: normalize_preview_pose_family_policy,
        background=lambda: selected_background_set_id,
        build=lambda selected, count, seed, policy: build_training_sample_plan(selected, count, seed, policy),
    ),
    DatasetRendering(
        draw=lambda: draw_training_preview,
        label=lambda: yolo_detection_label_line,
        annotation=lambda: write_training_annotation_preview,
        yaml=lambda path, directory, names: write_dataset_yaml(path, directory, names),
        max_occlusion=lambda: DETECTION_MAX_OCCLUSION_FRACTION,
        min_visible_area=lambda: DETECTION_MIN_VISIBLE_AREA_PX,
    ),
    output=lambda: output_write_dir_for_owner,
    update_provider=lambda: update_training_task, files=_business_files
)














def build_training_sample_plan(
    selected: list[dict[str, Any]],
    sample_count: int,
    seed: int,
    pose_policy: str,
) -> list[dict[str, Any]]:
    return _training_sample_planner.build_training_sample_plan(selected, sample_count, seed, pose_policy)


def public_training_output_url(path: Path) -> str:
    return _training_output_links.public_training_output_url(path)


def write_training_annotation_preview(image_path: Path, labels: list[dict[str, Any]], out_path: Path) -> str:
    return _training_annotation_preview.write_training_annotation_preview(image_path, labels, out_path)


def generate_training_dataset(task: dict[str, Any]) -> dict[str, Any]:
    return _training_dataset_generator.generate_training_dataset(task)


_training_executor_settings = ExecutorSettings(
    environment=lambda: os.environ, mask_url=lambda value: masked_url_for_status(value),
)


def training_executor_mode() -> str:
    return _training_executor_settings.training_executor_mode()


def worker_local_training_fallback_enabled() -> bool:
    return _training_executor_settings.worker_local_training_fallback_enabled()




def validate_remote_training_endpoint(value: Any) -> str:
    return _training_executor_settings.validate_remote_training_endpoint(value)


def validate_windows_worker_base_url(value: Any) -> str:
    return _training_executor_settings.validate_windows_worker_base_url(value)


def remote_training_endpoint() -> str:
    return _training_executor_settings.remote_training_endpoint()


def windows_worker_base_url() -> str:
    return _training_executor_settings.windows_worker_base_url()


def remote_training_timeout_seconds() -> float:
    return _training_executor_settings.remote_training_timeout_seconds()


def windows_worker_timeout_seconds() -> float:
    return _training_executor_settings.windows_worker_timeout_seconds()


def windows_worker_image_timeout_seconds() -> float:
    return _training_executor_settings.windows_worker_image_timeout_seconds()


def windows_worker_headers() -> dict[str, str]:
    return _training_executor_settings.windows_worker_headers()


from .training.legacy_worker_requests import LegacyWorkerSettings, LegacyWorkerRequests, windows_worker_status as _retired_worker_status

_legacy_worker_requests = LegacyWorkerRequests(
    LegacyWorkerSettings(lambda: windows_worker_base_url(), lambda: windows_worker_headers(), lambda: windows_worker_timeout_seconds()),
    lambda *args, **kwargs: requests.request(*args, **kwargs),
    lambda *args, **kwargs: windows_worker_request(*args, **kwargs), lambda seconds: time.sleep(seconds),
)

def windows_worker_request(method: str, path: str, *, json_body: dict[str, Any] | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
    return _legacy_worker_requests.windows_worker_request(method, path, json_body=json_body, timeout_seconds=timeout_seconds)
def windows_worker_form_request(
    method: str,
    path: str,
    *,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    return _legacy_worker_requests.windows_worker_form_request(method, path, data=data, files=files, timeout_seconds=timeout_seconds)
def windows_worker_status(*, force: bool = False, probe: bool = True, include_services: bool = False) -> dict[str, Any]:
    return _retired_worker_status(force=force, probe=probe, include_services=include_services)
def training_execution_status(*, include_worker_probe: bool = False, include_worker_services: bool = False) -> dict[str, Any]:
    return _training_executor_settings.training_execution_status(include_worker_probe=include_worker_probe, include_worker_services=include_worker_services)


from .training.dataset_archives import DatasetArchives, file_sha256 as strict_training_file_sha256
from .training.runpod_exports import RunPodExports, RunPodExportPaths, RunPodExportPolicy
from .training.runpod_artifacts import RunPodArtifacts, RunPodArtifactPaths

_training_dataset_archives = DatasetArchives(
    safe_name=lambda name: safe_name(name), skip_dirs=lambda: WORKER_BUNDLE_SKIP_DIRS,
    jpeg_quality=lambda: WORKER_BUNDLE_JPEG_QUALITY, digest=lambda path: file_sha256(path), runtime_provider=lambda: _business_files.runtime_provider()
)
_runpod_exports = RunPodExports(
    RunPodExportPaths(
        resolve=lambda: resolve_service_path, output=lambda kind, owner: output_write_dir_for_owner(kind, owner),
        safe_name=lambda value: safe_name(value),
    ),
    RunPodExportPolicy(
        token_hash=lambda token: runpod_dataset_token_hash(token), ttl=lambda: runpod_yolo_dataset_token_ttl_seconds(),
        public_base=lambda: runpod_yolo_public_base_url(),
    ),
    bundle=lambda directory, job: build_worker_training_bundle(directory, job), digest=lambda path: file_sha256(path),
    update_provider=lambda: update_training_task,
)
_runpod_artifacts = RunPodArtifacts(
    RunPodArtifactPaths(
        resolve=lambda value: resolve_service_path(value), output_root=lambda: OUTPUT_DIR,
        output=lambda: output_write_dir_for_owner,
    ),
    find=lambda job: find_training_task(job), summary=lambda value: runpod_public_response_summary(value),
)


def package_training_dataset(dataset_dir: Path, job_id: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    return _training_dataset_archives.package_training_dataset(dataset_dir, job_id)


# Directories inside a generated dataset that the remote trainer never needs.
# `previews/` holds UI-only annotated JPEGs; shipping them just inflates the
# cross-region upload that has to reach the Windows worker.
WORKER_BUNDLE_SKIP_DIRS = {"previews", "preview", "debug", "thumbnails", "thumbs"}
WORKER_BUNDLE_JPEG_QUALITY = 90


def build_worker_training_bundle(dataset_dir: Path, job_id: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    return _training_dataset_archives.build_worker_training_bundle(dataset_dir, job_id)


# Retain the original late override of the earlier best-effort hash helper.
def file_sha256(path: Path) -> str:
    return strict_training_file_sha256(path, files=_business_files)


def dataset_file_manifest(dataset_dir: Path) -> list[dict[str, Any]]:
    return _training_dataset_archives.dataset_file_manifest(dataset_dir)


from .training.worker_bundle_metadata import WorkerBundleMetadata
from .training.worker_bundle_submission import WorkerBundleFiles, WorkerBundleTransport, WorkerBundleTimeout, WorkerBundleSubmission

_worker_bundle_metadata = WorkerBundleMetadata(lambda path: file_sha256(path), lambda path: dataset_file_manifest(path))
_worker_bundle_timeout = WorkerBundleTimeout(lambda: remote_training_timeout_seconds())
_worker_bundle_submission = WorkerBundleSubmission(
    WorkerBundleFiles(lambda: resolve_service_path, lambda path, job_id: build_worker_training_bundle(path, job_id),
                      lambda *args: worker_training_bundle_metadata(*args)),
    WorkerBundleTransport(lambda: worker_training_upload_timeout_seconds(), lambda *args, **kwargs: _start_transfer_progress_thread(*args, **kwargs),
                          lambda *args, **kwargs: windows_worker_upload_bundle_streamed(*args, **kwargs),
                          lambda: windows_worker_form_request),
    lambda: update_training_task, lambda: time.time(), lambda seconds: time.sleep(seconds),
)

def worker_training_bundle_metadata(job_id: str, task: dict[str, Any], dataset: dict[str, Any], dataset_dir: Path, archive_path: Path) -> dict[str, Any]:
    return _worker_bundle_metadata.worker_training_bundle_metadata(job_id, task, dataset, dataset_dir, archive_path)
def worker_training_upload_timeout_seconds() -> float:
    # The bundle upload travels over a cross-region Tailscale link; give it a
    # generous ceiling so a slow-but-progressing transfer is not killed.
    return _worker_bundle_timeout.worker_training_upload_timeout_seconds()
from .training.worker_transfers import WorkerTransfers
from .training.transfer_progress import TransferProgress

_worker_transfers = WorkerTransfers(
    lambda: windows_worker_base_url(), lambda: windows_worker_headers(),
    lambda *args, **kwargs: requests.post(*args, **kwargs),
    lambda: requests.get, lambda: uuid.uuid4(),
)
_transfer_progress = TransferProgress(
    lambda: update_training_task,
    lambda: threading.Event(), lambda: threading.Thread,
    runtime=TrainingThreadLifecycle(scope=_runtime_repositories.thread_scope),
)

def windows_worker_upload_bundle_streamed(
    path: str,
    *,
    metadata_json: str,
    archive_path: Path,
    state: dict[str, int],
    timeout_seconds: float,
) -> dict[str, Any]:
    return _worker_transfers.windows_worker_upload_bundle_streamed(path, metadata_json=metadata_json, archive_path=archive_path, state=state, timeout_seconds=timeout_seconds)
def post_worker_training_bundle(job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    return _worker_bundle_submission.post_worker_training_bundle(job_id, task, dataset)
from .training.remote_training import RemoteTrainingSettings, RemoteTrainingPaths, RemoteTraining
from .training.worker_compatibility import worker_training_payload, worker_training_terminal_status, WorkerArtifactSummary

_remote_training = RemoteTraining(
    RemoteTrainingSettings(lambda: remote_training_endpoint(), lambda value: masked_url_for_status(value),
                           lambda: os.environ, lambda: remote_training_timeout_seconds()),
    RemoteTrainingPaths(lambda: resolve_service_path, lambda path, job_id: package_training_dataset(path, job_id)),
    lambda: update_training_task, lambda: requests.post, lambda: time.time(),
)
_worker_artifact_summary = WorkerArtifactSummary(lambda value: public_path_sanitized(value))

def run_remote_training_task(job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> None:
    return _remote_training.run_remote_training_task(job_id, task, dataset)
def runpod_yolo_endpoint_id() -> str:
    return _training_executor_settings.runpod_yolo_endpoint_id()


def runpod_yolo_api_key() -> str:
    return _training_executor_settings.runpod_yolo_api_key()


def runpod_yolo_api_base() -> str:
    return _training_executor_settings.runpod_yolo_api_base()


def runpod_yolo_public_base_url() -> str:
    return _training_executor_settings.runpod_yolo_public_base_url()


def runpod_yolo_job_timeout_seconds() -> int:
    return _training_executor_settings.runpod_yolo_job_timeout_seconds()


def runpod_yolo_client_timeout_seconds() -> float:
    return _training_executor_settings.runpod_yolo_client_timeout_seconds()


def runpod_yolo_poll_interval_seconds() -> float:
    return _training_executor_settings.runpod_yolo_poll_interval_seconds()


def runpod_yolo_dataset_token_ttl_seconds() -> int:
    return _training_executor_settings.runpod_yolo_dataset_token_ttl_seconds()


def runpod_yolo_inline_dataset_max_bytes() -> int:
    return _training_executor_settings.runpod_yolo_inline_dataset_max_bytes()


def runpod_yolo_artifact_max_bytes() -> int:
    return _training_executor_settings.runpod_yolo_artifact_max_bytes()


def runpod_yolo_url(path: str) -> str:
    return _training_executor_settings.runpod_yolo_url(path)


def runpod_yolo_authorization_values() -> list[str]:
    return _training_executor_settings.runpod_yolo_authorization_values()


from .training.runpod_client import RunPodClient, RunPodRequestSettings, runpod_dataset_token_hash

_runpod_client = RunPodClient(
    settings=RunPodRequestSettings(url=lambda path: runpod_yolo_url(path), authorization=lambda: runpod_yolo_authorization_values(),
                                  timeout=lambda: runpod_yolo_client_timeout_seconds()),
    request=lambda: requests.request,
    bound_text=lambda: bounded_text,
)


def runpod_yolo_http_request(method: str, path: str, *, json_body: dict[str, Any] | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
    return _runpod_client.runpod_yolo_http_request(method, path, json_body=json_body, timeout_seconds=timeout_seconds)


def runpod_public_response_summary(value: Any) -> Any:
    return _runpod_client.runpod_public_response_summary(value)




def create_runpod_training_dataset_archive(job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    return _runpod_exports.create_runpod_training_dataset_archive(job_id, task, dataset)


def create_runpod_training_artifact_upload(job_id: str, task: dict[str, Any]) -> dict[str, Any]:
    return _runpod_exports.create_runpod_training_artifact_upload(job_id, task)


from .training.runpod_submission import RunPodPayload, RunPodSubmission
from .training.runpod_outputs import RunPodOutputParser, runpod_terminal_status
from .training.runpod_flow import RunPodFlow, RunPodFlowSettings, RunPodFlowRecords, RunPodFlowInputs, RunPodFlowResults

_runpod_payload = RunPodPayload(
    upload=lambda job, task: create_runpod_training_artifact_upload(job, task),
    timeout=lambda: runpod_yolo_job_timeout_seconds(), inline_limit=lambda: runpod_yolo_inline_dataset_max_bytes(),
    environment=lambda: os.environ,
)
_runpod_submission = RunPodSubmission(
    timeout=lambda: runpod_yolo_job_timeout_seconds(), ttl=lambda: runpod_yolo_dataset_token_ttl_seconds(),
    request=lambda method, path, **kwargs: runpod_yolo_http_request(method, path, **kwargs),
)
_runpod_output_parser = RunPodOutputParser(bound_text=lambda: bounded_text)
_runpod_flow = RunPodFlow(
    RunPodFlowSettings(
        endpoint=lambda: runpod_yolo_endpoint_id(), timeout=lambda: runpod_yolo_job_timeout_seconds(),
        ttl=lambda: runpod_yolo_dataset_token_ttl_seconds(), poll=lambda: runpod_yolo_poll_interval_seconds(),
    ),
    RunPodFlowRecords(
        update_provider=lambda: update_training_task, sync=lambda job: sync_training_state_from_task(job),
        warmup=lambda: start_yolo_warmup,
    ),
    RunPodFlowInputs(
        archive=lambda job, task, dataset: create_runpod_training_dataset_archive(job, task, dataset),
        payload=lambda job, task, archive: runpod_training_input_payload(job, task, archive),
        submit=lambda payload: submit_runpod_yolo_training(payload),
    ),
    RunPodFlowResults(
        request=lambda: runpod_yolo_http_request,
        summary=lambda value: runpod_public_response_summary(value), extract=lambda value: extract_runpod_worker_output(value),
        import_artifacts=lambda: import_runpod_yolo_artifacts,
        terminal=lambda: runpod_terminal_status, bound_text=lambda: bounded_text,
    ),
)


def runpod_training_input_payload(job_id: str, task: dict[str, Any], archive: dict[str, Any]) -> dict[str, Any]:
    return _runpod_payload.runpod_training_input_payload(job_id, task, archive)


def submit_runpod_yolo_training(payload: dict[str, Any]) -> dict[str, Any]:
    return _runpod_submission.submit_runpod_yolo_training(payload)


def extract_runpod_worker_output(status_body: dict[str, Any]) -> dict[str, Any]:
    return _runpod_output_parser.extract_runpod_worker_output(status_body)


def import_runpod_yolo_artifacts(task: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    return _runpod_artifacts.import_runpod_yolo_artifacts(task, output)




def run_runpod_training_task(job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> None:
    return _runpod_flow.run_runpod_training_task(job_id, task, dataset)


from .training.legacy_worker_tasks import LegacyWorkerTaskPorts, LegacyWorkerTasks
from .training.legacy_worker_refresh import LegacyRefreshRecords, LegacyRefreshTransfer, LegacyRefreshArtifacts, LegacyWorkerRefresh

_legacy_worker_tasks = LegacyWorkerTasks(
    lambda: update_training_task, lambda: time.time(),
    LegacyWorkerTaskPorts(lambda: windows_worker_base_url(), lambda value: masked_url_for_status(value),
                          lambda *args, **kwargs: windows_worker_request_with_retry(*args, **kwargs), lambda task: worker_training_payload(task),
                          lambda *args: post_worker_training_bundle(*args), lambda value: public_path_sanitized(value)),
)
_legacy_worker_refresh = LegacyWorkerRefresh(
    LegacyRefreshRecords(lambda task: public_training_task(task), lambda: update_training_task,
                         lambda value: public_path_sanitized(value), lambda: IMAGE_JOB_ACTIVE_STATUSES),
    LegacyRefreshTransfer(lambda *args, **kwargs: windows_worker_request(*args, **kwargs), lambda *args, **kwargs: _start_transfer_progress_thread(*args, **kwargs),
                          lambda *args, **kwargs: windows_worker_get_json_streamed(*args, **kwargs), lambda: worker_training_upload_timeout_seconds()),
    LegacyRefreshArtifacts(lambda item: worker_training_artifact_summary(item), lambda task, artifacts: import_worker_training_artifacts(task, artifacts)),
    lambda: time.time(),
)

def run_worker_dataset_generation_task(job_id: str, task: dict[str, Any]) -> None:
    return _legacy_worker_tasks.run_worker_dataset_generation_task(job_id, task)
def run_worker_training_task(job_id: str, task: dict[str, Any], dataset: dict[str, Any] | None = None) -> None:
    return _legacy_worker_tasks.run_worker_training_task(job_id, task, dataset)
def worker_training_artifact_summary(item: dict[str, Any]) -> dict[str, Any]:
    return _worker_artifact_summary.worker_training_artifact_summary(item)
from .training.worker_artifacts import WorkerArtifactImport

_worker_artifact_import = WorkerArtifactImport(
    lambda: output_write_dir_for_owner, lambda: safe_name, lambda: time.time(),
)

def import_worker_training_artifacts(task: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    return _worker_artifact_import.import_worker_training_artifacts(task, artifacts)
def _start_transfer_progress_thread(
    job_id: str,
    state: dict[str, int],
    *,
    done_field: str,
    total_field: str,
    status_field: str,
    interval: float = 1.5,
) -> tuple[threading.Event, threading.Thread]:
    return _transfer_progress._start_transfer_progress_thread(job_id, state, done_field=done_field, total_field=total_field, status_field=status_field, interval=interval)
def windows_worker_get_json_streamed(path: str, *, state: dict[str, int], timeout_seconds: float) -> dict[str, Any]:
    return _worker_transfers.windows_worker_get_json_streamed(path, state=state, timeout_seconds=timeout_seconds)
def refresh_worker_training_task(task: dict[str, Any], *, include_artifacts: bool = False) -> dict[str, Any]:
    return _legacy_worker_refresh.refresh_worker_training_task(task, include_artifacts=include_artifacts)
def windows_worker_request_with_retry(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
    attempts: int = 3,
    backoff_seconds: float = 4.0,
) -> dict[str, Any]:
    return _legacy_worker_requests.windows_worker_request_with_retry(method, path, json_body=json_body, timeout_seconds=timeout_seconds, attempts=attempts, backoff_seconds=backoff_seconds)
from .training.worker_watcher import (
    worker_training_watcher_enabled as _retired_worker_watcher_enabled,
    _worker_training_watch_once as _retired_worker_watch_once,
    start_worker_training_watcher as _retired_worker_watcher_start,
    WorkerWatcherSettings, WorkerWatcherLoop,
)

_worker_watcher_settings = WorkerWatcherSettings(lambda: os.environ)
_worker_watcher_loop = WorkerWatcherLoop(
    lambda: worker_training_watcher_interval_seconds(), lambda: _worker_training_watch_once(),
    lambda: traceback.print_exc(file=sys.stderr), lambda seconds: time.sleep(seconds),
)

def worker_training_watcher_enabled() -> bool:
    return _retired_worker_watcher_enabled()
def worker_training_watcher_interval_seconds() -> float:
    return _worker_watcher_settings.worker_training_watcher_interval_seconds()
def _worker_training_watch_once() -> int:
    return _retired_worker_watch_once()
def _worker_training_watcher_loop() -> None:
    return _worker_watcher_loop._worker_training_watcher_loop()
@app.on_event("startup")
def start_worker_training_watcher() -> None:
    return _retired_worker_watcher_start()
from .training.runner import TrainingRunner, TrainingRunnerRecords, TrainingRunnerPaths, TrainingDatasetExecution, TrainingLocalExecution
from .training.submission import (
    TrainingSubmission, TrainingSubmissionPolicy, TrainingSubmissionIdentity, TrainingSubmissionRecords, TrainingSubmissionThreads,
)

_training_runner = TrainingRunner(
    records=TrainingRunnerRecords(find=lambda job_id: find_training_task(job_id), path=lambda job_id: training_task_path(job_id),
        load=lambda: load_training_task, update_provider=lambda: update_training_task,
        sync=lambda job_id: sync_training_state_from_task(job_id)),
    paths=TrainingRunnerPaths(resolve=lambda: resolve_service_path, tasks=lambda: TRAINING_TASKS_DIR, app=lambda: APP_DIR,
        output=lambda: output_write_dir_for_owner),
    datasets=TrainingDatasetExecution(mode=lambda: training_executor_mode(), generate=lambda task: generate_training_dataset(task),
        runpod=lambda job_id, task, dataset: run_runpod_training_task(job_id, task, dataset),
        remote=lambda job_id, task, dataset: run_remote_training_task(job_id, task, dataset)),
    local=TrainingLocalExecution(base_model=lambda: detect_base_model(), device=lambda: yolo_inference_device(), cli=lambda: yolo_cli_command(),
        start=lambda: subprocess.Popen, progress=lambda path, epochs: parse_yolo_epoch_progress(path, epochs),
        warmup=lambda: start_yolo_warmup),
    resolver=resolve_model_profiles,
)
_training_submission = TrainingSubmission(
    policy=TrainingSubmissionPolicy(estimate=lambda: training_estimate, uses_ocr=lambda item: accessory_uses_ocr(item)),
    identity=TrainingSubmissionIdentity(user=lambda: _request_user.get(), owner=lambda: current_owner_fields(),
        background=lambda: selected_background_set_id),
    records=TrainingSubmissionRecords(save=lambda task: save_training_task(task), public=lambda task: public_training_task(task)),
    threads=TrainingSubmissionThreads(target=lambda: run_training_task, create=lambda **kwargs: threading.Thread(**kwargs),
        records=lambda: _training_task_threads),
    runtime=_training_task_runtime,
)


def run_training_task(job_id: str) -> None:
    return _training_runner.run_training_task(job_id)


def enqueue_training_task(
    request: TrainingStartRequest,
    selected: list[dict[str, Any]],
    action: str,
    dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _training_submission.enqueue_training_task(request, selected, action, dataset)


from .training.task_lookup import TrainingTaskLookup, LookupCache, LookupRows
from .training.model_catalog import (
    TrainedModelCatalog, TrainingFiles, TrainingAccessories, TrainingPipeline, TrainingAccess,
)
from .pipeline.training_links import TrainingLinks

_training_task_lookup = TrainingTaskLookup(
    repository=lambda: runtime_postgres_repository_or_none(), file_loader=lambda: load_training_task,
    cache=LookupCache(get=lambda key: store_read_cache_get(key), put=lambda key, value: store_read_cache_put(key, value)),
    rows=LookupRows(decode=lambda rows: row_raw_json_list(rows), identifier=lambda path: file_stem_identifier(path),
                    matches=lambda task, requested, row: training_task_matches_identifier(task, requested, row)),
)
_training_links = TrainingLinks(tasks=lambda: load_pipeline_tasks(), name=lambda task: task_record_name(task))
_trained_model_catalog = TrainedModelCatalog(
    config=lambda: load_config(),
    files=TrainingFiles(roots=lambda: training_run_roots(), finder=lambda: training_task_finder(),
        task_path=lambda: training_task_path, read=lambda path: load_json_file_mtime_cached(path),
        output=lambda: OUTPUT_DIR, resolve=lambda: resolve_service_path),
    accessories=TrainingAccessories(uid=lambda item: accessory_uid(item), serialize=lambda item: serialize_accessory(item),
        uses_ocr=lambda: accessory_uses_ocr, profiles=lambda: build_ocr_accessory_profiles),
    pipeline=TrainingPipeline(tasks=lambda: load_pipeline_tasks(),
        link=lambda: pipeline_task_link_for_training_run,
        method=lambda: normalize_pipeline_detection_method),
    access=TrainingAccess(current_user=lambda: _request_user.get(), visible=lambda record, user: record_visible_to_user(record, user),
        audit=lambda: record_audit_fields),
    rules=lambda spec, config: apply_task_rule_override_to_spec(spec, config),
)


def training_task_finder() -> Callable[[Path], dict[str, Any] | None]:
    return _training_task_lookup.training_task_finder()


def pipeline_task_link_for_training_run(run_id: str, tasks: list[dict[str, Any]] | None = None) -> dict[str, str]:
    return _training_links.pipeline_task_link_for_training_run(run_id, tasks)


def list_trained_model_specs(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _trained_model_catalog.list_trained_model_specs(config)


from .detection.task_identity import (
    ai_detection_task_model_id as _detection_task_model_id,
    sanitize_ai_detection_task_id, clean_ai_detection_task_name, normalize_ai_detection_task_counts,
)
from .detection.task_store import DetectionTaskStore, TaskStorePaths, TaskReadCache, TaskRows
from .detection.task_backgrounds import (
    ai_detection_task_background_record as _detection_task_background_record,
    hydrate_auto_optimize_background_from_ai_task as _hydrate_detection_task_background,
)

_detection_task_store = DetectionTaskStore(
    repository=lambda: runtime_postgres_repository_or_none(),
    paths=TaskStorePaths(data=lambda: DATA_DIR, tasks=lambda: AI_DETECTION_TASKS_PATH, ensure=lambda: ensure_dirs()),
    cache=TaskReadCache(get=lambda key: store_read_cache_get(key), put=lambda key, value: store_read_cache_put(key, value),
                        invalidate=lambda key: store_read_cache_invalidate(key)),
    rows=TaskRows(encode=lambda task: ai_detection_task_row(task), decode=lambda: row_raw_json_list),
    normalize_background=lambda: safe_background_set_id,
)


def ai_detection_task_model_id(task_id: str) -> str:
    return _detection_task_model_id(task_id, AI_DETECTION_TASK_PREFIX)


from .accessories.lookup import AccessoryLookup
from .detection.requirements import RequiredAccessories

_accessory_lookup = AccessoryLookup(lambda item: accessory_uid(item), lambda item: accessory_legacy_uid(item))
_required_accessories = RequiredAccessories(lambda item: accessory_uid(item), lambda: CLASS_LABELS)


def accessory_lookup_by_id(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _accessory_lookup.accessory_lookup_by_id(config)


def accessory_id_aliases(item: dict[str, Any]) -> list[str]:
    return _accessory_lookup.accessory_id_aliases(item)


def resolve_accessory_id(config: dict[str, Any], accessory_id: str) -> tuple[str, dict[str, Any]] | None:
    return _accessory_selection.resolve_accessory_id(config, accessory_id)


def load_ai_detection_tasks() -> list[dict[str, Any]]:
    return _detection_task_store.load_ai_detection_tasks()


def save_ai_detection_tasks(tasks: list[dict[str, Any]]) -> None:
    return _detection_task_store.save_ai_detection_tasks(tasks)


def find_ai_detection_task(task_id: str) -> dict[str, Any] | None:
    return _detection_task_store.find_ai_detection_task(task_id)


def save_ai_detection_task(task: dict[str, Any], *, prepend: bool = False) -> None:
    return _detection_task_store.save_ai_detection_task(task, prepend=prepend)


def ai_detection_task_background_record(task_id: str) -> tuple[str, dict[str, Any]]:
    return _detection_task_background_record(task_id, find_task=lambda value: find_ai_detection_task(value),
                                             normalize_background=lambda: safe_background_set_id)


def hydrate_auto_optimize_background_from_ai_task(state: dict[str, Any]) -> bool:
    return _hydrate_detection_task_background(state, background_record=lambda: ai_detection_task_background_record,
                                              normalize_background=lambda: safe_background_set_id)


from .detection.task_projection import TaskProjection
from .detection.task_catalog import TaskCatalog, TaskCatalogSources, TaskCatalogAccess, TaskModelRegistry

_detection_task_projection = TaskProjection(
    lookup=lambda config: accessory_lookup_by_id(config), audit=lambda record: record_audit_fields(record),
    background=lambda task_id: ai_detection_task_background_record(task_id),
    public_path=lambda value: public_path_sanitized(value), model_id=lambda task_id: ai_detection_task_model_id(task_id),
)
_detection_task_catalog = TaskCatalog(
    sources=TaskCatalogSources(config=lambda: load_config(), tasks=lambda: load_ai_detection_tasks(),
                               trained=lambda *args: list_trained_model_specs(*args),
                               accessory_uid=lambda item: accessory_uid(item), serialize_accessory=lambda item: serialize_accessory(item)),
    access=TaskCatalogAccess(user=lambda: _request_user.get(),
                             visible=lambda record, user, target: record_visible_to_user(record, user, target),
                             owner_username=lambda record: record_owner_username(record)),
    registry=TaskModelRegistry(base_spec=lambda: MODEL_REGISTRY[AI_DETECTION_MODEL_ID], label=lambda: AI_DETECTION_LABEL,
                               tasks_path=lambda: AI_DETECTION_TASKS_PATH, legacy_owner=lambda: LEGACY_OWNER_ID,
                               model_id=lambda task_id: ai_detection_task_model_id(task_id)),
    project=lambda task, config: serialize_ai_detection_task(task, config),
)


def serialize_ai_detection_task(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _detection_task_projection.serialize_ai_detection_task(task, config)


def list_ai_detection_task_model_specs(config: dict[str, Any] | None = None, target_user_id: str | None = None) -> list[dict[str, Any]]:
    return _detection_task_catalog.list_ai_detection_task_model_specs(config, target_user_id)


def ai_detection_task_payload_from_request(request: AiDetectionTaskRequest, config: dict[str, Any]) -> dict[str, Any]:
    return _detection_task_projection.ai_detection_task_payload_from_request(request, config)


def ai_detection_tasks_response(
    config: dict[str, Any],
    selected_id: str | None = None,
    *,
    user: dict[str, Any] | None = None,
    target_user_id: str | None = None,
) -> dict[str, Any]:
    return _detection_task_catalog.ai_detection_tasks_response(config, selected_id, user=user, target_user_id=target_user_id)


def list_ai_detection_specialized_model_specs(
    config: dict[str, Any] | None = None,
    trained_specs: list[dict[str, Any]] | None = None,
    target_user_id: str | None = None,
) -> list[dict[str, Any]]:
    return _detection_task_catalog.list_ai_detection_specialized_model_specs(config, trained_specs, target_user_id)


def selected_model_spec(model_id: str | None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _model_selection.selected_model_spec(model_id, config)


def model(model_id: str | None = None, config: dict[str, Any] | None = None) -> YOLO:
    return _local_models.model(model_id, config)






def yolo_warmup_configured_model_ids(config: dict[str, Any]) -> list[str]:
    return _warmup_candidates.yolo_warmup_configured_model_ids(config)


def warm_yolo_model_once(model_id: str, config: dict[str, Any]) -> None:
    return _warmup_prediction.warm_yolo_model_once(model_id, config)


def yolo_warmup_status() -> dict[str, Any]:
    return _yolo_warmup_runtime.yolo_warmup_status()


def yolo_loaded_model_ids(config: dict[str, Any]) -> list[str]:
    return _local_models.yolo_loaded_model_ids(config)


def yolo_model_ready(model_id: str, config: dict[str, Any]) -> bool:
    return _local_models.yolo_model_ready(model_id, config)


def public_yolo_warmup_status(config: dict[str, Any]) -> dict[str, Any]:
    return _yolo_warmup_runtime.public_yolo_warmup_status(config)


def yolo_warmup_worker(reason: str = "startup", model_ids: list[str] | None = None) -> None:
    return _yolo_warmup_runtime.yolo_warmup_worker(reason, model_ids)


def start_yolo_warmup(reason: str = "startup", model_ids: list[str] | None = None) -> None:
    return _yolo_warmup_runtime.start_yolo_warmup(reason, model_ids, worker=lambda: yolo_warmup_worker)


@app.on_event("startup")
def start_yolo_model_warmup() -> None:
    start_yolo_warmup("startup")


from .detection.local_models import CheckpointSelection, yolo_inference_device

_checkpoint_selection = CheckpointSelection(
    lambda: DETECT_BASE_MODEL_OVERRIDE, lambda: ROOT, lambda: APP_DIR,
    lambda path: _business_files.exists(path),
)


detect_base_model = _checkpoint_selection.detect_base_model




from .runtime.paddle import prepare_runtime as prepare_paddle_runtime, DetectionOCREngine

_detection_ocr_engine = DetectionOCREngine(prepare=lambda: prepare_paddle_runtime())


def ocr_engine() -> Any:
    return _detection_ocr_engine.get()




from .runtime.service_paths import safe_name


from .detection.geometry import (
    polygon_overlap_ratio, polygon_area, polygon_bbox, bbox_gap, bbox_overlap_ratio
)










from .detection.ocr_matching import normalize_ocr_text, OCRMatching, MatchThresholds


OCR_ACCESSORY_MATCH_MIN_TEXT_SCORE = 0.65
OCR_ACCESSORY_MATCH_MIN_CONFIDENCE = 0.60
OCR_ACCESSORY_MATCH_MIN_MARGIN = 0.15
OCR_ACCESSORY_PROFILE_STOPWORDS = {
    "accessory",
    "document",
    "documentation",
    "instruction",
    "instructions",
    "label",
    "manual",
    "paper",
    "product",
    "text",
    "and",
    "back",
    "cover",
    "for",
    "from",
    "image",
    "images",
    "shows",
    "the",
    "that",
    "this",
    "white",
    "with",
}


_ocr_matching = OCRMatching(
    stopwords=lambda: OCR_ACCESSORY_PROFILE_STOPWORDS, uid=lambda item: accessory_uid(item),
    thresholds=MatchThresholds(text_score=lambda: OCR_ACCESSORY_MATCH_MIN_TEXT_SCORE,
                               confidence=lambda: OCR_ACCESSORY_MATCH_MIN_CONFIDENCE, margin=lambda: OCR_ACCESSORY_MATCH_MIN_MARGIN),
)
ocr_keyword_terms = _ocr_matching.keywords
build_ocr_accessory_profiles = _ocr_matching.profiles
match_ocr_text_accessory = _ocr_matching.match






from .detection.manual_text import ManualClassifier, ManualProjection
from .detection.results import DetectionLabels

_manual_classifier = ManualClassifier(keywords=lambda: MANUAL_TYPE_KEYWORDS, labels=lambda: MANUAL_TYPE_LABELS)
classify_manual_text = _manual_classifier.classify


from .detection.ocr_images import rotate_quarter_turn, resize_for_ocr, crop_detection_region






from .detection.ocr_scoring import OCRScoring, is_confident_manual_classification, better_ocr_result

_ocr_scoring = OCRScoring(engine=lambda: ocr_engine(), classify=lambda texts: classify_manual_text(texts))
build_ocr_result = _ocr_scoring.build
score_ocr_variant = _ocr_scoring.variant
score_ocr_variants = _ocr_scoring.variants
run_ocr_on_crop = _ocr_scoring.run_crop












_manual_projection = ManualProjection(
    class_ids=lambda: MANUAL_TYPE_CLASS_IDS,
    labels=DetectionLabels(class_names=lambda: CLASS_NAMES, class_labels=lambda: CLASS_LABELS,
                           generic_names=lambda: GENERIC_DETECTION_CLASS_NAMES, generic_labels=lambda: GENERIC_DETECTION_LABELS),
)
finalize_ocr_detection = _manual_projection.finalize


from .detection.ocr_attachment import OCRAttachment, AttachmentDependencies

_ocr_attachment = OCRAttachment(AttachmentDependencies(
    crop=lambda: crop_detection_region,
    score=lambda: score_ocr_variants,
    match=lambda: match_ocr_text_accessory,
    finalize=lambda det, result, orientation, max_texts: finalize_ocr_detection(det, result, orientation, max_texts),
))
attach_ocr_results = _ocr_attachment.attach


from .detection.postprocessing import filter_detections, dedupe_detections, postprocess_detections






from .detection.results import DetectionLabels, DetectionResults

_detection_results = DetectionResults(
    DetectionLabels(class_names=lambda: CLASS_NAMES, class_labels=lambda: CLASS_LABELS,
                    generic_names=lambda: GENERIC_DETECTION_CLASS_NAMES, generic_labels=lambda: GENERIC_DETECTION_LABELS),
    postprocess=lambda detections, shape, spec: postprocess_detections(detections, shape, spec),
)
detection_names_for_business_class = _detection_results.names
parse_detections = _detection_results.parse




from .detection.rules import CountRules

_detection_rules = CountRules(class_labels=lambda: CLASS_LABELS, manual_labels=lambda: MANUAL_TYPE_LABELS)
apply_rule = _detection_rules.apply


from .detection.drawing import draw_detections


def ai_required_accessories(config: dict[str, Any], spec: dict[str, Any]) -> list[tuple[dict[str, Any], int]]:
    return _required_accessories.ai_required_accessories(config, spec)


from .detection.presence_payload import PresencePayload
from .detection.presence_validation import (
    ai_detection_parsed_covers_required as _presence_covers_required,
    coerce_detection_count as _presence_count,
)

_presence_payload = PresencePayload(lambda: string_list, lambda: bounded_text)


def ai_detection_task_payload(required_accessories: list[dict[str, Any]]) -> dict[str, Any]:
    return _presence_payload.ai_detection_task_payload(required_accessories)


def ai_detection_output_token_budget(required_count: int) -> int:
    return max(180, min(420, 120 + max(1, required_count) * 64))


def ai_detection_provider_output_token_budget(required_count: int, settings: dict[str, Any]) -> int:
    budget = ai_detection_output_token_budget(required_count)
    if str(settings.get("provider") or "") == "qwen":
        # qwen3-vl drops the whole detections array more readily when the output
        # budget is tight; give it extra headroom (caps output tokens only).
        return min(800, budget * 2)
    return budget


def ai_detection_parsed_covers_required(parsed: Any, required_ids: set[str]) -> bool:
    return _presence_covers_required(parsed, required_ids)


def coerce_detection_count(value: Any) -> int | None:
    return _presence_count(value)


from .detection.failure_projection import FailureProjection
from .detection.failure_results import DetectionFailureResult

_failure_projection = FailureProjection(lambda: bounded_text, lambda settings: ai_tool_provider_meta(settings), lambda: AI_DETECTION_LABEL)
_detection_failure_result = DetectionFailureResult(
    lambda: ai_detection_settings(), lambda item, count: required_accessory_profile_payload(item, count),
    lambda required, settings, *, reason, timed_out=False, latency_ms=0: ai_presence_failure_payload(required, settings, reason=reason, timed_out=timed_out, latency_ms=latency_ms),
    lambda spec, settings: ai_model_payload(spec, settings),
)


def ai_presence_failure_payload(
    required_accessories: list[dict[str, Any]],
    settings: dict[str, Any],
    *,
    reason: str,
    timed_out: bool = False,
    latency_ms: int = 0,
) -> dict[str, Any]:
    return _failure_projection.ai_presence_failure_payload(required_accessories, settings, reason=reason, timed_out=timed_out, latency_ms=latency_ms)


def ai_detection_failure_result(
    request_id: str,
    spec: dict[str, Any],
    required_items: list[tuple[dict[str, Any], int]],
    annotated_url: str,
    *,
    reason: str,
    timed_out: bool = False,
    latency_ms: int = 0,
) -> dict[str, Any]:
    return _detection_failure_result.ai_detection_failure_result(request_id, spec, required_items, annotated_url, reason=reason, timed_out=timed_out, latency_ms=latency_ms)


from .detection.annotation import DetectionAnnotation, normalize_ai_box_2d as _normalize_ai_box_2d

_detection_annotation = DetectionAnnotation(
    lambda value: normalize_ai_box_2d(value), lambda: ai_box_2d_to_pixels,
    lambda: bounded_text, lambda: cv2, lambda kind: output_write_dir(kind), lambda path: output_url(path),
    lambda image, detections, rule: draw_ai_detection_boxes(image, detections, rule),
    lambda image, request_id: write_ai_original_output(image, request_id),
    runtime_provider=lambda: _business_files.runtime_provider(),
)


def write_ai_original_output(image_bgr: np.ndarray, request_id: str) -> str:
    return _detection_annotation.write_ai_original_output(image_bgr, request_id)


def normalize_ai_box_2d(value: Any) -> list[float] | None:
    return _normalize_ai_box_2d(value)


def ai_box_2d_to_pixels(box_2d: Any, image_shape: tuple[int, ...]) -> tuple[int, int, int, int] | None:
    return _detection_annotation.ai_box_2d_to_pixels(box_2d, image_shape)


def draw_ai_detection_boxes(image_bgr: np.ndarray, detections: list[dict[str, Any]], rule: dict[str, Any]) -> np.ndarray | None:
    return _detection_annotation.draw_ai_detection_boxes(image_bgr, detections, rule)


def write_ai_annotated_output(image_bgr: np.ndarray, request_id: str, detections: list[dict[str, Any]], rule: dict[str, Any]) -> str:
    return _detection_annotation.write_ai_annotated_output(image_bgr, request_id, detections, rule)


def ai_model_payload(spec: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    return _failure_projection.ai_model_payload(spec, settings)


from .detection.presence_results import PresenceResults

_presence_results = PresenceResults(
    lambda: coerce_detection_count, lambda: bounded_text, lambda: string_list,
    lambda settings: ai_tool_provider_meta(settings), lambda: AI_DETECTION_LABEL,
)


def normalize_ai_detection_result(
    parsed: dict[str, Any],
    required_accessories: list[dict[str, Any]],
    latency_ms: int,
    settings: dict[str, Any],
) -> dict[str, Any]:
    return _presence_results.normalize_ai_detection_result(parsed, required_accessories, latency_ms, settings)


from .detection.analysis import DetectionAnalysis
from .detection.ai_analysis import AiDetectionAnalysis
from .detection.analysis_ports import (
    AnalysisInput, AnalysisRouting, AnalysisInference, AnalysisOutput,
    AiProfiles, AiInspectionTools, AiAnalysisEvidence,
)

_ai_detection_analysis = AiDetectionAnalysis(
    AiProfiles(
        lambda config, spec: ai_required_accessories(config, spec), lambda item: accessory_uid(item),
        lambda profile, item: normalize_accessory_ai_profile(profile, item),
        lambda item: accessory_reference_image_contexts(item),
        lambda item, count, profile: required_accessory_profile_payload(item, count, profile), lambda config: save_config(config),
    ),
    AiInspectionTools(
        lambda: call_ai_mcp_tool, lambda: ai_detection_settings,
        lambda: external_ai_mcp_enabled(), lambda image, request_id: write_mcp_inspection_image(image, request_id),
        lambda: AI_REFERENCE_IMAGES_PER_ACCESSORY, lambda: AI_REFERENCE_IMAGE_MAX_SIDE, lambda: AI_REFERENCE_IMAGE_QUALITY,
    ),
    AiAnalysisEvidence(
        lambda image, request_id: write_ai_original_output(image, request_id),
        lambda request_id, spec, required, url, *, reason: ai_detection_failure_result(request_id, spec, required, url, reason=reason),
        lambda spec, settings: ai_model_payload(spec, settings),
        lambda result, request_id, *, image_path=None: persist_data_analysis_record_for_ai_detection(result, request_id, image_path=image_path),
    ),
)
_detection_analysis = DetectionAnalysis(
    AnalysisInput(lambda: load_config(), lambda: scope_config_for_user,
                  lambda model_id, config: selected_model_spec(model_id, config),
                  lambda: sanitize_ai_detection_task_id, lambda task_id: load_auto_optimize_state(task_id)),
    AnalysisRouting(
        lambda image, request_id, model_id=None, *, image_path=None: analyze_bgr(image, request_id, model_id, image_path=image_path),
        lambda image, request_id, spec, config, *, image_path=None: analyze_bgr_ai_detection(image, request_id, spec, config, image_path=image_path),
        lambda feature: removed_phase1_feature(feature), lambda: bounded_text,
    ),
    AnalysisInference(
        lambda: model, lambda: yolo_inference_device(), lambda result, spec: parse_detections(result, spec),
        lambda image, detections, config, spec: attach_ocr_results(image, detections, config, spec),
        lambda detections, config, spec: apply_rule(detections, config, spec),
        lambda image, detections, rule: draw_detections(image, detections, rule),
    ),
    AnalysisOutput(lambda kind: output_write_dir(kind), lambda: resize_bgr_max_side, lambda: INSPECTION_PREVIEW_MAX_SIDE,
                   lambda: cv2, lambda: INSPECTION_PREVIEW_JPEG_QUALITY, lambda path: output_url(path)),
    runtime_provider=lambda: _business_files.runtime_provider(),
)


@pinned_model_profiles(resolve_model_profiles)
def analyze_bgr_ai_detection(
    image_bgr: np.ndarray,
    request_id: str,
    spec: dict[str, Any],
    config: dict[str, Any],
    *,
    image_path: Path | None = None,
) -> dict[str, Any]:
    return _ai_detection_analysis.analyze_bgr_ai_detection(image_bgr, request_id, spec, config, image_path=image_path)


def analyze_bgr(image_bgr: np.ndarray, request_id: str, model_id: str | None = None, *, image_path: Path | None = None) -> dict[str, Any]:
    return _detection_analysis.analyze_bgr(image_bgr, request_id, model_id, image_path=image_path)


from .auth.users import UserService
from .auth.flows import AuthFlows

_user_service = _authentication.users
_auth_flows = _authentication.flows
_auth_routes = _authentication_http.register_auth(app)
auth_status = _auth_routes.auth_status
auth_bootstrap = _auth_routes.auth_bootstrap
auth_login = _auth_routes.auth_login
auth_logout = _auth_routes.auth_logout
get_task_navigation_preferences = _auth_routes.get_task_navigation_preferences
update_task_navigation_preferences = _auth_routes.update_task_navigation_preferences


openapi_schema, swagger_ui, redoc_ui = _authentication_http.register_documentation(app)






_user_routes = _authentication_http.register_users(app)
list_users = _user_routes.list_users
create_user = _user_routes.create_user
update_user = _user_routes.update_user
reset_user_password = _user_routes.reset_user_password
delete_user = _user_routes.delete_user


from .runtime.web_shell import WebShell, register_entry_routes, register_spa
_web_shell = WebShell(
    production_dist=lambda: REACT_PRODUCTION_DIST_DIR,
    exists=lambda path: _business_files.exists(path),
    route_segments=lambda: REACT_PRODUCTION_ROUTE_SEGMENTS,
    blocked_prefixes=lambda: REACT_PRODUCTION_BLOCKED_PREFIXES,
    enabled=lambda: react_production_spa_enabled(),
)
register_entry_routes(app, _web_shell)
index = _web_shell.index
legacy_index = _web_shell.legacy_index
react_preview = _web_shell.react_preview


from .auth.status_requests import ServiceStatusRequests
from .auth.status_requests_ports import StatusRequestAccess, StatusRequestCatalog, StatusRequestRuntime

_service_status_requests = ServiceStatusRequests(
    access=StatusRequestAccess(
        current_auth_user=lambda: current_auth_user,
        user_is_admin=lambda: user_is_admin,
        scope_config_for_user=lambda: scope_config_for_user,
        record_visible_to_user=lambda: record_visible_to_user,
        user_has_permission=lambda: user_has_permission,
        redact_status_payload_for_user=lambda: redact_status_payload_for_user,
        redact_config_summary_for_user=lambda: redact_config_summary_for_user,
        public_path_sanitized=lambda: public_path_sanitized,
    ),
    catalog=StatusRequestCatalog(
        load_config=lambda: load_config,
        selected_model_spec=lambda: selected_model_spec,
        accessory_uid=lambda: accessory_uid,
        list_training_tasks=lambda: list_training_tasks,
        list_trained_model_specs=lambda: list_trained_model_specs,
        legacy_model_specs=lambda: legacy_model_specs,
        list_ai_detection_specialized_model_specs=lambda: list_ai_detection_specialized_model_specs,
        ai_detection_tasks_response=lambda: ai_detection_tasks_response,
        _business_files=lambda: _business_files,
    ),
    runtime=StatusRequestRuntime(
        public_ai_detection_status=lambda: public_ai_detection_status,
        record_owner_username=lambda: record_owner_username,
        LEGACY_OWNER_ID=lambda: LEGACY_OWNER_ID,
        training_execution_status=lambda: training_execution_status,
        public_cursor_image2_status=lambda: public_cursor_image2_status,
        public_yolo_warmup_status=lambda: public_yolo_warmup_status,
        CLASS_LABELS=lambda: CLASS_LABELS,
        CLASS_NAMES=lambda: CLASS_NAMES,
    ),
)


@app.get("/api/status")
def status(user_id: str | None = None) -> dict[str, Any]:
    return _service_status_requests.status(user_id)


from .detection.warmup_requests import ModelWarmupAccess, ModelWarmupModels
from .detection.warmup_api import bind_warmup_start, compose_model_warmup_api

_model_warmup_requests = compose_model_warmup_api(
    app,
    access=ModelWarmupAccess(_access_control.current_auth_user, _app_config_store.load_config,
                            _account_projections.scope_config_for_user),
    models=ModelWarmupModels(_model_selection.selected_model_spec, _local_models.yolo_model_ready),
    status=_yolo_warmup_runtime.public_yolo_warmup_status,
    start=bind_warmup_start(_yolo_warmup_runtime),
)
warmup_detection_model = _model_warmup_requests.warmup_detection_model


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return public_path_sanitized(scope_config_for_user(load_config()))


@app.get("/api/config/summary")
def get_config_summary(user_id: str | None = None) -> dict[str, Any]:
    return _service_status_requests.get_config_summary(user_id)


def get_plc_config() -> dict[str, Any]:
    return plc_config_response()


def update_plc_config(request: PlcConfigRequest) -> dict[str, Any]:
    return _plc_config_diagnostics.update(request)


from .plc.config_diagnostics import ConfigDiagnostics as _ConfigDiagnostics
from .plc.config_diagnostics_api import register_config_diagnostics_routes as _register_config_diagnostics_routes
from .plc.config_diagnostics_ports import (
    ConfigAccess as _ConfigAccess, ConfigDisplay as _ConfigDisplay,
    ConfigErrors as _ConfigErrors, ConfigRuntime as _ConfigRuntime,
    ConfigSources as _ConfigSources,
)

_plc_config_diagnostics = _ConfigDiagnostics(
    _ConfigSources(
        load=lambda: load_config,
        raw_namespace=lambda: raw_plc_namespace,
        normalize=lambda: normalize_plc_config,
        defaults=lambda: DEFAULT_PLC_CONFIG,
        activation_errors=lambda: plc_activation_errors,
        dispatch_audit=lambda: plc_dispatch_audit_records,
    ),
    _ConfigDisplay(
        logical_address=lambda: logical_device_address,
        device_verified=lambda: plc_device_profile_verified,
        read_verified=lambda: plc_read_profile_verified,
    ),
    _ConfigRuntime(
        active_attempts=lambda: _plc_active_attempts_snapshot,
        audit_limit=lambda: PLC_DISPATCH_AUDIT_LIMIT,
        protocol_id=lambda: PLC_PROTOCOL_ID,
        generation_key=lambda: PLC_CONTROL_GENERATION_KEY,
        queue_wait_seconds=lambda: PLC_QUEUE_WAIT_SECONDS,
        worker_total_timeout_seconds=lambda: PLC_WORKER_TOTAL_TIMEOUT_SECONDS,
    ),
    _ConfigAccess(require_permission=lambda: require_permission),
    _ConfigErrors(
        config_error=lambda: PlcConfigError,
        http_error=lambda: HTTPException,
    ),
)

_register_config_diagnostics_routes(
    app,
    get_config=get_plc_config,
    update_config=update_plc_config,
)


@app.get("/api/version")
def get_release_version() -> dict[str, Any]:
    return current_release_version()


from .plc.workstation_management import WorkstationManagement as _WorkstationManagement
from .plc.workstation_management_api import register_workstation_management_routes as _register_workstation_management_routes
from .plc.workstation_management_ports import (
    WorkstationAccess as _WorkstationAccess,
    WorkstationErrors as _WorkstationErrors,
    WorkstationMutation as _WorkstationMutation,
    WorkstationProjection as _WorkstationProjection,
)

_plc_workstation_management = _WorkstationManagement(
    _WorkstationAccess(
        require_permission=lambda: require_permission,
        station_from_request=lambda: plc_web_serial_station_from_request,
        require_station=lambda: require_plc_web_serial_station,
    ),
    _WorkstationProjection(
        station_payload=lambda: plc_web_serial_station_payload,
        unpaired_payload=lambda: plc_web_serial_unpaired_payload,
        list_workstations=lambda: plc_web_serial_list_workstations,
    ),
    _WorkstationMutation(
        pair=lambda: plc_web_serial_pair,
        update_config=lambda: plc_web_serial_update_config,
        set_verified=lambda: plc_web_serial_set_verified,
    ),
    _WorkstationErrors(
        config_error=lambda: PlcConfigError,
        http_error=lambda: HTTPException,
    ),
)


def get_plc_web_serial_workstation(request: Request) -> dict[str, Any]:
    return _plc_workstation_management.get(request)


def list_plc_web_serial_workstations() -> dict[str, Any]:
    return _plc_workstation_management.list()


def pair_plc_web_serial_workstation(
    request: Request,
    response: Response,
    payload: PlcWorkstationPairRequest,
) -> dict[str, Any]:
    return _plc_workstation_management.pair(request, response, payload)


def update_plc_web_serial_workstation_config(
    request: Request,
    payload: PlcWebSerialConfigRequest,
) -> dict[str, Any]:
    return _plc_workstation_management.update_config(request, payload)


def verify_plc_web_serial_workstation_profile(
    request: Request,
    payload: PlcWorkstationVerifyRequest,
) -> dict[str, Any]:
    return _plc_workstation_management.verify_profile(request, payload)


_register_workstation_management_routes(
    app,
    get_workstation=get_plc_web_serial_workstation,
    list_workstations=list_plc_web_serial_workstations,
    pair_workstation=pair_plc_web_serial_workstation,
    update_config=update_plc_web_serial_workstation_config,
    verify_profile=verify_plc_web_serial_workstation_profile,
)


from .plc.connection_lease import ConnectionLease as _ConnectionLease
from .plc.connection_lease_api import register_connection_lease_routes as _register_connection_lease_routes
from .plc.connection_lease_ports import (
    LeaseAccess as _LeaseAccess, LeaseErrors as _LeaseErrors,
    LeaseMutation as _LeaseMutation,
)

_plc_connection_lease = _ConnectionLease(
    _LeaseAccess(
        require_station=lambda: require_plc_web_serial_station,
        require_model_permission=lambda: require_analyze_model_permission,
    ),
    _LeaseMutation(
        claim=lambda: plc_web_serial_claim_connecting_lease,
        activate=lambda: plc_web_serial_activate_lease,
        heartbeat=lambda: plc_web_serial_heartbeat,
        rebind_model=lambda: plc_web_serial_rebind_model,
        disconnect=lambda: plc_web_serial_release_lease,
    ),
    _LeaseErrors(
        config_error=lambda: PlcConfigError,
        http_error=lambda: HTTPException,
    ),
)


def claim_plc_web_serial_connection(
    request: Request,
    payload: PlcWorkstationLeaseRequest,
) -> dict[str, Any]:
    return _plc_connection_lease.claim(request, payload)


def activate_plc_web_serial_connection(
    request: Request,
    payload: PlcWorkstationLeaseActivateRequest,
) -> dict[str, Any]:
    return _plc_connection_lease.activate(request, payload)


def heartbeat_plc_web_serial_connection(
    request: Request,
    payload: PlcWorkstationLeaseHeartbeatRequest,
) -> dict[str, Any]:
    return _plc_connection_lease.heartbeat(request, payload)


def rebind_plc_web_serial_connection_model(
    request: Request,
    payload: PlcWorkstationLeaseRebindRequest,
) -> dict[str, Any]:
    return _plc_connection_lease.rebind_model(request, payload)


def disconnect_plc_web_serial_connection(
    request: Request,
    payload: PlcWorkstationLeaseHeartbeatRequest,
) -> dict[str, Any]:
    return _plc_connection_lease.disconnect(request, payload)


_register_connection_lease_routes(
    app,
    claim=claim_plc_web_serial_connection,
    activate=activate_plc_web_serial_connection,
    heartbeat=heartbeat_plc_web_serial_connection,
    rebind_model=rebind_plc_web_serial_connection_model,
    disconnect=disconnect_plc_web_serial_connection,
)


from .plc.dispatch_diagnostic import DispatchDiagnostic as _DispatchDiagnostic
from .plc.dispatch_diagnostic_api import register_dispatch_diagnostic_routes as _register_dispatch_diagnostic_routes
from .plc.dispatch_diagnostic_ports import (
    DispatchAccess as _DispatchAccess, DispatchErrors as _DispatchErrors,
    DispatchMutation as _DispatchMutation,
)

_plc_dispatch_diagnostic = _DispatchDiagnostic(
    _DispatchAccess(
        require_permission=lambda: require_permission,
        require_station=lambda: require_plc_web_serial_station,
    ),
    _DispatchMutation(
        declare_attempt=lambda: plc_web_serial_declare_attempt,
        diagnostic_plan=lambda: plc_web_serial_diagnostic_plan,
        diagnostic_receipt=lambda: plc_web_serial_finish_diagnostic,
        diagnostic_confirm=lambda: plc_web_serial_confirm_diagnostic,
        record_receipt=lambda: plc_web_serial_record_receipt,
    ),
    _DispatchErrors(
        config_error=lambda: PlcConfigError,
        http_error=lambda: HTTPException,
    ),
)


def declare_plc_web_serial_attempt(
    dispatch_id: str,
    request: Request,
    payload: PlcWebSerialAttemptRequest,
) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.declare_attempt(dispatch_id, request, payload)


def create_plc_web_serial_diagnostic_plan(
    request: Request,
    payload: PlcWebSerialAttemptRequest,
) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.diagnostic_plan(request, payload)


def finish_plc_web_serial_diagnostic(
    request: Request,
    payload: PlcWebSerialDiagnosticReceiptRequest,
) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.diagnostic_receipt(request, payload)


def confirm_plc_web_serial_diagnostic(
    request: Request,
    payload: PlcWebSerialDiagnosticConfirmRequest,
) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.diagnostic_confirm(request, payload)


def record_plc_web_serial_receipt_endpoint(
    dispatch_id: str,
    request: Request,
    payload: PlcWebSerialReceiptRequest,
) -> dict[str, Any]:
    return _plc_dispatch_diagnostic.record_receipt(dispatch_id, request, payload)


_register_dispatch_diagnostic_routes(
    app,
    declare_attempt=declare_plc_web_serial_attempt,
    diagnostic_plan=create_plc_web_serial_diagnostic_plan,
    diagnostic_receipt=finish_plc_web_serial_diagnostic,
    diagnostic_confirm=confirm_plc_web_serial_diagnostic,
    record_receipt=record_plc_web_serial_receipt_endpoint,
)


@app.post("/api/plc/capture-sessions/claim")
def claim_plc_capture_session(request: PlcCaptureSessionRequest) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="legacy_plc_input_capture_is_read_only")


@app.post("/api/plc/capture-sessions/heartbeat")
def heartbeat_plc_capture_session(request: PlcCaptureSessionHeartbeatRequest) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="legacy_plc_input_capture_is_read_only")


@app.delete("/api/plc/capture-sessions/{session_id}")
def release_plc_capture_session(session_id: str) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="legacy_plc_input_capture_is_read_only")


@app.get("/api/plc/capture-events/stream")
def stream_plc_capture_events(session_id: str) -> StreamingResponse:
    raise HTTPException(status_code=410, detail="legacy_plc_input_capture_is_read_only")


PIPELINE_TASKS_PATH = DATA_DIR / "pipeline_tasks.json"

from .pipeline.task_store import PipelineTaskStore, PipelineTaskPaths, PipelineTaskRows

_pipeline_task_store = PipelineTaskStore(
    repository=lambda: runtime_postgres_repository_or_none(),
    paths=PipelineTaskPaths(data=lambda: DATA_DIR, tasks=lambda: PIPELINE_TASKS_PATH),
    rows=PipelineTaskRows(encode=lambda task: pipeline_task_row(task), decode=lambda: row_raw_json_list),
    resolver=lambda: resolve_model_profiles,
)


_cost_paths = CostPaths(DATA_DIR, DATA_ANALYSIS_RECORDS_PATH, AI_DETECTION_TASKS_PATH,
                        PIPELINE_TASKS_PATH, AUTO_OPTIMIZE_DIR, AI_PROFILE_CACHE_PATH)
_cost_services = CostServices(CostStoreDependencies(
    paths=lambda paths=_cost_paths: paths,
    runtime_repository=_runtime_repository_access.runtime_postgres_repository_or_none,
    detection_tasks=_detection_task_store.load_ai_detection_tasks,
    pipeline_tasks=_pipeline_task_store.load_pipeline_tasks,
    auto_states=_auto_optimization_state_store.list_auto_optimize_states,
    training_tasks=_training_records.load_training_task_records,
    sanitize_task_id=sanitize_ai_detection_task_id,
), timestamp=coerce_record_timestamp)
_cost_repository = _cost_services.repository
_cost_ledger = _cost_services.ledger

api_cost_walk_usage = _cost_ledger.walk_usage
api_cost_store_payloads = _cost_repository.store_payloads
api_cost_training_records = _cost_ledger.training_records
api_cost_collect_records = _cost_ledger.collect_records
api_cost_summary = _cost_ledger.summary

get_api_cost_ledger = register_cost_api(app, _access_control.require_admin_role, _cost_ledger)


@app.get("/api/admin/runtime-store/probe")
def get_runtime_store_probe() -> dict[str, Any]:
    require_admin_role()
    return runtime_store_probe_payload()


@app.get("/api/windows-worker/status")
def get_windows_worker_status(force: bool = False, services: bool = False) -> dict[str, Any]:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "windows_worker_retired",
            "message": "Windows Worker execution is retired. Production training uses RunPod.",
        },
    )


@app.get("/api/windows-worker/training/jobs/{job_id}")
def get_windows_worker_training_job(job_id: str) -> dict[str, Any]:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "windows_worker_retired",
            "message": "Windows Worker training refresh is retired. Historical worker tasks are read-only.",
        },
    )


@app.get("/api/windows-worker/training/jobs/{job_id}/artifacts")
def get_windows_worker_training_artifacts(job_id: str) -> dict[str, Any]:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "windows_worker_retired",
            "message": "Windows Worker artifact import is retired. Production model artifacts are imported from RunPod.",
        },
    )


@app.get("/api/ai/config")
def get_ai_config() -> dict[str, Any]:
    require_admin_role()
    return public_ai_detection_status()


@app.post("/api/ai/config")
def update_ai_config(request: AiConfigRequest) -> dict[str, Any]:
    require_admin_role()
    raise HTTPException(409, "请使用模型与 API 配置库；旧配置入口已停用")


@app.get("/api/locateanything/config")
def get_locateanything_config() -> dict[str, Any]:
    removed_phase1_feature("LocateAnything")




@app.post("/api/locateanything/config")
def update_locateanything_config() -> dict[str, Any]:
    removed_phase1_feature("LocateAnything")




@app.get("/api/locateanything/status")
def locateanything_status() -> dict[str, Any]:
    removed_phase1_feature("LocateAnything")




@app.post("/api/locateanything/runtime/start")
def locateanything_runtime_start() -> dict[str, Any]:
    removed_phase1_feature("LocateAnything")




@app.get("/api/locateanything/accessories")
def locateanything_accessories() -> dict[str, Any]:
    removed_phase1_feature("LocateAnything")




@app.post("/api/locateanything/inspect")
async def locateanything_inspect() -> dict[str, Any]:
    removed_phase1_feature("LocateAnything")




@app.post("/api/locateanything/locate")
async def locateanything_locate() -> dict[str, Any]:
    removed_phase1_feature("LocateAnything")




_analysis_routes = register_analysis_api(app, lambda: current_auth_user(), lambda feature: removed_phase1_feature(feature), _analysis_queries)
list_data_analysis_records_api = _analysis_routes.list_records
get_data_analysis_record_api = _analysis_routes.get_record
delete_data_analysis_record_api = _analysis_routes.delete_record
run_data_analysis_record_locate_api = _analysis_routes.locate_record
run_data_analysis_batch_locate_api = _analysis_routes.locate_batch


@app.delete("/api/ai/config/key")
def delete_ai_config_key() -> dict[str, Any]:
    require_admin_role()
    raise HTTPException(409, "请在模型配置库管理 Key")


from .detection.task_requests import DetectionTaskRequests
from .detection.task_request_ports import TaskRequestAccess, TaskRequestPolicy, TaskRequestStore, TaskPipelineSync, TaskRequestClock

_detection_task_requests = DetectionTaskRequests(
    access=TaskRequestAccess(
        current_auth_user=lambda: current_auth_user,
        user_is_admin=lambda: user_is_admin,
        scope_config_for_user=lambda: scope_config_for_user,
        current_owner_fields=lambda: current_owner_fields,
        resource_owner_id_for_new_record=lambda: resource_owner_id_for_new_record,
        record_owner_id=lambda: record_owner_id,
        require_record_access=lambda: require_record_access,
    ),
    policy=TaskRequestPolicy(
        accessory_lookup_by_id=lambda: accessory_lookup_by_id,
        DASHBOARD_AI_TASK_NAME=lambda: DASHBOARD_AI_TASK_NAME,
        PIPELINE_DASHBOARD_AI_TASK_SOURCE=lambda: PIPELINE_DASHBOARD_AI_TASK_SOURCE,
        assert_unique_task_name=lambda: assert_unique_task_name,
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        ai_detection_task_payload_from_request=lambda: ai_detection_task_payload_from_request,
        ai_detection_tasks_response=lambda: ai_detection_tasks_response,
        serialize_ai_detection_task=lambda: serialize_ai_detection_task,
    ),
    store=TaskRequestStore(
        load_config=lambda: load_config,
        find_ai_detection_task=lambda: find_ai_detection_task,
        save_ai_detection_task=lambda: save_ai_detection_task,
        load_ai_detection_tasks=lambda: load_ai_detection_tasks,
        save_ai_detection_tasks=lambda: save_ai_detection_tasks,
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        store_read_cache_invalidate=lambda: store_read_cache_invalidate,
        delete_ai_detection_task_record=lambda: delete_ai_detection_task_record,
    ),
    pipeline=TaskPipelineSync(
        _pipeline_tasks_lock=lambda: _pipeline_tasks_lock,
        load_pipeline_tasks=lambda: load_pipeline_tasks,
        save_pipeline_tasks=lambda: save_pipeline_tasks,
        sync_ready_pipeline_ai_detection_tasks=lambda: sync_ready_pipeline_ai_detection_tasks,
        mark_pipeline_ai_task_deleted=lambda: mark_pipeline_ai_task_deleted,
    ),
    clock=TaskRequestClock(
        time=lambda: time,
        uuid=lambda: uuid,
    ),
)


@app.get("/api/ai/tasks")
def get_ai_detection_tasks(user_id: str | None = None) -> dict[str, Any]:
    return _detection_task_requests.get_ai_detection_tasks(user_id)


@app.post("/api/ai/tasks")
def create_ai_detection_task(request: AiDetectionTaskRequest) -> dict[str, Any]:
    return _detection_task_requests.create_ai_detection_task(request)


@app.put("/api/ai/tasks/{task_id}")
def update_ai_detection_task(task_id: str, request: AiDetectionTaskRequest) -> dict[str, Any]:
    return _detection_task_requests.update_ai_detection_task(task_id, request)


def delete_ai_detection_task_record(task_id: str, user: dict[str, Any], *, missing_ok: bool = False) -> str | None:
    return _detection_task_requests.delete_ai_detection_task_record(task_id, user, missing_ok=missing_ok)


from .pipeline.task_mutations import PipelineTaskMutations
from .pipeline.task_mutations_ports import MutationStorage, MutationAccess

_pipeline_task_mutations = PipelineTaskMutations(
    storage=MutationStorage(
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        save_pipeline_task=lambda: save_pipeline_task,
        save_pipeline_tasks=lambda: save_pipeline_tasks,
        _pipeline_tasks_lock=lambda: _pipeline_tasks_lock,
        load_pipeline_tasks=lambda: load_pipeline_tasks,
        load_pipeline_task=lambda: load_pipeline_task,
        save_pipeline_task_batch_changes=lambda: save_pipeline_task_batch_changes,
    ),
    access=MutationAccess(
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        record_mutable_by_user=lambda: record_mutable_by_user,
    ),
)


def save_pipeline_task_batch_changes(tasks: list[dict[str, Any]], changed_tasks: list[dict[str, Any]]) -> None:
    return _pipeline_task_mutations.save_pipeline_task_batch_changes(tasks, changed_tasks)


def mark_pipeline_ai_task_deleted(ai_task_id: str, user: dict[str, Any]) -> int:
    return _pipeline_task_mutations.mark_pipeline_ai_task_deleted(ai_task_id, user)


@app.delete("/api/ai/tasks/{task_id}")
def delete_ai_detection_task(task_id: str) -> dict[str, Any]:
    return _detection_task_requests.delete_ai_detection_task(task_id)


from .training.auto_optimization_requests import AutoOptimizationRequests
from .training.auto_optimization_requests_ports import RequestAccess, RequestState, RequestActions

_auto_optimization_requests = AutoOptimizationRequests(
    access=RequestAccess(
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        safe_record_id=lambda: safe_record_id,
        current_auth_user=lambda: current_auth_user,
        load_ai_detection_tasks=lambda: load_ai_detection_tasks,
        require_record_access=lambda: require_record_access,
        HTTPException=lambda: HTTPException,
    ),
    state=RequestState(
        _auto_optimize_lock=lambda: _auto_optimize_lock,
        load_auto_optimize_state=lambda: load_auto_optimize_state,
        save_auto_optimize_state=lambda: save_auto_optimize_state,
        public_auto_optimize_state=lambda: public_auto_optimize_state,
        auto_optimize_update_settings=lambda: auto_optimize_update_settings,
    ),
    actions=RequestActions(
        resolve_service_path=lambda: resolve_service_path,
        _business_files=lambda: _business_files,
        _image_files=lambda: _image_files,
        analyze_bgr=lambda: analyze_bgr,
        AI_DETECTION_TASK_PREFIX=lambda: AI_DETECTION_TASK_PREFIX,
        auto_optimize_bbox_training_entries=lambda: auto_optimize_bbox_training_entries,
        start_auto_optimize_training_check_worker=lambda: start_auto_optimize_training_check_worker,
    ),
)


@app.get("/api/ai/tasks/{task_id}/auto-optimize")
def get_ai_task_auto_optimize_status(task_id: str) -> dict[str, Any]:
    return _auto_optimization_requests.get_ai_task_auto_optimize_status(task_id)


@app.patch("/api/ai/tasks/{task_id}/auto-optimize")
def update_ai_task_auto_optimize_status(task_id: str, request: AutoOptimizeSettingsRequest) -> dict[str, Any]:
    return _auto_optimization_requests.update_ai_task_auto_optimize_status(task_id, request)


@app.delete("/api/ai/tasks/{task_id}/auto-optimize/samples/{sample_id}")
def delete_ai_task_auto_optimize_sample(task_id: str, sample_id: str) -> dict[str, Any]:
    return _auto_optimization_requests.delete_ai_task_auto_optimize_sample(task_id, sample_id)


@app.post("/api/ai/tasks/{task_id}/auto-optimize/samples/{sample_id}/retry")
def retry_ai_task_auto_optimize_sample(task_id: str, sample_id: str) -> dict[str, Any]:
    return _auto_optimization_requests.retry_ai_task_auto_optimize_sample(task_id, sample_id)


@app.post("/api/ai/tasks/{task_id}/auto-optimize/samples/{sample_id}/approve")
def approve_ai_task_auto_optimize_sample(
    task_id: str,
    sample_id: str,
    request: AutoOptimizeSampleApproveRequest | None = None,
) -> dict[str, Any]:
    return _auto_optimization_requests.approve_ai_task_auto_optimize_sample(task_id, sample_id, request)


from .detection.rule_api import compose_detection_rule_api
from .detection.rule_request_ports import RulePolicy, RuleStore, RuleAccess

_detection_rule_requests = compose_detection_rule_api(
    app,
    policy=RulePolicy(task_rule_id=task_rule_id, CLASS_NAMES=CLASS_NAMES),
    store=RuleStore(load_config=load_config, save_config=save_config,
                    list_trained_model_specs=list_trained_model_specs, time=time),
    access=RuleAccess(current_auth_user=current_auth_user,
                      record_visible_to_user=record_visible_to_user),
)
update_rules = _detection_rule_requests.update_rules
update_task_rules = _detection_rule_requests.update_task_rules


from .accessories.catalog import AccessoryCatalog, CatalogDependencies
from .accessories.api import register_catalog_api
_accessory_catalog = AccessoryCatalog(CatalogDependencies(
    current_user=lambda: current_auth_user(), load_config=lambda: load_config(),
    scope_config=lambda config, user, target: scope_config_for_user(config, user, target),
    require_access=lambda record, user=None, *, write=False: require_record_access(record, user, write=write),
    detail=lambda item: accessory_detail_payload(item),
), _accessory_projection)
_accessory_catalog_routes = register_catalog_api(app, _accessory_catalog)
get_accessories = _accessory_catalog_routes.get_accessories
get_accessory_detail = _accessory_catalog_routes.get_accessory_detail


from .accessories.candidate_queries import CandidateQueries, CandidateQueryDependencies
from .accessories.candidate_api import register_candidate_api
_candidate_queries = CandidateQueries(_candidate_repository, CandidateQueryDependencies(
    current_user=lambda: current_auth_user(),
    audit=lambda record, path: enrich_record_audit_fields(record, path),
    require_access=lambda record, user=None, *, write=False: require_record_access(record, user, write=write),
    image_jobs=lambda candidate: candidate_image_jobs(candidate),
    ensure_image_task_id=lambda candidate, job: ensure_image_job_task_id(candidate, job),
    refresh_image_job=lambda job: refresh_codex_image_job(job),
    store_image_job=lambda candidate, job: store_candidate_image_job(candidate, job),
))
get_accessory_candidate = register_candidate_api(app, _candidate_queries)


from .training.jobs_query import JobsReadAccess, JobsTraining, TrainingJobsQuery
from .training.task_mutations import TaskMutationRecords, TrainingTaskMutations
from .training.jobs_api import ImageJobActions
from .training import jobs_api as _training_jobs_api

_training_jobs_query = TrainingJobsQuery(
    JobsReadAccess(lambda: current_auth_user(), lambda user: user_is_admin(user),
                   lambda task, user, **kwargs: require_record_access(task, user, **kwargs)),
    JobsTraining(lambda job: find_training_task(job), lambda task: training_task_uses_worker(task),
                 lambda task: public_training_task(task),
                 lambda task, **kwargs: public_refreshed_training_task(task, **kwargs)),
    lambda **kwargs: list_training_tasks(**kwargs), lambda **kwargs: list_codex_image_jobs(**kwargs),
    lambda: IMAGE_JOB_ACTIVE_STATUSES,
)
_training_task_mutations = TrainingTaskMutations(
    lambda: current_auth_user(), lambda task, user, **kwargs: require_record_access(task, user, **kwargs),
    TaskMutationRecords(lambda job: find_training_task(job), lambda task: save_training_task(task),
                        lambda task: public_training_task(task), lambda job, user: delete_training_task_record(job, user),
                        lambda **kwargs: list_training_tasks(**kwargs)),
    lambda: time.time(),
)
_training_jobs_routes = _training_jobs_api.register(
    app, _training_jobs_query, _training_task_mutations,
    ImageJobActions(lambda job, action: update_codex_image_job(job, action),
                    lambda candidate, action: update_codex_image_candidate(candidate, action)),
)
image_jobs = _training_jobs_routes.image_jobs
image_job = _training_jobs_routes.image_job
update_training_task_endpoint = _training_jobs_routes.update_training_task_endpoint
delete_training_task_endpoint = _training_jobs_routes.delete_training_task_endpoint
stop_image_job = _training_jobs_routes.stop_image_job
retry_image_job = _training_jobs_routes.retry_image_job
delete_image_job = _training_jobs_routes.delete_image_job
stop_image_job_candidate = _training_jobs_routes.stop_image_job_candidate
delete_image_job_candidate = _training_jobs_routes.delete_image_job_candidate


from .accessories.creation import AccessoryCreation
from .accessories.creation_ports import CreationAccess, CreationStore, CreationMedia, CreationProfiles, CandidateCreation, CreationPipeline
from .accessories.confirmation import AccessoryConfirmation
from .accessories.confirmation_ports import ConfirmationAccess, ConfirmationStore, ConfirmationJobs, ConfirmationProfiles, ConfirmationMedia, ConfirmationPipeline
from .accessories.management_api import register_management_api, register_removal_api
_accessory_creation = AccessoryCreation(
    CreationAccess(
        current_user=lambda: current_auth_user(), owner_fields=lambda: current_owner_fields(),
        new_owner_id=lambda user: resource_owner_id_for_new_record(user),
        request_user=lambda: _request_user.get(),
    ),
    CreationStore(
        load=lambda: load_config(), save=lambda item, config: save_accessory_item(item, config),
        scope=lambda config, user: scope_config_for_user(config, user),
        unique_name=lambda config, name, owner: assert_unique_accessory_name(config, name, owner),
        class_names=lambda: CLASS_NAMES,
    ),
    CreationMedia(
        upload_directory=lambda: UPLOAD_DIR, safe_name=lambda name: safe_name(name),
        validate_text=lambda files, **kwargs: validate_text_accessory_uploads(files, **kwargs),
        size_reference=lambda value: normalize_size_reference(value),
        physical_size=lambda *args: physical_size_payload(*args),
        expand_sources=lambda identifier, files: expand_accessory_reference_sources(identifier, files),
        normalize=lambda item: normalize_accessory_assets(item),
        defer=lambda item: defer_accessory_normalization(item),
    ),
    CreationProfiles(
        ensure_reference=lambda item: ensure_default_ai_profile_reference(item),
        ensure_profile=lambda item, **kwargs: ensure_accessory_ai_profile(item, **kwargs),
        ensure_pose_jobs=lambda item: ensure_pose_collection_image_jobs(item),
        has_active_jobs=lambda item: candidate_has_active_image_jobs(item),
        start_worker=lambda: start_image_worker(),
    ),
    CandidateCreation(
        create=lambda *args: create_accessory_candidate(*args),
        save=lambda path, item: save_accessory_candidate(path, item),
        directory=lambda: ACCESSORY_CANDIDATES_DIR,
    ),
    CreationPipeline(
        add_accessory=lambda identifier: add_pipeline_accessory_id(identifier),
        add_pending=lambda identifier: add_pipeline_pending_candidate_id(identifier),
        payload=lambda config, user: pipeline_accessories_payload(config, user),
    ),
    _accessory_projection, files=_business_files
)




_accessory_confirmation = AccessoryConfirmation(
    ConfirmationAccess(
        current_user=lambda: current_auth_user(),
        require_access=lambda record, user=None, *, write=False: require_record_access(record, user, write=write),
        owner_id=lambda record: record_owner_id(record),
    ),
    ConfirmationStore(
        directory=lambda: ACCESSORY_CANDIDATES_DIR, lock=lambda: _candidate_store_lock,
        load_candidate=lambda identifier: load_accessory_candidate(identifier),
        save_candidate=lambda path, item: save_accessory_candidate(path, item),
        load_config=lambda: load_config(), save_item=lambda item, config: save_accessory_item(item, config),
        scope=lambda config, user: scope_config_for_user(config, user),
        unique_name=lambda config, name, owner: assert_unique_accessory_name(config, name, owner),
        class_names=lambda: CLASS_NAMES,
    ),
    ConfirmationJobs(
        ensure_ids=lambda item: ensure_candidate_image_job_task_ids(item),
        ensure_pose=lambda item: ensure_pose_collection_image_jobs(item),
        list_jobs=lambda item: candidate_image_jobs(item),
        refresh=lambda job: refresh_codex_image_job(job),
        store=lambda item, job: store_candidate_image_job(item, job),
        active_statuses=lambda: IMAGE_JOB_ACTIVE_STATUSES, start_worker=lambda: start_image_worker(),
    ),
    ConfirmationProfiles(
        ensure_reference=lambda item: ensure_default_ai_profile_reference(item),
        ensure_profile=lambda item, **kwargs: ensure_accessory_ai_profile(item, **kwargs),
        rejected=lambda item: accessory_ai_profile_rejected(item), ready=lambda item: accessory_ai_profile_ready(item),
        normalize=lambda profile, item: normalize_accessory_ai_profile(profile, item),
    ),
    ConfirmationMedia(
        defer=lambda item: defer_accessory_normalization(item),
        normalize=lambda item: normalize_accessory_assets(item),
        canonical_assets=lambda item: canonical_text_assets(item),
        complete=lambda item, assets: canonical_text_assets_complete(item, assets),
        error_detail=lambda item, assets, complete, ready: text_accessory_confirm_detail(item, assets, complete, ready),
    ),
    ConfirmationPipeline(
        confirmed_id=lambda item: candidate_confirmed_accessory_id(item),
        add_accessory=lambda identifier: add_pipeline_accessory_id(identifier),
        remove_pending=lambda identifier: remove_pipeline_pending_candidate_id(identifier),
        payload=lambda config, user: pipeline_accessories_payload(config, user),
    ),
    _accessory_projection,
)
_accessory_management_routes = register_management_api(app, _accessory_creation, _accessory_confirmation)
add_accessory = _accessory_management_routes.add_accessory
preview_accessory = _accessory_management_routes.preview_accessory
confirm_accessory = _accessory_management_routes.confirm_accessory


from .accessories.files import AccessoryFiles
from .accessories.file_ports import FileAccess, FileStore, FileMedia, FileProfiles
from .accessories.file_api import register_file_api
_accessory_files = AccessoryFiles(
    FileAccess(lambda: current_auth_user(), lambda record, user=None, *, write=False: require_record_access(record, user, write=write)),
    FileStore(lambda: load_config(), lambda item, config: save_accessory_item(item, config),
              lambda config, user: scope_config_for_user(config, user)),
    FileMedia(
        upload_directory=lambda: UPLOAD_DIR,
        data_directory=lambda: DATA_DIR,
        image_suffixes=lambda: IMAGE_REFERENCE_SUFFIXES,
        safe_name=lambda name: safe_name(name),
        validate_text_uploads=lambda files, *, existing_count=0: validate_text_accessory_uploads(files, existing_count=existing_count),
        text_source_count=lambda item: text_accessory_source_count(item),
        existing_source_paths=lambda item: existing_source_image_paths(item),
        is_rectified=lambda path: is_text_rectified_path(path),
        crop_stem=lambda path: stable_text_crop_stem(path),
        detail=lambda item: accessory_detail_payload(item),
        clean_sprites=lambda item: clean_sprite_assets(item),
        image_jobs=lambda item: candidate_image_jobs(item),
    ),
    FileProfiles(
        refresh=lambda item, *, force_profile=True: refresh_accessory_assets_after_source_change(item, force_profile=force_profile),
        fallback=lambda item: fallback_accessory_ai_profile(item),
        generate=lambda item, *, allow_provider=True: generate_accessory_ai_profile(item, allow_provider=allow_provider),
        save_cache=lambda payload: save_ai_profile_cache(payload),
        bounded_text=lambda value, limit: bounded_text(value, limit),
    ),
    _accessory_projection,
)
_accessory_file_routes = register_file_api(app, _accessory_files)
add_accessory_files = _accessory_file_routes.add_accessory_files
crop_accessory_text_image = _accessory_file_routes.crop_accessory_text_image
set_accessory_ai_reference = _accessory_file_routes.set_accessory_ai_reference
delete_accessory_file = _accessory_file_routes.delete_accessory_file


from .accessories.removal import AccessoryRemoval
from .accessories.removal_ports import RemovalStore
_accessory_removal = AccessoryRemoval(
    FileAccess(lambda: current_auth_user(), lambda record, user=None, *, write=False: require_record_access(record, user, write=write)),
    RemovalStore(
        load=lambda: load_config(),
        postgres_enabled=lambda: runtime_postgres_repository_or_none() is not None,
        delete=lambda identifier, *args: delete_accessory_item(identifier, *args),
        save_app_config=lambda config: save_app_config(config),
        scope=lambda config, user: scope_config_for_user(config, user),
    ),
    lambda identifier: remove_pipeline_accessory_id(identifier),
    _accessory_projection,
)
delete_accessory = register_removal_api(app, _accessory_removal)


@app.get("/api/label-sheets/references")
def get_label_sheet_references() -> dict[str, Any]:
    removed_phase1_feature("Label Sheet")




@app.post("/api/label-sheets/references")
async def add_label_sheet_reference() -> dict[str, Any]:
    removed_phase1_feature("Label Sheet")




@app.post("/api/label-sheets/match")
async def match_label_sheet_endpoint() -> dict[str, Any]:
    removed_phase1_feature("Label Sheet")



@app.post("/api/experimental/label-inspector/analyze")
async def analyze_label_experiment() -> dict[str, Any]:
    removed_phase1_feature("Label Sheet inspector")




from .detection.upload_ports import UploadAccess, UploadPaths, VideoResults

from .detection.image_upload import ImageUpload

from .detection.video_upload import VideoUpload

from .detection.video_results import video_frame_result_payload, VideoSummary

_upload_access = UploadAccess(lambda: ensure_dirs(), lambda model: require_analyze_model_permission(model))

_upload_paths = UploadPaths(lambda: safe_name, lambda: UPLOAD_DIR)

_image_upload = ImageUpload(_upload_access, _upload_paths, lambda: np, lambda: cv2, lambda image, request_id, model_id=None, *, image_path=None: analyze_bgr(image, request_id, model_id, image_path=image_path), files=lambda: _business_files)

_video_summary = VideoSummary(lambda: string_list)

_video_upload = VideoUpload(_upload_access, _upload_paths, lambda: shutil, lambda: load_config(), lambda: cv2, lambda image, request_id, model_id=None: analyze_bgr(image, request_id, model_id), VideoResults(lambda result, index, fps: video_frame_result_payload(result, index, fps), lambda frames: video_ai_summary(frames)), files=_business_files)


@app.post("/api/analyze/image")
async def analyze_image(file: UploadFile=File(...), model_id: str | None=Form(None)) -> dict[str, Any]:
    return await _image_upload.analyze_image(file, model_id)


from .detection.camera_request import CameraDetectionRequest
from .detection.camera_request_ports import CameraRequestAccess, CameraDispatchEvidence, CameraImageExecution

_camera_detection_request = CameraDetectionRequest(
    access=CameraRequestAccess(
        ensure_dirs=lambda: ensure_dirs,
        require_analyze_model_permission=lambda: require_analyze_model_permission,
        require_plc_web_serial_station=lambda: require_plc_web_serial_station,
    ),
    evidence=CameraDispatchEvidence(
        plc_web_serial_begin_camera_detection=lambda: plc_web_serial_begin_camera_detection,
        plc_web_serial_finish_camera_detection=lambda: plc_web_serial_finish_camera_detection,
        plc_web_serial_dispatch_public=lambda: plc_web_serial_dispatch_public,
    ),
    images=CameraImageExecution(
        UPLOAD_DIR=lambda: UPLOAD_DIR,
        _business_files=lambda: _business_files,
        safe_name=lambda: safe_name,
        analyze_bgr=lambda: analyze_bgr,
    ),
)


@app.post("/api/analyze/camera")
async def analyze_camera_image(
    request: Request,
    file: UploadFile = File(...),
    model_id: str | None = Form(None),
    plc_session_id: str = Form(...),
    camera_request_id: str = Form(...),
) -> dict[str, Any]:
    return await _camera_detection_request.analyze_camera_image(request, file, model_id, plc_session_id, camera_request_id)




def video_ai_summary(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _video_summary.video_ai_summary(frames)


@app.post("/api/analyze/video")
@pinned_model_profiles(resolve_model_profiles)
async def analyze_video(file: UploadFile=File(...), model_id: str | None=Form(None)) -> dict[str, Any]:
    return await _video_upload.analyze_video(file, model_id)


@app.post("/api/stream/config")
def update_stream(config_in: StreamConfig) -> dict[str, Any]:
    config = load_config()
    config["stream"] = {
        "enabled": config_in.enabled,
        "source": config_in.source,
        "url": config_in.url,
        "status": "reserved_for_camera_or_rtsp_input",
    }
    save_config(config)
    return {"status": "saved", "stream": config["stream"]}


from .training.background_query import BackgroundQuery
from .training.background_uploads import (
    BackgroundUploadPaths, BackgroundUploadRecords, BackgroundUpload,
    BackgroundCaptureIdentity, BackgroundCapturePaths, BackgroundCaptureTasks,
    BackgroundCaptureSets, BackgroundCaptureState, BackgroundCapture,
)
from .training import background_api as _training_background_api

_background_query = BackgroundQuery(
    lambda: current_auth_user(), lambda user: user_is_admin(user), lambda identifier: safe_background_set_id(identifier),
    lambda *args, **kwargs: list_background_sets(*args, **kwargs), lambda: load_background_sets_manifest(),
    lambda: selected_background_set_id,
    lambda: BACKGROUND_SETS_DIR, lambda: IMAGE_REFERENCE_SUFFIXES,
    files=lambda: _business_files,
)
_background_upload = BackgroundUpload(
    BackgroundUploadPaths(lambda: BACKGROUND_SETS_DIR, lambda: IMAGE_REFERENCE_SUFFIXES),
    BackgroundUploadRecords(lambda name: unique_background_set_id(name), lambda: update_background_set_manifest,
                            lambda identifier, name, source: enqueue_background_set_task(identifier, name, source),
                            lambda identifier, meta: background_set_payload(identifier, meta)),
    lambda: current_owner_fields(), lambda: time.time(), lambda: training_background_sets(),
    files=_business_files,
)
_background_capture = BackgroundCapture(
    BackgroundCaptureIdentity(lambda identifier: sanitize_ai_detection_task_id(identifier), lambda: current_auth_user(), lambda value: public_path_sanitized(value)),
    BackgroundCapturePaths(lambda: IMAGE_REFERENCE_SUFFIXES, lambda: output_write_dir_for_owner, lambda path: public_output_url(path)),
    BackgroundCaptureTasks(lambda: load_ai_detection_tasks(), lambda record, user, **kwargs: require_record_access(record, user, **kwargs), lambda task: save_ai_detection_task(task)),
    BackgroundCaptureSets(lambda identifier, task, path: validate_task_environment_background_image(identifier, task, path),
                          lambda: save_task_environment_background_set),
    BackgroundCaptureState(lambda: _auto_optimize_lock, lambda identifier: load_auto_optimize_state(identifier),
                           lambda state: save_auto_optimize_state(state), lambda identifier, **kwargs: public_auto_optimize_state(identifier, **kwargs)),
    lambda: time.time(), lambda: uuid.uuid4(),
    files=_business_files,
)
_background_routes = _training_background_api.register(app, _background_query, _background_upload, _background_capture)
background_image = _background_routes.background_image
training_background_sets = _background_routes.training_background_sets
upload_training_background_set = _background_routes.upload_training_background_set
upload_ai_task_environment_background = _background_routes.upload_ai_task_environment_background

from .training.launch_submission import LaunchConfiguration, LaunchInputs, TrainingLaunchSubmission
from .training.status_query import TrainingStatusQuery
from .training import launch_api as _training_launch_api

_training_launch_submission = TrainingLaunchSubmission(
    lambda: current_auth_user(),
    LaunchConfiguration(lambda: load_config(), lambda full, user: scope_config_for_user(full, user),
                        lambda: ensure_training_assets_for_request,
                        lambda full, user, state: set_training_state_for_user(full, user, state),
                        lambda full, config, user: merge_scoped_accessory_updates(full, config, user),
                        lambda full: save_config(full)),
    LaunchInputs(lambda: selected_accessories,
                 lambda: dataset_for_training,
                 lambda config, request, selected, **kwargs: validate_approved_preview(config, request, selected, **kwargs)),
    lambda request, selected, action, **kwargs: enqueue_training_task(request, selected, action, **kwargs),
    lambda: time.time(), lambda: BACKGROUND_SIZE_MM,
)
_training_status_query = TrainingStatusQuery(
    lambda: current_auth_user(), lambda user: user_is_admin(user), lambda: load_config(),
    lambda: scope_config_for_user,
    lambda config, user, target: filtered_training_state(config, user, target),
)


request_training = _training_launch_api.register_start(app, _training_launch_submission)


from .training.runpod_transfer import RunPodTrainingTransfer, TransferPaths
from .training.runpod_upload_store import RunPodUploadStore
from .training import runpod_transfer_api as _training_transfer_api

_training_upload_store = RunPodUploadStore(lambda: runpod_yolo_artifact_max_bytes())
_training_transfer = RunPodTrainingTransfer(
    lambda job: find_training_task(job), lambda token: runpod_dataset_token_hash(token), lambda: time.time(),
    TransferPaths(lambda: resolve_service_path, lambda: OUTPUT_DIR),
    _training_upload_store, lambda: update_training_task,
)
_training_transfer_routes = _training_transfer_api.register(app, _training_transfer)
download_runpod_training_dataset = _training_transfer_routes.download_runpod_training_dataset
upload_runpod_training_artifact = _training_transfer_routes.upload_runpod_training_artifact


request_sample_generation = _training_launch_api.register_generate(app, _training_launch_submission)


from .training.dataset_input import TrainingDatasetInput
from .training.preview_approval import TrainingPreviewApproval
from .training.status_projection import StatusAccess, StatusPreview, StatusTasks, TrainingStatusProjection

_training_dataset_input = TrainingDatasetInput(
    lambda identifier, **kwargs: find_dataset_resource(identifier, **kwargs),
    lambda record, user, **kwargs: require_record_access(record, user, **kwargs),
    lambda: public_path_sanitized, files=_business_files
)
_training_preview_approval = TrainingPreviewApproval(
    lambda: TRAINING_JOBS_DIR, lambda: selected_background_set_id,
    lambda selected: preview_cache_key(selected), files=_business_files
)
_training_status_projection = TrainingStatusProjection(
    StatusTasks(lambda job: find_training_task(job), lambda task: public_refreshed_training_task(task)),
    StatusAccess(lambda task, user, target: record_visible_to_user(task, user, target),
                 lambda user: user_is_admin(user), lambda record: record_owner_id(record)),
    StatusPreview(lambda: selected_accessories, lambda selected: preview_cache_key(selected),
                  lambda state, selected: training_preview_metadata_missing(state, selected)),
)


def dataset_for_training(dataset_id: str, user: dict[str, Any] | None = None) -> dict[str, Any]:
    return _training_dataset_input.dataset_for_training(dataset_id, user)


training_status = _training_launch_api.register_status(app, _training_status_query)


def validate_approved_preview(
    config: dict[str, Any],
    request: TrainingStartRequest,
    selected: list[dict[str, Any]],
    user: dict[str, Any] | None = None,
) -> None:
    return _training_preview_approval.validate_approved_preview(config, request, selected, user)


def filtered_training_state(
    config: dict[str, Any],
    user: dict[str, Any] | None = None,
    target_user_id: str | None = None,
) -> dict[str, Any]:
    return _training_status_projection.filtered_training_state(config, user, target_user_id)


from .training.dataset_catalog import (DatasetAccess, DatasetAudit, DatasetCatalog, DatasetPaths,
                                       clean_training_resource_id)
from .training.resource_queries import (ResourceAccess, ResourceConfiguration, ResourceDatasets,
                                        ResourceRecords, TrainingResources)
from .training.resource_api import ResourceReadAccess, register as register_training_resource_api

_dataset_catalog = DatasetCatalog(
    DatasetPaths(lambda: OUTPUT_DIR, lambda: resolve_service_path,
                 lambda: training_dataset_roots(), lambda value: clean_training_resource_id(value)),
    lambda path: load_json_file_mtime_cached(path),
    DatasetAudit(lambda record, path: record_audit_fields(record, path),
                 lambda: record_created_at,
                 lambda: record_updated_at),
    DatasetAccess(lambda record, user: record_visible_to_user(record, user),
                  lambda record, user: record_mutable_by_user(record, user)),
    lambda path, **options: dataset_resource_item(path, **options),
)
_training_resources = TrainingResources(
    ResourceDatasets(lambda: training_dataset_roots(),
                     lambda path, **options: dataset_resource_item(path, **options),
                     lambda task: training_task_dataset_resource_id(task)),
    ResourceRecords(lambda **options: list_training_tasks(**options),
                    lambda: list_trained_model_specs(), lambda: load_ai_detection_tasks()),
    ResourceConfiguration(lambda: load_config(),
                          lambda: scope_config_for_user,
                          lambda task, config: serialize_ai_detection_task(task, config)),
    ResourceAccess(lambda record, user, target: record_visible_to_user(record, user, target),
                   lambda record: record_owner_username(record), lambda: LEGACY_OWNER_ID,
                   lambda record: public_path_sanitized(record)),
    lambda: resolve_service_path, lambda: OUTPUT_DIR,
)


def dataset_resource_item(dataset_dir: Path, *, include_samples: bool = True) -> dict[str, Any] | None:
    return _dataset_catalog.dataset_resource_item(dataset_dir, include_samples=include_samples)




def training_task_dataset_resource_id(task: dict[str, Any]) -> str:
    return _dataset_catalog.training_task_dataset_resource_id(task)


def find_dataset_resource(
    dataset_id: str,
    user: dict[str, Any] | None = None,
    *,
    include_samples: bool = False,
    write: bool = False,
) -> tuple[Path | None, dict[str, Any] | None]:
    return _dataset_catalog.find_dataset_resource(dataset_id, user, include_samples=include_samples, write=write)


def training_dataset_roots() -> list[Path]:
    return _dataset_catalog.training_dataset_roots()


def training_run_roots() -> list[Path]:
    return _dataset_catalog.training_run_roots()


def training_resources_payload(
    *,
    include_samples: bool = False,
    user: dict[str, Any] | None = None,
    target_user_id: str | None = None,
) -> dict[str, Any]:
    return _training_resources.training_resources_payload(include_samples=include_samples, user=user, target_user_id=target_user_id)


_training_resource_routes = register_training_resource_api(
    app,
    ResourceReadAccess(lambda: current_auth_user(), lambda user: user_is_admin(user),
                       lambda record: public_path_sanitized(record)),
    lambda: training_resources_payload,
    lambda dataset_id, **options: find_dataset_resource(dataset_id, **options),
)
training_resources = _training_resource_routes.training_resources
training_dataset_detail = _training_resource_routes.training_dataset_detail


from .training.resource_mutations import (ResourceRetirement, ResourceWriteAccess,
                                         ResourceWriteCatalog, TrainingResourceMutations)
from .training.dataset_links import DatasetLinkRecords, TrainingDatasetLinks
from .pipeline.resource_links import PipelineResourceLinks
from .training.resource_api import register_writes as register_training_resource_writes

_training_dataset_links = TrainingDatasetLinks(
    lambda: _training_task_lock,
    DatasetLinkRecords(lambda: load_training_task_records(), lambda task: save_training_task(task),
                       lambda task: training_task_dataset_resource_id(task)),
    lambda record, user: record_mutable_by_user(record, user),
    lambda value: clean_training_resource_id(value),
)
_pipeline_resource_links = PipelineResourceLinks(
    lambda: _pipeline_tasks_lock, lambda: load_pipeline_tasks(),
    lambda tasks, changed: save_pipeline_task_batch_changes(tasks, changed),
    lambda record, user: record_mutable_by_user(record, user),
)
_training_resource_mutations = TrainingResourceMutations(
    ResourceWriteAccess(lambda: current_auth_user(),
                        lambda record, user, **options: require_record_access(record, user, **options),
                        lambda record: record_owner_id(record),
                        lambda: assert_unique_dataset_name,
                        lambda: assert_unique_model_name),
    ResourceWriteCatalog(lambda dataset_id, **options: find_dataset_resource(dataset_id, **options),
                         lambda: list_trained_model_specs(), lambda: resolve_service_path,
                         lambda **options: training_resources_payload(**options)),
    ResourceRetirement(lambda identifier, user, **options: delete_training_dataset_resource(identifier, user, **options),
                       lambda identifier, user, **options: delete_training_model_resource(identifier, user, **options),
                       lambda identifier, user: mark_training_task_dataset_deleted(identifier, user),
                       lambda identifier, user: mark_pipeline_dataset_deleted(identifier, user),
                       lambda identifier, user: mark_pipeline_model_deleted(identifier, user)), files=_business_files
)


def delete_training_dataset_resource(dataset_id: str, user: dict[str, Any], *, missing_ok: bool = False) -> dict[str, Any] | None:
    return _training_resource_mutations.delete_training_dataset_resource(dataset_id, user, missing_ok=missing_ok)


def mark_pipeline_dataset_deleted(dataset_id: str, user: dict[str, Any]) -> int:
    return _pipeline_resource_links.mark_pipeline_dataset_deleted(dataset_id, user)


def mark_training_task_dataset_deleted(dataset_id: str, user: dict[str, Any]) -> int:
    return _training_dataset_links.mark_training_task_dataset_deleted(dataset_id, user)


_training_resource_write_routes = register_training_resource_writes(app, _training_resource_mutations)
delete_training_dataset = _training_resource_write_routes.delete_training_dataset
update_training_dataset = _training_resource_write_routes.update_training_dataset
delete_training_dataset_sample = _training_resource_write_routes.delete_training_dataset_sample
delete_training_model = _training_resource_write_routes.delete_training_model
update_training_model = _training_resource_write_routes.update_training_model






def delete_training_model_resource(run_id: str, user: dict[str, Any], *, missing_ok: bool = False) -> dict[str, Any] | None:
    return _training_resource_mutations.delete_training_model_resource(run_id, user, missing_ok=missing_ok)


def mark_pipeline_model_deleted(run_id: str, user: dict[str, Any]) -> int:
    return _pipeline_resource_links.mark_pipeline_model_deleted(run_id, user)






from .training.preview_query import PlanAccess, PlanBackgrounds, PlanConfiguration, TrainingPlanQuery
from .training.preview_artifacts import PreviewArtifactStore
from .training.preview_submission import (PreviewConfiguration, PreviewPolicy, PreviewSelection,
                                          TrainingPreviewSubmission)
from .training.preview_api import register as register_training_preview_api

_training_plan_query = TrainingPlanQuery(
    PlanAccess(lambda: current_auth_user(), lambda user: user_is_admin(user), lambda: public_path_sanitized),
    PlanConfiguration(lambda: load_config(),
                      lambda: scope_config_for_user,
                      lambda config, user, target: filtered_training_state(config, user, target)),
    PlanBackgrounds(lambda user, target: list_background_sets(user, target),
                    lambda: selected_background_set_id,
                    lambda: BACKGROUND_SIZE_MM),
    lambda: serialize_accessory_items,
    lambda **kwargs: training_execution_status(**kwargs),
)
_training_preview_artifacts = PreviewArtifactStore(lambda kind: output_write_dir(kind), lambda: TRAINING_JOBS_DIR, files=_business_files)
_training_preview_submission = TrainingPreviewSubmission(
    current=lambda: current_auth_user(),
    config=PreviewConfiguration(
        load=lambda: load_config(), scope=lambda config, user: scope_config_for_user(config, user),
        ensure=lambda: ensure_training_assets_for_request,
        set_state=lambda full, user, state: set_training_state_for_user(full, user, state),
        merge=lambda full, config, user: merge_scoped_accessory_updates(full, config, user),
        save=lambda full: save_config(full),
    ),
    selection=PreviewSelection(
        selected=lambda: selected_accessories, uid=lambda item: accessory_uid(item),
        material=lambda item: accessory_material_type(item), sprites=lambda item: clean_sprite_assets(item),
        version=lambda item: accessory_sprite_version(item), cache=lambda selected: preview_cache_key(selected),
    ),
    policy=PreviewPolicy(
        normalize=lambda: normalize_preview_pose_family_policy,
        background=lambda: selected_background_set_id,
        sequence=lambda selected, count, policy: preview_pose_family_sequence(selected, count, policy),
        label=lambda sequence: preview_pose_family_sequence_label(sequence),
    ),
    artifacts=_training_preview_artifacts,
    draw=lambda: draw_training_preview,
    clock=lambda: time.time(), uuid=lambda: uuid.uuid4(),
)
_training_preview_routes = register_training_preview_api(app, _training_plan_query, _training_preview_submission)
training_plan = _training_preview_routes.training_plan
training_preview = _training_preview_routes.training_preview


# ============================================================
# Agent 化流水线编排:Agent 配置 / 参数推荐 / 看板任务
# ============================================================

AGENT_LOCAL_CONFIG_PATH = DATA_DIR / "agent_config.local.json"
PIPELINE_STATE_PATH = DATA_DIR / "pipeline_state.json"
from .pipeline.runtime_state import PipelineRuntimeState
_pipeline_runtime = PipelineRuntimeState()
_pipeline_tasks_lock = _pipeline_runtime.task_lock
_pipeline_state_lock = _pipeline_runtime.state_lock

AGENT_PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
AGENT_PROVIDER_CURSOR = "cursor"
AGENT_SUPPORTED_PROVIDERS = {AGENT_PROVIDER_OPENAI_COMPATIBLE, AGENT_PROVIDER_CURSOR}
AGENT_CURSOR_DEFAULT_BASE_URL = "https://api.cursor.com"
AGENT_CONNECTION_STATUSES = {"untested", "connected", "failed"}
AGENT_CURSOR_RECOMMENDATION_MESSAGE = "Cursor 已连接；参数推荐需要 Cursor Cloud Agent run 配置，当前使用规则推荐"

DEFAULT_AGENT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "provider": AGENT_PROVIDER_OPENAI_COMPATIBLE,
    "base_url": "",
    "api_key_env": "",
    "api_keys": [],
    "active_key_id": "",
    "api_key": "",
    "model": "",
    "model_options": [],
    "timeout_seconds": 45.0,
    "auto_advance_default": True,
    "connection_status": "untested",
    "connection_message": "",
    "last_tested_at": 0,
    "last_model_count": 0,
}

ACCESSORY_DETECTION_ROUTES = {"yolo", "ai", "archive_only"}
PIPELINE_DETECTION_METHODS = {"yolo", "yolo_ocr", "ai", "label_text_compare"}
PIPELINE_TRAINING_METHODS = {"yolo", "yolo_ocr"}
PIPELINE_STAGE_ORDER = ["draft", "samples", "training", "library"]
PIPELINE_DASHBOARD_AI_TASK_SOURCE = "pipeline_dashboard"
AGENT_MCP_ORCHESTRATION_VERSION = "agent-mcp-yolo-preview-v1"
AGENT_MCP_GEMINI_IMAGE_MODEL_ENV = "VANTALINE_GEMINI_IMAGE_MODEL"
AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV = "VANTALINE_GEMINI_IMAGE_TIMEOUT_SECONDS"
AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL = "gemini-3.1-flash-image"
AGENT_MCP_GEMINI_IMAGE_HIGH_FIDELITY_MODEL = "gemini-3-pro-image"
AGENT_MCP_GEMINI_IMAGE_DEFAULT_TIMEOUT_SECONDS = 120.0
AGENT_MCP_TOOL_POSE_IMAGE = "generate_accessory_pose_image"
AGENT_MCP_TOOL_SAMPLES = "generate_training_samples"
AGENT_MCP_TOOL_TRAINING = "start_model_training"
AGENT_MCP_CONVERSATION_LIMIT = 60
AGENT_MCP_AUTO_MAX_STEPS = 12
AGENT_PIPELINE_ACTIONS = {
    "advance",
    "set_params",
    "goto_stage",
    "retry",
    "replan",
    "pause_and_ask",
    "continue_existing_assets",
    "continue_training",
    "cancel",
    "reply",
}
AGENT_PIPELINE_STAGE_TARGETS = {"draft", "samples"}
_pipeline_auto_agent_lock = _pipeline_runtime.auto_agent_lock
_pipeline_auto_agent_inflight = _pipeline_runtime.auto_agent_inflight
_pipeline_recommendation_lock = _pipeline_runtime.recommendation_lock
_pipeline_recommendation_inflight = _pipeline_runtime.recommendation_inflight
# Async pipeline-advance runner state. Every advance (manual endpoint, GET-list
# auto-advance, chat/agent-feedback) is executed by a single per-task background
# thread so heavy/bounded compute never runs under _pipeline_tasks_lock and a
# stuck task can be cancelled. The inflight set guarantees idempotency (one
# thread per task); the cancel map lets delete/cancel stop a running advance.
_pipeline_advance_registry_lock = _pipeline_runtime.advance_registry_lock
_pipeline_advance_inflight = _pipeline_runtime.advance_inflight
_pipeline_advance_cancel = _pipeline_runtime.advance_cancel
# A task left in the advancing state longer than this with no live worker thread
# is treated as a zombie (e.g. the process restarted mid-advance) and reset.
PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S = 600


class PipelineAdvanceCancelled(Exception):
    """Raised inside advance_pipeline_task when the task's cancel event fires."""


from .agent.settings_policy import AgentSettingsPolicy as _AgentSettingsPolicy
from .agent.settings_projection import AgentSettingsProjection as _AgentSettingsProjection
from .agent.legacy_settings_store import LegacyAgentSettingsStore as _LegacyAgentSettingsStore
from .agent.settings_ports import AgentSettingsDefaults as _AgentSettingsDefaults, AgentProviderPolicy as _AgentProviderPolicy, AgentSettingsKeys as _AgentSettingsKeys, AgentSettingsAccess as _AgentSettingsAccess, AgentSettingsAuthorization as _AgentSettingsAuthorization, AgentSettingsPresentation as _AgentSettingsPresentation, AgentSettingsPaths as _AgentSettingsPaths, AgentSettingsCodec as _AgentSettingsCodec, AgentSettingsFiles as _AgentSettingsFiles, AgentSettingsPersistence as _AgentSettingsPersistence
_agent_settings_policy = _AgentSettingsPolicy(
    _AgentSettingsDefaults(cursor=lambda: AGENT_PROVIDER_CURSOR, openai=lambda: AGENT_PROVIDER_OPENAI_COMPATIBLE, config=lambda: DEFAULT_AGENT_CONFIG, cursor_url=lambda: AGENT_CURSOR_DEFAULT_BASE_URL, statuses=lambda: AGENT_CONNECTION_STATUSES),
    _AgentProviderPolicy(split_url=lambda: urlsplit, host=lambda: agent_base_url_host, is_cursor=lambda: is_cursor_base_url, detect=lambda: detect_agent_provider_from_base_url, normalize=lambda: normalize_agent_provider, options=lambda: normalize_agent_model_options),
    _AgentSettingsKeys(validate_environment=lambda: validate_ai_key_env, normalize=lambda: normalize_agent_key_items, for_provider=lambda: agent_keys_for_provider, environment_value=lambda: local_secret_env_value),
)
_agent_settings_projection = _AgentSettingsProjection(
    _AgentSettingsDefaults(cursor=lambda: AGENT_PROVIDER_CURSOR, openai=lambda: AGENT_PROVIDER_OPENAI_COMPATIBLE, config=lambda: DEFAULT_AGENT_CONFIG, cursor_url=lambda: AGENT_CURSOR_DEFAULT_BASE_URL, statuses=lambda: AGENT_CONNECTION_STATUSES),
    _AgentProviderPolicy(split_url=lambda: urlsplit, host=lambda: agent_base_url_host, is_cursor=lambda: is_cursor_base_url, detect=lambda: detect_agent_provider_from_base_url, normalize=lambda: normalize_agent_provider, options=lambda: normalize_agent_model_options),
    _AgentSettingsAccess(required=lambda: agent_required_fields_present, credentials=lambda: agent_credentials_present, connected=lambda: agent_connected, recommendation=lambda: agent_recommendation_supported, load=lambda: load_agent_config),
    _AgentSettingsAuthorization(is_admin=lambda: user_is_admin, current_user=lambda: current_auth_user),
    _AgentSettingsKeys(validate_environment=lambda: validate_ai_key_env, normalize=lambda: normalize_agent_key_items, for_provider=lambda: agent_keys_for_provider, environment_value=lambda: local_secret_env_value),
    _AgentSettingsPresentation(provider_label=lambda: agent_provider_label, public_keys=lambda: public_ai_key_items, mask=lambda: mask_secret),
)
_legacy_agent_settings_store = _LegacyAgentSettingsStore(
    _AgentSettingsDefaults(cursor=lambda: AGENT_PROVIDER_CURSOR, openai=lambda: AGENT_PROVIDER_OPENAI_COMPATIBLE, config=lambda: DEFAULT_AGENT_CONFIG, cursor_url=lambda: AGENT_CURSOR_DEFAULT_BASE_URL, statuses=lambda: AGENT_CONNECTION_STATUSES),
    _AgentSettingsPaths(file=lambda: AGENT_LOCAL_CONFIG_PATH, directory=lambda: DATA_DIR),
    _AgentSettingsCodec(loads=lambda: json.loads, dumps=lambda: json.dumps, decode_error=lambda: json.JSONDecodeError),
    _AgentSettingsFiles(replace=lambda: os.replace, chmod=lambda: os.chmod),
    _AgentSettingsPersistence(normalize=lambda: normalize_agent_config, keys=lambda: normalize_agent_key_items, persist=lambda: persist_secret_key_items),
)

def agent_base_url_host(base_url: str) -> str:
    return _agent_settings_policy.agent_base_url_host(base_url)


def is_cursor_base_url(base_url: str) -> bool:
    return _agent_settings_policy.is_cursor_base_url(base_url)


def detect_agent_provider_from_base_url(base_url: str) -> str:
    return _agent_settings_policy.detect_agent_provider_from_base_url(base_url)


def normalize_agent_provider(provider: str | None, base_url: str = "") -> str:
    return _agent_settings_policy.normalize_agent_provider(provider, base_url)


def agent_provider_label(provider: str) -> str:
    return _agent_settings_policy.agent_provider_label(provider)


def normalize_agent_model_options(value: Any) -> list[dict[str, str]]:
    return _agent_settings_policy.normalize_agent_model_options(value)


def agent_model_options_from_items(items: Any, *, prepend: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    return _agent_settings_policy.agent_model_options_from_items(items, prepend=prepend)


def normalize_agent_config(config: dict[str, Any]) -> dict[str, Any]:
    return _agent_settings_policy.normalize_agent_config(config)


def agent_required_fields_present(config: dict[str, Any]) -> bool:
    return _agent_settings_projection.agent_required_fields_present(config)


def agent_credentials_present(config: dict[str, Any]) -> bool:
    return _agent_settings_projection.agent_credentials_present(config)


def agent_connected(config: dict[str, Any]) -> bool:
    return _agent_settings_projection.agent_connected(config)


def agent_recommendation_supported(config: dict[str, Any]) -> bool:
    return _agent_settings_projection.agent_recommendation_supported(config)


def _legacy_load_agent_config() -> dict[str, Any]:
    return _legacy_agent_settings_store._legacy_load_agent_config()


def save_agent_config(config: dict[str, Any]) -> None:
    return _legacy_agent_settings_store.save_agent_config(config)


def agent_configured(config: dict[str, Any] | None = None) -> bool:
    return _agent_settings_projection.agent_configured(config)


def public_agent_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _agent_settings_projection.public_agent_config(config)


from .agent.protocol_policy import AgentProtocolPolicy as _AgentProtocolPolicy
from .agent.chat_transport import AgentChatTransport as _AgentChatTransport
from .agent.connection_discovery import AgentConnectionDiscovery as _AgentConnectionDiscovery
from .agent.recommendation import AgentRecommendation as _AgentRecommendation
from .agent.invocation_ports import AgentProtocolRuntime as _AgentProtocolRuntime, AgentInvocationSettings as _AgentInvocationSettings, AgentHttpIO as _AgentHttpIO, AgentInvocationCodec as _AgentInvocationCodec, AgentChatCalls as _AgentChatCalls, AgentModelCalls as _AgentModelCalls, AgentResponseParsing as _AgentResponseParsing, AgentRecommendationInputs as _AgentRecommendationInputs, AgentRecommendationCalls as _AgentRecommendationCalls
_agent_protocol_policy = _AgentProtocolPolicy(
    _AgentProtocolRuntime(base64_encode=lambda: base64.b64encode, cursor_base_url=lambda: AGENT_CURSOR_DEFAULT_BASE_URL),
)
_agent_chat_transport = _AgentChatTransport(
    _AgentInvocationSettings(load=lambda: load_agent_config, normalize_provider=lambda: normalize_agent_provider, openai_provider=lambda: AGENT_PROVIDER_OPENAI_COMPATIBLE, cursor_provider=lambda: AGENT_PROVIDER_CURSOR, cursor_message=lambda: AGENT_CURSOR_RECOMMENDATION_MESSAGE, is_cursor_url=lambda: is_cursor_base_url, required=lambda: agent_required_fields_present, connected=lambda: agent_connected, recommended=lambda: agent_recommendation_supported),
    _AgentHttpIO(request=lambda: urllib.request.Request, open=lambda: urllib.request.urlopen, http_error=lambda: urllib.error.HTTPError, url_error=lambda: urllib.error.URLError, error_message=lambda: agent_http_error_message, text=lambda: bounded_text),
    _AgentInvocationCodec(loads=lambda: json.loads, dumps=lambda: json.dumps),
    _AgentChatCalls(chat_url=lambda: openai_compatible_chat_url, legacy_chat=lambda: agent_openai_chat_completion, generate=lambda: generate_provider_json_with_fallback),
)
_agent_connection_discovery = _AgentConnectionDiscovery(
    _AgentInvocationSettings(load=lambda: load_agent_config, normalize_provider=lambda: normalize_agent_provider, openai_provider=lambda: AGENT_PROVIDER_OPENAI_COMPATIBLE, cursor_provider=lambda: AGENT_PROVIDER_CURSOR, cursor_message=lambda: AGENT_CURSOR_RECOMMENDATION_MESSAGE, is_cursor_url=lambda: is_cursor_base_url, required=lambda: agent_required_fields_present, connected=lambda: agent_connected, recommended=lambda: agent_recommendation_supported),
    _AgentHttpIO(request=lambda: urllib.request.Request, open=lambda: urllib.request.urlopen, http_error=lambda: urllib.error.HTTPError, url_error=lambda: urllib.error.URLError, error_message=lambda: agent_http_error_message, text=lambda: bounded_text),
    _AgentInvocationCodec(loads=lambda: json.loads, dumps=lambda: json.dumps),
    _AgentModelCalls(models_url=lambda: openai_compatible_models_url, auth_headers=lambda: cursor_auth_headers, cursor_url=lambda: cursor_api_url, options=lambda: agent_model_options_from_items, available=lambda: cursor_model_available, fetch=lambda: fetch_openai_compatible_model_options, cursor_test=lambda: test_cursor_agent_connection, openai_test=lambda: test_openai_agent_connection, legacy_chat=lambda: agent_openai_chat_completion),
)
_agent_recommendation = _AgentRecommendation(
    _AgentInvocationSettings(load=lambda: load_agent_config, normalize_provider=lambda: normalize_agent_provider, openai_provider=lambda: AGENT_PROVIDER_OPENAI_COMPATIBLE, cursor_provider=lambda: AGENT_PROVIDER_CURSOR, cursor_message=lambda: AGENT_CURSOR_RECOMMENDATION_MESSAGE, is_cursor_url=lambda: is_cursor_base_url, required=lambda: agent_required_fields_present, connected=lambda: agent_connected, recommended=lambda: agent_recommendation_supported),
    _AgentInvocationCodec(loads=lambda: json.loads, dumps=lambda: json.dumps),
    _AgentResponseParsing(substitute=lambda: re.sub, search=lambda: re.search, dotall=lambda: re.DOTALL),
    _AgentRecommendationInputs(config=lambda: load_config, selected=lambda: selected_accessories, material=lambda: accessory_material_type, background=lambda: selected_background_set_id, current_user=lambda: _request_user.get, selection_error=lambda: HTTPException),
    _AgentRecommendationCalls(rule=lambda: rule_recommendation, chat=lambda: agent_chat_completion, parse=lambda: parse_agent_json, clamp=lambda: clamp_recommend_params),
)

def openai_compatible_chat_url(base_url: str) -> str:
    return _agent_protocol_policy.openai_compatible_chat_url(base_url)


def openai_compatible_models_url(base_url: str) -> str:
    return _agent_protocol_policy.openai_compatible_models_url(base_url)


def agent_http_error_message(prefix: str, exc: urllib.error.HTTPError) -> str:
    return _agent_chat_transport.agent_http_error_message(prefix, exc)


def agent_openai_chat_completion(
    messages: list[dict[str, str]],
    config: dict[str, Any] | None = None,
    *,
    require_connected: bool = True,
) -> str:
    return _agent_chat_transport.agent_openai_chat_completion(messages, config, require_connected=require_connected)


def agent_chat_completion(messages: list[dict[str, str]], config: dict[str, Any] | None = None) -> str:
    return _agent_chat_transport.agent_chat_completion(messages, config)


def cursor_auth_headers(api_key: str) -> dict[str, str]:
    return _agent_protocol_policy.cursor_auth_headers(api_key)


def cursor_api_url(base_url: str, path: str) -> str:
    return _agent_protocol_policy.cursor_api_url(base_url, path)


def cursor_model_available(model: str, items: list[dict[str, Any]]) -> bool:
    return _agent_protocol_policy.cursor_model_available(model, items)


def fetch_openai_compatible_model_options(config: dict[str, Any]) -> list[dict[str, str]]:
    return _agent_connection_discovery.fetch_openai_compatible_model_options(config)


def test_cursor_agent_connection(config: dict[str, Any]) -> dict[str, Any]:
    return _agent_connection_discovery.test_cursor_agent_connection(config)


def test_openai_agent_connection(config: dict[str, Any]) -> dict[str, Any]:
    return _agent_connection_discovery.test_openai_agent_connection(config)


def test_agent_connection(config: dict[str, Any]) -> dict[str, Any]:
    return _agent_connection_discovery.test_agent_connection(config)


def parse_agent_json(content: str) -> dict[str, Any]:
    return _agent_recommendation.parse_agent_json(content)


def rule_recommendation(stage: str, selected: list[dict[str, Any]], sample_count: int | None = None) -> dict[str, Any]:
    return _agent_recommendation.rule_recommendation(stage, selected, sample_count)


def clamp_recommend_params(stage: str, params: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    return _agent_recommendation.clamp_recommend_params(stage, params, fallback)


def agent_recommendation(stage: str, accessory_ids: list[str], sample_count: int | None = None) -> dict[str, Any]:
    return _agent_recommendation.agent_recommendation(stage, accessory_ids, sample_count)


from .agent.settings_api import AgentSettingsApi as _AgentSettingsApi
from .agent.settings_api_ports import AgentSettingsHttpAccess as _AgentSettingsHttpAccess, AgentSettingsProjectionCall as _AgentSettingsProjectionCall, AgentRecommendationCall as _AgentRecommendationCall, AgentLegacySettingsPolicy as _AgentLegacySettingsPolicy, AgentLegacyKeyPolicy as _AgentLegacyKeyPolicy, AgentLegacySettingsEffects as _AgentLegacySettingsEffects
_agent_settings_api = _AgentSettingsApi(
    _AgentSettingsHttpAccess(admin=lambda: require_admin_role, http_error=lambda: HTTPException),
    _AgentSettingsProjectionCall(public=lambda: public_agent_config),
    _AgentRecommendationCall(recommend=lambda: agent_recommendation),
    _AgentLegacySettingsPolicy(load=lambda: load_agent_config, normalize=lambda: normalize_agent_config, credentials=lambda: agent_credentials_present, provider=lambda: normalize_agent_provider, supported=lambda: AGENT_SUPPORTED_PROVIDERS, cursor=lambda: AGENT_PROVIDER_CURSOR, label=lambda: agent_provider_label, options=lambda: normalize_agent_model_options),
    _AgentLegacyKeyPolicy(validate=lambda: validate_ai_key_env, name=lambda: default_secret_env_name, normalize=lambda: normalize_agent_key_items, identity=lambda: secret_key_item_id, for_provider=lambda: agent_keys_for_provider),
    _AgentLegacySettingsEffects(save=lambda: save_agent_config, secret=lambda: set_local_secret_env, test=lambda: test_agent_connection, now=lambda: time.time),
)

@app.get("/api/agent/config")
def get_agent_config() -> dict[str, Any]:
    return _agent_settings_api.get_agent_config()


@app.post("/api/agent/config")
def update_agent_config(request: AgentConfigRequest) -> dict[str, Any]:
    return _agent_settings_api.update_agent_config(request)


@app.post("/api/agent/config/test")
def test_agent_config() -> dict[str, Any]:
    return _agent_settings_api.test_agent_config()


@app.post("/api/agent/recommend")
def agent_recommend(request: AgentRecommendRequest) -> dict[str, Any]:
    return _agent_settings_api.agent_recommend(request)


from .pipeline.state_policy import normalize_pipeline_state
from .pipeline.state_store import PipelineStateStore, PipelineStatePaths, PipelineStateRows

_pipeline_state_store = PipelineStateStore(
    repository=lambda: runtime_postgres_repository_or_none(),
    paths=PipelineStatePaths(data=lambda: DATA_DIR, state=lambda: PIPELINE_STATE_PATH),
    rows=PipelineStateRows(encode=lambda: pipeline_state_rows,
                           decode=lambda: pipeline_state_from_rows),
    guard=lambda: _pipeline_state_lock,
)


def load_pipeline_tasks() -> list[dict[str, Any]]:
    return _pipeline_task_store.load_pipeline_tasks()


def save_pipeline_tasks(tasks: list[dict[str, Any]]) -> None:
    return _pipeline_task_store.save_pipeline_tasks(tasks)


def load_pipeline_task(task_id: str) -> dict[str, Any] | None:
    return _pipeline_task_store.load_pipeline_task(task_id)


def save_pipeline_task(task: dict[str, Any]) -> dict[str, Any] | None:
    return _pipeline_task_store.save_pipeline_task(task)


def delete_pipeline_task_row(task_id: str) -> bool:
    return _pipeline_task_store.delete_pipeline_task_row(task_id)


def mark_pipeline_task_advancing(task: dict[str, Any]) -> None:
    'Flag a task (in memory) as queued for the async advance runner. The caller\n    persists it and then schedules the worker after releasing _pipeline_tasks_lock.'
    return _pipeline_task_mutations.mark_pipeline_task_advancing(task)


def persist_pipeline_task_progress(
    task_id: str,
    *,
    job_note: str | None = None,
    progress: int | None = None,
    status: str | None = None,
) -> None:
    'Write live sub-step progress to the stored task record so the UI reflects\n    an in-flight advance immediately. Safe to call from the advance worker thread\n    (it briefly takes _pipeline_tasks_lock); never call while already holding it.'
    return _pipeline_task_mutations.persist_pipeline_task_progress(task_id, job_note=job_note, progress=progress, status=status)


def normalize_pipeline_detection_method(value: str | None) -> str:
    return _pipeline_task_metadata.normalize_pipeline_detection_method(value)


def pipeline_method_uses_training(method: str | None) -> bool:
    return _pipeline_task_metadata.pipeline_method_uses_training(method)


from .pipeline.candidate_flow import PipelineCandidateFlow
from .pipeline.candidate_flow_ports import CandidateStorage, CandidateProgress, CandidateProjection

_pipeline_candidate_flow = PipelineCandidateFlow(
    storage=CandidateStorage(
        ACCESSORY_CANDIDATES_DIR=lambda: ACCESSORY_CANDIDATES_DIR,
        _candidate_store_lock=lambda: _candidate_store_lock,
        runtime_postgres_repository_or_none=lambda: runtime_postgres_repository_or_none,
        load_accessory_candidate=lambda: load_accessory_candidate,
        HTTPException=lambda: HTTPException,
        _business_files=lambda: _business_files,
        save_accessory_candidate=lambda: save_accessory_candidate,
        load_config=lambda: load_config,
        load_pipeline_state=lambda: load_pipeline_state,
        update_pipeline_state=lambda: update_pipeline_state,
    ),
    progress=CandidateProgress(
        candidate_image_jobs=lambda: candidate_image_jobs,
        IMAGE_JOB_ACTIVE_STATUSES=lambda: IMAGE_JOB_ACTIVE_STATUSES,
        candidate_confirmed_accessory_id=lambda: candidate_confirmed_accessory_id,
        ensure_candidate_image_job_task_ids=lambda: ensure_candidate_image_job_task_ids,
        refresh_codex_image_job=lambda: refresh_codex_image_job,
        store_candidate_image_job=lambda: store_candidate_image_job,
        refresh_pipeline_candidate=lambda: refresh_pipeline_candidate,
    ),
    projection=CandidateProjection(
        resolve_accessory_id=lambda: resolve_accessory_id,
        enrich_record_audit_fields=lambda: enrich_record_audit_fields,
        pipeline_candidate_job_status=lambda: pipeline_candidate_job_status,
        accessory_material_type=lambda: accessory_material_type,
        LEGACY_OWNER_ID=lambda: LEGACY_OWNER_ID,
        record_owner_username=lambda: record_owner_username,
        accessory_lookup_by_id=lambda: accessory_lookup_by_id,
        record_visible_to_user=lambda: record_visible_to_user,
        pipeline_candidate_public=lambda: pipeline_candidate_public,
        canonical_pipeline_accessory_ids=lambda: canonical_pipeline_accessory_ids,
        serialize_accessory=lambda: serialize_accessory,
    ),
)


def canonical_pipeline_accessory_ids(config: dict[str, Any], raw_ids: list[str]) -> list[str]:
    return _pipeline_candidate_flow.canonical_pipeline_accessory_ids(config, raw_ids)




def load_pipeline_state() -> dict[str, list[str]]:
    return _pipeline_state_store.load_pipeline_state()


def save_pipeline_state(state: dict[str, list[str]]) -> None:
    return _pipeline_state_store.save_pipeline_state(state)


def save_pipeline_state_keys(state: dict[str, list[str]], changed_keys: set[str]) -> None:
    return _pipeline_state_store.save_pipeline_state_keys(state, changed_keys)


def update_pipeline_state(mutator: Callable[[dict[str, list[str]]], None]) -> dict[str, list[str]]:
    return _pipeline_state_store.update_pipeline_state(mutator)


def add_pipeline_accessory_id(accessory_id: str) -> dict[str, list[str]]:
    return _pipeline_state_store.add_pipeline_accessory_id(accessory_id)


def remove_pipeline_accessory_id(accessory_id: str) -> dict[str, list[str]]:
    return _pipeline_state_store.remove_pipeline_accessory_id(accessory_id)


def add_pipeline_pending_candidate_id(candidate_id: str) -> dict[str, list[str]]:
    return _pipeline_state_store.add_pipeline_pending_candidate_id(candidate_id)


def remove_pipeline_pending_candidate_id(candidate_id: str) -> dict[str, list[str]]:
    return _pipeline_state_store.remove_pipeline_pending_candidate_id(candidate_id)


def candidate_confirmed_accessory_id(candidate: dict[str, Any]) -> str:
    return _pipeline_candidate_flow.candidate_confirmed_accessory_id(candidate)


def pipeline_candidate_job_status(candidate: dict[str, Any]) -> tuple[str, int, str]:
    return _pipeline_candidate_flow.pipeline_candidate_job_status(candidate)


def pipeline_candidate_public(candidate: dict[str, Any]) -> dict[str, Any]:
    return _pipeline_candidate_flow.pipeline_candidate_public(candidate)


def refresh_pipeline_candidate(candidate_id: str) -> tuple[dict[str, Any] | None, bool]:
    return _pipeline_candidate_flow.refresh_pipeline_candidate(candidate_id)


def pipeline_accessories_payload(
    config: dict[str, Any] | None = None,
    user: dict[str, Any] | None = None,
    target_user_id: str | None = None,
) -> dict[str, Any]:
    return _pipeline_candidate_flow.pipeline_accessories_payload(config, user, target_user_id)


from .pipeline.task_snapshots import PipelineTaskSnapshots as _PipelineTaskSnapshots
from .pipeline.task_snapshot_ports import PipelineTaskSnapshotLinks as _PipelineTaskSnapshotLinks

_pipeline_task_snapshots = _PipelineTaskSnapshots(
    _PipelineTaskSnapshotLinks(
        load_ai_tasks=lambda: load_ai_detection_tasks,
        accessory_lookup=lambda: accessory_lookup_by_id,
        label_snapshot=lambda: pipeline_task_label_snapshot,
    )
)


def pipeline_task_label_snapshot(task: dict[str, Any]) -> dict[str, str]:
    return _pipeline_task_snapshots.pipeline_task_label_snapshot(task)


def pipeline_task_accessory_snapshot(config: dict[str, Any], task: dict[str, Any], accessory_ids: list[str]) -> tuple[dict[str, str], list[str]]:
    return _pipeline_task_snapshots.pipeline_task_accessory_snapshot(config, task, accessory_ids)


def ensure_pipeline_task_accessory_objects(config: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    return _pipeline_task_metadata.ensure_pipeline_task_accessory_objects(config, tasks)


from .pipeline.resource_status import PipelineResourceStatus as _PipelineResourceStatus
from .pipeline.resource_status_ports import PipelineResourceStatusLinks as _PipelineResourceStatusLinks

_pipeline_resource_status = _PipelineResourceStatus(
    _PipelineResourceStatusLinks(
        find_dataset=lambda: find_dataset_resource,
        load_ai_tasks=lambda: load_ai_detection_tasks,
        list_trained_specs=lambda: list_trained_model_specs,
    )
)


def pipeline_task_dataset_status(task: dict[str, Any]) -> str:
    return _pipeline_resource_status.pipeline_task_dataset_status(task)


def pipeline_task_model_status(
    task: dict[str, Any],
    *,
    ai_task_ids: set[str] | None = None,
    trained_model_specs: list[dict[str, Any]] | None = None,
) -> str:
    return _pipeline_resource_status.pipeline_task_model_status(
        task, ai_task_ids=ai_task_ids, trained_model_specs=trained_model_specs
    )


from .pipeline.auto_optimization_links import PipelineAutoOptimizationLinks
from .pipeline.auto_optimization_links_ports import LinkState, LinkProjection, LinkMatching

_auto_optimization_links = PipelineAutoOptimizationLinks(
    state=LinkState(
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        _auto_optimize_lock=lambda: _auto_optimize_lock,
        load_auto_optimize_state=lambda: load_auto_optimize_state,
        auto_optimize_completed_model_id=lambda: auto_optimize_completed_model_id,
        auto_optimize_stop_capture_for_model_locked=lambda: auto_optimize_stop_capture_for_model_locked,
        save_auto_optimize_state=lambda: save_auto_optimize_state,
        fast_completed_auto_optimize_model_id=lambda: fast_completed_auto_optimize_model_id,
        list_auto_optimize_states=lambda: list_auto_optimize_states,
        auto_optimize_states_by_task_id=lambda: auto_optimize_states_by_task_id,
    ),
    projection=LinkProjection(
        auto_optimize_phase_name=lambda: auto_optimize_phase_name,
        ai_detection_task_model_id=lambda: ai_detection_task_model_id,
        public_auto_optimize_link_for_task_id=lambda: public_auto_optimize_link_for_task_id,
    ),
    matching=LinkMatching(
        canonical_pipeline_accessory_ids=lambda: canonical_pipeline_accessory_ids,
        normalize_pipeline_accessory_counts=lambda: normalize_pipeline_accessory_counts,
    ),
)


def fast_completed_auto_optimize_model_id(state: dict[str, Any]) -> str:
    return _auto_optimization_links.fast_completed_auto_optimize_model_id(state)


def public_auto_optimize_link_for_task_id(task_id: str, *, source: str, state: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return _auto_optimization_links.public_auto_optimize_link_for_task_id(task_id, source=source, state=state)


def auto_optimize_states_by_task_id(states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _auto_optimization_links.auto_optimize_states_by_task_id(states)


def pipeline_task_auto_optimize_link(
    task: dict[str, Any],
    config: dict[str, Any],
    *,
    auto_optimize_states: list[dict[str, Any]] | None = None,
    auto_optimize_states_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    return _auto_optimization_links.pipeline_task_auto_optimize_link(task, config, auto_optimize_states=auto_optimize_states, auto_optimize_states_by_id=auto_optimize_states_by_id)


from .pipeline.task_projection import PipelineTaskProjection
from .pipeline.task_projection_ports import ProjectionMetadata, ProjectionResources

_task_projection = PipelineTaskProjection(
    metadata=ProjectionMetadata(
        accessory_lookup_by_id=lambda: accessory_lookup_by_id,
        enrich_record_audit_fields=lambda: enrich_record_audit_fields,
        normalize_pipeline_detection_method=lambda: normalize_pipeline_detection_method,
        pipeline_method_uses_training=lambda: pipeline_method_uses_training,
        resolve_accessory_id=lambda: resolve_accessory_id,
        normalize_pipeline_accessory_counts=lambda: normalize_pipeline_accessory_counts,
        pipeline_task_accessory_snapshot=lambda: pipeline_task_accessory_snapshot,
        accessory_material_type=lambda: accessory_material_type,
    ),
    resources=ProjectionResources(
        pipeline_task_dataset_status=lambda: pipeline_task_dataset_status,
        pipeline_task_model_status=lambda: pipeline_task_model_status,
        pipeline_task_auto_optimize_link=lambda: pipeline_task_auto_optimize_link,
        public_path_sanitized=lambda: public_path_sanitized,
    ),
)


def pipeline_task_public(
    task: dict[str, Any],
    config: dict[str, Any],
    *,
    ai_task_ids: set[str] | None = None,
    trained_model_specs: list[dict[str, Any]] | None = None,
    auto_optimize_states: list[dict[str, Any]] | None = None,
    auto_optimize_states_by_id: dict[str, dict[str, Any]] | None = None,
    sanitize: bool = True,
) -> dict[str, Any]:
    return _task_projection.pipeline_task_public(task, config, ai_task_ids=ai_task_ids, trained_model_specs=trained_model_specs, auto_optimize_states=auto_optimize_states, auto_optimize_states_by_id=auto_optimize_states_by_id, sanitize=sanitize)


def normalize_pipeline_accessory_counts(config: dict[str, Any], accessory_ids: list[str], raw_counts: Any = None) -> dict[str, int]:
    return _pipeline_task_metadata.normalize_pipeline_accessory_counts(config, accessory_ids, raw_counts)


from .agent.orchestration_state import AgentOrchestrationState as _AgentOrchestrationState
from .agent.tool_call_records import AgentToolCallRecords as _AgentToolCallRecords
from .agent.state_ports import AgentStateRuntime as _AgentStateRuntime, AgentStateCalls as _AgentStateCalls, AgentToolCallIdentity as _AgentToolCallIdentity, AgentToolCallState as _AgentToolCallState
_agent_orchestration_state = _AgentOrchestrationState(
    _AgentStateRuntime(clock=lambda: time.time, now=lambda: agent_mcp_now, version=lambda: AGENT_MCP_ORCHESTRATION_VERSION, image_config=lambda: agent_mcp_gemini_image_config),
    _AgentStateCalls(defaults=lambda: agent_mcp_default_stages, orchestration=lambda: agent_mcp_orchestration, pause=lambda: pause_agent_mcp_task, stage=lambda: set_agent_mcp_stage),
)
_agent_tool_call_records = _AgentToolCallRecords(
    _AgentToolCallIdentity(sanitize=lambda: safe_record_id, identifier=lambda: agent_mcp_tool_call_id, samples=lambda: AGENT_MCP_TOOL_SAMPLES, training=lambda: AGENT_MCP_TOOL_TRAINING),
    _AgentToolCallState(now=lambda: agent_mcp_now, orchestration=lambda: agent_mcp_orchestration, upsert=lambda: upsert_agent_mcp_tool_call, stage=lambda: set_agent_mcp_stage),
)

def agent_mcp_now() -> int:
    return _agent_orchestration_state.agent_mcp_now()


from .agent.pose_render_configuration import PoseRenderConfiguration as _PoseRenderConfiguration
from .agent.pose_render_content import PoseRenderContent as _PoseRenderContent
from .agent.pose_artifact_store import PoseArtifactStore as _PoseArtifactStore
from .agent.pose_render_ports import PoseRenderConfigurationSources as _PoseRenderConfigurationSources, PoseRenderConfigurationDefaults as _PoseRenderConfigurationDefaults, PoseRenderReferences as _PoseRenderReferences, PoseRenderPresentation as _PoseRenderPresentation, PoseRenderPaths as _PoseRenderPaths, PoseRenderArtifacts as _PoseRenderArtifacts
_pose_render_configuration = _PoseRenderConfiguration(
    _PoseRenderConfigurationSources(settings=lambda: image_generation_settings, provider_key=lambda: image_generation_provider_key, provider_label=lambda: image_generation_provider_label, model=lambda: default_image_generation_model, base_url=lambda: default_image_generation_base_url, key_environment=lambda: default_image_generation_api_key_env),
    _PoseRenderConfigurationDefaults(provider=lambda: IMAGE_GENERATION_DEFAULT_PROVIDER, timeout=lambda: IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS, key_environment=lambda: IMAGE_GENERATION_API_KEY_ENV, model_environment=lambda: IMAGE_GENERATION_MODEL_ENV, timeout_environment=lambda: IMAGE_GENERATION_TIMEOUT_ENV, high_fidelity_model=lambda: AGENT_MCP_GEMINI_IMAGE_HIGH_FIDELITY_MODEL, legacy_model_environment=lambda: AGENT_MCP_GEMINI_IMAGE_MODEL_ENV, legacy_timeout_environment=lambda: AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV),
)
_pose_render_content = _PoseRenderContent(
    _PoseRenderReferences(contexts=lambda: accessory_reference_image_contexts, resolve=lambda: resolve_service_path, mime=lambda: mimetypes.guess_type, encode=lambda: base64.b64encode, public_url=lambda: public_output_url_for_existing, digest=lambda: file_sha256),
    _PoseRenderPresentation(screen=lambda: normalize_chroma_screen),
)
_pose_artifact_store = _PoseArtifactStore(
    _PoseRenderPaths(owner_root=lambda: output_write_dir_for_owner, sanitize=lambda: safe_record_id),
    _PoseRenderArtifacts(output=lambda: agent_mcp_pose_output_path, digest=lambda: file_sha256, public_url=lambda: public_output_url, bounded=lambda: bounded_text, now=lambda: agent_mcp_now, dumps=lambda: json.dumps),
    _PoseRenderPresentation(screen=lambda: normalize_chroma_screen),
)

def agent_mcp_gemini_image_config() -> dict[str, Any]:
    return _pose_render_configuration.agent_mcp_gemini_image_config()


def agent_mcp_default_stages() -> list[dict[str, Any]]:
    return _agent_orchestration_state.agent_mcp_default_stages()


def agent_mcp_orchestration(task: dict[str, Any]) -> dict[str, Any]:
    return _agent_orchestration_state.agent_mcp_orchestration(task)


def set_agent_mcp_stage(orchestration: dict[str, Any], key: str, status: str, progress: int, **extra: Any) -> None:
    return _agent_orchestration_state.set_agent_mcp_stage(orchestration, key, status, progress, **extra)


def agent_mcp_object_kind(item: dict[str, Any]) -> str:
    return _agent_pose_templates.agent_mcp_object_kind(item)


def agent_mcp_pose_request() -> dict[str, Any]:
    return _agent_pose_templates.agent_mcp_pose_request()


def agent_mcp_pose_templates(base_id: str, object_kind: str) -> list[dict[str, Any]]:
    return _agent_pose_templates.agent_mcp_pose_templates(base_id, object_kind)


from .agent.pose_plan_policy import PosePlanPolicy as _PosePlanPolicy
from .agent.pose_plan_generation import PosePlanGeneration as _PosePlanGeneration
from .agent.pose_plan_assembly import PosePlanAssembly as _PosePlanAssembly
from .agent.pose_plan_ports import PosePlanIdentity as _PosePlanIdentity, PosePlanContent as _PosePlanContent, PosePlanRuntime as _PosePlanRuntime, PosePlanTemplates as _PosePlanTemplates, PosePlanProvider as _PosePlanProvider, PosePlanMedia as _PosePlanMedia, PosePlanCalls as _PosePlanCalls, PosePlanCatalog as _PosePlanCatalog
_pose_plan_policy = _PosePlanPolicy(
    _PosePlanIdentity(uid=lambda: accessory_uid, material=lambda: accessory_material_type, kind=lambda: agent_mcp_object_kind, sanitize=lambda: safe_record_id),
    _PosePlanContent(size=lambda: object_physical_size_mm, sprites=lambda: clean_sprite_assets, bounded=lambda: bounded_text, optional_number=lambda: optional_float, strings=lambda: string_list, compile=lambda: re.compile),
    _PosePlanRuntime(now=lambda: agent_mcp_now, version=lambda: AGENT_MCP_POSE_PLAN_VERSION, max_poses=lambda: AGENT_MCP_POSE_PLAN_MAX_POSES, min_confidence=lambda: AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE, clock=lambda: time.time),
    _PosePlanTemplates(request=lambda: agent_mcp_pose_request, poses=lambda: agent_mcp_pose_templates, fallback=lambda: fallback_accessory_pose_plan),
)
_pose_plan_generation = _PosePlanGeneration(
    _PosePlanIdentity(uid=lambda: accessory_uid, material=lambda: accessory_material_type, kind=lambda: agent_mcp_object_kind, sanitize=lambda: safe_record_id),
    _PosePlanContent(size=lambda: object_physical_size_mm, sprites=lambda: clean_sprite_assets, bounded=lambda: bounded_text, optional_number=lambda: optional_float, strings=lambda: string_list, compile=lambda: re.compile),
    _PosePlanRuntime(now=lambda: agent_mcp_now, version=lambda: AGENT_MCP_POSE_PLAN_VERSION, max_poses=lambda: AGENT_MCP_POSE_PLAN_MAX_POSES, min_confidence=lambda: AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE, clock=lambda: time.time),
    _PosePlanTemplates(request=lambda: agent_mcp_pose_request, poses=lambda: agent_mcp_pose_templates, fallback=lambda: fallback_accessory_pose_plan),
    _PosePlanProvider(settings=lambda: ai_detection_settings, call=lambda: call_ai_mcp_tool, dumps=lambda: json.dumps),
    _PosePlanMedia(path=lambda: Path, encode=lambda: image_path_data_url, max_side=lambda: AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE, quality=lambda: AI_PROFILE_REFERENCE_IMAGE_QUALITY),
    _PosePlanCalls(payload=lambda: accessory_pose_plan_prompt_payload, prompt=lambda: pose_plan_system_prompt, normalize=lambda: normalize_accessory_pose_plan, generate=lambda: generate_accessory_pose_plan),
)
_pose_plan_assembly = _PosePlanAssembly(
    _PosePlanIdentity(uid=lambda: accessory_uid, material=lambda: accessory_material_type, kind=lambda: agent_mcp_object_kind, sanitize=lambda: safe_record_id),
    _PosePlanRuntime(now=lambda: agent_mcp_now, version=lambda: AGENT_MCP_POSE_PLAN_VERSION, max_poses=lambda: AGENT_MCP_POSE_PLAN_MAX_POSES, min_confidence=lambda: AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE, clock=lambda: time.time),
    _PosePlanTemplates(request=lambda: agent_mcp_pose_request, poses=lambda: agent_mcp_pose_templates, fallback=lambda: fallback_accessory_pose_plan),
    _PosePlanCatalog(lookup=lambda: accessory_lookup_by_id, counts=lambda: normalize_pipeline_accessory_counts, canonical_ids=lambda: canonical_pipeline_accessory_ids, ensure=lambda: ensure_accessory_pose_plan),
)

def accessory_pose_plan_prompt_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _pose_plan_policy.accessory_pose_plan_prompt_payload(item)


def pose_plan_system_prompt() -> str:
    return _pose_plan_policy.pose_plan_system_prompt()


def fallback_accessory_pose_plan(item: dict[str, Any]) -> dict[str, Any]:
    return _pose_plan_policy.fallback_accessory_pose_plan(item)


def normalize_accessory_pose_plan(raw: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return _pose_plan_policy.normalize_accessory_pose_plan(raw, item)


def generate_accessory_pose_plan(item: dict[str, Any], *, allow_provider: bool = True, force: bool = False) -> dict[str, Any] | None:
    return _pose_plan_generation.generate_accessory_pose_plan(item, allow_provider=allow_provider, force=force)


def ensure_accessory_pose_plan(item: dict[str, Any], *, force: bool = False) -> dict[str, Any] | None:
    return _pose_plan_generation.ensure_accessory_pose_plan(item, force=force)


def build_agent_mcp_pose_plan(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _pose_plan_assembly.build_agent_mcp_pose_plan(task, config)


def agent_mcp_tool_call_id(task_id: str, tool_name: str, accessory_id: str = "", pose_id: str = "") -> str:
    return _agent_tool_call_records.agent_mcp_tool_call_id(task_id, tool_name, accessory_id, pose_id)


def upsert_agent_mcp_tool_call(orchestration: dict[str, Any], call: dict[str, Any]) -> dict[str, Any]:
    return _agent_tool_call_records.upsert_agent_mcp_tool_call(orchestration, call)


def agent_mcp_pose_reference_content(item: dict[str, Any], *, max_images: int = 3) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _pose_render_content.agent_mcp_pose_reference_content(item, max_images=max_images)


def agent_mcp_pose_prompt(task: dict[str, Any], plan: dict[str, Any], pose: dict[str, Any], chroma_screen: dict[str, Any] | None = None) -> str:
    return _pose_render_content.agent_mcp_pose_prompt(task, plan, pose, chroma_screen)


def agent_mcp_pose_output_path(task: dict[str, Any], accessory_id: str, pose_id: str, mime_type: str) -> Path:
    return _pose_artifact_store.agent_mcp_pose_output_path(task, accessory_id, pose_id, mime_type)


def write_agent_mcp_pose_artifact(
    task: dict[str, Any],
    call: dict[str, Any],
    result: dict[str, Any],
    *,
    prompt: str,
    reference_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    return _pose_artifact_store.write_agent_mcp_pose_artifact(task, call, result, prompt=prompt, reference_assets=reference_assets)


def suppress_green_spill(image_bgr: np.ndarray) -> np.ndarray:
    """Green-spill decontamination: where the green channel exceeds both red and
    blue (a green-tinted boundary/halo pixel), pull green down to max(red,blue).
    This neutralises the green fringe around a dark object cut from a green plate
    without removing or shrinking the silhouette. Neutral/grey/silver/black object
    pixels (green ~= red ~= blue) are untouched."""
    return _suppress_green_spill_impl(image_bgr)


def suppress_chroma_spill(image_bgr: np.ndarray, screen: dict[str, Any] | None = None) -> np.ndarray:
    return _chroma_cutouts.suppress_chroma_spill(image_bgr, screen)


def chroma_background_mask(image_bgr: np.ndarray, screen: dict[str, Any] | None = None) -> np.ndarray:
    return _chroma_cutouts.chroma_background_mask(image_bgr, screen)


def chroma_distance_alpha(image_bgr: np.ndarray, screen: dict[str, Any] | None = None) -> np.ndarray:
    return _chroma_cutouts.chroma_distance_alpha(image_bgr, screen)


def chroma_screen_object_cutout(
    image_bgr: np.ndarray,
    screen: dict[str, Any] | None = None,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    """Remove a fixed solid chroma tabletop/background and keep the largest object."""
    return _chroma_cutouts.chroma_screen_object_cutout(image_bgr, screen)


def bright_green_conveyor_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Boolean mask of UNAMBIGUOUS bright conveyor-green pixels. Tuned to catch the
    saturated, well-lit green plate while sparing dark/olive object pixels (e.g.
    carbon-fibre) and dark anti-aliased object edges, so it can trim a green halo
    without biting into the object."""
    return _bright_green_conveyor_mask_impl(image_bgr)


def precise_green_plate_cutout(
    image_bgr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    """High-precision cut-out of the single object on an AI green-conveyor plate
    using the local AI matte (rembg/u2net). Keeps the FULL silhouette (thin ends,
    corrugations, caps — no erosion) and only trims unambiguous bright-green halo
    pixels. Falls back to None when rembg is unavailable so callers can use the
    chroma-key path."""
    return _background_cutouts.precise_green_plate_cutout(image_bgr)


def green_conveyor_object_cutout(
    image_bgr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    """Chroma-key a single object off an AI-generated green-conveyor plate.
    Removes green (and green-tinted cast-shadow) pixels, keeps the largest
    non-green blob, fills interior holes. Used as the fallback when the AI matte
    is unavailable; tuned to avoid biting into dark object edges or thin features
    (no aggressive open/erode that would shave a thin part's silhouette)."""
    return _chroma_cutouts.green_conveyor_object_cutout(image_bgr)


def segment_agent_mcp_pose_object(
    image_bgr: np.ndarray,
    rng: np.random.Generator,
    chroma_screen: dict[str, Any] | None = None,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    return _pose_cutout_pipeline.segment_agent_mcp_pose_object(image_bgr, rng, chroma_screen)


from .agent.photo_highlight_sources import PhotoHighlightSources as _PhotoHighlightSources
from .agent.photo_highlight_selection import PhotoHighlightSelection as _PhotoHighlightSelection
from .agent.photo_highlight_workflow import PhotoHighlightWorkflow as _PhotoHighlightWorkflow
from .agent.photo_highlight_ports import PhotoSourceMedia as _PhotoSourceMedia, PhotoSpriteLimits as _PhotoSpriteLimits, PhotoSpriteReadiness as _PhotoSpriteReadiness, PhotoObjectSelection as _PhotoObjectSelection, PhotoWorkflowObjects as _PhotoWorkflowObjects, PhotoWorkflowState as _PhotoWorkflowState, PhotoWorkflowModels as _PhotoWorkflowModels
_photo_highlight_sources = _PhotoHighlightSources(
    _PhotoSourceMedia(resolve=lambda: resolve_service_path, suffixes=lambda: IMAGE_REFERENCE_SUFFIXES),
    _PhotoSpriteLimits(minimum=lambda: PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES, version=lambda: PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION),
    _PhotoSpriteReadiness(assets=lambda: clean_sprite_assets, complete=lambda: clean_sprites_policy_complete),
)
_photo_highlight_selection = _PhotoHighlightSelection(
    _PhotoObjectSelection(normalize=lambda: normalize_pipeline_detection_method, training=lambda: pipeline_method_uses_training, lookup=lambda: accessory_lookup_by_id, canonical=lambda: canonical_pipeline_accessory_ids, material=lambda: accessory_material_type),
)
_photo_highlight_workflow = _PhotoHighlightWorkflow(
    _PhotoWorkflowObjects(items=lambda: pipeline_photo_highlight_object_items, identifier=lambda: accessory_uid, sources=lambda: object_photo_highlight_source_paths, signature=lambda: accessory_sprite_version),
    _PhotoSpriteLimits(minimum=lambda: PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES, version=lambda: PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION),
    _PhotoWorkflowState(now=lambda: agent_mcp_now, tool=lambda: AGENT_MCP_TOOL_POSE_IMAGE, stage=lambda: set_agent_mcp_stage, pause=lambda: pause_agent_mcp_task, current=lambda: agent_mcp_orchestration, photo_flow=lambda: pipeline_uses_photo_highlight_sprite_flow, skip_legacy=lambda: mark_legacy_pose_flow_skipped_for_photo_highlight, build_plan=lambda: build_agent_mcp_pose_plan),
    _PhotoWorkflowModels(configuration=lambda: agent_mcp_gemini_image_config, settings=lambda: image_generation_settings, provider=lambda: image_generation_provider_from_settings, build_sprites=lambda: build_clean_sprites_from_photo_highlight_masks),
)

def object_photo_highlight_source_paths(item: dict[str, Any], *, limit: int = PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES) -> list[Path]:
    return _photo_highlight_sources.object_photo_highlight_source_paths(item, limit=limit)


def photo_highlight_clean_sprites_ready(item: dict[str, Any], source_paths: list[Path]) -> bool:
    return _photo_highlight_sources.photo_highlight_clean_sprites_ready(item, source_paths)


def pipeline_photo_highlight_object_items(task: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    return _photo_highlight_selection.pipeline_photo_highlight_object_items(task, config)


def pipeline_uses_photo_highlight_sprite_flow(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return bool(pipeline_photo_highlight_object_items(task, config))


def mark_legacy_pose_flow_skipped_for_photo_highlight(
    task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]
) -> dict[str, Any]:
    return _photo_highlight_workflow.mark_legacy_pose_flow_skipped_for_photo_highlight(task, config, orchestration)


from .agent.photo_highlight_image_input import PhotoHighlightImageInput as _PhotoHighlightImageInput
from .agent.photo_highlight_masks import decode_photo_highlight_mask as _decode_photo_highlight_mask_impl
from .agent.photo_highlight_masks import photo_highlight_auto_roi_mask as _photo_highlight_auto_roi_mask_impl
from .agent.photo_highlight_comparison import PhotoHighlightComparison as _PhotoHighlightComparison
from .agent.photo_highlight_image_ports import PhotoHighlightImagePolicy as _PhotoHighlightImagePolicy, PhotoMaskGeometry as _PhotoMaskGeometry
_photo_highlight_image_input = _PhotoHighlightImageInput(

    _PhotoHighlightImagePolicy(identifier=lambda: accessory_uid, max_side=lambda: PHOTO_HIGHLIGHT_MASK_MAX_SIDE),

)
_photo_highlight_comparison = _PhotoHighlightComparison(

    _PhotoMaskGeometry(alpha=lambda: alpha_bbox, iou=lambda: bbox_iou_xyxy),

)

def photo_highlight_mask_prompt(item: dict[str, Any]) -> str:
    return _photo_highlight_image_input.photo_highlight_mask_prompt(item)


def photo_highlight_input_data_url(image_bgr: np.ndarray) -> tuple[np.ndarray, str, float, float] | None:
    return _photo_highlight_image_input.photo_highlight_input_data_url(image_bgr)


def decode_photo_highlight_mask(mask_bgr: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    return _decode_photo_highlight_mask_impl(mask_bgr)


from .detection.geometry import bbox_iou_xyxy


def photo_highlight_auto_roi_mask(roi_bgr: np.ndarray, ai_roi_mask: np.ndarray) -> tuple[np.ndarray | None, dict[str, Any]]:
    return _photo_highlight_auto_roi_mask_impl(roi_bgr, ai_roi_mask)


def photo_highlight_auto_compare(ai_roi_mask: np.ndarray, auto_roi_mask: np.ndarray | None) -> dict[str, Any]:
    return _photo_highlight_comparison.photo_highlight_auto_compare(ai_roi_mask, auto_roi_mask)


from .agent.photo_highlight_builder import PhotoHighlightSpriteBuilder as _PhotoHighlightSpriteBuilder
from .agent.photo_highlight_builder_ports import PhotoBuildPolicy as _PhotoBuildPolicy, PhotoBuildRuntime as _PhotoBuildRuntime, PhotoBuildMasks as _PhotoBuildMasks, PhotoBuildModelPolicy as _PhotoBuildModelPolicy, PhotoBuildPublication as _PhotoBuildPublication, PhotoBuildArtifacts as _PhotoBuildArtifacts, PoseSpriteMetadata as _PoseSpriteMetadata
_photo_highlight_sprite_builder = _PhotoHighlightSpriteBuilder(
    _PhotoBuildPolicy(material=lambda: accessory_material_type, sources=lambda: object_photo_highlight_source_paths, ready=lambda: photo_highlight_clean_sprites_ready, alpha=lambda: object_alpha_material_policy, complete=lambda: clean_sprites_policy_complete, minimum=lambda: PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES),
    _PhotoBuildRuntime(identifier=lambda: accessory_uid, root=lambda: NORMALIZED_DIR, output=lambda: output_write_dir_for_owner, safe_id=lambda: safe_record_id, now=lambda: time.time, bounded=lambda: bounded_text),
    _PhotoBuildMasks(prompt=lambda: photo_highlight_mask_prompt, input=lambda: photo_highlight_input_data_url, decode=lambda: decode_photo_highlight_mask, bounds=lambda: alpha_bbox, roi=lambda: photo_highlight_auto_roi_mask, compare=lambda: photo_highlight_auto_compare),
    _PhotoBuildModelPolicy(attempts=lambda: PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS, error=lambda: AiProviderError, pose_version=lambda: AGENT_MCP_SPRITE_BUILD_VERSION, photo_version=lambda: PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION),
    _PhotoBuildPublication(sanitize=lambda: sanitize_data_analysis_record_id, item=lambda: image_processing_item, publish=lambda: upsert_data_analysis_image_processing_record),
    _PhotoBuildArtifacts(write=lambda: write_clean_sprite, public_url=lambda: public_output_url_for_existing),
    _PoseSpriteMetadata(footprint=lambda: pose_render_footprint_metadata, normalize=lambda: normalize_sprite_family_canvases, scale=lambda: apply_upright_scale_correction_metadata, laying=lambda: apply_laying_standard_render_size_hints),
)

def build_clean_sprites_from_photo_highlight_masks(
    task: dict[str, Any],
    item: dict[str, Any],
    provider: GeminiAiProvider | AgnesImageProvider,
    model: str,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    return _photo_highlight_sprite_builder.build_clean_sprites_from_photo_highlight_masks(task, item, provider, model, force=force)


def prepare_photo_highlight_sprites_for_task(task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]) -> tuple[bool, bool]:
    return _photo_highlight_workflow.prepare_photo_highlight_sprites_for_task(task, config, orchestration)


def build_clean_sprites_from_agent_mcp_poses(item: dict[str, Any], *, force: bool = False) -> bool:
    return _pose_sprite_builder.build_clean_sprites_from_agent_mcp_poses(item, force=force)


def materialize_agent_mcp_pose_assets(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return _pose_asset_materialization.materialize_agent_mcp_pose_assets(task, config)


def agent_mcp_accessory_has_existing_or_pose_asset(item: dict[str, Any], orchestration: dict[str, Any]) -> bool:
    return _agent_pose_assets.agent_mcp_accessory_has_existing_or_pose_asset(item, orchestration)


def agent_mcp_missing_existing_asset_names(task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]) -> list[str]:
    return _agent_pose_assets.agent_mcp_missing_existing_asset_names(task, config, orchestration)


from .agent.pose_call_registration import PoseCallRegistration as _PoseCallRegistration
from .agent.pose_call_execution import PoseCallExecution as _PoseCallExecution
from .agent.pose_sample_preparation import PoseSamplePreparation as _PoseSamplePreparation
from .agent.pose_execution_ports import PoseWorkflowState as _PoseWorkflowState, PoseWorkflowModels as _PoseWorkflowModels, PoseCallRegistry as _PoseCallRegistry, PoseCallContent as _PoseCallContent, PoseCallPresentation as _PoseCallPresentation, PoseSampleSteps as _PoseSampleSteps, PoseWorkflowDiagnostics as _PoseWorkflowDiagnostics
_pose_call_registration = _PoseCallRegistration(
    _PoseWorkflowState(plan=lambda: ensure_agent_mcp_pose_plan, photo_flow=lambda: pipeline_uses_photo_highlight_sprite_flow, stage=lambda: set_agent_mcp_stage, skip_legacy=lambda: mark_legacy_pose_flow_skipped_for_photo_highlight, pause=lambda: pause_agent_mcp_task, current=lambda: agent_mcp_orchestration),
    _PoseWorkflowModels(configuration=lambda: agent_mcp_gemini_image_config, error=lambda: AiProviderError, provider=lambda: image_generation_provider_from_settings, settings=lambda: image_generation_settings),
    _PoseCallRegistry(tool=lambda: AGENT_MCP_TOOL_POSE_IMAGE, lookup=lambda: accessory_lookup_by_id, cached=lambda: agent_mcp_accessory_pose_images_exist, identifier=lambda: agent_mcp_tool_call_id, upsert=lambda: upsert_agent_mcp_tool_call),
)
_pose_call_execution = _PoseCallExecution(
    _PoseWorkflowState(plan=lambda: ensure_agent_mcp_pose_plan, photo_flow=lambda: pipeline_uses_photo_highlight_sprite_flow, stage=lambda: set_agent_mcp_stage, skip_legacy=lambda: mark_legacy_pose_flow_skipped_for_photo_highlight, pause=lambda: pause_agent_mcp_task, current=lambda: agent_mcp_orchestration),
    _PoseWorkflowModels(configuration=lambda: agent_mcp_gemini_image_config, error=lambda: AiProviderError, provider=lambda: image_generation_provider_from_settings, settings=lambda: image_generation_settings),
    _PoseCallRegistry(tool=lambda: AGENT_MCP_TOOL_POSE_IMAGE, lookup=lambda: accessory_lookup_by_id, cached=lambda: agent_mcp_accessory_pose_images_exist, identifier=lambda: agent_mcp_tool_call_id, upsert=lambda: upsert_agent_mcp_tool_call),
    _PoseCallContent(prompt=lambda: agent_mcp_pose_prompt, references=lambda: agent_mcp_pose_reference_content, chroma=lambda: choose_agent_mcp_chroma_screen, artifact=lambda: write_agent_mcp_pose_artifact),
    _PoseCallPresentation(now=lambda: agent_mcp_now, bounded=lambda: bounded_text),
)
_pose_sample_preparation = _PoseSamplePreparation(
    _PoseWorkflowState(plan=lambda: ensure_agent_mcp_pose_plan, photo_flow=lambda: pipeline_uses_photo_highlight_sprite_flow, stage=lambda: set_agent_mcp_stage, skip_legacy=lambda: mark_legacy_pose_flow_skipped_for_photo_highlight, pause=lambda: pause_agent_mcp_task, current=lambda: agent_mcp_orchestration),
    _PoseWorkflowModels(configuration=lambda: agent_mcp_gemini_image_config, error=lambda: AiProviderError, provider=lambda: image_generation_provider_from_settings, settings=lambda: image_generation_settings),
    _PoseSampleSteps(missing=lambda: agent_mcp_missing_existing_asset_names, register=lambda: ensure_agent_mcp_pose_tool_calls, background=lambda: ensure_pipeline_background_plate, execute=lambda: execute_agent_mcp_pose_tool_calls, materialize=lambda: materialize_agent_mcp_pose_assets, photos=lambda: prepare_photo_highlight_sprites_for_task, save=lambda: save_config),
    _PoseWorkflowDiagnostics(stderr=lambda: sys.stderr, print_exception=lambda: traceback.print_exc),
)

def execute_agent_mcp_pose_tool_calls(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return _pose_call_execution.execute_agent_mcp_pose_tool_calls(task, config)


def ensure_agent_mcp_pose_plan(task: dict[str, Any], config: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    return _photo_highlight_workflow.ensure_agent_mcp_pose_plan(task, config, force=force)


def ensure_agent_mcp_pose_tool_calls(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _pose_call_registration.ensure_agent_mcp_pose_tool_calls(task, config)


def pause_agent_mcp_task(task: dict[str, Any], orchestration: dict[str, Any], *, stage: str, reason: str, suggested_actions: list[str]) -> None:
    return _agent_orchestration_state.pause_agent_mcp_task(task, orchestration, stage=stage, reason=reason, suggested_actions=suggested_actions)


from .agent.pipeline_background_publication import pipeline_background_plate_prompt as _pipeline_background_plate_prompt_impl

from .agent.pipeline_background_publication import PipelineBackgroundPublication as _PipelineBackgroundPublication

from .agent.pipeline_background_publication_ports import BackgroundPublicationTasks as _BackgroundPublicationTasks, BackgroundPublicationPaths as _BackgroundPublicationPaths, BackgroundPublicationSelection as _BackgroundPublicationSelection, BackgroundPublicationProviders as _BackgroundPublicationProviders, BackgroundPublicationCatalog as _BackgroundPublicationCatalog, BackgroundPublicationProjection as _BackgroundPublicationProjection

_pipeline_background_publication = _PipelineBackgroundPublication(
    _BackgroundPublicationTasks(state=lambda: agent_mcp_orchestration, ids=lambda: canonical_pipeline_accessory_ids, lookup=lambda: accessory_lookup_by_id),
    _BackgroundPublicationPaths(output=lambda: output_write_dir_for_owner, record_id=lambda: safe_record_id, set_id=lambda: safe_background_set_id, resolve=lambda: resolve_service_path, sets_directory=lambda: BACKGROUND_SETS_DIR),
    _BackgroundPublicationSelection(prompt=lambda: pipeline_background_plate_prompt, match=lambda: match_background_library_plate, derive=lambda: derive_background_plate_from_accessory),
    _BackgroundPublicationProviders(config=lambda: agent_mcp_gemini_image_config, references=lambda: agent_mcp_pose_reference_content, settings=lambda: image_generation_settings, create=lambda: image_generation_provider_from_settings, error_type=lambda: AiProviderError),
    _BackgroundPublicationCatalog(images=lambda: image_file_list, variants=lambda: create_background_variants_from_source, manifest=lambda: load_background_sets_manifest, publish=lambda: write_background_sets_manifest),
    _BackgroundPublicationProjection(bounded=lambda: bounded_text, url=lambda: public_output_url_for_existing, digest=lambda: file_sha256, now=lambda: agent_mcp_now, legacy_owner=lambda: LEGACY_OWNER_ID),
)

def pipeline_background_plate_prompt(item: dict[str, Any]) -> str:
    return _pipeline_background_plate_prompt_impl(item)


from .accessories.background_evidence import background_patch_boxes as _background_patch_boxes_impl
from .accessories.background_evidence import background_patch_signature as _background_patch_signature_impl
from .accessories.background_evidence import background_signature_distance as _background_signature_distance_impl
from .accessories.background_evidence import BackgroundPlateDerivation as _BackgroundPlateDerivation
from .accessories.background_evidence import BackgroundReferenceSignatures as _BackgroundReferenceSignatures
from .accessories.background_evidence_ports import PlateSources as _PlateSources, PlatePolicy as _PlatePolicy, BackgroundMasks as _BackgroundMasks, SignatureSources as _SignatureSources, SignaturePolicy as _SignaturePolicy, SignatureProjections as _SignatureProjections
_background_plate_derivation = _BackgroundPlateDerivation(
    _PlateSources(pose_assets=lambda: agent_mcp_pose_reference_assets, contexts=lambda: accessory_reference_image_contexts, resolve=lambda: resolve_service_path, suffixes=lambda: IMAGE_REFERENCE_SUFFIXES),
    _PlatePolicy(time_budget=lambda: PIPELINE_BG_PLATE_TIME_BUDGET_S, max_side=lambda: PIPELINE_BG_PLATE_MAX_SIDE, max_radius=lambda: PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS, mask_fraction=lambda: PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC),
    _BackgroundMasks(foreground=lambda: foreground_mask),
    files=_business_files, images=_accessory_image_io,
)
_background_reference_signatures = _BackgroundReferenceSignatures(
    _SignatureSources(paths=lambda: object_photo_highlight_source_paths, limit=lambda: PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES),
    _SignaturePolicy(max_patches=lambda: PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES),
    _BackgroundMasks(foreground=lambda: foreground_mask),
    _SignatureProjections(boxes=lambda: background_patch_boxes, signature=lambda: background_patch_signature), images=_accessory_image_io
)

def derive_background_plate_from_accessory(item: dict[str, Any], out_path: Path) -> Path | None:
    "Build an empty background plate from the first accessory's own capture\n    environment by segmenting out every foreground object and inpainting the\n    holes, leaving only the bare work surface. This guarantees a\n    first-accessory-derived task background even when the image model declines to\n    synthesize an empty surface. Returns the written plate path or None."
    return _background_plate_derivation.derive_background_plate_from_accessory(item, out_path)


def background_patch_boxes(width: int, height: int) -> list[tuple[int, int, int, int]]:
    return _background_patch_boxes_impl(width, height)


def background_patch_signature(patch_bgr: np.ndarray) -> dict[str, Any] | None:
    return _background_patch_signature_impl(patch_bgr)


def background_signature_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    return _background_signature_distance_impl(left, right)


def background_reference_signatures_from_accessory(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _background_reference_signatures.background_reference_signatures_from_accessory(item)


from .accessories.background_library_selection import BackgroundCandidateCatalog as _BackgroundCandidateCatalog
from .accessories.background_library_selection import BackgroundLibraryMatcher as _BackgroundLibraryMatcher
from .accessories.background_library_selection_ports import BackgroundOwnership as _BackgroundOwnership, BackgroundCatalogSources as _BackgroundCatalogSources, BackgroundCatalogPolicy as _BackgroundCatalogPolicy, BackgroundMatchSources as _BackgroundMatchSources, BackgroundMatchFeatures as _BackgroundMatchFeatures
_background_candidate_catalog = _BackgroundCandidateCatalog(
    _BackgroundOwnership(system=lambda: SYSTEM_OWNER_ID, legacy=lambda: LEGACY_OWNER_ID),
    _BackgroundCatalogSources(manifest=lambda: load_background_sets_manifest, directories=lambda: background_set_dirs, sanitize=lambda: safe_background_set_id, visible=lambda: background_set_visible_for_owner, images=lambda: image_file_list, resolve=lambda: resolve_service_path),
    _BackgroundCatalogPolicy(directory=lambda: BACKGROUND_SETS_DIR, suffixes=lambda: IMAGE_REFERENCE_SUFFIXES, limit=lambda: PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES), files=_business_files
)
_background_library_matcher = _BackgroundLibraryMatcher(
    _BackgroundMatchSources(references=lambda: background_reference_signatures_from_accessory, candidates=lambda: background_library_image_candidates),
    _BackgroundMatchFeatures(boxes=lambda: background_patch_boxes, signature=lambda: background_patch_signature, distance=lambda: background_signature_distance),
    lambda: PIPELINE_BG_MATCH_DISTANCE_THRESHOLD, images=_accessory_image_io
)

def background_set_visible_for_owner(meta: dict[str, Any], owner_id: str) -> bool:
    return _background_candidate_catalog.background_set_visible_for_owner(meta, owner_id)


def background_library_image_candidates(owner_id: str) -> list[tuple[str, Path, dict[str, Any]]]:
    return _background_candidate_catalog.background_library_image_candidates(owner_id)


def match_background_library_plate(item: dict[str, Any], owner_id: str) -> dict[str, Any] | None:
    return _background_library_matcher.match_background_library_plate(item, owner_id)


def ensure_pipeline_background_plate(task: dict[str, Any], config: dict[str, Any]) -> str | None:
    'Select or generate a single strict top-down empty background plate for the\n    task, register it as a per-task background set, and reuse it for both sprite\n    preparation and sample-generation backgrounds.'
    return _pipeline_background_publication.ensure_pipeline_background_plate(task, config)


def prepare_agent_mcp_before_sample_generation(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return _pose_sample_preparation.prepare_agent_mcp_before_sample_generation(task, config)


def log_agent_mcp_sample_tool_call(task: dict[str, Any], job: dict[str, Any]) -> None:
    return _agent_tool_call_records.log_agent_mcp_sample_tool_call(task, job)


def log_agent_mcp_training_tool_call(task: dict[str, Any], job: dict[str, Any]) -> None:
    return _agent_tool_call_records.log_agent_mcp_training_tool_call(task, job)


def agent_mcp_training_quality_gate(task: dict[str, Any]) -> bool:
    return _agent_orchestration_state.agent_mcp_training_quality_gate(task)


from .pipeline.ai_activation import PipelineAiActivation
from .pipeline.ai_activation_ports import ActivationPolicy, ActivationStorage

_pipeline_ai_activation = PipelineAiActivation(
    policy=ActivationPolicy(
        canonical_pipeline_accessory_ids=lambda: canonical_pipeline_accessory_ids,
        HTTPException=lambda: HTTPException,
        accessory_lookup_by_id=lambda: accessory_lookup_by_id,
        normalize_pipeline_accessory_counts=lambda: normalize_pipeline_accessory_counts,
        clean_ai_detection_task_name=lambda: clean_ai_detection_task_name,
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        normalize_pipeline_detection_method=lambda: normalize_pipeline_detection_method,
    ),
    storage=ActivationStorage(
        current_owner_fields=lambda: current_owner_fields,
        find_ai_detection_task=lambda: find_ai_detection_task,
        save_ai_detection_task=lambda: save_ai_detection_task,
        serialize_ai_detection_task=lambda: serialize_ai_detection_task,
        upsert_pipeline_ai_detection_task=lambda: upsert_pipeline_ai_detection_task,
    ),
)


def upsert_pipeline_ai_detection_task(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _pipeline_ai_activation.upsert_pipeline_ai_detection_task(task, config)


def activate_pipeline_ai_detection_task(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return _pipeline_ai_activation.activate_pipeline_ai_detection_task(task, config)


def sync_ready_pipeline_ai_detection_tasks(
    tasks: list[dict[str, Any]], config: dict[str, Any], user: dict[str, Any] | None, target_user_id: str | None = None
) -> bool:
    # Keep AI draft tasks editable after the first accessory is attached. Users
    # must be able to add multiple accessories before explicitly creating the
    # AI inspection task.
    return False


from .pipeline.ai_task_sync import PipelineAiTaskSync as _PipelineAiTaskSync
from .pipeline.ai_task_sync_ports import (
    PipelineAiAccess as _PipelineAiAccess,
    PipelineAiAccessories as _PipelineAiAccessories,
    PipelineAiIdentity as _PipelineAiIdentity,
    PipelineAiProjection as _PipelineAiProjection,
)

_pipeline_ai_task_sync = _PipelineAiTaskSync(
    _PipelineAiIdentity(
        safe_record_id=lambda: safe_record_id,
        sanitize_ai_detection_task_id=lambda: sanitize_ai_detection_task_id,
        ai_detection_task_model_id=lambda: ai_detection_task_model_id,
    ),
    _PipelineAiAccessories(
        accessory_lookup_by_id=lambda: accessory_lookup_by_id,
        canonical_pipeline_accessory_ids=lambda: canonical_pipeline_accessory_ids,
        accessory_material_type=lambda: accessory_material_type,
        normalize_pipeline_accessory_counts=lambda: normalize_pipeline_accessory_counts,
    ),
    _PipelineAiAccess(
        source=lambda: PIPELINE_DASHBOARD_AI_TASK_SOURCE,
        record_visible_to_user=lambda: record_visible_to_user,
        load_ai_detection_tasks=lambda: load_ai_detection_tasks,
    ),
    _PipelineAiProjection(
        clean_ai_detection_task_name=lambda: clean_ai_detection_task_name,
        training_route=lambda: pipeline_ai_task_training_route,
        task_id=lambda: pipeline_ai_task_id,
        now=lambda: time.time,
    ),
)


def pipeline_ai_task_id(ai_task_id: str) -> str:
    return _pipeline_ai_task_sync.pipeline_ai_task_id(ai_task_id)


def pipeline_ai_task_training_route(ai_task: dict[str, Any], config: dict[str, Any]) -> str:
    return _pipeline_ai_task_sync.pipeline_ai_task_training_route(ai_task, config)


def sync_pipeline_ai_detection_tasks(
    tasks: list[dict[str, Any]],
    config: dict[str, Any],
    user: dict[str, Any] | None,
    target_user_id: str | None = None,
    *,
    ai_tasks: list[dict[str, Any]] | None = None,
) -> bool:
    """Represent AI detection tasks as first-class pipeline tasks.

    These entries let the task pipeline show VLM-first tasks even before a YOLO
    model exists. They do not remove the original AI task; they keep a stable
    pipeline card linked to it so optimization/training state has one task home.
    """
    return _pipeline_ai_task_sync.sync_pipeline_ai_detection_tasks(
        tasks, config, user, target_user_id, ai_tasks=ai_tasks
    )


def normalize_pipeline_task_auto_advance_defaults(tasks: list[dict[str, Any]]) -> bool:
    return _pipeline_task_metadata.normalize_pipeline_task_auto_advance_defaults(tasks)


from .pipeline.training_status import PipelineTrainingStatus as _PipelineTrainingStatus
from .pipeline.training_status_ports import (
    TrainingJobLookup as _TrainingJobLookup,
    TrainingStatusEffects as _TrainingStatusEffects,
)
_pipeline_training_status = _PipelineTrainingStatus(
    _TrainingJobLookup(
        load=lambda: load_training_task,
        path=lambda: training_task_path,
        public=lambda: public_refreshed_training_task,
        linked=lambda: linked_training_job,
    ),
    _TrainingStatusEffects(
        orchestration=lambda: agent_mcp_orchestration,
        set_stage=lambda: set_agent_mcp_stage,
    ),
)


def linked_training_job(
    task: dict[str, Any],
    load_task: Callable[[Path], dict[str, Any] | None] | None = None,
) -> dict[str, Any] | None:
    return _pipeline_training_status.linked_training_job(task, load_task)


def sync_pipeline_task(
    task: dict[str, Any],
    load_task: Callable[[Path], dict[str, Any] | None] | None = None,
) -> bool:
    return _pipeline_training_status.sync_pipeline_task(task, load_task)


from .pipeline.training_links import PipelineTrainedModelLink as _PipelineTrainedModelLink
_pipeline_trained_model_link = _PipelineTrainedModelLink(catalog=lambda: list_trained_model_specs)


def link_pipeline_trained_model(task: dict[str, Any]) -> dict[str, Any] | None:
    """Link the freshly trained model to the pipeline task so the model library and
    detection workbench can use it immediately (transfer-back deployment path)."""
    return _pipeline_trained_model_link.link_pipeline_trained_model(task)


from .pipeline.stage_advance import PipelineStageAdvancer as _PipelineStageAdvancer
from .pipeline.stage_advance_ports import (
    StageAdvanceAssets as _StageAdvanceAssets,
    StageAdvanceJobs as _StageAdvanceJobs,
    StageAdvancePolicy as _StageAdvancePolicy,
    StageAdvanceRuntime as _StageAdvanceRuntime,
)

_pipeline_stage_advancer = _PipelineStageAdvancer(
    _StageAdvancePolicy(
        detection_method=lambda: normalize_pipeline_detection_method,
        consume_recommendation=lambda: consume_pipeline_recommendation,
        recommend=lambda: agent_recommendation,
        canonical_accessories=lambda: canonical_pipeline_accessory_ids,
        orchestration=lambda: agent_mcp_orchestration,
        pause=lambda: pause_agent_mcp_task,
        training_quality=lambda: agent_mcp_training_quality_gate,
        link_model=lambda: link_pipeline_trained_model,
        http_error=lambda: HTTPException,
        cancelled_error=lambda: PipelineAdvanceCancelled,
    ),
    _StageAdvanceAssets(
        load_config=lambda: load_config,
        save_config=lambda: save_config,
        activate_ai=lambda: activate_pipeline_ai_detection_task,
        prepare=lambda: prepare_agent_mcp_before_sample_generation,
        materialize=lambda: materialize_agent_mcp_pose_assets,
        normalize=lambda: ensure_training_normalized_assets_for_selection,
    ),
    _StageAdvanceJobs(
        request_type=lambda: TrainingStartRequest,
        sample_generation=lambda: request_sample_generation,
        training=lambda: request_training,
        task_name=lambda: task_record_name,
        log_samples=lambda: log_agent_mcp_sample_tool_call,
        log_training=lambda: log_agent_mcp_training_tool_call,
    ),
    _StageAdvanceRuntime(
        persist_progress=lambda: persist_pipeline_task_progress,
        monotonic=lambda: time.monotonic,
        clock=lambda: time.time,
        print=lambda: print,
    ),
)


def advance_pipeline_task(task: dict[str, Any], cancel_event: "threading.Event | None" = None) -> None:
    return _pipeline_stage_advancer.advance(task, cancel_event)


from .agent.conversation import AgentConversation as _AgentConversation
from .agent.decision_context import AgentDecisionContext as _AgentDecisionContext
from .agent.decision_policy import AgentDecisionPolicy as _AgentDecisionPolicy
from .agent.decision_flow import AgentDecisionFlow as _AgentDecisionFlow
from .agent.pipeline_decision_ports import AgentConversationRuntime as _AgentConversationRuntime, AgentDecisionText as _AgentDecisionText, AgentPipelineEvidence as _AgentPipelineEvidence, AgentDecisionAccessories as _AgentDecisionAccessories, AgentDecisionContextCalls as _AgentDecisionContextCalls, AgentDecisionPolicyValues as _AgentDecisionPolicyValues, AgentDecisionRuleCalls as _AgentDecisionRuleCalls, AgentDecisionInvocationSettings as _AgentDecisionInvocationSettings, AgentDecisionCodec as _AgentDecisionCodec, AgentDecisionFlowCalls as _AgentDecisionFlowCalls
_agent_conversation = _AgentConversation(
    _AgentConversationRuntime(orchestration=lambda: agent_mcp_orchestration, now=lambda: agent_mcp_now, uuid=lambda: uuid.uuid4, limit=lambda: AGENT_MCP_CONVERSATION_LIMIT),
    _AgentDecisionText(bounded=lambda: bounded_text),
)
_agent_decision_context = _AgentDecisionContext(
    _AgentPipelineEvidence(orchestration=lambda: agent_mcp_orchestration, image_config=lambda: agent_mcp_gemini_image_config, missing_assets=lambda: agent_mcp_missing_existing_asset_names, training_job=lambda: linked_training_job, pose_tool=lambda: AGENT_MCP_TOOL_POSE_IMAGE),
    _AgentDecisionAccessories(canonical=lambda: canonical_pipeline_accessory_ids, counts=lambda: normalize_pipeline_accessory_counts, lookup=lambda: accessory_lookup_by_id, material=lambda: accessory_material_type, detection=lambda: normalize_pipeline_detection_method),
    _AgentDecisionContextCalls(quality=lambda: agent_pipeline_quality_signals, stage_order=lambda: PIPELINE_STAGE_ORDER),
    _AgentDecisionText(bounded=lambda: bounded_text),
)
_agent_decision_policy = _AgentDecisionPolicy(
    _AgentDecisionPolicyValues(actions=lambda: AGENT_PIPELINE_ACTIONS, targets=lambda: AGENT_PIPELINE_STAGE_TARGETS),
    _AgentDecisionRuleCalls(rerun=lambda: _rule_rerun_failed_stage, normalize=lambda: normalize_agent_pipeline_decision),
    _AgentDecisionText(bounded=lambda: bounded_text),
)
_agent_decision_flow = _AgentDecisionFlow(
    _AgentDecisionInvocationSettings(load=lambda: load_agent_config, supported=lambda: agent_recommendation_supported, prompt=lambda: AGENT_PIPELINE_SYSTEM_PROMPT),
    _AgentDecisionCodec(dumps=lambda: json.dumps, parse=lambda: parse_agent_json),
    _AgentDecisionFlowCalls(context=lambda: agent_pipeline_context, chat=lambda: agent_chat_completion, normalize=lambda: normalize_agent_pipeline_decision, rule=lambda: agent_pipeline_rule_decision),
)

def agent_mcp_append_conversation(
    task: dict[str, Any],
    role: str,
    message: str,
    *,
    action: str = "",
    reason: str = "",
    target_stage: str = "",
    source: str = "",
    needs_user: bool = False,
    agent_error: str = "",
) -> dict[str, Any]:
    return _agent_conversation.agent_mcp_append_conversation(task, role, message, action=action, reason=reason, target_stage=target_stage, source=source, needs_user=needs_user, agent_error=agent_error)


def agent_pipeline_quality_signals(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _agent_decision_context.agent_pipeline_quality_signals(task, config)


def agent_pipeline_context(task: dict[str, Any], config: dict[str, Any], user_message: str | None, trigger: str) -> dict[str, Any]:
    return _agent_decision_context.agent_pipeline_context(task, config, user_message, trigger)


def normalize_agent_pipeline_decision(parsed: dict[str, Any]) -> dict[str, Any]:
    return _agent_decision_policy.normalize_agent_pipeline_decision(parsed)


def _rule_rerun_failed_stage(stage: str) -> tuple[str, str]:
    return _agent_decision_policy._rule_rerun_failed_stage(stage)


def agent_pipeline_rule_decision(task: dict[str, Any], user_message: str | None, trigger: str) -> dict[str, Any]:
    return _agent_decision_policy.agent_pipeline_rule_decision(task, user_message, trigger)


AGENT_PIPELINE_SYSTEM_PROMPT = (
    "你是工业视觉质检平台的任务流水线主导 Agent。目标：除上传素材与指定任务外，让用户尽量不手动调参，"
    "由你自主推动 draft→samples→training→library 全流程，并在合适时机用自然语言与用户沟通。"
    "你会收到任务当前状态、配件信息、编排阶段、质量信号、最近对话以及用户最新消息（可能为空，表示自动巡检触发）。"
    "请只输出一个 JSON 对象，不要输出多余文本。可用 action 含义："
    "advance=推进到下一阶段（仅当前阶段已完成）；"
    "set_params=调整训练参数(sample_count/epochs/image_size/train_mode)，可带 advance_after=true 立即推进；"
    "goto_stage=回退到更早阶段重做(target_stage 取 draft 改配件/参数, samples 重新生成样本)；"
    "retry=重试实拍高亮抠图素材生成；replan=重新准备实拍高亮抠图素材；"
    "pause_and_ask=暂停并主动联系用户(仅当任务复杂、有风险或质量存疑时使用，必须给出 message_to_user 与 suggested_actions)；"
    "continue_existing_assets=沿用现有实拍抠图素材继续；continue_training=确认样本质量进入训练；"
    "cancel=取消任务；reply=仅回答用户、不改变状态。"
    "尽量自主决策、保持流程推进；只有真正需要用户决定时才 pause_and_ask。"
    "JSON 字段："
    '{"action": str, "params": {"sample_count": int, "epochs": int, "image_size": int, "train_mode": "yolo"|"yolo_ocr"}, '
    '"advance_after": bool, "target_stage": "draft"|"samples", "needs_user": bool, '
    '"message_to_user": "面向用户的中文回复", "reason": "一句话中文决策理由", "suggested_actions": [str]}。'
    "message_to_user 与 reason 必填，参数需落在给定 constraints 范围内。"
)


@pinned_model_profiles(resolve_model_profiles)
def agent_pipeline_decide(
    task: dict[str, Any],
    config: dict[str, Any],
    *,
    user_message: str | None = None,
    trigger: str = "chat",
) -> dict[str, Any]:
    return _agent_decision_flow.agent_pipeline_decide(task, config, user_message=user_message, trigger=trigger)


from .agent.pipeline_actions import AgentPipelineActions as _AgentPipelineActions
from .agent.pipeline_turns import AgentPipelineTurns as _AgentPipelineTurns
from .agent.pipeline_action_ports import AgentActionState as _AgentActionState, AgentActionAdvance as _AgentActionAdvance, AgentActionJobs as _AgentActionJobs, AgentActionPolicy as _AgentActionPolicy, AgentActionPose as _AgentActionPose, AgentActionCalls as _AgentActionCalls, AgentTurnCalls as _AgentTurnCalls
_agent_pipeline_actions = _AgentPipelineActions(
    _AgentActionState(orchestration=lambda: agent_mcp_orchestration, now=lambda: agent_mcp_now, pause=lambda: pause_agent_mcp_task, bounded=lambda: bounded_text, http_error_type=lambda: HTTPException),
    _AgentActionAdvance(mark=lambda: mark_pipeline_task_advancing, sync=lambda: sync_pipeline_task, advance=lambda: advance_pipeline_task),
    _AgentActionJobs(delete=lambda: delete_training_task_record),
    _AgentActionPolicy(normalize=lambda: normalize_pipeline_detection_method, uses_training=lambda: pipeline_method_uses_training),
    _AgentActionPose(photo_flow=lambda: pipeline_uses_photo_highlight_sprite_flow, skip_legacy=lambda: mark_legacy_pose_flow_skipped_for_photo_highlight, plan=lambda: ensure_agent_mcp_pose_plan, ensure_calls=lambda: ensure_agent_mcp_pose_tool_calls, config=lambda: agent_mcp_gemini_image_config, execute=lambda: execute_agent_mcp_pose_tool_calls),
    _AgentActionCalls(safe_advance=lambda: agent_safe_advance, reset=lambda: reset_pipeline_task_to_stage),
)
_agent_pipeline_turns = _AgentPipelineTurns(
    _AgentTurnCalls(append=lambda: agent_mcp_append_conversation, apply=lambda: apply_agent_pipeline_decision),
)

def agent_safe_advance(
    task: dict[str, Any], config: dict[str, Any], pending_advances: list[str] | None = None
) -> None:
    return _agent_pipeline_actions.agent_safe_advance(task, config, pending_advances)


def reset_pipeline_task_to_stage(task: dict[str, Any], target: str, user: dict[str, Any] | None) -> None:
    return _agent_pipeline_actions.reset_pipeline_task_to_stage(task, target, user)


def apply_agent_pipeline_decision(
    task: dict[str, Any],
    config: dict[str, Any],
    decision: dict[str, Any],
    user: dict[str, Any] | None,
    *,
    trigger: str = "chat",
    pending_advances: list[str] | None = None,
) -> None:
    return _agent_pipeline_actions.apply_agent_pipeline_decision(task, config, decision, user, trigger=trigger, pending_advances=pending_advances)


def commit_pipeline_agent_turn(
    task: dict[str, Any],
    config: dict[str, Any],
    user: dict[str, Any] | None,
    user_message: str | None,
    decision: dict[str, Any],
    trigger: str,
    pending_advances: list[str] | None = None,
) -> dict[str, Any]:
    return _agent_pipeline_turns.commit_pipeline_agent_turn(task, config, user, user_message, decision, trigger, pending_advances)


from .pipeline.reconciliation import PipelineReconciliation as _PipelineReconciliation
from .pipeline.reconciliation_ports import (
    ReconciliationPolicy as _ReconciliationPolicy,
    ReconciliationRegistry as _ReconciliationRegistry,
    ReconciliationCalls as _ReconciliationCalls,
)
_pipeline_reconciliation = _PipelineReconciliation(
    _ReconciliationPolicy(
        normalize=lambda: normalize_pipeline_detection_method,
        uses_training=lambda: pipeline_method_uses_training,
    ),
    _ReconciliationRegistry(
        lock=lambda: _pipeline_advance_registry_lock,
        inflight=lambda: _pipeline_advance_inflight,
        timeout=lambda: PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S,
        now=lambda: time.time,
    ),
    _ReconciliationCalls(
        load_agent_config=lambda: load_agent_config,
        supported=lambda: agent_recommendation_supported,
        training_finder=lambda: training_task_finder,
        reap=lambda: reap_pipeline_advance_zombie,
        sync=lambda: sync_pipeline_task,
        needs_auto_agent=lambda: pipeline_task_needs_auto_agent,
        orchestration=lambda: agent_mcp_orchestration,
        signature=lambda: pipeline_task_decision_signature,
    ),
)


def pipeline_task_decision_signature(task: dict[str, Any]) -> str:
    return _pipeline_reconciliation.pipeline_task_decision_signature(task)


def pipeline_task_needs_auto_agent(task: dict[str, Any]) -> bool:
    return _pipeline_reconciliation.pipeline_task_needs_auto_agent(task)


from .pipeline.auto_agent_runtime import PipelineAutoAgentRuntime as _PipelineAutoAgentRuntime
from .pipeline.auto_agent_runtime_ports import (
    AutoAgentDecision as _AutoAgentDecision,
    AutoAgentExecution as _AutoAgentExecution,
    AutoAgentScheduling as _AutoAgentScheduling,
    AutoAgentTasks as _AutoAgentTasks,
)
_pipeline_auto_agent_runtime = _PipelineAutoAgentRuntime(
    _AutoAgentTasks(
        lock=lambda: _pipeline_tasks_lock,
        load=lambda: load_pipeline_task,
        needs_agent=lambda: pipeline_task_needs_auto_agent,
        orchestration=lambda: agent_mcp_orchestration,
        signature=lambda: pipeline_task_decision_signature,
        max_steps=lambda: AGENT_MCP_AUTO_MAX_STEPS,
        pause=lambda: pause_agent_mcp_task,
        append_conversation=lambda: agent_mcp_append_conversation,
        save=lambda: save_pipeline_task,
        deepcopy=lambda: copy.deepcopy,
    ),
    _AutoAgentDecision(
        scope_config=lambda: scope_config_for_user,
        load_config=lambda: load_config,
        decide=lambda: agent_pipeline_decide,
        commit=lambda: commit_pipeline_agent_turn,
        now=lambda: agent_mcp_now,
        schedule_advance=lambda: schedule_pipeline_advance,
    ),
    _AutoAgentExecution(
        identity=lambda: _request_user,
        traceback=lambda: traceback.print_exc,
        stderr=lambda: sys.stderr,
    ),
    _AutoAgentScheduling(
        lock=lambda: _pipeline_auto_agent_lock,
        inflight=lambda: _pipeline_auto_agent_inflight,
        thread=lambda: threading.Thread,
        runner=lambda: _run_pipeline_auto_agent_step,
    ),
    scope=_runtime_repositories.thread_scope,
)


@pinned_model_profiles(resolve_model_profiles, lambda identity: load_pipeline_task(identity))
def _run_pipeline_auto_agent_step(task_id: str, user: dict[str, Any] | None) -> None:
    _pipeline_auto_agent_runtime.run(task_id, user)


def schedule_pipeline_auto_agent(task_ids: list[str], user: dict[str, Any] | None) -> None:
    _pipeline_auto_agent_runtime.schedule(task_ids, user)


from .pipeline.advance_runtime import PipelineAdvanceRuntime as _PipelineAdvanceRuntime
from .pipeline.advance_runtime_ports import (
    AdvanceExecution as _AdvanceExecution,
    AdvancePolicy as _AdvancePolicy,
    AdvanceScheduling as _AdvanceScheduling,
    AdvanceTasks as _AdvanceTasks,
)
_pipeline_advance_runtime = _PipelineAdvanceRuntime(
    _AdvanceTasks(
        lock=lambda: _pipeline_tasks_lock,
        load=lambda: load_pipeline_task,
        sync=lambda: sync_pipeline_task,
        save=lambda: save_pipeline_task,
        deepcopy=lambda: copy.deepcopy,
    ),
    _AdvancePolicy(
        advance=lambda: advance_pipeline_task,
        guarded=lambda: advance_pipeline_task_guarded,
        cancelled_error=lambda: PipelineAdvanceCancelled,
        http_error=lambda: HTTPException,
        orchestration=lambda: agent_mcp_orchestration,
        pause=lambda: pause_agent_mcp_task,
        bounded_text=lambda: bounded_text,
    ),
    _AdvanceExecution(
        identity=lambda: _request_user,
        scope_config=lambda: scope_config_for_user,
        load_config=lambda: load_config,
        clock=lambda: time.time,
        traceback=lambda: traceback.print_exc,
        stderr=lambda: sys.stderr,
        print=lambda: print,
    ),
    _AdvanceScheduling(
        registry_lock=lambda: _pipeline_advance_registry_lock,
        inflight=lambda: _pipeline_advance_inflight,
        cancel_events=lambda: _pipeline_advance_cancel,
        event=lambda: threading.Event,
        thread=lambda: threading.Thread,
        runner=lambda: _run_pipeline_advance,
    ),
    scope=_runtime_repositories.thread_scope,
)


def advance_pipeline_task_guarded(
    task: dict[str, Any], config: dict[str, Any], cancel_event: "threading.Event | None" = None
) -> None:
    """Advance one stage, converting precondition/runtime failures into a paused
    state with a clear reason (mirrors the previous agent_safe_advance UX) so the
    async runner never crashes and the user always sees why a task stopped."""
    _pipeline_advance_runtime.guarded(task, config, cancel_event)


@pinned_model_profiles(resolve_model_profiles, lambda identity: load_pipeline_task(identity))
def _run_pipeline_advance(task_id: str, user: dict[str, Any] | None) -> None:
    _pipeline_advance_runtime.run(task_id, user)


def schedule_pipeline_advance(task_id: str, user: dict[str, Any] | None) -> bool:
    """Enqueue an async advance for a task. Idempotent: if a thread is already
    advancing this task, returns False without stacking a second one."""
    return _pipeline_advance_runtime.schedule(task_id, user)


def cancel_pipeline_advance(task_id: str) -> bool:
    """Signal a running advance worker to stop at the next checkpoint. Returns True
    if a worker was inflight."""
    return _pipeline_advance_runtime.cancel(task_id)


from .pipeline.recommendations import PipelineRecommendations as _PipelineRecommendations
from .pipeline.recommendation_ports import (
    PipelineRecommendationLinks as _PipelineRecommendationLinks,
    PipelineRecommendationMethodPolicy as _PipelineRecommendationMethodPolicy,
)

_pipeline_recommendations = _PipelineRecommendations(
    _PipelineRecommendationMethodPolicy(
        normalize=lambda: normalize_pipeline_detection_method,
        uses_training=lambda: pipeline_method_uses_training,
    ),
    _PipelineRecommendationLinks(
        signature=lambda: pipeline_recommendation_signature,
        next_stage=lambda: pipeline_next_recommendation_stage,
        ready=lambda: pipeline_recommendation_ready,
    ),
)


def pipeline_recommendation_signature(task: dict[str, Any], stage: str) -> str:
    return _pipeline_recommendations.pipeline_recommendation_signature(task, stage)


def pipeline_next_recommendation_stage(task: dict[str, Any]) -> str:
    """Which stage's params should be pre-computed so the next step is ready."""
    return _pipeline_recommendations.pipeline_next_recommendation_stage(task)


def pipeline_recommendation_ready(task: dict[str, Any], stage: str) -> bool:
    return _pipeline_recommendations.pipeline_recommendation_ready(task, stage)


def consume_pipeline_recommendation(task: dict[str, Any], stage: str) -> dict[str, Any] | None:
    """Return (and clear) the pre-generated params for a stage if present."""
    return _pipeline_recommendations.consume_pipeline_recommendation(task, stage)


from .pipeline.recommendation_runtime import PipelineRecommendationRuntime as _PipelineRecommendationRuntime
from .pipeline.recommendation_runtime_ports import (
    RecommendationExecution as _RecommendationExecution,
    RecommendationScheduling as _RecommendationScheduling,
    RecommendationTasks as _RecommendationTasks,
)
_pipeline_recommendation_runtime = _PipelineRecommendationRuntime(
    _RecommendationTasks(
        lock=lambda: _pipeline_tasks_lock,
        load=lambda: load_pipeline_task,
        next_stage=lambda: pipeline_next_recommendation_stage,
        ready=lambda: pipeline_recommendation_ready,
        signature=lambda: pipeline_recommendation_signature,
        save=lambda: save_pipeline_task,
    ),
    _RecommendationExecution(
        identity=lambda: _request_user,
        recommend=lambda: agent_recommendation,
        clock=lambda: time.time,
        traceback=lambda: traceback.print_exc,
        stderr=lambda: sys.stderr,
    ),
    _RecommendationScheduling(
        lock=lambda: _pipeline_recommendation_lock,
        inflight=lambda: _pipeline_recommendation_inflight,
        thread=lambda: threading.Thread,
        runner=lambda: _run_pipeline_recommendation_pregen,
    ),
    scope=_runtime_repositories.thread_scope,
)


@pinned_model_profiles(resolve_model_profiles, lambda identity: load_pipeline_task(identity))
def _run_pipeline_recommendation_pregen(task_id: str, stage: str, user: dict[str, Any] | None) -> None:
    _pipeline_recommendation_runtime.run(task_id, stage, user)


def schedule_pipeline_recommendation_pregen(items: list[tuple[str, str]], user: dict[str, Any] | None) -> None:
    _pipeline_recommendation_runtime.schedule(items, user)


def collect_pipeline_recommendation_pregen(tasks: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return _pipeline_recommendations.collect_pipeline_recommendation_pregen(tasks)


def reap_pipeline_advance_zombie(task: dict[str, Any]) -> bool:
    """Reset a task left in the advancing state with no live worker thread (e.g.
    the process restarted mid-advance) so the UI can distinguish working from
    timed-out and the user can retry. Returns True if the task was modified."""
    return _pipeline_reconciliation.reap_pipeline_advance_zombie(task)


def sync_and_auto_advance_pipeline(tasks: list[dict[str, Any]]) -> tuple[bool, list[str], list[str]]:
    return _pipeline_reconciliation.sync_and_auto_advance_pipeline(tasks)


# Reconciliation on the pipeline list GET is throttled so frequent polling (and
# multiple sessions) does not re-run sync/normalize/save work on every request.
# POST endpoints mutate state directly, so a throttled read only delays
# background reconciliation by at most this interval.
PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS = 5.0


_set_pipeline_tasks_sync_last_at = _pipeline_runtime.set_last_sync_at


from .pipeline.task_list import PipelineTaskList as _PipelineTaskList
from .pipeline.task_list_api import register_pipeline_task_list_api
from .pipeline.task_list_ports import (
    TaskListAccess as _TaskListAccess,
    TaskListReconciliation as _TaskListReconciliation,
    TaskListPresentation as _TaskListPresentation,
)
_pipeline_task_list = _PipelineTaskList(
    _TaskListAccess(
        current_user=lambda: current_auth_user,
        is_admin=lambda: user_is_admin,
        load_config=lambda: load_config,
        scope_config=lambda: scope_config_for_user,
        load_ai_tasks=lambda: load_ai_detection_tasks,
        visible=lambda: record_visible_to_user,
        incoming_allowed=lambda: incoming_text_task_access_allowed,
        has_permission=lambda: user_has_permission,
    ),
    _TaskListReconciliation(
        task_lock=lambda: _pipeline_tasks_lock,
        load_tasks=lambda: load_pipeline_tasks,
        monotonic=lambda: time.monotonic,
        last_sync_at=lambda: _pipeline_runtime.last_sync_at,
        set_last_sync_at=lambda value: _set_pipeline_tasks_sync_last_at(value),
        min_interval=lambda: PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS,
        ensure_accessories=lambda: ensure_pipeline_task_accessory_objects,
        save_config=lambda: save_config,
        sync_ai_tasks=lambda: sync_pipeline_ai_detection_tasks,
        sync_ready_ai_tasks=lambda: sync_ready_pipeline_ai_detection_tasks,
        normalize_auto_defaults=lambda: normalize_pipeline_task_auto_advance_defaults,
        sync_and_advance=lambda: sync_and_auto_advance_pipeline,
        save_tasks=lambda: save_pipeline_tasks,
        collect_pregen=lambda: collect_pipeline_recommendation_pregen,
    ),
    _TaskListPresentation(
        schedule_agent=lambda: schedule_pipeline_auto_agent,
        schedule_advance=lambda: schedule_pipeline_advance,
        schedule_pregen=lambda: schedule_pipeline_recommendation_pregen,
        trained_specs=lambda: list_trained_model_specs,
        optimize_states=lambda: list_auto_optimize_states,
        optimize_by_id=lambda: auto_optimize_states_by_task_id,
        public_task=lambda: pipeline_task_public,
        public_agent_config=lambda: public_agent_config,
        accessories_payload=lambda: pipeline_accessories_payload,
        sanitize=lambda: public_path_sanitized,
    ),
)
get_pipeline_tasks = register_pipeline_task_list_api(app, _pipeline_task_list)

from .pipeline.task_create import PipelineTaskCreator as _PipelineTaskCreator
from .pipeline.task_create_api import register_pipeline_task_create_api
from .pipeline.task_create_ports import (
    TaskCreateAccess as _TaskCreateAccess,
    TaskCreatePolicy as _TaskCreatePolicy,
    TaskCreateRuntime as _TaskCreateRuntime,
)

_pipeline_task_creator = _PipelineTaskCreator(
    _TaskCreateAccess(
        current_user=lambda: current_auth_user,
        require_permission=lambda: require_permission,
        http_error=lambda: HTTPException,
        is_admin=lambda: user_is_admin,
        owner_fields=lambda: owner_fields_for_new_record,
        fallback_owner=lambda: resource_owner_id_for_new_record,
        scope_config=lambda: scope_config_for_user,
        load_config=lambda: load_config,
        accessory_lookup=lambda: accessory_lookup_by_id,
        load_agent_config=lambda: load_agent_config,
    ),
    _TaskCreatePolicy(
        canonical_accessory_ids=lambda: canonical_pipeline_accessory_ids,
        normalize_detection_method=lambda: normalize_pipeline_detection_method,
        normalize_expected_count=lambda: normalize_expected_production_count,
        method_uses_training=lambda: pipeline_method_uses_training,
        normalize_accessory_counts=lambda: normalize_pipeline_accessory_counts,
        assert_unique_name=lambda: assert_unique_task_name,
        next_recommendation_stage=lambda: pipeline_next_recommendation_stage,
    ),
    _TaskCreateRuntime(
        uuid4=lambda: uuid.uuid4,
        now=lambda: time.time,
        lock=lambda: _pipeline_tasks_lock,
        activate_ai_task=lambda: activate_pipeline_ai_detection_task,
        save_task=lambda: save_pipeline_task,
        initialize_auto_optimize=lambda: initialize_auto_optimize_for_pipeline_task,
        load_task=lambda: load_pipeline_task,
        schedule_pregen=lambda: schedule_pipeline_recommendation_pregen,
        request_user=lambda: _request_user,
        public_task=lambda: pipeline_task_public,
    ),
)
create_pipeline_task = register_pipeline_task_create_api(app, _pipeline_task_creator)

from .pipeline.task_update import PipelineTaskUpdater as _PipelineTaskUpdater
from .pipeline.task_update_api import register_pipeline_task_update_api
from .pipeline.task_update_ports import (
    TaskUpdateAccess as _TaskUpdateAccess,
    TaskUpdatePolicy as _TaskUpdatePolicy,
    TaskUpdateRuntime as _TaskUpdateRuntime,
)

_pipeline_task_updater = _PipelineTaskUpdater(
    _TaskUpdateAccess(
        current_user=lambda: current_auth_user,
        http_error=lambda: HTTPException,
        load_config=lambda: load_config,
        scope_config=lambda: scope_config_for_user,
        load_task=lambda: load_pipeline_task,
        require_record_access=lambda: require_record_access,
        require_permission=lambda: require_permission,
        assert_unique_name=lambda: assert_unique_task_name,
        record_owner_id=lambda: record_owner_id,
    ),
    _TaskUpdatePolicy(
        canonical_accessory_ids=lambda: canonical_pipeline_accessory_ids,
        normalize_accessory_counts=lambda: normalize_pipeline_accessory_counts,
        accessory_snapshot=lambda: pipeline_task_accessory_snapshot,
        normalize_detection_method=lambda: normalize_pipeline_detection_method,
        method_uses_training=lambda: pipeline_method_uses_training,
        detection_methods=lambda: PIPELINE_DETECTION_METHODS,
        normalize_expected_count=lambda: normalize_expected_production_count,
    ),
    _TaskUpdateRuntime(
        lock=lambda: _pipeline_tasks_lock,
        now=lambda: time.time,
        save_task=lambda: save_pipeline_task,
        public_task=lambda: pipeline_task_public,
    ),
)
update_pipeline_task = register_pipeline_task_update_api(app, _pipeline_task_updater)

from .pipeline.accessory_routes import PipelineAccessoryRoutes as _PipelineAccessoryRoutes
from .pipeline.accessory_routes_api import register_pipeline_accessory_routes_api
from .pipeline.accessory_routes_ports import (
    PipelineAccessoryAccess as _PipelineAccessoryAccess,
    PipelineAccessoryCatalog as _PipelineAccessoryCatalog,
)
_pipeline_accessory_routes = _PipelineAccessoryRoutes(
    _PipelineAccessoryAccess(
        current_user=lambda: current_auth_user,
        load_config=lambda: load_config,
        scope_config=lambda: scope_config_for_user,
        http_error=lambda: HTTPException,
    ),
    _PipelineAccessoryCatalog(
        resolve=lambda: resolve_accessory_id,
        add_id=lambda: add_pipeline_accessory_id,
        aliases=lambda: accessory_id_aliases,
        remove_id=lambda: remove_pipeline_accessory_id,
        public_payload=lambda: pipeline_accessories_payload,
    ),
)
add_pipeline_accessory, remove_pipeline_accessory = register_pipeline_accessory_routes_api(
    app, _pipeline_accessory_routes,
)

from .pipeline.task_delete import PipelineTaskDeleter as _PipelineTaskDeleter
from .pipeline.task_delete_api import register_pipeline_task_delete_api
from .pipeline.task_delete_ports import (
    TaskDeleteAccess as _TaskDeleteAccess,
    TaskDeleteRuntime as _TaskDeleteRuntime,
    TaskDeleteCleanup as _TaskDeleteCleanup,
)
_pipeline_task_deleter = _PipelineTaskDeleter(
    _TaskDeleteAccess(
        current_user=lambda: current_auth_user,
        load_task=lambda: load_pipeline_task,
        require_record_access=lambda: require_record_access,
        http_error=lambda: HTTPException,
    ),
    _TaskDeleteRuntime(
        cancel_advance=lambda: cancel_pipeline_advance,
        lock=lambda: _pipeline_tasks_lock,
        delete_task_row=lambda: delete_pipeline_task_row,
    ),
    _TaskDeleteCleanup(
        delete_dataset=lambda: delete_training_dataset_resource,
        delete_model=lambda: delete_training_model_resource,
        delete_training_job=lambda: delete_training_task_record,
        delete_ai_task=lambda: delete_ai_detection_task_record,
    ),
)
delete_pipeline_task = register_pipeline_task_delete_api(app, _pipeline_task_deleter)

from .pipeline.agent_feedback import PipelineAgentFeedback as _PipelineAgentFeedback
from .pipeline.agent_feedback_api import register_pipeline_agent_feedback_api
from .pipeline.agent_feedback_ports import (
    AgentFeedbackAccess as _AgentFeedbackAccess,
    AgentFeedbackPolicy as _AgentFeedbackPolicy,
    AgentFeedbackRuntime as _AgentFeedbackRuntime,
)
_pipeline_agent_feedback = _PipelineAgentFeedback(
    _AgentFeedbackAccess(
        current_user=lambda: current_auth_user,
        load_config=lambda: load_config,
        scope_config=lambda: scope_config_for_user,
        load_task=lambda: load_pipeline_task,
        require_record_access=lambda: require_record_access,
        http_error=lambda: HTTPException,
    ),
    _AgentFeedbackPolicy(
        normalize_method=lambda: normalize_pipeline_detection_method,
        uses_training=lambda: pipeline_method_uses_training,
        sprite_flow=lambda: pipeline_uses_photo_highlight_sprite_flow,
    ),
    _AgentFeedbackRuntime(
        task_lock=lambda: _pipeline_tasks_lock,
        ensure_plan=lambda: ensure_agent_mcp_pose_plan,
        now=lambda: agent_mcp_now,
        skip_legacy=lambda: mark_legacy_pose_flow_skipped_for_photo_highlight,
        mark_advancing=lambda: mark_pipeline_task_advancing,
        pose_calls=lambda: ensure_agent_mcp_pose_tool_calls,
        image_config=lambda: agent_mcp_gemini_image_config,
        execute_calls=lambda: execute_agent_mcp_pose_tool_calls,
        pause_task=lambda: pause_agent_mcp_task,
        save_task=lambda: save_pipeline_task,
        public_task=lambda: pipeline_task_public,
        schedule_advance=lambda: schedule_pipeline_advance,
    ),
)
pipeline_agent_feedback = register_pipeline_agent_feedback_api(app, _pipeline_agent_feedback)

from .pipeline.agent_chat import PipelineAgentChat as _PipelineAgentChat
from .pipeline.agent_chat_api import register_pipeline_agent_chat_api
from .pipeline.agent_chat_ports import AgentChatAccess as _AgentChatAccess, AgentChatRuntime as _AgentChatRuntime

_pipeline_agent_chat = _PipelineAgentChat(
    _AgentChatAccess(
        current_user=lambda: current_auth_user,
        load_config=lambda: load_config,
        scope_config=lambda: scope_config_for_user,
        bounded_text=lambda: bounded_text,
        load_task=lambda: load_pipeline_task,
        require_record_access=lambda: require_record_access,
        http_error=lambda: HTTPException,
    ),
    _AgentChatRuntime(
        task_lock=lambda: _pipeline_tasks_lock,
        normalize_method=lambda: normalize_pipeline_detection_method,
        uses_training=lambda: pipeline_method_uses_training,
        deepcopy=lambda: copy.deepcopy,
        decide=lambda: agent_pipeline_decide,
        commit_turn=lambda: commit_pipeline_agent_turn,
        save_task=lambda: save_pipeline_task,
        public_task=lambda: pipeline_task_public,
        schedule_advance=lambda: schedule_pipeline_advance,
    ),
)
pipeline_agent_chat = register_pipeline_agent_chat_api(app, _pipeline_agent_chat)

from .pipeline.advance_control import PipelineAdvanceController as _PipelineAdvanceController
from .pipeline.advance_control_api import register_pipeline_advance_control_api
from .pipeline.advance_control_ports import (
    AdvanceControlAccess as _AdvanceControlAccess,
    AdvanceControlRuntime as _AdvanceControlRuntime,
)
_pipeline_advance_controller = _PipelineAdvanceController(
    _AdvanceControlAccess(
        current_user=lambda: current_auth_user,
        load_config=lambda: load_config,
        scope_config=lambda: scope_config_for_user,
        load_task=lambda: load_pipeline_task,
        require_record_access=lambda: require_record_access,
        http_error=lambda: HTTPException,
    ),
    _AdvanceControlRuntime(
        task_lock=lambda: _pipeline_tasks_lock,
        registry_lock=lambda: _pipeline_advance_registry_lock,
        inflight=lambda: _pipeline_advance_inflight,
        sync_task=lambda: sync_pipeline_task,
        now=lambda: time.time,
        save_task=lambda: save_pipeline_task,
        public_task=lambda: pipeline_task_public,
        schedule_advance=lambda: schedule_pipeline_advance,
        cancel_advance=lambda: cancel_pipeline_advance,
    ),
)
advance_pipeline_task_endpoint, cancel_pipeline_advance_endpoint = register_pipeline_advance_control_api(
    app, _pipeline_advance_controller,
)

# ---------------------------------------------------------------------------
# Account-scoped text inspection v2 (independent from the legacy task flow).

from local_inspection_service.text_inspection.record_store import (
    TEXT_INSPECTION_TABLES, TextRecordDependencies, TextRecordStore, record_row as _text_v2_row,
)

_text_records = TextRecordStore(TextRecordDependencies(
    runtime_repository=lambda: runtime_postgres_repository_or_none(),
    guard=lambda: _incoming_text_store_lock,
    directory=lambda: TEXT_INSPECTION_JSON_DIR,
    tables=lambda: TEXT_INSPECTION_TABLES,
    json_reader=lambda: _incoming_text_json_list,
    json_writer=lambda: _save_incoming_text_json_list,
    row_decoder=lambda: row_raw_json_list,
))


def _text_v2_json_path(kind: str) -> Path:
    return _text_records.json_path(kind)


def _text_v2_load(kind: str) -> list[dict[str, Any]]:
    return _text_records.load(kind)


def _text_v2_save(kind: str, value: dict[str, Any], *, insert_only: bool = False) -> bool:
    return _text_records.save(kind, value, insert_only=insert_only)


def _text_v2_update_attempt(kind: str, value: dict[str, Any], expected_status: str = "attempting") -> bool:
    return _text_records.update_attempt(kind, value, expected_status)


def _text_v2_owned(kind: str, record_id: str, owner_user_id: str) -> dict[str, Any] | None:
    return _text_records.owned(kind, record_id, owner_user_id)


def _text_v2_owner() -> tuple[str, str]:
    user = current_auth_user()
    return str(user.get("id") or ""), str(user.get("username") or "")


from local_inspection_service.text_inspection.media import TextMedia, TextMediaRecords
from local_inspection_service.text_inspection.images import (
    prepare_image as _text_v2_prepare_image, annotate as _text_v2_annotate,
    data_url as _text_v2_data_url, similarity as _text_v2_similarity,
    prepare_provider_image as _prepare_text_provider_image,
)

_text_media = TextMedia(
    directory=lambda: TEXT_INSPECTION_MEDIA_DIR,
    digest=lambda contents: sha256_bytes(contents),
    records=TextMediaRecords(
        owned=lambda: _text_v2_owned,
        save=lambda kind, value: _text_v2_save(kind, value),
    ),
)


def _text_v2_media_path(owner_user_id: str, standard_id: str, filename: str) -> Path:
    return _text_media.media_path(owner_user_id, standard_id, filename)


def _text_v2_write(path: Path, contents: bytes) -> None:
    return _text_media.write(path, contents)


def _text_v2_read_verified(path_value: str, owner_user_id: str, standard_id: str, *, expected_sha256: str = "", max_bytes: int = 120 * 1024 * 1024) -> bytes:
    return _text_media.read_verified(path_value, owner_user_id, standard_id, expected_sha256=expected_sha256, max_bytes=max_bytes)


from local_inspection_service.text_inspection.projection import public_record as _text_v2_public
from local_inspection_service.text_inspection.revisions import (
    RevisionRecords, TextRevisions,
    confirmed_snapshot as _text_v2_confirmed_snapshot, expected_revision as _text_v2_expected_revision,
)

_text_revisions = TextRevisions(
    RevisionRecords(
        load=lambda kind: _text_v2_load(kind),
        save=lambda kind, value, insert_only=False: _text_v2_save(kind, value, insert_only=insert_only),
    ),
    snapshot=lambda assets: _text_v2_confirmed_snapshot(assets),
)


def _text_v2_asset_bytes(asset: dict[str, Any], owner_user_id: str) -> bytes:
    return _text_media.asset_bytes(asset, owner_user_id)


def _text_v2_apply_revision(
    standard: dict[str, Any], assets: list[dict[str, Any]], *, action: str, asset_id: str, now: int,
) -> dict[str, Any]:
    return _text_revisions.apply(standard, assets, action=action, asset_id=asset_id, now=now)


from .text_inspection.standard_api import register as register_text_standards
from .text_inspection.standard_imports import StandardImports
from .text_inspection.standard_library import StandardLibrary as TextStandardLibrary
from .text_inspection.standard_edits import StandardEdits
from .text_inspection.standard_ports import (
    StandardAccess, StandardRecords, StandardWrites, StandardMedia,
    StandardRevisions, StandardParsers, StandardClassification, StandardPreparation,
)
from .text_inspection import preparation_policy as _standard_preparation_policy

_standard_access = StandardAccess(
    require_permission=lambda permission, **kwargs: require_permission(permission, **kwargs),
    owner=lambda: _text_v2_owner(),
)
_standard_records = StandardRecords(
    load=lambda kind: _text_v2_load(kind),
    save=lambda kind, value, **kwargs: _text_v2_save(kind, value, **kwargs),
    owned=lambda kind, identifier, owner: _text_v2_owned(kind, identifier, owner),
    public=lambda: _text_v2_public,
)
_standard_media = StandardMedia(
    path=lambda owner, standard, name: _text_v2_media_path(owner, standard, name),
    write=lambda: _text_v2_write,
    digest=lambda contents: sha256_bytes(contents),
)
_standard_imports = StandardImports(
    _standard_access, _standard_records, _standard_media,
    StandardParsers(doc=lambda: extract_doc_images,
                    docx=lambda data: extract_docx_candidates(data), pdf=lambda data: inspect_pdf(data)),
    StandardClassification(start=lambda standard, owner: document_import_jobs.start(standard, owner),
                           mark_unavailable=lambda: document_import_jobs.mark_unavailable),
    bounded_text=lambda: bounded_text,
)
_standard_library = TextStandardLibrary(
    _standard_access, _standard_records,
    refresh=lambda standard, owner: document_import_jobs.refresh(standard, owner),
    asset_bytes=lambda asset, owner: _text_v2_asset_bytes(asset, owner),
)
_standard_edits = StandardEdits(
    _standard_access, _standard_records,
    StandardWrites(repository=lambda: runtime_postgres_repository_or_none(), guard=lambda: _incoming_text_store_lock),
    _standard_media,
    StandardRevisions(expected=lambda: _text_v2_expected_revision,
                      snapshot=lambda assets: _text_v2_confirmed_snapshot(assets),
                      apply=lambda: _text_v2_apply_revision),
    StandardPreparation(start=lambda standard, owner: standard_preparation_jobs.start(standard, owner),
                        enabled=lambda owner: _standard_preparation_policy.enabled(owner)),
    prepare_image=lambda contents: _text_v2_prepare_image(contents),
    bounded_text=lambda: bounded_text,
)
_standard_routes = register_text_standards(app, _standard_imports, _standard_library, _standard_edits)
import_text_inspection_standard = _standard_routes.import_text_inspection_standard
list_text_inspection_standards = _standard_routes.list_text_inspection_standards
get_text_inspection_standard = _standard_routes.get_text_inspection_standard
get_text_inspection_asset_content = _standard_routes.get_text_inspection_asset_content
add_text_inspection_standard_asset = _standard_routes.add_text_inspection_standard_asset
patch_text_inspection_asset = _standard_routes.patch_text_inspection_asset
confirm_text_inspection_standard = _standard_routes.confirm_text_inspection_standard


from local_inspection_service.text_inspection.diagnostics import (
    TextDiagnostics, diagnostic_value as _text_v2_diagnostic_value,
    diagnostic_event as _text_v2_diagnostic_event, provider_diagnostics as _text_v2_provider_diagnostics,
)

_text_diagnostics = TextDiagnostics(
    digest=lambda: sha256_bytes,
    logger=lambda: TEXT_INSPECTION_DIAGNOSTIC_LOGGER,
)


def _text_v2_image_diagnostics(contents: bytes, *, source_format: str, mime_type: str) -> dict[str, Any]:
    return _text_diagnostics.image_diagnostics(contents, source_format=source_format, mime_type=mime_type)






def _text_v2_write_server_diagnostic(record: dict[str, Any]) -> None:
    return _text_diagnostics.write_server_diagnostic(record)


def _text_v2_prepare_provider_image(contents: bytes, mime_type: str) -> tuple[bytes, str, str]:
    return _prepare_text_provider_image(contents, mime_type,
        max_side=lambda: TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE, jpeg_quality=lambda: TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY)


from local_inspection_service.label_extraction_api import register as register_label_extraction
from local_inspection_service.agent_api import register as register_agent_api
from local_inspection_service.document_import_jobs import register as register_document_import_jobs

from .text_inspection.document_ports import DocumentAccess, DocumentRecords, DocumentModels
from .text_inspection.document_jobs import DocumentJobs
_document_records = DocumentRecords(
    repository=lambda: runtime_postgres_repository_or_none(),
    guard=lambda: _incoming_text_store_lock,
    owned=lambda kind, identifier, owner: _text_v2_owned(kind, identifier, owner),
    load=lambda kind: _text_v2_load(kind),
    save=lambda kind, record: _text_v2_save(kind, record),
    public=lambda record: _text_v2_public(record),
)
_document_models = DocumentModels(
    external_enabled=lambda: TEXT_INSPECTION_EXTERNAL_VLM_ENABLED,
    settings=lambda purpose: ai_detection_settings(purpose),
    transport=lambda request, settings, **kwargs: ai_urlopen(request, settings, **kwargs),
    record_usage=lambda settings, elapsed, ok, usage: record_model_call(settings, elapsed, ok, usage),
)
document_import_jobs = register_document_import_jobs(
    app,
    DocumentAccess(
        require_permission=lambda permission, **kwargs: require_permission(permission, **kwargs),
        owner=lambda: _text_v2_owner(),
    ),
    _document_records,
    DocumentJobs(
        _document_records, _document_models,
        asset_bytes=lambda asset, owner: _text_v2_asset_bytes(asset, owner),
        clear_repository=lambda: clear_thread_runtime_repository_selection(),
        runtime=TrainingThreadLifecycle(scope=_runtime_repositories.thread_scope),
    ),
)
from local_inspection_service.standard_preparation_jobs import register as register_standard_preparation
from .text_inspection.preparation_ports import PreparationAccess, PreparationRecords, PreparationMedia, PreparationModels, PreparationHistory
from .text_inspection.preparation_jobs import PreparationJobs
_preparation_records = PreparationRecords(
    repository=lambda: runtime_postgres_repository_or_none(),
    guard=lambda: _incoming_text_store_lock,
    owned=lambda kind, identifier, owner: _text_v2_owned(kind, identifier, owner),
    load=lambda kind: _text_v2_load(kind),
    save=lambda kind, value: _text_v2_save(kind, value),
    apply_revision=lambda standard, assets, **kwargs: _text_v2_apply_revision(standard, assets, **kwargs),
)
_preparation_media = PreparationMedia(
    path=lambda owner, identifier, name: _text_v2_media_path(owner, identifier, name),
    write=lambda path, data: _text_v2_write(path, data),
    digest=lambda data: sha256_bytes(data),
    asset_bytes=lambda asset, owner: _text_v2_asset_bytes(asset, owner),
    data_url=lambda data, mime: _text_v2_data_url(data, mime),
    read_verified=lambda path, owner, identifier, **kwargs: _text_v2_read_verified(path, owner, identifier, **kwargs),
)
_preparation_models = PreparationModels(
    settings=lambda purpose: ai_detection_settings(purpose),
    external_enabled=lambda: TEXT_INSPECTION_EXTERNAL_VLM_ENABLED,
    call_tool=lambda name, payload: call_ai_mcp_tool(name, payload),
    diagnostics=lambda provider, settings: _text_v2_provider_diagnostics(provider, settings),
)
standard_preparation_jobs = register_standard_preparation(
    app,
    PreparationAccess(
        require_permission=lambda permission, **kwargs: require_permission(permission, **kwargs),
        owner=lambda: _text_v2_owner(),
    ),
    _preparation_records,
    PreparationHistory(
        record_table=lambda: TEXT_INSPECTION_TABLES["records"],
        raw_rows=lambda rows: row_raw_json_list(rows),
        public=lambda record: _text_v2_public(record),
        attempt_writer=lambda: _text_v2_update_attempt,
    ),
    _preparation_media,
    PreparationJobs(_preparation_records, _preparation_media, _preparation_models,
                    clear_repository=lambda: clear_thread_runtime_repository_selection(),
                    runtime=TrainingThreadLifecycle(scope=_runtime_repositories.thread_scope)),
)
from local_inspection_service.comparison_history import register as register_comparison_history, display_snapshot as comparison_display_snapshot
from .text_inspection.history_ports import HistoryAccess, HistoryRecords, HistoryMedia
_history_records = HistoryRecords(
    repository=lambda: runtime_postgres_repository_or_none(),
    load=lambda kind: _text_v2_load(kind),
    owned=lambda kind, identifier, owner: _text_v2_owned(kind, identifier, owner),
    public=lambda record: _text_v2_public(record),
)
_history_media = HistoryMedia(
    path=lambda owner, standard, name: _text_v2_media_path(owner, standard, name),
    read_verified=lambda path, owner, standard, **kwargs: _text_v2_read_verified(path, owner, standard, **kwargs),
)
register_comparison_history(
    app,
    HistoryAccess(
        require_permission=lambda permission, **kwargs: require_permission(permission, **kwargs),
        owner=lambda: _text_v2_owner(),
    ),
    _history_records,
    _history_media,
)

from .text_inspection.extraction_ports import ExtractionAccess, ExtractionRecords, ExtractionMedia, ExtractionModels
_extraction_records = ExtractionRecords(
    repository=lambda: runtime_postgres_repository_or_none(),
    owned=lambda kind, identifier, owner: _text_v2_owned(kind, identifier, owner),
    load=lambda kind: _text_v2_load(kind),
    save=lambda kind, value, **kwargs: _text_v2_save(kind, value, **kwargs),
)
_extraction_media = ExtractionMedia(
    path=lambda owner, identifier, name: _text_v2_media_path(owner, identifier, name),
    write=lambda path, data: _text_v2_write(path, data),
    read_verified=lambda path, owner, identifier, **kwargs: _text_v2_read_verified(path, owner, identifier, **kwargs),
    digest=lambda data: sha256_bytes(data),
    data_url=lambda data, mime: _text_v2_data_url(data, mime),
)
_extraction_models = ExtractionModels(
    image_settings=lambda: image_generation_settings(),
    detection_settings=lambda purpose: ai_detection_settings(purpose),
    image_provider=lambda settings: image_generation_provider_from_settings(settings),
    transport=lambda request, settings, **kwargs: ai_urlopen(request, settings, **kwargs),
    diagnostic_value=lambda value: _text_v2_diagnostic_value(value),
    external_enabled=lambda: TEXT_INSPECTION_EXTERNAL_VLM_ENABLED,
)
_text_extraction_runtime = TrainingThreadLifecycle(scope=_runtime_repositories.thread_scope)
resolve_label_extraction = register_label_extraction(
    app,
    ExtractionAccess(
        require_permission=lambda permission, **kwargs: require_permission(permission, **kwargs),
        owner=lambda: _text_v2_owner(),
    ),
    _extraction_records, _extraction_media, _extraction_models,
    clear_repository=lambda: clear_thread_runtime_repository_selection(),
    runtime=_text_extraction_runtime,
)
from .agent.dependencies import AgentAccess, AgentAccounts
register_agent_api(
    app,
    AgentAccess(current_user=lambda: current_auth_user(), require_admin=lambda: require_admin_role()),
    AgentAccounts(load=lambda: load_auth_store(), find=lambda store, identifier: find_user(store, identifier)),
    repositories=lambda: runtime_postgres_repository_or_none(),
)
from local_inspection_service.codex_compare.api import register as register_codex_compare
from .codex_compare.dependencies import ComparisonAccess, StandardLibrary, ComparisonMedia, DocumentImports
_codex_standard_library = StandardLibrary(
    owned=lambda kind, identifier, owner: _text_v2_owned(kind, identifier, owner),
    load=lambda kind: _text_v2_load(kind),
    save=lambda kind, value, **kwargs: _text_v2_save(kind, value, **kwargs),
)
_codex_media = ComparisonMedia(
    data_directory=lambda: DATA_DIR,
    asset_bytes=lambda asset, owner: _text_v2_asset_bytes(asset, owner),
    media_path=lambda owner, standard, name: _text_v2_media_path(owner, standard, name),
    write=lambda path, data: _text_v2_write(path, data),
)
register_codex_compare(
    app,
    ComparisonAccess(
        require_permission=lambda permission: require_permission(permission),
        owner=lambda: _text_v2_owner(),
    ),
    repository_factory=lambda: runtime_postgres_repository_or_none(),
    standards=_codex_standard_library,
    media_dependencies=_codex_media,
    documents=DocumentImports(
        docx=lambda data: extract_docx_candidates(data),
        doc=lambda data: extract_doc_images(data),
    ),
)

from .label_inspection.api import register as register_label_inspection
from .label_inspection.dependencies import LabelAccess, RepositoryLifecycle, LabelImports
from .label_inspection import model as label_inspection_model
_label_repository_lifecycle = RepositoryLifecycle(
    repository=lambda: runtime_postgres_repository_or_none(),
    clear=lambda: clear_thread_runtime_repository_selection(),
)
_label_imports = LabelImports(
    data_directory=lambda: DATA_DIR,
    extract_docx=lambda data, **kwargs: extract_docx_candidates(data, **kwargs),
    extract_doc=lambda data: extract_doc_images(data),
    asset_bytes=lambda asset, owner: _text_v2_asset_bytes(asset, owner),
    read_verified=lambda path, owner, standard, **kwargs: _text_v2_read_verified(path, owner, standard, **kwargs),
)
register_label_inspection(
    app,
    LabelAccess(
        require_permission=lambda permission: require_permission(permission),
        require_admin=lambda: require_admin_role(),
        owner=lambda: _text_v2_owner(),
    ),
    _label_repository_lifecycle,
    _label_imports,
    models=lambda: resolve_model_profiles(),
    configuration=lambda: label_inspection_model.settings(lambda: resolve_model_profiles()),
)


from .text_inspection.inspection_api import register as register_text_inspections
from .text_inspection.comparison_submission import ComparisonSubmission
from .text_inspection.inspection_reviews import InspectionReviews
from .text_inspection.inspection_ports import (
    InspectionAccess, InspectionRecords, SubmissionPolicy, SubmissionImages,
    SubmissionModels, SubmissionDiagnostics, SubmissionMedia,
)
from . import qwen_evidence_jobs as _qwen_evidence_policy


from .text_inspection.comparison_runtime import ComparisonRuntime
_prepared_comparison_runtime = ComparisonRuntime(scope=_runtime_repositories.thread_scope)


def _submit_prepared_text_comparison(owner_user_id, owner_username, standard, asset, confirmed_snapshot, captured_upload, comparison_id, extraction):
    from local_inspection_service.standard_preparation_compare import submit
    from local_inspection_service.text_inspection.comparison_ports import ComparisonRecords, ComparisonMedia, ComparisonModels
    return submit(
        ComparisonRecords(_text_v2_load, _text_v2_save, _text_v2_owned, _text_v2_update_attempt, _text_v2_public),
        ComparisonMedia(_text_v2_media_path, _text_v2_write, sha256_bytes),
        ComparisonModels(ai_detection_settings, TEXT_INSPECTION_EXTERNAL_VLM_ENABLED, record_model_call),
        clear_thread_runtime_repository_selection,
        lambda name, default, environment=os: environment.getenv(name, default),
        standard_preparation_jobs, owner_user_id, owner_username,
        standard, asset, confirmed_snapshot, captured_upload, comparison_id, extraction,
        execution=_prepared_comparison_runtime)


_inspection_access = InspectionAccess(
    require_permission=lambda permission, **kwargs: require_permission(permission, **kwargs),
    owner=lambda: _text_v2_owner(),
)
_inspection_records = InspectionRecords(
    owned=lambda: _text_v2_owned,
    save=lambda kind, record, **kwargs: _text_v2_save(kind, record, **kwargs),
    public=lambda record: _text_v2_public(record),
)
_comparison_submission = ComparisonSubmission(
    _inspection_access, _inspection_records, load=lambda kind: _text_v2_load(kind),
    media=SubmissionMedia(path=lambda: _text_v2_media_path,
                          write=lambda path, data: _text_v2_write(path, data), digest=lambda: sha256_bytes),
    images=SubmissionImages(
        prepare=lambda: _text_v2_prepare_image,
        provider_copy=lambda data, mime: _text_v2_prepare_provider_image(data, mime),
        asset_bytes=lambda asset, owner: _text_v2_asset_bytes(asset, owner),
        annotate=lambda: _text_v2_annotate,
        data_url=lambda data, mime: _text_v2_data_url(data, mime),
    ),
    models=SubmissionModels(settings=lambda purpose: ai_detection_settings(purpose),
                            call=lambda: call_ai_mcp_tool,
                            prompt=lambda: strict_compare_prompt(),
                            normalize=lambda: normalize_vlm_provider_result,
                            validate=lambda value: validate_vlm_result(value)),
    policy=SubmissionPolicy(timeout=lambda: TEXT_INSPECTION_PROVIDER_TIMEOUT_SECONDS,
                            prompt_version=lambda: TEXT_INSPECTION_PROMPT_VERSION,
                            external_enabled=lambda: TEXT_INSPECTION_EXTERNAL_VLM_ENABLED,
                            automatic_match_verified=lambda: TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED,
                            qwen_enabled=lambda owner: _qwen_evidence_policy.enabled(owner)),
    diagnostics=SubmissionDiagnostics(
        image=lambda data, **kwargs: _text_v2_image_diagnostics(data, **kwargs),
        event=lambda: _text_v2_diagnostic_event,
        provider=lambda provider, settings: _text_v2_provider_diagnostics(provider, settings),
        value=lambda value: _text_v2_diagnostic_value(value),
        write=lambda record: _text_v2_write_server_diagnostic(record),
    ),
    prepared_submit=lambda *args: _submit_prepared_text_comparison(*args),
    resolve_extraction=lambda *args: resolve_label_extraction(*args),
    display_snapshot=lambda standard, asset: comparison_display_snapshot(standard, asset),
)
_inspection_reviews = InspectionReviews(
    _inspection_access, _inspection_records,
    read_verified=lambda: _text_v2_read_verified,
    audit=lambda: append_incoming_text_audit, bounded_text=lambda: bounded_text,
)
_inspection_routes = register_text_inspections(app, _comparison_submission, _inspection_reviews, _inspection_access)
compare_text_inspection_label = _inspection_routes.compare_text_inspection_label
get_text_inspection_v2_evidence = _inspection_routes.get_text_inspection_v2_evidence
create_text_manual_session = _inspection_routes.create_text_manual_session
inspect_text_manual_page = _inspection_routes.inspect_text_manual_page
complete_text_manual_session = _inspection_routes.complete_text_manual_session
review_text_inspection_v2 = _inspection_routes.review_text_inspection_v2


# ---------------------------------------------------------------------------
# Package-material incoming text inspection (legacy, retained for rollback).


from .runtime.json_records import (
    read_json_list as _incoming_text_json_list, write_json_list as _save_incoming_text_json_list,
)
from .text_inspection.incoming_store import IncomingTextStore, IncomingPaths, IncomingRows

_incoming_text_store = IncomingTextStore(
    repository=lambda: runtime_postgres_repository_or_none(), guard=lambda: _incoming_text_store_lock,
    paths=IncomingPaths(references=lambda: INCOMING_TEXT_REFERENCES_PATH,
                        inspections=lambda: INCOMING_TEXT_INSPECTIONS_PATH, audit=lambda: INCOMING_TEXT_AUDIT_PATH),
    rows=IncomingRows(reference=lambda record: incoming_text_reference_row(record),
                      inspection=lambda record: incoming_text_inspection_row(record),
                      audit=lambda event: audit_event_row(event), decode=lambda: row_raw_json_list),
    read_json=lambda path: _incoming_text_json_list(path),
    write_json=lambda path, values: _save_incoming_text_json_list(path, values),
    load_references=lambda: load_incoming_text_references(),
    load_inspections=lambda: load_incoming_text_inspections(),
)


def load_incoming_text_references() -> list[dict[str, Any]]:
    return _incoming_text_store.load_incoming_text_references()


def load_incoming_text_inspections() -> list[dict[str, Any]]:
    return _incoming_text_store.load_incoming_text_inspections()


def load_incoming_text_reference(reference_id: str) -> dict[str, Any] | None:
    return _incoming_text_store.load_incoming_text_reference(reference_id)


def load_incoming_text_inspection(inspection_id: str) -> dict[str, Any] | None:
    return _incoming_text_store.load_incoming_text_inspection(inspection_id)


def save_incoming_text_reference(reference: dict[str, Any], *, insert_only: bool = False) -> bool:
    return _incoming_text_store.save_incoming_text_reference(reference, insert_only=insert_only)


def save_incoming_text_inspection(inspection: dict[str, Any], *, insert_only: bool = False) -> bool:
    return _incoming_text_store.save_incoming_text_inspection(inspection, insert_only=insert_only)


def append_incoming_text_audit(event: dict[str, Any]) -> None:
    return _incoming_text_store.append_incoming_text_audit(event)



from .text_inspection.incoming_access import (
    public_record as _incoming_public_record, task_access_allowed as _incoming_task_access_allowed,
    IncomingTaskAccess,
)
from .text_inspection.incoming_ports import (
    IncomingAccess, IncomingReferences, IncomingInspections, IncomingTasks, IncomingMedia,
    IncomingWrites, IncomingJSON, IncomingOCR, IncomingImaging,
)
from .text_inspection.incoming_catalog import IncomingCatalog
from .text_inspection.incoming_execution import IncomingExecution
from .text_inspection.incoming_reviews import IncomingReviews
from .text_inspection.incoming_retention import IncomingCapacity, IncomingRetention
from .text_inspection.incoming_api import register_catalog as register_incoming_catalog, register_inspections as register_incoming_inspections

_incoming_task_access = IncomingTaskAccess(
    load=lambda task_id: load_pipeline_task(task_id), user=lambda: current_auth_user(),
    allowed=lambda: incoming_text_task_access_allowed,
)


def incoming_text_public(record: dict[str, Any]) -> dict[str, Any]:
    return _incoming_public_record(record, sanitize=lambda value: public_path_sanitized(value))


def incoming_text_task_access_allowed(task: dict[str, Any], user: dict[str, Any]) -> bool:
    return _incoming_task_access_allowed(task, user, is_admin=lambda value: user_is_admin(value), owner=lambda value: record_owner_id(value))


def require_incoming_text_task(task_id: str, *, write: bool = False) -> dict[str, Any]:
    return _incoming_task_access.require(task_id, write=write)






from .text_inspection.incoming_analysis import (
    decode_reference as decode_incoming_reference, result_mapping as _ocr_result_mapping,
    field_observation as _field_observation, IncomingOCREngine,
    observations as _incoming_observations, corroboration as _incoming_corroboration,
)

_incoming_ocr_engine = IncomingOCREngine(prepare_runtime=lambda: prepare_paddle_runtime())
_incoming_text_ocr_lock = _incoming_ocr_engine.lock


def incoming_text_ocr_engine() -> Any:
    return _incoming_ocr_engine.get()


def incoming_text_ocr_observations(image: np.ndarray) -> list[TextObservation]:
    return _incoming_observations(
        image, engine=lambda: incoming_text_ocr_engine(), mapping_provider=lambda: _ocr_result_mapping,
    )


def incoming_text_corroboration_observations(
    image: np.ndarray, rules: list[dict[str, Any]]
) -> dict[str, list[TextObservation]]:
    return _incoming_corroboration(image, rules, observe=lambda crop: incoming_text_ocr_observations(crop))


def _duplicate_incoming_capture(owner_user_id: str, task_id: str, capture_id: str) -> dict[str, Any] | None:
    return _incoming_reviews.duplicate(owner_user_id, task_id, capture_id)


_incoming_access = IncomingAccess(
    permission=lambda permission, **kwargs: require_permission(permission, **kwargs),
    user=lambda: current_auth_user(), task=lambda: require_incoming_text_task,
    record=lambda: require_record_access,
    owner=lambda record: record_owner_id(record), task_allowed=lambda task, user: incoming_text_task_access_allowed(task, user),
)
_incoming_references = IncomingReferences(
    all=lambda: load_incoming_text_references(), load=lambda reference_id: load_incoming_text_reference(reference_id),
    save=lambda record, **kwargs: save_incoming_text_reference(record, **kwargs),
)
_incoming_inspections = IncomingInspections(
    all=lambda: load_incoming_text_inspections(), load=lambda inspection_id: load_incoming_text_inspection(inspection_id),
    save=lambda record, **kwargs: save_incoming_text_inspection(record, **kwargs),
    duplicate=lambda owner, task_id, capture_id: _duplicate_incoming_capture(owner, task_id, capture_id),
)
_incoming_tasks = IncomingTasks(
    all=lambda: load_pipeline_tasks(), save=lambda task: save_pipeline_task(task),
    public=lambda: pipeline_task_public, config=lambda: scope_config_for_user(load_config()),
)
_incoming_media = IncomingMedia(
    output=lambda: output_write_dir_for_owner, root=lambda: OUTPUT_DIR,
    under=lambda path, root: path_is_under(path, root), decode=lambda: decode_incoming_reference,
)
_incoming_writes = IncomingWrites(
    repository=lambda: runtime_postgres_repository_or_none(), guard=lambda: _incoming_text_store_lock,
)
_incoming_json = IncomingJSON(
    paths=_incoming_text_store.paths,
    read=lambda path: _incoming_text_json_list(path), write=lambda path, values: _save_incoming_text_json_list(path, values),
)
_incoming_image_files = ImageFiles(lambda: cv2, files=_business_files)
_incoming_catalog = IncomingCatalog(
    _incoming_access, _incoming_references, _incoming_tasks, _incoming_media, _incoming_writes, _incoming_json,
    public=lambda record: incoming_text_public(record), verified=lambda: INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED,
    files=_business_files, images=_incoming_image_files,
)
_incoming_reviews = IncomingReviews(
    _incoming_access, _incoming_inspections, _incoming_tasks, _incoming_media, _incoming_writes, _incoming_json,
    decode_rows=lambda: row_raw_json_list, public=lambda record: incoming_text_public(record),
    files=_business_files,
)
_incoming_capacity = IncomingCapacity(data_dir=lambda: DATA_DIR, minimum_free=lambda: INCOMING_TEXT_MIN_FREE_BYTES)
_incoming_execution = IncomingExecution(
    _incoming_access, _incoming_references, _incoming_inspections, _incoming_media,
    IncomingOCR(observe=lambda image: incoming_text_ocr_observations(image),
                corroborate=lambda image, rules: incoming_text_corroboration_observations(image, rules),
                field=lambda: _field_observation),
    IncomingImaging(quality=lambda image: assess_image_quality(image), rectify=lambda: rectify_label,
                    similarity=lambda: local_visual_similarity,
                    annotate=lambda: annotate_inspection),
    capacity=lambda: require_incoming_text_storage_capacity, verified=lambda: INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED,
    public=lambda record: incoming_text_public(record), files=_business_files, images=_incoming_image_files,
)
_incoming_retention = IncomingRetention(
    _incoming_inspections, _incoming_media, _incoming_writes, _incoming_json,
    audit=lambda: append_incoming_text_audit, system_owner=lambda: SYSTEM_OWNER_ID, files=_business_files,
)
_incoming_catalog_routes = register_incoming_catalog(app, _incoming_catalog, files=lambda: _business_files)
get_incoming_text_task = _incoming_catalog_routes.get_incoming_text_task
get_incoming_text_reference_asset = _incoming_catalog_routes.get_incoming_text_reference_asset
create_incoming_text_reference = _incoming_catalog_routes.create_incoming_text_reference
update_incoming_text_reference_rules = _incoming_catalog_routes.update_incoming_text_reference_rules
clone_incoming_text_reference = _incoming_catalog_routes.clone_incoming_text_reference










def require_incoming_text_storage_capacity(upload_bytes: int) -> None:
    return _incoming_capacity.require(upload_bytes)


TEXT_COMPARE_BETA_MAX_BYTES = 10 * 1024 * 1024
TEXT_COMPARE_BETA_MAX_PIXELS = 16_000_000
TEXT_COMPARE_BETA_CACHE_TTL_SECONDS = 3600
TEXT_COMPARE_BETA_CACHE_MAX_BYTES = 32 * 1024 * 1024


from .text_inspection.beta_comparison import BetaComparison, BetaPolicy
from .text_inspection.beta_api import register as register_beta_comparison, BetaAccess

_beta_comparison = BetaComparison(
    BetaPolicy(ttl_seconds=lambda: TEXT_COMPARE_BETA_CACHE_TTL_SECONDS,
               max_pixels=lambda: TEXT_COMPARE_BETA_MAX_PIXELS,
               max_cache_bytes=lambda: TEXT_COMPARE_BETA_CACHE_MAX_BYTES),
    observer=lambda: incoming_text_ocr_observations,
)
_text_compare_beta_cache_lock = _beta_comparison.lock
_text_compare_beta_cache = _beta_comparison.cache


def _run_text_compare_beta(
    user_id: str, clean_id: str, reference_bytes: bytes, captured_bytes: bytes,
) -> dict[str, Any]:
    return _beta_comparison.run(user_id, clean_id, reference_bytes, captured_bytes)


analyze_text_compare_beta = register_beta_comparison(
    app, BetaAccess(require_permission=lambda permission, **kwargs: require_permission(permission, **kwargs),
                    current_user=lambda: current_auth_user()),
    max_bytes=lambda: TEXT_COMPARE_BETA_MAX_BYTES, run_provider=lambda: _run_text_compare_beta,
)


_incoming_inspection_routes = register_incoming_inspections(app, _incoming_execution, _incoming_reviews, files=lambda: _business_files)
inspect_incoming_text = _incoming_inspection_routes.inspect_incoming_text
get_incoming_text_inspection_evidence = _incoming_inspection_routes.get_incoming_text_inspection_evidence
review_incoming_text_inspection = _incoming_inspection_routes.review_incoming_text_inspection
list_incoming_text_inspections = _incoming_inspection_routes.list_incoming_text_inspections








def purge_expired_incoming_text_evidence() -> dict[str, int]:
    return _incoming_retention.purge()


DASHBOARD_AI_TASK_NAME = "Dashboard 快捷 AI 检测"


upsert_dashboard_ai_task = _detection_task_requests.upsert_dashboard_ai_task


from .accessories.routing import AccessoryRouting, RouteStore, RouteActions
from .accessories.routing_api import register_routing_api
_accessory_routing = AccessoryRouting(
    FileAccess(
        current_user=lambda: current_auth_user(),
        require_access=lambda record, user, **kwargs: require_record_access(record, user, **kwargs),
    ),
    RouteStore(
        load_config=lambda: load_config(),
        save_item=lambda item, config: save_accessory_item(item, config),
    ),
    RouteActions(
        ensure_profile=lambda item: ensure_accessory_ai_profile(item),
        upsert_task=lambda identifier, config: upsert_dashboard_ai_task(identifier, config),
        serialize=lambda item: serialize_accessory(item),
    ),
    allowed_routes=lambda: ACCESSORY_DETECTION_ROUTES,
)
set_accessory_route = register_routing_api(app, _accessory_routing)


REACT_PRODUCTION_ROUTE_SEGMENTS = {
    "workspace",
    "docs",
    "text-compare-beta",
    "login",
    "status",
    "inspect",
    "ai-inspect",
    "accessories",
    "training-library",
    "tasks",
    "pipeline",
    "rules",
    "users",
    "data-analysis",
}
REACT_PRODUCTION_BLOCKED_PREFIXES = (
    "/api/",
    "/static/",
    "/outputs/",
    "/react-preview",
    "/legacy",
    "/favicon",
    "/apple-touch-icon",
    "/site.webmanifest",
)


def react_production_spa_enabled() -> bool:
    return True


from .model_profiles.api import register as register_model_profiles
from .model_profiles.service import Service as ModelProfileService
from .model_profiles.dependencies import ProfileDependencies, ProfileApiDependencies
from .model_profiles.legacy import LegacyConfiguration, sources as legacy_model_sources

model_profile_service = ModelProfileService(ProfileDependencies(
    runtime_repository=lambda: runtime_postgres_repository_or_none(),
    write_secret=lambda key, value: set_local_secret_env(key, value),
    read_secret=lambda key: local_secret_env_value(key),
    legacy_sources=lambda: legacy_model_sources(LegacyConfiguration(
        ai=lambda: _legacy_ai_detection_settings(),
        image=lambda: _legacy_image_generation_settings(),
        agent=lambda: _legacy_load_agent_config(),
        local=lambda: load_ai_local_config(),
        ai_keys=lambda config: normalize_ai_key_items(config),
        image_keys=lambda config, provider: normalize_image_key_items(config, provider),
        agent_keys=lambda config: normalize_agent_key_items(config),
    )),
    validate_model=lambda value: validate_ai_model(value),
    validate_base_url=lambda value: validate_ai_base_url(value),
    mask_secret=lambda value: mask_secret(value),
))
register_model_profiles(app, model_profile_service, ProfileApiDependencies(
    require_admin=lambda: require_admin_role(),
    cost_from_usage=lambda model, usage: api_cost_from_usage(model, usage),
    cursor_api_url=lambda base, path: cursor_api_url(base, path),
    cursor_auth_headers=lambda key: cursor_auth_headers(key),
    model_options_from_items=lambda items, **kwargs: agent_model_options_from_items(items, **kwargs),
))


register_spa(app, _web_shell)
react_production_spa = _web_shell.react_production_spa


@app.on_event("startup")
def resume_image_worker_queue() -> None:
    list_codex_image_jobs()
    if os.environ.get("LOCAL_INSPECTION_AUTO_RESUME_WORKER") == "1":
        start_image_worker()


@app.on_event("startup")
def enforce_incoming_text_image_retention() -> None:
    try:
        purge_expired_incoming_text_evidence()
    except Exception as exc:  # retention failure must not make inspection data unavailable
        print(f"[incoming-text.retention] skipped: {type(exc).__name__}", flush=True)


from .runtime.shutdown import ShutdownStep, register_web_shutdown

_web_shutdown = register_web_shutdown(app, (
    ShutdownStep("pdf-import", app.state.label_pdf_import.close),
    ShutdownStep("pipeline-auto-agent", _pipeline_auto_agent_runtime.close),
    ShutdownStep("pipeline-advance", _pipeline_advance_runtime.close),
    ShutdownStep("pipeline-recommendation", _pipeline_recommendation_runtime.close),
    ShutdownStep("auto-label", _auto_optimization_label_processing.close),
    ShutdownStep("auto-shadow", _auto_optimization_shadow_evaluation.close),
    ShutdownStep("auto-training-check", _auto_optimization_training_scheduling.close),
    ShutdownStep("training", _training_task_runtime.close),
    ShutdownStep("background-codex", _background_codex_thread.close),
    ShutdownStep("image-worker", _image_worker_runtime.close),
    ShutdownStep("document-import", document_import_jobs.close),
    ShutdownStep("prepared-comparison", _prepared_comparison_runtime.close),
    ShutdownStep("standard-preparation", standard_preparation_jobs.close),
    ShutdownStep("text-extraction", _text_extraction_runtime.close),
    ShutdownStep("transfer-progress", _transfer_progress.close),
    ShutdownStep("yolo-warmup", _yolo_warmup_runtime.close),
    ShutdownStep("model-mcp", _ai_mcp_client.shutdown),
))


ensure_dirs()
