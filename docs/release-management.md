# VantaLine release management

`main` is the only production source of truth. Production is never built from
a developer worktree, a server checkout, a backup directory, or an untracked
frontend bundle.

## Change flow

1. Create `feature/*`, `fix/*`, or `hotfix/*` from current `origin/main`.
2. Open a pull request using the production change template.
3. Merge only after every required CI job passes.
4. The `Build release candidate` workflow creates one artifact from the merged
   commit. Source, backend, frontend bundle, `VERSION.json`, and checksums stay
   together.
5. Production deployment remains disabled until the baseline tag and rollback
   rehearsal are accepted.

## Invariants

- Never commit secrets, runtime data, models, logs, backups, databases,
  `node_modules`, or frontend build output.
- Never repair production by copying one backend or frontend file. Roll back or
  deploy a complete release.
- PLC protocol disagreement or bundle hash failure must disable PLC leases and
  physical writes while leaving the rest of the website available.
- Database changes use expand/contract migrations. A destructive migration may
  not be part of automatic deployment.

## Baseline activation checklist

- Baseline PR merged and tagged.
- Fresh clone passes CI and builds the same v4 contract.
- Release artifact checksum and `/api/version` agree with the tag commit.
- Install and forced-failure rollback rehearsal pass.
- Production PLC remains commissioning with zero leases and dispatches during
  the rehearsal.
