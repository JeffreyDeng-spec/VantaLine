"""Colleague layout prompt port. Rectangle localization, NOT mask segmentation.

No keys/configuration are owned here. The caller supplies a frozen server settings
snapshot and persists its attempt before calling request_once. Never retry.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import urllib.request
from PIL import Image
from . import label_extraction as geometry

VERSION = "colleague-layout-qwen-1"
TIMEOUT = 180
PROMPT = '''看这张图片，判断里面包含几个标签。

- 如果只有1个标签，返回 isMultiLabel=false
- 如果有多个标签（网格排列），返回 isMultiLabel=true，并找出其中最完整、最清晰的一个标签，返回它的位置（相对于整张图的比例，0~1）

只输出JSON：
```json
{
  "isMultiLabel": true,
  "labelCount": 6,
  "cropRect": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.15}
}
```

如果没有标签或者无法判断，返回：
```json
{
  "isMultiLabel": false,
  "labelCount": 0,
  "cropRect": null
}
```'''


def prepare(original: bytes):
    with Image.open(io.BytesIO(original)) as image:
        image = image.convert("RGB")
        source_size = list(image.size)
        scale = min(1, 1600 / max(image.size))
        size = tuple(max(1, int(v * scale)) for v in image.size)
        if size != image.size:
            image = image.resize(size, Image.Resampling.BICUBIC)
        stream = io.BytesIO()
        image.save(stream, "JPEG", quality=90)
    data = stream.getvalue()
    return data, {"source_size": source_size, "input_size": list(size),
                  "input_sha256": hashlib.sha256(data).hexdigest(),
                  "scope": "whole_image", "jpeg_quality": 90,
                  "resize_implementation": "Pillow bicubic; not byte-identical to GDI+",
                  "prompt_version": VERSION, "prompt": PROMPT,
                  "temperature": .1, "max_tokens": 512,
                  "enable_thinking": False, "timeout_seconds": TIMEOUT,
                  "mask_kind": "coordinate_rectangle_not_segmentation"}


def payload(data: bytes, model: str):
    return {"model": model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(data).decode()}}
    ]}], "temperature": .1, "max_tokens": 512, "enable_thinking": False}


def evidence(body: str, key: str = ""):
    """Bounded text evidence, including JSON embedded in the model content."""
    if key:
        body = body.replace(key, "<redacted>")
    body = re.sub(r"data:[^\s\"\\]+;base64,[A-Za-z0-9+/=]+", "<embedded-media>", body)
    body = re.sub(r"(?i)Bearer\s+[^\s\"\\]+", "Bearer <redacted>", body)
    def clean(value, depth=0):
        if depth > 10: return "<depth-limit>"
        if isinstance(value, dict):
            return {str(k): "<redacted>" if re.search(r"(?i)(api.?key|token|secret|cookie|authorization)",str(k)) and k not in ("prompt_tokens","completion_tokens","total_tokens") else clean(v,depth+1) for k,v in list(value.items())[:100]}
        if isinstance(value,list):return [clean(v,depth+1) for v in value[:100]]
        if isinstance(value,str):
            candidate=value.strip()
            if (candidate.startswith("```json\n") or candidate.startswith("```\n")) and candidate.endswith("```"):
                candidate=candidate.split("\n",1)[1][:-3].strip()
            try:return json.dumps(clean(json.loads(candidate),depth+1),ensure_ascii=False)
            except (ValueError,TypeError):
                return re.sub(r'(?i)("(?:api_key|token|secret|authorization|cookie)"\s*:\s*")[^"]*',r'\1<redacted>',value[:8192])
        return value
    try:return clean(json.loads(body))
    except ValueError:return body[:8192]


def request_once(data: bytes, settings: dict, open_request):
    if settings.get("provider") != "qwen" or not settings.get("configured") or not settings.get("model"):
        raise ValueError("bbox_not_configured")
    request = urllib.request.Request(settings["base_url"],
        data=json.dumps(payload(data, settings["model"])).encode(),
        headers={"Authorization": "Bearer " + settings["api_key"], "Content-Type": "application/json"}, method="POST")
    with open_request(request, settings, timeout=TIMEOUT) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise ValueError("bbox_response_too_large")
    # Retain the bounded body even when JSON parsing fails; caller sanitizes it.
    return body.decode("utf-8", errors="replace")


def parse(body: str):
    try:
        envelope = json.loads(body)
        if envelope["choices"][0].get("finish_reason") == "length":
            raise ValueError("bbox_output_truncated")
        text = envelope["choices"][0]["message"]["content"].strip()
        if text.startswith("```json\n") or text.startswith("```\n"):
            text = text.split("\n", 1)[1]
            if not text.endswith("```"):
                raise ValueError("bbox_invalid_json")
            text = text[:-3].strip()
        result = json.loads(text)
    except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError("bbox_invalid_json") from exc
    if not isinstance(result, dict) or type(result.get("isMultiLabel")) is not bool:
        raise ValueError("bbox_invalid_schema")
    if type(result.get("labelCount")) is not int or result["labelCount"] < 0:
        raise ValueError("bbox_invalid_schema")
    if result["labelCount"] == 0:
        raise ValueError("no_label")
    if not result["isMultiLabel"]:
        # The original prompt provides no bounds for single-label images.
        raise ValueError("bbox_missing_rectangle")
    if result["labelCount"] < 2:
        raise ValueError("bbox_invalid_schema")
    rect = result.get("cropRect")
    if not isinstance(rect, dict):
        raise ValueError("bbox_missing_rectangle")
    values = [rect.get(k) for k in ("x", "y", "w", "h")]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("bbox_invalid_coordinates")
    x, y, w, h = values
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1 or y+h > 1:
        raise ValueError("bbox_invalid_coordinates")
    return result, values


def crop_rectangle(original: bytes, rect):
    # C# casts x/y/width/height independently to integers. No clamp or expansion.
    with Image.open(io.BytesIO(original)) as image:
        w, h = image.size
        x, y, cw, ch = [int(v * size) for v, size in zip(rect, (w, h, w, h))]
        if min(cw, ch) < 2 or x < 0 or y < 0 or x+cw > w or y+ch > h:
            raise ValueError("bbox_empty_or_invalid_crop")
        out = io.BytesIO()
        image.crop((x, y, x+cw, y+ch)).save(out, "PNG")
    # Polygon vertices are source pixel centers, compatible with geometry.crop.
    points = [[px/(w-1), py/(h-1)] for px, py in
              ((x,y),(x+cw-1,y),(x+cw-1,y+ch-1),(x,y+ch-1))]
    return out.getvalue(), points, {"bbox": [x,y,cw,ch], "width": cw, "height": ch,
        "comparison_size_ok": min(cw,ch) >= 100, "colleague_size_gate_ok": min(cw,ch) > 50,
        "margin_pixels": 0, "boundary_verified": False}


def crop_revision(original: bytes, points):
    return geometry.crop(original, points, margin_pixels=0)
