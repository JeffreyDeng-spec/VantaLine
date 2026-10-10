"""Existing candidate/config image queue and bounded thread scheduling."""
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any
from ..runtime.image_worker import ImageWork
from .image_job_queue_ports import ImageQueueStorage, ImageQueueMetadata, ImageQueueExecution

@dataclass(frozen=True)
class ImageJobQueue:
    storage: ImageQueueStorage
    metadata: ImageQueueMetadata
    execution: ImageQueueExecution

    def mutate_candidate_image_job(self,
        path: Path,
        candidate: dict[str, Any],
        job: dict[str, Any],
        updates: dict[str, Any],
        *,
        preprocess_clean_sprites: bool = False,
    ) -> dict[str, Any]:
        self.metadata.ensure_image_job_task_id()(candidate, job)
        job_id = str(job.get("job_id", ""))
        with self.storage._candidate_store_lock():
            if path == self.storage.CONFIG_PATH():
                latest_config = self.storage.load_config()()
                latest = next(
                    (
                        item
                        for item in latest_config.get("accessories", [])
                        if isinstance(item, dict) and self.metadata.accessory_uid()(item) == self.metadata.accessory_uid()(candidate)
                    ),
                    None,
                )
                if latest is None:
                    return job
                self.metadata.ensure_candidate_image_job_task_ids()(latest)
                latest_job = next(
                    (item for item in self.metadata.candidate_image_jobs()(latest) if str(item.get("job_id", "")) == job_id),
                    dict(job),
                )
                if latest_job.get("status") == "stopped" and updates.get("status") != "stopped":
                    return latest_job
                latest_job.update(updates)
                self.metadata.store_candidate_image_job()(latest, latest_job)
                if preprocess_clean_sprites:
                    self.metadata.preprocess_object_clean_sprites()(latest, allow_ai_cutout=True)
                self.storage.save_config()(latest_config)
                return latest_job
            repository = self.storage.runtime_postgres_repository_or_none()()
            if repository is not None:
                try:
                    latest = self.storage.load_accessory_candidate()(str(candidate.get("id") or self.metadata.file_stem_identifier()(path)))
                except self.storage.HTTPException() as exc:
                    if exc.status_code != 404:
                        raise
                    latest = candidate
            else:
                if not self.storage._business_files().exists(path):
                    return job
                try:
                    latest = json.loads(self.storage._business_files().read_text(path, encoding="utf-8"))
                except json.JSONDecodeError:
                    latest = candidate
            self.metadata.ensure_candidate_image_job_task_ids()(latest)
            latest_job = next(
                (item for item in self.metadata.candidate_image_jobs()(latest) if str(item.get("job_id", "")) == job_id),
                dict(job),
            )
            if latest_job.get("status") == "stopped" and updates.get("status") != "stopped":
                return latest_job
            latest_job.update(updates)
            self.metadata.store_candidate_image_job()(latest, latest_job)
            if preprocess_clean_sprites:
                self.metadata.preprocess_object_clean_sprites()(latest, allow_ai_cutout=True)
            self.storage.save_accessory_candidate()(path, latest)
            return latest_job


    def next_queued_image_job(self) -> tuple[Path, dict[str, Any], dict[str, Any]] | None:
        for path, candidate in self.storage.list_accessory_candidate_records()(reverse=False):
            with self.storage._candidate_store_lock():
                for job in self.metadata.candidate_image_jobs()(candidate):
                    changed = self.metadata.ensure_image_job_task_id()(candidate, job)
                    if changed:
                        self.metadata.store_candidate_image_job()(candidate, job)
                    status = str(job.get("status", ""))
                    if status not in self.execution.IMAGE_JOB_QUEUED_STATUSES():
                        if changed:
                            self.storage.save_accessory_candidate()(path, candidate)
                        continue
                    depends_on_output = str(job.get("depends_on_output_path") or "")
                    if depends_on_output and not self.storage._business_files().exists(self.metadata.resolve_service_path()(depends_on_output)):
                        if changed:
                            self.storage.save_accessory_candidate()(path, candidate)
                        continue
                    output_path = self.metadata.image_job_output_path()(job, for_write=True)
                    if str(output_path) and str(output_path) != str(job.get("output_path", "")):
                        job["output_path"] = str(output_path)
                        job["output_url"] = self.metadata.public_output_url()(output_path)
                        changed = True
                    if self.storage._business_files().exists(output_path):
                        job["status"] = "completed"
                        job["progress"] = 100
                        job["output_url"] = self.metadata.public_output_url()(output_path)
                        job["completed_at"] = int(self.storage._business_files().stat(output_path).st_mtime)
                        self.metadata.store_candidate_image_job()(candidate, job)
                        self.metadata.preprocess_object_clean_sprites()(candidate, allow_ai_cutout=True)
                        self.storage.save_accessory_candidate()(path, candidate)
                        continue
                    if changed:
                        self.storage.save_accessory_candidate()(path, candidate)
                    return path, candidate, job
        with self.storage._candidate_store_lock():
            config = self.storage.load_config()()
            config_changed = False
            for candidate in config.get("accessories", []):
                if not isinstance(candidate, dict):
                    continue
                if self.metadata.accessory_material_type()(candidate) == "text":
                    continue
                if self.metadata.ensure_pose_collection_image_jobs()(candidate):
                    config_changed = True
                for job in self.metadata.candidate_image_jobs()(candidate):
                    changed = self.metadata.ensure_image_job_task_id()(candidate, job)
                    if changed:
                        self.metadata.store_candidate_image_job()(candidate, job)
                        config_changed = True
                    status = str(job.get("status", ""))
                    if status not in self.execution.IMAGE_JOB_QUEUED_STATUSES():
                        continue
                    depends_on_output = str(job.get("depends_on_output_path") or "")
                    if depends_on_output and not self.storage._business_files().exists(self.metadata.resolve_service_path()(depends_on_output)):
                        continue
                    output_path = self.metadata.image_job_output_path()(job, for_write=True)
                    if str(output_path) and str(output_path) != str(job.get("output_path", "")):
                        job["output_path"] = str(output_path)
                        job["output_url"] = self.metadata.public_output_url()(output_path)
                        changed = True
                    if self.storage._business_files().exists(output_path):
                        job["status"] = "completed"
                        job["progress"] = 100
                        job["output_url"] = self.metadata.public_output_url()(output_path)
                        job["completed_at"] = int(self.storage._business_files().stat(output_path).st_mtime)
                        self.metadata.store_candidate_image_job()(candidate, job)
                        self.metadata.preprocess_object_clean_sprites()(candidate, allow_ai_cutout=True)
                        config_changed = True
                        continue
                    if changed:
                        self.metadata.store_candidate_image_job()(candidate, job)
                        config_changed = True
                    if config_changed:
                        self.storage.save_config()(config)
                    return self.storage.CONFIG_PATH(), candidate, job
            if config_changed:
                self.storage.save_config()(config)
        return None


    def image_worker_loop(self) -> None:
        runtime = self.execution._image_worker_runtime()

        def prepare():
            queued = self.execution.next_queued_image_job()()
            if not queued:
                return None
            path, candidate, job = queued
            self.execution.update_image_worker_status()(
                path, candidate, job, status="running",
                progress=max(int(job.get("progress", 0) or 0), 12),
                started_at=int(time.time()), note="系统正在处理这个图像生成任务。",
            )
            run = self.execution.run_image_generation_job()
            return ImageWork(lambda: run(path, candidate, job),
                             f"image-generation-worker-{job.get('job_id', 'job')}")

        while not runtime.closing:
            launched = False
            while runtime.active_children() < self.execution.MAX_PARALLEL_IMAGE_WORKERS():
                if not runtime.launch(prepare):
                    break
                launched = True
            if not runtime.active_children() and not launched:
                return
            runtime.wait(2)


    def update_image_worker_status(self, path: Path, candidate: dict[str, Any], job: dict[str, Any], **fields: Any) -> None:
        updated_job = self.mutate_candidate_image_job(path, candidate, job, fields)
        job.update(updated_job)
