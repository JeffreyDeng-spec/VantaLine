"""Bounded A-compatible image processing and fail-closed response validation."""

import base64
import io
import json
import math
import os
import time
from pathlib import Path
from PIL import Image, ImageOps
from ..codex_compare.contracts import digest

MODEL = "doubao-seed-evolving"
URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
PROMPTS = json.loads(Path(__file__).with_name("prompts.json").read_text())
PROMPT_HASH = digest(PROMPTS)
COORDINATE_SPACE = "image_input_normalized_v2"
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000


def legacy_settings():
    path = os.getenv("VANTALINE_LABEL_INSPECTION_KEY_FILE", "")
    try:
        key = Path(path).read_text().strip() if path else ""
    except OSError:
        key = ""
    enabled = os.getenv("VANTALINE_LABEL_INSPECTION_ENABLED", "").lower() == "true"
    return {"enabled": enabled and bool(key), "key": key}



def settings():
    from .. import server
    configured = server.model_profile_service.resolve("label")
    enabled = os.getenv("VANTALINE_LABEL_INSPECTION_ENABLED", "").lower() == "true"
    return {**configured, "enabled": enabled and configured.get("configured", False), "key": configured.get("api_key", "")}


def decode(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("图片必须小于 10 MiB")
    with Image.open(io.BytesIO(data)) as source:
        if source.width * source.height > MAX_PIXELS:
            raise ValueError("图片超过 1600 万像素")
        orientation = int(source.getexif().get(274, 1))
        image = ImageOps.exif_transpose(source).convert("RGB")
        return image, {
            "original_size": list(source.size),
            "orientation": orientation,
            "size": list(image.size),
        }


def jpeg(image):
    image = image.convert("RGB")
    ratio = min(1, 1600 / max(image.size))
    size = tuple(int(x * ratio) for x in image.size)
    if size != image.size:
        image = image.resize(size, Image.Resampling.BICUBIC)
    output = io.BytesIO()
    image.save(output, "JPEG", quality=90)
    return output.getvalue()


def image_content(data):
    return {
        "type": "image_url",
        "image_url": {
            "url": "data:image/jpeg;base64," + base64.b64encode(data).decode()
        },
    }


def payload(stage, images, cropped=False):
    if stage == "layout":
        content = [
            {"type": "text", "text": PROMPTS["layout"]},
            image_content(images[0]),
        ]
    else:
        content = [
            {"type": "text", "text": PROMPTS["cropped" if cropped else "original"]},
            {"type": "text", "text": "【图片A：标准标签】"},
            image_content(images[0]),
            {"type": "text", "text": "【图片B：实物标签】"},
            image_content(images[1]),
            {"type": "text", "text": "请开始检测，输出JSON结果。"},
        ]
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
        "max_tokens": 512 if stage == "layout" else 8192,
        "thinking": {"type": "disabled"},
    }


def parse(response):
    choices = response.get("choices") or []
    if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
        raise ValueError("模型响应不完整，无法判定")
    text = choices[0].get("message", {}).get("content")
    if not isinstance(text, str):
        raise ValueError("模型未返回有效内容")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON")
    value = json.loads(
        text[start : end + 1],
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("非法数值")),
    )
    if not isinstance(value, dict):
        raise ValueError("模型结果格式错误")
    return value


def crop_rect(layout, size):
    multi, count = layout.get("isMultiLabel"), layout.get("labelCount")
    if (
        type(multi) is not bool
        or type(count) is not int
        or count < 1
        or (multi and count < 2)
    ):
        raise ValueError("无法确认实物标签数量")
    if not multi:
        if count != 1:
            raise ValueError("标签数量与布局判断矛盾")
        return None
    r = layout.get("cropRect")
    if not isinstance(r, dict) or any(
        type(r.get(k)) not in (int, float) or not math.isfinite(r[k])
        for k in ("x", "y", "w", "h")
    ):
        raise ValueError("多标签裁剪范围无效")
    if (
        min(r["x"], r["y"]) < 0
        or max(r["x"], r["y"]) >= 1
        or min(r["w"], r["h"]) <= 0
        or max(r["w"], r["h"]) > 1
    ):
        raise ValueError("多标签裁剪范围越界")
    width, height = size
    x, y = max(0, min(int(r["x"] * width), width - 1)), max(
        0, min(int(r["y"] * height), height - 1)
    )
    w, h = min(int(r["w"] * width), width - x), min(int(r["h"] * height), height - y)
    if w <= 50 or h <= 50:
        raise ValueError("裁剪区域过小，无法可靠检测")
    return [x, y, w, h]


def valid_box(value):
    if not isinstance(value, dict):
        return None
    v = [value.get(k) for k in ("x", "y", "w", "h")]
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in v):
        return None
    x, y, w, h = v
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.001 or y + h > 1.001:
        return None
    return v


def result(value, crop, size):
    issues = value.get("issues")
    if (
        type(value.get("hasDiff")) is not bool
        or not isinstance(issues, list)
        or len(issues) > 500
    ):
        raise ValueError("模型差异清单缺失或无效")
    if value["hasDiff"] != bool(issues):
        raise ValueError("模型结论与问题清单矛盾")
    score = value.get("similarity")
    if (
        type(score) not in (int, float)
        or not math.isfinite(score)
        or not 0 <= score <= 100
    ):
        raise ValueError("模型评分无效")
    image_coordinates = value.get("coordinateSpace") == COORDINATE_SPACE
    parsed = []
    for i, issue in enumerate(issues):
        if (
            not isinstance(issue, dict)
            or not isinstance(issue.get("description"), str)
            or not issue["description"].strip()
        ):
            raise ValueError("差异条目不完整")
        item = {"id": i + 1}
        for k in (
            "type",
            "category",
            "description",
            "standardText",
            "actualText",
            "severity",
            "location",
            "confidence",
        ):
            v = issue.get(k, "")
            if not isinstance(v, str) or len(v) > 8000:
                raise ValueError("差异字段无效")
            item[k] = v
        item["reference_box"] = (
            valid_box(issue.get("bboxStandard"))
            if issue.get("onStandard") is True
            else None
        )
        box = (
            valid_box(issue.get("bboxCamera"))
            if issue.get("onCamera") is True
            else None
        )
        if box and crop:
            x, y, w, h = crop
            W, H = size
            box = [
                (x + box[0] * w) / W,
                (y + box[1] * h) / H,
                box[2] * w / W,
                box[3] * h / H,
            ]
        item["suggested_reference_box"] = item["reference_box"]
        item["suggested_actual_box"] = box
        if image_coordinates:
            item["actual_box"] = box
            missing = []
            if item["reference_box"] is None:
                missing.append("标准侧无可见或有效定位")
            if item["actual_box"] is None:
                missing.append("实物侧无可见或有效定位")
            item["position_note"] = "；".join(missing) or "模型定位框，已映射至显示原图；请结合图像复核"
        else:
            item["reference_box"] = None
            item["actual_box"] = None
            item["position_note"] = "旧版或未声明坐标规范，无法可靠映射；重新检测可生成新版标注"
        parsed.append(item)
    consistent = value.get("consistentItems", [])
    if (
        not isinstance(consistent, list)
        or len(consistent) > 500
        or any(not isinstance(x, str) or len(x) > 8000 for x in consistent)
    ):
        raise ValueError("一致项格式无效")
    return {
        "decision": "DIFFERENCES" if parsed else "MATCH",
        "issues": parsed,
        "coordinate_space": COORDINATE_SPACE if image_coordinates else "unknown",
        "similarity": score,
        "consistent_items": consistent,
    }


def invoke(body, key):
    import requests

    started = time.monotonic()
    # No redirect or retry can forward a credential or duplicate paid work.
    with requests.post(
        URL,
        json=body,
        headers={"Authorization": "Bearer " + key},
        timeout=(10, 180),
        allow_redirects=False,
        stream=True,
    ) as response:
        data = bytearray()
        for block in response.iter_content(16384):
            data.extend(block)
            if len(data) > 1024 * 1024 or time.monotonic() - started > 180:
                raise ValueError("模型响应超时或超过容量限制")
        text = data.decode("utf-8", errors="replace").replace(key, "[REDACTED]")
        return response.status_code, text
