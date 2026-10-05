"""Shadow comparison, candidate promotion and retirement orchestration."""
from dataclasses import dataclass
from typing import Any
import cv2
import threading
import time
from .auto_optimization_shadow_evaluation_ports import ShadowState, ShadowObservation, ShadowPromotion

@dataclass(frozen=True)
class AutoOptimizationShadowEvaluation:
    state: ShadowState
    observation: ShadowObservation
    promotion: ShadowPromotion

    def start_auto_optimize_shadow_worker(self, task_id: str, sample_id: str) -> None:
        clean_task_id = self.state.sanitize_ai_detection_task_id()(task_id)
        if not clean_task_id:
            return
        key = f"{clean_task_id}:{sample_id}"
        with self.state._auto_optimize_lock():
            existing = self.state._auto_optimize_shadow_threads().get(key)
            if existing and existing.is_alive():
                return
            thread = threading.Thread(target=self.state.auto_optimize_shadow_worker(), args=(clean_task_id, sample_id), name=f"auto-opt-shadow-{clean_task_id}", daemon=True)
            self.state._auto_optimize_shadow_threads()[key] = thread
            thread.start()


    def auto_optimize_shadow_worker(self, task_id: str, sample_id: str) -> None:
        try:
            time.sleep(0.1)
            with self.state._auto_optimize_lock():
                state = self.state.load_auto_optimize_state()(task_id)
                opts = state.get("settings") if isinstance(state.get("settings"), dict) else {}
                if not opts.get("enabled"):
                    return
                candidate = next((item for item in state.get("candidate_models") or [] if isinstance(item, dict) and item.get("model_id")), None)
                if not candidate:
                    return
                sample = next((item for item in state.get("samples") or [] if isinstance(item, dict) and item.get("sample_id") == sample_id), None)
                if not sample:
                    return
                model_id = str(candidate.get("model_id") or "")
                image_path = self.observation.resolve_service_path()((sample.get("source_image") or {}).get("path"))
            image_bgr = self.observation._image_files().imread(str(image_path), cv2.IMREAD_COLOR)
            if image_bgr is None:
                return
            yolo_result = self.observation.analyze_bgr()(image_bgr, f"shadow_{self.observation.safe_record_id()(sample_id)}", model_id, image_path=image_path)
            ai_counts = ((sample.get("ai_result") or {}).get("rule") or {}).get("counts") or {}
            yolo_counts = (yolo_result.get("rule") or {}).get("counts") if isinstance(yolo_result.get("rule"), dict) else {}
            agreement = 1.0 if {str(k): int(v) for k, v in ai_counts.items()} == {str(k): int(v) for k, v in (yolo_counts or {}).items()} else 0.0
            shadow = {
                "sample_id": sample_id,
                "model_id": model_id,
                "status": "completed",
                "agreement": agreement,
                "ai_counts": ai_counts,
                "yolo_counts": yolo_counts or {},
                "created_at": int(time.time()),
            }
            with self.state._auto_optimize_lock():
                state = self.state.load_auto_optimize_state()(task_id)
                state.setdefault("shadow_runs", []).insert(0, shadow)
                state["shadow_runs"] = state["shadow_runs"][:5000]
                self.promotion.maybe_promote_auto_optimize_model_locked()(state)
                self.state.save_auto_optimize_state()(state)
        except Exception as exc:
            with self.state._auto_optimize_lock():
                state = self.state.load_auto_optimize_state()(task_id)
                state["last_shadow_error"] = self.state.bounded_text()(str(exc), 240)
                self.state.save_auto_optimize_state()(state)


    def maybe_promote_auto_optimize_model_locked(self, state: dict[str, Any]) -> None:
        opts = state.get("settings") if isinstance(state.get("settings"), dict) else {}
        if not opts.get("auto_promote"):
            return
        runs = [run for run in state.get("shadow_runs") or [] if isinstance(run, dict) and run.get("status") == "completed"]
        min_samples = int(opts.get("shadow_min_samples") or 80)
        if len(runs) < min_samples:
            return
        recent = runs[:min_samples]
        agreement = sum(float(run.get("agreement") or 0.0) for run in recent) / max(1, len(recent))
        if agreement < float(opts.get("shadow_min_agreement") or 0.98):
            return
        model_id = str(recent[0].get("model_id") or "")
        if not model_id:
            return
        old_model = str(state.get("active_model_id") or "")
        if old_model and old_model != model_id:
            state.setdefault("retired_model_ids", []).append(old_model)
            self.promotion.cleanup_auto_optimize_retired_candidate_locked()(state, old_model, keep_model_id=model_id)
        state["active_model_id"] = model_id
        settings = {**self.promotion.default_auto_optimize_settings()(), **(state.get("settings") or {})}
        settings["serving_mode"] = "promoted_yolo"
        settings["enabled"] = False
        state["settings"] = settings
        state["capture_stopped_at"] = int(time.time())
        state["capture_stop_reason"] = "shadow_promoted_model_ready"
        state["last_promotion"] = {"model_id": model_id, "agreement": round(float(agreement), 6), "sample_count": len(recent), "promoted_at": int(time.time())}


    def cleanup_auto_optimize_retired_candidate_locked(self, state: dict[str, Any], model_id: str, *, keep_model_id: str) -> None:
        if not model_id or model_id == keep_model_id:
            return
        candidates = [item for item in state.get("candidate_models") or [] if isinstance(item, dict)]
        candidate = next((item for item in candidates if str(item.get("model_id") or "") == model_id), None)
        if not candidate:
            return
        job_id = str(candidate.get("job_id") or "").strip()
        if not job_id:
            return
        dataset_id = str(candidate.get("dataset_id") or "")
        if dataset_id and not dataset_id.startswith("autoopt_"):
            return
        owner_user = {
            "id": str(state.get("owner_user_id") or self.promotion.LEGACY_OWNER_ID()),
            "username": str(state.get("owner_username") or state.get("owner_user_id") or self.promotion.LEGACY_OWNER_ID()),
            "role": "admin",
        }
        try:
            self.promotion.delete_training_task_record()(job_id, owner_user, missing_ok=True)
        except Exception as exc:
            candidate["retire_cleanup_error"] = self.state.bounded_text()(str(exc), 180)
            return
        deleted_paths: list[str] = []
        for root in self.promotion.training_run_roots()():
            run_dir = root / job_id
            if not self.promotion._business_files().exists(run_dir) or not self.promotion._business_files().is_dir(run_dir):
                continue
            try:
                self.promotion._business_files().rmtree(run_dir)
                deleted_paths.append(str(run_dir))
            except OSError as exc:
                candidate["retire_cleanup_error"] = self.state.bounded_text()(str(exc), 180)
                return
        candidate["status"] = "retired_deleted"
        candidate["deleted_at"] = int(time.time())
        candidate["deleted_paths"] = deleted_paths
