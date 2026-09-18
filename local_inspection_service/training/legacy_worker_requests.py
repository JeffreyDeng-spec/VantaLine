"""Retired request guards and status; historical request bodies remain behind immediate rejection."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
import requests
from .executor_settings import WINDOWS_WORKER_BASE_URL_ENV

Record = dict[str, Any]


@dataclass(frozen=True)
class LegacyWorkerSettings:
    base_url: Callable[[], str]
    headers: Callable[[], dict[str, str]]
    timeout: Callable[[], float]


class LegacyWorkerHttp(Protocol):
    def __call__(self, method: str, url: str, *, headers: dict[str, str], timeout: float,
                 json: Record | None = None, data: Record | None = None,
                 files: Record | None = None) -> requests.Response: ...


class LegacyWorkerJsonCall(Protocol):
    def __call__(self, method: str, path: str, *, json_body: Record | None = None,
                 timeout_seconds: float | None = None) -> Record: ...


class LegacyWorkerRequests:
    def __init__(self, settings: LegacyWorkerSettings, http: LegacyWorkerHttp,
                 json_request: LegacyWorkerJsonCall, sleep: Callable[[float], None]):
        self.settings, self.http, self.json_request, self.sleep = settings, http, json_request, sleep

    def windows_worker_request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
        raise RuntimeError("Windows Worker execution is retired. Production training uses RunPod.")
        base_url = self.settings.base_url()
        if not base_url:
            raise RuntimeError(f"{WINDOWS_WORKER_BASE_URL_ENV} is not configured")
        url = f"{base_url}{path if path.startswith('/') else f'/{path}'}"
        try:
            response = self.http(
                method,
                url,
                json=json_body,
                headers=self.settings.headers(),
                timeout=timeout_seconds or self.settings.timeout(),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Windows worker request failed: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            body = {"message": response.text[:500]}
        if response.status_code >= 400:
            detail = body.get("detail") if isinstance(body, dict) else body
            raise RuntimeError(f"Windows worker returned HTTP {response.status_code}: {detail or 'request failed'}")
        if not isinstance(body, dict):
            return {"result": body}
        return body

    def windows_worker_form_request(self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError("Windows Worker execution is retired. Production training uses RunPod.")
        base_url = self.settings.base_url()
        if not base_url:
            raise RuntimeError(f"{WINDOWS_WORKER_BASE_URL_ENV} is not configured")
        url = f"{base_url}{path if path.startswith('/') else f'/{path}'}"
        try:
            response = self.http(
                method,
                url,
                data=data,
                files=files,
                headers=self.settings.headers(),
                timeout=timeout_seconds or self.settings.timeout(),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Windows worker request failed: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            body = {"message": response.text[:500]}
        if response.status_code >= 400:
            detail = body.get("detail") if isinstance(body, dict) else body
            raise RuntimeError(f"Windows worker returned HTTP {response.status_code}: {detail or 'request failed'}")
        if not isinstance(body, dict):
            return {"result": body}
        return body

    def windows_worker_request_with_retry(self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
        attempts: int = 3,
        backoff_seconds: float = 4.0,
    ) -> dict[str, Any]:
        raise RuntimeError("Windows Worker execution is retired. Production training uses RunPod.")
        last_exc: Exception | None = None
        for attempt in range(max(1, attempts)):
            try:
                return self.json_request(method, path, json_body=json_body, timeout_seconds=timeout_seconds)
            except RuntimeError as exc:
                last_exc = exc
                if attempt + 1 >= attempts:
                    break
                self.sleep(backoff_seconds * (attempt + 1))
        raise last_exc if last_exc else RuntimeError("Windows worker request failed")


def windows_worker_status(*, force: bool = False, probe: bool = True, include_services: bool = False) -> dict[str, Any]:
    return {
        "configured": False,
        "ok": False,
        "status": "retired",
        "message": "Windows Worker execution is retired. Production training uses RunPod.",
    }
