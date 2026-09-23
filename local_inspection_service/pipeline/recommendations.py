"""Pipeline recommendation signature, readiness and cache consumption."""
from typing import Any

from .recommendation_ports import PipelineRecommendationLinks, PipelineRecommendationMethodPolicy


class PipelineRecommendations:
    def __init__(self, method: PipelineRecommendationMethodPolicy, links: PipelineRecommendationLinks):
        self.method = method
        self.links = links

    def pipeline_recommendation_signature(self, task: dict[str, Any], stage: str) -> str:
        accessory_ids = ",".join(str(item) for item in task.get("accessory_ids") or [])
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        sample_count = int(params.get("sample_count") or 0) if stage == "training" else 0
        return f"{stage}|{accessory_ids}|{sample_count}"

    def pipeline_next_recommendation_stage(self, task: dict[str, Any]) -> str:
        """Which stage's params should be pre-computed so the next step is ready."""
        detection_method = self.method.normalize()(
            str(task.get("detection_method") or (task.get("params") or {}).get("train_mode") or "")
        )
        if not self.method.uses_training()(detection_method):
            return ""
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        stage = str(task.get("stage") or "")
        status = str(task.get("status") or "")
        if stage == "draft" and "sample_count" not in params:
            return "samples"
        if stage == "samples" and status == "completed" and "epochs" not in params:
            return "training"
        return ""

    def pipeline_recommendation_ready(self, task: dict[str, Any], stage: str) -> bool:
        rec = task.get("recommended_params")
        return (
            isinstance(rec, dict)
            and rec.get("stage") == stage
            and rec.get("signature") == self.links.signature()(task, stage)
            and isinstance(rec.get("params"), dict)
        )

    def consume_pipeline_recommendation(self, task: dict[str, Any], stage: str) -> dict[str, Any] | None:
        """Return (and clear) the pre-generated params for a stage if present."""
        rec = task.get("recommended_params")
        if isinstance(rec, dict) and rec.get("stage") == stage and isinstance(rec.get("params"), dict):
            if rec.get("reason"):
                task["agent_reason"] = rec.get("reason")
            if rec.get("source"):
                task["agent_source"] = rec.get("source")
            params = dict(rec["params"])
            task.pop("recommended_params", None)
            return params
        return None

    def collect_pipeline_recommendation_pregen(self, tasks: list[dict[str, Any]]) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for task in tasks:
            stage = self.links.next_stage()(task)
            if not stage or self.links.ready()(task, stage):
                continue
            items.append((str(task.get("id")), stage))
        return items
