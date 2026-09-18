"""Read-only retired task projection; historical refresh code remains after its early return."""
from collections.abc import Callable, Collection
from dataclasses import dataclass
import threading
from typing import Any, Protocol
from urllib.parse import quote
from .legacy_worker_requests import LegacyWorkerJsonCall
from .legacy_worker_tasks import LegacyTaskUpdate

Record = dict[str, Any]


class LegacyRefreshProgress(Protocol):
    def __call__(self, job_id: str, state: dict[str, int], *, done_field: str,
                 total_field: str, status_field: str) -> tuple[threading.Event, threading.Thread]: ...


class LegacyRefreshDownload(Protocol):
    def __call__(self, path: str, *, state: dict[str, int], timeout_seconds: float) -> Record: ...


@dataclass(frozen=True)
class LegacyRefreshRecords:
    public: Callable[[Record], Record]
    update_provider: Callable[[], LegacyTaskUpdate]
    sanitize: Callable[[Any], Any]
    active_statuses: Callable[[], Collection[str]]


@dataclass(frozen=True)
class LegacyRefreshTransfer:
    request: LegacyWorkerJsonCall
    progress: LegacyRefreshProgress
    download: LegacyRefreshDownload
    timeout: Callable[[], float]


@dataclass(frozen=True)
class LegacyRefreshArtifacts:
    summary: Callable[[Record], Record]
    import_result: Callable[[Record, Record], Record]


class LegacyWorkerRefresh:
    def __init__(self, records: LegacyRefreshRecords, transfer: LegacyRefreshTransfer,
                 artifacts: LegacyRefreshArtifacts, clock: Callable[[], float]):
        self.records, self.transfer, self.artifacts, self.clock = records, transfer, artifacts, clock

    def refresh_worker_training_task(self, task: dict[str, Any], *, include_artifacts: bool = False) -> dict[str, Any]:
        public = self.records.public(task)
        public["executor_retired"] = True
        public["remote_refresh_retired"] = True
        public.setdefault("note", "历史 Windows-worker 训练记录仅保留只读展示；生产训练执行已切换为 RunPod。")
        return public
        remote_job_id = str(task.get("remote_training_job_id") or "").strip()
        if not remote_job_id:
            return self.records.public(task)
        job_id = str(task.get("job_id") or task.get("task_id") or "")
        already_imported = bool(task.get("worker_artifacts_imported_at"))
        updates: dict[str, Any] = {}
        try:
            body = self.transfer.request("GET", f"/training/jobs/{quote(remote_job_id, safe='')}", timeout_seconds=20)
            remote_job = body.get("job") if isinstance(body.get("job"), dict) else body
            remote_status = str(remote_job.get("status") or body.get("status") or "").strip()
            remote_progress = remote_job.get("progress") if isinstance(remote_job, dict) else None
            updates.update(
                {
                    "remote_training_status": remote_status or task.get("remote_training_status") or "submitted",
                    "remote_training_job": self.records.sanitize(remote_job),
                    "remote_training_poll_error": "",
                }
            )
            if isinstance(remote_progress, (int, float)):
                updates["remote_training_progress"] = remote_progress
            if remote_status:
                status_l = remote_status.lower()
                if status_l == "completed":
                    updates.update(
                        {
                            "status": "completed",
                            "progress": 100,
                            "completed_at": int(self.clock()),
                            "note": "Windows Worker 任务已完成。",
                        }
                    )
                elif status_l in {"failed", "cancelled", "canceled", "stopped"}:
                    updates.update(
                        {
                            "status": "failed",
                            "progress": 100,
                            "completed_at": int(self.clock()),
                            "error": str(remote_job.get("error") or remote_job.get("note") or remote_status),
                            "note": f"Windows Worker 任务结束：{remote_status}。",
                        }
                    )
                elif str(task.get("status")) in self.records.active_statuses():
                    updates.update(
                        {
                            "status": "running",
                            "progress": max(int(task.get("progress") or 0), 30),
                            "note": f"Windows Worker 任务状态：{remote_status}。",
                        }
                    )
            # Only fetch artifacts (a potentially large base64 model payload) once the
            # remote job has actually completed AND the model has not been imported yet.
            # Gating on "completed" (not merely include_artifacts) prevents pointless
            # downloads + a misleading model-return progress bar while training runs.
            if remote_status.lower() == "completed" and not already_imported:
                download_state: dict[str, int] = {"done": 0, "total": 0}
                stop_event, progress_thread = self.transfer.progress(
                    job_id,
                    download_state,
                    done_field="worker_download_received_bytes",
                    total_field="worker_download_total_bytes",
                    status_field="worker_download_status",
                )
                self.records.update_provider()(
                    job_id,
                    worker_download_status="running",
                    worker_download_started_at=int(self.clock()),
                    worker_download_received_bytes=0,
                    note="Windows Worker 训练完成，正在回传模型到 HK 服务器。",
                )
                try:
                    artifacts = self.transfer.download(
                        f"/training/jobs/{quote(remote_job_id, safe='')}/artifacts",
                        state=download_state,
                        timeout_seconds=self.transfer.timeout(),
                    )
                finally:
                    stop_event.set()
                    progress_thread.join(timeout=2.0)
                received_total = int(download_state.get("done") or 0)
                updates["remote_training_artifacts"] = {
                    "models": [
                        self.artifacts.summary(item)
                        for item in artifacts.get("models", [])
                        if isinstance(item, dict)
                    ],
                    "datasets": [
                        self.artifacts.summary(item)
                        for item in artifacts.get("datasets", [])
                        if isinstance(item, dict)
                    ],
                }
                updates.update(
                    {
                        "worker_download_status": "completed",
                        "worker_download_completed_at": int(self.clock()),
                        "worker_download_received_bytes": received_total,
                        "worker_download_total_bytes": int(download_state.get("total") or received_total),
                    }
                )
                if remote_status.lower() == "completed":
                    import_result = self.artifacts.import_result(task, artifacts)
                    if import_result:
                        updates.update(import_result)
                    elif not task.get("worker_artifacts_imported_at"):
                        attempts = int(task.get("worker_artifact_import_attempts") or 0) + 1
                        updates["worker_artifact_import_attempts"] = attempts
                        if attempts >= 5:
                            updates["worker_artifacts_imported_at"] = int(self.clock())
                            updates["worker_artifact_import_error"] = (
                                "Worker reported completed but returned no model artifact after 5 attempts."
                            )
        except Exception as exc:
            updates["remote_training_poll_error"] = str(exc)
            if not already_imported:
                updates["worker_download_status"] = "failed"
        if updates:
            task = self.records.update_provider()(str(task.get("job_id") or task.get("task_id")), **updates)
        return self.records.public(task)
