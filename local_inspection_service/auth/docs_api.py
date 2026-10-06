"""Administrator-only API documentation bound to a specific application."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

Record = dict[str, Any]


@dataclass(frozen=True)
class DocumentationAccess:
    authenticate: Callable[[Request], tuple[Record | None, Record, object]]
    users_exist: Callable[[Record], bool]
    is_admin: Callable[[Record], bool]

    def require_docs_admin(self, request: Request) -> dict[str, Any]:
        user, store, _ = self.authenticate(request)
        if not self.users_exist(store) or not user or not self.is_admin(user):
            raise HTTPException(status_code=404, detail="Not found")
        return user



def register_documentation_api(app: FastAPI, require_docs_admin: Callable[[Request], Record]):
    paths = {"/openapi.json", "/api/docs", "/redoc"}
    for route in app.routes:
        if getattr(route, "path", None) in paths and "GET" in (getattr(route, "methods", None) or ()):
            raise ValueError("Documentation routes are already registered")

    @app.get("/openapi.json", include_in_schema=False)
    def openapi_schema(request: Request) -> dict[str, Any]:
        require_docs_admin(request)
        if app.openapi_schema:
            return app.openapi_schema
        app.openapi_schema = get_openapi(
            title=app.title,
            version="1.0.0",
            routes=app.routes,
            description="Admin-only OpenAPI schema",
        )
        return app.openapi_schema


    @app.get("/api/docs", include_in_schema=False)
    def swagger_ui(request: Request) -> Response:
        require_docs_admin(request)
        return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} Docs")


    @app.get("/redoc", include_in_schema=False)
    def redoc_ui(request: Request) -> Response:
        require_docs_admin(request)
        return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} ReDoc")


    return openapi_schema, swagger_ui, redoc_ui
