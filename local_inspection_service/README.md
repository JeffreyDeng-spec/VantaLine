# VantaLine inspection service

**Status: Authoritative subsystem entry**

This directory contains the FastAPI backend, React frontend, runtime repository adapters, model/training integrations, and PLC planning/audit code.

Before making changes, return to the repository-wide [documentation index](../docs/README.md). Coding agents must also follow the root [AGENTS.md](../AGENTS.md) and this directory's [AGENTS.md](AGENTS.md).

## Boundaries

- FastAPI authenticates, authorizes, coordinates detection, creates immutable browser PLC plans, and records evidence.
- `frontend/` owns browser camera and Web Serial physical I/O.
- `storage/` owns persistent repository implementations; PostgreSQL is the shared production runtime.
- Mutable `data/` content, uploads, outputs, secrets, models, logs, and generated bundles are not source and must not be committed.

## Start and verify

```bash
python3 -m uvicorn local_inspection_service.server:app --host 127.0.0.1 --port 8000
npm --prefix local_inspection_service/frontend ci
npm --prefix local_inspection_service/frontend run typecheck
```

Use the authoritative [test matrix](../docs/testing.md), [architecture](../docs/architecture.md), [configuration reference](../docs/configuration-reference.md), and [PLC Web Serial v4 specification](../docs/plc-web-serial-v4.md). Do not use phase or migration evidence as current design documentation.
