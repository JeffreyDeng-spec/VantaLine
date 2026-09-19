"""Explicit conversation service without application imports."""
from typing import Any
from .pipeline_decision_ports import AgentConversationRuntime, AgentDecisionText


class AgentConversation:
    def __init__(self, conversation: AgentConversationRuntime, text: AgentDecisionText) -> None:
        self._conversation = conversation
        self._text = text

    def agent_mcp_append_conversation(self,
        task: dict[str, Any],
        role: str,
        message: str,
        *,
        action: str = "",
        reason: str = "",
        target_stage: str = "",
        source: str = "",
        needs_user: bool = False,
        agent_error: str = "",
    ) -> dict[str, Any]:
        orchestration = self._conversation.orchestration()(task)
        conversation = orchestration.setdefault("conversation", [])
        entry: dict[str, Any] = {
            "id": f"msg_{self._conversation.uuid()().hex[:10]}",
            "role": role,
            "message": self._text.bounded()(message, 800),
            "created_at": self._conversation.now()(),
        }
        if action:
            entry["action"] = action
        if reason:
            entry["reason"] = self._text.bounded()(reason, 400)
        if target_stage:
            entry["target_stage"] = target_stage
        if source:
            entry["source"] = source
        if needs_user:
            entry["needs_user"] = True
        if agent_error:
            entry["agent_error"] = self._text.bounded()(agent_error, 200)
        conversation.append(entry)
        if len(conversation) > self._conversation.limit():
            del conversation[: len(conversation) - self._conversation.limit()]
        orchestration["updated_at"] = self._conversation.now()()
        return entry
