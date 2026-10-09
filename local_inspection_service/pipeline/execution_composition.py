"""Compose three independent pinned native pipeline runtimes around owned records."""
from __future__ import annotations
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, ContextManager
from .persistence_composition import PipelinePersistence
from .auto_agent_runtime import PipelineAutoAgentRuntime
from .auto_agent_runtime_ports import AutoAgentTasks, AutoAgentDecision, AutoAgentExecution, AutoAgentScheduling
from .advance_runtime import PipelineAdvanceRuntime
from .advance_runtime_ports import AdvanceTasks, AdvancePolicy, AdvanceExecution, AdvanceScheduling
from .recommendation_runtime import PipelineRecommendationRuntime
from .recommendation_runtime_ports import RecommendationTasks, RecommendationExecution, RecommendationScheduling
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import pinned
Record = dict[str, Any]

@dataclass(frozen=True)
class PipelineAutoAgentTasksInputs:
    needs_agent: Callable[[], Callable[[Record], bool]]
    orchestration: Callable[[], Callable[[Record], Record]]
    signature: Callable[[], Callable[[Record], str]]
    max_steps: Callable[[], int]
    pause: Callable[[], Callable[..., Any]]
    append_conversation: Callable[[], Callable[..., Any]]
    deepcopy: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class PipelineAutoAgentDecisionInputs:
    scope_config: Callable[[], Callable[[Record, Record | None], Record]]
    load_config: Callable[[], Callable[[], Record]]
    decide: Callable[[], Callable[..., Record]]
    commit: Callable[[], Callable[..., Any]]
    now: Callable[[], Callable[[], Any]]

@dataclass(frozen=True)
class PipelineAutoAgentExecutionInputs:
    identity: Callable[[], Any]
    traceback: Callable[[], Callable[..., Any]]
    stderr: Callable[[], Any]

@dataclass(frozen=True)
class PipelineAutoAgentSchedulingInputs:
    thread: Callable[[], Callable[..., Any]]

@dataclass(frozen=True)
class PipelineAdvanceTasksInputs:
    sync: Callable[[], Callable[[Record], Any]]
    deepcopy: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class PipelineAdvancePolicyInputs:
    advance: Callable[[], Callable[..., Any]]
    cancelled_error: Callable[[], type[Exception]]
    http_error: Callable[[], type[Exception]]
    orchestration: Callable[[], Callable[[Record], Record]]
    pause: Callable[[], Callable[..., Any]]
    bounded_text: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class PipelineAdvanceExecutionInputs:
    identity: Callable[[], Any]
    scope_config: Callable[[], Callable[[Record, Record | None], Record]]
    load_config: Callable[[], Callable[[], Record]]
    clock: Callable[[], Callable[[], float]]
    traceback: Callable[[], Callable[..., Any]]
    stderr: Callable[[], Any]
    print: Callable[[], Callable[..., Any]]

@dataclass(frozen=True)
class PipelineAdvanceSchedulingInputs:
    event: Callable[[], Callable[[], Any]]
    thread: Callable[[], Callable[..., Any]]

@dataclass(frozen=True)
class PipelineRecommendationTasksInputs:
    next_stage: Callable[[], Callable[[Record], str]]
    ready: Callable[[], Callable[[Record, str], bool]]
    signature: Callable[[], Callable[[Record, str], str]]

@dataclass(frozen=True)
class PipelineRecommendationExecutionInputs:
    identity: Callable[[], Any]
    recommend: Callable[[], Callable[[str, list[str], int | None], Record]]
    clock: Callable[[], Callable[[], float]]
    traceback: Callable[[], Callable[..., Any]]
    stderr: Callable[[], Any]

@dataclass(frozen=True)
class PipelineRecommendationSchedulingInputs:
    thread: Callable[[], Callable[..., Any]]

class PipelineExecution:
    """No worker starts in construction; each runtime retains its own lifecycle."""
    def __init__(self, *, persistence: PipelinePersistence,
                 model_resolver: ResolverProvider,
                 scope: Callable[[], AbstractContextManager],
                 auto_tasks: PipelineAutoAgentTasksInputs,
                 auto_decision: PipelineAutoAgentDecisionInputs,
                 auto_execution: PipelineAutoAgentExecutionInputs,
                 auto_scheduling: PipelineAutoAgentSchedulingInputs,
                 advance_tasks: PipelineAdvanceTasksInputs,
                 advance_policy: PipelineAdvancePolicyInputs,
                 advance_execution: PipelineAdvanceExecutionInputs,
                 advance_scheduling: PipelineAdvanceSchedulingInputs,
                 recommendation_tasks: PipelineRecommendationTasksInputs,
                 recommendation_execution: PipelineRecommendationExecutionInputs,
                 recommendation_scheduling: PipelineRecommendationSchedulingInputs):
        self.persistence = persistence
        self.model_resolver = model_resolver
        self.auto = PipelineAutoAgentRuntime(
            AutoAgentTasks(
                lock=lambda: self.persistence.runtime.task_lock,
                load=lambda: self.load_pipeline_task,
                needs_agent=auto_tasks.needs_agent,
                orchestration=auto_tasks.orchestration,
                signature=auto_tasks.signature,
                max_steps=auto_tasks.max_steps,
                pause=auto_tasks.pause,
                append_conversation=auto_tasks.append_conversation,
                save=lambda: self.save_pipeline_task,
                deepcopy=auto_tasks.deepcopy,
            ),
            AutoAgentDecision(
                scope_config=auto_decision.scope_config,
                load_config=auto_decision.load_config,
                decide=auto_decision.decide,
                commit=auto_decision.commit,
                now=auto_decision.now,
                schedule_advance=lambda: self.schedule_pipeline_advance,
            ),
            AutoAgentExecution(
                identity=auto_execution.identity,
                traceback=auto_execution.traceback,
                stderr=auto_execution.stderr,
            ),
            AutoAgentScheduling(
                lock=lambda: self.persistence.runtime.auto_agent_lock,
                inflight=lambda: self.persistence.runtime.auto_agent_inflight,
                thread=auto_scheduling.thread,
                runner=lambda: self.run_auto_agent,
            ),
            scope=scope,
        )
        self.advance = PipelineAdvanceRuntime(
            AdvanceTasks(
                lock=lambda: self.persistence.runtime.task_lock,
                load=lambda: self.load_pipeline_task,
                sync=advance_tasks.sync,
                save=lambda: self.save_pipeline_task,
                deepcopy=advance_tasks.deepcopy,
            ),
            AdvancePolicy(
                advance=advance_policy.advance,
                guarded=lambda: self.advance_pipeline_task_guarded,
                cancelled_error=advance_policy.cancelled_error,
                http_error=advance_policy.http_error,
                orchestration=advance_policy.orchestration,
                pause=advance_policy.pause,
                bounded_text=advance_policy.bounded_text,
            ),
            AdvanceExecution(
                identity=advance_execution.identity,
                scope_config=advance_execution.scope_config,
                load_config=advance_execution.load_config,
                clock=advance_execution.clock,
                traceback=advance_execution.traceback,
                stderr=advance_execution.stderr,
                print=advance_execution.print,
            ),
            AdvanceScheduling(
                registry_lock=lambda: self.persistence.runtime.advance_registry_lock,
                inflight=lambda: self.persistence.runtime.advance_inflight,
                cancel_events=lambda: self.persistence.runtime.advance_cancel,
                event=advance_scheduling.event,
                thread=advance_scheduling.thread,
                runner=lambda: self.run_advance,
            ),
            scope=scope,
        )
        self.recommendation = PipelineRecommendationRuntime(
            RecommendationTasks(
                lock=lambda: self.persistence.runtime.task_lock,
                load=lambda: self.load_pipeline_task,
                next_stage=recommendation_tasks.next_stage,
                ready=recommendation_tasks.ready,
                signature=recommendation_tasks.signature,
                save=lambda: self.save_pipeline_task,
            ),
            RecommendationExecution(
                identity=recommendation_execution.identity,
                recommend=recommendation_execution.recommend,
                clock=recommendation_execution.clock,
                traceback=recommendation_execution.traceback,
                stderr=recommendation_execution.stderr,
            ),
            RecommendationScheduling(
                lock=lambda: self.persistence.runtime.recommendation_lock,
                inflight=lambda: self.persistence.runtime.recommendation_inflight,
                thread=recommendation_scheduling.thread,
                runner=lambda: self.run_recommendation,
            ),
            scope=scope,
        )

    def load_pipeline_task(self, task_id: str) -> Record | None:
        return self.persistence.load_pipeline_task(task_id)

    def save_pipeline_task(self, task: Record) -> Record | None:
        return self.persistence.save_pipeline_task(task)

    def run_auto_agent(self, task_id: str, user: Record | None) -> None:
        return pinned(self.model_resolver, self.load_pipeline_task)(self._execute_auto_agent)(task_id, user)

    def _execute_auto_agent(self, task_id: str, user: Record | None) -> None:
        return self.auto.run(task_id, user)

    def run_advance(self, task_id: str, user: Record | None) -> None:
        return pinned(self.model_resolver, self.load_pipeline_task)(self._execute_advance)(task_id, user)

    def _execute_advance(self, task_id: str, user: Record | None) -> None:
        return self.advance.run(task_id, user)

    def run_recommendation(self, task_id: str, stage: str, user: Record | None) -> None:
        return pinned(self.model_resolver, self.load_pipeline_task)(self._execute_recommendation)(task_id, stage, user)

    def _execute_recommendation(self, task_id: str, stage: str, user: Record | None) -> None:
        return self.recommendation.run(task_id, stage, user)

    def schedule_pipeline_auto_agent(self, task_ids: list[str], user: Record | None) -> None:
        return self.auto.schedule(task_ids, user)

    def schedule_pipeline_advance(self, task_id: str, user: Record | None) -> bool:
        return self.advance.schedule(task_id, user)

    def advance_pipeline_task_guarded(self, task: Record, config: Record, cancel_event: Any = None) -> None:
        return self.advance.guarded(task, config, cancel_event)

    def cancel_pipeline_advance(self, task_id: str) -> bool:
        return self.advance.cancel(task_id)

    def schedule_pipeline_recommendation_pregen(self, items: list[tuple[str, str]], user: Record | None) -> None:
        return self.recommendation.schedule(items, user)
