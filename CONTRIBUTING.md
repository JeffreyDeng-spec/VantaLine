# Contributing to VantaLine

## Change flow

1. Start from current `origin/main` in a clean worktree.
2. Use `feature/<topic>`, `fix/<topic>`, `hotfix/<topic>`, or `docs/<topic>`.
3. Read the domain documents linked by [docs/README.md](docs/README.md).
4. Implement the smallest coherent change and update mapped documentation.
5. Run targeted tests from [docs/testing.md](docs/testing.md).
6. Open a pull request and complete every section of the production template.
7. Squash merge only after all required checks pass. Successful `main` CI automatically creates and deploys an immutable release.

Direct pushes and force pushes to `main` are prohibited. Production is not a development environment and must not be repaired by copying individual files.

## Documentation impact

Behavior, API, permission, configuration, database, PLC, testing, or operational changes must update corresponding authoritative documentation in the same PR. `docs/contract.json` defines high-risk code-to-document mappings enforced by CI.

For an internal refactor with no documentation impact, the PR must explain why observable behavior, interfaces, operations, and safety invariants are unchanged. Historical documents are never updated to describe current behavior; update their authoritative replacement instead.

## Definition of done

- Targeted local checks and required CI pass.
- The documentation contract passes.
- The PR explains user-visible and operator-visible behavior.
- Rollback restores a complete previous release, not selected files.
- No secrets or production identifiers appear in code, docs, fixtures, logs, screenshots, or PR text.
