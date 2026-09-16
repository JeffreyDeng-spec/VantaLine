"""Candidate creation, retaining provider, thumbnail, pose and save ordering."""
from pathlib import Path
import time
from typing import Any
import uuid
import cv2
from fastapi import HTTPException
from .policy import normalize_object_alpha_material_policy, object_alpha_policy_label
from .preparation_ports import CandidateMedia, CandidatePreparation, CandidateStorage


class CandidateFactory:
    def __init__(self, media: CandidateMedia, preparation: CandidatePreparation, storage: CandidateStorage):
        self.media, self.preparation, self.storage = media, preparation, storage

    def create_accessory_candidate(self, 
        name: str,
        material_type: str,
        training_role: str,
        source_files: list[str],
        physical_size: dict[str, Any] | None = None,
        material_alpha_policy: str | None = None,
        size_reference: str | None = None,
    ) -> dict[str, Any]:
        candidate_id = f"cand_{uuid.uuid4().hex[:10]}"
        expanded_source_files, extracted_video_frames = self.media.expand_sources(candidate_id, source_files)
        alpha_policy = normalize_object_alpha_material_policy(material_alpha_policy) if material_type == "object" else None
        if material_type == "object" and not alpha_policy:
            raise HTTPException(status_code=400, detail="material_alpha_policy must be transparent or opaque for object accessories")
        item = {
            "id": candidate_id,
            "class_id": -1,
            "name": name,
            "material_type": material_type,
            "training_role": training_role,
            "physical_size": physical_size or self.media.default_size(material_type),
            "status": "candidate_review",
            "source_files": expanded_source_files,
            "original_source_files": source_files,
            "video_reference_frames": extracted_video_frames,
            "created_at": int(time.time()),
            **self.storage.owner_fields(),
        }
        if alpha_policy:
            item["material_alpha_policy"] = alpha_policy
            item["object_alpha_policy_label"] = object_alpha_policy_label(alpha_policy)
        size_reference_key = self.media.size_reference(size_reference) if material_type == "object" else ""
        if size_reference_key:
            item["size_reference"] = size_reference_key
        self.preparation.defer(item)
        self.preparation.ensure_reference(item)
        self.preparation.ensure_profile(item, allow_provider=True)
        thumbnails = []
        image_sources = [Path(path) for path in expanded_source_files if Path(path).suffix.lower() in self.media.image_suffixes()]
        if image_sources:
            thumb_dir = self.media.output_directory("accessory_candidates") / candidate_id
            thumb_dir.mkdir(parents=True, exist_ok=True)
        for idx, src in enumerate(image_sources[:8]):
            image = cv2.imread(str(src), cv2.IMREAD_COLOR)
            if image is not None:
                thumbnails.append(self.media.thumbnail(image, thumb_dir / f"source_{idx + 1:02d}.png", 0))
        item["thumbnails"] = thumbnails[:8]
        item["ai_generation_required"] = False
        item["pose_collection_prompt"] = ""
        item["pose_collection_prompts"] = {}
        item["codex_image_jobs"] = []
        item["codex_image_job"] = None
        self.preparation.ensure_pose_jobs(item)
        self.storage.save(self.storage.directory() / f"{candidate_id}.json", item)
        return item
