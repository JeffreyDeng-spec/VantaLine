"""Explicit orchestration state service without application imports."""
from typing import Any
from .state_ports import AgentStateRuntime, AgentStateCalls


class AgentOrchestrationState:
    def __init__(self, runtime: AgentStateRuntime, calls: AgentStateCalls) -> None:
        self._runtime = runtime
        self._calls = calls

    def agent_mcp_now(self) -> int:
        return int(self._runtime.clock()())

    def agent_mcp_default_stages(self) -> list[dict[str, Any]]:
        return [
            {"key": "agent_pose_planning", "label": "Agent pose planning", "status": "pending", "progress": 0},
            {"key": "pose_image_generation", "label": "MCP pose image generation", "status": "pending", "progress": 0},
            {"key": "sample_generation", "label": "MCP sample generation", "status": "pending", "progress": 0},
            {"key": "model_training", "label": "MCP model training", "status": "pending", "progress": 0},
        ]

    def agent_mcp_orchestration(self, task: dict[str, Any]) -> dict[str, Any]:
        raw = task.get("agent_mcp") if isinstance(task.get("agent_mcp"), dict) else {}
        orchestration = {
            "version": self._runtime.version(),
            "state": raw.get("state") or "created",
            "active_stage": raw.get("active_stage") or "created",
            "stages": raw.get("stages") if isinstance(raw.get("stages"), list) else self._calls.defaults()(),
            "pose_plan": raw.get("pose_plan") if isinstance(raw.get("pose_plan"), dict) else None,
            "tool_calls": raw.get("tool_calls") if isinstance(raw.get("tool_calls"), list) else [],
            "feedback": raw.get("feedback") if isinstance(raw.get("feedback"), list) else [],
            "conversation": raw.get("conversation") if isinstance(raw.get("conversation"), list) else [],
            "pause": raw.get("pause") if isinstance(raw.get("pause"), dict) else None,
            "skip_pose_image_generation": bool(raw.get("skip_pose_image_generation")),
            "training_quality_ack": bool(raw.get("training_quality_ack")),
            "auto_steps": int(raw.get("auto_steps") or 0),
            "last_auto_signature": str(raw.get("last_auto_signature") or ""),
            "last_auto_step_at": int(raw.get("last_auto_step_at") or 0),
            "created_at": int(raw.get("created_at") or self._runtime.now()()),
            "updated_at": int(raw.get("updated_at") or self._runtime.now()()),
            "tool_config": {
                **(raw.get("tool_config") if isinstance(raw.get("tool_config"), dict) else {}),
                "pose_image_generation": self._runtime.image_config()(),
            },
        }
        task["agent_mcp"] = orchestration
        return orchestration

    def set_agent_mcp_stage(self, orchestration: dict[str, Any], key: str, status: str, progress: int, **extra: Any) -> None:
        stages = orchestration.setdefault("stages", self._calls.defaults()())
        stage = next((item for item in stages if item.get("key") == key), None)
        if not stage:
            stage = {"key": key, "label": key.replace("_", " "), "status": "pending", "progress": 0}
            stages.append(stage)
        stage.update({"status": status, "progress": max(0, min(100, int(progress))), **extra})
        orchestration["updated_at"] = self._runtime.now()()

    def pause_agent_mcp_task(self, task: dict[str, Any], orchestration: dict[str, Any], *, stage: str, reason: str, suggested_actions: list[str]) -> None:
        now = self._runtime.now()()
        orchestration.update(
            {
                "state": "needs_user_action",
                "active_stage": stage,
                "pause": {
                    "stage": stage,
                    "reason": reason,
                    "suggested_actions": suggested_actions,
                    "created_at": now,
                },
                "updated_at": now,
            }
        )
        task.update(
            {
                "status": "needs_user_action",
                "progress": 20 if stage == "pose_image_generation" else 80,
                "last_error": reason[:240],
                "job_note": reason[:240],
                "updated_at": now,
            }
        )

    def agent_mcp_training_quality_gate(self, task: dict[str, Any]) -> bool:
        orchestration = self._calls.orchestration()(task)
        if orchestration.get("training_quality_ack"):
            return True
        if orchestration.get("skip_pose_image_generation"):
            reason = "Pose images were skipped because the image API is not configured; confirm before model training."
            self._calls.pause()(
                task,
                orchestration,
                stage="model_training",
                reason=reason,
                suggested_actions=["continue_training", "replan", "cancel"],
            )
            self._calls.stage()(orchestration, "model_training", "needs_user_action", 0, detail=reason)
            return False
        return True
