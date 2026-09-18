"""Stream worker uploads/downloads through explicit transports without adding retries."""
from collections.abc import Callable, Iterator, Mapping
import io
import json
from pathlib import Path
from typing import Any, ContextManager, Protocol
from uuid import UUID
import requests
from .executor_settings import WINDOWS_WORKER_BASE_URL_ENV


class WorkerUploadResponse(Protocol):
    status_code: int
    text: str
    def json(self) -> Any: ...


class WorkerDownloadResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]
    def iter_content(self, *, chunk_size: int) -> Iterator[bytes]: ...


class WorkerStreamPost(Protocol):
    def __call__(self, url: str, *, data: Iterator[bytes], headers: dict[str, str],
                 timeout: float) -> WorkerUploadResponse: ...


class WorkerStreamGet(Protocol):
    def __call__(self, url: str, *, headers: dict[str, str], timeout: float,
                 stream: bool) -> ContextManager[WorkerDownloadResponse]: ...


class WorkerTransfers:
    def __init__(self, base_url: Callable[[], str], headers: Callable[[], dict[str, str]],
                 post: WorkerStreamPost, get_provider: Callable[[], WorkerStreamGet], uuid_factory: Callable[[], UUID]):
        self.base_url, self.headers = base_url, headers
        self.post, self.get_provider, self.uuid_factory = post, get_provider, uuid_factory

    def windows_worker_upload_bundle_streamed(self,
        path: str,
        *,
        metadata_json: str,
        archive_path: Path,
        state: dict[str, int],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        """Stream a multipart upload to the worker while tracking sent bytes in `state`
    (no extra deps): a generator body paced by socket back-pressure gives a real
    upload progress bar. Content-Length is set so the request is not chunked."""
        base_url = self.base_url()
        if not base_url:
            raise RuntimeError(f"{WINDOWS_WORKER_BASE_URL_ENV} is not configured")
        url = f"{base_url}{path if path.startswith('/') else f'/{path}'}"
        boundary = f"----vantaline{self.uuid_factory().hex}"
        file_size = archive_path.stat().st_size
        preamble = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="metadata"\r\n\r\n'
            f"{metadata_json}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="dataset_archive"; filename="{archive_path.name}"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode("utf-8")
        epilogue = f"\r\n--{boundary}--\r\n".encode("utf-8")
        content_length = len(preamble) + file_size + len(epilogue)
        state["total"] = file_size
        state["done"] = 0

        def _body():
            yield preamble
            with archive_path.open("rb") as handle:
                while True:
                    chunk = handle.read(262144)
                    if not chunk:
                        break
                    state["done"] = int(state.get("done", 0)) + len(chunk)
                    yield chunk
            yield epilogue

        headers = {
            **self.headers(),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(content_length),
        }
        try:
            response = self.post(url, data=_body(), headers=headers, timeout=timeout_seconds)
        except requests.RequestException as exc:
            raise RuntimeError(f"Windows worker request failed: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            body = {"message": response.text[:500]}
        if response.status_code >= 400:
            detail = body.get("detail") if isinstance(body, dict) else body
            raise RuntimeError(f"Windows worker returned HTTP {response.status_code}: {detail or 'request failed'}")
        return body if isinstance(body, dict) else {"result": body}

    def windows_worker_get_json_streamed(self, path: str, *, state: dict[str, int], timeout_seconds: float) -> dict[str, Any]:
        """GET a JSON body from the worker while tracking received bytes in `state`
    (state['done']/state['total']) so download progress can be surfaced live."""
        base_url = self.base_url()
        if not base_url:
            raise RuntimeError(f"{WINDOWS_WORKER_BASE_URL_ENV} is not configured")
        url = f"{base_url}{path if path.startswith('/') else f'/{path}'}"
        buffer = io.BytesIO()
        try:
            with self.get_provider()(
                url,
                headers=self.headers(),
                timeout=timeout_seconds,
                stream=True,
            ) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"Windows worker returned HTTP {response.status_code}")
                try:
                    state["total"] = int(response.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    state["total"] = 0
                for chunk in response.iter_content(chunk_size=262144):
                    if chunk:
                        buffer.write(chunk)
                        state["done"] = buffer.tell()
        except requests.RequestException as exc:
            raise RuntimeError(f"Windows worker request failed: {exc}") from exc
        try:
            return json.loads(buffer.getvalue().decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"Windows worker returned non-JSON artifacts: {exc}") from exc
