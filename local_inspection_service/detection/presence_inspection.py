"""Presence inspection flow; explicit capabilities preserve provider and evidence ordering."""
from collections.abc import Callable
from pathlib import Path
from typing import Any
import json
import numpy as np
from .presence_inspection_ports import PresenceInput, PresenceGeneration, PresenceOutput, PresencePolicy


class PresenceInspection:
    def __init__(self, inputs: PresenceInput, generation: PresenceGeneration,
                 output: PresenceOutput, policy: PresencePolicy, clock: Callable[[], float]):
        self.input, self.generation, self.output, self.policy, self.clock = inputs, generation, output, policy, clock

    def tool_vision_inspect_presence(self, payload: dict[str, Any]) -> dict[str, Any]:
        trace_start = self.clock()
        timing: dict[str, int] = {}

        def mark(name: str) -> None:
            timing[name] = int((self.clock() - trace_start) * 1000)

        settings = dict(payload.get("provider_config") or self.input.settings())
        required_accessories = [
            item for item in (payload.get("required_accessories") or []) if isinstance(item, dict) and item.get("accessory_id")
        ]
        if not required_accessories:
            required_accessories = self.input.resolve()(payload.get("required_accessory_refs") or [])
        mark("resolved_required_ms")
        if not settings.get("configured"):
            return self.output.failure()(required_accessories, settings, reason=settings.get("message") or "AI provider is not configured")
        inspection_data_url = str(payload.get("inspection_image_data_url") or "")
        if not inspection_data_url:
            inspection_path = str(payload.get("inspection_image_path") or "")
            if inspection_path:
                inspection_data_url = self.input.path()(
                    Path(inspection_path),
                    max_side=self.policy.max_side(),
                    quality=self.policy.quality(),
                )
                if not inspection_data_url:
                    return self.output.failure()(required_accessories, settings, reason="Inspection image path could not be encoded")
            else:
                image_bgr = payload.get("inspection_image_bgr")
                if not isinstance(image_bgr, np.ndarray):
                    return self.output.failure()(required_accessories, settings, reason="Inspection image payload was missing")
                inspection_data_url = self.input.image()(
                    image_bgr,
                    max_side=self.policy.max_side(),
                    quality=self.policy.quality(),
                )
        mark("inspection_encoded_ms")
        task_payload = self.generation.task(required_accessories)
        profile_cache = self.generation.cache(required_accessories, settings)
        cache_provider_calls = max(0, int(profile_cache.get("provider_call_count") or 0))
        generate_attempt_budget = max(1, self.policy.max_attempts() - cache_provider_calls)
        profile_cache["provider_call_budget"] = self.policy.max_attempts()
        profile_cache["generate_attempt_budget"] = generate_attempt_budget
        profile_cache["profile_provider_call_count"] = cache_provider_calls
        mark("profile_cache_ready_ms")
        if profile_cache.get("enabled") and profile_cache.get("name"):
            user_content: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        "INSPECTION_IMAGE: decide presence only from the next image, using the cached required accessory "
                        "profile context. Current required accessory IDs and cues are repeated here to avoid ID drift:\n"
                        + json.dumps(task_payload, ensure_ascii=False)
                        + "\nReturn compact boolean/count QA JSON only. No narrative. "
                        "Count substantial identifiable partial views as present; reject only tiny or ambiguous fragments."
                    ),
                },
                {"type": "image_url", "image_url": {"url": inspection_data_url, "detail": "high"}},
            ]
        else:
            user_content = [
                {"type": "text", "text": json.dumps(task_payload, ensure_ascii=False)},
                {
                    "type": "text",
                    "text": (
                        "INSPECTION_IMAGE: decide presence only from the next image. "
                        "Return compact boolean/count QA JSON only. No narrative. "
                        "Count substantial identifiable partial views as present; reject only tiny or ambiguous fragments."
                    ),
                },
                {"type": "image_url", "image_url": {"url": inspection_data_url, "detail": "high"}},
            ]
        reference_count = 0
        per_accessory_reference_counts: dict[str, int] = {}
        for ref in payload.get("reference_descriptors") or []:
            if not isinstance(ref, dict) or not ref.get("data_url"):
                continue
            item_id = str(ref.get("accessory_id") or "")
            if not item_id:
                continue
            current_count = per_accessory_reference_counts.get(item_id, 0)
            if current_count >= self.policy.references():
                continue
            per_accessory_reference_counts[item_id] = current_count + 1
            user_content.append(
                {
                    "type": "text",
                    "text": f"REFERENCE_IMAGE for accessory_id={item_id}. Use this only as appearance evidence; do not count it as present.",
                }
            )
            user_content.append({"type": "image_url", "image_url": {"url": ref["data_url"], "detail": ref.get("detail", "low")}})
            reference_count += 1
        mark("user_content_ready_ms")
        generate_payload = {
            "provider_config": settings,
            "system_prompt": self.policy.prompt(),
            "user_content": user_content,
            "max_tokens": self.generation.tokens()(len(required_accessories), settings),
            "schema_hint": self.policy.schema(),
            "cached_content": profile_cache.get("name") if profile_cache.get("enabled") else "",
            "max_attempts": generate_attempt_budget,
        }
        provider_result = self.generation.call()("provider.gemini.generate_json", generate_payload)
        required_ids = {str(item.get("accessory_id") or "") for item in required_accessories if item.get("accessory_id")}
        if (
            str(settings.get("provider") or "") == "qwen"
            and provider_result.get("ok")
            and not self.generation.covers()(provider_result.get("parsed"), required_ids)
        ):
            # qwen occasionally returns a syntactically valid but empty/unrelated
            # JSON object. Without this check that would silently normalize into an
            # all-missing verdict; instead retry once, then fail closed as an
            # explicit provider failure so it is visible and re-runnable.
            retry_result = self.generation.call()(
                "provider.gemini.generate_json",
                {
                    **generate_payload,
                    "user_content": [
                        *user_content,
                        {
                            "type": "text",
                            "text": (
                                "RETRY_COVERAGE: the previous response did not include any of the required accessory_id "
                                "entries. Return the compact QA JSON with one detections entry per required accessory_id "
                                "listed in the task payload, using those exact accessory_id strings."
                            ),
                        },
                    ],
                    "max_attempts": 1,
                },
            )
            retry_meta = retry_result.get("meta") if isinstance(retry_result.get("meta"), dict) else {}
            if retry_result.get("ok") and self.generation.covers()(retry_result.get("parsed"), required_ids):
                provider_result = {**retry_result, "meta": {**retry_meta, "coverage_retry": True}}
            else:
                provider_result = {
                    **retry_result,
                    "ok": False,
                    "error": retry_result.get("error") or "AI provider response did not cover any required accessory",
                    "provider_failure": True,
                    "meta": {**retry_meta, "coverage_retry": True, "coverage_retry_failed": True},
                }
        mark("provider_result_ready_ms")
        if not provider_result.get("ok"):
            failure = self.output.failure()(
                required_accessories,
                settings,
                reason=provider_result.get("error") or "AI provider failed",
                timed_out=bool(provider_result.get("timed_out")),
                latency_ms=int(provider_result.get("latency_ms") or 0),
            )
            failure["ai"].update(provider_result.get("meta") if isinstance(provider_result.get("meta"), dict) else {})
            failure["ai"]["profile_cache"] = {
                key: value
                for key, value in profile_cache.items()
                if key
                in {
                    "enabled",
                    "status",
                    "reference_images",
                    "latency_ms",
                    "cache_key",
                    "error",
                    "usage_metadata",
                    "provider_call_count",
                    "provider_call_budget",
                    "profile_provider_call_count",
                    "generate_attempt_budget",
                }
            }
            failure.setdefault("ai", {})["timing"] = timing
            return failure
        result = self.output.normalize()(
            provider_result.get("parsed") or {},
            required_accessories,
            int(provider_result.get("latency_ms") or 0),
            settings,
        )
        result["ai"]["reference_images"] = int(profile_cache.get("reference_images") or reference_count)
        result["ai"]["profile_cache"] = {
            key: value
            for key, value in profile_cache.items()
            if key
            in {
                "enabled",
                "status",
                "reference_images",
                "latency_ms",
                "cache_key",
                "error",
                "usage_metadata",
                "provider_call_count",
                "provider_call_budget",
                "profile_provider_call_count",
                "generate_attempt_budget",
            }
        }
        result["ai"].update(provider_result.get("meta") if isinstance(provider_result.get("meta"), dict) else {})
        result["ai"]["timing"] = timing
        return result
