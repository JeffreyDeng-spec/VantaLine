"""Legacy pose-collection job construction and in-memory reconciliation."""
from dataclasses import dataclass
from pathlib import Path
import re
import time
from typing import Any
import uuid
from .pose_collection_job_ports import PoseJobIdentity, PoseJobMedia, PoseJobWorkflow

@dataclass(frozen=True)
class PoseCollectionJobs:
    identity: PoseJobIdentity
    media: PoseJobMedia
    workflow: PoseJobWorkflow

    def safe_record_id(self, value: Any) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "record")).strip("._") or "record"


    def pose_collection_output_dir(self, item: dict[str, Any]) -> Path:
        owner = self.identity.record_owner_id()(item)
        return self.media.output_write_dir_for_owner()("accessory_pose_collections", owner) / self.identity.safe_record_id()(self.identity.accessory_uid()(item) or str(uuid.uuid4()))


    def pose_collection_output_name(self, pose_family: str) -> str:
        return "pose_collection_endface.png" if pose_family == "upright" else "pose_collection_flat.png"


    def pose_collection_job_id(self, item: dict[str, Any], pose_family: str) -> str:
        return f"imgjob_{self.identity.safe_record_id()(self.identity.accessory_uid()(item))}_{pose_family}_anchor_replacement"


    def source_reference_inputs_for_pose_job(self, item: dict[str, Any], pose_family: str) -> list[str]:
        inputs: list[str] = []
        anchor = self.media.POSE_ANCHOR_IMAGES().get(pose_family)
        if anchor and self.media._business_files().exists(anchor):
            inputs.append(str(anchor))
        for path in self.media.existing_source_image_paths()(item):
            text = str(path)
            if text not in inputs:
                inputs.append(text)
        return inputs[:self.media.MAX_IMAGE_WORKER_INPUTS()]


    def make_pose_collection_job(self, item: dict[str, Any], pose_family: str) -> dict[str, Any]:
        output_path = self.media.pose_collection_output_dir()(item) / self.media.pose_collection_output_name()(pose_family)
        anchor_path = self.media.POSE_ANCHOR_IMAGES().get(pose_family)
        job = {
            "job_id": self.workflow.pose_collection_job_id()(item, pose_family),
            "task_id": self.identity.deterministic_task_id()(item, {"pose_family": pose_family, "output_path": str(output_path)}),
            "candidate_id": self.identity.accessory_uid()(item),
            "candidate_name": item.get("name") or self.identity.accessory_uid()(item),
            "label": "正立多角度图" if pose_family == "upright" else "平躺多角度图",
            "queue_kind": "image_generation",
            "status": "completed" if self.media._business_files().exists(output_path) else self.workflow.CODEX_IMAGE_WORKER_QUEUE_STATUS(),
            "progress": 100 if self.media._business_files().exists(output_path) else 0,
            "provider": self.workflow.LOCAL_CODEX_IMAGE_PROVIDER(),
            "generation_method": "codex_exec_image_worker",
            "generation_step": "anchor_replacement",
            "pose_family": pose_family,
            "prompt": self.workflow.build_anchor_replacement_pose_prompt()(item, pose_family),
            "input_files": self.media.source_reference_inputs_for_pose_job()(item, pose_family),
            "anchor_image_path": str(anchor_path) if anchor_path else "",
            "output_path": str(output_path),
            "output_url": self.media.public_output_url()(output_path),
            "created_at": int(time.time()),
            **self.identity.record_audit_fields()(item),
        }
        if self.media._business_files().exists(output_path):
            job["completed_at"] = int(self.media._business_files().stat(output_path).st_mtime)
        self.workflow.ensure_image_job_task_id()(item, job)
        self.workflow.ensure_anchor_image_provenance()(job)
        self.workflow.ensure_image_job_target_guides()(job)
        return job


    def ensure_pose_collection_image_jobs(self, item: dict[str, Any]) -> bool:
        if self.identity.accessory_material_type()(item) == "text":
            return False
        # Legacy anchor/grid pose-collection generation is retired. Object standard
        # images are now produced inside the training pipeline as single-object
        # top-down photos (agent_mcp pose images) and segmented into clean sprites;
        # no anchor grids are generated at accessory creation anymore.
        if not self.workflow.POSE_COLLECTION_GRID_ENABLED():
            return False
        jobs = self.workflow.candidate_image_jobs()(item)
        changed = False
        for job in jobs:
            changed = self.workflow.ensure_image_job_task_id()(item, job) or changed
            changed = self.workflow.ensure_anchor_image_provenance()(job) or changed
            changed = self.workflow.ensure_image_job_target_guides()(job) or changed
            if str(job.get("generation_step") or "") == "anchor_replacement":
                if job.get("provider") != self.workflow.LOCAL_CODEX_IMAGE_PROVIDER():
                    job["provider"] = self.workflow.LOCAL_CODEX_IMAGE_PROVIDER()
                    changed = True
                if job.get("generation_method") != "codex_exec_image_worker":
                    job["generation_method"] = "codex_exec_image_worker"
                    changed = True
                if job.get("queue_kind") != "image_generation":
                    job["queue_kind"] = "image_generation"
                    changed = True
                output_path = self.media.image_job_output_path()(job, for_write=True)
                if self.media._business_files().exists(output_path) and job.get("status") != "completed":
                    job["status"] = "completed"
                    job["progress"] = 100
                    job["completed_at"] = int(self.media._business_files().stat(output_path).st_mtime)
                    job["output_url"] = self.media.public_output_url()(output_path)
                    changed = True
                elif job.get("status") == "completed" and not self.media._business_files().exists(output_path):
                    job["status"] = self.workflow.CODEX_IMAGE_WORKER_QUEUE_STATUS()
                    job["progress"] = 0
                    job["provider"] = self.workflow.LOCAL_CODEX_IMAGE_PROVIDER()
                    job["generation_method"] = "codex_exec_image_worker"
                    job["error"] = f"Missing target PNG: {output_path}. Requeued for Windows CodexImageWorker."
                    job.pop("completed_at", None)
                    changed = True
        for pose_family in ("upright", "lying"):
            expected_name = self.media.pose_collection_output_name()(pose_family)
            existing = next(
                (
                    job
                    for job in jobs
                    if str(job.get("generation_step") or "") == "anchor_replacement"
                    and str(job.get("pose_family") or "") == pose_family
                    and Path(str(job.get("output_path") or "")).name == expected_name
                ),
                None,
            )
            if existing is None:
                jobs.append(self.workflow.make_pose_collection_job()(item, pose_family))
                changed = True
        if changed or jobs:
            item["codex_image_jobs"] = jobs
            item["codex_image_job"] = jobs[0] if jobs else None
            item["ai_generation_required"] = True
            item["pose_collection_prompts"] = {
                "upright": self.workflow.build_anchor_replacement_pose_prompt()(item, "upright"),
                "lying": self.workflow.build_anchor_replacement_pose_prompt()(item, "lying"),
            }
            item["pose_collection_prompt"] = item["pose_collection_prompts"]["lying"]
            item["status"] = "image_tool_plan_ready" if item.get("status") in {"candidate_review", "reference_uploaded", "active"} else item.get("status", "image_tool_plan_ready")
        return changed


    def pending_pose_collection_jobs(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        for job in self.workflow.candidate_image_jobs()(item):
            if str(job.get("generation_step") or "") != "anchor_replacement":
                continue
            output_path = self.media.image_job_output_path()(job, for_write=True)
            if str(job.get("status") or "") != "completed" or not self.media._business_files().exists(output_path):
                copy = dict(job)
                copy["missing_output_path"] = str(output_path)
                pending.append(copy)
        return pending


    def pose_collection_pending_detail(self, item: dict[str, Any], pending: list[dict[str, Any]]) -> str:
        details = []
        for job in pending[:4]:
            status = str(job.get("status") or "missing")
            pose = str(job.get("pose_family") or "pose")
            error = str(job.get("error") or "").strip()
            missing = str(job.get("missing_output_path") or job.get("output_path") or "")
            parts = [pose, status]
            if missing:
                parts.append(f"target={missing}")
            if error:
                parts.append(error)
            details.append(" / ".join(parts))
        suffix = "；..." if len(pending) > 4 else ""
        return f"配件 {item.get('name') or self.identity.accessory_uid()(item)} 的 Windows CodexImageWorker 多角度图还未完成：{'；'.join(details)}{suffix}。请等待生成任务完成，或重试失败任务后再生成训练样本。"
