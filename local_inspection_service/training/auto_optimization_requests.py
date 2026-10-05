"""Auto-optimization settings and manual sample request workflows."""
from dataclasses import dataclass
from typing import Any
import copy
import cv2
from ..schemas.training import AutoOptimizeSettingsRequest, AutoOptimizeSampleApproveRequest
import time
from .auto_optimization_requests_ports import RequestAccess, RequestState, RequestActions

@dataclass(frozen=True)
class AutoOptimizationRequests:
    access: RequestAccess
    state: RequestState
    actions: RequestActions

    def get_ai_task_auto_optimize_status(self, task_id: str) -> dict[str, Any]:
        clean_task_id = self.access.sanitize_ai_detection_task_id()(task_id)
        if not clean_task_id:
            raise self.access.HTTPException()(status_code=404, detail="AI detection task not found")
        user = self.access.current_auth_user()()
        task = next((item for item in self.access.load_ai_detection_tasks()() if item.get("id") == clean_task_id), None)
        if task:
            self.access.require_record_access()(task, user)
        return self.state.public_auto_optimize_state()(clean_task_id, user=user)


    def update_ai_task_auto_optimize_status(self, task_id: str, request: AutoOptimizeSettingsRequest) -> dict[str, Any]:
        clean_task_id = self.access.sanitize_ai_detection_task_id()(task_id)
        if not clean_task_id:
            raise self.access.HTTPException()(status_code=404, detail="AI detection task not found")
        user = self.access.current_auth_user()()
        task = next((item for item in self.access.load_ai_detection_tasks()() if item.get("id") == clean_task_id), None)
        if task:
            self.access.require_record_access()(task, user, write=True)
        return self.state.auto_optimize_update_settings()(clean_task_id, request)


    def delete_ai_task_auto_optimize_sample(self, task_id: str, sample_id: str) -> dict[str, Any]:
        clean_task_id = self.access.sanitize_ai_detection_task_id()(task_id)
        clean_sample_id = self.access.safe_record_id()(sample_id)
        if not clean_task_id or not clean_sample_id:
            raise self.access.HTTPException()(status_code=404, detail="Auto optimize sample not found")
        user = self.access.current_auth_user()()
        task = next((item for item in self.access.load_ai_detection_tasks()() if item.get("id") == clean_task_id), None)
        if task:
            self.access.require_record_access()(task, user, write=True)
        with self.state._auto_optimize_lock():
            state = self.state.load_auto_optimize_state()(clean_task_id)
            samples = [sample for sample in state.get("samples") or [] if isinstance(sample, dict)]
            target = next((sample for sample in samples if str(sample.get("sample_id") or "") == clean_sample_id), None)
            if not target:
                raise self.access.HTTPException()(status_code=404, detail="Auto optimize sample not found")
            self.access.require_record_access()(target, user, write=True)
            state["samples"] = [sample for sample in samples if str(sample.get("sample_id") or "") != clean_sample_id]
            self.state.save_auto_optimize_state()(state)
        return self.state.public_auto_optimize_state()(clean_task_id, user=user)


    def retry_ai_task_auto_optimize_sample(self, task_id: str, sample_id: str) -> dict[str, Any]:
        clean_task_id = self.access.sanitize_ai_detection_task_id()(task_id)
        clean_sample_id = self.access.safe_record_id()(sample_id)
        if not clean_task_id or not clean_sample_id:
            raise self.access.HTTPException()(status_code=404, detail="Auto optimize sample not found")
        user = self.access.current_auth_user()()
        task = next((item for item in self.access.load_ai_detection_tasks()() if item.get("id") == clean_task_id), None)
        if task:
            self.access.require_record_access()(task, user, write=True)
        with self.state._auto_optimize_lock():
            state = self.state.load_auto_optimize_state()(clean_task_id)
            samples = [sample for sample in state.get("samples") or [] if isinstance(sample, dict)]
            target = next((sample for sample in samples if str(sample.get("sample_id") or "") == clean_sample_id), None)
            if not target:
                raise self.access.HTTPException()(status_code=404, detail="Auto optimize sample not found")
            self.access.require_record_access()(target, user, write=True)
            source_image = target.get("source_image") if isinstance(target.get("source_image"), dict) else {}
            source_path = self.actions.resolve_service_path()(source_image.get("path") or "")
            if not self.actions._business_files().exists(source_path):
                raise self.access.HTTPException()(status_code=404, detail="Source image for retry was not found")
            target["label_status"] = "retrying"
            target["retry_requested_at"] = int(time.time())
            self.state.save_auto_optimize_state()(state)
        image_bgr = self.actions._image_files().imread(str(source_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise self.access.HTTPException()(status_code=400, detail="Could not decode source image for retry")
        retry_request_id = f"retry_{clean_sample_id}_{int(time.time())}"
        self.actions.analyze_bgr()(image_bgr, retry_request_id, f"{self.actions.AI_DETECTION_TASK_PREFIX()}{clean_task_id}", image_path=source_path)
        with self.state._auto_optimize_lock():
            state = self.state.load_auto_optimize_state()(clean_task_id)
            for sample in state.get("samples") or []:
                if isinstance(sample, dict) and str(sample.get("sample_id") or "") == clean_sample_id:
                    sample["label_status"] = "retried"
                    sample["retried_at"] = int(time.time())
                    break
            self.state.save_auto_optimize_state()(state)
        return self.state.public_auto_optimize_state()(clean_task_id, user=user)


    def approve_ai_task_auto_optimize_sample(self,
        task_id: str,
        sample_id: str,
        request: AutoOptimizeSampleApproveRequest | None = None,
    ) -> dict[str, Any]:
        clean_task_id = self.access.sanitize_ai_detection_task_id()(task_id)
        clean_sample_id = self.access.safe_record_id()(sample_id)
        if not clean_task_id or not clean_sample_id:
            raise self.access.HTTPException()(status_code=404, detail="Auto optimize sample not found")
        user = self.access.current_auth_user()()
        task = next((item for item in self.access.load_ai_detection_tasks()() if item.get("id") == clean_task_id), None)
        if task:
            self.access.require_record_access()(task, user, write=True)
        with self.state._auto_optimize_lock():
            state = self.state.load_auto_optimize_state()(clean_task_id)
            samples = [sample for sample in state.get("samples") or [] if isinstance(sample, dict)]
            target = next((sample for sample in samples if str(sample.get("sample_id") or "") == clean_sample_id), None)
            if not target:
                raise self.access.HTTPException()(status_code=404, detail="Auto optimize sample not found")
            self.access.require_record_access()(target, user, write=True)
            previous_status = str(target.get("label_status") or "")
            mode = str((request.mode if request else "") or "sprite").strip().lower()
            if mode not in {"sprite", "bbox_only", "image_only"}:
                raise self.access.HTTPException()(status_code=400, detail="Unknown approval mode")
            if previous_status in {"trainable", "trainable_bbox_only"}:
                return self.state.public_auto_optimize_state()(clean_task_id, user=user)
            if previous_status not in {"review_required", "rejected", "failed"}:
                raise self.access.HTTPException()(status_code=409, detail="Only manual-review samples can be approved")
            labels = [label for label in target.get("labels") or [] if isinstance(label, dict)]
            bbox_labels = self.actions.auto_optimize_bbox_training_entries()(target)
            if mode in {"bbox_only", "image_only"} and not bbox_labels:
                raise self.access.HTTPException()(status_code=409, detail="No bbox labels are available to approve")
            if mode == "sprite" and not labels:
                raise self.access.HTTPException()(status_code=409, detail="No AI mask labels are available to approve with sprite")
            label_artifacts = target.get("label_artifacts") if isinstance(target.get("label_artifacts"), dict) else {}
            has_sprite = any(
                isinstance(label.get("sprite"), dict)
                and ((label.get("sprite") or {}).get("path") or (label.get("sprite") or {}).get("raw_path"))
                for label in labels
            )
            has_mask_artifact = bool(label_artifacts.get("color_mask_url") or label_artifacts.get("mask_url") or label_artifacts.get("review_overlay_url"))
            if mode == "sprite" and not has_sprite and not has_mask_artifact:
                raise self.access.HTTPException()(status_code=409, detail="No AI mask artifact is available to approve")
            now = int(time.time())
            previous_failures = copy.deepcopy([failure for failure in target.get("label_failures") or [] if isinstance(failure, dict)])
            target["manual_review"] = {
                **(target.get("manual_review") if isinstance(target.get("manual_review"), dict) else {}),
                "status": "approved",
                "mode": "bbox_only" if mode in {"bbox_only", "image_only"} else "sprite",
                "approved_at": now,
                "approved_by_user_id": user.get("id") or "",
                "approved_by_username": user.get("username") or user.get("name") or "",
                "previous_label_status": previous_status,
                "previous_label_reject_reason": target.get("label_reject_reason") or "",
                "previous_label_failures": previous_failures,
            }
            if mode in {"bbox_only", "image_only"}:
                target["label_status"] = "trainable_bbox_only"
                target["bbox_labels"] = bbox_labels
                target["synthetic_status"] = "skipped"
                target["synthetic_error"] = "bbox_only_does_not_generate_sprite_samples"
            else:
                target["label_status"] = "trainable"
                target["synthetic_status"] = target.get("synthetic_status") or "pending"
                target.pop("synthetic_error", None)
            target["label_reject_reason"] = ""
            target["label_failures"] = []
            target["manual_approved_at"] = now
            target["manual_approved_by"] = user.get("username") or user.get("id") or ""
            target["label_completed_at"] = target.get("label_completed_at") or now
            target["updated_at"] = now
            self.state.save_auto_optimize_state()(state)
        response = self.state.public_auto_optimize_state()(clean_task_id, user=user)
        self.actions.start_auto_optimize_training_check_worker()(clean_task_id, delay_seconds=2.0)
        return response
