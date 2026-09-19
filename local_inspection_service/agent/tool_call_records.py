"""Explicit tool call records service without application imports."""
from typing import Any
from .state_ports import AgentToolCallIdentity, AgentToolCallState


class AgentToolCallRecords:
    def __init__(self, identity: AgentToolCallIdentity, state: AgentToolCallState) -> None:
        self._identity = identity
        self._state = state

    def agent_mcp_tool_call_id(self, task_id: str, tool_name: str, accessory_id: str = "", pose_id: str = "") -> str:
        return self._identity.sanitize()("__".join(part for part in [str(task_id), tool_name, accessory_id, pose_id] if part))

    def upsert_agent_mcp_tool_call(self, orchestration: dict[str, Any], call: dict[str, Any]) -> dict[str, Any]:
        calls = orchestration.setdefault("tool_calls", [])
        call_id = str(call.get("call_id") or "")
        existing = next((item for item in calls if str(item.get("call_id") or "") == call_id), None)
        now = self._state.now()()
        if existing:
            existing.update({**call, "updated_at": now})
            return existing
        call.setdefault("created_at", now)
        call.setdefault("updated_at", now)
        calls.append(call)
        orchestration["updated_at"] = now
        return call

    def log_agent_mcp_sample_tool_call(self, task: dict[str, Any], job: dict[str, Any]) -> None:
        orchestration = self._state.orchestration()(task)
        self._state.upsert()(
            orchestration,
            {
                "call_id": self._identity.identifier()(str(task.get("id") or ""), self._identity.samples()),
                "tool": self._identity.samples(),
                "task_id": task.get("id"),
                "request": {
                    "accessory_ids": task.get("accessory_ids") or [],
                    "sample_count": (task.get("params") or {}).get("sample_count"),
                    "train_mode": (task.get("params") or {}).get("train_mode"),
                },
                "status": "running",
                "output_path": "",
                "artifact_refs": [job.get("job_id")],
                "error": "",
            },
        )
        orchestration["state"] = "sample_generation"
        orchestration["active_stage"] = "sample_generation"
        self._state.stage()(orchestration, "sample_generation", "running", 0, detail=f"Sample generation job {job.get('job_id')} started.")

    def log_agent_mcp_training_tool_call(self, task: dict[str, Any], job: dict[str, Any]) -> None:
        orchestration = self._state.orchestration()(task)
        self._state.upsert()(
            orchestration,
            {
                "call_id": self._identity.identifier()(str(task.get("id") or ""), self._identity.training()),
                "tool": self._identity.training(),
                "task_id": task.get("id"),
                "request": {
                    "accessory_ids": task.get("accessory_ids") or [],
                    "dataset_id": task.get("dataset_id"),
                    "epochs": (task.get("params") or {}).get("epochs"),
                    "image_size": (task.get("params") or {}).get("image_size"),
                    "train_mode": (task.get("params") or {}).get("train_mode"),
                },
                "status": "running",
                "output_path": "",
                "artifact_refs": [job.get("job_id")],
                "error": "",
            },
        )
        orchestration["state"] = "model_training"
        orchestration["active_stage"] = "model_training"
        self._state.stage()(orchestration, "model_training", "running", 0, detail=f"Training job {job.get('job_id')} started.")
