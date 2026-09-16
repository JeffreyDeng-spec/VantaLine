"""Authorized candidate retrieval retains existing repair/refresh side effects."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from .candidate_repository import CandidateRepository, Record
from .catalog import RecordGuard


@dataclass(frozen=True)
class CandidateQueryDependencies:
    current_user: Callable[[], Record]
    audit: Callable[[Record, Path], Record]
    require_access: RecordGuard
    image_jobs: Callable[[Record], list[Record]]
    ensure_image_task_id: Callable[[Record, Record], bool]
    refresh_image_job: Callable[[Record], Record]
    store_image_job: Callable[[Record, Record], None]


class CandidateQueries:
    def __init__(self, repository: CandidateRepository, dependencies: CandidateQueryDependencies):
        self.repository = repository
        self.dependencies = dependencies

    def get_accessory_candidate(self, candidate_id: str) -> Record:
        user = self.dependencies.current_user()
        path = self.repository.dependencies.directory() / f"{candidate_id}.json"
        with self.repository.dependencies.lock():
            candidate = self.repository.load_accessory_candidate(candidate_id)
            candidate = self.dependencies.audit(candidate, path)
            self.dependencies.require_access(candidate, user)
            changed = False
            changed = self.repository.dependencies.ensure_task_ids(candidate) or changed
            for job in self.dependencies.image_jobs(candidate):
                changed = self.dependencies.ensure_image_task_id(candidate, job) or changed
                refreshed = self.dependencies.refresh_image_job(job)
                self.dependencies.store_image_job(candidate, refreshed)
                changed = True
            if changed:
                self.repository.save_accessory_candidate(path, candidate)
        return {"status": "candidate_ready", "candidate": candidate}
