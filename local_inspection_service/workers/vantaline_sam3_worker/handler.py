"""Single-instance SAM 3 worker. No customer data is persisted or logged."""
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import time

REVISION = "3c879f39826c281e95690f02c7821c4de09afae7"
WEIGHTS_SHA256 = "6d06f0a5f84e435071fe6603e61d0b4cc7b40e0d39d487cfd4d67d8cc11cc14a"
PROTOCOL = "sam3-single-label-v1"
MODEL_DIR = Path("/runpod-volume/sam3") / REVISION
_model = _processor = None


def validate_input(value):
    if not isinstance(value, dict) or value.get("protocol") != PROTOCOL:
        raise ValueError("invalid_protocol")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", value.get("request_id", "")):
        raise ValueError("invalid_request_id")
    if not re.fullmatch(r"[a-f0-9]{64}", value.get("source_sha256", "")):
        raise ValueError("invalid_source_hash")
    encoded = value.get("image_b64", "")
    if not isinstance(encoded, str) or len(encoded) > 16 * 1024 * 1024:
        raise ValueError("input_too_large")
    data = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(data).hexdigest() != value.get("image_sha256"):
        raise ValueError("image_hash_mismatch")
    from PIL import Image
    image = Image.open(io.BytesIO(data))
    if min(image.size) < 100 or max(image.size) > 2048 or image.width * image.height > 4_194_304:
        raise ValueError("invalid_image_size")
    image.load()
    image = image.convert("RGB")
    box = value.get("box")
    if not isinstance(box, list) or len(box) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in box):
        raise ValueError("invalid_box")
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 < image.width and 0 <= y0 < y1 < image.height):
        raise ValueError("box_out_of_bounds")
    return image, box


def load_model():
    global _model, _processor
    if _model is not None:
        return
    weights = MODEL_DIR / "model.safetensors"
    if not weights.is_file():
        raise RuntimeError("model_not_provisioned")
    digest = hashlib.sha256()
    with weights.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != WEIGHTS_SHA256:
        raise RuntimeError("model_checksum_mismatch")
    import torch
    from transformers import Sam3TrackerModel, Sam3TrackerProcessor
    if not torch.cuda.is_available():
        raise RuntimeError("gpu_unavailable")
    _processor = Sam3TrackerProcessor.from_pretrained(str(MODEL_DIR), local_files_only=True)
    _model = Sam3TrackerModel.from_pretrained(str(MODEL_DIR), local_files_only=True).to("cuda").eval()


def point_prompt(value, box):
    points = value.get("positive_points", [])
    if not isinstance(points, list) or len(points) > 8:
        raise ValueError("invalid_points")
    for point in points:
        if (not isinstance(point, list) or len(point) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
                or not (box[0] < point[0] < box[2] and box[1] < point[1] < box[3])):
            raise ValueError("invalid_points")
    return {"input_points": [[points]], "input_labels": [[[1]*len(points)]]} if points else {}


def handler(event):
    started = time.monotonic()
    try:
        value = event.get("input")
        image, box = validate_input(value)
        prompt = point_prompt(value, box)
        load_model()
        import torch
        import numpy as np
        from PIL import Image
        inputs = _processor(images=image, input_boxes=[[box]], return_tensors="pt", **prompt).to("cuda")
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            output = _model(**inputs, multimask_output=True)
        masks = _processor.post_process_masks(output.pred_masks.cpu(), inputs["original_sizes"])[0][0]
        scores = output.iou_scores.detach().float().cpu().reshape(-1).tolist()
        candidates = []
        for mask, score in zip(masks, scores):
            pixels = mask.numpy().astype(np.uint8) * 255
            stream = io.BytesIO()
            Image.fromarray(pixels, "L").save(stream, format="PNG")
            candidates.append({"mask_b64": base64.b64encode(stream.getvalue()).decode(), "score": float(score)})
        return {"ok": True, "protocol": PROTOCOL, "request_id": value["request_id"],
                "image_sha256": value["image_sha256"], "source_sha256": value["source_sha256"],
                "size": list(image.size), "revision": REVISION, "weights_sha256": WEIGHTS_SHA256,
                "candidates": candidates, "elapsed_ms": round((time.monotonic()-started)*1000)}
    except Exception as exc:
        # Upstream exception text can contain URLs or data; only bounded types escape.
        safe_codes = {"invalid_protocol", "invalid_request_id", "invalid_source_hash", "input_too_large",
                      "image_hash_mismatch", "invalid_image_size", "invalid_box", "box_out_of_bounds",
                      "model_not_provisioned", "model_checksum_mismatch", "gpu_unavailable", "invalid_points"}
        return {"ok": False, "error": str(exc) if str(exc) in safe_codes else type(exc).__name__,
                "elapsed_ms": round((time.monotonic()-started)*1000)}


if __name__ == "__main__":
    import runpod
    load_model()
    runpod.serverless.start({"handler": handler})
