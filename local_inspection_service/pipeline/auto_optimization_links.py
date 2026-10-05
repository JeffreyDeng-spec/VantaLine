"""Pipeline automatic-training links and public model readiness projection."""
from dataclasses import dataclass
from typing import Any
from .auto_optimization_links_ports import LinkState, LinkProjection, LinkMatching

@dataclass(frozen=True)
class PipelineAutoOptimizationLinks:
    state: LinkState
    projection: LinkProjection
    matching: LinkMatching

    def fast_completed_auto_optimize_model_id(self, state: dict[str, Any]) -> str:
        active_model_id = str(state.get("active_model_id") or "").strip()
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
        if active_model_id and settings.get("serving_mode") == "promoted_yolo":
            return active_model_id
        for candidate in state.get("candidate_models") or []:
            if not isinstance(candidate, dict):
                continue
            model_id = str(candidate.get("model_id") or "").strip()
            status = str(candidate.get("status") or "").strip()
            if model_id and status == "completed":
                return model_id
        return active_model_id


    def public_auto_optimize_link_for_task_id(self, task_id: str, *, source: str, state: dict[str, Any] | None = None) -> dict[str, Any] | None:
        clean_task_id = self.state.sanitize_ai_detection_task_id()(task_id)
        if not clean_task_id:
            return None
        if state is None:
            with self.state._auto_optimize_lock():
                state = self.state.load_auto_optimize_state()(clean_task_id)
                completed_model_id = self.state.auto_optimize_completed_model_id()(state)
                if completed_model_id and self.state.auto_optimize_stop_capture_for_model_locked()(
                    state,
                    completed_model_id,
                    reason="completed_model_ready",
                ):
                    self.state.save_auto_optimize_state()(state)
        else:
            state = dict(state)
            completed_model_id = self.state.fast_completed_auto_optimize_model_id()(state)
        if state is None:
            state = self.state.load_auto_optimize_state()(clean_task_id)
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
        active_model_id = str(state.get("active_model_id") or "").strip()
        return {
            "task_id": clean_task_id,
            "task_name": state.get("task_name") or "",
            "source": source,
            "enabled": bool(settings.get("enabled")),
            "serving_mode": settings.get("serving_mode") or "api_primary",
            "phase": self.projection.auto_optimize_phase_name()(state),
            "ai_model_id": self.projection.ai_detection_task_model_id()(clean_task_id),
            "active_model_id": active_model_id,
            "completed_model_id": completed_model_id or active_model_id,
            "capture_stopped_at": state.get("capture_stopped_at") or 0,
            "capture_stop_reason": state.get("capture_stop_reason") or "",
        }


    def auto_optimize_states_by_task_id(self, states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            clean_id: state
            for state in states
            for clean_id in [self.state.sanitize_ai_detection_task_id()(state.get("task_id") or "")]
            if clean_id
        }


    def pipeline_task_auto_optimize_link(self,
        task: dict[str, Any],
        config: dict[str, Any],
        *,
        auto_optimize_states: list[dict[str, Any]] | None = None,
        auto_optimize_states_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        states = auto_optimize_states if auto_optimize_states is not None else self.state.list_auto_optimize_states()()
        states_by_task_id = (
            auto_optimize_states_by_id
            if auto_optimize_states_by_id is not None
            else self.state.auto_optimize_states_by_task_id()(states)
        )
        direct_task_id = self.state.sanitize_ai_detection_task_id()(task.get("ai_task_id"))
        if direct_task_id:
            state = states_by_task_id.get(direct_task_id)
            if auto_optimize_states is not None and state is None:
                return None
            return self.projection.public_auto_optimize_link_for_task_id()(direct_task_id, source="direct", state=state)
        target_ids = self.matching.canonical_pipeline_accessory_ids()(config, [str(item_id) for item_id in task.get("accessory_ids") or []])
        if not target_ids:
            return None
        target_counts = self.matching.normalize_pipeline_accessory_counts()(config, target_ids, task.get("accessory_counts"))
        target_key = sorted(target_ids)
        owner_id = str(task.get("owner_user_id") or "").strip()
        newest_match: tuple[int, str] | None = None
        for state in states:
            state_owner_id = str(state.get("owner_user_id") or "").strip()
            if owner_id and state_owner_id and owner_id != state_owner_id:
                continue
            state_ids = self.matching.canonical_pipeline_accessory_ids()(config, [str(item_id) for item_id in state.get("selected_accessory_ids") or []])
            if sorted(state_ids) != target_key:
                continue
            state_counts = self.matching.normalize_pipeline_accessory_counts()(config, state_ids, state.get("required_accessory_counts"))
            if {item_id: int(state_counts.get(item_id, 1)) for item_id in state_ids} != {
                item_id: int(target_counts.get(item_id, 1)) for item_id in target_ids
            }:
                continue
            state_task_id = self.state.sanitize_ai_detection_task_id()(state.get("task_id") or "")
            if not state_task_id:
                continue
            updated_at = int(state.get("updated_at") or state.get("created_at") or 0)
            if newest_match is None or updated_at > newest_match[0]:
                newest_match = (updated_at, state_task_id)
        if not newest_match:
            return None
        return self.projection.public_auto_optimize_link_for_task_id()(
            newest_match[1],
            source="accessory_match",
            state=states_by_task_id.get(newest_match[1]),
        )
