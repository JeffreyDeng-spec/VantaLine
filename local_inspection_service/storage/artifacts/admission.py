"""Reserve multipart staging before Starlette receives or spools upload bodies."""
from pathlib import Path
import tempfile

from starlette.responses import JSONResponse
from .runtime import get_runtime
from .types import DiskCapacityError


class UploadAdmission:
    def __init__(self, app, *, runtime_provider=get_runtime):
        self.app, self.runtime_provider = app, runtime_provider

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", ()))
        if not headers.get(b"content-type", b"").lower().startswith(b"multipart/form-data"):
            return await self.app(scope, receive, send)
        runtime = self.runtime_provider()
        if runtime is None:
            return await self.app(scope, receive, send)
        raw = headers.get(b"content-length", b"")
        if not raw.isdigit():
            return await JSONResponse({"detail": "Upload Content-Length is required"}, 411)(scope, receive, send)
        size = int(raw)
        budget = runtime.store.budget
        # The body spool and verified immutable publication copy coexist. Reject
        # before receiving when even one request cannot fit both copies.
        if size <= 0 or size * 2 > budget.limits["upload"]:
            return await JSONResponse({"detail": "Upload exceeds staging capacity"}, 413)(scope, receive, send)
        if budget.preallocated:
            expected = budget.scratch_roots["upload"].parent / "spool"
            if Path(tempfile.gettempdir()).resolve() != expected.resolve():
                return await JSONResponse({"detail": "Upload staging is not configured"}, 503)(scope, receive, send)
        reservation = budget.reserve("upload", size)
        try:
            reservation.__enter__()
        except DiskCapacityError:
            return await JSONResponse({"detail": "Upload staging is busy"}, 503)(scope, receive, send)
        received = 0
        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > size:
                    # HTTPException participates in FastAPI's parser cleanup and
                    # prevents any route handler or paid task from starting.
                    from starlette.exceptions import HTTPException
                    raise HTTPException(413, "Upload exceeds declared size")
                if not message.get("more_body", False) and received != size:
                    from starlette.exceptions import HTTPException
                    raise HTTPException(400, "Upload body is incomplete")
            return message
        try:
            return await self.app(scope, bounded_receive, send)
        finally:
            reservation.__exit__(None, None, None)
