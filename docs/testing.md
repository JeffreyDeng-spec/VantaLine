# Testing

`node scripts/test_label_image_reuse.cjs` exercises actual React with synthetic images
and delayed HTTP: stable image node/source, zero actual-image downloads during a local
submission/completion, historical preview-only reads, deferred zoom/retry, bounded
fallback, lost-acknowledgement request recovery, replacement/camera cleanup and account
isolation. JPEG EXIF orientations 1-8 verify oriented pixels and marker geometry.
The existing label workspace suite invokes this regression, including in CI.
It writes request byte counts and submission/image/overlay timing to temporary JSON;
`LABEL_IMAGE_BASELINE=1 LABEL_IMAGE_FRONTEND=/path/to/previous/frontend` measures the
same fixture against a prior checkout. Synthetic timing is not production latency or
inference accuracy. Preserve the existing desktop/mobile, navigation, fullscreen and
camera/media suites; verify the deployed version and one existing result without
paid resubmission.

Private label diagnostics acceptance: ordinary and unauthenticated direct requests must
fail before evidence access; administrators retain only owner-scoped access. Verify full
call/quality evidence is retained for internal reads while normal run, history and
submission responses omit internal metadata. The browser fixture asserts no diagnostic
control, raw JSON or diagnostic request, and a visible detection ID.

**Status: Authoritative**

## Backend extraction contract

`python -X utf8 scripts/smoke_model_dependency_contract.py` verifies callable loader
binding after relocation, frozen/default/empty snapshots, missing dependencies,
concurrent async-to-thread scope propagation, independent recorders and ledger
failure without inference replay. The dependency smoke also checks nested real-service scope isolation and
that every manifest source changes the new fingerprint without rewriting a stored
historical fingerprint. Document-classifier and job tests include profile metadata
and assert an actual fake transport plus its usage recorder both run exactly once.
`smoke_model_profiles.py` supplies typed test
ports and retains real PostgreSQL immutable-version, restart and concurrent binding
checks. `smoke_model_profile_routing.py` retains real provider-adapter and role tests.

`python scripts/verify_backend_boundaries.py` rejects entry-point imports, circular
dependencies, wildcard imports and namespace injection inside extracted packages.
Its explicit package list currently covers `model_profiles`; each domain extraction
must extend it. Existing unconverted modules are not claimed compliant by this gate.

`python -X utf8 scripts/verify_backend_contract.py` imports the real application in a
temporary JSON runtime without starting lifespan hooks or provider workers. The
checked-in `tests/backend_contract/application.json` fixes assembled route order
(including hidden routes, mounts and the final SPA catch-all), permission routing,
OpenAPI schemas, middleware configuration and startup/shutdown registrations.
Real ASGI requests also freeze setup/401/403 errors, endpoint-local label guards,
media authentication, hidden OpenAPI and cross-origin rejection. CORS is isolated
from the host environment. Lifecycle registrations are structural evidence only;
worker shutdown and media mount targets still require their domain smoke tests.
The older `smoke_auth_rbac.py` currently rejects label endpoints because its central
mapping assertion does not account for their endpoint-local guards; this is an
existing baseline gap, not a reason to remove permission assertions.
CI compares it and never regenerates the expected value. An intentional HTTP or
lifecycle change requires explicit review of the fixture diff; use `--record`
only for that maintenance operation. Existing auth, navigation, media, PostgreSQL
and PLC tests remain mandatory; this snapshot alone does not certify behavior.

## A + Evolving label acceptance

Verify the upper-left Beta-style back control from the list, import, task and
result views, including refreshed result links and phone-width accessible labels.

Run `VANTALINE_POSTGRES_DSN=... python local_inspection_service/scripts/smoke_label_inspection.py`
against an isolated real PostgreSQL database. The script creates/drops a unique
schema and uses fake provider responses: direct DOCX import, repeated/invalid/empty
images, upload limits, owner/permission gates, immutable reference snapshots,
idempotency, strict two-call settings, fail-closed responses, expiration without
replay, global concurrency and pagination during concurrent task updates. It does not use a real API key.

Run `node scripts/test_label_workspace_ui.cjs` for the actual React workspace with synthetic API/camera fixtures, then frontend typecheck/build, navigation tests, existing manual/Beta and camera/file
contracts. The independent page must support list-first navigation, login returns,
refresh/history deep links, task continuation, standard version changes, image zoom,
camera stop on unmount/hidden tab, and non-PLC ordinary capture. Test 429, invalid
JSON, truncation, duplicate click and restart without a false pass or duplicate call.
Original A prompt boxes are label-relative without a trustworthy full-image extent;
verify the UI explicitly omits uncertain issue boxes and shows the selected crop.

For a live release, separately record results for the existing known missing-model
line and sixth-icon defects, plus named normal/defective control samples. Preserve
sample identities and call/token/timing evidence privately. This small controlled
verification does not estimate real production accuracy.


## Comparison dialog regression

Run `python -m local_inspection_service.scripts.smoke_comparison_history` for
real-route account isolation, stable pagination/search, missing/deleted standard
evidence, old formats, on-demand logs and non-mutation without model calls.
The preparation PostgreSQL smoke additionally covers both raw_json encodings,
SQL projection, cursor/search/decision filtering and owner isolation.
Run `scripts/test_comparison_history_ui.cjs` with the existing Vite/Playwright
variables for list/detail/Back, filtering, current-task isolation, zoom, lazy logs,
mobile layout and screenshots. These are synthetic UI fixtures, not OCR tests.

The evidence UI suite also asserts exactly one result reference image, the
overlaid zoom action and preserved element selection after returning from zoom.

With local Vite on port 5189, run `scripts/test_comparison_dialog_ui.cjs` and
`scripts/test_qwen_evidence_ui.cjs` using `REVIEW_UI_BASE=http://127.0.0.1:5189/react-preview`,
`PLAYWRIGHT_MODULE` and optionally `QWEN_TEST_BROWSER=msedge`. Synthetic HTTP
covers single submission, close/reopen, progress boundaries/95% cap, completion,
timeout, open/closed refresh, lost upload acknowledgment, unavailable upload,
network recovery, 401/403, account switch and stale-response isolation. The
evidence test checks full result migration, compressed preview, opt-in original,
collapsed logs and mobile overflow, saving desktop/mobile screenshots.

`PREPARATION_TEST_QWEN=1 python -m local_inspection_service.scripts.smoke_standard_preparation_endpoints`
also checks authenticated request-ID lookup, cross-owner/missing-request rejection
and non-mutation. These use fake providers and do not establish OCR accuracy.
One separately authorized real comparison is required for release commissioning;
record the exact task/version, timings and screenshots without exposing secrets.

## Qwen OCR evidence comparison (not commissioned)

`python -m local_inspection_service.scripts.smoke_local_ocr_reread` verifies bounded
candidate selection, outward crop coordinates, padding rejection, explicit coarse
text bounds, strict independent-view matching, account-scoped cache reuse,
unknown-outcome no-replay and review-only completion with stubbed paid calls.
The two-round local experiment scored 257/330 (77.9%) on a same-image synthetic
text subset; 44 unsupported cases are excluded, not successes. This does not
certify independent accuracy or production latency. Deployment retains human review.

`python -m local_inspection_service.scripts.smoke_local_evidence_search` checks
deterministic exact multi-box paths, wrapped lines, original spans, skipped NOT,
distant/reversed pieces, strict numeric/punctuation/case rules and bounded search.
Real saved OCR replays measure recovered evidence separately from new OCR accuracy.

`python -m local_inspection_service.scripts.smoke_qwen_ocr_evidence` runs offline
protocol and strict matching fixtures. It checks the pinned model/task, independent
image-only OCR input, nullable scores, original-coordinate bounds, duplicate text
positions, truncation rejection, no HTTP retry/redirect, whitespace-only matching,
one exact occurrence despite conflicting repeats, code provenance, candidate capacity, forged IDs, Unicode
character offsets, local reading order, skipped/reused characters and distant joins.
Spacing regressions cover prose comma/colon spacing with source-offset preservation,
numeric separators, decimal points, missing punctuation, NOT and strict unit boundaries.
Independent-mapping regressions cover valid/invalid siblings, duplicate-target
order independence, malformed envelopes and ranges, protected settled matches,
and retention of valid differences without weakening strict character validation.
An unrelated but legally referenced title must remain review when proposed for a
warning or origin field; similarity can never promote unequal text to matched.
Transport fixtures check bounded Base64, JPEG MIME, unchanged source pixels and
dimensions, and rejection before submission when no permitted encoding fits.
Real-image OCR accuracy after lossy transport must be measured separately.
Truncation tests retain safe usage and finish metadata while excluding provider
content and unknown usage keys from failure diagnostics.
Tile-subset fixtures reject out-of-image words without clamping, preserve valid
rows and original ordering, and still reject truncated responses as a whole.
Presence-mode fixtures additionally distinguish a valid empty array from missing
schema, over-capacity, truncated and all-invalid output. Empty evidence leaves all
required elements in review and schedules no LLM. A rejected unrelated border word
must not discard an independently valid expected value; partial status and rejected
indices remain visible. Cache keys separate the presence parser from old strict
results; no unknown old request is automatically replayed during recovery.
Malformed LLM proposal tests preserve allowlisted billing diagnostics and verify
that invalid proposals fail closed. Full provider bodies are separate private
evidence, not inline diagnostic payloads or service logs.
`python -m local_inspection_service.scripts.smoke_model_audit_preview` covers
JSON Object requests, raw malformed response retention, parse offsets, one-call
behavior, key/media redaction, immutable audit events and original-pixel-preserving
display derivatives. Endpoint fixtures cover preview/audit ownership and path
redaction. Run frontend typecheck/build for preview and on-demand original controls.
`scripts/probe_mapping_audit.py` requires explicit two-call consent, an owned saved
comparison and an exclusive output folder. It compares prompt-only and JSON Object
requests using the same saved OCR evidence, with no new OCR or business writes.
It is not a reconstruction of an unrecorded historical model response, nor an
end-to-end OCR accuracy or latency benchmark.
Auto-rotation fixtures verify an explicit boolean option, default-off behavior and
unchanged original-input coordinates on nonsquare images. Real returned boxes on
rotated images must be inspected separately before enabling a production caller.
`PREPARATION_TEST_QWEN=1 python -m
local_inspection_service.scripts.smoke_standard_preparation_endpoints` additionally
tests real authenticated routes with fake providers: pre-call claims, same-image
cache, request identity conflicts, no late settlement and account-isolated source
media. The PostgreSQL preparation smoke checks insert-once cache and owner/status
CAS. Frontend typecheck/build are required. No fake-provider result certifies OCR.
Existence-rule regressions also cover reversed observation order, absent MODEL,
numeric boundaries, local exact multi-box matches despite conflicting instances,
and display of matching rather than contradictory evidence. Full-sheet UI tests
must enable legacy extraction capability and still submit `captured_file` without
any extraction request; standards without templates cannot start comparison.
`scripts/accept_sheet_existence_replay.py --evidence <private-saved-probe-dir>
--output <new-private-dir>` replays complete real OCR evidence without a paid call.
It saves input/boxes, temporary expected-text templates, explicit synthetic
duplicate/negative cases and per-case PNGs plus JSON/Markdown results. These
regressions are not independent OCR accuracy, dense-sheet or automatic-MATCH gates.
The real synthetic probe verified min_pixels=3072, words_info locations, nullable
scores and HTTP 200; it does not establish dense-sheet accuracy or latency.
`scripts/test_qwen_evidence_ui.cjs` uses the same local Vite/Playwright variables
as the standard-preparation UI test. Its synthetic fixture checks the actual-side
start action, phase polling, next-image visibility, clickable evidence, folded
diagnostics and mobile overflow, saving desktop/mobile screenshots.
`scripts/probe_qwen_ocr.py` requires explicit paid-call consent and a new output
directory; it saves input, pre-call claim, raw output and actual-image box evidence.
Private image external disclosure requires explicit approval before execution.
Nine-image coverage, independent positives/negatives, 30 uncached full comparisons,
P50/P95, cost and template verification remain outstanding. Never count synthetic
authentication tests as full comparisons or enable automatic MATCH from them.

`python3 local_inspection_service/scripts/smoke_doc_images.py` checks direct DOC
extraction bounds, malformed output, missing runtime, timeout cleanup, temporary
cleanup and concurrency with process doubles. Real acceptance separately runs
`scripts/benchmark_doc_images.py --input-dir <fixtures> --output <new-directory>`
with `VANTALINE_DOC_IMAGE_BUNDLE` configured. It exports images, hashes, metadata
and an HTML preview gallery. Compare image inventories with an independently
inspected baseline; image counts alone are not proof of completeness. Word text
overlays and unrelated OLE files are deliberately not composited/exported.

## Classification-only document experiment

`python -m local_inspection_service.scripts.smoke_standard_preparation` checks
pixel provenance, coordinate transforms, strict ID-only classification, unsafe
background rejection and numeric boundaries. It prints a temporary directory
with original/clean/element-overlay PNGs and JSON. These are synthetic evidence.
Edge-cleaning regression covers all four image edges, corner contact, partial
overlap, touching and fully contained exclusions, and keep/uncertain protection.
Full-image RGBA equality checks prove only unprotected exclusion pixels change;
complex-background and unsafe-crop rejection remain tested.
Additional contracts cover adjacent exclusion unions, order-independent pixels,
bounded black/gray fringe removal, partial erasure beside and overlapping exterior
graphics, byte-identical white/alpha and graphic preservation, fully inseparable
background rejection, actual modified-pixel counts,
zero-element graphics confirmation, transparent/white outputs, blank manual crops,
and legacy empty versus nonempty comparison templates. Real-route fixtures verify
explicit/strict graphics confirmation, failed-model/recovery rejection, account
isolation, stale saves, non-comparable public assets and direct compare rejection
without OCR/VLM. Browser fixtures cover the opt-in checkbox, persisted unsupported
badge, and preventing recognition failure from becoming a graphics-only save.
`python -m local_inspection_service.scripts.smoke_standard_preparation_endpoints`
runs authenticated routes with fake OCR/VLM, verifying pre-call persistence,
dedup, immutable manual revisions, stale edits, owner-only media, saved-template
comparison, no VLM during comparison and request identity conflicts. Actual OCR,
semantic cleaning, PostgreSQL concurrency and browser acceptance remain separate
release gates; these fixtures cannot justify production enablement.

`PREPARATION_TEST_DATABASE_URL=<isolated-test-database> python -m
local_inspection_service.scripts.smoke_standard_preparation_postgres` verifies
concurrent claims, atomic publication, immutable history and rollback in a unique
temporary schema; it must not be pointed at the production database.
Run `scripts/test_standard_preparation_ui.cjs` against Vite on loopback port 5189
(or `REVIEW_UI_BASE`), with `PLAYWRIGHT_MODULE` where needed. It outputs desktop,
mobile and reload/no-resubmission evidence in a new temporary directory.
The real-page fixture also verifies activation without a second prepare POST,
source-order modal sequencing, click/keyboard state cycling, save failure retaining
edits, pause/resume, gallery editing through the same modal, dirty-close confirmation,
mobile zoom without document overflow and disabled edits during processing.
`scripts/accept_standard_preparation.py` is a separately consented paid read-only
probe using runtime account ownership/configuration. It writes each image's OCR,
original/clean/overlay PNGs, pre-call claim and sanitized provider response to a
new directory, never the standard library. Explicit `--ocr-cache` requires matching
source hashes; a new prompt experiment is not an automatic retry of an unknown call.

`smoke_standard_preparation_recovery` checks region limits, rejection of model-authored
text, mapping through rounded crops, pixel-preserving cleanup, stable added IDs,
duplicate/conflict handling, empty/timeout/edge reads and no OCR for non-labels.
Run endpoint fixtures with `PREPARATION_TEST_RECOVERY=success`, `timeout` and
`interrupted` to exercise persisted local claims, original observations, owner-only
region evidence, no paid replay, and rejection of late results after interruption.
The paid probe additionally saves `recovery.json`, region input and local OCR overlay
PNGs. Previously missed dimensions must be visually inspected, not accepted solely
because a coverage boolean or OCR confidence is high.

The review interface now accepts imperfect classification with explicit human
correction, not silent image removal. Run
`python3 local_inspection_service/scripts/smoke_document_review.py` for extracted
production-handler logic and a DB-API test double (not live PostgreSQL).
Run `scripts/test_document_review_ui.cjs` against local Vite with Playwright and
`REVIEW_UI_OUTPUT` set: it mounts the real page with a fixture API and saves desktop
and mobile screenshots. Optional `REVIEW_IMAGE_FIXTURES` selects local benchmark
images; these do not enter source control. Verify pending activation gating,
green/red/orange status indicators with explicit destination-action buttons, pending-to-retained-to-excluded toggling,
keyboard activation, exclusion recovery, API-error retention, refresh persistence,
undimmed zoom and mobile overflow. Human corrections are not model successes.
Also verify retained/pending/excluded display order, stable source ordinals within
groups, newly uploaded retained images ahead of exclusions, both toggle directions,
and the same order after reload. PDF/manual pages must retain their page order.
`scripts/test_label_confirm_flow.cjs` is a historical fixture for the retired
mandatory-crop workspace; use `scripts/test_qwen_evidence_ui.cjs` for the current
full-sheet page. Real-route extraction smoke tests still cover legacy confirmed
crop IDs, ownership and dirty/version gates for API compatibility, not live model
accuracy or a production comparison.
`smoke_document_review_postgres.py` exercises pending/cross-owner rejection,
reversible states and immutable snapshots on real PostgreSQL in an isolated
temporary schema. CI runs it plus a Java 17 helper build/hash validation job.
Deployed end-to-end checks remain a separate release gate.
`smoke_document_label_classifier.py` checks strict categories, preview bounds,
single-call behavior and redaction. `smoke_document_jobs_endpoints.py` runs real
authenticated routes with isolated JSON storage and a fake VLM: auto-start, hash
dedup, duplicate POST/import, human-vs-model races, stale status, ownership and
tombstone/history/media preservation. Real PostgreSQL tests also verify deletion
and cross-owner rejection. Fake model tests are not semantic accuracy evidence.
After release, `scripts/accept_document_classification.py --owner <approved-id>
--image <fixture> --output <new-directory> --allow-paid-calls` can probe 1-3 real
images through the gated production model configuration without creating orders.
It saves original bytes, model preview, pre-call claim and sanitized result/usage;
an existing output directory is rejected to prevent accidental replay.

Run checks from repository root unless stated otherwise.

## Public/workspace navigation

After integration with the Agent foundation, also run `test:agent`. Navigation
path tests cover Agent workspace URLs and context-domain resolution; the native
WebMCP fixture expects `/workspace` after opening overview and continues to check
logout revocation. Public routes must not mount the Agent provider.

Run `npm --prefix local_inspection_service/frontend run test:navigation` after
`npm ci` and `npx --no-install playwright install chromium` in the frontend.
The pinned development-only browser suite starts a loopback Vite server on port
5184 with fixture APIs, never a production account or model. `NAVIGATION_UI_OUTPUT`
selects screenshot/result output; otherwise a new temporary directory is used.
CI uploads the screenshots as `navigation-ui`.

Coverage includes public pages without auth dependencies, retryable auth errors,
old links with query/hash, safe login returns, login/logout failure and success,
ordinary-user permission denial, account-cache separation, session expiration,
404 behavior, website/documentation cards only inside About (no duplicate sidebar
links), both cards opening new tabs without reloading About, keyboard
guide navigation, desktop/mobile overflow and absence of camera/model/PLC writes.
`test_navigation_paths.cjs` executes the actual TypeScript path helpers with
malicious, encoded and malformed redirect fixtures. Production endpoint handling
is separately tested by
`python local_inspection_service/scripts/smoke_navigation_endpoints.py`, using the
real app and auth handlers with isolated runtime storage and a fixture SPA file.
It verifies direct refresh, old preview redirects, protected media/API errors and
public-guide vs admin-only API documentation boundaries. These browser fixtures
do not constitute a physical camera/PLC commissioning run.

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

The `vlm_bbox` experiment additionally requires `smoke_label_bbox.py` and `smoke_label_bbox_endpoints.py`: orientation, normalized rectangle rounding, zero-expansion pixel provenance, malformed/overflow/NaN coordinates, omitted single-label rectangles, separate account gate, input-media isolation, one-call idempotency, timeout without replay, immutable confirmation bytes and stale revision rejection. Browser acceptance switches the extraction method while an old result is pending and verifies it cannot overwrite the new method. Real-image logs must include actual inputs, raw bounded outputs, crop/overlay/detail images, independent visual failure descriptions, usage and unknown monetary charges explicitly. Do not turn manual correction, unreadable die lines or nine HTTP successes into nine automatic passes.

`smoke_label_extraction_postgres.py` runs against the CI PostgreSQL service in a disposable schema and verifies one-winner concurrent revision insertion plus account/root-scoped queries. For browser interaction, start Vite on port 5177 and run `smoke_label_extraction_browser.py` with development-only Playwright; `LABEL_TEST_BROWSER=msedge` selects an installed Edge. Its isolated fixture checks sub-pixel source-coordinate mapping across screen sizes, real React editing/confirmation state and absence of model calls during manual edits. No customer media is used.

## Agent foundation checks

Run `npm --prefix local_inspection_service/frontend run test:agent` for contract
generation and registry/adapter tests. Run
`python local_inspection_service/scripts/smoke_agent_operations_postgres.py` with an
explicit isolated `AGENT_TEST_DATABASE_URL` for real PostgreSQL transition and
authentication tests. `scripts/test_agent_webmcp.cjs` validates the native browser
API against in-memory endpoints, using the root Vite base and routing settings
listed in [implementation status](agent-platform.md). It executes tools without
DOM clicking. These tests do not prove full UI/tool coverage, external Agent
reasoning, physical PLC behavior or the planned load/latency targets.

The required frontend CI job runs `test:agent`, including bounded asynchronous
native-discovery polling and delayed result-channel cleanup regressions. Native
Chrome checks are separate: `scripts/test_agent_webmcp.cjs` covers the full-page
fixture and `scripts/test_agent_webmcp_lifecycle.cjs` covers the production adapter
on a synthetic page. Configure `PLAYWRIGHT_MODULE` and `AGENT_CHROME_PATH`; the
full-page fixture additionally needs `AGENT_UI_BASE`. Never use
`page.waitForFunction(async ...)` for native discovery in these tests: on the
verified Playwright version it can finish with a false resolved value. The shared
helper awaits observations, has negative timeout coverage, and retries no business
operations. Native suites are not yet CI gates; keep their browser version and
repeat-run evidence explicit.

## Codex comparison beta

Run `python -m pytest tests/codex_compare -q` with an explicit
`CODEX_TEST_DATABASE_URL` pointing to disposable PostgreSQL. Tests create random
schemas and cover concurrent admission/claim, writes, revisions, cross-owner
media, immutable snapshots, cancellation, stale recovery and CLI subprocess
lifecycle. No production DATABASE_URL fallback exists. The Linux CI job additionally
executes real bubblewrap isolation; macOS skips this Linux-only check.
Run `scripts/test_codex_compare_ui.cjs` against local Vite with `REVIEW_UI_BASE`,
`PLAYWRIGHT_MODULE` and optionally `QWEN_TEST_BROWSER`; all HTTP is synthetic.
It covers repeated-submit identity, refresh, incremental results, safe text,
evidence focus, review, account changes and mobile overflow, with screenshots.
Run frontend typecheck/build, existing text regression and docs/migration checks.
Real Codex/host and labeled-image commissioning remain separate requirements.

Proxy coverage validates explicit credential-free loopback configuration and real
Linux sandbox propagation, while rejecting inheritance of unrelated host proxy
variables. Commission actual device login and a real Codex turn on the target
host separately; proxy connectivity alone does not establish report accuracy.

Label-v2 tests additionally enforce additive checklist updates, immutable check
identity, full dimension coverage, linked issues, uncertain outcomes, dual-side
code evidence and original-normalized polygon bounds. The browser fixture covers
both legacy reports and incremental v2 elements, issue selection, polygon overlays,
problem filtering, literal injected text and mobile layout. The same disposable
PostgreSQL suite checks v2 revision/idempotency and retained selected reference bounds.
Real-library and intentionally modified samples must be reported separately from
real photographed pairs; neither synthetic tests nor successful exec establishes
conformity accuracy. Preserve per-dimension false-positive, false-negative,
uncertainty and elapsed-time measurements in private commissioning records.

`scripts/evaluate_label_cards.py private-cases.json` scores explicitly annotated
expected dimensions in exported reports. It separates real_photo, source_mutation
and synthetic samples and reports false positives/negatives among decided outcomes,
uncertainty, uninspected dimensions and mean elapsed time. Conditional precision/
recall must always be read alongside uncertainty and uninspected counts; they are
not full-population accuracy. Keep manifests, customer pixels and task exports in
private runtime storage, never Git. The script's input contract is in its docstring.

Label UI acceptance also asserts that the SVG viewBox follows image aspect ratio
and coincident issue/element markers have distinct label anchors.

Batch-v3 adds tests/codex_compare/test_batch.py to the existing PostgreSQL/CLI gate.
It checks durable drafts, idempotent uploads/submission, deduplicated references,
owner isolation, frozen media, selected human-corrected retries, scope validation
and one harness launch for batches of 1/5/10 actuals. Those harness tests use a
synthetic executable and are not real Codex quality evidence.

The required frontend job also runs scripts/test_label_batch_ui.cjs against
tests/label-batch.html: list-first entry despite a saved last-batch preference,
unified legacy/current task rows and earlier-page loading, new-task preparation
without empty-record creation, parent returns and draft reopening, two equal
panel widths at 1920/1440/1024/768/390 pixels with increased height and no workbench
overflow, extracted images inside the order panel without a separate tab, batch Word
upload, multi-image upload, refresh restoration,
single submit, frozen-task upload absence, problem ordering, preserved problem filter on
label return, separate label details, source markers, literal
injected text, account isolation and narrow-screen overflow. Screenshots use only
synthetic fixtures. Real batches separately measure correspondence accuracy,
manual-confirmation rate, per-dimension false results and completion within 600s.

`scripts/evaluate_label_batches.py` evaluates raw private batch task exports with
explicit label-to-standard and dimension annotations. It requires annotations for
every uploaded actual; unresolved matching stays in the accuracy denominator.
It reports wrong correspondence, confirmation and fully-checked proportions plus
per-dimension outcomes and elapsed batch time, grouped by sample kind. Do not mix
controlled source mutations with real photographed labels or claim a population
accuracy estimate from a small commissioning set.

The label browser fixture also delays a Word import response, leaves for the list,
and verifies that completion cannot pull navigation back to the abandoned task.

Invalid-image tiles are shown without enabling the hidden-standard filter and
remain non-selectable; limit failures retain their specific validation reason.


The label workspace browser fixture exercises native fullscreen entry before import,
root continuity, reload without an automatic request, explicit exit, denied fullscreen
without render retries, return-to-list cleanup, rename, and keyboard dock resizing.
Validate 1920x1080, 1440x900, 1366x768, 1024x768, 390x844 and a 683x384 effective
viewport (200% zoom equivalent): no document overflow, reachable result body/action,
and image aspect ratio preservation. Fixtures include 500 standards, 100 long issues,
60 histories and local scroll-boundary checks. Fullscreen actual device/Edge behavior,
OS Escape and native file pickers are additionally checked on release.

Native file pickers can exit browser fullscreen (including macOS Edge). The label
workspace remembers fullscreen only for that picker gesture and attempts restoration
on file selection while transient user activation is available. Cancellation, explicit
exit and navigation clear that intent; upload completion never forces fullscreen.
When restoration is unavailable the fixed viewport and manual toggle remain usable.

Compact issue regression verifies six visible rows at 1920x1080 and five at 1440x900, 16px single-line descriptions, full details including unlocated evidence, numbered existing boxes and selected-row highlight. Existing small-screen, local overflow, fullscreen, history, camera and navigation regressions remain required.

Run `python local_inspection_service/scripts/smoke_label_coordinates.py` for full-image/crop mapping, EXIF orientation, invisible sides, missing contract markers, nonfinite/out-of-bounds geometry and independent valid siblings. The PostgreSQL label smoke invokes these checks too. Before release, inspect real same-photo, rotated and multi-label outputs in the actual React workspace, preserving raw responses and overlays outside Git. Successful API responses alone do not establish localization quality.

## Label quality verification

`smoke_label_inspection.py` invokes `smoke_label_quality.py` in required backend CI.
Generated fixtures verify local rejection, unsupported/blank images, rotation,
small labels, mixed-quality multi-label selection, policy mismatch, exact prepared
JPEG/request-body equivalence, and zero/one/two provider calls. PostgreSQL tests
exercise saved policy/results, idempotency, account isolation, immutable standards,
restart non-replay and concurrent claims. No test calls a paid provider.

`scripts/replay_label_quality.py --manifest <private-json> --output <private-json>`
replays annotated real images, checks the fixed threshold grid against frozen
CONFIG and measures ten checks per image with P95 <500ms. Manifest entries contain
path, name and expected_pass; originals, annotations and output stay outside Git.
Do not use model verdicts as quality truth or count derivatives as independent data.

`scripts/test_label_workspace_ui.cjs` includes saved quality failure, absent model
scores, retry/camera access, historical unassessed message, full-screen navigation
and existing viewport/scroll regression. Inspect its quality-rejected screenshot.
Release acceptance also checks real clear/blurred photos, selected-label checks,
private history readback, production version and server-side latency.

The label PostgreSQL route smoke covers direct JPEG/PNG/WebP/BMP creation, Chinese filenames, original-byte preservation, EXIF orientation, transparent PNG, one-item grids/data, source filtering, idempotency, owner isolation and hide/restore revisions. Corrupt, mismatched, animated, unsupported and oversized images must return 422 without creating tasks. Workspace UI regression covers image selection/drop, image source filtering and the existing fullscreen, refresh, zoom and continuation flows. Live release acceptance imports one private standard image then checks actual-photo detection and persisted history.

## Independent purpose configuration

`python local_inspection_service/scripts/smoke_model_profiles.py` uses an isolated
PostgreSQL schema through `VANTALINE_POSTGRES_DSN`. It covers role denial, effective
migration fixtures, disabled assistant state, pending keys, same-model distinct
objects, new-version secret retention, restart, video scopes, incompatible models,
atomic concurrent saves, safe public projections and unpriced usage.
`node scripts/test_settings_ui.cjs` runs the real React/router against synthetic
HTTP fixtures: add returns to a pending selection, only Save commits bindings,
cancel restores values, members cannot see the library, and mobile does not overflow.
These tests make no live provider/device calls and do not certify detection accuracy.


## Unified PDF inspection

The real PostgreSQL smoke_label_inspection suite calls smoke_pdf_manual: synthetic rotated/landscape/portrait/square splits, atomic publication, checkpoint restart and stale-token fencing, account isolation, encrypted/invalid/excess-entry rejection and 0/1/2 provider-call contracts. It uses deterministic provider fixtures and never a paid model. Replay the private YATO source separately: 80 landscape pages must yield 160 entries left then right with helpers retained. UI checks cover PDF progress and read-only history in addition to existing fullscreen/grid/camera tests. Live rendered-photo acceptance must be labeled synthetic and record latency/tokens separately from real-photo accuracy.


PDF result compatibility: optional `consistentItems` entries may be strings or objects with a string `description`. Only that non-decision summary is normalized; raw provider evidence remains immutable. Missing/invalid descriptions and contradictory difference decisions still fail closed. Label parsing, PDF prompts, image inputs and model settings are unchanged. The PDF scope caption refers to page content rather than other labels. A regression covers enriched agreement summaries, input immutability and contradictory results.
