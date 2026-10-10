"""Training and pipeline persistence with explicit, graph-local completion edges."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from ..runtime.training_tasks import TrainingTaskRuntime
from ..model_profiles.dependencies import ResolverProvider
from ..pipeline.persistence_composition import PipelinePersistence, PipelinePersistenceRepository
from ..pipeline.task_store import PipelineTaskPaths, PipelineTaskRows
from ..pipeline.state_store import PipelineStatePaths, PipelineStateRows
from ..pipeline.training_sync import PipelineTrainingModels
from ..detection.training_candidate_sync import (
    TrainingCandidateSync, CandidateTrainingRecords, StopCaptureForModel)
from .account_state_composition import TrainingAccountState, TrainingConfiguration
from .state_composition import TrainingRecordAccess
from .record_store import TrainingRows
from .task_lifecycle import TrainingTaskWrites, RequireTrainingAccess
from .task_views import TrainingViewAccess
from .user_state import TrainingStateAccess
from .task_models import TrainingTaskModels

Record = dict[str, Any]


@dataclass(frozen=True)
class TrainingAccountInputs:
    runtime: TrainingTaskRuntime
    storage: TrainingRecordAccess
    rows: TrainingRows
    writes: TrainingTaskWrites
    require_access: RequireTrainingAccess
    view_access: TrainingViewAccess
    defaults: Callable[[], Record]
    legacy_owner: Callable[[], str]
    access: TrainingStateAccess
    configuration: TrainingConfiguration


@dataclass(frozen=True)
class PipelinePersistenceInputs:
    repository: Callable[[], PipelinePersistenceRepository | None]
    task_paths: PipelineTaskPaths
    task_rows: PipelineTaskRows
    resolver: Callable[[], ResolverProvider]
    state_paths: PipelineStatePaths
    state_rows: PipelineStateRows
    link_model: Callable[[Record], None]
    normalize_method: Callable[[], Callable[[str | None], str]]
    clean_id: Callable[[], Callable[[Any], str]]


@dataclass(frozen=True)
class TrainingCandidateInputs:
    guard: Callable[[], AbstractContextManager]
    records: CandidateTrainingRecords
    clean_id: Callable[[Any], str]
    stop_capture: StopCaptureForModel


class TrainingPersistenceGraph:
    """Allocate inert owners; select dependencies only during their operations."""

    def __init__(self, *, account: TrainingAccountInputs,
                 pipeline: PipelinePersistenceInputs,
                 candidate: TrainingCandidateInputs,
                 model_specs: Callable[[], list[Record]]):
        self.models = TrainingTaskModels(specs=model_specs)
        self.candidates = TrainingCandidateSync(
            guard=candidate.guard, records=candidate.records,
            clean_id=candidate.clean_id, stop_capture=candidate.stop_capture)
        self.pipeline = PipelinePersistence(
            repository=pipeline.repository, task_paths=pipeline.task_paths,
            task_rows=pipeline.task_rows, resolver=pipeline.resolver,
            state_paths=pipeline.state_paths, state_rows=pipeline.state_rows,
            training_models=PipelineTrainingModels(
                resolve=self._model_id, link=pipeline.link_model),
            normalize_method=pipeline.normalize_method, clean_id=pipeline.clean_id,
            sync_candidate=self._sync_candidate)
        self.account = TrainingAccountState(
            runtime=account.runtime, storage=account.storage, rows=account.rows,
            writes=account.writes, require_access=account.require_access,
            view_access=account.view_access, defaults=account.defaults,
            legacy_owner=account.legacy_owner, access=account.access,
            configuration=account.configuration, sync_pipeline=self._sync_pipeline)

    def _model_id(self, task: Record, job_id: str) -> str:
        return self.models.training_task_model_id(task, job_id)

    def _sync_candidate(self, task: Record, *, ai_task_id: str, model_id: str) -> None:
        return self.candidates.sync_auto_optimize_training_candidate_from_task(
            task, ai_task_id=ai_task_id, model_id=model_id)

    def _sync_pipeline(self, task: Record) -> None:
        return self.pipeline.sync_pipeline_training_state_from_task(task)
