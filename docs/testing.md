# Testing

**Status: Authoritative**

Run checks from repository root unless stated otherwise.

| Change area | Required local checks |
| --- | --- |
| Documentation only | `python scripts/verify_docs_contract.py --base-ref origin/main`, `git diff --check` |
| Backend/API/auth | Python compile plus affected smoke/permission tests |
| PLC/Web Serial | `smoke_plc_web_serial_v3.py`, `smoke_plc_frontend_contract.py`, release contract |
| Frontend | `npm ci`, typecheck, production build |
| Browser media inputs | `python local_inspection_service/scripts/smoke_frontend_media_inputs.py`; frontend typecheck/build. On the text-comparison camera surface, cover camera enumeration and labels, selection while another open is pending, stale-stream disposal, `devicechange`, selected-device removal, permission denial and no-device fallback. Every file input must use the shared drop contract, followed by any domain-specific validation. Cover chooser/drop acceptance, explicit single or multiple behavior, disabled-state rejection, visible invalid-file feedback and keyboard access. |
| PostgreSQL/migrations | migration safety, repository smoke, real PostgreSQL schema smoke |
| Text inspection v2 | `python local_inspection_service/scripts/smoke_text_compare_beta.py`; `python scripts/smoke_text_inspection_v2.py`; pass `--customer-docx` for the fixed image1–image18 acceptance file; run `smoke_text_inspection_v2_endpoints.py` in fail-closed, external-only and enabled modes; run `smoke_text_inspection_v2_postgres_contract.py`; frontend typecheck/build. Endpoint coverage must distinguish provider failure from response-schema validation failure, retain bounded provider evidence and stage timing, prove the 2048-pixel provider-copy bound and 30-second label-comparison timeout floor, exercise Qwen 0–1000 boxes, percentage confidence, `text_mismatch` mapping and exact-equal artifact removal without manufacturing `MATCH`, and prove credentials plus embedded media are redacted. The frontend smoke contract keeps camera and uploaded-actual inputs, broad image chooser/drop acceptance without browser-MIME blocking, backend content decoding and uncommon-format normalization (including a disguised-extension fixture), a two-column order-gallery/actual-image workbench, compact desktop top strip, viewport-height image allocation plus medium/narrow/short-screen adaptations, selected-thumbnail highlight, selection-independent full-size preview, accordion/import-modal navigation, inline order add/select/soft-disable/re-enable actions, gallery-only reference selection with no local-reference upload, selected-standard preservation when the actual changes, confirmed-only comparison, editable logical standards backed by immutable revisions, a default-closed, escaped and display-bounded raw/normalized diagnostic disclosure, absence of the legacy creation entry, and absence of the retired persistent scope-warning badge. |
| Release/install | release contract, dependency verification, shell syntax, docs contract |

Canonical commands:

```bash
python scripts/verify_docs_contract.py --base-ref origin/main
python scripts/verify_release_contract.py
python local_inspection_service/scripts/smoke_plc_web_serial_v3.py
python local_inspection_service/scripts/smoke_plc_frontend_contract.py
python local_inspection_service/scripts/smoke_frontend_media_inputs.py
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

Text-comparison camera-device changes must prove that an older pending `getUserMedia` result cannot replace a newer selection, every discarded stream has all tracks stopped, device labels are refreshed after permission, and a removed selected device falls back only while the text-comparison camera surface is active. Permission denial, no devices and a switch still opening must keep capture disabled. This selector is independent from the PLC detection workbench.

File-upload changes must enumerate every frontend file surface. Test click, Enter, Space and drag/drop; valid and invalid MIME/extension combinations; a mixture of accepted and rejected files; first-file behavior for a single target; preservation of all accepted files for a multiple target; repeated selection of the same file; and disabled chooser and drop behavior. A dragged image or video must retain upload provenance and never enter the camera PLC path.

Text inspection changes must cover cross-account 404 behavior, malicious DOCX/PDF/image bounds, reversible soft deletion, append-only confirmed revisions, optimistic revision conflicts during concurrent add/delete, refusal to confirm an empty draft, preservation of historical media and comparison records, exact revision/hash binding on new comparisons, response-loss idempotency, comparison-identity conflicts after any input change, VLM timeout-after-charge, invalid JSON/coordinates, lazy PDF rendering, explicit manual completion and no automatic pass on system failure. Frontend behavior must additionally cover accordion collapse, import-modal cancellation, inline order editing, click-to-select and selected-card highlight, selection-independent thumbnail-to-full-size inspection, keyboard access, absence of the standalone local-reference uploader, preservation of the actual image when a gallery reference changes, stale-result clearing and refusal to compare a draft asset. The legacy incoming-text regression suite remains required during the expand window.

Diagnostic assertions must verify the persisted request/provider/stage envelope for success, fail-closed, provider-error and invalid-schema paths. Tests must prove API keys, authorization/cookie values and embedded base64 media never enter either the durable diagnostics or the compact service-log event.

Single-label extraction requires `smoke_label_extraction.py` and `smoke_label_extraction_endpoints.py`. Geometry fixtures cover rectangular/circular/irregular shapes, preservation of original text pixels, multiple candidates, malformed masks, orientation and invalid polygons. Endpoint tests cover account/media isolation, request identity conflicts, preview-before-confirm, stale edit versions, confirmed server-crop comparison, mutually exclusive inputs and timeout-after-charge with no replay. Frontend acceptance includes contained-image coordinates under portrait/landscape/narrow screens, guide drag/resize, polygon editing, disabled confirmation after edits, stale response discard and independent standard selection. Measure real-sample correction rates and provider latency separately from synthetic correctness; synthetic tests do not certify segmentation accuracy.

`smoke_label_extraction_postgres.py` runs against the CI PostgreSQL service in a disposable schema and verifies one-winner concurrent revision insertion plus account/root-scoped queries. For browser interaction, start Vite on port 5177 and run `smoke_label_extraction_browser.py` with development-only Playwright; `LABEL_TEST_BROWSER=msedge` selects an installed Edge. Its isolated fixture checks sub-pixel source-coordinate mapping across screen sizes, real React editing/confirmation state and absence of model calls during manual edits. No customer media is used.
