# RunPod YOLO Training Worker

Platform transfer routes now use explicit transfer and upload-store services. Worker URLs, token
checks, expiry, ZIP streaming limits and result metadata remain unchanged; no worker rollout or
retry policy is introduced by this module move.

Web-side training ZIPs, tokenized export metadata and artifact import now use
`training.dataset_archives`, `training.runpod_exports` and `training.runpod_artifacts`.
The worker format stays unchanged: conversion skips only configured top-level directories,
uploaded artifacts select the first matching original member name in sorted order, and only
the selected weight bytes are written to the fixed import target. Existing checksum/path checks,
metadata ordering, cleanup and failure residue are retained. Source manifest v37 includes these producers.

Web-side RunPod payload construction, single submission, polling and strict output parsing
now use `training.runpod_submission`, `training.runpod_flow` and `training.runpod_outputs`.
The existing upload/export/import endpoints and worker package remain unchanged. Polling
still starts even for an already-completed submission response, uses the original pre-sleep
deadline comparison, and preserves the import/update/sync/warmup sequence. No automatic
retry or cancel is added. Source manifest v37 and historical task binding rules apply.

The Web-side sample plan, labels/YAML, annotation previews and dataset manifest now come
from explicit `training` modules. Sample contents, seed behavior and archive/RunPod input
contracts are unchanged. Source manifest v37 covers those relocated producers. No worker
service, submission retry, archive format or GPU execution policy changes in this extraction.

Training dispatch now enters `training.runner.TrainingRunner`; task construction lives in
`training.submission`. The existing RunPod request adapter, server-side RunPod payload builder
and worker package stay unchanged. Samples-only tasks still complete before executor dispatch.
The runner binds saved model references once before its separate task load and delegates to
the original RunPod flow; ordinary training threads gain no new identity propagation. New
source fingerprints use manifest v37, while historical task references remain untouched.

The Web-side executor settings now live in `training/executor_settings.py`, and the active
HTTP adapter/response summary in `training/runpod_client.py`. Dataset/archive input assembly,
worker payloads, polling, model artifacts and this worker package are unchanged. The adapter
captures URL and authorization candidates once per call, reads default timeout per attempt,
and only switches to the second existing auth format after HTTP 401/403. RequestException
outcomes are raised once with their exception type and original cause. No additional retry,
GPU worker or paid verification is introduced. The corresponding offline check is
`python scripts/smoke_training_executor_client.py`.

**Status: Authoritative**

This document defines the active remote GPU training worker package:

```text
local_inspection_service/workers/vantaline_yolo_train_worker/
```

The package name and RunPod template name should be
`vantaline-yolo-train-worker`.

## Scope

- RunPod is the production remote training target.
- No Qwen, PostgreSQL, auth, or detection-flow change.
- No RunPod key, dataset URL, artifact URL, or private model URL in source or
  public reports.
- Windows-worker training/gateway execution is retired. Do not reintroduce
  `VANTALINE_WORKER_*`, Windows gateway scripts, or Windows-worker training
  fallbacks for new production flow.

## Worker Contract

RunPod invokes `handler(event)` from `handler.py`. The worker reads
`event["input"]`.

Required real-job input:

```json
{
  "job_id": "train_20260706_sample",
  "train_mode": "yolo",
  "epochs": 10,
  "imgsz": 640,
  "base_model": "/models/vantaline-yolo-base.pt",
  "dataset_url": "<private presigned dataset zip URL>",
  "dataset_sha256": "<sha256>"
}
```

Optional:

```json
{
  "base_model_url": "<private presigned checkpoint URL>",
  "base_model_sha256": "<sha256>",
  "artifact_upload_url": "<private presigned output archive URL>",
  "artifact_upload_headers": {"Content-Type": "application/zip"},
  "return_artifact_b64": false,
  "device": "0",
  "timeout_seconds": 7200
}
```

For tiny offline smoke only, `dataset_archive_b64` may replace `dataset_url`.

Output includes:

- `status`
- `job_id`
- dataset archive `sha256`
- image and label counts
- training return code and log tail
- inference smoke status
- `best.pt` size and `sha256`
- artifact zip size and `sha256`
- optional artifact upload status, without echoing the upload URL

Failure output is structured as `ok=false`, `status=failed`, `error_type`, and
`error`.

## Cost Guardrails

Base-model guardrail:

- Real jobs must use a baked/mounted checkpoint path, optionally checked by
  `VANTALINE_RUNPOD_YOLO_BASE_MODEL_SHA256`, or a private `base_model_url` plus
  `base_model_sha256`.
- Bare model names that would trigger implicit Ultralytics runtime downloads are
  rejected outside explicit mock smoke.

RunPod endpoint/template:

- dedicated endpoint/template `vantaline-yolo-train-worker`
- `minWorkers=0`
- `maxWorkers=1`
- one active job per worker process
- finite execution timeout aligned to
  `VANTALINE_RUNPOD_YOLO_JOB_TIMEOUT_SECONDS`
- no always-on GPU training pod

Worker-side:

- `VANTALINE_RUNPOD_YOLO_MAX_CONCURRENCY=1`
- bounded `epochs`, `imgsz`, dataset byte size, and inline artifact size
- explicit subprocess timeout
- no persistent server loop outside RunPod serverless runtime

## Validation

Local no-key contract smoke:

```bash
python3 local_inspection_service/scripts/smoke_runpod_yolo_worker_contract.py
```

This smoke uses explicit mock training only after setting
`VANTALINE_RUNPOD_YOLO_ALLOW_MOCK=1`. It verifies archive ingest, checksum
failure, output contract, `best.pt` hash, inline artifact decode, and mocked
inference-smoke reporting.

Real acceptance still needs the manager-gated RunPod endpoint:

1. Upload a small private YOLO dataset zip.
2. Submit one job to the dedicated RunPod endpoint.
3. Confirm training reaches `completed`.
4. Confirm `best.pt` `sha256` and artifact download/upload.
5. Confirm inference smoke passes with the returned model.
