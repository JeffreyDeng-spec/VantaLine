`python scripts/smoke_plc_lease_rebind.py` replays the accepted v538 root against `VANTALINE_PLC_REBIND_BASELINE_SOURCE`; candidate execution checks the extracted state transition, strict in-flight deadline, shared fencing, late binding and independent A/B/A service instances. CI adds `--postgres` with an isolated schema for committed model rebinding and a real SQL write followed by rollback, IDLE transaction status and independent readback. No physical PLC or paid inference is used.

`python scripts/smoke_plc_lease_acquisition.py` replays claim and activation, with `VANTALINE_PLC_ACQUIRE_BASELINE_SOURCE` selecting the accepted v536 source. CI runs `--postgres` against an isolated schema to cover claim/activate persistence, duplicate claim rejection, and a real SQL write followed by rollback, IDLE status and independent readback. Offline cases cover preflight order, lease expiry boundaries, error priority, user capture, late binding and two-instance isolation.

`python scripts/smoke_plc_lease_maintenance.py` replays the extracted lease transitions; `VANTALINE_PLC_LEASE_BASELINE_SOURCE` points it at the accepted v534 source for original behavior. CI adds `--postgres` against an isolated schema to verify a committed heartbeat, fenced rollback, and draining release. The offline contract covers identity fencing, exact deadline boundaries, fallback clock, late binding and two-instance isolation.

With `VANTALINE_PLC_CONFIG_DIAG_BASELINE_SOURCE`, `python scripts/smoke_plc_config_diagnostics.py` replays the accepted v532 source; without it, the same command checks candidate root adapters. Offline cases cover empty/nondict config, validation short circuit, audit order/limit, in-flight shallow copy and lock scope, the POST permission-before-410 boundary, and candidate port isolation. Existing assembled HTTP/OpenAPI and PLC contracts remain required.

With `VANTALINE_PLC_DISPATCH_API_BASELINE_SOURCE`, `python scripts/smoke_plc_dispatch_diagnostic_api.py` replays the accepted v530 source; without it, the same command checks the candidate root callables. Offline cases cover five-route order/identity, diagnostic permission timing, unchanged 409 causes, late callee/error binding, partial-effect no-retry and candidate A/B/A port isolation. The existing assembled HTTP, PLC v4, frontend guard and release checks remain required.

With `VANTALINE_PLC_LEASE_API_BASELINE_SOURCE`, `python scripts/smoke_plc_connection_lease_api.py` replays the accepted v528 source; without it, the same command checks the candidate's preserved root callables. Synthetic tests cover operation order, payload identity, station/model denial, 409 cause, late callee/error binding and candidate-only A/B/A service isolation. The PLC v4, HTTP, source and release contracts remain required.

`python scripts/smoke_plc_workstation_management.py` replays the accepted v526 five workstation-management endpoints when `VANTALINE_PLC_MANAGEMENT_BASELINE_SOURCE` points to its `server.py`; otherwise it checks the candidate through preserved root callables. Windows/Linux synthetic cases cover paired/falsey stations, permission and error boundaries, late callee binding, partial cookie effects, and candidate-only constructor/A-B-A isolation. The backend boundary guard includes the new PLC package. Assembled HTTP, PLC v4, frontend source guard and release contracts remain required; no physical serial I/O or production data is used.

`python scripts/smoke_pipeline_stage_advance.py` replays the accepted v524 stage transition when `VANTALINE_STAGE_ADVANCE_BASELINE_SOURCE` points to its `server.py`; otherwise it checks the extracted service through the root adapter. Synthetic tests cover draft AI/locate/sample, cached recommendations, normalization 409/non-409 and save failures, sample/training guards, cancellation, late request binding and partial mutation without real jobs, paid model calls, PLC or customer data.

`python scripts/smoke_pipeline_advance_runtime.py` replays the v522 original guarded advance, runner, scheduler and cancellation functions when `VANTALINE_ADVANCE_RUNTIME_BASELINE_SOURCE` points to its `server.py`; otherwise it checks the extracted candidate. The v522 original passes twenty-two shared cases with three candidate-only skips; the candidate passes all twenty-five, including real decorated-root binding and independent A/B/A instances with all 25 capability getters observed. Synthetic cases cover two sync calls and lock placement, registry/Event partial failures, task snapshot/writeback identity, stale/deleted tasks, mid-step and post-step cancellation, late exception and mapping bindings, and cleanup/config order without real PLC, paid inference or customer data.

`python scripts/smoke_pipeline_auto_agent_runtime.py` replays the v520 original auto-Agent runner/scheduler when `VANTALINE_AUTO_AGENT_RUNTIME_BASELINE_SOURCE` points to its `server.py`; otherwise it checks the extracted candidate. The original AST passes seventeen shared cases with three candidate-only skips; the candidate passes all twenty, including real decorated-root binding and two-instance A/B/A. Synthetic cases cover lock boundaries, deep-copy isolation, stale signatures and second reads, exact step-limit pause, partial failures, late callbacks, registry cleanup and scheduling without paid inference, physical PLC or customer data.

`python scripts/smoke_pipeline_recommendation_runtime.py` replays the v518 original runner and scheduler when `VANTALINE_RECOMMENDATION_RUNTIME_BASELINE_SOURCE` points to its `server.py`; otherwise it checks the extracted candidate. The original AST runs eleven shared cases with three candidate-only skips because its decorator is removed for isolated replay; the candidate runs all fourteen, including two real decorated-root binding cases. Synthetic cases cover lock order, skipped/stale tasks, saved parameters, errors, model binding before request identity, duplicate scheduling, failed thread start, reset failure and independent A/B/A instances. It uses no paid model, physical PLC or customer data.

# Testing

`python scripts/smoke_pipeline_trained_model_link.py` replays the v516 root linker when `VANTALINE_MODEL_LINK_BASELINE_SOURCE` points to its `server.py`; otherwise it checks the extracted candidate. Synthetic cases cover first-match identity, fallback fields, catalog rebinding, expression order and error partial effects without real models, PLC or paid calls.

`python scripts/smoke_pipeline_training_status.py` replays the accepted-main lookup and synchronization functions when `VANTALINE_TRAINING_STATUS_BASELINE_SOURCE` points to its `server.py`; otherwise it tests the extracted candidate. Synthetic cases cover loader selection, late projection, state mapping, epoch reads and exception partial effects. No real PLC or paid model is used.

`python scripts/smoke_pipeline_reconciliation.py` replays the accepted-main four-function contract when `VANTALINE_RECONCILIATION_BASELINE_SOURCE` points to its `server.py`; otherwise it exercises the extracted service. Synthetic scenarios cover eligibility, zombie timeout boundaries, ordering, finder identity, duplicate IDs, partial effects and late callback rebinding without external services.

`python scripts/smoke_pipeline_accessory_routes.py` replays accepted-main add/remove routes when `VANTALINE_ACCESSORY_ROUTES_BASELINE_SOURCE` points to its `server.py`; otherwise it tests the candidate. Synthetic Windows/Linux cases cover canonical resolution, alias iteration order, repeated aliases, partial failures, payload overrides and callback rebinding. Candidate-only constructor, HTTP and A/B/A checks use no real PLC, paid inference or customer data.

`python scripts/smoke_pipeline_agent_feedback.py` replays accepted-main feedback when `VANTALINE_FEEDBACK_BASELINE_SOURCE` points to its `server.py`; otherwise it tests the extracted candidate. Synthetic Windows/Linux action and exception cases cover feedback-before-validation, sprite/legacy pose branches, lock placement, saves and unlocked scheduling. No paid image calls, physical PLC or customer records are used.

`python scripts/smoke_pipeline_task_list.py` replays the accepted-main GET when `VANTALINE_LIST_BASELINE_SOURCE` points to its `server.py`; otherwise it tests the candidate. Synthetic Windows/Linux scenarios cover the shared throttle, exception timing, config/save distinctions, all-task filtering, duplicate scheduling, late callbacks and projection order. Candidate-only constructor, A/B/A and HTTP adapter checks use no paid inference, PLC or customer records.

`python scripts/smoke_pipeline_agent_chat.py` replays accepted-main Agent chat when `VANTALINE_CHAT_BASELINE_SOURCE` points to its `server.py`; otherwise it checks the extracted candidate. Synthetic Windows/Linux cases cover permission and method gates, deep snapshot, one decision between two locks, late callbacks, partial failures and duplicate scheduling. Candidate-only constructor, A/B/A instance and focused HTTP checks use no paid model, real PLC or customer data.

`python scripts/smoke_pipeline_advance_control.py` replays the accepted-main advance/cancel endpoints when `VANTALINE_ADVANCE_CONTROL_BASELINE_SOURCE` points to its `server.py`; without that setting it runs the candidate. Windows/Linux synthetic cases cover task and registry locks, repeated requests, double cancellation load, partial failure effects, callback timing, second-clock failure, registry membership under lock and state transitions. Candidate-only zero-read constructor, A/B/A and focused HTTP adapter checks use no real PLC, paid model or customer data.

`python scripts/smoke_pipeline_task_delete.py` runs the accepted-main DELETE function when `VANTALINE_DELETE_BASELINE_SOURCE` points to its `server.py`; without that setting it runs the extracted candidate route. Synthetic Windows/Linux cases cover cancellation before access, 403/404, lock position, linked-ID filtering and duplicates, resource cleanup order, partial effects and callback rebinding. Candidate-only constructor and A/B/A checks verify explicit capabilities. No paid model, physical PLC or customer data is used.

`python scripts/smoke_pipeline_task_create.py` runs synthetic creation scenarios against the current candidate; setting `VANTALINE_CREATE_BASELINE_SOURCE` to an accepted-main `server.py` replays the original function. Both modes were run on Windows/Linux locally, covering permissions, owner fallback, field construction order, two-phase AI saves, callback rebinding and partial effects after failures. Candidate-only constructor and A/B/A instance checks verify explicit capabilities. No paid model, physical PLC or customer records are used. The legacy incoming-text smoke follows the creation branch in `pipeline/task_create.py` and checks its route registration in `server.py`.

`python scripts/smoke_pipeline_task_update.py` uses synthetic tasks to verify PATCH endpoint identity, late callback selection, partial mutation before 409, incoming-material and ordinary projection lock positions, save/projection failures, non-draft parameter updates and OverflowError propagation. The backend contract also checks route order, schema and operationId; no paid provider or PLC is accessed.

`python scripts/smoke_pipeline_resource_status.py` covers 21 original behavior groups on accepted main and one independent three-reader A/B/A group after extraction, on Windows and Linux. It checks deleted/none/available/pending/missing precedence, supplied empty collections, first matching spec, filesystem checks, callback rebinding and exception identity. Synthetic tests perform no real PLC or paid inference.

`python scripts/smoke_pipeline_task_snapshots.py` covers 16 original Windows/Linux label and accessory-name projection cases on accepted main plus one independent two-instance A/B/A group after extraction. It checks first-match linked AI labels, original fallback order, callback timing, alias/order retention and exception propagation. It uses synthetic records and no real model, PLC or customer media.

`python scripts/smoke_pipeline_recommendations.py` covers 21 original synthetic helper groups on the accepted main plus one independent two-instance A/B/A group after extraction. Both platforms verify signature formatting and failure propagation, stage/ready gates, stale-cache consumption, shallow aliasing, partial mutation and late callback rebinding. The independent fixture exercises all five capability getter names on representative successful paths. The pinned background worker, paid recommendations and production database are outside this focused suite.

`python scripts/smoke_pipeline_ai_task_sync.py` covers 17 root-compatible synthetic behavior groups (13 before extraction, 17 against accepted-main AST) and one independent composition group after extraction. It checks visibility, duplicate IDs, reverse insertion, existing object identity, paused state, default loading, partial errors and late root bindings. Independent A/B/A service instances exercise all 14 capability getter names on representative success paths without root business callbacks. This does not use real models, PLC, customer records or a production database.

`python scripts/smoke_pipeline_background_publication.py` retains 24 original groups
and adds one independent two-instance A/B/A group: 150 method assertion sites plus two
bootstrap guards. Synthetic contracts preserve prompt text, selection and provider
ordering, settings mutation, manifest/task partial effects and strict final hashing.
They use local temporary images and provider substitutes; real paid calls and PLC I/O
are outside this test.

`python scripts/smoke_background_library_selection.py` retains 18 original groups and
adds one independent A/B/A group for both services: 83 method assertion sites plus two
bootstrap guards. Synthetic contracts cover sharing, sorting, aliases, source
precedence, caps, callback selection, signature refresh, rounded comparisons and
threshold boundaries. Cap representatives include zero and positive values. Independent
fixtures cover all 17 getter names cumulatively per instance with injected matcher
candidates; they do not establish exact per-invocation read counts, every image failure
or the full catalog-to-matcher chain.

`python scripts/smoke_background_evidence.py` preserves 18 original groups and adds one
two-instance A/B/A group for both services: 90 method assertion sites plus two bootstrap
guards. Synthetic fixtures cover numerical representatives, source order, time boundary,
strip ties, capped dimensions, seeded fill, write failures, late reads, patch caps and
dictionary aliases. Inpaint coverage includes deadline equality, radius cap and fraction
gates at 0 and 1, not exact mask-fraction equality. Independent paths use substitutes
and getter logs for all 14 fields; they do not prove every image branch, default chain
or real-image quality.

`python scripts/smoke_accessory_profile_generation.py` retains 18 original groups and
adds one same-class two-instance check: 109 test-method assertion sites plus two
bootstrap guards. Contracts preserve prompt SHA, eager defaults, callback timing,
aliases and partial failures. Independent instances use substituted collaborators across
all three methods and 14 getters; callable poison non-invocation is combined with getter
logs and static free-name checks. This is not full default-chain, model or device
commissioning.

`python scripts/smoke_accessory_profile_payloads.py` retains 18 original groups and adds
one same-class two-instance check. The 19 groups contain 79 test-method assertion sites
and two bootstrap guards. Original coverage preserves prompt strings, aliases, counts,
repeated reads, callback selection and partial failure behavior. The independent fixture
exercises three methods and eight getters through substitute identity/profile/catalog
collaborators; it does not establish all default helper chains or failures.

`python scripts/smoke_accessory_dimensions.py` retains 18 original groups and adds a
same-class two-instance check. The 19 groups have 64 test-method assertion sites and two
bootstrap guards. Original coverage includes eager default mapping evaluation, lazy
normalization fallback and late payload selection with failure-state preservation. The
independent fixture calls all five methods and capabilities using substituted numeric,
material and payload callbacks; it does not establish every default chain or failure
path.

`python scripts/smoke_accessory_profile.py` preserves 20 original groups and adds one
same-class two-instance check. The 21 groups contain 73 test-method assertion sites plus
two bootstrap guards. Original coverage distinguishes real optional_float from a
permissive substitute, retains partial evaluation order and checks reference aliases and
conversion errors. The independent fixture exercises both methods and all 15 getters
with substituted collaborators; it does not prove complete internal chains or every
failure path.

`python scripts/smoke_accessory_labels.py` retains 20 original groups and adds one
same-class two-instance composition check. The 21 groups contain 71 test-method
assertion sites plus two bootstrap guards. Original fixtures preserve ordering,
capitalization, partial-state errors and policy refresh. The independent fixture
substitutes compact/preferred/string callbacks; it does not prove complete internal call
chains, every failure case or independent standalone size projection.

`python scripts/smoke_reference_evidence.py` preserves 23 original groups and adds one
same-class two-instance composition group. The 24 groups contain 101 test-method
assertion sites plus two bootstrap guards. Synthetic files and substituted decoders,
context and mask callbacks verify representative behavior and instance isolation, not
complete internal caller chains or every I/O failure. The independent fixture leaves
first-source and inventory fallback callbacks unused.

`python scripts/smoke_preview_assets.py` preserves 18 original groups and adds one
same-loader two-instance composition check. The 19 groups contain 86 test-method
assertion sites plus two bootstrap guards. Synthetic files and injected
decoders/candidates/selectors cover representative loading and fallback behavior, not
exhaustive I/O failures or independent standalone selection.

`python scripts/smoke_compositing.py` retains all 19 original groups and adds one
same-class two-instance composition check. The 20 groups contain 102 test-method
assertion sites plus two bootstrap guards. Synthetic fixtures cover representative
zero-angle paste, crop, interpolation, alpha and callback ordering; they do not
establish exhaustive rotated-pixel or partial-failure behavior.

`python scripts/smoke_preview_sprites.py` preserves 23 original test groups and adds one
independent two-instance renderer composition check. The 24 groups contain 95
test-method assertion sites plus two bootstrap guards. Representative non-AI
preprocessing, top-view selection and injected rotation prove separation of the two
instances; standalone decoder behavior has original synthetic coverage, not exhaustive
I/O/failure commissioning.

`python scripts/smoke_materialized_assets.py` retains 21 original synthetic groups and
adds one independent two-service composition check. It covers nullable decode, metadata
precedence and aliases, explicit-empty bypass, short circuits and callback timing.
Independent instances produce distinct metadata and use separately counted readiness
callbacks; both readiness examples pass, so they do not establish all failure paths.

`python scripts/smoke_preview_pose_policy.py` retains 21 original synthetic groups and
adds one independent composition check. It covers alias order, raw intersections, nullable
results, sequence/label rules and callback selection before conversion or formatting.
Two distinct service instances exercise all six methods and both error factories with
root callbacks poisoned and checked unused; this is not exhaustive input or real I/O coverage.

`python scripts/smoke_pose_policy.py` retains 22 original synthetic groups and adds two
independent compositions. It covers representative grid rotation, definition-time defaults,
callback lookup timing, filtering thresholds and exception propagation. Distinct service
instances exercise successful paths; this does not establish every input, failure or real I/O.

`python scripts/smoke_cutout_geometry.py` retains 24 original synthetic groups and
adds two independent composition checks. It covers representative color conversion,
component selection, crop aliases, fallback coordinates and callback timing. Independent
services cover successful paths; selection fallback remains in original fixtures.
Synthetic arrays do not establish all numerical branches or real image quality.

`python scripts/smoke_cutout_runtime.py` retains 12 original synthetic groups through
explicit fixture state access and adds three independent runtime/composition cases.
Tests cover lazy caching, held/reentrant locks, a coordinated cold-start schedule,
exception boundaries and successful consumer isolation. They do not prove all thread
schedules, pixel branches or real-model/device acceptance.

`python scripts/smoke_material_alpha.py` retains 17 original synthetic groups and two
independent composition checks. It covers opacity thresholds, morphology order, edge
evidence, dispatch timing and the actual legacy alpha helper under isolated fixtures.
Independent services cover simple successful transparent/opaque paths, not every pixel
or failure branch. The customer-media-dependent full legacy script is not acceptance.

`python scripts/smoke_sprite_publication.py` retains 23 original synthetic groups and two
independent constructor/composition cases. Tests cover encoded alpha, write failures,
partial metadata state, resize limits and callback selection. Independent services exercise
successful single/batch paths; these tests do not establish production storage atomicity
or physical/model/device acceptance.

`python scripts/smoke_sprite_metadata.py` preserves 22 original synthetic metadata groups,
four lookup-order cases and two composition checks. Tests cover zero image access on
metadata hits, bypasses, alias identity and partial updates. Independent services exercise
footprint/scale calculations and visible/render-size flows, not every update branch.
Synthetic fixtures do not establish physical accuracy, real model or device acceptance.

`python scripts/smoke_sprite_geometry.py` retains 15 original synthetic geometry groups,
three callback-timing cases and two composition cases. Independent instances exercise
upright, visible-size and resize operations; PCA/affine behavior uses original fixtures.
Tiny masks and injected callbacks do not establish production vision or device acceptance.

`python scripts/smoke_object_preprocessing.py` covers 27 synthetic groups: original
fallback/partial-state/exception contracts, four lookup-timing cases and two independent
composition cases. Synthetic arrays and collaborators do not establish real model or
vision accuracy. Every poisoned root business callback is asserted unused.

`python scripts/smoke_crop_components.py` covers 19 synthetic groups: 14 original image
contracts, three dependency-order cases and two composition checks. Tiny masks verify
strict thresholds, cap/order, copy/identity, focus padding, anchored support and diagnostics.
Every poisoned root callback is checked unused in independent instances. These fixtures
do not establish production vision accuracy or device/model commissioning.

`python scripts/smoke_photo_highlight_builder.py` exercises 27 synthetic groups: 21 original
workflow contracts, four dependency-refresh cases and two composition checks. Tests cover
provider and file failures, rejection, partial sources, metadata and final policy reads.
Independent instances execute synthetic successful flows with every root callback poison
verified unused, including audit exceptions that the original workflow intentionally catches.
This is not real inference, vision-accuracy or device commissioning.

`python scripts/smoke_photo_highlight_image.py` covers 19 synthetic helper groups: original
14 image/prompt contracts, three lookup-order checks and two independent composition
checks. Tiny arrays cover scaling, component decoding, available ROI and comparison
boundaries. Numerical libraries are explicitly imported shared modules; attribute patches
remain supported. Tests do not claim production vision accuracy or paid-model acceptance.

`python scripts/smoke_photo_highlight_workflow.py` exercises 26 synthetic contracts: original
20 behavior checks, four dependency-order checks and two independent-service checks.
Source limits retain definition-time defaults; tests cover readiness, selected object identity,
legacy state, configuration pauses and partial failures. Actual mask inference and the full
retired-worker legacy workflow are outside these tests.

`python scripts/smoke_agent_pose_materialization.py` covers 25 offline groups: 19 original
contracts, four dependency/hash-order checks and two constructor/composition checks. Tiny
synthetic arrays, private files and substituted cutout/codec callbacks exercise fallback order,
reference aliases, metadata, partial state and the post-write sprite cap. Source guards follow
the actual materialization method. Prior pose and isolated phase3d decision contracts remain;
no real inference, device or complete legacy retired-worker workflow acceptance is claimed.

`python scripts/smoke_agent_pose_execution.py` covers 23 offline groups: 17 original contracts,
four dependency-order checks and two constructor/composition checks. Synthetic providers
verify cache/no-op paths, exact call arguments, reference aliases, failure boundaries and
partial state without paid inference. Source guards follow the actual registration method.
The active phase3d decision helper and pose-render contracts remain; the complete legacy
retired-worker workflow and physical-device acceptance are not claimed.

`python scripts/smoke_agent_pose_render.py` covers 21 offline groups: 15 original contracts,
four evaluation/error-order checks and two constructor/composition checks. Synthetic fixtures
verify exact prompt text, reference aliases, callback lookup and partial artifact writes.
Injected digest failures test collaborator failure. A None-returning substitute checks result
propagation; the production root resolves the strict training hash helper, whose read errors escape.
The phase3d SynthID source guard follows the actual writer. Its active decision helper
remains separately tested; full legacy retired-worker or device acceptance is not claimed.

`python scripts/smoke_pipeline_decision_contract.py` runs the actual phase3d decision
helper offline, preserving its eight assertions for rules, parameter bounds, unknown actions,
empty synchronization and AI/YOLO eligibility. Empty synchronization verifies all three
outputs with scoped configuration/storage substitutes. The runner isolates temporary files
and blocks external operations before imports, regardless of inherited PostgreSQL settings.
The source-only phase3d check remains separate. Full legacy phase3d execution is not claimed:
its retired-worker enabled-by-default expectation remains stale.

`python scripts/smoke_agent_pose_planning.py` covers 21 offline groups: 15 original contracts,
four dependency/error-order checks and two constructor/composition checks. Synthetic model
tools verify cache identity, unchanged provider arguments, exception boundaries and partial
updates. The phase3d source guard follows the actual task-plan assembly method; full legacy
pipeline or device commissioning is not claimed.

`python scripts/smoke_agent_pose_assets.py` covers 21 offline groups: 15 original contracts,
four dependency-order checks and two constructor/composition checks. Synthetic paths and
objects verify asset aliases, readiness/rebuild gates and unchanged template requests.
The phase3d source guard follows the actual missing-asset validation method; full legacy
pipeline or device commissioning is not claimed.

`python scripts/smoke_agent_state.py` covers 21 offline groups: 15 original contracts, four
lookup/evaluation-order checks and two construction/composition checks. Synthetic fixtures
cover timestamps, nested aliases, call identity, partial state and stage metadata forwarding.
The existing phase3d source contract follows the sample/training log implementation methods;
this does not claim complete legacy pipeline or physical-device commissioning.

`python scripts/smoke_agent_pipeline_actions.py` covers 26 offline groups: 17 original
contracts, seven failure/evaluation-order checks and two construction/composition checks.
Synthetic callbacks verify pending-advance collection, linked-job cleanup, parameter aliasing,
partial updates, exception matcher lookup and turn ordering without paid execution. The
existing phase3d source guard follows the actual turn method; full legacy phase3d execution
is not claimed by this source check.

`python scripts/smoke_agent_pipeline_decisions.py` exercises 21 offline groups: 13 original
behavior contracts, six evaluation-order/failure checks and two construction/isolation checks.
Synthetic snapshot scopes, task dictionaries and model responses cover retained bindings and
exception boundaries. The phase3d source contract now reads actual implementation methods and
the current relative workspace route; its existing assertions remain. This source check does
not claim full pipeline, paid model or physical-device commissioning.

`python scripts/smoke_agent_settings_api.py` covers 17 offline groups: ten original HTTP
and handler contracts, five callback/failure-order checks and two construction/isolation checks.
Tests use the actual registered route objects in an isolated FastAPI app, without production
middleware or lifespan; this is handler-level HTTP coverage, supplemented by existing auth and
backend contracts. All original source bodies, including disabled legacy code, are retained.

`python scripts/smoke_agent_invocation.py` runs 26 offline groups: 12 original behavior
contracts, 12 capture/failure/accounting checks and two construction/isolation checks. Simulated
responses exercise the existing bound provider and accounting flow; a ledger failure must not
repeat a successful request. Request identity is checked across two contexts. No real provider
request, paid inference, production record or physical PLC is used.

`python scripts/smoke_agent_settings.py` exercises 21 synthetic offline groups: 12 original
contracts, seven evaluation-order/failure checks and two construction/isolation checks. Two live
compositions are called first, second, first to detect shared state. Tests use private temporary
files and model substitutes, without external provider calls or physical PLC access.

`python scripts/smoke_key_material.py` exercises 20 offline groups with synthetic secrets
and private temporary directories. Twelve original contracts are retained, plus six dependency
capture/failure cases and two construction/isolation cases. File replacement failure preserves
the old file and environment; tests do not read real secrets or make external calls.

`python scripts/smoke_provider_key_registry.py` runs 19 offline groups: the original 12
contracts, callback capture and refresh, six ordinary/prior/missing capture traces, zero
constructor reads and independent compositions. It verifies environment precedence, legacy
compatibility, deduplication, safe public fields and filter object identity using synthetic keys.

`python scripts/smoke_provider_configuration_policy.py` runs 19 offline groups, preserving
12 original groups and 17 expanded original-body groups verified on Windows/Linux. Tests cover
eager default lookups, provider/model/URL/timeout errors, public URL redaction, callback capture
and independent services. Inputs are synthetic and external operations are forbidden.

`python scripts/smoke_legacy_provider_settings.py` runs 23 offline groups, preserving
12 original groups and 21 expanded original-body groups verified on Windows/Linux. Coverage
includes distinct JSON/image key precedence, environment refresh, dynamic exception matching,
nested callback capture and independent compositions. All keys and settings are synthetic.

`python scripts/smoke_public_status.py` runs 18 offline groups. All 12 original groups and
16 expanded original-body groups passed on Windows/Linux before extraction. Tests preserve
field filtering, admin identity, permission short-circuiting, sanitizer evaluation order and
source immutability. Independent compositions use poisoned application callbacks and retain
no request state. All accounts, settings and media references are synthetic.

`python scripts/smoke_provider_orchestration.py` runs 24 offline groups, retaining all
16 original behavior groups. The 22 expanded original-body groups passed on Windows/Linux
before extraction. Tests cover selection, bound/cached fallback guards, existing retry budgets,
key rotation, failure usage, dependency timing and independent compositions. Model substitutes
and fake timing avoid paid requests, production data and physical devices.

`python scripts/smoke_image_provider_transports.py` runs 29 offline groups. The original
18 groups and 27 expanded original-body groups passed on Windows/Linux before extraction.
Synthetic transport/download failures, dynamic exception matching, dependency capture, size
configuration and accounting checks retain original behavior. Independent instances own their
resolvers and state. No paid model calls, production media or physical devices are used.

`python scripts/smoke_gemini_transport.py` runs 28 offline groups. The original 15
behavior groups and 25 expanded original-body groups passed on Windows/Linux before extraction.
Synthetic requests cover JSON, cached-content and image paths, captured cache defaults, model
resolvers, usage/raw-text state, proxy diagnostics, resource errors and first-failure boundaries.
No live provider, production media, model inference or physical device is accessed.

`python scripts/smoke_openai_transport.py` runs 32 offline groups, preserving the original
20 behavior groups and 29 expanded original-body groups. `smoke_provider_metering.py` runs
16 groups, retaining 12 original accounting contracts and adding instance concurrency, nested
calls and resolver replacement. Tests use synthetic settings, responses and accounting services;
network, process and device operations are forbidden. Full method AST comparison preserves the
original transport algorithm after explicit dependency substitution.

`python scripts/smoke_provider_foundations.py` runs 26 offline groups. The original 18
business groups and 23 expanded original-body groups passed on Windows/Linux before migration.
Contracts cover exception inheritance/metadata, old and new serialized import paths, exact HTTP
classification, JSON/data-URL semantics, dependency capture and the original JSONDecodeError catch
boundary. First-error recovery tests reject retries; independent services avoid root dependencies.
All input is synthetic and network/process/device operations are prohibited by the test harness.

`python scripts/smoke_detection_media.py` runs 27 offline groups. Twenty original
business groups and 25 expanded original-body groups passed on Windows/Linux before migration.
Synthetic arrays/files cover JPEG encoding, alpha/gray tiles, reference ordering, sheet layout,
cache/path isolation and original failure/partial-file boundaries. First-error recovery matrices
cover injected capabilities, filesystem calls and input/cache mappings; capture and refresh checks
retain callable selection and both locked cache accesses. No production media, real model
or paid provider is used. The MCP registry retains the actual reference-collection adapter.

`python scripts/smoke_detection_upload.py` runs 24 offline groups. The 17 original
business groups and 21 expanded original-body groups passed on Windows/Linux before migration.
Contracts retain uploaded-file evidence, image decode errors, video sampling/limits, per-frame
callback refresh, AI projection aliases and model-snapshot restoration. First-error recovery
matrices prohibit retries at file, callback and dependency boundaries. The actual HTTP routes and
PLC guard follow the moved implementation; structural mutations must be explicitly rejected.
Synthetic images/videos and providers avoid paid inference, cameras and physical PLC activity.

`python scripts/smoke_profile_cache.py` runs 30 synthetic groups. Twenty-one original
business groups and 26 expanded original-body groups pass on Windows/Linux. Contracts
retain canonical keys, exact prompts, reference order, expiry margins, write permissions,
atomic replacement and partial-file/record effects. Provider creation still records the same
single-call evidence and failure result; no replay is introduced. Explicit path, provider,
clock and formatting capabilities retain original evaluation order without constructor I/O.
Temporary files and synthetic providers avoid production records and paid inference.

`python scripts/smoke_presence_inspection.py` runs 29 synthetic groups. Twenty original
business groups and 25 expanded original-body groups pass on Windows/Linux. Contracts
retain exact prompts, cache budgets, image/reference selection, timing and metadata order.
Only a successful uncovered Qwen result permits the existing one coverage retry; exceptions
and unknown outcomes do not create another provider attempt. First-error recovery matrices
cover early failure paths, provider/policy reads, JSON rendering and partial result mutations.
Independent services use explicit capabilities; the MCP tool registry retains the actual adapter.
Models, transports and images are synthetic; tests do not access real devices or paid inference.

`python scripts/smoke_detection_analysis.py` and `python scripts/smoke_ai_detection_analysis.py`
run 20 and 20 synthetic groups. Original Windows/Linux baselines passed 12 and 13 groups;
expanded original-body replays retain 15 and 16 groups. Contracts cover routing, confidence bounds,
provider/read failure, partial profile/output effects, callback selection and per-item refresh.
Independent services retain snapshot scope and late policy reads. The PLC source guard follows
both actual business methods, their constructors/imports and the pinned AI adapter; existing
source assertions remain and reject dispatch or model-binding bypass. Synthetic models, callbacks
and images avoid external inference, production data and physical devices.

`python scripts/smoke_detection_annotation.py` runs 21 synthetic groups.
Fifteen original business groups passed before migration on Windows and Linux;
18 expanded groups also pass against saved original function bodies. Contracts retain
geometry rounding, strict coordinate types, drawing order, image copies and output behavior.
Backend policies refresh at original expression boundaries. First-failure recovery fixtures
reject hidden retries; existing partial-file residues and None-only fallback remain intact.
Synthetic images and image-backend substitutes avoid models, production media and device I/O.

`python scripts/smoke_presence_results.py` runs 19 synthetic groups.
Fourteen original business groups passed before migration on Windows and Linux;
17 expanded groups also pass against saved original function bodies. Contracts retain
count precedence, confidence bounds, duplicate IDs, provider metadata merge order and field reads.
Policies refresh between required items. First-failure recovery fixtures reject hidden retries;
TypeError/ValueError count fallback behavior remains unchanged.
No paid model calls, external requests or device operations run in these contracts.

`python scripts/smoke_detection_failures.py` runs 20 synthetic groups.
Twelve original business groups passed before migration on Windows and Linux;
16 expanded groups also pass against saved original function bodies. Contracts retain
failure records, provider metadata merge order, model projection aliases and exact field reads.
Callbacks refresh after ID conversion and between items. First-failure recovery fixtures reject
hidden retries without incidental failures. Existing error propagation remains unchanged.
No paid model calls, external requests or device operations run in these contracts.

`python scripts/smoke_presence_contracts.py` runs 20 synthetic groups.
Thirteen original business groups passed before migration on Windows and Linux;
17 expanded groups also pass against saved original function bodies. Contracts retain
exact payload text, count coercion, response coverage and double-read order. Five formatter
getters preserve callee selection before arguments and after prior conversions. First-failure
fixtures reject hidden retries; existing TypeError/ValueError count fallbacks remain intact.
No paid model calls, external requests or device operations run in these contracts.

`python scripts/smoke_accessory_requirements.py` runs 21 synthetic groups.
Fifteen original business groups passed before migration on Windows and Linux;
19 expanded groups also pass against saved original function bodies. Contracts retain
eager alias evaluation, first-wins alias lookup, last-wins UID/class indexes, duplicate selections,
minimum counts and exact missing-metadata records. Per-expression policies preserve dynamic
rebinding. First-failure then recovery fixtures reject retries; narrow class errors still skip.
No model inference, external requests or device operations run in these contracts.

`python scripts/smoke_training_worker_retired_flows.py` runs 12 synthetic groups.
Nine original business groups passed before migration on Windows and Linux;
10 expanded groups also pass against saved original function bodies. Contracts retain
retired task settlement fields, one update after the clock, current updater capture and
read-only public projection identity. Partial projection mutations and errors retain
original order. Historical unreachable network bodies remain unchanged after their
early returns; synthetic dependencies prove no remote work or artifacts are requested.

`python scripts/smoke_training_worker_retired_requests.py` runs 7 synthetic groups.
Six original business groups passed before migration on Windows and Linux;
6 expanded groups also pass against saved original function bodies. Contracts retain
immediate retirement rejection, exact error text, Python argument binding and fresh
status payloads. Poison parameters and transport substitutes prove no configuration,
parameter, network, retry, sleep or service-probe work occurs in the retired paths.

`python scripts/smoke_training_worker_watcher.py` runs 14 synthetic groups.
Eleven original business groups passed before migration on Windows and Linux;
12 expanded groups also pass against saved original function bodies. Contracts retain
disabled entry points, startup handler identity, interval clamping, original exception
reporting and per-iteration callback lookup. Fake events and bounded loop substitutes
verify lifecycle behavior without starting real threads or worker processes.

`python scripts/smoke_training_worker_artifacts.py` runs 17 synthetic groups.
Twelve original business groups passed before migration on Windows and Linux;
15 expanded groups also pass against saved original function bodies. Contracts retain
strict base64/checksum validation, exact metadata, filename fallback and partial file
writes on failure. Two narrow getters retain owner path and filename callback selection
before argument effects. Existing metadata and partial model/copy evidence remain on
errors. Temporary files and synthetic payloads are used; no model is loaded.

`python scripts/smoke_training_worker_bundle.py` runs 25 synthetic groups.
Seventeen original business groups passed before migration on Windows and Linux;
23 expanded groups also pass against saved original function bodies. Contracts retain
exact metadata, byte accounting, shared upload state and the existing one-time streamed
to form fallback. Three narrow getters retain resolve, form and updater selection before
argument effects. Tests verify original cleanup and error precedence with temporary
archives and synthetic transport/progress substitutes; no real uploads or training occur.

`python scripts/smoke_training_worker_transfers.py` runs 29 synthetic groups.
Seventeen original business groups passed before migration on Windows and Linux;
26 expanded groups also pass against saved original function bodies. Contracts retain
exact UTF-8 multipart bytes, 262144-byte chunks, lazy archive reads, shared counters,
response closure, JSON/length fallbacks and exception boundaries. Three narrow getters
preserve callback selection before headers, job formatting and counter conversion.
Fake events and threads verify progress flushing without real worker execution.

`python scripts/smoke_training_remote_compatibility.py` runs 20 synthetic groups.
Eleven original business groups passed before migration on Windows and Linux;
17 expanded groups also pass against saved original function bodies. Contracts retain
exact request metadata, one HTTP submission, status normalization, top-level response
filtering, archive closure and original cleanup/error boundaries. Three narrow getters
preserve callback selection before effectful arguments; pure payload/status projections
remain unchanged. Tests use real temporary archives and network substitutes only.

`python scripts/smoke_training_background_api.py` runs 26 synthetic groups.
Fifteen original HTTP/business groups passed before migration on Windows and Linux;
22 expanded groups also pass against saved original function bodies. Contracts retain
media permissions, upload validation, exact image analysis inputs, prompt-free formatting,
owner selection and partial-file/state mutations. Five narrow getters preserve callback
capture before argument effects. Real uploads, threadpool identities and temporary files
exercise independent applications; paid inference, physical PLC and production data are not used.

`python scripts/smoke_training_background_tasks.py` runs 34 synthetic groups.
Twenty original business groups passed before migration on Windows and Linux;
28 expanded groups also pass against saved original function bodies, including the
original model snapshot decorator. Contracts retain exact prompts/process commands,
timeout evidence, thread save/register/start order, late-bound callbacks and settlement
failure boundaries. Narrow getters preserve function selection before effectful arguments.
Independent compositions use isolated files and fake processes/threads; no real model,
paid inference, physical PLC or production data is used.

`python scripts/smoke_training_background_writes.py` runs 25 synthetic groups.
Fifteen original business groups passed before migration on Windows and Linux;
21 expanded groups also pass against saved original function bodies. The original
pixel/RNG golden remains unchanged. Contracts retain overwrite and partial-file behavior,
raw manifest aliases, two metadata clocks, eager values and callback exception boundaries.
Three narrow getters preserve callback capture before argument effects. Independent
compositions use owned temporary roots; all test deletions validate resolved containment.
No real training, paid inference, PLC or production data is used.

`python scripts/smoke_training_background_catalog.py` runs 25 synthetic groups.
Seventeen original business groups passed before migration on Windows and Linux;
22 expanded groups also pass against saved original function bodies. Contracts preserve
JSON error conversion, partial seeding writes, eager clocks, pre-seed manifest snapshots,
normalized-ID collisions, shallow aliases, permissions and selection short circuits.
Three callback getters preserve four call sites and refresh per invocation. Independent
compositions interleave real temporary files; no real training or production data is used.

`python scripts/smoke_training_jobs_api.py` runs 19 synthetic groups.
Sixteen original HTTP/business groups passed before migration on Windows and Linux;
17 expanded groups also pass against saved original function bodies. Contracts preserve
ordered duplicate-bearing lists, first-match aliases, exact statuses, permissions and partial
mutation/persistence ordering. Every callback first error propagates without retries. Active
policy is read after each status lookup. Independent apps exercise threadpool identities;
no training process, paid model, production database or physical PLC is used.

`python scripts/smoke_training_runpod_transfer.py` runs 23 synthetic groups.
Seventeen original HTTP/business groups passed before migration on Windows and Linux;
21 expanded groups also pass against saved original function bodies. Contracts preserve
token/expiry checks, path validation, streamed size limits, hashing, atomic replacement,
partial files, exception causes and cleanup behavior without retries. Resolver/update getters
capture callbacks before argument effects. Independent applications use synthetic streaming
and isolated storage; no real RunPod request, training process or PLC is involved.

`python scripts/smoke_training_launch_workflows.py` runs 18 synthetic groups.
Fourteen original HTTP/business groups passed before migration on Windows and Linux;
16 expanded groups also pass against saved original function bodies. Contracts preserve
request validation, scoped selection, approval, enqueue, clocks and partial state writes.
Four callback getters retain nine argument-effect call boundaries with per-call refresh.
Actual submission tests retain nullable backgrounds and frozen task model bindings.
Independent application instances exercise threadpool identities and late physical-size reads.
No real training process, paid inference, production database or physical PLC is used.

`python scripts/smoke_training_input_state.py` runs 24 offline groups.
Sixteen original business groups passed before migration on Windows and Linux;
22 expanded groups pass against saved original function bodies. The original sprite
fingerprint is retained in `tests/backend_contract/training_preview_cache.json`.
Four narrow callback getters preserve argument-effect order and per-asset resolver refresh.
Contracts preserve stat OSError zeroing, exact HTTP errors and causes, no automatic retry,
approval mutations, sanitized sample counts and visible task settlement before state projection.
Two independent compositions retain their own configuration and identity without constructor reads.
No production data, paid inference or physical PLC is used.

`python scripts/smoke_training_preview_workflows.py` runs 25 synthetic groups.
Nineteen original business/HTTP groups passed before migration on Windows and Linux;
23 expanded groups also pass against saved original function bodies. Contracts preserve
GET scope/sanitization, POST request defaults, exact error ordering, preview files and JSON,
partial failures, state updates and callback refresh. Nine narrow callback getters retain
capture before argument effects; first exceptions are never retried. Independent applications
exercise threadpool identity and storage isolation without constructor reads or worker starts.
No paid inference, real PLC, customer records or production database is used.

`python scripts/smoke_training_preview_renderer.py` runs 17 synthetic groups.
Twelve business groups passed on the actual original renderer on Windows and Linux before migration;
15 expanded groups also pass on originals. Original pixel, complete metadata, callback sequence
and RNG fingerprints remain fixed in `tests/backend_contract/training_preview_renderer.json`.
Cases cover documents, sprites, rematching, placeholders, masks, occlusion, threshold short-circuiting,
partial output and first-error propagation. Six callback getters preserve ten argument-effect
capture windows and refresh at each call; two Name-only calls share those typed field interfaces.
Independent renderers and new getter failures are checked separately. No real model or PLC calls.
The imported OpenCV 4.10.0 runtime uses its separate original-implementation golden file.
The production lock includes overlapping OpenCV distributions; 4.10 yields 0.6752 instead
of 0.6751 for the first placeholder label occlusion. All other metadata, pixels, calls
and RNG fingerprints match. The original 4.13/5 baseline stays unchanged; no tolerance
or output-based fallback is used, and production dependencies are not changed.

`python scripts/smoke_training_preview_layout.py` runs 22 offline contract groups.
Seventeen passed on the actual original twelve functions on Windows and Linux before migration;
20 expanded business groups also pass on saved originals. Contracts retain ROI capture, lazy
axis fallback, random call order, inclusive endpoints, attempt 180, earliest tie, rounding, real
intersections, mask pixels, contour clipping, threshold equality and stable ordering. Added cases
check callback capture before argument effects, refresh between axes/list items and first-error
propagation without retry. Independent services and new getter failure cases add two groups.
No PLC or model calls occur.

`python scripts/smoke_training_backgrounds.py` covers 22 offline groups. Thirteen passed
against the original seven functions on Windows and Linux before extraction; 20 expanded business groups also pass on the originals. Pixel fingerprints,
metadata and subsequent RNG state are fixed in `tests/backend_contract/training_background_pixels.json`
with the original commit recorded; the selected cases match both runtimes. Tests cover non-symmetric
image fitting, two INTER_AREA resizes, blur threshold/choice, texture blend, unchanged inputs, manifest
error types, list aliases/order, repeated selection, fallback versus exceptions and exact render
call counts. One extra group checks first errors from every new path getter; another constructs independent libraries/renderers without reads and uses real
synthetic PNGs with different BGR colors while root callbacks are forbidden. No model is loaded.

`python scripts/smoke_training_resource_mutations.py --postgres` covers 25 synthetic groups.
Nineteen passed on actual original functions before migration with an isolated PostgreSQL database;
23 expanded business groups also pass on saved originals. Windows skips PostgreSQL unless requested.
Independent services bind two HTTP applications and exercise all five write routes against separate
fixture files and records. Cross-thread probes cover record reads, permissions, updates, loads and
saves under the original locks, with timestamps outside. Contracts preserve
permission order, missing-resource differences, exact file/manifest formats, exception boundaries,
first-error call counts and partial completion. Recursive removals and unlink operations validate
resolved targets inside each temporary fixture. PostgreSQL markers use only row upserts, retain
other owners and historical model snapshots, and create no JSON files.
The legacy unique-resource-name smoke installs the same explicit model-profile fixture as
other JSON business smokes and supplies the required AI production-count field. Its original
name-collision assertions run unchanged in CI.

`python scripts/smoke_training_resource_catalog.py` covers 22 offline groups. Fifteen
passed on the actual original implementation before extraction; 19 expanded business
groups pass on saved originals. Independent service composition and new getter failure
groups cover three additional boundaries. Two HTTP applications verify zero
constructor reads and identity propagation into real synchronous handlers. Contracts include root
order, summary/detail file access, permission timing, shared read versus write, duplicate/history
rules, model timestamps and ambient identity, exact failure call counts and final sanitization.
Real task-view/lifecycle integration settles only visible interrupted tasks; failed saves stop
aggregation without retry. Legacy resource and missing-dataset deletion smokes exercise callers.

`python scripts/smoke_training_artifacts.py` covers 27 offline groups. Nineteen passed
on the actual original functions before extraction; 24 expanded business groups also
pass on saved originals. Independent composition and new getter failure groups add three.
Twelve callback capture traces cover path/owner resolution and both export writes.
Windows skips the symlink case only when creation permission is unavailable.
Synthetic ZIPs and plain bytes verify
strict hashing, sorting and repeated stat calls, top-level exclusions, real RGB JPEG conversion,
same-stem overwrites, late policy replacement, original-image and partial-JPEG fallback,
cleanup boundaries, token hashes/URL encoding, ZIP member selection and duplicate names,
optional SHA, path/owner rules and ordered partial-import failures. Acquired bundles are cleaned
exactly once even when output/name/copy/hash preparation fails; metadata and result writes
must not retry after an error. All recursive removals
are constrained to resolved temporary test paths. Tests explicitly select the native Pillow
decoder to avoid Ultralytics' optional HEIF auto-install hook; no checkpoint is loaded.

`python scripts/smoke_training_runpod_flow.py` covers twenty-four offline groups. Sixteen
passed against the actual original five functions before migration; twenty-two expanded
business groups also pass on saved original functions. Independent construction and new
getter failures add two groups. Thirty capture traces retain callback-before-argument
ordering, while first-error-then-recovery cases cover file access, environment lookup,
clocks, HTTP and JSON exception boundaries, and task writes. Repeated synthetic responses
remain valid so accidental retries cannot hide behind exhausted fixtures.
Checks include upload-before-validation, exact inline boundaries and file access order, POST
payload identity and TTL, strict output booleans, status normalization differences, encoded job
IDs, timeout equality and pre-sleep checks, terminal intermediate states from the original task,
all failure stages without retries, import/summary/update/sync/warmup order and keyword-collision
residue. Failure at each task-update position blocks later archive/submission/GET/import/sync
side effects without retrying the write. An outer-runner integration retains one historical model scope through completion.
HTTP, archive creation, artifact import, waits, model warming and process operations are substitutes.

`python scripts/smoke_training_dataset.py` covers twenty-seven offline groups. Seventeen
passed on the actual original ten functions before extraction. Twenty-three expanded business
groups pass on the saved original functions. Independent composition, shared async/threadpool
identity and new getter failures supply four additional groups. Twenty-one capture traces,
per-sample/per-label lookup and first-error-then-recovery cases preserve callback timing,
exception identity, call counts, HTTP normalization/save precedence and partial file writes.
Tests fix seeded sample order, RNG threshold/rounding, shared list identity, duplicate-ID
reindexing, label dimensions and exact bytes, YAML name collisions, request background versus
task ownership, metadata types and distributions, progress scheduling, configuration error
order and six file/metadata failure residues. Real synthetic images test bbox position, palette
indexing and unmodified input pixels; rendering and external transports are substitutes.
Fully and partly out-of-frame boxes have exact unit and generated-file assertions; clipping
the coordinates before normalization is rejected because it changes the original amodal labels.
The non-CI `verify_task_pipeline.py` has one existing geometry assertion expecting `[57, 143]`
where the current fixed 1280/600 px/mm scale produces `[85, 213]`. That exact assertion fails
identically on the actual original and fixed dataset implementations. The other
eleven checks pass, including sample distribution, background metadata, 64 document renders,
detection rules and pipeline handoff, with a synthetic model resolver and forbidden external
network/process operations. The legacy assertions remain intact; its full main is
not reported as passing. Geometry scaling is outside this structural extraction.

`python scripts/smoke_training_runner.py` covers twenty-nine offline groups. Sixteen passed on
the original four functions before extraction. Twenty-six expanded business groups also
pass on the saved original functions, including their actual model-binding decorator.
New getter and independent composition groups verify independent runners,
submissions and identities, zero-call construction and missing-resolver failure. Tests keep
binding and body task reads distinct, check historical/empty/ambient snapshots, async thread
scope isolation, exact command/request counts, poll/parse/sleep order, terminal and failure
settlement, save/register/start/publication ordering, failed-step residue, late target capture,
CLI lookup and bounded log parsing. Processes, external executors and submission threads are
substitutes; no real training or paid call is started. Forty-five capture traces and
first-error matrices preserve per-branch call counts and legal failure settlement.
They cover every update provider, process I/O, clocks, log-reader and CLI boundaries,
BaseException propagation and both failure-message conversions.
Ordinary Thread identity behavior is
unchanged; asyncio tests validate only the existing native thread-pool propagation.
Generation, RunPod and remote execution each have an independent unknown-outcome fixture
whose second call would succeed: each must be called once, settle failure once within the
saved model scope, and never fall through to another executor or a local process.
The non-CI `smoke_phase3d_pipeline.py` main still asserts retired worker bypass metadata
(`training_executor=local` and `worker_sample_generation_bypassed`). Replaying that exact
assertion against sample-completion updates from both saved original and migrated runners
fails identically; the legacy script remains unchanged and is not counted as passing.

`python scripts/smoke_training_state_services.py` covers twenty-one groups. Twelve first
passed against the original thirteen functions; the added group composes independent domain
services and identities. Nineteen expanded business groups also pass on the original
bodies; new getter-only cases are checked separately. Nine callback-capture traces,
first-error/later-valid matrices, five clock failure windows and cross-thread reads
retain original ordering, exceptions, partial state and lock release. Checks cover JSON default cloning, legacy-key collisions, state-object
aliasing, visibility and ContextVar ownership across two accounts entering thread pools,
nonterminal config propagation, ignored false returns, model precedence, terminal branch
fields, duplicate candidate identity and exception residue. Cross-thread probes require
pipeline-lock ownership only during pipeline writes and auto-lock ownership only during
candidate updates, including clocks, record.update and state-key assignments between I/O
callbacks. Unlocking either shared-object mutation is rejected by a dedicated mutation check.
The account concurrency check establishes identity isolation, not atomic
whole-configuration writes. Source tests mutate each manifest file and preserve old bindings.

`python scripts/smoke_training_executor_client.py` covers twenty-one offline groups. Eleven
passed on the original twenty-seven functions; the added group checks independent settings,
late environment replacement, injected clients and imports without Web/model runtimes.
Nineteen expanded business groups also pass against the original bodies. Nine
argument-capture traces, first-error/later-valid matrices, second authorized-attempt
failures, configuration seams, new provider failures and recursive failures retain original boundaries.
Tests fix exact URL/configuration validation, status order, whitespace fallback, timeout
clamps/NaN/Inf behavior, auth capture versus per-attempt timeout reads, request counts,
headers, error truncation/causes and the precise recursive redaction boundary. The HTTP
transport is always substituted. Retired endpoints remain zero-request controls.

`python scripts/smoke_training_task_lifecycle.py --postgres` covers twenty-one groups:
eleven behavior groups were established on the original nine functions, including
real PostgreSQL deletion and late-completion rejection. Nineteen expanded business
groups also pass against original functions; two new-interface groups verify
independent services/runtime aliases and getter failures. First-error matrices
retain call counts, original exceptions, intermediate records and marker residues.
Three traces preserve sanitizer capture before enrichment. Process signals and /proc checks use
substitutes. Contracts cover authorization before activity/stop, single SIGTERM,
exception boundaries, stop and deletion timestamps, same-object marker aliases,
cross-thread lock probes during all four marker timestamps and both alias writes,
failed-delete residue, existing-record precedence during late updates, worker-only
read-only views, projection defaults and visibility before refresh side effects.

`python scripts/smoke_pipeline_stores.py --postgres` covers twenty-one groups. Twelve
behavior groups first passed against the original fourteen functions, including
real partial-key updates and rollback after the second PostgreSQL write fails.
Nineteen expanded business groups also pass against the original functions. Two
interface groups check independent stores, root path overrides and getter failures.
Fifteen callback traces preserve capture before fetch, clock and snapshot membership.
First failures and whole-update copy/normalization lock probes supplement the
existing transaction boundaries. Contracts cover
JSON raw-list behavior, fixed temporary files, directory creation order, task binding,
first-replacement/all-deletion rules, nested repository reselection, state normalization,
commit/rollback exception boundaries and whole-update cross-thread guard probes.
Direct partial-key saves remain unguarded; update tests acquire no outer test lock.

`python scripts/smoke_training_record_store.py --postgres` adds twenty-one groups.
Eleven behavior groups passed with the original eight functions, including an
isolated PostgreSQL replay. Nineteen expanded business groups also pass against the original functions. Two
interface groups check independent instances and getter failures. Added contracts
cover callback/file first failures, nine callback capture traces and directory
resolution after task-id conversion. Nested repository selection failures, internal
read failures, serialization and per-row decoder selection are checked separately.
Tests cover
freeze/invalidation/lock/write order, missing resolver, existing None/empty snapshots,
scoped deep copies, two async thread saves, cross-thread lock probes, nested RLock
release after failure, partial file writes, JSON raw types, repeated repository
selection, direct-versus-fallback matching and PostgreSQL upsert/update/readback.
The original missing-dataset deletion smoke now installs the existing offline model
profile fixture and runs in CI; all deletion/resource assertions remain intact.

`python scripts/smoke_trained_model_catalog.py --postgres` covers nineteen groups:
ten offline groups and the isolated PostgreSQL group first passed against the
original three root functions; two groups check lazy independent service
construction, late composition callbacks and new getter failures. Seventeen business
groups also run against immutable original function bodies. Added failure contracts
cover callback/filesystem boundaries, second reads and second OCR/method calls;
27 traces cover nine original callback expressions with normal, prior-replaced and
missing callbacks. No first failure is automatically retried. Contracts include finder loader identity,
single lazy scan, local/shared snapshot aliases, partial failures without retry,
first-match links, duplicate roots, complete variant payloads, missing artifacts,
malformed counts/maps, final identity filtering and two accounts through `to_thread`.
The PostgreSQL group creates and drops its own schema; no model is loaded or called.
The repository source gate inspects the real finder and its lazy composition binding
without lowering the existing repository-entry threshold.

`python scripts/smoke_yolo_warmup.py` adds nineteen synthetic groups; the first eight ran
against the original root before migration. Fourteen business groups also pass
against immutable original function bodies. They cover environment defaults, candidate
ordering and limit-before-deduplication, exact zero-image prediction parameters,
shallow snapshots, disabled-state retention, progress/failure summaries, uncaught
setup errors, late thread targets, independent runtimes and cross-thread lock checks.
Predictions/thread scheduling use test doubles; small lock probes use real threads.
No real model is loaded, and the warmup delay is replaced during worker tests.
First failures retain their original exception or recorded failure without retry;
12 argument-boundary traces cover four callback captures, prior replacement and
missing callbacks. New getter failures are separate interface contracts. Disabled
worker/start state updates and all running/progress/final/snapshot locks are checked
from another thread; disabled paths do not obtain a worker or launch a thread.
Prediction cases assert exact call counts, including zero on skipped model types.
Missing environment keys explicitly verify enabled/limit/delay defaults of true,
6 and 1.5 seconds; in-memory duplicate/default mutations must fail these contracts.

`python scripts/smoke_local_model_runtime.py` adds seventeen groups; eight first passed
against the unchanged root. Fifteen business groups also pass against the original
function bodies. Synthetic model factories and temporary placeholder
files cover selection priority, removed-ID behavior, TypeError fallback, cache-hit
validation, by-ID and resolved-path aliases, failed loading, stale path readiness,
empty-ID branches, lazy construction and independent instance state. The real YOLO
constructor is never called. Source contracts require both new modules and verify
per-file fingerprint sensitivity while keeping old snapshots frozen.
First-failure checks cover selection, factory, catalog/ready calls, file lookups,
registry policies and partial cache writes. The original one-shot TypeError fallback
remains; unknown errors and its second failure are not retried. Path discovery skips
TypeError/OSError once and propagates ValueError. Cached None/falsey instances retain
identity. Three callback traces protect construction after resolution and before
path string conversion, including replacement and a missing callable.
Remote-model rejection asserts the complete original error messages; this caught
and corrected a mechanical identifier substitution inside string literals.

`python scripts/smoke_detection_task_catalog.py` adds thirteen synthetic groups.
The original eight first passed against the unchanged root; eleven business groups, including added
failure and complete-output contracts, also pass against its immutable function
bodies. They exercise duplicate IDs/labels, audit and background lookup, request validation order, native/trained precedence, eager
setdefault evaluation, partial mutation before failure, distinct accessory indexes,
None/empty configuration, explicit user versus request identity, two async thread
handoffs and independent service instances. Original HTTP/RBAC/resource/detection
checks remain. No model, physical device or paid provider is invoked.
Twenty-one callback/port boundaries retain the same first exception without retries;
the request lookup adds a second entry-path check. Full native, trained, projection
and response literals protect flags, owner, time, source, missing IDs and nested aliases.
Internal catalog calls are substituted on the catalog instance; root compatibility
forwards remain available. New identity/registry ports are validated separately from
old callback contracts.
Empty requests assert zero lookup even with a throwing provider; valid and unknown
accessories assert exactly one lookup. Both migrated files are mandatory fingerprint
sources, with per-file hash sensitivity and historical snapshot freeze checks.

`python scripts/smoke_detection_task_store.py --postgres` covers fifteen synthetic
groups. The initial seven passed against the unchanged root implementation before
extraction. Contracts cover normalization, shallow aliases, cache early returns,
JSON I/O and replacement failures, raw single-task writes, repeated repository
selection, background hydration, independent stores, late root providers and real
PostgreSQL replace/upsert/readback in a disposable schema. No model/device is used.
The PostgreSQL source gate follows all three actual store entries and the root's
lazy factory binding without reducing its original total-entry threshold.
The original phase3a resource and phase3b detection smokes also run in CI. Both use
the existing explicit model-profile fixture; the frontend source contract follows
the current workspace-relative routes and cancellable image/video calls. Original
ownership, list/delete and image-admission HTTP assertions remain intact.
Three failure matrices cover nine read, fourteen write and four background failures,
requiring the original exception, one attempt, cache invalidation and unchanged
storage or explicit temporary-file residue. The exists fault targets the task file
only, so a fixture directory probe cannot consume it before the storage operation. Five argument-effect traces, four
preceding-work traces and five missing-callback traces reject late/early capture
and skipped argument evaluation. The initial seven business groups and all six
added groups pass against the actual original root; the original PostgreSQL group
also passes in a newly created empty local test database. The independent service
composition group is verified separately. PostgreSQL runs use disposable schemas
in an isolated test database. No default or production database is required.


`python scripts/smoke_detection_ocr.py` covers twenty synthetic groups. Nine passed
against the original root before extraction: keywords/profiles, matching thresholds,
manual classification, image geometry, scoring failures, crop fallbacks, attachment
fallback/short-result rules, specialized resolution, and partial projection. Three
additional groups verify factory/bootstrap failures and instance isolation, real root
composition with late shared bootstrap replacement, and batch-build failure replay
order. Fake Paddle factories and prediction substitutes prevent model downloads or
inference. Existing task/OCR/YOLO-shape assertions remain required; complete HTTP,
boundary and historical-fingerprint contracts accompany the extraction.
Eight additional groups cover four callback capture windows and four absent-callback
traces, five attachment first-error boundaries, original UID/mapping failures, six
new policy-provider failure boundaries, single-image errors/BaseException propagation
and batch classification fallback order. Three preceding-work A-to-B-to-C traces
reject caching crop, default score or match callbacks at attachment entry. Valid subsequent returns prevent accidental
retries from passing the failure probes; attachment failures preserve partial state
and prevent downstream work. The cache also retains a falsey non-None model.
Sixteen business groups replay against actual original root bodies; the new provider
group, engine factory group, root composition group and class-based batch group are
checked separately and are not claimed as old factory behavior.
Crop pixel contracts verify real rectangle geometry and explicitly cover both
possible first-long-edge directions. This retains exact masks, rotation metadata
and resized pixels without assuming a platform-specific OpenCV vertex start order.



`python scripts/smoke_detection_results.py` covers fourteen synthetic groups.
Eight original business groups passed against the entry-point implementation before
extraction. Four additional business groups cover exact overlap/area/absorption
boundaries, complete parser records and short OBB/mask handling, real overlay
pixels and drawing calls, and original mapping/postprocessor first-error behavior.
Replay those twelve groups against the original function bodies. Two composition
groups cover root aliases, independent lazy label providers and newly introduced
provider failures; they are not claimed as original factory behavior.
First-error probes permit a valid second call and require the original exception
and one invocation. Keep the existing exact-count, manual-type and YOLO-shape
smoke assertions. No model prediction or device I/O is required. Source-contract
checks require all five migrated detection files and verify that editing each
changes the new-task fingerprint without rewriting stored snapshots.

`python scripts/smoke_incoming_text_workflows.py` covers seventeen groups: owner-only task access,
projection/media checks, reference creation and clone failures, activation order,
repeat/insert-loser admission, OCR and quality failure boundaries, review partial
writes, list filters, retention failures and interleaved HTTP identities. Synthetic
images and OCR doubles avoid model downloads or paid calls. Retain the original
incoming endpoint smoke, complete HTTP baseline and real PostgreSQL repository
checks. Static gates follow five actual workflow repository entries and their shared
lazy factory instead of counting composition forwarding twice.
The original ten groups first pass against actual old main function bodies.
New matrices cover twenty-one first-error boundaries with valid subsequent calls;
no retry may hide the error, change residual evidence or run later stages. JSON
read, comparison, mutation and write probes all require the same lock, followed by
release on exit. Thirteen A-to-B-to-C callback windows and thirteen missing-callback
traces retain argument effects and existing failure projection. The assembled HTTP
contract separately checks all thirteen real root getters under replacement and
restoration; it also preserves route order and exact handler identity.

`python scripts/smoke_incoming_text_analysis.py --root` adds sixteen synthetic groups:
OCR single initialization/failure retry/instance isolation; result mapping and color
order; critical-region crops; absence thresholds; raster limits; real PDF behavior;
Beta concurrent single-flight/observer capture; TTL, budget and cached-object rules;
HTTP-adapter read order/thread identity; and root state ownership. Linux uses real
cv2/PyMuPDF and the documented root-import YOLO substitute; no Paddle model downloads
or paid inference occur. Old source checks now inspect actual model parameters and
extend the normalization prohibition to both new algorithm modules. The original
incoming/Beta HTTP concurrency smoke remains required.
The original nine business groups first pass against actual old main functions.
Additional matrices offer successful second calls but require one attempt for five
OCR/parsing, two PDF and two Beta getter/serialization failures. Cross-thread probes
cover preparation, cache insertion, TTL cleanup and budget eviction under their
existing locks. Decode-time observer replacement and cache-hit skipping are tested;
three real-root mapping traces preserve capture before result truth/item effects,
including missing-callback failure. No production model is initialized.

`python scripts/smoke_incoming_text_store.py --root --postgres` covers thirteen groups:
JSON reference/inspection key differences and original input; lazy factory and SQL
dispatch without fallback; serializer/audit ordering; real file error boundaries;
lock release checked from another thread plus dynamic paths; root shared-lock and
helper identity; and real PostgreSQL unique keys/readback/audit inserts in a disposable
schema. Root and PostgreSQL groups can run separately in their respective local
runtimes. Keep the old incoming endpoint baseline, text-record contracts and complete
HTTP/source gates; the static repository-call threshold is unchanged.
The original six business groups first pass against actual main functions, including
an isolated PostgreSQL schema; the newly composed root identity check is separate.
Added matrices cover twelve read and eleven write/serializer/audit failure boundaries
with a valid second call, plus first-read and partial temporary-write failures.
Cross-thread probes run during actual uniqueness comparisons and input keys/item
access, requiring one shared guard through comparison, shallow copy and persistence.
Ten decoder traces cover A-to-B-to-C capture, missing callables and empty-row skips;
four root traces preserve public list-loader replacement and missing-loader errors.

`python scripts/smoke_text_comparison_api.py --root` adds fourteen synthetic groups:
prepared short-circuit/extraction bounds; exact fingerprint/provider payload and
persist-before-call order; duplicate/insert-loser/input-build boundaries; provider,
validation and annotation failures; second/final save, logger and admission gates;
review save/audit partial effects and evidence hashes; retained 410/403/422 HTTP
behavior; and per-submit root callback capture with dynamic environment reads.
Each provider is a test double. Original endpoint modes and source-fingerprint
checks remain required; the assembled contract verifies all six route aliases.
Seven original business groups first pass against the original main function bodies
through argument adapters; their candidate HTTP harness is not evidence for original
request-body lookup timing. Three first-error matrices add fourteen input, evidence,
postprocessing and review boundaries with valid second calls, exact attempt counts
and unchanged partial evidence/uncertain settlement. Fourteen original event traces,
thirteen A-to-B-to-C capture windows and thirteen missing-callback traces preserve
argument effects and exception policy. The application contract also checks live
replacement/restoration of all eleven new callback getters.
The Beta source guard follows revision fields into the actual submission module and
verifies its import, service composition, route registration and endpoint alias by
AST. Its original business/frontend and record-store assertions remain required.

`python scripts/smoke_text_standards.py` adds thirteen synthetic groups for import
validation/duplicate/parser ordering, DOC thread identity and DOCX synchronous
execution, partial writes and job failures, retrieval/media behavior, add cleanup,
patch feedback/exception boundaries, confirmation priority, and interleaved native
HTTP requests across two applications/accounts. The original five document-review
checks now call real service/HTTP adapters through explicit test capabilities instead
of compiling functions from the entry-point source. Their behavioral assertions are
retained. Source checks follow all three migrated repository entries without counting
the composition lambda twice; assembled HTTP checks verify all seven handler aliases.
Seven original groups first pass against old business function bodies through
argument adapters; the candidate route harness in that check does not establish
the old request-body timing, which has a separate original/candidate trace and
the existing full endpoint baseline. Ten explicit dependency event sequences cover
argument evaluation, DOC queue admission, projection and permission-before-JSON.
Seven A-to-B-to-C traces also bracket the capture point with earlier business work
and later argument evaluation, rejecting entry caching for six getter capabilities.
Four first-error matrices cover thirteen parser, job, write, database and JSON-body
boundaries. Each offers a succeeding second call and requires the original error
or HTTP cause, one attempt, preserved prior evidence and existing cleanup/lock order.
The original DOC thread identity and ContextVar assertions remain. The assembled
application verifies that each new getter follows live replacement and restoration.

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
