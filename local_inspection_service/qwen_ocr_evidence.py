"""Independent OCR transport and strict, original-pixel evidence normalization.

No standard text is accepted by this module. There are no retries or provider
fallbacks. Callers MUST persist a call claim before invoking ``recognize``.
"""
import base64
import hashlib
import io
import json
import math
from urllib.parse import urlparse

MODEL = "qwen-vl-ocr-2025-11-20"
VERSION = "qwen-ocr-original-pixels-v1"
MAX_PIXELS = 12_582_912
MAX_WORDS = 4096
MAX_TEXT = 100_000
MAX_RESPONSE = 4_000_000


class EvidenceError(ValueError):
    pass


def endpoint(base_url):
    value = urlparse(base_url)
    host = value.hostname or ""
    # Never forward credentials to a model-supplied URL, redirect or arbitrary host.
    if value.scheme != "https" or value.username or value.password or value.port not in (None, 443):
        raise EvidenceError("unapproved_ocr_endpoint")
    if host != "dashscope.aliyuncs.com" and not (host.startswith("ws-") and host.endswith(".cn-beijing.maas.aliyuncs.com")):
        raise EvidenceError("ocr_requires_verified_beijing_endpoint")
    return f"https://{host}/api/v1/services/aigc/multimodal-generation/generation"


def prepare(image):
    # Orientation was normalized by the shared content decoder. Composite alpha
    # on white, not black; do not silently shrink small text in dense sheets.
    if image.width * image.height > MAX_PIXELS or min(image.size) < 28:
        raise EvidenceError("image_capacity_requires_review")
    from PIL import Image
    picture = image.convert("RGBA")
    white = Image.new("RGBA", picture.size, "white")
    white.alpha_composite(picture)
    stream = io.BytesIO()
    white.convert("RGB").save(stream, format="PNG")
    return stream.getvalue(), dict(source_size=list(image.size), input_size=list(image.size),
        scale_x=1, scale_y=1, coordinate_space="orientation_normalized_original_pixels", version=VERSION)


def payload(blob):
    return {"model": MODEL, "input": {"messages": [{"role": "user", "content": [{
        "image": "data:image/png;base64," + base64.b64encode(blob).decode(),
        "min_pixels": 3072, "max_pixels": MAX_PIXELS, "enable_rotate": False,
    }]}]}, "parameters": {"ocr_options": {"task": "advanced_recognition"}, "max_tokens": 8192}}


def normalize(response, size):
    choices = response.get("output", {}).get("choices", [])
    if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
        raise EvidenceError("ocr_incomplete_or_truncated")
    content = choices[0].get("message", {}).get("content", [])
    results = [c["ocr_result"] for c in content if isinstance(c, dict) and "ocr_result" in c]
    if len(results) != 1 or not isinstance(results[0], dict):
        raise EvidenceError("ocr_position_schema_missing")
    words = results[0].get("words_info")
    if not isinstance(words, list) or not 1 <= len(words) <= MAX_WORDS:
        raise EvidenceError("ocr_empty_or_over_capacity")
    width, height = size
    observations = []
    characters = 0
    for order, word in enumerate(words):
        text, location = word.get("text"), word.get("location")
        if not isinstance(text, str) or not text.strip() or len(text) > 8192:
            raise EvidenceError("ocr_invalid_text")
        if not isinstance(location, list) or len(location) != 8 or any(type(v) not in (int, float) or not math.isfinite(v) for v in location):
            raise EvidenceError("ocr_invalid_coordinates")
        points = list(zip(location[::2], location[1::2]))
        if any(not (0 <= x <= width and 0 <= y <= height) for x, y in points):
            raise EvidenceError("ocr_coordinates_outside_original")
        area = abs(sum(points[i][0]*points[(i+1)%4][1] - points[(i+1)%4][0]*points[i][1] for i in range(4))) / 2
        turns = [(points[(i+1)%4][0]-points[i][0])*(points[(i+2)%4][1]-points[(i+1)%4][1]) -
                 (points[(i+1)%4][1]-points[i][1])*(points[(i+2)%4][0]-points[(i+1)%4][0]) for i in range(4)]
        if area <= 0 or not (all(t >= 0 for t in turns) or all(t <= 0 for t in turns)):
            raise EvidenceError("ocr_degenerate_polygon")
        score = word.get("confidence")
        if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1):
            raise EvidenceError("ocr_unknown_confidence_scale")
        characters += len(text)
        if characters > MAX_TEXT:
            raise EvidenceError("ocr_text_capacity")
        digest = hashlib.sha256(json.dumps([order, text, location], ensure_ascii=False).encode()).hexdigest()[:20]
        observations.append(dict(id="o_"+digest, text=text, type="text", polygon=points,
            box=[min(location[::2])/width, min(location[1::2])/height, max(location[::2])/width, max(location[1::2])/height],
            order=order, confidence=score, provenance="qwen_ocr"))
    return observations


def recognize(settings, blob, size, timeout, post=None):
    import requests
    if settings.get("provider") != "qwen" or not settings.get("api_key"):
        raise EvidenceError("qwen_credentials_unavailable")
    post = post or requests.post
    # Explicit no redirects; requests' default adapter does not retry POST.
    response = post(endpoint(settings["base_url"]), headers={"Authorization": "Bearer "+settings["api_key"]},
                    json=payload(blob), timeout=max(.1, timeout), allow_redirects=False, stream=True)
    try:
        if response.status_code != 200:
            raise EvidenceError("ocr_http_"+str(response.status_code))
        chunks, total = [], 0
        for chunk in response.iter_content(65536):
            total += len(chunk)
            if total > MAX_RESPONSE:
                raise EvidenceError("ocr_response_capacity")
            chunks.append(chunk)
        raw = json.loads(b"".join(chunks))
        observations = normalize(raw, size)
        # Do not retain arbitrary provider fields (could echo credentials/input).
        return observations, dict(model=MODEL, preprocess_version=VERSION,
            usage=raw.get("usage", {}), request_id=raw.get("request_id"),
            finish_reason="stop", words_info=observations)
    finally:
        response.close()
