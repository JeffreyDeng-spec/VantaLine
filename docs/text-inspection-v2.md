# Text inspection v2

The incoming-text medium OCR engine now calls the shared `runtime.paddle` bootstrap
through its existing late provider. Its model parameters, initialization lock and
prediction behavior are unchanged. Source manifest v55 includes the separated small
model runtime and detection OCR producers; existing task snapshots remain immutable.

Legacy incoming-text routes are assembled from `incoming_catalog`,
`incoming_execution`, `incoming_reviews` and `incoming_retention`, through
`incoming_api`. Same-capture returns still precede capacity and image processing;
a losing insert removes only its own source. Quality evaluation remains outside the
engine catch, while OCR/evidence failures settle as review-required. Clone metadata
continues to share source files. Source provenance v55 includes the relocated OCR
input orchestration; historical records and model snapshots are not rewritten.

Incoming-text OCR initialization and Beta comparison cache now have explicit service
owners. Model initialization is locked, while predictions retain their original
concurrency. Beta holds its lock throughout comparison, returns the same cached
result object, expires only when age exceeds the TTL and keeps the pre-OCR timestamp.
A cache hit does not recalculate size or immediately enforce a lowered budget. Model
comparison failures cache REVIEW_REQUIRED, while decode/size/serialization errors
retain their original uncached behavior. Standard PDF decoding retains its existing
single-page, rendering and failure behavior; this extraction is not an OCR change.

Shared JSON-list reads/writes now use the runtime adapter, and legacy incoming-text
records use a dedicated store. Existing JSON uniqueness rules remain deliberately
different: new reference IDs reject duplicate owner/task/version even for ordinary
saves, while inspections reject owner/task/capture duplicates only for insert-only
saves. PostgreSQL keeps its stricter existing constraints. Audit serialization still
occurs only on the PostgreSQL path; JSON retains its prior missing-ID deduplication.
No historical record or old endpoint is removed by this extraction.

The comparison/review HTTP layer is separate from submission and review services.
Submission still prepares inputs before duplicate lookup, writes the source before
the insert-only attempt, and records the provider attempt before calling the model.
Unknown outcomes do not replay. Input construction remains outside the provider try
block; final save and logging also remain outside it. Annotation failure retains
uncertain settlement even if a provider already replied. Human review still saves
before appending its audit; audit failure does not undo the saved review. Evidence
retains account/hash/20 MiB checks, and the three old manual routes remain read-only.

Standard import, library reads and human revision edits have separate business
services and thin HTTP adapters. Import still checks PDF rejection before duplicate
lookup; only legacy DOC extraction enters a thread pool. Its source file precedes
the standard insert and per-asset false inserts retain their original treatment.
Add obtains its repository after writing the file and before its cleanup try block.
An error inside that block deletes the new file but may leave earlier JSON records.
Patch still writes feedback outside the JSON lock even when the human state is
unchanged. Confirmation can start preparation before the confirmed-state shortcut.
These boundaries are preserved by extraction; no new transaction or retry is added.

Revision publication retains the original baseline-then-new-revision sequence and
shared snapshot lists. Baseline insert failure rejects publication; the later
revision insert's false return is still ignored, and an exception may leave the
baseline persisted and the caller's standard mutated. Structural extraction does
not add transactions or change this known boundary. Public projection remains a
deep copy with existing field filtering and URL rules. Diagnostic filtering covers
bounded structured keys and embedded media; it is not general free-text redaction.
The server diagnostic event hashes the failure message instead of logging it.

Verified media and lazy PDF page caching now use an explicit media service; image
normalization/provider copies/annotations live in a separate image module. Cached
media retains priority and failures do not trigger a silent rerender. PNG/JPEG/WEBP
fast paths keep the original bytes, including existing EXIF/transparency behavior;
conversion and white compositing retain their previous fallback/resize branches.
No recognition algorithm, prompt or image tuning changes are included.

Text persistence retains the original reader/writer/decoder lookup timing. Missing
or failing capabilities do not cause retries or fallback. JSON duplicate checks and
attempt status checks remain inside their original complete write-lock boundaries.

Text records use an explicit store service. OCR evidence and extraction rows retain
JSONB objects; other record kinds retain their existing JSON-string representation.
All rows still undergo serialization validation first. JSON normal saves do not
acquire new business-key rejection behavior; insert-only checks remain unchanged.
Owned lookup and terminal CAS retain the existing account/status conditions, with
no query optimization or history/snapshot rewriting in this extraction.

Prepared comparisons no longer copy the server namespace. Submission still writes
original media and a display-only preview before insert-only claim, and duplicate
requests return the existing owned record or reject an inconsistent fingerprint.
Thread-start failure retains its attempting record. OCR cache claims and mapping
attempts remain durable before calls; unknown cache entries cannot trigger replay.
A late timer cannot replace a completed result, and late work cannot reverse a
successful timeout settlement. These guarantees concern the existing Qwen CAS path;
local OCR retains its existing final-save behavior and independent commissioning.
Unknown mapping and region-call outcomes are never retried for the same claim.
The existing algorithm may still run the other separately claimed reread mode.

Standard preparation HTTP routes, jobs and snapshot policy now have explicit
ports. Existing attempt identity and processing-state checks are preserved: a late
interrupted result is diagnostic evidence; source changes can retain a draft result
without publishing it. Publication still checks source and current asset/job state;
this extraction does not add a job-ID guard to result settlement. JSON view calls
retain their existing writes, and PostgreSQL publication remains atomic. OCR and
prompt algorithms, history snapshots and recovery behavior are unchanged.
HTTP timeout settlement captures its compare-and-set writer before constructing the
timeout record. Background settlement resolves the writer after that construction.
Neither an unknown provider result nor an unknown final-publication write is retried.

Label extraction now receives typed account, persistence, verified-media and model
capabilities. Capability reads retain their existing expired-draft cleanup side
effect: history/confirmed roots stay protected and failed tombstone claims cannot
delete media. Immutable edits, single-call provider behavior and evidence byte/hash
validation are unchanged; this batch adds no historical-data cleanup policy.

Document classification routes and background jobs use explicit dependency ports.
Attempts are still persisted before media reads/provider calls; repeated content
reuses the same job-local result, including failures. Human selections and deleted
orders retain their existing protection against late results. Prompt and classifier
logic, stale thresholds and tombstone/history retention are unchanged.

Comparison history now registers through explicit account, record and media ports
in `text_inspection.history`. Existing consumers import the same projection/state
objects through the compatibility module. Old revision selection, evidence hashes,
redaction, pagination and account isolation retain their existing behavior.

Label API, detection-worker and PDF-worker registration now uses typed explicit
capabilities rather than the server namespace. HTTP ownership, imports, settings,
historical references, queue claims and paid-call processing are unchanged. Model
configuration is scoped to the composing application; importing the label package
no longer imports the Web entry point. This batch still uses the embedded workers.

Request authentication and central route policy now live in `auth.sessions`,
`auth.middleware` and `auth.route_permissions`. Text-inspection/Beta permissions
and label endpoint-local guards retain their previous behavior; no provider,
prompt, task state or upload limit changes in this extraction.

The current label workspace retains one owner/task/request/run-bound local photo URL
through submission and completion; result polling updates independent SVG overlays
without replacing the photo node or source. Photo replacement, navigation away and
account changes release this lease. Refresh uses the saved preview without resubmitting.
Historical actuals display their existing 1600px JPEG preview; zoom keeps the preview
visible until the full normalized image loads, with explicit retry on failure. Failed
local decoding falls back to the server preview, then the full normalized image once.
EXIF-oriented browser pixels share the server's oriented coordinate frame; normalized
issue boxes and original-size crop geometry do not depend on preview resolution.
No original or detector input bytes are changed.

Label call diagnostics are internal: the result page shows only a detection ID for
support. `GET /api/label-inspection/runs/{id}/diagnostics` requires administrator role
in addition to inspection permission and current-account ownership; it returns the
preserved run snapshot, quality measurements and call evidence. Ordinary run responses
omit model, prompt hash, layout and transformations, and reduce quality evidence to a
presence marker. Capabilities expose only availability. To trace another account,
authorized operators use the existing restricted runtime repository with owner and run
ID; this change grants no cross-account API access.

The original preparation/OCR APIs documented below remain for compatibility and
historical readers. New primary label submissions use only the following A +
Evolving module; those older pipelines are not part of its execution path.

## Production label mode: A + Evolving

The upper-left back control matches Beta: arrow, text, and right divider;
the list returns to the platform, task/import returns to the task list, and a
result returns to task details. On narrow phones the text is hidden while the
accessible label remains. Pending writes disable the in-workspace back button.

The primary label UI is `/workspace/label-inspection`. One DOC (30 MiB) or DOCX
(100 MiB) creates one named task, up to 500 embedded-image entries. No OCR,
classification, cleaning or standard-activation job is launched. A user selects a
visible valid standard before submitting one uploaded/captured actual image
(maximum 10 MiB / 16 million pixels). Rename, append, hide and restore preserve
immutable standard revisions and historical run evidence. Invalid embedded images
remain listed with a reason; no detection can use missing evidence.

The independent `/api/label-inspection` API provides capabilities, task list/import,
task detail/rename/standard edits, lazy legacy continuation, run submission/read,
on-demand call diagnostics and hash-verified private images. Every route requires
inspection permission and scopes all reads/writes to the current account. Imports
and mutations are idempotent; active runs serialize per task. Refresh only reads.
All media and run snapshots are private and preserved in runtime storage.

`label_inspection/prompts.json` retains A layout and comparison rules, with a versioned coordinate correction for the comparison response. Both
images are EXIF-transposed for orientation, with originals and transforms retained.
Model inputs use longest edge 1600, bicubic resize and JPEG quality 90. Call one
classifies the actual-image layout (512 output tokens). Multi-label images use A's
integer pixel crop/clamp calculation and explicitly check only that selected label.
Call two compares the standard with the full/cropped actual image (8192 tokens).
Both use `doubao-seed-evolving`, temperature 0.1, `thinking.type=disabled` and a
180-second stage timeout. Normal completion makes exactly two paid calls; invalid
layout stops before call two. Network errors, 429, invalid JSON, truncated output,
invalid crop and inconsistent hasDiff/issues cannot produce a passing result.

New comparison responses declare `coordinateSpace=image_input_normalized_v2`.
Each issue rectangle is normalized against its entire input image, including white
margins and document headings, and uses the input orientation even when reading
rotated labels. Standard rectangles map directly to the oriented standard; actual
rectangles are mapped from the selected crop back to the oriented full photograph.
Visible, finite, in-bounds rectangles are retained independently per side/issue and
rendered with matching numbers. Invalid, absent or invisible rectangles are skipped
without hiding valid siblings or changing the difference conclusion. Model boxes
remain approximate visual guidance, not verified pixel segmentation.
Historical label-relative coordinates and responses without the explicit contract
remain unrendered; historical conclusions and evidence are never rewritten. A new
linked detection uses the new prompt hash and produces new annotations. Normal
completion still makes two model calls with the same token/time limits.
Missing confidence
is displayed as not supplied. Similarity is explicitly a model score, never system
accuracy. Valid empty issues show green “未发现差异”; failures remain review-required.

The task list unifies account-owned old text orders and native Beta tasks without
content-similarity merging or model reruns. Old records keep original conclusions
and existing evidence reader. Continuing an old order takes a fresh original-image
snapshot, leaving old rows untouched; missing orders/images are explicit. The
old manual route redirects to unified read-only history or the task list, and the Beta route
and continuation rules remain unchanged.


## Private call audit and lightweight evidence previews

New prepared comparisons save a display-only 1600px JPEG once. The result panel
loads this preview by default with proportional evidence overlays; the explicit
original-image control loads full resolution. Original files and OCR inputs are
unchanged. Existing comparisons can obtain an on-demand preview without changing
their decision/history. Normal-orientation original JPEG/PNG downloads no longer
re-encode the source as PNG. No shared/public image cache is introduced.

Qwen correspondence uses JSON Object output with thinking off and strict local
evidence validation. Default-folded Raw Output links to private per-call request,
input-image, raw response and parsing/failure evidence. Polling excludes raw bodies
and filesystem paths. Keys and authorization headers are excluded; known-key
echoes and inline Base64 media are redacted. Requests remain at-most-once; response
capacity/transport failures retain explicit partial evidence and require review.
Old responses that were never recorded cannot be reconstructed by this feature.

## Activation-time standard preparation (gated experiment)

An independent actual-image reread allowlist adds polled phases
`rereading_regions` and `transcribing_regions` after text mapping. At most eight
candidate regions are reread per round, under the existing total 120s deadline.
Raw Output includes authenticated input thumbnails, per-call usage/state/timing,
source transforms and evidence. Text-only rereads display crop-region bounds,
not invented word boxes. Comparisons remain review-only. Standard preparation
and its saved templates are not rerun. No characters are joined across views.

POST standard `/confirm` delegates to preparation for allowlisted label accounts.
GET/POST `/api/text-inspection/standards/{id}/preparation` query/start durable work;
POST `.../preparation/{asset}/confirm` validates the expected draft/source hash,
records human element edits and publishes an immutable version without model calls.
GET `.../preparation/{asset}/{revision}/{clean|overlay}` serves owner-only evidence.
The existing comparison endpoint consumes prepared snapshots automatically and
returns a task record. GET `/api/text-inspection/prepared-comparisons/{id}` polls
that record; its `/media/reference` serves the standard-element result overlay.
The old image-comparison and original asset-media interfaces remain compatible.

The gallery activation action starts preparation directly; there is no separate
preparation panel or second start action. Progress is restored by GET polling,
never by resubmitting work. Once the batch finishes, unresolved images open in
source-ordinal order, one modal at a time. Closing pauses the queue; Continue
resumes it; Next can defer a difficult image without accepting it. Saving confirms label completeness and ownership in one action, then
advances only after a successful immutable publication. Failed saves preserve edits.
Gallery full-size preview reuses the same element editor for prepared images;
unprepared/excluded images remain read-only. Original-image normalized boxes are
clickable and keyboard operable: uncertain -> keep -> exclude -> keep. Both color
and check/cross/question marks identify states. Keep/uncertain source pixels are
never erased by the browser. The saved cleaned-image preview is explicitly separate
from unsaved edits. Text/box adjustments and bounded Raw Output stay available.
Unknown elements block saving; changed draft/source identities require reopening,
and dirty modal closure requires confirmation. All saves use existing authenticated,
optimistically versioned endpoints; no extra model call or changed matching rule.

Automatic and human-confirmed cleaning group nearby excluded text rectangles and
check their union, not each neighbor as foreign ink. A maximum three-source-pixel
fringe removes tight-OCR edge ink (including antialiasing below 250); the next
three-pixel existing perimeter identifies connected exterior ink below 250. Checks clip to the
image; lack of any checkable perimeter cannot justify nonempty erasure. A failed
group with no separable ink is left intact. Otherwise, exterior-connected nonwhite
components are subtracted and only separable excluded ink is cleared; a nearby
border no longer vetoes the whole group. White/transparent-white pixels are not
rewritten, and diagnostics count retained exterior pixels and actual cleared pixels.
Keep/uncertain and code rectangles are subtracted from erasure and checking masks;
protected RGBA pixels remain byte-identical. No unbounded dilation, largest-component
selection or arbitrary noise tolerance is used. Group IDs, source boxes, bounded
expansion, protected intersections and targeted pixel counts remain evidence. No inpainting
or new model call is involved; historical versions are unchanged. Whitespace trimming uses
all remaining ink, not the text bounding box. Uncertain/mixed boxes, low OCR
confidence, non-label/multiple designs and complex backgrounds require review.
Pure-graphics standards need explicit human `allow_graphics_only: true` confirmation
after successful single-label classification and complete recognition coverage.
Unknown/failed OCR, provider failure, incomplete recovery, unknown element states,
and blank/nearly blank output (fewer than 16 visible pixels) cannot use that path.
This visibility bound is a sanity check, not semantic proof of a label. Zero OCR
elements are allowed only with the same verified pipeline and explicit confirmation.
Published revisions record `graphics_only` and `text_comparison_supported: false`.
The gallery displays a non-comparable reason; direct comparison requests also
return 409 before recognition or task creation. Legacy empty templates are rejected
by contents even without the new flag; queued empty-template work stays review-only
without OCR. Existing request identities and historical evidence are not overwritten.
The VLM must explicitly assess whether visible text regions are covered by OCR;
missing/uncertain coverage cannot auto-activate even if every returned ID matches.
This semantic flag is not a proof of completeness and needs independent acceptance.
The v4 response adds strict `missing_regions` entries (normalized xywh, state,
reason; no recognized text). `coverage_complete` now means existing OCR boxes plus
these proposals cover all visible text. At most eight proposals, each <=20% and
sum <=40% of source area, are accepted. Non-label sources get no supplemental OCR.
Each local crop is scaled at most 3x with 2048-edge/4MP bounds and measured boxes
map through the actual rounded crop/resize dimensions. Only local OCR supplies
new text/IDs; proposals themselves are never erasure masks. Duplicate same-text,
same-state boxes with >=0.8 IoU are deduplicated, while overlaps/conflicts remain
uncertain and do not overwrite earlier evidence. Empty, timed-out or edge-touching
reads block automatic publication. Low-confidence retained readings still need review.
After clearing, a fully blank stripe >=max(12 pixels,4% of the corresponding image
dimension) separating remaining ink groups requires review, even if one group has
no OCR elements. This is an ambiguity guard, not a rule for deleting text: legitimate
borderless white layouts may also require human confirmation. It prevents the
known separated-size-note failure from being automatically accepted.
GET `.../preparation/{asset}/recovery/{region}/{region|ocr}` serves owned local
input/overlay evidence; progress and Raw Output include these images. The shared
60-second supplementation budget includes local OCR queueing; no full-page rerun
or second VLM call is performed. Human adjustments remain model-free.
The template keeps excluded elements and raw observations for audit. Scope is text
and decoded codes; graphics are explicitly unchecked. Missing observations are not
proof of missing print, and MATCH needs separate local-pipeline commissioning.

**Status: Authoritative**

## Opt-in Qwen actual-image evidence

Prepared comparisons may use the separate default-off Qwen OCR account allowlist.
This path reuses saved standard elements, performs independent positioned OCR,
strict direct matching and at most one text-only correspondence request. A durable
owner/image/model cache prevents repeated OCR; unknown outcomes never replay.
The comparison stays review-required in this release, even on exact matches.
The current workspace no longer requires actual-image extraction: upload/capture
the full sheet and start comparison. A missing prepared template is explained at
the start action; finish standard activation first. Old extraction APIs/evidence
remain compatible, but are no longer the primary workspace flow.
`evidence-matching-v2-existence` accepts a standard element after any one strict
occurrence; different repeated reads are retained and do not veto that element.
Direct-match display selects one occurrence, never concatenates repeated copies.
All observations remain stored. `element_presence_satisfied` reports whether all
required elements matched, independently of the still-disabled automatic MATCH.
This scope deliberately cannot certify every individual label or detect mixed
variants when correct content exists elsewhere. No-match remains reviewable.
The start button is beside the actual image with polled stages. Completed results
offer clickable standard boxes and authenticated actual-image evidence, expected
and observed text, plus default-folded OCR/mapping diagnostics. Green denotes
character evidence, yellow uncertainty and red candidate differences requiring
human verification. Graphics remain unchecked. Existing APIs/history are retained;
`prepared-comparisons/{id}/media/source` adds an authenticated normalized source
preview. Invalid/expired results cannot silently become an automatic pass.

Label import accepts `.doc` and `.docx` in the chooser, drag/drop and API. Legacy
DOC directly exports embedded pictures with POI HWPF, without rendering pages or
merging Word overlays. Missing helper/JRE returns 503; extraction failure returns
400 without creating a standard. The original DOC is preserved; no converted DOCX
is created. Images start pending; enabled accounts automatically start background
VLM classification. Non-previewable images remain pending. PDF is unchanged.

### Import image review

The label-order gallery keeps every extracted image visible by default. Retained
label candidates have green emphasis; pending items use amber dashed borders and
an explicit warning; excluded thumbnails are dimmed, not deleted. Preview and
manual controls remain legible, and zoom shows the undimmed source. Count filters
include all, retained, pending and excluded with an empty-filter recovery action.
The label gallery orders retained, pending, then excluded, keeping source ordinal
order within each group. Uploads and status changes recompute this display order;
source numbering, selected IDs and historical snapshots remain unchanged.
Each label asset separates a colored current-state indicator (green retained,
red excluded, orange uncertain) from a neutral action button explicitly naming
the next state. Uncertain and excluded become retained on click; retained
becomes excluded. After resolving uncertainty, clicks alternate retained/excluded.
Saving disables the controls; failed saves preserve the current server state.
The API still supports pending for compatibility, but the UI does not reset a
human decision to pending. Human
choices persist through the existing owned asset PATCH route (`confirm`, `review`,
`remove`); the first edit preserves `original_classification`, and feedback keeps
the action. Draft activation refuses unresolved pending images and requires at
least one retained image. Confirmed-standard edits continue to create immutable
membership revisions; a pending asset cannot be used for comparison.

Retained membership is not reference selection. Confirmed assets expose a
separate "use as comparison reference" action. After saving an extraction,
confirmation remains gated on a selected enabled reference and a valid unchanged
preview. The UI explains the current blocker next to the disabled control and
offers a library navigation action without resetting the crop. Reference changes
still require explicit confirmation against the new standard revision.

`POST /standards/{id}/classify` starts classification for an unclassified draft;
new imports start automatically for enabled accounts. Standard GET returns
`classification` progress; assets retain sanitized attempts, output and usage.
Duplicate POST/import never re-calls. The prompt judges whole-image flat label
artwork versus manuals, packaging, placement diagrams, photographs, other and
uncertain. Labels attached to photographed objects are not flat label artwork.
This step does not crop or generate masks. Human changes override late results.
Confirmation waits for processing and pending review to finish. A stale heartbeat
(150s) becomes interrupted on polling, without automatic replay or paid retry.

`DELETE /standards/{id}` requires ownership and inspection permission. It marks
a label order deleted with actor/time and removes it from the list; edits,
activation and new comparison reject deleted orders. UI confirmation is required.
Original media and immutable revisions remain readable by their owner. An already
submitted call may finish but cannot change deleted membership; subsequent calls
stop. Reimport of a deleted material/version requires a new version label because
historical uniqueness is retained. Deletion is not disk cleanup or evidence erasure.

The formal **文字检验** entry is account scoped and independent from product/YOLO tasks. It contains label comparison and PDF page comparison in the same task workspace. The previous `incoming_material_text` task workflow remains readable for existing records during the rollback window, but its “旧版” task-creation entry is no longer exposed; all new label comparison work starts from **文字检验**.

## Release stages

1. **Expand (completed):** add v2 tables, account-scoped APIs, safe DOCX candidate extraction, lazy PDF pages, confirmed immutable versions, idempotent comparison attempts, and the new UI. Old tables and APIs remain untouched.
2. **UI consolidation (current):** remove the legacy creation affordance while preserving existing legacy tasks and rollback-compatible routes. The label bench accepts either a live camera capture or an uploaded PNG/JPG/WEBP as the actual image. Its camera input lists available video devices, supports explicit switching, refreshes after device changes and keeps capture disabled while a stream is opening or unavailable. Permission denial or device removal leaves the uploaded-image alternative available. The label workspace has two columns: the order library and its vertically scrollable asset gallery on the left, and the actual-image surface on the right. Clicking an enabled gallery thumbnail selects and highlights it as the sole comparison reference; “view full image” remains independent from selection. There is no standalone local-reference upload surface. Import uses a modal, while every add, select, soft-disable, re-enable and initial-confirm action is available directly inside the expanded order. Standard documents, appended order images and actual images use the shared keyboard-accessible chooser/drop target, followed by their domain-specific validation. The workspace omits the former persistent scope-warning badge; the authoritative inspection limits remain documented below and enforced by the service gates.
3. **Migrate/observe:** tenant-by-tenant copy or cleanup is a separately authorized operation with backup/restore evidence, counts and hashes. It must not run from an automatic release.
4. **Contract:** after the observation and rollback windows, a separate PR may freeze and then remove old routes and permissions. Additive database policy keeps empty historical tables.

## Trust boundaries

- `owner_user_id` is always derived from the authenticated session; request IDs never select another account. Media downloads repeat the ownership check and validate the resolved path.
- DOCX imports are size/entry/ratio bounded, reject path traversal, external relationships and macros, and read only document XML plus `word/media`. OLE payloads are quarantined and never opened. Automatic classification only changes visibility; a user can restore every extracted candidate before confirmation.
- `.doc` uses direct POI image extraction, not LibreOffice conversion. A fixed helper bundle and Java runtime must be commissioned before production imports. Word overlays, crop settings and unrelated embedded OLE documents are not rendered or exported.
- PDF metadata is validated synchronously; the unified importer renders all split pages in a durable background job before publishing revision 1. Historical manual pages retain their original lazy read compatibility.
- The external VLM receives only one confirmed standard image and one capture. The service writes an `attempting` record before the call, uses one provider attempt, and never re-calls an uncertain comparison ID. Provider/schema/prompt failures become `REVIEW_REQUIRED`.
- Every label comparison persists a bounded diagnostic envelope in the same account-scoped record. It includes prepared image dimensions, byte counts, formats and hashes; provider/model/endpoint host and timeout; stage-by-stage timestamps; provider latency, HTTP/timeout/retry and usage metadata when returned; the parsed model response; the exact validation or post-processing failure stage and message; and a bounded raw model-text preview when JSON parsing fails. Embedded image data, authorization headers, cookies, tokens, API keys and secrets are redacted. A compact structured event is also written to the service log without model text or media. Diagnostics never authorize an automatic retry of an uncertain charged request.
- The comparison result exposes the already-sanitized provider output in a native, default-closed `Raw Output` disclosure. Successful responses show the parsed model JSON rather than an unbounded byte-for-byte body; invalid JSON may show the bounded raw-text preview. The provider-adapted value is shown separately so operators can distinguish model output from the value entering domain validation. The UI applies an additional display limit and never renders secrets, request headers or embedded media.

## API

### Comparison history

The title-right History entry lists only this account's label comparisons, not
manual sessions, legacy incoming-material tasks or the separate Codex beta.
`GET /api/text-inspection/history?q=&result=all&limit=20&cursor=` returns summaries
and an opaque next cursor; supported result filters are MATCH, DIFFERENCES and
REVIEW_REQUIRED. Execution state (processing/completed/failed/timeout/review)
is separate from the comparison decision. Limit is capped at 100.
`GET /history/{id}` returns the saved result and element evidence;
`GET /history/{id}/diagnostics` loads sanitized logs only on disclosure.
`GET /history/{id}/media/{thumbnail|preview|source|reference|annotated-preview}`
rechecks ownership and hashes. Missing historical media is not replaced with a
current standard. New records snapshot order/material/version/ordinal metadata;
older current-name lookups are labelled, including for deleted orders.
No history GET starts OCR, resubmits, edits a decision or clears an unknown claim.
The same modal switches list/detail and preserves filters/list scroll on Back.
Results reuse the live presentation; zoom keeps selection, logs are collapsed,
and full-resolution sources require explicit action. History is independent from
the active workbench task. There is no delete/export/recompare action in v1.

### Single-label extraction

An additional account-gated experimental `method=vlm_bbox` searches the **whole** image, canonicalizing target to `[0,0,1,1]`; guide coordinates do not select its target. Capabilities expose `bbox_enabled` and `bbox_available`. Its prompt is the original colleague multi-label layout prompt, ported to Qwen: normalized `cropRect` values are validated strictly, not clamped. Single/no-label replies without a rectangle fail closed rather than silently comparing the whole photograph. The known prompt limitation (no single-label coordinates requested) is preserved for the first baseline, not hidden by a second paid call.

The new method stores its algorithm version in request identity and the resolved model in task diagnostics. Input preview is available at the existing authenticated media route with `kind=input`. Output rectangles copy original pixels without dilation; human polygon revisions also use zero expansion for this method. Small rectangles may be inspected, but cannot be confirmed below the unchanged 100-pixel minimum. Confirmation freezes the exact inspected PNG bytes after source/geometry checks. Rectangles are candidates, never certified physical boundaries; no synthetic rectangle is presented as a model mask. All old methods retain their defaults.

`scripts/benchmark_label_bbox.py` runs at most nine original images against a single frozen existing server configuration through SSH. It writes no server code/media, never retries a claimed round, and saves inputs, sanitized responses, usage, rectangles, crops and independent visual reviews outside Git. First-round parameters are one prompt, 1600-pixel maximum edge, JPEG 90, temperature 0.1, 512 output tokens and disabled Qwen thinking. Pillow bicubic replaces Windows GDI+ bicubic, so model input JPEGs are not claimed byte-identical to the Windows application. This is a Qwen port, not a Doubao reproduction. A successful HTTP response or valid geometry is not label acceptance.

Accounts listed in `VANTALINE_LABEL_EXTRACTION_ACCOUNTS` use a guide/extract/preview/confirm workflow for both camera frames and uploaded actual images. The default guide covers the central 70% of the contained image, excluding letterboxes. Pointer and keyboard controls change normalized coordinates. Captures freeze the photo and guide; later input changes discard stale extraction responses. Operators can edit rectangular, circular or irregular polygons, save a preview, and explicitly confirm the selected standard before comparison.

`POST /api/text-inspection/extractions` accepts `file`, normalized `[x,y,width,height]` target, `request_id` and `method=ai|manual`. A durable claim precedes one image-generation call; repeated IDs never repeat that call. `GET /api/text-inspection/extractions/{id}` reads the latest revision. A lost worker remains uncertain and is never automatically replayed. `POST .../{id}/revise` accepts `version`, `polygon`, `confirm` and (for confirmation) `standard_asset_id`. Immutable revision inserts reject concurrent/stale edits. Confirmation only accepts a previously saved preview, binds the current standard revision, and is invalidated by subsequent edits. The compare endpoint accepts `extraction_id` or the legacy `captured_file`, never both; the enabled UI only sends confirmed extraction IDs. Media routes enforce account ownership and content hashes.

Image-generation settings are independent of Qwen text-comparison settings. The provider receives a 10%-expanded ROI explicitly padded to a square (never stretched); all padding/scaling transforms are recorded. A label-specific parser rejects multiple candidates, off-center targets, aspect changes, non-binary images and guide/image-edge crossings. Weak original-edge support requires manual adjustment. The crop is made from orientation-normalized original pixels, with white background and a two-pixel outward safety margin; no generated pixels, erosion, text repair or perspective resampling enter comparison. Geometry checks do not prove semantic completeness: operator confirmation remains mandatory and ordinary comparison quality gates remain in force.

Extraction diagnostics and authenticated source/mask/crop previews are available in a default-collapsed disclosure. Used extraction evidence is retained with comparison history. Unconfirmed, unreferenced drafts older than seven days are expired lazily on account capability checks; an atomic expiration revision competes with confirmation, and confirmed roots are conservatively retained. Retention never runs from the release installer. Old request IDs remain tombstoned so expiration cannot cause automatic paid replays.

The `/api/text-inspection` namespace requires `inspection`. Standards, assets, records, sessions and pages are limited to the current authenticated account. Main routes are standards import/list/detail/asset add/asset classification/confirm, label compare, read-only manual history, and label inspection review. Old manual session create/page/complete return HTTP 410. Confirmed asset mutations append their revision snapshots internally in the same transaction.

A user may add or remove images from the logical order standard at any time. The service implements that promise without rewriting audit history: the standard row represents the current logical order, while every confirmed mutation appends an immutable numbered revision containing the selected asset IDs and hashes. Delete is a reversible soft deletion and never physically removes media referenced by a revision or inspection record. Initial draft confirmation freezes revision 1; later add, remove and restore operations on the confirmed logical standard atomically advance its current revision. For confirmed standards created before the revision ledger existed, the first real edit first records the pre-edit membership as baseline revision 1, then records the requested edit as revision 2 in the same lock or transaction. Historical revisions remain read-only and available for traceability. Every comparison records the exact revision ID, revision number and reference hash that it used, and only an asset in the current confirmed snapshot may be selected for a new production comparison.

The client accepts exactly one reference source: a selected asset from the current confirmed order revision. Selecting another enabled thumbnail preserves the actual image but clears stale comparison output and identity. Replacing the actual image preserves the selected gallery asset. An unchanged retry may reuse its comparison identity, but changed inputs must not. Draft, pending and soft-disabled assets cannot be submitted as production comparison standards.

Image acceptance is content-based rather than extension- or browser-MIME-based. The client permits common image files without a narrow MIME rejection. The service keeps native PNG, JPEG and WebP inputs when OpenCV can read them, and flattens any other Pillow-decodable format (including common MPO, AVIF, BMP, GIF and TIFF variants available in the production decoder) to an orientation-corrected first-frame JPEG with a white transparency background. The 10 MB upload limit, 20-megapixel bound, minimum dimensions and complete-decode checks remain fail-closed. Records retain the detected source format and hashes for both original reference evidence and normalized model input.

Full-resolution prepared evidence remains stored for audit and annotation. Only the copy embedded in a label-comparison provider request is reduced when necessary to a 2048-pixel longest edge, using high-quality resampling and JPEG encoding, and label comparison enforces a 30-second minimum provider timeout. Diagnostics record both evidence and provider-copy dimensions, byte counts and hashes so transport optimization remains reviewable.

Provider responses pass through a provider-scoped adapter before the strict domain validator. For Qwen VL only, its 0–1000 box convention is converted to 0–1, percentage confidence is converted to a fraction, and `text_mismatch` is mapped from the compared text to `missing`, `extra` or `wrong_text`. Exact-equal reference/actual pairs are discarded, while case, spacing and punctuation differences remain significant. If all reported differences were exact-equal artifacts, the result fails closed to `REVIEW_REQUIRED`; the adapter never manufactures `MATCH`. The comparison prompt limits evidence to text physically printed inside the label and excludes surrounding specification metadata or document annotations.

The scoped-label instruction is recorded as prompt version `text-compare-v2-prompt-2`, and remains part of comparison identity so records created under earlier prompt semantics cannot be mistaken for an unchanged request.

The label workspace is responsive by available width and height, not by a single fixed canvas. On desktop, the account context, title, explanation and mode switch share a compact top strip; the order header also collapses sparse guidance into one line. The gallery becomes independently scrollable and the actual-image stage uses viewport-relative height so inspection imagery receives most of the visible area. At medium widths the two panels stack, and narrow or short screens progressively reduce spacing, typography and secondary chrome while preserving usable primary actions and image zoom.

The first classifier is a deterministic local context classifier with manual feedback. The customer fixture must keep `image1`–`image6` as label candidates and collapse `image7`–`image18` into packaging, dieline, manual/insert, carton, placement or photo categories. No classified asset is physically deleted.

## Remaining production gates

### Comparison progress and result dialog

The result contains one standard image. Its upper-right zoom button opens the
existing in-dialog viewer; element clicks still select actual-image evidence.
Returning preserves element selection. Older/malformed element output retains
one zoomable standard image instead of hiding the reference or duplicating it.

Starting a text comparison immediately opens a native modal dialog. The complete
summary, element evidence, differences, high-resolution opt-in and collapsed Raw
Output live there; closing keeps the task running. The workspace action becomes
`对比中 · 查看进度` then `查看结果`; completion never reopens a dismissed dialog.
Next image or another selected standard detaches the old task without mutating
its historical evidence. Historical results remain readable if a standard is
later disabled; this does not authorize a new comparison against that standard.

Estimated progress uses elapsed client time: 1–35% over 10s, 35–70% over the next
20s, 70–90% over the next 30s, then one percent per 12s up to 95%. It is explicitly
an estimate; only a stored `completed` record displays 100%. Failed/timeout
records show their reason. Desktop is bounded to 1200px / 90dvh; mobile is full
screen. Escape/close restore trigger focus, backdrop clicks do not dismiss, and
the mounted result preserves selection/scroll when returning from image zoom.

`GET /api/text-inspection/prepared-comparisons/by-request/{request_id}` is a
read-only recovery endpoint requiring inspection permission and current-owner
binding. PostgreSQL uses the existing `(owner_user_id, comparison_id)` key; the
fallback repository filters both fields. Unknown or other-owner requests return
404. No model call, timeout transition or history rewrite occurs in this lookup.
Subsequent record-ID polling retains the existing backend timeout semantics.

`text-comparison:v1:<account>` sessionStorage contains only request/record IDs,
standard/asset/image identity metadata, start time, definitive submission-rejection
flag and dialog visibility. Definitive invalid/forbidden/conflicting uploads stop
immediately; their rejection flag survives refresh without re-uploading. Refresh
restores those fields and queries the server, without uploading again. Network
errors/401 preserve the task and retry GETs; 403 or a missing known record stop
with an access error. A missing request is queried for a 30s acknowledgment grace
period, then asks for a new image. Files not received by the server cannot be
recovered. Closing the browser tab ends this tab-local recovery scope.

External media sending defaults off (`VANTALINE_TEXT_INSPECTION_EXTERNAL_VLM_ENABLED`). Even after consent enables sending, `MATCH` remains review-only until `VANTALINE_TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED` is set after customer samples, account budgets/rate limits, prompt/model pinning and commissioning evidence pass. Manual completion cannot return PASS until `VANTALINE_TEXT_INSPECTION_MANUAL_PASS_VERIFIED` is set after page lease/fencing and multi-tab recovery tests pass.

## Developing browser tools

The WebMCP workspace hooks reuse current standard/asset selection, document
import, comparison, camera and extraction-revision callbacks. Geometry tools
use source-normalized guide and polygon coordinates, not viewport pixels.
The native browser fixture covers selection and import-field state; complete
workflow equivalence and all inspection modes remain separate acceptance work.
Activation and limitations are documented in [Agent platform status](agent-platform.md).

Asynchronous import/continuation/submission responses may update navigation only
while the originating account component and view are still current. Leaving the
page or signing out never lets a late response return the browser to an old task.

Invalid imported images remain visible by default with their decoding/limit reason
and cannot be selected for detection; hiding valid standards remains reversible.


### Fixed fullscreen task workspace

Task views fill the viewport without document scrolling. Desktop images share equal
columns; below 850px standard/actual tabs replace the two columns, and selecting a
standard opens the actual tab. Camera and actual-image preview occupy one stage.
The compact header contains Beta-style back navigation, task-name rename dialog,
version, fullscreen toggle and a more menu. Existing-task and new-task clicks request
browser fullscreen before asynchronous work; import-to-task transitions retain the
root. Esc/manual exit never forces reentry. Reloads, deep links, denied/unsupported
fullscreen retain the fixed viewport and a usable manual toggle. All dialogs remain
inside the fullscreen root. Only this module's fullscreen is exited on leave.

The result/history dock defaults to 32% and has pointer/keyboard resizing from
20% to 45%, with a small-viewport minimum so its scrollable body remains reachable.
Detection and summary controls remain outside scrolling bodies. Gallery, issues,
history, diagnostics and lengthy notices scroll locally without chaining to the page.
Images use measured available space and intrinsic aspect ratio; crop overlays share
the fitted image rectangle. The top-right thumbnail CircleMinus control hides a
standard and RotateCcw restores it, using existing immutable-version operations;
they cannot select the thumbnail. Invalid images keep their reason and no action.
Icons have names/tooltips and 32px desktop/44px coarse-pointer hit areas.

Native file pickers can exit browser fullscreen (including macOS Edge). The label
workspace remembers fullscreen only for that picker gesture and attempts restoration
on file selection while transient user activation is available. Cancellation, explicit
exit and navigation clear that intent; upload completion never forces fullscreen.
When restoration is unavailable the fixed viewport and manual toggle remain usable.

The default abnormality list shows one line per issue (number, type, description) at 16px. Long descriptions use ellipsis with full evidence in the Details dialog; standard/actual text, severity, model confidence and positioning notes are preserved there. The default dock uses 32% of the operation area and remains adjustable. Desktop rows are 32px (44px for touch). Six rows fit at 1920x1080 and five at 1440x900 with the default dock. Existing valid boxes have matching issue numbers, with selected boxes highlighted. Unlocated issues remain textual.

## Conservative label photo quality gate

Before any Evolving call, local grayscale/Otsu segmentation, closing and external
contours locate candidate dark labels. Area, aspect, solidity, fill, border and
surrounding-contrast checks reject unreliable candidates; no largest-dark-blob
fallback is used. External contours consolidate nested regions. Analysis excludes
label borders and flat blocks, measures native/input size and normalized internal
Laplacian variance. Only obvious size/focus failures are commissioned; weak-block,
brightness and darkness fractions are diagnostic, not standalone rejection rules.
Missing text/icons are not quality criteria. Local glare/blur can still be missed.

At least one candidate must pass. Layout's crop must contain at least 90% of one
candidate's bounding rectangle and must not overlap another by more than 10%; an
uncropped result requires exactly one candidate. An ambiguous selection or a bad
selected candidate stops after one call without automatic reselection. A good
cropped selection is remeasured on its unchanged comparison JPEG. All input images,
prompts, temperatures and model parameters remain byte-equivalent for admitted runs.

Quality failures save reason/metrics/policy/stage/timing in optional `quality`
run data and `error_code`, use failed/REVIEW_REQUIRED, and create no comparison
result. Diagnostics return `quality` alongside calls. The workspace shows an
unfinished-comparison message and a retry action retaining the selected standard;
retry creates a linked run. Old history explicitly says quality was not checked.

Initial private calibration used six distinct files (four clearer, two visibly
low-quality) covering two dark label designs. Several files depict closely related
scenes, so these are not six independent capture conditions. Automatic candidate
bounds were visually checked. A fixed grid of minimum short side 200..300 by 25
and focus 200..1600 by 200 selected the lowest lexicographic feasible pair (200,
1000). This is calibration, not held-out validation or a production accuracy claim.
Other colors, clipped labels and uncertain localization may require retaking.

Direct standard-image import uses the same task POST and request id: JPG/JPEG, PNG, WebP or BMP, at most 10 MiB and 16 million pixels. Extension must match the decoded format; animated/multi-frame, unsupported, corrupt or oversized files fail before task creation. One complete image creates exactly one enabled standard (ordinal 1, revision 1), without label splitting, extraction calls or actual-photo quality screening. Original bytes, EXIF-normalized image and preview use existing private media storage. The task name defaults to the filename stem; source `image` is displayed/filterable as “图片上传”. Word, legacy and Beta sources remain compatible. Standard append/hide/restore and later actual-photo quality checks are unchanged.

## Purpose-specific provider selection

Label layout and comparison share the `label` profile. Manuals use `manual`,
fixed when a manual session is submitted. Preparation/legacy text uses `document`;
dedicated OCR uses `ocr`. Existing Qwen-specific paths still validate their provider
and pinned OCR model. Label runs persist ID/version and retain the existing prompt,
validation and at-most-once/no-automatic-retry policy. Administrators configure
these bindings in Settings; business submissions cannot choose arbitrary keys or
profiles. Codex Beta remains its dedicated engine and retains its existing gates.


## Unified PDF page comparison

New tasks accept PDF (200 MiB) through the existing `/api/label-inspection/tasks` multipart route.
Displayed orientation, including page rotation, decides splitting: width > height creates left then right;
portrait and square pages stay whole. Keep original sequence, duplicates, blank pages and printing helpers.
Each half/full-page clip is rendered directly to a 3200px longest-edge RGB image with its source page,
rotation and display-space clip preserved. No OCR, classification, helper cleanup or automatic matching.
The split result has at most 500 standards. Task JSON stores source `pdf` and import progress; POST returns
202. One global leased importer checkpoints each deterministic page. Restart reclaims an expired lease;
old tokens cannot publish. Only complete imports publish immutable revision 1. Failed imports remain
visible and cannot submit detection. Existing image/Word limits and behavior are unchanged.

PDF tasks use `pdf-page-v1`, frozen at submission together with prompt hash, quality policy and profile
snapshot. The label credential/endpoint binding supplies transport; the PDF model is fixed to
`doubao-seed-evolving` on Doubao, thinking disabled, temperature 0.1, 180 seconds per stage. Both stages
use max-edge 3200 JPEG90 without upsampling. Layout (1024 tokens) receives only the actual image and
requires exactly one complete, readable, confidently located page. Invalid bounds, multiple pages,
missing edges and unreadable content stop after one call. Comparison (8192 tokens) receives the selected
standard and rectangle crop from the orientation-normalized original photo. It checks all page content,
including punctuation, case, figures, page numbers and formal footers, while ignoring print helpers
outside the finished page and photographic distortions. Uncertain reading, contradictory results,
truncation and invalid JSON never pass. Reliable numbered boxes map back to original image coordinates.
No perspective correction, local black-label quality gate or uncalibrated paper blur threshold is used.
File decode failures make zero calls; a normal inspection makes two. Existing label prompts, input bytes,
quality gate and at-most-once call semantics are unchanged. PDF preview rendering is not a real-photo
accuracy benchmark. Ordinary inspection never dispatches PLC operations.

There are no separate manual creation entries or mode switches. The existing fullscreen task grid and
camera are reused, with page wording and “每次只拍一页”. Old orders, sessions and pages appear through
an owner-scoped read-only adapter; old identified URLs resolve to history, other old URLs to the task list.
Missing photos/associations are explicitly shown. Old manual writes (including edits/reviews) are disabled;
new work requires a new PDF import. Beta retains its own route and behavior.


PDF result compatibility: optional `consistentItems` entries may be strings or objects with a string `description`. Only that non-decision summary is normalized; raw provider evidence remains immutable. Missing/invalid descriptions and contradictory difference decisions still fail closed. Label parsing, PDF prompts, image inputs and model settings are unchanged. The PDF scope caption refers to page content rather than other labels. A regression covers enriched agreement summaries, input immutability and contradictory results.
