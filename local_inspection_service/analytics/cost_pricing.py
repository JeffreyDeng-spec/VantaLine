"""Existing ledger pricing and classification rules (no repricing)."""
import os
import time
from pathlib import Path
from typing import Any

API_COST_PRICING_USD_PER_MILLION = {
    "gemini-3.1-flash-image": {
        "input": 0.50,
        "cached_input": 0.05,
        "output_text": 3.00,
        "output_image": 60.00,
    },
    "gemini-2.5-flash": {
        "input": 0.30,
        "cached_input": 0.075,
        "output_text": 2.50,
        "output_image": 0.0,
    },
    "gemini-2.5-flash-lite": {
        "input": 0.10,
        "cached_input": 0.025,
        "output_text": 0.40,
        "output_image": 0.0,
    },
    # Alibaba Cloud Model Studio Qwen pricing is region/scope-sensitive. This
    # model-only ledger uses the first international tier for the current
    # DashScope International endpoint.
    "qwen3.7-plus": {
        "input": 0.40,
        "cached_input": 0.40,
        "output_text": 1.60,
        "output_image": 0.0,
    },
    "qwen3.7-plus-2026-05-26": {
        "input": 0.40,
        "cached_input": 0.40,
        "output_text": 1.60,
        "output_image": 0.0,
    },
    "qwen3.6-flash": {
        "input": 0.25,
        "cached_input": 0.25,
        "output_text": 1.50,
        "output_image": 0.0,
    },
    "qwen3.6-flash-2026-04-16": {
        "input": 0.25,
        "cached_input": 0.25,
        "output_text": 1.50,
        "output_image": 0.0,
    },
    "qwen3.7-max": {
        "input": 2.50,
        "cached_input": 2.50,
        "output_text": 7.50,
        "output_image": 0.0,
    },
}

API_COST_CATEGORY_LABELS = {
    "image_generation": "生图 API",
    "structured_output": "任务结构性输出 API",
    "agent": "Agent API",
    "training": "RunPod 训练 API",
}

# RunPod serverless bills per GPU-second from worker start to stop. The YOLO
# training endpoint currently runs RTX A5000 flex workers ($0.00026/s per
# RunPod published pricing); override via env if the endpoint GPU tier changes.
RUNPOD_GPU_USD_PER_SECOND_DEFAULT = 0.00026
RUNPOD_GPU_USD_PER_SECOND_ENV = "VANTALINE_RUNPOD_GPU_USD_PER_SECOND"


def runpod_gpu_usd_per_second() -> float:
    raw = str(os.environ.get(RUNPOD_GPU_USD_PER_SECOND_ENV, "") or "").strip()
    try:
        value = float(raw)
    except ValueError:
        return RUNPOD_GPU_USD_PER_SECOND_DEFAULT
    return value if value > 0 else RUNPOD_GPU_USD_PER_SECOND_DEFAULT


def api_cost_pricing_for_model(model: str) -> dict[str, float] | None:
    clean_model = str(model or "").strip()
    if not clean_model:
        return None
    if clean_model in API_COST_PRICING_USD_PER_MILLION:
        return API_COST_PRICING_USD_PER_MILLION[clean_model]
    for key, pricing in API_COST_PRICING_USD_PER_MILLION.items():
        if key in clean_model:
            return pricing
    return None


def api_cost_usage_token_count(usage: dict[str, Any], key: str) -> int:
    aliases = {
        "promptTokenCount": ("promptTokenCount", "prompt_tokens", "input_tokens"),
        "cachedContentTokenCount": ("cachedContentTokenCount", "cached_tokens", "cached_prompt_tokens"),
        "candidatesTokenCount": ("candidatesTokenCount", "completion_tokens", "output_tokens"),
        "thoughtsTokenCount": ("thoughtsTokenCount", "reasoning_tokens"),
        "totalTokenCount": ("totalTokenCount", "total_tokens"),
        "tokenCount": ("tokenCount", "token_count"),
    }
    for candidate in aliases.get(key, (key,)):
        value = usage.get(candidate)
        if value is None:
            continue
        try:
            return max(0, int(float(value or 0)))
        except (TypeError, ValueError):
            continue
    return 0


def api_cost_detail_tokens(usage: dict[str, Any], key: str, modality: str) -> int:
    details = usage.get(key)
    if not isinstance(details, list):
        return 0
    total = 0
    for item in details:
        if not isinstance(item, dict):
            continue
        if str(item.get("modality") or "").upper() != modality.upper():
            continue
        total += api_cost_usage_token_count(item, "tokenCount")
    return total


def api_cost_from_usage(model: str, usage: dict[str, Any]) -> tuple[float, dict[str, int], bool]:
    pricing = api_cost_pricing_for_model(model)
    prompt_tokens = api_cost_usage_token_count(usage, "promptTokenCount")
    cached_tokens = api_cost_usage_token_count(usage, "cachedContentTokenCount")
    output_tokens = (
        api_cost_usage_token_count(usage, "candidatesTokenCount")
        + api_cost_usage_token_count(usage, "thoughtsTokenCount")
    )
    image_output_tokens = api_cost_detail_tokens(usage, "candidatesTokensDetails", "IMAGE")
    if image_output_tokens <= 0:
        image_output_tokens = api_cost_detail_tokens(usage, "outputTokensDetails", "IMAGE")
    if output_tokens <= 0 and image_output_tokens > 0:
        output_tokens = image_output_tokens
    text_output_tokens = max(0, output_tokens - image_output_tokens)
    if prompt_tokens <= 0:
        total_tokens = api_cost_usage_token_count(usage, "totalTokenCount")
        prompt_tokens = max(0, total_tokens - output_tokens)
    non_cached_tokens = max(0, prompt_tokens - cached_tokens)
    tokens = {
        "input": int(non_cached_tokens),
        "cached_input": int(cached_tokens),
        "output_text": int(text_output_tokens),
        "output_image": int(image_output_tokens),
        "total": api_cost_usage_token_count(usage, "totalTokenCount") or int(prompt_tokens + output_tokens),
    }
    if not pricing:
        return 0.0, tokens, False
    cost = (
        tokens["input"] * float(pricing.get("input") or 0.0)
        + tokens["cached_input"] * float(pricing.get("cached_input") or pricing.get("input") or 0.0)
        + tokens["output_text"] * float(pricing.get("output_text") or 0.0)
        + tokens["output_image"] * float(pricing.get("output_image") or 0.0)
    ) / 1_000_000
    return cost, tokens, True


def api_cost_day(timestamp: Any) -> str:
    try:
        ts = int(float(timestamp or 0))
    except (TypeError, ValueError):
        ts = 0
    if ts <= 0:
        ts = int(time.time())
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def api_cost_classify(path: Path, payload: dict[str, Any]) -> tuple[str, str]:
    path_text = str(path).replace("\\", "/").lower()
    provider = str(payload.get("provider") or payload.get("provider_label") or "").lower()
    model = str(payload.get("model") or payload.get("provider_model") or "").lower()
    if "agent_mcp_pose_images" in path_text or "auto_optimize" in path_text or "image_generation" in provider or "image" in model:
        return "image_generation", "生图 / AI mask"
    if "agent" in path_text or provider == "cursor" or "agent" in provider:
        return "agent", "Agent 调用"
    if "ai_profile_cache" in path_text:
        return "structured_output", "AI Profile cache"
    if "data_analysis_records" in path_text:
        return "structured_output", "检测结构化输出"
    return "structured_output", "结构化输出"
