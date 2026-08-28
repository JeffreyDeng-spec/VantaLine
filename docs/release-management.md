# VantaLine release management

**Status: Authoritative**

`main` is the only production source of truth. Production is never built from a developer worktree, server checkout, backup directory, untracked bundle, or manually selected files.

## Change and release flow

1. Create `feature/*`, `fix/*`, `hotfix/*`, or `docs/*` from current `origin/main`.
2. Open a pull request using the production-change template and update mapped authoritative docs.
3. Merge only after every required CI job passes.
4. Successful push CI on `main` triggers `Release and deploy production`; no manual deployment approval/button is required.
5. The workflow builds one immutable artifact, creates a draft Release, deploys through the restricted account, verifies exact SHA/protocol/assets/service acceptance, then publishes the Release.

## Artifact and production invariants

- Frontend and backend share one release, Git SHA, and PLC protocol contract.
- The artifact contains source, production bundle, migrations, locked dependencies, `VERSION.json`, and `SHA256SUMS`.
- Production uses `/opt/vantaline/releases/<release-id>` and an atomic `current` link; mutable state stays outside releases.
- Existing tags/releases are immutable. Failed drafts and deployment logs remain evidence.
- The installer requires at least 2 GiB free, healthy service/database preflight, and no unsafe PLC in-flight state.
- Destructive database changes cannot be part of one automatic deployment; use expand/migrate/contract phases.

## Failure, retry, and rollback

An unchanged failed workflow job may be rerun only after its external gate is safely corrected, such as restoring disk capacity or deployment connectivity. Never rebuild locally to bypass failure. Acceptance failure automatically points `current` back to the prior release and restarts. A post-acceptance regression is handled by a complete revert/release or previous immutable artifact, never a partial file rollback.

Protocol or bundle mismatch keeps ordinary website functions available but disables PLC leases and physical actions. See [Production runbook](production-runbook.md) for diagnosis.
