Codex comparison `list` and `events` now have a narrow repository read transaction. It commits on success, rolls back on decode errors and closes its cursor without taking the global comparison advisory lock. `get` and every state transition retain the original serialized transaction, including worker prechecks before artifact side effects. HTTP events still performs its existing locked ownership lookup first.

The label task-list first page now indexes its already loaded legacy label records by the existing standard-or-orphan key. Legacy task construction and run-history projection reuse record references in original order, removing repeated whole-record scans for each label order. Detail reads, manual/Beta grouping, asset lookup, SQL, advisory-lock boundaries and persisted page snapshots are unchanged.

The label repository now runs `list`, bounded native-run batches and legacy-source lists in short committed PostgreSQL read transactions without the global label advisory lock. `get`, request-id/model-snapshot lookup, idempotency lookup, page snapshot creation/cleanup, claims and all writes retain the existing write fence. This keeps read ownership and connection lifetime local to each request while allowing ordinary list reads to see the last committed version during a writer transaction.

Label task-list first pages now batch native run reads in groups of at most 64 task IDs. Each group uses the existing account-bound query in an unlocked short read transaction; task projection, legacy/manual/Beta merging, list sorting and 15-minute result snapshot remain unchanged. Task detail retains the original per-task run read. This is only the first read optimization; old-source repeated scans and full run JSON still require separate work.

PLC diagnostic receipt/finalization now uses `DiagnosticState.finish` through late-bound lease-record and current-user capabilities. The root keeps a thin compatibility adapter; the original PostgreSQL mutation, HTTP permission boundary, error order and browser serial ownership remain intact. Finish accepts active or draining leases, including expired deadlines, and clears only the three in-flight diagnostic fields after verifying session, epoch, owner, ID, token and outcome.

PLC diagnostic confirmation now uses `DiagnosticState.confirm` through one added late-bound digest comparator. The original root adapter, active-lease guard, PostgreSQL mutation transaction and HTTP permission boundary stay intact; receipt/finalization now live in the same focused state service. Confirmation does not consume the token, alter lease expiry or prove a browser ACK.

PLC diagnostic reservation now lives in `plc/diagnostic_state.py` with explicit late-bound token, clock, lease, frame and mutation capabilities. The root application keeps its public adapter, while shared active-lease validation, PostgreSQL mutation and browser serial I/O remain in their existing paths. A reservation still persists only a token hash and does not extend the lease expiry.

PLC browser lease model rebinding now lives in `plc/lease_maintenance.py` through an eighth late-bound capability for the shared active-lease guard. The root function remains a compatibility wrapper. Model ID validation, fencing, in-flight rejection, lease write order, PostgreSQL transaction, browser serial ownership and ACK evidence are unchanged.

PLC workstation claim and activation transitions now live in `plc/lease_acquisition.py` with explicit late-bound capabilities. The application entry retains compatibility wrappers, while the same PostgreSQL row-mutation transaction, permission gate, browser serial ownership, and ACK evidence rules remain in force.

PLC browser lease heartbeat and release transitions now live in `plc/lease_maintenance.py` behind seven narrow late-bound capabilities. The root entry point keeps compatibility wrappers and the existing PostgreSQL mutation transaction, so browser ownership, fencing, and dispatch evidence stay in their previous order.

Legacy PLC configuration diagnostics now register GET/POST through `plc/config_diagnostics_api.py` and assemble the GET projection in `plc/config_diagnostics.py` using explicit source, display, runtime, access and error ports. The POST remains read-only with `system_settings` authorization followed by 410; unreachable historical write code stays in the root compatibility adapter. Lease/dispatch state and browser serial ownership remain unchanged.

Five PLC dispatch/diagnostic HTTP routes now register through `plc/dispatch_diagnostic_api.py` in original order. `plc/dispatch_diagnostic.py` owns only existing permission order, delegation and 409 error translation through narrow late-resolved ports. Attempt/receipt persistence, evidence, idempotency and uncertain-result state remain in root business functions.

Five PLC connection-lease HTTP routes now register through `plc/connection_lease_api.py` in the original order. `plc/connection_lease.py` holds only station/model authorization, delegation and unchanged 409 error translation through narrow late-resolved capabilities. The lease state machine, epoch fencing, persistence, browser serial ownership and ACK behavior remain in the existing implementation.

The extracted dependency-direction guard now includes the PLC package and rejects application-entry imports, cycles, namespace injection and wildcard imports there. Five PLC workstation-management HTTP routes now register in their original order through `plc/workstation_management_api.py`. `plc/workstation_management.py` owns the thin get/list/pair/config/profile-verification flow with explicit access, projection, mutation and error capabilities. Root request models and lower-level workstation state remain unchanged; the get/list path can still cause the existing migration and expiration writes.

Pipeline draft, sample, and training stage transitions live in `pipeline/stage_advance.py` with policy, asset, job, and runtime ports. The Web entry retains the public callable, pinned-model scope at its existing caller, and late-bound collaborators. Progress persistence keeps its own task lock; the transition has no new outer lock. Request models, actual job submission, task storage, and PLC behavior remain with their current owners.

Pipeline advance lifecycle now lives in `pipeline/advance_runtime.py`: guarded stage execution, the background runner, scheduling and cancellation share one focused runtime. The Web entry retains the pinned-model decorator, process-shared task/registry locks, inflight set and cancellation Event map. Explicit capabilities preserve locked snapshot/save, unlocked guarded invocation, the two distinct cancellation outcomes and final stored-record replacement. The stage algorithm remains in its existing module.

Pipeline auto-Agent background steps now run and schedule through `pipeline/auto_agent_runtime.py`. The root retains pinned-model binding, shared inflight registry and thin adapters. Explicit task, decision, execution and scheduler capabilities preserve the first locked eligibility/step-limit check, unlocked decision, second locked commit and unlocked advance scheduling. No Agent decision policy or worker topology changes.

Pipeline recommendation pre-generation now runs and schedules through `pipeline/recommendation_runtime.py`. The root keeps the pinned-model decorator and the process-shared inflight set/lock; narrow late-resolved ports preserve the task lock around two reads/writes, the unlocked provider call, and the existing failure and cleanup order. This does not change worker topology or recommendation policy.

# Architecture

Pipeline trained-model linking now lives beside the reverse run lookup in `pipeline/training_links.py`, as a separate class with a late-resolved catalog capability. It selects the first visible matching run and mutates the caller-owned task in place. The caller still owns locks, saves and any following Agent or training actions.

Pipeline training-job lookup and status projection now live in `pipeline/training_status.py`, separate from terminal training-to-pipeline synchronization. Late-resolved capabilities preserve the selected loader, root-linked callback and Agent stage updates; the caller retains locks and storage. Local interrupted-job projection may still write training state, so this is not a read-only boundary.

Pipeline status reconciliation now lives in `pipeline/reconciliation.py`. It preserves the original per-task reap, sync and auto-agent decision order through late-resolved capabilities; server retains the shared registry/locks, background runners, schedulers and public wrappers. No training job scan is added per task.

Pipeline accessory add/remove routes now register in their original order through `pipeline/accessory_routes_api.py`. `pipeline/accessory_routes.py` owns request authentication, canonical ID resolution and ordered alias deletion using narrow late-resolved catalog capabilities. The underlying accessory store and alias policy retain ownership of persistence and locking; partial deletion and payload override behavior stay unchanged.

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

`runtime/path_configuration_composition.py` owns ServicePaths, ServiceDirectories,
LocalPathMigration and ApplicationConfiguration as one inert graph. Directory
initialization, config save/read, sanitization and migration recursion select
named methods on that domain owner, without calling entry forwarders. Request
identity and PostgreSQL selection remain operation-time capabilities. The default
entry retains explicit compatibility aliases. This closes the path/configuration
graph, not the complete infrastructure builder or application factory.

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


## Agent policy read transaction

The Agent policy display path in `storage/agent_operations.py` uses a short owner-scoped read transaction. Agent writes and admission still use the per-account advisory transaction lock, so a display read cannot reserve budget or make an admission decision. This is a read-path boundary only; operation state ownership and worker topology remain unchanged.


## Fixed-reference model read transaction

A fixed model profile reference now reads its immutable profile version and mutable connection-test row through a short PostgreSQL transaction. When no explicit reference or scope is available, `resolve` obtains an initialized task snapshot; this snapshot now uses a short read transaction. Migration and all writes retain their advisory lock; the admin display now uses a short read transaction as described below. Usage-call listing also uses a short read transaction, with row conversion inside the transaction and JSON decoding afterward. Secret and proxy references remain bound to the requested version and are read only after the transaction closes.


## Model registry initialization fast path

Model profile `initialize()` first checks the committed state row in a short read transaction. A truthy row ends initialization without waiting for the global profile write lock. If state is missing or falsey, the read transaction closes before acquiring the original advisory transaction lock, and the original state check repeats inside that lock before any migration or secret operation. Cold migration and writes retain their advisory transaction boundaries; task snapshots and the admin display use short read transactions as described below.

## Model task snapshot read transactions

`Service.snapshot()` and the first state read in `snapshot_for_record()` now use short PostgreSQL read transactions. Snapshot projection still reads the binding state first and then its append-only profile versions; a concurrent uncommitted binding update returns the last committed binding. Historical records still compare `created_at` strictly with `migrated_at` and deep-copy the migration snapshot. For other records the first transaction closes before the existing separate `snapshot()` call. The scope, secret resolver, public projection fields and permissions, and every write transaction retain their prior behavior.

## Model admin public read transaction

`Service.public()` now reads the model-profile state, append-only head versions and each version-bound connection-test row in a short repository read transaction. The state revision, bindings and heads are captured before projection, preserving profile order and `used_by`; mutable test rows can reflect later committed statements because PostgreSQL READ COMMITTED is used. The projection whitelist and administrator route guard are unchanged. Cold migration, profile/binding writes, tests and usage-call registration retain their advisory write transactions.

## Label list-only run payloads

The first task-list page now calls a bounded list-only run reader for groups of at most 64 native task IDs. Its SQL result removes only five fields that `public()` already discards for JSON objects whose own `kind` is `run`: `model`, `prompt_hash`, `layout`, `transformations`, and `profile_snapshot`. Non-run or non-object JSON is returned unchanged. The API still decodes, projects and sorts every run per task before filtering the mixed native/legacy/manual/Beta rows or creating the fixed 15-minute page snapshot. Detail continues to fetch complete run JSON. This lowers transfer size for ordinary runs; it does not yet replace full-row reads with SQL summaries or remove the older source scans.


## COS compatibility stage

`storage/artifacts` owns explicit logical paths, append-only PostgreSQL generations,
private content-addressed STANDARD objects, verified pinned reads and Unix process-shared
scratch reservations. Business modules never patch `Path`/`open` or mount COS as a filesystem.
The default remains `local`. The comparison/text media stores, output HTTP responses,
training archive/export/transfer/import, dataset/model catalog and native model loader
now have opt-in adapters. This is not yet a complete production cutover: remaining
upload, generation, image-processing and worker file operations require conversion
and disk-inaccessible acceptance before enabling COS on production.

COS publication verifies a complete remote SHA-256/length before a CAS appends the
next available generation. Database failure retains unreferenced remote objects and
the producer source; deletion adds a tombstone without deleting historical objects.
HTTP ownership and RunPod token authorization precede lookup; HEAD/Range use a pinned
selected generation. Training ZIPs stream indexed original bytes without a second
dataset tree or lossy transcode. Native model initialization uses an original-name
leased file and cleans it after the loader returns.

The next compatibility slice routes ordinary OpenCV image reads/writes, accessory/background uploads, sample image/label/manifest publication, legacy incoming evidence and video decoding through explicit business-file adapters. Cache-backed native reads use links to read-only cache blobs with original filenames, held by a cache pin and a process lease, so model/video reads do not duplicate whole files or take the training preparation slot. Configuration and packaged files keep local I/O.

Native worker scratch can use independently capped, preallocated ext4 filesystems backed by files on the system disk. This is local temporary storage only. Multipart parsing reserves the upload budget before body receipt; native workers retain the exclusive work reservation through child exit and result publication. COS-mode Cursor Image2 failures never automatically invoke a paid fallback. JSON resource mutations carry the version observed when reading and reject stale updates. The location index preserves source mtime_ns on historical import so cache/provenance checks do not mistake migration time for generation time.

COS RunPod submission reserves upload headroom and publishes a durable per-job claim before the paid POST. An existing claim prevents automatic resubmission after a timeout, process death or lost response; operators must reconcile the original remote job. Dataset generation and ZIP preparation share the exclusive work slot, and COS training rejects local/legacy-worker fallback. Regression fixtures exercise capacity rejection before POST and a timed-out POST that is called only once.

The explicit detection image ports use the shared business-file adapter in COS mode, including inspection evidence, reference sheets, annotations and encoded input. OpenCV transforms remain injected capabilities; only file reads and writes go through verified storage. Pipeline model/dataset availability uses the same index.
## Label consumer lifecycle

The label consumer lifecycle now belongs to `label_inspection/worker.py:LabelWorker`, without FastAPI or server imports. `worker_api.py` installs one pair of hooks per application and rejects conflicting repeat registration. Two process-local consumers retain the PostgreSQL global concurrency fence. A short lock admits iterations; stop refuses later admissions, while an earlier admitted connect/claim/process and its thread-local connection cleanup remain in flight. Drain acknowledges success only after both threads exit; all joins share one monotonic 480-second budget, and a live timed-out generation cannot be replaced. This describes the embedded predecessor topology; PDF imports retain their separate Web daemon after external activation.

A connection-cleanup exception marks that consumer generation failed even after its threads exit. Drain returns false and in-process restart is rejected; process restart is required. The lifecycle regression also retains falsey repository/run handling and the original idle decision after cleanup.

Attempted threads are tracked before native launch. Any startup exception fails that controller even if no thread is currently live, because launch may already have happened. Registration is serialized per process to prevent duplicate hooks during concurrent composition. Synthetic tests cover failure before and after native launch and concurrent registration.

Label batch/payload performance acceptance now emits per-case synthetic samples before failing a guard. This is diagnostic instrumentation of the existing isolated PostgreSQL benchmark; repository, HTTP and worker boundaries are unchanged.

The shared streaming file checksum helper also uses the business-file adapter. In COS mode, provenance checks during image-job startup pin and read the verified object cache; they cannot open the retired logical file path. Local configuration, package files and temporary archives retain their existing local stream behavior. Missing objects and read failures propagate before metadata is published.

The release controller is a root-owned standalone Bash script rendered deterministically from `scripts/install_release.template.sh` and six standard-library runtime modules plus the explicitly bundled pure configuration contract. Its quoted Python helper runs `/usr/bin/python3 -I -S`; package metadata selects only fixed topologies and service roles. It never imports a candidate validator. Schema-2 transitions use peer-verified private Unix sockets, exact build/PID/process-instance identity, a maintenance acknowledgement, queue drain and consumer pause before service changes. The preceding managed bridge declared schema-2 embedded, and the Web implements this control protocol. The external activation below follows that bridge.

The protocol requires every new managed build, embedded or external, to report maintenance and a paused consumer before controller acceptance. The runtime must persist accepted build activation separately from process identity so ordinary restarts of an accepted build can retain their intended state. The managed embedded predecessor implemented that activation state; shared configuration and external activation follow as separate releases.

Rollback pauses the candidate before waiting for its active runs and admitted iterations to finish; it preserves queued rows without starting paid work on an unaccepted build. A forward switch from an already-paused predecessor also retains its backlog and pause intent. An active predecessor still drains its queue before a normal forward switch. State-machine and rendered-installer faults cover queued legacy-to-managed rollback and paused-backlog transitions; queued work is not evidence of an active call.

## Managed embedded label control

Managed embedded label runtime uses the immutable package topology, a typed process identity, thread-owned repositories, a root-authenticated Unix control socket and `label_runtime_state`. New builds initialize paused behind maintenance; a restart of the same build preserves its durable intent. A process/role lock precedes initialization. Duplicate startup keeps the existing threads; a completed second lifespan creates a new instance and two new consumers. Pause counts each admitted connection/claim/model/cleanup iteration until it exits. The paid `process()` pipeline is unchanged. The independent-worker bootstrap and explicit shared configuration described below are prerequisites before an external manifest is accepted.

The control endpoint owns a dedicated PostgreSQL connection factory with explicit connect/TCP failure-detection settings; request and paid-task connections retain their configuration. SQL timeouts apply after connection, and the root client has a separate bounded acknowledgement deadline; these do not constitute a hard total deadline for every driver operation. A control-thread shutdown timeout retains its role lock and fails that controller generation until process restart. Regression probes block connection creation and verify no duplicate role, then release the old thread for cleanup. A real claim/processing-substitute/cleanup integration proves pause does not acknowledge drain until two admitted iterations finish, while queued task snapshots remain unchanged.

Label list query architecture is unchanged by the stop-allowance bridge. Its repository benchmark now initializes planner statistics for the disposable bulk-loaded fixture before comparing existing full and projected payload reads; no runtime SQL, index, transaction or connection policy changes.

## Proposal: shared label runtime configuration preparation

The preceding embedded configuration bridge introduced a bounded data-only snapshot of the existing label/database/storage/network settings, exact existing model-secret environment references and data directory. Unset and explicit empty values remain distinct. COS credentials are represented by their byte digest and transferred only through a private root-authenticated path; a worker must receive its own systemd credential directory. The pure contract and private-file roundtrip tests use synthetic values. The candidate Web wiring can capture a configuration revision and export its immutable snapshot only through the private authenticated control socket; public status contains only the revision. A prepared root file publisher writes immutable private versions and restores one atomic current pointer. The installed helper now embeds the audited data-only contract, captures a peer/build/instance-bound private export before external transitions, and journals the previous configuration pointer before mutation. It restores that pointer with the complete release on rollback, derives escaped mount dependencies and provisions the worker own systemd credential from root-owned bytes. No candidate application module is imported by the isolated root helper. Tests cover pointer interruption, export tampering, private modes, standalone execution and synthetic installer recovery. That bridge release retained embedded execution. Its complete-release acceptance is a prerequisite for the external activation described below.

## Proposal: standalone label process

The candidate `label_inspection.runtime` bootstrap reads the root-owned immutable configuration and its own systemd credential, checks the active package build/topology, initializes local storage, and creates separate thread-owned business and control repository factories. It imports no Web application. The existing model service is reused through an existing-registry reader: missing registration fails startup rather than migrating legacy settings. Secret-file syntax, environment precedence, immutable version references and usage accounting remain unchanged. Manifest v141 names 366 actual sources; historic snapshots are not rewritten.

In external mode, Web composition owns admission/control only and constructs no label consumer. The standalone process owns the existing two-thread consumer and its exclusive role socket; SIGTERM/SIGINT stop new work and use the existing 480-second drain budget. Real isolated PostgreSQL tests cover old-model resolution after settings changes and reader recreation, actual child PID/peer checks, duplicate-role rejection, signal drain and controller-driven embedded-to-external acceptance, failure and complete rollback. Synthetic model values and local storage are used; no paid inference or PLC call occurs. The bootstrap-only predecessor did not enable an external release. External activation remains conditional on preceding complete-release acceptance and final exact-build validation as described below.

Standalone signal handlers only assign a monotonic stop latch. Normal control flow performs drain and cleanup; initialization checks the latch before consumer startup, and each consumer admission checks it even across the check/start boundary. Real child-process tests inject repeated SIGTERM/SIGINT before and during initialization and while native thread startup holds the worker lock; no post-stop iteration is admitted. Already admitted iterations retain the existing drain budget.

The unauthorized control-socket regression accepts EOF, connection reset or broken pipe only on the denied-peer path, asserts zero handler calls and unchanged durable maintenance state, and forces EOF-before-send to cover early rejection deterministically. Authorized commands retain their strict response contract; runtime socket behavior is unchanged.

## Proposal: label runtime monitoring

Managed processes publish bounded heartbeats on the existing private control thread with a five-second target interval after the previous tick completes. Database work and control requests can delay a tick. Each uses the dedicated thread-owned connection factory. The operational table stores only build/configuration/process identity, worker state, process-lifetime counters and fixed recent-error codes. A blocked heartbeat retains the same role lock on shutdown timeout. The private deployment protocol remains unchanged.

`GET /api/label-inspection/runtime` requires administrator access before any database call. Its short unlocked READ COMMITTED transaction samples state, queue and heartbeat in separate statements; these are not an atomic health snapshot. It returns queue/active counts, oldest queue age, maintenance/pause intent and expected-role heartbeats; missing, mismatched or older-than-15-second samples are unhealthy. Heartbeat freshness is sampled liveness, not a guarantee against a subsequent crash. Lock acquisition counts/total/max wait include successful and timed-out acquisition attempts. These and rejected duplicate submission/stage-call counters belong to the process lifetime: process restart resets them, while a control restart within the same process changes the instance but retains counters. Idempotent replay is not counted as rejection. Errors never include exception strings, media, customer fields, secrets or filesystem paths. Real PostgreSQL/HTTP tests cover authorization, redaction, actual lock contention, duplicate refusals, stale generations and heartbeat shutdown. Manifest v142 names 367 actual sources. The observability-only predecessor retained embedded execution; the external activation below is a separate release and requires acceptance of every predecessor.

The administrator runtime endpoint is registered in the exhaustive tested label-route guard set. The assembled authentication regression exercises anonymous 401, member 403 (including a synthetic stored inspection/system-settings over-grant), administrator 200 and zero monitor access on rejection. Endpoint-local admin authorization and public error formats remain unchanged; no broad route exemption or additional feature grant is introduced.

## Activated label process topology

The immutable package selects external label mode: Web registers HTTP/admission and
its control role without constructing a label consumer. A separate lightweight
`local_inspection_service.label_inspection.runtime` process reads the versioned shared
configuration and creates its own model service, two consumer threads and thread-owned
business/control repositories without importing the Web application. Both processes
use one database and one complete release. Authentication ContextVar, task model
snapshots, stage-call evidence and existing global claim limit remain unchanged.

Label detail reads (`LabelRepository.get`) now use short committed-read transactions without the label write fence. Mutations re-read and validate inside their original transaction; `request_run` retains the fence so an in-flight idempotent submission still resolves its persisted model binding.

### PLC domain boundaries

`plc/` now owns historical event projection, evidence transition policy and persisted-record validation; dispatch mutation and browser receipt services; workstation service/repository adapters; retained legacy dispatch/runtime/capture-state workflows. `schemas/plc.py` owns strict request models. The application entry composes these services with explicit storage, identity, lease and policy interfaces. Business modules do not import the entry, and dependency checks include both PLC protocol modules.

This is structural relocation. The browser retains physical serial ownership; legacy server transport stays disabled. No lease, ACK, uncertain-write retry, timeout, receipt or callback-order policy changes are included. Temporary entry forwarders preserve assembled endpoint and existing dependency-replacement contracts until final composition cleanup.

### Auto-optimization domain boundaries

The `training/auto_optimization_*` modules own settings, recommendations, task initialization and storage, readiness, capture, status, mask policy/verification, label generation, sprite sizing/publication, rendering, synthetic batches, dataset construction, training scheduling, label processing, shadow evaluation and request handling. Focused typed ports connect each service to its existing collaborators. The application entry assembles them and retains temporary forwarding functions; no new process, global user or database connection is introduced.

This is structural relocation of existing workflows. Prompt text, callback selection/evaluation order, locks, mutable task ownership, partial effects and exception behavior remain unchanged. Model binding still surrounds the existing caller. No inference, training or image algorithm is adjusted.

### Pipeline workflow boundaries

Pipeline auto-optimization links, task projection, candidate flow, metadata, mutations and AI activation now live in focused `pipeline/` modules. Each receives its own typed record, access, model or execution capabilities. The application entry assembles them and temporarily forwards existing call sites. Shared task locks, saved state, partial mutations, model binding and scheduling order remain with their original owners; this batch changes no workflow algorithm.

### Accessory image workflow boundaries

Accessory text preparation, pose prompts/jobs, reference media, image diagnostics, queue execution/management and candidate artifact ownership now have focused services under `accessories/`. `model_providers/image_provider_configuration.py` owns the existing image provider setup and response interpretation; `training/training_asset_preparation.py` owns the accessory-derived asset preparation used by training. Each boundary receives typed dependencies; the entry retains temporary caller adapters and shared process state.

This is structural relocation of one accessory image workflow family. Prompt text, provider/retry selection, queue timing, owner visibility, media authorization, subprocess behavior, save-before-start order and deletion partial effects remain unchanged. Training and image jobs retain their existing process topology.

### Configuration and service-status boundaries

`config/app_store.py` owns application configuration persistence with explicit file, repository-row and protected-namespace interfaces. `model_providers/local_model_config.py` owns legacy provider configuration normalization and saving; `model_providers/tool_dispatch.py` owns JSON tool result/error projection and existing MCP dispatch. `auth/status_requests.py` owns the permission-aware service status request workflows. Each boundary has narrowly scoped typed dependencies; the application composes them and retains caller adapters.

Existing call-time identity, protected PLC namespaces, PostgreSQL authority, atomic primary-file replacement, model snapshot binding and selected callback timing are preserved. No module stores a global request user or database connection. Dependency checks now include the config package, and source-location checks follow the actual configuration store without lowering required coverage.

## Derived label summary preparation

Storage owns the optional `label_run_projection` side table and its exact
source-change invalidation DDL. This slice creates only empty compatible state;
HTTP list/detail paths, business repositories and task/model evidence are
unchanged. Future publication must validate the actual source row while holding
its row lock until the summary commits; readers must join the authoritative
source and use the original payload for missing/unknown summary versions.
Neither a generic global context nor a second authoritative task store is added.

Label run public projection now lives in the pure `label_inspection/projection.py` module. The API calls the same redaction/field-projection implementation without changing response fields, pagination or storage reads.

## Optional post-settlement label summaries

After the existing label `process` returns, its admitted consumer iteration may
publish derived state through `storage/label_run_projection.py`. This occurs in
a separate transaction after business settlement, never inside the global
label advisory lock. A single owned terminal run is selected `FOR UPDATE SKIP
LOCKED`; the actual returned payload is validated by the pure `run_summary`
policy before a compact projection is committed under that same row lock.
Web list queries can use validated derived fields; details retain their original payload query. No new thread,
process, scheduler or read-triggered backfill is introduced.

The publisher declines active or autocommit connections and never commits a
caller's transaction. It uses local 100 ms lock and 500 ms statement limits;
these do not bound network I/O or total Python execution. It skips a busy source,
missing/wrong-owner run, nonterminal status, or unprovable payload. Business writes
continue invalidating existing cache in their source transaction. Optional
publication failure records a fixed error code, without settling/requeuing the
run or repeating a model call. Pause/stop skips work not yet admitted to the
publisher; in-progress publication and connection cleanup remain inside drain.

The projection storage module is explicitly included in the static dependency
graph alongside its pure label policy; reverse imports into Web composition and
cycles are rejected. Row locking still permits indirect contention when another
writer holds the global fence while waiting for the projected row. Tests preserve
this counterexample; optional work is not described as contention-free.

## Source-driven label list cache reads

The bounded native list query joins each account-owned authoritative run to its derived projection in one statement snapshot. Matching version 1 returns only the proven list fields; missing/unknown versions return the previous trimmed payload. The source controls ownership, membership, SQL task grouping and original row order. Existing Python history validation, raw JSON fractional timestamp sorting, mixed legacy/manual/Beta projection and paging are retained. Detail/diagnostic reads still load the original full JSON. There is no read-time repair, backfill or cache-derived authoritative task. This slice reduces payload transfer; per-task SQL latest/count aggregation remains separate work.

The Web registrar prepends a label-reader prerequisite check to the startup lifecycle, before all previously registered startup callbacks, control readiness and HTTP serving. It obtains the same thread-owned business repository used by label HTTP queries, executes a read-only zero-row source/projection column query, rolls back, and releases the selection. It neither reads customer rows nor repairs grants. A managed runtime without PostgreSQL fails; unmanaged JSON development mode retains its existing absence of this database reader.

Lifecycle registration remains inert. The first reader readiness callback precedes the existing PDF and label startup callbacks; each application passes its own business repository capability to that check.

The label reader's repeated benchmark protocol observes Python CPU/GC outside its original timing window and uses synthetic-session prepared counters after failures. This is validation tooling; application composition, SQL and worker ownership are unchanged.

Service path rebasing, public path projection, JSON path migration and output placement live in `runtime/service_paths.py`. Focused typed settings, policy, file, identity and sibling-call interfaces preserve late resolution without retaining a request user or connection. Existing root forwarders remain temporary composition adapters; migration scheduling and its lock remain unchanged.

Read-cache state is owned by three explicit instances in `runtime/read_caches.py`: request ContextVar memoization, short-lived store values, and JSON metadata-validated values. Each instance owns its locks/state; application composition supplies only the store TTL/clock and file-facade factory. No current user or database connection is retained. Existing request consumers temporarily share the same ContextVar alias; callables are bound directly to cache instances.

`runtime/directories.py` owns directory preparation and the one-time local-path migration lock/completion state. Each application composition creates one `ServiceDirectories` and one `LocalPathMigration`; construction performs no filesystem operation. Existing output/config/migration capabilities are supplied explicitly, with the same directory order and double-checked migration gate.

Four remaining stateless policies are direct domain imports: `runtime/text_policy.py` owns text bounding, `config/environment.py` owns affirmative environment flags, and detection geometry modules own box IoU and maximum-side image scaling. They have no application dependency or state container; entry exports preserve existing callers.

FileDigest in storage/artifacts/files.py owns streamed SHA-256 calculation through a read-only byte-stream capability. Generated upload names live beside path policies in runtime/service_paths.py. The entry retains a digest adapter and directly imports the naming function; neither adds request or database state.

HTTP-safe runtime repository selection and admin probe projection live in runtime/repository_access.py. RuntimeRepositoryAccess receives a thread repository factory and per-call selection/fingerprint/store-kind capabilities; it never retains a database connection. ThreadRepositoryFactory remains the sole connection lifecycle owner. The entry retains three adapters and directly exports the process-local fingerprint helper.

AppConfigStore now also owns save_app_config and mutate_app_config_atomically. Protected configuration mutation uses the same supplied reentrant guard and authorization ContextVar as generic configuration persistence. Its internal load/save calls use its own methods, removing these two business bodies and their callbacks through the entry. Root exports remain bound aliases; no new aggregate service or connection state is introduced.

Historical integration record (before PR266; not the current bundled architecture): That foundation integration followed the accepted reader-readiness source manifest and retained its prerequisite. Its bundled manifest was v157 with 479 unique sources (including `label_inspection/readiness.py`); historical slice counts above refer to their original isolated candidates. The existing fixed reader benchmark protocol remained mandatory; that historical candidate did not include native-history aggregation. The current integration retains the native-history implementation accepted in PR266.

## Native label history statistics

The list-only repository method computes count/latest in SQL for a batch of at most
64 task IDs, only when every native run has a version 1 proof and the caller has
explicitly permitted that task ID. The API excludes every ID associated with any
legacy extension in the same batch, including duplicate identities in historical
raw task JSON. Mixed legacy histories retain all original native rows: historical
JSON text can contain non-finite times, for which replacing Python's full sort with
a merge of per-source maxima changes behavior. Partially proven groups likewise
retain every row and the previous source creation/id order. SQL casts are guarded
by the proof version inside each expression, independently of the outer filter.

The pure `history_summary.RunHistorySummary` value carries count and latest between
storage and HTTP composition. No current identity, connection or service state is
stored there. Full detail and legacy/manual/Beta projection remain unchanged, as do
fixed 15-minute account/filter-bound snapshots. Manifest v151 includes the actual
new source; historical fingerprints are not rewritten.

The native history query carries source/proof JSON references through window
selection and source ordering, then projects the returned payloads. An ordered
subquery with OFFSET 0 keeps wide fallback JSON construction above its sort.
Whole-group completeness, version-guarded keys, owner filtering and fallback
membership are unchanged; all source rows still participate in window counts.

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

The current native-history integration retains the accepted foundation and readiness modules. Its bundled manifest is v158 with 480 unique sources. Historical counts above describe earlier isolated slices. The original 47 reader/history cases and both frozen baselines remain required; legacy/manual/Beta SQL aggregation is not completed by this native slice.

Account-scoped configuration, accessory merge, model permission and media/response projections now live in `auth/account_projections.py`. Owner-scoped naming rules live in `records/resource_names.py`. Each service uses focused typed access/policy/catalog/media interfaces and stores neither a request identity nor a connection. Existing deep/shallow reference behavior, callback order, legacy output sharing, linked-task exclusions and first-model-run deduplication are retained.

Origin comparison/admission and public runtime URL/path projection now live in `auth/public_network.py`. Focused origin, endpoint-mask and account interfaces preserve existing per-call policy evaluation. The application composes them for middleware and status services; no DNS lookup or new network access is introduced.

Administrator documentation composition is owned by auth/docs_api.py. DocumentationAccess holds only authentication/account-policy callables; every request authenticates before checking the supplied app OpenAPI cache. The registrar closes over the provided FastAPI instance, retaining the three route names/order and separate app caches. Constructors invoke no authentication or storage. Root aliases preserve entry compatibility; full server application-factory work remains separate.

AuthenticationServices in auth/composition.py builds one focused authentication graph: password hashing, repository, account/session/access services, login limiter, users and login flows. It owns the shared reentrant write guard. Internal account/session dependencies bind actual domain methods; the entry retains service and function aliases while HTTP registration stays in its original order. Constructors do not invoke settings, repository factories, authentication or other external I/O. RequestIdentity remains context-local and database selection stays per execution thread.

`auth/http_composition.py` composes the real security middleware and authentication, user and administrator documentation routes around one `AuthenticationServices` and its `RequestIdentity`. Internal authentication/account methods bind directly; output-media and origin policies are explicit HTTP capabilities. The application installs each registrar at its original position. Root exports remain compatibility names, but these HTTP paths no longer look them up. This closes the auth HTTP graph only; full production application-factory and lifecycle work remains outstanding.

The earlier identity-only candidate used manifest v162/488 on fac841. Its PR265 latency failure remains a recorded NoGo; those results do not approve this new integration.

This identity integration is rebuilt on main734e5e0 after PR266. It retains native-history SQL, readiness and all47 fixed reader/history cases byte-for-byte from that main. The complete manifest is v163 with489 unique sources; earlier slice counts are historical. This changed prerequisite requires fresh integration, hostedCI and release acceptance and does not explain or waive PR265 performance failure.

Provider proxy selection and URL transport dispatch now live in `model_providers/proxy_runtime.py`, with focused settings, validation and transport interfaces. Environment selection, optional local probe and request dispatch preserve the existing order and exception boundaries. The shared local proxy default is declared in that module and re-exported by the entry.

The optional stdio LocalAiMcpClient now lives in model_providers/mcp_client.py and owns its process handle, RLock and message counter. Composition supplies only the working directory, provider error type and runtime metadata. Construction starts no child process; existing explicit warmup and tool dispatch retain their lifecycle and ordering.

The remaining MCP mode and image-payload policies live in model_providers/mcp_runtime.py. Pure mode helpers and four constants are directly exported; the root composes a payload adapter and a warmup service, retaining the startup thread hook. Warmup resolves the client separately for start and failure-close, preserving replacement timing. Constructors read no environment, encode no image and start no process. Tool dispatch, its registry cycle and existing fallback policy remain unchanged.

Model warmup HTTP registration now lives in detection/warmup_api.py and request orchestration in detection/warmup_requests.py. Access/configuration, model selection/readiness, and warmup status/start are explicit capabilities. The entry binds actual domain methods and the provided YoloWarmup instance; constructors obtain no user/configuration/model and start no worker. The route remains at its original registration position. Each application must receive its intended runtime; the registrar creates no hidden singleton or full-application factory.

Local YOLO device and training checkpoint selection live beside the model cache in `detection/local_models.py`. The device function is directly imported; `CheckpointSelection` receives only override, root, application-directory and existence capabilities. It constructs no model, accesses no device and checks no file during construction. Existing callback timing and fallback precedence remain unchanged.

Image file encoding, strict base64 decoding and Windows-worker response selection live in the existing model_providers/payloads.py module. ImagePayloadCodec receives only a byte reader, decoder and candidate selector; the pure decoder is directly exported. The entry retains two temporary forwarders.

Historical integration record (before PR266; not the current bundled architecture): That model/provider integration followed the accepted reader-readiness source manifest and retained its prerequisite. Its bundled manifest was v168 with 494 unique sources (including `label_inspection/readiness.py`); historical slice counts above refer to their original isolated candidates. The existing fixed reader benchmark protocol remained mandatory; that historical candidate did not include native-history aggregation. The current integration retains the native-history implementation accepted in PR266.

This model/provider integration is based on main ad1292a after PR267 and preserves the native-history and reader-readiness implementation accepted in PR266. Its production and test sources match the independently reviewed model candidate 63df072. The complete bundled manifest is v169 with495 unique sources; earlier slice counts describe isolated candidates. Both fixed reader19 and history28 benchmark gates remain mandatory. Publication requires acceptance of the identity release, followed by this candidate’s own CI and independent review; the prerequisite’s first main CI AA failure remains recorded.

The local checkpoint-selection composition contract is structural: its override, root, application directory and business-file existence callbacks remain lazy. Contract verification ignores only source formatting, while dependency substitutions and duplicate composition bindings fail.

Detection task list/create/update/delete workflows are owned by `detection/task_requests.py`, with focused typed account, policy, store, pipeline synchronization and clock interfaces. HTTP route declarations remain in application composition. List synchronization keeps the existing pipeline lock; mutation ordering and storage behavior are unchanged.

`detection/rule_requests.py` owns existing global/task rule updates and trained-spec rule projection. Typed policy, configuration store and account interfaces preserve visibility, normalization, reference identity and error ordering. Application composition retains the original HTTP route decorators and signatures.

The dedicated camera request workflow lives in `detection/camera_request.py`, with explicit access, durable dispatch evidence and image execution capabilities. Application composition retains the same async route and parameter defaults. Ordinary image/video workflows remain separate and cannot create PLC plans.

Detection rule HTTP composition is now local to detection/rule_api.py. It creates one DetectionRules from eight explicit policy/store/access capabilities and registers the two POST routes at their original position. The self-referential rule lookup is now a service-internal call. Config and identity are still obtained for each invocation; constructors do not read stores or start workers. CountRules remains a separate detection-result policy. Root adapters for catalog projections remain until the catalog cycle is explicitly composed; this is not a full application factory or Stage 8 completion.

Duplicate-route preflight is not a transaction around arbitrary FastAPI registration failures. If application construction fails during route installation, discard that partially built application. No retry or cleanup guarantee is added.

This detection integration retains the native-history and reader-readiness implementation accepted in PR266 and the identity release accepted in PR267. It is based on actual main bea11ce from PR268, retaining its Python-version-independent model-binding test fix. Main CI and release acceptance for PR268 must precede publication. All detection production and test sources, including the ordered application entry, match the independently reviewed detection candidate183f739. The complete bundled manifest is v173 with502 unique sources; earlier slice counts are historical. Fixed reader19 and history28 protocols remain mandatory; prior performance failures remain recorded.

AnalysisServices in analytics/analysis_composition.py composes the eight analysis boundaries around one owned reentrant persistence guard. Each existing typed interface still describes only its responsibility. Query presentation binds processing/projection methods and the processing summary directly, removing four internal callbacks through the entry. The entry retains service/export aliases and original HTTP registration. Constructors read no records, users, configuration or paths and open no connection.

This analysis candidate retains the native-history/readiness implementation and accepted model composition from main bea11ce. It is prepared after detection candidate af8d242 in PR269; actual-main rebind and detection release acceptance must precede publication. Analysis production/tests and the ordered entry match reviewed59db3d3. The bundled manifest is v174 with503 unique sources. The original history28 and reader19 benchmark protocols remain mandatory; recorded prior performance failures are retained.

Dashboard shortcut task upsert now belongs to the existing detection/task_requests.py service. It receives the accessory catalog and dashboard name/source through three explicit policy suppliers and reuses existing task storage, identity, clock and projection ports. The entry exports the actual bound method. The original first fixed-name match, selection deduplication/filtering, counts, labels and payload overlay are preserved.

Remaining accessory selection and reference/render dimension policies now live in the existing catalog and physical-dimension modules. `AccessorySelection` preserves eager serialization, requested-ID ordering, alias resolution and fallback behavior; `ReferenceDimensions` preserves reference aliases and render size calculations through focused settings. Existing route-level catalog and dimension services keep their interfaces.

Four remaining accessory entry workflows now belong to their existing modules: job ID matching in image_job_metadata, sprite readiness in ObjectSpritePreprocessor, status update in ImageJobQueue and first-source selection in CandidateArtifacts. The entry exports the module-level function and three bound methods. Same-service operations call their owner directly, removing these internal callbacks through server. Existing typed policy/storage capabilities remain; no new aggregate context or production module is added.

This accessory candidate retains the native-history/readiness implementation and detection composition from actual main dcb4805, and follows analysis candidate bb3afa6. Actual-main rebind and analysis release acceptance must precede publication. Accessory production/tests and the ordered entry match reviewed c43118e. The bundled manifest is v175 with 504 unique sources. Original history28 and reader19 benchmark protocols remain mandatory; prior recorded performance failures are retained.

`runtime/image_worker.py` owns the application-instance image worker startup lock, thread and existing subprocess registry. The entry supplies the loop/thread factory and retains a temporary registry alias for existing consumers. Construction starts no thread; the original guarded start method is exposed directly. No identity or database connection is captured in this owner.

`pipeline/runtime_state.py` owns pipeline task/store guards, auto-Agent/recommendation/advance registries, cancellation events and the list reconciliation timestamp for one application. The entry retains temporary mutable-object aliases for existing consumers, but the reconciliation clock is read and written on its owner. Construction starts no thread, selects no user and opens no database connection.

`training/auto_optimization_runtime_state.py` owns the shared auto-optimization RLock and separate label/shadow thread registries for one application. Existing domain services receive the same owned objects through the temporary composition aliases. Initialization has no user, database, provider or thread-start side effect.

Auto-optimization settings composition now supplies 24 direct typed method capabilities to nine consumer boundaries. Six entry wrappers are bound aliases to one selected AutoOptimizationSettings instance. Consumers no longer look up these six functions through the application entry. The negative-sample startup default remains fixed while environment-derived settings are read when each method runs. Dynamic identity, model binding, repository factories and other lifecycle collaborators remain runtime providers.

This background candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows accessory candidate f397a31. Actual-main rebind and accessory release acceptance must precede publication. Production/tests and the ordered entry match reviewed 5a44e61. The bundled manifest is v176 with 507 unique sources. Fixed history28 and reader19 protocols remain mandatory; prior recorded performance failures remain retained.

## Real-photo feedback foundation

The account-opt-in `real_photo_vlm` feedback adapter collects readable original photos independently of detector pass/fail and instance count. Task-associated AI/YOLO results use the independent `real_photo_states`, `real_photo_jobs`, and `real_photo_events` tables; original bytes are frozen under the owner and exact hashes deduplicate admission. Camera session, source-video and upload-request groups travel only as capture provenance. Initial generated-image pretraining and its shared providers are retained. See [real-photo feedback](real-photo-feedback.md) for shipped boundaries and later proposal phases.

Independent review runs in `training_review.worker`, separate from Web and the label queue. A whole-image report is validated and stored before successful CLI exit grants acceptance. Source/annotation/class-version changes invalidate the review key; partial rounds never enqueue executable training. Frozen train proposals remain queued until the subsequent dispatcher batch.
Retained legacy PLC heartbeat/reconciler/poller start helpers and their six lock/thread state slots are owned by plc/legacy_workers.py. The root keeps three bound entry aliases and supplies narrow heartbeat and loop capabilities. Each owner creates three independent ordinary Locks but starts no thread or I/O at construction. The Web Serial startup hook remains an unconditional no-op; this move does not activate historical server-side workers.

The shared active browser-lease guard is owned by PlcStationService in plc/station_service.py. The entry exports the bound method; existing callers retain its name. Storage record parsing, request identity, protocol, configuration migration and the fallback clock are explicit live capabilities. No repository or request user is captured. Existing station methods and transaction ownership are unchanged.

Retained server-serial activation readiness checks now live in plc/legacy_activation.py. LegacyActivationPolicy has separate source and check capabilities; the entry exports its six bound methods. Database primitive availability, device/read fingerprint selection, optional serial import and ordered activation errors keep their original semantics. No transport is opened or worker started by this module.

Retained PLC runtime namespace mutation, receipt copies and process-owner lease policy now live in plc/legacy_coordination.py. LegacyRuntimeCoordination has focused storage and policy capabilities; the entry exports five bound methods. Namespace transactions remain repository-owned; the service does not cache connections, identity or claim results.

Retained PLC audit projection and dispatch identity lookup now live in plc/legacy_records.py. LegacyDispatchRecords owns six methods with focused record sources and policy capabilities. The entry exports bound methods; existing repository, validation, lock and sanitization services remain their respective authorities.

LegacyPlcOperations in plc/legacy_operations.py owns the two retained one-shot dispatch reconciliation and capture-poll workflows. Configuration, ownership, dispatch and capture capabilities are explicit. The entry exports bound methods, while LegacyPlcWorkers still owns the dormant loop threads. The current application startup continues to start neither legacy loop.

This PLC candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows the reviewed background ownership candidate. Actual-main rebind and predecessor release acceptance must precede publication. Production/tests and the ordered entry match reviewed a139e03. The bundled manifest is v177 with 512 unique sources. Fixed history28 and reader19 protocols remain mandatory; prior recorded performance failures remain retained. Browser-only physical IO, uncertain-write no-retry and inert retained startup remain unchanged.

Public document responses and preview redirects are owned by runtime/web_shell.py with explicit path, file and route-policy capabilities. Entry and SPA registrars remain at their original composition positions; API routes stay ahead of the catch-all. Each shell can be bound to one application without sharing document paths. This domain composition does not yet establish a complete production application factory.

This Web-shell candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows PLC candidate e73394d. Actual-main rebind and predecessor release acceptance must precede publication. Production/tests and the ordered entry match reviewed 4b28b8e. The bundled manifest is v178 with 513 unique sources. Fixed history28 and reader19 protocols remain mandatory; earlier recorded performance failures remain retained.

Seven entry functions retain their exact live prefix while unreachable code after their unconditional return/raise is removed. Current PLC config still delegates to its service; retired capture endpoints retain HTTP 410, and retired model-config mutations retain their prior admin check and HTTP 409. No route or current feature is removed. This avoids introducing module interfaces solely for inaccessible legacy code.

This unreachable-tail candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows Web-shell candidate 82cc0d0. Actual-main rebind and predecessor release acceptance must precede publication. Production and the ordered entry match reviewed ed9dc91; the retained-tail test explicitly handles Python 3.10 frame cells and Python 3.11+ compiler metadata without skipping behavior checks. The bundled manifest is v179 with 513 unique sources. Fixed history28 and reader19 protocols remain mandatory; prior performance failures remain retained. Existing endpoints and live behavior remain; only statements following unconditional exits are removed.

`runtime/repository_composition.py` owns each application connection factory and HTTP repository adapter. Construction performs no connection or query. Internal selection, probe and cache-key suppliers bind that owner instead of looking back into the entry namespace. Environment values remain live inputs, and connection objects remain thread-local. Existing external entry forwarders still exist pending the remaining domain composition migration; this is not the complete production application factory.

This repository candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows the reviewed tails candidate. Actual-main rebind and predecessor release acceptance must precede publication. Repository production and the ordered entry match reviewed dd74e3e. The bundled manifest is v180 with 514 unique sources. Fixed history28 and reader19 protocols remain mandatory; earlier performance failures remain retained. This is scoped connection ownership, not a complete production application factory.

`AuthenticationDomain` owns a fresh request identity and the existing authentication service graph. Its HTTP composer receives the same identity/services and still registers middleware/auth/users/admin docs at the application’s original positions. Root composition binds the actual owned repository adapter and output-media policy directly. Auth paths and environment-derived settings are captured at composition; the selected repository factory continues resolving connections/configuration per operation. Authentication routes retain their existing service behavior. The rest of the application still awaits its full factory migration.

This authentication candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows repository candidate 3ac769a. Actual-main rebind and predecessor release acceptance must precede publication. Authentication production/tests and ordered entry match reviewed a1933f3. The bundled manifest is v181 with 515 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Explicit startup captures intentionally narrow private root rebinding; this is not a complete application factory.

RecordServices composes ownership, audit and request-scoped access with the authentication domain identity and explicit current-user/account lookup capabilities. Entry compatibility exports bind the selected domain methods directly; they do not look up private root owner names again. The domain holds no current user or database connection. Remaining application composition is still pending.

This record composition candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows authentication candidate 552944a. Actual-main rebind and predecessor release acceptance must precede publication. Record production/tests and ordered entry match reviewed f5d759e. The bundled manifest is v182 with 516 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Explicit selected methods narrow private root rebinding; no new permission or persistence atomicity is claimed.

Runtime bootstrap path selection lives in runtime/bootstrap_locations.py. RootLocator receives environment, the original entry-file anchor and directory probing explicitly; RuntimeLocations contains only the 30 original derived paths. Construction of path values does no directory creation or migration. The entry retains the original resolution point and exports existing path names while domain composition is migrated.

This bootstrap candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows record candidate bdbe2fa. Actual-main rebind and predecessor release acceptance must precede publication. Bootstrap production/tests and ordered entry match reviewed 4a4733a. The bundled manifest is v183 with 517 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Existing path resolution order and errors remain; no directory creation or complete application factory is introduced.

CostServices owns the existing CostRepository and CostLedger with explicit storage/timestamp capabilities. The entry binds selected repository/detection/pipeline/auto/training owners and captured CostPaths before the original admin route slot. Only the inert PipelineTaskStore import/construction and original pipeline path assignment move earlier to make those dependencies available; its existing suppliers and all business implementations remain unchanged. This removes cost root-name lookups but is not the complete application factory.

This cost composition candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows bootstrap candidate f265821. Actual-main rebind and predecessor release acceptance must precede publication. Cost production/tests and ordered entry match reviewed 73a6a78. The bundled manifest is v184 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Selected source owners and paths are explicit; no atomic ledger snapshot, accounting algorithm change or complete application factory is introduced.

The image worker owner now tracks coordinator admission and every child thread independently of the subprocess registry. Closing this owner rejects new lookups/launches and waits up to the supplied deadline for admitted work, thread-owned database cleanup and final persistence; timeout explicitly returns undrained. Already admitted work may start while closing. Start/prepare failures preserve existing evidence and do not requeue work or retry providers. The maximum active-child concurrency remains unchanged; immediately completed jobs may replenish capacity earlier. Scope cleanup happens on each owning thread, including model resolution inside the job callback. No store or provider callback runs under the lifecycle lock, and joins occur outside that lock. This adds the owner drain capability and wires queue/thread scopes; application shutdown/factory integration and MCP drain remain separate pending work. It does not promise full application shutdown or cancel running image providers.

A successful image-owner drain proves that admitted threads and their cleanup scopes have exited. It does not prove that final persistence succeeded or that every subprocess was reaped; task failures and subprocess evidence remain governed by the execution service.

This image-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows cost candidate 9ffd4a0. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 1a286c0, including retained uncertain-start handles. The bundled manifest is v185 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. This scoped owner drain does not establish whole-application shutdown or final persistence success.

Image coordinator and child starts now retain uncertain-start handles even if `is_alive()` is false, child lists are pruned, or a later coordinator replaces the current handle. A failed start revokes an unentered target, and shutdown must join retained handles before reporting drained. A never-started handle may remain undrained; stored running evidence is preserved and never requeued. Deterministic interrupted-bootstrap tests cover both launch paths and later coordinator replacement.

MCP operations now have a client-owned admission boundary covering the complete tool dispatch, including the existing stdio failure fallback, and warmup cleanup. New operations are rejected before transport or fallback after shutdown begins; same-thread nested work belonging to an already admitted operation can finish. Startup and request serialization share the client lock, independently of the admission condition. The bounded shutdown waits for admitted work, then terminates and reaps owned transports; an expired deadline returns undrained without cancelling a blocked call or inducing fallback. Recoverable close retains terminated processes for later reaping. Existing provider selection, prompts, wire messages and transport-failure fallback behavior are unchanged. The client retains the startup warmup thread and admits it before construction/start. Shutdown drains this reserved startup operation, joins its owned thread, then retires transports. Application shutdown registration and full production factory integration remain pending.

MCP recovery retains both live and already-exited displaced processes by identity. An exited transport skips termination but still participates in final wait and stdin/stdout cleanup; EOF followed by the existing fallback cannot lose this cleanup ownership.

This MCP-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows image-drain candidate f8e5dbc. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 008c167, including exited-transport ownership. The bundled manifest is v186 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. This client drain does not establish whole-application shutdown or business persistence success.

MCP warmup startup retains its enabled check and original callback, thread name and daemon setting, but now starts through its client owner. Duplicate live starts and starts after closing are rejected. Thread construction/start failures release reservations exactly once; a thread that started before a start error remains tracked. Already reserved warmup may finish nested client operations after closing begins; unrelated threads cannot inherit that admission. No join occurs under admission or client locks.

A failed or interrupted warmup `Thread.start()` cannot use `is_alive() == False` as proof that no OS thread exists. A target not yet entered is revoked, but its handle is retained and shutdown reports undrained until joining proves completion. A start that never actually created a thread can therefore remain conservatively undrained; no target or paid fallback is replayed. A deterministic interrupted-bootstrap regression covers the late-start window.

Uncertain warmup handles are also retained across a later warmup start. Replacing the current handle cannot erase a revoked thread that has not yet confirmed startup/completion; shutdown joins every retained handle.

This MCP-warmup candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows MCP-drain candidate 88cf6c3. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed ed5bda6, including all uncertain warmup handles. The bundled manifest is v187 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Warmup cleanup remains bounded and conservative; full application lifecycle acceptance is separate.

YOLO warmup starts now belong to their `YoloWarmup` instance, including pending thread construction and every admitted thread. Each thread enters and releases its repository scope on that same thread. Closing rejects later starts and waits outside lifecycle/status locks; a timeout reports undrained without cancelling inference, changing model selection, or requeuing work. Existing repeated-start behavior and per-model handling remain. Application-wide lifecycle registration and per-app graph construction remain separate pending work. Prompt source manifest v188 retains the same 518 ordered files.

Interrupted or failed warmup starts retain uncertain handles even across later starts. An unentered target is revoked and every retained handle must be joined; a never-started handle remains conservatively undrained. The tests cover delayed native bootstrap, interrupted startup, later thread replacement and same-thread scope exit.

This YOLO-warmup candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows MCP-warmup candidate 16e6733. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 4b1cfa5. The bundled manifest is v188 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Joining owned warmup threads does not prove inference success or complete application shutdown.

TrainingTaskRuntime now owns admission and actual Python thread handles for both training/sample and background-set submission. One shared owner reserves before persistence, preserves save/create/register/start/public ordering, and wraps the selected target in the repository thread scope. close(timeout) closes admission and joins handles independently of mutable public registries. The application shutdown hook is not enabled by this slice.

The training launch capability is valid only on the synchronous submitting thread while its reservation is active; retained or cross-thread calls fail before construction. Future application shutdown must first stop external admission, then drain training callers before closing their MCP/YOLO dependencies. These cross-owner shutdown steps are not enabled in this slice.

This training-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows YOLO-warmup candidate 3325d48. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 89ea498. The bundled manifest is v189 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Native-thread drain does not certify task persistence, remote settlement or whole-application shutdown.

CodexBackgroundThread owns its native threads through a separate TrainingThreadLifecycle. The same lifecycle implementation underlies TrainingTaskRuntime; task locks/registries/tombstones remain only on that derived training-state owner. Factory/target/name evaluation order is preserved, and the selected background target runs inside the injected repository scope. No application shutdown hook is added.

This owner covers only threads launched by CodexBackgroundThread. Direct synchronous generation remains owned by its caller and must be drained through that caller. Extracting TrainingThreadLifecycle preserves method bodies and initialization order, but changes TrainingTaskRuntime method qualnames and MRO; class metadata equivalence is not promised.

This Codex-background drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows training-drain candidate ad431e7. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 9634271. The bundled manifest is v190 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Only owner-started native threads are drained; synchronous callers and remote business settlement remain separate.

TransferProgress owns its periodic reporter threads through an independent TrainingThreadLifecycle and injected repository scope. close stops admission, signals current reporters and any already admitted event construction, then waits for real thread and scope exit. It stops progress reporting only; transfer requests and counters remain owned by their callers. No app shutdown hook is added.

Each reporter requires its own Event from the injected factory, matching production threading.Event. Pending starts and uncertain handles stay owned; an interrupted native bootstrap cannot authorize a late progress update.

This transfer-reporter drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows Codex-background candidate bb5e844. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 5d64dfe. The bundled manifest is v191 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Reporter drain does not cancel transfers or certify task persistence or whole-application shutdown.

Auto-optimization label, shadow-evaluation and delayed-training-check starters each own an independent TrainingThreadLifecycle. Existing task guards, live-thread deduplication and selected targets are retained; pending construction and native handles remain owned until repository-scope exit. Closing rejects new starts before sanitization. This slice does not enable application shutdown hooks or change worker algorithms.

This auto-optimization starter-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows transfer-reporter candidate 7f3f2a7. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 4e88155. The bundled manifest is v192 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Native-thread drain does not certify remote settlement or whole-application shutdown; the executor scope fix remains a separate successor.

runtime/application_foundation.py constructs only three foundational owners from explicit FoundationInputs: RuntimeRepositories, AuthenticationDomain and RecordServices. Each call allocates separate identity, connection factory, auth locks/limiter and record services; callers may supply distinct live environment mappings and connectors. It performs no file creation, DB connection, route registration or worker startup. The entry still constructs one foundation; existing directory creation and routing/startup positions remain. This is a prerequisite, not the complete production application factory.

This application-foundation candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows auto-optimization starter candidate d81faba. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 66697fc. The bundled manifest is v193 with 519 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Three inert foundational owners are distinct; this does not complete the application factory or lifecycle.

Automatic-mask executor tasks now enter the injected repository thread scope inside the executor thread. Thread-local selections are released before their Future finishes. The existing executor context waits for all submitted work, including failures; batch selection, concurrency, algorithm and settlement remain unchanged. This change preserves bare-executor ContextVar behavior and does not copy request identity, model context, read caches or write-authorization contexts.

This automatic-mask pool-scope candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows application-foundation candidate 8dd3e33. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests match reviewed c84e963 and the ordered entry is unchanged. The bundled manifest is v194 with 519 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Repository cleanup is scoped to executor work; model-binding propagation remains a separate successor.

Automatic-mask executor submissions explicitly bind only the already selected model snapshot through model_profiles.snapshots.bind_current. Each submission captures the injected resolver and a private copy of its current snapshot before scheduling, then restores any previous worker model scope on exit. This fixes the bare executor losing the parent binding for downstream training-vision settings. Request identity, mutable read caches and write-authorization contexts are not copied. Missing resolver or bound snapshot fails before executor submission; the existing batch error path retains claimed state without paid retry.

Each pending sample receives a newly bound callback used once by its Future. Reusing that same callback would reuse its captured private snapshot; the helper does not promise a fresh copy per invocation or atomic binding of the whole batch. Mid-batch binding failure does not undo earlier submissions or imply that no provider call occurred.

This automatic-mask model-binding candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows pool-scope candidate 60a094b. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed b86a647. The bundled manifest is v195 with 519 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Only the selected model snapshot is propagated; later binding failure does not undo already submitted work.

DocumentJobs and PreparationJobs each own an independent TrainingThreadLifecycle, with the repository scope injected by composition. A per-acquire JobPermit transfers the existing bounded slot to an outer target wrapper: cancellation returns only an unentered permit, while an entered target retains capacity through business cleanup and repository-scope exit. This intentionally fixes startup/cleanup slot leaks and premature/double release; it is not a pure behavior-equivalent relocation. Direct synchronous run calls are caller-owned and do not acquire or release a job slot. Application shutdown registration remains separate work.

This text-job ownership candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows model-binding candidate 8302940. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 4491be2. The bundled manifest is v196 with 520 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Job permits retain capacity through thread and repository cleanup; direct synchronous calls remain caller-owned.

The initial FastAPI transport shell is built by runtime/http_application.py from an explicit environment mapping. Each construction owns a fresh app, route collection, state and CORS list. Domain registration, authentication middleware placement, artifact runtime ownership and application startup/shutdown still belong to the surrounding composition; this focused factory does not yet provide a complete isolated production create_app.

This HTTP-shell candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows text-job candidate a071786. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 5d1d582. The bundled manifest is v197 with 521 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. A fresh transport shell is not yet a complete isolated production application.

create_http_application accepts an optional typed upload_runtime_provider. Omission retains UploadAdmission’s original default provider and middleware arguments. An explicit provider is selected only for multipart requests in non-local mode, and remains lazy across calls. The shell does not build or close artifact resources. Existing server composition still uses the original default; this capability alone does not provide full application or artifact-store isolation.

This HTTP upload-provider candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows HTTP-shell candidate fa14007. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests match reviewed 6f11bcd and the ordered entry is unchanged. The bundled manifest is v198 with 521 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Explicit provider injection is enabled for later composition; the current entry still uses the default provider.

storage.artifacts.runtime.ArtifactRuntimeProvider owns its lock, initialized runtime and configuration signature. It accepts an environment supplier and optional typed builder without creating files or clients at construction. get_runtime delegates to one default owner and resolves the normal builder at operation time. Validation and the local-mode bypass remain before locking, runtime creation stays serialized, failed construction is not cached and an initialized non-local configuration change still requires restart. Independent owners can initialize without sharing a lock or cache. This is not a new full artifact resource lifecycle or a production-wide per-app storage switch.

This artifact-runtime ownership candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows HTTP upload-provider candidate 4ab91fe. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests match reviewed 4c2b19e and the ordered entry is unchanged. The bundled manifest is v199 with 521 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Owners isolate selector locks and caches, not underlying paths or resources; the default entry owner remains process-scoped.

Frozen HTTP constructor evidence is pinned to canonical Git LF bytes with an explicit checkout attribute. The raw SHA guard still rejects any changed fixture; this fixes platform-dependent test acceptance without changing application behavior or historical task snapshots.

Frozen artifact-runtime evidence is checked out as canonical Git LF bytes. The original raw SHA and immutable fixture Git blob remain unchanged; a CRLF working-copy mismatch is a test portability failure, not a runtime regression.

Pipeline advance, auto-Agent and recommendation schedulers now retain admitted preparation and native threads through a per-runtime lifecycle. Same-thread repository scopes surround the already selected pinned-model runner. close rejects new schedules and waits for scope exit; timeouts do not cancel tasks, rewrite evidence or retry providers. Registry and cancellation behavior stays with each existing scheduling capability. Auto-Agent can schedule advances, so application shutdown must drain parents before their dependencies; the final coordinated hook remains pending.

Closing a pipeline owner rejects even empty or duplicate new scheduling calls before registry effects. Already admitted whole batches may finish preparation after close begins. A successful close denotes thread completion, not successful persistence or repository cleanup; scope-entry and construction failures may retain inflight evidence. Coordinated shutdown must drain auto-Agent before advance because admitted parent work can still schedule advances.

Extraction registration accepts its own TrainingThreadLifecycle. After the existing authorization, upload read and normalization, the synchronous prepared-input path reserves admission before new source writes or task claims, preserving its original settings/fingerprint/deduplication order. The selected extraction worker enters the injected repository scope on its native thread. Existing resolver return values and route order remain unchanged; composition retains the owner explicitly for later application shutdown integration.

Prepared local and Qwen comparison cleanup now returns an acquired semaphore slot even when final persistence, timer cancellation or repository clearing raises. Nested finally blocks guarantee each later cleanup step is attempted; they do not retry persistence, alter a model result or clear an attempting record. This fixes an existing capacity leak. If settlement and cleanup both raise, the later cleanup exception is primary and the earlier exception remains its Python context; single-fault exception identity is preserved.

Prepared comparisons now receive a ComparisonRuntime owning native comparison threads, deadline timers and separate local/Qwen single-slot capacities. A per-target ComparisonSlot acquires at the original business position and returns capacity only after the outer repository scope exits, including failure. DeadlineTimers tracks pending starts and actual callback completion; cancellation is not completion. Parent drain must succeed before deadline admission closes, so active comparisons retain timeout protection. Composition injects repository scope and retains the owner; application shutdown wiring remains separate work.

Each PDF import registration owns a PdfImportRuntime, exposed at app.state.label_pdf_import. Its admitted starter creates at most one consumer, including concurrent or repeated startup. The existing loop, claim token, per-iteration repository cleanup and two-second idle/recovery wait are unchanged. close(timeout) requests stop and joins admitted construction and actual thread completion; a stop request alone is not completion. The existing shutdown hook still requests stop only; coordinated application draining is separate work.

This offline lifecycle integration retains native-history/readiness and detection composition from actual main dcb4805 and follows artifact-owner candidate 6b648b5. Owned production/tests and ordered entry match reviewed 28de9fa; both canonical fixture corrections are already retained. The bundled manifest is v204 with 523 unique sources; earlier paragraph counts refer to their original individual candidates. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Publication must use independently reviewed domain-scoped PRs on accepted main, with full hosted and release gates; this offline combined tree is not a blanket grouped publication approval or complete application factory.

Web composition now registers a single ordered shutdown owner after domain registration. It preserves the two existing PDF-stop and label/control-stop hooks in their original order, then joins PDF, pipeline producers, auto-optimization producers, training/background/image owners, text owners, transfer reporters, YOLO warmup and finally MCP. Only explicit True acknowledges a drained native owner; a failed producer stops traversal before downstream dependencies are closed. Successful prefix steps are retained across explicit subsequent drain attempts. This changes shutdown composition only; the full independent application factory and artifact graph remain pending.

Shutdown permanently closes these resource owners. The same production app instance must not be started again after teardown; process restart or a separately constructed resource graph is required. Two independently allocated HTTP shells are tested, not repeated startup of the same production graph. The native fan-out test executes actual pipeline auto-agent run and advance schedule/run methods with synthetic business ports, using the production shutdown binding order.

This offline shutdown replay follows lifecycle candidate 7d7886a and preserves current native history, readiness, model/tail and canonical LF fixes. Four owned runtime/test/contract blobs match reviewed 82313c5. Manifest v205 lists 524 sources. The 480-second shutdown allowance remains cooperative and requires ASGI request quiescence; complete independent application composition is still pending. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

ImageUpload requires a narrow lazy UploadFiles supplier; DetectionAnnotation and DetectionAnalysis require an explicit runtime supplier. The entry binds these three services to its business-file selection. Other detection helpers and the complete application resource graph still use their existing compositions; this slice does not claim full per-app isolation. Shared image_backend retains call-time default runtime selection for existing callers.

This offline detection artifact replay follows shutdown candidate 8618f7a and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 713010a. Manifest v206 lists 524 sources. Storage suppliers retain call-time selection; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Detection media no longer constructs its own BusinessFiles or calls image_backend without an explicit runtime. ImageEncoding and InspectionImageStore resolve their supplied runtime at operation time; ReferenceSheet resolves a narrow files supplier for each existing file operation. LocalModels and VideoUpload capture an explicitly supplied files object at construction. The entry supplies its business files; replacing that entry variable later changes the lazy suppliers, but not the two captured objects. This completes explicit storage wiring within detection, not the entire application factory.

This offline detection media replay follows artifact candidate e7e12b2 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 5e86530. Manifest v207 lists 524 sources. Explicit stores retain original cache, error and video cleanup behavior; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

HTTP media composition explicitly supplies files to incoming-text asset/evidence responses and training background queries, and supplies runtime selection to upload admission and the output mount. The response helper distinguishes omitted files (legacy default) from an invalid explicit None (failure). Incoming catalog/review business-path lookups still own their earlier storage dependencies; response injection alone does not complete their storage graph or the whole application factory. Background lookup intentionally reselects its files for existence and response operations, retaining their original order.

This offline HTTP artifact replay follows detection media candidate f2b4519 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 301b6c1. Manifest v208 lists 524 sources. Explicit missing file dependencies fail closed while genuinely omitted legacy arguments retain their documented default. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Legacy incoming catalog, inspection execution, reviews and retention require explicit narrow file/image capabilities. Composition supplies one captured BusinessFiles object and matching ImageFiles to those four services; business modules no longer create default artifact adapters. Request identity and repository factories remain operation-time capabilities. This is a focused resource boundary, not the complete application factory.

This offline incoming workflow replay follows HTTP artifact candidate 2336193 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 8e4d991. Manifest v209 lists 524 sources. Consistent captured files/images dependencies retain original partial-write, exception and retention semantics. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Training background manifest, file listing, seeding, identifier allocation, library lookup, upload and environment capture require explicit file capabilities from training/background_file_ports.py. The seven services capture their supplied adapter; production assembly supplies its existing BusinessFiles. Image rendering/validation/variant adapters and task state retain their separate composition; this slice does not claim a fully isolated training pipeline.

The initial background-file candidate failed independent manifest-path validation before publication. Its path was corrected without changing business code, and the existing actual-source fingerprint contract is required in the local acceptance matrix.

This offline background file replay follows incoming candidate 841c4ba and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed c80ed68. Manifest v210 lists 525 sources, with the corrected service-relative background capability path. Captured file capabilities retain original ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

TrainingBackgroundRenderer, BackgroundValidation and BackgroundVariants now require narrow image capabilities. Production assembly constructs one ImageFiles against the same captured BusinessFiles used by background metadata/upload services. Non-file OpenCV operations remain in their original modules. These three image services and the seven previously migrated background file services no longer construct default adapters. At the preceding image-only slice, background Codex generation and its task runner still used default BusinessFiles; their subsequent migration is described below. Unrelated dataset/preview services and complete application construction remain separate.

CodexBackgroundGeneration and BackgroundTaskRunner require explicit file capabilities. The generation runner still selects one runtime for its remote branch before calling the unchanged native generation workflow; task execution retains its existing model-snapshot decorator and file-existence check position. Root supplies the same captured BusinessFiles as background file/image services. This closes their two remaining default-adapter sites, not the full application resource graph.

This offline background image replay follows file candidate 89875c1 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 09ef623. Manifest v211 lists 525 sources. Three image services use explicit adapters; generator and runner defaults remain outside this slice. Original algorithms and golden contracts remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

This offline background generation replay follows image candidate 9a2d333 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 22986e9. Manifest v212 lists 525 sources. Generator and task runner now receive captured file adapters, retaining model snapshots, subprocess policy, partial outputs and exception behavior. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

TrainingDatasetInput, DatasetGenerator, TrainingPreviewCache, PreviewArtifactStore and TrainingPreviewApproval require explicit narrow file capabilities from training/file_ports.py. Production composition supplies its existing captured BusinessFiles. Their lookup, permission, serialization, error and partial-publication ordering stays unchanged. Rendering, dataset archives, resource mutations and other callers retain separate composition; this is not a complete application factory.

This offline training file replay follows generation candidate 2fdb9ee and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 214fe9c. Manifest v213 lists 526 sources, appending training/file_ports.py. Five services capture matching file capabilities while preserving validation, cache, write ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Training preview rendering and annotation image I/O require explicit image capabilities; dataset YAML writing requires its file writer. Production composition binds both image services to one ImageFiles over its captured BusinessFiles and preserves the public entry YAML helper signature through a composition forwarder. Layout, pixel calculations and codecs are unchanged. Other training file services and full application construction remain separate.

This offline training image replay follows file candidate 94c1eec and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 75d63a9. Manifest v214 lists 526 sources. Image adapters are captured and YAML selects its writer per call; arbitrary private rebinding is not preserved as an atomic hot swap. Algorithms, goldens and public signatures remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

TrainingResourceMutations and TaskBackgroundStore require explicit file capabilities, DatasetArchives requires an explicit runtime supplier, and its strict file digest requires a materialization capability. Production composition supplies the existing files/runtime and preserves the entry digest signature. Authorization, archive contents, lease scope, mutation order and partial-completion behavior remain unchanged; archive/runtime callbacks are not an atomic resource snapshot.

This offline training resource replay follows image candidate 9063ace and preserves current history, readiness, model/tail, shutdown, corrected boundary documentation and canonical LF guards. Production and test blobs match reviewed fbf5434. At this replay boundary manifest v215 selects 526 sources. Explicit resource and archive capabilities preserve file operation ordering, strict digest failures, partial publication and archive formats. Current source changes require actual-main rebind, independent review and full CI/release acceptance before publication.

Accessory creation uploads, image-job provenance and sprite metadata existence checks now require narrow file capabilities. Root binds its captured BusinessFiles to AccessoryCreation, the provenance ImageJobMetadata instance and SpriteRenderMetadata. The injected model resolver, hashing callback and image decoder retain their prior independent contracts; this change does not isolate the entire accessory workflow.

This offline accessory file replay follows training resource candidate 7ae44bf and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed eccc553, including ordered constructor bindings. At this replay boundary manifest v216 selects 526 sources. Upload ordering, partial publication, provenance collisions and sprite fallbacks remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

BackgroundPlateDerivation, BackgroundReferenceSignatures, BackgroundCandidateCatalog, BackgroundLibraryMatcher, ReferenceEvidence and PreviewAssetLoader now receive narrow file/image capabilities. Root supplies its existing BusinessFiles and a matching captured ImageFiles. Existence checks, raw-byte hashing, decode order, source selection and matching calculations retain their existing boundaries; other accessory image workflows still require separate composition.

This offline accessory evidence replay follows file candidate b368404 and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed 466195b. At this replay boundary manifest v217 selects 526 sources. Decode and hashing selection, source mutation, partial publication and error propagation remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

SpriteAssetCatalog and TextAssetCatalog require captured file and image ports; load_clean_sprite requires an image reader selected by its existing entry wrapper. Metadata mutation, dimension setdefault semantics, alpha thresholds and pixel-copy rules remain unchanged. Other accessory image workflows and complete application factory wiring remain pending.

This offline accessory catalog replay follows evidence candidate 2d442b2. All owned production/test blobs and the complete ordered entry match reviewed 87ebec1; current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v218 selects 526 sources. Existing catalog mutation and decoder behavior are unchanged. Exact-source neighbor evidence is reused; current targeted, assembled HTTP and fingerprint checks are distinct. Actual-main rebind and independent full CI/release acceptance remain required.

CandidateFactory requires an image reader and AccessoryGallery requires file/image capabilities. The existing root image adapter is allocated before candidate composition and shared with the later accessory services. Candidate preparation/save order and gallery read-time publication, alpha composition and error behavior are preserved.

This offline accessory gallery replay follows catalog candidate 8f453b3. Owned source/test blobs and ordered entry match reviewed 7f02e9d, including the single inert ImageFiles allocation relocation. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v219 selects 526 sources. Existing partial publication and failed-write behavior are unchanged. Neighbor evidence is reused only for exact source; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

AccessoryFiles receives narrow upload/existence/unlink and image IO capabilities. Its four existing edit workflows retain permission, validation, metadata mutation, profile refresh and save ordering. The root supplies matching file/image owners; no new retry or compensation is introduced.

This offline accessory edit replay follows gallery candidate 1b5c003. Owned source/test blobs and ordered entry match reviewed 6f78019. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v220 selects 526 sources. Authorization order, crop geometry, partial publication and deletion failure behavior remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

ObjectSpritePreprocessor receives required existence and image-read ports from accessory composition. Pose discovery, cached-sprite rebuild, source fallback, cutout/provider policy, metadata and partial publication order remain unchanged. Artifact writing remains the existing explicit callback; independently supplied ports are not an atomic storage graph.

This offline accessory preprocessing replay follows edit candidate 96c7b23. Owned source/test blobs and ordered entry match reviewed dbcd8b5. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v221 selects 526 sources. Discovery, decode, publication, status and exception ordering remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

AgentPoseAssets, PhotoHighlightSources and PoseRenderContent require narrow file readers. PoseExecutionWorkflows binds its supplied storage owner to the photo and render readers; the remaining AgentPoseAssets constructor receives that same explicit file capability at the entry. Source filtering, source metadata mutation, encoded evidence construction and prompt text remain unchanged. The source-position contract validates the actual composed owners before strictly replaying the reviewed Pose and path deltas; all original required-reader and isolation assertions remain.

`build_infrastructure` in `runtime/infrastructure.py` constructs fresh foundational repository/auth/record owners, the path/configuration cycle, provider/profile configuration and three read caches. It allocates artifact services unless an already allocated artifact composition is explicitly supplied. The default entry uses this same builder and preserves its earlier artifact owner needed for root discovery. Path identity and configuration/profile repository suppliers select that foundation at operation time; local-model configuration and JSON caches select that artifact owner. Construction performs no IO, model resolution, route registration or worker start. Its typed return belongs only to the application assembler, which distributes narrow dependencies. Existing mkdir, HTTP registration, startup and shutdown positions and bound directory/migration aliases remain. Remaining domain registration and complete application lifecycle composition are separate acceptance gates. Explicit external environments and paths can intentionally be shared and are not automatically isolated by owner allocation. New tasks use manifest v272/586 with both actual construction modules; historical fingerprints remain unchanged.

This offline Agent reference replay follows accessory preprocessing candidate b1d835d. Owned source/test blobs and ordered entry match reviewed efa17b7. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v222 selects 527 sources. Reference selection, digest acceptance, path mutation and exception ordering are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

PoseArtifactStore and PoseAssetMaterialization require explicit file capabilities. Root supplies its existing owner. Image-before-digest-before-metadata publication, local/remote text-write selection and incremental materialization remain unchanged; image bytes and metadata are not an atomic pair.

This offline Agent pose storage replay follows reference candidate 9a90408. Owned source/test blobs and ordered entry match reviewed 11919d9. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v223 selects 527 sources. Image and metadata publication ordering, local/remote callback timing and partial mutations remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

PhotoHighlightSpriteBuilder requires byte-publication and image IO ports. Root supplies matching file and image owners. Source evidence, provider attempt policy, mask processing, diagnostics, artifact publication and metadata order are unchanged; callbacks still have independent ownership.

This offline Agent photo replay follows pose storage candidate a56b846. Owned source/test blobs and ordered entry match reviewed 6afd82e. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v224 selects 527 sources. Provider attempts, diagnostic failure handling, publication and item mutation order are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

PipelineBackgroundPublication requires explicit file and PIL image ports, supplied by matching root owners. Existing library reuse, eager configuration/reference selection, provider error handling, fallback, set replacement and manifest/task publication order are preserved. This boundary does not make all callbacks or the whole application independently owned.

This offline Agent background replay follows photo candidate 5bcd15e. Owned source/test blobs and ordered entry match reviewed e8c63a3. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v225 selects 527 sources. Existing library fallback, partial file and manifest publication, callback timing and errors remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

PipelineResourceStatus requires a captured file-existence port. Composition supplies the existing business-file owner; dataset/model matching, first-match order, deleted and pending states, and AI-task lookup precedence remain unchanged.

This offline pipeline availability replay follows Agent background candidate 37a1265. Owned source/test blobs and ordered entry match reviewed ed60859. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v226 selects 527 sources. First-match, pending-state, bypass and storage error behavior are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Text extraction registration and StandardEdits receive explicit cleanup-file capabilities. Root supplies the matching business-file owner; expiration selection, immutable tombstone competition, losing-revision cleanup and failed-standard-edit cleanup order remain unchanged. Other record/media callbacks retain their own boundaries.

This offline text cleanup replay follows pipeline availability candidate 6f13fd9. Owned source/test blobs and ordered entry match reviewed c89fbbd. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v227 selects 528 sources. Cleanup exception precedence, tombstone-before-deletion and partial effects remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

DatasetCatalog, TrainingResources and TrainedModelCatalog require explicit narrow file adapters supplied by the composition owner. Existing local and indexed algorithms, catalog ordering, audit timestamps, task settlement and permission filters are unchanged. Record and projection callbacks are still independently supplied.

This offline training catalog replay follows text cleanup candidate 1199028. Owned source/test blobs and ordered entry match reviewed 8f0715d. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v228 selects 528 sources. Local and indexed selection, permission ordering and repeated reads remain unchanged. Exact-source neighbor evidence is reused; current targeted, real PostgreSQL, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

TextMedia now requires an explicit artifact-runtime provider from its composition owner. Local atomic replacement, remote generation checks, owner/path checks and lazy PDF publication retain their existing algorithms and order.

This offline text media replay follows training catalog candidate 920904d. Owned source/test blobs and ordered entry match reviewed f71e6c4. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v229 selects 528 sources. Local path, hybrid readiness, size, digest and publication rules remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

TrainingRunner requires file existence and runtime selection capabilities from its composition owner. Model binding still precedes the separate task load; executor mode, dataset lookup, work-budget reservation and execution callbacks retain their existing order.

This offline training runner replay follows text media candidate da44932. Owned source/test blobs and ordered entry match reviewed 9b024f4. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v230 selects 528 sources. Running-state persistence, runtime mode, repeated existence reads, failure settlement and pinned model restoration remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

RunPodExports and RunPodArtifacts require explicit artifact-runtime providers. Dataset/token metadata, checksum validation, ZIP selection and ordered artifact publication retain their existing local/COS behavior.

This offline RunPod artifact replay follows training runner candidate b7b8760. Owned source/test blobs and ordered entry match reviewed 671f233. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v231 selects 528 sources. Repeated runtime selection, cleanup exception masking, publication ordering and local replacement remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

RunPodFlow, RunPodTrainingTransfer and RunPodUploadStore require explicit artifact-runtime providers. Durable submission claims, token/path validation, bounded upload and the existing polling loop remain unchanged.

This offline RunPod transport replay follows artifact candidate 97a9963. Owned source/test blobs and ordered entry match reviewed 12f1743. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v232 selects 528 sources. Durable claim ordering, ambiguous submit retention, streaming limits and partial upload publication remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Codex HTTP registration requires an explicit artifact-runtime provider from the composition owner. Request context creates its MediaStore with that provider; permission, owner and repository checks retain their order. During the preceding Codex HTTP-only slice, label and CLI MediaStore callers retained their previous ownership.

Label HTTP, PDF-import registration, LabelWorker and LabelProcess require explicit artifact-runtime providers. The Web root supplies its file owner; standalone bootstrap passes its own process entry provider after the existing storage startup validation. Neither domain imports the Web app.

This offline Codex HTTP replay follows transport candidate 0beaefc. Owned source/test blobs and ordered entry match reviewed 42fcded. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v233 selects 528 sources. Authorization, media exception mapping and partial publication ordering remain unchanged. Exact-source neighbor evidence is reused; current targeted, isolated PostgreSQL, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

This offline label media replay follows Codex HTTP candidate 41743d5. The original provider-only delta from reviewed b696cba is applied while retaining current native history summaries and their test adapters. All other owned source/test blobs and ordered entry match the reviewed source. At this replay boundary manifest v234 selects 528 sources. Current history, readiness, model/tail, shutdown and canonical LF guards remain. Worker claims, PDF cleanup, provider identity and error ordering remain unchanged. Current isolated PostgreSQL and affected integration checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

Shared comparison MediaStore requires an explicit artifact-runtime provider. All Web, PDF, label worker and Codex CLI constructions supply it. Codex execution selects its work budget through the supplied media owner, while CLI startup retains its existing process storage validation.

This offline comparison media replay follows current-history label candidate f447c5d. Owned source/test blobs match reviewed 552cea1; the entry remains unchanged. Current native history and its explicit-provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v235 selects 528 sources. Worker budget and reservation settlement ordering, ambiguous paid outcomes and CLI selection remain unchanged. Current isolated PostgreSQL and affected integration checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

The Web entry constructs ArtifactComposition, a narrow storage graph containing one lazy ArtifactRuntimeProvider and its BusinessFiles/ImageFiles views. It does not use the process-default runtime cache for those views. Each separately constructed graph owns its configuration signature and lock; this is not yet a complete application factory.

This offline Web artifact composition replay follows comparison candidate d2ae509. Owned source/test blobs and ordered entry match reviewed a0fa2ed, including the Python 3.10 structural source guard. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v236 selects 529 sources. The Web graph owns a fresh lazy runtime provider and two focused views; this is not a complete application factory or proof of independent underlying resources. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

Stream configuration saving is owned by config/stream.py through explicit load/save capabilities. The application entry retains the existing route and delegates to this service; load, payload-field evaluation, mutation, save and response order are preserved.

This offline stream configuration replay follows Web artifact candidate f2e481b. Owned source/test blobs and ordered entry match reviewed 14f6504. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v237 selects 530 sources. Existing load, mutation, save and post-save response ordering remain unchanged; configuration is not given a new transaction or lock. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

IncomingTextStore now resolves JSON single-record lookups through its own list methods. The two callbacks through the application entry have been removed; narrow repository, guard, path and row-adapter inputs remain. Tests replace the owning store method and cover two independent stores, preserving missing-loader errors, call-time repository selection and lock behavior. TextStorage allocates both text stores and their shared write lock per composition, without opening a connection or retaining a user. Manifest v238 selects 531 source paths, including text_inspection/storage_composition.py. This closes the store self-reference only; full application factory and route/lifecycle instance isolation remain unfinished.

The text storage lock belongs to `TextStorage` and its public lock property cannot be rebound. The entry lock alias initially references it; replacing that private entry alias no longer replaces either store guard. Remaining route/write adapters still use their existing inputs until their domain composition is migrated. This intentional narrowing of private test seams does not change configured runtime behavior.

IncomingWorkflows now builds the incoming-text catalog, reviews, capture execution and retention graph around one explicit TextStorage owner. The graph supplies the same files/images adapters and storage lock to its relevant services. Duplicate capture lookup is shared by reviews and admission without a construction cycle. Account and repository suppliers remain operation-time ports. Complete application assembly and lifecycle isolation remain separate work.

The incoming domain owns its response-file capability and exposes separate catalog and inspection route registration methods. Application composition calls them at their original positions, preserving the intervening Beta comparison routes and the existing media authorization/error behavior. The actual domain-builder HTTP tests exercise these methods; this does not claim a completed whole-application factory.

Replacing the default entry business-file alias no longer redirects this incoming domain. Its response capability is selected on the owner after authorization; changing that capability does not atomically replace the separate file adapters already held by catalog/execution/retention. No whole-graph hot-swap guarantee is introduced.


Training catalog composition is owned by training/catalog_composition.py. One inert ModelCatalog creates the task lookup, trained catalog, pipeline lookup/linkage, model selection and local cache owners. Internal query edges resolve the graph's actual services at operation time instead of calling application-entry aliases. Permissions and repository selection remain per invocation; catalog queries do not gain task write capabilities. Different graph instances have distinct model caches. This domain graph is not yet a complete application factory.

Candidate image work now composes under accessories/image_composition.ImageJobs: one candidate lock, metadata, candidate repository, diagnostics, queue, execution service and native worker process/child registry belong to that graph. Internal queue/execution/diagnostic edges select that owner at operation time. External artifact, configuration, preprocessing and provider capabilities remain focused suppliers. Construction does not select a request identity, repository, model or native thread; all internal targets exist before worker admission. The entry retains existing public forwarders and route/lifecycle registration. This domain graph does not complete the full application factory or move training/image work into separate processes.

ImageJobs internal operation suppliers select the domain owner directly. Existing root private lock/process aliases are views of that owner in the default application; rebinding an alias does not redirect the owned graph. Remaining legacy consumers still use their existing root suppliers until their domain composition is migrated. This is an explicit private replacement boundary, not a complete application-factory guarantee.

The model-tool domain graph is owned by `model_providers/tool_composition.py`: one ModelTools owns the LocalAiMcpClient, dispatch service, PresenceInspection and the four-key semantic tool map. The client is constructed before handlers; lazy internal edges are complete before the constructor returns. The entry retains aliases and explicit accessory/provider/configuration suppliers. Internal provider-error, presence-dispatch and client/handler edges resolve this owner, so rebinding old private root aliases or wrappers no longer redirects them. External accessory wrappers remain captured as before. This is a domain graph, not two complete application factories.

Presence selects the owned call wrapper before its argument effects, then that wrapper selects the dispatch method after arguments are ready, preserving the preceding two-step callback-selection order. The wrapper references only its owner, not application-entry globals.

Owned MCP fallback retains admission, payload preparation, selected stdio invocation, late selected client close, then the existing single in-process handler sequence; close failure prevents fallback.

DetectionWorkflows in detection/workflow_composition.py composes the analysis repository/publication, capture, ordinary detection and AI analysis services as one inert graph. Publication invokes its own capture, AI evidence invokes its own publisher, promoted-model recursion uses its own ordinary analysis, and teacher fallback uses its own pinned AI wrapper. Public entry adapters retain their existing signatures and model decorator. Construction never selects an identity, connection or model; the original external suppliers remain lazy. Capture lock, state storage and background launchers are supplied by the existing auto-optimization runtime, so this graph is not a new independent auto-optimization runtime or a complete application factory. Internal operations no longer follow arbitrary replacements of root private aliases.

Text standards compose through text_inspection/standard_composition.TextStandardWorkflows. The inert domain owner holds the supplied TextRecordStore, media, revisions, standard imports/library/edits, document classification and preparation jobs. Internal storage/media/revision callbacks select that owner at operation time; each native job service has its own scoped lifecycle. Three registration methods remain at their original entry positions, preserving intervening routes. This does not complete application assembly or remove the remaining comparison/extraction/history dependencies.

TextComparisonWorkflows in text_inspection/comparison_composition.py composes comparison submission, reviews, history, extraction admission and prepared comparison lifecycles around the actual text standard owner. Record/media/preparation edges select that owner; the entry retains explicit compatibility forwarders. History, extraction and inspection registration stay at their original positions. The extraction resolver has one typed field completed by extraction registration before inspection admission; an unassembled resolver fails explicitly. Remaining Codex/label interfaces and other application domains still need final assembly.

AutoOptimizationCore in training/core_composition.py composes state storage, recommendations, readiness, status and shadow evaluation around the supplied settings and shared auto-optimization runtime. Internal record, recursive status/readiness and promotion callbacks select this owner at operation time. Shadow analysis selects the explicit DetectionWorkflows owner after argument evaluation, without importing the Web entry. The root keeps compatibility aliases and the original bounded shadow shutdown step. Generation, dataset, training scheduling, HTTP and pipeline collaborators still require their own final composition; this is not a complete application factory.

The owned shadow native target preserves the original pinned model-profile entry through an explicit resolver provider captured at composition. Task loading and one model scope run after native repository-scope entry, using the actual core store; the public compatibility worker keeps its original single decorated call. Tests cover retained task version after configuration changes, empty and inherited snapshots, missing resolver before task I/O, exceptional restoration and one scope without retry.

AutoOptimizationExecution in training/execution_composition.py composes initialization, mask prompts/visuals/verification, sprite publication, label generation/processing, scheduling, sprites/rendering, synthetic batches, dataset and requests. Its narrow external groups retain their original lazy selection; internal calls select the actual component after argument evaluation. Core, settings, shared runtime and separate label/check lifecycles are explicitly supplied. Native label/check entrypoints pin the supplied model resolver and actual task store once after repository scope entry; the public compatibility decorators remain unchanged. No model, prompt, task-state or process topology change is included. Core status selects the same workflow owner for label-start and sprite-pool callbacks. Route/lifecycle assembly and a complete application factory remain pending.

AutoOptimizationWorkflows in training/workflow_composition.py composes the existing Core and Execution owners with the same explicit settings/shared runtime and three separate native lifecycle owners. The two status-to-execution edges select named workflow forwarders; those select execution after argument evaluation. It constructs both inert graphs at the former Core position, with all eager dependencies already defined and the External port imports explicitly moved before their first use. No generic registry, delayed binding slot, new process, algorithm or API change is introduced. Original aliases, public worker decorators, route order and close order remain. This closes only the automatic-optimization graph; capture, pipeline collaborators and complete application assembly still require explicit final integration.

TrainingStateWorkflows in training/state_composition.py composes the existing TrainingRecordStore, TrainingTaskLifecycle and TrainingTaskViews around the supplied TrainingTaskRuntime. Records and lifecycle select the same existing RLock; lifecycle record operations and view load/refresh operations select named methods on this owner after argument evaluation. Repository factories and the two-layer model resolver remain operation-time suppliers; no user, connection or current snapshot is captured. Model freeze precedes invalidation and locking. Visibility still precedes refresh, and retired worker records remain read-only. Authorization, dual canonical/alias tombstones and partial deletion failures retain the original behavior. The entry keeps its public signatures and original component aliases. Replacing those private aliases no longer redirects owned edges; tests replace actual owner capabilities. This composes only training state, not datasets, training execution, submission, pipeline or the complete application factory.

TrainingAccountState in training/account_state_composition.py combines TrainingStateWorkflows and TrainingUserState around one supplied runtime, with operation-time repository/model/identity suppliers and explicit configuration load/save and pipeline synchronization. TrainingExecution in training/native_execution_composition.py owns the original Runner and Submission with the same account records/runtime; the existing Runner model pin remains single. TrainingTaskWorkflows in training/task_composition.py owns jobs, mutations, launch, status, dataset, preview and RunPod transfer services and validates shared account/execution identity. Internal calls use named owners; five HTTP registrars stay at their original positions. The runtime remains shared with background submission, with its original shutdown owner. Launch configuration failure preserves the already-started task; upload metadata failure preserves the published artifact; a failed completion sync retains the original failed-task update and second sync attempt without repeating generation. Neighboring assets, catalogs, background workflows and pipeline services remain explicit collaborators. This is training-task domain composition, not a complete application factory.

ModelConfiguration owns one actual model-profile service, its snapshot scope,
settings projections and HTTP registrar. Construction obtains no repository,
identity or secret. AI/image settings resolve through that owner; agent settings
still resolve first, then merge current defaults and derive enabled from configured.
Default server compatibility exports retain the existing API, while JSON fixtures
replace the explicit owner service. Missing resolution fails explicitly. Source
manifest v251 includes the actual new composition source for new task fingerprints;
historical snapshots are unchanged. This domain owner is a prerequisite for full
application composition, not proof that the complete application factory is finished.

The default `model_profile_service` compatibility name refers to its initially
constructed service; assigning that module alias no longer redirects resolution.
Tests replace `ModelConfiguration.service` explicitly. Independent factories must
supply their own repository and secret capabilities, environment mappings and
legacy-label settings supplier. The default composition retains its existing
process environment, secret store and label feature settings; this change does
not claim those default resources are isolated across complete applications.

ProviderConfiguration in model_providers/configuration_composition.py composes the twelve existing defaults, validation, URL, key identity, secret store, key registry, proxy, local-model and legacy JSON/image/agent configuration services. Internal callbacks select named owner methods at operation time; the default entry supplies external environment, paths, codecs and policy values explicitly. The profile owner uses that same provider configuration for secrets, validation and legacy migration. Construction performs no reads, migration or worker start; profile route registration stays at its original position. Compatibility method names forward to the owned domain, and tests replace its actual capabilities. This closes the configuration graph, not the remaining application-domain assembly or complete application lifecycle.

The model-profile engines route receives an explicit Codex-model supplier. The
default composition reads the existing process environment at request time;
independent registrars can supply separate environments without importing a
process-global environment from the HTTP module. Empty and whitespace values
retain the original truthiness behavior, and the administrator check remains
first. This does not establish independent construction of the full Web app.

The consolidated offline integration now starts from accepted main e1cfee3
(real-photo feedback and independent review worker). DetectionWorkflows receives
narrow analysis/capture feedback callbacks; both original capture gates and
provenance scopes remain. Compatibility aliases select the composed owners.
The real-photo routes, purpose bindings, incremental tables and review worker
remain present. Manifest v253 contains 557 actual sources at this checkpoint;
historical task snapshots are not rewritten. Full factory, combined CI and
release acceptance are separate remaining gates.

Beta list reads compact only label entries that are flat objects with string, boolean or null values, replacing each safe value-object with an empty object while retaining every label key. Numeric, nested and non-object entries and all unknown top-level fields stay intact. The original Python public projection still computes every list field; no tagged SQL row bypass remains. This avoids transferring safe unused evidence without hiding integer/depth decoding errors. Detail reads keep the complete persisted payload.

Beta list reads return an internal BetaHistoryRead containing the decoded compacted payload plus nullable reference/label counts from the same owner-bound SELECT. SQL counts only object keys and array elements. The HTTP projection still evaluates original fields in original order; missing/null/scalar or encoded JSON uses the original len fallback. This type is not persisted and detail reads are unchanged.


Beta summary consumer is integrated into the final read batch on business composition 2b6e9ce; manifest v251 selects 547 actual sources. This is list SQL compaction, not complete legacy SQL aggregation or release acceptance.

Historical baseline-only prerequisite: manual history read optimization was not active in that commit. Its original helper is frozen independently for tests: the baseline endpoint receives a separately loaded module containing the complete original rows/resolve implementation, so later candidate helper changes cannot silently change the oracle. Production grouping, detail materialization and database reads are unchanged.

The manual-history benchmark measures the complete first-page endpoint with original fixed snapshots against separately frozen tasks and manual-helper sources. That protocol-only prerequisite did not alter production grouping or activate an index. Its performance claim is limited to synthetic manual populations; existing reader/history/Beta protocols remain independent requirements.

Manual history list projection now opts into request-local indexes for multiple groups with proven ordinary decoded rows. Original key discovery/set iteration and full row projection stay unchanged. Session IDs map to every selected group even when duplicate IDs make the separate discovery map last-wins; each page is appended once to both matching-session groups and its fallback group in original page-before-record order. Unsupported references, timestamps or assets use the original scans and error behavior. Default rows/resolve detail calls keep the original path. This is an intermediate in-memory read optimization, not SQL aggregation.

The indexed path still scales with actual memberships: many duplicate session IDs can attach each page to many groups. It does not promise globally linear output size or universal memory bounds; homogeneous performance cases are complemented by explicit overlap/fallback tests.

The manual-history index retains equal-ordinal assets in their input order. PostgreSQL fixtures derive that order from the actual cached repository source; separate synthetic fixtures verify both forward and reversed ties. This test hardening changes no production, sorting or benchmark policy.


The initial read-batch integration at v252 combined the guarded manual index and Beta SQL consumer on business composition 2b6e9ce. The current guarded legacy cohort is described below; independent application construction remains unfinished.

## Guarded legacy list projections

The final read batch combines request-local manual indexing, Beta SQL compaction/counts and a derived legacy label/manual cohort. `storage/legacy_list_projection.py` verifies complete original token streams (including discarded duplicate-key values), decoded shapes, numeric/depth bounds and the original projections before publication. Unknown shapes, decoder-incompatible tokens, negative zero, time-dependent label status, conflicting latest manual decisions and native legacy extensions retain the original raw reader. Previously cached sources are never replaced by a newer observation. Detail reads remain complete.

The additive `2026_10_08_legacy_list_projection.sql` owns only epoch, ready and normalized-row tables. Old INSERT/UPDATE/DELETE writers increment affected owner epochs and invalidate readiness in their source transaction; TRUNCATE invalidates all ready cohorts without resetting epochs. Publication captures the initial epoch, verifies sources without a global advisory lock, then locks and rechecks the epoch before atomically replacing derived rows and readiness. A conflicting write rejects publication. No request backfills data, source records are never rewritten and failed publication rolls back. The exact canonical derived-cache migration is audited as a complete exception; altered SQL remains rejected by the migration guard.

An operator may explicitly run `python scripts/publish_legacy_list_projection.py --owner ACCOUNT_ID` with the configured PostgreSQL runtime after the migration. The command loads no Web application, logs no account/media/payload/credentials and closes its connection. Unsupported or changed cohorts remain on the original path. Rollback restores the complete release and retains incremental tables, epochs and source/task/call evidence; never delete or reset epochs during cleanup.

An eligible first page uses SQL grouped counts and latest-value selection from the matching ready generation. The result is still persisted as the original account/filter-bound 15-minute snapshot; old cursors bypass reaggregation. First-page legacy sources are sampled at the ready-read statement, while native and Beta data keep their separate sampling boundaries; this is not a database-wide snapshot. Dirty/unavailable cohorts add two bounded read probes and then execute the original source queries. The manual benchmark accounts for exactly 10 baseline queries, 12 dirty candidate queries or 7 ready candidate queries at both 1,000 and 10,000 tasks. `--projection` publishes outside timed work; A/A plus three 1,000/10,000 A/B repetitions, 31 samples, original latency/memory thresholds and frozen oracles remain.

Source manifest v253 lists 549 actual files; only new task fingerprints change. Synthetic production-Python/PostgreSQL smoke covers cross-group membership, owner isolation, old writers, CAS rejection, rollback, malformed-source fallback and unchanged cursors. The initial join-based SQL failed the performance gate and is retained as evidence; the replacement grouped aggregate still requires complete final performance and independent CI/release acceptance. This does not complete independent application construction or activate a new worker topology.

Final local PostgreSQL verification additionally covers INSERT and DELETE on all
five legacy source tables, replace_all/replace_tables rollback and committed
invalidation, competing publishers at the final epoch lock, old-writer lock
timeout with rollback, old-ready visibility before commit, and invalidation after
a subsequent source commit. Nonlatest label diagnostics/elapsed errors and
manual asset sort errors retain the original exception even when filters match
no orders. The final targeted run additionally proves partial derived insertion rollback and both ready owners on transfer; earlier failed fixture attempts
remain evidence and are not counted as passing.

`python scripts/benchmark_legacy_publication.py --output REPORT.json` measures
explicit publication separately from first-page performance gates. It emits one
traced sample each for 1,000 and 10,000 synthetic manual groups: elapsed time,
Python peak allocation, an upper bound on final epoch-lock hold, and fetched
source JSON UTF-8 bytes. These bytes exclude wire overhead; the synthetic
eligibility ratio does not predict customer cohorts. This is not a publication
P95 measurement. Local observations were about 0.39/3.55 seconds elapsed,
7.7/77.2 MB Python peak, and 0.21/1.75 seconds epoch hold upper bound (including statement wait and cursor close). Ordinary
writers may wait during this short final transaction; the original lock-timeout
and failed-publication behavior remain, without automatic retries.

The ready and dirty first-page protocols each completed their A/A and six A/B
cases with unchanged latency/memory guards. These measurements use the frozen
source; the corrected manual clock source inherits only the proven equivalent
pure-manual input and hot query. This is not full application-factory, final CI,
release or mixed-source publication performance acceptance.

The current-writer lock audit distinguishes live endpoints from generic batch
repository capability. Standard add/patch/confirm/document mutations first take
the existing owner+standard advisory lock and prelock the standard and its
existing assets. Single-row text persistence commits independently. Generic
replace_all/replace_tables application callers currently target unrelated tables;
the legacy multi-table COPY importer is an exclusive stopped-service operation.
Do not run custom cross-standard batch transactions or legacy bulk imports
concurrently with Web/native workers: the derived owner epoch adds a write lock
and arbitrary source-first/epoch-first multi-statement schedules can deadlock.
No automatic transaction retry is introduced. This is a maintenance boundary,
not a claim that arbitrary SQL has unchanged lock behavior.

The targeted PostgreSQL regression executes actual add/add, document mutation
vs another-standard patch, same-standard patch, and lazy single-asset save.
It observes blocking PIDs and the source row lock, then releases the first
transaction; both operations finish without retry and return idle connections.
Existing ready generations invalidate and republishing matches the original
reader. The test matrix has 16 test methods with four native-writer subcases.
This closes these concrete audited live schedules; it is not a general no-deadlock
proof or permission to publish before final integration/CI/release review.

The consolidated source manifest is v254 with 560 actual files after integrating
the reviewed legacy/Beta read batch with main e1cfee3 and owned configuration.
Earlier manifest counts describe their separate checkpoints. Both real-photo
and derived-summary incremental schemas are retained; whole-head CI, complete
application assembly and managed release/worker acceptance remain pending.


Application configuration is now composed by config/application_composition.py.
Each owner allocates its own reentrant guard and protected-write ContextVar;
training configuration selects that same owner lazily. Construction performs no
file or repository access. PostgreSQL protected writes retain their existing
transaction/advisory-lock behavior. Two real PostgreSQL owner fixtures cover
concurrent protected writes, training-state persistence and rollback after a
partial write. Run scripts/smoke_application_configuration_composition.py with
VANTALINE_POSTGRES_DSN to execute all six cases. JSON-only mode skips that one
PostgreSQL case. PostgreSQL fixture markers use JSON objects because the existing
record decoder treats strings as serialized JSON; this increment does not change
the decoder or rewrite stored configuration. Full application factory, PLC and
pipeline ownership and hosted/release gates remain open.
The combined Beta benchmark accounts explicitly for one legacy schema catalog
probe and one generation/eligibility query when the derived schema is installed
but no cohort is ready. A/A has neither probe. All other query counts must stay
fixed, the total remains at most 12, and original 31 samples, three memory
samples, P95 and peak-memory limits remain. Full combined CI is still required.

Static PostgreSQL persistence checks read the current business modules. Their
old-location oracle runs only after the actual 26 composition modules and
complete integrated root pass immutable AST bindings. Two explicitly reviewed
deltas restore the older assembly for its retained assertions; they do not
represent current source locations. Positive and adverse checks cover changed
repository timing/owner/import, missing or reordered nodes, route/shutdown order
and corrupted delta regions. This is test adaptation, with no production change.


The accepted-real-photo dispatcher exports group-disjoint original-only YOLO datasets with frozen labels/reviews and full class order. Local/RunPod held-out evaluation yields unavailable metrics for unsupported categories; candidates remain manual and collection continues. Supplemental masks use a separate explicit dispatcher and have no training admission effect. Training submission is reserved durably and never replayed after an uncertain outcome.

Camera inspection without a PLC lease may use the ordinary image endpoint with bounded `capture_session_id` metadata, grouping its real-photo feedback by the browser capture session. This metadata grants no camera dispatch or PLC capability; the leased dedicated camera endpoint retains its existing physical contract.

Real-photo scheduling freezes source IDs at the cumulative review trigger while labels are still pending. Later arrivals cannot starve the cohort; ready review and assessment jobs have queue precedence. Explicit changed annotation versions may be rechecked without new originals, preserving the real-photo count and prior cumulative cutoff. Incomplete annotation preparation is archived before pausing; failed review or assessment pauses the controller.

Assessment inputs freeze the initialization decision, current approved-real target and candidate trigger alongside reviewed decisions. The Agent can lower its approved target within 20–50 with a reason, but must distinguish that new target from the recorded initial value; prior reports remain immutable.

The dedicated review crop tool supports the system Pillow legacy `Image.LANCZOS` API and newer `Image.Resampling.LANCZOS` with identical pixel bounds and transform sidecars. Commission the actual sandbox interpreter under the final unit protections; a parent virtualenv crop or successful model exit does not verify the child tool. Keep original review receipts unchanged when fixing runtime compatibility.


The combined backend batch includes main 5bd0baf real-photo feedback stage3.
Image uploads retain capture-session grouping and exact original-byte hashes,
while selecting the application-owned file capability. Training retains frozen
executor, dataset and evaluation configuration checks; the runner selects its
owned artifact runtime. The new dispatcher stop hook precedes existing shutdown
hooks inside the ordered shutdown owner. These main changes are preserved, not
introduced as new behavior by the composition refactor. Current manifest v256
contains 566 actual files, including the new RunPod frozen-model settings module; historical source fingerprints are unchanged. The
source oracle records the exact two-region main root delta and the exact updated
runner/submission file digests. Whole current-head CI and deployment remain gates.


Real-photo mask/training dispatcher producers are tracked by the application-owned
DispatcherRuntime with a repository thread scope. Stop closes new loop iterations;
the first native shutdown step joins the actual producer threads and scope exits
before closing their training and model-MCP dependencies. A drain timeout keeps
those dependencies available and reports failure; it does not cancel an in-flight
call or repeat an uncertain start. Startup is once-only, including partial-start
failure; a stopped instance cannot restart. Existing two-second polling, enable
rules and task algorithms are retained. Synthetic lifecycle checks cover blocked
tick, blocked scope exit, startup/close races, partial/uncertain starts and two
independent owners. Current manifest v258 contains 568 actual sources. Complete
application assembly and current-head hosted/release gates remain pending.


Artifact port regression checks follow the actual detection workflow runtime
provider and accessory image metadata files through their current owners. They
retain constructor counts, exact forwarding aliases, required/None/falsey checks
and all upload/storage behavior assertions. The current 26 composition AST
bindings protect actual constructor edges before these source checks.


The image-provider configuration source check retains the exact three typed port
groups and every zero-argument supplier. The three reviewed model-option, provider and masked URL suppliers
select their exact ProviderConfiguration methods; all other getters still
select their original named capabilities. Actual composition AST bindings and
existing redaction, failure ordering and instance-isolation cases remain.


Public network policy still checks all seven original suppliers and exact
zero-argument getters, with the reviewed masked URL method on its provider owner.
TextMedia runtime checks follow the actual standard owner, its one constructor
and exact StandardMediaStorage provider. Required/None/falsey and all media
behavior tests remain; source guards reject unexpected owner edges.

## Workstation domain composition

`plc/workstation_composition.py` owns the existing workstation repository, station service and browser dispatch service. Seven typed external capability groups supply storage, identity and policy without selecting a connection, user, clock or file during construction. Internal calls use named methods that select the owned component after argument evaluation. The active-lease callback instead retains its original one-time station binding. Compatibility exports and route positions remain unchanged; assigning private entry aliases does not redirect owned internal edges.

The original three business implementations remain byte-identical. Source contracts verify the actual owner and complete ordered root before replaying the narrowly recorded constructor relocation; original protocol assertions remain. The new actual-owner tests cover independent graphs with identical IDs, request-time identity, duplicate admission, persisted declaration before projection failure, uncertain timeout settlement and callback rollback. Manifest v259 adds the actual owner source for new task fingerprints; historical snapshots remain unchanged. This closes the three-service workstation graph, while capture collaborators, pipeline and complete application lifecycle assembly remain pending.

`plc/lease_diagnostic_composition.py` composes the existing lease acquisition, maintenance and diagnostic services around the same workstation owner. Three typed external groups retain 24 lazy suppliers; four ordinary storage/token capabilities select named forwarding methods after arguments, while active-lease checks retain the initial station binding. Original component aliases, HTTP registrars and operation signatures remain in place. Claim/activate, heartbeat/rebind, diagnostic reservation/confirmation, draining release and late receipt preserve their transaction and uncertainty contracts. Six business modules remain byte-identical across these two composition increments. Capture and full application/pipeline lifecycle assembly remain separate work.

PlcCaptureWorkflows owns the retained LegacyRuntimeCoordination and PlcCaptureState graph through 18 external suppliers and six internal callbacks (three captured coordination methods and two capture forwarders, with the mutation method reused). Its constructor performs no I/O or worker startup. The existing capture/generation/owner-epoch state remains separate from Web Serial workstation leases. Both business implementations are unchanged; compatibility aliases retain original fixed coordination receivers and late-selected capture helper receivers. This closes capture state assembly only; legacy worker loops, pipeline and a complete application factory remain pending.

PipelinePersistence owns PipelineRuntimeState, PipelineTaskStore, PipelineStateStore and PipelineTrainingSync. Training completion reads/writes select named record forwarders; task and state guards are separate and owned by that runtime. The task store does not acquire a new lock: terminal synchronization already holds the original non-reentrant task lock. Constructors remain inert despite earlier allocation; paths, model providers and row codecs are lazy. Existing CostServices keeps its direct captured task-store reader. Native pipeline execution/pinning, HTTP registration and full application factory remain pending.

PipelineExecution composes the three existing native runtimes around one PipelinePersistence. Eleven narrow input groups carry 42 external suppliers; 21 internal getter edges select owned records, guards, registries, runners and auto-to-advance scheduling. Each runtime keeps a separate native lifecycle and shutdown step; three scope arguments retain the original bound repository thread_scope. The original ResolverProvider object is captured without calling it; each scheduled entry pins exactly once inside repository scope before request identity and selects the runtime after model binding. Public decorated compatibility entries and the producer-first close order remain unchanged. Pipeline task/query/agent/pose/HTTP assembly and the complete application factory remain unfinished.

PipelineQueries in pipeline/query_composition.py composes the actual metadata, candidate flow, task snapshots, resource status, auto-optimization links and public projection around PipelinePersistence. Its 46 external inputs remain narrow suppliers; 22 internal edges select named owner methods at operation time. Candidate refresh and missing-state optimization links retain protected writes and exception side effects. Resource files are captured at construction while candidate files remain operation-time suppliers. This graph introduces no new worker or whole-application factory.

The PostgreSQL endpoint source oracle verifies actual composition owners and replays the reviewed deltas in one dependency-ordered restore_business_root call. This preserves its original persistence, permission and repository-reference assertions without relaxing unknown-root rejection. It changes verification only, not application architecture or database behavior.

AgentPipelineWorkflows in agent/pipeline_composition.py composes the actual conversation, decision context/policy/flow, actions and turn services around PipelineQueries. Thirteen narrow input groups supply 36 external abilities, while 15 internal getters and four query forwarders select named owners at operation time. Its owned decision entry binds the directly supplied model resolver before selecting the actual flow; the root compatibility decision retains its original decorator. Settings/support/context failures remain outside rule fallback, while provider/parse/normalize exceptions retain one fallback without retry. This graph owns no worker lifecycle and does not complete the application factory.

PipelineStages in `pipeline/stage_composition.py` now composes AI activation, AI-card synchronization, training status, stage advancement, reconciliation and recommendation cache workflows around the actual PipelineQueries and the supplied PipelineRuntimeState. Internal metadata and transition calls select named methods on that owner; reconciliation selects the same runtime advance lock/inflight set used by native execution. The entry retains original component aliases and public function signatures. Its named `advance_pipeline_task` entry is distinct from the `advance` component. Constructors do not select suppliers, launch work or call a model. Preserve save-before-public-projection failures, paused-card state, shallow sharing, cache consumption and cancellation checkpoints. This closes these six stage workflows only; pose/task/HTTP composition, complete application factory, hosted performance gates and production topology activation remain pending.

PipelineTaskWorkflows in `pipeline/task_composition.py` composes the eight task-list, create, update, accessory routing, delete, Agent feedback/chat and manual advance/cancel services. It receives the actual Query, Stage, Execution and Agent owners and rejects mismatched query/persistence/runtime identities before constructing services. Internal calls select named methods; the original eight HTTP registrars execute at their original entry positions, preserving all ten endpoints and route order. Reconciliation still runs and may save before GET visibility filtering; deletion still requests cancellation before record authorization; chat still decides once outside the task guard and rechecks authorization before committing under the guard. Pose feedback remains an explicit external capability and may execute under the existing guard. Execution's own decision/advance inputs remain separate explicit ports; sharing this task graph does not complete those native cross-domain edges or the whole application factory.

PipelineRuntimeWorkflows in `pipeline/runtime_composition.py` constructs the actual mutation, stage, Agent and native execution services in dependency order around PipelineQueries and its shared PipelineRuntimeState. The 38 narrow groups expose 117 external abilities; 21 owned edges use 18 named forwarders. Native auto decisions and commits select the actual Agent; Agent advance selects actual stage/mutation services; stage progress persists through the actual task store. Constructors select no supplier and start no work. The directly supplied model resolver and separate native lifecycles remain unchanged. This closes the native pipeline collaborators, not pose assembly or the whole application factory.

Mutation progress/batch/mark test substitutions target the connected owner forwarders. The actual frozen mutation service and its class remain unchanged, preserving other application graphs. This test-seam repair changes no runtime ownership or business behavior.

Codex API registration now requires a typed environment mapping alongside its runtime provider. Account admission, model readiness and capabilities read that supplied live mapping. The default Web assembly explicitly supplies os.environ; the independent Codex worker explicitly supplies its own process environment to account selection. This isolates separately assembled API configurations without changing default behavior, model execution or worker topology. It closes this environment edge only, not the full application factory.

The registered API captures the supplied mapping object: in-place updates are visible, while replacing the process os.environ object does not replace the registered dependency. The independent worker chooses its own current process mapping at each claim.

The original pipeline runtime ownership clock oracle validates actual composed modules and replays the reviewed root assembly before its unchanged historical clock assertion. This preserves the original state/lock tests after task-list clock ownership moved into PipelineTaskWorkflows. No runtime or PLC behavior changes.

The composition source guard accepts partially replayed roots only when their entire AST matches an immutable reviewed descendant checkpoint. It still validates every actual owner before replay, rejects unknown edits at each checkpoint, and ends at the exact workstation parent. Historical oracle assertions and generic single-delta semantics remain unchanged; this does not approve a missing default Codex environment binding.

Provider dependency-capture tests substitute secret-key identification on the actual ProviderConfiguration instance. The same original A/B/C argument-time mutation and missing-callable assertions remain; other provider capabilities retain their existing locations. The temporary mock is restored on exit and changes no model call, key selection or retry algorithm.

Pipeline resource-status file binding is now assembled by PipelineQueries. The retained source-position oracle uses the strict integrated-root inverse, which verifies the actual query owner and unchanged business files before inspecting the original binding. Runtime file-isolation and error-propagation assertions continue to exercise PipelineResourceStatus directly.

Training task source contracts now enter through the central integrated-root inverse once. It verifies current domain owners, then configuration and integration layers in order before the unchanged training-specific import, owner, business-source and route/lifetime checks. A premature second configuration inverse is removed; runtime training code is unchanged.


Agent Pose domain assembly uses three inert owners: `AgentStateWorkflows`
(state, tool-call records and render configuration), `PosePlanningWorkflows`
(templates, policy, generation and task plans), and `PoseExecutionWorkflows`
(photo highlight, rendering, artifact publication, call execution and sample
preparation). Internal edges select named owners at call time and preserve
callee/argument evaluation order. Clock/configuration refresh, nested state
identity and partial failures retain their original behavior. Public entry
signatures and route/lifecycle order remain unchanged; no algorithm or prompt
change is included. This closes these domain edges, not complete application
factory assembly. New tasks use manifest v270 with 583 actual source entries;
historical task snapshots and secret references are unchanged.
