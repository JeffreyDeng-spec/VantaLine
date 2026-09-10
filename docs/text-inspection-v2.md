# Text inspection v2

**Status: Authoritative**

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

The formal **文字检验** entry is account scoped and independent from product/YOLO tasks. It contains label comparison and a manual-page pilot. The previous `incoming_material_text` task workflow remains readable for existing records during the rollback window, but its “旧版” task-creation entry is no longer exposed; all new label comparison work starts from **文字检验**.

## Release stages

1. **Expand (completed):** add v2 tables, account-scoped APIs, safe DOCX candidate extraction, lazy PDF pages, confirmed immutable versions, idempotent comparison attempts, and the new UI. Old tables and APIs remain untouched.
2. **UI consolidation (current):** remove the legacy creation affordance while preserving existing legacy tasks and rollback-compatible routes. The label bench accepts either a live camera capture or an uploaded PNG/JPG/WEBP as the actual image. Its camera input lists available video devices, supports explicit switching, refreshes after device changes and keeps capture disabled while a stream is opening or unavailable. Permission denial or device removal leaves the uploaded-image alternative available. The label workspace has two columns: the order library and its vertically scrollable asset gallery on the left, and the actual-image surface on the right. Clicking an enabled gallery thumbnail selects and highlights it as the sole comparison reference; “view full image” remains independent from selection. There is no standalone local-reference upload surface. Import uses a modal, while every add, select, soft-disable, re-enable and initial-confirm action is available directly inside the expanded order. Standard documents, appended order images and actual images use the shared keyboard-accessible chooser/drop target, followed by their domain-specific validation. The workspace omits the former persistent scope-warning badge; the authoritative inspection limits remain documented below and enforced by the service gates.
3. **Migrate/observe:** tenant-by-tenant copy or cleanup is a separately authorized operation with backup/restore evidence, counts and hashes. It must not run from an automatic release.
4. **Contract:** after the observation and rollback windows, a separate PR may freeze and then remove old routes and permissions. Additive database policy keeps empty historical tables.

## Trust boundaries

- `owner_user_id` is always derived from the authenticated session; request IDs never select another account. Media downloads repeat the ownership check and validate the resolved path.
- DOCX imports are size/entry/ratio bounded, reject path traversal, external relationships and macros, and read only document XML plus `word/media`. OLE payloads are quarantined and never opened. Automatic classification only changes visibility; a user can restore every extracted candidate before confirmation.
- `.doc` uses direct POI image extraction, not LibreOffice conversion. A fixed helper bundle and Java runtime must be commissioned before production imports. Word overlays, crop settings and unrelated embedded OLE documents are not rendered or exported.
- PDF metadata is validated synchronously, but pages are rendered lazily with page and pixel limits. The complete action is the only time missing pages are calculated.
- The external VLM receives only one confirmed standard image and one capture. The service writes an `attempting` record before the call, uses one provider attempt, and never re-calls an uncertain comparison ID. Provider/schema/prompt failures become `REVIEW_REQUIRED`.
- Every label comparison persists a bounded diagnostic envelope in the same account-scoped record. It includes prepared image dimensions, byte counts, formats and hashes; provider/model/endpoint host and timeout; stage-by-stage timestamps; provider latency, HTTP/timeout/retry and usage metadata when returned; the parsed model response; the exact validation or post-processing failure stage and message; and a bounded raw model-text preview when JSON parsing fails. Embedded image data, authorization headers, cookies, tokens, API keys and secrets are redacted. A compact structured event is also written to the service log without model text or media. Diagnostics never authorize an automatic retry of an uncertain charged request.
- The comparison result exposes the already-sanitized provider output in a native, default-closed `Raw Output` disclosure. Successful responses show the parsed model JSON rather than an unbounded byte-for-byte body; invalid JSON may show the bounded raw-text preview. The provider-adapted value is shown separately so operators can distinguish model output from the value entering domain validation. The UI applies an additional display limit and never renders secrets, request headers or embedded media.

## API

### Single-label extraction

An additional account-gated experimental `method=vlm_bbox` searches the **whole** image, canonicalizing target to `[0,0,1,1]`; guide coordinates do not select its target. Capabilities expose `bbox_enabled` and `bbox_available`. Its prompt is the original colleague multi-label layout prompt, ported to Qwen: normalized `cropRect` values are validated strictly, not clamped. Single/no-label replies without a rectangle fail closed rather than silently comparing the whole photograph. The known prompt limitation (no single-label coordinates requested) is preserved for the first baseline, not hidden by a second paid call.

The new method stores its algorithm version in request identity and the resolved model in task diagnostics. Input preview is available at the existing authenticated media route with `kind=input`. Output rectangles copy original pixels without dilation; human polygon revisions also use zero expansion for this method. Small rectangles may be inspected, but cannot be confirmed below the unchanged 100-pixel minimum. Confirmation freezes the exact inspected PNG bytes after source/geometry checks. Rectangles are candidates, never certified physical boundaries; no synthetic rectangle is presented as a model mask. All old methods retain their defaults.

`scripts/benchmark_label_bbox.py` runs at most nine original images against a single frozen existing server configuration through SSH. It writes no server code/media, never retries a claimed round, and saves inputs, sanitized responses, usage, rectangles, crops and independent visual reviews outside Git. First-round parameters are one prompt, 1600-pixel maximum edge, JPEG 90, temperature 0.1, 512 output tokens and disabled Qwen thinking. Pillow bicubic replaces Windows GDI+ bicubic, so model input JPEGs are not claimed byte-identical to the Windows application. This is a Qwen port, not a Doubao reproduction. A successful HTTP response or valid geometry is not label acceptance.

Accounts listed in `VANTALINE_LABEL_EXTRACTION_ACCOUNTS` use a guide/extract/preview/confirm workflow for both camera frames and uploaded actual images. The default guide covers the central 70% of the contained image, excluding letterboxes. Pointer and keyboard controls change normalized coordinates. Captures freeze the photo and guide; later input changes discard stale extraction responses. Operators can edit rectangular, circular or irregular polygons, save a preview, and explicitly confirm the selected standard before comparison.

`POST /api/text-inspection/extractions` accepts `file`, normalized `[x,y,width,height]` target, `request_id` and `method=ai|manual`. A durable claim precedes one image-generation call; repeated IDs never repeat that call. `GET /api/text-inspection/extractions/{id}` reads the latest revision. A lost worker remains uncertain and is never automatically replayed. `POST .../{id}/revise` accepts `version`, `polygon`, `confirm` and (for confirmation) `standard_asset_id`. Immutable revision inserts reject concurrent/stale edits. Confirmation only accepts a previously saved preview, binds the current standard revision, and is invalidated by subsequent edits. The compare endpoint accepts `extraction_id` or the legacy `captured_file`, never both; the enabled UI only sends confirmed extraction IDs. Media routes enforce account ownership and content hashes.

Image-generation settings are independent of Qwen text-comparison settings. The provider receives a 10%-expanded ROI explicitly padded to a square (never stretched); all padding/scaling transforms are recorded. A label-specific parser rejects multiple candidates, off-center targets, aspect changes, non-binary images and guide/image-edge crossings. Weak original-edge support requires manual adjustment. The crop is made from orientation-normalized original pixels, with white background and a two-pixel outward safety margin; no generated pixels, erosion, text repair or perspective resampling enter comparison. Geometry checks do not prove semantic completeness: operator confirmation remains mandatory and ordinary comparison quality gates remain in force.

Extraction diagnostics and authenticated source/mask/crop previews are available in a default-collapsed disclosure. Used extraction evidence is retained with comparison history. Unconfirmed, unreferenced drafts older than seven days are expired lazily on account capability checks; an atomic expiration revision competes with confirmation, and confirmed roots are conservatively retained. Retention never runs from the release installer. Old request IDs remain tombstoned so expiration cannot cause automatic paid replays.

The `/api/text-inspection` namespace requires `inspection`. Standards, assets, records, sessions and pages are limited to the current authenticated account. Main routes are standards import/list/detail/asset add/asset classification/confirm, label compare, manual session create/page/complete, and inspection review. Confirmed asset mutations append their revision snapshots internally in the same transaction.

A user may add or remove images from the logical order standard at any time. The service implements that promise without rewriting audit history: the standard row represents the current logical order, while every confirmed mutation appends an immutable numbered revision containing the selected asset IDs and hashes. Delete is a reversible soft deletion and never physically removes media referenced by a revision or inspection record. Initial draft confirmation freezes revision 1; later add, remove and restore operations on the confirmed logical standard atomically advance its current revision. For confirmed standards created before the revision ledger existed, the first real edit first records the pre-edit membership as baseline revision 1, then records the requested edit as revision 2 in the same lock or transaction. Historical revisions remain read-only and available for traceability. Every comparison records the exact revision ID, revision number and reference hash that it used, and only an asset in the current confirmed snapshot may be selected for a new production comparison.

The client accepts exactly one reference source: a selected asset from the current confirmed order revision. Selecting another enabled thumbnail preserves the actual image but clears stale comparison output and identity. Replacing the actual image preserves the selected gallery asset. An unchanged retry may reuse its comparison identity, but changed inputs must not. Draft, pending and soft-disabled assets cannot be submitted as production comparison standards.

Image acceptance is content-based rather than extension- or browser-MIME-based. The client permits common image files without a narrow MIME rejection. The service keeps native PNG, JPEG and WebP inputs when OpenCV can read them, and flattens any other Pillow-decodable format (including common MPO, AVIF, BMP, GIF and TIFF variants available in the production decoder) to an orientation-corrected first-frame JPEG with a white transparency background. The 10 MB upload limit, 20-megapixel bound, minimum dimensions and complete-decode checks remain fail-closed. Records retain the detected source format and hashes for both original reference evidence and normalized model input.

Full-resolution prepared evidence remains stored for audit and annotation. Only the copy embedded in a label-comparison provider request is reduced when necessary to a 2048-pixel longest edge, using high-quality resampling and JPEG encoding, and label comparison enforces a 30-second minimum provider timeout. Diagnostics record both evidence and provider-copy dimensions, byte counts and hashes so transport optimization remains reviewable.

Provider responses pass through a provider-scoped adapter before the strict domain validator. For Qwen VL only, its 0–1000 box convention is converted to 0–1, percentage confidence is converted to a fraction, and `text_mismatch` is mapped from the compared text to `missing`, `extra` or `wrong_text`. Exact-equal reference/actual pairs are discarded, while case, spacing and punctuation differences remain significant. If all reported differences were exact-equal artifacts, the result fails closed to `REVIEW_REQUIRED`; the adapter never manufactures `MATCH`. The comparison prompt limits evidence to text physically printed inside the label and excludes surrounding specification metadata or document annotations.

The scoped-label instruction is recorded as prompt version `text-compare-v2-prompt-2`, and remains part of comparison identity so records created under earlier prompt semantics cannot be mistaken for an unchanged request.

The label workspace is responsive by available width and height, not by a single fixed canvas. On desktop, the account context, title, explanation and mode switch share a compact top strip; the order header also collapses sparse guidance into one line. The gallery becomes independently scrollable and the actual-image stage uses viewport-relative height so inspection imagery receives most of the visible area. At medium widths the two panels stack, and narrow or short screens progressively reduce spacing, typography and secondary chrome while preserving usable primary actions and image zoom.

The first classifier is a deterministic local context classifier with manual feedback. The customer fixture must keep `image1`–`image6` as label candidates and collapse `image7`–`image18` into packaging, dieline, manual/insert, carton, placement or photo categories. No classified asset is physically deleted.

## Remaining production gates

External media sending defaults off (`VANTALINE_TEXT_INSPECTION_EXTERNAL_VLM_ENABLED`). Even after consent enables sending, `MATCH` remains review-only until `VANTALINE_TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED` is set after customer samples, account budgets/rate limits, prompt/model pinning and commissioning evidence pass. Manual completion cannot return PASS until `VANTALINE_TEXT_INSPECTION_MANUAL_PASS_VERIFIED` is set after page lease/fencing and multi-tab recovery tests pass.

## Developing browser tools

The WebMCP workspace hooks reuse current standard/asset selection, document
import, comparison, camera and extraction-revision callbacks. Geometry tools
use source-normalized guide and polygon coordinates, not viewport pixels.
The native browser fixture covers selection and import-field state; complete
workflow equivalence and all inspection modes remain separate acceptance work.
Activation and limitations are documented in [Agent platform status](agent-platform.md).
