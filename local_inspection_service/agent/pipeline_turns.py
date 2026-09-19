"""Explicit pipeline turns service without application imports."""
from typing import Any
from .pipeline_action_ports import AgentTurnCalls


class AgentPipelineTurns:
    def __init__(self, turn: AgentTurnCalls) -> None:
        self._turn = turn

    def commit_pipeline_agent_turn(self,
        task: dict[str, Any],
        config: dict[str, Any],
        user: dict[str, Any] | None,
        user_message: str | None,
        decision: dict[str, Any],
        trigger: str,
        pending_advances: list[str] | None = None,
    ) -> dict[str, Any]:
        """Apply a pre-computed Agent decision under the pipeline tasks lock.

    The LLM call (`agent_pipeline_decide`) must run *before* this, outside the
    lock, so a slow provider request never blocks pipeline polling. Any advance
    the decision triggers is collected into `pending_advances` and scheduled by
    the caller after the lock is released (heavy work runs in the async runner).
    """
        if user_message:
            self._turn.append()(task, "user", user_message)
        self._turn.apply()(task, config, decision, user, trigger=trigger, pending_advances=pending_advances)
        self._turn.append()(
            task,
            "agent",
            decision.get("message_to_user") or decision.get("reason") or "已处理。",
            action=str(decision.get("action") or ""),
            reason=str(decision.get("reason") or ""),
            target_stage=str(decision.get("target_stage") or ""),
            source=str(decision.get("source") or ""),
            needs_user=bool(decision.get("needs_user")),
            agent_error=str(decision.get("agent_error") or ""),
        )
        return decision
