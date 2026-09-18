"""Lazy training executor configuration; no application or credential ownership."""
from collections.abc import Callable, Mapping
import ipaddress
from typing import Any
from urllib.parse import quote, urlsplit

REMOTE_TRAINING_EXECUTOR_ENV = "INSPECTION_TRAINING_EXECUTOR"
REMOTE_TRAINING_ENDPOINT_ENV = "INSPECTION_REMOTE_TRAINING_ENDPOINT"
REMOTE_TRAINING_API_KEY_ENV = "INSPECTION_REMOTE_TRAINING_API_KEY"
REMOTE_TRAINING_TIMEOUT_ENV = "INSPECTION_REMOTE_TRAINING_TIMEOUT_SECONDS"
REMOTE_TRAINING_DEFAULT_TIMEOUT_SECONDS = 600.0
RUNPOD_YOLO_ENDPOINT_ID_ENV = "VANTALINE_RUNPOD_YOLO_ENDPOINT_ID"
RUNPOD_YOLO_API_KEY_ENV = "VANTALINE_RUNPOD_API_KEY"
RUNPOD_YOLO_API_BASE_ENV = "VANTALINE_RUNPOD_API_BASE"
RUNPOD_YOLO_PUBLIC_BASE_URL_ENV = "VANTALINE_PUBLIC_BASE_URL"
RUNPOD_YOLO_DATASET_TOKEN_TTL_ENV = "VANTALINE_RUNPOD_YOLO_DATASET_TOKEN_TTL_SECONDS"
RUNPOD_YOLO_POLL_INTERVAL_ENV = "VANTALINE_RUNPOD_YOLO_POLL_INTERVAL_SECONDS"
RUNPOD_YOLO_JOB_TIMEOUT_ENV = "VANTALINE_RUNPOD_YOLO_JOB_TIMEOUT_SECONDS"
RUNPOD_YOLO_CLIENT_TIMEOUT_ENV = "VANTALINE_RUNPOD_YOLO_CLIENT_TIMEOUT_SECONDS"
RUNPOD_YOLO_AUTH_SCHEME_ENV = "VANTALINE_RUNPOD_AUTH_SCHEME"
RUNPOD_YOLO_INLINE_DATASET_MAX_BYTES_ENV = "VANTALINE_RUNPOD_YOLO_INLINE_DATASET_MAX_BYTES"
RUNPOD_YOLO_ARTIFACT_MAX_BYTES_ENV = "VANTALINE_RUNPOD_YOLO_ARTIFACT_MAX_BYTES"
WINDOWS_WORKER_BASE_URL_ENV = "VANTALINE_WORKER_BASE_URL"
WINDOWS_WORKER_TOKEN_ENV = "VANTALINE_WORKER_TOKEN"
WINDOWS_WORKER_TIMEOUT_ENV = "VANTALINE_WORKER_TIMEOUT_SECONDS"
WINDOWS_WORKER_DEFAULT_TIMEOUT_SECONDS = 30.0


def host_is_private_or_tailnet(host: str) -> bool:
    value = str(host or "").strip().strip("[]").lower()
    if value in {"localhost", "127.0.0.1", "::1"}:
        return True
    if value.endswith((".local", ".lan", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address in ipaddress.ip_network("100.64.0.0/10")


class ExecutorSettings:
    def __init__(self, environment: Callable[[], Mapping[str, str]], mask_url: Callable[[Any], str]):
        self.environment, self.mask_url = environment, mask_url

    def training_executor_mode(self) -> str:
        mode = self.environment().get(REMOTE_TRAINING_EXECUTOR_ENV, "local").strip().lower()
        if mode == "worker":
            return "runpod"
        return mode if mode in {"local", "remote", "runpod"} else "local"

    def worker_local_training_fallback_enabled(self) -> bool:
        return self.environment().get("INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}

    def validate_remote_training_endpoint(self, value: Any) -> str:
        endpoint = str(value or "").strip()
        if not endpoint:
            return ""
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(f"{REMOTE_TRAINING_ENDPOINT_ENV} must be an http(s) URL")
        if parsed.username or parsed.password:
            raise RuntimeError(f"{REMOTE_TRAINING_ENDPOINT_ENV} must not include credentials")
        if parsed.query or parsed.fragment:
            raise RuntimeError(f"{REMOTE_TRAINING_ENDPOINT_ENV} must not include query strings or fragments")
        if parsed.scheme == "http" and not host_is_private_or_tailnet(parsed.hostname or ""):
            raise RuntimeError(f"{REMOTE_TRAINING_ENDPOINT_ENV} uses http; use a private/Tailscale/reverse-tunnel host or HTTPS")
        return endpoint.rstrip("/")

    def validate_windows_worker_base_url(self, value: Any) -> str:
        endpoint = str(value or "").strip()
        if not endpoint:
            return ""
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(f"{WINDOWS_WORKER_BASE_URL_ENV} must be an http(s) URL")
        if parsed.username or parsed.password:
            raise RuntimeError(f"{WINDOWS_WORKER_BASE_URL_ENV} must not include credentials")
        if parsed.query or parsed.fragment:
            raise RuntimeError(f"{WINDOWS_WORKER_BASE_URL_ENV} must not include query strings or fragments")
        if parsed.scheme == "http" and not host_is_private_or_tailnet(parsed.hostname or ""):
            raise RuntimeError(f"{WINDOWS_WORKER_BASE_URL_ENV} uses http; use a private/Tailscale/reverse-tunnel host or HTTPS")
        return endpoint.rstrip("/")

    def remote_training_endpoint(self) -> str:
        return self.validate_remote_training_endpoint(self.environment().get(REMOTE_TRAINING_ENDPOINT_ENV, ""))

    def windows_worker_base_url(self) -> str:
        return self.validate_windows_worker_base_url(self.environment().get(WINDOWS_WORKER_BASE_URL_ENV, ""))

    def remote_training_timeout_seconds(self) -> float:
        try:
            return max(5.0, min(3600.0, float(self.environment().get(REMOTE_TRAINING_TIMEOUT_ENV, "") or REMOTE_TRAINING_DEFAULT_TIMEOUT_SECONDS)))
        except (TypeError, ValueError):
            return REMOTE_TRAINING_DEFAULT_TIMEOUT_SECONDS

    def windows_worker_timeout_seconds(self) -> float:
        try:
            return max(2.0, min(3600.0, float(self.environment().get(WINDOWS_WORKER_TIMEOUT_ENV, "") or WINDOWS_WORKER_DEFAULT_TIMEOUT_SECONDS)))
        except (TypeError, ValueError):
            return WINDOWS_WORKER_DEFAULT_TIMEOUT_SECONDS

    def windows_worker_image_timeout_seconds(self) -> float:
        try:
            return max(60.0, min(1800.0, float(self.environment().get("VANTALINE_WORKER_IMAGE_TIMEOUT_SECONDS", "") or 960.0)))
        except (TypeError, ValueError):
            return 960.0

    def windows_worker_headers(self) -> dict[str, str]:
        token = self.environment().get(WINDOWS_WORKER_TOKEN_ENV, "").strip()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def training_execution_status(self, *, include_worker_probe: bool = False, include_worker_services: bool = False) -> dict[str, Any]:
        endpoint = ""
        endpoint_error = ""
        try:
            endpoint = self.remote_training_endpoint()
        except RuntimeError as exc:
            endpoint_error = str(exc)
        mode = self.training_executor_mode()
        return {
            "executor": mode,
            "remote_enabled": mode == "remote",
            "remote_endpoint_configured": bool(endpoint),
            "remote_endpoint": self.mask_url(endpoint),
            "remote_endpoint_error": endpoint_error,
            "remote_api_key_present": bool(self.environment().get(REMOTE_TRAINING_API_KEY_ENV, "").strip()),
            "required_endpoint_env": REMOTE_TRAINING_ENDPOINT_ENV,
            "required_api_key_env": REMOTE_TRAINING_API_KEY_ENV,
            "runpod_enabled": mode == "runpod",
            "runpod_endpoint_configured": bool(self.environment().get(RUNPOD_YOLO_ENDPOINT_ID_ENV, "").strip()),
            "runpod_api_key_present": bool((self.environment().get(RUNPOD_YOLO_API_KEY_ENV, "") or self.environment().get("RUNPOD_API_KEY", "")).strip()),
            "runpod_public_base_url_configured": bool(self.environment().get(RUNPOD_YOLO_PUBLIC_BASE_URL_ENV, "").strip() or self.environment().get("INSPECTION_PUBLIC_BASE_URL", "").strip()),
            "required_runpod_endpoint_env": RUNPOD_YOLO_ENDPOINT_ID_ENV,
            "required_runpod_api_key_env": RUNPOD_YOLO_API_KEY_ENV,
            "required_runpod_public_base_url_env": RUNPOD_YOLO_PUBLIC_BASE_URL_ENV,
            "retired_executors": ["windows_worker"],
        }

    def runpod_yolo_endpoint_id(self) -> str:
        endpoint_id = str(self.environment().get(RUNPOD_YOLO_ENDPOINT_ID_ENV, "") or "").strip()
        if not endpoint_id:
            raise RuntimeError(f"{RUNPOD_YOLO_ENDPOINT_ID_ENV} is not configured")
        return endpoint_id

    def runpod_yolo_api_key(self) -> str:
        api_key = str(self.environment().get(RUNPOD_YOLO_API_KEY_ENV, "") or self.environment().get("RUNPOD_API_KEY", "") or "").strip()
        if not api_key:
            raise RuntimeError(f"{RUNPOD_YOLO_API_KEY_ENV} is not configured")
        return api_key

    def runpod_yolo_api_base(self) -> str:
        raw = str(self.environment().get(RUNPOD_YOLO_API_BASE_ENV, "") or "https://api.runpod.ai/v2").strip().rstrip("/")
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise RuntimeError(f"{RUNPOD_YOLO_API_BASE_ENV} must be an http(s) base URL without query or fragment")
        if parsed.username or parsed.password:
            raise RuntimeError(f"{RUNPOD_YOLO_API_BASE_ENV} must not include credentials")
        return raw

    def runpod_yolo_public_base_url(self) -> str:
        raw = str(self.environment().get(RUNPOD_YOLO_PUBLIC_BASE_URL_ENV, "") or self.environment().get("INSPECTION_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise RuntimeError(f"{RUNPOD_YOLO_PUBLIC_BASE_URL_ENV} must be the public http(s) base URL for this service")
        if parsed.username or parsed.password:
            raise RuntimeError(f"{RUNPOD_YOLO_PUBLIC_BASE_URL_ENV} must not include credentials")
        return raw

    def runpod_yolo_job_timeout_seconds(self) -> int:
        try:
            return max(300, min(7 * 24 * 3600, int(float(self.environment().get(RUNPOD_YOLO_JOB_TIMEOUT_ENV, "") or 7200))))
        except (TypeError, ValueError):
            return 7200

    def runpod_yolo_client_timeout_seconds(self) -> float:
        try:
            return max(5.0, min(300.0, float(self.environment().get(RUNPOD_YOLO_CLIENT_TIMEOUT_ENV, "") or 60.0)))
        except (TypeError, ValueError):
            return 60.0

    def runpod_yolo_poll_interval_seconds(self) -> float:
        try:
            return max(5.0, min(120.0, float(self.environment().get(RUNPOD_YOLO_POLL_INTERVAL_ENV, "") or 20.0)))
        except (TypeError, ValueError):
            return 20.0

    def runpod_yolo_dataset_token_ttl_seconds(self) -> int:
        try:
            return max(3600, min(7 * 24 * 3600, int(float(self.environment().get(RUNPOD_YOLO_DATASET_TOKEN_TTL_ENV, "") or 3 * 24 * 3600))))
        except (TypeError, ValueError):
            return 3 * 24 * 3600

    def runpod_yolo_inline_dataset_max_bytes(self) -> int:
        try:
            return max(0, min(8 * 1024 * 1024, int(float(self.environment().get(RUNPOD_YOLO_INLINE_DATASET_MAX_BYTES_ENV, "") or 0))))
        except (TypeError, ValueError):
            return 0

    def runpod_yolo_artifact_max_bytes(self) -> int:
        try:
            return max(
                10 * 1024 * 1024,
                min(1024 * 1024 * 1024, int(float(self.environment().get(RUNPOD_YOLO_ARTIFACT_MAX_BYTES_ENV, "") or 256 * 1024 * 1024))),
            )
        except (TypeError, ValueError):
            return 256 * 1024 * 1024

    def runpod_yolo_url(self, path: str) -> str:
        endpoint_id = quote(self.runpod_yolo_endpoint_id(), safe="")
        clean_path = str(path or "").strip().lstrip("/")
        return f"{self.runpod_yolo_api_base()}/{endpoint_id}/{clean_path}"

    def runpod_yolo_authorization_values(self) -> list[str]:
        api_key = self.runpod_yolo_api_key()
        scheme = str(self.environment().get(RUNPOD_YOLO_AUTH_SCHEME_ENV, "") or "bearer").strip().lower()
        if scheme in {"raw", "none", "token"}:
            return [api_key, f"Bearer {api_key}"]
        return [f"Bearer {api_key}", api_key]
