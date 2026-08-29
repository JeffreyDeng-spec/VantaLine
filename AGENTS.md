# VantaLine repository instructions for coding agents

Before planning or changing code, read [docs/agent-overview.md](docs/agent-overview.md) and follow its routing table. `main`, immutable GitHub Releases, and production `/api/version` are the sources of version truth.

## Required workflow

1. Fetch `origin/main` and work in a clean, short-lived `feature/*`, `fix/*`, `hotfix/*`, or `docs/*` branch/worktree.
2. Preserve user-owned and unrelated uncommitted changes. Never reset, clean, or deploy a dirty historical worktree.
3. Make surgical changes and update every authoritative document mapped to changed high-risk code by `docs/contract.json`.
4. Run targeted checks in [docs/testing.md](docs/testing.md), plus `python scripts/verify_docs_contract.py --base-ref origin/main` and `git diff --check`.
5. Open a pull request using the production-change template. Record risk, documentation impact, test evidence, and whole-release rollback.
6. Merge only after required CI passes. Do not manually copy files to production; merge-to-main builds and deploys one immutable frontend/backend release.

## Safety invariants

- The server must never open a serial port in the current Web Serial v4 architecture.
- Only an authorized, leased, workstation-bound Edge/Chrome page may perform PLC I/O.
- Never retry a physical PLC write after timeout, malformed response, disconnect, browser crash, or any uncertain outcome.
- Ordinary image upload and video analysis must not generate PLC writes; only the dedicated camera flow may produce a browser dispatch.
- A blank output control point means no Y operation in planning, frames, execution, or audit.
- Database changes are additive/expand-first. Destructive contract changes require a separate staged rollout.
- Never expose or commit credentials, deployment hosts, keys, cookies, DSNs, runtime records, customer media, models, or production data.

## Documentation rules

- `docs/README.md` lists every authoritative document.
- Current behavior belongs only in documents marked **Authoritative**.
- Proposed behavior must be explicitly marked **Proposal**.
- Files marked **Historical / Do not implement** are evidence, not instructions.
- If code and documentation disagree, stop and resolve the discrepancy in the same PR.

More specific `AGENTS.md` files may add subtree rules, but may not weaken these repository-wide requirements.
