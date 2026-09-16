"""Creation and preview orchestration with original partial-effect ordering."""
import shutil
import time
import uuid
from typing import Any
from fastapi import HTTPException, UploadFile
from .creation_ports import CreationAccess, CreationStore, CreationMedia, CreationProfiles, CandidateCreation, CreationPipeline
from .policy import normalize_object_alpha_material_policy, object_alpha_policy_label, accessory_uid
from .projection import AccessoryProjection


class AccessoryCreation:
    def __init__(self, access: CreationAccess, store: CreationStore, media: CreationMedia,
                 profiles: CreationProfiles, candidates: CandidateCreation,
                 pipeline: CreationPipeline, projection: AccessoryProjection):
        self.access, self.store, self.media = access, store, media
        self.profiles, self.candidates = profiles, candidates
        self.pipeline, self.projection = pipeline, projection

    async def add_accessory(
        self,
        name: str,
        class_id: int,
        material_type: str,
        material_alpha_policy: str,
        training_role: str,
        pipeline_context: str,
        paper_preset: str,
        paper_width_mm: str,
        paper_height_mm: str,
        object_length_mm: str,
        object_width_mm: str,
        object_height_mm: str,
        size_reference: str,
        files: list[UploadFile],
    ) -> dict[str, Any]:
        user = self.access.current_user()
        if material_type not in {"text", "object"}:
            raise HTTPException(status_code=400, detail="material_type must be text or object")
        alpha_policy = normalize_object_alpha_material_policy(material_alpha_policy) if material_type == "object" else None
        if material_type == "object" and not alpha_policy:
            raise HTTPException(status_code=400, detail="请选择物品透明或不透明")
        if material_type == "text":
            self.media.validate_text(files)
        size_reference_key = self.media.size_reference(size_reference) if material_type == "object" else ""
        config = self.store.load()
        self.store.unique_name(config, name, self.access.new_owner_id(user))
        if class_id < 0:
            existing_ids = [int(item.get("class_id", -1)) for item in config.get("accessories", [])]
            class_id = max(existing_ids + list(self.store.class_names().keys())) + 1
        saved_files = []
        accessory_id = f"acc_{uuid.uuid4().hex[:10]}"
        target_dir = self.media.upload_directory() / "accessories" / accessory_id
        target_dir.mkdir(parents=True, exist_ok=True)
        for upload in files:
            path = target_dir / self.media.safe_name(upload.filename)
            with path.open("wb") as f:
                shutil.copyfileobj(upload.file, f)
            saved_files.append(str(path))
        expanded_source_files, extracted_video_frames = self.media.expand_sources(accessory_id, saved_files)

        item = {
            "id": accessory_id,
            "class_id": class_id,
            "name": name,
            "material_type": material_type,
            "training_role": training_role,
            "physical_size": self.media.physical_size(
                material_type,
                paper_preset,
                paper_width_mm,
                paper_height_mm,
                object_length_mm,
                object_width_mm,
                object_height_mm,
            ),
            "status": "reference_uploaded",
            "source_files": expanded_source_files,
            "original_source_files": saved_files,
            "video_reference_frames": extracted_video_frames,
            "created_at": int(time.time()),
            **self.access.owner_fields(),
        }
        if alpha_policy:
            item["material_alpha_policy"] = alpha_policy
            item["object_alpha_policy_label"] = object_alpha_policy_label(alpha_policy)
        if material_type == "object" and size_reference_key:
            item["size_reference"] = size_reference_key
        if material_type == "text":
            item.update(self.media.normalize(item))
            item["normalization_deferred"] = False
        else:
            self.media.defer(item)
        self.profiles.ensure_reference(item)
        self.profiles.ensure_profile(item, allow_provider=True)
        if material_type != "text":
            self.profiles.ensure_pose_jobs(item)
        config["accessories"].append(item)
        self.store.save(item, config)
        if self.profiles.has_active_jobs(item):
            self.profiles.start_worker()
        scoped_config = self.store.scope(config, user)
        response = {
            "status": "saved",
            "item": self.projection.serialize_accessory_summary(config["accessories"][-1]),
            "items": self.projection.serialize_accessory_items(scoped_config["accessories"]),
        }
        if str(pipeline_context or "").strip().lower() in {"1", "true", "yes", "pipeline"}:
            self.pipeline.add_accessory(accessory_uid(item))
            response["pipeline"] = self.pipeline.payload(scoped_config, self.access.request_user())
        return response

    async def preview_accessory(
        self,
        name: str,
        material_type: str,
        material_alpha_policy: str,
        training_role: str,
        pipeline_context: str,
        paper_preset: str,
        paper_width_mm: str,
        paper_height_mm: str,
        object_length_mm: str,
        object_width_mm: str,
        object_height_mm: str,
        size_reference: str,
        files: list[UploadFile],
    ) -> dict[str, Any]:
        user = self.access.current_user()
        if material_type not in {"text", "object"}:
            raise HTTPException(status_code=400, detail="material_type must be text or object")
        alpha_policy = normalize_object_alpha_material_policy(material_alpha_policy) if material_type == "object" else None
        if material_type == "object" and not alpha_policy:
            raise HTTPException(status_code=400, detail="请选择物品透明或不透明")
        if material_type == "text":
            self.media.validate_text(files)
        size_reference_key = self.media.size_reference(size_reference) if material_type == "object" else ""
        self.store.unique_name(self.store.load(), name, self.access.new_owner_id(user))
        saved_files = []
        if files:
            candidate_source_dir = self.media.upload_directory() / "accessory_candidates" / f"src_{uuid.uuid4().hex[:10]}"
            candidate_source_dir.mkdir(parents=True, exist_ok=True)
            for upload in files:
                path = candidate_source_dir / self.media.safe_name(upload.filename)
                with path.open("wb") as f:
                    shutil.copyfileobj(upload.file, f)
                saved_files.append(str(path))
        physical_size = self.media.physical_size(
            material_type,
            paper_preset,
            paper_width_mm,
            paper_height_mm,
            object_length_mm,
            object_width_mm,
            object_height_mm,
        )
        candidate = self.candidates.create(name, material_type, training_role, saved_files, physical_size, alpha_policy, size_reference_key)
        if str(pipeline_context or "").strip().lower() in {"1", "true", "yes", "pipeline"}:
            candidate["pipeline_context"] = "pipeline"
            self.candidates.save(self.candidates.directory() / f"{candidate['id']}.json", candidate)
            self.pipeline.add_pending(str(candidate["id"]))
            pipeline_payload = self.pipeline.payload(self.store.scope(self.store.load(), user), user)
        else:
            pipeline_payload = None
        if candidate.get("codex_image_job"):
            self.profiles.start_worker()
        result = {"status": "candidate_ready", "candidate": candidate}
        if pipeline_payload is not None:
            result["pipeline"] = pipeline_payload
        return result
