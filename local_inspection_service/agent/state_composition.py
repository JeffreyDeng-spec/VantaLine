"""Own Agent state and tool records around an independent configuration leaf."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from .orchestration_state import AgentOrchestrationState
from .tool_call_records import AgentToolCallRecords
from .state_ports import AgentStateRuntime, AgentStateCalls, AgentToolCallIdentity, AgentToolCallState
from .pose_render_configuration import PoseRenderConfiguration
from .pose_render_ports import PoseRenderConfigurationSources, PoseRenderConfigurationDefaults

@dataclass(frozen=True)
class AgentStateClock:
    clock: Callable[[], Callable[[], float]]
    version: Callable[[], str]

@dataclass(frozen=True)
class AgentToolNames:
    sanitize: Callable[[], Callable[[str], str]]
    samples: Callable[[], str]
    training: Callable[[], str]

class AgentStateWorkflows:
    """Construct inert owners; task state remains on the supplied task record."""
    def __init__(self, *, clock: AgentStateClock, tools: AgentToolNames,
                 configuration_sources: PoseRenderConfigurationSources,
                 configuration_defaults: PoseRenderConfigurationDefaults):
        self.configuration = PoseRenderConfiguration(configuration_sources, configuration_defaults)
        self.state = AgentOrchestrationState(
            AgentStateRuntime(clock=clock.clock, now=lambda: self.agent_mcp_now,
                              version=clock.version, image_config=lambda: self.agent_mcp_gemini_image_config),
            AgentStateCalls(defaults=lambda: self.agent_mcp_default_stages,
                            orchestration=lambda: self.agent_mcp_orchestration,
                            pause=lambda: self.pause_agent_mcp_task,
                            stage=lambda: self.set_agent_mcp_stage),
        )
        self.tools = AgentToolCallRecords(
            AgentToolCallIdentity(sanitize=tools.sanitize, identifier=lambda: self.agent_mcp_tool_call_id,
                                  samples=tools.samples, training=tools.training),
            AgentToolCallState(now=lambda: self.agent_mcp_now,
                               orchestration=lambda: self.agent_mcp_orchestration,
                               upsert=lambda: self.upsert_agent_mcp_tool_call,
                               stage=lambda: self.set_agent_mcp_stage),
        )

    def agent_mcp_now(self) -> int:
        return self.state.agent_mcp_now()

    def agent_mcp_gemini_image_config(self) -> dict[str, Any]:
        return self.configuration.agent_mcp_gemini_image_config()

    def agent_mcp_default_stages(self) -> list[dict[str, Any]]:
        return self.state.agent_mcp_default_stages()

    def agent_mcp_orchestration(self, task: dict[str, Any]) -> dict[str, Any]:
        return self.state.agent_mcp_orchestration(task)

    def set_agent_mcp_stage(self, orchestration: dict[str, Any], key: str, status: str, progress: int, **extra: Any) -> None:
        return self.state.set_agent_mcp_stage(orchestration, key, status, progress, **extra)

    def agent_mcp_tool_call_id(self, task_id: str, tool_name: str, accessory_id: str='', pose_id: str='') -> str:
        return self.tools.agent_mcp_tool_call_id(task_id, tool_name, accessory_id, pose_id)

    def upsert_agent_mcp_tool_call(self, orchestration: dict[str, Any], call: dict[str, Any]) -> dict[str, Any]:
        return self.tools.upsert_agent_mcp_tool_call(orchestration, call)

    def pause_agent_mcp_task(self, task: dict[str, Any], orchestration: dict[str, Any], *, stage: str, reason: str, suggested_actions: list[str]) -> None:
        return self.state.pause_agent_mcp_task(task, orchestration, stage=stage, reason=reason, suggested_actions=suggested_actions)

    def log_agent_mcp_sample_tool_call(self, task: dict[str, Any], job: dict[str, Any]) -> None:
        return self.tools.log_agent_mcp_sample_tool_call(task, job)

    def log_agent_mcp_training_tool_call(self, task: dict[str, Any], job: dict[str, Any]) -> None:
        return self.tools.log_agent_mcp_training_tool_call(task, job)

    def agent_mcp_training_quality_gate(self, task: dict[str, Any]) -> bool:
        return self.state.agent_mcp_training_quality_gate(task)
