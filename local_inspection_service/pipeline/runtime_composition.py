"""Pipeline native execution and stage/Agent transitions share actual owners."""
from __future__ import annotations
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import threading
from ..model_profiles.dependencies import ResolverProvider
from .query_composition import PipelineQueries
from ..pipeline.task_mutations import PipelineTaskMutations
from ..pipeline.task_mutations_ports import MutationStorage, MutationAccess
from ..pipeline.stage_composition import PipelineStages
from ..pipeline.stage_composition import (
    ActivationPolicyInputs,
    ActivationStorageInputs,
    PipelineAiIdentityInputs,
    PipelineAiAccessoriesInputs,
    PipelineAiAccessInputs,
    PipelineAiProjectionInputs,
    TrainingJobLookupInputs,
    TrainingStatusEffectsInputs,
    StageAdvancePolicyInputs,
    StageAdvanceAssetsInputs,
    StageAdvanceJobsInputs,
    StageAdvanceRuntimeInputs,
    ReconciliationRegistryInputs,
    ReconciliationCallsInputs,
)
from ..agent.pipeline_composition import AgentPipelineWorkflows
from ..agent.pipeline_composition import (
    AgentConversationRuntimeInputs,
    AgentDecisionTextInputs,
    AgentPipelineEvidenceInputs,
    AgentDecisionAccessoriesInputs,
    AgentDecisionContextCallsInputs,
    AgentDecisionPolicyValuesInputs,
    AgentDecisionInvocationSettingsInputs,
    AgentDecisionCodecInputs,
    AgentDecisionFlowCallsInputs,
    AgentActionStateInputs,
    AgentActionAdvanceInputs,
    AgentActionJobsInputs,
    AgentActionPoseInputs,
)
from ..pipeline.execution_composition import PipelineExecution
from ..pipeline.execution_composition import (
    PipelineAutoAgentTasksInputs,
    PipelineAutoAgentDecisionInputs,
    PipelineAutoAgentExecutionInputs,
    PipelineAutoAgentSchedulingInputs,
    PipelineAdvanceTasksInputs,
    PipelineAdvancePolicyInputs,
    PipelineAdvanceExecutionInputs,
    PipelineAdvanceSchedulingInputs,
    PipelineRecommendationTasksInputs,
    PipelineRecommendationExecutionInputs,
    PipelineRecommendationSchedulingInputs,
)
Record = dict[str, Any]
Getter = Callable[[], Callable[..., Any]]

@dataclass(frozen=True)
class RuntimeMutationStorage:
    runtime_postgres_repository_or_none: Callable[[], Callable[[], Any]]

@dataclass(frozen=True)
class RuntimeStageAdvanceRuntimeInputs:
    monotonic: Getter
    clock: Getter
    print: Getter

@dataclass(frozen=True)
class RuntimeAgentPipelineEvidenceInputs:
    orchestration: Callable[[], Callable[[Record], Record]]
    image_config: Callable[[], Callable[[], Record]]
    missing_assets: Callable[[], Callable[[Record, Record, Record], list[str]]]
    pose_tool: Callable[[], str]

@dataclass(frozen=True)
class RuntimePipelineAutoAgentTasksInputs:
    orchestration: Callable[[], Callable[[Record], Record]]
    max_steps: Callable[[], int]
    pause: Callable[[], Callable[..., Any]]
    deepcopy: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class RuntimePipelineAutoAgentDecisionInputs:
    scope_config: Callable[[], Callable[[Record, Record | None], Record]]
    load_config: Callable[[], Callable[[], Record]]
    now: Callable[[], Callable[[], Any]]

@dataclass(frozen=True)
class RuntimePipelineAdvanceTasksInputs:
    deepcopy: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class RuntimePipelineAdvancePolicyInputs:
    cancelled_error: Callable[[], type[Exception]]
    http_error: Callable[[], type[Exception]]
    orchestration: Callable[[], Callable[[Record], Record]]
    pause: Callable[[], Callable[..., Any]]
    bounded_text: Callable[[], Callable[[Any, int], str]]

class PipelineRuntimeWorkflows:
    """Construct inert domains in dependency order; each native owner keeps its lifecycle."""
    def __init__(self, *, queries: PipelineQueries, model_resolver: ResolverProvider,
                 scope: Callable[[], AbstractContextManager],
                 mutations_storage: RuntimeMutationStorage,
                 mutations_access: MutationAccess,
                 stages_activation_policy: ActivationPolicyInputs,
                 stages_activation_storage: ActivationStorageInputs,
                 stages_pipeline_ai_identity: PipelineAiIdentityInputs,
                 stages_pipeline_ai_accessories: PipelineAiAccessoriesInputs,
                 stages_pipeline_ai_access: PipelineAiAccessInputs,
                 stages_pipeline_ai_projection: PipelineAiProjectionInputs,
                 stages_training_job_lookup: TrainingJobLookupInputs,
                 stages_training_status_effects: TrainingStatusEffectsInputs,
                 stages_stage_advance_policy: StageAdvancePolicyInputs,
                 stages_stage_advance_assets: StageAdvanceAssetsInputs,
                 stages_stage_advance_jobs: StageAdvanceJobsInputs,
                 stages_stage_advance_runtime: RuntimeStageAdvanceRuntimeInputs,
                 stages_reconciliation_registry: ReconciliationRegistryInputs,
                 stages_reconciliation_calls: ReconciliationCallsInputs,
                 agent_conversation_runtime: AgentConversationRuntimeInputs,
                 agent_decision_text: AgentDecisionTextInputs,
                 agent_pipeline_evidence: RuntimeAgentPipelineEvidenceInputs,
                 agent_decision_accessories: AgentDecisionAccessoriesInputs,
                 agent_decision_context_calls: AgentDecisionContextCallsInputs,
                 agent_decision_policy_values: AgentDecisionPolicyValuesInputs,
                 agent_decision_invocation_settings: AgentDecisionInvocationSettingsInputs,
                 agent_decision_codec: AgentDecisionCodecInputs,
                 agent_decision_flow_calls: AgentDecisionFlowCallsInputs,
                 agent_action_state: AgentActionStateInputs,
                 agent_action_jobs: AgentActionJobsInputs,
                 agent_action_pose: AgentActionPoseInputs,
                 execution_auto_tasks: RuntimePipelineAutoAgentTasksInputs,
                 execution_auto_decision: RuntimePipelineAutoAgentDecisionInputs,
                 execution_auto_execution: PipelineAutoAgentExecutionInputs,
                 execution_auto_scheduling: PipelineAutoAgentSchedulingInputs,
                 execution_advance_tasks: RuntimePipelineAdvanceTasksInputs,
                 execution_advance_policy: RuntimePipelineAdvancePolicyInputs,
                 execution_advance_execution: PipelineAdvanceExecutionInputs,
                 execution_advance_scheduling: PipelineAdvanceSchedulingInputs,
                 execution_recommendation_execution: PipelineRecommendationExecutionInputs,
                 execution_recommendation_scheduling: PipelineRecommendationSchedulingInputs):
        self.queries=queries
        self.runtime=queries.persistence.runtime
        self.model_resolver=model_resolver
        self.mutations = PipelineTaskMutations(
            storage=MutationStorage(
                runtime_postgres_repository_or_none=mutations_storage.runtime_postgres_repository_or_none,
                save_pipeline_task=lambda: self.save_pipeline_task,
                save_pipeline_tasks=lambda: self.save_pipeline_tasks,
                _pipeline_tasks_lock=lambda: self.runtime.task_lock,
                load_pipeline_tasks=lambda: self.load_pipeline_tasks,
                load_pipeline_task=lambda: self.load_pipeline_task,
                save_pipeline_task_batch_changes=lambda: self.save_pipeline_task_batch_changes,
            ),
            access=MutationAccess(
                sanitize_ai_detection_task_id=mutations_access.sanitize_ai_detection_task_id,
                record_mutable_by_user=mutations_access.record_mutable_by_user,
            ),
        )
        self.stages = PipelineStages(
            queries=queries, runtime=self.runtime,
            activation_policy=ActivationPolicyInputs(
                HTTPException=stages_activation_policy.HTTPException,
                accessory_lookup_by_id=stages_activation_policy.accessory_lookup_by_id,
                clean_ai_detection_task_name=stages_activation_policy.clean_ai_detection_task_name,
                sanitize_ai_detection_task_id=stages_activation_policy.sanitize_ai_detection_task_id,
            ),
            activation_storage=ActivationStorageInputs(
                current_owner_fields=stages_activation_storage.current_owner_fields,
                find_ai_detection_task=stages_activation_storage.find_ai_detection_task,
                save_ai_detection_task=stages_activation_storage.save_ai_detection_task,
                serialize_ai_detection_task=stages_activation_storage.serialize_ai_detection_task,
            ),
            pipeline_ai_identity=PipelineAiIdentityInputs(
                safe_record_id=stages_pipeline_ai_identity.safe_record_id,
                sanitize_ai_detection_task_id=stages_pipeline_ai_identity.sanitize_ai_detection_task_id,
                ai_detection_task_model_id=stages_pipeline_ai_identity.ai_detection_task_model_id,
            ),
            pipeline_ai_accessories=PipelineAiAccessoriesInputs(
                accessory_lookup_by_id=stages_pipeline_ai_accessories.accessory_lookup_by_id,
                accessory_material_type=stages_pipeline_ai_accessories.accessory_material_type,
            ),
            pipeline_ai_access=PipelineAiAccessInputs(
                source=stages_pipeline_ai_access.source,
                record_visible_to_user=stages_pipeline_ai_access.record_visible_to_user,
                load_ai_detection_tasks=stages_pipeline_ai_access.load_ai_detection_tasks,
            ),
            pipeline_ai_projection=PipelineAiProjectionInputs(
                clean_ai_detection_task_name=stages_pipeline_ai_projection.clean_ai_detection_task_name,
                now=stages_pipeline_ai_projection.now,
            ),
            training_job_lookup=TrainingJobLookupInputs(
                load=stages_training_job_lookup.load,
                path=stages_training_job_lookup.path,
                public=stages_training_job_lookup.public,
            ),
            training_status_effects=TrainingStatusEffectsInputs(
                orchestration=stages_training_status_effects.orchestration,
                set_stage=stages_training_status_effects.set_stage,
            ),
            stage_advance_policy=StageAdvancePolicyInputs(
                recommend=stages_stage_advance_policy.recommend,
                orchestration=stages_stage_advance_policy.orchestration,
                pause=stages_stage_advance_policy.pause,
                training_quality=stages_stage_advance_policy.training_quality,
                link_model=stages_stage_advance_policy.link_model,
                http_error=stages_stage_advance_policy.http_error,
                cancelled_error=stages_stage_advance_policy.cancelled_error,
            ),
            stage_advance_assets=StageAdvanceAssetsInputs(
                load_config=stages_stage_advance_assets.load_config,
                save_config=stages_stage_advance_assets.save_config,
                prepare=stages_stage_advance_assets.prepare,
                materialize=stages_stage_advance_assets.materialize,
                normalize=stages_stage_advance_assets.normalize,
            ),
            stage_advance_jobs=StageAdvanceJobsInputs(
                request_type=stages_stage_advance_jobs.request_type,
                sample_generation=stages_stage_advance_jobs.sample_generation,
                training=stages_stage_advance_jobs.training,
                task_name=stages_stage_advance_jobs.task_name,
                log_samples=stages_stage_advance_jobs.log_samples,
                log_training=stages_stage_advance_jobs.log_training,
            ),
            stage_advance_runtime=StageAdvanceRuntimeInputs(
                persist_progress=lambda: self.persist_pipeline_task_progress,
                monotonic=stages_stage_advance_runtime.monotonic,
                clock=stages_stage_advance_runtime.clock,
                print=stages_stage_advance_runtime.print,
            ),
            reconciliation_registry=ReconciliationRegistryInputs(
                timeout=stages_reconciliation_registry.timeout,
                now=stages_reconciliation_registry.now,
            ),
            reconciliation_calls=ReconciliationCallsInputs(
                load_agent_config=stages_reconciliation_calls.load_agent_config,
                supported=stages_reconciliation_calls.supported,
                training_finder=stages_reconciliation_calls.training_finder,
                orchestration=stages_reconciliation_calls.orchestration,
            ),
        )
        self.agent = AgentPipelineWorkflows(
            queries=queries, model_resolver=model_resolver,
            conversation_runtime=AgentConversationRuntimeInputs(
                orchestration=agent_conversation_runtime.orchestration,
                now=agent_conversation_runtime.now,
                uuid=agent_conversation_runtime.uuid,
                limit=agent_conversation_runtime.limit,
            ),
            decision_text=AgentDecisionTextInputs(
                bounded=agent_decision_text.bounded,
            ),
            pipeline_evidence=AgentPipelineEvidenceInputs(
                orchestration=agent_pipeline_evidence.orchestration,
                image_config=agent_pipeline_evidence.image_config,
                missing_assets=agent_pipeline_evidence.missing_assets,
                training_job=lambda: self.linked_training_job,
                pose_tool=agent_pipeline_evidence.pose_tool,
            ),
            decision_accessories=AgentDecisionAccessoriesInputs(
                lookup=agent_decision_accessories.lookup,
                material=agent_decision_accessories.material,
            ),
            decision_context_calls=AgentDecisionContextCallsInputs(
                stage_order=agent_decision_context_calls.stage_order,
            ),
            decision_policy_values=AgentDecisionPolicyValuesInputs(
                actions=agent_decision_policy_values.actions,
                targets=agent_decision_policy_values.targets,
            ),
            decision_invocation_settings=AgentDecisionInvocationSettingsInputs(
                load=agent_decision_invocation_settings.load,
                supported=agent_decision_invocation_settings.supported,
                prompt=agent_decision_invocation_settings.prompt,
            ),
            decision_codec=AgentDecisionCodecInputs(
                dumps=agent_decision_codec.dumps,
                parse=agent_decision_codec.parse,
            ),
            decision_flow_calls=AgentDecisionFlowCallsInputs(
                chat=agent_decision_flow_calls.chat,
            ),
            action_state=AgentActionStateInputs(
                orchestration=agent_action_state.orchestration,
                now=agent_action_state.now,
                pause=agent_action_state.pause,
                bounded=agent_action_state.bounded,
                http_error_type=agent_action_state.http_error_type,
            ),
            action_advance=AgentActionAdvanceInputs(
                mark=lambda: self.mark_pipeline_task_advancing,
                sync=lambda: self.sync_pipeline_task,
                advance=lambda: self.advance_pipeline_task,
            ),
            action_jobs=AgentActionJobsInputs(
                delete=agent_action_jobs.delete,
            ),
            action_pose=AgentActionPoseInputs(
                photo_flow=agent_action_pose.photo_flow,
                skip_legacy=agent_action_pose.skip_legacy,
                plan=agent_action_pose.plan,
                ensure_calls=agent_action_pose.ensure_calls,
                config=agent_action_pose.config,
                execute=agent_action_pose.execute,
            ),
        )
        self.execution = PipelineExecution(
            persistence=queries.persistence, model_resolver=model_resolver, scope=scope,
            auto_tasks=PipelineAutoAgentTasksInputs(
                needs_agent=lambda: self.pipeline_task_needs_auto_agent,
                orchestration=execution_auto_tasks.orchestration,
                signature=lambda: self.pipeline_task_decision_signature,
                max_steps=execution_auto_tasks.max_steps,
                pause=execution_auto_tasks.pause,
                append_conversation=lambda: self.agent_mcp_append_conversation,
                deepcopy=execution_auto_tasks.deepcopy,
            ),
            auto_decision=PipelineAutoAgentDecisionInputs(
                scope_config=execution_auto_decision.scope_config,
                load_config=execution_auto_decision.load_config,
                decide=lambda: self.agent_pipeline_decide,
                commit=lambda: self.commit_pipeline_agent_turn,
                now=execution_auto_decision.now,
            ),
            auto_execution=PipelineAutoAgentExecutionInputs(
                identity=execution_auto_execution.identity,
                traceback=execution_auto_execution.traceback,
                stderr=execution_auto_execution.stderr,
            ),
            auto_scheduling=PipelineAutoAgentSchedulingInputs(
                thread=execution_auto_scheduling.thread,
            ),
            advance_tasks=PipelineAdvanceTasksInputs(
                sync=lambda: self.sync_pipeline_task,
                deepcopy=execution_advance_tasks.deepcopy,
            ),
            advance_policy=PipelineAdvancePolicyInputs(
                advance=lambda: self.advance_pipeline_task,
                cancelled_error=execution_advance_policy.cancelled_error,
                http_error=execution_advance_policy.http_error,
                orchestration=execution_advance_policy.orchestration,
                pause=execution_advance_policy.pause,
                bounded_text=execution_advance_policy.bounded_text,
            ),
            advance_execution=PipelineAdvanceExecutionInputs(
                identity=execution_advance_execution.identity,
                scope_config=execution_advance_execution.scope_config,
                load_config=execution_advance_execution.load_config,
                clock=execution_advance_execution.clock,
                traceback=execution_advance_execution.traceback,
                stderr=execution_advance_execution.stderr,
                print=execution_advance_execution.print,
            ),
            advance_scheduling=PipelineAdvanceSchedulingInputs(
                event=execution_advance_scheduling.event,
                thread=execution_advance_scheduling.thread,
            ),
            recommendation_tasks=PipelineRecommendationTasksInputs(
                next_stage=lambda: self.pipeline_next_recommendation_stage,
                ready=lambda: self.pipeline_recommendation_ready,
                signature=lambda: self.pipeline_recommendation_signature,
            ),
            recommendation_execution=PipelineRecommendationExecutionInputs(
                identity=execution_recommendation_execution.identity,
                recommend=execution_recommendation_execution.recommend,
                clock=execution_recommendation_execution.clock,
                traceback=execution_recommendation_execution.traceback,
                stderr=execution_recommendation_execution.stderr,
            ),
            recommendation_scheduling=PipelineRecommendationSchedulingInputs(
                thread=execution_recommendation_scheduling.thread,
            ),
        )

    def save_pipeline_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        return self.queries.persistence.save_pipeline_task(task)

    def save_pipeline_tasks(self, tasks: list[dict[str, Any]]) -> None:
        return self.queries.persistence.save_pipeline_tasks(tasks)

    def load_pipeline_tasks(self) -> list[dict[str, Any]]:
        return self.queries.persistence.load_pipeline_tasks()

    def load_pipeline_task(self, task_id: str) -> dict[str, Any] | None:
        return self.queries.persistence.load_pipeline_task(task_id)

    def save_pipeline_task_batch_changes(self, tasks: list[dict[str, Any]], changed_tasks: list[dict[str, Any]]) -> None:
        return self.mutations.save_pipeline_task_batch_changes(tasks, changed_tasks)

    def persist_pipeline_task_progress(self, task_id: str, *, job_note: str | None=None, progress: int | None=None, status: str | None=None) -> None:
        return self.mutations.persist_pipeline_task_progress(task_id, job_note=job_note, progress=progress, status=status)

    def linked_training_job(self, task: dict[str, Any], load_task: Callable[[Path], dict[str, Any] | None] | None=None) -> dict[str, Any] | None:
        return self.stages.linked_training_job(task, load_task)

    def mark_pipeline_task_advancing(self, task: dict[str, Any]) -> None:
        return self.mutations.mark_pipeline_task_advancing(task)

    def sync_pipeline_task(self, task: dict[str, Any], load_task: Callable[[Path], dict[str, Any] | None] | None=None) -> bool:
        return self.stages.sync_pipeline_task(task, load_task)

    def advance_pipeline_task(self, task: dict[str, Any], cancel_event: 'threading.Event | None'=None) -> None:
        return self.stages.advance_pipeline_task(task, cancel_event)

    def pipeline_task_needs_auto_agent(self, task: dict[str, Any]) -> bool:
        return self.stages.pipeline_task_needs_auto_agent(task)

    def pipeline_task_decision_signature(self, task: dict[str, Any]) -> str:
        return self.stages.pipeline_task_decision_signature(task)

    def agent_mcp_append_conversation(self, task: dict[str, Any], role: str, message: str, *, action: str='', reason: str='', target_stage: str='', source: str='', needs_user: bool=False, agent_error: str='') -> dict[str, Any]:
        return self.agent.agent_mcp_append_conversation(task, role, message, action=action, reason=reason, target_stage=target_stage, source=source, needs_user=needs_user, agent_error=agent_error)

    def agent_pipeline_decide(self, task: dict[str, Any], config: dict[str, Any], *, user_message: str | None=None, trigger: str='chat') -> dict[str, Any]:
        return self.agent.agent_pipeline_decide(task, config, user_message=user_message, trigger=trigger)

    def commit_pipeline_agent_turn(self, task: dict[str, Any], config: dict[str, Any], user: dict[str, Any] | None, user_message: str | None, decision: dict[str, Any], trigger: str, pending_advances: list[str] | None=None) -> dict[str, Any]:
        return self.agent.commit_pipeline_agent_turn(task, config, user, user_message, decision, trigger, pending_advances)

    def pipeline_next_recommendation_stage(self, task: dict[str, Any]) -> str:
        return self.stages.pipeline_next_recommendation_stage(task)

    def pipeline_recommendation_ready(self, task: dict[str, Any], stage: str) -> bool:
        return self.stages.pipeline_recommendation_ready(task, stage)

    def pipeline_recommendation_signature(self, task: dict[str, Any], stage: str) -> str:
        return self.stages.pipeline_recommendation_signature(task, stage)
