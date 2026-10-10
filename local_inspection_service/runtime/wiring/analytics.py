"""Static application wiring; original narrow business ports remain the boundary.

Only the canonical assembler consumes this result. Business components receive
their existing narrow ports; no application-entry callback is used.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import MutableMapping
from typing import Any, Callable
import contextvars
import _thread
from ..application_values import ApplicationValues
from typing import Any
from typing import Callable
from local_inspection_service.analytics.cost_repository import CostPaths
from local_inspection_service.analytics.cost_composition import CostServices
from local_inspection_service.analytics.cost_repository import CostStoreDependencies
from local_inspection_service.records.audit import coerce_record_timestamp as _coerce_record_timestamp
from local_inspection_service.detection.task_identity import sanitize_ai_detection_task_id
import local_inspection_service.analytics.cost_composition
import local_inspection_service.analytics.cost_repository
import local_inspection_service.analytics.costs
import local_inspection_service.detection.task_store
import local_inspection_service.pipeline.task_store
import local_inspection_service.runtime.repository_access
import local_inspection_service.training.auto_optimization_state_store
import local_inspection_service.training.record_store
coerce_record_timestamp = _coerce_record_timestamp

@dataclass(frozen=True)
class AnalyticsWiringInputs:
    _auto_optimization_state_store: Callable[[], local_inspection_service.training.auto_optimization_state_store.AutoOptimizationStateStore]
    _detection_task_store: Callable[[], local_inspection_service.detection.task_store.DetectionTaskStore]
    _pipeline_task_store: Callable[[], local_inspection_service.pipeline.task_store.PipelineTaskStore]
    _runtime_repository_access: Callable[[], local_inspection_service.runtime.repository_access.RuntimeRepositoryAccess]
    _training_records: Callable[[], local_inspection_service.training.record_store.TrainingRecordStore]

@dataclass(frozen=True)
class AnalyticsAssembly:
    _cost_ledger: local_inspection_service.analytics.costs.CostLedger
    _cost_paths: local_inspection_service.analytics.cost_repository.CostPaths
    _cost_repository: local_inspection_service.analytics.cost_repository.CostRepository
    _cost_services: local_inspection_service.analytics.cost_composition.CostServices
    api_cost_collect_records: Callable[..., Any]
    api_cost_store_payloads: Callable[..., Any]
    api_cost_summary: Callable[..., Any]
    api_cost_training_records: Callable[..., Any]
    api_cost_walk_usage: Callable[..., Any]

def assemble_analytics(values: ApplicationValues, environment: MutableMapping[str, str], ports: AnalyticsWiringInputs) -> AnalyticsAssembly:
    _cost_paths = CostPaths(values.DATA_DIR, values.DATA_ANALYSIS_RECORDS_PATH, values.AI_DETECTION_TASKS_PATH, values.PIPELINE_TASKS_PATH, values.AUTO_OPTIMIZE_DIR, values.AI_PROFILE_CACHE_PATH)
    _cost_services = CostServices(CostStoreDependencies(paths=lambda paths=_cost_paths: paths, runtime_repository=ports._runtime_repository_access().runtime_postgres_repository_or_none, detection_tasks=ports._detection_task_store().load_ai_detection_tasks, pipeline_tasks=ports._pipeline_task_store().load_pipeline_tasks, auto_states=ports._auto_optimization_state_store().list_auto_optimize_states, training_tasks=ports._training_records().load_training_task_records, sanitize_task_id=sanitize_ai_detection_task_id), timestamp=coerce_record_timestamp)
    _cost_repository = _cost_services.repository
    _cost_ledger = _cost_services.ledger
    api_cost_walk_usage = _cost_ledger.walk_usage
    api_cost_store_payloads = _cost_repository.store_payloads
    api_cost_training_records = _cost_ledger.training_records
    api_cost_collect_records = _cost_ledger.collect_records
    api_cost_summary = _cost_ledger.summary
    return AnalyticsAssembly(
        _cost_ledger=_cost_ledger,
        _cost_paths=_cost_paths,
        _cost_repository=_cost_repository,
        _cost_services=_cost_services,
        api_cost_collect_records=api_cost_collect_records,
        api_cost_store_payloads=api_cost_store_payloads,
        api_cost_summary=api_cost_summary,
        api_cost_training_records=api_cost_training_records,
        api_cost_walk_usage=api_cost_walk_usage,
    )
