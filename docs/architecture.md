# Architecture

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
The two calls use the fixed Evolving alias and original A layout/comparison prompts.
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
