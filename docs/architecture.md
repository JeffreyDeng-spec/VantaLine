# Architecture

Pipeline Agent feedback registers through `pipeline/agent_feedback_api.py`; `pipeline/agent_feedback.py` owns the unchanged action priority and mutations. Access, policy and runtime capabilities preserve the single task lock, legacy pose-tool execution inside it, feedback appended before branch validation, save/public under lock and scheduling afterward. The cancel action still updates task state only; worker cancellation remains with its current owner.

The pipeline task-list GET now registers through `pipeline/task_list_api.py`; `pipeline/task_list.py` owns the existing process-shared five-second reconciliation gate, all-task synchronization, visibility filtering and unlocked scheduling/projection order. Narrow access, reconciliation and presentation capabilities replace root namespace dependencies. This remains a write-capable GET; SQL pagination and read-lock optimization are separate later work.

Pipeline Agent chat registers through `pipeline/agent_chat_api.py` at its historical route position. `pipeline/agent_chat.py` owns the two locked task reads and a single out-of-lock Agent decision; narrow late-resolved access/runtime capabilities preserve authorization, deep snapshot, partial commit/save effects and scheduling order. Decision policy, paid call evidence and task runner remain with their existing owners.

Manual pipeline advance and cancel requests now register in their original order through `pipeline/advance_control_api.py`; `pipeline/advance_control.py` owns validation, marking and pause-state updates. Two focused late-resolved capability groups preserve the nested task/registry lock, out-of-lock scheduling, cancellation signal between two locked task reads, and current partial effects. The runner, scheduler, inflight registry and cancellation mapping remain with their original owners.

Pipeline task POST now registers at its historical route position through `pipeline/task_create_api.py`; `pipeline/task_create.py` owns the complete creation use case. Focused late-resolved capabilities preserve permissions, owner resolution, two-stage AI persistence, recommendation scheduling and partial effects. The Web entry still owns storage, the shared lock and the actual AI activation/optimization/scheduler implementations; create extraction does not finish pipeline domain migration.

Pipeline task DELETE now registers at its original route position through `pipeline/task_delete_api.py`; `pipeline/task_delete.py` owns cancellation, authorization, row deletion and ordered linked-resource cleanup. Three narrow late-resolved capability groups preserve cancellation before record access, the locked row delete and sequential cleanup outside the pipeline-task lock. Storage, worker cancellation and the resource deletion implementations remain with their existing owners.

Pipeline task PATCH now registers at its original route position through `pipeline/task_update_api.py`; `pipeline/task_update.py` owns the complete update use case. Three focused, late-resolved capability groups preserve authorization, policy, persistence and the original lock boundaries. The Web entry still owns task storage and the shared lock; background advance runner and scheduler flows remain there. This is one domain boundary, not completion of the pipeline migration.

Pipeline dataset and model resource availability projections live in `pipeline/resource_status.py`. Three late-resolved readers preserve the existing dataset finder, AI task loader and trained-spec loader at their original call sites. File existence and caller-provided preloaded sets/lists retain their current semantics; this extraction adds no caching or batch reads.

Pipeline task labels and accessory display names now live in `pipeline/task_snapshots.py`. Three late-resolved capabilities preserve the current AI-task label load, accessory lookup and public root label adapter at their original call sites. The Web entry still owns linked-task storage and the configuration-writing recovery path; this projection adds no cache or model-snapshot rewrite.

Pipeline recommendation signature, next-stage choice, readiness, cached-parameter consumption and pre-generation selection live in `pipeline/recommendations.py`. Two narrow capability groups preserve per-call method and root-helper lookup. The Web entry still owns the pinned-model background runner, scheduler, locks, thread lifecycle and persistence; recommendations retain caller-owned task mutation.

AI detection task-to-pipeline card synchronization lives in `pipeline/ai_task_sync.py`. Four narrow capability groups keep identity, accessory, visibility and projection dependencies late-bound. The Web entry retains its three public adapters; the list endpoint still owns locking, loading and persistence. Existing cards are updated in place, and the coordinator does not retain a user, connection or task list.

Pipeline background plate prompt and publication now live in `agent/pipeline_background_publication.py`.
One coordinator retains library matching, provider fallback, variant creation and manifest/task
publication order. Six narrow capability groups resolve dependencies at their original read
points; the Web entry keeps the public adapters. Provider transport and training background
catalog remain separate, and this extraction does not make filesystem and task updates atomic.

Background-library selection lives in accessories/background_library_selection.py. A
candidate catalog owns visibility and ordered file selection; a separate matcher owns
image-signature comparison. Five narrow capability groups and one threshold getter
expose the existing dependencies. The training catalog, model providers and pipeline
background publication remain separate.

Background evidence lives in accessories/background_evidence.py. Three stateless
numerical helpers accompany separate plate-derivation and reference-signature services.
Six narrow capability groups keep source lookup, mask calculation, projections and
policy reads explicit. Constructors retain dependencies only; callers own paths, items
and output effects.

Accessory profile generation lives in accessories/profile_generation.py. A three-method
service receives profile, MCP/configuration, reference-policy and update capabilities.
Provider transports remain external. The composition stores lazy capabilities before the
existing MCP handler registration; public functions retain their original definition
positions.

Accessory profile prompt payloads, required-profile projections and reference resolution
live in accessories/profile_payloads.py. One three-method service separates identity,
profile projection and catalog capabilities. Provider transport and inference remain
outside this service.

Accessory physical-size payloads, profile dimension projections, normalization and
application live in accessories/physical_dimensions.py. One five-method service uses
separate value/default and update capabilities. Shared numeric parsing remains outside
this service.

Accessory fallback profile construction and normalization live in
accessories/profile_projection.py. A focused two-method service uses four narrow groups
for identity, text, dimensions and reference capabilities; provider transports and model
configuration remain separate.

Accessory display naming lives in accessories/display_labels.py through a four-method
service and two narrow policy/text groups. Size text remains a standalone projection.
The module imports only Python typing and regular-expression capabilities plus its
ports; shared text normalization remains outside the accessory domain.

Accessory reference paths, file context and chroma evidence live in
accessories/reference_evidence.py. ReferenceEvidence receives four narrow capability
groups and stores no request, user or connection state. The standalone saturated chroma
mask remains pure numerical computation; file/context methods preserve I/O, mutations
and callback evaluation points.

Preview and rectified-document loading now live in accessories/preview_assets.py. One
loader receives root/suffix policy, path resolution and loader/selector capabilities
through three narrow groups. A standalone candidate selector retains RNG use and shallow
metadata projection. Constructors store dependencies without opening files or owning
request state.

Asset canvas composition now lives in accessories/compositing.py: four standalone
helpers retain rectangular mask, crop, render-box and document-paste behavior, while
AssetCompositor owns masked, physical and rotated pasting. Two narrow capability groups
supply geometry and paste operations without owning runtime state. Document paste and
compositor methods retain canvas mutation.

Preview sprite decoding and render-input selection now live in
accessories/preview_sprites.py. A focused renderer receives inventory, pose, media and
rotation capabilities; its constructor stores dependencies without resolving or owning
runtime state. The decoder is existing image I/O, not a pure calculation.

Materialized accessory assets live in one domain module with separate sprite and text
catalog services, plus pure metadata-presence and confirmation-detail helpers. Five
narrow capability groups keep path resolution, pose metadata and readiness dependencies
explicit; this asset inventory does not own HTTP authorization or request state.

Accessory pose layout, selection and preview policies share one domain module with four
pure helpers and three focused services. Eight narrow typed groups retain dependencies
at their original lookup sites; no policy module imports the Web application. Preview
errors use a typed exception factory supplied by the composition root.

Accessory cutout geometry separates stateless foreground masks and green spill from
object selection and chroma processing. Two small services use three typed dependency
groups; no geometry module imports the Web entry or owns a model session.

One accessory cutout runtime owns the successful rembg session cache and reentrant
lock. It is constructed at the original resource initialization point; only model loading
is lazy. Both background cutout consumers share that owner through narrow dependencies.

Material alpha calculation lives in stateless accessory mask helpers and a small material
policy dispatcher. One local capability group keeps policy and branch selection at the
original lookup sites; root adapters retain exact public signatures and defaults.

Single sprite artifacts and batch canvas normalization live in separate accessory services.
Six narrow capability groups expose geometry, metadata and image operations at original
lookup points; both root adapters keep exact signatures and caller-owned state.

Sprite dimension metadata lives in accessory values, footprint, scale and render-metadata
modules. Six narrow capability groups expose policies, collaborators and image reads;
no metadata service imports the Web entry. Root adapters retain signatures and defaults.

Masked sprite geometry uses seven stateless helpers in `accessories/mask_geometry.py` and
five operations in `sprite_geometry.py`. Two narrow operation groups keep helper selection
at existing call sites; root adapters preserve signatures and defaults.

Object sprite preprocessing lives in `accessories/object_preprocessing.py` with domain-local
policy, source, runtime, cutout, component, metadata and artifact capabilities. Root
adapters preserve the public signature and original fallback ordering.

Accessory component analysis lives in `accessories/crop_analysis.py`; crop selection and
quality checks live in `crop_selection.py` with a two-callback geometry/trimming interface.
The two pure functions need no service state. Root adapters retain existing signatures.

`agent/photo_highlight_builder.py` owns the real-photo sprite coordinator through narrow
source policy, runtime, mask, model policy, audit, artifact and metadata interfaces.
The root adapter retains its public provider annotation; internally the coordinator uses
`PoseImageProvider`. This move establishes ownership; its existing large workflow still
needs a separately reviewed internal decomposition.

Photo-highlight image input and comparison use narrow policy/geometry interfaces in
`agent/photo_highlight_image_input.py` and `photo_highlight_comparison.py`. Pure mask
decoding and ROI computation live in `photo_highlight_masks.py` with ordinary explicit
numerical-library imports. Root adapters retain public entry points.

Photo-highlight source readiness, object selection and task transitions live in
`agent/photo_highlight_sources.py`, `photo_highlight_selection.py` and
`photo_highlight_workflow.py`. Seven capability groups keep media, policies, task state
and model callbacks explicit. The root source-path adapter preserves its definition-time limit.

Agent pose materialization separates chroma selection, cutout fallback, sprite construction
and asset registration into `agent/pose_chroma_policy.py`, `pose_cutout_pipeline.py`,
`pose_sprite_builder.py` and `pose_asset_materialization.py`. Nine narrow capability groups
preserve dependency lookup without storing tasks, users or connections.

Agent pose call registration, execution and sample preparation live in
`agent/pose_call_registration.py`, `pose_call_execution.py` and `pose_sample_preparation.py`.
Seven narrow capability groups keep state, model access, call records, rendering and
preparation dependencies explicit. Constructors retain dependencies, never tasks or users.

Agent pose rendering separates configuration projection, prompt/reference content and artifact
writing into `agent/pose_render_configuration.py`, `pose_render_content.py` and
`pose_artifact_store.py`. Six narrow capability groups preserve per-use dependency lookup.
Constructors retain dependencies only; callers retain task state and model bindings.

Agent pose planning separates payload/validation policy, accessory generation/cache and
task aggregation in `agent/pose_plan_policy.py`, `pose_plan_generation.py` and
`pose_plan_assembly.py`. Eight narrow groups preserve dependency lookup and caller-owned state.

Agent reusable pose assets and template policy live in `agent/pose_assets.py` and
`agent/pose_templates.py`. Seven narrow capability groups preserve per-use lookup.
Reference path normalization retains caller-owned asset objects and existing readiness gates.

Agent orchestration state and tool-call records live in `agent/orchestration_state.py` and
`agent/tool_call_records.py`. Four typed capability groups preserve runtime lookup and
caller-owned dictionaries, lists and call objects. Stage adapters forward all extra metadata.

Agent action state transitions and turn commit ordering live in `agent/pipeline_actions.py`
and `agent/pipeline_turns.py`. Seven typed capability groups preserve per-use callback and
exception-matcher resolution. Tasks, users and pending advances remain caller-owned inputs.

Agent conversation updates, decision context, decision policy and decision flow live in
`agent/conversation.py`, `decision_context.py`, `decision_policy.py` and `decision_flow.py`.
Ten narrow capability groups preserve lookup order without retaining request identities. The
application decision adapter retains its single model-profile binding decorator; services do
not bind a second snapshot. Conversation changes remain caller-owned in-memory updates.

Agent settings HTTP handlers live in `agent/settings_api.py`, with six typed capability
groups in `settings_api_ports.py`. The application retains the same four route registrations
and request schemas. Authorization and callback evaluation order are preserved; constructors
only retain dependencies. Modern model-profile loading remains in the composition root.

Agent protocol helpers, chat transport, connection discovery and parameter recommendation
live in `agent/protocol_policy.py`, `chat_transport.py`, `connection_discovery.py` and
`recommendation.py`. Nine narrow capability groups in `invocation_ports.py` preserve call
and exception evaluation order. Constructors do no I/O. Request identity is read from the
existing context at the original call site; services do not cache users or configurations.

Agent settings normalization, permission-aware projection and legacy file persistence live in
`agent/settings_policy.py`, `settings_projection.py` and `legacy_settings_store.py`. Narrow typed
capabilities in `settings_ports.py` preserve dependency evaluation order. Constructors perform no
reads and services retain no request identity or connection. The modern model-bound loader remains
in the composition root; legacy persistence does not replace purpose-based model resolution.

Key identity helpers and local secret-file access live in `model_providers/key_identity.py`
and `local_secret_store.py`. Narrow typed runtime, path, codec, filesystem, environment, policy
and store-access capabilities live in `key_material_ports.py`. Constructors perform no reads;
no service-level key cache, request identity or database connection is added. The composition root
keeps the existing callbacks and process-environment lifecycle.

Provider key normalization, filtering and public projections live in `model_providers/key_registry.py`.
Five narrow capability groups in `key_registry_ports.py` supply key material, presentation and
the separate JSON/image/Agent policies. The service performs no constructor reads and holds no
request identity or database connection. Secret persistence and identity helpers remain explicit
application callbacks; root adapters retain their original signatures.

Provider defaults, configuration validation and public URL formatting live in
`model_providers/configuration_defaults.py`, `configuration_validation.py` and `public_urls.py`.
Four narrow capability groups in `configuration_ports.py` retain policy lookup and callback
timing. Services perform no constructor I/O and hold no request state. Root adapters retain
all public signatures and existing callers.

Legacy JSON and image settings used during model-profile migration live in
`model_providers/legacy_json_settings.py` and `legacy_image_settings.py`. Narrow settings,
presentation, policy and environment capabilities are declared in `legacy_settings_ports.py`.
Constructors perform no I/O; calls read current dependencies at their original expression
boundaries. The two root migration callbacks retain their original signatures.

Public AI/image/service/model/configuration projections live in `auth/status.py`.
`auth/status_ports.py` separates permission policy, settings sources and nested projections.
The service performs no constructor I/O and retains no user or database connection. Root
adapters preserve public signatures, the model field allowlist and callback evaluation order.

Provider selection/key rotation, retry classification/evidence and JSON/image retry flow live
in `model_providers/selection.py`, `retry_policy.py` and `retry_flow.py`. Typed capabilities in
`orchestration_ports.py` keep factories, evidence and timing explicit. Services perform no
constructor I/O and hold no current user, connection or per-call state. Root adapters retain
public signatures and detection prompt binding; request budgets and evidence remain call-local.

Agnes and Qwen image transports live in `model_providers/agnes_transport.py` and
`qwen_image_transport.py`, sharing narrow capabilities in `image_ports.py`. The root constructors
bind callbacks and existing model resolvers. Each instance owns its settings and raw-text state;
constructors perform no I/O. Generation remains the accounting boundary, including Agnes's
existing one-time response-format compatibility fallback.

Gemini JSON, cached-content and image operations live in `model_providers/gemini_transport.py`.
`gemini_ports.py` provides narrow request, parsing, image-decoding, URL-formatting and error
capabilities. Each instance owns its existing usage and raw-text state; constructors perform no I/O.
The application adapter retains the cached-content TTL default captured at class definition and
passes it explicitly to the service. JSON/image methods use the existing instance-accounting
adapter; cached-content creation retains its original direct-call accounting behavior.

The OpenAI-compatible JSON transport lives in `model_providers/openai_transport.py`.
Typed IO and error capabilities in `openai_ports.py` preserve dependency evaluation order; the
application subclass only supplies these capabilities and the existing resolver. Each provider
owns its settings and usage state. The additive `metered_instance` adapter reuses the existing
accounting decorator with an instance resolver; it introduces no shared mutable instance cache.
The resolver callable is selected at composition time and its service is read per call. Constructors
perform no I/O.

Provider exceptions, JSON/data-URL parsing and HTTP error classification live in
`model_providers/errors.py`, `payloads.py` and `http_errors.py`. The package imports no application
entry. Pure parsing helpers remain functions; parser and HTTP services receive narrow callable
dependencies without constructor I/O or request state. Root exception names remain aliases to
the same new class objects. Transport ownership is described above.

Detection media responsibilities live in `detection/image_encoding.py`,
`inspection_image_store.py`, `reference_images.py` and `reference_sheet.py`; `media_ports.py`
defines codec, rendering, storage-policy and cache capabilities. The composition root owns the
existing process-local reference-sheet cache and lock. Services hold no current user or database
connection, perform no constructor I/O, and keep per-call arrays and descriptor construction local.

Ordinary image and video uploads use `detection/image_upload.py` and `video_upload.py`.
`upload_ports.py` supplies narrow authorization, paths, codecs, file-copy and analysis capabilities;
`video_results.py` owns frame projection and AI aggregation. HTTP signatures, route order and the
video model-snapshot decorator remain on the application adapters. Camera/PLC orchestration remains
separate. Constructors perform no I/O and services retain no request identity or connection.

Profile-cache identity/context, JSON persistence and provider orchestration live in
`detection/profile_cache_policy.py`, `profile_cache_store.py` and `profile_cache.py`. Narrow
capabilities supply formatting, paths, filesystem operations, time, provider construction/type and
existing record services. Constructors do no I/O. Root cache save/load adapters remain late-bound
for accessory workflows; business modules do not import the application entry.

Presence inspection orchestration lives in `detection/presence_inspection.py`. Its input,
generation, output and policy ports are explicit; constructors do no I/O and each invocation owns
its timings and reference counters. The MCP registry retains the root adapter. The service adds no
model-snapshot scope; it uses the existing caller scope and supplied provider settings.

Detection orchestration lives in `detection/analysis.py` and `ai_analysis.py`, with narrowly
scoped configuration, routing, inference, output, profile and evidence capabilities in
`analysis_ports.py`. Constructors do no I/O. The root AI adapter retains its original model-profile
pin; ordinary analysis calls that decorated entry. Independent compositions explicitly bind their
AI service at composition time. Bare business methods do not establish a snapshot scope themselves.

`detection/annotation.py` owns normalized box geometry, image overlays and AI output writes.
A pure geometry function and one service receive narrow image, formatter and storage capabilities.
Callees resolve at their original expressions while later constants/arguments retain their order;
constructors do no I/O. Root signatures remain adapters and the module never imports the app.

`detection/presence_results.py` normalizes provider presence responses through narrow count,
text, string-list, metadata and label capabilities. Each formatter is resolved at its original
expression, before its arguments. The service does no constructor work, retains no request state
or connection, and preserves both traversals, duplicate-ID behavior and metadata merge order.

`detection/failure_projection.py` owns failure/model response projection through explicit formatter,
metadata and label capabilities. `failure_results.py` assembles failure results through settings,
profile, failure and model callbacks. Constructors perform no reads. Original traversal, per-call
formatting, eager label defaults and shared payload fields remain in their original order.

`detection/presence_payload.py` builds provider request payloads with explicit formatting providers.
Each expression captures its formatter before reading argument fields. `presence_validation.py`
contains pure response-coverage and count validation. Constructors do no work; root signatures,
repeated reads, output text and original exception boundaries remain unchanged.

Accessory alias lookup lives in `accessories/lookup.py`; required-item resolution lives in
`detection/requirements.py`. Both use explicit identity policies, and ordinary missing-item labels
are provided only at each fallback. Constructors perform no reads, retain no request identity or
connection, and do not import the application entry point. Existing root signatures remain adapters.

`training/legacy_worker_tasks.py` settles retired dataset/training calls through an updater
provider and clock. The provider captures the current updater before timestamp arguments evaluate.
`legacy_worker_refresh.py` returns the same public projection with retirement flags and setdefault
note. Historical bodies remain after their early returns behind narrow, explicit capabilities;
constructors create no runtime state or I/O and do not restore remote execution.

`training/legacy_worker_requests.py` owns three retired request entry points and the pure retired
status response. Each request's first executable statement still raises the original error, before
reading arguments or capabilities. Historical code after those guards is retained with explicit
settings, HTTP, JSON-helper and sleep ports; it remains unreachable. No constructor performs I/O.

`training/worker_watcher.py` holds the retired watcher no-ops, lazy interval settings and a loop
with explicit interval/tick/error-report/sleep callbacks. Constructors do no work. The original
root startup handler stays registered in place and is called as before; it remains a no-op that
creates no watcher thread. The dormant loop is not started by this extraction.

`training/worker_artifacts.py` imports legacy worker model artifacts through three explicit
capabilities: owner output directory, safe name and clock. Standard-library validation and file
operations retain their order. The constructor does no I/O and the root adapter performs late
lookup; no global current-user or database connection is introduced.

`training/worker_bundle_metadata.py` owns worker bundle metadata through explicit digest and
file-manifest callbacks. `worker_bundle_submission.py` owns timeout policy and outer submission
through narrow file, transport, progress, update and timing capabilities. Constructors do no I/O;
root adapters preserve late lookup. The original stream-then-form fallback remains unchanged.

`training/worker_transfers.py` owns streamed legacy worker upload/download through explicit
URL, header, HTTP and UUID capabilities. `transfer_progress.py` publishes shared counters through
explicit task updates and event/thread factories. Constructors do no I/O; root adapters keep late
lookup. Only these helpers add no retries; the outer bundle submission retry/fallback remains.

`training/remote_training.py` owns the legacy remote training request and response flow with
explicit settings, archive, update and HTTP capabilities. `worker_compatibility.py` holds pure
worker payload/status conversion and a separate artifact projection with a sanitizer callback.
Constructors do no I/O; retired worker early-return paths and existing multipart retry code remain.

`training/background_validation.py` owns empty-scene validation through one explicit analysis
port. `background_query.py` owns visible media and catalog/default selection. `background_uploads.py`
separates training uploads from task capture orchestration with narrow path, record and state
capabilities. `background_api.py` preserves the four route signatures and positions. Async uploads
keep their original file-copy execution; request identities remain arguments or late-bound providers.

`training/background_codex.py` owns background process and thread launch through typed ports.
`background_task_runner.py` binds the task model snapshot exactly once before execution, even in
independent service compositions. `background_task_submission.py` reuses the training save and
thread capabilities; constructors do no I/O and retain no request identity or live connection.
Task registry and thread targets remain late-bound at their original evaluation points.

Local background pixel generation and minimum-image initialization live in
`training/background_variants.py`; identifier allocation and metadata updates are in
`background_writes.py`. `task_background_store.py` owns task background file replacement with
explicit identity, path and record capabilities. Constructors retain no request identity or
connection and perform no reads. The root temporarily forwards the original helper signatures.

Background-set persistence is in `training/background_manifest.py`; `background_seeding.py`
retains default image copying and minimum-image initialization before directory reads. Identifier,
file enumeration and catalog projection live in `background_catalog.py`, with available-set
selection in `background_selection.py`. Explicit late-bound path, record and permission callbacks
preserve cross-call behavior. Constructors do not read files or retain request identities.

`training/jobs_query.py` owns the ordered training/image job catalog and single-job projection;
`task_mutations.py` owns training task edit/delete orchestration. `jobs_ports.py` declares narrow
list/refresh capabilities and `jobs_api.py` preserves the original nine route positions. Image
control routes delegate once to their existing services; no process or retry logic moves into the
adapters. Query/mutation instances contain callbacks, not request identities or database connections.

RunPod transfer uses narrow resolver and task-update getters, preserving lookup before
record/path/clock argument effects. Streaming persistence retains the original exception
and cleanup boundaries, including evidence left by BaseException and post-replace errors.

RunPod transfer routes are assembled by `training/runpod_transfer_api.py` at their original
position. `runpod_transfer.py` handles token, expiry, output containment and task metadata;
`runpod_upload_store.py` owns streamed writes, limits, temporary files and replacement. Stream
creation remains lazy inside the original cleanup block. Instances have explicit path, record,
clock, hash and size-limit capabilities without constructor reads or shared request state.

Training launch uses four narrow getters at nine original call sites: selected inputs,
dataset lookup, asset preparation and status scoping. Each callback is captured after
preceding business work and before argument effects, without eager caching or retries.

Training launch business flows live in `training/launch_submission.py`; `status_query.py` scopes
status reads before invoking the existing projection. `launch_api.py` registers start, generate and
status separately at their original positions, preserving the intervening RunPod transfer routes.
Dependencies are typed, late-bound capabilities. Constructors never read configuration or retain
users; the existing submission service still owns saving, registering and starting training tasks.

Four narrow getters capture the path resolver, background selector, sanitizer and selected-
accessories callback before their original argument effects. Resolver selection refreshes
for every asset; stat/read failures retain existing conversion and mutation boundaries.

Training preview fingerprints live in `training/preview_cache.py`, approval checks in
`preview_approval.py`, dataset input validation in `dataset_input.py`, and state hydration in
`status_projection.py`. Each has explicit callbacks for its own records, identity checks and file
roots. Constructors hold no request state and perform no reads. Status hydration can still settle
visible interrupted tasks through the existing lifecycle service; it is not a pure read.

Nine narrow getters preserve callback capture before configuration reads, request attributes,
response construction and pose-sequence access. Getters refresh after rescoping and between
previews; artifact writes retain original partial-output and exception semantics.

Training plan and preview HTTP adapters are in `training/preview_api.py`, registered in their
original order. `preview_query.py` scopes and sanitizes plan reads; `preview_submission.py` owns
preview generation and user-state updates. `preview_artifacts.py` alone creates preview output
directories and writes plan JSON using lazy output/jobs roots. Configuration and identity are
explicit callbacks; no constructor reads or per-request state are stored in these services.

Preview renderer contracts retain exact original-runtime baselines for OpenCV 4.10 and
4.13/5; runtime selection affects only test expectations, not application composition.

Six narrow getters preserve callback capture before shape/list access, truth tests and metadata
string conversion. Existing Name-only providers remain direct. Per-record mask lookups use local
builtin dictionaries and do not require extra getters; rendering algorithms remain unchanged.

`training/preview_renderer.py` now owns the complete existing preview drawing workflow.
`training/preview_ports.py` defines capabilities scoped to its surface, assets, sizes, poses, layout
and detection thresholds. They hold callbacks, not users, connections, RNGs or per-render state.
The application composes late-bound adapters and keeps the original public drawing signature.
Sprite loading, asset transforms and training jobs remain separate future
extractions. This move preserves the entire algorithm and metadata projection.

Three narrow callback getters preserve four capture boundaries: both fallback axes, each placed
rectangle intersection and contour shape access. Binding refreshes per axis/list item; the existing
canvas provider remains lazy. Pure geometry and image functions retain their original bodies.

Preview layout is divided into pure `training/preview_geometry.py`, mask conversion/filtering
in `training/preview_masks.py`, and placement search in `training/preview_placement.py`.
Placement and visible-mask services receive narrow callbacks; construction reads no runtime state.
The application keeps original public signatures and captured ROI defaults, and forwards through
late-bound callbacks. Canvas size is read separately only for axes that need fallback. The complete
preview renderer remains in the application until its own extraction and caller verification.

Training background manifest/library lookup now lives in `training/background_library.py`;
`training/background_rendering.py` owns the unchanged split, synthetic image, crop, augmentation
and render functions. File, selection and render dependencies are explicit lazy ports. Selection
retains its existing default-background seeding side effects and repeated lookup through the file
helper. Constructors do not read configuration, files or identity. The main preview renderer and
background management/job workflows remain in their existing modules for a later extraction.

Resource writes use three narrow getters at four owner/path argument boundaries.
Marker conditions, permissions, mutations and saves remain inside the existing process guard.
Existing partial filesystem effects and exception handling remain unchanged.

Training resource modification and removal now use `training/resource_mutations.py` and five
thin adapters in `training/resource_api.py`. `training/dataset_links.py` and
`pipeline/resource_links.py` retain their existing shared guards around load, record mutation
and persistence. The composition root supplies late identity, permission, catalog and retirement
ports. Constructors perform no I/O; each application owns its service bindings.

Dataset sample resolution and audit timestamps, model path resolution, configuration scope
and the resource HTTP payload use six narrow callback getters. Each lookup remains before
its original argument effects; request identity and visibility checks keep their existing order.

Training resource manifests and ordered filesystem lookup live in `training/dataset_catalog.py`;
`training/resource_queries.py` owns dataset/model/task/AI aggregation and `training/resource_api.py`
registers the two resource GET routes at their original position. Typed file, audit, access and
record ports remain late-bound in the composition root; constructors do not read identity or storage.
Roots retain enumeration order, physical duplicate IDs remain, and missing historical datasets are
filled once by ID. Task listing still settles interrupted visible local tasks through its existing
lifecycle service. Dataset detail hydration still precedes lookup permission checks.

Archive export path resolution and artifact output use narrow callback getters, alongside
the reviewed writer provider. Function lookup stays before task-derived arguments. The
earlier nullable hash definition and later strict hash override retain their original order.

Training ZIP packaging and strict file hashing now live in `training.dataset_archives`.
`training.runpod_exports` prepares dataset download and artifact upload metadata;
`training.runpod_artifacts` verifies and imports returned bytes or uploaded ZIP members.
Each service has explicit path, policy and record providers and performs no constructor I/O.
The earlier best-effort root hash definition is retained, and the strict imported hash takes
over at the original later binding point. HTTP routes and worker/archive formats are unchanged.

The RunPod flow retains its reviewed task-writer provider and adds six narrow getters
for request, import, warmup, terminal and error-text argument evaluation. Each callback
is resolved at its original call site; no process or request state is owned here.

RunPod task input and submission live in `training.runpod_submission`, terminal/output
parsing in `training.runpod_outputs`, and polling/completion orchestration in
`training.runpod_flow`. Explicit ports separate settings, submission inputs, task updates,
status projection and artifact import. Constructors read no configuration or task state.
Root forwards preserve late adapters. Dataset/archive export, upload/download routes, artifact
filesystem import and the worker package retain their current implementations.

Training sample creation is separated into `training.sample_plan` (allocation and RNG flow),
`training.annotations` (label/YAML formats, output links and annotated images),
`training.dataset_generation` (configuration and file orchestration), and `training.estimates`.
Typed ports expose only the required records, planning, rendering, output and progress operations.
Seven callback getters preserve function lookup before task/label arguments; each sample
and label resolves its own callback. No service stores a current account or live connection.
Constructors perform no I/O or identity reads. The root still supplies the existing renderer;
image composition and occlusion algorithms are unchanged. Root compatibility forwards resolve
callbacks when used, including the annotation URL only after writing the image.

Record updates use their previously reviewed provider; seven additional narrow
getters preserve eight load, path, process, warmup and submission argument windows.
The Thread factory retains its existing interface and target lookup ordering.

`training.runner.TrainingRunner` owns the training execution flow through explicit
record, dataset, filesystem and local-process ports. Each instance wraps its bound method
once with the model-profile binding helper; construction does not resolve a profile or read
a task. The root now forwards without a second decorator. Binding still reads find(job_id)
before the body separately reads path/load. `training.submission` assembles and saves tasks,
registers the created thread in the original runtime map, starts it, then returns the public
projection. `training.local_process` owns CLI discovery and 128 KiB log-tail parsing.

Pipeline ID cleaners and method normalizers use narrow getters at the original
three argument expressions, preserving prior replacement and missing callbacks.

Training account state lives in `training.user_state`; model identity selection lives in
`training.task_models`. `pipeline.training_sync` propagates terminal training outcomes and
then calls `detection.training_candidate_sync` after releasing the pipeline lock. Each
service receives narrow storage, ownership, model or lock providers; constructors do not
resolve configuration, current identity or later-defined locks. Configuration state saves
retain their previous semantics; the shared non-reentrant pipeline Lock and auto-optimization
RLock are never nested by this chain. Root functions remain external compatibility forwards.

Transport and error formatter getters preserve capture before timeout/detail
argument effects at the three original expressions. Nested configuration and
response-summary calls stay within their service instance.

Training executor parsing and status projection live in `training.executor_settings`.
`ExecutorSettings` receives a late environment provider and URL-mask callback; immutable
setting-name constants remain available through the root imports. `training.runpod_client`
receives typed request settings, an HTTP transport and a text-bound callback. Both modules
import without the Web application or model runtimes. Root callables remain thin forwards;
client settings and transport resolve root adapters at invocation time. Retired Windows
request/form/status implementations remain in place and are not reactivated.

Public-view sanitizers use a narrow getter before record enrichment. Prior callback
replacement and missing-callable argument effects retain their original ordering.

Training lifecycle and authorized deletion now live in `training.task_lifecycle`;
public projection and visibility-filtered refresh live in `training.task_views`.
`runtime.training_tasks.TrainingTaskRuntime` owns the existing RLock, thread map and
process-local deletion markers. The root keeps aliases to those exact objects for
current enqueue/render and test entry points; narrow state providers resolve them
at call time. Lifecycle record, permission and write ports do not import the Web
application. The training process topology and stop/delete ordering remain unchanged.

Pipeline decoders, state encoder and task model resolver use four narrow callback
getters at five original expressions. Capture remains before fetch, clock conversion
or snapshot membership checks, preserving prior replacements and missing callbacks.

Pipeline task persistence lives in `pipeline.task_store.PipelineTaskStore`; the two
ordered working-set lists live in `pipeline.state_store.PipelineStateStore` with the
pure `state_policy` normalizer. Typed repository, row, path, model-resolver and guard
ports replace root namespace dependencies. Nested store operations call instance
methods; external root functions remain thin forwards with late path/resolver binding.
Task-lock ownership stays with orchestration, and state update keeps its existing
shared RLock. Scheduling, advancement, task progress and PLC flows remain separate.

Row decode/encode and model-resolver callbacks are captured by narrow getters at
the original expressions. Task directory lookup follows identifier conversion.
These boundaries preserve prior callback replacement and first-failure semantics.

Training record persistence lives in `training.record_store.TrainingRecordStore`;
identifier/path and timestamp policies live in `training.task_identity`. The store
receives repository, directory, shared guard, resolver, cache invalidation, row and
audit ports. Nested reads/finds use instance methods, so tests replace those methods
or their ports rather than the root's internal call chain. External root forwarding
and the earlier catalog/lookup late bindings remain. This extraction does not move
training execution, task tombstones, update/delete orchestration or process ownership.

Training catalog path, resolver, audit, OCR and pipeline callbacks use seven narrow
getters at nine original argument expressions. This preserves callback capture
before argument effects, including prior replacement and missing callbacks. Finder
repository selection, lazy snapshots and partial-failure state remain unchanged.

Training discovery now lives in `training.model_catalog.TrainedModelCatalog`,
with filesystem, accessory, pipeline and identity/audit ports. `training.task_lookup`
creates same-thread operation snapshots; `pipeline.training_links` resolves the
first matching task. The catalog depends on a link callback, not the pipeline
service implementation. Root forwards remain late-bound during migration. Repeated
roots, missing weight files, stable mtime ordering and shared variant fields keep
their prior semantics. Request identity is read only after model assembly and rule
overrides. Training execution and pipeline orchestration remain in the entry point.

Warmup method, path resolver, model loader and error formatter use narrow callback
getters at their original expressions, after preceding work and before argument
conversion. Missing callbacks retain argument effects; new getter failures stop
before them. No retry, lock or thread admission policy is added.

YOLO warmup settings/candidates live in `detection.warmup_policy`, dummy prediction
parameters in `detection.warmup_prediction`, and per-process status/threads in
`runtime.yolo_warmup.YoloWarmup`. Typed callbacks connect the three components;
runtime does not import the application or detection services. Each runtime owns
its RLock and status, with root compatibility references to the same objects.
Snapshots remain shallow; state updates hold the lock, while prediction runs outside
it. Startup keeps the existing registered callback. Every enabled start still creates
a daemon thread and resolves its current worker after checking the enabled flag.

Local model factory lookup uses a narrow getter after path resolution and before
string conversion, preserving callback replacement and missing-callable argument
effects. Existing cache publication order and exception boundaries remain unchanged.

`detection.model_selection` owns ordered specification selection, including the
legacy trained-provider TypeError fallback. `detection.local_models.LocalModels`
owns per-process model instances and resolved path aliases; initialization calls no
providers. Root `_models`/`_model_paths` remain references to those same dictionaries
for maintenance scripts using pop/clear. Reassigning root variables is not a runtime
replacement seam; tests use the service or mutate the compatibility objects.
Selection, factory and catalog providers remain lazy. Warmup state, startup and
threading behavior are unchanged; this extraction does not add a model-loading lock.

`detection.task_projection` now owns task display/request mapping, while
`detection.task_catalog` owns native and training-derived task model catalogs and
list response assembly. Narrow providers supply records, current request identity,
registry values and projection. No user, repository connection or catalog result is
cached by these services. Catalog-to-catalog calls are instance methods; replace their
ports/methods when testing those internals. Root projection remains a late callback.
Explicit response user filtering and nested ContextVar filtering retain their
original separate timing, as do native precedence, merge order and shallow mutation.

Detection task IDs/counts now live in `detection.task_identity`, persistence in
`detection.task_store`, and background lookup/hydration in `detection.task_backgrounds`.
The store receives lazy repository, path, cache and row-adapter capabilities. Shared
read-cache ownership and its five-second TTL remain in the composition root; returned
lists are shallow copies with shared record objects. No repository connection or
request identity is stored by these services. Internal load/save calls now use the
store instance; test replacements belong at its ports. Root background resolver and
prefix remain late-bound for compatibility.
Row decoding and background callback getters resolve at the original expressions:
after preceding work and before fetch/string/mapping argument effects. Missing
callbacks preserve argument evaluation and TypeError. The bundled source manifest covers
the three task modules; no retry, cache policy or transaction change is introduced.


Detection OCR now separates image variants (`detection.ocr_images`), keyword
matching (`ocr_matching`), manual classification/projection (`manual_text`), scoring
(`ocr_scoring`) and job selection/enrichment (`ocr_attachment`). Narrow callbacks
supply labels, thresholds, model access and late scoring substitutions. The shared
Paddle bootstrap and small-model instance live in `runtime.paddle`; the medium
incoming-text engine retains its own instance and initialization lock. Small-model
initialization retains its existing unlocked behavior. Neither cache contains a user
or database connection. Pure/internal test substitutions target the actual modules.
Attachment crop, score and match getters capture the current callable at each
original expression, before argument effects. Missing callbacks still evaluate
arguments and raise the original TypeError. Single-image OCR retains its existing
Exception handling; batch failures retain the existing per-image fallback. No new
retry or model-initialization lock is introduced.


Detection geometry, result filtering/deduplication, model-result parsing, exact-count
rules and overlays now live in `detection.geometry`, `postprocessing`, `results`,
`rules` and `drawing`. Pure functions are identical root exports. The parser and rule
service receive narrow label providers; the parser resolves the root postprocessor
at use time. These modules own no model, worker, identity or database state. Internal
pure helper substitutions belong in their actual modules, not unrelated root aliases.
The bundled source manifest includes these five modules so relocation retains source provenance.
Provider and postprocessor exceptions propagate without an automatic retry.

Nine legacy incoming-text routes now live in `text_inspection.incoming_api`,
registered as five catalog routes and four inspection routes around the unchanged
Beta route. Catalog, capture execution, human reviews and retention have explicit
services and narrow account, record, media, OCR and write capabilities. Repository,
identity, path and policy providers are resolved at use time; services hold no user
or connection. Capture OCR remains synchronous inside its existing async handler.
The root keeps compatible helper forwards and aliases to actual route handlers.

Workflow callback getters resolve only at their original call expressions, after
preceding work and before argument effects. Missing callbacks retain argument
evaluation and the original exception or fail-closed projection. Request identities
and database connections remain transient; no new retry policy is introduced.

The OCR result-mapping getter preserves the original lookup after prediction and
before result truth/item access. Missing callbacks fail at the same point; no
extra OCR, rendering, parsing or serialization retry is introduced.

Legacy image/OCR evidence now lives in `text_inspection.incoming_analysis`.
`IncomingOCREngine` owns its lazy model and initialization RLock; prediction remains
outside that lock. `beta_comparison.BetaComparison` owns its cache and full-comparison
RLock, with root aliases to the same objects. `beta_api` retains upload validation
and the thread-pool handoff. Each comparison captures the current OCR observer once;
corroboration continues to resolve the observer on each region. State contains no
request user or database connection. No OCR model or recognition algorithm changes.

Legacy incoming-text persistence now lives in `text_inspection.incoming_store`.
Seven methods receive a thread repository factory, shared guard, path providers,
row adapters and JSON-list callbacks. Single JSON lookups use two explicit list
callbacks, preserving the public loader lookup and its normal second repository
selection. List decoding obtains its callback before fetching rows; single-row
decoding obtains it after a successful lookup and skips it for an absent row.
`runtime.json_records` owns
the two unchanged file helpers; root aliases preserve their identity for current
text-record consumers. No identity or connection is stored in the new service.

Text comparison submission and human inspection review now live in
`text_inspection.comparison_submission` and `inspection_reviews`; `inspection_api`
registers their six routes, including the retained manual read-only responses.
Submission receives record, media, image, model, policy and diagnostic capabilities.
Prepared comparisons still capture the current callbacks and admission flag on each
submission through a small root composition function. Ordinary comparison gates
remain dynamic at their original points. No worker or transaction topology changes.
Submission and review obtain the relevant callback before evaluating its arguments,
using narrow getters for ownership, image preparation/annotation, media paths/hashes,
model dispatch/normalization, diagnostic events, evidence reads, text and audit.
SubmissionMedia is distinct from the per-job captured ComparisonMedia. Review JSON
lookup remains after permission and record checks; no eager callback validation or
method-entry caching is introduced.

Seven standard HTTP routes now live in `text_inspection.standard_api`, in the same
order with the same request types and synchronous/asynchronous boundaries. Import,
retrieval and human edits use `standard_imports`, `standard_library` and
`standard_edits`; narrow record, media, revision, parser and job capabilities are
composed in the root. Providers resolve identities, repositories and jobs at use
time. Compatibility names point to the actual registered handlers. Retrieval can
refresh classification or generate cached media and is not uniformly a pure read.
Narrow callback getters preserve the original evaluation window for bounded text,
media writes, expected revisions, revision application, public projection and
unavailable-job marking. The DOC parser is captured before thread submission; the
PATCH request JSON method is looked up only after permission and resource checks.

Text public projection, revision publication and diagnostics now live in
`text_inspection.projection`, `revisions` and `diagnostics`. Revision storage and
snapshot providers, diagnostic hashing and the logger are explicit capabilities;
the root retains compatible exports and thin forwards. The revision service keeps
caller-owned transaction boundaries and the original partial-failure behavior.
These modules do not own request identities, database connections or worker state.
Diagnostic hashing resolves its callback at the original call expression, after
preceding fields and before message conversion. The logger remains late-bound;
neither capability is cached or checked eagerly.

`text_inspection.media.TextMedia` owns account-scoped evidence paths, verified
reads, atomic file replacement and lazy PDF page caches, with explicit record ports.
`text_inspection.images` owns the original image decoding, provider-copy and
annotation, data-URL and similarity functions. The entry point keeps compatible
exports/forwards and provides narrow getters for resize constants at their original
comparison, thumbnail and encoding expressions. The owned-record callback is
resolved after preceding asset checks and before its identifier argument. No eager
policy or callback caching is introduced. The bundled source manifest includes both
migrated media producers so new task provenance covers their actual shipped code.

`text_inspection.record_store.TextRecordStore` now owns text-record JSON/SQL
selection, insert-only writes, owned lookup and attempt compare-and-set. Its ports
obtain the thread repository, shared write lock, directory, table mapping and JSON
adapters lazily. The entry point retains five thin forwards and the identical row
serializer export. Internal store calls use the store itself; storage substitutions
belong at its ports. Revision policy, query shape and lock placement are unchanged.
Reader, writer and row-decoder factories preserve the original callable lookup
before path or fetch-all arguments are evaluated. Owned lookup retains its separate
post-query decoder lookup only when a row exists; no callable is cached or prevalidated.

Prepared comparison orchestration now lives in `text_inspection.comparison_jobs`.
The application constructs narrow record/media/model capabilities for each submit,
capturing function references and the external-model flag just as the prior namespace
copy did. Runtime account allowlists stay dynamic. Qwen orchestration keeps its
source location and receives the same capabilities explicitly; audit and preview
writers require only media path/write methods. No namespace injection remains in
the application. Dependency checks now also include these three evidence modules;
a constant local-name membership test is permitted, namespace passing is rejected.
Timer and final-timeout forwarding defer the record writer lookup until settlement;
the HTTP preparation history factory retains its separate early-capture boundary.

Standard preparation is split into `text_inspection.preparation_api`,
`preparation_jobs` and `preparation_policy`. Narrow record, media, model, account
and history capabilities replace namespace injection; the composition root shares
one record/media capability pair with the job service. Compatibility exports remain.
Qwen timeout settlement takes its compare-and-set callback explicitly; the
comparison GET captures its writer before timeout and rereads the authoritative
record after settlement. Worker timeout paths resolve their writer after timestamp
evaluation, preserving their distinct original lookup boundaries. OCR, classification,
recovery, prompt sources, transaction order and embedded thread topology are unchanged.

Label extraction registration now lives in `text_inspection.extraction_api` and
takes explicit account, record, media, model and cleanup capabilities. The old
registrar export remains identical. This dependency batch retains the existing
nested workflow; geometry, bounding-box algorithms and worker topology are unchanged.

Agent HTTP discovery, policy and operation inspection/cancellation now live in
`agent.api`, with narrow identity, account-store and repository factory capabilities.
Strict requests live in `schemas.agent` and the public projection in `agent.projection`;
the old module re-exports identical objects. Durable operation transactions and
commissioning gates are unchanged; operation submission remains unavailable.

Document classification now separates `text_inspection.document_api` from
`document_jobs`, composed with explicit account, record, model/transport, media and
connection-cleanup capabilities. Repository lookup and shared JSON lock stay lazy;
the compatibility module exports the same class and registrar. Each job service
retains two slots and the original persisted-attempt and human-edit rules.

Historical comparison routes and projections now live in `text_inspection.history`.
Typed account, record and verified-media capabilities replace namespace injection;
`comparison_history` re-exports the same six public objects for existing consumers.
Media decoders remain lazy imports. Ordering, JSON fallback, PostgreSQL adapters,
revision selection and diagnostic visibility are unchanged.

Codex single-image and batch registration now uses explicit account, repository,
standard-library, media and document-import capabilities. Repository/identity lookups
remain lazy and thread-local; source-library reads stay outside the queue transaction.
Shared HTTP requests live in `schemas/codex_compare.py`; report value validation is
separate from version dispatch, removing API/report cycles while preserving existing
exports. The entire Codex package now passes dependency checks. Its worker is unchanged.

Label inspection registration now takes the app separately from typed access,
repository-lifecycle, import/media and model-provider capabilities. API and worker
code no longer read the application's global namespace. `model.settings(provider)`
also resolves its explicit model service, so importing the label package cannot load
`server`. All providers remain lazy: owner and repositories are obtained in the
request/worker thread. The whole label package is now covered by dependency checks.

`accessories.routing.AccessoryRouting` owns detection-route selection; `routing_api`
registers its synchronous endpoint in the original position. Access, config storage,
profile preparation, AI-task upsert and response projection are explicit capabilities.
Route validation still precedes record lookup, and profile failure is deliberately
recoverable while later save/task/projection failures propagate.

Accessory source preparation now has three explicit services: `AccessoryPreparation`
for normalization/reference expansion, `AccessoryRefresh` for post-edit preparation,
and `CandidateFactory` for candidate creation. Narrow media, profile and persistence
ports retain existing call ordering and partial file effects. Crop/video/image
algorithms remain existing providers. The actual object-plan prompt is now in
`accessories/preparation.py`, included in the bundled source manifest for new tasks.

`accessories.image_job_metadata` owns deterministic job identity, candidate job
aliases, anchor/guide provenance and update binding. Its service receives an
explicit model-resolver provider and narrow provenance capabilities. Freeze still
precedes ID/file mutation, and existing snapshot references remain untouched.
The root intentionally injects its final `file_sha256` binding: the later strict
implementation overrides an earlier definition, and I/O errors must still propagate.
The versioned source manifest includes the actual migrated metadata file for new task evidence.

`accessories.gallery.AccessoryGallery` owns public detail projection, preview
image writes and gallery assembly. Asset lookup, output storage and display
capabilities are explicit and share the existing accessory projection. Detail
retrieval still authorizes before invoking it. GET retains preview-file writes
and asset callback mutations; this service is not a pure serializer.

Accessory management has separate creation, confirmation and removal services.
`management_api` preserves the original three creation/confirmation route positions
and registers deletion separately after file routes. Confirmation retains the same
candidate RLock through authorization, model preparation, persistence and response
projection. Candidate creation, profile generation and pipeline callbacks retain
their existing implementations; services receive narrow capabilities, not globals.

`accessories.file_api` preserves the four file-edit routes and their sync/async
boundaries; `files.AccessoryFiles` owns upload, text crop, reference selection and
file deletion orchestration. Narrow access/store/media/profile ports are composed
in the root. Gallery rendering and profile generation remain existing callbacks.
Authorization order, partial file effects and provider fallback remain unchanged.

`accessories.candidate_repository` owns candidate load/save/delete/list/path and
atomic-file helpers; `candidate_queries` and `candidate_api` own retrieval.
The root injects its existing candidate RLock and job callbacks. Retrieval retains
load-time ID/provenance repair before authorization, then authorized job refresh and
model-freezing storage within the same outer lock. It is not a pure read. Candidate
creation, rendering and image execution remain in their existing implementation.

Accessory listing/detail routes now use `accessories.api` and `accessories.catalog`.
`policy` owns existing ID/material/profile-readiness rules; `projection` owns full
and summary serialization; `repository` owns the existing row writes/JSON fallbacks.
Each service receives only its required capabilities. Detail still calls the
gallery service, which may write previews, only after authorization.
Candidate/image generation and the remaining write HTTP workflows stay in the root.
Four constant aliases and fourteen compatibility helpers preserve existing callers.
The source manifest includes `accessories/policy.py`; old task fingerprints
are unchanged. This is a structure change without policy or model changes.

`records.access.RecordAccess` owns request owner fields, administrator owner
assignment and hidden-resource guards. It shares the authentication identity and
ownership policy and receives lazy current-user/target-user capabilities. It holds
no current user or connection. The target port retains the existing full auth-store
lookup; this extraction does not introduce indexed reads or alter write locking.

`records.audit` owns timestamp coercion, field precedence, file-time fallback and
shallow audit projection. `RecordAudit` receives the existing ownership policy;
six root forwarding functions preserve caller signatures. Request identity and
persistence retain their existing implementations.

`records.ownership.RecordOwnership` contains five pure ownership policies shared
by existing record callers. The root supplies the existing legacy/system identifiers and
retains the five original function signatures as explicit forwarding adapters.
Shared users can read; administrators or owners can write. Administrator owner
filters remain binding. Identity and storage
are outside this extraction and retain their current lifecycle.

The existing Codex comparison worker observes process exit once per loop, waits
for its event reader and persists final session/usage metadata before settling.
An exit during a heartbeat is handled in the next loop. Cancellation and deadline
checks still precede completion; a reader that has not reached EOF cannot claim
success. This is a terminal-state correctness fix, not the label-worker split.

`auth.accounts` owns account creation and environment bootstrap; `auth.sessions`
owns cookies, sliding expiry and indexed/full-store authentication. Settings and
repository ports resolve on each call. `auth.access` and `auth.middleware` share
the same request identity instance; `auth.route_permissions` retains the exact
central policy, including existing endpoint-local label guards. `auth.api` owns
thin account/user/preference HTTP registrars around `auth.flows` and `auth.users`.
`auth.login_limits` owns each composition's throttle state and reentrant lock.
`auth.ports` declares the narrow persistence capabilities for these services.
Domain-specific resource guards remain with their current business domains.

Authentication foundations live in `auth.policy`, `auth.credentials`,
`auth.preferences` and `auth.repository`. Pure permission/credential/preference
rules do not depend on the application. Persistence receives lazy path, repository
and reentrant-lock factories, retaining thread ownership and raw/hashed session
compatibility. The root assembles these services and retains compatibility
exports for old callers. API documentation routes remain at their original
position between preference and user-administration routes.

Analysis records use `analytics.analysis_records` for normalization,
`analysis_repository` for JSON/PostgreSQL persistence, `analysis_service` for
owner-aware access, `analysis_queries` for list/detail assembly and `analysis_api`
for the five original routes. The composition root injects narrow factories and
permission/presentation ports. Existing source IDs, normalization, lock placement,
sort order, offset pagination, hidden 404s and retired 410 routes remain intact.
`analysis_processing` owns image-processing metadata and request-local manifest
projection; `analysis_scope` owns required-accessory scope/count projection;
`analysis_projection` owns public/debug record views and source-image lookup;
`analysis_publication` owns detection/image-processing record publication. These
services receive explicit media/configuration/identity/persistence ports and do
not import the application. Current identity/cache is fetched at each call, never
stored at construction. Compatibility exports remain for unconverted callers.

`schemas/` contains dependency-free HTTP request models grouped into authentication,
configuration, detection, accessories, training, pipeline and text inspection.
The application explicitly imports these classes; business modules can depend on
the same contracts without importing `server`. Defaults, coercion and field names
are unchanged. PLC request models remain with the PLC domain until its dedicated
extraction and protocol review.

`runtime/identity.py` owns the request identity port backed by a `ContextVar` per
composition. `runtime/connections.py` owns thread-local repository selection,
generation invalidation, closed-connection rebuilding and explicit same-thread
release scopes. The Web composition supplies factories and keeps its existing
HTTP-safe store errors. Existing workers retain their explicit finally cleanup;
HTTP connection caching and worker startup behavior remain unchanged in this step.
The new `thread_scope` belongs inside synchronous work sent to an executor, never
across an await; it is available for subsequent worker lifecycle migration.

Model-profile composition uses `model_profiles/dependencies.py`: the service gets
a repository factory, secret access, legacy configuration and validation ports;
the HTTP registrar gets explicit admin and formatting callbacks. Snapshot decorators
receive a resolver provider and callable task loader. They do not discover services
through a function's module, string loader names or a global namespace. The provider
is resolved at execution time and must exist before provider work. No connection or
request user is captured in these dependencies; the existing thread-local repository
factory and request `ContextVar` remain responsible for their lifetimes.
Each profile service owns its own snapshot `ContextVar`, so nested independent
application compositions cannot borrow one another's active model versions.
Usage accounting receives an explicit recorder. Ledger failure after inference is
logged without replaying the call. New task source fingerprints use the versioned
`model_profiles/prompt_sources.json` manifest; saved task references remain unchanged.

The label actual-image component remains mounted from local selection through run
completion. A single in-memory photo lease binds owner, task, request ID and then run
ID; only that run may reuse the blob URL. Navigation, replacement, next-item, logout
and unmount release it. Request recovery binds only the original pending request.
Historical reads use the stored JPEG preview; full normalized images load only on
zoom or a bounded preview failure fallback. Original uploads and inference inputs
remain unchanged, and authenticated no-store media policy is preserved.

The label result page exposes a detection ID for support, with no call-diagnostic
control or diagnostic fetch. Normal run responses omit model/prompt/layout/transform
internals and retain only a quality-check presence marker. Full evidence remains in
durable storage; the diagnostics endpoint additionally requires administrator role and
retains current-account ownership checks.

## Label inspection A + Evolving workspace

The production text-inspection label entry opens `/workspace/label-inspection`
in the same tab without the platform sidebar. Its default view is an account-owned
task list; `?view=new`, `?task=ID`, and `?task=ID&run=ID` preserve navigation and
login return locations. Manuals remain at `/workspace/text-compare-beta?mode=manual`;
Codex Beta keeps its native routes and execution engine.

The label workspace shares Beta's upper-left hierarchical back navigation:
list to platform, task/import to list, and result to task. It uses explicit router
destinations rather than browser history, including on refreshed deep links.

`label_inspection/api.py` composes an independent service and durable PostgreSQL
repository. Each Word import creates one task containing all embedded images,
including duplicates and invalid-image placeholders. Selection is manual. Standard
edits create immutable revisions; submission freezes reference bytes/hashes,
revision, model and prompt hash. Ordinary uploads and this camera never create PLC
plans. The existing storage connection selector and Word extractors are reused.

Two worker threads claim durable queued runs under one database advisory lock,
with global concurrency two and at most one active run per task. A paid stage is
recorded before external I/O, cannot be replayed, and is not retried after unknown
outcomes. A 420-second run deadline invalidates late results. Service restart does
not requeue claimed runs; expired runs require an explicit new linked detection.
The two calls use the fixed Evolving alias and original A layout prompt and A comparison rules with versioned full-input image coordinates.
See [text inspection](text-inspection-v2.md) for exact parameters and coordinate limits.

Old text records are read without rewriting conclusions and grouped by original
standard ID. Missing-order records stay visible separately. First continuation
creates an owner-scoped extension and original-image snapshot. Beta batch/single
histories keep their native structure and links. New records use the new engine;
manual inspection and Beta configuration are independent.


## Bounded actual-image reread trial

The separately account-gated local reread follows whole-image OCR, deterministic
matching and the existing one text-only LLM mapping. A frozen first-pass candidate
list chooses at most eight source regions (top two candidates per unresolved
element, character similarity >=0.35). Each crop has 20% line-height context,
at most 4x resize and 64px white padding for advanced recognition. Still-unmatched
regions may receive one unpadded text-recognition call. Both use the pinned OCR
model, never standard answers as OCR input. Different views satisfy elements
independently; characters cannot be stitched across views. Source geometry is
mapped only after strict local matching. Text-only evidence has coarse crop bounds.
An advanced OCR box with at least 90% bounding-area overlap with real crop pixels
may also be retained as coarse crop evidence when it overhangs white padding;
it is never clamped into a purported word polygon. Padding-only evidence is rejected.
All stages share the existing 120s deadline and at most 16 additional paid calls.
Results remain REVIEW_REQUIRED; the synthetic experiment does not commission MATCH.

**Status: Authoritative**

### Qwen OCR evidence comparison — opt-in, not commissioned

`VANTALINE_QWEN_OCR_ACCOUNTS` selects `qwen_evidence_jobs.py` at prepared-comparison
submission; other accounts keep local OCR. The pinned `qwen-vl-ocr-2025-11-20`
uses `advanced_recognition`, image-only input, min_pixels=3072 and explicit original
resolution bounds. The original-coordinate words_info output is authoritative;
OCR transport v2 bounds Base64 to 9 MB below the provider's 10 MB limit. PNG is
preferred; oversized PNGs use a same-resolution JPEG copy (quality 95/92/90/85,
no chroma subsampling), never downscaling or replacing the archived original.
Encoding, lossy status, byte counts and input hash are recorded; images still
too large fail before external I/O. The preprocessing version separates caches.
Rejected OCR responses retain allowlisted token counts, termination reason and
response byte count/hash in the failed call and cache diagnostics, not arbitrary
provider content. Interrupted or rejected calls remain non-replayable.
The presence-comparison caller retains independently validated word rows from a
complete response while recording rejected row indices/reasons and `scan_complete=false`.
It never clamps invalid coordinates, accepts an all-invalid nonempty response, or
salvages truncated responses. A valid empty words array yields zero evidence and
yellow review markers, not a provider error or a claim of proven absence. Missing
schema/over-capacity responses remain failures. No-evidence elements skip the LLM.
The default adapter remains strict for other callers. Presence evidence has a
separate validation-policy cache namespace; partial evidence must not be described
as a complete page scan. A completed claim means processing finished, not full
coverage. One independently valid exact occurrence can still support an element;
the whole comparison continues to require human review.
The OCR adapter also accepts experimental explicit auto-rotation (default false).
It uses provider original-input word coordinates without a second client rotation;
diagnostics record the option. Experimental callers must isolate caches by this
option. Production callers remain unchanged until real coordinate/accuracy tests.
processed_text's internal coordinates are not used. Missing scores remain null.
Exact character matching precedes at most one text-only LLM correspondence request;
before that request, bounded deterministic local multi-box search attempts exact
paths using only existing OCR characters. It preserves whitespace/punctuation rules,
uses the same strict span validator, rejects intervening OCR words, and records
search limits. It never produces a difference or invents missing characters.
IDs, character spans, boundaries and local adjacency are checked by the backend.
Mappings are validated independently: an invalid sibling cannot discard another
element's valid evidence. Duplicate targets reject all proposals for that target;
malformed envelopes remain whole-response failures. Diagnostics preserve usage,
accepted references and bounded per-mapping rejection reasons. No extra call is made.
Text-only LLM requests use non-thinking JSON Object output; backend envelope,
ID, span and character validation remains mandatory. Private per-call evidence
files retain requests (image bytes separately referenced), response bodies,
HTTP status, network timing and parse location on failure. Keys/authorization
headers are never stored; known-key echoes and inline image data are redacted.
Response caps remain enforced and partial reads are explicitly marked. Polling
returns only metadata and authenticated download links, never full raw bodies.
Invalid content is not repaired or retried. Historical missing raw bodies cannot
be reconstructed. Cache hits do not create fake new provider responses.
Prepared comparisons precompute a display-only 1600px JPEG preview once; OCR and
matching still use the full original. Evidence UI defaults to the preview and
loads full resolution only on request. Normal-orientation JPEG/PNG source media
is served verbatim; other orientations/formats retain normalization. Legacy
records generate previews on demand without rewriting business history. All
media remains account-authorized with private/no-store responses (no shared cache).
Legal references alone cannot establish corresponding fields: unequal text with
character-sequence similarity below 0.75 stays review rather than becoming a red
difference. This heuristic only downgrades differences, never authorizes matches;
even related differences still require human verification.
Saved templates are not re-OCRed or corrected. Codes require local decoder evidence.
The workspace compares the entire uploaded/captured image without mandatory mask
generation or crop confirmation. Standards must have a prepared element template;
opted-in accounts without one get 409 rather than silently using legacy VLM comparison.
Matching v3 ignores layout whitespace beside prose commas, colons and semicolons,
while preserving the punctuation, word spaces, numeric-separator spaces and original
character offsets. It checks sheet-level element presence: one exact occurrence satisfies an
element even if other occurrences differ. Other reads and conflicts remain audit
evidence, not vetoes. Unmatched parameters can still use validated local multi-box
correspondence. No distant stitching or partial numeric matching is permitted.
This does not check individual labels for omissions, misprints or mixed variants.
The account-owned `text_ocr_evidence` insert-once claim/cache prevents repeated OCR
on the same input hash/model/preprocessing version. Unknown claims are not replayed;
a new comparison cannot silently retry an unknown cache entry. There is currently
no public cache retry endpoint. Complete evidence can be reused with another template.
Record CAS settlement prevents a 120-second timeout from being overwritten by late
workers. Restarted tasks are queried/expired, never automatically submitted again.
This first opt-in release always requires human review, even on exact matches;
independent accuracy, template verification and 30-run performance gates remain.
There is no automatic model replacement, local full-sheet OCR fallback or PLC I/O.

Legacy DOC import extracts embedded image payloads directly using a versioned
Apache POI HWPF helper; it does not convert DOCX, render pages, merge overlaid Word
text/shapes, apply Word crop settings or follow external links. Original DOC and
its hash remain authoritative. Java runs off the request event loop with a 256MiB
heap, 30s wall timeout and process-group termination. This is not an OS sandbox;
keep the JRE and parser patched. Missing/invalid runtime bundles return 503.
Images start pending, then account-gated DOC/DOCX jobs classify unique images
with the existing Qwen vision model. Undecodable images are retained
with a preview-unavailable reason. Other embedded OLE files are not exported.

Document import review preserves all extracted images for human correction. The
gallery distinguishes retained/pending/excluded without hiding excluded sources.
Label cards display retained first, pending next, excluded last; source ordinals
order each group. This display-only ordering recomputes after uploads/reviews and
does not mutate stored assets, selection IDs, snapshots or manual page ordering.
Manual review separates a green/red/orange current-state indicator from a neutral
one-click action labelled with its destination (retain or exclude). Pending first
becomes retained, then retained and excluded toggle. Existing PATCH history and
revision handling are unchanged; a failed save does not flip the displayed state.
Owned asset PATCH adds `review` for `needs_confirmation`; JSON and PostgreSQL
paths preserve initial classification metadata on human edits. Pending assets
are excluded from active snapshots, and unresolved pending items block draft
activation. Classification persists each attempt before external I/O, preserves
human edits, and never replays interrupted/unknown paid calls. Label-order deletion
is a tombstone: future list/edit/compare use stops; media and history stay owned.

## Components and boundaries

Account-gated standard preparation runs on activation: one local OCR prediction
and local code decoding, VLM classification of existing element IDs plus bounded
missing-region localization, optional local-only supplemental OCR, deterministic white
background clearing, safe all-ink whitespace trimming, then atomic publication
of a cleaned PNG and immutable element template.
Clearing clips checks to image bounds and subtracts all keep/uncertain rectangles
from erasure and background checks. Overlap pixels remain byte-identical; edge
contact is allowed. Other unsafe-background and code-erasure guards remain.
Nearby exclusions share a union/perimeter check and a bounded three-pixel ink
fringe, so neighboring removable text cannot veto itself. Local nonwhite connected
components reaching the unprotected perimeter are preserved, while separable
excluded ink is erased. White pixels (including alpha) remain unchanged. Entirely
inseparable nonwhite candidates and missing checkable perimeter still require review;
per-group evidence counts retained exterior pixels and actual erased pixels.
Pure-graphics revisions require explicit human confirmation and
successful complete source recognition; they remain viewable standards but carry
no text-comparison capability. Both public readiness and the backend submit/worker
guards reject empty or non-comparable templates, including legacy records.
Original pixels, observations, excluded elements and previous active snapshots remain available. Partial success
publishes only ready assets; uncertain images require explicit human correction.
Prepared comparisons read the saved template and recognize only the actual image.
Activation owns the preparation UI lifecycle: a compact progress indicator and
an ordered review-modal queue replace the standalone preparation panel. Gallery
zoom uses that same original-coordinate element editor, with immutable save,
stale-version blocking and explicit dirty-close protection. Plain unprepared
images keep read-only zoom. No new model or preparation endpoints are introduced.
They check text/decoded codes, not icons or logos. A separate commissioning gate
controls MATCH; missing evidence and numeric conflicts require review.
This experimental path is not commissioned by synthetic tests. OCR runs in an
isolated, two-thread CPU worker with explicit local model paths and hard timeout;
no request downloads models or invokes image generation. Existing flows are unchanged.

Supplementation uses the same single VLM response, never a second paid request.
The model proposes only region geometry/ownership, never text. Up to eight regions
receive one local prediction each within a shared 60-second budget; original OCR
observations are retained and measured new boxes map back to source pixels.
Conflicts, empty results, crop-edge text or incomplete coverage require review.
`supplementing` is a durable phase; stale results cannot revive interrupted jobs.

### Public site and workspace routing

`/` always serves the product introduction and `/docs` the curated public user
guide, irrespective of login state. Neither mounts the authentication gate or
workspace data queries. `/workspace` is the protected dashboard; all functional
pages and pinned task URLs live under `/workspace/*`. `/workspace/about` is
available to every signed-in user and links to the public site and guide in new
tabs. These workspace resource links live only inside About; the sidebar retains
the About entry without duplicate website/documentation shortcuts.

The React router keeps a root production basename, separate public/login/app
layouts, and one release bundle (including the existing PLC bundle contract).
Unauthenticated deep links go straight to `/login?next=…`; an allowlisted local
workspace destination preserves query/hash after login and rejects open redirects.
Session 401 responses recheck authentication without replaying the operation.
Identity changes cancel/remove private query caches before mounting another
account; workstation cookies and persisted per-account task preferences remain.
Failed logout stays retryable; successful logout lands on `/login`, not marketing.

Legacy functional URLs (including `/text-compare-beta` and `/tasks/...`) redirect
to their workspace counterparts. Retired `/react-preview/...` bookmarks retain
their target and query. Server SPA allowlisting handles direct refreshes without
capturing `/api`, static assets or authenticated media; unknown UI pages show 404
content instead of silently returning to the homepage. `/docs` is no longer
Swagger: administrator-only Swagger lives at `/api/docs`; `/openapi.json` and
`/redoc` retain their administrator checks. No customer or internal repository
documents are published automatically.

This is same-origin path separation, not a domain migration: DNS, TLS, cookies,
camera/serial permission origins and model/PLC configuration are unchanged.

- **React frontend:** task/model selection, camera and upload workflows, administration, and workstation-local Web Serial.
- **FastAPI backend:** authentication, permissions, task/model orchestration, immutable PLC plans, audit receipts, static release serving, and `/api/version`.
- **PostgreSQL runtime repository:** shared application configuration, workstation identity/configuration, leases, dispatch state, and durable records.
- **Workers/model services:** training and inference integrations; they do not own PLC serial I/O.
- **Text inspection v2:** an account-scoped standard library and inspection workflow, independent from product/YOLO tasks. New label comparisons enter only through this workspace and accept a browser camera capture or uploaded actual image. Image acceptance trusts decoded content rather than browser MIME or filename suffix; uncommon but readable formats are normalized to a stable JPEG before OpenCV/model processing while upload and pixel safety bounds remain enforced. The label workspace is a two-column bench: the left side combines collapsible orders with a scrollable gallery of their assets, while the right side owns actual-image capture/upload and comparison preview. Its desktop header keeps sparse context and the mode switch on one compact line, while gallery and actual-image heights scale against the available viewport; medium and narrow screens stack the bench and progressively tighten spacing without shrinking primary controls below practical touch sizes. Clicking an enabled gallery thumbnail selects and highlights the sole comparison reference; there is no standalone local-reference upload surface. Full-size inspection remains a separate action that does not change selection. Asset add, soft-disable and re-enable actions live directly in the expanded order. A logical order standard remains editable, but confirmed history is append-only: initial confirmation and every later add, soft-delete or restore atomically record an immutable numbered asset snapshot, and each comparison binds to the exact revision and reference hash it used. Only assets in the current confirmed snapshot enter the comparison state. The former persistent scope-warning badge is not rendered, while the service-side verification gates and documented limits remain unchanged. Existing legacy incoming-text tasks remain readable, but their creation affordance is retired. PDF pages are rendered lazily. See `docs/text-inspection-v2.md`.
- **Text inspection diagnostics:** each label comparison record owns a bounded, account-scoped diagnostic envelope covering input metadata, provider configuration identity, lifecycle stages, provider outcome, raw parsed response, provider-adapted response and precise failure classification. The result UI presents only the sanitized raw parsed/preview value and adapted value in a default-closed disclosure, with a second client-side display bound. Full-resolution evidence remains available for audit and annotation, while oversized provider copies are reduced to a 2048-pixel longest edge and label comparisons receive at least 30 seconds for the provider response. Qwen-specific coordinate/type conventions are normalized before strict domain validation, but ambiguous or unchanged-only difference output remains review-required and never becomes an automatic match. Service logs receive only compact identifiers and failure metadata. Credentials, cookies and embedded media are never logged; uncertain requests remain non-retryable.
- **GitHub Actions:** required checks, one-commit release packaging, checksum/version generation, production installation, acceptance, release publication, and rollback on failure.

## Inspection flows

- Retaining a library asset and selecting a comparison reference are separate
  actions. Enabled assets expose an explicit reference-selection button. The
  extraction confirmation control explains missing order activation/reference,
  unsaved contours, pending work or missing preview; it links back to the library
  without discarding the crop. Draft/inactive assets cannot serve as references.

- The optional `vlm_bbox` extraction method ports the colleague's whole-image rectangle prompt to the existing Qwen vision settings. It is account-gated separately, disabled by default, and never changes the comparison or image-generation provider. Its 1600-pixel JPEG input, bounded model response and zero-expansion original-pixel rectangle are evidence, not a verified mask. Invalid output has no whole-image fallback. Polygon corrections and confirmation retain immutable previews and the existing comparison size gate.

- Single-label extraction is an account-gated stage before text comparison. It owns normalized camera/upload coordinates, a persisted at-most-once image-generation attempt, label-specific mask validation, immutable polygon/confirmation revisions, and original-pixel crops. The text-comparison provider consumes a confirmed server crop, with the extraction evidence attached to its diagnostic record. It does not use the accessory sprite pipeline or create PLC actions.

- Image upload and video requests perform detection only and never create a PLC plan.
- The text-comparison camera surface enumerates video inputs, exposes a labeled device selector, invalidates stale `getUserMedia` requests when a user switches devices, and refreshes on `devicechange`. If the selected device disappears, an available fallback may be opened only while that surface is active; permission denial or no remaining device leaves capture disabled and keeps the uploaded-image path available. Other camera surfaces retain their existing device lifecycle until separately hardened.
- File selection and drag/drop use one accessible frontend contract across the application. The chooser and drop path apply the same `accept`, single-versus-multiple and disabled rules; Enter or Space opens the chooser, rejected files are reported, and a disabled target cannot accept a drop. Domain-specific handlers still perform their stricter image, video or document validation after selection. These browser-only input conveniences do not change API authorization or PLC provenance.
- Camera detection uses a dedicated authenticated endpoint. Its final result may reserve one workstation-bound v4 dispatch.
- An enabled foreground workstation polls its configured D input locally through Web Serial. After observing reset, one non-trigger-to-trigger edge may invoke the same camera flow; sustained trigger values do not repeat and missed busy/not-ready edges are not replayed.
- The browser declares the attempt, writes D, waits for ACK, optionally writes Y only after D ACK, and submits one evidence receipt.
- Network/server failure after declaration cannot authorize automatic physical replay.

## Deployment and data ownership

Text comparison history reads the existing account-owned records, not a second
store. The title-bar entry opens a separate list/detail dialog sharing
`ComparisonResult` with live results; it never changes current inputs, polling or
sessionStorage. PostgreSQL projects bounded summaries with owner filtering and
stable `(created_at,id)` descending pagination; diagnostics/media load on demand.
New submissions snapshot display metadata. Older names are explicitly current
lookup metadata, never claimed as historical names. Images resolve recorded
revisions/hashes, not current activation. Missing evidence is visible as missing.
History GETs do not settle/replay jobs; stale attempts are displayed as timeout.
240px list thumbnails and 1600px detail previews are private display derivatives.

Text comparison UI presents results in one modal. The reference image is rendered once by `EvidenceResults`,
with element hit targets and an overlaid zoom action; legacy/unparseable evidence
keeps that same single reference image without element targets. No duplicate
reference panel or new recognition request is introduced. `useComparisonTask` owns
a single POST and independent
1.5-second GET polling. `ComparisonDialog` owns presentation only: closing it
never cancels the backend job. Account-keyed sessionStorage stores identifiers,
binding metadata, start time and visibility, never image bytes, credentials or
result logs. Account changes remount the workspace; changed input fences stale
responses. Refresh performs owner-authorized lookup by request ID when the POST
acknowledgment was lost, and never resubmits an uncertain paid operation.
The existing backend deadline and OCR/matching paths are unchanged.

`main` is packaged into `/opt/vantaline/releases/<release-id>` and production `current` atomically points to one immutable release. Mutable data, environment configuration, model artifacts, and database state remain outside release directories. A release contains backend source, one production frontend bundle, migration definitions, locked dependencies, `VERSION.json`, and `SHA256SUMS`.

The browser cookie identifies a workstation independently of login. User permissions still gate configuration, connection, camera inspection, attempt, and receipt operations. Secrets remain in GitHub Environment secrets or restricted server environment files and are never represented by real values in Git.

## Browser Agent foundation

The developing WebMCP surface shares page callbacks and existing API query functions.
Its typed registry, native permission waits and PostgreSQL operation primitives
are documented in [Agent platform implementation status](agent-platform.md).
Full-site coverage, shared policy enforcement across legacy/background paths and
independent worker admission are still incomplete. Protected PostgreSQL requests
now use indexed session/account lookup; analysis detail uses its primary-key loader.
These changes do not establish the planned million-record latency target.

WebMCP registration cleanup retains active result channels through the next
JavaScript task after callbacks settle, avoiding premature native cancellation on
Chrome 152. Revocation still blocks new execution immediately. Browser tests await
resolved discovery snapshots; a Promise-valued polling predicate is not a ready
signal. See the lifecycle investigation in the Agent implementation document.

## Codex text comparison beta

An independent default-off workspace submits frozen label inputs to a PostgreSQL
queue. A separate same-host worker owns one isolated Codex session per task; its
Unix-socket CLI adds versioned report items and source-derived evidence. Reports
remain advisory, with separate human review and no PLC path. Existing OCR/Qwen
flows are unchanged. See [Codex beta](codex-text-compare.md) for boundaries.

The worker may explicitly expose a dedicated loopback HTTP proxy to its Codex
child through `VANTALINE_CODEX_COMPARE_PROXY_URL`; website/DB environment remains
excluded. The independently managed proxy stays outside the filesystem namespace.

### Codex label inspection cards v2

The legacy single-label task endpoint creates `label-v2` reports with frozen original-coordinate
reference selection. The website calls the existing task API; all agent writes
remain on the private task socket. Elements, additive checklists, per-dimension
results, issues and local decoding evidence are append-only events with current
JSONB projections. The ten overall dimensions and category-specific element
coverage are validated before finalization. Historical v1 text reports retain
v1 validation and rendering. The readonly task-scoped label inspection skill is
explicitly named and included in the fresh exec input; version/hash are recorded.
The independent decoder subprocess receives only a frozen crop, has a 15-second
limit and never follows payload URLs. No old OCR/Qwen pipeline or PLC is invoked.

Label annotation SVGs use the original image aspect ratio so marker text scales
uniformly; issue and element labels use separate vertical anchors. Skill v2.2
requires Chinese report prose while preserving the source label's language.

### Order batch inspection v3

The Codex entry now mounts an authenticated full-screen workspace at the existing
/workspace/text-compare-codex URL, outside AppShell. Its bare entry lists active,
draft and historical tasks through the existing owner-scoped /tasks pagination,
including single-label reports with no separate legacy menu or data migration.
Explicit new-task, task-detail and label-detail views have parent navigation;
entering the list never redirects to the last batch. Draft URLs resume editing,
while submitted task inputs stay read-only. The preparation/detail bench has two
equal-width, viewport-height panels: order selection and Word import display their
extracted references inline on the left; actual labels occupy the right. There is
no separate reference tab or panel. Narrow controls adapt within the two halves.
Drafts, uploaded photos and imported references live in the task store. Word import
reuses direct DOC/DOCX embedded-image extraction and the owned standard library,
without activating the standard or launching old Qwen/OCR preparation. Identical
reference bytes are deduplicated with source occurrences retained.

One label-batch-v3 task owns all uploaded actual label cards and exactly one exec
session with a shared 600-second deadline. Import/queue time precedes that deadline.
The model publishes standard regions and correspondence, then per-label v2 element
plans, checks, issues and summaries. Unused document images are outside scope; every
actual stays present, with ambiguous correspondence requiring human confirmation.
CLI operations explicitly name a label; geometry/evidence use its frozen originals.
The batch overview contains summaries/counts only; detailed child reports are fetched
separately. Problem cards precede uncertainty, pending and passing cards. A manual
correction or selected rerun creates a linked fresh batch, never resumes a session.

The independent label workspace binds async navigation to its mounted account
and initiating view; late responses cannot navigate after a view change/logout.


The task workspace is a fixed 100dvh shell: compact header, contained image stage,
resizable result/history dock, and independently scrollable panes. Import and task
navigation retain the same Fullscreen API root. Only explicit task/new-task clicks
request fullscreen; direct links/reloads use the fixed viewport fallback. Owned
fullscreen exits on list/external navigation or unmount, and camera capture uses
the actual-image stage rather than a second vertically stacked preview.

Native file pickers can exit browser fullscreen (including macOS Edge). The label
workspace remembers fullscreen only for that picker gesture and attempts restoration
on file selection while transient user activation is available. Cancellation, explicit
exit and navigation clear that intent; upload completion never forces fullscreen.
When restoration is unavailable the fixed viewport and manual toggle remain usable.

Label result issues use a single 32px desktop row with 16px text, number, type and description. Secondary evidence and uncertainty fields remain available in a modal inside the fullscreen root. All reliable existing issue boxes are displayed with matching numbers; selecting a row highlights that number on both images. Missing geometry is never invented.

## Label photo quality admission

The label worker performs deterministic OpenCV checks on read-only copies of the
unchanged prepared JPEGs before the first paid call. At least one localized black
label must pass. After layout, the selected extent must identify one complete
candidate; a rejected/ambiguous target stops before comparison. A crop is measured
again on the exact second-stage JPEG. Paid calls are therefore 0, 1 or 2; successful
comparisons retain the original two request bodies. No OCR, extra provider, PLC
operation, input enhancement or camera setting change is introduced.

New submissions freeze the quality policy version/hash. Old queued submissions
without that policy, or incompatible policies, stop without external I/O and
require a new linked run. Terminal history is never re-evaluated. A quality failure
uses failed/REVIEW_REQUIRED with a QUALITY_* code, no result or model score.

Label task creation accepts either Word or one static JPG/JPEG, PNG, WebP or BMP. Direct images are strictly validated before persistence and become one complete version-1 standard; they do not enter the actual-photo quality gate or any model call. Source `image` uses existing task JSON and private media fields; no schema migration or new endpoint is required.

## Settings and model routing

The administrator cost ledger is assembled through `analytics.cost_api`, with
`CostLedger` owning aggregation and `CostRepository` owning read-only source
access. Pricing and classification live in `analytics.cost_pricing`. The root
injects lazy path, runtime repository and existing task loader callbacks; no
connection or request identity is stored in the ledger. PostgreSQL raw JSON
remains authoritative, legacy source paths still define stable call IDs, and
file metadata is read only after store-backed payloads. Existing loader locking
and pricing are unchanged by this extraction. Analysis-record endpoints use the
separate analytics query/access/repository services described above.

Settings groups administrative controls into 模型与 API, 设备与运行 and 用量与成本.
`model_profiles` resolves label, manual, pipeline, image, training_assistant,
accessory, training_vision, document and ocr independently. Provider adapters keep
their own wire formats; labels no longer compare a queued job against a global
model constant. Codex Beta, local OCR, YOLO and browser PLC remain separate engines.

Profiles are immutable metadata versions in PostgreSQL; restricted server secret
storage holds credentials. Submission snapshots bind profile ID/version, provider/model and a SHA-256
fingerprint of shipped prompt-producing source (dynamic inputs stay in task
records), and
workers scope existing provider calls to that snapshot. Existing pre-migration
jobs use the initial migration snapshot. Video scopes cover all frames; manual
sessions preserve their original model binding. Public task projections remove
private configuration references. Usage failures must not turn a successful paid
response into a failed/retried call. No new cross-model fallback is introduced.


## Unified PDF inspection

The unified label-inspection service now owns PDF manual tasks. A globally leased deterministic PDF importer publishes complete immutable revisions; a separate versioned two-call page strategy uses the same durable run/call storage. Historical manual routes are read-only, and old frontend entries redirect into the unified task list/history. No PLC path changes.


PDF result compatibility: optional `consistentItems` entries may be strings or objects with a string `description`. Only that non-decision summary is normalized; raw provider evidence remains immutable. Missing/invalid descriptions and contradictory difference decisions still fail closed. Label parsing, PDF prompts, image inputs and model settings are unchanged. The PDF scope caption refers to page content rather than other labels. A regression covers enriched agreement summaries, input immutability and contradictory results.
