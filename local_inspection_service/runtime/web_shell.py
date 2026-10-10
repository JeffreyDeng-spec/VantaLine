"""Public document responses; API authorization remains in security middleware."""
from dataclasses import dataclass
from pathlib import Path
from typing import AbstractSet, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse


@dataclass(frozen=True)
class WebShell:
    production_dist: Callable[[], Path]
    exists: Callable[[Path], bool]
    route_segments: Callable[[], AbstractSet[str]]
    blocked_prefixes: Callable[[], tuple[str, ...]]
    enabled: Callable[[], bool]

    def index(self) -> FileResponse:
        index_path = self.production_dist() / "index.html"
        if not self.exists(index_path):
            raise HTTPException(status_code=404, detail="React production build is not available")
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    def legacy_index(self, legacy_path: str = "") -> FileResponse:
        raise HTTPException(status_code=404, detail="Legacy frontend has been removed")

    def react_preview(self, request: Request, preview_path: str = "") -> RedirectResponse:
        path = preview_path.strip("/")
        first_segment = path.split("/", 1)[0]
        if not path:
            destination = "/workspace"
        elif first_segment in {"workspace", "docs", "login"}:
            destination = f"/{path}"
        elif first_segment in self.route_segments():
            destination = f"/workspace/{path}"
        else:
            raise HTTPException(status_code=404, detail="Not found")
        if request.url.query:
            destination += f"?{request.url.query}"
        return RedirectResponse(url=destination, status_code=307)

    def react_production_spa(self, react_path: str) -> FileResponse:
        if not self.enabled():
            raise HTTPException(status_code=404, detail="Not found")
        normalized = f"/{react_path.strip('/')}" if react_path else "/"
        if normalized == "/" or normalized.startswith(self.blocked_prefixes()):
            raise HTTPException(status_code=404, detail="Not found")
        first_segment = normalized.strip("/").split("/", 1)[0]
        if first_segment not in self.route_segments():
            raise HTTPException(status_code=404, detail="Not found")
        index_path = self.production_dist() / "index.html"
        if not self.exists(index_path):
            raise HTTPException(status_code=404, detail="Production React build is not available")
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )


def register_entry_routes(app: FastAPI, shell: WebShell) -> None:
    app.get("/")(shell.index)
    for path in ("/legacy/{legacy_path:path}", "/legacy/", "/legacy"):
        app.get(path)(shell.legacy_index)
    for path in ("/react-preview/{preview_path:path}", "/react-preview/", "/react-preview"):
        app.get(path)(shell.react_preview)


def register_spa(app: FastAPI, shell: WebShell) -> None:
    app.get("/{react_path:path}")(shell.react_production_spa)
