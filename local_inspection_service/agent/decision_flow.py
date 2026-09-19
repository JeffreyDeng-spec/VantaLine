"""Explicit decision flow service without application imports."""
from typing import Any
from .pipeline_decision_ports import AgentDecisionInvocationSettings, AgentDecisionCodec, AgentDecisionFlowCalls


class AgentDecisionFlow:
    def __init__(self, settings: AgentDecisionInvocationSettings, codec: AgentDecisionCodec, calls: AgentDecisionFlowCalls) -> None:
        self._settings = settings
        self._codec = codec
        self._calls = calls

    def agent_pipeline_decide(self,
        task: dict[str, Any],
        config: dict[str, Any],
        *,
        user_message: str | None = None,
        trigger: str = "chat",
    ) -> dict[str, Any]:
        agent_config = self._settings.load()()
        if not self._settings.supported()(agent_config):
            return self._calls.rule()(task, user_message, trigger)
        context = self._calls.context()(task, config, user_message, trigger)
        try:
            content = self._calls.chat()(
                [
                    {"role": "system", "content": self._settings.prompt()},
                    {"role": "user", "content": self._codec.dumps()(context, ensure_ascii=False)},
                ],
                agent_config,
            )
            parsed = self._codec.parse()(content)
            return self._calls.normalize()(parsed)
        except Exception as exc:  # noqa: BLE001 - 任意 Agent 失败都回退规则引擎
            fallback = self._calls.rule()(task, user_message, trigger)
            fallback["agent_error"] = str(exc)[:200]
            return fallback
