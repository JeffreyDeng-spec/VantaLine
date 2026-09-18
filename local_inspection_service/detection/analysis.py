"""Ordinary detection selection, inference and output orchestration."""
from pathlib import Path
from typing import Any
import numpy as np
from .analysis_ports import AnalysisInput, AnalysisRouting, AnalysisInference, AnalysisOutput


class DetectionAnalysis:
    def __init__(self, inputs: AnalysisInput, routing: AnalysisRouting,
                 inference: AnalysisInference, output: AnalysisOutput):
        self.input, self.routing, self.inference, self.output = inputs, routing, inference, output

    def analyze_bgr(self, image_bgr: np.ndarray, request_id: str, model_id: str | None = None, *, image_path: Path | None = None) -> dict[str, Any]:
        config = self.input.scope()(self.input.load())
        spec = self.input.select(model_id, config)
        if spec.get("is_ai_detection"):
            task_id = self.input.task_id()(spec.get("task_id") or spec.get("run_id") or "")
            if task_id:
                state = self.input.state(task_id)
                settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
                active_model_id = str(state.get("active_model_id") or "").strip()
                if settings.get("enabled") and settings.get("serving_mode") == "promoted_yolo" and active_model_id:
                    try:
                        promoted = self.routing.analyze(image_bgr, request_id, active_model_id, image_path=image_path)
                        promoted["ai_auto_optimize"] = {
                            "serving_mode": "promoted_yolo",
                            "ai_task_id": task_id,
                            "active_model_id": active_model_id,
                            "fallback_used": False,
                        }
                        return promoted
                    except Exception as exc:
                        # Production should fall back to the API teacher if the promoted
                        # student model is missing or temporarily unhealthy.
                        fallback = self.routing.ai(image_bgr, request_id, spec, config, image_path=image_path)
                        fallback["ai_auto_optimize"] = {
                            "serving_mode": "api_primary",
                            "ai_task_id": task_id,
                            "active_model_id": active_model_id,
                            "fallback_used": True,
                            "fallback_reason": self.routing.text()(str(exc), 180),
                        }
                        return fallback
            return self.routing.ai(image_bgr, request_id, spec, config, image_path=image_path)
        if spec.get("is_label_sheet_match"):
            self.routing.retired("Label Sheet")
        try:
            confidence_threshold = max(0.001, min(0.99, float(spec.get("confidence_threshold", config.get("confidence_threshold", 0.25)))))
        except (TypeError, ValueError):
            confidence_threshold = 0.25
        result = self.inference.model()(str(spec["id"]), config).predict(
            image_bgr,
            imgsz=int(config["image_size"]),
            device=self.inference.device(),
            conf=confidence_threshold,
            verbose=False,
        )[0]
        detections = self.inference.parse(result, spec)
        if spec.get("uses_ocr", False):
            detections = self.inference.ocr(image_bgr, detections, config, spec)
        rule = self.inference.rule(detections, config, spec)
        annotated = self.inference.draw(image_bgr, detections, rule)
        out_name = f"{request_id}_annotated.jpg"
        out_path = self.output.directory("inspection") / out_name
        preview = self.output.resize()(annotated, self.output.max_side())
        self.output.images().imwrite(str(out_path), preview, [int(self.output.images().IMWRITE_JPEG_QUALITY), self.output.quality()])
        return {
            "request_id": request_id,
            "passed": rule["passed"],
            "model": {
                "id": spec["id"],
                "label": spec["label"],
                "uses_ocr": bool(spec.get("uses_ocr", False)),
            },
            "rule": rule,
            "detections": detections,
            "annotated_url": self.output.url(out_path),
        }
