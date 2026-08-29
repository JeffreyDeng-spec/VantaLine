# VantaLine

VantaLine is a production visual-inspection platform for defining inspection tasks, managing accessory evidence, training or selecting models, inspecting camera/images/video, and optionally reporting camera results to a workstation-local PLC.

## Current production shape

- React frontend and FastAPI backend are released together from one Git commit.
- PostgreSQL owns shared runtime records and workstation-scoped PLC configuration.
- Physical PLC I/O is performed only by desktop Edge/Chrome through Web Serial v4. The server performs zero serial I/O.
- `main` is the only production source. CI builds an immutable release and deploys it automatically after merge.
- `/api/version` is the runtime source for release and protocol consistency.

## Start here

- **Human maintainers:** [Documentation index](docs/README.md)
- **Coding agents:** read [AGENTS.md](AGENTS.md), then [Agent overview](docs/agent-overview.md)
- **First day:** [New maintainer checklist](docs/new-maintainer-checklist.md)
- **Contributing:** [CONTRIBUTING.md](CONTRIBUTING.md)
- **Production incidents:** [Production runbook](docs/production-runbook.md)

## Local quick start

```bash
git clone https://github.com/JeffreyDeng-spec/VantaLine.git
cd VantaLine
python3 -m pip install -r requirements.txt
python3 -m uvicorn local_inspection_service.server:app --host 127.0.0.1 --port 8000
```

Frontend development and the authoritative test matrix are documented in [Testing](docs/testing.md). Production dependencies use `requirements-production.lock`, not an ad-hoc environment.
The required CI toolchain is Python 3.10, Node.js 22, and PostgreSQL 16. Use tracked dependency manifests and locks; do not infer production versions from a developer machine.


## Non-negotiable safety rules

- Never deploy from a developer worktree, production checkout, backup, or locally built bundle.
- Never edit production source in place. Use a short-lived branch, pull request, required CI, and an immutable release.
- Never commit secrets, environment files, runtime data, uploads, outputs, models, logs, databases, caches, backups, or frontend build output.
- Never automatically retry an uncertain PLC write. Preserve at-most-once physical-action semantics.
- Update mapped authoritative documentation whenever a public behavior, interface, operational procedure, permission boundary, database contract, or PLC invariant changes.

Historical design documents are retained for audit only. They are indexed under [Historical documents](docs/archive/README.md) and must not be implemented as current behavior.
