# Production baseline reconciliation — 2026-08

**Status: Authoritative provenance record**

This branch was created as a fresh worktree from `origin/main` at
`4af229d78e4fb328a66c4b2637f002bd5c01c6cc`. It does not reuse the historical
dirty deployment worktree.

The candidate source was reconciled from three read-only inputs:

- GitHub `main`, as the ancestry and review base;
- the source files currently installed under `/opt/vantaline/app`;
- selected uncommitted source and tests required to make the installed PLC v4,
  incoming-text, navigation, and PostgreSQL behavior rebuildable.

The reconciliation excludes environment files, credentials, uploads, runtime
records, detection results, model binaries, logs, virtual environments, caches,
backups, databases, and generated frontend output. `dist-production` is rebuilt
by CI and packaged with the backend from one fixed commit.

This document records provenance only. The immutable release manifest is
generated later by `scripts/build_release_artifact.py` as `VERSION.json` and
`SHA256SUMS`; neither an old production backup nor this reconciliation directory
is a release artifact.

Activation remains gated on the pull-request checks, a baseline tag, and a
successful rollback rehearsal. Until those gates pass, no workflow deploys to
production and the existing systemd unit remains unchanged.
