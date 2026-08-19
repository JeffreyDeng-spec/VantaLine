# VantaLine Phase 1 React Parity Checklist

Phase 1 narrows the product to the active quality-inspection workflow and keeps
the backend monolith in place. No database migration, backend split, worker
expansion, or new dependency is part of this phase.

## Preserved Product Surfaces

| Surface | Route | Primary API smoke |
| --- | --- | --- |
| Tasks | `/tasks` | `GET /api/ai/tasks` |
| Accessories | `/accessories` | `GET /api/accessories` |
| Dataset training | `/pipeline` | `GET /api/training/resources` |
| Detection | `/inspect` | `GET /api/status` |
| Result review | `/data-analysis` | `GET /api/data-analysis/records` |

## Phase 1 Acceptance Checks

- React production build succeeds with `npm --prefix frontend run build:production-cutover`.
- TypeScript succeeds with `npm --prefix frontend run typecheck`.
- `python3 scripts/smoke_phase1_core_cleanup.py` passes.
- Public config payloads do not expose retired experimental profile state.
- Retired top-level routes return `404`.
- Retired API entry points return `410` for administrators and are not granted
  ordinary feature permissions.

## Out Of Scope

- Online deployment or remote service cleanup.
- Database migrations or persisted schema rewrites beyond local JSON field
  cleanup.
- Splitting the FastAPI service into new services.
- Adding new worker runtimes or dependencies.
