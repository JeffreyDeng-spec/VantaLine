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
