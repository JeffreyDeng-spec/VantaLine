"""Training task HTTP services composed around one account and execution graph."""
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from .account_state_composition import TrainingAccountState
from .native_execution_composition import TrainingExecution
from .jobs_query import JobsReadAccess, JobsTraining, TrainingJobsQuery
from .jobs_ports import ListJobs
from .task_lifecycle import RequireTrainingAccess, training_task_uses_worker
from .task_mutations import TaskMutationRecords, TrainingTaskMutations
from .launch_submission import LaunchConfiguration, LaunchInputs, TrainingLaunchSubmission
from .status_query import TrainingStatusQuery
from .dataset_catalog import FindDataset
from .dataset_input import TrainingDatasetInput
from .preview_approval import TrainingPreviewApproval
from .status_projection import StatusAccess, StatusPreview, StatusTasks, TrainingStatusProjection
from .runpod_upload_store import RunPodUploadStore
from .runpod_transfer import RunPodTrainingTransfer, TransferPaths
from .file_ports import TrainingInputFiles
from ..storage.artifacts.runtime import ArtifactRuntime
from ..schemas.training import TrainingStartRequest

Record = dict[str, Any]
SelectAccessories = Callable[[Record, list[str]], list[Record]]


class TrainingTaskFiles(TrainingInputFiles, Protocol):
    runtime_provider: Callable[[], ArtifactRuntime | None]


@dataclass(frozen=True)
class TrainingMutationAccess:
    current: Callable[[], Record]
    require: RequireTrainingAccess
    clock: Callable[[], float]


@dataclass(frozen=True)
class TrainingLaunchConfiguration:
    load: Callable[[], Record]
    scope: Callable[[Record, Record], Record]
    ensure: Callable[[], Callable[[Record, Record, Record, list[str]], bool]]
    merge: Callable[[Record, Record, Record], None]
    save: Callable[[Record], Any]


@dataclass(frozen=True)
class TrainingLaunchAccess:
    current: Callable[[], Record]
    selected: Callable[[], SelectAccessories]
    clock: Callable[[], float]
    physical_size: Callable[[], Record]


@dataclass(frozen=True)
class TrainingStatusRead:
    current: Callable[[], Record]
    admin: Callable[[Record], bool]
    load: Callable[[], Record]
    scope: Callable[[], Callable[[Record, Record, str | None], Record]]


@dataclass(frozen=True)
class TrainingDatasetAccess:
    find: FindDataset
    require: RequireTrainingAccess
    sanitize: Callable[[], Callable[[list[Any]], list[Any]]]


@dataclass(frozen=True)
class TrainingPreviewInputs:
    jobs: Callable[[], Path]
    background: Callable[[], Callable[[str | None, Record | None], str | None]]
    cache: Callable[[list[Record]], str]


@dataclass(frozen=True)
class TrainingTransferAccess:
    maximum: Callable[[], int]
    token_hash: Callable[[str], str]
    clock: Callable[[], float]
    paths: TransferPaths


class TrainingTaskWorkflows:
    def __init__(self, *, account: TrainingAccountState, execution: TrainingExecution,
                 files: TrainingTaskFiles, jobs_access: JobsReadAccess,
                 image_jobs: ListJobs, image_active: Callable[[], Collection[str]],
                 mutations: TrainingMutationAccess,
                 launch_config: TrainingLaunchConfiguration, launch: TrainingLaunchAccess,
                 status: TrainingStatusRead, dataset: TrainingDatasetAccess,
                 preview: TrainingPreviewInputs, status_access: StatusAccess,
                 status_preview: StatusPreview, transfer: TrainingTransferAccess):
        if execution.account is not account or execution.state is not account.records:
            raise ValueError('Training task services must share their account and task state')
        self.account, self.execution = account, execution
        self.jobs_query = TrainingJobsQuery(
            jobs_access,
            JobsTraining(
                lambda job: self.account.records.find_training_task(job), training_task_uses_worker,
                lambda task: self.account.records.public_training_task(task),
                lambda task, **kwargs: self.account.records.public_refreshed_training_task(task, **kwargs),
            ),
            lambda **kwargs: self.account.records.list_training_tasks(**kwargs), image_jobs, image_active,
        )
        self.task_mutations = TrainingTaskMutations(
            mutations.current, mutations.require,
            TaskMutationRecords(
                lambda job: self.account.records.find_training_task(job),
                lambda task: self.account.records.save_training_task(task),
                lambda task: self.account.records.public_training_task(task),
                lambda job, user: self.account.records.delete_training_task_record(job, user),
                lambda **kwargs: self.account.records.list_training_tasks(**kwargs),
            ),
            mutations.clock,
        )
        self.launch_submission = TrainingLaunchSubmission(
            launch.current,
            LaunchConfiguration(
                launch_config.load, launch_config.scope, launch_config.ensure,
                lambda full, user, state: self.account.set_training_state_for_user(full, user, state),
                launch_config.merge, launch_config.save,
            ),
            LaunchInputs(
                launch.selected, lambda: self.dataset_for_training,
                lambda config, request, selected, **kwargs: self.validate_approved_preview(config, request, selected, **kwargs),
            ),
            lambda request, selected, action, **kwargs: self.execution.enqueue_training_task(request, selected, action, **kwargs),
            launch.clock, launch.physical_size,
        )
        self.status_query = TrainingStatusQuery(
            status.current, status.admin, status.load, status.scope,
            lambda config, user, target: self.filtered_training_state(config, user, target),
        )
        self.upload_store = RunPodUploadStore(transfer.maximum, runtime_provider=files.runtime_provider)
        self.transfer = RunPodTrainingTransfer(
            lambda job: self.account.records.find_training_task(job), transfer.token_hash,
            transfer.clock, transfer.paths, self.upload_store, lambda: self.update_training_task,
            runtime_provider=files.runtime_provider,
        )
        self.dataset_input = TrainingDatasetInput(dataset.find, dataset.require, dataset.sanitize, files=files)
        self.preview_approval = TrainingPreviewApproval(preview.jobs, preview.background, preview.cache, files=files)
        self.status_projection = TrainingStatusProjection(
            StatusTasks(
                lambda job: self.account.records.find_training_task(job),
                lambda task: self.account.records.public_refreshed_training_task(task),
            ),
            status_access, status_preview,
        )

    def update_training_task(self, job_id: str, **values: Any) -> Record:
        return self.account.records.update_training_task(job_id, **values)

    def dataset_for_training(self, dataset_id: str, user: Record | None = None) -> Record:
        return self.dataset_input.dataset_for_training(dataset_id, user)

    def validate_approved_preview(self, config: Record, request: TrainingStartRequest,
                                  selected: list[Record], user: Record | None = None) -> None:
        return self.preview_approval.validate_approved_preview(config, request, selected, user)

    def filtered_training_state(self, config: Record, user: Record | None = None,
                                target_user_id: str | None = None) -> Record:
        return self.status_projection.filtered_training_state(config, user, target_user_id)
