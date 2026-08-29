# vantaline-yolo-train-worker

**Status: Authoritative**

RunPod serverless worker for VantaLine YOLO training. This package is
intentionally independent from the production FastAPI app and the legacy Windows
worker gateway.

## Boundary

- Does not import or modify `local_inspection_service.server`.
- Does not change the production Qwen, PostgreSQL, task, or detection flow.
- Does not depend on Windows paths or a local Windows training process.
- Does not require a RunPod API key for local contract validation.
- Does not print or return dataset URLs, artifact upload URLs, API keys, or
  private model-weight URLs.

## RunPod Endpoint Settings

Use a dedicated serverless endpoint/template named
`vantaline-yolo-train-worker`.

Recommended cost guardrails:

- `minWorkers = 0`
- `maxWorkers = 1`
- one active job per worker process
- endpoint/job timeout aligned to `VANTALINE_RUNPOD_YOLO_JOB_TIMEOUT_SECONDS`
- no always-on GPU pods for training
- use presigned private object-storage URLs for dataset input and artifact
  upload; do not put URLs or credentials in public chat or frontend bundles

Worker env defaults:

```text
VANTALINE_RUNPOD_YOLO_WORK_ROOT=/workspace/vantaline-yolo-worker
VANTALINE_RUNPOD_YOLO_BASE_MODEL=/models/vantaline-yolo-base.pt
VANTALINE_RUNPOD_YOLO_MAX_CONCURRENCY=1
VANTALINE_RUNPOD_YOLO_JOB_TIMEOUT_SECONDS=7200
VANTALINE_RUNPOD_YOLO_MAX_DATASET_BYTES=5368709120
VANTALINE_RUNPOD_YOLO_RETURN_INLINE_MAX_BYTES=52428800
```

Set `VANTALINE_RUNPOD_YOLO_ALLOW_MOCK=1` only for offline contract smoke. Do not
set it on a production RunPod template.

## Build

From the repository root:

```bash
docker build \
  -t vantaline-yolo-train-worker:latest \
  -f local_inspection_service/workers/vantaline_yolo_train_worker/Dockerfile \
  local_inspection_service/workers/vantaline_yolo_train_worker
```

Real training must use a controlled base checkpoint. Bake or mount it into the
image, set `VANTALINE_RUNPOD_YOLO_BASE_MODEL=/models/vantaline-yolo-base.pt`,
and optionally set `VANTALINE_RUNPOD_YOLO_BASE_MODEL_SHA256`. If the checkpoint
is fetched from private storage, pass `base_model_url` plus
`base_model_sha256`; the worker downloads it into the private job directory and
never echoes the URL. Bare model names that would trigger implicit Ultralytics
runtime downloads are rejected outside explicit mock smoke.

## API Contract

RunPod calls `handler(event)`. The worker reads `event["input"]`.

Required fields:

```json
{
  "job_id": "train_20260706_sample",
  "train_mode": "yolo",
  "epochs": 10,
  "imgsz": 640,
  "base_model": "/models/vantaline-yolo-base.pt",
  "dataset_url": "https://private-storage.example/dataset.zip?...",
  "dataset_sha256": "<sha256>"
}
```

Accepted dataset inputs:

- `dataset_url` plus `dataset_sha256` for real RunPod use.
- `dataset_archive_b64` plus `dataset_sha256` for tiny contract tests.

Optional fields:

```json
{
  "base_model_url": "https://private-storage.example/base.pt?...",
  "base_model_sha256": "<sha256>",
  "artifact_upload_url": "https://private-storage.example/output.zip?...",
  "artifact_upload_headers": {"Content-Type": "application/zip"},
  "return_artifact_b64": false,
  "device": "0",
  "timeout_seconds": 7200
}
```

The dataset archive must contain an Ultralytics detection dataset:

```text
dataset.yaml
images/train/*
labels/train/*.txt
images/val/*
labels/val/*.txt
```

The worker rewrites `dataset.yaml` `path:` to the extracted container path
before training.

Successful response shape:

```json
{
  "ok": true,
  "status": "completed",
  "job_id": "train_20260706_sample",
  "worker": "vantaline-yolo-train-worker",
  "contract_version": 1,
  "dataset": {
    "archive_sha256": "<sha256>",
    "image_count": 3,
    "label_count": 3
  },
  "training": {
    "return_code": 0,
    "log_tail": "..."
  },
  "inference_smoke": {
    "ok": true,
    "status": "passed"
  },
  "artifacts": {
    "best_pt": {
      "filename": "best.pt",
      "size": 123456,
      "sha256": "<sha256>"
    },
    "run_archive": {
      "filename": "train_20260706_sample_artifacts.zip",
      "size": 234567,
      "sha256": "<sha256>"
    }
  }
}
```

Failure response shape:

```json
{
  "ok": false,
  "status": "failed",
  "job_id": "train_20260706_sample",
  "error_type": "WorkerError",
  "error": "dataset_archive checksum mismatch"
}
```

## Local Contract Smoke

This does not need RunPod credentials or a GPU. It verifies archive ingest,
checksum enforcement, output shape, artifact hashing, and failure reporting with
explicit mock training:

```bash
python3 local_inspection_service/scripts/smoke_runpod_yolo_worker_contract.py
```

Real acceptance still requires a gated RunPod endpoint and a private small
sample dataset:

1. Upload/generate a small YOLO dataset zip and checksum.
2. Submit one worker job with the dedicated RunPod endpoint.
3. Verify training reaches `completed`.
4. Verify `best.pt` SHA256 and artifact download/upload.
5. Run inference smoke using the returned model artifact.
