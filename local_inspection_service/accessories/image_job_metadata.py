"""Image-job identity and provenance, with an explicit immutable-model resolver."""
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import freeze_record as freeze_model_record


@dataclass(frozen=True)
class ProvenanceDependencies:
    # The root supplies its actual final hash binding, including its I/O errors.
    hash_file: Callable[[Path], str | None]
    policy_version: Callable[[], str]
    guide_images: Callable[[], Mapping[str, Sequence[Path]]]
    max_inputs: Callable[[], int]


def candidate_image_jobs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = candidate.get("codex_image_jobs")
    if isinstance(jobs, list) and jobs:
        return [job for job in jobs if isinstance(job, dict)]
    job = candidate.get("codex_image_job")
    return [job] if isinstance(job, dict) and job else []


def deterministic_task_id(candidate: dict[str, Any], job: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(job.get("job_id") or ""),
            str(candidate.get("id") or job.get("candidate_id") or ""),
            str(job.get("pose_family") or ""),
            str(job.get("created_at") or candidate.get("created_at") or ""),
            str(job.get("output_path") or ""),
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"task_{digest}"


def ensure_image_job_task_id(candidate: dict[str, Any], job: dict[str, Any]) -> bool:
    changed = False
    if not job.get("job_id"):
        job["job_id"] = f"imgjob_{candidate.get('id', deterministic_task_id(candidate, job))}"
        changed = True
    if not job.get("candidate_id") and candidate.get("id"):
        job["candidate_id"] = candidate.get("id")
        changed = True
    if not job.get("task_id"):
        job["task_id"] = deterministic_task_id(candidate, job)
        changed = True
    return changed


class ImageJobMetadata:
    def __init__(self, provenance: ProvenanceDependencies, model_resolver: ResolverProvider):
        self.provenance, self.model_resolver = provenance, model_resolver

    def ensure_anchor_image_provenance(self, job: dict[str, Any]) -> bool:
        if job.get("generation_step") != "anchor_replacement":
            return False
        changed = False
        anchor_path = Path(str(job.get("anchor_image_path") or ""))
        if anchor_path.name and not job.get("anchor_image_basename"):
            job["anchor_image_basename"] = anchor_path.name
            changed = True
        if "anchor_image_sha256" not in job:
            output_path = Path(str(job.get("output_path") or ""))
            output_predates_anchor = False
            try:
                output_predates_anchor = output_path.exists() and anchor_path.exists() and output_path.stat().st_mtime < anchor_path.stat().st_mtime
            except OSError:
                output_predates_anchor = False
            if job.get("status") == "completed" or output_predates_anchor:
                job["anchor_image_sha256"] = None
                job["anchor_provenance"] = "legacy_path_only"
            else:
                job["anchor_image_sha256"] = self.provenance.hash_file(anchor_path)
                job["anchor_policy_version"] = self.provenance.policy_version()
                job["anchor_provenance"] = "sha256"
            changed = True
        elif job.get("anchor_image_sha256"):
            if not job.get("anchor_policy_version"):
                job["anchor_policy_version"] = self.provenance.policy_version()
                changed = True
            if not job.get("anchor_provenance"):
                job["anchor_provenance"] = "sha256"
                changed = True
        elif not job.get("anchor_provenance"):
            job["anchor_provenance"] = "legacy_path_only"
            changed = True
        return changed

    def ensure_image_job_target_guides(self, job: dict[str, Any]) -> bool:
        pose_family = str(job.get("pose_family") or "")
        guides = [path for path in self.provenance.guide_images().get(pose_family, []) if path.exists()]
        if not guides:
            return False
        changed = False
        input_files = [str(item) for item in job.get("input_files", []) or []]
        anchor_path = str(job.get("anchor_image_path") or "")
        insert_at = 1 if anchor_path and input_files and input_files[0] == anchor_path else 0
        for guide in guides:
            guide_text = str(guide)
            if guide_text not in input_files:
                input_files.insert(insert_at, guide_text)
                insert_at += 1
                changed = True
        target_paths = [str(path) for path in guides]
        target_hashes = {path.name: self.provenance.hash_file(path) for path in guides}
        if job.get("target_guide_paths") != target_paths:
            job["target_guide_paths"] = target_paths
            changed = True
        if job.get("target_guide_sha256") != target_hashes:
            job["target_guide_sha256"] = target_hashes
            changed = True
        if changed:
            job["input_files"] = input_files[:self.provenance.max_inputs()]
        return changed

    def ensure_candidate_image_job_task_ids(self, candidate: dict[str, Any]) -> bool:
        changed = False
        jobs = candidate_image_jobs(candidate)
        for job in jobs:
            changed = ensure_image_job_task_id(candidate, job) or changed
            changed = self.ensure_anchor_image_provenance(job) or changed
            changed = self.ensure_image_job_target_guides(job) or changed
        if jobs:
            candidate["codex_image_jobs"] = jobs
            candidate["codex_image_job"] = jobs[0]
        return changed

    def store_candidate_image_job(self, candidate: dict[str, Any], updated_job: dict[str, Any]) -> None:
        freeze_model_record(self.model_resolver, updated_job)
        ensure_image_job_task_id(candidate, updated_job)
        self.ensure_anchor_image_provenance(updated_job)
        self.ensure_image_job_target_guides(updated_job)
        job_id = str(updated_job.get("job_id", ""))
        jobs = candidate_image_jobs(candidate)
        replaced = False
        next_jobs = []
        for job in jobs:
            ensure_image_job_task_id(candidate, job)
            if str(job.get("job_id", "")) == job_id:
                next_jobs.append(updated_job)
                replaced = True
            else:
                next_jobs.append(job)
        if not replaced:
            next_jobs.append(updated_job)
        candidate["codex_image_jobs"] = next_jobs
        candidate["codex_image_job"] = next_jobs[0] if next_jobs else None
