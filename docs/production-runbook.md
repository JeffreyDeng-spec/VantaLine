# Production runbook

The current source manifest is v102 (278 entries). Per-domain notes describe which sources belong in the complete release; they do not identify when each module first appeared. Deploy and roll back only a complete release with its matching bundled manifest.

Pipeline AI task-card synchronization remains in the Web process. The v102 source manifest includes its new module and ports; deployment and whole-release rollback use the existing procedure.

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
modules with matching source manifest v102 as one complete release.

Preview submission preserves sequential partial completion: create directory, draw images,
write plan JSON, update user state, merge accessory changes, then save configuration. It does not
remove prior files or retry after a later failure. Missing clean object sprites return the existing
409; text fallback remains allowed. Jobs-root lookup occurs only when the plan is written, and the
store does not create a missing jobs directory. A false save return still returns the original plan.
Deploy/rollback the complete workflow package with matching source manifest v102.

Preview rendering retains original output failure semantics: a false return from image writing
still produces the existing URL response; a write exception prevents URL generation, and a URL
exception leaves an already-written file. No automatic retries or cleanup compensation are added.
Occluded labels remain in the preview with the original dropped flag and complete amodal box.
Deploy or restore the renderer and its ports with matching source manifest v102 together.

Preview placement still makes at most 180 candidate attempts and does not retry exceptions.
Overlap sums include repeated placed rectangles; failed searches keep the earliest minimum.
Successful metadata reports zero overlap, while failure reports the rounded minimum with its
original pass flag. Deploy or roll back all three layout modules and source manifest v102 together.

Background lookup keeps existing selection and default-seeding behavior; it is not a newly
pure read. An unreadable image returning None uses the synthetic fallback, while read/fit/augment
exceptions propagate without selecting another image or retrying. All successful/fallback paths
augment once and preserve the shared random stream. Deploy or restore both background modules
with matching source manifest v102 as a complete release.

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
source manifest v102; do not copy individual catalog files into production.

Archive export keeps the original replacement and cleanup sequence. Once a temporary bundle
is acquired, cleanup runs after export success or failure; cleanup failure can supersede an
earlier error. Already replaced export directories and completed writes are not rolled back.
Artifact import verifies the optional checksum before selecting the output directory, then
writes weights, copies the uploaded ZIP, writes library metadata and writes the response summary.
Later failures retain earlier files; no retry or compensating deletion is added. Deploy and
restore the complete package with matching source manifest v102.

RunPod orchestration preserves its existing failure boundaries: exceptions propagate to the
outer training runner and do not trigger an extra submission, GET retry, cancel or local fallback.
Completed artifact import and record writes can remain when a later summary/sync/warmup step
fails. The training polling deadline is checked before sleep; completion returned after that
wait can still be accepted. This extraction retains that training behavior and does not alter
label-detection timeout/late-response rules. Restore the complete package with manifest v102.

Dataset generation keeps its existing partial-failure behavior: already written images,
labels, annotation previews or YAML remain after a later step fails. An incomplete manifest
write can leave partial content. No retry, cleanup or transaction spanning files/config is
introduced. Error during asset normalization saves configuration only for HTTPException, and
save failure still supersedes that exception. Restore the complete release with its matching
v102 manifest; do not repair a rollout by copying individual generation files.

Training runner extraction preserves existing execution and failure handling. A process
exception is not retried, and errors after a process starts do not introduce a new terminate
or kill action. A later sync/warmup exception can still enter the existing failure settlement
after an earlier completed update; this structural batch does not redesign that behavior.
Submission failures retain prior saved records and thread-map entries according to the
original step order. Deploy/restore all matching modules and source manifest v102 together.

Training status propagation still saves account configuration before the pipeline record,
then updates the candidate state after releasing the pipeline lock. It does not add a
cross-store transaction: later failure may leave earlier writes and in-memory changes, as
before. Exceptions stop later steps; a false return value alone does not. Two-account tests
verify request identity isolation, not prevention of concurrent whole-config lost updates.
Ship/restore the matching v102 manifest and modules together; historical snapshots are retained.

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
runtime records and deploy both new modules with source manifest v102.

Training discovery extraction introduces no schema, connection, cache-policy or
process-topology change. Artifact discovery can still expose a task whose weight file
is absent; existing selection/loading performs its later checks. Finder snapshots
retain the existing partial-failure behavior and must be consumed on their creating
thread. Deploy and roll back the entire package, including the three new modules and
source manifest v102. Existing records and historical model snapshots are preserved.

Warmup remains the existing best-effort daemon-thread operation. Disabled runs only
update enabled/status/error; old detail fields remain. Setup errors can leave the
prior status, and formatter or BaseException failures may leave running status.
Prediction failures are recorded and remaining models continue. This extraction adds
no thread coordination or lifecycle idempotence; deploy/restore manifest v102 and all
components as one complete release.

Local model cache behavior remains process-local and unlocked during first load.
Same-ID hits still select/validate their specification; new IDs check file existence
before reusing a live instance at the resolved path. Removing an instance can leave
a path alias that still influences readiness, as before. This batch does not alter
warmup threads or restart behavior. Roll back the complete package with manifest v102.

Task projection/catalog extraction preserves current filtering and merge behavior,
including partial in-memory changes before an exception. It introduces no database
migration, cache policy or runtime topology change. Publish/restore both modules and
source manifest v102 with the entire immutable release.

Detection task storage extraction preserves cache invalidation and existing partial
failure behavior. JSON saves retain the fixed `.json.tmp` path and atomic replacement;
failed replacement leaves the old target and temporary file. This batch changes no
locks, cache policy, schema or worker topology. Recovery remains whole-release rollback.

Detection OCR extraction preserves synchronous local prediction, process-local
caching and original exception boundaries. A malformed batch result still triggers
the original per-image fallback; short valid batches are not padded or retried.
Single-image build errors remain outside its prediction catch. This structural
batch does not add initialization locking or change concurrency, topology or model
parameters. Deploy/rollback all OCR modules and manifest v102 as one complete release.

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
with matching manifest v102, retaining historical snapshots. This batch does not
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
