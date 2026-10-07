"""Own one candidate image queue, native worker and execution graph.

External suppliers stay lazy. Internal edges resolve only this owner; constructing
the graph never accesses a repository, user, artifact or model provider.
"""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import threading
from pathlib import Path
from typing import Any
from ..runtime.image_worker import ImageWorkerRuntime, ThreadFactory
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import pinned
from .image_job_metadata import ImageJobMetadata, ProvenanceDependencies, candidate_image_jobs, ensure_image_job_task_id
from .file_ports import AccessoryProvenanceFiles
from .candidate_repository import CandidateRepository, CandidateStoreDependencies
from .image_job_queue import ImageJobQueue
from .image_worker_diagnostics import ImageWorkerDiagnostics
from .image_job_execution import ImageJobExecution
from . import candidate_repository as candidate_ports
from . import image_job_queue_ports as queue_ports
from . import image_worker_diagnostic_ports as diagnostic_ports
from . import image_job_execution_ports as execution_ports


@dataclass(frozen=True)
class CandidateFiles:
    runtime_repository: Callable[[], candidate_ports.PostgresRuntimeRepository | None]
    directory: Callable[[], Path]
    safe_id: Callable[[Any], str]
    created_at: Callable[[candidate_ports.Record, Path], int]
    updated_at: Callable[[candidate_ports.Record, Path], int]


@dataclass(frozen=True)
class QueueStorage:
    CONFIG_PATH: Callable[[], Path]
    load_config: Callable[[], Callable[[], queue_ports.Record]]
    save_config: Callable[[], Callable[[queue_ports.Record], None]]
    runtime_postgres_repository_or_none: Callable[[], Callable[[], object | None]]
    _business_files: Callable[[], queue_ports.QueueFiles]
    HTTPException: Callable[[], type[queue_ports.HTTPException]]


@dataclass(frozen=True)
class QueueMetadata:
    accessory_uid: Callable[[], Callable[[queue_ports.Record], str]]
    file_stem_identifier: Callable[[], Callable[[Path], str]]
    accessory_material_type: Callable[[], Callable[[queue_ports.Record], str]]
    ensure_pose_collection_image_jobs: Callable[[], Callable[[queue_ports.Record], bool]]
    public_output_url: Callable[[], Callable[[Path], str]]
    resolve_service_path: Callable[[], Callable[[str], Path]]
    preprocess_object_clean_sprites: Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class QueueLimits:
    IMAGE_JOB_QUEUED_STATUSES: Callable[[], queue_ports.Set[str]]
    MAX_PARALLEL_IMAGE_WORKERS: Callable[[], int]


@dataclass(frozen=True)
class DiagnosticMedia:
    _business_files: Callable[[], diagnostic_ports.DiagnosticFiles]
    resolve_service_path: Callable[[], diagnostic_ports.ResolvePath]
    safe_name: Callable[[], Callable[[str], str]]
    IMAGE_WORKER_LOG_DIR: Callable[[], Path]


@dataclass(frozen=True)
class ExecutionFiles:
    _business_files: Callable[[], execution_ports.ExecutionFiles]
    _image_files: Callable[[], execution_ports.ExecutionImages]
    IMAGE_WORKER_LOG_DIR: Callable[[], Path]
    ROOT: Callable[[], Path]
    safe_name: Callable[[], Callable[[str], str]]
    resolve_service_path: Callable[[], Callable[[str], Path]]
    public_output_url: Callable[[], Callable[[Path], str]]


@dataclass(frozen=True)
class ExecutionEvidence:
    image_job_prompt: Callable[[], Callable[[execution_ports.Record], str]]
    bounded_text: Callable[[], Callable[[Any, int], str]]


@dataclass(frozen=True)
class ExecutionProviders:
    LOCAL_CODEX_IMAGE_PROVIDER: Callable[[], str]
    CURSOR_IMAGE2_PROVIDER: Callable[[], str]
    CURSOR_IMAGE2_QUEUE_STATUS: Callable[[], str]
    CODEX_IMAGE_WORKER_QUEUE_STATUS: Callable[[], str]
    MAX_IMAGE_WORKER_INPUTS: Callable[[], int]
    cursor_image2_settings: Callable[[], Callable[[], execution_ports.Record]]
    cursor_image2_payload: Callable[[], Callable[[execution_ports.Record, list[str], execution_ports.Record], execution_ports.Record]]
    cursor_auth_headers: Callable[[], Callable[[str], dict[str, str]]]
    extract_cursor_image2_bytes: Callable[[], Callable[[execution_ports.Record, execution_ports.Record], bytes]]
    windows_worker_base_url: Callable[[], Callable[[], str]]
    windows_worker_headers: Callable[[], Callable[[], dict[str, str]]]
    windows_worker_image_timeout_seconds: Callable[[], Callable[[], float]]
    windows_worker_image_response_bytes: Callable[[], Callable[[execution_ports.Record], bytes]]
    masked_url_for_status: Callable[[], Callable[[str], str]]


class ImageJobs:
    """The graph is complete before native task admission can start."""
    def __init__(self, *, provenance: ProvenanceDependencies,
                 resolver: ResolverProvider, files: AccessoryProvenanceFiles,
                 threads: Callable[[], ThreadFactory], scope: Callable[[], AbstractContextManager],
                 candidates: CandidateFiles, storage: QueueStorage,
                 metadata: QueueMetadata, limits: QueueLimits,
                 diagnostic_media: DiagnosticMedia,
                 diagnostic_policy: diagnostic_ports.ImageDiagnosticPolicy,
                 execution_files: ExecutionFiles, evidence: ExecutionEvidence,
                 providers: ExecutionProviders):
        self.lock = threading.RLock()
        self.worker = ImageWorkerRuntime(target=lambda: self.queue.image_worker_loop,
                                         threads=threads, scope=scope)
        self.metadata = ImageJobMetadata(provenance, resolver, files=files)
        self.candidates = CandidateRepository(CandidateStoreDependencies(
            runtime_repository=candidates.runtime_repository, directory=candidates.directory,
            lock=lambda: self.lock,
            ensure_task_ids=lambda candidate: self.metadata.ensure_candidate_image_job_task_ids(candidate),
            safe_id=candidates.safe_id, created_at=candidates.created_at, updated_at=candidates.updated_at,
        ))
        self.diagnostics = ImageWorkerDiagnostics(
            media=diagnostic_ports.ImageDiagnosticMedia(
                _business_files=diagnostic_media._business_files,
                resolve_service_path=diagnostic_media.resolve_service_path,
                safe_name=diagnostic_media.safe_name,
                IMAGE_WORKER_LOG_DIR=diagnostic_media.IMAGE_WORKER_LOG_DIR,
                read_image_worker_log_tail=lambda: self.diagnostics.read_image_worker_log_tail,
            ),
            runtime=diagnostic_ports.ImageDiagnosticRuntime(
                _image_worker_processes=lambda: self.worker.processes,
                image_worker_process_alive=lambda: self.diagnostics.image_worker_process_alive,
                codex_process_has_log_open=lambda: self.diagnostics.codex_process_has_log_open,
                image_job_has_live_worker=lambda: self.diagnostics.image_job_has_live_worker,
            ), policy=diagnostic_policy,
        )
        self.queue = ImageJobQueue(
            storage=queue_ports.ImageQueueStorage(
                _candidate_store_lock=lambda: self.lock,
                CONFIG_PATH=storage.CONFIG_PATH, load_config=storage.load_config,
                save_config=storage.save_config,
                runtime_postgres_repository_or_none=storage.runtime_postgres_repository_or_none,
                load_accessory_candidate=lambda: self.candidates.load_accessory_candidate,
                save_accessory_candidate=lambda: self.candidates.save_accessory_candidate,
                list_accessory_candidate_records=lambda: self.candidates.list_accessory_candidate_records,
                _business_files=storage._business_files, HTTPException=storage.HTTPException,
            ),
            metadata=queue_ports.ImageQueueMetadata(
                ensure_image_job_task_id=lambda: ensure_image_job_task_id,
                ensure_candidate_image_job_task_ids=lambda: self.metadata.ensure_candidate_image_job_task_ids,
                candidate_image_jobs=lambda: candidate_image_jobs,
                store_candidate_image_job=lambda: self.metadata.store_candidate_image_job,
                accessory_uid=metadata.accessory_uid,
                file_stem_identifier=metadata.file_stem_identifier,
                accessory_material_type=metadata.accessory_material_type,
                ensure_pose_collection_image_jobs=metadata.ensure_pose_collection_image_jobs,
                image_job_output_path=lambda: self.diagnostics.image_job_output_path,
                public_output_url=metadata.public_output_url,
                resolve_service_path=metadata.resolve_service_path,
                preprocess_object_clean_sprites=metadata.preprocess_object_clean_sprites,
            ),
            execution=queue_ports.ImageQueueExecution(
                _image_worker_runtime=lambda: self.worker,
                IMAGE_JOB_QUEUED_STATUSES=limits.IMAGE_JOB_QUEUED_STATUSES,
                MAX_PARALLEL_IMAGE_WORKERS=limits.MAX_PARALLEL_IMAGE_WORKERS,
                next_queued_image_job=lambda: self.queue.next_queued_image_job,
                update_image_worker_status=lambda: self.queue.update_image_worker_status,
                run_image_generation_job=lambda: self.run_image_generation_job,
            ),
        )
        self.execution = ImageJobExecution(
            files=execution_ports.ImageExecutionFiles(
                _business_files=execution_files._business_files, _image_files=execution_files._image_files,
                image_job_output_path=lambda: self.diagnostics.image_job_output_path,
                IMAGE_WORKER_LOG_DIR=execution_files.IMAGE_WORKER_LOG_DIR,
                ROOT=execution_files.ROOT, safe_name=execution_files.safe_name,
                resolve_service_path=execution_files.resolve_service_path,
                public_output_url=execution_files.public_output_url,
            ),
            evidence=execution_ports.ImageExecutionEvidence(
                mutate_candidate_image_job=lambda: self.queue.mutate_candidate_image_job,
                update_image_worker_status=lambda: self.queue.update_image_worker_status,
                _image_worker_processes=lambda: self.worker.processes,
                image_job_prompt=evidence.image_job_prompt,
                codex_log_has_generated_image=lambda: self.diagnostics.codex_log_has_generated_image,
                classify_image_worker_failure=lambda: self.diagnostics.classify_image_worker_failure,
                bounded_text=evidence.bounded_text,
            ),
            providers=execution_ports.ImageExecutionProviders(
                LOCAL_CODEX_IMAGE_PROVIDER=providers.LOCAL_CODEX_IMAGE_PROVIDER,
                CURSOR_IMAGE2_PROVIDER=providers.CURSOR_IMAGE2_PROVIDER,
                CURSOR_IMAGE2_QUEUE_STATUS=providers.CURSOR_IMAGE2_QUEUE_STATUS,
                CODEX_IMAGE_WORKER_QUEUE_STATUS=providers.CODEX_IMAGE_WORKER_QUEUE_STATUS,
                MAX_IMAGE_WORKER_INPUTS=providers.MAX_IMAGE_WORKER_INPUTS,
                cursor_image2_settings=providers.cursor_image2_settings,
                cursor_image2_payload=providers.cursor_image2_payload,
                cursor_auth_headers=providers.cursor_auth_headers,
                extract_cursor_image2_bytes=providers.extract_cursor_image2_bytes,
                run_codex_image_job=lambda: self.execution.run_codex_image_job,
                run_cursor_image2_job=lambda: self.execution.run_cursor_image2_job,
                run_cos_codex_image_job=lambda: self.execution.run_cos_codex_image_job,
                windows_worker_base_url=providers.windows_worker_base_url,
                windows_worker_headers=providers.windows_worker_headers,
                windows_worker_image_timeout_seconds=providers.windows_worker_image_timeout_seconds,
                windows_worker_image_response_bytes=providers.windows_worker_image_response_bytes,
                masked_url_for_status=providers.masked_url_for_status,
            ),
        )
        def execute(path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
            return self.execution.run_image_generation_job(path, candidate, job)
        self.run_image_generation_job = pinned(resolver, argument=2)(execute)
