"""Dependency-light worker protocol checks; no model weights/GPU required."""
import base64
import hashlib
import importlib.util
import io
from pathlib import Path
from PIL import Image

path = Path(__file__).resolve().parents[1]/"local_inspection_service/workers/vantaline_sam3_worker/handler.py"
spec = importlib.util.spec_from_file_location("sam3_worker", path)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
stream = io.BytesIO()
Image.new("RGB", (200,200), "white").save(stream, format="PNG")
data = stream.getvalue()
value = {"protocol": worker.PROTOCOL, "request_id":"test-label-001", "source_sha256":"a"*64,
         "image_sha256":hashlib.sha256(data).hexdigest(), "image_b64":base64.b64encode(data).decode(),
         "box":[20,20,180,180]}
assert worker.validate_input(value)[0].size == (200,200)
assert worker.point_prompt(value, value["box"]) == {}
assert worker.point_prompt({"positive_points":[[90,80]]}, value["box"])["input_labels"] == [[[1]]]
for points in [[[0,0]], [[float("nan"),50]], [[True,50]], [[20,50]], [[50]], "bad"]:
    try:
        worker.point_prompt({"positive_points": points}, value["box"])
    except ValueError:
        pass
    else:
        raise AssertionError("invalid point accepted")
response = worker.handler({"input":{**value,"positive_points":[[0,0]]}})
assert response["ok"] is False and response["error"] == "invalid_points"
assert "image_b64" not in response
print("SAM3 worker protocol smoke passed")
