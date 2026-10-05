"""Existing automatic mask label generation with explicit domain capabilities."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
import time
import cv2
import numpy as np

from .auto_optimization_label_generation_ports import LabelGenerationArtifacts, LabelGenerationPolicy, LabelGenerationModels


@dataclass(frozen=True)
class AutoOptimizationLabelGeneration:
    artifacts: LabelGenerationArtifacts
    policy: LabelGenerationPolicy
    models: LabelGenerationModels

    def auto_optimize_generate_labels_for_sample(
        self,
        sample: dict[str, Any],
        provider_settings: dict[str, Any],
        model: str,
        artifact_dir: Path,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        image_path = self.artifacts.resolve_service_path()((sample.get("source_image") or {}).get("path"))
        image_bgr = self.artifacts._image_files().imread(str(image_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            return [], [{"status": "failed", "reason": "source_image_unreadable"}], {}
        candidates = [item for item in sample.get("candidate_accessories") or [] if isinstance(item, dict)]
        if not candidates:
            return [], [{"status": "rejected", "reason": "no_present_single_accessory_candidates"}], {}
        payload = self.policy.photo_highlight_input_data_url()(image_bgr)
        if payload is None:
            return [], [{"status": "failed", "reason": "source_image_encode_failed"}], {}
        ai_bgr, data_url, scale_x, scale_y = payload
        input_h, input_w = ai_bgr.shape[:2]
        orig_h, orig_w = image_bgr.shape[:2]
        labels: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        combined_mask = np.zeros((orig_h, orig_w, 3), dtype=np.uint8)
        sample_id = self.artifacts.safe_record_id()(str(sample.get("sample_id") or "sample"))
        started = int(time.time())
        api_calls: list[dict[str, Any]] = []
        accessories_by_id = self.policy.auto_optimize_accessory_lookup_for_sample()(sample)
        mask_targets_per_call = max(
            1,
            min(
                len(self.policy.AUTO_OPTIMIZE_MASK_PALETTE()),
                int(os.environ.get("VANTALINE_AUTO_OPTIMIZE_MASK_TARGETS_PER_CALL", str(len(self.policy.AUTO_OPTIMIZE_MASK_PALETTE()))) or str(len(self.policy.AUTO_OPTIMIZE_MASK_PALETTE()))),
            ),
        )
        mask_generation_attempts = max(1, int(os.environ.get("VANTALINE_AUTO_OPTIMIZE_MASK_GENERATION_ATTEMPTS", "3") or "3"))
        for chunk_index in range(0, len(candidates), mask_targets_per_call):
            chunk = candidates[chunk_index : chunk_index + mask_targets_per_call]
            chunk_number = int(chunk_index // mask_targets_per_call)
            assignments = [
                {
                    "candidate": candidate,
                    "palette": self.policy.AUTO_OPTIMIZE_MASK_PALETTE()[offset],
                    "profile": self.policy.auto_optimize_mask_target_profile()(candidate, accessories_by_id),
                }
                for offset, candidate in enumerate(chunk)
            ]
            prompt = self.policy.auto_optimize_multicolor_mask_prompt()(assignments, input_w=input_w, input_h=input_h)
            user_content = [
                {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
            ]
            try:
                result = self.models.auto_optimize_generate_image_with_retry()(provider_settings, model, prompt, user_content)
            except self.models.AiProviderError() as exc:
                for item in assignments:
                    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
                    failures.append(
                        {
                            "accessory_id": candidate.get("accessory_id"),
                            "label": candidate.get("label"),
                            "status": "failed",
                            "reason": self.policy.bounded_text()(str(exc), 180),
                            "attempts": getattr(exc, "attempts", None),
                            "retry_count": getattr(exc, "retry_count", None),
                            "previous_errors": getattr(exc, "previous_errors", [])[-3:],
                        }
                    )
                continue
            usage_metadata = result.get("usage_metadata") if isinstance(result.get("usage_metadata"), dict) else {}
            api_calls.append(
                {
                    "provider": str(provider_settings.get("provider") or "image_generation"),
                    "model": str(model or result.get("model") or ""),
                    "created_at": int(time.time()),
                    "latency_ms": int(result.get("latency_ms") or 0),
                    "attempts": int(result.get("attempts") or 1),
                    "retry_count": int(result.get("retry_count") or 0),
                    "previous_errors": result.get("previous_errors") if isinstance(result.get("previous_errors"), list) else [],
                    "chunk_index": chunk_number,
                    "targets_per_call": mask_targets_per_call,
                    "prompt_mode": self.policy.AUTO_OPTIMIZE_MASK_PROMPT_MODE(),
                    "target_profile_count": len([item for item in assignments if (item.get("profile") or {}).get("visual_signature") or (item.get("profile") or {}).get("positive_cues")]),
                    "usage_metadata": usage_metadata,
                }
            )
            mask_path = artifact_dir / f"{sample_id}_multicolor_mask_{chunk_number + 1}.png"
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            self.artifacts._business_files().write_bytes(mask_path, result["bytes"])
            mask_bgr = self.artifacts._image_files().imread(str(mask_path), cv2.IMREAD_COLOR)
            if mask_bgr is None:
                try:
                    self.artifacts._business_files().unlink(mask_path, missing_ok=True)
                except OSError:
                    pass
                for item in assignments:
                    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
                    failures.append(
                        {
                            "accessory_id": candidate.get("accessory_id"),
                            "label": candidate.get("label"),
                            "status": "failed",
                            "reason": "generated_mask_unreadable",
                        }
                    )
                continue
            if mask_bgr.shape[1] != input_w or mask_bgr.shape[0] != input_h:
                mask_bgr = cv2.resize(mask_bgr, (input_w, input_h), interpolation=cv2.INTER_NEAREST)
            color_masks, mask_meta = self.policy.decode_multicolor_mask()(mask_bgr, assignments)
            try:
                self.artifacts._business_files().unlink(mask_path, missing_ok=True)
            except OSError:
                pass
            for item in assignments:
                candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
                palette = item.get("palette") if isinstance(item.get("palette"), dict) else {}
                profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
                accessory_id = str(candidate.get("accessory_id") or candidate.get("label") or palette.get("name") or "")
                ai_mask = color_masks.get(accessory_id)
                label_name = str(candidate.get("label") or accessory_id or "目标配件")
                if ai_mask is None or int(np.count_nonzero(ai_mask)) == 0:
                    fallback_failure: dict[str, Any] | None = None
                    if mask_targets_per_call == 1 and mask_generation_attempts > 1:
                        for retry_index in range(2, mask_generation_attempts + 1):
                            fallback_label, fallback_failure = self.models.auto_optimize_generate_label_for_candidate()(
                                sample,
                                candidate,
                                provider_settings,
                                model,
                                artifact_dir,
                            )
                            if fallback_label:
                                fallback_label.setdefault("mask_meta", {})["generation_attempt"] = retry_index
                                fallback_label["mask_meta"]["fallback_reason"] = "retry_after_no_highlight_component"
                                labels.append(fallback_label)
                                api_calls.append(
                                    {
                                        "provider": str(provider_settings.get("provider") or "image_generation"),
                                        "model": str(model or ""),
                                        "created_at": int(time.time()),
                                        "latency_ms": int((fallback_label.get("mask_meta") or {}).get("latency_ms") or 0),
                                        "attempts": int((fallback_label.get("mask_meta") or {}).get("attempts") or 1),
                                        "retry_count": int((fallback_label.get("mask_meta") or {}).get("retry_count") or 0),
                                        "previous_errors": (fallback_label.get("mask_meta") or {}).get("previous_errors") if isinstance(fallback_label.get("mask_meta"), dict) else [],
                                        "chunk_index": chunk_number,
                                        "targets_per_call": 1,
                                        "generation_attempt": retry_index,
                                        "fallback_reason": "no_highlight_component",
                                        "prompt_mode": self.policy.AUTO_OPTIMIZE_MASK_PROMPT_MODE(),
                                    }
                                )
                                break
                            if not fallback_failure or fallback_failure.get("reason") not in {"no_highlight_component", "empty_scaled_mask", "generated_mask_unreadable", "mask_decode_failed", "ai_mask_auto_crop_mismatch"}:
                                break
                        if fallback_label:
                            continue
                    if fallback_failure:
                        fallback_failure = {k: v for k, v in fallback_failure.items() if k != "full_mask"}
                    failures.append(
                        {
                            "accessory_id": accessory_id,
                            "label": label_name,
                            "status": "rejected",
                            "reason": "no_highlight_component",
                            "color": palette.get("name"),
                            "color_hex": palette.get("hex"),
                            "fallback_failure": fallback_failure,
                        }
                    )
                    continue
                full_mask = cv2.resize(ai_mask, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
                bbox = self.policy.alpha_bbox()(full_mask, threshold=8)
                if bbox == [0, 0, 0, 0]:
                    fallback_failure = None
                    if mask_targets_per_call == 1 and mask_generation_attempts > 1:
                        for retry_index in range(2, mask_generation_attempts + 1):
                            fallback_label, fallback_failure = self.models.auto_optimize_generate_label_for_candidate()(
                                sample,
                                candidate,
                                provider_settings,
                                model,
                                artifact_dir,
                            )
                            if fallback_label:
                                fallback_label.setdefault("mask_meta", {})["generation_attempt"] = retry_index
                                fallback_label["mask_meta"]["fallback_reason"] = "retry_after_empty_scaled_mask"
                                labels.append(fallback_label)
                                break
                            if not fallback_failure or fallback_failure.get("reason") not in {"no_highlight_component", "empty_scaled_mask", "generated_mask_unreadable", "mask_decode_failed", "ai_mask_auto_crop_mismatch"}:
                                break
                        if fallback_label:
                            continue
                    if fallback_failure:
                        fallback_failure = {k: v for k, v in fallback_failure.items() if k != "full_mask"}
                    failures.append(
                        {
                            "accessory_id": accessory_id,
                            "label": label_name,
                            "status": "rejected",
                            "reason": "empty_scaled_mask",
                            "color": palette.get("name"),
                            "color_hex": palette.get("hex"),
                            "fallback_failure": fallback_failure,
                        }
                    )
                    continue
                x1, y1, x2, y2 = bbox
                bgr = tuple(int(v) for v in (palette.get("bgr") or (0, 255, 0))[:3])
                text_gate = self.policy.validate_auto_optimize_text_mask_region()(
                    image_bgr,
                    full_mask,
                    [int(x1), int(y1), int(x2), int(y2)],
                    candidate,
                    profile,
                )
                if not text_gate.get("ok"):
                    failures.append(
                        {
                            "accessory_id": accessory_id,
                            "label": label_name,
                            "status": "rejected",
                            "reason": text_gate.get("reason") or "text_mask_region_failed_quality_gate",
                            "color": palette.get("name"),
                            "color_hex": palette.get("hex"),
                            "color_bgr": list(bgr),
                            "bbox_xyxy": [int(x1), int(y1), int(x2), int(y2)],
                            "full_mask": full_mask,
                            "metrics": text_gate,
                        }
                    )
                    continue
                sprite_artifact = self.artifacts.auto_optimize_write_sprite_artifact()(
                    image_bgr=image_bgr,
                    full_mask=full_mask,
                    bbox=[int(x1), int(y1), int(x2), int(y2)],
                    sample_id=sample_id,
                    accessory_id=accessory_id,
                    label_name=label_name,
                    artifact_dir=artifact_dir,
                    source_image_path=image_path,
                )
                base_meta = {
                    "input_size_px": [int(input_w), int(input_h)],
                    "scale_xy": [round(float(scale_x), 6), round(float(scale_y), 6)],
                    "latency_ms": int(result.get("latency_ms") or 0),
                    "attempts": int(result.get("attempts") or 1),
                    "retry_count": int(result.get("retry_count") or 0),
                    "previous_errors": result.get("previous_errors") if isinstance(result.get("previous_errors"), list) else [],
                    "model": str(model or ""),
                    "multi_color": True,
                    "class_check": "matched",
                    "color": palette.get("name"),
                    "color_hex": palette.get("hex"),
                    "mask_meta": mask_meta,
                    "processing_artifacts": {
                        "transparent_sprite_url": sprite_artifact.get("url") or "",
                        "raw_transparent_sprite_url": sprite_artifact.get("raw_url") or "",
                    },
                }
                entry = {
                    "accessory_id": accessory_id,
                    "label": label_name,
                    "bbox_xyxy": [int(x1), int(y1), int(x2), int(y2)],
                    "confidence": float(candidate.get("confidence") or 0.0),
                    "sprite": sprite_artifact,
                    "mask_meta": base_meta,
                    "color": palette.get("name"),
                    "color_hex": palette.get("hex"),
                    "color_bgr": list(bgr),
                    "full_mask": full_mask,
                    "profile": profile,
                    "candidate": candidate,
                }
                labels.append(entry)
        pre_verifier_mask = np.zeros((orig_h, orig_w, 3), dtype=np.uint8)
        for entry in [*labels, *failures]:
            full_mask = entry.get("full_mask") if isinstance(entry, dict) else None
            color_bgr = entry.get("color_bgr") if isinstance(entry, dict) else None
            if isinstance(full_mask, np.ndarray) and isinstance(color_bgr, list) and len(color_bgr) >= 3:
                pre_verifier_mask[full_mask > 8] = tuple(int(value) for value in color_bgr[:3])
        pre_verifier_mask_path = artifact_dir / f"{sample_id}_multicolor_mask_all_targets.png"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts._image_files().imwrite(str(pre_verifier_mask_path), pre_verifier_mask)

        verifier_meta = {"enabled": False, "status": "skipped"}
        if labels:
            labels, verifier_failures, verifier_meta = self.models.verify_auto_optimize_mask_sample()(sample, image_bgr, labels)
            failures.extend(verifier_failures)
        combined_mask = np.zeros((orig_h, orig_w, 3), dtype=np.uint8)
        for label in labels:
            full_mask = label.get("full_mask")
            color_bgr = label.get("color_bgr")
            if isinstance(full_mask, np.ndarray) and isinstance(color_bgr, list) and len(color_bgr) >= 3:
                combined_mask[full_mask > 8] = tuple(int(value) for value in color_bgr[:3])
        combined_mask_path = artifact_dir / f"{sample_id}_multicolor_mask_combined.png"
        review_overlay_path = artifact_dir / f"{sample_id}_ai_mask_review_overlay.jpg"
        self.artifacts._image_files().imwrite(str(combined_mask_path), combined_mask)
        review_url, review_meta = self.policy.draw_auto_optimize_review_overlay()(image_bgr, labels, failures, review_overlay_path)
        for entry in [*labels, *failures]:
            entry.pop("full_mask", None)
            entry.pop("profile", None)
            entry.pop("candidate", None)
        artifacts = {
            "multi_color": True,
            "pre_verifier_mask_url": self.artifacts.public_output_url_for_existing()(pre_verifier_mask_path),
            "all_targets_mask_url": self.artifacts.public_output_url_for_existing()(pre_verifier_mask_path),
            "color_mask_url": self.artifacts.public_output_url_for_existing()(combined_mask_path),
            "review_overlay_url": review_url,
            "review_meta": review_meta,
            "class_check": {
                "expected_count": len(candidates),
                "matched_count": len(labels),
                "missing_count": len([item for item in failures if isinstance(item, dict) and item.get("reason") in {"no_highlight_component", "empty_scaled_mask"}]),
                "status": "matched" if labels and not failures else "needs_review",
            },
            "api_calls": api_calls,
            "verifier": verifier_meta,
            "started_at": started,
            "completed_at": int(time.time()),
        }
        return labels, failures, artifacts

    def auto_optimize_generate_label_for_candidate(
        self,
        sample: dict[str, Any],
        candidate: dict[str, Any],
        provider_settings: dict[str, Any],
        model: str,
        artifact_dir: Path,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        image_path = self.artifacts.resolve_service_path()((sample.get("source_image") or {}).get("path"))
        image_bgr = self.artifacts._image_files().imread(str(image_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            return None, {"status": "failed", "reason": "source_image_unreadable"}
        payload = self.policy.photo_highlight_input_data_url()(image_bgr)
        if payload is None:
            return None, {"status": "failed", "reason": "source_image_encode_failed"}
        ai_bgr, data_url, scale_x, scale_y = payload
        input_h, input_w = ai_bgr.shape[:2]
        accessories_by_id = self.policy.auto_optimize_accessory_lookup_for_sample()(sample)
        assignments = [
            {
                "candidate": candidate,
                "palette": self.policy.AUTO_OPTIMIZE_MASK_PALETTE()[0],
                "profile": self.policy.auto_optimize_mask_target_profile()(candidate, accessories_by_id),
            }
        ]
        prompt = self.policy.auto_optimize_multicolor_mask_prompt()(assignments, input_w=input_w, input_h=input_h)
        user_content = [
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
        ]
        try:
            result = self.models.auto_optimize_generate_image_with_retry()(
                provider_settings,
                model,
                prompt,
                user_content,
            )
        except self.models.AiProviderError() as exc:
            return None, {
                "status": "failed",
                "reason": self.policy.bounded_text()(str(exc), 180),
                "attempts": getattr(exc, "attempts", None),
                "retry_count": getattr(exc, "retry_count", None),
                "previous_errors": getattr(exc, "previous_errors", [])[-3:],
            }
        mask_path = artifact_dir / f"{self.artifacts.safe_record_id()(str(sample.get('sample_id') or 'sample'))}_{self.artifacts.safe_record_id()(str(candidate.get('accessory_id') or 'item'))}.png"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts._business_files().write_bytes(mask_path, result["bytes"])
        mask_bgr = self.artifacts._image_files().imread(str(mask_path), cv2.IMREAD_COLOR)
        mask_url = self.artifacts.public_output_url_for_existing()(mask_path)
        if mask_bgr is None:
            return None, {"status": "failed", "reason": "generated_mask_unreadable", "mask_url": mask_url}
        if mask_bgr.shape[1] != input_w or mask_bgr.shape[0] != input_h:
            mask_bgr = cv2.resize(mask_bgr, (input_w, input_h), interpolation=cv2.INTER_NEAREST)
            self.artifacts._image_files().imwrite(str(mask_path), mask_bgr)
        ai_mask, mask_meta = self.policy.decode_photo_highlight_mask()(mask_bgr)
        if not mask_meta.get("ok"):
            return None, {
                "status": "rejected",
                "reason": mask_meta.get("reason") or "mask_decode_failed",
                "mask_url": self.artifacts.public_output_url_for_existing()(mask_path),
                "mask_meta": mask_meta,
            }
        orig_h, orig_w = image_bgr.shape[:2]
        full_mask = cv2.resize(ai_mask, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
        bbox = self.policy.alpha_bbox()(full_mask, threshold=8)
        if bbox == [0, 0, 0, 0]:
            return None, {
                "status": "rejected",
                "reason": "empty_scaled_mask",
                "mask_url": self.artifacts.public_output_url_for_existing()(mask_path),
                "mask_meta": mask_meta,
            }
        x1, y1, x2, y2 = bbox
        profile = assignments[0].get("profile") if isinstance(assignments[0].get("profile"), dict) else {}
        text_gate = self.policy.validate_auto_optimize_text_mask_region()(
            image_bgr,
            full_mask,
            [int(x1), int(y1), int(x2), int(y2)],
            candidate,
            profile,
        )
        if not text_gate.get("ok"):
            return None, {
                "status": "rejected",
                "reason": text_gate.get("reason") or "text_mask_region_failed_quality_gate",
                "bbox_xyxy": [int(x1), int(y1), int(x2), int(y2)],
                "full_mask": full_mask,
                "metrics": text_gate,
                "mask_url": self.artifacts.public_output_url_for_existing()(mask_path),
                "mask_meta": mask_meta,
            }
        roi_bgr = image_bgr[y1:y2, x1:x2].copy()
        roi_mask = full_mask[y1:y2, x1:x2].copy()
        auto_mask, auto_meta = self.policy.photo_highlight_auto_roi_mask()(roi_bgr, roi_mask)
        compare_meta = self.policy.photo_highlight_auto_compare()(roi_mask, auto_mask)
        artifact_stem = f"{self.artifacts.safe_record_id()(str(sample.get('sample_id') or 'sample'))}_{self.artifacts.safe_record_id()(str(candidate.get('accessory_id') or 'item'))}"
        box_overlay_path = artifact_dir / f"{artifact_stem}_ai_mask_box_overlay.jpg"
        roi_path = artifact_dir / f"{artifact_stem}_roi.png"
        ai_roi_mask_path = artifact_dir / f"{artifact_stem}_ai_roi_mask.png"
        auto_roi_mask_path = artifact_dir / f"{artifact_stem}_traditional_roi_mask.png"
        transparent_path = artifact_dir / f"{artifact_stem}_transparent_sprite.png"
        try:
            box_overlay = image_bgr.copy()
            mask_overlay = box_overlay.copy()
            mask_overlay[full_mask > 8] = (0, 210, 0)
            box_overlay = cv2.addWeighted(mask_overlay, 0.28, box_overlay, 0.72, 0)
            cv2.rectangle(box_overlay, (int(x1), int(y1)), (int(x2), int(y2)), (0, 220, 0), 4, cv2.LINE_AA)
            label_text = self.policy.bounded_text()(candidate.get("label") or candidate.get("accessory_id") or "AI mask box", 48)
            cv2.putText(
                box_overlay,
                label_text,
                (int(x1), max(24, int(y1) - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 220, 0),
                2,
                cv2.LINE_AA,
            )
            self.artifacts._image_files().imwrite(str(box_overlay_path), box_overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            self.artifacts._image_files().imwrite(str(roi_path), roi_bgr)
            self.artifacts._image_files().imwrite(str(ai_roi_mask_path), roi_mask)
            if auto_mask is not None:
                self.artifacts._image_files().imwrite(str(auto_roi_mask_path), auto_mask)
            bgra = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2BGRA)
            bgra[:, :, 3] = roi_mask
            self.artifacts._image_files().imwrite(str(transparent_path), bgra)
        except Exception:
            pass
        sprite_artifact = self.artifacts.auto_optimize_write_sprite_artifact()(
            image_bgr=image_bgr,
            full_mask=full_mask,
            bbox=[int(x1), int(y1), int(x2), int(y2)],
            sample_id=self.artifacts.safe_record_id()(str(sample.get("sample_id") or "sample")),
            accessory_id=str(candidate.get("accessory_id") or ""),
            label_name=str(candidate.get("label") or candidate.get("accessory_id") or ""),
            artifact_dir=artifact_dir,
            source_image_path=image_path,
        )
        processing_artifacts = {
            "ai_mask_box_overlay_url": self.artifacts.public_output_url_for_existing()(box_overlay_path),
            "source_roi_url": self.artifacts.public_output_url_for_existing()(roi_path),
            "ai_roi_mask_url": self.artifacts.public_output_url_for_existing()(ai_roi_mask_path),
            "traditional_roi_mask_url": self.artifacts.public_output_url_for_existing()(auto_roi_mask_path),
            "transparent_sprite_url": sprite_artifact.get("url") or self.artifacts.public_output_url_for_existing()(transparent_path),
            "raw_transparent_sprite_url": sprite_artifact.get("raw_url") or "",
        }
        palette = self.policy.AUTO_OPTIMIZE_MASK_PALETTE()[0]
        bgr = tuple(int(v) for v in (palette.get("bgr") or (0, 255, 0))[:3])
        label = {
            "accessory_id": str(candidate.get("accessory_id") or ""),
            "label": str(candidate.get("label") or candidate.get("accessory_id") or ""),
            "bbox_xyxy": [int(x1), int(y1), int(x2), int(y2)],
            "confidence": float(candidate.get("confidence") or 0.0),
            "mask_path": str(mask_path),
            "mask_url": self.artifacts.public_output_url_for_existing()(mask_path),
            "sprite": sprite_artifact,
            "mask_meta": {
                **mask_meta,
                "auto_roi_mask": auto_meta,
                "auto_compare": compare_meta,
                "processing_artifacts": processing_artifacts,
                "input_size_px": [int(input_w), int(input_h)],
                "scale_xy": [round(float(scale_x), 6), round(float(scale_y), 6)],
                "latency_ms": int(result.get("latency_ms") or 0),
                "attempts": int(result.get("attempts") or 1),
                "retry_count": int(result.get("retry_count") or 0),
                "previous_errors": result.get("previous_errors") if isinstance(result.get("previous_errors"), list) else [],
                "model": str(model or ""),
                "prompt_mode": self.policy.AUTO_OPTIMIZE_MASK_PROMPT_MODE(),
                "fallback_single_target": True,
            },
            "color": palette.get("name"),
            "color_hex": palette.get("hex"),
            "color_bgr": list(bgr),
            "full_mask": full_mask,
            "profile": profile,
            "candidate": candidate,
        }
        status = "trainable" if compare_meta.get("ok") else "review_required"
        return label, {
            "status": status,
            "reason": "" if compare_meta.get("ok") else compare_meta.get("reason") or "ai_mask_auto_crop_mismatch",
            "score": compare_meta.get("score") or 0.0,
            "bbox_xyxy": [int(x1), int(y1), int(x2), int(y2)],
            "mask_url": self.artifacts.public_output_url_for_existing()(mask_path),
            "processing_artifacts": processing_artifacts,
            "mask_meta": {
                **mask_meta,
                "auto_roi_mask": auto_meta,
                "auto_compare": compare_meta,
            },
        }
