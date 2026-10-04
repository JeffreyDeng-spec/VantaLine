"""File responses behind the application's existing ownership middleware."""
import mimetypes
from pathlib import Path

from anyio import CancelScope, to_thread
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.datastructures import Headers

from .runtime import get_runtime
from .types import ArtifactUnavailable
from .files import BusinessFiles


def file_response(path, *, local_factory=FileResponse, **kwargs):
    """Use only after the calling route's existing permission/ownership checks."""
    runtime = BusinessFiles().runtime(path)
    if runtime is None:
        return local_factory(path, **kwargs)
    row = runtime.store.locations.get(runtime.key(Path(path)))
    if row is None and runtime.mode == "hybrid":
        return local_factory(path, **kwargs)
    if row is None or row.state != "ready":
        raise HTTPException(404)
    return ArtifactResponse(runtime, row, kwargs.get("media_type") or mimetypes.guess_type(str(path))[0] or "application/octet-stream",
                            filename=kwargs.get("filename"), headers=kwargs.get("headers"))


class ArtifactResponse(Response):
    def __init__(self, runtime, artifact, media_type, *, filename=None, headers=None):
        super().__init__(media_type=media_type)
        self.runtime, self.artifact = runtime, artifact
        self.filename, self.file_headers = filename, headers or {}

    async def __call__(self, scope, receive, send):
        lease = self.runtime.store.cache.open(self.artifact)
        try:
            path = await to_thread.run_sync(lease.__enter__)
        except ArtifactUnavailable:
            await Response("File storage unavailable", status_code=503)(scope, receive, send)
            return
        try:
            # Pin the exact selected generation through the final response byte,
            # including disconnects, HEAD and Range responses.
            response = FileResponse(path, media_type=self.media_type, filename=self.filename, headers={
                "etag": '"' + self.artifact.sha256 + '"',
                "cache-control": "private, no-cache",
                **self.file_headers,
            })
            await response(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await to_thread.run_sync(lease.__exit__, None, None, None)


class ArtifactStaticFiles(StaticFiles):
    """This class never authorizes an object key; the outer app must authorize URL."""
    def __init__(self, *, directory, runtime_provider=get_runtime):
        super().__init__(directory=directory)
        self.runtime_provider = runtime_provider

    async def get_response(self, path, scope):
        runtime = self.runtime_provider()
        if runtime is None:
            return await super().get_response(path, scope)
        if scope["method"] not in {"GET", "HEAD"}:
            raise HTTPException(405)
        try:
            key = runtime.key(Path(self.directory) / path)
        except ValueError:
            raise HTTPException(404) from None
        try:
            row = await to_thread.run_sync(runtime.store.locations.get, key)
        except ArtifactUnavailable:
            raise HTTPException(503, "File storage unavailable") from None
        if row is None and runtime.mode == "hybrid":
            return await super().get_response(path, scope)
        if row is None or row.state != "ready":
            raise HTTPException(404)
        request_headers = Headers(scope=scope)
        if self.is_not_modified(Headers({"etag": '"' + row.sha256 + '"'}), request_headers):
            return Response(status_code=304, headers={"etag": '"' + row.sha256 + '"',
                                                      "cache-control": "private, no-cache"})
        media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return ArtifactResponse(runtime, row, media_type)
