"""Pending pipeline candidates: progress refresh, canonicalization and publication."""
import json
from dataclasses import dataclass
from typing import Any
from .candidate_flow_ports import CandidateStorage, CandidateProgress, CandidateProjection

@dataclass(frozen=True)
class PipelineCandidateFlow:
    storage: CandidateStorage
    progress: CandidateProgress
    projection: CandidateProjection

    def canonical_pipeline_accessory_ids(self, config: dict[str, Any], raw_ids: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw_id in raw_ids or []:
            resolved = self.projection.resolve_accessory_id()(config, str(raw_id))
            if not resolved:
                continue
            item_id, _ = resolved
            if item_id in seen:
                continue
            seen.add(item_id)
            result.append(item_id)
        return result


    def candidate_confirmed_accessory_id(self, candidate: dict[str, Any]) -> str:
        return str(candidate.get("confirmed_accessory_id") or "").strip()


    def pipeline_candidate_job_status(self, candidate: dict[str, Any]) -> tuple[str, int, str]:
        jobs = self.progress.candidate_image_jobs()(candidate)
        if not jobs:
            return "ready", 100, "已上传，待确认"
        statuses = [str(job.get("status") or "") for job in jobs]
        progress = max(0, min(100, int(sum(int(job.get("progress") or 0) for job in jobs) / max(1, len(jobs)))))
        if any(status in self.progress.IMAGE_JOB_ACTIVE_STATUSES() for status in statuses):
            if any(status == "running" for status in statuses):
                return "running", progress, "生成中"
            return "running", progress, "排队中"
        if any(status == "failed" for status in statuses):
            return "failed", 100, "建档失败"
        if all(status == "completed" for status in statuses):
            return "ready", 100, "已生成，待确认"
        return statuses[0] or "ready", progress, "已上传，待确认"


    def pipeline_candidate_public(self, candidate: dict[str, Any]) -> dict[str, Any]:
        candidate = self.projection.enrich_record_audit_fields()(candidate)
        status, progress, status_text = self.projection.pipeline_candidate_job_status()(candidate)
        return {
            "id": str(candidate.get("id") or ""),
            "name": str(candidate.get("name") or "新配件"),
            "material_type": self.projection.accessory_material_type()(candidate),
            "status": status,
            "status_text": status_text,
            "progress": progress,
            "created_at": int(candidate.get("created_at") or 0),
            "updated_at": int(candidate.get("updated_at") or candidate.get("created_at") or 0),
            "owner_user_id": str(candidate.get("owner_user_id") or self.projection.LEGACY_OWNER_ID()),
            "owner_username": str(candidate.get("owner_username") or self.projection.record_owner_username()(candidate)),
        }


    def refresh_pipeline_candidate(self, candidate_id: str) -> tuple[dict[str, Any] | None, bool]:
        path = self.storage.ACCESSORY_CANDIDATES_DIR() / f"{candidate_id}.json"
        with self.storage._candidate_store_lock():
            repository = self.storage.runtime_postgres_repository_or_none()()
            if repository is not None:
                try:
                    candidate = self.storage.load_accessory_candidate()(candidate_id)
                except self.storage.HTTPException() as exc:
                    if exc.status_code != 404:
                        raise
                    return None, True
            else:
                if not self.storage._business_files().exists(path):
                    return None, True
                try:
                    candidate = json.loads(self.storage._business_files().read_text(path, encoding="utf-8"))
                except json.JSONDecodeError:
                    return None, True
            candidate = self.projection.enrich_record_audit_fields()(candidate, path)
            if self.progress.candidate_confirmed_accessory_id()(candidate):
                return candidate, True
            changed = self.progress.ensure_candidate_image_job_task_ids()(candidate)
            for job in self.progress.candidate_image_jobs()(candidate):
                refreshed = self.progress.refresh_codex_image_job()(job)
                if any(refreshed.get(key) != job.get(key) for key in ("status", "progress", "completed_at", "failed_at", "error", "output_path", "output_url", "log_path")):
                    self.progress.store_candidate_image_job()(candidate, refreshed)
                    changed = True
            if changed:
                self.storage.save_accessory_candidate()(path, candidate)
            return candidate, False


    def pipeline_accessories_payload(self,
        config: dict[str, Any] | None = None,
        user: dict[str, Any] | None = None,
        target_user_id: str | None = None,
    ) -> dict[str, Any]:
        config = config or self.storage.load_config()()
        accessories_by_id = self.projection.accessory_lookup_by_id()(config)
        state = self.storage.load_pipeline_state()()
        accessory_ids: list[str] = []
        seen_accessories: set[str] = set()
        for item_id in state["accessory_ids"]:
            resolved = self.projection.resolve_accessory_id()(config, item_id)
            if not resolved:
                continue
            canonical_id, _ = resolved
            if canonical_id in seen_accessories:
                continue
            seen_accessories.add(canonical_id)
            accessory_ids.append(canonical_id)
        if accessory_ids != state["accessory_ids"]:
            def prune_accessories(latest: dict[str, list[str]]) -> None:
                latest["accessory_ids"] = accessory_ids

            self.storage.update_pipeline_state()(prune_accessories)
        pending_candidates: list[dict[str, Any]] = []
        kept_candidate_ids: list[str] = []
        remove_candidate_ids: list[str] = []
        migrated_accessory_ids: list[str] = []
        for candidate_id in state["pending_candidate_ids"]:
            candidate, remove = self.progress.refresh_pipeline_candidate()(candidate_id)
            if remove:
                confirmed_id = self.progress.candidate_confirmed_accessory_id()(candidate or {})
                resolved = self.projection.resolve_accessory_id()(config, confirmed_id) if confirmed_id else None
                if resolved:
                    confirmed_accessory_id, _ = resolved
                    if confirmed_accessory_id not in seen_accessories:
                        seen_accessories.add(confirmed_accessory_id)
                        accessory_ids.insert(0, confirmed_accessory_id)
                    migrated_accessory_ids.append(confirmed_accessory_id)
                remove_candidate_ids.append(candidate_id)
                continue
            if candidate:
                kept_candidate_ids.append(candidate_id)
                if not user or self.projection.record_visible_to_user()(candidate, user, target_user_id):
                    pending_candidates.append(self.projection.pipeline_candidate_public()(candidate))
        if remove_candidate_ids or migrated_accessory_ids:
            def prune_candidates(latest: dict[str, list[str]]) -> None:
                remove_ids = set(remove_candidate_ids)
                latest["pending_candidate_ids"] = [item_id for item_id in latest["pending_candidate_ids"] if item_id not in remove_ids]
                for item_id in reversed(migrated_accessory_ids):
                    if item_id and item_id not in latest["accessory_ids"]:
                        latest["accessory_ids"].insert(0, item_id)
                latest["accessory_ids"] = self.projection.canonical_pipeline_accessory_ids()(config, latest["accessory_ids"])

            self.storage.update_pipeline_state()(prune_candidates)
        return {
            "accessories": [self.projection.serialize_accessory()(accessories_by_id[item_id]) for item_id in accessory_ids],
            "pending_candidates": pending_candidates,
        }
