#!/usr/bin/env python3
"""Optional LocateAnything-3B runtime for the VantaLine workbench.

This script is intentionally not imported by local_inspection_service/server.py.
Start it manually only in a Python 3.10 environment prepared for the model:

  pip install opencv-python-headless==4.11.0.86 transformers==4.57.1 numpy==1.25.0 Pillow==11.1.0 peft torchvision decord==0.6.0 lmdb==1.7.5 accelerate safetensors fastapi uvicorn python-multipart

Install PyTorch separately for the machine CUDA version before loading the model.
The NVIDIA LocateAnything-3B model is licensed for non-commercial research use.
"""

from __future__ import annotations

import io
import os
import threading
import time
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image


MODEL_ID = os.environ.get("LOCATEANYTHING_MODEL_ID", "nvidia/LocateAnything-3B")
DEVICE = os.environ.get("LOCATEANYTHING_DEVICE", "cuda")
DTYPE = os.environ.get("LOCATEANYTHING_DTYPE", "bfloat16")
WARMUP_ON_START = os.environ.get("LOCATEANYTHING_WARMUP_ON_START", "").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(title="VantaLine LocateAnything Runtime", version="0.1")
_worker_lock = threading.Lock()
_worker: "LocateAnythingWorker | None" = None


class LocateAnythingWorker:
    def __init__(self, model_id: str, device: str, dtype_name: str) -> None:
        import torch
        from transformers import AutoModel, AutoProcessor, AutoTokenizer

        dtype = getattr(torch, dtype_name, torch.bfloat16)
        quantization = os.environ.get("LOCATEANYTHING_QUANTIZATION", "").strip().lower()
        self.device = device
        self.dtype = dtype
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        self.processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        model_kwargs: dict[str, Any] = {
            "torch_dtype": dtype,
            "trust_remote_code": True,
            "low_cpu_mem_usage": True,
        }
        if quantization in {"4bit", "8bit"} and device.startswith("cuda"):
            from transformers import BitsAndBytesConfig

            if quantization == "4bit":
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=dtype,
                    bnb_4bit_quant_type=os.environ.get("LOCATEANYTHING_BNB_4BIT_TYPE", "nf4"),
                    bnb_4bit_use_double_quant=os.environ.get("LOCATEANYTHING_BNB_DOUBLE_QUANT", "1") != "0",
                )
            else:
                model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
            model_kwargs["device_map"] = {"": 0}
            self.model = AutoModel.from_pretrained(model_id, **model_kwargs).eval()
        else:
            self.model = AutoModel.from_pretrained(model_id, **model_kwargs).to(device).eval()

    def predict(self, image: Image.Image, prompt: str, generation_mode: str, max_new_tokens: int) -> dict[str, Any]:
        import torch

        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
        text = self.processor.py_apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images, videos = self.processor.process_vision_info(messages)
        inputs = self.processor(text=[text], images=images, videos=videos, return_tensors="pt").to(self.device)
        with torch.no_grad():
            response = self.model.generate(
                pixel_values=inputs["pixel_values"].to(self.dtype),
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                image_grid_hws=inputs.get("image_grid_hws"),
                tokenizer=self.tokenizer,
                max_new_tokens=max_new_tokens,
                use_cache=True,
                generation_mode=generation_mode,
                temperature=0.7,
                do_sample=True,
                top_p=0.9,
                repetition_penalty=1.1,
                verbose=False,
            )
        answer = response[0] if isinstance(response, tuple) else response
        result: dict[str, Any] = {"answer": answer}
        if isinstance(response, tuple) and len(response) >= 3:
            result["stats"] = response[2]
        return result


def worker() -> LocateAnythingWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = LocateAnythingWorker(MODEL_ID, DEVICE, DTYPE)
        return _worker


def warmup_worker() -> None:
    try:
        worker()
    except Exception as exc:
        print(f"LocateAnything warmup failed: {exc}", flush=True)


@app.on_event("startup")
def startup_warmup() -> None:
    if WARMUP_ON_START:
        threading.Thread(target=warmup_worker, name="locateanything-warmup", daemon=True).start()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": MODEL_ID, "loaded": _worker is not None}


@app.get("/help")
def help_text() -> dict[str, Any]:
    return {
        "endpoint": "POST /locate with multipart image, prompt, generation_mode, max_new_tokens",
        "generation_modes": ["fast", "hybrid", "slow"],
        "default_generation_mode": "hybrid",
        "notes": [
            "Use fast for RTX 4060 latency experiments; expect low throughput.",
            "Use hybrid for quality checks and slow for offline stability.",
            "This runtime downloads/loads model weights only when /locate is first called.",
        ],
    }


@app.post("/locate")
async def locate(
    image: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
    prompt: str = Form(...),
    generation_mode: str = Form("hybrid"),
    max_new_tokens: int = Form(2048),
) -> dict[str, Any]:
    upload = image or file
    if upload is None:
        raise HTTPException(status_code=400, detail="image file is required")
    mode = generation_mode.strip().lower()
    if mode not in {"fast", "hybrid", "slow"}:
        raise HTTPException(status_code=400, detail="generation_mode must be fast, hybrid, or slow")
    tokens = max(64, min(8192, int(max_new_tokens)))
    payload = await upload.read()
    if not payload:
        raise HTTPException(status_code=400, detail="image file is empty")
    try:
        pil_image = Image.open(io.BytesIO(payload)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"could not decode image: {exc}") from exc
    start = time.monotonic()
    result = worker().predict(pil_image, prompt.strip(), mode, tokens)
    result.update(
        {
            "ok": True,
            "model": MODEL_ID,
            "generation_mode": mode,
            "max_new_tokens": tokens,
            "latency_ms": int((time.monotonic() - start) * 1000),
        }
    )
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("LOCATEANYTHING_HOST", "127.0.0.1"), port=int(os.environ.get("LOCATEANYTHING_PORT", "8000")))
