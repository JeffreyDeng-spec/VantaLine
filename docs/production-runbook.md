# Production runbook

Analysis projection/publication changes use the ordinary complete-release restart.
Verify normal/admin analysis visibility and preserved history; no recomputation,
backfill, worker mode change or database cleanup is needed. Whole-release rollback
retains saved records, including records whose later capture step failed.

Analysis record extraction requires no data migration, maintenance window or
service topology change beyond the ordinary Web restart. Roll back the entire
previous release if history access regresses. Retain records, model references
and call evidence; do not rebuild historical JSON or replay provider calls.

Cost-domain extraction ships in the ordinary immutable release, with no data
migration or worker change. Revert the complete release on regression; preserve
stored call evidence and existing metadata. There is no cost-ledger repair or
recalculation step during deployment.

Backend extraction contract checks run against a temporary test runtime before
merge. They do not start production workers or inspect customer data. Contract-only
releases use the existing complete-release deployment and rollback procedure.

**Status: Authoritative**

Runtime connection/identity extraction uses ordinary complete-release restart and
rollback. It adds no service, flag, migration or maintenance gate. Existing worker
cleanup remains on its own thread; do not close an active worker's connection from
an HTTP shutdown callback. Connection factory tests cover redacted failures before
this independently deployable step is merged.

For model dependency extraction, use normal whole-release deployment and verify
health/version before observing existing tasks. Missing resolver/recorder errors
must be corrected in composition, never bypassed by replaying a paid task. Rollback
restores the previous complete release while keeping all saved model references,
secret versions and call evidence. This step adds no migration or worker topology.

For the local OCR reread trial, verify the immutable release and health first,
then add only the authorized owner to `VANTALINE_QWEN_REREAD_ACCOUNTS` in restricted
runtime configuration and restart via the normal service procedure. Keep automatic
MATCH disabled. Verify the submitted task records its reread version and that all
calls share the 120s deadline. Roll back by disabling new reread submissions and
restoring the previous complete immutable release; retain evidence and unknown
call claims. Never clear claims to force a paid retry.

For direct DOC extraction, the release workflow builds the locked POI helper with
Java 17 and packages its jars, licenses and checksum manifest in the immutable
release. Configure `VANTALINE_DOC_IMAGE_BUNDLE` to
`/opt/vantaline/current/local_inspection_service/workers/doc_image_extractor/bundle`
and verify the real fixtures under the service account with a patched Java 11+
runtime. Do not install LibreOffice or fonts. Imports make no runtime downloads.
Unset the variable to disable DOC imports without affecting DOCX/PDF or old media.
Full code rollout still follows PR, required CI and immutable release acceptance.

Document-review UI rollout requires frontend build, review-handler tests and
target PostgreSQL regression before release. It adds no tables and does not
enable DOC conversion. Verify all three asset states remain
visible, excluded images can be restored and pending assets block draft activation.
Rollback is a whole immutable release, never deletion of images or feedback.

Enable `VANTALINE_DOCUMENT_CLASSIFICATION_ACCOUNTS` only for approved accounts
with configured Qwen vision and external-media authorization. Verify real imported
images obtain classification results (not just extraction), unknown calls are not
replayed, and deleted orders disappear without removing historical media. Clearing
the allowlist prevents new jobs; whole-release rollback preserves all evidence.

Before merging a PLC automatic-capture release, confirm the frontend `test:plc-capture` step, backend PLC smoke, release contract, and documentation contract all passed.

Before enabling text inspection v2, confirm account isolation, the customer DOCX fixture, migration safety, frontend production build, the standard-library revision/add/soft-delete contract, and provider fail-closed, external-only and enabled-mode tests. A confirmed standard revision is audit evidence and must never be edited or physically deleted in place; every user-facing add, remove or restore on a confirmed logical standard must append a numbered snapshot under the standard transaction lock. Verify that new comparisons bind to that exact revision and reference hash, old comparisons and media remain readable after later edits, and cross-account standard mutation, asset and media requests fail closed. Keep automatic VLM `MATCH` review-only until customer commissioning, external-media consent and account cost controls are recorded. Do not run old-data cleanup from the immutable release installer.

Before merging camera-selector or upload-surface changes, run the browser-media input smoke plus frontend typecheck and production build. Confirm every file chooser also accepts a validated drop, single/multiple and disabled semantics are preserved, and dragged media cannot acquire camera or PLC provenance. For the text-comparison selector, additionally verify stale camera requests are discarded, removed devices fall back only while that surface is active, and permission denial leaves capture disabled with image upload still available.

## A + Evolving label rollout and rollback

Deploy label inspection only through a reviewed PR, required CI and one immutable
frontend/backend release. Provision the authorized Ark experiment key in a
restricted runtime file readable by the service account, then configure the two
`VANTALINE_LABEL_INSPECTION_*` variables independently of existing providers.
Never print the secret or copy it into a release. The normal installer applies the
additive label object table migration before service cutover.

After deployment verify `/api/version` consistency and perform one real Word
import, detection, saved-result read and continuation. Verify that the text entry
has no main sidebar and that manuals and Beta still open. Test control images must
be clearly named and must not be treated as production accuracy measurements.

Rollback uses the previous complete immutable release, disabling new label
submissions/claims first. Keep all new tables, immutable revisions, calls and media;
do not reverse the additive migration or replay unknown calls. Submitted runs that
lost their worker remain unknown until deadline expiration when the new service
resumes, and require a user-created linked retry.


## Read-only diagnosis first

After a history release, verify the title-bar entry, current-owner pagination,
one saved result and its private thumbnail/reference/source access. Compare it
with the same saved record, without submitting a paid comparison. Cross-owner
requests must return 404. No new schema, account flag, model setting or retention
job is required. Whole-release rollback preserves all historical evidence and
ignores the additive display metadata.

For the public/workspace navigation release, verify `/` stays the introduction,
`/docs` is the public user guide, and `/workspace` plus a functional deep link
refresh correctly. An unauthenticated deep link must go directly to login and
return to the same target; an authenticated `/` must remain public. Website/docs
links live inside About, open another tab, and are not duplicated in the sidebar.
Admin Swagger is now `/api/docs`,
not `/docs`; verify ordinary/anonymous users cannot read API documentation.
Check legacy task links, account switching, version consistency and that viewing
help does not replace the active workbench. No DNS, cookies, provider keys,
database migration or device authorization migration is part of this rollout.
Roll back the whole release on regression; original root-level functional
addresses remain compatible, while new workspace bookmarks require this release.

For single-label extraction, enable only the intended account through `VANTALINE_LABEL_EXTRACTION_ACCOUNTS` after image-generation configuration and synthetic mask acceptance. Verify manual correction, explicit confirmation, stale-version rejection and authenticated source/mask/crop access. Observe `label_extraction` events for status, elapsed time and failure code; inspect bounded record diagnostics for provider usage when available. A stuck attempt is uncertain, not a reason to replay a paid model call. Draft media expiration is limited to unconfirmed/unreferenced roots older than seven days and retains metadata tombstones; all confirmed evidence remains available. Roll back the complete release if regression occurs; the additive table remains readable.

1. Check the GitHub workflow and immutable Release for the expected commit.
2. Query `/api/version`; verify release, full Git SHA, build time, backend/frontend protocol, and `consistent=true`.
3. Check the service is active and inspect recent error-level logs.
4. Check current release symlink, disk space, database connectivity, and PLC active/in-flight leases before considering deployment action.

Do not place real hosts, usernames, keys, or DSNs in commands committed to this repository. Obtain deployment access from the approved secret store.

## Deployment behavior

Qwen OCR evidence is a default-off account trial. Deploy its additive migration
with the immutable release, then verify required fake-provider/real PostgreSQL
checks and explicitly authorized real-image evidence before changing the separate
`VANTALINE_QWEN_OCR_ACCOUNTS` allowlist. Key authorization alone does not enable
this pipeline. This release has no automatic MATCH commissioning path. Keep the
allowlist empty if private-image approval or validation is missing. Rollback clears
the allowlist and restores a whole release; retain cache claims and all evidence,
including unknown calls, rather than clearing them to force a paid retry.

Standard preparation remains off until real document-image acceptance, PostgreSQL
transaction tests and browser review pass. Provision only the existing local OCR
artifacts through `VANTALINE_STANDARD_OCR_MODEL_DIR`; no new GPU or model subscription
is part of this change. Then allowlist the trial account, verify activation progress,
clean image/template version binding and actual-only OCR. Keep its independent MATCH
allowlist empty until independent negative samples pass. Restarted/unknown paid
attempts stay reviewable; never resend them from a recovery script. Roll back the
entire immutable release and retain all source/derived media and revision JSONB.

Include v4 missing-region recovery in commissioning: inspect actual supplemental
OCR pixels, false positives, region truncation, dimensions removed and internal
MODEL/parameters retained. Successful local recovery does not certify the remaining
template text. Keep the draft release blocked if automatic acceptance is incorrect.
Do not replay an interrupted `supplementing` attempt or its VLM classification.

Keep `VANTALINE_LABEL_BBOX_ACCOUNTS` empty until real-image rectangle localization is accepted. The method reuses resolved Qwen comparison credentials, not the generation service. Review the saved model input and crop before enabling any account; failure or timeout never falls back to a whole-sheet comparison. Roll back the complete release, retaining prior extraction evidence, if integration regressions occur.

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

## Agent platform development boundary

Keep `VANTALINE_WEBMCP_ACCOUNTS` empty in production while the outstanding gates in
[Agent platform implementation status](agent-platform.md) remain. Native browser
fixture tests are not a full industrial rollout approval. The additive operation
migration is compatible with older releases; whole-release rollback must retain
policy, attempt, reservation and audit rows for reconciliation. The browser tool
switch alone cannot revoke an Agent using an authenticated full-page session.

The frontend CI gate now includes `test:agent`. A passing unit gate does not enable
the experimental Agent account allowlist or establish native-browser, physical
PLC or full-platform acceptance. Native lifecycle evidence and remaining rollout
constraints are recorded in `docs/agent-platform.md`; the whole-release rollback
procedure remains unchanged.

## Codex text comparison beta

Keep its account allowlist empty until the dedicated server login, native Codex
binary, Linux namespace test, shared private-media permissions and a real
one-shot report have passed. Follow [the commissioning sequence](codex-text-compare.md).
The service template is not an automatic host installer. Disable new submissions
and drain active work before moving releases; stop its entire process group when
interruption is necessary. Roll back the complete release, retaining all new
tables, reports, media and unknown outcomes.

For label-v2 upgrades, drain admission and stop the independent Codex worker
before switching the whole immutable release, then restart it against `current`.
The release must contain the task skill, CLI helpers and matching report contract.
Verify an actual fresh session records the skill version/hash, writes elements
before checks and produces visible issue annotations. Keep originals, selected
reference bounds and all v1/v2 history on rollback. An older worker must not claim
queued label-v2 cards; cancel/drain queued v2 work before rolling back. The decoder
uses the release Python/OpenCV locally; unsupported/unreadable codes remain uncertain.

For label-batch-v3, disable admission and drain the queue before the immutable
release switch, then restart the independent worker against current. Commission a
real batch with multiple actuals and record a single session ID, early matching,
per-label CLI findings, safe uncertain matching and partial-report behavior. Preserve
all draft/terminal v3 records and media on rollback; cancel/drain queued v3 tasks
before starting an older worker. The 600-second limit applies to the entire batch.

## Label quality rollout

Before enabling this release, run private real-photo calibration and inspect the
automatic candidate overlays. Require two low-quality captures rejected and four
clearer files retained, plus 0/1/2-call and unchanged-input contracts. Sample counts
are calibration evidence only. Benchmark on the service host without provider
calls; each local check must have P95 <500ms. No new credential/config is required.

Drain active label work before switching releases. New submissions freeze the
release policy; older queued runs without a compatible snapshot stop and require
manual retry. After immutable release/version acceptance, verify clear/blurred
submissions, mixed-label selection and owned history in the browser. Restore the
previous complete release to roll back; preserve all task, quality and call data.
The previous release does not enforce this quality gate.

## Model profile rollout

Before merge, run the registry PostgreSQL regression, settings browser acceptance,
frontend typecheck/build and existing text/PLC gates. Apply the additive registry
migration via the immutable installer. On first authenticated admin settings read,
verify migrated purpose bindings and masked keys without printing credentials.
Check the training assistant connection status and recent recorded calls separately:
a configured code path is not proof of recent use. Unknown prices display 未计价.
Verify `/api/version`, admin-only settings access and preserved account feature gates.
Do not send customer images merely to validate settings or credential connectivity.
Rollback restores the previous complete immutable release and legacy settings;
retain the new table and all secret versions. Do not reverse migrations or replay
uncertain paid calls. New-library edits are not written back into legacy settings.


## Unified PDF inspection

For unified PDF releases, verify the actual proxy multipart allowance (201m), PDF limit 200 MiB, importer progress after refresh, complete standard count and a clearly named synthetic comparison. Confirm old manual URLs/history remain readable and Word/image/Beta flows remain available. Roll back the entire previous immutable release and stop new PDF submissions; preserve PDF tasks, assets, leases, runs and call records. Never infer real-photo accuracy from rendered-page tests.
