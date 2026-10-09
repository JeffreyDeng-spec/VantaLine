# RunPod YOLO Training Worker

Worker artifacts and Web code are deployed as one matching release with its bundled source manifest.

Platform transfer routes now use explicit transfer and upload-store services. Worker URLs, token
checks, expiry, ZIP streaming limits and result metadata remain unchanged; no worker rollout or
retry policy is introduced by this module move.

Web-side training ZIPs, tokenized export metadata and artifact import now use
`training.dataset_archives`, `training.runpod_exports` and `training.runpod_artifacts`.
The worker format stays unchanged: conversion skips only configured top-level directories,
uploaded artifacts select the first matching original member name in sorted order, and only
the selected weight bytes are written to the fixed import target. Existing checksum/path checks,
metadata ordering, cleanup and failure residue are retained. The bundled source manifest includes these producers.

Web-side RunPod payload construction, single submission, polling and strict output parsing
now use `training.runpod_submission`, `training.runpod_flow` and `training.runpod_outputs`.
The existing upload/export/import endpoints and worker package remain unchanged. Polling
still starts even for an already-completed submission response, uses the original pre-sleep
deadline comparison, and preserves the import/update/sync/warmup sequence. No automatic
retry or cancel is added. The bundled source manifest and historical task binding rules apply.

The Web-side sample plan, labels/YAML, annotation previews and dataset manifest now come
from explicit `training` modules. Sample contents, seed behavior and archive/RunPod input
contracts are unchanged. The bundled source manifest covers those relocated producers. No worker
service, submission retry, archive format or GPU execution policy changes in this extraction.

Training dispatch now enters `training.runner.TrainingRunner`; task construction lives in
`training.submission`. The existing RunPod request adapter, server-side RunPod payload builder
and worker package stay unchanged. Samples-only tasks still complete before executor dispatch.
The runner binds saved model references once before its separate task load and delegates to
the original RunPod flow; ordinary training threads gain no new identity propagation. New
source fingerprints use the bundled manifest, while historical task references remain untouched.

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


## COS compatibility path

In opt-in COS mode, the host builds ZIPs from indexed objects using one bounded
workspace, preserving native image bytes and skipping the existing training-only
excluded folders. The RunPod worker still receives the same token-protected ZIP
URL and SHA-256/size contract. It accepts native PNGs; only the old local path
performs the historical JPEG conversion. Dataset publication verifies COS before
saving task tokens/references. Uploads are bounded and verified before task success;
model imports retain original logical paths and immutable object history. No local
CPU/GPU fallback or new paid retry is introduced. Real remote acceptance remains
a separate budgeted gate after synthetic transfer tests.

The Web shared file checksum helper resolves mapped business files through a pinned verified COS cache before streaming their bytes. This also covers startup image-guide provenance, which shares the helper. Temporary training ZIPs outside the business root still use their local file stream; the RunPod payload and worker format are unchanged.

## Real-photo feedback foundation boundary

The feedback foundation adds source/annotation queues and strict original-image contracts but submits no RunPod training. Initial generated-image training and the worker request contract remain unchanged in this batch. Held-out real-photo evaluation and grouped dataset publication require the later training batch and compatible worker commissioning.
Local training submission now has a shared Python thread admission/drain owner with repository cleanup in that thread. Runpod transport, worker subprocess algorithms, snapshot binding and remote settlement stay unchanged. close(...) returning True certifies local thread/scope exit only and cannot be used as a remote-job cancellation or completion signal.

The shared training thread lifecycle now also owns the separately launched Codex background-generation thread. Runpod transport and training process/remote worker behavior are unchanged; Python-thread close results do not certify remote or child-process completion.

Periodic transfer progress threads now have explicit admission, stop signals and bounded join ownership. Closing reporting does not terminate or replay RunPod/network work. The transfer caller continues to own its upload/download and final task state; the application shutdown hook is not enabled in this slice.

Auto-optimization label, shadow and delayed-check Python threads now have explicit admission and drain ownership. Their algorithms, task guards and RunPod transport remain unchanged. Closing these owners waits for local thread/scope completion and is not a remote-job completion or cancellation signal.

Automatic-mask executor tasks release local repository selections on the executor thread. This change retains the existing executor ContextVar behavior, mask batch limits and remote training behavior; local cleanup is not a remote completion guarantee.

Automatic-mask child work now explicitly inherits the submitting task model snapshot for downstream training-vision resolution. It does not inherit unrelated request/cache/authorization contexts or change mask algorithms, concurrency, prompts or remote training behavior.

Dataset label and manifest writes now use an explicitly supplied file capability. Sample planning, rendering, archive construction, remote worker commands and partial-failure behavior are unchanged. This composition change neither starts a training worker nor alters its retry policy.

This offline training file replay follows generation candidate 2fdb9ee and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 214fe9c. Manifest v213 lists 526 sources, appending training/file_ports.py. Five services capture matching file capabilities while preserving validation, cache, write ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Training preview and annotation image I/O and dataset YAML writes use explicitly supplied storage capabilities. Dataset formats, labels, image quality, worker bundle preparation and remote training commands remain unchanged.

This offline training image replay follows file candidate 94c1eec and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 75d63a9. Manifest v214 lists 526 sources. Image adapters are captured and YAML selects its writer per call; arbitrary private rebinding is not preserved as an atomic hot swap. Algorithms, goldens and public signatures remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Dataset archives and strict file digests receive storage/runtime dependencies explicitly. Remote archives still stream original bytes; local worker conversion, skipped folders, JPEG quality, digest chunks and lease duration remain unchanged. No training process, remote transport or retry policy changes.

This offline training resource replay follows image candidate 9063ace and preserves current history, readiness, model/tail, shutdown, corrected boundary documentation and canonical LF guards. Production and test blobs match reviewed fbf5434. At this replay boundary manifest v215 selects 526 sources. Explicit resource and archive capabilities preserve file operation ordering, strict digest failures, partial publication and archive formats. Current source changes require actual-main rebind, independent review and full CI/release acceptance before publication.

TrainingRunner now receives explicit file/runtime capabilities. COS still requires RunPod, selected dataset existence is checked twice at the original call sites, and sample generation retains its work reservation. The worker package, paid submission and timeout policies are unchanged.

This offline training runner replay follows text media candidate da44932. Owned source/test blobs and ordered entry match reviewed 9b024f4. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v230 selects 528 sources. Running-state persistence, runtime mode, repeated existence reads, failure settlement and pinned model restoration remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Web RunPod exports/imports receive explicit runtime providers. Repeated selection remains at the original points, including the existing local fallback if a later selection returns None. Token expiry, worker archive format, selected best.pt ordering and partial publication remain unchanged.

This offline RunPod artifact replay follows training runner candidate b7b8760. Owned source/test blobs and ordered entry match reviewed 671f233. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v231 selects 528 sources. Repeated runtime selection, cleanup exception masking, publication ordering and local replacement remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

The Web RunPod flow, download validation and upload receiver now use explicitly supplied runtime providers. Token/hash/expiry order, limits, claims, polling and unknown-result no-retry semantics are unchanged; no additional worker process or paid validation is introduced.

This offline RunPod transport replay follows artifact candidate 97a9963. Owned source/test blobs and ordered entry match reviewed 12f1743. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v232 selects 528 sources. Durable claim ordering, ambiguous submit retention, streaming limits and partial upload publication remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

TrainingAccountState, TrainingExecution and TrainingTaskWorkflows compose the existing account/task storage, native submission/runner and token-protected transfer APIs. All use the same original local task runtime; background submission retains that runtime and its existing shutdown owner. RunPod payloads, token checks, worker algorithms and remote settlement are unchanged. Local artifact publication remains committed before task metadata update, so a later metadata failure keeps the published artifact without uploading again. A local close result still certifies only local thread/scope exit. The combined domain is one review/release batch, with synthetic verification and whole-bundle rollback.


For `real_photo_vlm`, the frozen dataset includes train/val/test, class IDs and test support counts; base SHA256 is mandatory. The compatible worker performs an unaugmented held-out test evaluation after training and returns `training.real_photo_test_metrics`; missing real support/test instances are unavailable, not zero. Mock training is rejected for this strategy. The Web executor rejects completed responses without those metrics. Rebuild/pin the worker image and verify a real GPU job before enabling the training account flag. Legacy pretraining payloads retain their behavior.
