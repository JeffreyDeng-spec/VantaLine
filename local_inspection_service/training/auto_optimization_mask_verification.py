"""Mask review orchestration; policy and provider attempts retain original semantics."""
from dataclasses import dataclass
from typing import Any
import json
import numpy as np

from .auto_optimization_mask_verification_ports import AutoOptimizationMaskVerificationPorts


@dataclass(frozen=True)
class AutoOptimizationMaskVerification:
    ports: AutoOptimizationMaskVerificationPorts

    def verify_auto_optimize_mask_sample(self, sample: dict[str, Any], image_bgr: np.ndarray, labels: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        if not labels:
            return (labels, [], {'enabled': True, 'status': 'skipped_empty'})
        settings = self.ports.ai_detection_settings()('training_vision')
        if not settings.get('configured'):
            failures = [{'accessory_id': label.get('accessory_id'), 'label': label.get('label'), 'status': 'failed', 'reason': 'mask_verifier_provider_not_configured', 'bbox_xyxy': label.get('bbox_xyxy'), 'color': label.get('color'), 'color_hex': label.get('color_hex'), 'color_bgr': label.get('color_bgr'), 'full_mask': label.get('full_mask')} for label in labels]
            return ([], failures, {'enabled': True, 'status': 'failed', 'reason': 'provider_not_configured'})
        targets_payload: list[dict[str, Any]] = []
        label_by_id = {str(label.get('accessory_id') or ''): label for label in labels}
        for label in labels:
            profile = label.get('profile') if isinstance(label.get('profile'), dict) else {}
            candidate = label.get('candidate') if isinstance(label.get('candidate'), dict) else {}
            accessory_id = str(label.get('accessory_id') or '')
            negative_candidates = [{'accessory_id': str(other.get('accessory_id') or ''), 'label': str(other.get('label') or other.get('accessory_id') or '')} for other in labels if str(other.get('accessory_id') or '') != accessory_id]
            targets_payload.append({'accessory_id': accessory_id, 'label': str(label.get('label') or accessory_id), 'bbox_xyxy': label.get('bbox_xyxy'), 'assigned_color': label.get('color_hex') or label.get('color'), 'detection_evidence': self.ports.bounded_text()(candidate.get('evidence') or '', 220), 'ai_profile': {'material_type': profile.get('material_type') or 'unknown', 'description': profile.get('description') or '', 'visual_signature': profile.get('visual_signature') or '', 'distinguishing_text': profile.get('distinguishing_text') if isinstance(profile.get('distinguishing_text'), list) else [], 'positive_cues': profile.get('positive_cues') if isinstance(profile.get('positive_cues'), list) else [], 'negative_cues': profile.get('negative_cues') if isinstance(profile.get('negative_cues'), list) else [], 'mask_scope': profile.get('mask_scope') or ''}, 'negative_candidates': negative_candidates})
        task_payload = {'task_type': 'mask_verification', 'request_id': sample.get('request_id') or sample.get('sample_id') or '', 'acceptance_policy': {'accept': 'masked region is the exact intended accessory and tightly localized', 'reject': 'wrong object, sibling part, handle/cap, background, shadow, or unrelated region', 'review': 'uncertain identity or partial localization'}, 'thresholds': {'identity_score': 0.75, 'localization_score': 0.7, 'negative_match_score': 0.25}, 'targets': targets_payload}
        user_content: list[dict[str, Any]] = [{'type': 'text', 'text': 'MASK_VERIFIER_TASK_JSON:\n' + json.dumps(task_payload, ensure_ascii=False, indent=2)}, {'type': 'text', 'text': 'ORIGINAL_INSPECTION_IMAGE'}, {'type': 'image_url', 'image_url': {'url': self.ports.image_bgr_data_url()(image_bgr, max_side=1280, quality=82), 'detail': 'high'}}, {'type': 'text', 'text': 'MASK_OVERLAY_IMAGE: colored regions and bounding boxes to verify.'}, {'type': 'image_url', 'image_url': {'url': self.ports.image_bgr_data_url()(self.ports.auto_optimize_mask_verifier_overlay()(image_bgr, labels), max_side=1280, quality=84), 'detail': 'high'}}]
        for label in labels:
            crop = self.ports.auto_optimize_mask_verifier_crop()(image_bgr, label)
            if crop is None:
                continue
            user_content.append({'type': 'text', 'text': f"MASKED_CROP accessory_id={label.get('accessory_id')} label={label.get('label')} color={label.get('color_hex') or label.get('color')}"})
            user_content.append({'type': 'image_url', 'image_url': {'url': self.ports.image_bgr_data_url()(crop, max_side=768, quality=84), 'detail': 'high'}})
        try:
            parsed, latency_ms, provider_meta = self.ports.generate_provider_json_with_fallback()(settings, self.ports.MASK_VERIFIER_SYSTEM_PROMPT(), user_content, max_tokens=1800, max_attempts=3, overloaded_retry_delay_seconds=3.0, allow_overloaded_model_fallback=False)
        except self.ports.AiProviderError() as exc:
            failures = []
            for label in labels:
                failures.append({'accessory_id': label.get('accessory_id'), 'label': label.get('label'), 'status': 'failed', 'reason': 'mask_verifier_provider_failed', 'error': self.ports.bounded_text()(str(exc), 220), 'attempts': getattr(exc, 'attempts', None), 'retry_count': getattr(exc, 'retry_count', None), 'previous_errors': getattr(exc, 'previous_errors', [])[-3:], 'bbox_xyxy': label.get('bbox_xyxy'), 'color': label.get('color'), 'color_hex': label.get('color_hex'), 'color_bgr': label.get('color_bgr'), 'full_mask': label.get('full_mask')})
            return ([], failures, {'enabled': True, 'status': 'failed', 'reason': 'provider_failed', 'error': self.ports.bounded_text()(str(exc), 240), 'attempts': getattr(exc, 'attempts', None), 'retry_count': getattr(exc, 'retry_count', None)})
        raw_targets = parsed.get('targets') if isinstance(parsed.get('targets'), list) else []
        decision_by_id = {str(item.get('accessory_id') or ''): item for item in raw_targets if isinstance(item, dict)}
        accepted: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        normalized_targets: list[dict[str, Any]] = []
        for accessory_id, label in label_by_id.items():
            raw = decision_by_id.get(accessory_id) or {}
            identity = self.ports.clamp_unit_score()(raw.get('identity_score'))
            localization = self.ports.clamp_unit_score()(raw.get('localization_score'))
            negative = self.ports.clamp_unit_score()(raw.get('negative_match_score'))
            decision = str(raw.get('decision') or '').strip().lower()
            matches = bool(raw.get('mask_region_matches_target'))
            auto_accept = matches and decision == 'accept' and (identity >= 0.75) and (localization >= 0.7) and (negative <= 0.25)
            normalized = {'accessory_id': accessory_id, 'label': label.get('label'), 'mask_region_matches_target': matches, 'identity_score': round(identity, 4), 'localization_score': round(localization, 4), 'negative_match_score': round(negative, 4), 'decision': decision or 'review', 'reason': self.ports.bounded_text()(raw.get('reason') or '', 240), 'wrong_object_evidence': self.ports.string_list()(raw.get('wrong_object_evidence'), max_items=5, max_len=160)}
            normalized_targets.append(normalized)
            label['mask_verifier'] = normalized
            if auto_accept:
                accepted.append(label)
                continue
            review_or_reject = 'rejected' if decision == 'reject' or negative > 0.45 else 'review_required'
            failures.append({'accessory_id': accessory_id, 'label': label.get('label'), 'status': review_or_reject, 'reason': 'mask_verifier_rejected' if review_or_reject == 'rejected' else 'mask_verifier_review_required', 'bbox_xyxy': label.get('bbox_xyxy'), 'color': label.get('color'), 'color_hex': label.get('color_hex'), 'color_bgr': label.get('color_bgr'), 'full_mask': label.get('full_mask'), 'metrics': normalized})
        overall = 'accept' if len(accepted) == len(labels) else 'reject' if any((item.get('status') == 'rejected' for item in failures)) else 'review'
        return (accepted, failures, {'enabled': True, 'status': overall, 'latency_ms': latency_ms, 'provider': settings.get('provider'), 'model': settings.get('model'), 'attempts': provider_meta.get('attempts'), 'retry_count': provider_meta.get('retry_count'), 'targets': normalized_targets, 'raw_overall_decision': parsed.get('overall_decision') or ''})
