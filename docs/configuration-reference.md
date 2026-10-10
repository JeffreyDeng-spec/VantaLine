> **Current backend composition:** The Web application is assembled by `runtime/application.py`; `server:app` retains the stable ASGI entry and compatibility exports. Earlier migration checkpoint statements about unfinished domain/application assembly describe their historical checkpoint and are superseded by [canonical application construction](architecture.md#canonical-web-application-construction). They do not establish current CI, performance or production acceptance; those remain separate release gates.

Account visibility composition adds no setting. CORS origins/regex, authentication/access checks, output directory, model catalog, configuration and masked URL supplier retain their existing operation-time selection. Manifest v274 contains 588 actual source files; new fingerprints include the graph without rewriting historical task snapshots.

`TrainingPersistenceGraph` adds no environment setting or user configuration. Existing model-spec suppliers, resolver providers, account configuration, paths and repositories remain operation-time inputs. Training completion does not gain a combined transaction, retry or global guard. New task source fingerprints use manifest v273 with 587 actual sources, including the new graph; historical model snapshots and fingerprints are not rewritten.

Legacy label-list indexing adds no setting, provider, model or permission change. Source manifest v133 retains 341 actual sources and fingerprints the changed `label_inspection/api.py` for new tasks; historical task snapshots and secret references are not rewritten.

Label pure-list read transactions add no setting or provider change. Source manifest v132 retains the 341 actual entries from v131 and fingerprints the updated `storage/label_inspection.py` for new tasks; existing task model snapshots, secret references and historical fingerprints are untouched.

Label task-list batching adds no operator setting, default, model permission or provider selection. Source manifest v131 appends the actual `label_inspection/api.py` and `storage/label_inspection.py` sources (341 entries) for new task fingerprints; historical task snapshots, prompt bindings and secret references are not rewritten.

PLC diagnostic receipt extraction adds no operator setting, model permission, default, protocol version or secret. Source manifest v130 retains 339 actual source entries and fingerprints the changed diagnostic state source for new tasks; historical model snapshots, fingerprints and secret references remain unchanged.

PLC diagnostic confirmation extraction changes no operator setting, model permission, default, protocol version or secret. Source manifest v129 retains 339 entries and fingerprints the changed diagnostic state source for new tasks; historical model snapshots, fingerprints and secret references remain unchanged.

PLC diagnostic reservation extraction changes no operator setting, model permission, default, protocol version or secret. Source manifest v128 adds the two actual diagnostic state modules (339 entries) for new task fingerprints; historical model snapshots, fingerprints and secret references remain unchanged.

PLC model-rebind extraction changes no operator setting, model permission, default, protocol version or secret. Source manifest v127 fingerprints the changed lease-maintenance source (337 entries) for new tasks; historical model snapshots, fingerprints and secret references remain unchanged.

The lease acquisition extraction changes no operator setting, model permission, default, protocol version or secret. Source manifest v126 adds its two actual modules (337 entries) to new task fingerprints; historical model snapshots and secret references are unchanged.

PLC lease maintenance changes no operator setting, default, protocol or secret. Source manifest v125 adds the two lease state modules (335 entries) for new task fingerprints; historical task snapshots and secret references are unchanged.

The legacy PLC config diagnostic extraction changes no PLC setting, default, permission, protocol or secret. POST stays read-only and returns 410 after authorization. Source manifest v124 adds three actual files (333 entries) for new task fingerprints; historical model snapshots are unchanged.

PLC dispatch/diagnostic HTTP extraction changes no protocol, model, permission setting, default or secret. Source manifest v123 adds three actual files (330 entries) for new task fingerprints; historical model snapshots and fingerprints remain untouched.

PLC connection-lease HTTP extraction changes no PLC profile, model permission, default, protocol or secret. Source manifest v122 adds the three actual lease boundary files (327 entries) for new task fingerprints; existing model snapshots and historical fingerprints remain unchanged.

PLC workstation-management HTTP extraction changes no PLC profile, default, protocol, permission or commissioning setting. Source manifest v121 adds four actual PLC module files (324 entries) for new task fingerprints; existing workstation records, model snapshots and historical fingerprints remain untouched.

Pipeline stage-transition extraction changes no model settings, defaults, worker mode or secret references. Source manifest v120 includes its two actual modules (320 entries) for new task fingerprints; existing model snapshots and historical fingerprints remain unchanged.

Pipeline advance runtime extraction keeps account-scoped configuration, pinned model binding, task defaults and cancellation semantics unchanged. Source manifest v119 includes its two moved modules (318 entries) in new task fingerprints; historical snapshots, model versions and secret references remain intact.

Pipeline auto-Agent runtime extraction keeps the model binding, account scope, Agent step limit and decision configuration unchanged. Source manifest v118 records the two moved modules (316 entries) for new task fingerprints; old snapshots, model versions and secrets remain intact.

Pipeline recommendation pre-generation keeps the same model binding, request identity, provider selection and task settings. Source manifest v117 includes the two moved runtime modules (314 entries) in new task fingerprints; historical snapshots, model bindings and secrets are not rewritten.

# Configuration reference

Pipeline trained-model linking keeps existing catalog visibility, fallback model-ID construction and model-path truthiness unchanged. Source manifest v116 retains the same 312 entries because `pipeline/training_links.py` was already listed; new task fingerprints reflect its changed source, while historical snapshots, model bindings and secrets are untouched.

Pipeline training status extraction keeps training job lookup, local interruption settlement and Agent stage configuration unchanged. Source manifest v115 contains 312 entries including the two moved modules for new task fingerprints; existing snapshots, model bindings and secret references remain unchanged.

Pipeline reconciliation keeps the five-second list throttle, Agent selection and training-task lookup settings unchanged. Source manifest v114 contains 310 entries including the two moved reconciliation modules; new task fingerprints use their actual source, while existing snapshots and secret references remain unchanged.

Pipeline accessory membership retains existing account-scoped configuration, canonical/alias resolution and public payload behavior. Source manifest v113 (308 entries) includes the three moved route modules for new task fingerprints; old snapshots, model bindings and secret references remain untouched.

Pipeline Agent feedback preserves current action aliases, pose image provider configuration, model/tool-call selection and clock usage. Source manifest v112 (305 entries) records the three actual moved feedback modules for new fingerprints; historical snapshots, model versions and secret references are unchanged.

Pipeline task listing retains the shared five-second synchronization window, admin scope, all-task normalization and model projection settings. Source manifest v111 (302 entries) adds the three actual list modules for new task fingerprints; old snapshots, model versions and secrets are unchanged.

Pipeline Agent chat retains current model selection, config scope, task snapshot and one-decision behavior. Source manifest v110 (299 entries) includes the three actual Agent chat modules for new task fingerprints; historical snapshots, model bindings and secret references remain unchanged.

Manual pipeline advance and cancel keep their existing request identity, permission checks, double task load on cancellation, repeated-request behavior, state text and exact lock boundaries. Source manifest v109 (296 entries) records the three moved control files for new task fingerprints; prior snapshots and bindings stay unchanged.

Pipeline deletion keeps the existing request identity and record-access order, linked ID filtering and duplicate rules, error responses, and partial cleanup after the locked row delete. Source manifest v108 (293 entries) includes the three moved task-delete files for new fingerprints; historical snapshots and bindings are unchanged.

Pipeline creation keeps existing permission and owner selection order, request defaults, incoming-material constraints, AI task binding and two distinct save phases. Source manifest v107 (290 entries) includes the three moved task-create files for new fingerprints; historical snapshots and bindings are unchanged.

Pipeline task update retains the existing role and record checks, incoming-material restrictions, current request-model defaults and coercion, partial in-memory mutation on later failure and the previous save/projection order. Source manifest v106 (287 entries) includes the three moved task-update files for new fingerprints; historical task snapshots and model bindings are unchanged.

The current source manifest is v109 (296 entries). Version references below describe earlier complete manifest snapshots, not when each module first appeared; operational deployment and rollback use the manifest bundled with the selected release.

Dataset/model resource-status projection retains the current input, loader and file-existence semantics. Source manifest v105 includes its service and ports for new task fingerprints; historical snapshots remain unchanged.

Pipeline task label and accessory-name projection uses the current linked AI task labels and retains the existing name fallbacks. Source manifest v104 includes the two moved files for new task fingerprints; historical snapshots and model bindings remain unchanged.

Pipeline recommendation helpers retain training-mode normalization, signature inputs and cached-parameter consumption. Source manifest v103 includes the two actual moved sources for new task fingerprints; historical model bindings and snapshots remain unchanged.

AI task pipeline synchronization retains existing accessory route selection, account visibility, task identity and saved-card state. Source manifest v102 adds the two actual pipeline sync sources (278 total); new task fingerprints follow the moved code, while historical snapshots and model bindings remain unchanged.

Pipeline background publication preserves the original prompt and image model settings,
library-first selection, reference cap and existing fallback behavior. Source manifest
v101 adds the actual coordinator and ports (276 entries) for new task fingerprints;
historical snapshots and model bindings are not rewritten.

Background-library selection preserves owner and list-only sharing rules, sorted
candidate order, per-set image limits, source precedence, score rounding and threshold
reads. The existing zero-distance truthy fallback is retained and tracked separately.
Manifest v101 includes the two actual new sources without rewriting historical task
snapshots.

Background evidence retains source ordering, limits, component thresholds, strip
selection, inpaint policy and fixed noise seed. The time budget is checked at existing
boundaries and is not a hard interruption deadline. Manifest v101 includes the two actual
new sources; existing task snapshots are not rewritten.

Profile generation preserves all prompt literals, token budgets, model configuration
selection and reference defaults. Default expressions remain eagerly evaluated at their
original sites. Port annotations do not add runtime validation or guarantee dictionary
results from injected collaborators. Manifest v101 covers the actual moved source files
for new fingerprints; historical snapshots are unchanged.

Profile payload projection keeps the existing English instruction and Chinese usage
strings unchanged. New capability input types reflect existing missing or non-dictionary
values without adding validation; public signatures remain unchanged. Manifest v101
includes the actual moved sources for new fingerprints and retains historical snapshots.

Physical dimensions retain existing preset defaults, units, rounding and numeric
parsing. Paper mappings are resolved at all four original sites, including eager A4
default evaluation. Valid normalized raw values do not read fallback dimensions.
Manifest v101 adds the actual two source files for new task fingerprints; historical
snapshots remain unchanged.

Profile projection retains original naming, source sorting, count coercion, reference
filtering and dictionary alias behavior. Raw type checks and reference reads precede
fallback construction; fallback then precedes subsequent field normalization. Real
optional_float rejects nonpositive values and NaN; permissive injected callbacks can
exercise a different boundary. Manifest v101 includes the actual moved files for new task
fingerprints without rewriting old snapshots.

Display label extraction preserves explicit field, profile, name, label, native-marker
and search priorities. Defaults, generic-token filtering, word caps, capitalization and
phrase insertion order are unchanged. Manifest v101 adds the actual display label sources
for new fingerprints; historical snapshots remain intact.

Reference context collection keeps its public definition-bound
AI_PROFILE_REFERENCE_IMAGES default. The domain method requires max_images explicitly,
while the public adapter always forwards it. The fraction method retains its literal
default 3. Zero limits can still attempt one image. Manifest v101 adds the two actual
reference evidence sources for new fingerprints; historical snapshots remain intact.

Preview asset loading preserves normalized/source/default priority and
canonical-text/all-normalized/rectified-source/manual-default fallback order. Policy
strings, source indices, nullable decode, dimension fallback and required keyword-only
selector parameters are unchanged. Manifest v101 adds the two actual loader sources for
new fingerprints; historical snapshots remain intact.

Asset composition preserves public defaults, trim thresholds, aspect ratios,
interpolation, alpha truncation and physical metadata aliases. Physical object paste
still avoids a second resize. Manifest v101 adds the two actual compositing sources for
new fingerprints; historical task snapshots remain unchanged.

Preview sprite selection preserves the non-AI preprocessing fallback, raw/canonical pose
family precedence, supported top-view positions and legacy source-position exemptions.
Alpha thresholds, image-copy behavior, orientation thresholds and public keyword-only
parameters remain unchanged. Manifest v101 adds the two actual preview sprite sources;
historical snapshots retain their original provenance.

Materialized assets retain original dimension defaults, family precedence and readiness
semantics. Existing false dimension values survive setdefault; metadata completeness
requires presence rather than truthiness. Manifest v101 records the two actual new
sources without rewriting historical task snapshots or model bindings.

Preview pose policy keeps aliases, raw-family intersections and None versus empty-list
results. The original public list[str] annotation still permits None in practice; the
dependency port declares that nullable result accurately. Manifest v101 retains the prior
274 source entries, including background-library selection, and adds two pipeline
background publication sources, for 276 in total.
Actual source fingerprints update without rewriting old snapshots.

Pose policy preserves the public definition-time BACKGROUND_ROI_PX default and forwards
roi explicitly to the internal required parameter. Manifest v101 includes both actual pose
policy sources; historical task snapshots remain unchanged.

Cutout geometry keeps existing color normalization, thresholds, component selection
and alpha calculations. Normalization still accepts strings, dictionaries and empty
values. Manifest v101 includes four actual geometry modules; old snapshots stay intact.

Cutout runtime extraction preserves u2net selection, both matting parameter sets,
thresholds and exception scopes. Manifest v101 includes the three actual cutout modules;
historical task snapshots and model bindings are unchanged.

Material alpha preserves transparent/opaque policy, mask thresholds, morphology order
and output statistics. Manifest v101 includes the three actual alpha modules; historical
task snapshots and model bindings are not rewritten.

Sprite publication retains foreground/edge thresholds, existing physical metadata
projection and canvas sizing/interpolation rules. Manifest v101 includes the three actual
modules; historical task snapshots are not rewritten.

Sprite metadata preserves default-size and ratio reads at their original points, physical
projection rules and in-place metadata aliases. Manifest v101 records the actual five
modules; existing task snapshots and model bindings are not rewritten.

Sprite geometry retains mask thresholds, component area minima, orientation boundaries,
resize interpolation, metadata and copy/identity semantics. Manifest v101 records its actual
modules without changing configuration or historical model snapshots.

Object preprocessing retains alpha policy reads, pose-position counts, cache/force rules
and metadata completeness semantics. Source manifest v101 includes the actual two modules;
no configuration setting or historical snapshot is rewritten.

Crop component extraction retains alpha/area thresholds, component caps, padding, anchor
selection and diagnostic metadata. Source manifest v101 records the actual three modules;
no configuration setting or historical model snapshot is changed.

The photo-highlight sprite coordinator preserves source limits, attempt counts, build
versions and late callback selection. No model, prompt or retry policy changes. Source
manifest v101 adds its actual modules; historical task snapshots remain unchanged.

Photo-highlight image helpers preserve exact prompts, JPEG quality, input size limits,
mask thresholds and comparison scores. Manifest v101 records the actual helper source
files; existing model bindings and historical snapshots remain unchanged.

Photo-highlight workflows retain the original source count/default binding, sprite-build
version checks, training-mode precedence and image model configuration. Manifest v101
fingerprints actual modules without rewriting historical task snapshots.

Pose materialization preserves chroma thresholds, sprite policy/version, output limits,
reference suffixes and the final strict hash binding. Source manifest v101 records the actual implementation
files; historical model bindings and task snapshots remain unchanged.

Pose task workflows retain model selection, configuration projection, cached-asset reuse
and missing-configuration behavior. Source manifest v101 covers the actual workflow sources;
historical model bindings and task snapshots remain unchanged.

Pose rendering preserves provider defaults, timeout bounds, exact prompt text and reference
selection. Digest callbacks retain the final strict hash binding. Source manifest v101 includes the actual
implementations without rewriting historical task snapshots.

Pose planning preserves prompt text, confidence and pose limits, training_vision settings
lookup, cached plan reuse and provider request fields. Source manifest v101 fingerprints
the actual implementations; historical task snapshots are unchanged.

Pose asset extraction preserves reference suffixes, sprite build checks, material precedence
and every pose template/request literal. Manifest v101 includes the actual implementations;
existing model settings and historical task snapshots remain unchanged.

Agent state construction preserves orchestration version, stage defaults, timestamps and
image configuration resolution. Manifest v101 includes the actual state and call-record
implementations. Existing task snapshots and business settings remain unchanged.

Agent pipeline action extraction preserves action defaults, parameter copying, optional
legacy inline advancement and exception matching. It introduces no business setting.
Manifest v101 includes the actual action and turn implementations without rewriting old snapshots.

Agent pipeline decisions retain their original actions, parameter bounds, prompt literals and
model bindings. Settings/support checks and context construction remain outside the transport
fallback block. Unknown chat failures invoke the existing rule fallback once; interrupts escape.
Manifest v101 fingerprints the actual source files without rewriting old task snapshots.

The Agent configuration read endpoint retains its administrator check. The retired write
and connection-test endpoints still check administrator access and then return the existing
409 response before reading settings, saving secrets or probing providers. Recommendation
request validation and defaults are unchanged. Manifest v101 includes the actual moved sources.

Agent invocation extraction preserves provider dispatch, connection probes, model options,
recommendation bounds and all prompt literals. Bound calls retain the selected profile snapshot,
a shallow settings copy and one attempt through the existing provider accounting boundary. Legacy
HTTP calls retain their prior accounting behavior. No model binding, retry or fallback policy
changes; manifest v101 records the actual moved sources without rewriting historical snapshots.

Agent settings extraction retains URL-based provider selection, timeout bounds, key selection
and existing public fields. Non-admin output returns before secret projection; admin output masks
keys and preserves established metadata. Legacy save persists secret references before replacing
the settings file. Failure keeps prior secret writes and temporary-file evidence; no retry, lock,
encryption or compensation is added. Existing model bindings and historical snapshots are unchanged.

Key-material extraction preserves ID hashing, secret masking, generated environment names,
local-file syntax and process-environment precedence/cache. Save still writes the temporary file,
attempts its chmod, replaces the destination and attempts its chmod; only the existing OSError
exceptions are tolerated. Set/delete update process state after persistence. This retains the
existing fixed temporary filename and adds no concurrent-writer transaction or encryption change.

Key registry extraction preserves environment-over-inline precedence, provider-scoped ID
deduplication, pending environment references and legacy key naming. JSON skips an explicitly
unsupported provider; image and Agent entries retain their fallback rules. Agent normalization
continues mapping qwen to openai_compatible. Public output keeps its field allowlist and masked
keys. No secret-file write, model binding or historical snapshot behavior changes.

Provider configuration-policy extraction changes no accepted provider/model/key-name grammar,
timeout bound, error status or message. Base URL and proxy URL retain their distinct credential
and HTTP rules. Public URL projections retain credential/query removal, masked proxy usernames,
IPv6 formatting and invalid-port fallback. Manifest v101 includes actual sources; no environment
setting, model binding, prompt or historical snapshot changes.

Legacy provider-settings extraction preserves migration precedence: JSON detection prefers
direct environment, named environment, then local keys; image generation retains local-key
precedence. Provider fallback, timeout bounds, key deduplication and public metadata are unchanged.
These helpers do not override model-purpose bindings after migration. Source manifest v101 records
the actual files; historical task snapshots and secret references are not rewritten.

Status projection extraction preserves the existing public field exclusions and permission
checks. Admin service status retains payload identity; configuration summaries still pass through
the path sanitizer. Non-admin views keep their existing restricted fields. This is the existing
shallow projection contract, not recursive sanitization of arbitrary new fields. No setting,
permission, model binding or historical snapshot changes. Manifest v101 records actual sources.

Provider orchestration extraction preserves current JSON/image retry policies, backoff,
key rotation and JSON repair text. Bound model profiles cannot use the legacy overloaded-model
fallback; cached content and explicit fallback disablement retain their existing guards.
Unknown non-provider exceptions escape unchanged. Existing provider-error retry classification,
including errors around the image semaphore, is preserved. Manifest v101 includes actual moved
sources; no model, prompt, secret reference or historical snapshot is rewritten.

Image transport extraction preserves both request formats, image limits, error classification,
download behavior and proxy metadata. Single-attempt calls retain fixed sizes; legacy calls read
VANTALINE_AGNES_IMAGE_SIZE or VANTALINE_QWEN_IMAGE_SIZE per call. Agnes retains exactly one
response-format compatibility fallback when single_attempt is false; Qwen adds no retry.
Manifest v101 includes the actual moved sources; historical snapshots are not rewritten.

Gemini extraction preserves thinking settings, token defaults, cache payloads and TTL bounds,
image selection, proxy diagnostics and HTTP classification. The cached-content default still
captures INSPECTION_AI_PROFILE_CACHE_TTL_SECONDS at application load. No prompt, model or retry
policy changes. Source manifest v101 includes the actual moved transport and ports for new tasks;
historical snapshots and secret references are not rewritten.

OpenAI-compatible transport extraction preserves request payloads, token defaults, thinking
flags, timeout conversion, response validation, error evidence and the existing accounting policy.
Missing bound-model resolvers fail before sending. A successful call is never repeated because
accounting fails. No model, prompt or retry configuration changes. Source manifest v101 includes
the moved transport, ports and accounting implementation; historical task snapshots stay intact.

Provider foundations preserve HTTP status classification, text truncation, JSON candidate
priority, fallback parsing and the existing non-decoding data-URL contract. No prompt, provider,
model or retry policy changes. New exception classes identify their actual module as
`local_inspection_service.model_providers.errors`; root import aliases retain old serialized
exception paths. Source manifest v101 includes actual moved sources without rewriting old snapshots.

Media extraction preserves JPEG quality, image dimensions, reference limits, alpha/gray
conversion, sheet layout, digest inputs and cache-hit rules. No model or prompt setting changes.
Source manifest v101 includes the actual moved media implementations for new fingerprints;
previous task snapshots and secret references remain unchanged.

Ordinary upload extraction preserves original filename handling, image decoding, video FPS
fallback, sampling stride, frame limits and AI-summary formatting. No upload limit, permission,
model-selection or retry policy changes. Manifest v101 includes the four actual moved sources;
existing task snapshots and secret references are not rewritten.

Profile-cache extraction preserves its existing key version and canonical payload, prompt text,
reference mode, TTL, 60-second hit margin and JSON path. It retains repeated field/TTL reads and
partial-failure evidence. A create-failed result still reports provider_call_count=1 even when
failure occurs before an actual request. Source manifest v101 includes all three moved sources;
historical model snapshots and secret versions are unchanged.

Presence inspection preserves image priority, profile-cache accounting, per-accessory reference
limits and the existing Qwen coverage retry. Cache budget exhaustion still leaves one generation
attempt; the coverage retry retains its separate single attempt. Prompt text and provider choices
are unchanged. Source manifest v101 includes the actual orchestration and ports; existing task
snapshots and secret versions remain intact.

Detection orchestration preserves promoted-model fallback, threshold conversion, OCR, profile
updates, reference-image limits, output writes and evidence recording. The existing AI decorator
continues to use argument zero (the image): it inherits an ambient snapshot or resolves the same
empty-record default, not a new spec-based binding policy. Manifest v101 includes both actual
business sources and their ports; prior task snapshots and secret versions are not rewritten.

The annotation extraction keeps strict coordinate types, clamp/round order, pixel bounds,
colors, font sizes, blending and JPEG quality 92. Only a None annotation falls back to the original
image; existing write return/error behavior is preserved. No image or detection policy changes.
Manifest v101 hashes the actual moved source for new fingerprints without rewriting old snapshots.

Presence result normalization preserves rule-count precedence, strict presence, confidence
validation before rounding, count mismatches and existing text limits. No decision algorithm,
model, timeout or retry setting changes. Manifest v101 includes the actual new source for future
fingerprints; historical task bindings, fingerprints and secret references remain unchanged.

Detection failure projection preserves existing response fields, metadata merge behavior, duplicate
IDs, empty-input behavior and collection references. No detection threshold, model, timeout or retry
setting changes. Manifest v101 hashes the two actual moved modules for new source fingerprints;
existing task bindings, secret references and historical snapshots remain untouched.

Presence payload and response validation move without changing prompts, token budgets or retry
policy. Coverage still accepts any mentioned required ID; count validation still rejects booleans,
strings, negative/fractional and nonfinite numbers. Source manifest v101 includes both actual moved
modules, while task bindings, secret references and historical fingerprints remain unchanged.

Accessory resolution preserves first-wins alias lookup, last-wins UID/class indexes, selected-item
order and duplicates, minimum count clamping and missing-metadata records. No configuration default,
detection rule or model policy changes. Source manifest v101 includes the actual new lookup and
requirements modules for new fingerprints; historical snapshots are not rewritten.

Retired worker task settlement still reports failed/progress=100 with the original RunPod-facing
messages and timestamp conversion. Refresh adds the same two True retirement flags and only a
missing note default. No parameter, feature switch, retry or model binding changes. Source
manifest v101 includes both moved files for new fingerprints; old snapshots remain unchanged.

No setting can enable the retired Windows worker request methods. All three immediately raise
the same retirement RuntimeError and status remains configured=false/ok=false/status=retired.
Argument defaults are preserved but not interpreted beyond ordinary Python binding. Source
manifest v101 records the relocated source for new fingerprints without rewriting old snapshots.

Retired watcher interval parsing keeps the 20-second default and 5..600 bounds, including existing
NaN/infinity and TypeError/ValueError behavior. The setting does not enable the watcher: enabled
remains false, watch-once returns zero and startup returns None. Source manifest v101 includes the
actual moved source for new fingerprints; no historical snapshot or internal switch is changed.

Worker artifact import retains optional trimmed/lowercase SHA-256 verification, strict base64
input, owner values, filename fallback and metadata timestamps. No upload limit, authorization,
retry or model policy is added. Source manifest v101 includes the actual relocated artifact source
for new fingerprints only; stored model versions and historical snapshots remain unchanged.

Worker bundle metadata retains all fields, numeric clamps, train-mode priority, dataset-path
basename fallback, strict archive hashing and returned manifest aliases. The upload timeout remains
`max(1800.0, remote_training_timeout_seconds())` with one callback read. No setting or retry policy
is added. Source manifest v101 includes both relocated files only for new source fingerprints.

Streamed worker helpers retain URL concatenation, header lookup, timeout values, multipart field
names and byte accounting. Progress retains its 1.5-second default and shared counter semantics.
No environment switch, retry, model or identity scope is added. Source manifest v101 records the
two actual relocated files for new task fingerprints; historical bindings remain unchanged.

Remote training compatibility extraction keeps endpoint/key settings, metadata defaults, clamps,
status interpretation and exact top-level response filtering. Worker terminal checks still differ
from remote success aliases. No retry, binding scope, parameter, endpoint or retired-worker policy
is added. Source manifest v101 includes both relocated source files for new task fingerprints.

Background API extraction preserves supported suffixes, metadata defaults, visibility checks and
empty-scene rejection messages. Validation makes the same single analysis call and does not add
retry, count normalization or model policy. Async upload blocking-copy behavior, middleware access
checks and all request/response defaults are retained. New source fingerprints use manifest v101.

Background task extraction retains Codex command arguments, prompt content and process timeout,
including existing nonzero-exit and partial-output handling. Task model bindings are resolved
before task loading; missing resolvers fail explicitly. The thread topology, owner-field behavior
and all background settings remain unchanged. New task source fingerprints use manifest v101.

Background write extraction retains the local random seed, pixel operations, suffix fallback,
variant names, manifest alias behavior, fifty identifier attempts and timestamp fallback. Task
background replacement keeps two metadata timestamps and the original ownership defaults. No
new setting, model, provider call, prompt or image-generation policy is introduced.

Background-set helper extraction keeps the default ID, image suffix rules, visibility, system
ownership and nullable selected-ID behavior. Directory reads still seed the default source and
may persist the manifest; list projection retains its already-loaded metadata snapshot. JSON
non-mappings and invalid count types are not silently repaired. No new settings, deduplication,
variant-generation algorithm or background provider policy are introduced.

Job list/detail and training task PATCH/DELETE request contracts are unchanged. Training lookup
retains precedence over image jobs and authorization precedes worker/native projection. Empty
training records still fall back to the first image job/task ID match. Native detail does not add
settlement; legacy worker detail remains read-only. Editing no fields still updates the timestamp
and saves. Image stop/retry/delete routes retain delegated identity and permission checks.

RunPod training transfer API contracts are unchanged. Token mismatch remains 404 and expired URLs
remain 410; expiry equal to the integer current time is accepted and zero means no expiry check.
Artifacts still use the configured size cap, a fixed `.uploading` sibling and final replacement.
No new account check, lock, retry, archive validation or setting is introduced by this extraction.

Training start and sample generation keep their existing request schema and defaults. A truthy
dataset ID selects the dataset path only for start; generation still validates the approved preview.
Asset refresh may re-scope and reselect after one approval check. Background IDs remain nullable.
State writes follow task enqueue; failed state persistence does not cancel or automatically replay
the task. Status accepts an account target only for administrators and retains projection errors.

Input/state extraction adds no configuration or cache-key version change. Fingerprints retain
original path strings, sprite order/duplicates, stat metadata, JSON options and SHA1 truncation.
Approval compares ordered accessory IDs before background and cache; only stale cache mutates
training configuration before its existing 409. New source manifest v101 records all four relocated
input/state modules. Historical model/source snapshots and existing preview keys are not rewritten.

No available background still resolves to None through plan reads, rendering, plan JSON and user
state. Preview workflow interfaces declare that nullable value explicitly.

Preview workflow extraction adds no setting, caching or request-model change. `force_refresh=False`
still regenerates previews. GET alone applies final path sanitization; POST returns its original
plan. Member requests ignore GET user_id, while admins retain target scoping. The three original
clock reads, sprite-count short circuit, repeated-UID overwrite and image count limits remain.
Source manifest v101 includes the relocated query, submission and plan-storage sources for new
fingerprints; historical task snapshots remain unchanged.

The preview renderer has no new configuration. Its tests select the original metadata
golden by the imported OpenCV version because the existing lock includes overlapping
OpenCV distributions; this change does not alter that production dependency lock.

Preview rendering adds no setting or algorithm. Existing repeated object size/center and generic
asset calls are preserved along with the shared random stream, stable document-first ordering,
one optional sprite rematch and paste metadata override order. Detection threshold providers retain
the original short-circuit reads. Source manifest v101 includes the relocated renderer; stored task
model versions and historical source fingerprints remain unchanged.

Layout extraction introduces no configuration or placement policy. The original ROI default
remains captured at function definition; later reassignment does not change omitted arguments.
Explicit None still fails. Existing 12px margins, 180 attempts, 0.5 overlap acceptance, contour
thresholds and OpenCV transforms remain. New task source manifest v101 includes the three actual
layout source files. Historical model snapshots and fingerprints are not rewritten.

Background extraction adds no setting or rendering policy. Provider file order and duplicates,
default-file insertion into the supplied list, two-stage background selection and the original
manifest exception handling remain. The same RNG flows through image choice, fitting and
augmentation; canvas sizes, interpolation, noise/blur/texture parameters and disabled glare stay
unchanged. Source manifest v101 includes both actual relocated background input files for new task
fingerprints. Historical model bindings and stored source fingerprints are not rewritten.

Resource mutations add no configuration or request defaults. Dataset PATCH converts manifest
read OSError/JSONDecodeError to HTTP 500; model PATCH treats only JSONDecodeError as empty metadata;
sample DELETE retains its existing OSError/JSONDecodeError catch around manifest read/write.
Invalid UTF-8 and unlink errors propagate. No-field PATCH still updates the timestamp. Dataset,
training-link and model identifiers retain their different normalization rules. This write-path
extraction adds no model-input producer: it does not extend the source manifest, and old bindings stay intact.

Training resource catalogs add no settings or API defaults. Summary mode omits per-sample path
hydration but still loads the manifest and record audit; detail preserves per-sample audit and
ownership fallback. Model discovery retains its ambient request identity in addition to resource
projection's explicit user filter. Source manifest v101 adds `training/dataset_catalog.py`, the
actual model-root discovery and dataset selection source; historical snapshots are unchanged.

Archive skip directories and JPEG quality remain runtime-provided values with their existing
root constants and defaults. Dataset URLs use the raw job ID; artifact URLs use the stripped ID
and keep a separate directory-name cleaning rule. Imported paths still resolve under the output
root; task lookup can supply the uploaded archive, while output ownership and metadata come
from the caller's task. No setting, model scope or minimum artifact policy is added. Source
manifest v101 includes the archive, export and artifact modules for new fingerprints only.

RunPod flow extraction introduces no setting or extra model scope. Its four base-model
environment-name constants move to `training.runpod_submission` and remain root imports.
Environment reads remain lazy, including whitespace/default and URL-with-checksum rules.
Payload mode selection and completion warmup retain their distinct priority rules. New task
fingerprints use source manifest v101, including the three relocated RunPod source files;
old model references and existing snapshots are not rewritten.

Dataset generation adds no setting or model binding scope. Its caller's saved model scope
remains authoritative. Background selection uses the current request identity through its
one-argument callback; filesystem ownership uses the task's explicit owner. Integer seed zero
falls back to the clock, while string "0" resolves to zero. Manifest v101 includes the relocated
sample planning, annotation, dataset generation and estimate sources for new fingerprints;
existing records and historical fingerprints are retained.

Training execution adds no setting. Executor selection, repeated dataset-existence checks,
CPU/GPU command flags, CLI discovery precedence and snapshot fallback retain their original
rules. Submission still reads request identity at its original points and does not add
ContextVar propagation to ordinary training threads. Each Runner has one binding wrapper;
missing model dependencies fail before task reads or failure-state writes. Source manifest
v101 adds `training/runner.py`, `training/submission.py` and `training/local_process.py` for
the actual relocated task and command input sources; old task snapshots are not rewritten.

Training state services preserve current-owner ContextVar precedence over an explicit
state/user when setting ownership. Store keys are normalized while raw owner fields keep
existing payload spelling. Direct sanitization mutates the supplied record; user views first
copy only the top level. The current source manifest is v101 and adds `training/user_state.py`,
`training/task_models.py`, `pipeline/training_sync.py` and `detection/training_candidate_sync.py`
for the moved selection, training parameter and model-ID assembly. Existing frozen references,
secret versions and historical fingerprints are not rewritten. No new setting is introduced.

Executor extraction adds no settings and preserves existing environment names/defaults.
Whitespace primary RunPod keys still suppress fallback before trimming; public-URL presence
and parsed-URL validity retain their separate rules. RunPod URL/auth are resolved once per
request, while the default timeout is read inside each attempt. Only explicit 401/403
responses use the existing second authorization format. Timeouts and uncertain transport
failures are not retried. Source manifest v101 includes both moved executor implementations; historical
model bindings and snapshots remain unchanged.

Training lifecycle extraction adds no setting. Retired Windows-worker records remain
read-only regardless of allow_remote_refresh; RunPod classification keeps its existing
precedence. Public projections retain existing None/empty values set by earlier steps
and parse only the first epochs/imgsz command argument. Source manifest v101 covers the moved runtime, lifecycle and view implementations;
existing model references and historical snapshots are not rewritten.

Pipeline task single saves retain their frozen model references; bulk saves do not
add missing snapshots. JSON task payloads retain their raw IDs even when the SQL row
encoder normalizes the primary key. State normalization keeps the two ordered lists
and the original iterable input handling. Root PIPELINE_STATE_PATH overrides are
resolved when called. No setting change accompanies this storage
extraction. Source manifest v101 includes the three migrated pipeline implementations;
historical model bindings and fingerprints remain intact.

Training storage keeps the existing model-binding policy: only records without the
`model_profiles` key acquire a new frozen snapshot. Existing None, empty or historical
values stay untouched. A new record without an available resolver fails before cache
invalidation or storage. No setting or schema changes are introduced; source manifest
v101 includes the moved training identity/storage implementations. The shared
snapshot algorithm and historical fingerprints remain unchanged.

Training catalog path, resolver, audit, OCR and pipeline callbacks use seven narrow
getters at nine original argument expressions. This preserves callback capture
before argument effects, including prior replacement and missing callbacks. Finder
repository selection, lazy snapshots and partial-failure state remain unchanged.

Training model discovery keeps existing config fallback, task/manifest/metadata
precedence, accessory counts and OCR variant selection. It adds no environment or
business API setting. Source manifest v101 includes `training/task_lookup.py`,
`training/model_catalog.py` and `pipeline/training_links.py`; new snapshots use that
truthful source fingerprint and historical task/secret/model bindings remain intact.

Warmup method, path resolver, model loader and error formatter use narrow callback
getters at their original expressions, after preceding work and before argument
conversion. Missing callbacks retain argument effects; new getter failures stop
before them. No retry, lock or thread admission policy is added.

Warmup extraction preserves all `VANTALINE_YOLO_PREWARM*` defaults and read timing.
Explicit model lists retain duplicates, implicit candidates apply the original limits
before final deduplication, and no admission or concurrency setting is added. Manifest
v101 includes the three migrated warmup sources; historical snapshots remain unchanged.

Local model factory lookup uses a narrow getter after path resolution and before
string conversion, preserving callback replacement and missing-callable argument
effects. Existing cache publication order and exception boundaries remain unchanged.

Local model selection/cache extraction adds no settings or selection rules. Current
source manifest v101 includes `detection/model_selection.py` and `detection/local_models.py`
so new fingerprints cover the moved specification and actual weight-instance choice.
Historical task bindings, prompt fingerprints and secret versions remain unchanged.

Task catalog extraction changes no API defaults, thresholds or model selection
rules. Manifest v101 now includes the actual task projection and catalog files that
assemble model accessory names/counts. New tasks receive the new source fingerprint;
existing task snapshots, secret references and historical fingerprints are untouched.

Detection task storage adds no configuration or defaults. Existing ID/name/count
normalization, background selection, path providers and shared read-cache TTL remain.
Source manifest v101 adds the three task modules that normalize counts and select
background inputs, retaining all previously listed sources. Stored model versions
and historical snapshots are unchanged.
Row decoding and background callback getters resolve at the original expressions:
after preceding work and before fetch/string/mapping argument effects. Missing
callbacks preserve argument evaluation and TypeError. Source manifest v101 covers
the three task modules; no retry, cache policy or transaction change is introduced.


Paddle settings and OCR thresholds are unchanged. `runtime.paddle` keeps setdefault
semantics for environment flags and the exact English PP-OCRv6-small parameters;
the incoming engine continues to use PP-OCRv6-medium. Source manifest v101 lists the
actual bootstrap and five detection OCR modules. New snapshots record this source
fingerprint; stored model versions, secret references and historical fingerprints
remain untouched. No new business switch or worker mode is introduced.
Attachment crop, score and match getters capture the current callable at each
original expression, before argument effects. Missing callbacks still evaluate
arguments and raise the original TypeError. Single-image OCR retains its existing
Exception handling; batch failures retain the existing per-image fallback. No new
retry or model-initialization lock is introduced.


Detection result extraction changes no settings or thresholds. Label maps remain
lazy providers. Existing specialized thresholds, geometry ratios, exact-count rules
and manual-type requirements retain their original defaults and evaluation timing.
Source manifest v101 includes all five migrated detection files, preserving source
coverage previously supplied by the monolithic root. New records use the actual
source fingerprint; historical snapshots and model bindings are not rewritten.

Legacy incoming workflow extraction adds no business configuration. Existing
automatic-decision admission, minimum free space and image retention settings retain
their defaults and read timing. Narrow providers read current request identity,
repository and paths; nothing caches a user or a database connection. Source manifest
v101 includes `text_inspection/incoming_execution.py`, the actual CLAHE/OCR input
orchestrator, without changing OCR parameters, business prompt versions or old snapshots.

Workflow callback getters resolve only at their original call expressions, after
preceding work and before argument effects. Missing callbacks retain argument
evaluation and the original exception or fail-closed projection. Request identities
and database connections remain transient; no new retry policy is introduced.

The OCR result-mapping getter preserves the original lookup after prediction and
before result truth/item access. Missing callbacks fail at the same point; no
extra OCR, rendering, parsing or serialization retry is introduced.

OCR/Beta extraction preserves the PP-OCRv6 medium model names and orientation
options, image thresholds, one-hour cache TTL and existing byte budgets. Limits and
request identity remain lazy providers. Manifest v101 includes the actual migrated input
and OCR orchestration files, `text_inspection/incoming_analysis.py` and
`text_inspection/beta_comparison.py`; stored fingerprints and business prompt versions
are unchanged. No new worker mode or setting is introduced.

Incoming-text store extraction adds no setting. Its three file paths, row adapters
and runtime repository selection remain late-bound. JSON records preserve original
input values rather than replacing them with normalized SQL rows; PostgreSQL keeps
its existing table constraints. Shared JSON formatting and exception behavior stay
unchanged. Prompt-source manifest remains v101; no model-input source moved here.
Decoder and JSON fallback capabilities preserve live callback replacement and
missing-callback ordering without eager validation, retries or backend fallback.

Comparison extraction keeps provider timeouts, external-media/automatic-MATCH
admission and the business prompt version unchanged. Prompt-source manifest v101
adds `text_inspection/comparison_submission.py`, which now assembles model input,
and `text_inspection_v2.py`, the actual strict-prompt definition previously absent
from the list. New fingerprints reflect both files; stored snapshots are unchanged.
Prepared jobs retain per-submission captured callbacks rather than later replacements.
Submission/review getter capabilities add no setting and preserve argument effects,
missing-callback failures and existing uncertain-result settlement. They do not
introduce provider, storage, postprocessing or audit retries.

Standard-route extraction introduces no configuration. Permission, account gates,
100 MiB import read limit, legacy PDF read-only responses, expected revisions and
preparation enablement retain their existing behavior. Identity and job providers
remain late-bound. Model-input producers stay in their existing modules and source
manifest v101 continues; stored task bindings and historical fingerprints are retained.
Provider getters resolve at the original call expressions, without eager caching
or callable validation. This includes exception-detail conversion and PostgreSQL
confirmation before projection; no new retry or cleanup policy is introduced.

Revision/projection/diagnostic extraction introduces no setting. Diagnostic limits,
logger replacement, public fields and expected-revision errors retain their values.
Source manifest is v101; these helpers do not move model-input producers.
New fingerprints change normally with listed source edits; old snapshots remain.
Diagnostic hash callback lookup and missing-callable errors retain their evaluation
order. An absent failure message does not obtain a hash callback.

Text media extraction introduces no setting or image-policy change. Provider
maximum side and JPEG quality retain their values and are obtained through explicit
getters at the original expressions. Passthrough never reads JPEG quality; resize
reads the maximum once for comparison and twice for thumbnail dimensions. Input
byte/pixel limits, 1.5x PDF rendering, image fast paths and error
messages remain. New source fingerprints use manifest v101 with the migrated media
and image sources; existing model versions, secret references and snapshots remain.

Text record callback factories add no configuration. Each operation obtains only
its required reader/writer/decoder; missing callbacks preserve their original error
ordering rather than silently choosing another persistence backend.

Text-record extraction adds no configuration. The JSON directory and table mapping
remain late-bound, as do the thread repository factory and shared reentrant lock.
No repository connection or request identity is retained on the store. Existing
string coercion, missing values and JSON-versus-PostgreSQL behavior are preserved.

Prepared comparison extraction adds no settings. Qwen resolution still obtains
document settings, attaches OCR settings to that same dictionary, then validates
both providers. Per-submission capabilities retain the submitted callbacks, model
admission flag and usage recorder; local MATCH commissioning reads account lists
at execution time. The prompt source manifest uses v101, but edits to listed
source files naturally change new fingerprints. Stored snapshots are not rewritten.

Preparation dependency extraction adds no settings. The existing preparation
account allowlist and external-model admission remain; the resolved settings object
is captured at submission, with no new deep-copy or immutability guarantee. Verified
history media retains its 120 MiB default. Provider timeouts and single-attempt
arguments remain unchanged; this is not the independent label-worker cutover.
The HTTP history port supplies a per-request writer factory rather than a global
connection; worker settlement retains its later callback lookup.

Extraction dependency ports preserve the existing account gates, external-VLM flag,
image/document model settings and single-attempt arguments. Upload reads remain
bounded at 10 MiB plus one byte; verified media reads retain the explicit 100 MiB
limit and evidence hash. No setting or model/prompt change is introduced.

Agent dependency extraction adds no setting or authorization. Commissioning still
reads `VANTALINE_WEBMCP_ACCOUNTS` dynamically and skips database access for excluded
accounts. Policy routes retain admin checks and strict request types; operation
inspection and cancellation keep their existing account/version constraints.

Document-job extraction preserves the existing classification account allowlist,
external-VLM flag and configured Qwen HTTPS checks. Settings are read before slot
acquisition and the same resolved settings object is passed to the background job;
transport and usage recording remain explicit, late-bound capabilities.

History extraction adds no configuration. The existing text-inspection permission,
account isolation, cursor validation and page bounds remain. Historical media uses
the bound revision/hash, private no-store caching and nosniff response headers;
diagnostics retain the same inspection permission rather than an added admin gate.

Codex dependency extraction adds no setting. Account admission and the configured
model continue to be read dynamically; capability queries do not require PostgreSQL.
Existing tasks remain readable/cancellable after account admission is removed, while
new work and retry retain their existing guards. Source hashes, request defaults,
report limits and omitted-versus-explicit import arguments are unchanged.

Label dependency extraction changes no environment setting. Configuration still
resolves `label` with an omitted reference before reading the enabled flag; submitting
a repeated request resolves its explicit stored reference, including None. Worker
claim handling retains its existing empty-reference legacy fallback. A missing model
service raises before processing; it never selects another model or replays a call.

Route-selection extraction preserves the existing `yolo`, `ai`, and `archive_only`
values and `apply=True` request default. Applying AI still calls profile preparation
with the item alone, then saves before AI-task upsert; non-applied AI still saves
the selected route. The retired `locate` route retains its existing 410 response.

Source preparation adds no configuration or prompt-content change. New task source
fingerprints use manifest v101, which includes the actual `accessories/preparation.py`
producer. Historical source fingerprints and model/secret references remain unchanged.
Existing crop limits, source ordering, default sizes and profile call flags remain.

Image-job metadata extraction adds no setting or ID conversion. Existing task,
model and secret-version references remain unchanged. New source fingerprints use
the versioned source manifest, including `accessories/image_job_metadata.py`; historical fingerprints
are never rewritten. Guide insertion/limits and strict file-read errors are preserved.

Gallery extraction adds no settings. Existing preview dimensions, alpha/gray
conversion, source/pose/sprite ordering, duplicate suppression, reference selection,
audit fields, metadata limits and per-request redaction are unchanged. Asset
normalization and prompt-producing callbacks remain in their original locations.

Management extraction changes no setting, form default or owner rule. Creation,
preview and confirmation deliberately keep their different worker-start conditions.
Confirmation retains its two profile-preparation calls and existing force flags.
Legacy JSON whole-accessory deletion currently returns 404 after pre-filtering its
configuration; this known pre-existing behavior is covered, not repaired here.

Accessory file-edit extraction adds no settings. Upload limits, crop coordinates,
shared-read-only permissions, reference-provider selection and media deletion
boundaries retain their existing behavior. No task binding or prompt producer moves.

Candidate persistence/retrieval extraction changes no setting. Load identifiers
retain their existing exact form; deletion trims them and generated record paths
use the existing sanitizer. GET may repair legacy job metadata before authorization;
provider execution is unchanged. Existing task model references are preserved.

Accessory catalog extraction introduces no settings. Existing member/admin
visibility, full-versus-summary payloads, source redaction, defaults and physical
dimensions are unchanged. Task prompt provenance uses the versioned source manifest,
including the extracted policy source; existing snapshots keep their old reference.

Record access extraction adds no settings. Only administrators may assign another
owner; existing special IDs bypass user lookup. Other targets are freshly resolved
through the existing auth-store path, including inactive accounts. The `legacy`
filter alias is not an owner-assignment alias. Storage failures are not hidden.

Record audit extraction adds no settings. Timestamp priority, integer truncation,
nonzero fallback and file-time behavior are unchanged. Audit projection does not
rewrite stored timestamps, owners or historical records.

Shared record policy extraction introduces no configuration. `legacy_admin` and
`system` retain their fixed owner meanings. The `legacy` alias applies to filtering;
owner assignment continues to use its existing rules. Shared read access never
confers write access, and administrative filtering remains enforced.

Authentication HTTP extraction changes no routes, response schemas, throttle
parameters or cookie attributes. Each application composition owns its limiter;
settings remain resolved at use time. Bootstrap/login only set a cookie after
persistence succeeds, and logout only clears it after the existing delete/save
path succeeds. Internal flow return values are not serialized to the client.

Session settings remain resolved at use time: cookie name, TTL and persist interval
keep their current values. Bootstrap environment reads remain dynamic. Extracted
middleware preserves early-denial responses, CORS order, security/cache headers,
media authentication and the exact public RunPod transfer path/method exceptions.

Authentication foundation extraction preserves password hashing format and
iteration configuration, session expiry/cookies, permission defaults, navigation
limits and JSON/PostgreSQL selection. No new setting or credential is introduced.

Analysis projection/publication extraction changes no model, prompt, threshold,
source-image path rule or display default. Ordinary detail responses still omit
raw model/debug fields; only the existing administrator detail path enables them.
The list retains its 40-item preview cap and detail retains the full item list.

Analysis record extraction adds no configuration. Its list/detail/delete and
retired LocateAnything endpoints preserve their schemas, query defaults and
permission behavior. Cross-owner read/delete remains hidden as 404; admin user
filters and owner-scoped media projection remain unchanged.

The extracted administrator cost ledger retains `/api/admin/api-cost-ledger`,
existing response fields and the `VANTALINE_RUNPOD_GPU_USD_PER_SECOND` override
(default `0.00026`, invalid/nonpositive values use that default). Missing provider
usage is not estimated and unknown models remain unpriced. No new setting or
permission is introduced. Compatibility exports in `server` are composition
adapters; domain tests replace typed source dependencies.

Label actual-photo reuse is browser-memory-only with no configuration flag or durable
browser cache. History uses the existing 1600px, JPEG quality-90 preview. Full-size
normalized images remain on-demand; this does not change model input compression,
original upload limits, provider settings, permissions or retention.

Label call diagnostics have no user-facing toggle or new environment flag. The existing
administrator-role check protects the diagnostics endpoint before repository access;
account ownership and inspection permission still apply. Runtime call evidence is
retained unchanged.

**Status: Authoritative**

PathConfigurationWorkflows assembles directories, persisted-path migration,
service paths and ApplicationConfiguration without reading storage during
construction. Initial defaults still save before migration; failed saves prevent
migration and failed migration leaves its completion flag unset. Protected PLC
configuration retains atomic mutation. Each composition owns its config lock,
authorization ContextVar and migration state; identity/repositories remain per call.

HTTP configuration/authentication request shapes now live in `schemas/` by domain.
This location change adds no configuration keys, validation rule or default value;
the assembled OpenAPI and real HTTP error baseline remain the compatibility gate.

Model dependency extraction adds no environment flag or model default. A missing
injected model resolver is a configuration error and cannot silently execute an
unbound task. Profile-version and secret references in historical records remain
immutable. New snapshots use a `source-sha256:v1:` fingerprint of the checked-in
source manifest and files; migration never rewrites old prompt fingerprints.

This document lists ownership and names, never secret values or production endpoints.

## Independent A + Evolving label detection

The Beta-style hierarchical back control uses frontend routes and requires no
runtime configuration or model setting changes.

- `VANTALINE_LABEL_INSPECTION_ENABLED=true`: enables new paid submissions/claims.
  Disabled or unavailable credentials still allow task/history reads and maintenance.
- `VANTALINE_LABEL_INSPECTION_KEY_FILE`: absolute restricted runtime file containing
  the explicitly authorized experiment Ark key. The shared billing account serves
  all users with inspection permission. Never include the key in frontend, Git,
  reports, diagnostics or request logs.

The endpoint is fixed to Ark Beijing `/api/v3/chat/completions`; the model alias is
`doubao-seed-evolving`. No browser credentials or per-user model override is exposed.
Temperature, thinking, tokens and stage timeout are fixed in the module. This
configuration does not change manuals, OCR preparation or Codex Beta settings.


## Configuration layers

`VANTALINE_QWEN_REREAD_ACCOUNTS` is a separate, default-empty owner allowlist.
It requires the existing Qwen OCR account gate and external-send authorization.
Submission freezes the reread version in request identity. It adds at most eight
advanced-region calls and eight text-only region calls using the pinned
`qwen-vl-ocr-2025-11-20`, within the shared 120s deadline. It does not select
qwen3.5, change standard preparation, or enable automatic MATCH. Empty the list
to disable new reread submissions; existing submitted attempts retain their snapshot.

- **Git-tracked defaults/contracts:** safe defaults, schemas, `release/plc-protocol.json`, dependency locks, migrations.
- **PostgreSQL runtime settings:** shared application records and workstation-specific PLC configuration/leases.
- **Restricted server environment:** database connection, provider credentials, runtime paths, trusted origins, release metadata overrides.
- **GitHub Environment secrets:** restricted deployment user/host, pinned SSH material, and deployment-only credentials.
- **Browser state:** workstation HttpOnly cookie, selected serial permission, active in-memory reader/writer and lease state.

Common backend variable families include `VANTALINE_POSTGRES_DSN`, `INSPECTION_AI_*`, `INSPECTION_CORS_ORIGINS`, and release/version inputs consumed by packaging. Exact accepted settings must be confirmed against typed server configuration before adding a value; examples are placeholders.

## Rules

Public navigation uses `/`, `/docs`, and protected `/workspace/*` on the same
origin; no new environment variable, domain or API credential is needed.
`VITE_ROUTER_BASENAME=/` remains the production setting; preview builds retain
their existing basename support. Public user documentation is static curated
content. API documentation is separate: `/api/docs` requires an authenticated
administrator (and keeps the handler's admin check), while `/openapi.json` and
`/redoc` remain admin-only. The website must not treat `/docs` as API tooling.

- Never commit `.env`, private keys, tokens, cookies, real DSNs, production addresses, customer data, or copied server environment files.
- Do not add a second configuration source for an existing setting.
- Server-wide settings belong in controlled environment/runtime configuration; workstation PLC addresses belong to the bound workstation record.
- Defaults must be fail-closed for external I/O.
- New configuration requires schema validation, permission definition, documentation, tests, and explicit behavior for missing/invalid values.

## Workstation PLC schema v5

The current preset is `mitsubishi_fx3ga_40mr` over browser Web Serial with fixed 9600/7E1, checksum including ETX, 500 ms timeout, zero retries, and a 200 ms input poll interval. Workstation-owned editable fields are `enabled`, `result_register`, optional `output_control_point`, `capture_trigger_enabled`, `capture_input_register`, and `capture_trigger_value`. Defaults are fail-closed: PLC and capture are disabled, input is D205, trigger is 1, result is D206, and Y is blank.

## Text inspection v2

Prepared Qwen comparisons request `response_format={"type":"json_object"}` with
thinking disabled on the existing correspondence model; unsupported models fail
without fallback. No extra provider/key or automatic retry is added. Full call
evidence is stored under existing account media ownership, with bounded bodies,
redaction and authenticated attachment downloads. No secrets enter application logs.
Display previews use a fixed 1600px longest edge, JPEG quality 85, 4:4:4; this does
not change OCR input resolution/encoding or the original evidence archive.

`VANTALINE_QWEN_OCR_ACCOUNTS` is a separate default-empty allowlist selecting the
actual-image Qwen OCR evidence path. It also requires the existing external-media
gate and resolved Qwen credentials. It does not change standard preparation or
other model settings. The existing Key must explicitly permit both the pinned
OCR model and the configured correspondence model. Only approved HTTPS Beijing
DashScope/workspace endpoints are accepted, with redirects/retries disabled.
`min_pixels=3072` is required by the verified OCR API; the 12,582,912-pixel bound
is explicit. Invalid, incomplete or unavailable results remain review-required.
This release intentionally cannot emit automatic MATCH for this provider; the
older local MATCH allowlist does not commission it. Keep recognition disabled
until approved real-image testing and release verification. Unknown cache entries
are retained and block paid replay; changing the standard is not a retry consent.
Matching policy v2 changes request fingerprints, not the OCR cache identity:
complete image-only evidence can be reused under the new existence rule, while
historical comparison results are never reinterpreted in place. Opted-in accounts
require a saved standard template; missing templates return 409 before model I/O.

`VANTALINE_STANDARD_PREPARATION_ACCOUNTS` is a default-empty account allowlist for
activation-time cleaning and reusable text/code templates. It additionally requires
the existing external-media authorization and configured visual model. Each source
gets at most one classification call; unknown calls are never replayed.
The same response may locate up to eight missing-text regions for local OCR,
with a shared 60-second supplementary budget; this adds no paid provider or key.
The region limit and area bounds are fixed validation constraints, not environment
overrides. Invalid responses remain reviewable without retries.
Manual edits call no external service. `VANTALINE_STANDARD_OCR_MODEL_DIR` must contain the
existing `PP-OCRv6_medium_det`, `PP-OCRv6_medium_rec` and
`PP-LCNet_x1_0_textline_ori` directories with inference.yml/json/pdiparams. Models
are not downloaded by requests. Missing local models leave the source reviewable.
`VANTALINE_STANDARD_ELEMENTS_MATCH_ACCOUNTS` separately commissions local MATCH;
keep it empty until independent accuracy and runtime gates pass. Neither switch
authorizes graphic matching or alters PLC/other inspection configurations.

`VANTALINE_DOCUMENT_CLASSIFICATION_ACCOUNTS` is a default-empty account allowlist
for DOC/DOCX classification. It also requires the external-media gate and the
existing configured Qwen visual model/key from `ai_detection_settings()`.
Each unique image has at most one call (60s timeout); two document workers per
application process are allowed. Busy/unconfigured imports show the reason and
allow explicit later start. PDF is unchanged. No other model/key fallback exists.

`VANTALINE_DOC_IMAGE_BUNDLE` points to the fixed POI 5.5.1 helper bundle built by
`scripts/build_doc_image_extractor.py --output <directory>`. Java 11+ is required
at runtime (use a supported patched JRE); building additionally needs javac/jar.
The bundle manifest verifies every jar's SHA-256 and the helper source version.
No download or model call occurs in the Java helper, and credentials/JVM injection
environment variables are not inherited by the helper. No LibreOffice, fonts,
bubblewrap or DOC-to-DOCX conversion is required. The earlier converter flag is
unused. Limits: 30MB DOC, 500 images, 30MB per image, 100MB total output, 256MiB Java
heap and 30s timeout; one concurrent import per application process. This is not
an OS security sandbox or a bound on total JVM RSS. Missing bundle returns 503.
DOCX/PDF retain their existing 100MB bound. Original DOC hashes govern deduplication.

`VANTALINE_LABEL_BBOX_ACCOUNTS` is a separate, default-empty account allowlist for `vlm_bbox`. An account must also be in `VANTALINE_LABEL_EXTRACTION_ACCOUNTS`. Availability requires the external-media gate and a configured Qwen result from the same `ai_detection_settings()` resolver used for label comparison. There is no new key/model source or browser-supplied endpoint. One task freezes these resolved settings; the experimental timeout is 180 seconds, one attempt, temperature 0.1, 512 output tokens and `enable_thinking=false`. The timeout overrides only this method, not the comparison settings. Never activate based on synthetic tests alone.

`VANTALINE_LABEL_EXTRACTION_ACCOUNTS` is a comma-separated allowlist of authenticated account IDs; empty disables the new extraction UI. The extraction capabilities route reports availability without keys. AI masks use the existing image-generation provider/model/key, require the existing external-media gate, and disable provider format-retry fallback for this one-call path. Missing image-generation configuration leaves explicit manual polygon extraction available. Qwen text comparison keeps its existing separate settings. Enable the initial account only after synthetic extraction and manual-confirmation acceptance; do not infer image-generation availability from the text model's configuration.

The feature uses the existing authenticated AI provider configuration and `inspection` permission. No provider key or media is stored in Git. Legacy `.doc` image extraction requires the configured POI bundle, not an office converter. External image sending defaults off and requires `VANTALINE_TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=true`; automatic label match and manual-book pass have separate commissioning flags. Missing flags, provider failure, invalid JSON and uncertain charging always return review-required behavior.

The backend returns resolved protocol addresses and an immutable `capture_read_plan`; these are diagnostics/authorization output, never user input. Account logout does not delete the workstation cookie or configuration.

## WebMCP development commissioning

`VANTALINE_WEBMCP_ACCOUNTS` is a default-empty comma-separated account-ID allowlist.
The developing browser surface also requires an enabled policy in PostgreSQL;
admin-only `/api/agent/policy/{account_id}` GET/PUT manages versioned policy records.
The new migration must exist before an account is allowlisted. Keep production
activation off: existing business/worker paths do not yet all enforce this policy.
A persisted budget or provider ID list is not a platform-wide safety guarantee.
See [implementation status](agent-platform.md) for the remaining release gates.

## Codex comparison worker

`VANTALINE_CODEX_COMPARE_ACCOUNTS` defaults empty. `VANTALINE_CODEX_COMPARE_MODEL`
is a deployment-pinned concrete account model; effort is high. Worker-only
`VANTALINE_CODEX_COMPARE_BINARY`, `_AUTH_HOME`, `_WORK_ROOT`, `_MEDIA_ROOT`
configure native runtime, private login, scratch and shared evidence. PostgreSQL
uses the existing `VANTALINE_DATA_STORE`/`DATABASE_URL` selector. No API key is
injected into the child. Full paths, auth and isolation requirements are in
[Codex beta](codex-text-compare.md); examples contain no secret values.

Optional worker-only `VANTALINE_CODEX_COMPARE_PROXY_URL` accepts only a credential-free
`http://127.0.0.1:PORT` local proxy. It explicitly enters the cleared sandbox as
HTTP(S) proxy variables with fixed localhost bypass; generic host proxies are not
inherited. Empty preserves direct behavior. See the Codex commissioning guide.

Label import decoding/size failures are user-visible validation results and do not
change model configuration or trigger any provider request.


Fixed/fullscreen label workspace layout requires no server settings. Browser fullscreen
is gesture-gated; its refusal does not disable detection. The 28% result-dock size is
local component state and bounded to 20-45% when resized, with a small viewport minimum.
No model, prompt, storage or shared Fullscreen API permission configuration is changed.

Native file pickers can exit browser fullscreen (including macOS Edge). The label
workspace remembers fullscreen only for that picker gesture and attempts restoration
on file selection while transient user activation is available. Cancellation, explicit
exit and navigation clear that intent; upload completion never forces fullscreen.
When restoration is unavailable the fixed viewport and manual toggle remain usable.

Compact label issue rows and numbered overlays are frontend presentation only and require no new settings. They preserve saved model results, confidence, evidence coordinates and prompts; details are available from each row.

Label comparison now declares image_input_normalized_v2 in its prompt and result. No new environment setting is needed. Prompt hashes freeze this contract at submission; new runs use the corrected coordinates, while legacy results retain their original evidence. Model, two-call count and limits are unchanged.

## Label quality policy

The release-owned `label_inspection/quality.py` policy `black-label-quality-v1`
is mandatory for new A + Evolving runs; it has no browser/account bypass or runtime
threshold override. Submit freezes its version and CONFIG hash. Changing rules or
thresholds requires a tested immutable release; incompatible queued policy fails
before provider I/O. The model/key/encoding settings above remain unchanged.

Initial parameters use a 1000px detection view, 300px score view, 4x4 internal grid,
200px minimum short side and focus threshold 1000. A candidate is rejected for
blur only when both overall and active-block median Laplacian variance are below
threshold. Fewer than four active blocks are unassessable. Values are tied to this
implementation/scaling, not generic sharpness scores. Unsupported localization
fails closed; expected first-release coverage is dark labels on lighter backgrounds.

Label standard-image imports use fixed existing image limits: 10 MiB and 16 million pixels. Accepted static formats are JPG/JPEG, PNG, WebP and BMP with extension/decoded-format agreement; animations and HEIC/HEIF are rejected. No new runtime setting or model configuration is introduced. Word limits remain DOC 30 MiB, DOCX 100 MiB and 500 standard entries.

## Versioned model profiles and purpose bindings

Administrators use Settings → 模型与 API to choose one saved model/Key object
per purpose. Creating a profile does not bind it: the main Save commits all
purpose selections with an optimistic revision, returning 409 on stale edits.
The advanced library supports multiple keys for the same model and shared use
across purposes. Only administrators may list, test or mutate this library;
legacy ai_config/agent_config permission grants do not bypass role checks.
Old configuration writes return 409 and direct users to the profile library.

`/api/admin/model-profiles` is the metadata API (GET/POST); `/{id}` PUT appends
an immutable version, `/{id}/test` POST tests saved credentials, `/bindings` PUT
atomically saves selections, and `/usage` GET returns the last 500 recorded calls.
No API returns raw keys. Key/endpoint/model edits clear prior connection status.
Unbind a profile before disabling it; old versions and secret references remain
available to previously submitted jobs. There is no destructive secret deletion.

The first read migrates effective legacy AI, image, training assistant and label
settings, including their effective environment overrides. Remaining saved keys
without a known model become disabled pending profiles. Migration retains the
training assistant enabled gate and operational defaults. After migration, legacy
settings/environment values no longer override purpose bindings. Existing external
call/account feature gates remain authoritative and are not enabled by adding a key.
Dedicated OCR accepts only the pinned Qwen OCR model; document preparation keeps
its existing Qwen-compatible requirement. Existing migrated bindings are retained.
Connection tests use metadata endpoints; success does not certify model accuracy.


## Unified PDF inspection

PDF import accepts at most 200 MiB and 500 split entries. Configure the site multipart request body allowance above 200 MiB (installer uses 201m); other application file limits remain enforced. PDF comparison fixes Evolving/disabled thinking/0.1/180s, 3200 JPEG90 and 1024/8192 output limits. It resolves the existing label profile credentials but requires Doubao and freezes its profile revision. The former manual profile no longer starts new comparisons.


PDF result compatibility: optional `consistentItems` entries may be strings or objects with a string `description`. Only that non-decision summary is normalized; raw provider evidence remains immutable. Missing/invalid descriptions and contradictory difference decisions still fail closed. Label parsing, PDF prompts, image inputs and model settings are unchanged. The PDF scope caption refers to page content rather than other labels. A regression covers enriched agreement summaries, input immutability and contradictory results.


## Fixed-reference model read transaction

Fixed-reference model resolution and the admin usage-call list use short PostgreSQL read transactions. An explicit version remains pinned across later edits and secret rotation. A concurrent uncommitted connection-test update or call is not visible until commit; a reference to a still-uncommitted new version can fail with the existing missing-version 503 before that commit. This changes no configuration key, binding default, prompt-source manifest, stored snapshot, or migration.


## Model registry initialization fast path

The model registry warm-start check now reads committed state without taking the global advisory lock. A missing or falsey state still uses the original locked migration with an in-lock recheck. No setting, default, stored binding, snapshot, secret reference or prompt-source fingerprint changes. External secret writes made before a failed database migration retain their existing non-transactional behavior.

## Model task snapshot read transactions

No configuration value changes. The task snapshot and historical-record state reads use short PostgreSQL read transactions after registry initialization. The original append-only profile versions, binding configuration, prompt-source fingerprint, secret references and admin write validation are unchanged.

## Model admin public read transaction

No model setting, default, binding, permission, secret reference or prompt-source fingerprint changes. The administrator model-library GET projection uses a short PostgreSQL read transaction; writes and connection-test registration still use the existing serialized write transaction.

## Label list-only run payloads

No operator setting, source filter, model binding, media permission or cursor format changes. The first-page label task list transfers fewer fields from native run rows; task detail and previously created 15-minute cursor snapshots remain unchanged. New tasks naturally record the prompt-source fingerprint of the changed shipped API/storage files; historical fingerprints and model bindings are not rewritten.


## Opt-in COS file storage

`VANTALINE_FILE_STORE` defaults to `local`; `hybrid` reads an unmapped legacy file
locally and `cos` never falls back for mapped business roots. Tombstones never fall
back. Production must remain local until the complete disk-independent gate passes.
Nonlocal modes require `VANTALINE_DATA_ROOT`, `VANTALINE_ARTIFACT_WORK_ROOT`,
`VANTALINE_ARTIFACT_CACHE_ROOT`, `VANTALINE_COS_BUCKET`, the existing `DATABASE_URL`,
and systemd-provided `CREDENTIALS_DIRECTORY`. Work/cache live outside the logical data root. The software-only compatibility mode keeps
these on one filesystem. Production cutover requires the hard-limit layout below,
where the business configuration and volume backing files reside on the system disk.
The region is `ap-hongkong`, transport HTTPS and new storage class STANDARD.

Each service uses `LoadCredential=cos-credentials.json:<restricted source file>`;
the JSON has `COS_SECRET_ID`, `COS_SECRET_KEY` and optional `COS_SESSION_TOKEN`.
The runtime rejects symlink/nonprivate credential files. Never place values in Git,
normal environment configuration, logs or reports. Web and worker share a restricted
Unix group and group-writable control/cache directories; configuration is fixed until
restart. Initial fixed budgets are cache 6 GiB, work 12 GiB, upload 2 GiB and an
8 GiB free-space floor. Only one work reservation runs at a time.

The image/native-read adapter slice adds no settings. It uses the same opt-in file store and existing account/root boundaries. Native reads hold links to read-only cache blobs under the cache scratch root; the links contain no second data copy and are removed with their process lease.


For production cutover, `VANTALINE_ARTIFACT_HARD_LIMITS=1` and
`VANTALINE_ARTIFACT_UPLOAD_ROOT` select three fully preallocated local ext4 loop
volumes (cache 6 GiB, work 12 GiB, upload 2 GiB). These are temporary system-disk
filesystems, not a COS mount or a new cloud disk. Work/cache/upload are direct
children of the same state directory; `volumes/<kind>.ext4` backing files must
be private, fully allocated and on the system disk. Startup verifies mounts and
backing sizes. Ext4 metadata reduces usable capacity slightly below each limit.
Set `TMPDIR=<upload root>/spool` for both services. Multipart admission reserves
the declared length before parsing, requires Content-Length, and leaves room for
the simultaneous durable publication copy. Chunked ordinary multipart uploads are
rejected; RunPod's separate bounded raw-upload protocol is unchanged.

Native image generation uses `VANTALINE_IMAGE_CODEX_BINARY` and
`VANTALINE_IMAGE_CODEX_AUTH_HOME` (a dedicated private, existing Codex auth home).
The isolated child receives a private working copy of that runtime's auth/config,
never COS credentials or application configuration. Native image and comparison
workers require hard limits in COS mode, hold the shared exclusive work lease,
and publish results before completion. Missing runtime authentication fails before
a paid invocation. Keep both services' KillMode=control-group and mount dependencies.
## Label consumer lifecycle

Label consumer lifecycle introduces no setting, model choice, default, permission or secret change. Source manifest v134 has 343 actual source entries, including the consumer and Web adapter; new task provenance follows those sources without rewriting historical snapshots. The 480-second drain budget is an application wait limit, not a cancellation deadline or proof of the host systemd stop budget.

The label batch/payload benchmark diagnostic output adds no runtime setting. It uses the existing isolated `VANTALINE_POSTGRES_DSN` test database and emits synthetic timing, memory and payload-size values only; the DSN and records are never printed.

The existing VANTALINE_FILE_STORE setting also governs shared file checksums used by startup guide provenance and training metadata. No additional hash setting or local fallback is introduced; COS reads use a pinned, verified cache file.

The controller bridge adds no business configuration or worker-mode override. `--capabilities` is a read-only installed-controller probe. A future external topology requires an already-running protocol-1 embedded bridge and a non-null shared configuration revision; both roles must agree on that revision. The preceding managed bridge emitted schema-2 embedded with runtime protocol 1 and the sole Web service. The external activation below adds the separate worker service.

Rollback pauses the candidate before waiting for its active runs and admitted iterations to finish; it preserves queued rows without starting paid work on an unaccepted build. A forward switch from an already-paused predecessor also retains its backlog and pause intent. An active predecessor still drains its queue before a normal forward switch. State-machine and rendered-installer faults cover queued legacy-to-managed rollback and paused-backlog transitions; queued work is not evidence of an active call.

## Managed embedded label control

The protocol-1 embedded label runtime is selected only by an exact schema-2 embedded package manifest matching VERSION and the active release pointer. No environment variable can enable a second label consumer. Source checkouts and schema-1 packages retain their existing lifecycle. The control directory is private, sockets are mode 0600 and accept root peers only. No credentials are returned in state. Source manifest v139 covers 362 actual files; historical model/profile snapshots and secret references remain immutable.

The control endpoint owns a dedicated PostgreSQL connection factory with explicit connect/TCP failure-detection settings; request and paid-task connections retain their configuration. SQL timeouts apply after connection, and the root client has a separate bounded acknowledgement deadline; these do not constitute a hard total deadline for every driver operation. A control-thread shutdown timeout retains its role lock and fails that controller generation until process restart. Regression probes block connection creation and verify no duplicate role, then release the old thread for cleanup. A real claim/processing-substitute/cleanup integration proves pause does not acknowledge drain until two admitted iterations finish, while queued task snapshots remain unchanged.

The label batch benchmark statistics preparation has no environment flag or production setting. ANALYZE is scoped to its generated synthetic schema before measurement; existing read/write lock, pagination and model-snapshot settings are unchanged.

## Proposal: shared label runtime configuration preparation

The preceding embedded configuration bridge introduced a bounded data-only snapshot of the existing label/database/storage/network settings, exact existing model-secret environment references and data directory. Unset and explicit empty values remain distinct. COS credentials are represented by their byte digest and transferred only through a private root-authenticated path; a worker must receive its own systemd credential directory. The pure contract and private-file roundtrip tests use synthetic values. The candidate Web wiring can capture a configuration revision and export its immutable snapshot only through the private authenticated control socket; public status contains only the revision. A prepared root file publisher writes immutable private versions and restores one atomic current pointer. The installed helper now embeds the audited data-only contract, captures a peer/build/instance-bound private export before external transitions, and journals the previous configuration pointer before mutation. It restores that pointer with the complete release on rollback, derives escaped mount dependencies and provisions the worker own systemd credential from root-owned bytes. No candidate application module is imported by the isolated root helper. Tests cover pointer interruption, export tampering, private modes, standalone execution and synthetic installer recovery. That bridge release retained embedded execution. Its complete-release acceptance is a prerequisite for the external activation described below.

## Proposal: standalone label process

The candidate `label_inspection.runtime` bootstrap reads the root-owned immutable configuration and its own systemd credential, checks the active package build/topology, initializes local storage, and creates separate thread-owned business and control repository factories. It imports no Web application. The existing model service is reused through an existing-registry reader: missing registration fails startup rather than migrating legacy settings. Secret-file syntax, environment precedence, immutable version references and usage accounting remain unchanged. Manifest v141 names 366 actual sources; historic snapshots are not rewritten.

In external mode, Web composition owns admission/control only and constructs no label consumer. The standalone process owns the existing two-thread consumer and its exclusive role socket; SIGTERM/SIGINT stop new work and use the existing 480-second drain budget. Real isolated PostgreSQL tests cover old-model resolution after settings changes and reader recreation, actual child PID/peer checks, duplicate-role rejection, signal drain and controller-driven embedded-to-external acceptance, failure and complete rollback. Synthetic model values and local storage are used; no paid inference or PLC call occurs. The bootstrap-only predecessor did not enable an external release. External activation remains conditional on preceding complete-release acceptance and final exact-build validation as described below.

The unauthorized control-socket regression accepts EOF, connection reset or broken pipe only on the denied-peer path, asserts zero handler calls and unchanged durable maintenance state, and forces EOF-before-send to cover early rejection deterministically. Authorized commands retain their strict response contract; runtime socket behavior is unchanged.

## Proposal: label runtime monitoring

Managed processes publish bounded heartbeats on the existing private control thread with a five-second target interval after the previous tick completes. Database work and control requests can delay a tick. Each uses the dedicated thread-owned connection factory. The operational table stores only build/configuration/process identity, worker state, process-lifetime counters and fixed recent-error codes. A blocked heartbeat retains the same role lock on shutdown timeout. The private deployment protocol remains unchanged.

`GET /api/label-inspection/runtime` requires administrator access before any database call. Its short unlocked READ COMMITTED transaction samples state, queue and heartbeat in separate statements; these are not an atomic health snapshot. It returns queue/active counts, oldest queue age, maintenance/pause intent and expected-role heartbeats; missing, mismatched or older-than-15-second samples are unhealthy. Heartbeat freshness is sampled liveness, not a guarantee against a subsequent crash. Lock acquisition counts/total/max wait include successful and timed-out acquisition attempts. These and rejected duplicate submission/stage-call counters belong to the process lifetime: process restart resets them, while a control restart within the same process changes the instance but retains counters. Idempotent replay is not counted as rejection. Errors never include exception strings, media, customer fields, secrets or filesystem paths. Real PostgreSQL/HTTP tests cover authorization, redaction, actual lock contention, duplicate refusals, stale generations and heartbeat shutdown. Manifest v142 names 367 actual sources. The observability-only predecessor retained embedded execution; the external activation below is a separate release and requires acceptance of every predecessor.

The administrator runtime endpoint is registered in the exhaustive tested label-route guard set. The assembled authentication regression exercises anonymous 401, member 403 (including a synthetic stored inspection/system-settings over-grant), administrator 200 and zero monitor access on rejection. Endpoint-local admin authorization and public error formats remain unchanged; no broad route exemption or additional feature grant is introduced.

## External label topology selection

Independent label mode is declared by the immutable release topology, not a mutable
business setting. Web exports a bounded revision-bound configuration through its
private authenticated control socket; the installed controller publishes its private
version and provisions the worker credential/mount dependencies. The worker must match
that configuration and build before detection admission is restored. Existing model
secret references and unset/empty environment distinctions are preserved.

The label detail-read optimization adds no configuration. Model-binding request lookup remains fenced; only the pure get-by-owner/id/kind path becomes an unlocked committed read.

PLC domain extraction introduces no setting or API default. Workstation configuration and request identities still use their existing call-time dependencies; no shared database connection or current-user value is stored in the new services. Strict request schemas retain defaults, extra-field rejection and field validation.

Auto-optimization extraction adds no setting, model default, permission or worker mode. Source manifest v144 appends the 37 actual new training source files (424 entries). New task fingerprints use these sources; existing task snapshots, bound model versions and secret references are not rewritten.

Pipeline workflow extraction adds no configuration, permission, model default or worker mode. Source manifest v145 appends the twelve actual new pipeline source files (436 entries). New task fingerprints identify these sources; old snapshots, model bindings and secret references remain unchanged.

Accessory image workflow extraction adds no configuration, provider default, worker mode or permission. Source manifest v146 appends the twenty-two actual new source files (458 entries). New task fingerprints follow these files; historical snapshots, model versions and secret references are unchanged.

Configuration/status extraction changes no setting, permission, provider selection, model default or worker mode. App-config missing primary still uses defaults, while exhausted transient reads can use backup. Ordinary JSON saves retain current PLC-protected fields; the existing ContextVar-authorized path can change them. PostgreSQL preserves protected keys in its existing transaction. Missing local model-config files return a shallow defaults copy before normalization; recognized-key save and chmod/replace behavior are unchanged. Source manifest v147 adds nine actual files (467 entries); historical snapshots and secret references remain unchanged.

Pure label projection extraction changes no settings or model binding. Source manifest v148 appends the actual projection source (468 entries); historical snapshots are not rewritten.

The optional post-settlement summary publisher adds no environment setting. Its
fixed proof bounds are compatibility constraints, not user tuning knobs.
`summary_publication_failed` is a fixed operational error code; it contains no
exception text, row identifiers, credentials or paths. Manifest v149 includes
470 actual sources, including the proof and row-lock publisher. Historical model
references/fingerprints and provider/prompt selection remain unchanged.

The label list cache reader introduces no setting or worker-mode change. It requires the additive projection table/invalidation migration and source-first publisher from earlier accepted releases. It recognizes projection version 1 only; unknown or missing versions fall back without rewriting records. Prompt-source manifest v150 contains 471 actual files, including the startup prerequisite and records the changed repository source for new tasks; historical task snapshots are unchanged.

Reader startup now verifies the actual business connection and effective PostgreSQL role, including existing libpq environment settings. The installer migration identity alone is insufficient. Manifest v150 additionally includes `label_inspection/readiness.py` (471 actual sources); historical fingerprints are unchanged. No new environment variable, automatic grant or database selection fallback is introduced.

Synthetic lifecycle tests replace the explicit readiness capability rather than disabling it through an environment flag. Production startup always retains the actual database check when a PostgreSQL repository is selected.

Reader benchmark evidence v1 adds no runtime configuration or reduced-repetition switch. Its fixed three A/B repetitions and separate A/A control use only the existing isolated-test PostgreSQL DSN; diagnostic output omits SQL, parameters and credentials.

Service-path extraction adds no setting. Manifest v158 includes both actual runtime source files (479 sources). Existing stale-prefix handling, output layout and legacy/system/admin shared placement remain unchanged. Owner values retain the existing trusted-caller contract; this is not a new untrusted-path validation API.

Read-cache ownership preserves the existing five-second store TTL and file generation/size or mtime/size keys; it adds no setting. Returned payloads remain shared read-only-by-contract values. Manifest v158 appends the actual cache module (479 sources); historical model snapshots remain unchanged.

Directory lifecycle ownership adds no setting or data migration. It preserves the existing startup/on-demand path migration and default-config behavior. Manifest v158 includes the actual lifecycle source (479 files); historical model snapshots remain unchanged.

Foundation policy relocation retains flag vocabulary, arbitrary defaults, text slicing, box integer coercion and image rounding. Manifest v158 includes 479 actual sources; task snapshots and secret bindings are not rewritten. The permissive provider proxy flag policy is separate and unchanged.

File digest and name relocation adds no settings. Digest reads remain 1 MiB chunks with OSError mapped to None; naming retains its existing clock, UUID prefix, stem truncation and suffix fallback. Manifest v158 retains 479 actual sources and leaves historical snapshots unchanged.

Repository access relocation adds no datastore configuration or fallback. Selector failures retain the existing 503 codes and messages; count-probe failures expose only the exception class. The existing 16-character connection fingerprint remains process/thread scoped. Manifest v158 records the real module (479 sources); historical snapshots stay intact.

Protected configuration ownership changes no defaults, protected keys or setting. PostgreSQL mutation retains the namespace transaction and a fresh configuration load while the shared local RLock remains held. JSON mutation still rejects unprotected changes before authorizing a protected save and resets the previous ContextVar value in finally. Private root load/save rebinding no longer redirects these internal owner calls; replace actual typed ports for tests. Manifest v158 fingerprints the updated existing modules (479 paths), preserving historical task snapshots.

Historical integration record (before PR266; not the current bundled architecture): That foundation integration followed the accepted reader-readiness source manifest and retained its prerequisite. Its bundled manifest was v157 with 479 unique sources (including `label_inspection/readiness.py`); historical slice counts above refer to their original isolated candidates. The existing fixed reader benchmark protocol remained mandatory; that historical candidate did not include native-history aggregation. The current integration retains the native-history implementation accepted in PR266.

Native label history count/latest is an internal list-read optimization with no
new setting. It uses the same versioned derived proof and is disabled per task
when proof coverage is incomplete or any same-batch task identity links to legacy
history. No model selection, prompt, concurrency, permission or worker mode changes.

Late JSON projection in native history reads introduces no configuration switch,
operator tuning requirement or model change. Existing reader startup checks and
worker-mode/maintenance configuration remain authoritative.

History result column-name reuse is confined to a single query result. It changes no configuration, schema, API or worker topology; whole-release rollback and snapshot/call evidence retention remain unchanged.

Native list-history fallback now compacts a nonempty `quality` object only when every immediate value is a JSON string, boolean or null. This matches the existing public checked marker while avoiding unnecessary evidence transfer. Numeric and nested values stay intact so JSON decoding errors remain visible; other fields, ordering, detail payloads and old snapshots are unchanged. PostgreSQL/HTTP regressions cover flat Unicode/string/bool/null, empty and other shapes, and bounded-decoder failures. The original complete performance protocols and thresholds remain mandatory; private diagnostics are not acceptance.

The current native-history integration retains the accepted foundation and readiness modules. Its bundled manifest is v158 with 480 unique sources. Historical counts above describe earlier isolated slices. The original 47 reader/history cases and both frozen baselines remain required; legacy/manual/Beta SQL aggregation is not completed by this native slice.

Account and name policy extraction changes no permission, setting, normalization, default or concurrency policy. Manifest v163 appends the four actual source files (488 total); historic snapshots are unchanged. Naming remains the existing caller-coordinated read/check/write flow, without a new atomic uniqueness guarantee.

Public network policy extraction adds no setting and changes no origin allowlist, regex, private-host classification or path filtering rule. Manifest v163 adds both actual source files (488 total). Existing policy is intentionally preserved; these public display filters are not a new comprehensive URL/path sanitizer.

OpenAPI/Swagger/ReDoc paths, hidden-schema registration, admin-only 404 guard and middleware permission responses are unchanged. OpenAPI generation still uses version 1.0.0 and the current provided app routes/title; the existing truthy cache is reused only after authorization. Captured auth/policy functions are stable capabilities: replacing private root names no longer rewires documentation endpoints. Manifest v163 includes auth/docs_api.py (488 sources), preserving historical task fingerprints.

Authentication composition retains live suppliers for data paths, password cost, cookie/session durations, login limits, legacy owner and the thread repository factory. The graph captures internal method capabilities; arbitrary rebinding of private root auth helpers or its former write-lock name no longer reconfigures it. No auth settings or permissions change. Source manifest v163 records auth/composition.py (488 sources); historical task fingerprints are preserved.

Authentication HTTP construction accepts the identity already owned by its authentication graph and rejects a mismatched identity. It calls no settings, database, identity or visibility providers during construction. Session settings, repository selection and request identity retain their existing per-call behavior; only stable internal service methods replace entry callbacks.

The earlier identity-only candidate used manifest v162/488 on fac841. Its PR265 latency failure remains a recorded NoGo; those results do not approve this new integration.

This identity integration is rebuilt on main734e5e0 after PR266. It retains native-history SQL, readiness and all47 fixed reader/history cases byte-for-byte from that main. The complete manifest is v163 with489 unique sources; earlier slice counts are historical. This changed prerequisite requires fresh integration, hostedCI and release acceptance and does not explain or waive PR265 performance failure.

Provider proxy extraction changes no proxy environment precedence, configuration default, Gemini-only auto-local probe, timeout or retry policy. Manifest v169 includes both actual proxy modules (494 sources). Existing task snapshots and secret references are untouched.

MCP client relocation changes no runtime default, environment option or wire protocol. In-process remains the default and stdio remains opt-in. Manifest v169 adds the actual MCP client source (494 entries); historical snapshots are untouched. Direct construction of the client now requires its three explicit dependencies.

MCP environment parsing still happens per call, with any nonempty INSPECTION_AI_MCP_SERVER_MODE taking precedence and legacy enabling checked only after unrecognized runtime values. Policy source is now the provider module: arbitrary rebinding of the root mode function or mode constants is intentionally not a configuration mechanism. Payload encoder and size/quality suppliers are evaluated at their original operation points. Manifest v169 records the actual module (494 sources), preserving old task snapshots.

Model warmup keeps identity and scoped configuration evaluation before model ID validation, two readiness checks on the local-model path, and the existing remote-model skip response. Captured capabilities deliberately replace private root-name rebinding; callers read current identity/configuration at request time. The start adapter resolves the supplied runtime worker after its enable check. No model, settings, timeout or concurrency policy changes. Source manifest v169 includes the two actual warmup modules (494 paths); old task fingerprints remain unchanged.

The local model selection owner is `detection/local_models.py`. `INSPECTION_YOLO_DEVICE` remains read on each call; a nonempty stripped value bypasses torch detection. Otherwise CUDA availability selects integer `0` or `cpu`, with ordinary detection errors falling back to `cpu`. `INSPECTION_DETECT_BASE_MODEL` remains captured at application startup; fallback checks root/application `yolo26s.pt`, root `yolo11s.pt`, then root `yolov8s.pt`, and returns `yolo26s.pt` when absent. Selection itself does not download weights.

Image payload relocation adds no settings or decoding policy. MIME fallback, base64 validation, top-level key precedence and nested candidate order remain unchanged. Prompt-source manifest v169 retains 494 real sources; historical snapshots are not rewritten.

Historical integration record (before PR266; not the current bundled architecture): That model/provider integration followed the accepted reader-readiness source manifest and retained its prerequisite. Its bundled manifest was v168 with 494 unique sources (including `label_inspection/readiness.py`); historical slice counts above refer to their original isolated candidates. The existing fixed reader benchmark protocol remained mandatory; that historical candidate did not include native-history aggregation. The current integration retains the native-history implementation accepted in PR266.

This model/provider integration is based on main ad1292a after PR267 and preserves the native-history and reader-readiness implementation accepted in PR266. Its production and test sources match the independently reviewed model candidate 63df072. The complete bundled manifest is v169 with495 unique sources; earlier slice counts describe isolated candidates. Both fixed reader19 and history28 benchmark gates remain mandatory. Publication requires acceptance of the identity release, followed by this candidate’s own CI and independent review; the prerequisite’s first main CI AA failure remains recorded.

The local selection test portability correction changes no configuration, model selection, prompts or production source. Existing selection defaults and snapshot fingerprints remain unchanged.

Detection task request extraction adds no setting, permission or transaction policy. Manifest v172 includes the two actual source files (501 total); historical task/model bindings are unchanged. The service resolves account identity and thread repository on each call.

Detection rule relocation preserves all current defaults and clamping, including the distinct projection and update count behavior. It introduces no setting or validation rule. Manifest v172 includes two actual rule source files (501 total); historical snapshots remain unchanged.

Camera request relocation adds no setting, permission or retry policy. Manifest v172 includes the two actual camera workflow sources (501 total); historical model bindings and source fingerprints remain untouched.

Rule configuration paths, schemas, authorization middleware, validation and persistence order remain unchanged. Rule methods capture their supplied callable capabilities at domain composition time; arbitrary rebinding of server rule/config helper names no longer rewires that instance. The captured callables still load current config and request identity on every request. The existing mapping and clock are references, not copied snapshots. Source manifest v173 includes detection/rule_api.py (501 sources), without rewriting existing task fingerprints.

This detection integration retains the native-history and reader-readiness implementation accepted in PR266 and the identity release accepted in PR267. It is based on actual main bea11ce from PR268, retaining its Python-version-independent model-binding test fix. Main CI and release acceptance for PR268 must precede publication. All detection production and test sources, including the ordered application entry, match the independently reviewed detection candidate183f739. The complete bundled manifest is v173 with502 unique sources; earlier slice counts are historical. Fixed reader19 and history28 protocols remain mandatory; prior performance failures remain recorded.

Analysis composition adds no setting or API. Paths, repository factories, identity, cache scope and external policy callbacks remain operation-time suppliers; captured defaults and batch limit retain their previous values. Query presentation now captures domain methods, so private root presentation-name rebinding no longer rewires it. Manifest v174 records analytics/analysis_composition.py (503 source paths), without rewriting historical task fingerprints.

This analysis candidate retains the native-history/readiness implementation and accepted model composition from main bea11ce. It is prepared after detection candidate af8d242 in PR269; actual-main rebind and detection release acceptance must precede publication. Analysis production/tests and the ordered entry match reviewed59db3d3. The bundled manifest is v174 with503 unique sources. The original history28 and reader19 benchmark protocols remain mandatory; recorded prior performance failures are retained.

Dashboard task ownership adds no operator configuration or model-selection policy. New task fingerprints use manifest v175 over the unchanged 504 source paths; stored task snapshots remain intact. Name/source and other required capabilities are selected at operation time.

Accessory selection/dimension relocation adds no setting or size normalization. Original known-key precedence, minimum pixel sizes, numeric coercion and fallback behavior remain. Source manifest v175 contains 504 entries, adding the catalog source newly used by moved selection functions; historical snapshots stay unchanged.

Accessory workflow ownership adds no settings. Job matching still repairs IDs before matching, readiness still uses the same short-circuit/force policy, worker status merges only after mutation returns, and first-source selection preserves list order. Private root helper rebinding no longer replaces these internal same-service calls; tests target actual owner capabilities. Manifest v175 retains the 504 actual source paths and fingerprints their updated contents; historical snapshots remain untouched.

This accessory candidate retains the native-history/readiness implementation and detection composition from actual main dcb4805, and follows analysis candidate bb3afa6. Actual-main rebind and analysis release acceptance must precede publication. Accessory production/tests and the ordered entry match reviewed c43118e. The bundled manifest is v175 with 504 unique sources. Original history28 and reader19 benchmark protocols remain mandatory; prior recorded performance failures are retained.

Image worker ownership keeps the existing daemon thread name and auto-resume setting, and does not change job scheduling or thread context propagation. Manifest v176 fingerprints the actual runtime source (507 total); existing task snapshots stay unchanged.

Pipeline state ownership preserves the existing lock types, shared five-second reconciliation interval, per-task registries and cancellation behavior. Manifest v176 includes the actual owner source (507 total); historical snapshots remain untouched.

Auto-optimization runtime ownership changes no model, concurrency setting, default, promotion or cancellation policy. Manifest v176 includes 507 actual sources; historical model bindings and task snapshots are untouched.

The settings composition change introduces no business configuration or default. Environment values are still parsed for every call, including the same invalid-environment errors before explicit overrides. Reassigning private entry settings aliases no longer rewires consumers: tests and extensions must inject a capability at the consuming service boundary. Manifest v176 retains 507 real sources; historic task snapshots remain unchanged.

This background candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows accessory candidate f397a31. Actual-main rebind and accessory release acceptance must precede publication. Production/tests and the ordered entry match reviewed 5a44e61. The bundled manifest is v176 with 507 unique sources. Fixed history28 and reader19 protocols remain mandatory; prior recorded performance failures remain retained.

## Real-photo feedback foundation

`VANTALINE_REAL_PHOTO_ACCOUNTS` is an explicit comma-separated owner-ID allowlist; unset/empty disables the new adapter. Only the owning authenticated account can enable or inspect it, including for admins. `bbox_annotation` is an independent model-profile purpose requiring Doubao `doubao-seed-2-1-pro-260915`; an absent binding blocks enablement without detection/image-provider fallback. Request settings are temperature 0, thinking disabled, detail high, 4096 output tokens, strict 0–1000 xyxy. Frozen first-frame pixels do not silently apply EXIF rotation or historical coordinate reinterpretation. There is no automatic training in the foundation batch.

The second batch requires `VANTALINE_TRAINING_REVIEW_BINARY`, `VANTALINE_TRAINING_REVIEW_AUTH_HOME`, `VANTALINE_TRAINING_REVIEW_WORK_ROOT`, `VANTALINE_TRAINING_REVIEW_SECRET_FILE`, the explicit owner allowlist and PostgreSQL/COS runtime settings. `VANTALINE_TRAINING_REVIEW_MODEL` is fixed to `gpt-6-astra`; other values fail startup. Optional `VANTALINE_TRAINING_REVIEW_PROXY_URL` must be a credential-free loopback HTTP proxy. Only the parent reads profile secret material. The child receives a fresh dedicated auth.json and minimal config, read-only task media, bounded writable scratch and a scoped report socket. No personal plugins or Web/DB/COS credentials are mounted.
Legacy PLC worker ownership introduces no configuration or enable switch. Intervals and repository/config/renewal/loop callbacks are still resolved at operation time. Root lock/thread state is no longer the patch surface; tests target the LegacyPlcWorkers instance. Manifest v177 includes the real source (512 sources), preserving existing task snapshots.

The station guard adds one explicit fallback-clock supplier without a new operator setting. New tasks use prompt source manifest v177 over the same 512 source paths; historical fingerprints and model bindings remain intact. The root guard export captures the station instance method while its required identity/configuration suppliers remain live.

The retained PLC readiness policy still reads VANTALINE_PLC_DEVICE_PROFILE_FINGERPRINT and VANTALINE_PLC_READ_PROFILE_FINGERPRINT lazily, with existing strip/lowercase normalization and constant-time digest comparison. A non-None injected transport, even falsey, preserves test override semantics; serial availability also checks the current ContextVar user. There are no new settings. Prompt source manifest v177 includes plc/legacy_activation.py (512 paths), leaving historical task fingerprints untouched.

Retained PLC coordination reads the existing namespace keys, process identifier, lease duration and quarantine duration at operation time. No new setting or default is introduced. Same-process renewal, competing-owner expiry plus quarantine checks, and receipt deep-copy behavior are unchanged.

PLC audit projection preserves absent, malformed and dictionary namespace distinctions, list-only dispatch storage and shallow record copies. The existing path sanitizer and absent sentinel remain operation-time capabilities. No configuration key, default or persisted record format changes.

Legacy PLC operations retain the original enabled/capture/activation gates, control-generation checks, queue-adoption reasons and read timeout cap of 0.15 seconds. No new flag, default, protocol or activation path is introduced.

This PLC candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows the reviewed background ownership candidate. Actual-main rebind and predecessor release acceptance must precede publication. Production/tests and the ordered entry match reviewed a139e03. The bundled manifest is v177 with 512 unique sources. Fixed history28 and reader19 protocols remain mandatory; prior recorded performance failures remain retained. Browser-only physical IO, uncertain-write no-retry and inert retained startup remain unchanged.

Web-shell composition introduces no setting, route allowlist or sanitization policy. Existing file paths and enabled/allowlist/blocklist suppliers are evaluated at the original operation points. Public HTML does not grant API permission; existing security middleware still controls API access.

This Web-shell candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows PLC candidate e73394d. Actual-main rebind and predecessor release acceptance must precede publication. Production/tests and the ordered entry match reviewed 4b28b8e. The bundled manifest is v178 with 513 unique sources. Fixed history28 and reader19 protocols remain mandatory; earlier recorded performance failures remain retained.

Removing unreachable entry tails changes no configuration defaults, permissions or model selection. New-task provenance uses manifest v179 with the existing 513 actual sources; historical task snapshots remain untouched.

This unreachable-tail candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows Web-shell candidate 82cc0d0. Actual-main rebind and predecessor release acceptance must precede publication. Production and the ordered entry match reviewed ed9dc91; the retained-tail test explicitly handles Python 3.10 frame cells and Python 3.11+ compiler metadata without skipping behavior checks. The bundled manifest is v179 with 513 unique sources. Fixed history28 and reader19 protocols remain mandatory; prior performance failures remain retained. Existing endpoints and live behavior remain; only statements following unconditional exits are removed.

The repository owner retains operation-time VANTALINE_DATA_STORE/DATABASE_URL reads and existing libpq settings. Its explicit optional connector replaces the private entry-only test hook; changing that connector invalidates that owner’s thread cache under the existing key rule. No deployment setting or driver policy changes. Manifest v180 includes runtime/repository_composition.py (514 actual sources), without rewriting historical task fingerprints.

This repository candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows the reviewed tails candidate. Actual-main rebind and predecessor release acceptance must precede publication. Repository production and the ordered entry match reviewed dd74e3e. The bundled manifest is v180 with 514 unique sources. Fixed history28 and reader19 protocols remain mandatory; earlier performance failures remain retained. This is scoped connection ownership, not a complete production application factory.

Authentication configuration remains derived from the same startup environment/defaults. Auth path, password iterations, cookie/TTL/session-persist interval, rate-limit values and legacy-owner ID are now captured as explicit composition inputs. Arbitrary rebinding of their private server constants no longer changes the constructed auth graph; tests inject the domain settings capability. Live repository selection still observes its owned environment/connector. Manifest v181 includes auth/application.py (515 actual sources); historical snapshots are unchanged.

This authentication candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows repository candidate 3ac769a. Actual-main rebind and predecessor release acceptance must precede publication. Authentication production/tests and ordered entry match reviewed a1933f3. The bundled manifest is v181 with 515 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Explicit startup captures intentionally narrow private root rebinding; this is not a complete application factory.

Record composition preserves legacy/system owner IDs, admin/shared-read/write permissions, audit timestamp rules and hidden 404 responses. No setting changes. Manifest v182 adds records/composition.py (516 actual sources), only for new snapshots. Rebinding private entry record owners or account helpers is no longer a wiring mechanism; replace explicit domain capabilities in tests.

This record composition candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows authentication candidate 552944a. Actual-main rebind and predecessor release acceptance must precede publication. Record production/tests and ordered entry match reviewed f5d759e. The bundled manifest is v182 with 516 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Explicit selected methods narrow private root rebinding; no new permission or persistence atomicity is claimed.

Bootstrap location extraction preserves LOCAL_INSPECTION_ROOT, INSPECTION_SERVICE_ROOT and VANTALINE_REPO_ROOT precedence, empty-value fallback, tilde/relative resolution, trailing local_inspection_service handling and missing-directory errors. Existing data/media/frontend paths and startup defaults are unchanged. Manifest v183 adds the actual bootstrap source (517 sources); old task snapshots remain untouched.

This bootstrap candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows record candidate bdbe2fa. Actual-main rebind and predecessor release acceptance must precede publication. Bootstrap production/tests and ordered entry match reviewed 4a4733a. The bundled manifest is v183 with 517 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Existing path resolution order and errors remain; no directory creation or complete application factory is introduced.

Cost composition captures the resolved six CostPaths and chosen callable owners at assembly. Private server constant/function rebinding no longer rewires the ledger; tests replace explicit CostStoreDependencies. Runtime repository selection still occurs on every original operation, and source contents remain live. Pricing/environment defaults and admin permission rules are unchanged. New task provenance uses manifest v184 with 518 sources; historical snapshots are not rewritten.

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

Training thread admission/drain adds no environment variable, model selection, prompt, HTTP route or default request change. The root injects the existing repository thread scope into the shared owner. Internal submission after close raises TrainingRuntimeClosed before any save; ordinary application startup does not call close. The honest source manifest is version189 with518 sources; existing task snapshots retain their recorded versions.

This training-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows YOLO-warmup candidate 3325d48. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 89ea498. The bundled manifest is v189 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Native-thread drain does not certify task persistence, remote settlement or whole-application shutdown.

Codex background thread ownership adds no external configuration, command, prompt, model or default API change. TrainingThreadLifecycle keeps the existing admission/uncertain-start policy; each owner is independent. The current manifest is v190 with518 sources and records current content; historical task snapshots stay unchanged.

This Codex-background drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows training-drain candidate ad431e7. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 9634271. The bundled manifest is v190 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Only owner-started native threads are drained; synchronous callers and remote business settlement remain separate.

Transfer reporter ownership adds no setting or change to the 1.5-second default reporting interval. Callback lookup, counter conversion and swallowed periodic update errors remain unchanged. Prompt source manifest v191 retains the same 518 ordered files.

This transfer-reporter drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows Codex-background candidate bb5e844. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 5d64dfe. The bundled manifest is v191 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Reporter drain does not cancel transfers or certify task persistence or whole-application shutdown.

Auto-optimization starter ownership adds no configuration or request default. Each service receives its own repository-scoped thread lifecycle through composition. TrainingRuntimeClosed rejects internal starts after close; this slice does not invoke close during normal application operation. Prompt source manifest v192 retains the same 518 ordered files and fingerprints changed source bytes for new snapshots.

This auto-optimization starter-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows transfer-reporter candidate 7f3f2a7. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 4e88155. The bundled manifest is v192 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Native-thread drain does not certify remote settlement or whole-application shutdown; the executor scope fix remains a separate successor.

FoundationInputs explicitly supplies live environment, authentication settings, fixed auth paths/owner IDs and optional connector. Distinct application configuration requires distinct mutable inputs; sharing the same mapping intentionally shares future values, while owner state remains separate. No environment default or route changes. Manifest v193 now includes 519 unique sources including runtime/application_foundation.py; historical snapshots remain unchanged.

`InfrastructureInputs` adds explicit path/configuration codecs and policies, image-library suppliers, provider configuration ports, legacy label/Agent defaults and cache TTL/clock. `ProviderConfigurationInputs` mirrors the existing 36 typed provider groups and binds local-model file access and directory initialization to the selected infrastructure. SecretEnvironment, legacy environment/transport ports and secret/Agent paths remain explicit supplied capabilities; separate infrastructure owners do not isolate intentionally shared external inputs. The default Web entry uses the builder with its explicitly preallocated artifact owner. No public setting or topology changes. New task source manifest v272 includes both construction modules; historical snapshots remain unchanged. Complete Web domain/lifecycle assembly remains pending.

This application-foundation candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows auto-optimization starter candidate d81faba. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 66697fc. The bundled manifest is v193 with 519 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Three inert foundational owners are distinct; this does not complete the application factory or lifecycle.

Automatic-mask pool repository scoping has no new setting. Manifest v194 contains the same 519 ordered source files; new snapshots fingerprint changed source bytes. Repository selections remain thread-local; the pool retains its prior context propagation behavior.

This automatic-mask pool-scope candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows application-foundation candidate 8dd3e33. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests match reviewed c84e963 and the ordered entry is unchanged. The bundled manifest is v194 with 519 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Repository cleanup is scoped to executor work; model-binding propagation remains a separate successor.

Automatic-mask batches receive an explicit model resolver capability; there is no new setting or prompt. An absent resolver or missing active snapshot fails before the affected child submission. If a later binding fails, earlier children may already have executed; the existing executor waits for them and the batch records its existing failure state without replay. Empty bound snapshots remain valid. Manifest v195 keeps the same 519 sources and records actual changed bytes for new tasks, without rewriting stored snapshots or secret versions.

This automatic-mask model-binding candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows pool-scope candidate 60a094b. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed b86a647. The bundled manifest is v195 with 519 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Only the selected model snapshot is propagated; later binding failure does not undo already submitted work.

Text document/preparation admission adds no public configuration or request default. Document classification retains two local slots and preparation one; these are separate from the global label-worker concurrency limit. Internal starts after close raise TrainingRuntimeClosed before settings or record access. Manifest v196 includes 520 actual source files, adding text_inspection/job_admission.py; historical snapshots are not rewritten.

This text-job ownership candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows model-binding candidate 8302940. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 4491be2. The bundled manifest is v196 with 520 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Job permits retain capacity through thread and repository cleanup; direct synchronous calls remain caller-owned.

HTTP shell construction retains existing file-store selection, local/LAN CORS defaults, explicit origins, empty/invalid regex behavior and parsing order. Settings are read at construction, as before. It adds no operator setting. Source manifest v197 includes 521 actual source files for new fingerprints, including runtime/http_application.py; existing task snapshots are unchanged.

This HTTP-shell candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows text-job candidate a071786. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 5d1d582. The bundled manifest is v197 with 521 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. A fresh transport shell is not yet a complete isolated production application.

The optional HTTP upload runtime provider is an internal composition capability, not an environment setting or public API. Existing file-store mode selection, upload size limits, responses and default provider behavior stay unchanged. Local mode does not invoke an explicit upload provider.

This HTTP upload-provider candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows HTTP-shell candidate fa14007. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests match reviewed 6f11bcd and the ordered entry is unchanged. The bundled manifest is v198 with 521 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Explicit provider injection is enabled for later composition; the current entry still uses the default provider.

Artifact runtime instances retain the existing mode, required-value and hard-limit validation and error messages. The environment supplier selects one mapping per get call, whose keys remain operation-time reads in the original order. get_runtime uses the current os.environ mapping through its default owner. Environment mutation during initialization retains the existing snapshot/signature behavior; switching to local mode bypasses the cached non-local runtime without disposing it.

This artifact-runtime ownership candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows HTTP upload-provider candidate 4ab91fe. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests match reviewed 4c2b19e and the ordered entry is unchanged. The bundled manifest is v199 with 521 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Owners isolate selector locks and caches, not underlying paths or resources; the default entry owner remains process-scoped.

Frozen HTTP constructor evidence is pinned to canonical Git LF bytes with an explicit checkout attribute. The raw SHA guard still rejects any changed fixture; this fixes platform-dependent test acceptance without changing application behavior or historical task snapshots.

Frozen artifact-runtime evidence is checked out as canonical Git LF bytes. The original raw SHA and immutable fixture Git blob remain unchanged; a CRLF working-copy mismatch is a test portability failure, not a runtime regression.

Pipeline thread ownership adds no setting, changes no prompt or model binding, and retains original worker arguments. Source manifest v206 retains 519 ordered actual sources and records their new bytes for new tasks; historical task snapshots and secret versions are unchanged.

Extraction ownership adds no setting, request field, provider choice or timeout change. Each registered application receives an independent owner; after close, prepared-input submission raises TrainingRuntimeClosed, including duplicate/manual POSTs. Authorization, capability checks and input normalization precede that internal boundary. Prompt-source manifest v205 contains the same 518 ordered sources; historical snapshots remain unchanged.

Comparison cleanup fixes have no new settings, request defaults, model selection or timeouts. Both existing one-slot comparison limits remain. Manifest v206 retains the same 518 ordered source paths and fingerprints changed cleanup code for new task snapshots; existing snapshots stay unchanged.

Comparison ownership introduces no business setting, model, prompt or timeout change. Local and Qwen capacities remain one each within the application owner; the external label worker global limit remains two. Manifest v207 appends runtime/deadline_tasks.py and text_inspection/comparison_runtime.py (520 sources); only new task fingerprints change. Legacy direct submit/run callers retain their existing default module capacity and native launch; production composition explicitly supplies the owner.

PDF import ownership adds no configuration or rendering/concurrency policy. Manifest v208 fingerprints the existing PDF implementation path and retains all520 source paths. A startup failure is surfaced and the same owner never silently starts a replacement; create a new application instance after resolving the startup failure. A closed owner rejects restart. Deterministic PDF import progress/resume rules are unchanged.

This offline lifecycle integration retains native-history/readiness and detection composition from actual main dcb4805 and follows artifact-owner candidate 6b648b5. Owned production/tests and ordered entry match reviewed 28de9fa; both canonical fixture corrections are already retained. The bundled manifest is v204 with 523 unique sources; earlier paragraph counts refer to their original individual candidates. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Publication must use independently reviewed domain-scoped PRs on accepted main, with full hosted and release gates; this offline combined tree is not a blanket grouped publication approval or complete application factory.

Web shutdown introduces no configuration setting. Its cooperative budget is 480 seconds starting before existing synchronous stop hooks. Existing label/control hooks retain their current timeout semantics, and their actual elapsed time reduces the remaining allowance for native owners. Those callbacks are not interrupted or preempted, so this is not a strict hard wall-clock upper bound.

This offline shutdown replay follows lifecycle candidate 7d7886a and preserves current native history, readiness, model/tail and canonical LF fixes. Four owned runtime/test/contract blobs match reviewed 82313c5. Manifest v205 lists 524 sources. The 480-second shutdown allowance remains cooperative and requires ASGI request quiescence; complete independent application composition is still pending. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Explicit detection storage ports add no business setting or change to image decoding, inference, JPEG quality, API payloads, model selection or PLC behavior. Missing/non-callable composition dependencies now fail explicitly at construction. At the detection artifact replay boundary, manifest v206 retains all 524 source paths and fingerprints changed implementation files for new tasks only.

This offline detection artifact replay follows shutdown candidate 8618f7a and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 713010a. Manifest v206 lists 524 sources. Storage suppliers retain call-time selection; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Detection media composition adds no environment setting or model/prompt/codec policy. ModelFiles declares runtime selection, is_file and local_file; VideoFiles declares runtime selection, stream publication and local materialization. Required dependency omissions fail during construction. At the detection media replay boundary, manifest v207 retains all 524 ordered paths; historical task snapshots are not changed.

This offline detection media replay follows artifact candidate e7e12b2 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 5e86530. Manifest v207 lists 524 sources. Explicit stores retain original cache, error and video cleanup behavior; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

HTTP artifact ports introduce no business setting, media authorization rule, route, upload limit or storage mode. Required suppliers must be callable; a supplied None result cannot silently select default storage. At the HTTP artifact replay boundary, manifest v208 retains all 524 actual source paths and updates provenance only for new task snapshots.

This offline HTTP artifact replay follows detection media candidate f2b4519 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 301b6c1. Manifest v208 lists 524 sources. Explicit missing file dependencies fail closed while genuinely omitted legacy arguments retain their documented default. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Explicit incoming business storage capabilities add no setting or model/OCR policy. Required file/image dependencies reject omission or None at composition time and keep falsey protocol objects. At the incoming workflow replay boundary, source manifest v209 retains all 524 selected source paths and fingerprints changed sources for new tasks; historical snapshots are unchanged.

This offline incoming workflow replay follows HTTP artifact candidate 2336193 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 8e4d991. Manifest v209 lists 524 sources. Consistent captured files/images dependencies retain original partial-write, exception and retention semantics. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Background file injection introduces no setting or image policy. Explicit constructor dependencies reject omission/None and do not inspect truthiness. At the background file replay boundary, manifest v210 contains 525 selected source paths, appending training/background_file_ports.py; only new task provenance changes.

Prompt-source names are relative to local_inspection_service, so this manifest entry is training/background_file_ports.py. Fingerprints read actual shipped bytes through prompt_source_version/fingerprint_sources; no placeholder or historical hash substitution is used.

This offline background file replay follows incoming candidate 841c4ba and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed c80ed68. Manifest v210 lists 525 sources, with the corrected service-relative background capability path. Captured file capabilities retain original ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Background image capabilities introduce no codec, random-seed, augmentation, model-validation or setting change. Missing/None dependencies fail at construction, falsey supplied adapters are retained. At the background image replay boundary, manifest v211 keeps all525 selected source paths; the actual shipped-source fingerprint check covers their resolution.

This offline background image replay follows file candidate 89875c1 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 09ef623. Manifest v211 lists 525 sources. Three image services use explicit adapters; generator and runner defaults remain outside this slice. Original algorithms and golden contracts remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Required background-generation storage ports add no environment, process command, prompt, model, timeout or retry setting. Missing/None ports fail during construction; falsey explicit objects remain. At the background generation replay boundary, manifest v212 preserves the same525 selected source paths and updates only new-task provenance.

This offline background generation replay follows image candidate 9a2d333 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 22986e9. Manifest v212 lists 525 sources. Generator and task runner now receive captured file adapters, retaining model snapshots, subprocess policy, partial outputs and exception behavior. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Training input/generation and preview metadata file ports add no business setting or dataset/preview policy. Missing/None dependencies fail during construction; falsey adapters remain valid. At the training file replay boundary, manifest v213 appends training/file_ports.py for526 selected sources, updating new-task provenance only.

This offline training file replay follows generation candidate 2fdb9ee and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 214fe9c. Manifest v213 lists 526 sources, appending training/file_ports.py. Five services capture matching file capabilities while preserving validation, cache, write ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Explicit training image/YAML dependencies introduce no settings, model/prompt policy, RNG, labels, layout or codec changes. Missing/None dependencies fail explicitly. At the training image replay boundary, manifest v214 retains all526 selected sources and updates only new-task source provenance.

This offline training image replay follows file candidate 94c1eec and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 75d63a9. Manifest v214 lists 526 sources. Image adapters are captured and YAML selects its writer per call; arbitrary private rebinding is not preserved as an atomic hot swap. Algorithms, goldens and public signatures remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Required training resource/archive capabilities add no business setting, archive format, JPEG quality, hashing algorithm or retry policy. Missing/None files and missing/non-callable runtime suppliers fail explicitly. At the training resource replay boundary, manifest v215 retains526 selected paths for new-task provenance.

This offline training resource replay follows image candidate 9063ace and preserves current history, readiness, model/tail, shutdown, corrected boundary documentation and canonical LF guards. Production and test blobs match reviewed fbf5434. At this replay boundary manifest v215 selects 526 sources. Explicit resource and archive capabilities preserve file operation ordering, strict digest failures, partial publication and archive formats. Current source changes require actual-main rebind, independent review and full CI/release acceptance before publication.

Explicit accessory file ports introduce no upload setting, model binding, provenance policy or sprite calculation change. Missing/None dependencies fail at composition; falsey objects are retained. At the accessory file replay boundary, manifest v216 preserves526 actual selected paths and updates new-task provenance only.

This offline accessory file replay follows training resource candidate 7ae44bf and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed eccc553, including ordered constructor bindings. At this replay boundary manifest v216 selects 526 sources. Upload ordering, partial publication, provenance collisions and sprite fallbacks remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

Explicit accessory evidence/preview file and image ports add no settings, source selection, background scoring, image decoding or model policy. Missing/None ports fail at construction. At the accessory evidence replay boundary, manifest v217 retains526 selected sources and changes provenance for new snapshots only.

This offline accessory evidence replay follows file candidate b368404 and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed 466195b. At this replay boundary manifest v217 selects 526 sources. Decode and hashing selection, source mutation, partial publication and error propagation remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

Accessory catalog and sprite decoding ports add no setting or model policy. Missing/None ports fail explicitly. Prompt-source manifest v218 retains526 selected paths; old task snapshots remain unchanged.

This offline accessory catalog replay follows evidence candidate 2d442b2. All owned production/test blobs and the complete ordered entry match reviewed 87ebec1; current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v218 selects 526 sources. Existing catalog mutation and decoder behavior are unchanged. Exact-source neighbor evidence is reused; current targeted, assembled HTTP and fingerprint checks are distinct. Actual-main rebind and independent full CI/release acceptance remain required.

Explicit candidate/gallery storage adds no public configuration or model policy. Missing/None ports fail explicitly. Manifest v219 retains526 selected sources and records new provenance only for new task snapshots.

This offline accessory gallery replay follows catalog candidate 8f453b3. Owned source/test blobs and ordered entry match reviewed 7f02e9d, including the single inert ImageFiles allocation relocation. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v219 selects 526 sources. Existing partial publication and failed-write behavior are unchanged. Neighbor evidence is reused only for exact source; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Accessory file-edit storage injection adds no API or configuration. Required ports reject None, and manifest v220 keeps526 selected sources without rewriting historical snapshots.

This offline accessory edit replay follows gallery candidate 1b5c003. Owned source/test blobs and ordered entry match reviewed 6f78019. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v220 selects 526 sources. Authorization order, crop geometry, partial publication and deletion failure behavior remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Explicit preprocessing readers add no settings or algorithm changes. Required ports reject None; manifest v221 retains526 selected sources and historical task snapshots are not rewritten.

This offline accessory preprocessing replay follows edit candidate 96c7b23. Owned source/test blobs and ordered entry match reviewed dbcd8b5. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v221 selects 526 sources. Discovery, decode, publication, status and exception ordering remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Agent reference storage injection adds no API, prompt or model setting. Required ports reject None. Manifest v222 adds agent/file_ports.py to527 selected paths; historical snapshots remain unchanged.

This offline Agent reference replay follows accessory preprocessing candidate b1d835d. Owned source/test blobs and ordered entry match reviewed efa17b7. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v222 selects 527 sources. Reference selection, digest acceptance, path mutation and exception ordering are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Pose storage injection adds no configuration or model/prompt change. Missing/None dependencies fail at construction; manifest v223 preserves527 selected paths and leaves prior snapshots readable.

This offline Agent pose storage replay follows reference candidate 9a90408. Owned source/test blobs and ordered entry match reviewed 11919d9. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v223 selects 527 sources. Image and metadata publication ordering, local/remote callback timing and partial mutations remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Photo-highlight media injection adds no setting, prompt or retry change. Required ports reject None and manifest v224 preserves527 selected paths; historical snapshots remain unchanged.

This offline Agent photo replay follows pose storage candidate a56b846. Owned source/test blobs and ordered entry match reviewed 6afd82e. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v224 selects 527 sources. Provider attempts, diagnostic failure handling, publication and item mutation order are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Pipeline background media injection adds no setting, model or prompt change. Required file/image ports reject None; actual-source manifest v225 retains527 paths and does not rewrite historical snapshots.

This offline Agent background replay follows photo candidate 5bcd15e. Owned source/test blobs and ordered entry match reviewed e8c63a3. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v225 selects 527 sources. Existing library fallback, partial file and manifest publication, callback timing and errors remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Pipeline availability storage injection adds no configuration or default status change. Missing file ports fail construction, and actual-source manifest v226 retains527 paths for new snapshots only.

This offline pipeline availability replay follows Agent background candidate 37a1265. Owned source/test blobs and ordered entry match reviewed ed60859. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v226 selects 527 sources. First-match, pending-state, bypass and storage error behavior are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Text cleanup file injection is required and rejects None before route/runtime construction. No API setting, retention period, model or prompt changes. Actual-source manifest v227 includes528 selected paths; old task fingerprints remain historical.

This offline text cleanup replay follows pipeline availability candidate 6f13fd9. Owned source/test blobs and ordered entry match reviewed c89fbbd. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v227 selects 528 sources. Cleanup exception precedence, tombstone-before-deletion and partial effects remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Training catalog file capabilities are required, with None rejected. No storage mode/default ordering change is introduced. Source manifest v228 retains528 paths for new task snapshots; prior fingerprints are not rewritten.

This offline training catalog replay follows text cleanup candidate 1199028. Owned source/test blobs and ordered entry match reviewed 8f0715d. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v228 selects 528 sources. Local and indexed selection, permission ordering and repeated reads remain unchanged. Exact-source neighbor evidence is reused; current targeted, real PostgreSQL, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

TextMedia rejects an omitted or None runtime provider; the supplied provider may return None for the existing local branch. No new storage mode is introduced. Prompt source manifest v229 retains528 paths and applies only to newly bound tasks.

This offline text media replay follows training catalog candidate 920904d. Owned source/test blobs and ordered entry match reviewed f71e6c4. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v229 selects 528 sources. Local path, hybrid readiness, size, digest and publication rules remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Training runner files are required and reject None. Runtime selection still occurs after the running-state update and executor-mode lookup; COS mode continues to reject local/remote execution. Source manifest v230 retains528 paths and preserves historical task snapshots.

This offline training runner replay follows text media candidate da44932. Owned source/test blobs and ordered entry match reviewed 9b024f4. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v230 selects 528 sources. Running-state persistence, runtime mode, repeated existence reads, failure settlement and pinned model restoration remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

RunPod export/import runtime providers are required and reject None as a missing dependency. A callable returning None retains local operation. Source manifest v231 retains528 paths for newly bound tasks; historical fingerprints remain unchanged.

This offline RunPod artifact replay follows training runner candidate b7b8760. Owned source/test blobs and ordered entry match reviewed 671f233. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v231 selects 528 sources. Repeated runtime selection, cleanup exception masking, publication ordering and local replacement remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

RunPod transport runtime providers reject omitted or None dependencies; providers returning None retain the existing local behavior. Source manifest v232 retains528 paths without rewriting old task snapshots.

This offline RunPod transport replay follows artifact candidate 97a9963. Owned source/test blobs and ordered entry match reviewed 12f1743. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v232 selects 528 sources. Durable claim ordering, ambiguous submit retention, streaming limits and partial upload publication remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Codex HTTP runtime injection adds no setting, model or API change. An omitted or None provider fails at registration; a provider returning None keeps local media behavior. Source manifest v233 retains528 paths and updates provenance only for new tasks.

This offline Codex HTTP replay follows transport candidate 0beaefc. Owned source/test blobs and ordered entry match reviewed 42fcded. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v233 selects 528 sources. Authorization, media exception mapping and partial publication ordering remain unchanged. Exact-source neighbor evidence is reused; current targeted, isolated PostgreSQL, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Required label media runtime providers reject omission or None, while a callable returning None retains local storage. Re-registering a worker with a different provider is rejected in either topology. Manifest v234 retains528 source paths and leaves old snapshots untouched.

This offline label media replay follows Codex HTTP candidate 41743d5. The original provider-only delta from reviewed b696cba is applied while retaining current native history summaries and their test adapters. All other owned source/test blobs and ordered entry match the reviewed source. At this replay boundary manifest v234 selects 528 sources. Current history, readiness, model/tail, shutdown and canonical LF guards remain. Worker claims, PDF cleanup, provider identity and error ordering remain unchanged. Current isolated PostgreSQL and affected integration checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

MediaStore has no process-default runtime fallback; missing and None providers fail before path construction. A supplied callable may return None for local mode. Manifest v235 retains528 source paths for newly bound tasks only.

This offline comparison media replay follows current-history label candidate f447c5d. Owned source/test blobs match reviewed 552cea1; the entry remains unchanged. Current native history and its explicit-provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v235 selects 528 sources. Worker budget and reservation settlement ordering, ambiguous paid outcomes and CLI selection remain unchanged. Current isolated PostgreSQL and affected integration checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

Web artifact composition receives live environment and image backend suppliers explicitly and allocates no storage during graph construction. Existing local/COS validation and restart-on-configuration-change behavior remain in ArtifactRuntimeProvider. Manifest v236 adds storage/artifacts/composition.py for529 actual source paths.

This offline Web artifact composition replay follows comparison candidate d2ae509. Owned source/test blobs and ordered entry match reviewed a0fa2ed, including the Python 3.10 structural source guard. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v236 selects 529 sources. The Web graph owns a fresh lazy runtime provider and two focused views; this is not a complete application factory or proof of independent underlying resources. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

POST /api/stream/config retains StreamConfig defaults and the reserved_for_camera_or_rtsp_input status. It saves configuration only and starts no camera, stream or PLC operation. Source manifest v237 adds config/stream.py (530 paths), without changing historical task fingerprints.

This offline stream configuration replay follows Web artifact candidate f2e481b. Owned source/test blobs and ordered entry match reviewed 14f6504. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v237 selects 530 sources. Existing load, mutation, save and post-save response ordering remain unchanged; configuration is not given a new transaction or lock. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

IncomingTextStore now resolves JSON single-record lookups through its own list methods. The two callbacks through the application entry have been removed; narrow repository, guard, path and row-adapter inputs remain. Tests replace the owning store method and cover two independent stores, preserving missing-loader errors, call-time repository selection and lock behavior. TextStorage allocates both text stores and their shared write lock per composition, without opening a connection or retaining a user. Manifest v238 selects 531 source paths, including text_inspection/storage_composition.py. This closes the store self-reference only; full application factory and route/lifecycle instance isolation remain unfinished.

The text storage lock belongs to `TextStorage` and its public lock property cannot be rebound. The entry lock alias initially references it; replacing that private entry alias no longer replaces either store guard. Remaining route/write adapters still use their existing inputs until their domain composition is migrated. This intentional narrowing of private test seams does not change configured runtime behavior.

Incoming-text workflow composition adds no configuration or environment setting. Its references, inspections, JSON adapters and write guard come from the selected TextStorage owner; replacing private server forwarding functions or the root lock alias does not rewire this graph. Replace the explicit owner methods or ports in tests. Prompt manifest v239 records 533 actual sources including incoming_composition.py and incoming_duplicates.py; historical task snapshots are retained.

The incoming domain owns its response-file capability and exposes separate catalog and inspection route registration methods. Application composition calls them at their original positions, preserving the intervening Beta comparison routes and the existing media authorization/error behavior. The actual domain-builder HTTP tests exercise these methods; this does not claim a completed whole-application factory.

Replacing the default entry business-file alias no longer redirects this incoming domain. Its response capability is selected on the owner after authorization; changing that capability does not atomically replace the separate file adapters already held by catalog/execution/retention. No whole-graph hot-swap guarantee is introduced.


ModelCatalog construction stores capability suppliers, not the current user, a database connection or a loaded model. Registry, default ID, model factory and request identity remain selected during their existing operations. Entry compatibility aliases do not configure internal catalog dependencies; replace the explicit owner methods in tests or supply separate graph ports. Business configuration and historical task snapshots remain unchanged.

Candidate image worker composition uses existing settings and injected operation-time configuration/model resolver capabilities; no new business configuration or queue status is introduced. The queue pins the submitted job model snapshot on the native child before provider dispatch; missing resolver fails explicitly. Its candidate lock and child/process registries belong to the image domain instance. The current default application still exports its existing image-worker compatibility bindings and uses the existing shutdown sequence.

The image queue receives an explicit resolver supplier and pins it for the native execution call. Normal model-service selection remains unchanged; private test rebinding of the root resolve_model_profiles name can affect that injected supplier, while the retained public wrapper decorator still captures its original callable. Tests replace the actual domain model/provider ports rather than assuming arbitrary root-name rebinding is equivalent.

ModelTools introduces no operator setting or provider selection change. Source manifest v242 contains 536 real source files including model_providers/tool_composition.py; new tasks record the new source fingerprint, while historical snapshots and secret references remain unchanged. Existing provider/fallback budgets and operation-time external configuration suppliers are retained; internal callbacks follow the owned services.

The owned call export retains the two-step dispatch selection around argument evaluation; it adds no inference attempt or configuration change.

The owned MCP transport retains the original stdio failure fallback and error behavior. No provider attempt budget, retry policy or operator setting changes.

Detection workflow composition adds no model setting, prompt, default, secret or worker mode. Existing public AI entry and the graph-owned teacher route each enter exactly one existing model-profile scope; inherited task scope remains effective. Source manifest v243 lists 537 actual sources, adding detection/workflow_composition.py for new task fingerprints. Historical snapshots and secret references are not rewritten. Private root alias replacement no longer redirects owned detection/publication/capture operations; external configuration, identity, repository and auto-optimization runtime capabilities retain their current selection rules.

The text standard domain receives media placement, model settings, external-call enablement, parsing and native repository scope through explicit narrow interfaces. Configuration values are evaluated at their existing operation boundaries; construction opens no connection or worker. Preparation account policy and OCR availability still use their existing process configuration. Independent domain owners do not imply independently mutable application-wide configuration.

Comparison composition keeps submission model/image/policy/diagnostic capabilities separate from extraction model settings and prepared-comparison model snapshots. The digest callable, prepared cleanup and environment reader retain their original per-submission selection boundaries. Qwen/OCR/preparation account policy remains process configuration; separate domain graphs do not imply independent full application configuration.

AutoOptimizationCore receives existing AutoOptimizationSettings, runtime state and narrow external capabilities. Defaults, environment reads, model-profile snapshots, permissions and training/image topology remain unchanged. Replacing a private root compatibility alias no longer rewires these internal callbacks; tests replace actual owned methods. Prompt source manifest v246 includes training/core_composition.py for new task provenance; historical snapshots are retained.

The owned shadow native target preserves the original pinned model-profile entry through an explicit resolver provider captured at composition. Task loading and one model scope run after native repository-scope entry, using the actual core store; the public compatibility worker keeps its original single decorated call. Tests cover retained task version after configuration changes, empty and inherited snapshots, missing resolver before task I/O, exceptional restoration and one scope without retry.

Auto-optimization execution composition introduces no configuration keys. It receives the existing settings owner, negative-sample default, model resolver and shared runtime explicitly. Native label/check workers keep stored task model versions and fail explicitly when the resolver is missing; historical snapshots are not rewritten. Prompt source manifest v247 includes the actual execution composition source for new fingerprints.

Automatic-optimization workflow composition adds no configuration. Separate explicit shadow_resolver/model_resolver inputs retain the original provider selections, which both resolve through resolve_model_profiles in the default Web assembly. New task fingerprints use manifest v248 with training/workflow_composition.py; historical model snapshots and secrets are unchanged.

Training state composition adds no business configuration, model, prompt or executor mode. New task fingerprints use source manifest v249 with 543 actual sources including training/state_composition.py; existing snapshots and secret references remain unchanged. The existing model resolver getter/provider layers and per-operation repository selection are preserved.

Training-task composition adds no operator settings, model/prompt changes or worker topology. Account configuration is supplied through TrainingConfiguration load/save capabilities; request identity and database selection remain lazy. The pure training worker classifier belongs to the composed jobs capability; replacing a private server alias does not rewire it. New task fingerprints use source manifest v250 with 546 distinct sources, including account_state_composition.py, native_execution_composition.py and task_composition.py; historical snapshots and secret references remain unchanged.

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

Beta list compaction adds no setting, writer, schema or migration. The honest manifest remains v251 with547 source paths including storage/label_beta_summary.py, whose current content defines the new fingerprint. Old task snapshots are not rewritten. Missing/null/array/scalar labels and unknown fields retain their original values; no size/depth/numeric cutoff controls list behavior.

Beta history SQL counts add no setting. Only object/array counts are supplied; zero is valid, while unavailable counts remain null internally. Existing wrong-shape and explicit-null error behavior remains. Prompt source manifest v251 selects 547 ordered files.


Beta summary consumer is integrated into the final read batch on business composition 2b6e9ce; manifest v251 selects 547 actual sources. This is list SQL compaction, not complete legacy SQL aggregation or release acceptance.

The historical baseline-only prerequisite added no runtime setting, source fingerprint, migration or read optimization. Existing fixed 15-minute account/filter-bound cursor behavior remains the contract, including cursors created by the frozen endpoint and consumed by the candidate.

Manual benchmark configuration is fixed in source: one1000-group A/A case and three repetitions of1000/10000-group A/B cases. No production setting or prompt-source manifest changes are introduced by this test-only protocol.

The internal manual rows indexed keyword is enabled only by the list endpoint and adds no public API parameter or setting. One or zero groups skip index construction. The fast path requires the actual per-request LabelRepository legacy cache; it may read cached assets fewer times but preserves database query behavior. Manifest v239 retains531 paths and records changed code for new task fingerprints; historical snapshots remain unchanged.

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


`VANTALINE_REAL_PHOTO_TRAINING_ENABLED=1` enables server execution of accepted-original proposals in addition to the owner allowlist and independent screening worker. Default is disabled. Local training requires existing base weights; RunPod additionally requires a base SHA256 (including URL mode), a compatible held-out-evaluation worker, and verified executor readiness. Executor/device/weights/80 epochs/640 image size are frozen in the dataset before submission; drift fails rather than falling back. No secret or signed model URL is included in that snapshot.

The production reviewer inherits `/etc/vantaline/cos-storage.env` and receives its own systemd `CREDENTIALS_DIRECTORY`. Its private review environment overrides only intended settings; it must explicitly provide PostgreSQL/account admission and the training-specific binary/auth/work-root/secret-file configuration. Reusing the COS credential source does not reuse the label worker's Codex login or queue.

The real-photo review trigger is a cumulative original ordinal, independent of the approved target. Its cohort is frozen before pending labels settle; later originals wait for the next cohort. Explicit annotation-version rechecks retain the previous original cutoff and do not count as new photos. No additional configuration variables are introduced. Failed preparation/review/assessment requires explicit recovery and never raises a synthesized-sample fallback.

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

Workstation composition adds no operator setting or default change. Its explicit ports retain the existing request-time account, repository and policy suppliers. Prompt-source manifest v259 includes `plc/workstation_composition.py` for newly created task fingerprints; stored model/configuration/secret bindings and historical task snapshots remain unchanged.

Lease/diagnostic composition introduces no configuration flag, model setting or account default. It retains call-time suppliers for identity, release consistency, permissions and clocks. Prompt-source manifest v260 adds `plc/lease_diagnostic_composition.py` for new fingerprints without rewriting historical snapshots.

Capture composition adds no configuration or environment switch. The two retained capture state owners use existing configuration, generation, receipt and runtime keys through operation-time suppliers. Historical model snapshots are untouched; prompt source manifest v261 includes the actual new capture_composition.py module.

PipelinePersistence introduces no new business configuration. Model resolver suppliers retain both callable layers and save_pipeline_task freezes before encoding or repository selection. Manifest v262 includes the actual pipeline/persistence_composition.py source without rewriting task snapshots. Task/state path suppliers keep their existing operation-time selection.

PipelineExecution adds no model or worker configuration. It retains the original ResolverProvider object and native task ID/stage/user signatures. Existing task model_profiles takes precedence when binding; missing resolver fails explicitly before the runtime body. Manifest v263 includes pipeline/execution_composition.py; task snapshots and prompts are unchanged.

PipelineQueries adds no setting. Model snapshots remain unchanged; prompt source manifest v264 records pipeline/query_composition.py. Public responses retain model_profiles removal, original normalization/defaults, account visibility and preloaded resource semantics.

Agent pipeline composition adds no setting or prompt change. Manifest v265 records agent/pipeline_composition.py as actual source. The model resolver is directly captured; record model_profiles precedes inherited scope, and a missing resolver fails before the flow can fall back or invoke a provider. The existing system prompt remains an operation-time supplier.

Pipeline stage composition adds no configuration key or model fallback. The existing stage policy, timeout and job/model configuration remain operation-time capabilities; AI activation keeps the existing save/projection order and recommendation cache handling. Prompt provenance manifest version 266 adds the actual `pipeline/stage_composition.py` source (576 files); old task snapshots and prior fingerprints are retained unchanged.

Task/HTTP composition adds no business configuration or permission. Each task workflow resolves user, scoped configuration and request identity when called. Prompt provenance manifest version 267 adds `pipeline/task_composition.py` (577 files); historic model snapshots and fingerprints remain immutable. A missing/mismatched domain owner is an assembly failure, not an implicit model fallback.

Pipeline runtime composition adds no business setting or topology flag. New task provenance uses source manifest v268 with 578 entries including `pipeline/runtime_composition.py`; historical snapshots and secret references are unchanged. Native entry scope, captured resolver selection, model pin and account identity retain their original order.

Codex account/model settings retain their exact default Web values and live-read behavior; its registrar now requires the environment mapping explicitly. Empty supplied mappings do not fall back to process settings. Model whitespace is still stripped for readiness and preserved verbatim in capabilities. New task source provenance is manifest v269 with 580 sources including the changed Codex API and worker; historical snapshots are not rewritten.

The registered API captures the supplied mapping object: in-place updates are visible, while replacing the process os.environ object does not replace the registered dependency. The independent worker chooses its own current process mapping at each claim.

The original pipeline runtime ownership clock oracle validates actual composed modules and replays the reviewed root assembly before its unchanged historical clock assertion. This preserves the original state/lock tests after task-list clock ownership moved into PipelineTaskWorkflows. No runtime or PLC behavior changes.

The composition source guard accepts partially replayed roots only when their entire AST matches an immutable reviewed descendant checkpoint. It still validates every actual owner before replay, rejects unknown edits at each checkpoint, and ends at the exact workstation parent. Historical oracle assertions and generic single-delta semantics remain unchanged; this does not approve a missing default Codex environment binding.

Provider dependency-capture tests substitute secret-key identification on the actual ProviderConfiguration instance. The same original A/B/C argument-time mutation and missing-callable assertions remain; other provider capabilities retain their existing locations. The temporary mock is restored on exit and changes no model call, key selection or retry algorithm.

Pipeline resource availability still uses the configured BusinessFiles capability supplied to PipelineQueries. The test-only historical constructor oracle now verifies the actual owner before strict replay; no storage configuration, environment variable, runtime fallback or public API default changes.

The training source-oracle ordering repair changes no configuration defaults or providers. Actual application configuration remains verified by the central integrated replay before the historical training contract is inspected; duplicated premature configuration replay is removed only from the test helper.

The Agent reference-reader source contract also verifies actual Pose and path composition before its historical constructor assertion. PoseExecutionWorkflows receives explicit file readers; this test-location repair adds no storage fallback, configuration key or model call. Required-reader and falsey-input checks remain unchanged.


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

The provider transport builder receives an explicit cache TTL and app-owned transport/resolver inputs. No environment key or API default changes. Image sizes are selected at operation time; Gemini cache TTL retains the original composition-time default and explicit per-call override. Missing model resolvers still fail before a bound paid transport call.

The real-photo composition preserves `VANTALINE_REAL_PHOTO_ACCOUNTS` and `VANTALINE_REAL_PHOTO_TRAINING_ENABLED`. Constructing this graph does not read the allowlist, acquire a database connection or start a dispatcher. Existing process-environment allowlist policy is retained; the complete Web app factory remains pending.

Canonical construction adds no operator environment key, business setting, route permission or model default. `create_application(environment, entry_file=..., connector=...)` accepts explicit composition inputs for tooling/tests; business still consumes individual typed capabilities. Defaults and environment-derived values validate before HTTP publication. Model fallback remains eagerly evaluated as before; malformed composition values may now fail earlier in construction. Existing third-party/process allowlist environment behavior is retained.

New tasks use source manifest v277/612, including the actual factory, wiring, lifetime, shared cancellation/list policy and default-call compatibility modules. Historical task model snapshots, source fingerprints and secret versions are not rewritten. No prompt or model algorithm is changed.

Real-photo localization applies fixed longest-edge limits of 1024 for class references and 2048 for the actual original before provider JPEG quality-90 encoding (review/export canonicalization remains lossless PNG). Source byte/pixel limits remain; fixed 4:4:4 JPEG90 bounds are 2 MiB per reference, 6 MiB per original, 32 MiB prefix JSON and 10 MiB suffix JSON. This introduces no environment option or alternate model; original dimensions, first-frame orientation and scale evidence remain frozen. Preparation-stage failures display only fixed stage codes and exception types, never secret-bearing exception messages.

训练审核诊断随不可变 worker 发布，无新增运行开关或模型配置。尝试回执包含固定诊断及提示词 SHA-256；1000 字符的 reason/gap 限制在版本化审核 skill 中显式说明。CLI/model/报告约束保持不变。

Real-photo provider encoding is fixed JPEG quality 90, matching the label-comparison encoding; this is not a configurable fallback. Original bytes and training/review PNGs remain unchanged. Transport and response-validation failures are classified separately without endpoint, credential or embedded-media text.

## Operator-confirmed workstation setup

**Status: Authoritative**

`inspection` and `ai_detection` accounts may self-register/configure their current cookie-bound workstation. The first-use UI proposes D205 input, trigger 1, D206 result, blank Y and automatic capture enabled; operator confirmation is required before enabling the station. Existing configurations are preserved, and unconfirmed server defaults remain disabled. Transport parameters stay FX3GA-40MR / FX ASCII / 9600 / 7E1 / 500ms / zero write retries. Read-only connection verification is lease-scoped and separate from manual `profile_verified`. These APIs grant no global configuration or station takeover permission.

Real-photo bbox transport resolves the immutable bbox_annotation profile proxy_ref through the dedicated private secret file and disables ambient HTTP proxy settings. Its Ark v3 endpoint is used as /responses with fixed model doubao-seed-2-1-pro-260915; no fallback. Explicit provider cache inference permission is required. One-hour prefixes are keyed by owner/task/classes/reference hashes/profile/prompt/compression policy; a 180-second expiry margin gates annotation. There are no new environment toggles. Prefix and suffix requests use store=true with the same absolute expiry, so storage/input costs must be measured rather than assumed free. Shared label/pretraining settings remain unchanged. See real-photo-feedback.md.

The upstream reference-prefix release uses prompt source manifest v180 and includes training/real_photo_cache.py and training/real_photo_transport.py. This combined application batch retains all previously selected modules and those two actual upstream sources as manifest v282/616. Stored historical model-profile/task fingerprints remain immutable.

Real-photo connection/upload timeout is min(profile timeout, 30 seconds), response reads remain capped at 120 seconds. This is fixed transport policy, with no new setting or model fallback. Upstream source manifest v181 records the change; the combined application manifest is v281/616; stored profiles and historical snapshots are not rewritten.

Explicit real-photo pause clears the active review round into cancelled history, without changing model profiles or automatically resubmitting work. Re-enable retains initialization. Failed cache creation and cancelled annotation attempts still require owner-authorized explicit recovery.

## Detection without an empty-background step

**Status: Authoritative**

No background upload is required to start detection. This adds no configuration switch or database migration. Existing task background IDs and environment records remain readable and training keeps its established selected-background/default fallback. The compatibility environment-background endpoint is retained for existing integrations, while the current detection UI exposes no upload or capture step.

The real-photo annotation-version recovery guard has no new setting, model binding, timeout or fallback. Source manifest v182 records the workflow change; historical snapshots and failed attempts remain unchanged.

The v182 recovery change also permits source-group edits on legacy disabled states with revoked rounds, without enabling optimization or changing any model setting.

Upstream recovery manifest v182 is included in the combined application manifest v282/616. Existing task and profile snapshots retain their recorded source provenance.

## Real-photo source confirmation

Real-photo source confirmation is per-sample metadata, not a deployment flag or a reduced training threshold. `source_group_confirmed=false` and pending placeholder group names exclude the sample from approved counts and independent dataset groups. The frontend group request accepts an optional strict boolean; omitted legacy requests derive confirmation from a non-placeholder group. Source version/history are additive JSON fields. Existing 20-photo, positive-sample and three-source-group gates remain unchanged.

The exact main289 source-confirmation behavior and optional strict-boolean HTTP contract are retained. The fixed current source delta follows the original, main284 and main288 API hash chain; prior source oracles remain immutable. New task provenance uses combined manifest v282/616, including upstream v183, without rewriting historical task snapshots.
