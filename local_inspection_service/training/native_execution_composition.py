"""Training submission and pinned native execution around owned task state."""
from collections.abc import Callable
from pathlib import Path
from typing import Any
from ..model_profiles.dependencies import ResolverProvider
from .account_state_composition import TrainingAccountState
from .runner import (TrainingRunner, TrainingRunnerRecords, TrainingRunnerPaths,
                     TrainingDatasetExecution, TrainingLocalExecution)
from .file_ports import TrainingRunnerFiles
from .submission import (TrainingSubmission, TrainingSubmissionPolicy,
                         TrainingSubmissionIdentity, TrainingSubmissionRecords,
                         TrainingSubmissionThreads, TrainingThreadFactory)
from ..schemas.training import TrainingStartRequest


class TrainingExecution:
    def __init__(self, *, account: TrainingAccountState, files: TrainingRunnerFiles,
                 paths: TrainingRunnerPaths,
                 datasets: TrainingDatasetExecution, local: TrainingLocalExecution,
                 resolver: ResolverProvider, policy: TrainingSubmissionPolicy,
                 identity: TrainingSubmissionIdentity, create_thread: TrainingThreadFactory):
        self.account = account
        self.state = account.records
        self.runner = TrainingRunner(
            files=files,
            records=TrainingRunnerRecords(
                find=lambda job_id: self.state.find_training_task(job_id),
                path=lambda job_id: self.state.training_task_path(job_id),
                load=lambda: self.load_training_task,
                update_provider=lambda: self.update_training_task,
                sync=lambda job_id: self.account.sync_training_state_from_task(job_id),
            ),
            paths=paths, datasets=datasets, local=local, resolver=resolver,
        )
        self.submission = TrainingSubmission(
            policy=policy, identity=identity,
            records=TrainingSubmissionRecords(
                save=lambda task: self.state.save_training_task(task),
                public=lambda task: self.state.public_training_task(task),
            ),
            threads=TrainingSubmissionThreads(
                target=lambda: self.run_training_task,
                create=create_thread,
                records=lambda: self.state.runtime.threads,
            ),
            runtime=self.state.runtime,
        )

    def load_training_task(self, path: Path) -> dict[str, Any] | None:
        return self.state.load_training_task(path)

    def update_training_task(self, job_id: str, **values: Any) -> dict[str, Any]:
        return self.state.update_training_task(job_id, **values)

    def run_training_task(self, job_id: str) -> None:
        return self.runner.run_training_task(job_id)

    def enqueue_training_task(self, request: TrainingStartRequest,
                              selected: list[dict[str, Any]], action: str,
                              dataset: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.submission.enqueue_training_task(request, selected, action, dataset)
