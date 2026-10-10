"""Owned pipeline Agent conversation, decisions, actions and turn commit graph."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from .invocation_ports import EncodeJson
from ..pipeline.query_composition import PipelineQueries
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import pinned
Record = dict[str, Any]
from .pipeline_action_ports import PauseAction, DeleteActionJob, PlanActionPose, ApplyAction, AppendTurn, AgentActionState, AgentActionAdvance, AgentActionJobs, AgentActionPolicy, AgentActionPose, AgentActionCalls, AgentTurnCalls
from .pipeline_decision_ports import AgentDecisionText, AgentConversationRuntime, AgentPipelineEvidence, AgentDecisionAccessories, AgentDecisionContextCalls, AgentDecisionPolicyValues, AgentDecisionRuleCalls, AgentDecisionInvocationSettings, AgentDecisionCodec, AgentDecisionFlowCalls
from .conversation import AgentConversation
from .decision_context import AgentDecisionContext
from .decision_policy import AgentDecisionPolicy
from .decision_flow import AgentDecisionFlow
from .pipeline_actions import AgentPipelineActions
from .pipeline_turns import AgentPipelineTurns

@dataclass(frozen=True)
class AgentConversationRuntimeInputs:
    orchestration: Callable[[], Callable[[Record], Record]]
    now: Callable[[], Callable[[], int]]
    uuid: Callable[[], Callable[[], UUID]]
    limit: Callable[[], int]

@dataclass(frozen=True)
class AgentDecisionTextInputs:
    bounded: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class AgentPipelineEvidenceInputs:
    orchestration: Callable[[], Callable[[Record], Record]]
    image_config: Callable[[], Callable[[], Record]]
    missing_assets: Callable[[], Callable[[Record, Record, Record], list[str]]]
    training_job: Callable[[], Callable[[Record], Record | None]]
    pose_tool: Callable[[], str]

@dataclass(frozen=True)
class AgentDecisionAccessoriesInputs:
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    material: Callable[[], Callable[[Record], str]]

@dataclass(frozen=True)
class AgentDecisionContextCallsInputs:
    stage_order: Callable[[], list[str]]

@dataclass(frozen=True)
class AgentDecisionPolicyValuesInputs:
    actions: Callable[[], set[str]]
    targets: Callable[[], set[str]]

@dataclass(frozen=True)
class AgentDecisionInvocationSettingsInputs:
    load: Callable[[], Callable[[], Record]]
    supported: Callable[[], Callable[[Record], bool]]
    prompt: Callable[[], str]

@dataclass(frozen=True)
class AgentDecisionCodecInputs:
    dumps: Callable[[], EncodeJson]
    parse: Callable[[], Callable[[str], Record]]

@dataclass(frozen=True)
class AgentDecisionFlowCallsInputs:
    chat: Callable[[], Callable[[list[dict[str, str]], Record | None], str]]

@dataclass(frozen=True)
class AgentActionStateInputs:
    http_error_type: Callable[[], type[Exception]]
    orchestration: Callable[[], Callable[[Record], Record]]
    now: Callable[[], Callable[[], int]]
    pause: Callable[[], PauseAction]
    bounded: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class AgentActionAdvanceInputs:
    mark: Callable[[], Callable[[Record], None]]
    sync: Callable[[], Callable[[Record], bool]]
    advance: Callable[[], Callable[[Record], None]]

@dataclass(frozen=True)
class AgentActionJobsInputs:
    delete: Callable[[], DeleteActionJob]

@dataclass(frozen=True)
class AgentActionPoseInputs:
    photo_flow: Callable[[], Callable[[Record, Record], bool]]
    skip_legacy: Callable[[], Callable[[Record, Record, Record], Record]]
    plan: Callable[[], PlanActionPose]
    ensure_calls: Callable[[], Callable[[Record, Record], Record]]
    config: Callable[[], Callable[[], Record]]
    execute: Callable[[], Callable[[Record, Record], bool]]

class AgentPipelineWorkflows:
    """Inert services; model binding precedes actual decision receiver selection."""
    def __init__(self, *, queries: PipelineQueries, model_resolver: ResolverProvider,
                 conversation_runtime: AgentConversationRuntimeInputs,
                 decision_text: AgentDecisionTextInputs,
                 pipeline_evidence: AgentPipelineEvidenceInputs,
                 decision_accessories: AgentDecisionAccessoriesInputs,
                 decision_context_calls: AgentDecisionContextCallsInputs,
                 decision_policy_values: AgentDecisionPolicyValuesInputs,
                 decision_invocation_settings: AgentDecisionInvocationSettingsInputs,
                 decision_codec: AgentDecisionCodecInputs,
                 decision_flow_calls: AgentDecisionFlowCallsInputs,
                 action_state: AgentActionStateInputs,
                 action_advance: AgentActionAdvanceInputs,
                 action_jobs: AgentActionJobsInputs,
                 action_pose: AgentActionPoseInputs):
        self.queries = queries
        self.model_resolver = model_resolver
        self.conversation = AgentConversation(
            AgentConversationRuntime(
                orchestration=conversation_runtime.orchestration,
                now=conversation_runtime.now,
                uuid=conversation_runtime.uuid,
                limit=conversation_runtime.limit,
            ),
            AgentDecisionText(
                bounded=decision_text.bounded,
            ),
        )
        self.context = AgentDecisionContext(
            AgentPipelineEvidence(
                orchestration=pipeline_evidence.orchestration,
                image_config=pipeline_evidence.image_config,
                missing_assets=pipeline_evidence.missing_assets,
                training_job=pipeline_evidence.training_job,
                pose_tool=pipeline_evidence.pose_tool,
            ),
            AgentDecisionAccessories(
                canonical=lambda: self.canonical_pipeline_accessory_ids,
                counts=lambda: self.normalize_pipeline_accessory_counts,
                lookup=decision_accessories.lookup,
                material=decision_accessories.material,
                detection=lambda: self.normalize_pipeline_detection_method,
            ),
            AgentDecisionContextCalls(
                quality=lambda: self.agent_pipeline_quality_signals,
                stage_order=decision_context_calls.stage_order,
            ),
            AgentDecisionText(
                bounded=decision_text.bounded,
            ),
        )
        self.policy = AgentDecisionPolicy(
            AgentDecisionPolicyValues(
                actions=decision_policy_values.actions,
                targets=decision_policy_values.targets,
            ),
            AgentDecisionRuleCalls(
                rerun=lambda: self._rule_rerun_failed_stage,
                normalize=lambda: self.normalize_agent_pipeline_decision,
            ),
            AgentDecisionText(
                bounded=decision_text.bounded,
            ),
        )
        self.decision = AgentDecisionFlow(
            AgentDecisionInvocationSettings(
                load=decision_invocation_settings.load,
                supported=decision_invocation_settings.supported,
                prompt=decision_invocation_settings.prompt,
            ),
            AgentDecisionCodec(
                dumps=decision_codec.dumps,
                parse=decision_codec.parse,
            ),
            AgentDecisionFlowCalls(
                context=lambda: self.agent_pipeline_context,
                chat=decision_flow_calls.chat,
                normalize=lambda: self.normalize_agent_pipeline_decision,
                rule=lambda: self.agent_pipeline_rule_decision,
            ),
        )
        self.actions = AgentPipelineActions(
            AgentActionState(
                orchestration=action_state.orchestration,
                now=action_state.now,
                pause=action_state.pause,
                bounded=action_state.bounded,
                http_error_type=action_state.http_error_type,
            ),
            AgentActionAdvance(
                mark=action_advance.mark,
                sync=action_advance.sync,
                advance=action_advance.advance,
            ),
            AgentActionJobs(
                delete=action_jobs.delete,
            ),
            AgentActionPolicy(
                normalize=lambda: self.normalize_pipeline_detection_method,
                uses_training=lambda: self.pipeline_method_uses_training,
            ),
            AgentActionPose(
                photo_flow=action_pose.photo_flow,
                skip_legacy=action_pose.skip_legacy,
                plan=action_pose.plan,
                ensure_calls=action_pose.ensure_calls,
                config=action_pose.config,
                execute=action_pose.execute,
            ),
            AgentActionCalls(
                safe_advance=lambda: self.agent_safe_advance,
                reset=lambda: self.reset_pipeline_task_to_stage,
            ),
        )
        self.turns = AgentPipelineTurns(
            AgentTurnCalls(
                append=lambda: self.agent_mcp_append_conversation,
                apply=lambda: self.apply_agent_pipeline_decision,
            ),
        )

    def canonical_pipeline_accessory_ids(self, config: Record, ids: list[str]) -> list[str]:
        return self.queries.canonical_pipeline_accessory_ids(config, ids)

    def normalize_pipeline_accessory_counts(self, config: Record, ids: list[str], counts: Any = None) -> dict[str, int]:
        return self.queries.normalize_pipeline_accessory_counts(config, ids, counts)

    def normalize_pipeline_detection_method(self, value: str | None) -> str:
        return self.queries.normalize_pipeline_detection_method(value)

    def pipeline_method_uses_training(self, value: str | None) -> bool:
        return self.queries.pipeline_method_uses_training(value)

    def agent_pipeline_decide(self, task: Record, config: Record, *, user_message: str | None = None, trigger: str = 'chat') -> Record:
        return pinned(self.model_resolver)(self._execute_decision)(task, config, user_message=user_message, trigger=trigger)

    def agent_mcp_append_conversation(self, task: dict[str, Any], role: str, message: str, *, action: str='', reason: str='', target_stage: str='', source: str='', needs_user: bool=False, agent_error: str='') -> dict[str, Any]:
        return self.conversation.agent_mcp_append_conversation(task, role, message, action=action, reason=reason, target_stage=target_stage, source=source, needs_user=needs_user, agent_error=agent_error)

    def agent_pipeline_quality_signals(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return self.context.agent_pipeline_quality_signals(task, config)

    def agent_pipeline_context(self, task: dict[str, Any], config: dict[str, Any], user_message: str | None, trigger: str) -> dict[str, Any]:
        return self.context.agent_pipeline_context(task, config, user_message, trigger)

    def normalize_agent_pipeline_decision(self, parsed: dict[str, Any]) -> dict[str, Any]:
        return self.policy.normalize_agent_pipeline_decision(parsed)

    def _rule_rerun_failed_stage(self, stage: str) -> tuple[str, str]:
        return self.policy._rule_rerun_failed_stage(stage)

    def agent_pipeline_rule_decision(self, task: dict[str, Any], user_message: str | None, trigger: str) -> dict[str, Any]:
        return self.policy.agent_pipeline_rule_decision(task, user_message, trigger)

    def _execute_decision(self, task: dict[str, Any], config: dict[str, Any], *, user_message: str | None=None, trigger: str='chat') -> dict[str, Any]:
        return self.decision.agent_pipeline_decide(task, config, user_message=user_message, trigger=trigger)

    def agent_safe_advance(self, task: dict[str, Any], config: dict[str, Any], pending_advances: list[str] | None=None) -> None:
        return self.actions.agent_safe_advance(task, config, pending_advances)

    def reset_pipeline_task_to_stage(self, task: dict[str, Any], target: str, user: dict[str, Any] | None) -> None:
        return self.actions.reset_pipeline_task_to_stage(task, target, user)

    def apply_agent_pipeline_decision(self, task: dict[str, Any], config: dict[str, Any], decision: dict[str, Any], user: dict[str, Any] | None, *, trigger: str='chat', pending_advances: list[str] | None=None) -> None:
        return self.actions.apply_agent_pipeline_decision(task, config, decision, user, trigger=trigger, pending_advances=pending_advances)

    def commit_pipeline_agent_turn(self, task: dict[str, Any], config: dict[str, Any], user: dict[str, Any] | None, user_message: str | None, decision: dict[str, Any], trigger: str, pending_advances: list[str] | None=None) -> dict[str, Any]:
        return self.turns.commit_pipeline_agent_turn(task, config, user, user_message, decision, trigger, pending_advances)
