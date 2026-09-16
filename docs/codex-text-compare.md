# Codex label inspection beta

Worker completion requires an observed successful process exit, reader EOF and
valid completion/session events after draining the queue. Final session/usage
metadata is pulsed before settlement. A process exiting during a database heartbeat
is handled on the next iteration; cancellation/deadline rules and finalized-report
requirements remain authoritative. No unknown call is retried or requeued.

**Status: Authoritative — implemented, default disabled; production/model accuracy not commissioned**

## User contract

`/workspace/text-compare-codex` is an independent owner-scoped workspace. Each
submission freezes a confirmed label asset's original bytes, standard revision,
EXIF-oriented input and private preview. It does not require or call the prepared
OCR/Qwen pipeline. One actual photograph contains one label. DOC/PDF import and
standard membership remain managed by the existing standard library.

Cards and `?task=<id>` links survive browser closure/reload. Running report items
are preliminary. Terminal failed/cancelled/interrupted/timed-out jobs retain
partial evidence. Summary decisions are advisory; append-only human reviews do
not overwrite them or generate PLC actions. New label-v2 reports cover the ten visual dimensions below. Legacy v1 reports
remain text-only. Structural coverage validation does not establish accuracy.

## Execution and storage

`codex_comparison_tasks` stores current task/report projections; immutable
`codex_comparison_events` records revisions and idempotent writes. Tasks bind
owner, request key, input hashes, version and optional parent task. Claiming uses
a PostgreSQL global transaction lock and allows only one active attempt. A new
session is never automatically retried/resumed. Disabled owners cannot submit
or start queued work; history/cancel/review remain available with permission.

A dedicated same-host worker starts one native `codex exec --json` per task,
using a pinned model with high effort. Fresh task directories contain no personal
rules, plugins, history or project instructions. Bubblewrap is mandatory; there
is no unisolated fallback. Its outer PID/filesystem namespace exposes OS tools,
a pinned native Codex directory, dedicated per-task account auth, readonly
inputs, writable scratch, and one Unix socket. Only the parent gets PostgreSQL
configuration. Network remains available for Codex authentication/inference;
prompt instructions exclude external OCR and browsing. This is not a network
allowlist or a claim that Codex itself enforces that exclusion.

The account's auth.json refresh is persisted privately; personal config and
session history are never copied back. Known auth-token values and task-token
echoes are removed from report writes. Raw reasoning/commands are not published.
Runtime metadata stores session ID, installed CLI version and bounded usage.

`vantaline task show`, `report progress`, `report item upsert`, `report summary set`,
`artifact add`, and `report finalize` use the task socket with a bearer scoped to
one attempt. `--request-id` supports replay of identical writes; changed payloads
conflict. Legacy examples live in `codex_compare/prompt.md`; v2 examples live in the
versioned task skill under `codex_compare/skills/vantaline-label-inspection`. Validation
failures are returned for correction within the same session. No arbitrary HTML
or script is rendered. Boxes are original-normalized xywh. Evidence needs
`--source reference|actual --box '[x,y,w,h]'`; the server reconstructs the stated
crop from immutable input and resizes to the submitted image dimensions. It never
trusts agent-edited pixels as source evidence. Transforms record rounded source
pixel bounds and output dimensions. Use null boxes for unsupported locations.

Finalization freezes report writes but does not finish the job: the worker also
requires process success, session identity, a completed turn and validated report.
Cancellation revokes writes immediately and kills the process group. A ten-minute
watchdog applies independently of DB I/O; loss of successful heartbeat for twenty
seconds also kills the subprocess. Stale thirty-second heartbeats become
interrupted, never queued. No automatic restart of an uncertain model session.
Scratch is removed after terminal settlement; after hard process death, the
worker also collects only recorded scratch belonging to terminal attempts; persistent media/reports are not
subject to automatic deletion in this release.

## API and limits

All website routes require authentication plus `inspection`, and exact owner
matching (including administrators). New submissions additionally require the
explicit commissioning allowlist and configured model. GET capabilities does
not query new tables, so default-off rollback remains safe.

- POST `/api/text-compare-codex/tasks`: multipart `captured_file`,
  `standard_asset_id`, `expected_revision` (immutable revision ID), `request_id`,
  optional `reference_region` (JSON normalized XYWH, defaults to whole image).
- GET `/tasks`: 30-item pages, opaque `before` cursor. GET `/tasks/{id}`: report.
- GET `/tasks/{id}/events?after=N`: up to 100 ordered revisions.
- POST `/tasks/{id}/cancel`, `/retry` (`request_id`), `/review`
  (`request_id`, `decision`, `note`). Retry creates a new task against frozen inputs.
- GET `/tasks/{id}/media/{sha}`: only referenced, hash-verified owner media,
  private/no-store. The agent socket is not exposed through website auth routes.

Inputs: 10 MiB and 16 million pixels. Reports: 500 items, 200 evidence attachments,
2000 events, 64 KiB text-write envelopes; individual transcription/explanation
fields are bounded. Artifacts are limited to 4096 pixels per edge and reconstructed
from source crops. History is stored outside immutable release directories.

## Configuration and commissioning

Server and worker use the same `VANTALINE_CODEX_COMPARE_ACCOUNTS` (empty by default)
and `VANTALINE_CODEX_COMPARE_MODEL`. Resolve the desired account default model
on the deployment host, then set its concrete ID; do not track a floating default.
The worker additionally requires:

- `VANTALINE_DATA_STORE=postgres`, `DATABASE_URL`: existing runtime-selector contract.
- `VANTALINE_CODEX_COMPARE_BINARY`: absolute, version-pinned native Codex executable.
  Its parent directory is exposed read-only inside the namespace; keep that
  directory limited to Codex runtime files. An npm shell wrapper is insufficient.
- `VANTALINE_CODEX_COMPARE_AUTH_HOME`: dedicated 0700 auth directory populated by
  logging in to the operator's Codex account. Never copy personal config/plugins.
- `VANTALINE_CODEX_COMPARE_WORK_ROOT`: private writable scratch directory.
- `VANTALINE_CODEX_COMPARE_MEDIA_ROOT`: exactly the website's
  `DATA_DIR/codex_comparisons/media`, with shared service-account read/write access (setgid root, private shared group).

Commission Linux bubblewrap/user namespaces, `/usr/bin/python3` with Pillow,
native Codex runtime/version and connectivity before enabling the owner allowlist.
`python -m local_inspection_service.codex_compare.worker --check` validates basic
configuration/version only; it is not the real-session acceptance gate.
`deploy/vantaline-codex-compare.service` is a reviewed service template, not installed
automatically. Create the dedicated worker account, shared media ACLs and runtime
directories through the normal controlled host procedure. Both existing web and
worker services must access newly created media; account-specific media directories
are 2770/files 0660 and inherit the provisioned root group. Limit that group to
the web and worker service accounts; set the media root to 2770 before use.
Authentication and scratch remain 0700. Do not make evidence world-readable. Verify both identities before enablement.
The worker has a 2 GiB/96-task/150%-CPU service cap; one task runs at a time.

Deploy source via PR/CI and an immutable release only. Install/restart the worker
service against that release while no task is running; never switch source below
an active worker. Disable admission and wait for settlement before upgrades or
rollback; stop the worker with KillMode=control-group if interrupted. Retain the
new tables and evidence on whole-release rollback. Clearing the allowlist stops
new work, not an already-running authorized task.

Production access, login, host isolation and a real Codex session must be verified
before marking commissioned. Use labeled positive/negative examples (wrong/missing/
extra text, case, numbers, units, punctuation, rotation, blur, glare and crop loss).
Report false positives/negatives and latency; synthetic tests or a zero exit code
are not accuracy acceptance. Record production version, task ID and evidence
without including secrets or customer media in Git.

## Optional dedicated local proxy

Set worker-only `VANTALINE_CODEX_COMPARE_PROXY_URL=http://127.0.0.1:PORT`
when this host uses an independently managed local HTTP proxy. Only this explicit
credential-free loopback URL is forwarded as upper/lowercase HTTP(S) proxy
variables through bubblewrap's cleared environment. Generic host proxy variables
are not inherited. Localhost bypass is fixed; the task report Unix socket is
unaffected. The proxy and upstream credentials remain outside the namespace.
This does not enforce a network allowlist or transparently redirect other tools.

Keep the proxy bound to loopback and managed by its existing service, independently
of a developer laptop. Verify login and a real isolated Codex turn through it
before enabling admission. A proxy outage fails the session normally; no automatic
resubmission or configured direct fallback is added. Use the same HTTP(S) proxy
variables for the dedicated account's device login. Keep subscriptions and node
secrets in restricted host configuration, never in Git. Unset the worker-specific
variable to restore the original direct behavior, then restart only after draining
active work. No global OS or website proxy change is required.


## Label-v2 multidimensional workflow

Legacy single-label cards are label-v2; the public route stays compatible and is labelled 标签检查
Beta. Freeze one selected label region plus both full originals. Packaging dielines,
manuals and whole-product inspection are excluded; known non-label categories are
filtered and rejected, and the skill must report uncertainty for misclassified
or ambiguous inputs. Multi-label reference images require selection before submit.

The CLI exposes `card show/progress/summary set/finalize`, `element upsert`,
`checklist set`, `check upsert`, `issue upsert` and existing `artifact add`.
The task-card identity is provided by the website, never chosen by the agent.
Ten dimensions: text, typography, color, graphics, completeness, orientation,
shape, layout, codes, print. Type-specific element checks supplement all ten
whole-label checks. Engineering notes are separate requirements, not printed
content; uncalibrated photos cannot prove exact color, material or millimetres.

Checklist IDs preserve element references, dimension and expectation. Later sets
append only; results can be revised until finalization with full event history.
Pending/running checks cannot finalize; uncertain and not_applicable require an
observation and explanation. MATCH requires verified scope and no open issues;
DIFFERENCES requires a difference check with an issue. Processed counts include
uncertainty/inapplicability and are explicitly distinct from successful checks.

Elements and issues carry nullable original-normalized rectangles/polygons; the
website renders controlled SVG/text, not generated markup. Selecting a check or
issue highlights the relevant sides. Missing elements never require invented
actual coordinates. Crop helpers return original transforms, and uploaded crop
pixels are reconstructed server-side. `image map` maps normalized crop rectangles
to originals. `image decode` invokes a bounded local OpenCV subprocess and persists
its payload evidence. Unsupported codes, decode failure and blur stay uncertain;
code MATCH requires nonempty equal locally decoded payload sets on both sides.

The release-bundled skill is mounted read-only at
`/work/.agents/skills/vantaline-label-inspection`. Every new session explicitly
mentions `$vantaline-label-inspection`, asks it to read SKILL.md and includes the
exact SKILL.md body as task context. The worker records its hash/version and CLI
version; this is runtime provenance, not proof of model obedience. Tests and real
session observations establish actual CLI behavior. Existing v1 tasks retain the
legacy prompt and contract. No personal skills or project history are imported.

Limits add 200 elements, 500 checks/issues and 200 decoder records to existing
bounds. Every task still has a 600-second total deadline and global concurrency 1.
Early decomposition/plan publication is required; timed-out cards retain pending
work. Finalization cannot create a false pass by dropping checks. Human review
remains independent and no dimension produces automatic business/PLC actions.

User-facing v2 findings, progress and summaries are written in Simplified Chinese;
inspected source text remains verbatim. Original-aspect SVG overlays preserve
legible marker text on long/thin labels, with issue IDs placed separately from
element IDs when their regions overlap.

## Order batch workspace (label-batch-v3)

The main beta entry is an immersive authenticated task list without AppShell sidebar.
It uses the existing owner-scoped /tasks listing to show active sessions, drafts and
historical v1/v2/v3 tasks together, with paginated earlier records. Old single-label
reports have no separate menu and are not rewritten. The bare entry always opens
the list, including when a last-batch browser preference exists. Saved direct batch
and legacy task links still open the corresponding detail; task=history opens the list.

New task opens a separate preparation page (view=new), with existing order selection
or direct Word import. Merely opening that page does not create an empty database
record. The first selected order or upload creates a server draft and binds its URL.
Returning from the list to a draft resumes editing; submission opens task detail.
Each level has a parent return: main page, task list, task overview, label detail.
List scroll and label filters/overview scroll are retained for in-page return.

The workbench has two equal-width panels with viewport-based increased height.
The left Order panel contains order selection, DOC/DOCX upload, extraction progress
and the resulting reference-image gallery together; there is no separate standard
panel or tab. Actual photos occupy the right half. Both halves fit the viewport,
with compact controls and galleries on narrow screens. Bottom:
label cards ordered differences, confirmation, unfinished, match. Details, raw checks
and source annotations open per label; overview polling excludes those collections.
Uploaded drafts and selected order persist on the server. Uploads that have not
returned success are never presented as saved. Frozen task detail has no upload or
camera controls; adding inputs starts through New task and leaves the original intact.

DOC is bounded by the existing 30 MiB helper; DOCX by the existing 100 MiB importer.
This import path stores owned draft standards with filename-derived names and an
internal material identifier, but never confirms them or invokes old Qwen/OCR jobs.
Word text/drawing composition is not rendered. Exact embedded duplicates retain
all source occurrences; unsupported images show an explicit preview error.
A draft allows at most 50 actuals (usual usage 1–10), each 10 MiB/16MP, and 500
reference image/region entries. Repeated actual bytes require explicit acceptance
as another sample. A single task remains queued/running regardless of photo count.

New APIs under /api/text-compare-codex:
- POST /batches with request_id creates a durable draft; GET /batches pages by before.
- GET /batches/{id} returns the overview; GET /batches/{id}/labels/{label} gives detail.
- POST /batches/{id}/document: file and request_id; import state is pollable.
- POST /batches/{id}/order: standard_id and request_id; stores source snapshots.
- POST /batches/{id}/name: name and request_id; changes draft report display name.
- POST /batches/{id}/photos: file, request_id, allow_duplicate=false.
- POST /batches/{id}/labels/{label}/remove: request_id, draft only.
- POST /batches/{id}/submit: request_id; rejects changed orders and freezes input.
- POST /batches/{id}/labels/{label}/review: separate decision/note/request_id.
- POST /batches/{id}/retry: request_id, label_ids, optional matches mapping each
  selected label to asset_id/region; creates and queues a fresh linked batch.
Existing /tasks/{id}/events, /cancel and private /media/{sha} apply to batches.
Legacy /tasks endpoints and saved v1/v2 reports remain supported. No v3 data rewrite.

See the release-bundled batch CLI reference for commands and schemas. Every scoped
operation includes --label, including local crop, decode and evidence. Reference
regions cannot change after inspection starts. Human-selected retry correspondences
are frozen. The broker reconstructs each evidence crop from the current label's
immutable source. It never accepts a different label's evidence IDs as proof.
Batch limits preserve per-label v2 caps plus 20,000 total events; JSON writes remain
64 KiB. A batch-wide summary must disclose every actual's outcome. Pending matches
or checks prevent finalize; unresolved matching may finish processing only with
REVIEW_REQUIRED, never MATCH. Timeout keeps pending work and partial reports.

The updated skill is explicitly invoked and mounted read-only for every session.
Navigation contact sheets are separate from full-resolution inspection files.
The entire batch shares one 600-second session; no automatic child session, retry,
external OCR, old classification or PLC action is introduced. An ambiguous actual
must remain a visible confirmation card, while unused document photos are not
missing-label defects. Real quality and deadline completion require measured
commissioning; synthetic UI/harness evidence does not certify accuracy.
