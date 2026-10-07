# Inspection service agent routing

The root [AGENTS.md](../AGENTS.md) remains mandatory. Before changing this subtree, read [architecture](../docs/architecture.md) and [testing](../docs/testing.md).

- PLC, camera dispatch, workstation lease, or `frontend/src/features/plc/`: also read [PLC Web Serial v4](../docs/plc-web-serial-v4.md).
- Authentication, permission, API, or configuration: also read [configuration reference](../docs/configuration-reference.md).
- Storage or migration: also read [PostgreSQL runtime operations](../docs/postgresql-runtime.md) and the [production runbook](../docs/production-runbook.md).

Do not create a second source of truth in this subtree. Update the mapped repository-level authoritative document when behavior changes.

Text standards compose through text_inspection/standard_composition.TextStandardWorkflows. The inert domain owner holds the supplied TextRecordStore, media, revisions, standard imports/library/edits, document classification and preparation jobs. Internal storage/media/revision callbacks select that owner at operation time; each native job service has its own scoped lifecycle. Three registration methods remain at their original entry positions, preserving intervening routes. This does not complete application assembly or remove the remaining comparison/extraction/history dependencies.
