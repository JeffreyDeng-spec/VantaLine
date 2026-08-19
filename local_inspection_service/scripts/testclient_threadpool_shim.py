"""Compatibility shim for smoke tests that exercise sync FastAPI endpoints.

The managed Codex sandbox can hang in ``anyio.to_thread.run_sync`` with the
installed Starlette/FastAPI stack. Smoke tests use this opt-in shim so
TestClient/ASGITransport can still dispatch synchronous endpoint functions.
Production runtime code does not import this module.
"""

from __future__ import annotations

import asyncio
import functools
import json
import secrets
from http.cookies import SimpleCookie
from typing import Any, Callable, TypeVar
from urllib.parse import urlencode, urlsplit


T = TypeVar("T")


async def _run_in_asyncio_threadpool(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    # Smoke scripts are single-process request/response checks. Calling sync
    # endpoints inline avoids the managed sandbox's broken anyio thread worker
    # path while preserving endpoint behavior and exception propagation.
    return functools.partial(func, *args, **kwargs)()


async def _run_sync_inline(
    func: Callable[..., T],
    *args: Any,
    abandon_on_cancel: bool = False,
    cancellable: bool | None = None,
    limiter: Any = None,
) -> T:
    return func(*args)


def install() -> None:
    import anyio.to_thread
    import fastapi.concurrency
    import fastapi.dependencies.utils
    import fastapi.routing
    import starlette._exception_handler
    import starlette.background
    import starlette.concurrency
    import starlette.datastructures
    import starlette.endpoints
    import starlette.middleware.errors
    import starlette.routing

    modules = (
        fastapi.concurrency,
        fastapi.dependencies.utils,
        fastapi.routing,
        starlette._exception_handler,
        starlette.background,
        starlette.concurrency,
        starlette.datastructures,
        starlette.endpoints,
        starlette.middleware.errors,
        starlette.routing,
    )
    for module in modules:
        if hasattr(module, "run_in_threadpool"):
            module.run_in_threadpool = _run_in_asyncio_threadpool
    anyio.to_thread.run_sync = _run_sync_inline


class SmokeASGIResponse:
    def __init__(self, *, status_code: int, headers: list[tuple[bytes, bytes]], content: bytes) -> None:
        self.status_code = status_code
        self.content = content
        self.headers: dict[str, str] = {}
        for key, value in headers:
            text_key = key.decode("latin-1").lower()
            text_value = value.decode("latin-1")
            if text_key in self.headers:
                self.headers[text_key] = f"{self.headers[text_key]}, {text_value}"
            else:
                self.headers[text_key] = text_value

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


class SmokeASGIClient:
    def __init__(self, app: Any, base_url: str = "http://testserver", **_: Any) -> None:
        self.app = app
        self.base_url = base_url
        self.cookies: dict[str, str] = {}

    def __enter__(self) -> "SmokeASGIClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: dict[str, Any] | None = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
        content: bytes | str | None = None,
        **_: Any,
    ) -> SmokeASGIResponse:
        body, request_headers = self._build_body_headers(json=json, data=data, files=files, content=content)
        merged_headers = {**request_headers, **(headers or {})}
        response = asyncio.run(self._request_async(method.upper(), url, params=params, body=body, headers=merged_headers))
        self._store_response_cookies(response)
        return response

    def get(self, url: str, **kwargs: Any) -> SmokeASGIResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> SmokeASGIResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> SmokeASGIResponse:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> SmokeASGIResponse:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> SmokeASGIResponse:
        return self.request("DELETE", url, **kwargs)

    async def _request_async(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None,
        body: bytes,
        headers: dict[str, str],
    ) -> SmokeASGIResponse:
        parsed_base = urlsplit(self.base_url)
        parsed_url = urlsplit(url)
        scheme = parsed_url.scheme or parsed_base.scheme or "http"
        host = parsed_url.hostname or parsed_base.hostname or "testserver"
        port = parsed_url.port or parsed_base.port or (443 if scheme == "https" else 80)
        path = parsed_url.path or "/"
        query = parsed_url.query
        if params:
            extra_query = urlencode(params, doseq=True)
            query = f"{query}&{extra_query}" if query else extra_query
        header_items = [(b"host", host.encode("latin-1"))]
        if self.cookies:
            header_items.append((b"cookie", "; ".join(f"{key}={value}" for key, value in self.cookies.items()).encode("latin-1")))
        header_items.extend((key.lower().encode("latin-1"), str(value).encode("latin-1")) for key, value in headers.items())
        messages: list[dict[str, Any]] = []
        response_complete = asyncio.Event()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": scheme,
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query.encode("utf-8"),
            "headers": header_items,
            "client": ("testclient", 50000),
            "server": (host, port),
            "root_path": "",
            "state": {},
        }
        sent = False

        async def receive() -> dict[str, Any]:
            nonlocal sent
            if sent:
                if not response_complete.is_set():
                    await response_complete.wait()
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)
            if message.get("type") == "http.response.body" and not message.get("more_body", False):
                response_complete.set()

        await self.app(scope, receive, send)
        status_code = 500
        response_headers: list[tuple[bytes, bytes]] = []
        chunks: list[bytes] = []
        for message in messages:
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 500)
                response_headers = list(message.get("headers") or [])
            elif message.get("type") == "http.response.body":
                chunks.append(message.get("body") or b"")
        return SmokeASGIResponse(status_code=status_code, headers=response_headers, content=b"".join(chunks))

    def _build_body_headers(
        self,
        *,
        json: Any,
        data: dict[str, Any] | None,
        files: Any,
        content: bytes | str | None,
    ) -> tuple[bytes, dict[str, str]]:
        if json is not None:
            return (
                __import__("json").dumps(json, ensure_ascii=False).encode("utf-8"),
                {"content-type": "application/json"},
            )
        if files:
            return self._multipart_body(data or {}, files)
        if data is not None:
            return urlencode(data, doseq=True).encode("utf-8"), {"content-type": "application/x-www-form-urlencoded"}
        if isinstance(content, str):
            return content.encode("utf-8"), {}
        return content or b"", {}

    def _multipart_body(self, data: dict[str, Any], files: Any) -> tuple[bytes, dict[str, str]]:
        boundary = f"vantaline-smoke-{secrets.token_hex(12)}"
        parts: list[bytes] = []
        for key, value in data.items():
            values = value if isinstance(value, list) else [value]
            for item in values:
                parts.append(
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{item}\r\n".encode("utf-8")
                )
        file_items = files.items() if isinstance(files, dict) else files
        for field_name, file_info in file_items:
            filename, file_content, content_type = self._normalize_file_info(file_info)
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"{field_name}\"; filename=\"{filename}\"\r\n"
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8")
                + file_content
                + b"\r\n"
            )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(parts), {"content-type": f"multipart/form-data; boundary={boundary}"}

    @staticmethod
    def _normalize_file_info(file_info: Any) -> tuple[str, bytes, str]:
        if isinstance(file_info, tuple):
            filename = str(file_info[0])
            file_content = file_info[1]
            content_type = str(file_info[2]) if len(file_info) > 2 else "application/octet-stream"
        else:
            filename = "upload"
            file_content = file_info
            content_type = "application/octet-stream"
        if hasattr(file_content, "read"):
            file_content = file_content.read()
        if isinstance(file_content, str):
            file_content = file_content.encode("utf-8")
        return filename, bytes(file_content), content_type

    def _store_response_cookies(self, response: SmokeASGIResponse) -> None:
        raw_cookie = response.headers.get("set-cookie")
        if not raw_cookie:
            return
        cookie = SimpleCookie()
        cookie.load(raw_cookie)
        for key, morsel in cookie.items():
            if morsel["max-age"] == "0" or not morsel.value:
                self.cookies.pop(key, None)
            else:
                self.cookies[key] = morsel.value
