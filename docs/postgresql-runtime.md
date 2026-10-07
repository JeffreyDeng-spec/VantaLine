Codex comparison list and event-history repository SELECTs use short read transactions without the global advisory fence. Writes, claims, cancellation, report settlement and detail `get` retain the existing transaction lock. PostgreSQL committed visibility, decode rollback and reverse write-lock waits are required CI contracts. No schema or migration changes.

The first-page label legacy-record index is in-process only: it groups references from the already owner-filtered `records` JSON returned by the existing short read transaction. It creates no index, table, write or additional connection. Detail and cursor paths still use their old code; legacy assets/manual/Beta aggregation and full run JSON remain separate later work.

Label `list`, `runs_for_tasks` and `legacy` now use a dedicated short read transaction with commit on success, rollback on error and cursor close in `finally`, but no `label-inspection-v1` advisory lock. A reader concurrent with an uncommitted writer sees the last committed PostgreSQL version; a later request sees the committed update. The methods are not a shared snapshot across calls or native/legacy sources. `get`, `request_run`, `lookup` and `page` still use the write-lock transaction because they participate in write preconditions, model-snapshot reuse or snapshot creation/cleanup. All claims, expiries, edits, paid-call registration and other mutations retain the original lock.

The label task list now uses owner-scoped, parameterized `task_id = ANY(text[])` reads for at most 64 native tasks at a time. These reads use the unlocked short PostgreSQL read transaction; global claim and write fencing remain unchanged. Empty batches open no transaction. The old 15-minute page snapshot is still created/cleaned in its write transaction, and existing cursor pages read frozen items without reaggregation. Native run visibility during first-page assembly is now sampled once per batch instead of once per task; concurrent writes can therefore appear across batch boundaries just as they previously could across task boundaries. A first-page assembly across native batches and legacy/manual/Beta sources is not a database-wide consistent snapshot; only the persisted 15-minute page result is frozen. This batching pass still loads full run JSON; the subsequent v132 read-transaction change removes the global advisory lock from the three pure-list methods while leaving legacy/manual/Beta aggregation for later batches.

# PostgreSQL runtime operations

Profile-cache extraction retains its existing JSON cache store and adds no database connection,
transaction, schema or advisory-lock change. Cache file updates remain separate from caller-owned
task settlement and model-call accounting.

Retired task settlement uses the same update callback exactly once and preserves its failure
behavior and return-value handling. Retired refresh performs no persistence and returns the same
public projection object. The extraction adds no connection, transaction, advisory lock or schema;
updater selection occurs before timestamp evaluation as in the original call expression.

Retired worker request/status extraction adds no database access or connection state. Its public
request methods immediately reject and its status response is a fresh constant projection; all
existing task settlement and transaction ownership remains with callers.

Retired watcher extraction performs no task reads/writes from enabled, watch-once or startup
entry points and creates no database connection. The dormant loop receives a tick callback but
is not started. Connection, transaction and advisory-lock behavior remain unchanged.

Worker artifact extraction returns the same imported-path/error fields and does not persist the
training record itself. It adds no repository, connection, transaction or advisory-lock changes;
partial file writes remain separate from caller-owned task settlement.

Worker bundle extraction keeps initial, retry, completion and failed task-update ordering and
ignores false update return values as before. It adds no connection, transaction, schema or lock
behavior. File cleanup and progress finalization retain their separate failure boundaries.

Transfer progress retains the same task-update callback, shared state and periodic write order.
It adds no connection, transaction, schema, advisory-lock or request-identity behavior. Exceptions
from progress conversion/update remain swallowed; event waiting is outside that catch boundary.

Remote training extraction retains the existing task-update callback and its initial/final write
order. It adds no repository, schema, connection or advisory-lock change; archive cleanup remains
separate from database task persistence.

Background capture retains one task save followed by optimization-state save under the existing
shared lock. It keeps row-persistence interfaces, shared environment metadata and partial-write
ordering. This module move introduces no schema, transaction or advisory-lock optimization.

Background task services continue using the existing training record persistence interface and
filesystem background manifest. Model bindings remain frozen at task save and restored at run.
There is no database schema, transaction, connection lifecycle or advisory-lock change.

Background write services keep the existing filesystem assets and JSON manifest behavior.
They introduce no database schema, connection, advisory-lock or transaction change.

Background catalog helper extraction retains the existing filesystem manifest store and its
initialization writes during directory reads. It adds no database schema, migration or lock change
and does not classify all catalog calls as pure reads.

Task PATCH/DELETE adapters keep the existing training record save/delete services and locking.
The combined jobs list may retain its existing lifecycle refresh writes. Moving these routes does
not make the list a pure read or combine deletion and response projection into one transaction.

RunPod transfer task metadata still uses the existing training-task update path after final archive
replacement. Extracting the upload store does not combine filesystem and database operations into
a transaction, change locks, or retry failed metadata writes.

Training launch HTTP extraction changes no database transactions or locking. Existing enqueue and
user-state persistence remain sequential operations; status continues to use the projection whose
visible interrupted-task settlement may write through the existing lifecycle service.

Training state projection remains capable of settling interrupted visible tasks via the existing
training lifecycle write path. Moving it to `training/status_projection.py` does not remove write
locks or make all training GET operations pure reads; settlement errors still propagate.

Resource retirement markers keep the existing pipeline/training process guards and persistence
callbacks. Pipeline markers pass all loaded tasks plus the changed object references to the existing
batch helper; PostgreSQL still upserts changed rows. Training markers save matching tasks one at a
time. These are the same sequential writes, not a new transaction across filesystem, training and
pipeline records. A later failure leaves earlier writes intact; no compensating writes or retry is
added. Synthetic PostgreSQL contracts verify account isolation and preserved model snapshots.

Training state synchronization now uses explicit storage ports but keeps the existing
configuration, pipeline and candidate persistence functions and write-lock behavior. No SQL,
DDL, connection lifecycle or transaction scope changes here. Completion synchronization is
still sequential across those stores; this extraction does not make their writes atomic
as a unit. Read-lock removal remains a separate performance change.

Training deletion obtains its repository inside the existing shared training guard,
after authorization, stop processing and in-memory deletion markers. Valid SQL rows
invalidate the training lookup cache before primary-key deletion. Active local tasks
keep a persisted stopped marker instead. Late updates with a marker ignore new values
and return a copy of the current stored record when truthy, otherwise the marker.
The extracted delete source gate verifies its actual entry and authorized root forward;
SQL, transaction boundaries and advisory-lock behavior remain unchanged.

Pipeline task/state stores retain five and three actual repository selections,
respectively. Single task load uses the primary key; bulk save replaces valid rows;
single save upserts only after freezing and encoding. State partial-key saves encode
outside the try block, upsert each changed row with commit=False, then commit once.
Exception failures inside that block call rollback when callable and re-raise;
BaseException and encoding failures keep their original boundaries. The update guard
covers load, JSON copy, mutation, normalization, changed-key detection and persistence.
Raw partial saves do not acquire this guard. SQL and advisory-lock scopes are unchanged.

`TrainingRecordStore` retains three real repository entry points for list, save and
single read. Nested JSON-list reads and find fallbacks reselect the current repository
at the original call sites. Save freezes model references and invalidates the read
cache before entering the existing shared reentrant training guard; repository
selection, row encoding and upsert remain inside it. Invalid SQL rows still skip the
write after those steps. No read/write SQL or advisory-lock behavior changes here.

The extracted training finder selects the current thread repository once when the
finder is created and fetches `training_tasks` lazily on first lookup. Its closure
is an operation snapshot for that same thread, not a shareable repository or global
connection. Shared cache invalidation does not mutate an existing finder snapshot.
A failed fetch leaves empty local pairs; partial decode or cache-write failure leaves
the accumulated pairs. The same finder does not automatically repeat those operations.
Factory/query errors never fall back to JSON; JSON returns the current loader object.
SQL, transaction scope and advisory locks are unchanged in this structural batch.

Detection task persistence now obtains the current thread repository inside each
of its three original storage entry points. JSON single-task writes retain the
nested load/save factory selections; SQL single writes still upsert and full saves
still replace all valid rows. Invalid single rows are skipped after cache invalidation
and directory creation; a fully invalid bulk save still replaces with an empty set.
Factory/query errors propagate without JSON fallback. Existing locks, SQL and schema
are unchanged; read-lock optimization belongs to a later batch.
Row decoding and background callback getters resolve at the original expressions:
after preceding work and before fetch/string/mapping argument effects. Missing
callbacks preserve argument evaluation and TypeError. The bundled source manifest covers
the three task modules; no retry, cache policy or transaction change is introduced.


Legacy incoming catalog, review/list and retention workflows obtain the current
thread repository through `IncomingWrites.repository` at each original entry point.
Activation retains draft-save then repository activation then task publication;
review retains the repository's atomic decision/audit operation. JSON alternatives
keep the shared reentrant guard and their original file-write order. No SQL, lock,
index or migration changes accompany this extraction.

Incoming-text persistence uses seven lazy repository entries in the extracted store.
Reference and inspection writes validate their row before selecting a repository;
audit selects it first and serializes only on PostgreSQL. SQL single reads remain
primary-key reads, and a repository error never falls back to JSON. Existing unique
constraints, transaction locks and raw-record formats remain; no schema change is
introduced. JSON single reads still make the original second selection in their list
method, so the service does not cache the repository choice.

Standard edit services obtain their thread repository lazily for add, patch and
confirm. Existing repository transactions, advisory locks and JSON authoritative
rereads remain unchanged; the source gate follows the actual three service entries.
This extraction adds no database optimization, migration or connection cache.

Text-record persistence now lives in `text_inspection.record_store`. The existing
repository factory is called inside each operation, including nested JSON CAS
operations; no connection is cached by this service. Only records/OCR evidence use
indexed owned lookup, while other kinds retain their existing list/filter path.
JSON insert-only checks and normal upserts retain distinct semantics. Repository
errors do not fall back to JSON. Existing transaction/advisory locks are unchanged.
Unknown read/write outcomes propagate once without a new retry policy. JSON save
holds the shared lock through duplicate checks, copy and write; compare-and-set holds
it through the status check and nested save. Neither sequence is split into separate
lock regions by this extraction.

Candidate repository extraction retains existing transaction and lock placement.
Load may repair and upsert legacy job metadata; GET holds the original outer RLock
through authorization, refresh and final save. PG listing remains ordered by
updated/created/id while JSON listing uses file time. No read unlock or schema
optimization is included. A denied GET can retain its earlier load-time repair.

Accessory row persistence now lives in `accessories.repository` behind a lazy
runtime-repository factory and the existing configuration lock. JSON fallbacks,
row-ID normalization, raw payloads and fetch/delete transaction behavior are
unchanged. No new indexes, tables or unlocked reads are introduced by this batch.

`auth.users` uses narrow persistence ports and the original repository RLock for
session-revocation/user-deletion ordering. Password revocation, last-admin checks
and user saving retain their prior separate operations. This extraction does not
make bootstrap or password changes a new atomic database transaction.

Indexed request authentication now enters `auth.sessions.SessionService` and still
uses `authenticate_session` on the thread-owned repository. An invalid cookie with
existing users returns an authentication sentinel without full-table fallback;
only an empty user store falls back to bootstrap. JSONB inactive users and mismatched
session/user identities remain denied. No query or transaction optimization occurs.

`auth.repository` owns user/session persistence with injected thread-owned
repositories and the existing reentrant write lock. Raw and hashed session-key
candidates, expiry cutoff and account-scoped revocation remain compatible. Login
revocation and insertion retain their prior separate database operations; this
extraction does not claim a new atomic transaction or alter advisory locks.

`analytics.analysis_publication` uses the same injected repository and lock as
analysis CRUD. Image-processing read/merge/save retains the existing local lock;
detection publication still saves first and only then requests auto-optimize
capture. A capture failure leaves the saved record and is not automatically
retried by this service. No transaction or advisory-lock optimization is included.

`analytics.analysis_repository` owns analysis-record SQL/JSON selection through
an injected thread-owned runtime repository factory. Replace-all, row upsert,
lookup and deletion retain their existing transactions and local lock placement.
This migration introduces no schema/index, unlocked reads or changed pagination.
Authorization and deletion keep their prior separate read/write sequence; this
phase does not claim to close that pre-existing race window.

Repository connection selection now lives in `runtime/connections.py`. Web and
worker callers continue using the same factory/clear interfaces: each execution
thread owns its connection, reset advances a generation, and other threads evict
their stale selection on next use. A closed connection is rebuilt. Explicit release
scopes must open and close on the execution thread, including exception paths.
This extraction changes no SQL, advisory-lock scope, pagination snapshot or schema.

**Status: Authoritative**

Document review uses existing asset status and JSONB fields; no migration is
needed. `review` transitions to `needs_confirmation` under the standard advisory
lock and revision check, preserving `original_classification` in raw_json. On an
enabled order it creates a new immutable membership snapshot excluding that
asset. Draft confirmation rejects pending assets within the same transaction.
Document job claims/results and tombstones use `mutate_text_document` with the
same advisory lock as human edits. Only changed rows are updated. Compatible
JSONB job/attempt/deletion fields require no new table; snapshots stay immutable.

PostgreSQL is the production shared runtime store. Historical JSON-to-PostgreSQL preparation packets are migration evidence and must not be used to switch production back to JSON.

## Additive label-inspection objects

`2026_09_15_label_inspection.sql` adds `label_inspection_objects` through the normal
immutable-release migration installer. The shared runtime repository owns its
connection. Object kinds are task, immutable revision, run, paid call, and edit
receipt, plus short-lived owner-scoped pagination snapshots. Snapshot cursors
keep cross-source traversal stable while tasks receive new activity; expired page
objects are pruned after 15 minutes without touching historical records.
Owner/kind/idempotency-key uniqueness and a global transaction advisory
lock serialize submissions and claims; queue indexes support global concurrency two.
Runs freeze source hashes and prompt/model versions. Call evidence is inserted
before provider I/O. There is no automatic retry of a claimed or unknown paid stage.
A worker timeout expires the run without publishing a late result. Old text/Beta
tables are compatibility-read only; continuation adds new objects and media.

No destructive migration, old-record backfill or content-similarity deduplication
is required. Backups must include the database and `label_inspection/media` under
the existing runtime DATA_DIR. Diagnostic bodies may contain label text and remain
account-private. Raw binary/image files never belong in the source release.


## Ownership and compatibility

Comparison history uses the existing owner/created_at index and a bounded SQL
summary projection with stable created_at/id cursor ordering. It accepts raw_json
objects and historical JSON-encoded strings. Display snapshots are additive JSONB
fields on new records only; existing records/images are not migrated or copied.
Historical standard media resolves immutable revision evidence. Missing snapshots
remain explicit. Current name lookups are display-only and labelled as such.

Local OCR rereads reuse the OCR evidence table with owner/source/input hash,
mode, pinned model and preprocessing version in the cache key. Each input gets
an insert-once claim before its paid call; only completed results are reusable.
Unknown claims survive restart and are never automatically resent. Per-comparison
diagnostics link owned, hash-verified input media; API responses omit disk paths.
No schema change or historical evidence rewrite is required.

`2026_09_12_text_ocr_evidence.sql` adds account-owned OCR claims/cache. Deterministic
IDs bind owner, source hash, pinned model and preprocessing version. Insert-once
precedes external OCR; only completed results are reusable. Unknown or interrupted
claims are retained. `update_text_attempt` uses owner/status predicates for both
cache and comparison records, preventing late completion after terminal settlement.
Legacy record raw_json encoding is preserved; cache raw_json is a JSONB object.
No old table or customer evidence is rewritten; previous releases ignore this table.

Standard preparation adds asset/standard JSONB fields, not new tables. Attempts
are claimed under the standard advisory lock before paid I/O. Immutable preparation
revisions contain the source hash, elements, cleaning evidence, and derivative hash.
`mutate_text_document(..., revision_action='prepare')` publishes the active pointer
and an append-only standard snapshot in the same transaction. Legacy source SHA
fields retain their meaning; `preparation`/`reference_sha256` identify the effective
reference. New unprepared assets cannot enter a managed snapshot. Previous active
snapshots stay usable until their replacements are ready. Records bind the exact
preparation revision; no original, historical evidence or old revision is overwritten.

The `supplementing` phase stores the successful VLM response, original observations,
and each local region's claim before OCR. Region results/coordinates/media hashes
live in additive attempt diagnostics. An interrupted phase never replays the paid
call; late completion cannot publish or replace manual edits. No new table is needed.

Public/workspace path separation requires no schema or data migration. Task
identities and account-scoped preferences remain unchanged; only generated
browser URLs gain `/workspace`. The deployed PostgreSQL acceptance runner checks
the admin-doc boundary at `/api/docs` (Swagger), not the now-public `/docs` user
guide. Existing API/data-store and media-isolation checks remain unchanged.

- Runtime repositories own database access; API/business code must not introduce ad-hoc direct connections.
- Migrations are additive and expand-first. The new schema must remain readable by the previous release during deployment and rollback.
- Dropping, renaming, narrowing, or repurposing fields requires a separately reviewed multi-release contract phase.
- Database credentials are supplied through restricted runtime configuration; they never appear in Git, logs, fixtures, or documentation.

## Change procedure

`2026_09_06_text_label_extractions.sql` adds an independent account-owned extraction table. Task claim IDs are deterministic from account/request identity; edit and confirmation IDs are deterministic from root/version, and insert-once is the concurrency arbiter. Only the original task is updated by its single worker; edit and confirmation rows are immutable. Expiration appends a competing revision and retains tombstones, while any confirmed or comparison-referenced root is excluded from media cleanup. The previous release ignores this additive table.

Extraction `raw_json` is passed to the repository as an object so PostgreSQL stores a JSONB object, not a twice-encoded JSON string. Account/root-scoped queries use the indexed `root_id` inside that object. Existing tables retain their representation for compatibility.

1. Update repository/schema code and migration safety expectations in one PR.
2. Run migration safety, repository smoke, and real PostgreSQL 16 schema validation.
3. Document data ownership, compatibility window, observability, and whole-release rollback.
4. Let the immutable release installer apply only approved compatible migrations.

`2026_08_29_text_inspection_v2.sql` is expand-only. It adds six independent `text_inspection_*` tables and does not rename, rewrite or drop the previous `incoming_text_*` tables. Data deletion or copying is never part of automatic deployment and requires a separately authorized, restartable operational run with restore evidence.

Text-inspection library edits preserve the same expand-first boundary. The standard row is the current logical-order pointer, while `text_inspection_standard_revisions` is the append-only history. Initial confirmation and every later add, remove or restore on a confirmed standard advance the revision number and insert the complete selected-asset snapshot under the account-and-standard advisory lock. Soft deletion updates current membership but must not physically remove media referenced by a prior revision or inspection record. Each new inspection stores the revision ID, revision number and reference hash. Repository smoke must exercise concurrent revision checks, add/delete/confirm ordering, an empty-draft confirmation failure, and continued reads of historical snapshot data on PostgreSQL as well as the JSON fallback.
5. Verify service health and data behavior after deployment; do not switch to a legacy JSON runtime as an ad-hoc rollback.

Backups and destructive retention actions require separate operational authorization and restore evidence. See [Production runbook](production-runbook.md).

## Agent operation foundation

`2026_09_11_agent_operations.sql` adds `agent_policies`, `agent_operations`,
`agent_operation_attempts` and `agent_operation_audit`. Admission and reservation
share an account advisory lock and transaction; `(owner_user_id, idempotency_key)`
is unique. A changed parameter hash conflicts. Unknown outcomes keep reservations
and cannot be re-claimed. Audit writes are append-only through the repository.
These primitives are not yet connected to production business submission or
provider settlement. Previous releases ignore the new tables; retain them on
rollback. Real PostgreSQL concurrency tests and current limitations are recorded
in [Agent platform implementation status](agent-platform.md).

## Codex comparison storage

`2026_09_14_codex_comparisons.sql` adds tasks and append-only events. Owner/request
uniqueness and a global advisory transaction lock enforce idempotency and one
active claim across workers. Report projection plus event revision are atomic.
Stale active attempts are interrupted, never replayed; late writes fail. The
previous release ignores the new tables. Preserve them and source-hash media
during rollback. See [Codex beta](codex-text-compare.md).

Codex label-v2 cards extend the existing comparison task/event JSONB projections
with report_version, elements, checks, issues and decoder evidence; no destructive
migration or new database permission is required. Checklist updates only append
new IDs and cannot remove pending work or reset recorded results. Geometry,
references, coverage, idempotency and attempt revocation are validated within the
existing serialized transaction. Missing report_version identifies historical v1.

Batch-v3 uses the same additive JSONB task/event tables and advisory lock. Draft
status is never claimed. Draft file writes and submission have request fingerprints;
queued input cannot change. labels/references are nested per-batch projections with
immutable actual IDs after submission, independent review histories and append-only
revisions. Child cards do not have queue rows or their own sessions. The worker
credential is still task/attempt-scoped, and validates label scope on every write.
No DDL or database role expansion is required. Drain all v3 queue rows before
rolling back to workers without the batch contract.

## Label quality snapshots

New run raw_json adds `quality.policy` at submission; the worker appends preflight
and selected diagnostics with normalized bounds, scalar/block metrics and timings.
Quality refusal adds `error_code=QUALITY_*` and retains failed/REVIEW_REQUIRED.
No migration, new connection, old-row backfill or historical reinterpretation is
needed. Request identity remains based on user intent, so an identical request ID
returns the original policy snapshot even across releases. New retries get fresh
policy snapshots and retain parent_id. Quality evidence shares existing owner
isolation and backups; no raw quality media enters application logs or Git.

## Model configuration registry

`2026_09_16_model_profiles.sql` adds `model_profile_objects`. JSONB rows hold
append-only profile versions, audit/usage events, per-version connection-test
status and one binding state with optimistic revision. An advisory transaction
lock serializes migration and writes across processes. Keys/proxy credentials
are stored only in restricted server secret storage; metadata stores references.
The registry requires PostgreSQL and has no JSON runtime fallback. Initial
migration is idempotent; original settings and immutable secret versions remain
for complete-release rollback. Never remove a secret used by unfinished work.


## Unified PDF inspection

PDF task JSON extends label_inspection_objects with source pdf, import manifest/checkpoints/lease, and import_queued/import_running/import_failed states. No DDL migration. One advisory-lock-protected importer owns a token with a 300s renewed lease; stale tokens cannot checkpoint or publish. Revision 1 is inserted atomically only after all pages render. Existing runs freeze pdf-page-v1 or label strategy. Old manual standards/sessions/pages/records are owner-scoped read-only projections.


## Agent policy read transaction

Agent policy display reads use a short PostgreSQL transaction without the per-account advisory lock. A concurrent write can leave a read seeing the preceding committed version; the next read sees the new committed version. `set_policy`, admission, reservation and operation transitions still acquire the per-account advisory transaction lock and read/check/write inside that transaction. No schema or migration is needed.


## Fixed-reference model read transaction

The model-profile repository now has a short read transaction for already-determined profile versions and the usage-call list. It performs no advisory lock acquisition; each PostgreSQL statement reads committed data, so the immutable profile and mutable test status are not promised as a shared fixed snapshot. Cold initialization migration, version/binding writes, connection-test registration and call writes retain the global model-profile advisory transaction lock. Task snapshots and admin display reads use short read transactions as described below. No DDL is changed.


## Model registry initialization fast path

For model-profile initialization, an already committed truthy `state` row is read in a short transaction without the global advisory lock. Missing or falsey state ends that read transaction and takes the existing advisory write transaction, where state is read again before migration. Migration profile/version inserts, initial snapshot, audit and secret calls stay in their previous locked sequence. No schema migration or process-local initialized cache is introduced.

## Model task snapshot read transactions

Task snapshot reads use the existing `model_profiles.Repository.read_tx()` lifecycle: commit on success, rollback on exception, and cursor close in all cases, without the global model-profile advisory lock. The first state read in `snapshot_for_record()` closes before its nonhistorical fallback calls `snapshot()`; model-profile writes and cold initialization still use the advisory write transaction.

## Model admin public read transaction

The administrator model-profile projection now uses `Repository.read_tx()`: commit on success, rollback on failure, and cursor close in all cases. It does not acquire the global model-profile advisory lock. Its state revision/heads are captured together, but mutable connection-test rows may be observed at different committed statement times. This is not a fixed database-wide snapshot.

## Label list-only run payloads

A dedicated owner-scoped `list_run_payloads_for_tasks` query keeps the existing 64-ID bound, SQL task grouping and short read transaction. For object JSON carrying `kind=run`, PostgreSQL removes five fields later discarded by the API run projection; other JSON shapes pass through unchanged. It reads all run rows and retains SQL column ordering only as the input to the existing per-task JSON-time sort. There is no schema or index change; writes and claims keep the advisory transaction lock.


## File location index

`2026_10_04_artifact_locations.sql` is an idempotent expand migration.
`vantaline.artifact_locations` retains logical path, generation, object key, size,
SHA-256, ready/deleted state and creation time. The composite primary key and
per-path transaction advisory lock implement compare-and-swap publication. Reads
and writes own short separate connections; no business transaction is borrowed.
Rollback retains this additive table and every prior generation. The initial
index importer rejects a differing existing path and re-verifies remote contents
before publishing missing rows. It does not overwrite newer business writes.

The additive artifact_locations index retains mtime_ns alongside immutable object identity and generation. Historical manifest imports preserve source time; new publications use database clock time. No original business table or legacy reference is rewritten by this expansion. JSON file mutations bind to the generation read, so a later concurrent version rejects publication.


## Label runtime state preparation

The additive `2026_10_04_label_runtime_state` migration creates an empty operational-state table with a text primary key, bigint update time and JSONB payload. It seeds no admission or worker state and changes no existing table, row, lock or runtime query. Generated PostgreSQL/SQLite schemas and the repository table/key registry include the same shape. A later release will define and use the runtime control protocol; this migration alone does not change label execution.


## Managed embedded label control

`LabelRuntimeStore` persists the current build/mode, optional configuration revision, maintenance/paused intent and control revision in the already-added operational table. All control writes take the existing label advisory transaction lock. A managed submission checks maintenance inside its original submit transaction after acknowledged-idempotency lookup, and a managed claim checks the paused/build fence before expiration and task selection. Thus maintenance acknowledgement cannot race a later new enqueue; existing acknowledged requests remain readable. Maintenance permits the queued work to drain. Pause prevents further claims without requeueing or rewriting calls. State/queue probes use short reads; malformed/missing state and mismatched generations fail closed. The global concurrency limit remains two.

The control endpoint owns a dedicated PostgreSQL connection factory with explicit connect/TCP failure-detection settings; request and paid-task connections retain their configuration. SQL timeouts apply after connection, and the root client has a separate bounded acknowledgement deadline; these do not constitute a hard total deadline for every driver operation. A control-thread shutdown timeout retains its role lock and fails that controller generation until process restart. Regression probes block connection creation and verify no duplicate role, then release the old thread for cleanup. A real claim/processing-substitute/cleanup integration proves pause does not acknowledge drain until two admitted iterations finish, while queued task snapshots remain unchanged.

## Proposal: shared label runtime configuration preparation

The preceding embedded configuration bridge introduced a bounded data-only snapshot of the existing label/database/storage/network settings, exact existing model-secret environment references and data directory. Unset and explicit empty values remain distinct. COS credentials are represented by their byte digest and transferred only through a private root-authenticated path; a worker must receive its own systemd credential directory. The pure contract and private-file roundtrip tests use synthetic values. The candidate Web wiring can capture a configuration revision and export its immutable snapshot only through the private authenticated control socket; public status contains only the revision. A prepared root file publisher writes immutable private versions and restores one atomic current pointer. The installed helper now embeds the audited data-only contract, captures a peer/build/instance-bound private export before external transitions, and journals the previous configuration pointer before mutation. It restores that pointer with the complete release on rollback, derives escaped mount dependencies and provisions the worker own systemd credential from root-owned bytes. No candidate application module is imported by the isolated root helper. Tests cover pointer interruption, export tampering, private modes, standalone execution and synthetic installer recovery. That bridge release retained embedded execution. Its complete-release acceptance is a prerequisite for the external activation described below.

## Proposal: standalone label process

The candidate `label_inspection.runtime` bootstrap reads the root-owned immutable configuration and its own systemd credential, checks the active package build/topology, initializes local storage, and creates separate thread-owned business and control repository factories. It imports no Web application. The existing model service is reused through an existing-registry reader: missing registration fails startup rather than migrating legacy settings. Secret-file syntax, environment precedence, immutable version references and usage accounting remain unchanged. Manifest v141 names 366 actual sources; historic snapshots are not rewritten.

In external mode, Web composition owns admission/control only and constructs no label consumer. The standalone process owns the existing two-thread consumer and its exclusive role socket; SIGTERM/SIGINT stop new work and use the existing 480-second drain budget. Real isolated PostgreSQL tests cover old-model resolution after settings changes and reader recreation, actual child PID/peer checks, duplicate-role rejection, signal drain and controller-driven embedded-to-external acceptance, failure and complete rollback. Synthetic model values and local storage are used; no paid inference or PLC call occurs. The bootstrap-only predecessor did not enable an external release. External activation remains conditional on preceding complete-release acceptance and final exact-build validation as described below.

## Proposal: label runtime monitoring

Managed processes publish bounded heartbeats on the existing private control thread with a five-second target interval after the previous tick completes. Database work and control requests can delay a tick. Each uses the dedicated thread-owned connection factory. The operational table stores only build/configuration/process identity, worker state, process-lifetime counters and fixed recent-error codes. A blocked heartbeat retains the same role lock on shutdown timeout. The private deployment protocol remains unchanged.

`GET /api/label-inspection/runtime` requires administrator access before any database call. Its short unlocked READ COMMITTED transaction samples state, queue and heartbeat in separate statements; these are not an atomic health snapshot. It returns queue/active counts, oldest queue age, maintenance/pause intent and expected-role heartbeats; missing, mismatched or older-than-15-second samples are unhealthy. Heartbeat freshness is sampled liveness, not a guarantee against a subsequent crash. Lock acquisition counts/total/max wait include successful and timed-out acquisition attempts. These and rejected duplicate submission/stage-call counters belong to the process lifetime: process restart resets them, while a control restart within the same process changes the instance but retains counters. Idempotent replay is not counted as rejection. Errors never include exception strings, media, customer fields, secrets or filesystem paths. Real PostgreSQL/HTTP tests cover authorization, redaction, actual lock contention, duplicate refusals, stale generations and heartbeat shutdown. Manifest v142 names 367 actual sources. The observability-only predecessor retained embedded execution; the external activation below is a separate release and requires acceptance of every predecessor.

## External label process connections

External label activation introduces no migration or backfill. Web and the standalone
consumer each own separate thread-bound business and control connection factories.
Existing claim/stage-call writes retain their coordination locks, and operational
reads remain short unlocked sampled transactions. Keep runtime state, heartbeat,
task/call evidence and configuration/secret versions through whole-release rollback.

Label detail reads return the last committed task/run while a writer is in progress. Owner/kind predicates and connection cleanup are unchanged. Submission, task editing, expiry, claim, stage calls, page snapshot writes and bound-request lookup retain their original advisory transactions.

PLC domain modules receive existing repository and atomic mutation capabilities. The extraction does not change transaction scopes, advisory fences, SQL, migration versions or PostgreSQL-versus-JSON authority. Synthetic store probes supplement the existing real-PostgreSQL CI contracts; they do not replace concurrency evidence.

Auto-optimization state storage is supplied its existing runtime repository, account and clock capabilities. PostgreSQL stays authoritative when selected, without JSON fallback on database failure. Transaction scopes, locking, key selection and rollback behavior are unchanged; the real PostgreSQL state-store contract remains in CI.

Pipeline workflow extraction uses the existing task stores and atomic operations through explicit interfaces. It does not change SQL, account filters, transactions or lock ownership. Focused synthetic probes supplement the existing real PostgreSQL contracts rather than replacing them.

Accessory image workflows keep current repository authority, transactions and lock ownership. A non-None PostgreSQL repository, including a falsey test double, remains authoritative; database errors do not silently select JSON. Artifact deletion and process side effects retain their original nontransactional behavior.

Application configuration and accessory rows continue to commit in the same protected-key replacement transaction. A non-None PostgreSQL repository is authoritative, including falsey doubles, and failures never choose JSON fallback. The real PostgreSQL config test observes commit and injected post-write rollback using a second connection. No SQL, schema or lock scope changes are included.

## Derived label summary state preparation

`2026_10_04_label_run_projection` adds an empty `label_run_projection` side table
(id primary key, projection version and JSONB). Business rows, historical model
snapshots, HTTP reads and advisory-lock scopes are unchanged. There is no
backfill, application cache publisher or cache reader in this preparation.
The generated PostgreSQL schema and incremental migration install the same
row trigger. Every source INSERT, UPDATE and DELETE invalidates the affected
projection IDs atomically, including both IDs on rename and ordinary COPY/upsert.
It runs AFTER row changes so it uses the final NEW identity. Transaction or
savepoint rollback restores the prior projection; same-ID replacement invalidates
it. TRUNCATE can leave unused orphan projections, but new INSERTs invalidate
those IDs and a future reader must always join through the authoritative source.

The trigger uses a fixed schema-qualified target, `search_path=pg_catalog`, and
checks its exact source schema/table, timing and row level. Its narrow SECURITY
DEFINER permission allows old source-only writers to invalidate derived rows
without cache-table grants. It never updates source rows or evaluates dynamic
SQL. The generic runtime upsert registry intentionally omits the derived table;
a future publisher must lock the source first, validate the row returned under
that lock, and publish the projection before the same transaction releases it.
No absent-row, pre-lock or asynchronous proof may be published. A future reader
must use one source/cache join snapshot and fall back on an unknown version.

Only the exact complete audited migration generated by `label_summary_schema.py`
is exempted from the general destructive-SQL pattern check. Mutating, wrapping or
appending SQL to that migration does not retain the exception. Other migrations
retain the existing guard. Reapplying identical SQL preserves cache rows and the
single ledger entry. A five-second lock timeout aborts migration atomically if
the short source-table DDL lock cannot be obtained.

The isolated generated-schema and import validators use complete multiline single-user SQL input, including PL/pgSQL bodies. They do not split SQL on semicolons. The schema validator checks trigger presence and rejects database error output; this validation change does not alter generated or deployed migration SQL.

## Post-settlement projection transaction

The optional publisher requires an idle, non-autocommit thread-owned connection.
It owns one new transaction, selects a single owned terminal source row with
`FOR UPDATE SKIP LOCKED`, validates its actual stored trimmed JSON, and upserts
derived state while holding the source row lock through commit. Lock order is
source then cache. It obtains no global label advisory lock and does not change
`LabelRepository.put`, claims, call registration or business settlement. The
existing source trigger invalidates its proof when any old/new writer changes
that source. A cache error rolls back only this separate transaction.

A concurrent write to this same source can wait for the short projection lock;
other run claims can proceed unless a separate writer holds the global fence.
100 ms lock/500 ms SQL statement timeouts and a 256 KiB payload bound reduce this
exposure but are not an end-to-end network deadline. Projection version 1 admits
only validated ID/time/optional status/decision fields. The complete trimmed
payload is parsed (including unknown fields and `import`), with at most 512
integer digits, finite floats and depth 64; unsafe shapes remain uncached.
Any future change to this proof, public projection semantics or consumed list
fields requires a new projection version and fallback tests. Historical source
records are neither rewritten nor scanned for backfill.

## Cached list read transaction

A single source-driven LEFT JOIN reads source/cache under one PostgreSQL statement snapshot. Source SQL owner/kind/task filters and creation/id order are unchanged; a committed old-writer update invalidates the projection atomically and forces fallback. An uncommitted source/cache change exposes the old consistent committed view. Ordinary cache reads use the existing short read transaction, with no advisory or row lock and no cache write. Page creation/cleanup and all mutations still use the write fence. Orphan cache entries never produce rows. Do not disable the invalidation trigger or manually repopulate derived state.

Before enabling the joined list reader, Web startup probes all referenced source and projection columns on its actual effective database session with LIMIT 0. The transaction is explicitly read-only with local SQL/lock limits; both success and failure roll back and release the thread-owned connection. A non-idle/autocommit session is rejected, not committed. This checks current schema and SELECT privileges, including column grants; it does not prove future grants, row-level security equivalence, trigger integrity after administrative changes, or cache population.

Cache ownership extraction does not alter repository queries, connection lifetime, advisory locks or transactions. Store caches keep their existing process-local invalidation and TTL for external writes. No database connection or request identity is captured by a cache instance.

FileDigest now owns the existing streamed file SHA-256 helper in storage/artifacts/files.py. Its injected byte-stream reader still selects the same artifact backend; hashing retains 1 MiB reads, stream cleanup and OSError-to-None behavior. This relocation adds no SQL, schema, connection, transaction or advisory-lock change. Existing PostgreSQL artifact CAS and connection lifecycle contracts remain required.

Repository selection and administrative row-count projection moved to runtime/repository_access.py. The factory still acquires/releases connections per execution thread; the new service holds no connection. There is no SQL, advisory-lock, transaction, migration or fallback policy change. Failed count probes retain existing HTTP redaction; malformed count results and fingerprint errors preserve their original uncaught boundaries.

Protected namespace ownership is structural: mutate_app_config_namespace still acquires its existing transaction-scoped advisory lock, reads/mutates/writes protected rows and commits before a fresh configuration load. That load may see a later committed writer; a reload failure after successful commit does not undo or replay it. save_app_config continues to omit accessory-table replacement. No SQL, transaction, write-lock or isolation policy changes.

The native list statistics reader uses one unlocked statement per 64-task batch.
Window counts and row selection share one authoritative source/cache view; the
proof-version CASE guards casts even on fallback groups. Missing/unknown proofs
return the previous ordered payloads, not partial counts. Aggregate eligibility is
explicitly restricted to IDs without mixed legacy history. It introduces no new
table, index, write lock or cache repair, and leaves all write transactions intact.

History payload projection occurs after the source-ordered selection subquery.
The OFFSET 0 boundary prevents PostgreSQL from flattening that projection into
the sort; the outer ORDER BY still explicitly specifies returned source order.
This avoids sorting constructed wide fallback JSON in the observed PostgreSQL 16
plan. It does not remove window work or promise a fixed plan on every server.
Unknown-version proofs still cannot reach the guarded timestamp cast, and partial
or excluded histories still return all previous payloads from the same snapshot.

History result decoding now reuses column names only within one fetched result
set. It obtains metadata lazily for the first non-mapping row, preserving empty
results and mapping-row behavior; the generic repository decoder still accepts
all existing callers without supplied columns. Duplicate-column overwrite,
shallow mapping copies and decode-failure rollback/close remain unchanged. This
removes repeated psycopg Column construction without changing SQL, transactions,
query counts, source ordering or proof eligibility. The real PostgreSQL history
smoke verifies one metadata access across a wide mixed-result batch and retains
the original sentinel decode-failure check.

Column-name reuse assumes the stable metadata of one psycopg result set. A private decoder override that avoids metadata, or a nonstandard cursor that changes columns between rows, is outside this optimization contract. Default decoder callers retain the original list-based metadata construction.

The native history reader combines a same-statement current-proof gate with result-local column-name reuse. A batch with no current owned proof uses the ordered fallback branch without history windows; proven batches retain guarded count/latest aggregation. The gate and both source branches use the original typed owner comparison rather than converting the owner parameter to text. This is a new candidate combining two previously separately measured mechanisms, not a retry or acceptance of earlier failed candidates. Both fixed performance protocols and their original latency, memory and query limits remain mandatory; no universal speedup is claimed.

Native list-history fallback now compacts a nonempty `quality` object only when every immediate value is a JSON string, boolean or null. This matches the existing public checked marker while avoiding unnecessary evidence transfer. Numeric and nested values stay intact so JSON decoding errors remain visible; other fields, ordering, detail payloads and old snapshots are unchanged. PostgreSQL/HTTP regressions cover flat Unicode/string/bool/null, empty and other shapes, and bounded-decoder failures. The original complete performance protocols and thresholds remain mandatory; private diagnostics are not acceptance.

Authentication composition holds only the thread repository factory, never its returned connection. Repository and session services invoke that factory at their existing operation points, with unchanged SQL and transaction boundaries. Preserve account/session isolation, exception cleanup and connection rebuild checks; the local reentrant guard is not a cross-process database lock.

The composed analysis graph retains a per-call runtime repository factory and holds no connection. Local guard ownership moves into that graph without changing SQL, transaction boundaries or advisory-lock rules. Real PostgreSQL row-upsert/isolation/connection cleanup checks remain required; this slice makes no performance or cross-process consistency claim.

Dashboard task upsert retains its original read/modify/save operations and existing repository transactions. This move adds no outer transaction, lock or uniqueness enforcement: concurrent upserts, first-name-match selection and failures after in-memory mutation keep their previous behavior. A successful save followed by serialization failure is not retried.

Moving active-lease validation into the station service does not move database transaction or lease mutation boundaries. Rebind and diagnostic contracts still validate commit/rollback behavior with an isolated PostgreSQL schema. No schema, advisory lock, retry or lease timing changes are introduced.

The retained PLC readiness check still treats any non-None repository as authoritative and only inspects whether mutate_plc_fenced_attempt_with_db_time is callable. It never invokes that method as a probe. This structural extraction changes no database transaction, lock or owner-fencing primitive.

LegacyRuntimeCoordination mutates only the existing PLC runtime app_config row through mutate_app_config_namespace, preserving the advisory transaction lock and absent-row serialization. JSON fallback still uses protected app-config mutation. A claimed owner performs the original fresh repository check before selecting the heartbeat callback; callback failure after persistence does not undo or replay the committed claim.

PLC legacy record projection still delegates configuration reads to the existing store. The extraction introduces no SQL, lock, transaction or consistency change: returned audit records remain shallow copies and persisted validation occurs after the original configuration read guard. It does not establish a new atomic read/verify transaction.

LegacyPlcOperations delegates to the existing configuration, ownership, record and settlement services. Extraction adds no SQL or transaction and does not strengthen the original multi-read consistency or application-clock ownership guarantees. Error paths and already-persisted evidence keep their prior semantics.

Repository ownership is per application graph; a reset of one owner cannot close a different owner’s connection. Cross-thread reset still invalidates by generation without closing another active thread’s connection, and the thread closes its old selection at its next access/scope exit. JSON selection, PostgreSQL failure without JSON fallback, transaction semantics and probe responses are unchanged. Two owners sharing the same environment mapping still observe its changes; libpq process environment and database state are not made application-private.

Each build_foundation call creates its own RuntimeRepositories factory. Connection acquisition stays lazy and thread-local, cache keys still observe live store/DSN/connector values, and one foundation reset cannot close another foundation connection. The builder neither connects nor migrates the database; statement locking and transaction behavior remain unchanged.

ArtifactRuntimeProvider isolates the lazy artifact-runtime cache and configuration signature within one owner. Its default owner retains the existing database URL validation and restart-on-configuration-change behavior. The underlying artifact location connector and transaction policies are unchanged; this adds no schema, migration, connection pool or database lock policy. Independently supplied builders remain responsible for their actual resource sharing.

Ordered Web drain waits for owned background thread scopes to finish on their own threads. It does not close another thread's connection, sweep a global connection registry or infer commit/cleanup success merely from thread completion. Existing repository scope and exception cleanup contracts remain in force.

This offline shutdown replay follows lifecycle candidate 7d7886a and preserves current native history, readiness, model/tail and canonical LF fixes. Four owned runtime/test/contract blobs match reviewed 82313c5. Manifest v205 lists 524 sources. The 480-second shutdown allowance remains cooperative and requires ASGI request quiescence; complete independent application composition is still pending. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

The three explicit detection storage suppliers preserve the existing ArtifactStore publication, generation and transaction rules. This composition change adds no database migration, connection owner, retry or lock-policy change.

This offline detection artifact replay follows shutdown candidate 8618f7a and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 713010a. Manifest v206 lists 524 sources. Storage suppliers retain call-time selection; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Detection image codecs, reference sheets, video materialization and local-model loading now receive storage dependencies explicitly. Object publication, generation checks, database transactions and existing cache lifetimes are unchanged; no migration or additional retry is introduced.

This offline detection media replay follows artifact candidate e7e12b2 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 5e86530. Manifest v207 lists 524 sources. Explicit stores retain original cache, error and video cleanup behavior; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

HTTP artifact injection changes response composition only. Artifact database lookups, read-cache leases, generations, storage modes and database connection/transaction ownership retain existing behavior. Explicit dependency failure does not retry a lookup in a process-global store.

This offline HTTP artifact replay follows detection media candidate f2b4519 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 301b6c1. Manifest v208 lists 524 sources. Explicit missing file dependencies fail closed while genuinely omitted legacy arguments retain their documented default. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Training resource/archive storage injection preserves artifact generation checks and repository transaction ownership. Existing model/dataset retirement markers still use their original repository methods; no SQL, advisory-lock, migration or cross-resource transaction is changed. Integration fixtures now pass the strict digest file port directly instead of replacing its module global.

This offline training resource replay follows image candidate 9063ace and preserves current history, readiness, model/tail, shutdown, corrected boundary documentation and canonical LF guards. Production and test blobs match reviewed fbf5434. At this replay boundary manifest v215 selects 526 sources. Explicit resource and archive capabilities preserve file operation ordering, strict digest failures, partial publication and archive formats. Current source changes require actual-main rebind, independent review and full CI/release acceptance before publication.

Accessory explicit file capabilities preserve artifact generation checks and repository transaction behavior. The guide provenance integration fixture supplies the files port directly; this refactor changes no SQL, connection lifetime, locks or schema.

This offline accessory file replay follows training resource candidate 7ae44bf and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed eccc553, including ordered constructor bindings. At this replay boundary manifest v216 selects 526 sources. Upload ordering, partial publication, provenance collisions and sprite fallbacks remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

Training model, dataset and resource catalog file ownership is explicit; repository selection, training-task lookup aliases and snapshot reads are unchanged. Validate the original trained-model catalog suite with --postgres against an isolated disposable database, including schema cleanup. This storage-injection change adds no SQL, migration or database lock policy.

This offline training catalog replay follows text cleanup candidate 1199028. Owned source/test blobs and ordered entry match reviewed 8f0715d. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v228 selects 528 sources. Local and indexed selection, permission ordering and repeated reads remain unchanged. Exact-source neighbor evidence is reused; current targeted, real PostgreSQL, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

A Web artifact composition owns the lazy artifact selector but does not change PostgresLocations connection allocation, transaction scope or schema. Independent builders remain responsible for physical resource sharing; logical owner isolation does not make multi-store writes atomic.

This offline Web artifact composition replay follows comparison candidate d2ae509. Owned source/test blobs and ordered entry match reviewed a0fa2ed, including the Python 3.10 structural source guard. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v236 selects 529 sources. The Web graph owns a fresh lazy runtime provider and two focused views; this is not a complete application factory or proof of independent underlying resources. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

StreamConfiguration uses existing load/save capabilities and adds no repository, connection, transaction or advisory lock. A failed save retains the original in-memory mutation; this structural extraction adds no transactional guarantee.

This offline stream configuration replay follows Web artifact candidate f2e481b. Owned source/test blobs and ordered entry match reviewed 14f6504. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v237 selects 530 sources. Existing load, mutation, save and post-save response ordering remain unchanged; configuration is not given a new transaction or lock. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

IncomingTextStore now resolves JSON single-record lookups through its own list methods. The two callbacks through the application entry have been removed; narrow repository, guard, path and row-adapter inputs remain. Tests replace the owning store method and cover two independent stores, preserving missing-loader errors, call-time repository selection and lock behavior. TextStorage allocates both text stores and their shared write lock per composition, without opening a connection or retaining a user. Manifest v238 selects 531 source paths, including text_inspection/storage_composition.py. This closes the store self-reference only; full application factory and route/lifecycle instance isolation remain unfinished.

The text storage lock belongs to `TextStorage` and its public lock property cannot be rebound. The entry lock alias initially references it; replacing that private entry alias no longer replaces either store guard. Remaining route/write adapters still use their existing inputs until their domain composition is migrated. This intentional narrowing of private test seams does not change configured runtime behavior.

Incoming workflow composition resolves its repository through the selected store on the calling thread and holds no connection or account. Duplicate lookup keeps the existing owner/task/capture query, missing-row decoder behavior, JSON fallback order and exceptions. It introduces no schema, transaction, cache, lock removal or retry. JSON mutation guards share the selected TextStorage lock.
