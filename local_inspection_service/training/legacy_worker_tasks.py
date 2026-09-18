"""Retired task settlement, retaining the original early return and historical submission bodies."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from .legacy_worker_requests import LegacyWorkerJsonCall

Record = dict[str, Any]


class LegacyTaskUpdate(Protocol):
    def __call__(self, job_id: str, **updates: Any) -> Any: ...


@dataclass(frozen=True)
class LegacyWorkerTaskPorts:
    base_url: Callable[[], str]
    mask_url: Callable[[Any], str]
    request: LegacyWorkerJsonCall
    payload: Callable[[Record], Record]
    bundle: Callable[[str, Record, Record], Record]
    sanitize: Callable[[Any], Any]


class LegacyWorkerTasks:
    def __init__(self, update_provider: Callable[[], LegacyTaskUpdate], clock: Callable[[], float],
                 legacy: LegacyWorkerTaskPorts):
        self.update_provider, self.clock, self.legacy = update_provider, clock, legacy

    def run_worker_dataset_generation_task(self, job_id: str, task: dict[str, Any]) -> None:
        self.update_provider()(
            job_id,
            status="failed",
            progress=100,
            completed_at=int(self.clock()),
            training_executor="runpod",
            error="Windows Worker dataset generation is retired. Production training uses RunPod.",
            note="Windows Worker 已退役；请使用 RunPod 训练链路。",
        )
        return
        self.update_provider()(
            job_id,
            status="running",
            progress=12,
            training_executor="worker",
            windows_worker_endpoint=self.legacy.mask_url(self.legacy.base_url()),
            note="正在提交样本生成任务到 Windows Worker。",
        )
        body = self.legacy.request("POST", "/training/datasets/generate", json_body=self.legacy.payload(task))
        worker_job_id = str(body.get("job_id") or body.get("task_id") or body.get("id") or "").strip()
        self.update_provider()(
            job_id,
            status="running",
            progress=30,
            remote_training_status=str(body.get("status") or "submitted"),
            remote_training_job_id=worker_job_id,
            remote_training_response={key: value for key, value in body.items() if key not in {"api_key", "token", "secret"}},
            note="样本生成任务已提交到 Windows Worker，等待远端处理。",
        )

    def run_worker_training_task(self, job_id: str, task: dict[str, Any], dataset: dict[str, Any] | None = None) -> None:
        self.update_provider()(
            job_id,
            status="failed",
            progress=100,
            completed_at=int(self.clock()),
            training_executor="runpod",
            error="Windows Worker training is retired. Production training uses RunPod.",
            note="Windows Worker 已退役；请使用 RunPod 训练链路。",
        )
        return
        self.update_provider()(
            job_id,
            status="running",
            progress=12,
            training_executor="worker",
            windows_worker_endpoint=self.legacy.mask_url(self.legacy.base_url()),
            worker_transfer_required=True,
            note="正在提交训练任务到 Windows Worker。",
        )
        if dataset and dataset.get("dataset_yaml"):
            self.update_provider()(
                job_id,
                progress=18,
                note="正在打包 HK 样本集并传输到 Windows Worker。",
                **dataset,
            )
            body = self.legacy.bundle(job_id, task, dataset)
        else:
            body = self.legacy.request("POST", "/training/jobs", json_body=self.legacy.payload(task))
        worker_job_id = str(body.get("job_id") or body.get("task_id") or body.get("id") or "").strip()
        self.update_provider()(
            job_id,
            status="running",
            progress=30,
            remote_training_status=str(body.get("status") or "submitted"),
            remote_training_job_id=worker_job_id,
            worker_bundle_transfer=self.legacy.sanitize(body.get("transfer") or body.get("bundle") or {}),
            remote_training_response={key: value for key, value in body.items() if key not in {"api_key", "token", "secret"}},
            note="训练任务和样本集已提交到 Windows Worker，等待远端处理。" if dataset else "训练任务已提交到 Windows Worker，等待远端处理。",
        )
