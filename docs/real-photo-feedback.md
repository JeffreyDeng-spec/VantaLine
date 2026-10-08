# Real-photo feedback

**Status: Authoritative**

## Foundation batch

The foundation introduces account-opt-in `real_photo_vlm` storage, API, source capture and strict localization contracts. Empty `VANTALINE_REAL_PHOTO_ACCOUNTS` preserves current behavior. Enabling requires an explicit fixed Doubao bbox binding and first disables legacy feedback admission; active legacy labeling must settle first. Initial AI-generated pretraining remains unchanged. Historical artifacts remain available through the old API and the owner-only history index; their frames are drafts and require explicit original-hash, first-frame geometry and source-group confirmation before reuse. Failed historical review records are not combined into labels.

Original source bytes are frozen separately from annotated previews. Exact source hashes and explicit lineages deduplicate candidates; approximate similarity never deletes different photos. Camera source groups derive from the existing station/session, videos from source upload identity, and ordinary uploads from the upload request. Historical missing groups block split admission until an owner supplies one. UI/VLM/labels use decoded first-frame pixels, identity mapping and recorded EXIF orientation; no implicit orientation conversion is applied.

`bbox_annotation` is independently bound to `doubao-seed-2-1-pro-260915`. The blind request includes every task category/reference and the real original, never previous detections, masks or review results. It uses normalized 0–1000 xyxy, visible tight boxes, temperature 0, thinking disabled, high detail and 4096 output tokens. Invalid/unknown/duplicate/out-of-bounds/truncated results fail as complete attempts and retain their bounded response and available usage. Each attempt is recorded before execution. A retry requires an explicit new version; there is no mask fallback.

The owner-only `/api/ai/tasks/{id}/real-photo` API exposes counters, private canonical image previews, source groups, history, restart and versioned relabel requests. Queued annotation/review jobs require the later independent worker. The foundation does not run automatic training. Masks requested through the new endpoint are queued supplemental artifacts and cannot change boxes, review keys or training admission.

## Subsequent batches — Proposal

1. Ship an independent Linux Codex review worker with its own service account, queue, private authentication, pinned native runtime and allowlisted task report tools. Actual image review must be commissioned on private business samples; process completion and fixture reports alone do not prove correctness.
2. Enable accepted-original dataset publication, held-out YOLO evaluation, continuous feedback and manual candidate selection only after worker and executor validation. Preserve complete task classes and mark missing real/test support as unavailable metrics. Do not auto-promote models or revive old synthetic feedback on rollback.

## Verification and rollback

Foundation tests require an explicit disposable PostgreSQL DSN for locking/idempotency/owner isolation. Check migrations, generated schema, original-capture regressions, PLC camera invariants, boundaries and the documentation contract. No private samples, runtime credentials, API keys, receipts or model artifacts belong in Git.

Rollback closes new admission, settles running attempts and restores one previous complete immutable release. Keep additive tables and all evidence. Unknown paid attempts are never automatically replayed. Runtime flags, production `/api/version` and immutable release evidence remain separate from fixture verification.
