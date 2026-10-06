The Codex comparison list/event repository read change needs no migration, setting or worker switch. It preserves the existing Web restart and full-package rollback; keep task/event evidence and prior releases intact. A successful repository read bypasses the comparison advisory lock, while detail and all writes still wait for it. The HTTP events route retains its preliminary locked ownership lookup.

The first-page legacy label-record index changes only in-process list assembly and source manifest v133. It requires no migration, setting, worker switch or special rollout; CI compares the exact accepted parent before merge. Deploy and restore complete immutable packages while preserving page snapshots and run/call evidence.

The second label-list read optimization removes the global advisory lock only from task/run/legacy list reads. A concurrent uncommitted writer is not visible to these PostgreSQL reads; POST run idempotency and its bound model snapshot still use the original write lock. No topology, schema, PLC or operator setting changes. Release and rollback as a complete immutable package; preserve 15-minute page snapshots and run/call evidence.

The first label task-list read optimization keeps the Web process, embedded label worker, schema, advisory-lock key and operator configuration unchanged. CI compares 1,000/10,000 synthetic PostgreSQL tasks and runs the established label concurrency/pagination smoke. Deploy or restore only a complete immutable release with source manifest v133 for the current complete release; retain page snapshots, run/call evidence and historical records on rollback.

Diagnostic receipt now runs through the diagnostic state service with the original station mutation transaction. Source manifest v130 changes no runtime topology, schema or operator setting. Deploy and restore complete releases; retain the original lease and browser evidence, and never retry an uncertain physical PLC write.

Diagnostic confirmation now runs through the diagnostic state module but retains the original transaction and active-lease fence. It does not clear in-flight evidence or imply successful physical I/O. Deploy and roll back complete releases with source manifest v129; continue using browser ACK/receipt evidence for physical outcomes and do not retry unknown writes.

PLC diagnostic reservation now uses a separate state module but retains the same browser serial ownership and PostgreSQL lease transaction. Deploy and restore the full release with source manifest v128. Do not retry unknown physical writes or copy individual PLC files during rollback; existing token-hash and ACK evidence remains intact.

PLC model rebinding now runs through lease maintenance with the shared active-lease fence and original PostgreSQL mutation transaction. The Web process and browser-owned serial topology are unchanged. Deploy and restore the complete release with source manifest v127; do not copy individual PLC files or alter lease and dispatch evidence during rollback.

The PLC lease acquisition extraction requires no schema migration, worker switch or device operation. CI uses synthetic workstation data and isolated PostgreSQL; rollback restores the previous complete release without copying individual modules or altering lease and dispatch evidence.

The PLC lease-maintenance extraction requires no schema migration or worker topology change. Deploy the full release and retain the previous complete release for rollback; no PLC hardware or paid inference is needed for its synthetic CI contract.

The legacy PLC config diagnostic extraction keeps the same Web topology and browser-owned serial I/O. It introduces no schema migration, worker mode or operator setting. Deploy or restore the complete release with source manifest v124; do not copy individual PLC modules.

PLC dispatch/diagnostic HTTP extraction keeps the Web process, shared database and browser-owned serial I/O. There is no schema migration, worker topology or operator setting change. Deploy or restore the full release with source manifest v123; do not copy individual PLC files.

PLC connection-lease HTTP extraction keeps the existing Web process, database, lease clock and browser-owned serial I/O. There is no schema migration, worker topology or operator setting change. Deploy or roll back the full release with source manifest v122; do not copy an individual PLC file.

PLC workstation-management HTTP extraction keeps the existing Web process, shared database and browser-owned serial I/O. There is no schema migration, worker topology or operator setting change. Deploy or roll back the whole release with source manifest v121; do not copy isolated route or state files.

Pipeline stage-transition extraction retains the embedded Web runner and existing task-lock ownership. No database migration, operator setting, worker topology or PLC change. Source manifest v120 affects only new task fingerprints; deploy or restore the complete release with persisted tasks and call evidence intact.

Pipeline advance lifecycle extraction keeps the embedded Web thread and existing process-local inflight/cancellation registry. No database migration, operator setting or worker topology change. Source manifest v119 changes new source fingerprints only; rollback restores the previous complete release, while persisted task state and call evidence remain.

Pipeline auto-Agent runtime extraction keeps the embedded Web thread, shared inflight registry and existing exception/cleanup behavior. No database migration, new operator setting or worker topology change. Source manifest v118 affects new task fingerprints only; rollback restores the previous complete release while retaining persisted task state and call evidence.

Pipeline recommendation runtime extraction retains the embedded Web thread, shared inflight registry and existing cleanup behavior. No database migration, worker topology or operator setting changes; source manifest v117 affects only new task fingerprints. Rollback restores the previous complete release and retains persisted tasks and paid-call evidence.

# Production runbook

Pipeline trained-model linking extraction keeps catalog lookup and caller-owned task locks/saves. No database migration, worker topology or operator setting changes; source manifest v116 changes new source fingerprints but retains 312 entries.

Pipeline training-status extraction keeps the existing local interrupted-task settlement path and its possible training-state write, without adding pipeline locks or retries. No database migration, worker topology or operator setting changes; source manifest v115 affects new task fingerprints only.

Pipeline reconciliation extraction preserves task and registry lock ownership, the five-second list throttle and current background scheduling behavior. No database migration, worker topology or operator setting changes; source manifest v114 affects only new task fingerprints.

Pipeline accessory route extraction keeps the existing membership store, authorization and ordered alias removal semantics. No schema migration, worker topology, PLC behavior or operator setting changes; source manifest v113 affects new task fingerprints only.

Agent feedback extraction preserves the single locked mutation/tool-call path and unlocked advance scheduling. This release does not alter worker topology, database schema, provider settings or the meaning of cancel. Source manifest v112 updates new task fingerprints only.

Pipeline list extraction preserves the current write-capable GET, process-shared reconciliation interval and lock boundaries. Release topology, database schema and operator settings are unchanged; source manifest v111 records the moved list modules for new task evidence.

Pipeline Agent chat extraction is route-compatible and keeps the existing two-lock request flow, one Agent decision, stored-call evidence and scheduling behavior. The source manifest moves to v110 for new task fingerprints; no database migration, worker topology switch or operational setting is introduced by this PR.

Manual pipeline advance/cancel extraction changes only route composition. Deploy and rollback continue switching the complete Web release under the existing health gate; no database migration, new worker service, PLC command or release procedure is added. Persisted task state is retained on rollback; process-local threads, registry entries and cancellation events restart under the existing recovery path.

Pipeline task-delete extraction changes application route composition only. Install and rollback switch the complete Web release with its matching source manifest; it adds no database migration, worker-topology step, PLC action or production command. Restoring the previous code release does not undo a completed task or resource deletion.

Pipeline task-create extraction requires no database migration or worker-topology operation. Install and rollback switch the complete Web release under the existing health gate; saved task records remain in the current database.

Pipeline task-update extraction changes the application route composition only. Deploy and rollback continue to switch the complete Web release; no database migration, worker-topology change, PLC action, or additional production command is required.


Pipeline resource-status projection ships with its root adapters and both source-manifest entries as one complete package. Worker topology, database schema and deployment commands remain unchanged; restore the previous complete release if required.

Pipeline task label and accessory-name projection ships with its root adapters and both new source-manifest entries in one complete package. It changes no worker topology, database schema or deployment commands; restore the previous complete release if needed.

Pipeline recommendation helper extraction changes no worker topology, database schema or release commands. Publish and restore its Web adapters, helper module and ports as one complete package with the bundled source manifest.

The current source manifest is v109 (296 entries). Per-domain notes describe which sources belong in the complete release; they do not identify when each module first appeared. Deploy and roll back only a complete release with its matching bundled manifest.

Pipeline AI task-card synchronization remains in the Web process. The bundled source manifest includes its new module and ports; deployment and whole-release rollback use the existing procedure.

Pipeline background publication still selects library images before provider fallback,
then creates variants and writes the manifest before task projection. Existing partial
files and task state on failure are unchanged. This extraction adds no service, database
migration, admission change or physical PLC operation. Verify the complete release and
restore the previous complete package and topology on failure.

Background-library selection preserves image reads, metadata aliases, callback failures
and candidate caps. The global cap is checked after append; a zero cap still admits the
first candidate. This extraction adds no task mutation, database transaction, model
call, worker change or PLC action.

Background evidence preserves file decoding, directory creation, write-false
continuation and exception propagation. A successful write may precede a later timing or
logging failure. Reference source reads can continue after the patch cap is reached.
This extraction changes no worker topology, admission gate, transaction or physical PLC
behavior.

Profile generation retains fallback and provider-error behavior, callback order, aliases
and partial item updates on failure. This extraction adds no model calls, transport
retries, worker mode or maintenance setting. Keep the existing complete-release restart
and rollback process.

Reference resolution retains duplicate catalog last-wins behavior and input reference
order. Exceptions midway through resolution propagate with prior callback effects intact
and later references unprocessed. This extraction introduces no provider calls, retry or
worker mode.

Applying profile dimensions preserves the previous physical_size object when numeric
conversion or payload construction fails. Equal sizes keep the existing dictionary
identity; replacement retains the returned payload alias. This extraction changes no
retry, worker or deployment mode.

Accessory profile normalization still converts all eligible reference entries before
applying its limit. Conversion errors beyond the eventual cap propagate; this extraction
introduces no retry or new runtime mode. Existing full-release restart and rollback
remain.

Accessory label updates retain their existing in-memory item/profile mutation order. A
later profile-read failure can leave an earlier item update intact. No I/O, new runtime
option, process or retry is introduced; ordinary whole-release restart and rollback
remain.

Reference evidence preserves path mutation before subsequent failures, direct file
hashing, nullable image decode and the existing OSError boundary. Context formatting
errors and fraction decoder errors still propagate. No new runtime switch, process,
retry or resource owner is introduced; ordinary whole-release restart remains.

Preview asset loading retains existing filesystem reads, decoder errors and
normalized-path mutation before decode. Failures can leave the same partial metadata
changes. No process, retry, resource lifecycle or runtime switch is introduced; use the
ordinary whole-release Web restart.

Asset composition retains existing in-place canvas and metadata effects, including
partial outcomes on failure. No process, resource lifecycle, retry or operational switch
is added. Continue the ordinary whole-release Web restart procedure.

Preview sprite selection retains existing asset reads and non-AI preprocessing effects,
including original failure and partial metadata behavior. This extraction adds no
process, retry or lifecycle owner. The ordinary whole-release Web restart remains the
deployment path.

Materialized asset discovery preserves existing file existence checks, image reads and
in-place dictionary updates. A failure can leave the same partial metadata state as
before; this extraction does not add atomic file or metadata transactions.

Preview pose selection retains existing sprite discovery file/image reads and metadata
effects through its asset callback. Callback exceptions and HTTP errors preserve their
original ordering; this extraction adds no worker, storage or model configuration.

Pose candidate policy keeps existing sprite asset file/image reads and metadata effects
through the same callback. No new I/O, worker topology, model loading or transaction change
is introduced; nullable results, aliases and narrow exception handling remain intact.

The geometry extraction introduces no model loading, file writes or worker topology
change. Shared rembg ownership stays in the cutout runtime. Existing crop copies,
nullable results and fallback ordering are preserved.

A process owns one cutout session cache and lock. Successful sessions are reused;
ordinary initialization failure permits a later call to acquire a session, without an
internal retry loop. Construction does not download or warm up a model. No worker
topology or global label concurrency change is introduced.

Material alpha extraction adds no model loading, image storage writes, retry policy or
new process. Existing callback failures and caller-owned array/statistics behavior remain.

Sprite publication preserves existing partial file and metadata effects. Single-image
write False returns no artifact; batch canvas normalization historically continues metadata
updates after False. This extraction does not add atomic writes, retries or new processes.

Sprite metadata extraction preserves direct Path semantics, decoder fallback/exception
behavior and partial in-place updates. No process, migration or configuration change is
introduced. Restore a complete release while retaining task/media/model evidence.

Sprite geometry extraction adds no process, model call or storage effect. Existing image
preprocessing and rendering callers retain their entry points. Use complete-release rollback
and preserve all task, media and model evidence.

Object sprite preprocessing keeps existing file effects, model-cutout gates and propagated
failures. Generated output may return success while remaining partial. No worker topology
or database migration changes; preserve evidence during whole-release rollback.

Crop component analysis and selection add no model call, file write or runtime process.
Existing preprocessing callers retain their entry points. Deploy and roll back the complete
release together, retaining task/media/model evidence.

Photo-highlight sprite coordination retains existing provider error boundaries, artifact
write order and partial-success state. Tests use synthetic bytes and mocked providers.
Deploy and roll back the complete release, preserving task/media/model evidence.

Photo-highlight image-helper extraction retains image algorithms, score/reason metadata
and codec failures. It adds no provider call or retry. Rollback uses the previous complete
release and retains task, model and media evidence.

Photo-highlight task preparation keeps configuration pauses, legacy-call skipping,
provider creation order and partial progress on failure. Existing callers own persistence;
the image-mask producer remains an unchanged collaborator. Roll back the complete release.

Pose materialization retains existing cutout fallbacks, all image writes before the retained
sprite cap, postprocessing order and partial state on failure. Existing callers own persistence
and task coordination. Rollback restores the previous complete release and retains media,
model and task evidence; no automatic retry or cleanup policy is introduced.

Pose task execution preserves existing call/status update order, provider-error boundaries
and partial state on unexpected exceptions. Real-photo preparation keeps its existing gates
and never introduces a legacy fallback. No retry or worker topology change is added. Restore
the previous complete release on rollback and retain call/task evidence.

Pose artifacts retain image-before-hash-before-metadata write order and partial files on
failure. No retry, cleanup, worker or task-claim policy changes. Rollback restores the previous
complete release and preserves task, model and call evidence.

The offline pipeline decision check uses synthetic configuration/storage collaborators and
verifies both deferred scheduling outputs are empty for empty input. It changes no service,
worker, database or rollback behavior. Full legacy phase3d tests still contain retired-worker
expectations and are not production health checks.

Pose planning services preserve reference-collection fallback, provider exception boundaries
and partial plan/status updates. There is no new process, paid-call retry, task claim or
persistence policy. Rollback restores the previous complete release and retains evidence.

Pose asset and template services retain in-memory path normalization and the existing asset
reuse policy. They add no process, persistence, task claim or retry. Rollback restores the
previous complete release and retains task, media and model evidence.

Agent state services preserve partial updates on failure and original object references.
Existing callers still own persistence, locking and task scheduling. There is no new runtime
process or retry policy. Rollback restores the previous complete release and retains evidence.

Agent action services retain the pending-advance collector and original partial state on
failure. Existing callers still own task locks, persistence and scheduling. No process topology,
paid-call retry or task claiming policy changes. Rollback restores the previous whole release.

Agent pipeline decision extraction adds no worker, scheduler, database write or retry. A
conversation failure retains the same partial in-memory state as before. Existing pipeline
transaction and task advancement boundaries remain in the application. Rollback restores the
previous complete release and preserves model, task and call evidence.

Agent settings HTTP extraction changes no worker topology, maintenance state, deployment
process or configuration. Retired legacy write/probe endpoints remain disabled. Restore the
previous complete release for rollback while preserving task state and model/call evidence.

Agent invocation services ship with the existing application adapters and model-provider flow.
No new worker, service process, setting or maintenance gate is introduced by this extraction.
Unknown transport outcomes are not replayed. Rollback restores the previous complete release
while retaining model versions, task state and call evidence.

Agent settings services and their application adapters deploy together in one release. Legacy
settings saves retain their existing fixed temporary path and partial-write behavior. Unknown
filesystem failures escape without retry. Restore the previous complete release for rollback,
retaining runtime settings, secret versions and task evidence.

Key identity and local secret-file services ship with their adapters in the complete release.
Tests use private temporary paths and synthetic values. Unknown filesystem errors escape without
automatic retry; existing chmod OSError tolerance is unchanged. Rollback restores the previous
complete release and retains secret files, model secret versions and task evidence.

Provider key registry code and its capability definitions deploy in the complete release.
This extraction changes no secret-file persistence, database schema or worker topology.
Validation uses synthetic keys and isolated test state; rollback restores the prior complete
release while retaining runtime evidence and secret versions.

Provider configuration policy and public URL projections deploy with their typed capabilities
and adapters in one immutable package. This extraction changes neither storage nor worker topology.
Synthetic contract tests verify validation and redaction; rollback selects the prior complete
release while preserving runtime evidence and model secret versions.

Legacy provider settings and explicit capabilities ship with the model-profile migration
callbacks in one immutable release. No configuration, database schema or worker-topology change
is introduced. Offline synthetic settings and isolated PostgreSQL profile contracts verify the
change. Rollback restores the previous complete release while preserving runtime evidence.

Public status projections and explicit capabilities ship in the complete immutable release.
This extraction changes no worker topology, storage schema or operational configuration. Verify
permission/redaction contracts with synthetic users and settings; rollback restores the previous
complete release while preserving runtime data and model/call evidence.

Provider selection, retry policy/evidence and orchestration services ship with their explicit
capabilities and source manifest as one immutable release. This extraction does not change paid
call policies, worker topology or database schema. Offline acceptance uses model substitutes;
rollback restores the previous complete release while retaining task/call and secret evidence.

Agnes/Qwen image transports, explicit capabilities, composition adapters and source manifest
ship as one immutable release. Worker topology, database schema and paid-call behavior remain
unchanged. Offline acceptance uses synthetic responses. Rollback restores the complete prior
release while preserving runtime data, call evidence, model secret versions and old snapshots.

The Gemini transport extraction changes no worker topology, database schema or paid-call
retry policy. Deploy or roll back its application adapter, ports, implementation and source
manifest as one immutable release, preserving runtime records, call evidence and old snapshots.
Verification uses synthetic responses and does not require real Gemini requests.

The OpenAI-compatible transport extraction changes no worker topology or database schema.
Its application adapter, explicit ports, accounting adapter and source manifest deploy together
as one immutable release. Roll back the complete release while retaining task/call evidence,
runtime data and historical model snapshots. This change adds no live-provider acceptance calls.

The provider-foundation extraction changes no worker topology, database schema or paid-call
execution. Existing root exception imports and old serialized exception paths remain readable;
new serialization records the real new module path. Deploy and roll back a complete immutable
release while retaining runtime data, task/call evidence and historical model snapshots.

Detection media services preserve the existing inspection-image failure suppression,
reference-sheet partial-file effects and process-local cache behavior. Output location remains
caller-scoped. This migration needs no database change or worker cutover; restore the previous
complete release for rollback while retaining all runtime files and task/call evidence.

Ordinary image/video upload services preserve partial uploaded-file evidence and existing
capture release/error boundaries. This extraction changes no worker topology, database schema or
PLC behavior. Restore the previous complete immutable release for rollback and retain stored data.

Profile-cache JSON persistence keeps the same temporary filename, replacement and chmod
attempts. Partial write/replace failures retain the same file residue, and a save failure leaves
in-memory creation evidence intact. The extraction does not change file concurrency or move cache
data. Use whole-release rollback; do not delete model secrets or task/call evidence.

The presence-inspection service preserves the existing cache and generation accounting,
coverage retry, error metadata and per-call timing. This structural migration does not enable a
separate worker. Whole-release rollback retains tasks, call evidence and secret/model versions.

Detection orchestration now uses explicit domain capabilities while keeping its existing
model scope, promoted-model fallback and output/persistence order. This migration does not enable
an independent worker or change PLC behavior. Use whole-release rollback; leave stored task,
model-secret and call-evidence versions intact.

The annotation extraction preserves the existing output naming, rendering and file-error
boundaries, including partial files after a failed write. It needs no maintenance switch, schema
change or worker cutover. Roll back the complete package without rewriting records or snapshots.

Presence normalization is a structural extraction that preserves the existing count and
confidence decisions. It adds no maintenance switch, database migration or worker topology change.
Rollback uses the previous complete release; stored tasks, calls and model versions remain intact.

The failure-response extraction preserves existing failure fields, metadata merging and response
object relationships. It requires no migration, runtime setting or worker cutover. Restore the
previous complete package on rollback; do not rewrite stored task or model-secret versions.

The presence payload/validation extraction needs no operational switch or migration. Request text,
provider coverage checks, count handling and existing retries remain unchanged. The previous complete
release remains the rollback unit; retain task records, model secrets and stored source fingerprints.

Accessory lookup and required-item resolution use extracted modules with the existing public
adapters. No operational switch, migration or worker change is needed. Duplicate handling, missing
metadata and required counts retain their prior behavior; rollback restores the complete package.

Retired worker dataset/training entry points perform their single failed-task update and return;
task/dataset inputs are not inspected. The updater is captured before reading the clock. Retired
refresh is a public projection only and ignores include_artifacts, with no task write, clock read
or remote call. Existing notes and partial projection mutations remain; historical remote logic
stays unreachable. Rollback restores the complete package without rewriting stored records.

Retired JSON, multipart and retry request entry points still reject calls before reading settings,
arguments or transports. The retry-named function does not invoke even the JSON helper. Status
flags do not trigger probing. Historical unreachable code remains preserved; this extraction does
not make it executable. No external request, retry, worker service or topology is enabled.

The retired worker watcher startup handler remains registered and invoked, but still does nothing
and starts no thread. Its dormant loop retains one interval read, exception reporting and sleep
order through explicit callbacks. No scheduling, shutdown, stop event, retry or worker topology is
introduced. Existing historical worker records stay read-only through the same entry points.

Legacy worker artifact import preserves prior overwrite and partial-file behavior. Invalid first
eligible payload/checksum returns the existing error without trying later models. Directory
creation precedes naming; model write precedes optional best.pt copy; metadata precedes the second
clock. Errors do not roll back or retry those writes. Retired worker execution remains disabled.

Legacy worker bundle submission still attempts streamed upload then one form fallback after
RuntimeError, including RuntimeError from completion persistence. Retry sleep remains before
progress stop/join. Other exceptions bypass fallback. Progress construction is outside each
attempt's finally; resolve/build are outside outer cleanup. Stop failure skips join, and outer
cleanup can replace earlier outcomes. These existing behaviors are preserved, not expanded.

The worker stream helpers preserve partial counters and their existing error boundaries. Upload
headers resolve outside request exception handling; download headers resolve inside it. Download
closes the response before decoding JSON. Progress stops through the caller-owned event; this
extraction adds no initial/final flush, stop/join, shutdown behavior or retry. Outer bundle submission
still owns its existing attempts/fallback. Restore complete releases, not individual helper files.

Legacy remote training still makes one HTTP request and closes the archive before checking the
response. Failures after entering the existing try block invoke cleanup; metadata/environment
failures before that block keep the original cleanup boundary. Cleanup failures may replace an
earlier exception. This extraction does not reactivate retired workers or add retries/compensation.

Rejected empty-scene validation still leaves the uploaded capture; later state failures preserve
prior file/background/task writes. Task save occurs before the existing optimization-state lock;
state mutations and save remain under that lock, and public projection remains outside it. No
compensation or retry is introduced. Deploy or roll back the complete matching release package.

Background tasks retain their existing in-process threads and save/register/start order. A failed
start retains the saved task and registered thread. Background generation failure writes manifest
failure before task failure, and preserves prior outputs. Unknown process results are not retried.
Ship or restore all three background-task modules with the matching immutable package.

Task background replacement still deletes the previous set directory before copying the source,
then generates variants and persists metadata. Later failures keep the original partial file or
metadata effects; this structural change adds no compensation or retry. The whole immutable
package, including the background modules and source manifest, remains the rollback unit.

Background catalog reads can still copy the default image, ensure minimum variants and write the
manifest. Existing targets are preserved, and later initialization failures retain prior files or
in-memory changes according to the original ordering. This module extraction does not introduce
atomic replacement, cleanup, retries or process-topology changes.

Jobs API extraction preserves task mutation before save and task deletion before refreshed list
projection. A subsequent save, public projection or list failure does not undo the mutation or
repeat deletion. Image process controls remain in their existing services; topology and process
shutdown behavior are unchanged by the adapter move.

RunPod transfer extraction preserves existing failure evidence: ordinary streaming failures attempt
temporary-file cleanup, while cancellation is outside that Exception handler. After replacement,
digest, clock or task-metadata errors leave the final archive in place. Do not infer a missing file
from an error response or automatically replay an upload. Deployment topology remains unchanged.

Training launch extraction preserves task enqueue before user-state persistence. If a later clock,
state, merge or save step fails, the already-created task may still run; do not automatically retry
submission or discard its evidence. No process topology, shutdown or restart behavior changes.

Training status projection retains visibility checks before task refresh and existing writes
that settle interrupted visible tasks. Hidden/missing queued or running records are still marked
stopped in the projected state. Settlement write failure stops further hydration/projection without
retry. Normal state responses retain the original object; stale preview projection shallow-copies
only after active-task hydration has already updated that object. Ship/restore all four input/state
modules with matching source manifest as one complete release.

Preview submission preserves sequential partial completion: create directory, draw images,
write plan JSON, update user state, merge accessory changes, then save configuration. It does not
remove prior files or retry after a later failure. Missing clean object sprites return the existing
409; text fallback remains allowed. Jobs-root lookup occurs only when the plan is written, and the
store does not create a missing jobs directory. A false save return still returns the original plan.
Deploy/rollback the complete workflow package with matching source manifest.

Preview rendering retains original output failure semantics: a false return from image writing
still produces the existing URL response; a write exception prevents URL generation, and a URL
exception leaves an already-written file. No automatic retries or cleanup compensation are added.
Occluded labels remain in the preview with the original dropped flag and complete amodal box.
Deploy or restore the renderer and its ports with matching source manifest together.

Preview placement still makes at most 180 candidate attempts and does not retry exceptions.
Overlap sums include repeated placed rectangles; failed searches keep the earliest minimum.
Successful metadata reports zero overlap, while failure reports the rounded minimum with its
original pass flag. Deploy or roll back all three layout modules and source manifest together.

Background lookup keeps existing selection and default-seeding behavior; it is not a newly
pure read. An unreadable image returning None uses the synthetic fallback, while read/fit/augment
exceptions propagate without selecting another image or retrying. All successful/fallback paths
augment once and preserve the shared random stream. Deploy or restore both background modules
with matching source manifest as a complete release.

Resource deletion retains the current file-delete, training-marker, pipeline-marker and response
query order. Errors stop later stages and do not restore earlier files or records. Sample deletion
can still report removed manifest records after a swallowed manifest-write OSError, even if those
records remain on disk; this extraction preserves that behavior rather than changing recovery policy.
Model deletion still requires the selected run directory to exist, unlike missing dataset retirement.
Normal release restart and whole-package rollback remain in effect with the complete release and its matching source manifest.

Training resource listing is not a pure read: its existing task-view dependency may mark an
interrupted local training task stopped. Visibility is checked before this lifecycle refresh,
and refresh failure aborts later resource aggregation. This extraction does not change that
write path, permissions, locks or cleanup behavior. Restore the complete release with its matching
source manifest; do not copy individual catalog files into production.

Archive export keeps the original replacement and cleanup sequence. Once a temporary bundle
is acquired, cleanup runs after export success or failure; cleanup failure can supersede an
earlier error. Already replaced export directories and completed writes are not rolled back.
Artifact import verifies the optional checksum before selecting the output directory, then
writes weights, copies the uploaded ZIP, writes library metadata and writes the response summary.
Later failures retain earlier files; no retry or compensating deletion is added. Deploy and
restore the complete package with matching source manifest.

RunPod orchestration preserves its existing failure boundaries: exceptions propagate to the
outer training runner and do not trigger an extra submission, GET retry, cancel or local fallback.
Completed artifact import and record writes can remain when a later summary/sync/warmup step
fails. The training polling deadline is checked before sleep; completion returned after that
wait can still be accepted. This extraction retains that training behavior and does not alter
label-detection timeout/late-response rules. Restore the complete package with manifest.

Dataset generation keeps its existing partial-failure behavior: already written images,
labels, annotation previews or YAML remain after a later step fails. An incomplete manifest
write can leave partial content. No retry, cleanup or transaction spanning files/config is
introduced. Error during asset normalization saves configuration only for HTTPException, and
save failure still supersedes that exception. Restore the complete release with its matching
bundled manifest; do not repair a rollout by copying individual generation files.

Training runner extraction preserves existing execution and failure handling. A process
exception is not retried, and errors after a process starts do not introduce a new terminate
or kill action. A later sync/warmup exception can still enter the existing failure settlement
after an earlier completed update; this structural batch does not redesign that behavior.
Submission failures retain prior saved records and thread-map entries according to the
original step order. Deploy/restore all matching modules and source manifest together.

Training status propagation still saves account configuration before the pipeline record,
then updates the candidate state after releasing the pipeline lock. It does not add a
cross-store transaction: later failure may leave earlier writes and in-memory changes, as
before. Exceptions stop later steps; a false return value alone does not. Two-account tests
verify request identity isolation, not prevention of concurrent whole-config lost updates.
Ship/restore the matching bundled manifest and modules together; historical snapshots are retained.

Executor settings and the active RunPod client now have explicit dependencies. They do
not start workers, retain environment credentials in a service instance, or change training
submission/polling behavior. The existing 401/403 authorization-format fallback remains;
unknown transport outcomes still fail without retry. Offline transport contracts require
no production access. Deployment and rollback continue to use the whole release package.

Training stop/delete remains non-atomic in its existing order. A failed stop creates
no deletion marker; failures after marker assignment can leave both requested and
canonical IDs pointing to the same marker even if deletion/persistence failed. JSON
delete still skips read-cache invalidation. Markers are process-local and restart
behavior is unchanged. SIGTERM is sent at most once by each stop invocation, with the
same exception handling; no process join or retry is introduced. Restore the complete
release and retain records; this extraction does not change worker topology.

Pipeline JSON saves retain DATA_DIR creation and fixed tasks/state .tmp files followed
by os.replace; failure may leave a temporary file while the original target remains.
Destination parent directories outside DATA_DIR are not implicitly created. JSON
single task saves replace the first matching raw ID; deletes remove every match.
PostgreSQL partial-state rollback preserves other keys; rollback errors can replace
the original exception as before. This batch introduces no schema or topology change.
Recover by restoring the complete immutable release and retaining existing runtime data.

Training storage still uses ordinary JSON write_text with indent=2 and default
ASCII escaping, requiring job_id and an existing directory. It does not add an atomic
file replacement: partial-write failures can leave partial content as before. JSON
reads suppress OSError/JSONDecodeError only; PostgreSQL errors never fall back to JSON.
Model binding can remain added to the in-memory task after a later failure. Locks are
released on exceptions, including nested saves. Recover with the whole release; keep
runtime records and deploy both new modules with source manifest.

Training discovery extraction introduces no schema, connection, cache-policy or
process-topology change. Artifact discovery can still expose a task whose weight file
is absent; existing selection/loading performs its later checks. Finder snapshots
retain the existing partial-failure behavior and must be consumed on their creating
thread. Deploy and roll back the entire package, including the three new modules and
source manifest. Existing records and historical model snapshots are preserved.

Warmup remains the existing best-effort daemon-thread operation. Disabled runs only
update enabled/status/error; old detail fields remain. Setup errors can leave the
prior status, and formatter or BaseException failures may leave running status.
Prediction failures are recorded and remaining models continue. This extraction adds
no thread coordination or lifecycle idempotence; deploy/restore manifest and all
components as one complete release.

Local model cache behavior remains process-local and unlocked during first load.
Same-ID hits still select/validate their specification; new IDs check file existence
before reusing a live instance at the resolved path. Removing an instance can leave
a path alias that still influences readiness, as before. This batch does not alter
warmup threads or restart behavior. Roll back the complete package with manifest.

Task projection/catalog extraction preserves current filtering and merge behavior,
including partial in-memory changes before an exception. It introduces no database
migration, cache policy or runtime topology change. Publish/restore both modules and
source manifest with the entire immutable release.

Detection task storage extraction preserves cache invalidation and existing partial
failure behavior. JSON saves retain the fixed `.json.tmp` path and atomic replacement;
failed replacement leaves the old target and temporary file. This batch changes no
locks, cache policy, schema or worker topology. Recovery remains whole-release rollback.

Detection OCR extraction preserves synchronous local prediction, process-local
caching and original exception boundaries. A malformed batch result still triggers
the original per-image fallback; short valid batches are not padded or retried.
Single-image build errors remain outside its prediction catch. This structural
batch does not add initialization locking or change concurrency, topology or model
parameters. Deploy/rollback all OCR modules and manifest as one complete release.

Detection result modules preserve the existing in-process inference topology.
Filtering still annotates candidate dictionaries, parsers still prefer nonempty
boxes over oriented boxes, and rule errors retain their original propagation.
Deploy and roll back the complete immutable release; no data migration or runtime
maintenance action accompanies this structural batch.

Legacy incoming workflow modules preserve partial-failure boundaries. Activation
can persist before task publication fails; JSON review writes the inspection before
audit, and repeating an already identical decision does not repair missing audit.
Retention only removes eligible evidence: partial unlink failures do not mark the
record; a later audit failure does not restore removed files. This refactor does not
run retention or change database transactions. Roll back the complete release.

OCR and Beta services remain inside the existing Web process; restarting clears
these process-local states as before. A failed initialization remains retryable on
a later request; Beta failed comparisons retain their prior cached-review behavior.
The migrated PDF decoder still lacks an explicit close and does not share raster
size checks; those existing boundaries are not changed here. Roll back the complete
release with its matching source manifest and retain task snapshots and records.

Incoming-store extraction retains the shared JSON lock and file replacement rules.
Invalid JSON or read OSError still yields an empty list, while invalid UTF-8 propagates.
Replacement failure keeps the old target and completed temporary file; this batch
does not add cleanup or claim to resolve the earlier Windows replacement error.
Deploy or roll back the complete package containing the runtime file adapter and
incoming store together, preserving existing records and audit evidence.

Comparison extraction preserves attempts, media, uncertain-call evidence and the
existing review/audit ordering. A failed final save can leave a persisted attempt;
retry is not a recovery action. Use the usual complete-release restart and rollback
with matching manifest, retaining historical snapshots. This batch does not
activate an independent label worker or modify deployment topology.

Standard-route extraction keeps the current jobs, write locks and complete-release
restart procedure. Partial imports and edit evidence retain existing behavior; a
repository-factory failure after media creation can leave that file. No cleanup or
schema migration is bundled. Rollback restores the full prior package and retains
standard revisions, feedback, source files and uncertain classification attempts.

Revision/diagnostic extraction retains caller-owned transactions, baseline writes,
partial-failure evidence and existing log handling. It introduces no schema change,
worker switch or cleanup. Ship all three modules with the matching entry point and
restore the previous complete release on rollback, retaining records and snapshots.

Media extraction preserves existing evidence and cache failure behavior. Cached
asset read/hash failures do not rerender from the parent PDF; a save failure may
leave the new file and mutated asset, and an atomic replace failure may leave its
temporary file. Resolved links targeting the owned directory retain prior behavior.
No cleanup, data migration or provider policy change is bundled here. Roll back
the full release together with its matching provenance manifest; retain old records.

Text-record store extraction requires only the usual complete-release restart.
No schema, index, JSON format, cursor or worker-topology migration is included.
Keep attempts and revision history on rollback. Restore the full previous package,
including its matching entry point and record-store module; do not copy files alone.

Prepared comparison dependency extraction keeps both existing module-level slots,
daemon threads and timer behavior. Timer cancellation does not join its callback;
settlement still relies on the existing compare-and-set. Local final-save failure
can prevent cleanup/release, while Qwen final CAS failure still cancels the timer
and clears the connection; cleanup failure can prevent release. Retain these known
boundaries during structural migration. Preserve unknown-call records and private
evidence, and roll back only the complete release; no new worker topology is enabled.

Preparation module extraction retains the current daemon job, single preparation
slot and whole-release restart/rollback. Keep attempts, snapshots and revision
media. Existing cleanup failure can prevent slot release; a duplicate-claim view
failure can trigger a second release and mask the original exception. These are
recorded boundaries, not changes bundled into the structural migration. Unknown
paid calls remain non-replayable. No schema or worker-topology change is introduced.

Extraction dependency changes use ordinary complete-release restart/rollback.
Preserve immutable edits, tombstones, source media and uncertain attempts. A failed
final save still clears the worker connection but does not justify automatic replay.
No data migration or worker-process switch is included in this extraction.

Agent HTTP extraction uses the existing immutable-release restart and rollback.
Include the API, dependency, schema and projection modules together. Preserve durable
operations, reservations and unknown-outcome evidence; no new tables, workers or
account enablement are part of this extraction.

Document-job extraction preserves daemon threads and normal complete-release restart.
A thread-start failure can leave a durable claim, and unknown attempts must not be
replayed. Existing cleanup-callback exceptions still prevent slot release; this batch
records that boundary rather than combining an exception-policy change with extraction.
Restore the previous complete release while retaining attempts and evidence.

History extraction requires only the existing complete-release restart/rollback.
Keep the compatibility module and new history package in the same release. No data,
index, cursor format or worker-topology migration is introduced; preserve immutable
revision/media evidence during rollback.

Codex dependency extraction uses the existing complete-release restart/rollback.
The independent Codex worker is unchanged. Preserve partially imported standard/media
records and immutable task evidence on failure; do not auto-retry document/model work
or copy individual modules between releases. No data or topology migration is needed.

Label dependency extraction keeps the existing embedded topology: one PDF import
thread and two detection threads in the Web process. Startup, stop-event signaling,
claim and cleanup behavior are unchanged. Use the normal whole-release restart and
rollback; no independent-worker switch or queue drain is introduced by this batch.

Route-selection extraction uses ordinary immutable-release restart and rollback.
A failed profile attempt still permits route saving and AI-task creation. A later
AI-task or projection failure can follow a successful save; preserve that record
and do not auto-retry inference or invent rollback of these existing partial effects.

Preparation extraction uses the normal whole-release restart and rollback.
Candidate preparation can leave frames or thumbnails before a later failure, as
before; preserve these files and task evidence. No database migration, automatic
model retry or worker-topology cutover is part of this extraction.

Image-job metadata uses ordinary complete-release restart and rollback. Preserve
existing task IDs, old model/secret references and anchor/guide evidence, including
partial metadata left after a file-read error. New tasks use the versioned source manifest;
rollback does not rewrite their snapshots or regenerate/requeue paid work.

Gallery extraction uses ordinary whole-release restart and rollback. Verify
authorized detail previews with synthetic media. Preserve existing generated
previews and task/source files during rollback; a failed detail request may already
have written earlier previews. No image regeneration or data migration is required.

Management extraction uses ordinary full-package restart. Preserve candidate and
accessory records on rollback: confirmation can persist an accessory before a
later candidate write fails, as before. Do not auto-retry model preparation or
infer transaction atomicity from this structural extraction. The existing JSON
whole-accessory deletion 404 remains a separate issue; PG deletion order is unchanged.

Accessory file editing uses ordinary complete-release restart and rollback.
Check authorized upload/crop/delete and reference selection with synthetic media.
On regression restore the previous complete release, preserving file and task
records; do not replay model calls or remove already-written files during rollback.

Candidate extraction uses ordinary complete-release restart and rollback. Check
candidate retrieval and existing job status display. Preserve task identifiers,
anchor provenance and model snapshots, including repairs already persisted during
reads. Do not regenerate images or replay provider calls when rolling back.

Accessory catalog extraction uses the ordinary complete-release restart. Check
owner/shared/admin listing and details. New tasks record the current prompt-source
manifest; retain old snapshots and paid-call evidence on complete-release rollback.
No record-ID conversion, image regeneration or data migration is required.

Record access uses the ordinary complete-release restart. Verify member-owned and
shared record access and administrator assignment. On regression restore the
previous complete release, retaining accounts, sessions and ownership records.

Audit projection extraction uses the ordinary whole-release restart and rollback.
Check displayed creation/update times and ownership in analysis and cost views.
Restoring the previous release requires no data or timestamp conversion.

Shared ownership policy extraction uses the ordinary complete-release restart.
Check owner/shared/admin record visibility. Roll back the entire prior release on
regression; do not relabel records, rewrite owners or clean historical data.

The auth HTTP/service split uses ordinary complete-release restart and rollback.
Check administrator/member login, navigation and protected media. Existing cookies,
password hashes and account rows require no conversion or session reset. Preserve
all runtime records when restoring the prior complete release.

Request-authentication extraction retains sessions and deployment topology. After
the ordinary complete-release restart, check login, protected API/media access and
navigation. A regression requires complete-release rollback, preserving session,
model and paid-call evidence; no account conversion or provider replay is needed.

Authentication foundations use the ordinary immutable-release restart. Existing
sessions and password hashes require no conversion. Verify administrator/member
login and navigation; rollback restores the complete prior release while retaining
user/session tables. No session reset or database cleanup is part of deployment.

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

## COS evacuation tooling

`scripts/cos_migrate.py` provides operator-run inventory, upload, independent
verification and isolated restore. It does not switch runtime storage, modify database records, delete
local data, or authorize disk detachment. Pause relevant file writers for the final
inventory/transfer; an online inventory is only preliminary evidence.

Run `inventory --root SOURCE --include outputs --manifest MANIFEST` with reviewed,
non-overlapping relative roots; repeat `--include` for other selected subtrees. Keep
manifests and receipts outside the source filesystem in a restricted directory.
The tool creates new 0600 files and refuses overwrites. Dot paths, credential/key
names, local environment/config/auth files and symlinks are recorded as excluded;
review exclusions and preserve required local-only state separately. A file scan
is not a consistent PostgreSQL backup: take `pg_dump` with the approved database
identity, verify restore separately, and select the dump as a reviewed input.
Never copy live PostgreSQL data files into COS.

Install the official `cos-python-sdk-v5` in a separate operational environment and
record its resolved version. Supply `COS_SECRET_ID`, `COS_SECRET_KEY` and optional
`COS_SESSION_TOKEN` through restricted process credentials, never command history,
TAT command text, source or reports. The application environment is unchanged.
Use `upload --manifest MANIFEST --receipt NEW_RECEIPT --bucket BUCKET --region REGION`.
The default `objects/sha256/` layout is content-addressed: manifests map legacy
paths to checksums, and receipts record final object keys. The target bucket must
be private and in the approved region; uploads request STANDARD storage over HTTPS.
Credentials need scoped read/write/multipart operations, not deletion or management.

Each object is read back in full and SHA-256/length checked. Existing objects are
verified rather than overwritten; partial runs have no complete footer. Retry with
the same manifest and a new receipt. Changed sources require a new inventory.
Use `verify` with the same options for an independent remote readback. Before disk
retirement, preserve restricted remote copies of the manifests and receipts and
verify recovery of original paths and permissions. Completed receipts alone do not
prove runtime readiness, account isolation, database restore, or sufficient local
working space; those remain separate cutover gates.

For a representative restore, use `restore --manifest MANIFEST --bucket BUCKET
--region REGION --destination NEW_DIRECTORY --include RELATIVE_FILE_OR_SUBTREE`.
Omit `--include` only when a complete restore fits locally. The original source
disk need not exist. The command requires a new destination and enough free space
for all selected bytes plus a 256 MiB reserve. It verifies each complete download
before publishing that file, fails on corruption, and never replaces existing
files. Restored files are private (0600) under a private root (0700); the operator
must apply the reviewed application's ownership/permissions after validation.
Retain the command's result and manifest digest as recovery evidence. A partial
directory after failure is not a successful restore; use a fresh destination for
another attempt. For database restore checks, enumerate every application schema,
not only `public`, and reject a validation run that checked no business tables.

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


## Agent policy read transaction

For an Agent policy read-path release, inspect the backend CI Agent PostgreSQL regressions before promotion. The policy display read may return the preceding committed policy while an update is in flight; a later read returns the committed update. Policy updates and admission still serialize on the account advisory lock. Roll back the complete immutable release if policy reads fail; no data migration or worker topology switch is involved.


## Fixed-reference model read transaction

For a fixed-reference model read-path release, verify both the existing model-profile PostgreSQL contract and the new isolated read-transaction regression in backend CI. A pinned task remains on its stored model version and secret reference; a connection-test status or usage call being written appears only after commit. Roll back the complete immutable release on a read-path failure, retaining profile versions, secrets, tests, calls and task snapshots.


## Model registry initialization fast path

For a model initialization fast-path release, require the isolated PostgreSQL warm/cold race and failure-retry regression in backend CI. Existing installations should take the short committed-state read; a new or missing state still migrates under the original advisory lock. On failure, restore the previous complete immutable release and retain profile rows, secret versions and task snapshots; do not attempt a reverse migration.

## Model task snapshot read transactions

Task model snapshots may now return the last committed binding while an administrator has an uncommitted update. Newly submitted tasks continue to persist their selected snapshot; pre-migration tasks retain their historical migration snapshot. No operator action or new configuration is required.

## Model admin public read transaction

The administrator model-library view may show the last committed revision while a settings write is in progress; a refresh after commit shows the new revision. Connection-test statuses are read by version and may reflect separately committed statements. No operator setting or rollout action is required.

## Label list-only run payloads

No operator action is needed. The first label task-list page transfers fewer model/prompt/layout/snapshot fields from native run rows; details and saved 15-minute cursor pages retain their existing content. Continue normal complete-release rollback if list behavior regresses.

## Embedded installer bridge checks

For the first bridge release, expect the old host installer to perform the application switch and then promote the new installer. The production workflow must read back the installed script digest and exact live `/api/version` commit before publishing. The next embedded release exercises the new manifest check. The package still declares only `vantaline`. The promoted controller can recognize the fixed future label-worker topology, but no standalone worker is enabled by this embedded package.

If promotion fails after the application has passed health checks, the command reports `application_committed=true control_promotion=incomplete` and fails. Verify the live commit, then retry the same immutable release to complete promotion; do not infer that the application rolled back. If the application fails before commitment, the installer restores the previous symlink and Web service as before. Never enable a separate worker based on this embedded-only bridge.


## COS runtime transition gates

The compatibility adapters remain disabled by default; their presence is not disk
retirement evidence. First install the pinned SDK dependencies through the existing
controlled dependency update, then deploy a complete CI-approved immutable package.
Do not copy application modules to the host. Keep a complete COS-compatible rollback
package before changing storage mode.

`import_cos_locations.py --pair MANIFEST RECEIPT --report NEW_REPORT` validates
complete manifest/receipt identity and reads every unique remote object back without
opening the original disk. Add `--apply` to append missing locations after verification.
Provide runtime configuration and systemd credentials as above. Reports are exclusive
0600 files; partial imports can resume, but a conflicting path requires explicit delta
reconciliation. Historical object keys are reused, never copied to a second prefix.

Do not enable production COS until every business file producer/consumer, active
missing reference, two-account permission test, largest-dataset preparation, bounded
real RunPod/detection test, final paused-writer delta, fresh database restore and
rollback gate pass. Normal maintenance starts only after readiness; begin rollback
at minute 25 and restore within 30 minutes. If the expired disk is reclaimed first,
remain in maintenance and recover only with a COS-compatible complete package.
After normal unmount, verify service restart, host reboot, a complete release and
COS rollback with no legacy-disk fallback or fstab dependency. Observe seven days
without formatting the original disk or deleting historical COS objects.

The image adapter slice is still a compatibility rollout, not cutover authorization. Ordinary file and native-reader contracts do not certify live Codex/image-worker scratch directories or every asynchronous provider path. Keep the production file-store mode local until those paths, request staging bounds and the complete disk-inaccessible service tests pass.

Before COS commissioning, review and run `scripts/setup_artifact_volumes.py` without flags for its read-only space plan, then use `--apply` from the verified release to provision local capacity caps. The script creates only absent backing files, never reformats existing files or touches the business-data mount, and requires 8 GiB free plus a 1 GiB setup margin after preallocation. It installs three persistent mount units; it does not change application mode. Configure systemd `RequiresMountsFor` for all three mounts, ReadWritePaths for the state roots, the private LoadCredential, and TMPDIR to upload/spool. Verify the same configuration in the independent acceptance instance before switching either production service. Native workspace failure/unknown provider outcome must not cause an automatic paid retry. A missing image runtime credential is a commissioning gap, not a reason to disable a previously working feature.

COS RunPod submission reserves upload headroom and publishes a durable per-job claim before the paid POST. An existing claim prevents automatic resubmission after a timeout, process death or lost response; operators must reconcile the original remote job. Dataset generation and ZIP preparation share the exclusive work slot, and COS training rejects local/legacy-worker fallback. Regression fixtures exercise capacity rejection before POST and a timed-out POST that is called only once.

Detection image persistence and pipeline resource availability are included in the COS adapter gate. A successful inference with a failed artifact upload is a failed request; do not retry a paid teacher to compensate for unavailable storage. The independent source-inaccessible service acceptance remains required.
## Label consumer lifecycle

The embedded label controller now exposes an internal `drain()` result: true means both consumer threads and their cleanup exited; false means drain cannot be acknowledged: threads may still be live, or startup/connection cleanup failed. Inspect the internal state and live-thread count. Stop admission includes already-admitted blocked claims in the drain budget; a failed drain cannot authorize a worker topology switch. The 420-second task deadline fences results but does not cancel external I/O. Application waiting is bounded at 480 seconds; host systemd allowance remains a release-controller prerequisite. No independent label worker or maintenance gate is enabled in this release, and the PDF-import daemon remains in Web. Restore a complete previous release on failure; do not requeue unknown paid calls.

A connection-cleanup exception marks that consumer generation failed even after its threads exit. Drain returns false and in-process restart is rejected; process restart is required. The lifecycle regression also retains falsey repository/run handling and the original idle decision after cleanup.

Attempted threads are tracked before native launch. Any startup exception fails that controller even if no thread is currently live, because launch may already have happened. Registration is serialized per process to prevent duplicate hooks during concurrent composition. Synthetic tests cover failure before and after native launch and concurrent registration.

If the label batch or payload benchmark blocks main CI, retain its per-case raw samples and limits before investigating latency. Do not infer runner noise or loosen the P95 guard from a bare assertion. Automatic release stays blocked until the normal CI gate succeeds; production remains on the last accepted complete release.

Source-inaccessible acceptance must include application startup with existing image-job records: guide/provenance hashes use the same COS file adapter as business media. Verify production dependencies and SDK imports as both actual service accounts before installation; a root-only successful import does not establish readable package metadata for systemd services.

### COS commissioning service and rollback checks

For the embedded label controller's 480-second drain, commission a systemd
`TimeoutStopSec=510s` allowance with `KillMode=control-group` before the controlled
release restart. Check the effective unit values after `daemon-reload`. Drain
active jobs before maintenance; this allowance does not extend the 30-minute
normal cutover window or permit a retry of an uncertain paid call.

Validate the source-inaccessible instance with normal application lifespan
hooks enabled. A diagnostic instance started with `--lifespan off` can locate
individual request failures, but cannot satisfy startup or worker acceptance.
For authenticated media checks, retain both existing rules: a user's private
output subtree rejects another user, while root-level administrator/legacy
outputs remain shared with authenticated users. Anonymous access remains denied.

Retain the immutable package, archive digest, source commit and verified live
version for each accepted COS rollback target. The installer's successful
same-release retry is an integrity/readiness check, not a fresh release test.
The post-unmount full-release gate must exercise installation of a different
complete CI-approved release. Switching back to an already installed complete
rollback tree requires stopped/drained services, package verification and an
atomic `current` symlink replacement under the production release lock. Preserve
COS mode, private credentials, system-disk data root and volume dependencies;
then restart every release-consuming service and recheck version and business
reads. Never restore pre-COS storage configuration with an otherwise compatible
code rollback.

## Installed runtime controller checks

After the root-owned script digest matches the immutable artifact, the workflow checks its read-only capabilities. Schema-1 deployments still use the existing embedded Web restart; the 500-second managed stop settings apply only when the later schema-2 runtime bridge is installed. Do not enable a worker from capability output alone. A first schema-2 external deployment must be preceded by an accepted embedded control protocol and explicit shared-configuration migration.

Managed transitions retain root-only recovery evidence under `/var/lib/vantaline-release`; any journal left in the older backups location blocks installation for inspection. A queue that cannot drain aborts the switch and attempts to restore the same instance's prior admission state. Missing/stale runtime identity, unavailable database evidence, wrong configuration and missing bridge prerequisites fail closed. A rollback failure keeps admission fenced, retains both complete releases and the transition journal, and reports failure instead of claiming recovery. Restore both declared roles from one complete version; never copy a runtime module or replay an uncertain paid call. Synthetic controller fault drills do not replace real worker, configuration, PostgreSQL concurrency and production acceptance tests.

A killed installer leaves a PID lock and managed journal. A root advisory guard allows retry only when the old PID is demonstrably gone; an alive or ambiguous owner still blocks. Retry the same verified archive to recover the recorded phase, including when Web is stopped. Recovery checks the package before startup and repeats version, static assets, service journal and PDF proxy acceptance before reopening label admission. A different pending transition blocks another release. Do not delete the journal to bypass recovery. Existing maintenance and paused consumer states survive success or rollback.

The rollback journal records restored pointer/units before restarting old roles and binds their verified instances before reopening admission. Same-transition recovery then resumes that restoration without stopping a live old consumer, including a crash after admission reopened. Retain the journal until the whole-release health check and final cleanup succeed.

Rollback pauses the candidate before waiting for its active runs and admitted iterations to finish; it preserves queued rows without starting paid work on an unaccepted build. A forward switch from an already-paused predecessor also retains its backlog and pause intent. An active predecessor still drains its queue before a normal forward switch. State-machine and rendered-installer faults cover queued legacy-to-managed rollback and paused-backlog transitions; queued work is not evidence of an active call.

## Label runtime state preparation

Deploy `2026_10_04_label_runtime_state` through the immutable release installer and its existing migration checksum ledger. It creates an empty table for later label runtime control. Roll back the whole release while retaining this table and any later operational records; never reverse the migration. Existing label tasks, calls, model bindings and PLC evidence are untouched, and the worker remains embedded.


## Managed embedded label control

The managed embedded runtime requires the installed controller bridge and prior additive state migration. Its private control endpoint returns exact release/build/process identity, monotonic heartbeat, queue counts and drain acknowledgement. Each newly installed build starts paused/closed until controller acceptance. Same-build restarts preserve the durable state. On rollback, the previous managed build starts fenced and the controller restores its prior intent. Keep the complete previous release, task/call evidence and operational table; do not clear the table to bypass a gate. Independent worker, shared credentials/configuration and COS service mount inheritance must be verified in their later transitions.

The control endpoint owns a dedicated PostgreSQL connection factory with explicit connect/TCP failure-detection settings; request and paid-task connections retain their configuration. SQL timeouts apply after connection, and the root client has a separate bounded acknowledgement deadline; these do not constitute a hard total deadline for every driver operation. A control-thread shutdown timeout retains its role lock and fails that controller generation until process restart. Regression probes block connection creation and verify no duplicate role, then release the old thread for cleanup. A real claim/processing-substitute/cleanup integration proves pause does not acknowledge drain until two admitted iterations finish, while queued task snapshots remain unchanged.

The current managed embedded activation package declares schema 2/protocol 1, following the accepted schema-1 recovery-storage and stop-allowance bridges. Its first installation uses the accepted controller, retains the sole Web service, initializes the new build paused behind maintenance, and reopens only after acceptance. The compatible controller checks exact effective Web allowances of 500 or 510 seconds, worker allowance of 500 seconds, and control-group kill mode before stopping services. Unsupported effective values cause pre-stop failure and restoration. Retain the earlier COS commissioning administrator-owned 510-second file; the compatibility policy must be promoted through its preceding schema-1 release before managed commissioning. This release does not enable an external worker.


## Recovery storage bridge operation

Install the new schema-1 repair bridge as a fresh immutable release through normal
CI deployment. Preserve the existing application-owned base/backups directories,
legacy root guard and PID lock protocol, and administrator systemd drop-ins. The
successor installer validates or creates its root-only 0700 state directory at
`/var/lib/vantaline-release` during its next installation; read-only capability
probes do not create this directory. Never use chmod/chown, file replacement or
journal deletion to bypass a failed state check. Existing unsafe entries, legacy
journals, other-release pending journals and malformed current journals require
inspection before another transition.

The old controller can accept the bridge application and then fail installer
promotion. In this window the application may be healthy while the release remains
unpublished. Confirm live release/commit and installer digest before recovery. The
old controller's same-ID retry cannot promote on the application-owned backups
layout; recover with a different complete, reviewed schema-1 release. Retain all
accepted and failed release evidence. Only after successor promotion and complete
release acceptance may a separate schema-2 commissioning PR proceed. Effective
Web allowance of exactly 500 or 510 seconds, worker allowance of exactly 500 seconds
and control-group mode are mandatory with the separately promoted compatibility
controller. The storage repair never rewrites an administrator's 510-second setting
or claims that its precedence has been validated in production.


## Commissioned stop allowance bridge

Deploy the Web stop-allowance policy as a new complete schema-1 release after the
root-storage bridge is accepted. This normal successor-driven installation also
validates or creates the new root-only recovery directory; do not create it with a
separate host command. Verify the exact promoted installer digest and healthy
schema-1 version before a later schema-2 release. Merely bundling the policy in the
schema-2 activation package is insufficient: the previously installed strict
controller would still execute that transition.

Keep administrator unit files unchanged. Managed commissioning checks the effective
Web allowance is exactly 500 or 510 seconds and the label-worker allowance exactly
500 seconds, with control-group mode for every involved service. The installer
still has a shared 500-second forward drain/stop deadline and requires stopped
service state with both PIDs zero before a pointer switch. A 510-second PID1 fallback
does not extend that deadline or guarantee forced exit in 500 seconds. If stop or
rollback cannot verify exit, retain both releases, root journal and call evidence;
do not start a candidate, clear admission state or retry uncertain paid calls.

The benchmark statistics preparation is confined to disposable synthetic schemas in local/CI validation. It requires no production database command, configuration change or manual deployment action. Whole-release acceptance and rollback requirements remain unchanged.

## Managed embedded activation acceptance

Before merging this activation, accept both preceding complete schema-1 bridge
releases and verify their installed controller digests. The current package enables
only the embedded control protocol; its declaration still contains one Web service.
Keep the previous complete bridge as rollback target and preserve incremental tables,
model secret versions, calls and task snapshots. Do not reuse the failed earlier
managed release or delete its evidence.

Normal deployment validates root recovery storage, exact effective Web allowance
500/510 and control-group mode. On this first schema-1-to-schema-2 switch the old
Web has no managed pause/drain acknowledgement. Stop uses its existing shutdown
lifecycle and 480-second consumer wait; queued records may survive for the accepted
successor. Require verified service exit before changing the release pointer.
The new build starts paused and is accepted only after whole-application checks
and matching control identity, then admission is restored. Later managed-to-managed
forward transitions pause admission and drain an active predecessor before stop;
a failed drain restores prior intent. An already-paused predecessor keeps its backlog.
A failed acceptance uses the journal-bound complete-release rollback. This phase
neither installs an external label service nor establishes shared configuration or
actual standalone-worker capacity.

## Proposal: shared label runtime configuration preparation

The preceding embedded configuration bridge introduced a bounded data-only snapshot of the existing label/database/storage/network settings, exact existing model-secret environment references and data directory. Unset and explicit empty values remain distinct. COS credentials are represented by their byte digest and transferred only through a private root-authenticated path; a worker must receive its own systemd credential directory. The pure contract and private-file roundtrip tests use synthetic values. The candidate Web wiring can capture a configuration revision and export its immutable snapshot only through the private authenticated control socket; public status contains only the revision. A prepared root file publisher writes immutable private versions and restores one atomic current pointer. The installed helper now embeds the audited data-only contract, captures a peer/build/instance-bound private export before external transitions, and journals the previous configuration pointer before mutation. It restores that pointer with the complete release on rollback, derives escaped mount dependencies and provisions the worker own systemd credential from root-owned bytes. No candidate application module is imported by the isolated root helper. Tests cover pointer interruption, export tampering, private modes, standalone execution and synthetic installer recovery. That bridge release retained embedded execution. Its complete-release acceptance is a prerequisite for the external activation described below.

The configuration bridge preserves the existing COS reader credential forms, including a null optional token and unused metadata, while binding their exact bytes. A distinct previous configuration is fully validated before journaling or closing admission; corruption aborts before service changes. Rollback may replace a damaged candidate pointer with a verified previous version. These cases have offline regression coverage.

## Proposal: standalone label process

The candidate `label_inspection.runtime` bootstrap reads the root-owned immutable configuration and its own systemd credential, checks the active package build/topology, initializes local storage, and creates separate thread-owned business and control repository factories. It imports no Web application. The existing model service is reused through an existing-registry reader: missing registration fails startup rather than migrating legacy settings. Secret-file syntax, environment precedence, immutable version references and usage accounting remain unchanged. Manifest v141 names 366 actual sources; historic snapshots are not rewritten.

In external mode, Web composition owns admission/control only and constructs no label consumer. The standalone process owns the existing two-thread consumer and its exclusive role socket; SIGTERM/SIGINT stop new work and use the existing 480-second drain budget. Real isolated PostgreSQL tests cover old-model resolution after settings changes and reader recreation, actual child PID/peer checks, duplicate-role rejection, signal drain and controller-driven embedded-to-external acceptance, failure and complete rollback. Synthetic model values and local storage are used; no paid inference or PLC call occurs. The bootstrap-only predecessor did not enable an external release. External activation remains conditional on preceding complete-release acceptance and final exact-build validation as described below.

Standalone signal handlers only assign a monotonic stop latch. Normal control flow performs drain and cleanup; initialization checks the latch before consumer startup, and each consumer admission checks it even across the check/start boundary. Real child-process tests inject repeated SIGTERM/SIGINT before and during initialization and while native thread startup holds the worker lock; no post-stop iteration is admitted. Already admitted iterations retain the existing drain budget.

## Proposal: label runtime monitoring

Managed processes publish bounded heartbeats on the existing private control thread with a five-second target interval after the previous tick completes. Database work and control requests can delay a tick. Each uses the dedicated thread-owned connection factory. The operational table stores only build/configuration/process identity, worker state, process-lifetime counters and fixed recent-error codes. A blocked heartbeat retains the same role lock on shutdown timeout. The private deployment protocol remains unchanged.

`GET /api/label-inspection/runtime` requires administrator access before any database call. Its short unlocked READ COMMITTED transaction samples state, queue and heartbeat in separate statements; these are not an atomic health snapshot. It returns queue/active counts, oldest queue age, maintenance/pause intent and expected-role heartbeats; missing, mismatched or older-than-15-second samples are unhealthy. Heartbeat freshness is sampled liveness, not a guarantee against a subsequent crash. Lock acquisition counts/total/max wait include successful and timed-out acquisition attempts. These and rejected duplicate submission/stage-call counters belong to the process lifetime: process restart resets them, while a control restart within the same process changes the instance but retains counters. Idempotent replay is not counted as rejection. Errors never include exception strings, media, customer fields, secrets or filesystem paths. Real PostgreSQL/HTTP tests cover authorization, redaction, actual lock contention, duplicate refusals, stale generations and heartbeat shutdown. Manifest v142 names 367 actual sources. The observability-only predecessor retained embedded execution; the external activation below is a separate release and requires acceptance of every predecessor.

## Independent label worker acceptance

This activation requires the preceding managed embedded configuration and monitoring
releases to be accepted first. Normal immutable deployment closes detection admission
with the existing maintenance response and waits for accepted queued/in-flight work;
it aborts and restores intent when draining fails. Already-paused predecessors keep
their backlog and pause intent. The controller verifies old-process exit before
switching releases. Web then owns HTTP/control only; `vantaline-label-worker` owns
exactly two label consumer threads. Training and image workers retain their current
process arrangement.

Accept only matching Web/worker build and configuration identities, new process
instances, successful control acknowledgements and application checks. The admin
runtime endpoint exposes sampled queue age/counts, active work, expected role
heartbeats and bounded operational counters. Samples older than 15 seconds or
identity mismatches are unhealthy; a fresh sample is not continuous-availability
proof. No credentials, internal paths or customer payloads are returned.

Worker signals stop further admission and wait up to the existing 480-second drain
allowance; the task deadline remains 420 seconds. Systemd worker stop allowance is
500 seconds and Web allows exactly 500 or 510. On failed acceptance the controller
stops the new worker before restoring the whole managed embedded release and its
configuration. Preserve recovery journals if exit or rollback cannot be verified.
Actual production capacity and latency require release observation; synthetic tests
must not be reported as paid-model or physical-PLC acceptance.

The label detail-read change needs no migration or new configuration. Roll back the complete release to restore the former read fence; historical task/call/model evidence remains unchanged.

PLC structural modules are packaged together with Web and the release-declared label worker. Deployment and rollback remain complete immutable releases. No PLC hardware calls are made by the new validation checks; browser ownership and server-side transport disablement remain mandatory.

The auto-optimization structural batch is included in the complete release with Web and the declared label worker. No database migration or service topology change is required. Roll back the complete prior release and its declared topology; preserve task records and model evidence.

Pipeline structural services ship with Web and the declared label worker in one complete release. There is no new migration or service topology. Roll back the whole previous release while preserving mutable task records and model evidence.

Accessory image services ship with the same complete Web/label-worker release. No new process service or migration is introduced. Retain model evidence and mutable records during whole-release rollback. Candidate cleanup refuses shared references but preserves existing partial deletion and check-then-delete behavior.

Configuration services retain original partial-failure behavior: primary-file replacement is atomic, backup OSError is best effort and may leave a temporary file, and local model-config replacement failure may leave its pending temp file. No stronger concurrent-writer or backup guarantee is introduced. MCP stdio errors retain the existing close-before-one-local-fallback behavior; this is not a new uncertain-call retry guarantee. Label durable stage admission and unknown-result rules remain unchanged.

## Derived label summary state preparation

Install the additive `2026_10_04_label_run_projection` migration only through the
normal complete release. It creates empty derived state and an atomic row-change
invalidation trigger, without enabling cached reads or rewriting history. The
migration owner must own the label source and new objects; existing application
writers need only their original source DML privileges. A five-second DDL lock
timeout leaves the migration unapplied; inspect workload/lock ownership and retry
through the normal release flow, never remove the trigger to force progress.

Whole-release rollback retains this side table, function and trigger. Old writers
continue invalidating the cache without extra grants. Administrative imports or
restores that disable triggers can bypass this invariant: before any future
cache-reading release is admitted, discard only derived projections in the
controlled maintenance procedure and verify source/trigger integrity. This
preparation introduces no cache reader, backfill or topology switch and is not
evidence of full list performance or production acceptance.

Before admitting the summary preparation, the generated-schema and import real-engine checks must accept complete trigger definitions and retain their SQL-error rejection. These temporary single-user databases open no listening sockets and do not touch production state. The production migration and complete-release rollback procedure are unchanged.

The pure label projection helper ships in the complete release. It changes no database reader, cache publisher or worker topology; retain derived storage and evidence on whole-release rollback.

## Optional post-settlement summary preparation

The publisher requires the additive projection migration and uses the existing
consumer threads after business settlement. Confirm the service database role
can read the source and insert/update derived state during acceptance; older
source-only writers remain compatible with the invalidation trigger. A missing
permission or unavailable cache produces a fixed `summary_publication_failed`
operational event and leaves the completed business result intact. No cached
HTTP read is enabled by this slice. Rollback restores the complete previous
release and retains derived objects; do not reverse the migration or replay
unknown calls. Optional publication is included in drain, and stop/pause skips
work that has not begun. Local SQL limits are not a guaranteed network deadline.

The list cache reader must follow the accepted empty-table/invalidation and publisher releases. Confirm the actual runtime role can SELECT the projection table before deployment. A missing/unknown cache version safely uses original list data; a missing table or missing SELECT grant is a release prerequisite failure, not a reason to silently skip database errors. Whole-release rollback retains the compatible table and source invalidation trigger. No historical backfill is run.

The reader prerequisite is enforced during candidate Web startup, after the normal package switch but before background callbacks, control readiness or HTTP serving. Missing source/projection SELECT/schema or a timed-out SQL check rejects readiness with a fixed safe error; the installed controller cannot start the candidate worker or accept/open admission and performs its existing complete-release rollback. This can extend the ordinary restart interruption on failure; it is not a pre-switch or zero-downtime check. The query uses the actual business connection and only required columns with LIMIT 0, accepting column-level grants. It uses a read-only transaction, 1 s lock and 1.5 s statement limits, followed by rollback and connection release. These SQL limits are not an end-to-end network/connect deadline. Do not grant permissions automatically or change DSNs to pass the check.

Reader benchmark diagnostics run only on isolated synthetic PostgreSQL. They do not query production, change runtime topology, retry model calls or relax deployment gates. A failed benchmark leaves release unaccepted; continue using the last accepted complete package until the new commit passes the normal CI and release verification.

Service-path relocation preserves existing file migration and output placement semantics and changes no production data automatically. File writes retain the original error and partial-effect behavior. Request identity is resolved for each placement call. Rollback restores the previous complete Web/worker package.

Request/store/JSON cache instances now own their state independently. Existing process-local invalidation, five-second cross-process TTL and metadata-key freshness remain unchanged; no eviction, data migration or lock redesign is introduced. Deploy and roll back the complete release; process restart recreates in-memory caches.

Directory/path-migration state is now owned by an application lifecycle object. The existing migration still marks completion only after callbacks finish; an exception leaves it retryable, and partial earlier file effects remain. No extra migration or historical rewrite is introduced. Rollback restores the complete release and retains mutable data.

Stateless foundation policy relocation changes no worker, configuration, database or release procedure. Deploy and restore complete packages with the versioned source manifest; no historical task data is changed.

Digest/name relocation changes no file storage selection, upload limit, worker topology or naming policy. The existing name helper is not a new path sanitizer. Restore whole releases and retain runtime data and task/model evidence.

The runtime repository HTTP adapter relocation keeps administrative authorization in the existing endpoint and connection cleanup in the existing thread scope. It introduces no new probe data, connection pool or monitor. Rollback restores the previous complete release without changing database or task evidence.

Protected configuration methods move into AppConfigStore with the existing shared RLock and context-local authorization. Database commit followed by response/load failure retains the original partial-success semantics; do not infer rollback or retry. Restore a complete accepted release if needed, retaining additive schema, source records, snapshots and call evidence.

Native history statistics require the same accepted projection schema, publisher
and SELECT privileges as the cached reader. Deployment introduces no data rewrite
or topology switch. Observe first-page latency and memory against the same workload;
sparse histories may pay aggregation overhead while repeated histories transfer
fewer rows. Roll back the complete release if the operational baseline regresses;
retain derived tables and source invalidation, and never replay model calls.

The history query's late JSON projection is a read-only query change in the
complete release. It adds no schema or operator setting and requires the same
actual-role startup reader gate. Restore the previous complete package on failure;
retain projections, source records, snapshots and call evidence. Isolated query
plans and synthetic benchmarks are not measurements of production capacity.

History result column-name reuse is confined to a single query result. It changes no configuration, schema, API or worker topology; whole-release rollback and snapshot/call evidence retention remain unchanged.

The native history reader combines a same-statement current-proof gate with result-local column-name reuse. A batch with no current owned proof uses the ordered fallback branch without history windows; proven batches retain guarded count/latest aggregation. The gate and both source branches use the original typed owner comparison rather than converting the owner parameter to text. This is a new candidate combining two previously separately measured mechanisms, not a retry or acceptance of earlier failed candidates. Both fixed performance protocols and their original latency, memory and query limits remain mandatory; no universal speedup is claimed.

Native list-history fallback now compacts a nonempty `quality` object only when every immediate value is a JSON string, boolean or null. This matches the existing public checked marker while avoiding unnecessary evidence transfer. Numeric and nested values stay intact so JSON decoding errors remain visible; other fields, ordering, detail payloads and old snapshots are unchanged. PostgreSQL/HTTP regressions cover flat Unicode/string/bool/null, empty and other shapes, and bounded-decoder failures. The original complete performance protocols and thresholds remain mandatory; private diagnostics are not acceptance.

Account and resource policies ship with all callers in the complete release. This structural slice changes no schema, transaction, model call or process topology and performs no data rename/migration. Restore the previous complete release on failure while retaining records, snapshots and call evidence.

Public network policy relocation preserves configured CORS and public status filtering behavior. There is no new setting, network probe, permission or topology switch. Whole-release rollback restores the previous complete application and worker package.

Documentation composition uses existing authentication/session storage and no new background process or database lifecycle. Duplicate-route preflight rejects an already installed GET route before adding any documentation route. Unexpected failure during later route registration is not transactional; discard a partially built app. Deploy and roll back complete releases preserving runtime data.

Authentication composition changes no session format, permission, database query or worker topology. The repository and user administration share one per-composition RLock; PostgreSQL transaction/coordination boundaries stay unchanged. Independent graphs use isolated test stores; there is no new cross-process JSON-store safety claim. Deploy and roll back complete releases preserving users, sessions and runtime evidence.

Authentication HTTP composition preserves route/middleware order, authentication errors, media access and administrator documentation behavior. It adds no worker, storage migration or startup hook. Deploy and roll back the complete immutable release. Auth-only multi-app tests do not demonstrate full production lifecycle isolation.

Provider proxy relocation introduces no new network operation, environment setting or process. Existing request-time proxy resolution remains. Release and rollback restore the complete Web/label-worker package; no credentials or historical snapshots are rewritten.

The optional stdio client keeps existing limitations: initialization errors retain the assigned process, close terminates without a new wait/join, and stream reads retain their existing timeout policy. This structural move adds no retry, response-ID enforcement or shutdown guarantee. No real subprocess or paid model is used for routine acceptance; deploy and roll back complete releases.

MCP helper relocation retains the current startup thread and optional-client topology. Warmup still catches start failures and reselects the client for close; a close failure still propagates. This adds no timeout, join, retry or shutdown guarantee. Ordinary acceptance performs no subprocess/provider call. Deploy and roll back complete releases preserving all runtime evidence.

Model warmup request extraction retains the existing YoloWarmup state, thread start and startup behavior. A failure after a thread starts is not compensated or retried; status and final readiness can still fail independently. No new deduplication, drain or lifecycle guarantee is introduced. Apply and roll back whole releases with their declared topology and preserve task/call evidence.

Local model selection extraction changes code ownership only. Device/checkpoint defaults, process topology, database schema and model loading remain unchanged. Deploy and roll back the complete release; synthetic selection checks do not establish GPU, model download or production capacity availability.

Image payload relocation changes no storage, provider calls or worker topology. A decoded byte sequence is not newly validated as PNG. Deploy and roll back complete releases, preserving task snapshots and call evidence.

Detection task request relocation changes no database statements, schema or deployment topology. Existing save/delete-before-response/link-update behavior remains observable on failure; no automatic retry or rollback is added. Roll back the complete previous Web/worker release while preserving records and evidence.

Detection rule extraction is structural and retains existing save, failure and partial in-memory mutation semantics. No migration, automatic normalization, historical task rewrite or model call is performed by deployment. Restore the previous complete release on failure.

Camera orchestration extraction changes no dispatch transaction, browser lease, physical I/O or uncertain-write retry rule. Evidence is still declared before analysis. Existing best-effort error settlement and partial file/result effects are retained; extraction does not introduce replay. Use complete-release rollback and preserve dispatch/call evidence.

Detection rule domain composition does not change worker topology, authorization, database lifecycle or transactions. Config and identity providers are called per request. A duplicate domain installation fails before either rule route is added. Independent test apps prove this domain boundary only; the complete Web app still has remaining global assembly. Deploy and roll back whole releases, preserving records and model snapshots.

Duplicate-route preflight is not a transaction around arbitrary FastAPI registration failures. If application construction fails during route installation, discard that partially built application. No retry or cleanup guarantee is added.

Analysis graph composition preserves all local RLock scopes, PostgreSQL writes/transactions, list projections, publication ordering and partial failures. It adds no cross-process guard, cache invalidation or stronger consistency. Deploy and roll back complete releases; retain data, task snapshots and call evidence.

Dashboard task ownership is a structural move without a new lock, task transition or runtime topology. Whole-release rollback preserves task records and existing storage. The fixture with two service instances proves capability separation, not cross-process atomic task creation or full application isolation.

Accessory selection and dimension relocation changes no storage, worker topology, provider or PLC behavior. Deploy and roll back complete releases, preserving task/model snapshots and existing accessory records.

Accessory readiness/status/reference ownership changes no queue admission, subprocess or worker topology, retry policy, filesystem storage, model binding or PLC behavior. Existing partial mutation/save failure behavior is preserved. Deploy and roll back complete releases while retaining data and call evidence.

Image worker state ownership does not split a process or introduce a shutdown/retry policy. Its thread and child-process bookkeeping remain process-local under the existing Web service control group. Deploy and rollback complete Web/label-worker releases with persistent job evidence intact.

Pipeline registries remain process-local and reset under the existing Web restart/recovery policy. State ownership introduces no worker process, persistent schema or cancellation/retry policy. Restore full releases while retaining task/call evidence.

Auto-optimization locks and thread registries remain local to the Web process with the existing restart behavior. This ownership change does not split training or image work, alter scheduling or introduce recovery retries. Restore only complete releases while retaining task/call evidence.

Auto-optimization settings composition freezes only the chosen policy instance and its method capabilities; it does not freeze computed settings, user identity or database connections. There is no worker, thread, model or PLC topology change. Deploy and roll back complete releases preserving data and task evidence.

The legacy PLC worker state extraction must never enable those workers. Production continues Web Serial browser-only I/O; the root startup hook remains no-op. The retained routines have no new stop/join/cancellation contract and are not run for routine verification. Deploy and roll back complete releases without changing PLC or runtime configuration.

Active-lease ownership cleanup has no runtime topology or physical-device action. Deploy and roll back complete accepted releases, retaining station records and uncertain dispatch evidence. The synthetic method-instance check is not proof of full application-factory or production capacity isolation.

Legacy activation readiness ownership is a structural release only. Do not enable server-side serial workers; ordinary service startup remains Web Serial browser-owned. Whole-release rollback retains all existing coordination and audit records, and this change makes no new live-device or production-capacity claim.

The retained PLC coordination extraction changes code ownership only. It does not activate old server workers, change Web/label-worker topology, add a migration, or modify physical PLC permissions. Rollback remains replacement of the complete previous release; retained coordination rows are not rewritten.

The PLC dispatch-record ownership slice is structural and preserves current Web Serial, dormant legacy workers and external label-worker topology. It changes neither database schema nor release control. Rollback restores the full previous package and leaves dispatch evidence intact.

Moving retained PLC single-iteration workflows does not start legacy workers or change the Web/label-worker topology. The application startup hook remains dormant. Rollback uses the complete previous release; no PLC state, dispatch evidence or database object is deleted.

Web-shell composition retains public SPA responses, no-cache headers, preview redirects and legacy 404 responses. No worker mode, release topology or operator setting changes. Use the existing whole-release rollback and version checks.

The retained retired endpoints continue returning the same errors after the same middleware/body-validation/admin sequence. Rollback of the unreachable-tail cleanup restores the previous complete release; there is no data transformation or PLC action.

Repository composition introduces no schema, topology or operator setting. Whole-release rollback restores the previous composition while preserving runtime records and model evidence. This change does not add connection-pool capacity or stronger close/network deadlines; existing close error suppression remains unchanged.

Authentication-domain composition adds no schema, operator setting or service. Existing cookie, permission, media and admin documentation behavior remains. Rollback restores the prior complete release and its topology/configuration while preserving accounts, sessions and task evidence.

Record-domain composition changes no schema, routes, worker topology or PLC behavior. Existing whole-release rollback preserves accounts and inspection records. This slice does not establish a full production application factory.

Bootstrap locations do not move data, create a new data root or change release symlinks/topology. Directory creation and migrations still run at their existing points. Rollback uses the complete prior release and existing external runtime directories.

CostServices does not cache a connection, introduce an atomic ledger snapshot or change the existing source loaders and their file/cache/error behavior. It changes application assembly only. No operator setting or database migration is required; deploy and restore complete immutable packages with the matching topology.

Image worker lifecycle verification now includes the owned admission/drain smoke in CI. The bundled source manifest advances to v185 with the same 518 paths. Queue workers enter their own repository scopes; owner drain reports timeout without cancellation or retry. This slice does not yet wire Web application shutdown or MCP drain, so managed release topology and stop deadlines remain unchanged. Whole-release rollback remains required.

Image coordinator and child starts now retain uncertain-start handles even if `is_alive()` is false, child lists are pruned, or a later coordinator replaces the current handle. A failed start revokes an unentered target, and shutdown must join retained handles before reporting drained. A never-started handle may remain undrained; stored running evidence is preserved and never requeued. Deterministic interrupted-bootstrap tests cover both launch paths and later coordinator replacement.

MCP operations now have a client-owned admission boundary covering the complete tool dispatch, including the existing stdio failure fallback, and warmup cleanup. New operations are rejected before transport or fallback after shutdown begins; same-thread nested work belonging to an already admitted operation can finish. Startup and request serialization share the client lock, independently of the admission condition. The bounded shutdown waits for admitted work, then terminates and reaps owned transports; an expired deadline returns undrained without cancelling a blocked call or inducing fallback. Recoverable close retains terminated processes for later reaping. Existing provider selection, prompts, wire messages and transport-failure fallback behavior are unchanged. The client retains the startup warmup thread and admits it before construction/start. Shutdown drains this reserved startup operation, joins its owned thread, then retires transports. Application shutdown registration and full production factory integration remain pending.

MCP recovery retains both live and already-exited displaced processes by identity. An exited transport skips termination but still participates in final wait and stdin/stdout cleanup; EOF followed by the existing fallback cannot lose this cleanup ownership.

MCP warmup startup retains its enabled check and original callback, thread name and daemon setting, but now starts through its client owner. Duplicate live starts and starts after closing are rejected. Thread construction/start failures release reservations exactly once; a thread that started before a start error remains tracked. Already reserved warmup may finish nested client operations after closing begins; unrelated threads cannot inherit that admission. No join occurs under admission or client locks.

A failed or interrupted warmup `Thread.start()` cannot use `is_alive() == False` as proof that no OS thread exists. A target not yet entered is revoked, but its handle is retained and shutdown reports undrained until joining proves completion. A start that never actually created a thread can therefore remain conservatively undrained; no target or paid fallback is replayed. A deterministic interrupted-bootstrap regression covers the late-start window.

Uncertain warmup handles are also retained across a later warmup start. Replacing the current handle cannot erase a revoked thread that has not yet confirmed startup/completion; shutdown joins every retained handle.

YOLO warmup starts now belong to their `YoloWarmup` instance, including pending thread construction and every admitted thread. Each thread enters and releases its repository scope on that same thread. Closing rejects later starts and waits outside lifecycle/status locks; a timeout reports undrained without cancelling inference, changing model selection, or requeuing work. Existing repeated-start behavior and per-model handling remain. Application-wide lifecycle registration and per-app graph construction remain separate pending work. Prompt source manifest v188 retains the same 518 ordered files.

Interrupted or failed warmup starts retain uncertain handles even across later starts. An unentered target is revoked and every retained handle must be joined; a never-started handle remains conservatively undrained. The tests cover delayed native bootstrap, interrupted startup, later thread replacement and same-thread scope exit.

The training owner close result covers only admitted preparation, Python threads and repository scope exit. A false result never cancels, requeues, restarts or settles work. Interrupted starts and registration failures retain their handles; a never-started unjoinable handle deliberately leaves close false. A true result does not certify child-process termination, remote work completion or successful task settlement. This slice adds no production shutdown hook; full application lifecycle integration remains outstanding.

CodexBackgroundThread.close(timeout) rejects later starts and waits for admitted construction and actual Python thread/scope completion. It does not retry, cancel or settle an unknown generation result. The existing Codex process/transport implementation is unchanged, so a true thread-drain result does not certify child-process reclamation or generated artifact success. Future app shutdown must drain callers before this dependency and its model/MCP providers.

Closing the Codex starter does not wait for separate direct synchronous generation calls. Application shutdown must first drain their caller owners; a successful starter close alone is not proof that all generation activity has ended.

TransferProgress.close(timeout) may return false while an update callback, construction or uncertain thread start remains outstanding. It never cancels the upload/download, sends a final success update, retries a transfer or settles a training task. Future app shutdown must drain transfer callers before closing their reporter owner and repositories.

Auto-optimization starter close results certify local Python thread and repository-scope exit only. They do not cancel or settle training subprocesses or remote calls. Future shutdown integration must drain upstream callers before these owners and their dependencies; that application hook is not enabled by this change.

The foundational graph builder is inert. Existing server import-time directory creation and actual lifecycle callbacks remain in their prior positions, so this step does not enable a second production app or a second worker role. It changes no connection cleanup policy or deployment topology.

Automatic-mask Futures now finish after their repository scope exits. This closes the child-executor cleanup gap within the existing joined parent workflow; it does not prove remote model settlement, model-context propagation or application-wide shutdown. Repository close retains its established best-effort error handling.

Automatic-mask child tasks now resolve downstream training-vision settings under the parent task model snapshot. This is an intentional correction to prior bare-thread-pool context loss. Only that model binding crosses threads; repository selections stay thread-local and retain per-task cleanup. No paid retries, task requeue, global identity propagation or additional worker service is introduced.

Text document/preparation close stops new local admission and waits for already admitted preparation and owned native threads. An uncertain start can remain undrained until its handle can be joined, even if the unentered target was revoked and its slot safely returned. Never clear durable classification/preparation attempts or retry calls to force drain. This prerequisite does not yet install application-wide shutdown integration.

The HTTP shell builder changes only Web construction. It starts no worker, opens no connection and changes no deployment topology or drain procedure. Rollback remains restoration of the complete previous immutable release.

The HTTP upload-provider injection adds no rollout setting or resource startup. Production continues using its existing artifact provider until explicit full-app composition is implemented and verified. No separate artifact cleanup or change to disk-budget limits is installed by this slice.

The artifact runtime owner extraction retains process-default production selection and the existing restart requirement for an initialized non-local configuration change. It adds no resource shutdown, disposal, automatic reconfiguration, migration or credential rewrite. Restart and rollback still operate on complete releases.

Pipeline scheduler close is an owned-thread drain capability, not yet an application shutdown hook. Failed constructors or starts preserve original inflight/cancel registry evidence and are not automatically retried. Uncertain native starts remain conservatively owned until joining proves exit. Whole-release rollback stays unchanged.

The extraction owner is a prerequisite for application shutdown. Its close result covers prepared-input submissions and their native workers, not HTTP requests still reading or normalizing uploads. Stop and drain those upstream requests before closing extraction and its repository dependencies. Never remove an attempting record or retry an unknown provider outcome to force drain.

A comparison slot returned after cleanup failure only permits later independent work. It does not authorize resubmission of the failed comparison or imply successful database/model settlement. Keep its original attempt/call evidence for review; do not infer timer drain from timer.cancel.

Prepared comparison ownership exposes close(timeout): first close parent admission and wait for admitted preparation, native comparison threads and repository scopes; only then cancel and join deadline timers. A false result must not be treated as drained or used to close its repository dependency. Parent timeout leaves deadline callbacks active. This slice does not register an application shutdown hook, cancel paid calls, requeue uncertain work or alter release topology. Failed unjoinable starts remain conservatively undrained.

PDF import shutdown still sets its per-registration stop event. The retained owner offers close(timeout) for the later coordinated application lifecycle: false means admitted construction or an actual/uncertain native thread remains and dependent repositories must stay available. Rendering already in progress finishes through the existing progress protocol; stop prevents the next loop iteration. Constructor/start failures are not retried by the same owner. This slice does not activate a new shutdown timeout or service topology.

This offline lifecycle integration retains native-history/readiness and detection composition from actual main dcb4805 and follows artifact-owner candidate 6b648b5. Owned production/tests and ordered entry match reviewed 28de9fa; both canonical fixture corrections are already retained. The bundled manifest is v204 with 523 unique sources; earlier paragraph counts refer to their original individual candidates. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Publication must use independently reviewed domain-scoped PRs on accepted main, with full hosted and release gates; this offline combined tree is not a blanket grouped publication approval or complete application factory.

After the ASGI server has stopped serving and drained HTTP requests, Web shutdown executes its registered ordered drain. An undrained or exceptional owner causes a component-only RuntimeError; raw provider errors and paths are not emitted by the coordinator. Downstream resources remain available for unfinished work, and completed teardown callbacks are not repeated. Shutdown does not cancel training, kill provider processes with active calls, settle uncertain tasks, replay model work or claim successful persistence from thread completion. The existing systemd 500-second stop limit is unchanged; a long training job can exceed the available drain budget and must remain an explicit failure, not a successful-drain report.

Shutdown permanently closes these resource owners. The same production app instance must not be started again after teardown; process restart or a separately constructed resource graph is required. Two independently allocated HTTP shells are tested, not repeated startup of the same production graph. The native fan-out test executes actual pipeline auto-agent run and advance schedule/run methods with synthetic business ports, using the production shutdown binding order.

The retained MCP shutdown first waits for active operations, then terminates and reaps its owned transport process. The coordinator adds no forced termination or training-subprocess cancellation. The synthetic tests do not prove live Uvicorn request quiescence, nonempty production shutdown timing, or an acyclic graph under arbitrary replacement of live dependency suppliers.

This offline shutdown replay follows lifecycle candidate 7d7886a and preserves current native history, readiness, model/tail and canonical LF fixes. Four owned runtime/test/contract blobs match reviewed 82313c5. Manifest v205 lists 524 sources. The 480-second shutdown allowance remains cooperative and requires ASGI request quiescence; complete independent application composition is still pending. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Detection storage-port wiring deploys in the normal complete release. All runtime modes retain current storage validation and failure propagation. Roll back the whole prior release; do not copy individual adapters or remove artifact records. This change does not complete the application-wide artifact lifecycle migration.

This offline detection artifact replay follows shutdown candidate 8618f7a and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 713010a. Manifest v206 lists 524 sources. Storage suppliers retain call-time selection; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Detection media keeps existing operational limits: local-model ID/path caches do not revalidate remote generations, and an error leaving the model file lease may leave an already-constructed model cached before its path entry is recorded. Local video keeps its existing cleanup behavior; remote video releases the capture in finally and exits the materialized-file lease even when capture release raises. This refactor does not redesign those failure semantics. Reference-sheet graphs need independent caches and consistently bound file/encoder providers; changing one supplier between operations is not a transaction snapshot or a supported store hot-swap.

This offline detection media replay follows artifact candidate e7e12b2 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 5e86530. Manifest v207 lists 524 sources. Explicit stores retain original cache, error and video cleanup behavior; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

The media response port change uses the ordinary whole-release deployment and rollback. Authentication/permission/ownership checks still precede media responses, including output HEAD, Range and conditional GET. No migration, new retry or storage hot-swap is added. Selected response generations remain attached to their original runtime through transmission; a failing composition dependency must be repaired before serving that media path.

This offline HTTP artifact replay follows detection media candidate f2b4519 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 301b6c1. Manifest v208 lists 524 sources. Explicit missing file dependencies fail closed while genuinely omitted legacy arguments retain their documented default. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

The incoming storage capability change uses the existing whole-release rollout and rollback. It adds no remote cleanup job, migration, retry or resource disposal. Synthetic retention tests operate only on isolated test records and storage. Complete application construction and artifact lifecycle ownership remain separate acceptance work.

This offline incoming workflow replay follows HTTP artifact candidate 2336193 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 8e4d991. Manifest v209 lists 524 sources. Consistent captured files/images dependencies retain original partial-write, exception and retention semantics. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Background file ports preserve the original directory creation, default seeding, partial publication, manifest generation checks and enqueue order. No compensating deletion, automatic retry, storage hot-swap, migration or disposal is added. Whole-release rollout/rollback remains mandatory. Captured services and existing lazy response suppliers must belong to one consistently assembled resource graph.

This offline background file replay follows incoming candidate 841c4ba and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed c80ed68. Manifest v210 lists 525 sources, with the corrected service-relative background capability path. Captured file capabilities retain original ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Background image port injection retains the original local unreadable-image fallbacks and remote ArtifactUnavailable propagation, including existing partial variant publication. There is no retry, rollback of already-published variants, new paid call, training start or storage hot-swap. Root adapters must remain consistently assembled with background files; whole-release rollback remains unchanged.

This offline background image replay follows file candidate 89875c1 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 09ef623. Manifest v211 lists 525 sources. Three image services use explicit adapters; generator and runner defaults remain outside this slice. Original algorithms and golden contracts remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Background generation retains its original uncertainty and partial-publication boundaries: a nonzero remote generator exit preserves its log before failing; generation conflicts do not replay paid work or overwrite newer artifacts. Local subprocess behavior, including the existing timeout kill and partial output return, is unchanged. No paid calls occur in the synthetic acceptance tests. Captured resource graphs do not support storage hot-swap; whole-release rollback remains required.

This offline background generation replay follows image candidate 9a2d333 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 22986e9. Manifest v212 lists 525 sources. Generator and task runner now receive captured file adapters, retaining model snapshots, subprocess policy, partial outputs and exception behavior. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Training file capability injection retains existing local directory creation, per-file remote publication and partial output residue on failure. It adds no retry, compensating deletion, generation transaction or storage hot-swap. Assemble all callbacks and adapters consistently; deploy and roll back the complete release.

This offline training file replay follows generation candidate 2fdb9ee and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 214fe9c. Manifest v213 lists 526 sources, appending training/file_ports.py. Five services capture matching file capabilities while preserving validation, cache, write ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Training image capability injection retains unreadable-image returns, local directory creation, image write return-value handling and partial outputs on failure. It adds no automatic retry, compensation, generation transaction or storage hot-swap. Whole-release deployment and rollback remain required.

This offline training image replay follows file candidate 94c1eec and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 75d63a9. Manifest v214 lists 526 sources. Image adapters are captured and YAML selects its writer per call; arbitrary private rebinding is not preserved as an atomic hot swap. Algorithms, goldens and public signatures remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Explicit training resource storage preserves original partial deletion/publication and archive cleanup behavior. No production cleanup is performed by this refactor or its tests. It adds no cross-file transaction, automatic replay, migration or hot-swap guarantee; complete-release rollout and rollback remain required.

This offline training resource replay follows image candidate 9063ace and preserves current history, readiness, model/tail, shutdown, corrected boundary documentation and canonical LF guards. Production and test blobs match reviewed fbf5434. At this replay boundary manifest v215 selects 526 sources. Explicit resource and archive capabilities preserve file operation ordering, strict digest failures, partial publication and archive formats. Current source changes require actual-main rebind, independent review and full CI/release acceptance before publication.

Accessory file injection preserves authorization order, upload partial writes and legacy provenance fallbacks. No cleanup, retry, migration or storage hot-swap is introduced; file, hash and image capabilities must belong to one consistently assembled graph. Use whole-release rollout and rollback.

This offline accessory file replay follows training resource candidate 7ae44bf and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed eccc553, including ordered constructor bindings. At this replay boundary manifest v216 selects 526 sources. Upload ordering, partial publication, provenance collisions and sprite fallbacks remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

Accessory evidence capabilities must be assembled against one consistent file/image graph. Existing source fallback, metadata mutation and failure ordering remain; no store hot-swap, retry, compensation or migration is added. Deploy and roll back the complete release.

This offline accessory evidence replay follows file candidate b368404 and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed 466195b. At this replay boundary manifest v217 selects 526 sources. Decode and hashing selection, source mutation, partial publication and error propagation remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

Accessory catalog files and image readers must share the intended storage owner. Captured services and operation-time entry-wrapper selection do not promise atomic store replacement. Existing partial metadata mutation and image failure propagation are retained; use complete-release rollback.

This offline accessory catalog replay follows evidence candidate 2d442b2. All owned production/test blobs and the complete ordered entry match reviewed 87ebec1; current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v218 selects 526 sources. Existing catalog mutation and decoder behavior are unchanged. Exact-source neighbor evidence is reused; current targeted, assembled HTTP and fingerprint checks are distinct. Actual-main rebind and independent full CI/release acceptance remain required.

Candidate and gallery image dependencies must share the intended file owner. Gallery reads still publish previews; partial writes and False image-write handling remain compatible. Do not infer atomic graph replacement or compensating cleanup. Use whole-release rollback.

This offline accessory gallery replay follows catalog candidate 8f453b3. Owned source/test blobs and ordered entry match reviewed 7f02e9d, including the single inert ImageFiles allocation relocation. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v219 selects 526 sources. Existing partial publication and failed-write behavior are unchanged. Neighbor evidence is reused only for exact source; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Accessory upload/crop/delete keep existing partial-write and metadata effects. OSError deletion handling still differs from artifact-service errors; edits are not an atomic multi-file transaction. Storage injection must use a consistent owner and whole-release rollback.

This offline accessory edit replay follows gallery candidate 1b5c003. Owned source/test blobs and ordered entry match reviewed 6f78019. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v220 selects 526 sources. Authorization order, crop geometry, partial publication and deletion failure behavior remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Sprite preprocessing uses explicit media readers with the existing artifact writer. Failed reads, published sprites before later metadata errors and cache decisions retain original behavior. No atomic multi-artifact transaction or live graph replacement is introduced; use whole-release rollback.

This offline accessory preprocessing replay follows edit candidate 96c7b23. Owned source/test blobs and ordered entry match reviewed dbcd8b5. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v221 selects 526 sources. Discovery, decode, publication, status and exception ordering remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Agent source existence and bytes use explicit storage capabilities. Metadata digest callbacks may observe a separate read, so this does not add an immutable evidence snapshot. Keep dependency owners consistent and roll back complete releases.

This offline Agent reference replay follows accessory preprocessing candidate b1d835d. Owned source/test blobs and ordered entry match reviewed efa17b7. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v222 selects 527 sources. Reference selection, digest acceptance, path mutation and exception ordering are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Pose storage preserves partial publication: image bytes may survive digest/metadata errors, and materialized records may remain after a later sprite callback fails. No compensation/retry is added. Restore the complete release and retain artifact evidence.

This offline Agent pose storage replay follows reference candidate 9a90408. Owned source/test blobs and ordered entry match reviewed 11919d9. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v223 selects 527 sources. Image and metadata publication ordering, local/remote callback timing and partial mutations remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Photo-highlight image ports preserve partial diagnostic writes, existing swallowed ordinary errors and propagated artifact conflicts/unavailability. No atomic publication, replay or compensating cleanup is introduced. Restore a complete prior release on failure.

This offline Agent photo replay follows pose storage candidate a56b846. Owned source/test blobs and ordered entry match reviewed 6afd82e. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v224 selects 527 sources. Provider attempts, diagnostic failure handling, publication and item mutation order are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Pipeline background storage ports retain whole-set removal before variants and manifest publication, partial artifacts on failure, and original OSError/ValueError fallback boundaries. Artifact unavailability still propagates. No atomic multi-file transaction or automatic provider replay is added.

This offline Agent background replay follows photo candidate 5bcd15e. Owned source/test blobs and ordered entry match reviewed e8c63a3. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v225 selects 527 sources. Existing library fallback, partial file and manifest publication, callback timing and errors remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.
