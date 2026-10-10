"""Bound training execution orchestration; transports and local processes are explicit ports."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Any, Protocol, TextIO
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import pinned
from .file_ports import TrainingRunnerFiles

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
                 local: TrainingLocalExecution, resolver: ResolverProvider, *, files: TrainingRunnerFiles):
        self.records, self.paths, self.datasets, self.local = records, paths, datasets, local
        if files is None:
            raise TypeError('files is required')
        self.files = files
        # Wrap the bound method once: constructor validation does not resolve a profile or read a task.
        self.run_training_task = pinned(resolver, records.find)(self.run_training_task)

    def run_training_task(self, job_id: str) -> None:
        task = self.records.load()(self.records.path(job_id))
        if not task:
            return
        try:
            self.records.update_provider()(job_id, status="running", progress=5, started_at=int(time.time()), note="任务已启动。")
            executor_mode = self.datasets.mode()
            if task.get('feedback_strategy')=='real_photo_vlm' and executor_mode!=task['real_photo_training_configuration']['executor']:
                raise RuntimeError('frozen executor changed')
            runtime = self.files.runtime_provider()
            if runtime is not None and executor_mode != "runpod":
                raise RuntimeError("COS training requires RunPod; local training fallback is disabled")
            task_dataset_yaml = self.paths.resolve()(task.get("dataset_yaml", ""))
            files = self.files
            has_local_dataset = bool(task.get("dataset_yaml") and files.exists(task_dataset_yaml))
            if task.get('feedback_strategy') == 'real_photo_vlm' and not has_local_dataset:
                raise RuntimeError('frozen real-photo dataset missing; image generation fallback is forbidden')
            if task.get("dataset_yaml") and files.exists(task_dataset_yaml):
                dataset = {
                    "dataset_dir": str(self.paths.resolve()(task.get("dataset_dir", "")) if task.get("dataset_dir") else task_dataset_yaml.parent),
                    "dataset_yaml": str(task_dataset_yaml),
                    "manifest_path": str(task.get("manifest_path") or ""),
                }
                self.records.update_provider()(job_id, status="running", progress=74, note="已选择样本集，正在启动 YOLO 训练。", **dataset)
            else:
                if runtime is None:
                    dataset = self.datasets.generate(task)
                else:
                    # Images publish directly to COS. Hold the same cross-process
                    # work slot as packaging so two large preparations cannot run.
                    with runtime.store.budget.reserve("work", 1):
                        dataset = self.datasets.generate(task)
            if task.get("action") == "generate_samples":
                self.records.update_provider()(job_id, status="completed", progress=100, completed_at=int(time.time()), note="训练样本已生成完成。", **dataset)
                self.records.sync(job_id)
                return
            if executor_mode == "runpod":
                self.datasets.runpod(job_id, task, dataset)
                return
            if self.datasets.mode() == "remote":
                if task.get('feedback_strategy')=='real_photo_vlm':
                    raise RuntimeError('legacy remote executor lacks frozen real-photo evaluation; use RunPod or local executor')
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
            if task.get('feedback_strategy')=='real_photo_vlm':
                from .real_photo_training_config import validate_local
                frozen=task['real_photo_training_configuration']
                validate_local(frozen,model_path,training_device)
                if epochs!=frozen['epochs'] or image_size!=frozen['image_size']:
                    raise ValueError('frozen real-photo training parameters changed')
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
            real_metrics=None
            if return_code==0 and task.get('feedback_strategy')=='real_photo_vlm':
                from .real_photo_evaluation import evaluate
                real_metrics=evaluate(task,run_dir/job_id,dataset['dataset_yaml'],training_device)
            self.records.update_provider()(
                job_id,
                status="completed" if return_code == 0 else "failed",
                **({'real_photo_test_metrics':real_metrics} if real_metrics is not None else {}),
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
