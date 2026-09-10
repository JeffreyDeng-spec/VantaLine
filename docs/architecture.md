# Architecture

**Status: Authoritative**

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

`main` is packaged into `/opt/vantaline/releases/<release-id>` and production `current` atomically points to one immutable release. Mutable data, environment configuration, model artifacts, and database state remain outside release directories. A release contains backend source, one production frontend bundle, migration definitions, locked dependencies, `VERSION.json`, and `SHA256SUMS`.

The browser cookie identifies a workstation independently of login. User permissions still gate configuration, connection, camera inspection, attempt, and receipt operations. Secrets remain in GitHub Environment secrets or restricted server environment files and are never represented by real values in Git.
