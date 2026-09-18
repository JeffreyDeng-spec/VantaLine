"""Training task assembly and its existing save/register/start publication order."""
from collections.abc import Callable
from dataclasses import dataclass
import threading
import time
from typing import Any, Protocol
import uuid
from ..schemas.training import TrainingStartRequest

Record = dict[str, Any]


class TrainingEstimate(Protocol):
    def __call__(self, sample_count: int, *, include_training: bool, include_generation: bool,
                 epochs: int, image_size: int, selected_count: int, train_mode: str) -> Record: ...


class TrainingThreadFactory(Protocol):
    def __call__(self, *, target: Callable[[str], None], args: tuple[str], name: str, daemon: bool) -> threading.Thread: ...


@dataclass(frozen=True)
class TrainingSubmissionPolicy:
    estimate: Callable[[], TrainingEstimate]
    uses_ocr: Callable[[Record], bool]


@dataclass(frozen=True)
class TrainingSubmissionIdentity:
    user: Callable[[], Record | None]
    owner: Callable[[], Record]
    background: Callable[[], Callable[[str | None, Record | None], str | None]]


@dataclass(frozen=True)
class TrainingSubmissionRecords:
    save: Callable[[Record], None]
    public: Callable[[Record], Record]


@dataclass(frozen=True)
class TrainingSubmissionThreads:
    target: Callable[[], Callable[[str], None]]
    create: TrainingThreadFactory
    records: Callable[[], dict[str, threading.Thread]]


class TrainingSubmission:
    def __init__(self, policy: TrainingSubmissionPolicy, identity: TrainingSubmissionIdentity,
                 records: TrainingSubmissionRecords, threads: TrainingSubmissionThreads):
        self.policy, self.identity, self.records, self.threads = policy, identity, records, threads

    def enqueue_training_task(self,
        request: TrainingStartRequest,
        selected: list[dict[str, Any]],
        action: str,
        dataset: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sample_count = max(1, min(20000, int(dataset.get("sample_count") if dataset else request.sample_count)))
        epochs = max(1, min(500, int(request.epochs)))
        image_size = max(320, min(1280, int(request.image_size)))
        estimate = self.policy.estimate()(
            sample_count,
            include_training=action == "train_model",
            include_generation=action == "generate_samples" or (action == "train_model" and not dataset),
            epochs=epochs,
            image_size=image_size,
            selected_count=len(selected),
            train_mode=request.train_mode,
        )
        job_id = f"{'train' if action == 'train_model' else 'samples'}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        task = {
            "job_id": job_id,
            "task_id": job_id,
            "candidate_id": job_id,
            "candidate_name": "训练模型" if action == "train_model" else "生成训练样本",
            "label": "训练模型" if action == "train_model" else "生成训练样本",
            "queue_kind": "training",
            "action": action,
            "status": "queued",
            "progress": 0,
            "created_at": int(time.time()),
            "selected_accessory_ids": [item["id"] for item in selected],
            "required_accessory_counts": {str(item["id"]): 1 for item in selected},
            "accessory_class_map": {str(idx): str(item["id"]) for idx, item in enumerate(selected)},
            "class_accessory_map": {str(item["id"]): idx for idx, item in enumerate(selected)},
            "ocr_accessory_ids": [str(item["id"]) for item in selected if self.policy.uses_ocr(item)],
            "model_variant": request.train_mode,
            "sample_count": sample_count,
            "mode": request.train_mode,
            "epochs": epochs,
            "image_size": image_size,
            "background_set_id": self.identity.background()(request.background_set_id, self.identity.user()),
            "approved_preview_id": request.approved_preview_id,
            "preview_pose_family_policy": "auto",
            "note": "任务已加入队列。",
            **self.identity.owner(),
            **estimate,
        }
        pipeline_task_id = str(request.pipeline_task_id or "").strip()
        pipeline_task_name = str(request.pipeline_task_name or "").strip()
        if pipeline_task_id:
            task["pipeline_task_id"] = pipeline_task_id[:128]
        if pipeline_task_name:
            task["pipeline_task_name"] = pipeline_task_name[:160]
        if dataset:
            task.update(
                {
                    "source_dataset_id": dataset["id"],
                    "dataset_dir": dataset.get("dataset_dir", ""),
                    "dataset_yaml": dataset.get("dataset_yaml", ""),
                    "manifest_path": dataset.get("manifest_path", ""),
                    "label": dataset.get("display_name") or task["label"],
                    "candidate_name": dataset.get("display_name") or task["candidate_name"],
                }
            )
        self.records.save(task)
        thread = self.threads.create(target=self.threads.target(), args=(job_id,), name=f"training-task-{job_id}", daemon=True)
        self.threads.records()[job_id] = thread
        thread.start()
        return self.records.public(task)
