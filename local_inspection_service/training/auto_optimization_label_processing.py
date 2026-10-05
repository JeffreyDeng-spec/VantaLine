"""Automatic optimization label batch processing and worker startup."""
from dataclasses import dataclass
from typing import Any
import threading
import time
from .auto_optimization_label_processing_ports import ProcessingState, ProcessingArtifacts, ProcessingExecution

@dataclass(frozen=True)
class AutoOptimizationLabelProcessing:
    state: ProcessingState
    artifacts: ProcessingArtifacts
    execution: ProcessingExecution

    def start_auto_optimize_label_worker(self, task_id: str) -> None:
        clean_task_id = self.state.sanitize_ai_detection_task_id()(task_id)
        if not clean_task_id:
            return
        with self.state._auto_optimize_lock():
            existing = self.state._auto_optimize_label_threads().get(clean_task_id)
            if existing and existing.is_alive():
                return
            thread = threading.Thread(target=self.state.auto_optimize_label_worker(), args=(clean_task_id,), name=f"auto-opt-label-{clean_task_id}", daemon=True)
            self.state._auto_optimize_label_threads()[clean_task_id] = thread
            thread.start()


    def auto_optimize_process_label_sample(self,
        task_id: str,
        pending: dict[str, Any],
        provider_settings: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        artifact_dir = self.artifacts.output_write_dir_for_owner()("auto_optimize_masks", str(pending.get("owner_user_id") or "")) / self.artifacts.safe_record_id()(task_id)
        try:
            labels, failures, label_artifacts = self.artifacts.auto_optimize_generate_labels_for_sample()(pending, provider_settings, model, artifact_dir)
        except Exception as exc:  # noqa: BLE001
            labels, failures, label_artifacts = [], [{"status": "failed", "reason": self.artifacts.bounded_text()(str(exc), 180)}], {}
        api_calls = label_artifacts.get("api_calls") if isinstance(label_artifacts, dict) else []
        api_calls = api_calls if isinstance(api_calls, list) else []
        return {
            "sample_id": pending.get("sample_id"),
            "labels": labels,
            "failures": failures,
            "label_artifacts": label_artifacts,
            "label_attempts": sum(max(1, int((item or {}).get("attempts") or 1)) for item in api_calls if isinstance(item, dict)),
            "label_retry_count": sum(max(0, int((item or {}).get("retry_count") or 0)) for item in api_calls if isinstance(item, dict)),
            "completed_at": int(time.time()),
        }


    def auto_optimize_label_worker(self, task_id: str) -> None:
        try:
            settings = self.execution.image_generation_settings()()
            if not settings.get("configured"):
                return
            model = str(settings.get("model") or settings.get("image_model") or "")
            while True:
                with self.state._auto_optimize_lock():
                    state = self.state.load_auto_optimize_state()(task_id)
                    completed_model_id = self.state.auto_optimize_completed_model_id()(state)
                    if completed_model_id:
                        self.state.auto_optimize_stop_capture_for_model_locked()(state, completed_model_id, reason="completed_model_ready")
                        self.state.save_auto_optimize_state()(state)
                        return
                    opts = state.get("settings") if isinstance(state.get("settings"), dict) else self.state.default_auto_optimize_settings()()
                    if not opts.get("enabled"):
                        return
                    max_parallel = max(1, min(self.execution.AUTO_OPTIMIZE_MASK_MAX_PARALLEL(), int(opts.get("max_label_jobs_per_cycle") or self.execution.AUTO_OPTIMIZE_MASK_MAX_PARALLEL())))
                    samples = state.get("samples") if isinstance(state.get("samples"), list) else []
                    now = int(time.time())
                    pending_samples = [
                        dict(sample)
                        for sample in samples
                        if isinstance(sample, dict)
                        and (
                            sample.get("label_status") == "pending"
                            or (sample.get("label_status") == "labeling" and now - int(sample.get("label_started_at") or now) > 900)
                        )
                    ][:max_parallel]
                    if not pending_samples:
                        self.state.maybe_start_auto_optimize_training_locked()(state)
                        return
                    pending_ids = {str(sample.get("sample_id") or "") for sample in pending_samples}
                    for sample in samples:
                        if not isinstance(sample, dict) or str(sample.get("sample_id") or "") not in pending_ids:
                            continue
                        sample["label_status"] = "labeling"
                        sample["label_started_at"] = now
                        sample["label_parallel_batch_size"] = len(pending_samples)
                        sample["label_worker_parallelism"] = max_parallel
                        sample.pop("label_completed_at", None)
                        sample.pop("label_reject_reason", None)
                    self.state.save_auto_optimize_state()(state)

                results: list[dict[str, Any]] = []
                with self.execution.ThreadPoolExecutor()(max_workers=len(pending_samples), thread_name_prefix=f"auto-opt-mask-{task_id}") as executor:
                    futures = [
                        executor.submit(self.execution.auto_optimize_process_label_sample(), task_id, pending, dict(settings), model)
                        for pending in pending_samples
                    ]
                    for future in self.execution.as_completed()(futures):
                        results.append(future.result())

                with self.state._auto_optimize_lock():
                    state = self.state.load_auto_optimize_state()(task_id)
                    by_sample_id = {str(result.get("sample_id") or ""): result for result in results}
                    for sample in state.get("samples") or []:
                        if not isinstance(sample, dict):
                            continue
                        result = by_sample_id.get(str(sample.get("sample_id") or ""))
                        if not result:
                            continue
                        labels = result["labels"]
                        failures = result["failures"]
                        sample["labels"] = labels
                        sample["label_failures"] = failures[:8]
                        sample["label_artifacts"] = result["label_artifacts"]
                        sample["label_completed_at"] = result["completed_at"]
                        sample["label_attempts"] = int(result.get("label_attempts") or 0)
                        sample["label_retry_count"] = int(result.get("label_retry_count") or 0)
                        if labels and not failures:
                            sample["label_status"] = "trainable"
                            sample["label_reject_reason"] = ""
                            self.artifacts.auto_optimize_generate_synthetic_batch_for_sample()(task_id, state, sample)
                        elif labels:
                            sample["label_status"] = "review_required"
                            sample["label_reject_reason"] = "ai_detection_ai_mask_class_mismatch"
                        else:
                            hard_failed = any((failure or {}).get("status") == "failed" for failure in failures if isinstance(failure, dict))
                            sample["label_status"] = "failed" if hard_failed else "review_required"
                            sample["label_reject_reason"] = failures[0].get("reason") if failures else "no_valid_label"
                    self.state.save_auto_optimize_state()(state)
                    self.state.maybe_start_auto_optimize_training_locked()(state)
        except Exception as exc:
            with self.state._auto_optimize_lock():
                state = self.state.load_auto_optimize_state()(task_id)
                state["last_label_error"] = self.artifacts.bounded_text()(str(exc), 240)
                self.state.save_auto_optimize_state()(state)
