# PostgreSQL runtime operations

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

## Ownership and compatibility

Standard preparation adds asset/standard JSONB fields, not new tables. Attempts
are claimed under the standard advisory lock before paid I/O. Immutable preparation
revisions contain the source hash, elements, cleaning evidence, and derivative hash.
`mutate_text_document(..., revision_action='prepare')` publishes the active pointer
and an append-only standard snapshot in the same transaction. Legacy source SHA
fields retain their meaning; `preparation`/`reference_sha256` identify the effective
reference. New unprepared assets cannot enter a managed snapshot. Previous active
snapshots stay usable until their replacements are ready. Records bind the exact
preparation revision; no original, historical evidence or old revision is overwritten.

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
