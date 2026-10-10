"""Pipeline task operations and HTTP registration around explicit domain owners."""
from __future__ import annotations
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Container
from fastapi import FastAPI
from .query_composition import PipelineQueries
from .stage_composition import PipelineStages
from .execution_composition import PipelineExecution
from ..agent.pipeline_composition import AgentPipelineWorkflows
from .task_list_ports import TaskListAccess, TaskListReconciliation, TaskListPresentation
from .task_list import PipelineTaskList
from .task_list_api import register_pipeline_task_list_api

@dataclass(frozen=True)
class TaskListAccessInputs:
    current_user: Callable[[], Callable[[], Any]]
    is_admin: Callable[[], Callable[[Any], bool]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    load_ai_tasks: Callable[[], Callable[[], list[dict[str, Any]]]]
    visible: Callable[[], Callable[..., bool]]
    incoming_allowed: Callable[[], Callable[..., bool]]
    has_permission: Callable[[], Callable[..., bool]]

@dataclass(frozen=True)
class TaskListReconciliationInputs:
    monotonic: Callable[[], Callable[[], float]]
    min_interval: Callable[[], float]
    save_config: Callable[[], Callable[[dict[str, Any]], Any]]
    sync_ready_ai_tasks: Callable[[], Callable[..., bool]]

@dataclass(frozen=True)
class TaskListPresentationInputs:
    trained_specs: Callable[[], Callable[..., Any]]
    optimize_states: Callable[[], Callable[[], Any]]
    public_agent_config: Callable[[], Callable[[], dict[str, Any]]]
    sanitize: Callable[[], Callable[..., dict[str, Any]]]
from .task_create_ports import TaskCreateAccess, TaskCreatePolicy, TaskCreateRuntime
from .task_create import PipelineTaskCreator
from .task_create_api import register_pipeline_task_create_api

@dataclass(frozen=True)
class TaskCreateAccessInputs:
    current_user: Callable[[], Callable[[], Any]]
    require_permission: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]
    is_admin: Callable[[], Callable[[Any], bool]]
    owner_fields: Callable[[], Callable[..., dict[str, Any]]]
    fallback_owner: Callable[[], Callable[[Any], str]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    accessory_lookup: Callable[[], Callable[[dict[str, Any]], dict[str, Any]]]
    load_agent_config: Callable[[], Callable[[], dict[str, Any]]]

@dataclass(frozen=True)
class TaskCreatePolicyInputs:
    normalize_expected_count: Callable[[], Callable[[Any], int]]
    assert_unique_name: Callable[[], Callable[[str, str], Any]]

@dataclass(frozen=True)
class TaskCreateRuntimeInputs:
    uuid4: Callable[[], Callable[[], Any]]
    now: Callable[[], Callable[[], float]]
    initialize_auto_optimize: Callable[[], Callable[..., Any]]
    request_user: Callable[[], Any]
from .task_update_ports import TaskUpdateAccess, TaskUpdatePolicy, TaskUpdateRuntime
from .task_update import PipelineTaskUpdater
from .task_update_api import register_pipeline_task_update_api

@dataclass(frozen=True)
class TaskUpdateAccessInputs:
    current_user: Callable[[], Callable[[], Any]]
    http_error: Callable[[], Callable[..., Exception]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[[dict[str, Any], Any], dict[str, Any]]]
    require_record_access: Callable[[], Callable[..., Any]]
    require_permission: Callable[[], Callable[..., Any]]
    assert_unique_name: Callable[[], Callable[..., Any]]
    record_owner_id: Callable[[], Callable[[dict[str, Any]], str]]

@dataclass(frozen=True)
class TaskUpdatePolicyInputs:
    detection_methods: Callable[[], Any]
    normalize_expected_count: Callable[[], Callable[[Any], int]]

@dataclass(frozen=True)
class TaskUpdateRuntimeInputs:
    now: Callable[[], Callable[[], float]]
from .accessory_routes_ports import PipelineAccessoryAccess, PipelineAccessoryCatalog
from .accessory_routes import PipelineAccessoryRoutes
from .accessory_routes_api import register_pipeline_accessory_routes_api

@dataclass(frozen=True)
class PipelineAccessoryAccessInputs:
    current_user: Callable[[], Callable[[], Any]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    http_error: Callable[[], Callable[..., Exception]]

@dataclass(frozen=True)
class PipelineAccessoryCatalogInputs:
    resolve: Callable[[], Callable[..., Any]]
    aliases: Callable[[], Callable[..., Any]]
from .task_delete_ports import TaskDeleteAccess, TaskDeleteRuntime, TaskDeleteCleanup
from .task_delete import PipelineTaskDeleter
from .task_delete_api import register_pipeline_task_delete_api

@dataclass(frozen=True)
class TaskDeleteAccessInputs:
    current_user: Callable[[], Callable[[], Any]]
    require_record_access: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]

@dataclass(frozen=True)
class TaskDeleteCleanupInputs:
    delete_dataset: Callable[[], Callable[..., Any]]
    delete_model: Callable[[], Callable[..., Any]]
    delete_training_job: Callable[[], Callable[..., Any]]
    delete_ai_task: Callable[[], Callable[..., Any]]
from .agent_feedback_ports import AgentFeedbackAccess, AgentFeedbackPolicy, AgentFeedbackRuntime
from .agent_feedback import PipelineAgentFeedback
from .agent_feedback_api import register_pipeline_agent_feedback_api

@dataclass(frozen=True)
class AgentFeedbackAccessInputs:
    current_user: Callable[[], Callable[[], Any]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    require_record_access: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]

@dataclass(frozen=True)
class AgentFeedbackPolicyInputs:
    sprite_flow: Callable[[], Callable[..., bool]]

@dataclass(frozen=True)
class AgentFeedbackRuntimeInputs:
    ensure_plan: Callable[[], Callable[..., dict[str, Any]]]
    now: Callable[[], Callable[[], int]]
    skip_legacy: Callable[[], Callable[..., dict[str, Any]]]
    mark_advancing: Callable[[], Callable[..., Any]]
    pose_calls: Callable[[], Callable[..., dict[str, Any]]]
    image_config: Callable[[], Callable[[], dict[str, Any]]]
    execute_calls: Callable[[], Callable[..., bool]]
    pause_task: Callable[[], Callable[..., Any]]
from .agent_chat_ports import AgentChatAccess, AgentChatRuntime
from .agent_chat import PipelineAgentChat
from .agent_chat_api import register_pipeline_agent_chat_api

@dataclass(frozen=True)
class AgentChatAccessInputs:
    current_user: Callable[[], Callable[[], Any]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    require_record_access: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]

@dataclass(frozen=True)
class AgentChatRuntimeInputs:
    deepcopy: Callable[[], Callable[[Any], Any]]
from .advance_control_ports import AdvanceControlAccess, AdvanceControlRuntime
from .advance_control import PipelineAdvanceController
from .advance_control_api import register_pipeline_advance_control_api

@dataclass(frozen=True)
class AdvanceControlAccessInputs:
    current_user: Callable[[], Callable[[], Any]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    require_record_access: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]

@dataclass(frozen=True)
class AdvanceControlRuntimeInputs:
    now: Callable[[], Callable[[], float]]

class PipelineTaskWorkflows:
    """Inert task graph; routes are registered explicitly in original order."""
    def __init__(self, *, queries: PipelineQueries, stages: PipelineStages, execution: PipelineExecution, agent: AgentPipelineWorkflows,
                 task_list_access: TaskListAccessInputs,
                 task_list_reconciliation: TaskListReconciliationInputs,
                 task_list_presentation: TaskListPresentationInputs,
                 task_create_access: TaskCreateAccessInputs,
                 task_create_policy: TaskCreatePolicyInputs,
                 task_create_runtime: TaskCreateRuntimeInputs,
                 task_update_access: TaskUpdateAccessInputs,
                 task_update_policy: TaskUpdatePolicyInputs,
                 task_update_runtime: TaskUpdateRuntimeInputs,
                 pipeline_accessory_access: PipelineAccessoryAccessInputs,
                 pipeline_accessory_catalog: PipelineAccessoryCatalogInputs,
                 task_delete_access: TaskDeleteAccessInputs,
                 task_delete_cleanup: TaskDeleteCleanupInputs,
                 agent_feedback_access: AgentFeedbackAccessInputs,
                 agent_feedback_policy: AgentFeedbackPolicyInputs,
                 agent_feedback_runtime: AgentFeedbackRuntimeInputs,
                 agent_chat_access: AgentChatAccessInputs,
                 agent_chat_runtime: AgentChatRuntimeInputs,
                 advance_control_access: AdvanceControlAccessInputs,
                 advance_control_runtime: AdvanceControlRuntimeInputs):
        if stages.queries is not queries or execution.persistence is not queries.persistence or agent.queries is not queries:
            raise ValueError('Pipeline task domains must share queries and persistence')
        if stages.runtime is not queries.persistence.runtime:
            raise ValueError('Pipeline task stages must share persistence runtime')
        self.queries=queries
        self.stages=stages
        self.execution=execution
        self.agent=agent
        self.runtime=queries.persistence.runtime
        self.listing = PipelineTaskList(
            TaskListAccess(
                current_user=task_list_access.current_user,
                is_admin=task_list_access.is_admin,
                load_config=task_list_access.load_config,
                scope_config=task_list_access.scope_config,
                load_ai_tasks=task_list_access.load_ai_tasks,
                visible=task_list_access.visible,
                incoming_allowed=task_list_access.incoming_allowed,
                has_permission=task_list_access.has_permission,
            ),
            TaskListReconciliation(
                task_lock=lambda: self.runtime.task_lock,
                load_tasks=lambda: self.load_pipeline_tasks,
                monotonic=task_list_reconciliation.monotonic,
                last_sync_at=lambda: self.runtime.last_sync_at,
                set_last_sync_at=lambda value: self.runtime.set_last_sync_at(value),
                min_interval=task_list_reconciliation.min_interval,
                ensure_accessories=lambda: self.ensure_pipeline_task_accessory_objects,
                save_config=task_list_reconciliation.save_config,
                sync_ai_tasks=lambda: self.sync_pipeline_ai_detection_tasks,
                sync_ready_ai_tasks=task_list_reconciliation.sync_ready_ai_tasks,
                normalize_auto_defaults=lambda: self.normalize_pipeline_task_auto_advance_defaults,
                sync_and_advance=lambda: self.sync_and_auto_advance_pipeline,
                save_tasks=lambda: self.save_pipeline_tasks,
                collect_pregen=lambda: self.collect_pipeline_recommendation_pregen,
            ),
            TaskListPresentation(
                schedule_agent=lambda: self.schedule_pipeline_auto_agent,
                schedule_advance=lambda: self.schedule_pipeline_advance,
                schedule_pregen=lambda: self.schedule_pipeline_recommendation_pregen,
                trained_specs=task_list_presentation.trained_specs,
                optimize_states=task_list_presentation.optimize_states,
                optimize_by_id=lambda: self.auto_optimize_states_by_task_id,
                public_task=lambda: self.pipeline_task_public,
                public_agent_config=task_list_presentation.public_agent_config,
                accessories_payload=lambda: self.pipeline_accessories_payload,
                sanitize=task_list_presentation.sanitize,
            ),
        )
        self.creator = PipelineTaskCreator(
            TaskCreateAccess(
                current_user=task_create_access.current_user,
                require_permission=task_create_access.require_permission,
                http_error=task_create_access.http_error,
                is_admin=task_create_access.is_admin,
                owner_fields=task_create_access.owner_fields,
                fallback_owner=task_create_access.fallback_owner,
                scope_config=task_create_access.scope_config,
                load_config=task_create_access.load_config,
                accessory_lookup=task_create_access.accessory_lookup,
                load_agent_config=task_create_access.load_agent_config,
            ),
            TaskCreatePolicy(
                canonical_accessory_ids=lambda: self.canonical_pipeline_accessory_ids,
                normalize_detection_method=lambda: self.normalize_pipeline_detection_method,
                normalize_expected_count=task_create_policy.normalize_expected_count,
                method_uses_training=lambda: self.pipeline_method_uses_training,
                normalize_accessory_counts=lambda: self.normalize_pipeline_accessory_counts,
                assert_unique_name=task_create_policy.assert_unique_name,
                next_recommendation_stage=lambda: self.pipeline_next_recommendation_stage,
            ),
            TaskCreateRuntime(
                uuid4=task_create_runtime.uuid4,
                now=task_create_runtime.now,
                lock=lambda: self.runtime.task_lock,
                activate_ai_task=lambda: self.activate_pipeline_ai_detection_task,
                save_task=lambda: self.save_pipeline_task,
                initialize_auto_optimize=task_create_runtime.initialize_auto_optimize,
                load_task=lambda: self.load_pipeline_task,
                schedule_pregen=lambda: self.schedule_pipeline_recommendation_pregen,
                request_user=task_create_runtime.request_user,
                public_task=lambda: self.pipeline_task_public,
            ),
        )
        self.updater = PipelineTaskUpdater(
            TaskUpdateAccess(
                current_user=task_update_access.current_user,
                http_error=task_update_access.http_error,
                load_config=task_update_access.load_config,
                scope_config=task_update_access.scope_config,
                load_task=lambda: self.load_pipeline_task,
                require_record_access=task_update_access.require_record_access,
                require_permission=task_update_access.require_permission,
                assert_unique_name=task_update_access.assert_unique_name,
                record_owner_id=task_update_access.record_owner_id,
            ),
            TaskUpdatePolicy(
                canonical_accessory_ids=lambda: self.canonical_pipeline_accessory_ids,
                normalize_accessory_counts=lambda: self.normalize_pipeline_accessory_counts,
                accessory_snapshot=lambda: self.pipeline_task_accessory_snapshot,
                normalize_detection_method=lambda: self.normalize_pipeline_detection_method,
                method_uses_training=lambda: self.pipeline_method_uses_training,
                detection_methods=task_update_policy.detection_methods,
                normalize_expected_count=task_update_policy.normalize_expected_count,
            ),
            TaskUpdateRuntime(
                lock=lambda: self.runtime.task_lock,
                now=task_update_runtime.now,
                save_task=lambda: self.save_pipeline_task,
                public_task=lambda: self.pipeline_task_public,
            ),
        )
        self.accessories = PipelineAccessoryRoutes(
            PipelineAccessoryAccess(
                current_user=pipeline_accessory_access.current_user,
                load_config=pipeline_accessory_access.load_config,
                scope_config=pipeline_accessory_access.scope_config,
                http_error=pipeline_accessory_access.http_error,
            ),
            PipelineAccessoryCatalog(
                resolve=pipeline_accessory_catalog.resolve,
                add_id=lambda: self.add_pipeline_accessory_id,
                aliases=pipeline_accessory_catalog.aliases,
                remove_id=lambda: self.remove_pipeline_accessory_id,
                public_payload=lambda: self.pipeline_accessories_payload,
            ),
        )
        self.deleter = PipelineTaskDeleter(
            TaskDeleteAccess(
                current_user=task_delete_access.current_user,
                load_task=lambda: self.load_pipeline_task,
                require_record_access=task_delete_access.require_record_access,
                http_error=task_delete_access.http_error,
            ),
            TaskDeleteRuntime(
                cancel_advance=lambda: self.cancel_pipeline_advance,
                lock=lambda: self.runtime.task_lock,
                delete_task_row=lambda: self.delete_pipeline_task_row,
            ),
            TaskDeleteCleanup(
                delete_dataset=task_delete_cleanup.delete_dataset,
                delete_model=task_delete_cleanup.delete_model,
                delete_training_job=task_delete_cleanup.delete_training_job,
                delete_ai_task=task_delete_cleanup.delete_ai_task,
            ),
        )
        self.feedback = PipelineAgentFeedback(
            AgentFeedbackAccess(
                current_user=agent_feedback_access.current_user,
                load_config=agent_feedback_access.load_config,
                scope_config=agent_feedback_access.scope_config,
                load_task=lambda: self.load_pipeline_task,
                require_record_access=agent_feedback_access.require_record_access,
                http_error=agent_feedback_access.http_error,
            ),
            AgentFeedbackPolicy(
                normalize_method=lambda: self.normalize_pipeline_detection_method,
                uses_training=lambda: self.pipeline_method_uses_training,
                sprite_flow=agent_feedback_policy.sprite_flow,
            ),
            AgentFeedbackRuntime(
                task_lock=lambda: self.runtime.task_lock,
                ensure_plan=agent_feedback_runtime.ensure_plan,
                now=agent_feedback_runtime.now,
                skip_legacy=agent_feedback_runtime.skip_legacy,
                mark_advancing=agent_feedback_runtime.mark_advancing,
                pose_calls=agent_feedback_runtime.pose_calls,
                image_config=agent_feedback_runtime.image_config,
                execute_calls=agent_feedback_runtime.execute_calls,
                pause_task=agent_feedback_runtime.pause_task,
                save_task=lambda: self.save_pipeline_task,
                public_task=lambda: self.pipeline_task_public,
                schedule_advance=lambda: self.schedule_pipeline_advance,
            ),
        )
        self.chat = PipelineAgentChat(
            AgentChatAccess(
                current_user=agent_chat_access.current_user,
                load_config=agent_chat_access.load_config,
                scope_config=agent_chat_access.scope_config,
                bounded_text=agent_chat_access.bounded_text,
                load_task=lambda: self.load_pipeline_task,
                require_record_access=agent_chat_access.require_record_access,
                http_error=agent_chat_access.http_error,
            ),
            AgentChatRuntime(
                task_lock=lambda: self.runtime.task_lock,
                normalize_method=lambda: self.normalize_pipeline_detection_method,
                uses_training=lambda: self.pipeline_method_uses_training,
                deepcopy=agent_chat_runtime.deepcopy,
                decide=lambda: self.agent_pipeline_decide,
                commit_turn=lambda: self.commit_pipeline_agent_turn,
                save_task=lambda: self.save_pipeline_task,
                public_task=lambda: self.pipeline_task_public,
                schedule_advance=lambda: self.schedule_pipeline_advance,
            ),
        )
        self.control = PipelineAdvanceController(
            AdvanceControlAccess(
                current_user=advance_control_access.current_user,
                load_config=advance_control_access.load_config,
                scope_config=advance_control_access.scope_config,
                load_task=lambda: self.load_pipeline_task,
                require_record_access=advance_control_access.require_record_access,
                http_error=advance_control_access.http_error,
            ),
            AdvanceControlRuntime(
                task_lock=lambda: self.runtime.task_lock,
                registry_lock=lambda: self.runtime.advance_registry_lock,
                inflight=lambda: self.runtime.advance_inflight,
                sync_task=lambda: self.sync_pipeline_task,
                now=advance_control_runtime.now,
                save_task=lambda: self.save_pipeline_task,
                public_task=lambda: self.pipeline_task_public,
                schedule_advance=lambda: self.schedule_pipeline_advance,
                cancel_advance=lambda: self.cancel_pipeline_advance,
            ),
        )

    def register_task_list(self, app: FastAPI):
        return register_pipeline_task_list_api(app, self.listing)

    def register_task_create(self, app: FastAPI):
        return register_pipeline_task_create_api(app, self.creator)

    def register_task_update(self, app: FastAPI):
        return register_pipeline_task_update_api(app, self.updater)

    def register_accessory_routes(self, app: FastAPI):
        return register_pipeline_accessory_routes_api(app, self.accessories)

    def register_task_delete(self, app: FastAPI):
        return register_pipeline_task_delete_api(app, self.deleter)

    def register_agent_feedback(self, app: FastAPI):
        return register_pipeline_agent_feedback_api(app, self.feedback)

    def register_agent_chat(self, app: FastAPI):
        return register_pipeline_agent_chat_api(app, self.chat)

    def register_advance_control(self, app: FastAPI):
        return register_pipeline_advance_control_api(app, self.control)

    def load_pipeline_tasks(self) -> list[dict[str, Any]]:
        return self.queries.persistence.load_pipeline_tasks()

    def ensure_pipeline_task_accessory_objects(self, config: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
        return self.queries.ensure_pipeline_task_accessory_objects(config, tasks)

    def sync_pipeline_ai_detection_tasks(self, tasks: list[dict[str, Any]], config: dict[str, Any], user: dict[str, Any] | None, target_user_id: str | None=None, *, ai_tasks: list[dict[str, Any]] | None=None) -> bool:
        return self.stages.sync_pipeline_ai_detection_tasks(tasks, config, user, target_user_id, ai_tasks=ai_tasks)

    def normalize_pipeline_task_auto_advance_defaults(self, tasks: list[dict[str, Any]]) -> bool:
        return self.queries.normalize_pipeline_task_auto_advance_defaults(tasks)

    def sync_and_auto_advance_pipeline(self, tasks: list[dict[str, Any]]) -> tuple[bool, list[str], list[str]]:
        return self.stages.sync_and_auto_advance_pipeline(tasks)

    def save_pipeline_tasks(self, tasks: list[dict[str, Any]]) -> None:
        return self.queries.persistence.save_pipeline_tasks(tasks)

    def collect_pipeline_recommendation_pregen(self, tasks: list[dict[str, Any]]) -> list[tuple[str, str]]:
        return self.stages.collect_pipeline_recommendation_pregen(tasks)

    def schedule_pipeline_auto_agent(self, task_ids: list[str], user: dict[str, Any] | None) -> None:
        return self.execution.schedule_pipeline_auto_agent(task_ids, user)

    def schedule_pipeline_advance(self, task_id: str, user: dict[str, Any] | None) -> bool:
        return self.execution.schedule_pipeline_advance(task_id, user)

    def schedule_pipeline_recommendation_pregen(self, items: list[tuple[str, str]], user: dict[str, Any] | None) -> None:
        return self.execution.schedule_pipeline_recommendation_pregen(items, user)

    def auto_optimize_states_by_task_id(self, states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return self.queries.auto_optimize_states_by_task_id(states)

    def pipeline_task_public(self, task: dict[str, Any], config: dict[str, Any], *, ai_task_ids: set[str] | None=None, trained_model_specs: list[dict[str, Any]] | None=None, auto_optimize_states: list[dict[str, Any]] | None=None, auto_optimize_states_by_id: dict[str, dict[str, Any]] | None=None, sanitize: bool=True) -> dict[str, Any]:
        return self.queries.pipeline_task_public(task, config, ai_task_ids=ai_task_ids, trained_model_specs=trained_model_specs, auto_optimize_states=auto_optimize_states, auto_optimize_states_by_id=auto_optimize_states_by_id, sanitize=sanitize)

    def pipeline_accessories_payload(self, config: dict[str, Any] | None=None, user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
        return self.queries.pipeline_accessories_payload(config, user, target_user_id)

    def canonical_pipeline_accessory_ids(self, config: dict[str, Any], raw_ids: list[str]) -> list[str]:
        return self.stages.canonical_pipeline_accessory_ids(config, raw_ids)

    def normalize_pipeline_detection_method(self, value: str | None) -> str:
        return self.stages.normalize_pipeline_detection_method(value)

    def pipeline_method_uses_training(self, method: str | None) -> bool:
        return self.stages.pipeline_method_uses_training(method)

    def normalize_pipeline_accessory_counts(self, config: dict[str, Any], accessory_ids: list[str], raw_counts: Any=None) -> dict[str, int]:
        return self.stages.normalize_pipeline_accessory_counts(config, accessory_ids, raw_counts)

    def pipeline_next_recommendation_stage(self, task: dict[str, Any]) -> str:
        return self.stages.pipeline_next_recommendation_stage(task)

    def activate_pipeline_ai_detection_task(self, task: dict[str, Any], config: dict[str, Any]) -> bool:
        return self.stages.activate_pipeline_ai_detection_task(task, config)

    def save_pipeline_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        return self.queries.persistence.save_pipeline_task(task)

    def load_pipeline_task(self, task_id: str) -> dict[str, Any] | None:
        return self.queries.persistence.load_pipeline_task(task_id)

    def pipeline_task_accessory_snapshot(self, config: dict[str, Any], task: dict[str, Any], accessory_ids: list[str]) -> tuple[dict[str, str], list[str]]:
        return self.queries.pipeline_task_accessory_snapshot(config, task, accessory_ids)

    def add_pipeline_accessory_id(self, accessory_id: str) -> dict[str, list[str]]:
        return self.queries.persistence.add_pipeline_accessory_id(accessory_id)

    def remove_pipeline_accessory_id(self, accessory_id: str) -> dict[str, list[str]]:
        return self.queries.persistence.remove_pipeline_accessory_id(accessory_id)

    def cancel_pipeline_advance(self, task_id: str) -> bool:
        return self.execution.cancel_pipeline_advance(task_id)

    def delete_pipeline_task_row(self, task_id: str) -> bool:
        return self.queries.persistence.delete_pipeline_task_row(task_id)

    def agent_pipeline_decide(self, task: dict[str, Any], config: dict[str, Any], *, user_message: str | None=None, trigger: str='chat') -> dict[str, Any]:
        return self.agent.agent_pipeline_decide(task, config, user_message=user_message, trigger=trigger)

    def commit_pipeline_agent_turn(self, task: dict[str, Any], config: dict[str, Any], user: dict[str, Any] | None, user_message: str | None, decision: dict[str, Any], trigger: str, pending_advances: list[str] | None=None) -> dict[str, Any]:
        return self.agent.commit_pipeline_agent_turn(task, config, user, user_message, decision, trigger, pending_advances)

    def sync_pipeline_task(self, task: dict[str, Any], load_task: Callable[[Path], dict[str, Any] | None] | None=None) -> bool:
        return self.stages.sync_pipeline_task(task, load_task)
