# Agent overview

**Status: Authoritative**

## Mission and current system

VantaLine lets users define inspection tasks, maintain accessory evidence, build/train or select detection models, and inspect camera, image, or video input. Camera results may produce a workstation-scoped PLC output plan.

```text
Edge/Chrome React UI ──HTTPS──> FastAPI ──> PostgreSQL/runtime storage
       │ camera                         │ detection/model workers
       └─ Web Serial v4 ──> local PLC  └─ immutable audit/dispatch plan

GitHub PR → required CI → main → immutable release → production → /api/version
```

The browser owns camera capture and physical serial I/O. FastAPI authenticates, authorizes, generates immutable PLC frames/plans, and records browser evidence. PostgreSQL owns shared records and workstation identity/configuration. Production source is never edited in place.

## Code and ownership map

- `local_inspection_service/server.py`: API composition, authentication/permissions, detection orchestration, PLC station leases/dispatches.
- `local_inspection_service/frontend/src/`: React UI; `features/plc/webSerialClient.ts` is the physical Web Serial state machine.
- `local_inspection_service/storage/`: persistent runtime repositories and PostgreSQL coordination.
- `local_inspection_service/plc_web_serial.py` and `release/plc-protocol.json`: logical-address/frame and release protocol contract.
- `scripts/` and `.github/workflows/`: verification, immutable packaging, installation, rollback, and automation.
- Runtime uploads, outputs, secrets, models, logs, and databases are external mutable state and are not source.

## Invariants agents must preserve

- Current PLC protocol is `plc-web-serial-v4`; server serial opens/writes remain zero.
- One active browser lease/epoch owns a station. A dispatch is declared before physical I/O and is at-most-once.
- ACK may keep a connection reusable. Timeout, malformed/extra response, crash, disconnect, or unknown write outcome is uncertain and is never automatically replayed.
- D must ACK before optional Y. Blank Y means no Y frame or audit operation.
- Only the dedicated camera endpoint can create a PLC plan; image upload/video cannot assert camera provenance.
- Frontend/backend protocol or bundle mismatch disables PLC action while ordinary website functions remain available.
- Database migration is expand-first and must remain compatible with the previous release during rollout.

## Work routing

| Change | Read first | Minimum focused checks |
| --- | --- | --- |
| PLC/Web Serial/camera dispatch | `plc-web-serial-v4.md`, `architecture.md` | PLC smoke, frontend contract, typecheck, release contract |
| API/auth/permissions/config | `architecture.md`, `configuration-reference.md` | targeted backend smoke, permission tests, docs contract |
| PostgreSQL/migrations | data migration runbook, `production-runbook.md` | migration safety and real PostgreSQL schema smoke |
| Frontend behavior | `architecture.md`, `testing.md` | typecheck and production build |
| CI/release/install | `release-management.md`, `production-runbook.md` | source safety, shell syntax, release contract |

## Never do

Do not deploy from a dirty worktree, copy individual files to production, build on the server, bypass PR/CI, commit mutable data/secrets, infer production configuration from examples, or revive archived server-side pyserial/input-polling designs. If repository truth conflicts with runtime truth, stop, collect read-only evidence, and reconcile both through a PR.
