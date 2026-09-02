# Production runbook

**Status: Authoritative**

Before merging a PLC automatic-capture release, confirm the frontend `test:plc-capture` step, backend PLC smoke, release contract, and documentation contract all passed.

Before enabling text inspection v2, confirm account isolation, the customer DOCX fixture, migration safety, frontend production build, the standard-library revision/add/soft-delete contract, and provider fail-closed, external-only and enabled-mode tests. A confirmed standard revision is audit evidence and must never be edited or physically deleted in place; every user-facing add, remove or restore on a confirmed logical standard must append a numbered snapshot under the standard transaction lock. Verify that new comparisons bind to that exact revision and reference hash, old comparisons and media remain readable after later edits, and cross-account standard mutation, asset and media requests fail closed. Keep automatic VLM `MATCH` review-only until customer commissioning, external-media consent and account cost controls are recorded. Do not run old-data cleanup from the immutable release installer.

Before merging camera-selector or upload-surface changes, run the browser-media input smoke plus frontend typecheck and production build. Confirm every file chooser also accepts a validated drop, single/multiple and disabled semantics are preserved, and dragged media cannot acquire camera or PLC provenance. For the text-comparison selector, additionally verify stale camera requests are discarded, removed devices fall back only while that surface is active, and permission denial leaves capture disabled with image upload still available.

## Read-only diagnosis first

1. Check the GitHub workflow and immutable Release for the expected commit.
2. Query `/api/version`; verify release, full Git SHA, build time, backend/frontend protocol, and `consistent=true`.
3. Check the service is active and inspect recent error-level logs.
4. Check current release symlink, disk space, database connectivity, and PLC active/in-flight leases before considering deployment action.

Do not place real hosts, usernames, keys, or DSNs in commands committed to this repository. Obtain deployment access from the approved secret store.

## Deployment behavior

A successful push CI for `main` triggers `Release and deploy production` automatically. The workflow creates one immutable artifact, verifies checksums/version/protocol, uploads it through the restricted account, runs the installer, atomically switches `current`, restarts once, and performs acceptance. GitHub Release publication occurs only after acceptance.

The installer requires at least 2 GiB free under `/opt/vantaline`. If the disk gate fails, inspect usage first. Prefer deleting reproducible caches, package caches, expired logs, disabled package revisions, and failed incoming artifacts. Never remove shared customer data, databases, current/rollback releases, model outputs, or backups without a separate verified retention decision.

## Failure and rollback

- Build/contract failure: fix through a new PR; do not deploy a local artifact.
- Upload/SSH failure: verify GitHub Environment secret availability and pinned host identity; never paste keys into logs.
- Preflight failure: resolve the named gate and rerun the failed workflow job only when its immutable inputs remain unchanged.
- Acceptance failure: installer restores the previous `current` release and restarts; retain failed release/log evidence.
- Runtime regression after accepted deployment: deploy/revert a complete prior immutable release. Never mix frontend/backend files.

## PLC incident triage

Confirm browser support, HTTPS/Permissions Policy, workstation binding, active lease/epoch, configuration generation, profile verification, protocol consistency, and receipt evidence. ACK/NAK can be conclusive; timeout, malformed response, residual bytes, browser crash, or lost receipt is uncertain and must not be resent automatically. Ordinary website availability does not imply PLC effective enablement.
