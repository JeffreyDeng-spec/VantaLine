"""Locked confirmation retains task, profile and persistence transition ordering."""
import json
import time
import uuid
from typing import Any
from fastapi import HTTPException
from .confirmation_ports import ConfirmationAccess, ConfirmationStore, ConfirmationJobs, ConfirmationProfiles, ConfirmationMedia, ConfirmationPipeline
from .policy import accessory_uid, accessory_material_type, normalize_object_alpha_material_policy, object_alpha_material_policy, object_alpha_policy_label
from .projection import AccessoryProjection


class AccessoryConfirmation:
    def __init__(self, access: ConfirmationAccess, store: ConfirmationStore, jobs: ConfirmationJobs,
                 profiles: ConfirmationProfiles, media: ConfirmationMedia,
                 pipeline: ConfirmationPipeline, projection: AccessoryProjection):
        self.access, self.store, self.jobs = access, store, jobs
        self.profiles, self.media = profiles, media
        self.pipeline, self.projection = pipeline, projection

    def confirm_accessory(self, candidate_id: str) -> dict[str, Any]:
        user = self.access.current_user()
        path = self.store.directory() / f"{candidate_id}.json"
        with self.store.lock():
            candidate = self.store.load_candidate(candidate_id)
            self.access.require_access(candidate, user, write=True)
            confirmed_id = self.pipeline.confirmed_id(candidate)
            if confirmed_id:
                config = self.store.load_config()
                item = next((entry for entry in config.get("accessories", []) if accessory_uid(entry) == confirmed_id), None)
                if not item:
                    for key in ("confirmed_accessory_id", "confirmed_at", "confirmed_class_id"):
                        candidate.pop(key, None)
                    candidate["status"] = "candidate_review"
                    self.store.save_candidate(path, candidate)
                if item and candidate.get("pipeline_context") == "pipeline":
                    self.pipeline.add_accessory(confirmed_id)
                    self.pipeline.remove_pending(candidate_id)
                if item:
                    # Sprite generation is deferred to task start; do not build it on
                    # (re)confirmation of an already-saved accessory.
                    return {
                        "status": "already_saved",
                        "item": self.projection.serialize_accessory_summary(item),
                        "items": self.projection.serialize_accessory_items(self.store.scope(config, user)["accessories"]),
                        "pipeline": self.pipeline.payload(self.store.scope(config, user), user),
                    }
            material_type = accessory_material_type(candidate)
            if material_type == "object" and not normalize_object_alpha_material_policy(candidate.get("material_alpha_policy")):
                raise HTTPException(status_code=400, detail="确认前必须选择物品透明或不透明")
            if material_type == "object":
                candidate["material_alpha_policy"] = object_alpha_material_policy(candidate)
                candidate["object_alpha_policy_label"] = object_alpha_policy_label(candidate["material_alpha_policy"])
            job_plan_changed = self.jobs.ensure_ids(candidate)
            job_plan_changed = self.jobs.ensure_pose(candidate) or job_plan_changed
            if job_plan_changed:
                self.store.save_candidate(path, candidate)
            refreshed_jobs = []
            changed = False
            for job in self.jobs.list_jobs(candidate):
                refreshed = self.jobs.refresh(job)
                self.jobs.store(candidate, refreshed)
                refreshed_jobs.append(refreshed)
                changed = changed or refreshed.get("status") != job.get("status") or refreshed.get("completed_at") != job.get("completed_at")
            if changed:
                self.store.save_candidate(path, candidate)
            if any(str(job.get("status", "")) in self.jobs.active_statuses() for job in refreshed_jobs):
                self.jobs.start_worker()
                raise HTTPException(status_code=409, detail="Image generation is still running. Confirm after all pose jobs complete.")

            self.media.defer(candidate)
            self.profiles.ensure_reference(candidate)
            self.profiles.ensure_profile(candidate, force=not isinstance(candidate.get("ai_profile"), dict), allow_provider=True)
            if material_type == "text" and self.profiles.rejected(candidate):
                text_assets = self.media.canonical_assets(candidate)
                text_assets_complete = self.media.complete(candidate, text_assets)
                self.store.save_candidate(path, candidate)
                raise HTTPException(
                    status_code=422,
                    detail=self.media.error_detail(
                        candidate,
                        text_assets,
                        text_assets_complete,
                        self.profiles.ready(candidate),
                    ),
                )

            config = self.store.load_config()
            self.store.unique_name(config, candidate.get("name"), self.access.owner_id(candidate))
            existing_ids = [int(item.get("class_id", -1)) for item in config.get("accessories", [])]
            original_class_id = candidate.get("class_id", -1)
            original_candidate_id = str(candidate.get("id") or candidate_id)
            candidate["class_id"] = max(existing_ids + list(self.store.class_names().keys())) + 1
            candidate["id"] = f"acc_{uuid.uuid4().hex[:10]}"
            candidate["status"] = candidate.get("status", "candidate_review").replace("candidate_review", "active")
            candidate["confirmed_at"] = int(time.time())
            self.profiles.ensure_reference(candidate)
            self.profiles.ensure_profile(candidate, force=True, allow_provider=True)
            confirmed_item = json.loads(json.dumps(candidate))
            if accessory_material_type(confirmed_item) == "text":
                # Documents: crop + deskew + normalize to the chosen paper size NOW, at
                # creation. No image generation and no task-time sprite step — the task
                # just reuses these canonical pages.
                confirmed_item.update(self.media.normalize(confirmed_item))
                confirmed_item["normalization_deferred"] = False
                text_assets = self.media.canonical_assets(confirmed_item)
                text_assets_complete = self.media.complete(confirmed_item, text_assets)
                profile_ready = self.profiles.ready(confirmed_item)
                if not text_assets_complete or not profile_ready:
                    failed_candidate = json.loads(json.dumps(candidate))
                    failed_candidate["id"] = original_candidate_id
                    failed_candidate["class_id"] = original_class_id
                    failed_candidate["status"] = "candidate_review"
                    for key in ("confirmed_accessory_id", "confirmed_at", "confirmed_class_id"):
                        failed_candidate.pop(key, None)
                    if isinstance(failed_candidate.get("ai_profile"), dict):
                        failed_candidate["ai_profile"] = self.profiles.normalize(failed_candidate["ai_profile"], failed_candidate)
                    self.store.save_candidate(path, failed_candidate)
                    raise HTTPException(
                        status_code=422,
                        detail=self.media.error_detail(confirmed_item, text_assets, text_assets_complete, profile_ready),
                    )
            else:
                # Objects: defer sprite generation until a pipeline task starts.
                self.media.defer(confirmed_item)
            config["accessories"].append(confirmed_item)
            self.store.save_item(confirmed_item, config)
            candidate_record = json.loads(json.dumps(confirmed_item))
            candidate_record["id"] = original_candidate_id
            candidate_record["class_id"] = original_class_id
            candidate_record["status"] = "confirmed"
            candidate_record["confirmed_accessory_id"] = accessory_uid(confirmed_item)
            candidate_record["confirmed_at"] = confirmed_item.get("confirmed_at") or int(time.time())
            candidate_record["confirmed_class_id"] = confirmed_item.get("class_id")
            self.store.save_candidate(path, candidate_record)
            if candidate_record.get("pipeline_context") == "pipeline":
                self.pipeline.add_accessory(accessory_uid(confirmed_item))
                self.pipeline.remove_pending(candidate_id)
            return {
                "status": "saved",
                "item": self.projection.serialize_accessory_summary(confirmed_item),
                "items": self.projection.serialize_accessory_items(self.store.scope(config, user)["accessories"]),
                "pipeline": self.pipeline.payload(self.store.scope(config, user), user),
            }
