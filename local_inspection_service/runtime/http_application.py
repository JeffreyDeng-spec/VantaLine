"""Construct the transport shell; domain routes and lifetime remain with composition."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from ..storage.artifacts.admission import UploadAdmission
from ..storage.artifacts.runtime import ArtifactRuntime

LOCAL_CORS_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"
LAN_CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|"
    r"[^/:]+\.local"
    r")(?::\d+)?$"
)


@dataclass(frozen=True)
class HttpApplication:
    app: FastAPI
    cors_origins: list[str]
    cors_origin_regex: str


def create_http_application(
    environment: Mapping[str, str],
    *, upload_runtime_provider: Callable[[], ArtifactRuntime | None] | None = None,
) -> HttpApplication:
    """Allocate a fresh HTTP shell without domain routes, resources or workers."""
    app = FastAPI(title="VantaLine Local Inspection Service", docs_url=None, redoc_url=None, openapi_url=None)
    if environment.get("VANTALINE_FILE_STORE", "local") != "local":
        if upload_runtime_provider is None:
            app.add_middleware(UploadAdmission)
        else:
            app.add_middleware(UploadAdmission, runtime_provider=upload_runtime_provider)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    origin_regex = environment.get(
        "INSPECTION_CORS_ORIGIN_REGEX",
        LAN_CORS_ORIGIN_REGEX if environment.get("INSPECTION_ENABLE_LAN_CORS") == "1" else LOCAL_CORS_ORIGIN_REGEX,
    )
    origins = [origin.strip() for origin in environment.get("INSPECTION_CORS_ORIGINS", "").split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    return HttpApplication(app, origins, origin_regex)
