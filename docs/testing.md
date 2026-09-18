# Testing

`python scripts/smoke_text_revisions.py --root` adds nine synthetic groups: exact revision
write order and shared snapshot objects; baseline conflicts and partial failures;
expected-revision validation and snapshot compatibility; copied public projections
and legacy URL/error rules; diagnostic bounds/redaction/clock rollback; and real
image metadata with late logger replacement and hashed failure messages. The full
application contract asserts identical exports and logger composition. Existing
text endpoint modes, history, document jobs and model-binding checks remain required.
All six original groups first pass against the old entry-point implementation.
Added matrices require the same exception object and no retry for revision load,
baseline insert and final insert, preserving persisted baseline and shared mutated
snapshot evidence. Image/error hashing, logger acquisition and log output each
fail once with a succeeding second call available; later stages must not run.
Logger acquisition failure is a new explicit-port contract, distinct from the old
entry point's logger attribute lookup. Root A-to-B-to-C and missing-callback tests
retain the hash lookup window before message conversion, without logging that text.
Root tests disable Ultralytics automatic installation. Local Linux verification
uses the existing fail-if-called YOLO substitute and real image libraries.

`python scripts/smoke_text_media.py --root` adds eight groups using synthetic media:
path/account/hash/size checks and failed atomic replacement; resolved symlink
behavior; real PDF caching and cache-failure rules; PDF close/write/save failures;
original-byte versus image fallback behavior; provider copies/annotations, data URLs and similarity; and
application composition with dynamic resize policy. PyMuPDF is already in the
production lock. Local Windows lacks it, so this suite runs on Linux with real
PIL/cv2/PyMuPDF; only the root import uses the documented fail-if-called YOLO substitute.
CI uses the complete locked runtime. Source-fingerprint tests cover both new files
and preserve stored historical fingerprints.
The original six offline groups and a new failure group also pass against the old
entry-point implementation through argument adapters. Eight first-error cases make
a succeeding second call available for replacement, cached read, PDF load/render/
encode/close, page write and metadata save; the original error and partial evidence
must remain without retry or source rerender. Root tests preserve the owned callback
A-to-B-to-C capture window, missing-callable order and policy changes during image
open/transpose. Getter counts and passthrough/failure short circuits remain explicit.

`python scripts/smoke_text_record_store.py --root --postgres` runs eight groups:
nine table encodings and payload aliases; JSON unique keys/order/copy behavior;
account/status CAS and reentrant lock failures; exact SQL dispatch without JSON
fallback; real application lock/factory/table composition; and two independent
PostgreSQL connections racing insert-only and terminal updates. PostgreSQL uses an
explicit test DSN and disposable schema. Source contracts now inspect the extracted
implementation and all compatibility forwards; the minimum repository gate remains.
The original Beta smoke checks the revisions-table mapping in `record_store.py`
and verifies its composition binding in the entry point.
The root group replaces callbacks while paths and queries are evaluated, preserving
reader/writer/decoder capture order and missing-callable errors. Owned lookup still
resolves its decoder after a successful query and skips it for an absent row.
An A-to-B-to-C replacement matrix also rejects entry-time caching: prior factory
or read work selects B, argument evaluation selects C, the current call uses B,
and the next call uses C.
Nine first-error I/O cases allow a succeeding second call but require the original
error exactly once, with no JSON fallback or later write. Cross-thread nonblocking
lock probes cover the copy phase of save and the status comparison of CAS, including
the original nested lock and exception-release checks.

`python scripts/smoke_comparison_dependencies.py` has ten synthetic groups:
duplicate/conflicting requests and per-submission callback isolation; admission and
thread-start failure; durable unknown OCR cache with account isolation; both orders
of timer-versus-result settlement; dynamic local commissioning; settings alias/order
and missing usage recorder; distinct cleanup-failure sequences; and captured usage
across OCR, mapping and both region rereads. The eight original groups passed against
the current pre-migration implementation through argument-only adapters. Final save
and CAS failures now fail once with a succeeding second call available, preserving
the original exception and distinct cleanup order without retry. Two added groups
verify one unknown mapping call and one call per region/mode claim; a different
independent reread mode may still proceed under the existing algorithm. Existing
Qwen protocol, local-reread, audit/preview and six preparation endpoint modes remain
required, alongside the real PostgreSQL preparation smoke. No paid probe is run.
Preparation timeout contracts also invoke the actual Timer callback after dependency
replacement, preserving the late worker lookup and early HTTP writer capture.

`python scripts/smoke_preparation_dependencies.py` adds nine offline groups for
native HTTP timeout/CAS races, JSON write/lock ordering, PostgreSQL forwarding,
slot admission and thread-start failures, captured settings, late-result/source
changes and snapshot compatibility. The assembled application checks shared port
identity. Keep the six original endpoint modes and real PostgreSQL preparation
claim/publication/history/rollback smoke. The new port fixture is not a substitute
for real PostgreSQL. No real model or PLC is used.
First provider and final-publication failures are injected with a succeeding second
call available: neither may retry. Final-publication failure propagates before one
connection clear and slot release. Timeout tests replace the writer during timestamp
evaluation: worker settlement reads the replacement, while HTTP settlement retains
the writer captured before entering timeout. Missing and failing HTTP writers retain
their original failure ordering without retry.

Local Linux endpoint cross-checks use a fail-if-called YOLO import substitute
because that test environment lacks ultralytics; CI installs the locked runtime.
Windows recovery smoke exposed an intermittent `os.replace` access error in the
unchanged JSON helper. This batch does not change file locking or claim to fix it;
Linux cross-checks and required CI supplement, rather than erase, that evidence.

`python scripts/smoke_extraction_dependencies.py` adds six offline groups covering
native ASGI two-app isolation and returned resolver closures; frozen worker settings,
insert-only losers and save-failure cleanup; history-pinned/failed-tombstone retention;
and media authorization/hash/headers plus revision-loser file cleanup. File checks
use only disposable directories; symlink retention is checked where creation is
permitted. Original extraction/bbox endpoint tests and real PostgreSQL revision-race
smoke remain required. Windows endpoint tests need a short temporary root to avoid
the existing 271-character generated path; no production path behavior is changed.
Both workers propagate a first final-save error without retry, even when a second
save would succeed, and clear their connection once afterward. Exact-deadline and
just-after-deadline reads preserve the strict comparison and never settle storage;
the eventual worker result remains readable without launching a second call.

`python scripts/smoke_agent_dependencies.py` drives four original native-ASGI groups
before and after extraction: dynamic commissioning and PostgreSQL availability,
concurrent two-app account isolation, admin policy validation and error ordering,
and cancel ownership/version/error behavior with public-field filtering. Existing
real PostgreSQL operation smoke also passes before and after; only registration
fixtures change, preserving budget, unknown-outcome, concurrency and audit assertions.
A fifth group makes policy writes and cancellation transitions fail once while a
second call would succeed. Each writes once, preserves the original exception and
returns the existing generic HTTP 500; unknown outcomes never trigger a retry.

`python scripts/smoke_document_job_dependencies.py` adds nine offline groups for
native ASGI account isolation, JSON change-only writes and PG transaction forwarding,
admission/duplicate/thread-start failure, independent slot limits, durable attempts,
success/failure SHA reuse, human/deletion fencing and stale-job boundaries. It also
checks claim/load/finish failures and clear-before-slot-release ordering. The PG
adapter is a substitute; original document endpoint smoke remains intact and passes
before and after migration. Seven business methods and two handlers are AST-equivalent.
The worker retains the exact settings captured at admission after the resolver
changes. A first settlement failure is never retried even if a second attempt
would succeed; the attempt remains unresolved and cleanup runs once in order.

`python scripts/smoke_history_dependencies.py` covers seven isolated groups: native
ASGI concurrent account/app isolation and PostgreSQL adapter arguments; permission,
filter and cursor ordering; immutable revision/hash evidence failures; real PNG/JPEG
orientation and thumbnail behavior; and compatibility export/cursor/state semantics.
Invalid cursors fail before repository, JSON or media access. A verified reader's
first error propagates unchanged without a second read or rendering, even when a
second read would succeed; this covers all five supported media variants.
The PostgreSQL adapter here is a substitute; existing real PostgreSQL label smoke
and the original JSON-backed comparison-history smoke remain required. Original
functions and handler bodies were AST-compared before and after migration.

`python scripts/smoke_codex_dependencies.py` adds four groups for concurrent two-app
identity/repository isolation, frozen-source hashes, dynamic owner/model configuration,
capabilities without PostgreSQL, history/cancel after admission removal and endpoint-
specific upload-read/permission order. It also fixes shared-export identity and exact
report value semantics (bool/nonfinite boxes, boundary coordinates, whitespace and
summary keys). Five request classes and three pure validators were AST-compared.
All 55 existing Codex tests pass before and after migration with isolated PostgreSQL;
only the two registration fixtures changed, preserving the existing business assertions.

`python scripts/smoke_label_dependencies.py` adds seven isolated groups for two-app
configuration and concurrent identity isolation, async-to-thread repository acquisition,
prior None/empty/old model references, late resolver replacement and missing-provider
failure before inference. Deterministic thread/event substitutes exercise the actual
registrars: PDF then two detection threads, independent stops, claim/resolver/process
ordering, cleanup after repository/claim/model-resolution/process failures, and existing
one-/two-second idle waits. Cleanup-callback failure behavior is unchanged. Original
real PostgreSQL/PDF/import/call/concurrency/pagination smoke remains intact; only its
namespace fixture is replaced with explicit capabilities and a lazy asset reader.

`python scripts/smoke_accessory_routing.py` fixes five original real-HTTP groups:
401/403 and hidden ownership denial, retired/invalid-route ordering, trimmed but
case-sensitive values, default apply and non-applied AI routes, first matching ID,
shared config/item identity, provider failure with retained mutation and bounded error,
and separate save/task/projection failures. The same tests pass before and after
extraction using a real disposable auth store and provider/task substitutes.

`python scripts/smoke_accessory_preparation.py` fixes eight original-runtime groups
before and after migration: crop ordering/limits, empty-source results, exact object
plans, deferred-field cleanup, reference normalization, video expansion ordering,
refresh force flags, candidate ownership/aliasing, default-size arity, thumbnail
limits and partial files on provider/pose/save failure. Providers use substitutes;
no paid call, image worker or real PLC is started. Existing management/file/gallery,
immutable model snapshots and complete application contracts remain required.

`python scripts/smoke_image_job_metadata.py` fixes six original-runtime groups:
deterministic IDs and legacy aliases, anchor timestamps/hashes and strict read
errors, guide order/truncation/basename collisions, duplicate job identities,
snapshot deep copies/context binding and failure evidence. The original seven
bodies are compared before wiring. Existing actual-root candidate, model resolver,
real-PG candidate and full application gates remain. Source-fingerprint tests require
the migrated file and verify that changing each declared source changes the hash.

`python scripts/smoke_accessory_gallery.py` covers real image pixels (transparent,
partial-alpha, opaque and grayscale), preview sizing, unreadable input and the
existing unchecked image-write return. Synthetic HTTP cases fix gallery order,
deduplication, audit/asset metadata, explicit/default references, eighteen-sprite
limit before duplicate suppression, per-account redaction and path normalization,
shared-read authorization before preview writes and partial files on error.
The same five groups passed against the original implementation. Existing file,
management, model and complete-application contracts remain required.

`python scripts/smoke_accessory_management.py` exercises ten original HTTP
contract groups before and after management wiring: owner-scoped names, global
class allocation, upload residues, preview persistence, lock scope, active/failed
jobs, duplicate confirmation, missing-target repair, both text rejection paths,
profile call arguments and partial commits. PG removal branch ordering is tested
in an isolated HTTP composition with a storage substitute; it is not a real-PG
integration test. Full-app authentication uses a disposable real JSON store.
Existing real-PG repository and model-binding gates remain independently required.

`python scripts/smoke_accessory_files.py` runs six real-HTTP contract groups with
disposable images and provider substitutes. The same tests passed before wiring.
They cover shared-write denial, partial upload effects, crop limits and asymmetric
corner pixels, legacy job fields, data-directory deletion, provider fallback and
failure ordering. Four service bodies and HTTP signatures were compared against
the prior root implementation; the complete application and RBAC gates remain.

`python scripts/smoke_accessory_candidates.py --postgres --root` covers JSON repair,
atomic-file replacement failure, format/file-time ordering, exact PG lock/factory
order, no fallback, real HTTP denial/refresh and error cleanup. Isolated PostgreSQL
tests include concurrent repair/upserts, timestamp ordering and missing raw IDs.
The full-runtime fixture uses actual legacy job, anchor/guide and model-freeze
callbacks with a status-refresh substitute; it exercises the assembled root too.
Seven migrated function bodies were compared before wiring. The source gate reads
the actual candidate repository and validates all six root delegates; the assembled
gate verifies the same repository and RLock. No provider or device is contacted.

`python scripts/smoke_accessory_catalog.py --postgres` covers accessory policy,
projection, JSON mutation/failure, lazy PG capability/lock ordering and real HTTP
visibility, view modes, duplicate IDs and authorization before gallery side effects.
The isolated PostgreSQL fixture tests concurrent row updates, legacy raw payloads,
deletes and thread-owned connection cleanup. Migration validation compared sixteen
AST bodies, 448 policy outcomes and 24 full/summary results against actual root
dependencies before wiring. Existing full RBAC, model, HTTP and source contracts
remain required. The source gate now inspects the actual accessory repository and
root delegates; the dependency gate includes `accessories`.

`python scripts/smoke_record_access.py` verifies lazy administrator target lookup,
special owner IDs, literal legacy alias lookup, renamed/deleted/inactive accounts,
unchanged storage errors, explicit-user override, anonymous 401 and hidden 404.
Real ASGI requests cover shared-read/write denial, concurrent thread dispatch,
two isolated compositions and exception restoration. The assembled application
gate asserts auth/record services share the same identity and ownership objects.

`python scripts/smoke_record_audit.py` covers timestamp field priority, numeric
coercion, zero/negative/invalid values, unchanged infinite-value exceptions,
file errors, separate creation/update stat calls and shallow-copy behavior.
Six original function bodies were compared before wiring. Cost, analysis HTTP
and assembled application contracts exercise the existing consumers after wiring.

`python scripts/smoke_record_ownership.py` checks legacy field precedence, blank
owner fallback, shared users/wildcards versus malformed sharing values, read/write
distinctions, administrator filters and isolated owner configurations. Migration
validation compared the five function ASTs and 2,688 old/new outcomes before wiring.
Full auth/RBAC, actual analysis HTTP and assembled application contracts also pass.
The dependency boundary gate includes `records`.

`tests/codex_compare/test_worker_exit.py` runs the actual worker and event reader
under deterministic process/thread scheduling: exit before or during a heartbeat,
delayed EOF, nonzero exit, failed/missing completion events, cancellation and
deadline precedence. It verifies final metadata is persisted before completion and
scratch files are cleaned. It launches no process, model or database. The original
real PostgreSQL/CLI regression remains and includes allowlisted failure evidence.

The PLC frontend source contract locates the actual `analyze_bgr` AST body for
its no-dispatch assertion, rather than using an unrelated auth route as the end
marker. Ordinary-image, video and zero-server-serial checks remain in place.

`python scripts/smoke_auth_api.py` tests two independent HTTP compositions,
private-token exclusion, cookie persistence ordering under injected failures,
login-throttle key/threshold/window/expiry rules, revoked-session arguments and
reentrant-lock release after deletion failure. The original `smoke_auth_rbac.py`
now uses the existing synthetic model fixture and exercises all 13 label-local
permission guards through valid real HTTP requests. Its original cross-owner,
media, training, password and permission assertions are retained, and the full
suite passed before and after the auth API extraction. CI runs both suites.

`python scripts/smoke_auth_access.py` exercises actual account/session services and
ASGI middleware: dynamic settings/bootstrap, JSON expiry persistence throttling,
empty-store fallback versus indexed no-scan behavior, cookie attributes, parallel
identities across async/native threads and independent applications, exception
recovery, security/cache headers, media denial and exact RunPod public path/method
exceptions. The real PostgreSQL agent smoke now calls the actual `SessionService`
with full-store access configured to fail, retaining inactive/mismatched identity
assertions. No server-source function copy is executed by that test.

`python scripts/smoke_auth_foundation.py --postgres` covers permission/password
rules, JSON replacement and temporary-file cleanup, isolated PostgreSQL account
updates, concurrent sessions, raw/hashed legacy keys, expiry equality, login
revocation isolation and reentrant-lock release on failure. It uses synthetic
credentials and drops its own schema. The existing agent PostgreSQL smoke imports
the real extracted user lookup while retaining indexed request-auth assertions;
the source contract follows the actual auth repository. HTTP and navigation
contracts remain required.

`python scripts/smoke_analysis_projections.py` exercises actual processing/scope/
view/publication services with synthetic dependencies: manifest reuse, status
normalization, stable item merging, scope precedence, normal/admin debug fields,
list/detail limits, unavailable images, save-before-capture, persistence failure,
capture failure without retry, owner preservation and concurrent item upserts.
The real-server `smoke_data_analysis.py` additionally exercises nested cache scopes,
exception restoration and concurrent asyncio ContextVar isolation through the
migrated projection's explicit dependency port. No provider or device is contacted.

`python scripts/smoke_analysis_records.py --postgres` covers normalization,
legacy JSON shapes and atomic-file replacement, deterministic ordering, bounded
records, owner guards, row upserts/deletes and concurrent independent PostgreSQL
writes in a disposable schema. It checks no JSON fallback and connection release.
`smoke_data_analysis.py` now installs the existing model fixture and retains the
real HTTP detection-to-history assertions, plus cross-owner hidden 404s, denied
deletion preservation, internal missing_ok and repeated HTTP deletion.
The PostgreSQL source contract follows the actual extracted repository and checks
that public/HTTP deletion reaches authorization before persistence.

The unrelated `smoke_postgres_cutover_full.py --mode local-fake-postgres` currently
fails on its fake SQL parser's unsupported PLC advisory-lock SELECT. This failure
was reproduced on the pre-analysis baseline; the script is retained. It is not
evidence against actual PostgreSQL behavior, which the new isolated test exercises.

`python scripts/smoke_cost_ledger.py` uses synthetic records and temporary files
with real cost services/adapters: token aliases, cached/image/reasoning pricing,
unknown models, raw PostgreSQL-source precedence over stale JSON, stable call
IDs, metadata patterns, duplicate IDs, ordering, training durations, summary
filtering and administrator denial before any source read. It requires no paid
provider or customer data. The full assembled HTTP baseline still checks route
order and schema. `verify_backend_boundaries.py` includes `analytics`.

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
Its explicit package list currently covers `model_profiles`, `runtime` and `schemas`; each domain extraction
must extend it. Existing unconverted modules are not claimed compliant by this gate.

Request-schema extraction preserved each moved class's normalized AST. Continue
running the assembled OpenAPI/HTTP baseline and real navigation/auth, model routing
and PLC contract tests; source re-exports in the application preserve existing
test imports while new business modules import their domain schema directly.

`python scripts/smoke_runtime_lifecycle.py --postgres` runs native ASGI and thread-pool
requests for two identities with separate PostgreSQL connections, plus exception
cleanup, nested scopes, closed-connection rebuilding and generation invalidation
during connection creation. It requires the isolated `VANTALINE_POSTGRES_DSN`; omit
`--postgres` for the offline connection doubles. The original
`smoke_endpoint_runtime_store_probe.py` still checks the actual Web composition's
JSON default, redacted 503 errors, cache reuse and reset behavior. New release scopes
are tested infrastructure; existing HTTP request caching is not yet migrated to them.

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
