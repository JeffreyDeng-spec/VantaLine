"""HTTP security assembly without importing the application entry point."""
from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any, Protocol
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from ..runtime.identity import RequestIdentity
from .policy import user_is_admin, user_has_permission
from .route_permissions import route_allowed_permissions


class Authenticate(Protocol):
    def __call__(self, request: Request, *, indexed: bool = False) -> tuple[dict[str, Any] | None, dict[str, Any], bool]: ...


@dataclass(frozen=True)
class SecurityDependencies:
    authenticate: Authenticate
    users_exist: Callable[[dict[str, Any]], bool]
    identity: RequestIdentity
    output_visible: Callable[[str, dict[str, Any]], bool]
    same_origin: Callable[[str, str], bool]
    cors_origin_allowed: Callable[[str], bool]


def register_security_middleware(app: FastAPI, dependencies: SecurityDependencies):
    @app.middleware("http")
    async def reject_untrusted_cross_origin_writes(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            host = request.headers.get("host", "")
            if origin and not dependencies.same_origin(origin, host) and not dependencies.cors_origin_allowed(origin):
                return PlainTextResponse("Untrusted cross-origin write request", status_code=403)
        path = request.url.path
        auth_user: dict[str, Any] | None = None
        token = None
        public_auth_paths = {"/api/auth/status", "/api/auth/login", "/api/auth/bootstrap", "/api/auth/logout", "/api/version"}
        public_runpod_training_transfer = (
            request.method in {"GET", "HEAD"}
            and re.match(r"^/api/training/runpod/datasets/[^/]+/[^/]+/dataset\.zip$", path) is not None
        ) or (
            request.method == "PUT"
            and re.match(r"^/api/training/runpod/artifacts/[^/]+/[^/]+/run\.zip$", path) is not None
        )
        if path.startswith("/api/") and path not in public_auth_paths and not public_runpod_training_transfer:
            auth_user, auth_store, _ = dependencies.authenticate(request, indexed=True)
            if not dependencies.users_exist(auth_store):
                return JSONResponse({"detail": "First admin setup required", "setup_required": True}, status_code=503)
            if not auth_user:
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            if (path.startswith(("/api/ai/config", "/api/agent/config", "/api/admin/model-profiles"))) and not user_is_admin(auth_user):
                return JSONResponse({"detail": "Admin role required"}, status_code=403)
            required_permissions = route_allowed_permissions(path, request.method.upper())
            if required_permissions and not any(user_has_permission(auth_user, permission) for permission in required_permissions):
                return JSONResponse(
                    {"detail": "Permission denied", "permission": " / ".join(required_permissions)},
                    status_code=403,
                )
            request.state.user = auth_user
            token = dependencies.identity.set(auth_user)
        elif path.startswith("/outputs/"):
            auth_user, auth_store, _ = dependencies.authenticate(request, indexed=True)
            if not dependencies.users_exist(auth_store):
                return PlainTextResponse("First admin setup required", status_code=503)
            if not auth_user:
                return PlainTextResponse("Authentication required", status_code=401)
            if not dependencies.output_visible(path, auth_user):
                return PlainTextResponse("Not found", status_code=404)
            request.state.user = auth_user
            token = dependencies.identity.set(auth_user)
        try:
            response = await call_next(request)
        finally:
            if token is not None:
                dependencies.identity.reset(token)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(self), serial=(self), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' https: wss:; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        if str(request.headers.get("x-forwarded-proto") or request.url.scheme).lower() == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.method in {"GET", "HEAD"}:
            cacheable_ok = getattr(response, "status_code", 200) < 400
            if path.startswith("/static/") and cacheable_ok:
                response.headers.setdefault("Cache-Control", "public, max-age=604800, immutable")
            elif path.startswith("/react-preview/assets/") and cacheable_ok:
                response.headers.setdefault("Cache-Control", "public, max-age=604800, immutable")
            elif path == "/react-preview" or path.startswith("/react-preview/"):
                response.headers.setdefault("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            elif path.startswith("/outputs/"):
                # Output artifacts are effectively write-once; let the browser show the
                # cached copy instantly on reopen and revalidate in the background
                # (StaticFiles still answers conditional requests with a cheap 304).
                response.headers.setdefault("Cache-Control", "private, max-age=600, stale-while-revalidate=86400")
            elif path.startswith("/api/"):
                response.headers.setdefault("Cache-Control", "no-store")
        return response

    return reject_untrusted_cross_origin_writes
