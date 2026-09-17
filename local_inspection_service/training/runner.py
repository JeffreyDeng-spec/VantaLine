"""Bound training execution orchestration; transports and local processes are explicit ports."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Any, Protocol, TextIO
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import pinned

Record = dict[str, Any]


class UpdateTrainingTask(Protocol):
    def __call__(self, job_id: str, **values: Any) -> Record: ...


class TrainingProcess(Protocol):
    pid: int
    returncode: int | None
    def poll(self) -> int | None: ...


class StartTrainingProcess(Protocol):
    def __call__(self, command: list[str], *, cwd: str, stdout: TextIO, stderr: int, text: bool) -> TrainingProcess: ...


@dataclass(frozen=True)
class TrainingRunnerRecords:
    find: Callable[[str], Record | None]
    path: Callable[[str], Path]
    load: Callable[[], Callable[[Path], Record | None]]
    # Resolve at each call site before any argument callbacks.
    update_provider: Callable[[], UpdateTrainingTask]
    sync: Callable[[str], None]


@dataclass(frozen=True)
class TrainingRunnerPaths:
    resolve: Callable[[], Callable[[str], Path]]
    tasks: Callable[[], Path]
    app: Callable[[], Path]
    output: Callable[[], Callable[[str, str], Path]]


@dataclass(frozen=True)
class TrainingDatasetExecution:
    mode: Callable[[], str]
    generate: Callable[[Record], Record]
    runpod: Callable[[str, Record, Record], None]
    remote: Callable[[str, Record, Record], None]


@dataclass(frozen=True)
class TrainingLocalExecution:
    base_model: Callable[[], str]
    device: Callable[[], Any]
    cli: Callable[[], str]
    start: Callable[[], StartTrainingProcess]
    progress: Callable[[Path, int], tuple[int, int] | None]
    warmup: Callable[[], Callable[[str, list[str]], None]]


class TrainingRunner:
    def __init__(self, records: TrainingRunnerRecords, paths: TrainingRunnerPaths, datasets: TrainingDatasetExecution,
                 local: TrainingLocalExecution, resolver: ResolverProvider):
        self.records, self.paths, self.datasets, self.local = records, paths, datasets, local
        # Wrap the bound method once: constructor validation does not resolve a profile or read a task.
        self.run_training_task = pinned(resolver, records.find)(self.run_training_task)

    def run_training_task(self, job_id: str) -> None:
        task = self.records.load()(self.records.path(job_id))
        if not task:
            return
        try:
            self.records.update_provider()(job_id, status="running", progress=5, started_at=int(time.time()), note="任务已启动。")
            executor_mode = self.datasets.mode()
            task_dataset_yaml = self.paths.resolve()(task.get("dataset_yaml", ""))
            has_local_dataset = bool(task.get("dataset_yaml") and task_dataset_yaml.exists())
            if task.get("dataset_yaml") and task_dataset_yaml.exists():
                dataset = {
                    "dataset_dir": str(self.paths.resolve()(task.get("dataset_dir", "")) if task.get("dataset_dir") else task_dataset_yaml.parent),
                    "dataset_yaml": str(task_dataset_yaml),
                    "manifest_path": str(task.get("manifest_path") or ""),
                }
                self.records.update_provider()(job_id, status="running", progress=74, note="已选择样本集，正在启动 YOLO 训练。", **dataset)
            else:
                dataset = self.datasets.generate(task)
            if task.get("action") == "generate_samples":
                self.records.update_provider()(job_id, status="completed", progress=100, completed_at=int(time.time()), note="训练样本已生成完成。", **dataset)
                self.records.sync(job_id)
                return
            if executor_mode == "runpod":
                self.datasets.runpod(job_id, task, dataset)
                return
            if self.datasets.mode() == "remote":
                self.datasets.remote(job_id, task, dataset)
                return
            self.records.update_provider()(job_id, status="running", progress=76, note="样本已生成，正在启动 YOLO 训练。", **dataset)
            run_dir = self.paths.output()("training_runs", str(task.get("owner_user_id") or ""))
            # Detection-only training: transfer-learn from a COCO-pretrained bbox
            # detector (not the old segmentation checkpoint).
            model_path = self.local.base_model()
            epochs = max(1, min(500, int(task.get("epochs") or 1)))
            image_size = max(320, min(1280, int(task.get("image_size") or 640)))
            training_device = self.local.device()
            training_device_text = str(training_device).strip().lower()
            cpu_training = training_device_text == "cpu"
            command = [
                self.local.cli(),
                "detect",
                "train",
                f"model={model_path}",
                f"data={dataset['dataset_yaml']}",
                f"imgsz={image_size}",
                f"epochs={epochs}",
                "batch=1" if cpu_training else "batch=0.72",
                f"device={training_device}",
                "cache=False" if cpu_training else "cache=ram",
                "workers=0",
                "amp=False" if cpu_training else "amp=True",
                "patience=25",
                "optimizer=auto",
                "mosaic=0.0",
                "mixup=0.0",
                "copy_paste=0.0",
                "plots=False" if cpu_training else "plots=True",
                f"project={run_dir}",
                f"name={job_id}",
                "exist_ok=True",
            ]
            log_path = self.paths.tasks() / f"{job_id}.log"
            with log_path.open("w", encoding="utf-8") as log:
                process = self.local.start()(command, cwd=str(self.paths.app()), stdout=log, stderr=subprocess.STDOUT, text=True)
                self.records.update_provider()(
                    job_id,
                    training_command=command,
                    training_log_path=str(log_path),
                    training_pid=process.pid,
                    current_epoch=0,
                    total_epochs=epochs,
                    progress=82,
                    note=f"YOLO 训练已启动：Epoch 0/{epochs}。",
                )
                last_epoch = 0
                while process.poll() is None:
                    parsed_epoch = self.local.progress(log_path, epochs)
                    if parsed_epoch and parsed_epoch[0] != last_epoch:
                        last_epoch = parsed_epoch[0]
                        epoch_progress = min(98, 82 + int((last_epoch / max(1, epochs)) * 16))
                        self.records.update_provider()(
                            job_id,
                            status="running",
                            progress=epoch_progress,
                            current_epoch=last_epoch,
                            total_epochs=parsed_epoch[1],
                            note=f"YOLO 训练中：Epoch {last_epoch}/{parsed_epoch[1]}。",
                        )
                    time.sleep(5)
                return_code = process.returncode
                parsed_epoch = self.local.progress(log_path, epochs)
                if parsed_epoch:
                    last_epoch = max(last_epoch, parsed_epoch[0])
            self.records.update_provider()(
                job_id,
                status="completed" if return_code == 0 else "failed",
                progress=100,
                completed_at=int(time.time()),
                return_code=return_code,
                current_epoch=epochs if return_code == 0 else last_epoch,
                total_epochs=epochs,
                training_run_dir=str(run_dir / job_id),
                note="模型训练已完成。" if return_code == 0 else "模型训练失败，请查看训练日志。",
            )
            self.records.sync(job_id)
            if return_code == 0:
                variant = str(task.get("model_variant") or task.get("mode") or "yolo")
                variant = variant if variant in {"yolo", "yolo_ocr"} else "yolo"
                self.local.warmup()("training_completed", [f"trained_{job_id}__{variant}"])
        except Exception as exc:
            self.records.update_provider()(job_id, status="failed", progress=100, completed_at=int(time.time()), error=str(exc), note=f"任务失败：{exc}")
            self.records.sync(job_id)
