# PostgreSQL runtime operations

Detection task persistence now obtains the current thread repository inside each
of its three original storage entry points. JSON single-task writes retain the
nested load/save factory selections; SQL single writes still upsert and full saves
still replace all valid rows. Invalid single rows are skipped after cache invalidation
and directory creation; a fully invalid bulk save still replaces with an empty set.
Factory/query errors propagate without JSON fallback. Existing locks, SQL and schema
are unchanged; read-lock optimization belongs to a later batch.
Row decoding and background callback getters resolve at the original expressions:
after preceding work and before fetch/string/mapping argument effects. Missing
callbacks preserve argument evaluation and TypeError. Source manifest v11 covers
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
