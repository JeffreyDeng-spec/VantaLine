# React Production Readiness

Phase 1 serves the React production bundle directly from FastAPI. The former
static root is not the production source of truth anymore.

## Serving Shape

- `GET /` serves `frontend/dist-production/index.html`.
- Preserved deep links are routed to the same React shell:
  `/tasks`, `/accessories`, `/pipeline`, `/inspect`, and `/data-analysis`.
- Built assets are served from `/static/assets/*`, backed by
  `frontend/dist-production/assets`.
- Retired top-level workbench routes must stay `404` in Phase 1.

## Local Build Gate

Run the frontend production gate before handing off review:

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run build:production-cutover
```

Expected result:

- TypeScript passes.
- The production bundle is generated under `frontend/dist-production`.
- Vite chunk-size warnings are acceptable unless they become hard build errors.

## Core Smoke Gate

Run the focused Phase 1 smoke from the service root:

```bash
python3 scripts/smoke_phase1_core_cleanup.py
```

The smoke verifies:

- The preserved React routes return `200`.
- Retired routes return `404`.
- `/api/config` does not expose retired profile fields.
- Core preserved API surfaces for tasks, accessories, training resources,
  detection status, and review records still respond.
- Retired backend helper implementations are absent; only 410 route stubs and
  auth guards remain for removed endpoint families.
- Historical local backup/data payloads are sanitized at runtime so retired
  profile and comparison fields do not leak through public APIs.

## Deployment Boundary

This checklist is local-readiness only. It does not deploy online services,
change database schema, introduce microservices, or start worker processes.
