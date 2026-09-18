"""AI detection orchestration; composition establishes the model-snapshot scope."""
from pathlib import Path
from typing import Any
import numpy as np
from .analysis_ports import AiProfiles, AiInspectionTools, AiAnalysisEvidence


class AiDetectionAnalysis:
    def __init__(self, profiles: AiProfiles, tools: AiInspectionTools, evidence: AiAnalysisEvidence):
        self.profiles, self.tools, self.evidence = profiles, tools, evidence

    def analyze_bgr_ai_detection(self,
        image_bgr: np.ndarray,
        request_id: str,
        spec: dict[str, Any],
        config: dict[str, Any],
        *,
        image_path: Path | None = None,
    ) -> dict[str, Any]:
        required_items = self.profiles.required(config, spec)
        if not required_items:
            annotated_url = self.evidence.original(image_bgr, request_id)
            result = self.evidence.failure(
                request_id,
                spec,
                [],
                annotated_url,
                reason="AI detection task has no required accessories configured.",
            )
            self.evidence.persist(result, request_id, image_path=image_path)
            return result
        changed = False
        real_ids = {self.profiles.uid(item) for item in config.get("accessories", [])}
        required_accessories: list[dict[str, Any]] = []
        required_accessory_refs: list[dict[str, Any]] = []
        reference_descriptors: list[dict[str, Any]] = []
        for item, expected_count in required_items:
            item_id = self.profiles.uid(item)
            current_profile = item.get("ai_profile") if isinstance(item.get("ai_profile"), dict) else None
            if not current_profile or current_profile.get("accessory_id") != item_id:
                profile_result = self.tools.call()(
                    "accessory.profile.generate",
                    {
                        "accessory": item,
                        "expected_count": expected_count,
                        "allow_provider": False,
                        "provider_config": self.tools.settings()("accessory"),
                    },
                )
                item["ai_profile"] = profile_result["profile"]
                item["ai_profile_status"] = profile_result["status"]
                current_profile = profile_result["profile"]
                if item_id in real_ids:
                    changed = True
            else:
                normalized_profile = self.profiles.normalize(current_profile, item)
                current_refs = normalized_profile.get("reference_images") if isinstance(normalized_profile.get("reference_images"), list) else []
                if current_refs:
                    if normalized_profile != current_profile:
                        item["ai_profile"] = normalized_profile
                        current_profile = normalized_profile
                        if item_id in real_ids:
                            changed = True
                else:
                    expected_refs = self.profiles.references(item)
                    if expected_refs:
                        normalized_profile["reference_images"] = expected_refs
                        item["ai_profile"] = normalized_profile
                        current_profile = normalized_profile
                        if item_id in real_ids:
                            changed = True
            required_accessories.append(self.profiles.payload(item, expected_count, current_profile))
            required_accessory_refs.append({"accessory_id": item_id, "expected_count": expected_count})
            if self.tools.references_per_accessory() > 0:
                reference_result = self.tools.call()(
                    "accessory.reference.collect",
                    {
                        "accessory": item,
                        "max_images": self.tools.references_per_accessory(),
                        "max_side": self.tools.reference_max_side(),
                        "quality": self.tools.reference_quality(),
                    },
                )
                reference_descriptors.extend(reference_result.get("references") or [])
        if changed:
            self.profiles.save(config)
        settings = self.tools.settings()()
        mcp_image_path = self.tools.image(image_bgr, request_id) if self.tools.external() else None
        vision_result = self.tools.call()(
            "vision.inspect.presence",
            {
                "inspection_image_bgr": image_bgr,
                "inspection_image_path": str(mcp_image_path) if mcp_image_path else "",
                "required_accessories": required_accessories,
                "required_accessory_refs": required_accessory_refs,
                "reference_descriptors": reference_descriptors,
                "provider_config": settings,
            },
        )
        ai_debug = vision_result.get("ai") if isinstance(vision_result.get("ai"), dict) else {}
        for key in ("mcp_transport", "mcp_runtime", "mcp_dispatch_ms", "mcp_fallback_from", "mcp_fallback_error"):
            if vision_result.get(key) is not None:
                ai_debug = {**ai_debug, key: vision_result.get(key)}
        rule = vision_result.get("rule") if isinstance(vision_result.get("rule"), dict) else {}
        detections = vision_result.get("detections") if isinstance(vision_result.get("detections"), list) else []
        annotated_url = self.evidence.original(image_bgr, request_id)
        result = {
            "request_id": request_id,
            "passed": bool(vision_result.get("passed")),
            "model": self.evidence.model(spec, settings),
            "rule": rule,
            "detections": detections,
            "annotated_url": annotated_url,
            "ai": ai_debug,
        }
        self.evidence.persist(result, request_id, image_path=image_path)
        return result
