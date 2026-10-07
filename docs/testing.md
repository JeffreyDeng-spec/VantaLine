Codex comparison real-PostgreSQL CI now holds a writer advisory transaction while `list` and `events` read the old committed task and event rows, then checks visibility after commit. Nonempty row decoding proves an independent writer can take the fence; injected decode errors preserve the same exception, rollback to IDLE, close the cursor and allow reuse. Owner, task, before/after, ordering and 100-event bounds remain covered. Reverse tests observe an actual advisory wait for `get`, `cancel` and `write_report`, including rejection of a token revoked before commit. These tests do not measure production latency or remove the HTTP events endpoint ownership lookup lock.

`scripts/smoke_label_legacy_index.py` replays the actual accepted-parent `label_inspection/api.py` in CI alongside the candidate; it checks duplicate/tied records, orphan and extended orders, batch-source exclusion, native-vs-legacy error priority, falsey orphan IDs failing before native decoding, the 120-second attempting boundary, and per-extension state recomputation. `scripts/benchmark_label_legacy_index.py` pins the v550 API blob (`36e55d6a`) and alternates five same-environment v550/candidate traversals at 1,000 and 10,000 synthetic legacy records across 100 groups, asserting full output equality, fewer standard-ID scans and latency/peak-memory guardrails. The benchmark measures the list/API Python path, not PostgreSQL query latency or production workload. Existing real PostgreSQL label smoke still covers owner, concurrency and pagination.

`python scripts/smoke_label_read_transactions.py` runs on isolated PostgreSQL in CI: a writer holds the existing advisory lock and an uncommitted task update while list/batch/legacy reads complete on another connection and see the old committed value; after commit a new read sees the update. It also verifies an independent connection can acquire the write lock during nonempty result handling for all three paths, and injected decode failure in each path preserves the exact exception, rolls back to IDLE and permits another read. The existing 1,000/10,000-task benchmark now asserts batch reads do not acquire the write fence; its old/new latency compares per-task with batched SQL under the same current no-lock implementation, not the v548-to-v132 lock change. The test also proves actual `request_run` waits on the write fence and returns the committed bound model snapshot; label smoke retains repeated submission, call registration, global concurrency two and pagination contracts. No real provider or PLC is used.

`python scripts/smoke_label_run_batch.py` compares an accepted v546/v548/v550 list source when `VANTALINE_LABEL_LIST_BASELINE_SOURCE` points to its `api.py` source. It covers empty and 64/65/129-task boundaries, native/legacy/manual/Beta projection, read-only and falsey IDs, task-order JSON errors and cursor reuse. CI also runs `python scripts/benchmark_label_run_batch.py` on isolated PostgreSQL with 1,000 and 10,000 synthetic tasks, zero/long-tail runs with 2 KiB synthetic evidence, owner isolation and SQL-vs-JSON task-ID mismatch; it checks that a second connection can take the write advisory lock during batch reads, plus failure rollback and IDLE, prints expected transaction counts plus old/new latency and repository-level peak-memory metrics, and checks output identity. Existing real label smoke retains pagination, permissions, concurrency-two and paid-call protections. No real provider or PLC is contacted.

`python scripts/smoke_plc_diagnostic_finish.py` replays the accepted v544 root when `VANTALINE_PLC_FINISH_BASELINE_SOURCE` points to its source. Candidate checks active/draining, expiry tolerance, error priority, short-circuit token access, all three outcomes, repeat rejection and exact field removal. CI runs `--postgres` against an isolated schema for committed receipt and injected SQL-write rollback/IDLE/independent readback. No physical PLC or paid inference is used.

`python scripts/smoke_plc_diagnostic_confirm.py` replays the accepted v542 root with `VANTALINE_PLC_CONFIRM_BASELINE_SOURCE`; candidate execution checks error priority, deadline equality, empty-hash short circuit, digest timing, repeated confirmation and unchanged evidence. CI adds `--postgres` in an isolated schema with the real active guard, SHA256 and digest comparator, plus injected SQL-write rollback/IDLE/independent-readback evidence. The SQL write is test-only; confirmation itself does not modify lease state. No physical PLC or paid inference is used.

`python scripts/smoke_plc_diagnostic_state.py` replays the accepted v540 root with `VANTALINE_PLC_DIAGNOSTIC_BASELINE_SOURCE`; candidate execution checks token order, dual clocks, generation and in-flight fences, partial effects, late active-guard binding, frames identity and independent service instances. CI runs `--postgres` against an isolated schema for committed hash-only reservation and real SQL-write rollback/IDLE/independent-readback evidence. Synthetic tests use no physical PLC or paid inference.

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

COS evacuation: `python scripts/smoke_cos_migrate.py` runs offline synthetic checks
for interrupted inventories, source mutation before/during upload, same-length
remote corruption, deduplicated resume, secret/symlink exclusion and path escape.
It also restores without the original source disk, rejects a pre-existing target,
never publishes corrupt restored files, checks subset selection and free-space
failure, and rejects manifest entries outside their declared subtrees.
The fake client performs no network calls. Real SDK transfer, full production
readback, database restore and runtime cutover remain separate operational gates.

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


## Agent policy read transaction

The backend PostgreSQL CI job runs both `local_inspection_service/scripts/smoke_agent_operations_postgres.py` and `scripts/smoke_agent_policy_read_transactions.py` with `AGENT_TEST_DATABASE_URL` set to the disposable CI database. The latter creates its own random schema and checks committed reads during an uncommitted policy update, read/write lock independence, exception rollback and connection reuse, and advisory serialization for policy revisions and operation admission. It performs no model or PLC I/O.


## Fixed-reference model read transaction

`scripts/smoke_model_profile_read_transactions.py` runs in backend CI against a random disposable PostgreSQL schema. It checks fixed-version secret and proxy binding, committed reads while a writer holds the global advisory lock, independent writer progress during nonempty decoding, rollback/IDLE/cursor closure and connection reuse after injected failures, missing-version 503 query order, post-commit call JSON errors, and the 500-call ordering limit. The existing `smoke_model_profiles.py` continues to cover migration, admin permissions, binding races, historical and async snapshots, key rotation and secret projection. No provider or PLC is contacted.


## Model registry initialization fast path

`scripts/smoke_model_profile_initialize_fast_path.py` runs in backend CI against disposable PostgreSQL schemas. It proves warm initialization completes while a writer holds the global lock; simultaneous cold initializers serialize and create one state/profile/audit; a migration failure rolls back DB state and can be retried; falsey state takes the old cold path; injected state-read failures preserve exception identity and leave an IDLE reusable connection with a closed cursor. Existing model-profile and fixed-reference PostgreSQL regressions still run.

## Model task snapshot read transactions

`scripts/smoke_model_profile_snapshot_reads.py` runs against an isolated PostgreSQL schema in backend CI. It verifies committed snapshots during an uncommitted writer, old task replay after version changes, binding/head coherence across a concurrent commit, independent write progress during a paused read, separate fallback transaction timing, scope behavior, strict timestamp cases, and rollback/IDLE/cursor closure after injected state or profile decode failures. The full model-profile registry smoke remains in CI; no provider or PLC is contacted.

## Model admin public read transaction

`scripts/smoke_model_profile_public_read.py` runs in backend CI against a random PostgreSQL schema. It checks revision/binding/profile order, version-bound connection status, secret omission, old committed output during an uncommitted writer, new output after commit, writer progress during a paused display read, state/head capture across a concurrent commit, eager version-read error order, and rollback/closed cursor/connection reuse after state, version or test-row decode errors. Existing model API permission and write-race smoke remains in CI.

## Label list-only run payloads

CI replays the exact v564 `label_inspection/api.py` source against candidate list fixtures, including redacted heavy fields, same-second floating JSON times, nonlatest errors, native/legacy/manual/Beta ordering, and cursor pages. `scripts/smoke_label_list_payloads.py` checks real PostgreSQL field trimming, scalar/non-run preservation, SQL-vs-JSON task mismatch, owner isolation, committed reads under a write lock, exception rollback/IDLE and connection reuse. The 1,000/10,000-task isolated PostgreSQL benchmark alternates full and list-only bounded reads five times and compares output identity, serialized payload bytes, P95 and repository-level peak memory. This synthetic benchmark does not certify production latency or a complete SQL summary.

`git show 825f96337a47088a5a90bf756a912a16ab7921b2:scripts/install_release.sh > /tmp/legacy-installer-v566.sh` followed by `VANTALINE_BASE_INSTALLER=/tmp/legacy-installer-v566.sh bash scripts/smoke_release_installer_bridge.sh` executes the production installer inside private Linux mount namespaces with synthetic archives and stubbed systemd/database/HTTP commands. It checks successful embedded installation, missing/mismatched/unsupported topology and bad checksum before service stop, failed health rollback, post-commit installer promotion failure and exact-release retry, and rejection when the already-installed live commit differs. The matrix also executes the frozen v566 installer for the first bridge package, the promoted installer for a second embedded release, legacy-current retry without installer downgrade, and TERM/INT on both sides of the application commit boundary. The CI release-package job builds the complete immutable package and verifies VERSION, topology, installer bytes and checksums. These tests do not prove an independent worker topology or real production latency. The release workflow separately compares the promoted host installer digest with the immutable artifact and checks the live commit before publishing.


## COS runtime tests

Run `scripts/smoke_artifact_storage.py` for failed/corrupt upload, immutable object
retention after DB failure, CAS conflict, cache pins/eviction, reserved-space refusal
and kernel-lock release after process death. `scripts/smoke_artifact_integrations.py`
checks comparison/text media ownership, real HTTP middleware with synthetic users,
HEAD/Range/ETag, legacy sharing, original-byte ZIP packaging, RunPod token transfer,
synthetic artifact import and named local model loading without source files.
These tests do not claim real model inference or remote GPU acceptance.

Set `ARTIFACT_TEST_DATABASE_URL` to a disposable database named exactly
`vantaline_cos_storage_test` and run `scripts/smoke_artifact_postgres.py`; it refuses
other database names and checks real concurrent CAS, migration idempotence, prefix
isolation, rollback and retained versions. The CI artifact-storage job uses its own
PostgreSQL service and synthetic fixtures.

`benchmark_artifact_workspace.py --report NEW_REPORT` is an opt-in 3,920,294,827-byte
incompressible synthetic ZIP benchmark, not a paid training call or a substitute
for actual historical-dataset acceptance. It records output/reserved space, free
space and cleanup and retains no benchmark archive.

The image-storage integration test uses actual OpenCV/Pillow PNG round-trips with synthetic data, verifies tombstone behavior and failed replacement preservation, and checks persistence precedes ordinary image analysis. Local Mac floating-point call-trace golden mismatches in background variants and preview rendering were reproduced on unchanged e0b43c3; Linux CI remains the gate and these local checks are not reported as passing.

COS regression coverage also includes multipart admission before the route handler, staging release after failure, stale JSON read-modify-write rejection, and no second paid submission after a successful provider response followed by failed persistence. Real PostgreSQL tests verify historical version retrieval and the additive mtime field. The hard-volume provisioning script is not proof of a live mounted layout; record actual mount/backing-file and capacity evidence during Linux commissioning.

COS RunPod submission reserves upload headroom and publishes a durable per-job claim before the paid POST. An existing claim prevents automatic resubmission after a timeout, process death or lost response; operators must reconcile the original remote job. Dataset generation and ZIP preparation share the exclusive work slot, and COS training rejects local/legacy-worker fallback. Regression fixtures exercise capacity rejection before POST and a timed-out POST that is called only once.

COS integration smoke additionally exercises a real OpenCV inspection-image producer with no local output file, verified readback, and failed-upload propagation. A separate promoted-model fixture proves a storage failure never triggers a paid teacher fallback. The ordinary detection media, analysis, annotation, photo highlight and pipeline-resource contracts remain required.
## Label consumer lifecycle

`python scripts/smoke_label_worker_lifecycle.py` checks the actual consumer with real threads and barriers: duplicate startup, two in-flight polls, blocked claims, cleanup on worker threads, timed-out drain/restart fencing, shared join budget, partial startup failure, cleanup failure redaction, disabled/missing repository, conflicting registration, repeated ASGI lifespans, explicit adapter timeout, and import without FastAPI/server. `smoke_label_dependencies.py` retains model/legacy binding and exception-stage behavior on the extracted loop. Assembled HTTP contracts change only the label shutdown callback name from `set` to `stop`; real PostgreSQL label smoke retains the persisted concurrency/deadline/call fences. These synthetic tests do not establish a production 480-second systemd allowance.

A connection-cleanup exception marks that consumer generation failed even after its threads exit. Drain returns false and in-process restart is rejected; process restart is required. The lifecycle regression also retains falsey repository/run handling and the original idle decision after cleanup.

Attempted threads are tracked before native launch. Any startup exception fails that controller even if no thread is currently live, because launch may already have happened. Registration is serialized per process to prevent duplicate hooks during concurrent composition. Synthetic tests cover failure before and after native launch and concurrent registration.

Frozen label-list API replays import the former `worker.register` Web adapter. Their shared test fixture temporarily supplies `worker_api.register` at that old location while retaining the original list function and all assertions; it restores the module immediately afterwards. Production consumer code has no compatibility import back into the Web adapter.

The artifact integration gate also checks indexed retention with no source files: failed database publication cannot mark evidence purged, while successful expiry tombstones its logical location and retains the remote historical bytes.
The isolated PostgreSQL label batch/payload benchmark flushes the five alternating raw time and peak-memory samples, task count, unrounded P95 and unchanged guard limits before each performance assertion. The payload case also records synthetic wire bytes. Preserve this output when a CI guard fails; a missing post-success summary is not evidence of runner noise. This diagnostic output does not change datasets, measurement order, thresholds, queries or production behavior.

The artifact integration suite now exercises the image-job startup guide-provenance service with a mapped guide whose logical local file is absent. The shared checksum reads COS bytes, stores the expected hash, and leaves the local path absent; a second reconciliation is unchanged. Existing training-artifact tests retain local streaming and I/O error contracts. This regression is not a substitute for restarting the complete source-inaccessible application.

Release-controller checks: run `python scripts/render_release_installer.py`, `python scripts/smoke_release_runtime_contract.py`, and on Linux `python scripts/smoke_release_runtime_client.py`, `python scripts/smoke_release_runtime_transition.py`, `python scripts/smoke_release_services.py`. Run both installer shell suites in their private mount namespaces. The managed suite executes the rendered installer against real local Unix sockets and synthetic service processes, exercising joint startup, worker startup failure, public-health rollback and unavailable database evidence. Separate state-machine tests cover stale identity, missing configuration, undrained queues, preserved maintenance and rollback-stop failure. These tests establish controller behavior, not acceptance of the future real standalone worker or shared-configuration migration.

The rendered managed installer matrix additionally covers SIGKILL after old-service stop, after pointer replacement before new startup, and before acceptance, followed by same-archive retries; it seeds an interrupted rollback pointer and verifies restoration of an originally paused consumer. The embedded matrix verifies that a rejected concurrent/live PID lock attempt cannot delete the active installer's staged archive. These are synthetic local process and filesystem fault injections inside private mount namespaces.

Rollback fault tests interrupt after old-process startup, before the verified-instance journal save, after resume, after admission reopen and before the final rollback save. Recovery preserves the live old PID and any newly accepted work; it never stops that process merely to repeat rollback. The installer journals restored units/pointer before startup and verified instances before restoring admission.

Rollback pauses the candidate before waiting for its active runs and admitted iterations to finish; it preserves queued rows without starting paid work on an unaccepted build. A forward switch from an already-paused predecessor also retains its backlog and pause intent. An active predecessor still drains its queue before a normal forward switch. State-machine and rendered-installer faults cover queued legacy-to-managed rollback and paused-backlog transitions; queued work is not evidence of an active call.

## Label runtime state preparation

`scripts/smoke_label_runtime_migration.py` uses two randomly named PostgreSQL schemas. It applies the actual new migration to a pre-existing label store, compares the new table columns and primary key with generated DDL, proves repeated application preserves both old task/call/model evidence and new control records, verifies the empty initial state and single migration ledger row, and exercises old label read/write operations afterwards. It contacts no PLC or model service.


## Managed embedded label control

Managed label controls are tested by `smoke_label_runtime_identity.py` (strict immutable activation and malformed state), `smoke_label_runtime_pause.py` (real threads including blocked cleanup and repeated pause/resume), and real PostgreSQL `smoke_label_runtime_state.py`, `smoke_label_runtime_control.py`, `smoke_label_runtime_http.py`. They cover shared-lock admission ordering, two global claims under competing connections, paused queue retention, wrong build, rollback-safe state, actual Unix sockets/SO_PEERCRED, duplicate roles and startup, reconnection and error redaction, same-build restart/new-build fencing, HTTP 503 maintenance, 401/404 ownership, idempotent replay and frozen model references. Model/provider and PLC calls are absent. The HTTP fixture tests the actual label registrar and deliberately omits the unrelated PDF importer; the existing full label/PDF smoke remains required.

The managed runtime deployment smoke combines the shipped release controller/client with real PostgreSQL, private Unix sockets and consumer lifespans. It verifies acceptance, failed public-health rollback, interruption after rollback admission, database failure before service stop and preserved maintenance/pause intent. Systemd and the public HTTP health result are substituted; actual installer/service fault tests remain separate.

The control endpoint owns a dedicated PostgreSQL connection factory with explicit connect/TCP failure-detection settings; request and paid-task connections retain their configuration. SQL timeouts apply after connection, and the root client has a separate bounded acknowledgement deadline; these do not constitute a hard total deadline for every driver operation. A control-thread shutdown timeout retains its role lock and fails that controller generation until process restart. Regression probes block connection creation and verify no duplicate role, then release the old thread for cleanup. A real claim/processing-substitute/cleanup integration proves pause does not acknowledge drain until two admitted iterations finish, while queued task snapshots remain unchanged.

The current managed activation release-package gate asserts an exact schema-2/protocol-1 embedded manifest and sole Web role, after the preceding schema-1 repair bridges. The real PostgreSQL/control-socket deployment harness now imports the controller from this same checkout; it no longer requires another worktree on PYTHONPATH. Pre-stop effective-setting rejection, paused candidate acceptance and full rollback remain covered.


Recovery-storage regression runs `scripts/smoke_release_runtime_storage.py` on
Linux for ancestor/owner/type/mode checks, permission and fsync failures, atomic
journal replacement failure, capability read-only behavior and journal validation.
The two `managed_root_journal_*` scenarios in the rendered installer suite freeze
the accepted predecessor script by SHA-256 and run as root in private mount
namespaces. They use real UID/GID 998 ownership for the base/backups, then verify
schema-1 installation, successor promotion, same-release retry and a later managed
embedded transition. Promotion failure also proves the old controller's exact
same-release failure with the same archive restored, then recovers via a fresh
complete schema-1 identity. Twelve unsafe/pending-storage cases assert unchanged
Web PID, current pointer and offending metadata without a stop or permission fix.
The original managed and embedded fault matrices remain required. Systemd, HTTP
health and database replies are substitutes; Unix sockets and filesystem ownership
are real. These tests do not certify production unit precedence, actual service
availability throughout a deployment, or standalone worker acceptance.


The Web stop-allowance compatibility suite adds exact {500,510} Web acceptance,
strict worker500 and control-group checks, administrator-file byte/mode preservation,
and unsupported near-duration rejection. The real stop polling loop runs with a
virtual monotonic clock for stuck state/MainPID/ControlPID cases; the transition
integration proves its shared500 deadline includes time already spent before stop,
never switches the pointer or starts a candidate after timeout, and retains the
journal if rollback also cannot verify exit. The rendered installer additionally
covers effective510 success and health rollback, Web499/511, worker510 and unsafe
kill-mode pre-stop rejection using actual private administrator drop-in files.
A frozen root-storage predecessor executes the schema-1 policy handoff on UID998
application directories, validates root recovery storage, promotes the successor,
then exercises a later managed embedded510 transition. These remain isolated
service substitutes; production policy commissioning is separately accepted.

The synthetic run-batch/payload benchmark explicitly analyzes its newly bulk-loaded table before either query shape is prepared or timed. Both arms then start with statistics for the same committed fixture; timed loops, output equivalence, query bounds, memory guards and P95 thresholds are unchanged. Plan diagnostics belong to separate probes and must not be inserted into measured runs. A prior hosted 10,000-task payload failure is retained as evidence; a passing local ANALYZE comparison does not reconstruct that runner's exact plan.

Managed embedded reactivation changes only the immutable topology declaration and
its package assertion. Retain every root-storage/stop-allowance fault test and the
existing actual label identity, PostgreSQL/control-socket deployment, admission,
pause, duplicate-worker, model snapshot, HTTP and full application contracts. The
package gate must assert embedded mode and sole Web service; passing standalone
controller substitute tests is not evidence that an external worker is enabled.

## Proposal: shared label runtime configuration preparation

The preceding embedded configuration bridge introduced a bounded data-only snapshot of the existing label/database/storage/network settings, exact existing model-secret environment references and data directory. Unset and explicit empty values remain distinct. COS credentials are represented by their byte digest and transferred only through a private root-authenticated path; a worker must receive its own systemd credential directory. The pure contract and private-file roundtrip tests use synthetic values. The candidate Web wiring can capture a configuration revision and export its immutable snapshot only through the private authenticated control socket; public status contains only the revision. A prepared root file publisher writes immutable private versions and restores one atomic current pointer. The installed helper now embeds the audited data-only contract, captures a peer/build/instance-bound private export before external transitions, and journals the previous configuration pointer before mutation. It restores that pointer with the complete release on rollback, derives escaped mount dependencies and provisions the worker own systemd credential from root-owned bytes. No candidate application module is imported by the isolated root helper. Tests cover pointer interruption, export tampering, private modes, standalone execution and synthetic installer recovery. That bridge release retained embedded execution. Its complete-release acceptance is a prerequisite for the external activation described below.

The configuration bridge preserves the existing COS reader credential forms, including a null optional token and unused metadata, while binding their exact bytes. A distinct previous configuration is fully validated before journaling or closing admission; corruption aborts before service changes. Rollback may replace a damaged candidate pointer with a verified previous version. These cases have offline regression coverage.


Shared-configuration integration retains the root recovery directory checks and the
role-specific Web500/510, worker500 policy. Run all predecessor root-storage and
stop-allowance installer scenarios as well as configuration publication and rollback
tests. Policy tests must provide a valid synthetic configuration when checking
external-role settings, so a missing-configuration rejection cannot masquerade as
a stop-budget rejection. Both configuration and recovery-storage capabilities are
required by the post-promotion workflow. The private installer fixture mounts its
synthetic /etc separately while preserving the root-storage namespace.

## Proposal: standalone label process

The candidate `label_inspection.runtime` bootstrap reads the root-owned immutable configuration and its own systemd credential, checks the active package build/topology, initializes local storage, and creates separate thread-owned business and control repository factories. It imports no Web application. The existing model service is reused through an existing-registry reader: missing registration fails startup rather than migrating legacy settings. Secret-file syntax, environment precedence, immutable version references and usage accounting remain unchanged. Manifest v141 names 366 actual sources; historic snapshots are not rewritten.

In external mode, Web composition owns admission/control only and constructs no label consumer. The standalone process owns the existing two-thread consumer and its exclusive role socket; SIGTERM/SIGINT stop new work and use the existing 480-second drain budget. Real isolated PostgreSQL tests cover old-model resolution after settings changes and reader recreation, actual child PID/peer checks, duplicate-role rejection, signal drain and controller-driven embedded-to-external acceptance, failure and complete rollback. Synthetic model values and local storage are used; no paid inference or PLC call occurs. The bootstrap-only predecessor did not enable an external release. External activation remains conditional on preceding complete-release acceptance and final exact-build validation as described below.

Standalone signal handlers only assign a monotonic stop latch. Normal control flow performs drain and cleanup; initialization checks the latch before consumer startup, and each consumer admission checks it even across the check/start boundary. Real child-process tests inject repeated SIGTERM/SIGINT before and during initialization and while native thread startup holds the worker lock; no post-stop iteration is admitted. Already admitted iterations retain the existing drain budget.

The unauthorized control-socket regression accepts EOF, connection reset or broken pipe only on the denied-peer path, asserts zero handler calls and unchanged durable maintenance state, and forces EOF-before-send to cover early rejection deterministically. Authorized commands retain their strict response contract; runtime socket behavior is unchanged.

## Proposal: label runtime monitoring

Managed processes publish bounded heartbeats on the existing private control thread with a five-second target interval after the previous tick completes. Database work and control requests can delay a tick. Each uses the dedicated thread-owned connection factory. The operational table stores only build/configuration/process identity, worker state, process-lifetime counters and fixed recent-error codes. A blocked heartbeat retains the same role lock on shutdown timeout. The private deployment protocol remains unchanged.

`GET /api/label-inspection/runtime` requires administrator access before any database call. Its short unlocked READ COMMITTED transaction samples state, queue and heartbeat in separate statements; these are not an atomic health snapshot. It returns queue/active counts, oldest queue age, maintenance/pause intent and expected-role heartbeats; missing, mismatched or older-than-15-second samples are unhealthy. Heartbeat freshness is sampled liveness, not a guarantee against a subsequent crash. Lock acquisition counts/total/max wait include successful and timed-out acquisition attempts. These and rejected duplicate submission/stage-call counters belong to the process lifetime: process restart resets them, while a control restart within the same process changes the instance but retains counters. Idempotent replay is not counted as rejection. Errors never include exception strings, media, customer fields, secrets or filesystem paths. Real PostgreSQL/HTTP tests cover authorization, redaction, actual lock contention, duplicate refusals, stale generations and heartbeat shutdown. Manifest v142 names 367 actual sources. The observability-only predecessor retained embedded execution; the external activation below is a separate release and requires acceptance of every predecessor.

The administrator runtime endpoint is registered in the exhaustive tested label-route guard set. The assembled authentication regression exercises anonymous 401, member 403 (including a synthetic stored inspection/system-settings over-grant), administrator 200 and zero monitor access on rejection. Endpoint-local admin authorization and public error formats remain unchanged; no broad route exemption or additional feature grant is introduced.

## External topology activation checks

The release package must declare external mode and exactly Web plus label worker,
with the same full commit as VERSION.json. Activation changes only this literal,
the matching CI assertion and documentation; bootstrap, model binding, controller,
configuration and monitoring source must match the accepted predecessor.

Run the isolated PostgreSQL state/control/HTTP/deployment, standalone process,
external deployment and monitoring checks together. Retain signal-startup races,
configuration credential/mount checks, duplicate-claim/stage fences, two global
claims, stale/build fencing, installer fault matrices, HTTP/model/PLC contracts and
front-end build. Separate-process tests use synthetic processing and a disposable
Unix-socket-only database. Exact-head hosted CI and independent release artifact
review are required; production acceptance must verify both roles, and is distinct
from a real-provider or hardware test.

`smoke_label_read_transactions.py` now exercises detail reads during an uncommitted update, cross-account/kind denial, post-commit visibility and injected decode failure with connection reuse. Its real `request_run` positive control still waits on the writer and returns the committed original model snapshot.

The PLC domain adds `smoke_plc_event_projection.py`, `smoke_plc_transition_policy.py`, `smoke_plc_persisted_validation.py`, `smoke_plc_event_commands.py`, `smoke_plc_dispatch_mutations.py`, `smoke_plc_station_service.py`, `smoke_plc_browser_dispatch.py`, `smoke_plc_workstation_repository.py`, `smoke_plc_request_models.py`, `smoke_plc_legacy_dispatch.py`, `smoke_plc_dispatch_runtime_state.py` and `smoke_plc_capture_state.py` under `scripts/`. CI runs these alongside the existing Web Serial, lease, PostgreSQL, frontend, model-binding and HTTP contracts. The first four are pure policy/evidence contracts; service checks substitute dependencies, and legacy dispatch replays the original scripted matrix without initializing physical transport. Synthetic capture rollback is not PostgreSQL concurrency evidence. Baseline selectors retained by the service smokes can replay original functions; normal CI exercises the extracted implementations. Real device actions remain outside routine acceptance.

The existing diagnostic state/confirm PostgreSQL fixtures load the actual station service assembly for token hashing after its relocation. Their commit visibility, rollback and plaintext-token assertions are retained.

CI runs the nineteen `scripts/smoke_auto_optimization_*.py` contracts for the extracted settings, recommendations, initialization, state store, readiness, capture, status, mask policy and verification, label generation, sprites, rendering, synthetic batches, dataset, training scheduling, label processing, shadow evaluation, requests and sprite publication. State-store tests use `--postgres` for a real isolated PostgreSQL transaction; other suites use local synthetic media and substituted providers. Original assertions and baseline selectors remain. Existing endpoint-source checks now inspect the actual moved state storage method. These checks do not perform paid inference, remote training or physical PLC I/O and do not establish production capacity.

Six focused CI commands cover `smoke_pipeline_auto_optimization_links.py`, `smoke_pipeline_task_projection.py`, `smoke_pipeline_candidate_flow.py`, `smoke_pipeline_task_metadata.py`, `smoke_pipeline_task_mutations.py` and `smoke_pipeline_ai_activation.py`. Original baseline selectors and assertions remain, including exact docstrings and selected callback timing. Synthetic collaborators verify visibility, aliases, partial state, lock positions, persistence/scheduling order and independent service instances. Retained HTTP/model and neighboring pipeline contracts remain required; no paid model, remote training or physical PLC is used.

Eleven smoke commands cover accessory text preparation, pose prompts/jobs, worker diagnostics, reference media, image queue, training asset preparation, image provider configuration, image execution/management and candidate artifacts. Existing artifact integration assertions now use the actual moved execution dependency. Original baseline selectors, exact prompt snapshots and adverse ordering contracts remain. Routine checks use synthetic files/providers/processes, preserve two-account async thread identity coverage and do not invoke paid models or physical PLC. Candidate deletion tests use strictly scoped private files; Linux tests include a symlink escape. The retired Windows execution path performs no external process or network I/O but retains its original directory creation and failure persistence.

The four added contracts are `smoke_service_status_requests.py`, `smoke_app_config_store.py`, `smoke_local_model_config.py` and `smoke_model_tool_dispatch.py`. They retain original behavior selectors and check permissions, protected configuration, default/recovery boundaries, atomic file replacement and partial failures, provider normalization, metadata precedence, timeout/overload handling and selected-callable/late-handler timing. App-config tests use real isolated PostgreSQL when the existing test DSN is present; all model and transport calls use substitutes. The source guard follows the real store and keeps its original minimum/required sets. The pre-existing local-fake-postgres cutover failure on unsupported advisory SQL remains documented and is not counted as passing.

## Derived label summary migration

`scripts/smoke_label_summary_migration.py` runs against disposable PostgreSQL
schemas and a temporary restricted role. It compares generated/incremental DDL,
empty state and retained source evidence; exercises all source-column updates,
COPY/upsert, ID rename/reuse, transaction/savepoint rollback and the source-first
publication lock; checks old source-only writer permissions, hostile search_path
and foreign-trigger attachment; and injects a real DDL lock timeout and a
mid-migration error to prove atomic rollback and reentry. No application cache
read or paid/PLC call occurs. Migration guard tests retain all previous negative
cases and reject changes to the exact audited exception, including another
target/schema, missing WHERE, dynamic SQL, and surrounding executable SQL.

The generated-schema and CSV-import real-engine smokes send complete SQL blocks to `postgres --single -j`, preserving semicolons inside quoted trigger bodies. Embedded single-user input delimiters are rejected explicitly. The schema smoke verifies the installed trigger and a quoted semicolon, and proves that an intentional SQL error is rejected even when the backend process exits successfully.

`python scripts/smoke_label_public_projection.py` verifies the original public run projection against the extracted pure module, including private-field omission, error and quality truthiness, shallow nested identity, import allowlists and invalid-input errors. Existing HTTP, owner isolation and pagination contracts remain required.

## Post-settlement summary publisher

`smoke_label_run_summary.py` covers complete-payload validation, integer/float/
depth/size bounds, malformed import values, source identity and absent-versus-null
fields. `smoke_label_run_projection.py` uses isolated real PostgreSQL to exercise
terminal-only ownership, wrong/missing/busy source skips, transaction ownership,
source-first publication, actual unrelated claim progress while a projection is
held, old-writer invalidation, rollback/reuse and cache lock timeout reset.
`smoke_label_summary_worker.py` verifies that projection failure follows business
processing without replay or exception disclosure; pause/stop skip optional work;
and admitted publication/cleanup prevents a false drain acknowledgement.

The synchronous-in-business-transaction prototype failed the prior write-cost
guard (100 synthetic 8 KiB updates, P95 about 16 ms to 35 ms) and was not adopted.
The selected publisher leaves business repository/paid processing statements
unchanged and generates derived state after settlement. This slice enables no
cache reader and does not complete full-API/mixed-history performance acceptance.

The projection smoke also observes the actual three-party PostgreSQL wait chain:
a held projection row lock blocks a writer that already owns the global advisory
fence, which then blocks an unrelated claim. Releasing the proof lets the writer
invalidate the cache and the claim proceed. This retained counterexample prevents
treating the absence of an advisory acquisition as absence of indirect contention.
The fixture closes partially opened connections and preserves original errors if
cleanup also fails; proof failure retains the original exception and closes its
cursor before IDLE/reuse verification.

`benchmark_label_projection.py` records 31 alternating post-warmup samples for
actual `update_run` settlement, optional publication and competing write/claim
latency at 256 B, 8 KiB and 200 KiB synthetic quality payloads. It reports
nearest-rank P95, raw timings and optional worker occupancy separately, with a
50 ms publication budget and unchanged per-case claim/settlement guard of
`max(before * 1.25, before + 5 ms)`. An optional `--report` path is created
exclusively. These synthetic sizes do not assert production payload distribution
or paid processing latency. The new storage module participates in dependency
cycle/entry-point checks.

`scripts/smoke_label_summary_reads.py` uses an isolated real PostgreSQL schema and the unchanged API registrar with a frozen c798ac8 parent reader. It covers cached/uncached mixed native/legacy/manual/Beta lists, fractional/tied timestamps, SQL owner scope, unknown-version fallback, old cursor reuse across task insertion/rename/completion, account/filter binding and fixed expiry, old-writer snapshot consistency, decode rollback/IDLE/cursor release, malformed nonlatest data and HTTP permissions. It does not use real PLCs or inference.

`scripts/benchmark_label_summary_reads.py` measures actual list endpoint first-page SQL, cross-source projection and persisted snapshot at 1,000/10,000 tasks with synthetic 8 KiB quality strings and 0/50/100% run-cache coverage. It excludes HTTP transport/serialization and does not model production distributions. Four warmups precede 31 alternating samples; P95 is nearest rank. Separate balanced memory passes avoid tracing distortion. Candidate limits are max(parent P95 * 1.25, parent + 10 ms) and max(parent peak * 1.25, parent + 1 MiB). It checks full traversal equality and at most ceil(tasks/64)+12 SQL statements, retaining raw samples on failure.

The frozen label reader oracle hashes canonical LF bytes so a Windows CRLF checkout has the same pinned source identity. Only CRLF-to-LF normalization is allowed; any source-token change still fails the recorded SHA check.

`smoke_label_reader_readiness.py` uses a real isolated PostgreSQL effective restricted role: the frozen source-only reader succeeds while missing projection SELECT rejects candidate startup before earlier callbacks/control/HTTP. Column-only grants then permit startup. Missing table/column and DDL lock timeout fail safely and close the idle connection; active caller transactions are never committed. The real managed transition/control-socket harness rejects the candidate, never starts its separate worker or accepts it, and restores the whole previous package/configuration/admission. The candidate Web is an ASGI fixture using the restricted business connection; its identity/control constructors, systemd/units and model execution are substituted. This is not a complete production-Web startup drill. The separate existing external deployment suite exercises an actual consumer child process. The recorded startup contract intentionally adds `verify_label_list_database` first; HTTP routes and all prior callbacks retain their order.

The existing label dependency/lifecycle fixture deliberately supplies non-database records and synthetic threads. It explicitly substitutes only the readiness capability there, asserting no eager call and one correct-app preflight before either app starts its PDF/label threads. All prior model/identity/independent-stop assertions remain; real preflight SQL/failure/cleanup is exercised in the separate PostgreSQL readiness suite.

Reader benchmark evidence protocol v1 runs a separate 1,000-task/0%-hit A/A control (both arms use the frozen reader), followed by three complete A/B repetitions. Each repetition creates fresh fixtures per task count; every original 31-sample/four-warmup/query/P95/peak-memory guard must pass independently. There is no pooling, retry, dropped sample or A/A exemption. Failure stops the protocol, records failed/not-run groups and preserves nonzero exit. Diagnostic/report output errors retain an existing primary exception; output failure after otherwise successful work still fails the command. CPU, context-switch and GC collection snapshots are outside the unchanged wall timer, with a slightly wider CPU envelope and possible probe heap perturbation; Python CPU excludes the PostgreSQL process. Failure-only prepared counters contain no SQL/parameters and are captured before cleanup, without EXPLAIN or diagnostic rollback. They are session totals, not per-sample plans. The smoke verifies arm selection, timing window, complete coverage and early/late failure propagation. This strengthens empirical acceptance but does not establish the cause of CI #645's tail-latency failure.

`smoke_service_paths.py` runs original-function selectors through `VANTALINE_SERVICE_PATHS_BASELINE_SOURCE` and the explicit service on Windows and Linux. It covers escaped path migration, partial file failures, filtering, candidate probe order, blank paths, symlink containment on Linux, URL projection, owner placement and call-time identity. It creates only temporary synthetic files. Inverse AST comparison preserves all twelve functions and every unrelated entry node; media/auth/model HTTP regressions remain required.

`smoke_read_cache_ownership.py` compares all five original cache functions through `VANTALINE_READ_CACHE_BASELINE_SOURCE` before candidate instances. It covers nested scopes, exception reset, concurrent threads and async-to-thread context propagation, TTL boundary, value identity, invalidation and clock failure, independent cache instances, local/COS/hybrid metadata keys and distinct I/O error boundaries. Same mtime and size intentionally reuse the old value; metadata validation is not content-hash freshness. Existing analytics, artifact, state-store, task-store and HTTP contracts remain required.

`smoke_directory_lifecycle.py` compares original `ensure_dirs` and path migration through `VANTALINE_DIRECTORY_LIFECYCLE_BASELINE_SOURCE` with explicit owner instances on Windows/Linux. It verifies directory order/partial failure, default object identity, save-before-migrate, sorted/deduplicated recursive JSON candidates, ignored false return, exception/retry semantics, concurrent one-time execution and independent owner state. Full inverse AST and existing path/media/auth/HTTP/storage contracts remain required.

`smoke_foundation_policies.py` runs the same original functions via `VANTALINE_FOUNDATION_POLICIES_BASELINE_SOURCE` and candidate functions on Windows/Linux. It covers falsey values, conversion errors, negative slicing, exact flag defaults, box symmetry/bounds and truncation, image identity/rounding, selected OpenCV arguments and error identity. Direct entry imports replace these four implementation bodies; existing model, geometry and HTTP checks remain.

smoke_artifact_file_policies.py replays the original digest/name functions through VANTALINE_FILE_POLICIES_BASELINE_SOURCE. Synthetic streams cover chunk sizes, empty files, open/read/close failures and exception identity; deterministic clock/UUID probes preserve filename behavior. Artifact, training, image metadata, path, model and HTTP regressions remain required.

smoke_runtime_repository_access.py replays four original helpers through VANTALINE_REPOSITORY_ACCESS_BASELINE_SOURCE and exercises the actual service with fake stores. It checks JSON/no-query selection, exact error/status/cause boundaries, count/fingerprint order, selected repository identity and per-call providers. Keep the existing endpoint probe/source guards, two-account async/thread lifecycle checks, model binding, HTTP contracts and real PostgreSQL connection cleanup tests.

smoke_protected_config_ownership.py compares the two original entry methods via VANTALINE_PROTECTED_CONFIG_BASELINE_SOURCE against AppConfigStore. Preserve existing config tests; cover JSON unprotected changes, reentrant guard/exclusion/release, prior authorization restoration after failed save, falsey repositories, commit-before-reload failure and no retry. Isolated PostgreSQL uses two independent local guards with the shared database namespace lock for concurrent increments, then rejects a second-row write failure and unprotected mutation without committing partial changes. The endpoint source guard follows the actual methods and exact root aliases, retaining its minimum repository-call threshold.

### Native list count/latest aggregation

`smoke_label_history_statistics.py` uses disposable PostgreSQL and the actual API,
with the complete pre-change `tasks` function frozen at fdb3ce9 in
`tests/backend_contract/label_history_tasks_baseline.py`. Its canonical LF SHA is
checked before compiling; surrounding API functions remain shared and unchanged.
It covers finite float/Unicode ordering, unknown-version unsafe casts, complete and
partial proofs, empty groups, original SQL grouping, owner isolation, raw-ID aliases,
historical NaN legacy input, malformed nonlatest native-before-legacy failures, old
cursors, old-writer visibility, unlocked reads and connection recovery. Existing
summary-read, HTTP/permission and business regression checks remain required.

`benchmark_label_history_statistics.py` compares the complete first-page endpoint
to that frozen endpoint: the original 1,000/10,000 task workloads plus 1,000 tasks
with 20 runs each, all at 0/50/100% synthetic cache coverage. Each uses four warmups,
31 alternating timing samples and a separate three-pass memory sample. The same
25%/10ms latency and 25%/1MiB memory guards apply. This measures SQL, projection and
page snapshot persistence, excluding HTTP transport/serialization. Synthetic
repeated histories demonstrate aggregation scaling; they do not establish the
production distribution or make sparse histories inherently faster.

The history benchmark adds a distinct fixed protocol: one 1k/0%-hit A/A control
using the frozen parent endpoint, then three complete repetitions of its nine
workloads (28 cases total). The existing reader protocol still runs all 19 cases.
Each history case/group carries the history depth, comparison and frozen endpoint
SHA; missing, duplicated, reordered or mislabeled cases fail. Actual synthetic
run counts are checked before timing: default 1k/10k populations have 1,003/10,029
runs and 142/1,421 empty tasks; the 1k x 20 population has 20,000 runs and no empty
tasks. Coverage follows the original run-ID prefix, not random production hits.
No threshold, sample count, query bound or original timed statement changes.
Failure diagnostics and exclusive report writes preserve primary exceptions.
`smoke_label_history_benchmark.py` tests all 28 failure positions, late coverage
mutations, old/new endpoint separation and report/summary output failures. The
reader baseline explicitly adapts the new history call to its frozen pre-cache
payload reader; the history baseline instead uses the frozen complete endpoint
with the current cached payload reader. Neither comparison silently runs both
arms through the aggregate query. Fresh main CI and release acceptance remain
required; this does not explain historical CI #645's tail-latency failure.

The population check is outside timed windows but can warm PostgreSQL buffers;
this is not an identical total measurement environment to earlier protocols.
Reader19 compares the pre-cache payload baseline with the cumulative current
endpoint. History28 compares the pre-aggregation cached endpoint with aggregation.
Their percentage changes answer different questions and are not interchangeable.

The history smoke also compares wide 40-run histories with the cached payload
reader: complete histories preserve Python latest/count, while partial, excluded
and unknown-version groups preserve every payload in source order. SQL and JSON
timestamps deliberately disagree; unsafe unknown-version timestamps cannot affect
fallback. The full fixed reader19/history28 protocols and guards remain required.
The first actual-main history candidate failed repetition 2 of the 1k/0% history
P95 gate; that failure is retained. Late payload projection is a substantive SQL
revision, not a rerun exemption or a proven explanation of that earlier tail.

History result decoding now reuses column names only within one fetched result
set. It obtains metadata lazily for the first non-mapping row, preserving empty
results and mapping-row behavior; the generic repository decoder still accepts
all existing callers without supplied columns. Duplicate-column overwrite,
shallow mapping copies and decode-failure rollback/close remain unchanged. This
removes repeated psycopg Column construction without changing SQL, transactions,
query counts, source ordering or proof eligibility. The real PostgreSQL history
smoke verifies one metadata access across a wide mixed-result batch and retains
the original sentinel decode-failure check.

Column-name reuse assumes the stable metadata of one psycopg result set. A private decoder override that avoids metadata, or a nonstandard cursor that changes columns between rows, is outside this optimization contract. Default decoder callers retain the original list-based metadata construction.

The native history reader combines a same-statement current-proof gate with result-local column-name reuse. A batch with no current owned proof uses the ordered fallback branch without history windows; proven batches retain guarded count/latest aggregation. The gate and both source branches use the original typed owner comparison rather than converting the owner parameter to text. This is a new candidate combining two previously separately measured mechanisms, not a retry or acceptance of earlier failed candidates. Both fixed performance protocols and their original latency, memory and query limits remain mandatory; no universal speedup is claimed.

Native list-history fallback now compacts a nonempty `quality` object only when every immediate value is a JSON string, boolean or null. This matches the existing public checked marker while avoiding unnecessary evidence transfer. Numeric and nested values stay intact so JSON decoding errors remain visible; other fields, ordering, detail payloads and old snapshots are unchanged. PostgreSQL/HTTP regressions cover flat Unicode/string/bool/null, empty and other shapes, and bounded-decoder failures. The original complete performance protocols and thresholds remain mandatory; private diagnostics are not acceptance.

Two added CI contracts (`smoke_account_projections.py`, `smoke_resource_names.py`) use explicit services and preserve original-function selectors. Root checks run both selectors against the actual integrated parent, then verify two-account identity, filtering/redaction/media escapes, linked-name exclusions and exception/callback order. The artifact HTTP fixture constructs the actual moved ownership service and retains every assertion. Current-main auth/RBAC tests, including label runtime 401/403 and admin-only access, remain unmodified and required.

`smoke_public_network_policy.py` compares seven original functions through `VANTALINE_PUBLIC_NETWORK_BASELINE_SOURCE` to their service implementation on Windows/Linux. Cases include default ports, malformed ports/regexes, IPv6 normalization, complete allowlist evaluation, private/local names without DNS, masker failure/late resolution, lexical path treatment and admin permission short-circuit. Original HTTP/RBAC, media and status contracts stay required.

smoke_admin_documentation_composition.py replays the original four functions via VANTALINE_ADMIN_DOCS_BASELINE_SOURCE and checks separate app titles/routes/cache objects, authorization before cached reads, short-circuit/error boundaries, same schema/HTML and duplicate preflight. Actual assembled middleware checks retain anonymous/member/admin statuses without entering lifespan. Keep auth/RBAC, model/HTTP contracts and boundary/release validation.

smoke_authentication_composition.py verifies shared repository/user guard identity, distinct graph states, no construction I/O, live settings/repository factories and two independent HTTP applications. Original authentication domain and root RBAC checks remain; use explicit domain dependencies for failure injection. Keep async/thread identity cleanup, real PostgreSQL account/session isolation, full HTTP/lifecycle and model/source/release contracts. These tests do not prove that two whole production applications may safely consume the same runtime store.

`scripts/smoke_authentication_composition.py` retains the existing HTTP, concurrent identity, failure-reset and real PostgreSQL assertions while exercising `AuthenticationHttp` in its fixture. Added cases check zero constructor I/O, graph/identity mismatch, two app route/owner separation and complete assembled-app requests while root auth/origin compatibility exports are replaced with failing sentinels. Documentation tests now assert the real composed owner. The fixture is authentication-only and the full assembled HTTP probe deliberately does not start workers; neither is full production factory/lifecycle acceptance.

The retained pipeline frontend/source contract resolves shared-output visibility from AccountProjections.output_path_visible_to_user, where that policy now lives. The original visibility marker and every existing assertion remain; only its source-location mapping changes. This supplements the existing actual media-permission/account projection contracts.

`smoke_provider_proxy_runtime.py` compares five original functions using `VANTALINE_PROVIDER_PROXY_BASELINE_SOURCE` with the extracted service. Synthetic transports cover invalid environment precedence, explicit-config fallback, flag semantics, socket timeout/error boundaries, URL opener selection and transport failure identity. Original provider and assembled HTTP/model-binding checks remain required; these checks contact no real proxy or provider.

smoke_mcp_client_runtime.py replays the original client with VANTALINE_MCP_CLIENT_BASELINE_SOURCE and exercises the extracted client using fake subprocesses and text streams only. It checks spawn/initialize order, message IDs, Unicode, malformed responses, text selection, close failures, no implicit replay and late error/runtime resolution. Existing tool dispatch, AI detection, model binding and HTTP/lifecycle contracts remain required.

smoke_mcp_runtime_policy.py runs original four-helper behavior with VANTALINE_MCP_POLICY_BASELINE_SOURCE and extracted policies with explicit ports. Cover environment aliases/precedence, shallow payload copy and path priority, encoder-before-argument order, enabled errors outside the catch, replacement client close and close error propagation. Retain original MCP default/opt-in probes, client/dispatch tests, model binding and full HTTP/source contracts. Tests use only fake clients and synthetic arrays.

smoke_model_warmup_api.py compares the original request via VANTALINE_MODEL_WARMUP_BASELINE_SOURCE and the extracted service with the same assertions: ordering, scoped arguments, blank/remote/ready paths, both readiness reads, shallow status merge and first/late failures. Synthetic HTTP checks cover two independently supplied service fixtures, 400/403/422/500 and route names; candidate checks cover no constructor work, duplicate preflight, runtime worker supplier and the full assembled HTTP contract without starting its lifespan. Keep the full original warmup/local-model suites and permission/model/boundary checks; use no real models or inference.

`python scripts/smoke_local_model_selection.py` checks explicit device bypass, synthetic torch availability/import failures, Exception versus BaseException, checkpoint priority, eager candidate construction, late file-reader replacement, original failure propagation, and independent instances. `VANTALINE_LOCAL_SELECTION_BASELINE_SOURCE` replays the two pre-extraction functions. Tests load no model or GPU and perform no paid inference or PLC access; existing warmup, training, model snapshot and assembled HTTP checks remain required.

smoke_image_payload_codec.py replays original functions with VANTALINE_IMAGE_PAYLOAD_BASELINE_SOURCE and tests the actual codec with synthetic bytes. It covers MIME fallback, read and conversion errors, strict decoding, empty data URLs, key/candidate order and late decoder resolution. Existing provider, image-job, model and HTTP contracts remain required.

Local model selection composition checks compare parsed AST structure, including exact lazy callbacks and entry aliases, instead of interpreter-specific ast.unparse whitespace. Mutation probes reject changed dependencies, eager override evaluation, wrong aliases/imports and duplicate assignments. PR 268 initial CI failed on Python lambda rendering; that failed run is retained, and the corrected test requires a new full CI run.

`smoke_detection_task_requests.py` compares five original entry functions through `VANTALINE_DETECTION_TASK_REQUESTS_BASELINE_SOURCE` with the explicit service. It covers target-account restrictions, lock release on sync failures, selected-callback timing, payload-before-lookup error ordering, permission/duplicate rejection, timestamp failures, owner overlay, JSON and PostgreSQL delete order, and failures after persisted writes. Existing assembled HTTP/RBAC, detection and pipeline contracts remain required. The tests preserve existing partial effects and do not claim atomic multi-store mutations.

`smoke_detection_rules.py` compares original functions through `VANTALINE_DETECTION_RULES_BASELINE_SOURCE` before the candidate service on Windows/Linux. It covers malformed existing configuration, finite/NaN thresholds, selected-accessory filtering, global/task count handling, shallow-copy identities, owner visibility, error precedence and partial mutations on save/conversion failure. Inverse AST and unchanged HTTP/RBAC/detection/model checks remain required.

`smoke_camera_detection_request.py` runs the original async function through `VANTALINE_CAMERA_DETECTION_BASELINE_SOURCE` and the explicit service on Windows/Linux. Synthetic encoded images and callback substitutes cover permission/station denial before upload reads, evidence-before-analysis, completed/pending duplicates, decode errors, filesystem/model/settlement/publication failures, best-effort error settlement, late callbacks across await and pre-try filename errors. Tests preserve original error settlement attempts without replaying analysis; no physical PLC or paid model is used. Existing HTTP/RBAC, browser-PLC and ordinary-upload safety contracts remain required.

smoke_detection_rule_composition.py tests two separately composed FastAPI instances with separate stores and ContextVars, concurrent async HTTP entering synchronous thread-pool routes, hidden-task rejection, response/error schemas, duplicate registration rejection and no construction I/O. Existing smoke_detection_rules business assertions remain; its fixture now supplies direct capabilities and its assembly check observes eight inputs. Keep full assembled HTTP/OpenAPI/permission/route-order checks and neighboring detection/catalog contracts. No real model, PLC or production records are used.

smoke_analysis_composition.py verifies graph/guard identity, no constructor I/O, independent state and exact direct presentation bindings. Existing analysis projection/publication and JSON/PostgreSQL repository assertions run through composed services as well as their original fixtures. Keep root full HTTP/permission/lifecycle, source guards, model and release checks. Isolated test graphs do not demonstrate shared-JSON multi-app safety.

smoke_dashboard_task_ownership.py runs the same original function via VANTALINE_DASHBOARD_TASK_BASELINE_SOURCE and the owned service. It checks exact create payload/order, first-name-match updates, duplicate/missing accessory filtering, counts/label fallback, owner-field overlay, errors before clock, insert/update partial effects after save failure, post-save projection failure, late collaborator selection and independent supplied capabilities. Existing detection request assertions remain with all 30 suppliers verified; retain accessory routing HTTP and detection task-store real PostgreSQL tests. No paid model or PLC calls occur.

`smoke_accessory_selection_dimensions.py` compares five original functions via `VANTALINE_ACCESSORY_SELECTION_BASELINE_SOURCE` with the actual existing-domain services. It covers alias precedence, shallow reference identity, missing reference presets, render minima/errors, eager serialization, duplicate requested IDs, repeated fallback serialization and partial failures. Existing catalog/dimension, rendering, pipeline, model and HTTP contracts remain required.

smoke_accessory_workflow_ownership.py compares the four original root helpers (VANTALINE_ACCESSORY_WORKFLOW_BASELINE_SOURCE) with owned implementations. It covers ID mutation, readiness short circuit/force, first-source/error behavior and status failure before/after partial mutation. Candidate-only checks verify direct root exports and actual shared service owners. Retain existing metadata, object preprocessing, queue, candidate artifact, reference evidence, image execution and model/HTTP contracts. Tests use synthetic records and substitutes only.

`smoke_image_worker_ownership.py` compares original startup using `VANTALINE_IMAGE_WORKER_OWNER_BASELINE_SOURCE` with the new owner on Windows/Linux. Two simultaneous starts produce one thread; live/dead thread handling, factory/start/liveness failure identity, lock release, late loop selection and separate owner registries retain their contracts. Worker job, accessory preparation and assembled HTTP/lifecycle regressions remain required.

`smoke_pipeline_runtime_ownership.py` compares original state initialization through `VANTALINE_PIPELINE_OWNER_BASELINE_SOURCE` with independent runtime instances: lock recursion rules, independent registries, guarded concurrent registration and original timestamp assignment. Existing list tests now replace the clock on its actual owner, retain old-baseline support and keep every ordering, error, permission, five-second boundary and partial-effect assertion. Advance, auto-Agent, recommendation, reconciliation and store suites remain required.

`smoke_auto_optimization_runtime_ownership.py` compares original state initialization via `VANTALINE_AUTO_OPT_OWNER_BASELINE_SOURCE`, checking reentrant guard behavior, cross-thread exclusion, separate registries and instance isolation. Original label processing, shadow evaluation, requests, training scheduling and state-store regressions remain required.

smoke_auto_optimization_settings_composition.py verifies all 24 actual application capabilities, six bound aliases, zero settings callbacks through the entry, live environment reads/error order and alternate-owner isolation. The nine existing domain smokes replace these stable callables at actual test ports using auto_optimization_test_ports.py; their business/order/concurrency assertions remain. This is an intentional narrowing of arbitrary root rebinding compatibility, not complete observational equivalence of Python monkeypatching. Retain downstream dataset/training, two-account threadpool, model snapshot, HTTP and isolated PostgreSQL state-store checks.

smoke_plc_legacy_worker_ownership.py compares original start helpers via VANTALINE_PLC_LEGACY_WORKERS_BASELINE_SOURCE with the new state owner. Worker Thread objects, sleeps and worker callbacks are substitutes; two real caller threads test serialization. Cover alive/dead/start-failure state, ordinary Lock serialization, heartbeat exit/epoch/error paths, poll/reconcile catch and sleep ordering. Verify actual startup is still no-op and source/browser/lease contracts stay intact. No serial or live PLC is used.

smoke_plc_active_lease.py replays the original root guard through VANTALINE_PLC_ACTIVE_LEASE_BASELINE_SOURCE or the owned station method. Synthetic cases retain missing-state lookup order, zero-clock fallback, every fence, short-circuit numeric errors, optional epoch, reference identity and configuration callback partial effects. Candidate checks bind the actual owner and construct separate services without IO. Existing rebind, diagnostic reservation and confirmation fixtures now resolve the real method export and retain every behavioral/PostgreSQL assertion. The original 32 lazy station ports remain checked, plus the new clock supplier; full HTTP, source and PLC contracts remain required.

smoke_plc_activation_policy.py compares the original six functions through VANTALINE_PLC_ACTIVATION_BASELINE_SOURCE against the owned policy. Synthetic checks cover falsey repositories/transports, fingerprint field order and read extension, env normalization, ContextVar isolation across threads, serial ImportError versus other failures, ordered errors, disabled/capture gates and late helper selection. Candidate assembly starts nothing and the unchanged startup function remains a single return. Retain legacy dispatch/capture/worker, configuration diagnostics, HTTP, dependency and physical-I/O source guards; no real transport/provider is used.

Run python scripts/smoke_plc_runtime_coordination.py for retained owner renewal/takeover, quarantine/deadline boundaries, receipt isolation, narrow row persistence, exception identity and late heartbeat selection. With an isolated VANTALINE_POSTGRES_DSN it also races independent repositories on an absent owner and verifies rollback, namespace isolation and connection closure. The original-source mode is VANTALINE_PLC_COORDINATION_BASELINE_SOURCE. All heartbeat callbacks are substitutes; this is not hardware or DB-clock fencing acceptance.

Run python scripts/smoke_plc_dispatch_records.py for namespace distinctions, shallow copies, reverse lookup, exact dispatch hash/strict passed identity, guard release before verification, late validation selection and conflict evidence preservation. VANTALINE_PLC_DISPATCH_RECORDS_BASELINE_SOURCE replays the same behavior on the original entry. Existing synthetic legacy dispatch and typed mutation suites remain required; no physical PLC is used.

Run python scripts/smoke_plc_legacy_operations.py for legacy single-iteration gating, malformed configuration, queued record selection/reasons, pending-slot/owner races, exception and finally behavior, stale-read rejection, and read argument/order contracts. VANTALINE_PLC_LEGACY_OPERATIONS_BASELINE_SOURCE replays the original two bodies. Tests supply synthetic read/transport callbacks and never start worker loops or contact a physical PLC.

smoke_web_shell_composition.py covers original/candidate response errors, provider short-circuits, mutable path and route suppliers, query-preserving redirects and separate real ASGI route sets with API precedence. Keep the existing actual navigation/auth smoke and full application HTTP snapshot; these are distinct from startup/shutdown acceptance.

`smoke_retired_entry_tails.py` freezes the seven original entry bodies and compares the retained AST prefix, signature, decoded executable instructions, flags/free variables and interpreter-supported exception tables. It explicitly permits only enumerated unused closure-cell allocations (eleven on Python 3.10, ten on Python 3.11+) to disappear, with no reachable closure/DEREF/frame access. Internal frame/code introspection therefore narrows; bytecode identity is not claimed. The full unchanged assembled HTTP contract remains, and actual ASGI requests for anonymous/member/admin identities compare validation/status/error bodies and helper calls against the frozen bodies. Unreachable helpers are poisoned. No lifespan, provider or physical PLC is started.

The retained-tail compiler contract supports Python 3.10 frame-created closure cells and CO_NOFREE semantics and Python 3.11+ MAKE_CELL/exception tables explicitly. Both branches retain exact AST prefixes, enumerated cell variables, complete executable-instruction comparison and the same seven-endpoint HTTP replay; compiler-version handling does not skip behavior checks.

`smoke_repository_composition.py --postgres` verifies inert construction, two independent connection owners, environment/connector invalidation, broken-connection rebuild, same-thread close, reset during another active thread, original HTTP-safe errors and native ASGI thread-pool identity/connection isolation with real PostgreSQL. Its two applications are focused fixtures, not the complete production factory. Existing endpoint probe and cutover assertions remain intact while connector replacement targets the explicit owner; the source guard now verifies the actual composition module and its bindings.

The authentication composition fixture and real PostgreSQL replay now instantiate the actual AuthenticationDomain, retaining the inherited HTTP/account/session/locking assertions. Two graphs retain separate identities/locks/login caches/routes. Root binding tests verify the same identity and repository owner, direct media policy, and that rebinding private entry path/TTL/repository exports does not rewire the graph. The explicit SessionService.settings capability remains replaceable for tests; startup environment parsing and default values are unchanged. These are domain graphs, not yet two full production create_app lifecycles.

smoke_record_composition.py replays all original record-access tests through the actual composer, including lazy lookup, hidden read/write denial and concurrent ASGI-to-thread identity restoration. It also checks inert separate graphs, owned access/audit identity and actual entry binding against poisoned private root aliases. Original ownership/audit/access tests remain independently required. Domain fixtures are not complete production application factories.

smoke_bootstrap_locations.py compares explicit root resolution and all 30 paths with the frozen b2d6f07 bootstrap, including environment precedence, empty/relative/tilde inputs, missing roots, callback error identity and per-instance paths. It verifies the actual entry anchor and frozen-source correspondence. No files or data are migrated; domain tests do not establish complete create_app lifecycle isolation.

smoke_cost_composition.py replays all original CostTests assertions; their explicitly separate CostSource/fake Ledger checks remain direct business/HTTP tests. Added contracts prove inert cost/pipeline constructors, distinct owners, exact root method/path bindings, unchanged full HTTP contract and real root 401/403 before any source capability. Authenticated synthetic replay replaces only explicit cost storage dependencies and preserves repeated source reads. Original cost tests remain separately required; this adds no production PostgreSQL capacity or atomic-ledger guarantee.

The image worker owner now tracks coordinator admission and every child thread independently of the subprocess registry. Closing this owner rejects new lookups/launches and waits up to the supplied deadline for admitted work, thread-owned database cleanup and final persistence; timeout explicitly returns undrained. Already admitted work may start while closing. Start/prepare failures preserve existing evidence and do not requeue work or retry providers. The maximum active-child concurrency remains unchanged; immediately completed jobs may replenish capacity earlier. Scope cleanup happens on each owning thread, including model resolution inside the job callback. No store or provider callback runs under the lifecycle lock, and joins occur outside that lock. This adds the owner drain capability and wires queue/thread scopes; application shutdown/factory integration and MCP drain remain separate pending work. It does not promise full application shutdown or cancel running image providers.

`python scripts/smoke_image_worker_drain.py` uses actual threads/events, synthetic job callbacks and fake connections to exercise admission during lookup/start, failed starts, coordinator/child exceptions, final-save contention, independent owners, and same-thread connection cleanup. Existing queue ordering, concurrency and persistence checks remain; target-call assertions now execute the scoped wrapper. No paid model, PLC or production database is used.

A successful image-owner drain proves that admitted threads and their cleanup scopes have exited. It does not prove that final persistence succeeded or that every subprocess was reaped; task failures and subprocess evidence remain governed by the execution service.

Image coordinator and child starts now retain uncertain-start handles even if `is_alive()` is false, child lists are pruned, or a later coordinator replaces the current handle. A failed start revokes an unentered target, and shutdown must join retained handles before reporting drained. A never-started handle may remain undrained; stored running evidence is preserved and never requeued. Deterministic interrupted-bootstrap tests cover both launch paths and later coordinator replacement.

MCP operations now have a client-owned admission boundary covering the complete tool dispatch, including the existing stdio failure fallback, and warmup cleanup. New operations are rejected before transport or fallback after shutdown begins; same-thread nested work belonging to an already admitted operation can finish. Startup and request serialization share the client lock, independently of the admission condition. The bounded shutdown waits for admitted work, then terminates and reaps owned transports; an expired deadline returns undrained without cancelling a blocked call or inducing fallback. Recoverable close retains terminated processes for later reaping. Existing provider selection, prompts, wire messages and transport-failure fallback behavior are unchanged. The client retains the startup warmup thread and admits it before construction/start. Shutdown drains this reserved startup operation, joins its owned thread, then retires transports. Application shutdown registration and full production factory integration remain pending.

`python scripts/smoke_mcp_drain.py` exercises blocked stdio, concurrent initialization, rejection before fallback, draining an already active fallback, nested admission, warmup failure/rejection, independent clients and timeout/reap retries. Transport callbacks use synthetic responses; one harmless local Python sleeper verifies actual terminate/wait/stream cleanup. No model provider, PLC or production database is accessed.

MCP recovery retains both live and already-exited displaced processes by identity. An exited transport skips termination but still participates in final wait and stdin/stdout cleanup; EOF followed by the existing fallback cannot lose this cleanup ownership.

MCP warmup startup retains its enabled check and original callback, thread name and daemon setting, but now starts through its client owner. Duplicate live starts and starts after closing are rejected. Thread construction/start failures release reservations exactly once; a thread that started before a start error remains tracked. Already reserved warmup may finish nested client operations after closing begins; unrelated threads cannot inherit that admission. No join occurs under admission or client locks.

`python scripts/smoke_mcp_warmup_ownership.py` verifies ten actual-thread startup races using synthetic callbacks only: pending constructor, duplicate start, pre/post-start failures, post-completion failure, target exception, self shutdown, cross-thread rejection and independent owners. The runtime-policy suite also checks the real enabled startup callback delegates to its owner.

A failed or interrupted warmup `Thread.start()` cannot use `is_alive() == False` as proof that no OS thread exists. A target not yet entered is revoked, but its handle is retained and shutdown reports undrained until joining proves completion. A start that never actually created a thread can therefore remain conservatively undrained; no target or paid fallback is replayed. A deterministic interrupted-bootstrap regression covers the late-start window.

Uncertain warmup handles are also retained across a later warmup start. Replacing the current handle cannot erase a revoked thread that has not yet confirmed startup/completion; shutdown joins every retained handle.

YOLO warmup starts now belong to their `YoloWarmup` instance, including pending thread construction and every admitted thread. Each thread enters and releases its repository scope on that same thread. Closing rejects later starts and waits outside lifecycle/status locks; a timeout reports undrained without cancelling inference, changing model selection, or requeuing work. Existing repeated-start behavior and per-model handling remain. Application-wide lifecycle registration and per-app graph construction remain separate pending work. Prompt source manifest v188 retains the same 518 ordered files.

Interrupted or failed warmup starts retain uncertain handles even across later starts. An unentered target is revoked and every retained handle must be joined; a never-started handle remains conservatively undrained. The tests cover delayed native bootstrap, interrupted startup, later thread replacement and same-thread scope exit.

Run scripts/smoke_training_thread_drain.py for real-thread pending preparation/publication, registration/start interruption, overwritten registries, uncertain native bootstrap, selected callback arguments, scope cleanup, two-thread connection isolation and native tail waits. Existing training runner/background tests retain model snapshot and original failure/evaluation-order checks; target identity checks execute the new wrapper to verify the originally selected callback. No paid model, real PLC or external process is required.

Run scripts/smoke_codex_background_drain.py for closed admission, original target-before-name selection, exact argument identity, pending factory across close, scoped cleanup and separate owners. Retain the20 shared training lifecycle tests and all34 background generation/business tests; old target identity checks invoke the selected wrapper with synthetic process/provider substitutes. No physical PLC, paid inference or real Codex subprocess is required.

smoke_transfer_progress_drain.py covers rejection before event construction, returned native handles, reporting blocked during close, event construction crossing close, same-thread repository cleanup, scope-entry failure cleanup and owner isolation. Existing transfer callbacks and transport tests remain required; fixtures use synthetic callbacks and no remote worker.

Reporter-specific failure coverage also verifies original provider/constructor exception identity with event-registry cleanup, plus interrupted native bootstrap where close remains false until the revoked late target exits and removes its event.

Run scripts/smoke_auto_optimization_thread_drain.py for all three starter types: closed admission, exact callback arguments, same-thread repository cleanup, overwritten public registries, pending construction across close and independent owners. Keep the original label-processing, shadow-evaluation and training-scheduling tests, with selected wrappers executed against synthetic callbacks. Retain shared lifecycle interrupted-start tests. No paid inference, physical PLC or remote training is used.

scripts/smoke_application_foundation.py verifies two real foundation graphs, no construction I/O or workers, same-thread interleaved identities/connections, instance-local environment/connector changes, real ASGI sync-thread exception cleanup and actual-entry owner binding. With VANTALINE_POSTGRES_DSN it also verifies distinct PostgreSQL backend sessions and independent reset. Keep repository/auth/record regressions and full HTTP route/lifecycle contracts; complete create_app/startup-failure/shutdown isolation remains separate.

scripts/smoke_auto_optimization_pool_scope.py runs real executors with synthetic callbacks: two worker-local identities, simultaneous submissions, one reused worker, scope-entry failure, blocked exception cleanup and the actual batch orchestration. It verifies per-task connections close on the owning thread and parent ContextVars are not implicitly propagated. Existing processing contracts remain unchanged. Model snapshot propagation needs its own explicit capability and acceptance test.

scripts/smoke_auto_optimization_model_binding.py includes the original bare-executor counterexample, version1 captured before version2 mutation, preserved secret reference, parallel private snapshots, empty legacy snapshot, exception restoration, missing dependency rejection, and actual batch downstream training-vision binding. A separate test confirms identity/read-cache/write-authorization ContextVars are not copied. Earlier processing and pool-cleanup tests retain all assertions with explicit synthetic resolver fixtures.

The model-binding suite also fails the resolver on the second pending sample, verifies that the first callback executes exactly once and is joined, and retains the existing claimed states and batch error without any retry.

Run scripts/smoke_text_job_drain.py with synthetic callbacks to verify both text-job capacities, closed admission before persistence, pending claims, same-thread scope exit, constructor failure, uncertain and post-start failure, actual interrupted native bootstrap, scope entry/exit failure and duplicate-view failure. Retain document/preparation dependency tests and shared training lifecycle regressions; the document cleanup-failure expectation now requires its acquired slot to be returned even when cleanup raises. No paid model or physical PLC is used.

Run scripts/smoke_http_application.py against the frozen original constructor: middleware order and settings, actual CORS preflight/compression/error responses, disabled default docs, deferred invalid-regex errors, environment error order, inert construction and independent repeated shells. Retain full assembled HTTP/OpenAPI/order, authentication/media and artifact admission tests. Shell isolation does not establish complete domain or worker lifecycle isolation.

scripts/smoke_http_upload_runtime.py verifies lazy explicit providers, two simultaneous ASGI apps with independent reservations, capacity refusal and cleanup on route failure, provider failure without fallback, and unchanged default/local behavior. Fixtures use in-memory budgets and synthetic multipart bodies without disks, cloud SDK calls, credentials, PostgreSQL or paid inference. Existing upload storage/integration and full HTTP contracts remain required.

scripts/smoke_artifact_runtime_provider.py freezes the original global get_runtime and compares configuration reads, builder arguments, errors, cached/local behavior and failure retry semantics. Native-thread cases verify one build per owner and independent owners while one builder blocks. Default-provider delegation and explicit HTTP upload use retain the existing artifact/HTTP regressions. All builders are synthetic; no credentials, cloud traffic, paid models or live database are used.

Frozen HTTP constructor evidence is pinned to canonical Git LF bytes with an explicit checkout attribute. The raw SHA guard still rejects any changed fixture; this fixes platform-dependent test acceptance without changing application behavior or historical task snapshots.

Frozen artifact-runtime evidence is checked out as canonical Git LF bytes. The original raw SHA and immutable fixture Git blob remain unchanged; a CRLF working-copy mismatch is a test portability failure, not a runtime regression.

Run scripts/smoke_pipeline_thread_drain.py for all three scheduler types: closed admission before registry effects, real thread/same-thread scope cleanup, pending constructors crossing close, constructor and post-start failures, original duplicate gates, isolated owners and callback exceptions without replay. Keep all three original pipeline runtime suites; thread doubles now expose liveness and target-selection checks execute synthetic selected callbacks. Shared training lifecycle tests retain interrupted-native-bootstrap coverage; full HTTP, model-binding and repository checks remain required.

The pipeline ownership suite also exercises admitted multi-item batches spanning close, later-item constructor or post-start failure, and repository scope entry/exit failure. It distinguishes owned native-thread completion from successful persistence and registry cleanup; constructor and scope-entry failures can preserve inflight evidence.

Run scripts/smoke_extraction_thread_drain.py for closed admission without new task writes, pending source writes crossing close, real worker cleanup, interrupted native bootstrap, constructor errors preserving claims, and independent owners with manual/duplicate requests. Retain every extraction dependency test; fake worker threads now expose is_alive for lifecycle pruning. Providers are synthetic and no external inference runs. Full HTTP, model binding and shared thread-lifecycle checks remain required.

scripts/smoke_comparison_cleanup.py exercises real bounded semaphores for local/Qwen final-settlement failures, clear failures and combined failures, Qwen timer-cancel failure, and no-acquisition paths. Assertions retain durable attempting evidence, one settlement/model attempt, original single-fault exception identity and explicit combined-fault context. Existing comparison dependency tests intentionally replace the previous leaked-slot expectations; all other model, timeout, late-result and no-retry assertions remain.

Run scripts/smoke_comparison_thread_drain.py for waiting/running timers, cancellation versus actual join, pending constructors, interrupted native bootstrap, post-start error, callback registry pruning, scope-entry/exit failure, parent-before-timer drain, distinct owners and actual local/Qwen submissions with global slots poisoned. Actual blocked repository cleanup retains each acquired capacity until scope exit, including a raised cleanup error. Preserve all cleanup, dependency, root HTTP, model and shared lifecycle tests. All providers are synthetic and network calls are prohibited.

The comparison ownership smoke also resolves every shipped prompt-source path against the real service root and computes the real source fingerprint; synthetic manifests alone cannot verify packaged path correctness.

scripts/smoke_pdf_import_drain.py uses real threads and synthetic repositories/rendering to test repeated and concurrent startup, independent owners, blocked processing and same-thread cleanup, pending construction across close, interrupted native bootstrap, post-start error and constructor failure without implicit replacement. Retain all original label dependency tests, actual PostgreSQL label HTTP contracts, shared lifecycle tests and complete route/order contracts.

This offline lifecycle integration retains native-history/readiness and detection composition from actual main dcb4805 and follows artifact-owner candidate 6b648b5. Owned production/tests and ordered entry match reviewed 28de9fa; both canonical fixture corrections are already retained. The bundled manifest is v204 with 523 unique sources; earlier paragraph counts refer to their original individual candidates. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Publication must use independently reviewed domain-scoped PRs on accepted main, with full hosted and release gates; this offline combined tree is not a blanket grouped publication approval or complete application factory.

The two frozen HTTP-constructor and artifact-runtime Python fixtures use Git-enforced LF checkout bytes. Their tests hash the actual canonical Git content before executing it, so Windows checkout conversion cannot invalidate the frozen contract. The HTTP fixture expected hash is corrected from its original CRLF working-copy digest to the committed LF blob digest; fixture source content and the artifact fixture digest are unchanged. The integration verification retained both the initial private runner filename error and the subsequent observed CRLF artifact-baseline failure.

scripts/smoke_web_shutdown.py checks actual parent-to-child native-thread fan-out after an initial failed drain, same-thread scope exit, one remaining-time budget including prior hooks, exception redaction, partial progress, repeated/concurrent/reentrant close, two separate ASGI shells, registration rejection and idle teardown of the assembled production graph without startup. The frozen HTTP contract changes only shutdown callback registration; original stop-hook order is separately asserted. No paid provider, PLC or customer fixtures are used.

Shutdown permanently closes these resource owners. The same production app instance must not be started again after teardown; process restart or a separately constructed resource graph is required. Two independently allocated HTTP shells are tested, not repeated startup of the same production graph. The native fan-out test executes actual pipeline auto-agent run and advance schedule/run methods with synthetic business ports, using the production shutdown binding order.

The retained MCP shutdown first waits for active operations, then terminates and reaps its owned transport process. The coordinator adds no forced termination or training-subprocess cancellation. The synthetic tests do not prove live Uvicorn request quiescence, nonempty production shutdown timing, or an acyclic graph under arbitrary replacement of live dependency suppliers.

This offline shutdown replay follows lifecycle candidate 7d7886a and preserves current native history, readiness, model/tail and canonical LF fixes. Four owned runtime/test/contract blobs match reviewed 82313c5. Manifest v205 lists 524 sources. The 480-second shutdown allowance remains cooperative and requires ASGI request quiescence; complete independent application composition is still pending. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Run python scripts/smoke_detection_artifact_ports.py on Linux. Two real ArtifactStore graphs with synthetic object clients use identical business paths concurrently; default runtime selection is poisoned. Tests cover upload-before-analysis, byte hashes, no local fallback, failure isolation, lazy providers, selected runtime stability during argument evaluation, unused AI/retired/annotation output paths, explicit missing dependencies and late-bound shared defaults. Existing annotation, analysis, AI analysis, upload, artifact integration and PLC source contracts remain required. The first integration run caught definition-time capture of get_runtime; the corrected helper resolves that default at call time.

This offline detection artifact replay follows shutdown candidate 8618f7a and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 713010a. Manifest v206 lists 524 sources. Storage suppliers retain call-time selection; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Run python scripts/smoke_detection_media_ports.py on Linux, plus existing detection media/upload/local-model, artifact integration and assembled HTTP/PLC contracts. Concurrent real ArtifactStore graphs use synthetic object clients, identical source/output names and independent reference caches. Tests verify image bytes, descriptor cache separation, model alias identity and constructor-failure lease cleanup, successful/failed video analysis and capture-release failure cleanup. The default image runtime is poisoned and an AST guard requires explicit providers throughout detection. InspectionImageStore retains ordinary Exception-to-None behavior while artifact errors propagate; this is not proof of uniform video cleanup, model cache rollback after lease-exit failure, or whole-app isolation.

This offline detection media replay follows artifact candidate e7e12b2 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 5e86530. Manifest v207 lists 524 sources. Explicit stores retain original cache, error and video cleanup behavior; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Run python scripts/smoke_http_artifact_ports.py on Linux plus existing incoming workflows, background API, artifact integrations, HTTP shell/upload and assembled HTTP contracts. New ASGI tests combine the real security middleware with synthetic catalog/review authorization ports, two independently supplied stores, 401/403/404-before-storage, successful bytes, Range, output HEAD/304, and identity cleanup. A poisoned default constructor proves response-boundary isolation. Explicit None dependency results must return an error without fallback; the initial independent counterexample is retained. This is not a claim that underlying incoming catalog/review stores are fully per-app.

This offline HTTP artifact replay follows detection media candidate f2b4519 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 301b6c1. Manifest v208 lists 524 sources. Explicit missing file dependencies fail closed while genuinely omitted legacy arguments retain their documented default. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Run python scripts/smoke_incoming_artifact_ports.py on Linux, alongside the existing incoming workflows, artifact integration, HTTP media, assembled HTTP and dependency checks. Real incoming services and security middleware operate against two real ArtifactStore instances with synthetic object clients and OCR; identical paths/IDs contain different bytes. The test covers upload, canonical image, evidence generation, 401/403/404, Range, owner cleanup, retention isolation, failed publication without fallback and missing/falsey dependencies. Existing local partial-failure and algorithm assertions remain required.

This offline incoming workflow replay follows HTTP artifact candidate 2336193 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 8e4d991. Manifest v209 lists 524 sources. Consistent captured files/images dependencies retain original partial-write, exception and retention semantics. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Run python scripts/smoke_background_file_ports.py on Linux and retain all five existing background suites, artifact integrations and assembled HTTP/boundary/PLC checks. Two real ArtifactStore graphs with synthetic clients exercise same-path seeding, enumeration, manifests, uploads, version conflicts and owner-local updates; capture permission and publication failures precede validation. Missing/None and falsey dependencies plus seven root bindings are checked. No real generation/training/PLC is invoked.

Independent review rejected the first background-file candidate because its new manifest path repeated the service directory. The original failed head and failing actual-source test log are retained. The corrected relative path must pass the existing smoke_comparison_thread_drain.py actual-shipped fingerprint check over every selected source; synthetic placeholder manifests alone do not validate shipped paths.

This offline background file replay follows incoming candidate 841c4ba and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed c80ed68. Manifest v210 lists 525 sources, with the corrected service-relative background capability path. Captured file capabilities retain original ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Run python scripts/smoke_background_image_ports.py with all existing background suites and the actual-shipped fingerprint check in smoke_comparison_thread_drain.py. Two real stores at identical paths produce distinct source/variant pixels and synthetic validation inputs. Remote read failures must propagate before generation/analysis, and a failed first variant publication must not attempt later variants. The first test run referenced a nonexistent synthetic client.put method; the corrected probe observes the real object-store put method and retains that original harness failure log.

This offline background image replay follows file candidate 89875c1 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 09ef623. Manifest v211 lists 525 sources. Three image services use explicit adapters; generator and runner defaults remain outside this slice. Original algorithms and golden contracts remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Run python scripts/smoke_background_generation_ports.py with existing background task/local process contracts, file/image port tests and actual-shipped fingerprint checks. Real stores and a synthetic image_job context exercise identical paths across two generators, generated PNG/log publication, nonzero exit evidence, generation conflicts without replay, owner-specific source checks and retained model binding. No actual process or paid generator is invoked.

This offline background generation replay follows image candidate 9a2d333 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 22986e9. Manifest v212 lists 525 sources. Generator and task runner now receive captured file adapters, retaining model snapshots, subprocess policy, partial outputs and exception behavior. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Run scripts/smoke_training_file_ports.py alongside the existing training dataset, input/state and preview workflow/renderer suites, artifact integrations, assembled HTTP/boundary/PLC checks and actual shipped-source fingerprint verification. Synthetic object stores at identical paths exercise independent dataset/plan content, stat-based cache versions, stale approval state and publication failures. No training process, paid model, PLC or customer data is used.

The initial synthetic training file test used a non-business top-level directory and correctly remained on local storage. The fixture was corrected to the production outputs/training_datasets hierarchy; its initial failure log is retained. Production storage routing was unchanged.

This offline training file replay follows generation candidate 2fdb9ee and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 214fe9c. Manifest v213 lists 526 sources, appending training/file_ports.py. Five services capture matching file capabilities while preserving validation, cache, write ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Run scripts/smoke_training_image_ports.py with the existing preview renderer pixel/metadata goldens, training dataset and preview workflow/input suites, artifact integrations, HTTP/boundary/PLC contracts and actual-source fingerprint verification. Synthetic real-store tests check distinct pixels at identical paths, selected-store YAML, image publication failure and missing dependencies without training or model calls.

This offline training image replay follows file candidate 94c1eec and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 75d63a9. Manifest v214 lists 526 sources. Image adapters are captured and YAML selects its writer per call; arbitrary private rebinding is not preserved as an atomic hot swap. Algorithms, goldens and public signatures remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Run scripts/smoke_training_resource_ports.py with original training resource mutation, background writes and artifact/worker tests, real artifact integrations, assembled HTTP/boundary/PLC and actual-source fingerprint checks. Synthetic store graphs at identical paths verify mutation isolation, version conflicts, archive contents and digest leases; destructive test operations are confined to temporary synthetic storage.

The first synthetic archive probe retained the small generic work quota and correctly failed capacity admission. Its private fixture now uses the established archive-test work allowance; production quotas and archive guards are unchanged, and the initial failure log is retained.

This offline training resource replay follows image candidate 9063ace and preserves current history, readiness, model/tail, shutdown, corrected boundary documentation and canonical LF guards. Production and test blobs match reviewed fbf5434. At this replay boundary manifest v215 selects 526 sources. Explicit resource and archive capabilities preserve file operation ordering, strict digest failures, partial publication and archive formats. Current source changes require actual-main rebind, independent review and full CI/release acceptance before publication.

Run scripts/smoke_accessory_file_ports.py with original accessory management, image-job metadata, sprite metadata and artifact integration tests, HTTP/boundary/PLC and actual-source fingerprint checks. Synthetic stores at identical paths verify upload bytes, guide/anchor evidence, existence-dependent dimensions and failure order without paid calls or customer files.

The first accessory port draft also injected files into a later, unrelated ImageJobMetadata dataclass with the same import name; the full assembled-app regression caught this before publication. Injection is now limited to the provenance service. Synthetic failure probes were corrected to observe put_stream and assign explicit fixture mtimes instead of assuming memory-store timestamps. Initial failures remain recorded.

This offline accessory file replay follows training resource candidate 7ae44bf and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed eccc553, including ordered constructor bindings. At this replay boundary manifest v216 selects 526 sources. Upload ordering, partial publication, provenance collisions and sprite fallbacks remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

Run scripts/smoke_accessory_evidence_ports.py with original background evidence/library selection, reference evidence and preview asset tests, artifact integrations, HTTP/boundary/PLC and actual-source fingerprint verification. Real stores with synthetic clients exercise identical-path image/hash isolation, catalog existence checks and remote errors before fallback or matching.

This offline accessory evidence replay follows file candidate b368404 and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed 466195b. At this replay boundary manifest v217 selects 526 sources. Decode and hashing selection, source mutation, partial publication and error propagation remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

Run scripts/smoke_accessory_catalog_ports.py with original materialized asset and preview sprite suites, artifact integrations, assembled HTTP/boundary/PLC and actual-source fingerprint tests. Synthetic stores at identical paths verify dimensions, alpha decoding, existence ownership and mutation before remote errors.

This offline accessory catalog replay follows evidence candidate 2d442b2. All owned production/test blobs and the complete ordered entry match reviewed 87ebec1; current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v218 selects 526 sources. Existing catalog mutation and decoder behavior are unchanged. Exact-source neighbor evidence is reused; current targeted, assembled HTTP and fingerprint checks are distinct. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_accessory_gallery_ports.py with original accessory preparation/gallery regressions, artifact integrations, assembled HTTP/boundary/PLC and actual-source fingerprints. Synthetic same-path stores exercise candidate thumbnails, gallery pixels and read/publication failures without paid providers.

This offline accessory gallery replay follows catalog candidate 8f453b3. Owned source/test blobs and ordered entry match reviewed 7f02e9d, including the single inert ImageFiles allocation relocation. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v219 selects 526 sources. Existing partial publication and failed-write behavior are unchanged. Neighbor evidence is reused only for exact source; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_accessory_edit_ports.py with original accessory file HTTP/pixel/permission tests, accessory management, artifact integrations and HTTP/boundary/PLC/source-fingerprint checks. Synthetic stores verify same-path uploads, crops, reference selection, deletion ownership and partial effects on failure.

This offline accessory edit replay follows gallery candidate 1b5c003. Owned source/test blobs and ordered entry match reviewed 6f78019. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v220 selects 526 sources. Authorization order, crop geometry, partial publication and deletion failure behavior remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_accessory_preprocessor_ports.py with original object preprocessing and workflow ownership regressions, artifact integration, assembled HTTP/boundary/PLC and actual-source fingerprints. Two synthetic stores verify source pixels, metadata, publication isolation and failures before or after publication; no paid cutout is invoked.

This offline accessory preprocessing replay follows edit candidate 96c7b23. Owned source/test blobs and ordered entry match reviewed dbcd8b5. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v221 selects 526 sources. Discovery, decode, publication, status and exception ordering remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_agent_reference_ports.py with original pose asset/render and photo-highlight workflow regressions, artifact integration, HTTP/boundary/PLC and actual-source fingerprint checks. Identical-path synthetic stores verify existence and encoded bytes without model calls.

This offline Agent reference replay follows accessory preprocessing candidate b1d835d. Owned source/test blobs and ordered entry match reviewed efa17b7. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v222 selects 527 sources. Reference selection, digest acceptance, path mutation and exception ordering are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_agent_pose_storage_ports.py with original pose rendering/materialization contracts, Agent reference tests, artifact integration and assembled HTTP/boundary/PLC/source-fingerprint checks. Synthetic stores exercise identical output paths and metadata, materialization ownership, and failure after image publication without any provider calls.

This offline Agent pose storage replay follows reference candidate 9a90408. Owned source/test blobs and ordered entry match reviewed 11919d9. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v223 selects 527 sources. Image and metadata publication ordering, local/remote callback timing and partial mutations remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_agent_photo_image_ports.py with original photo-highlight builder/image/workflow contracts, artifact integration and HTTP/boundary/PLC/source-fingerprint checks. Real synthetic stores and model substitutes verify identical-path source/mask/ROI outputs and failures without paid calls.

This offline Agent photo replay follows pose storage candidate a56b846. Owned source/test blobs and ordered entry match reviewed 6afd82e. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v224 selects 527 sources. Provider attempts, diagnostic failure handling, publication and item mutation order are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_agent_background_image_ports.py with original pipeline-background publication contracts, artifact integration and HTTP/boundary/PLC/source-fingerprint checks. Synthetic stores cover matching absolute paths, pixel identity, provider payload and partial publication failures; no paid models are called.

This offline Agent background replay follows photo candidate 5bcd15e. Owned source/test blobs and ordered entry match reviewed e8c63a3. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v225 selects 527 sources. Existing library fallback, partial file and manifest publication, callback timing and errors remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_pipeline_status_file_ports.py plus original pipeline resource-status and task projection/list checks, artifact integration and HTTP/boundary/PLC/source-fingerprint tests. Synthetic stores at identical paths verify isolated availability, missing resources and propagated storage failures.

This offline pipeline availability replay follows Agent background candidate 37a1265. Owned source/test blobs and ordered entry match reviewed ed60859. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v226 selects 527 sources. First-match, pending-state, bypass and storage error behavior are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_text_cleanup_file_ports.py with original extraction/standard/document-review and extraction-drain tests, artifact integration, HTTP/boundary/PLC/source-fingerprint checks. Synthetic stores verify owner isolation, tombstone-before-delete, retention of losing remote media and original failure propagation.

This offline text cleanup replay follows pipeline availability candidate 6f13fd9. Owned source/test blobs and ordered entry match reviewed c89fbbd. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v227 selects 528 sources. Cleanup exception precedence, tombstone-before-deletion and partial effects remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_training_catalog_file_ports.py with original resource and trained-model catalog checks, artifact integration and full HTTP/boundary/PLC/source-fingerprint tests. Real synthetic stores verify identical-path catalog isolation, model existence, missing manifests and storage failure propagation.

This offline training catalog replay follows text cleanup candidate 1199028. Owned source/test blobs and ordered entry match reviewed 8f0715d. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v228 selects 528 sources. Local and indexed selection, permission ordering and repeated reads remain unchanged. Exact-source neighbor evidence is reused; current targeted, real PostgreSQL, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_text_media_runtime_port.py and the original smoke_text_media.py --root, artifact integrations, HTTP, dependency, PLC and fingerprint contracts. Synthetic independent stores exercise same-path isolation, hybrid fallback, checksum and availability errors, and lazy PDF partial publication without paid inference.

This offline text media replay follows training catalog candidate 920904d. Owned source/test blobs and ordered entry match reviewed f71e6c4. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v229 selects 528 sources. Local path, hybrid readiness, size, digest and publication rules remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_training_runner_file_port.py alongside the unchanged training runner, artifact integration, HTTP, boundary, PLC and model dependency contracts. Synthetic independent stores verify selected datasets, COS fallback rejection, reservation/error ordering and pinned snapshots without starting real training.

This offline training runner replay follows text media candidate da44932. Owned source/test blobs and ordered entry match reviewed 9b024f4. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v230 selects 528 sources. Running-state persistence, runtime mode, repeated existence reads, failure settlement and pinned model restoration remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_runpod_artifact_runtime_ports.py with original training artifact and storage integration regressions, HTTP/boundary/PLC and model dependency contracts. Two synthetic stores verify same-path exports/imports and partial publication/error boundaries without executing models or contacting RunPod.

This offline RunPod artifact replay follows training runner candidate b7b8760. Owned source/test blobs and ordered entry match reviewed 671f233. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v231 selects 528 sources. Repeated runtime selection, cleanup exception masking, publication ordering and local replacement remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_runpod_transport_runtime_ports.py with original RunPod flow/transfer, artifact integration, HTTP/boundary/PLC and model dependency checks. Synthetic stores exercise independent same-job claims, unknown submissions, upload isolation, admission and authorization-before-runtime failures. No real provider request is made.

This offline RunPod transport replay follows artifact candidate 97a9963. Owned source/test blobs and ordered entry match reviewed 12f1743. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v232 selects 528 sources. Durable claim ordering, ambiguous submit retention, streaming limits and partial upload publication remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_codex_api_runtime_port.py with original Codex dependencies, PostgreSQL API/batch tests, artifact integrations and HTTP/boundary/model/source fingerprint contracts. Independent synthetic stores and real API routes exercise evidence isolation, authorization before runtime selection and propagated read failures.

This offline Codex HTTP replay follows transport candidate 0beaefc. Owned source/test blobs and ordered entry match reviewed 42fcded. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v233 selects 528 sources. Authorization, media exception mapping and partial publication ordering remain unchanged. Exact-source neighbor evidence is reused; current targeted, isolated PostgreSQL, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_label_media_runtime_ports.py with label dependencies, lifecycle, PDF drain, summary worker, standalone bootstrap/signals, PostgreSQL process/control/deployment/readiness tests and original label API smoke. Synthetic storage owners cover HTTP and both worker media paths without model calls; no concurrency, admission, settlement or drain assertion may be removed.

This offline label media replay follows Codex HTTP candidate 41743d5. The original provider-only delta from reviewed b696cba is applied while retaining current native history summaries and their test adapters. All other owned source/test blobs and ordered entry match the reviewed source. At this replay boundary manifest v234 selects 528 sources. Current history, readiness, model/tail, shutdown and canonical LF guards remain. Worker claims, PDF cleanup, provider identity and error ordering remain unchanged. Current isolated PostgreSQL and affected integration checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_comparison_media_owner.py, both HTTP media-owner suites, artifact integrations, original Codex pytest contracts against isolated PostgreSQL, full HTTP and actual-source fingerprint checks. Synthetic reservations exercise selected-owner budget admission, error settlement, local mode and cleanup without invoking a model.

This offline comparison media replay follows current-history label candidate f447c5d. Owned source/test blobs match reviewed 552cea1; the entry remains unchanged. Current native history and its explicit-provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v235 selects 528 sources. Worker budget and reservation settlement ordering, ambiguous paid outcomes and CLI selection remain unchanged. Current isolated PostgreSQL and affected integration checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

Run scripts/smoke_web_artifact_composition.py with original runtime-provider behavior, artifact integration, HTTP media ownership, detection storage and assembled HTTP/boundary/model/source-fingerprint checks. Synthetic independent stores test identical-path file/image views, lazy concurrent construction, owner-local configuration fencing and failure propagation.

Run scripts/smoke_stream_config.py against the frozen c25e1bb handler and the service. Tests cover request defaults, two owners, late load/save bindings, evaluation order, failure partial effects and actual root route delegation. Preserve assembled HTTP, app-config, model dependency, fingerprint and PLC frontend route-order checks.

Artifact composition binding guards compare parsed AST structure, including whitespace-equivalent lambda syntax and wrong-supplier negatives, so Python 3.10 and newer unparsers cannot change the outcome.

This offline Web artifact composition replay follows comparison candidate d2ae509. Owned source/test blobs and ordered entry match reviewed a0fa2ed, including the Python 3.10 structural source guard. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v236 selects 529 sources. The Web graph owns a fresh lazy runtime provider and two focused views; this is not a complete application factory or proof of independent underlying resources. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

This offline stream configuration replay follows Web artifact candidate f2e481b. Owned source/test blobs and ordered entry match reviewed 14f6504. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v237 selects 530 sources. Existing load, mutation, save and post-save response ordering remain unchanged; configuration is not given a new transaction or lock. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

IncomingTextStore now resolves JSON single-record lookups through its own list methods. The two callbacks through the application entry have been removed; narrow repository, guard, path and row-adapter inputs remain. Tests replace the owning store method and cover two independent stores, preserving missing-loader errors, call-time repository selection and lock behavior. TextStorage allocates both text stores and their shared write lock per composition, without opening a connection or retaining a user. Manifest v238 selects 531 source paths, including text_inspection/storage_composition.py. This closes the store self-reference only; full application factory and route/lifecycle instance isolation remain unfinished.

Run `python scripts/smoke_text_storage_composition.py` for inert construction, caller-thread repository selection, concurrent independent HTTP storage graphs, and shared-versus-distinct lock isolation. Run both existing store suites with `--root --postgres` against an isolated database; these checks do not establish full production application-factory isolation.

The text storage lock belongs to `TextStorage` and its public lock property cannot be rebound. The entry lock alias initially references it; replacing that private entry alias no longer replaces either store guard. Remaining route/write adapters still use their existing inputs until their domain composition is migrated. This intentional narrowing of private test seams does not change configured runtime behavior.

Run python scripts/smoke_incoming_composition.py for the actual incoming workflow builder: inert construction, shared writer lock, single duplicate query, absent-row decoder ordering, two HTTP apps with equal task/capture IDs, per-owner failure isolation and operation-time store selection on a native thread. Keep incoming workflow/store/artifact tests, the migrated source composition guard, assembled HTTP, fingerprint, documentation and PostgreSQL contracts. These domain HTTP graphs do not establish complete production create_app isolation.

The incoming domain owns its response-file capability and exposes separate catalog and inspection route registration methods. Application composition calls them at their original positions, preserving the intervening Beta comparison routes and the existing media authorization/error behavior. The actual domain-builder HTTP tests exercise these methods; this does not claim a completed whole-application factory.


Catalog graph contracts cover inert construction, equal run IDs with separate owner catalogs/model caches, concurrent ContextVar propagation into thread execution, operation-time replacement of owned query services, and real application composition aliases. Existing local-model/catalog/pipeline/media assertions remain; test replacement targets now identify their actual service methods. Real PostgreSQL catalog tests and whole HTTP/source-fingerprint contracts remain required. No real model or PLC is used.

scripts/smoke_accessory_image_composition.py exercises the integrated candidate image graph with synthetic provider ports: inert construction, explicit missing-resolver failure, native thread-constructor failure before admission, final-save failure without a repeated provider call, retained model binding and independent native drain while another owner remains operational. Original queue, execution, diagnostics, ownership and drain assertions remain; operation replacement and source guards now target the actual domain owners/constructor. Synthetic per-domain evidence does not establish two complete production apps, paid inference, physical PLC operation or production capacity.

The image composition source contract preserves all original external supplier expressions in tests/backend_contract/accessory_image_composition_ports.json, frozen from parent 5b61947. Parsed-expression AST checks match each exact execution/diagnostic edge and all eight root ownership aliases; mutants cover swapped provider methods, same-leaf wrong owners, wrong external groups and a substituted model resolver. The old e251 source guards accepted five wrong-binding mutants and are superseded by these stronger checks; original business assertions remain.
