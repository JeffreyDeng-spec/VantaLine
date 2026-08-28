# PostgreSQL runtime operations

**Status: Authoritative**

PostgreSQL is the production shared runtime store. Historical JSON-to-PostgreSQL preparation packets are migration evidence and must not be used to switch production back to JSON.

## Ownership and compatibility

- Runtime repositories own database access; API/business code must not introduce ad-hoc direct connections.
- Migrations are additive and expand-first. The new schema must remain readable by the previous release during deployment and rollback.
- Dropping, renaming, narrowing, or repurposing fields requires a separately reviewed multi-release contract phase.
- Database credentials are supplied through restricted runtime configuration; they never appear in Git, logs, fixtures, or documentation.

## Change procedure

1. Update repository/schema code and migration safety expectations in one PR.
2. Run migration safety, repository smoke, and real PostgreSQL 16 schema validation.
3. Document data ownership, compatibility window, observability, and whole-release rollback.
4. Let the immutable release installer apply only approved compatible migrations.
5. Verify service health and data behavior after deployment; do not switch to a legacy JSON runtime as an ad-hoc rollback.

Backups and destructive retention actions require separate operational authorization and restore evidence. See [Production runbook](production-runbook.md).
