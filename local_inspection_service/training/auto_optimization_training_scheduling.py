"""Automatic training admission, submission and delayed-check orchestration."""
from dataclasses import dataclass, field
from typing import Any
import os
import threading
from ..runtime.training_tasks import TrainingThreadLifecycle, ThreadLaunch
import time
from .auto_optimization_training_scheduling_ports import SchedulingPolicy, SchedulingSubmission, SchedulingState

@dataclass(frozen=True)
class AutoOptimizationTrainingScheduling:
    policy: SchedulingPolicy
    submission: SchedulingSubmission
    state: SchedulingState

    runtime: TrainingThreadLifecycle = field(default_factory=TrainingThreadLifecycle, compare=False, repr=False, kw_only=True)

    def maybe_start_auto_optimize_training_locked(self, state: dict[str, Any]) -> None:
        completed_model_id = self.policy.auto_optimize_completed_model_id()(state)
        if completed_model_id:
            self.policy.auto_optimize_stop_capture_for_model_locked()(state, completed_model_id, reason="completed_model_ready")
            return
        opts = state.get("settings") if isinstance(state.get("settings"), dict) else self.policy.default_auto_optimize_settings()
        if not opts.get("enabled"):
            return
        task_id = str(state.get("task_id") or "")
        trainable = [sample for sample in state.get("samples") or [] if isinstance(sample, dict) and sample.get("label_status") == "trainable"]
        bbox_only = [sample for sample in state.get("samples") or [] if isinstance(sample, dict) and sample.get("label_status") == "trainable_bbox_only"]
        negative = [sample for sample in state.get("samples") or [] if isinstance(sample, dict) and sample.get("label_status") == "negative"]
        real_positive_source_count = len(trainable) + len(bbox_only)
        requirements = self.policy.auto_optimize_training_requirements(opts, real_positive_source_count=real_positive_source_count)
        samples_per_real_image = self.policy.auto_optimize_samples_per_real_image(opts)
        positive_derivatives_per_real_image = self.policy.auto_optimize_positive_derivatives_per_real_image(opts)
        generated_negative_count = real_positive_source_count * self.policy.auto_optimize_negative_samples_per_real_image(opts)
        projected_positive_count = len(trainable) * (positive_derivatives_per_real_image + self.policy.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT()) + len(bbox_only) * self.policy.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT()
        projected_negative_count = len(negative) + generated_negative_count
        usable_count = projected_positive_count + projected_negative_count
        if usable_count < requirements["min_trainable_samples"]:
            return
        if projected_positive_count < requirements["min_positive_samples"]:
            return
        if projected_negative_count < requirements["min_negative_samples"]:
            return
        active_candidate = next((item for item in state.get("candidate_models") or [] if isinstance(item, dict) and item.get("status") in {"queued", "running"}), None)
        if active_candidate:
            return
        negative_ratio = max(0.0, min(1.0, float(os.environ.get("VANTALINE_AUTO_OPT_NEGATIVE_RATIO", "0.25"))))
        max_negative = max(
            requirements["min_negative_samples"],
            requirements["min_trainable_samples"] - len(trainable),
            int(len(trainable) * negative_ratio),
        )
        if negative and max_negative <= 0:
            max_negative = 1
        dataset_samples = trainable + bbox_only + negative[:max_negative]
        dataset = self.submission.build_auto_optimize_dataset()(task_id, state, dataset_samples)
        if not dataset:
            self.state.save_auto_optimize_state()(state)
            return
        state.setdefault("datasets", []).insert(0, dataset)
        self.state.save_auto_optimize_state()(state)
        owner_user = {
            "id": str(state.get("owner_user_id") or self.submission.LEGACY_OWNER_ID()),
            "username": str(state.get("owner_username") or state.get("owner_user_id") or self.submission.LEGACY_OWNER_ID()),
            "role": "admin",
        }
        token = self.submission._request_user().set(owner_user)
        try:
            config = self.submission.scope_config_for_user()(self.submission.load_config()(), owner_user)
            selected = self.submission.selected_accessories()(config, dataset.get("selected_accessory_ids") or state.get("selected_accessory_ids") or [])
        finally:
            self.submission._request_user().reset(token)
        if not selected:
            return
        training_parameters = self.policy.auto_optimize_training_parameters(opts)
        request = self.submission.TrainingStartRequest()(
            selected_accessory_ids=[item["id"] for item in selected],
            sample_count=int(dataset.get("sample_count") or len(dataset_samples)),
            train_mode="yolo",
            dataset_id=dataset["id"],
            epochs=training_parameters["training_epochs"],
            image_size=training_parameters["training_image_size"],
            background_set_id=dataset.get("background_set_id") or None,
            pipeline_task_id=self.submission.pipeline_ai_task_id()(task_id),
            pipeline_task_name=str(state.get("task_name") or task_id),
        )
        token = self.submission._request_user().set(owner_user)
        try:
            task = self.submission.enqueue_training_task()(request, selected, "train_model", dataset=dataset)
        finally:
            self.submission._request_user().reset(token)
        candidate = {
            "job_id": task["job_id"],
            "status": task.get("status") or "queued",
            "dataset_id": dataset["id"],
            "model_id": f"trained_{task['job_id']}__yolo",
            "created_at": int(time.time()),
            "training_requirements": requirements,
            "training_parameters": training_parameters,
        }
        state.setdefault("candidate_models", []).insert(0, candidate)
        self.state.save_auto_optimize_state()(state)


    def auto_optimize_training_check_worker(self, task_id: str, delay_seconds: float = 0.0) -> None:
        clean_task_id = self.state.sanitize_ai_detection_task_id()(task_id)
        if not clean_task_id:
            return
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        try:
            with self.state._auto_optimize_lock():
                state = self.state.load_auto_optimize_state()(clean_task_id)
                self.state.maybe_start_auto_optimize_training_locked()(state)
                self.state.save_auto_optimize_state()(state)
        except Exception as exc:  # noqa: BLE001
            with self.state._auto_optimize_lock():
                state = self.state.load_auto_optimize_state()(clean_task_id)
                state["last_training_check_error"] = self.state.bounded_text()(str(exc), 240)
                self.state.save_auto_optimize_state()(state)


    def start_auto_optimize_training_check_worker(self, task_id: str, delay_seconds: float = 0.0) -> None:
        return self.runtime.submit(lambda launch: self._start_check(task_id, delay_seconds, launch))

    def _start_check(self, task_id: str, delay_seconds: float, launch: ThreadLaunch) -> None:
        clean_task_id = self.state.sanitize_ai_detection_task_id()(task_id)
        if not clean_task_id:
            return
        launch(lambda wrap: threading.Thread(
            target=wrap(self.state.auto_optimize_training_check_worker()),
            args=(clean_task_id, delay_seconds),
            name=f"auto-opt-training-check-{clean_task_id}",
            daemon=True,
        ), lambda thread: None)

    def close(self, timeout: float) -> bool:
        return self.runtime.close(timeout)
