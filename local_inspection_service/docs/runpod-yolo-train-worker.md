# RunPod YOLO Training Worker

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
