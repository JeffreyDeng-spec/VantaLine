"""Image decoding, model copies and annotation with explicit resize policy."""
import io
import base64
from typing import Any
import cv2
import numpy as np
from PIL import Image, ImageOps
from fastapi import HTTPException


def prepare_image(contents: bytes, *, max_bytes: int = 10 * 1024 * 1024) -> tuple[bytes, str, str, str]:
    """Trust decoded image content, then normalize uncommon readable formats."""
    if not contents or len(contents) > max_bytes:
        raise HTTPException(status_code=400, detail="图片必须存在且不超过 10MB")
    try:
        with Image.open(io.BytesIO(contents)) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            if width * height > 20_000_000 or min(width, height) < 100:
                raise HTTPException(status_code=400, detail="实物图片像素尺寸不符合要求")
            image.seek(0)
            image.load()
            if image_format in {"PNG", "JPEG", "JPG", "WEBP"}:
                decoded = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
                if decoded is not None:
                    formats = {"PNG": ("image/png", ".png"), "JPEG": ("image/jpeg", ".jpg"), "JPG": ("image/jpeg", ".jpg"), "WEBP": ("image/webp", ".webp")}
                    mime, suffix = formats[image_format]
                    return contents, mime, suffix, image_format
            normalized = ImageOps.exif_transpose(image)
            if normalized.mode in {"RGBA", "LA"} or "transparency" in normalized.info:
                rgba = normalized.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = normalized.convert("RGB")
            output = io.BytesIO()
            rgb.save(output, format="JPEG", quality=95, optimize=True)
            prepared = output.getvalue()
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=400, detail="图片格式损坏或当前服务器无法解码") from exc
    decoded = cv2.imdecode(np.frombuffer(prepared, np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise HTTPException(status_code=400, detail="图片无法完整解码")
    return prepared, "image/jpeg", ".jpg", image_format or "UNKNOWN"


def prepare_provider_image(contents: bytes, mime_type: str, *, max_side: int, jpeg_quality: int) -> tuple[bytes, str, str]:
    """Bound only the model copy while preserving full-resolution audit evidence."""
    try:
        with Image.open(io.BytesIO(contents)) as image:
            image_format = str(image.format or "").upper() or "UNKNOWN"
            width, height = image.size
            if max(width, height) <= max_side:
                return contents, mime_type, image_format
            working = ImageOps.exif_transpose(image)
            working.thumbnail(
                (max_side, max_side),
                Image.Resampling.LANCZOS,
            )
            if working.mode in {"RGBA", "LA"} or "transparency" in working.info:
                rgba = working.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = working.convert("RGB")
            output = io.BytesIO()
            rgb.save(
                output,
                format="JPEG",
                quality=jpeg_quality,
                optimize=True,
            )
            prepared = output.getvalue()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="图片无法为模型生成兼容副本") from exc
    return prepared, "image/jpeg", "JPEG"


def annotate(contents: bytes, differences: list[dict[str, Any]]) -> bytes:
    image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("capture image decode failed")
    height, width = image.shape[:2]
    for index, difference in enumerate(differences, start=1):
        box = difference.get("box") or []
        if len(box) != 4:
            continue
        x1, y1, x2, y2 = (int(float(box[0]) * width), int(float(box[1]) * height), int(float(box[2]) * width), int(float(box[3]) * height))
        cv2.rectangle(image, (x1, y1), (x2, y2), (20, 20, 235), max(3, width // 500))
        cv2.putText(image, str(index), (x1, max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 235), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise ValueError("annotation encode failed")
    return encoded.tobytes()


def data_url(contents: bytes, mime: str = "") -> str:
    if not mime:
        mime = "image/png" if contents.startswith(b"\x89PNG") else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(contents).decode('ascii')}"


def similarity(left: bytes, right: bytes) -> float:
    a = cv2.imdecode(np.frombuffer(left, np.uint8), cv2.IMREAD_GRAYSCALE)
    b = cv2.imdecode(np.frombuffer(right, np.uint8), cv2.IMREAD_GRAYSCALE)
    if a is None or b is None:
        return 0.0
    a = cv2.resize(a, (160, 220), interpolation=cv2.INTER_AREA)
    b = cv2.resize(b, (160, 220), interpolation=cv2.INTER_AREA)
    direct = 1.0 - float(np.mean(cv2.absdiff(a, b))) / 255.0
    hist_a = cv2.calcHist([a], [0], None, [32], [0, 256])
    hist_b = cv2.calcHist([b], [0], None, [32], [0, 256])
    hist = max(0.0, float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)))
    return max(0.0, min(1.0, direct * 0.65 + hist * 0.35))
