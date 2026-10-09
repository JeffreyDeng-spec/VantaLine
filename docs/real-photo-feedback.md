# Real-photo feedback

**Status: Authoritative**

## Foundation batch

The foundation introduces account-opt-in `real_photo_vlm` storage, API, source capture and strict localization contracts. Empty `VANTALINE_REAL_PHOTO_ACCOUNTS` preserves current behavior. Enabling requires an explicit fixed Doubao bbox binding and first disables legacy feedback admission; active legacy labeling must settle first. Initial AI-generated pretraining remains unchanged. Historical artifacts remain available through the old API and the owner-only history index; their frames are drafts and require explicit original-hash, first-frame geometry and source-group confirmation before reuse. Failed historical review records are not combined into labels.

Original source bytes are frozen separately from annotated previews. Exact source hashes and explicit lineages deduplicate candidates; approximate similarity never deletes different photos. Camera source groups derive from the existing station/session, videos from source upload identity, and ordinary uploads from the upload request. Historical missing groups block split admission until an owner supplies one. UI/VLM/labels use decoded first-frame pixels, identity mapping and recorded EXIF orientation; no implicit orientation conversion is applied.

`bbox_annotation` is independently bound to `doubao-seed-2-1-pro-260915`. The blind request includes every task category/reference and the real original, never previous detections, masks or review results. It uses normalized 0–1000 xyxy, visible tight boxes, temperature 0, thinking disabled, high detail and 4096 output tokens. Invalid/unknown/duplicate/out-of-bounds/truncated results fail as complete attempts and retain their bounded response and available usage. Each attempt is recorded before execution. A retry requires an explicit new version; there is no mask fallback.

The owner-only `/api/ai/tasks/{id}/real-photo` API exposes counters, private canonical image previews, source groups, history, restart and versioned relabel requests. Queued annotation/review jobs require the later independent worker. The foundation does not run automatic training. Masks requested through the new endpoint are queued supplemental artifacts and cannot change boxes, review keys or training admission.

## Independent review worker

The second batch ships `training_review.worker`, its own systemd unit, immutable report socket and the versioned training review skill. It reuses the bubblewrap launcher with separate tool/skill mounts; existing label comparison defaults remain unchanged. The serial worker claims initialize/annotation/review/assessment jobs with owner allowlisting, 600-second CLI deadlines, heartbeat fencing and per-version reports. At most ten originals enter one review invocation. Failed CLI exit, cancellation, expired tokens, missing reports or partial rounds block admission. A failed VLM localization can only be excluded/uncertain, never converted to a negative. Parent-only late receipts preserve usage/evidence without reopening a job.

Initialization independently sets review trigger and approved target to 20–50. A full round freezes its membership, preserves already completed decisions, and produces a training proposal or next 1–50 increment. At least twenty approved distinct originals, a positive and three valid source groups are enforced independently of class coverage. Missing classes are recorded without an extra per-class minimum. New arrivals wait for the next round. This batch freezes proposed train jobs but does not execute YOLO.

Real CLI business acceptance is still an operations gate. The dedicated login, pinned native runtime, cache/scratch mounts, read-only original/reference access, report-only tools and model connection must be verified before activation. Fixture reports and clean CLI exit are not visual-quality evidence.

## Subsequent training batch — Proposal

2. Enable accepted-original dataset publication, held-out YOLO evaluation, continuous feedback and manual candidate selection only after worker and executor validation. Preserve complete task classes and mark missing real/test support as unavailable metrics. Do not auto-promote models or revive old synthetic feedback on rollback.

## Verification and rollback

Foundation tests require an explicit disposable PostgreSQL DSN for locking/idempotency/owner isolation. Check migrations, generated schema, original-capture regressions, PLC camera invariants, boundaries and the documentation contract. No private samples, runtime credentials, API keys, receipts or model artifacts belong in Git.

Rollback closes new admission, settles running attempts and restores one previous complete immutable release. Keep additive tables and all evidence. Unknown paid attempts are never automatically replayed. Runtime flags, production `/api/version` and immutable release evidence remain separate from fixture verification.
