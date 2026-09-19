"""Explicit decision context service without application imports."""
from typing import Any
from .pipeline_decision_ports import AgentPipelineEvidence, AgentDecisionAccessories, AgentDecisionContextCalls, AgentDecisionText


class AgentDecisionContext:
    def __init__(self, evidence: AgentPipelineEvidence, accessories: AgentDecisionAccessories, context: AgentDecisionContextCalls, text: AgentDecisionText) -> None:
        self._evidence = evidence
        self._accessories = accessories
        self._context = context
        self._text = text

    def agent_pipeline_quality_signals(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        orchestration = self._evidence.orchestration()(task)
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        accessory_ids = self._accessories.canonical()(config, [str(item_id) for item_id in task.get("accessory_ids") or []])
        counts = self._accessories.counts()(config, accessory_ids, task.get("accessory_counts"))
        accessory_total = sum(counts.values()) or len(accessory_ids)
        sample_count = int(params.get("sample_count") or 0)
        signals: dict[str, Any] = {
            "accessory_count": len(accessory_ids),
            "accessory_unit_total": accessory_total,
            "sample_count": sample_count,
        }
        if accessory_total and sample_count:
            signals["samples_per_accessory_unit"] = round(sample_count / max(1, accessory_total), 1)
        pose_calls = [call for call in orchestration.get("tool_calls") or [] if call.get("tool") == self._evidence.pose_tool()]
        signals["pose_images_total"] = len(pose_calls)
        signals["pose_images_completed"] = len([call for call in pose_calls if call.get("status") == "completed"])
        signals["pose_images_failed"] = len([call for call in pose_calls if call.get("status") == "failed"])
        signals["skip_pose_image_generation"] = bool(orchestration.get("skip_pose_image_generation"))
        gemini = self._evidence.image_config()()
        signals["image_generation_configured"] = bool(gemini.get("configured"))
        try:
            signals["missing_assets"] = self._evidence.missing_assets()(task, config, orchestration)[:6]
        except Exception:  # noqa: BLE001 - 质量信号收集失败不应阻塞决策
            signals["missing_assets"] = []
        try:
            job = self._evidence.training_job()(task)
        except Exception:  # noqa: BLE001
            job = None
        if job:
            signals["linked_job_status"] = str(job.get("status") or "")
            signals["linked_job_note"] = self._text.bounded()(job.get("note"), 200)
            if job.get("current_epoch") is not None:
                signals["current_epoch"] = job.get("current_epoch")
                signals["total_epochs"] = job.get("total_epochs") or job.get("epochs") or 0
            for key in ("map50", "map", "precision", "recall"):
                if job.get(key) is not None:
                    signals[key] = job.get(key)
        if task.get("last_error"):
            signals["last_error"] = self._text.bounded()(task.get("last_error"), 200)
        return signals

    def agent_pipeline_context(self, task: dict[str, Any], config: dict[str, Any], user_message: str | None, trigger: str) -> dict[str, Any]:
        orchestration = self._evidence.orchestration()(task)
        accessories_by_id = self._accessories.lookup()(config)
        accessory_ids = self._accessories.canonical()(config, [str(item_id) for item_id in task.get("accessory_ids") or []])
        counts = self._accessories.counts()(config, accessory_ids, task.get("accessory_counts"))
        accessories = [
            {
                "name": str(accessories_by_id[item_id].get("name") or item_id),
                "material_type": self._accessories.material()(accessories_by_id[item_id]),
                "count": int(counts.get(item_id, 1)),
            }
            for item_id in accessory_ids
            if item_id in accessories_by_id
        ]
        pause = orchestration.get("pause") if isinstance(orchestration.get("pause"), dict) else None
        stages = [
            {"key": stage.get("key"), "status": stage.get("status"), "progress": stage.get("progress")}
            for stage in orchestration.get("stages") or []
        ]
        recent = [
            {"role": entry.get("role"), "message": entry.get("message"), "action": entry.get("action")}
            for entry in (orchestration.get("conversation") or [])[-8:]
        ]
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        return {
            "trigger": trigger,
            "task": {
                "id": task.get("id"),
                "name": task.get("name"),
                "stage": task.get("stage"),
                "status": task.get("status"),
                "progress": task.get("progress"),
                "detection_method": self._accessories.detection()(str(task.get("detection_method") or params.get("train_mode") or "")),
                "auto_advance": bool(task.get("auto_advance")),
                "params": {key: params.get(key) for key in ("sample_count", "epochs", "image_size", "train_mode", "background_set_id")},
            },
            "accessories": accessories,
            "orchestration": {
                "state": orchestration.get("state"),
                "active_stage": orchestration.get("active_stage"),
                "stages": stages,
                "pause": ({"reason": pause.get("reason"), "suggested_actions": pause.get("suggested_actions")} if pause else None),
                "training_quality_ack": bool(orchestration.get("training_quality_ack")),
                "skip_pose_image_generation": bool(orchestration.get("skip_pose_image_generation")),
            },
            "quality_signals": self._context.quality()(task, config),
            "recent_conversation": recent,
            "user_message": user_message or "",
            "stage_order": self._context.stage_order(),
            "constraints": {
                "sample_count": [50, 20000],
                "epochs": [1, 500],
                "image_size": [320, 1280],
                "train_mode": ["yolo", "yolo_ocr"],
            },
        }
