"""Legacy remote training submission with one request and the original cleanup/error boundaries."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, BinaryIO, Protocol
from .executor_settings import REMOTE_TRAINING_ENDPOINT_ENV, REMOTE_TRAINING_API_KEY_ENV

Record = dict[str, Any]


class RemoteArchiveCleanup(Protocol):
    def cleanup(self) -> None: ...


class RemoteTrainingResponse(Protocol):
    text: str
    def raise_for_status(self) -> None: ...
    def json(self) -> Any: ...


class RemoteTrainingPost(Protocol):
    def __call__(self, endpoint: str, *, data: dict[str, str], files: dict[str, tuple[str, BinaryIO, str]],
                 headers: dict[str, str], timeout: float) -> RemoteTrainingResponse: ...


class RemoteTrainingUpdate(Protocol):
    def __call__(self, job_id: str, **updates: Any) -> Any: ...


@dataclass(frozen=True)
class RemoteTrainingSettings:
    endpoint: Callable[[], str]
    mask: Callable[[str], str]
    environment: Callable[[], Mapping[str, str]]
    timeout: Callable[[], float]


@dataclass(frozen=True)
class RemoteTrainingPaths:
    resolve: Callable[[], Callable[[Any], Path]]
    package: Callable[[Path, str], tuple[RemoteArchiveCleanup, Path]]


class RemoteTraining:
    def __init__(self, settings: RemoteTrainingSettings, paths: RemoteTrainingPaths,
                 update_provider: Callable[[], RemoteTrainingUpdate], post: Callable[[], RemoteTrainingPost], clock: Callable[[], float]):
        # Capture the actual callee before evaluating argument callbacks.
        self.settings, self.paths, self.update_provider = settings, paths, update_provider
        self.post, self.clock = post, clock

    def run_remote_training_task(self, job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> None:
        endpoint = self.settings.endpoint()
        if not endpoint:
            raise RuntimeError(
                "Remote training executor is enabled but no private Windows training endpoint is configured. "
                f"Set {REMOTE_TRAINING_ENDPOINT_ENV} to a URL reachable only over Tailscale/reverse tunnel/VPN, "
                f"and set {REMOTE_TRAINING_API_KEY_ENV} if that service requires a bearer token."
            )
        dataset_dir = self.paths.resolve()(dataset.get("dataset_dir", ""))
        self.update_provider()(
            job_id,
            status="running",
            progress=78,
            note="样本已生成，正在提交到 Windows 远程训练端点。",
            training_executor="remote",
            remote_training_endpoint=self.settings.mask(endpoint),
            **dataset,
        )
        temp_dir, archive_path = self.paths.package(dataset_dir, job_id)
        headers: dict[str, str] = {}
        api_key = self.settings.environment().get(REMOTE_TRAINING_API_KEY_ENV, "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        metadata = {
            "job_id": job_id,
            "train_mode": task.get("train_mode") or task.get("mode") or "yolo_ocr",
            "epochs": max(1, min(500, int(task.get("epochs") or 1))),
            "image_size": max(320, min(1280, int(task.get("image_size") or 640))),
            "dataset_yaml": str(dataset.get("dataset_yaml") or ""),
            "manifest_path": str(dataset.get("manifest_path") or ""),
            "source": "vantaline_cloud",
        }
        try:
            with archive_path.open("rb") as handle:
                response = self.post()(
                    endpoint,
                    data={"metadata": json.dumps(metadata, ensure_ascii=False)},
                    files={"dataset_archive": (archive_path.name, handle, "application/zip")},
                    headers=headers,
                    timeout=self.settings.timeout(),
                )
            response.raise_for_status()
            try:
                body = response.json()
            except ValueError:
                body = {"status": "submitted", "message": response.text[:300]}
            if not isinstance(body, dict):
                body = {"status": "submitted", "message": str(body)[:300]}
            remote_status = str(body.get("status") or body.get("state") or "submitted").strip().lower()
            remote_job_id = str(body.get("job_id") or body.get("id") or "").strip()
            completed = remote_status in {"completed", "succeeded", "success", "done"}
            self.update_provider()(
                job_id,
                status="completed" if completed else "running",
                progress=100 if completed else 90,
                completed_at=int(self.clock()) if completed else 0,
                remote_training_status=remote_status,
                remote_training_job_id=remote_job_id,
                remote_training_response={key: value for key, value in body.items() if key not in {"api_key", "token", "secret"}},
                note="Windows 远程训练已完成。" if completed else "训练任务已提交到 Windows 远程端点，等待远程训练服务处理。",
            )
        finally:
            temp_dir.cleanup()
