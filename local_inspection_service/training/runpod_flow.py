"""Existing RunPod orchestration and polling with no transport or record ownership."""
from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any, Protocol
from urllib.parse import quote
from .runpod_submission import RunPodRequest

Record = dict[str, Any]


class RunPodTaskUpdate(Protocol):
    def __call__(self, job_id: str, **values: Any) -> Record: ...


@dataclass(frozen=True)
class RunPodFlowSettings:
    endpoint: Callable[[], str]
    timeout: Callable[[], int]
    ttl: Callable[[], int]
    poll: Callable[[], float]


@dataclass(frozen=True)
class RunPodFlowRecords:
    # Resolve at each call site before any argument callbacks.
    update_provider: Callable[[], RunPodTaskUpdate]
    sync: Callable[[str], None]
    warmup: Callable[[], Callable[[str, list[str]], None]]


@dataclass(frozen=True)
class RunPodFlowInputs:
    archive: Callable[[str, Record, Record], Record]
    payload: Callable[[str, Record, Record], Record]
    submit: Callable[[Record], Record]


@dataclass(frozen=True)
class RunPodFlowResults:
    request: Callable[[], RunPodRequest]
    summary: Callable[[Any], Any]
    extract: Callable[[Record], Record]
    import_artifacts: Callable[[], Callable[[Record, Record], Record]]
    terminal: Callable[[], Callable[[str], bool]]
    bound_text: Callable[[], Callable[[Any, int], str]]


class RunPodFlow:
    def __init__(self, settings: RunPodFlowSettings, records: RunPodFlowRecords,
                 inputs: RunPodFlowInputs, results: RunPodFlowResults):
        self.settings, self.records = settings, records
        self.inputs, self.results = inputs, results

    def run_runpod_training_task(self, job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> None:
        endpoint_id = self.settings.endpoint()
        self.records.update_provider()(
            job_id,
            status="running",
            progress=78,
            training_executor="runpod",
            runpod_endpoint_id=endpoint_id,
            remote_training_status="preparing_dataset",
            note="样本已生成，正在准备 RunPod YOLO worker 训练数据包。",
            **dataset,
        )
        archive = self.inputs.archive(job_id, task, dataset)
        payload = self.inputs.payload(job_id, task, archive)
        submission = self.inputs.submit(payload)
        runpod_job_id = str(submission.get("id") or submission.get("job_id") or "").strip()
        if not runpod_job_id:
            raise RuntimeError("RunPod did not return a job id")
        self.records.update_provider()(
            job_id,
            status="running",
            progress=82,
            training_executor="runpod",
            remote_training_job_id=runpod_job_id,
            runpod_job_id=runpod_job_id,
            remote_training_status=str(submission.get("status") or "IN_QUEUE"),
            remote_training_response=self.results.summary(submission),
            note="训练任务已提交到 RunPod YOLO worker，等待远端处理。",
        )
        started = time.monotonic()
        timeout_seconds = self.settings.timeout() + self.settings.ttl()
        poll_interval = self.settings.poll()
        last_status_body: dict[str, Any] = submission
        while True:
            if time.monotonic() - started > timeout_seconds:
                raise RuntimeError("RunPod training status polling exceeded configured timeout")
            time.sleep(poll_interval)
            status_body = self.results.request()("GET", f"status/{quote(runpod_job_id, safe='')}")
            last_status_body = status_body
            remote_status = str(status_body.get("status") or "").strip().upper()
            progress = 86 if remote_status == "IN_QUEUE" else 92 if remote_status == "IN_PROGRESS" else 96
            self.records.update_provider()(
                job_id,
                status="running" if not self.results.terminal()(remote_status) else str(task.get("status") or "running"),
                progress=progress,
                remote_training_status=remote_status or "UNKNOWN",
                remote_training_response=self.results.summary(status_body),
                note=f"RunPod YOLO worker 状态：{remote_status or 'UNKNOWN'}。",
            )
            if remote_status == "COMPLETED":
                output = self.results.extract(status_body)
                import_updates = self.results.import_artifacts()({**task, "job_id": job_id, "runpod_job_id": runpod_job_id}, output)
                self.records.update_provider()(
                    job_id,
                    status="completed",
                    progress=100,
                    completed_at=int(time.time()),
                    remote_training_status=remote_status,
                    remote_training_response=self.results.summary(status_body),
                    runpod_training_output=self.results.summary(output),
                    current_epoch=max(1, min(500, int(task.get("epochs") or 1))),
                    total_epochs=max(1, min(500, int(task.get("epochs") or 1))),
                    note="RunPod YOLO worker 训练完成，模型已导入训练库。",
                    **import_updates,
                )
                self.records.sync(job_id)
                variant = str(task.get("model_variant") or task.get("mode") or "yolo")
                variant = variant if variant in {"yolo", "yolo_ocr"} else "yolo"
                self.records.warmup()("training_completed", [f"trained_{job_id}__{variant}"])
                return
            if remote_status in {"FAILED", "CANCELLED", "CANCELED", "TIMED_OUT"}:
                detail = (status_body.get("error") or status_body.get("message") or status_body.get("output") or remote_status)
                raise RuntimeError(f"RunPod training ended with {remote_status}: {self.results.bound_text()(str(detail), 300)}")
            if not remote_status and self.results.terminal()(str(last_status_body.get("status") or "")):
                raise RuntimeError("RunPod training ended without a readable status")
