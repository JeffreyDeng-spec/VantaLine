"""RunPod HTTP adaptation and response projection with an explicit transport."""
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from typing import Any, Protocol
import requests


class RunPodTransport(Protocol):
    def __call__(self, method: str, url: str, *, json: dict[str, Any] | None,
                 headers: dict[str, str], timeout: float) -> requests.Response: ...


@dataclass(frozen=True)
class RunPodRequestSettings:
    url: Callable[[str], str]
    authorization: Callable[[], list[str]]
    timeout: Callable[[], float]


class RunPodClient:
    def __init__(self, settings: RunPodRequestSettings, request: Callable[[], RunPodTransport], bound_text: Callable[[], Callable[[Any, int], str]]):
        self.settings, self.request, self.bound_text = settings, request, bound_text

    def runpod_yolo_http_request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
        url = self.settings.url(path)
        auth_values = self.settings.authorization()
        last_body: dict[str, Any] | None = None
        last_status = 0
        for index, auth_value in enumerate(auth_values):
            headers = {"accept": "application/json", "authorization": auth_value}
            if json_body is not None:
                headers["content-type"] = "application/json"
            try:
                response = self.request()(
                    method,
                    url,
                    json=json_body,
                    headers=headers,
                    timeout=timeout_seconds or self.settings.timeout(),
                )
            except requests.RequestException as exc:
                raise RuntimeError(f"RunPod request failed: {type(exc).__name__}") from exc
            last_status = int(response.status_code)
            try:
                body = response.json()
            except ValueError:
                body = {"message": response.text[:500]}
            last_body = body if isinstance(body, dict) else {"result": body}
            if response.status_code in {401, 403} and index + 1 < len(auth_values):
                continue
            if response.status_code >= 400:
                detail = last_body.get("error") or last_body.get("detail") or last_body.get("message") or "request failed"
                raise RuntimeError(f"RunPod returned HTTP {response.status_code}: {self.bound_text()(str(detail), 240)}")
            return last_body
        detail = (last_body or {}).get("error") or (last_body or {}).get("detail") or (last_body or {}).get("message") or "request failed"
        raise RuntimeError(f"RunPod returned HTTP {last_status}: {self.bound_text()(str(detail), 240)}")

    def runpod_public_response_summary(self, value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                key_l = str(key).lower()
                if key_l in {"artifact_b64", "dataset_url", "base_model_url", "artifact_upload_url", "authorization", "api_key", "token", "secret"}:
                    if isinstance(item, str):
                        result[key] = f"<redacted:{len(item)} chars>"
                    else:
                        result[key] = "<redacted>"
                    continue
                result[key] = self.runpod_public_response_summary(item)
            return result
        if isinstance(value, list):
            return [self.runpod_public_response_summary(item) for item in value[:80]]
        if isinstance(value, str):
            return self.bound_text()(value, 1200)
        return value

def runpod_dataset_token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
