# New maintainer checklist

**Status: Authoritative**

## First hour

- Read root `README.md`, `AGENTS.md` (agents), this checklist, `architecture.md`, and `CONTRIBUTING.md`.
- Confirm the repository remote and protected `main`; do not reuse an unknown or dirty deployment worktree.
- Compare latest GitHub Release SHA with production `/api/version` using approved access.
- Identify which domain document owns the intended work and whether it is authoritative, proposal, or historical.
- Review `.gitignore`, `CODEOWNERS`, PR template, CI, and `docs/contract.json` before editing.

## First day

- Create a clean worktree/short-lived branch from current `origin/main`.
- Install dependencies from tracked manifests without inventing versions.
- Run the documentation contract, release contract, frontend typecheck/build, and one relevant backend smoke test.
- Trace one request from React through FastAPI/storage and, for PLC work, through plan/attempt/browser receipt without opening real hardware.
- Learn where secrets and mutable data live conceptually; do not copy them into the repository.

## First pull request

- Keep the change focused and update mapped authoritative docs.
- Complete purpose, risk, documentation impact, evidence, and whole-release rollback sections.
- Verify no generated/runtime/secret file is tracked.
- Wait for required checks, squash merge, then verify automated release status and `/api/version` if the PR deploys.

You are ready to maintain independently when you can explain the product, production data flow, browser-owned PLC boundary, source-of-truth/release process, forbidden files, targeted tests, and rollback path without relying on oral history.
