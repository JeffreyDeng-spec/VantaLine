# Codex text comparison beta

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
not overwrite them or generate PLC actions. Graphics/colors/print quality are
outside scope. MATCH requires a nonempty fully located match-only report and no
unverified text scope; this structural validation does not establish accuracy.

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
conflict. JSON schema examples live in `codex_compare/prompt.md`. Validation
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
Scratch is removed after terminal settlement; persistent media/reports are not
subject to automatic deletion in this release.

## API and limits

All website routes require authentication plus `inspection`, and exact owner
matching (including administrators). New submissions additionally require the
explicit commissioning allowlist and configured model. GET capabilities does
not query new tables, so default-off rollback remains safe.

- POST `/api/text-compare-codex/tasks`: multipart `captured_file`,
  `standard_asset_id`, `expected_revision` (immutable revision ID), `request_id`.
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
