# Testing

**Status: Authoritative**

Run checks from repository root unless stated otherwise.

| Change area | Required local checks |
| --- | --- |
| Documentation only | `python scripts/verify_docs_contract.py --base-ref origin/main`, `git diff --check` |
| Backend/API/auth | Python compile plus affected smoke/permission tests |
| PLC/Web Serial | `smoke_plc_web_serial_v3.py`, `smoke_plc_frontend_contract.py`, release contract |
| Frontend | `npm ci`, typecheck, production build |
| PostgreSQL/migrations | migration safety, repository smoke, real PostgreSQL schema smoke |
| Text inspection v2 | `python local_inspection_service/scripts/smoke_text_compare_beta.py`; `python scripts/smoke_text_inspection_v2.py`; pass `--customer-docx` for the fixed image1–image18 acceptance file; run `smoke_text_inspection_v2_endpoints.py` in fail-closed, external-only and enabled modes; run `smoke_text_inspection_v2_postgres_contract.py`; frontend typecheck/build. The frontend smoke contract keeps camera and uploaded-image inputs, zoomable comparison previews, label thumbnails/full-size preview, accordion/back/modal navigation, a single exclusive reference source, state reset on mode/order/asset changes, confirmed-only comparison, editable logical standards backed by immutable revisions, absence of the legacy creation entry, and absence of the retired persistent scope-warning badge. |
| Release/install | release contract, dependency verification, shell syntax, docs contract |

Canonical commands:

```bash
python scripts/verify_docs_contract.py --base-ref origin/main
python scripts/verify_release_contract.py
python local_inspection_service/scripts/smoke_plc_web_serial_v3.py
python local_inspection_service/scripts/smoke_plc_frontend_contract.py
python local_inspection_service/scripts/smoke_migration_safety.py
python local_inspection_service/scripts/smoke_postgres_runtime_repository.py
npm --prefix local_inspection_service/frontend ci
npm --prefix local_inspection_service/frontend run test:plc-capture
npm --prefix local_inspection_service/frontend run typecheck
npm --prefix local_inspection_service/frontend run build:production-cutover
git diff --check
```

CI is authoritative for production dependency and PostgreSQL service checks. Never weaken or delete a failing safety assertion merely to make a change mergeable; resolve the behavioral mismatch or update the documented contract in the same reviewed PR.

PLC input changes must additionally cover D-register read golden frames and parsing, v4-to-v5 migration, input/output conflicts, reset-before-arm, one edge/one capture, sustained-trigger latching, reset/retrigger, busy/not-ready missed edges, write priority, and reconnect fail-closed behavior.

Text inspection changes must cover cross-account 404 behavior, malicious DOCX/PDF/image bounds, reversible soft deletion, append-only confirmed revisions, optimistic revision conflicts during concurrent add/delete, refusal to confirm an empty draft, preservation of historical media and comparison records, exact revision/hash binding on new comparisons, response-loss idempotency, comparison-identity conflicts after any input change, VLM timeout-after-charge, invalid JSON/coordinates, lazy PDF rendering, explicit manual completion and no automatic pass on system failure. Frontend behavior must additionally cover accordion collapse, explicit back and modal cancellation, thumbnail-to-full-size inspection, keyboard access, reference-source exclusivity, stale-result clearing and refusal to compare a draft asset. The legacy incoming-text regression suite remains required during the expand window.
