"""Legacy bundle submission retaining its existing fallback and cleanup boundaries."""
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import threading
from typing import Any, BinaryIO, Protocol

Record = dict[str, Any]


class WorkerBundleCleanup(Protocol):
    def cleanup(self) -> None: ...


class WorkerBundleUpdate(Protocol):
    def __call__(self, job_id: str, **updates: Any) -> Any: ...


class WorkerBundleProgress(Protocol):
    def __call__(self, job_id: str, state: dict[str, int], *, done_field: str,
                 total_field: str, status_field: str) -> tuple[threading.Event, threading.Thread]: ...


class WorkerBundleStream(Protocol):
    def __call__(self, path: str, *, metadata_json: str, archive_path: Path,
                 state: dict[str, int], timeout_seconds: float) -> Record: ...


class WorkerBundleForm(Protocol):
    def __call__(self, method: str, path: str, *, data: dict[str, str],
                 files: dict[str, tuple[str, BinaryIO, str]], timeout_seconds: float) -> Record: ...


@dataclass(frozen=True)
class WorkerBundleFiles:
    resolve: Callable[[], Callable[[Any], Path]]
    build: Callable[[Path, str], tuple[WorkerBundleCleanup, Path]]
    metadata: Callable[[str, Record, Record, Path, Path], Record]


@dataclass(frozen=True)
class WorkerBundleTransport:
    timeout: Callable[[], float]
    progress: WorkerBundleProgress
    stream: WorkerBundleStream
    form: Callable[[], WorkerBundleForm]


class WorkerBundleTimeout:
    def __init__(self, remote_timeout: Callable[[], float]):
        self.remote_timeout = remote_timeout

    def worker_training_upload_timeout_seconds(self) -> float:
        # The bundle upload travels over a cross-region Tailscale link; give it a
        # generous ceiling so a slow-but-progressing transfer is not killed.
        return max(1800.0, self.remote_timeout())


class WorkerBundleSubmission:
    def __init__(self, files: WorkerBundleFiles, transport: WorkerBundleTransport,
                 update_provider: Callable[[], WorkerBundleUpdate], clock: Callable[[], float], sleep: Callable[[float], None]):
        # Resolve once per write, before clocks and error-string arguments.
        self.files, self.transport, self.update_provider = files, transport, update_provider
        self.clock, self.sleep = clock, sleep

    def post_worker_training_bundle(self, job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
        dataset_dir = self.files.resolve()(dataset.get("dataset_dir", ""))
        temp_dir, archive_path = self.files.build(dataset_dir, job_id)
        try:
            metadata = self.files.metadata(job_id, task, dataset, dataset_dir, archive_path)
            metadata_json = json.dumps(metadata, ensure_ascii=False)
            archive_bytes = archive_path.stat().st_size
            bundle_mb = round(archive_bytes / (1024 * 1024), 1)
            self.update_provider()(
                job_id,
                progress=20,
                worker_bundle_size_mb=bundle_mb,
                worker_upload_status="running",
                worker_upload_started_at=int(self.clock()),
                worker_upload_total_bytes=archive_bytes,
                worker_upload_sent_bytes=0,
                note=f"已压缩 HK 样本集（{bundle_mb}MB，仅训练所需图像），正在上传到 Windows Worker。",
            )
            timeout_seconds = self.transport.timeout()
            last_error: Exception | None = None
            for attempt in range(1, 3):
                upload_state: dict[str, int] = {"done": 0, "total": archive_bytes}
                stop_event, progress_thread = self.transport.progress(
                    job_id,
                    upload_state,
                    done_field="worker_upload_sent_bytes",
                    total_field="worker_upload_total_bytes",
                    status_field="worker_upload_status",
                )
                try:
                    if attempt == 1:
                        body = self.transport.stream(
                            "/training/jobs/import",
                            metadata_json=metadata_json,
                            archive_path=archive_path,
                            state=upload_state,
                            timeout_seconds=timeout_seconds,
                        )
                    else:
                        # Fallback path: proven (non-streaming) form upload for reliability.
                        with archive_path.open("rb") as handle:
                            body = self.transport.form()(
                                "POST",
                                "/training/jobs/import",
                                data={"metadata": metadata_json},
                                files={"dataset_archive": (archive_path.name, handle, "application/zip")},
                                timeout_seconds=timeout_seconds,
                            )
                    self.update_provider()(
                        job_id,
                        worker_upload_status="completed",
                        worker_upload_sent_bytes=archive_bytes,
                        worker_upload_total_bytes=archive_bytes,
                        worker_upload_completed_at=int(self.clock()),
                    )
                    return body
                except RuntimeError as exc:
                    last_error = exc
                    if attempt >= 2:
                        self.update_provider()(job_id, worker_upload_status="failed")
                        break
                    self.update_provider()(
                        job_id,
                        progress=20,
                        worker_upload_status="running",
                        note=f"上传到 Windows Worker 失败（第 {attempt} 次），正在重试：{str(exc)[:160]}",
                    )
                    self.sleep(5)
                finally:
                    stop_event.set()
                    progress_thread.join(timeout=2.0)
            raise last_error if last_error else RuntimeError("Windows worker bundle upload failed")
        finally:
            temp_dir.cleanup()
