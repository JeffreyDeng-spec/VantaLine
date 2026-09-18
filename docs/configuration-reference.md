# Configuration reference

Incoming-text store extraction adds no setting. Its three file paths, row adapters
and runtime repository selection remain late-bound. JSON records preserve original
input values rather than replacing them with normalized SQL rows; PostgreSQL keeps
its existing table constraints. Shared JSON formatting and exception behavior stay
unchanged. Prompt-source manifest remains v6; no model-input source moved here.
Decoder and JSON fallback capabilities preserve live callback replacement and
missing-callback ordering without eager validation, retries or backend fallback.

Comparison extraction keeps provider timeouts, external-media/automatic-MATCH
admission and the business prompt version unchanged. Prompt-source manifest v6
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
manifest v6 continues; stored task bindings and historical fingerprints are retained.
Provider getters resolve at the original call expressions, without eager caching
or callable validation. This includes exception-detail conversion and PostgreSQL
confirmation before projection; no new retry or cleanup policy is introduced.

Revision/projection/diagnostic extraction introduces no setting. Diagnostic limits,
logger replacement, public fields and expected-revision errors retain their values.
Source manifest remains v6: these helpers do not move model-input producers.
New fingerprints change normally with listed source edits; old snapshots remain.
Diagnostic hash callback lookup and missing-callable errors retain their evaluation
order. An absent failure message does not obtain a hash callback.

Text media extraction introduces no setting or image-policy change. Provider
maximum side and JPEG quality retain their values and are obtained through explicit
getters at the original expressions. Passthrough never reads JPEG quality; resize
reads the maximum once for comparison and twice for thumbnail dimensions. Input
byte/pixel limits, 1.5x PDF rendering, image fast paths and error
messages remain. New source fingerprints use manifest v6 with the migrated media
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
at execution time. The prompt source manifest uses v6, but edits to listed
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
fingerprints use manifest v6, which includes the actual `accessories/preparation.py`
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
