"""Own pipeline records, state guards and terminal training synchronization."""
from __future__ import annotations
from collections.abc import Callable
from typing import Any, Protocol
from .runtime_state import PipelineRuntimeState
from .task_store import PipelineTaskStore, PipelineTaskPaths, PipelineTaskRows, PipelineTaskRepository
from .state_store import PipelineStateStore, PipelineStatePaths, PipelineStateRows, PipelineStateRepository
from .training_sync import PipelineTrainingSync, PipelineTrainingRecords, PipelineTrainingModels, TrainingCandidateSink
from ..model_profiles.dependencies import ResolverProvider
Record = dict[str, Any]

class PipelinePersistenceRepository(PipelineTaskRepository, PipelineStateRepository, Protocol):
    pass

class PipelinePersistence:
    """Allocate inert owners; repository, identity and model selection remain operation-time."""
    def __init__(self, *, repository: Callable[[], PipelinePersistenceRepository | None],
                 task_paths: PipelineTaskPaths, task_rows: PipelineTaskRows,
                 resolver: Callable[[], ResolverProvider], state_paths: PipelineStatePaths,
                 state_rows: PipelineStateRows, training_models: PipelineTrainingModels,
                 normalize_method: Callable[[], Callable[[str | None], str]],
                 clean_id: Callable[[], Callable[[Any], str]], sync_candidate: TrainingCandidateSink):
        self.runtime = PipelineRuntimeState()
        self.tasks = PipelineTaskStore(repository, task_paths, task_rows, resolver)
        self.state = PipelineStateStore(repository, state_paths, state_rows,
            guard=lambda: self.runtime.state_lock)
        self.training = PipelineTrainingSync(
            guard=lambda: self.runtime.task_lock,
            records=PipelineTrainingRecords(load=lambda task_id: self.load_pipeline_task(task_id),
                save=lambda task: self.save_pipeline_task(task)),
            models=training_models, normalize_method=normalize_method, clean_id=clean_id,
            sync_candidate=sync_candidate)

    def load_pipeline_tasks(self) -> list[dict[str, Any]]:
        return self.tasks.load_pipeline_tasks()

    def save_pipeline_tasks(self, tasks: list[dict[str, Any]]) -> None:
        return self.tasks.save_pipeline_tasks(tasks)

    def load_pipeline_task(self, task_id: str) -> dict[str, Any] | None:
        return self.tasks.load_pipeline_task(task_id)

    def save_pipeline_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        return self.tasks.save_pipeline_task(task)

    def delete_pipeline_task_row(self, task_id: str) -> bool:
        return self.tasks.delete_pipeline_task_row(task_id)

    def load_pipeline_state(self) -> dict[str, list[str]]:
        return self.state.load_pipeline_state()

    def save_pipeline_state(self, state: dict[str, list[str]]) -> None:
        return self.state.save_pipeline_state(state)

    def save_pipeline_state_keys(self, state: dict[str, list[str]], changed_keys: set[str]) -> None:
        return self.state.save_pipeline_state_keys(state, changed_keys)

    def update_pipeline_state(self, mutator: Callable[[dict[str, list[str]]], None]) -> dict[str, list[str]]:
        return self.state.update_pipeline_state(mutator)

    def add_pipeline_accessory_id(self, accessory_id: str) -> dict[str, list[str]]:
        return self.state.add_pipeline_accessory_id(accessory_id)

    def remove_pipeline_accessory_id(self, accessory_id: str) -> dict[str, list[str]]:
        return self.state.remove_pipeline_accessory_id(accessory_id)

    def add_pipeline_pending_candidate_id(self, candidate_id: str) -> dict[str, list[str]]:
        return self.state.add_pipeline_pending_candidate_id(candidate_id)

    def remove_pipeline_pending_candidate_id(self, candidate_id: str) -> dict[str, list[str]]:
        return self.state.remove_pipeline_pending_candidate_id(candidate_id)

    def auto_optimize_task_id_from_pipeline_task(self, pipeline_task_id: str, pipeline_task: dict[str, Any] | None=None) -> str:
        return self.training.auto_optimize_task_id_from_pipeline_task(pipeline_task_id, pipeline_task)

    def sync_pipeline_training_state_from_task(self, task: dict[str, Any]) -> None:
        return self.training.sync_pipeline_training_state_from_task(task)
