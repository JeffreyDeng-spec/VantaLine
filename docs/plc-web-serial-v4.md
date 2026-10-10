> **Current backend composition:** The Web application is assembled by `runtime/application.py`; `server:app` retains the stable ASGI entry and compatibility exports. Earlier migration checkpoint statements about unfinished domain/application assembly describe their historical checkpoint and are superseded by [canonical application construction](architecture.md#canonical-web-application-construction). They do not establish current CI, performance or production acceptance; those remain separate release gates.

The retained legacy deadline smoke uses a synthetic write-event barrier to establish its after-write snapshot premise and drains the synthetic worker before restoring test callbacks. Its 0.5-second deadline and evidence assertions remain. This test scheduling changes no production PLC policy, browser ownership, protocol, persistence, physical I/O or uncertain-write retry behavior; it does not establish real-device acceptance.

Account visibility graph wiring retains the existing private configuration projection and media permissions. PLC route ordering, workstation leases, browser-only I/O, actual ACK and uncertain-write handling remain unchanged.

Training completion graph assembly does not change PLC I/O, lease ownership, ACK settlement or uncertain-write handling. Its synthetic graph verification does not contact a serial port or PLC.

Diagnostic receipt/finalization now delegates to `plc/diagnostic_state.py` inside the existing station mutation transaction. It accepts an active or draining owner lease even after lease or diagnostic deadline expiry, so a late browser result can clear the in-flight diagnostic ID, deadline and token hash. It does not alter state, expiry or heartbeat, record an ACK, retry a physical write, or open a serial port. A repeated receipt fails because the diagnostic is no longer in flight.

Diagnostic confirmation now delegates to `plc/diagnostic_state.py`. It still checks the active lease, matching diagnostic ID, strict deadline and token hash inside the original station mutation transaction. A missing hash short-circuits token access. A successful confirmation leaves in-flight evidence and lease timing untouched and may be repeated before the deadline; it is not evidence that a serial write or ACK succeeded.

Diagnostic reservation state now lives in `plc/diagnostic_state.py`. It generates the diagnostic ID and attempt token before the station mutation; after active-lease and generation checks it rejects an in-flight dispatch with a strict deadline boundary. It preserves the DB-issued timestamp and separate host-millisecond deadline, D206/value 6, 2000 ms execution window, 500 ms ACK/read timeouts, and hash-only persisted token. Receipt behavior is described above; confirmation is described separately.

The model rebind state transition lives in `plc/lease_maintenance.py`. It still strips and validates the model before the station mutation, then invokes the shared active-lease guard before the strict in-flight deadline check. It updates only model, heartbeat and expiry; the existing browser-owned serial path and ACK evidence remain unchanged.

The browser lease claim and activation state machine is implemented in `plc/lease_acquisition.py`. Claim still checks release consistency, client ID, protocol and model permission before the station transaction. A lease may be reclaimed at expiry equality; activation still rejects a repeated activation and preserves its distinct missing, fenced, expired and generation errors.

The lease heartbeat and disconnect state transitions now use `plc/lease_maintenance.py`. Heartbeat still fences session, epoch, owner, active state, expiry and configuration generation before extending a `plcweb_` in-flight deadline. Disconnect still returns released for a missing lease and drains only while an in-flight deadline remains; it does not alter browser ACK evidence.

The legacy `/api/plc/config` GET response is assembled through `plc/config_diagnostics.py`; POST still requires `system_settings` and returns the existing 410 before any write. The diagnostic projection keeps its original validation order, audit ordering and lock-scoped shallow snapshot of active attempts. It does not read or write physical serial.

The dispatch/diagnostic HTTP boundary covers attempt declaration, diagnostic plan/receipt/confirmation and dispatch receipt through `plc/dispatch_diagnostic_api.py`. The three diagnostic routes still require `system_settings` before workstation authorization. Original dispatch IDs and payloads reach unchanged business functions; ACK, idempotent receipt and uncertain write handling do not move.

The connection-lease HTTP boundary registers connect, activate, heartbeat, model rebind and disconnect through `plc/connection_lease_api.py` and delegates to `plc/connection_lease.py`. Station authorization precedes every operation; model rebind separately checks model permission before its mutation. Existing lease state, database clock, fencing, draining and physical browser I/O do not move.

The first workstation-management HTTP boundary now registers five existing get/list/pair/config/verification routes through `plc/workstation_management_api.py` and delegates their unchanged authorization and error handling to `plc/workstation_management.py`. Root request models, state mutators, PostgreSQL/local storage, leases, dispatches and browser serial operation remain in place. The get/list projections may migrate stored configuration, revoke leases or settle expired dispatches as uncertain; they are not pure reads or cached.

# PLC Web Serial v4

Accessory catalog policy, projection and persistence now live in `accessories`.
Their composition receives no PLC dispatch, workstation or serial capability.
The adjacent capture-dispatch implementation retains browser ownership, lease
validation, actual ACK evidence and the existing no-retry rule for uncertain writes.
Accessory IDs, visibility and catalog payloads retain their previous contracts.

The frontend/source guard follows the root adapters to the actual `DetectionAnalysis.analyze_bgr`
and `AiDetectionAnalysis.analyze_bgr_ai_detection` methods. It rejects PLC dispatch in either body,
changed class imports/constructor bindings or forwarding, a missing model-snapshot decorator or
ordinary routing that bypasses the pinned
AI entry. Existing image/video/camera provenance checks remain unchanged; these services receive no
PLC dispatch capability and the physical protocol is unaffected.

Authentication route policy now lives in `auth.route_permissions`; its PLC
administrator/runtime permission alternatives are unchanged. Middleware extraction
does not change browser ownership, leases, dispatch ACK rules or physical I/O.

The adjacent administrator cost route is now mounted through `analytics.cost_api`
at its original application position. Cost aggregation has no PLC port, lease or
dispatch dependency; this extraction leaves capture streaming and physical-write
rules unchanged.

**Status: Authoritative — only current PLC implementation contract**

Path/configuration composition retains ApplicationConfiguration's atomic protected
namespace mutation and per-owner authorization ContextVar. Moving directory,
sanitizer and path-migration callbacks into their domain owner does not change
leases, browser ownership, protocol or uncertain-write no-retry behavior. Source
contracts validate the actual new owner before replaying the original PLC oracle.

## Ownership and profile

Physical PLC communication runs in a foreground desktop Edge/Chrome page through feature-detected `navigator.serial`; the production server performs zero serial I/O. Configuration is workstation-scoped, survives account logout, and is not a user preference.

The current workstation schema is v5 while the physical protocol remains `plc-web-serial-v4`. Its preset profile is Mitsubishi FX3GA-40MR and uses logical D/Y names, 9600 baud, even parity, 7 data bits, 1 stop bit, checksum including ETX, a 500 ms timeout, and zero automatic retries. D is decimal; Y is octal and rejects digits 8/9. Derived hexadecimal protocol addresses are read-only diagnostics.

Safe defaults are automatic capture disabled, input `D205`, trigger value `1`, result `D206`, a blank optional Y point, and a fixed 200 ms browser poll interval. Input and result registers must be different and inside D0-D255. A v4 workstation configuration migrates to v5 without enabling automatic capture or changing its existing D/Y choices.

## Connection lifecycle

Connection requires a user gesture, Web Lock, server connecting lease, browser port selection/open, then active station lease. Heartbeat maintains the lease. A model change rebinds the active lease without reopening the serial port. A temporarily hidden page pauses new attempts and validates the lease before resume.

Normal ACK and a clean single-byte NAK may keep the port connected. Port removal, lease loss, bundle/protocol mismatch, timeout, short/malformed/extra response, or uncertain write closes the port and requires manual reconnection.

When automatic capture is enabled, the foreground camera page reads the configured D input through the same reader/writer and serialized transaction queue. Polls never overlap and result writes/diagnostics take priority. No per-poll server request or server serial operation exists.

Connection, refresh, configuration change, or reconnect starts unarmed. The browser must read a non-trigger value before a later transition to the trigger value can capture once. A sustained trigger value is latched and cannot repeat until reset. A trigger observed while the camera/model is not ready or another detection is busy is recorded as missed and is never queued for delayed capture.

## Dispatch and evidence

Only dedicated camera detection, whether manually requested or initiated by a valid PLC input edge, may create a v4 output plan. The plan binds station, lease epoch, configuration generation, model/request identity, logical and resolved addresses, frame digests, and a short execution deadline. Image upload and video remain detection-only.

The shared drag/drop component changes only browser file selection. A dragged image or video retains ordinary upload provenance and cannot create a PLC plan. Camera-device lifecycle in the PLC detection workbench remains governed by the existing readiness, edge-latching and no-replay rules; the text-comparison camera selector does not participate in PLC dispatch.

The browser declares the complete attempt before I/O, writes D (`PASS=1`, `FAIL=0`), waits for `ACK=06`, then handles optional Y. D failure suppresses Y. Blank Y produces no Y plan/frame/write/audit. `NAK=15` is rejected only when the input becomes quiet; residual bytes make the operation uncertain.

Receipts are workstation evidence, not proof against browser/OS failure. At-most-once is the promised physical safety property; end-to-end exactly-once is not claimed.

## Production gates

The initial request-schema extraction moves only non-PLC validation models into
domain schema modules. PLC models and strict field validation remain in their
current domain; browser ownership, lease/ACK rules and zero uncertain-write retries
are unchanged. Keep the assembled HTTP and existing PLC contracts in this gate.

Public/workspace route separation keeps the same browser origin. Updated camera
task links use `/workspace/tasks/.../inspect`; legacy URLs remain aliases.
Website/help shortcuts open new tabs instead of replacing a live workbench;
the existing hidden-page pause and lease-validation behavior still applies.
Authentication return navigation never automatically connects a port, starts
capture or replays a request. No PLC protocol, lease, plan or physical I/O logic
is changed by the navigation layer.

PLC action remains fail-closed unless workstation binding/configuration is enabled, authorization, lease/generation, protocol/bundle consistency, HTTPS/Permissions Policy, and browser support are valid. Configuration or detection success never overrides an invalid physical-action gate.

`profile_verified`/`production_ready` is currently commissioning and UI evidence, not an enforced physical-write gate. Do not describe it as a hard safety gate unless code, tests, and this specification are changed together.

## Developing structured browser entry points

The Agent workbench hooks call the existing camera capture, disconnect and
diagnostic callbacks. First serial connection returns a native-user-input wait;
no arbitrary serial-write tool or server serial path is added. Uploaded images
and videos still use their existing non-PLC analysis flow. Tool unregistration
is not a verified cancellation of physical I/O and does not permit replay.
Native browser fixture tests do not access physical devices; authorized station
commissioning remains outstanding in [Agent platform status](agent-platform.md).

## Settings location and role boundary

The existing workstation pairing/configuration/verification form now lives under
Settings → 设备与运行. Only administrators edit system parameters. Authorized
operators still choose cameras and connect/disconnect PLC on the detection page.
The move does not alter browser-owned serial I/O, real-ACK verification, capture
provenance, leases, addresses or uncertain-write/no-retry behavior.

The opt-in COS file adapter changes camera image persistence only: it must succeed before image analysis can continue. PLC authorization, lease epochs, planned frames, browser-only serial I/O and the ban on retrying uncertain physical writes remain unchanged. Storage tests use synthetic images and perform no PLC I/O.

### Backend module ownership

Request schemas live in `schemas/plc.py`. `plc/browser_dispatch.py` and `plc/dispatch_mutations.py` retain declaration-before-I/O, workstation/browser ownership and durable receipt handling. Workstation service/repository interfaces retain existing leases and atomic writes. Historical projection, transition, validation, capture and legacy-dispatch modules preserve readable evidence without reviving server serial I/O. Unknown outcomes remain non-retryable and a late completed callback cannot turn an expired analysis into a pass.

Auto-optimization capture extraction retains its existing source and state collaborators. It does not grant the backend serial ownership or add physical output. Browser leases, actual ACK requirements and uncertain-write non-retry behavior are unchanged.

Pipeline workflow relocation does not grant physical PLC capability or alter camera provenance. Browser station leases, actual ACK evidence and uncertain-write non-retry behavior stay unchanged.

Accessory image extraction and training asset preparation do not produce physical PLC writes. Camera provenance, leased browser serial ownership and actual ACK requirements remain unchanged; uncertain writes remain non-retryable.

Configuration extraction preserves protected PLC namespace policy and existing transaction authority. It does not grant server serial access or alter browser leases, actual ACK validation or uncertain-write non-retry behavior.

The two generic/protected app-configuration write entry helpers now delegate to AppConfigStore. Existing protected PLC keys, namespace transaction, shared reentrant guard and authorization-token reset remain unchanged. This move does not enable legacy workers, open serial ports, create dispatch attempts, change browser leases or retry uncertain physical writes.

The existing camera/lease callers now obtain model permission and account configuration through the explicit auth projection boundary. Permission order and scoped model lookup remain unchanged, as do browser serial ownership, lease/ACK and uncertain-write rules.

Dedicated camera orchestration is implemented in `detection/camera_request.py`; `server.py` retains route composition. It preserves station/permission checks, upload fingerprinting, durable begin-before-analysis, completed-request reuse and pending conflicts, followed by result/error evidence settlement. Ordinary image/video services remain unable to generate browser dispatch plans; no server serial I/O is introduced.

### Real-photo feedback provenance

The dedicated camera request propagates its existing station/session identity as a source group around analysis. This metadata grants no PLC capability and changes no dispatch fingerprint, D/Y frames, lease, retry or physical-write behavior. Ordinary image/video provenance also grants no camera dispatch authority.
Historical server worker definitions now live in plc/legacy_workers.py, with per-instance locks and thread references. The current start_plc_runtime_workers hook still returns None and does not start them. This is retained legacy implementation for contract/history verification, not a supported physical-I/O topology: only the leased workstation browser performs PLC communication. No protocol, lease, ACK, uncertain-write retry or browser capture behavior changes.

Active-lease validation retains record/clock/user order, session/owner/active-state fencing, strict expiry, generation and protocol checks, optional epoch and enabled configuration. A zero/missing database timestamp still selects the live fallback clock. Missing/fenced/disabled errors and lazy short-circuit evaluation remain distinct. The owned guard records no ACK, sends no serial command and changes no lease. A supplied configuration migration callback retains its existing side effects and exceptions.

The legacy activation readiness helper moved out of the application entry; start_plc_runtime_workers still returns without starting any server-side serial activity. Its optional import check never opens a port. Existing DB-clock atomic-primitive requirement and ordered profile/dependency errors are retained solely for compatibility; passing this policy does not authorize a physical write or establish browser ACK evidence.

LegacyRuntimeCoordination isolates retained coordination bookkeeping only. Claims still use the existing application clock and namespace transaction, and a successful claim can invoke the supplied heartbeat starter. This is not a DB-clock physical-I/O fencing primitive or permission to enable server serial I/O. Current startup remains dormant and Web Serial ownership/ACK rules are unchanged.

LegacyDispatchRecords retains reverse audit lookup and the exact idempotent dispatch hash, source/request/passed-identity/fingerprint checks. Only record lookup is under the existing configuration guard; verification retains its original position after guard release. Conflict responses preserve authoritative evidence and the existing failed/no-new-I/O fields. No physical action or retry is added.

The retained reconciliation and input-poll bodies moved intact into LegacyPlcOperations. They remain disabled by current startup. Reconciliation skips invalid or non-pristine records, settles the same blocked records and returns after one eligible item. Polling retains ownership/pending gates, nonblocking slot acquisition, release in finally and post-read generation checks. The module is not a new physical-I/O permission; only synthetic read/transport capabilities are used in its tests.

Unreachable pre-Web-Serial capture implementation tails are no longer present in the application entry. Claim/heartbeat/release/event-stream routes remain registered with the same request schemas and HTTP 410 behavior. Current PLC config still forwards to the existing service, and physical I/O remains browser-only.

Bootstrap location composition retains the existing plc_web_serial_state.json location beneath the same data directory. It creates no files, changes no browser lease or dispatch protocol and opens no serial port.

Cost service composition is initialized immediately after the retained legacy PLC route slot; those PLC route bodies, registration order, browser ownership and serial prohibition remain unchanged. The early PipelineTaskStore constructor stores suppliers only and performs no database or physical operation.

DetectionWorkflows closes internal ordinary/AI/publication/capture routing without adding PLC dispatch. The no-dispatch source contract follows root aliases through the actual graph to both original analysis implementations, checks the real pinned teacher route, and rejects class/decorator import shadowing. Dedicated camera provenance, browser leases, actual ACK and uncertain-write no-retry rules remain unchanged. Synthetic graph tests perform no physical PLC I/O.


Configuration persistence allocates its RLock and protected-namespace ContextVar
inside ApplicationConfiguration. The default assembled Web instance keeps its
legacy _config_io_lock alias for existing PLC suppliers; those suppliers still
select the guard lazily. Two independently constructed configuration owners have
distinct guards and flags. PostgreSQL PLC namespace writes retain the existing
advisory lock and atomic write transaction. This does not complete the PLC
workstation/capture domain factory or alter browser ownership, lease checks, ACK
evidence or the prohibition on retrying uncertain physical writes.
Real-photo source metadata binds ordinary/camera uploads to their exact payload hash and video feedback to the analyzed frame pixels. This adds no physical I/O or server serial access. Only the existing dedicated camera request still declares a browser dispatch; ordinary image/video feedback cannot create one.

An ordinary upload's optional capture-session identifier is feedback grouping metadata only. It never asserts a PLC camera request, station lease or dispatch. Non-PLC camera frames can therefore remain in one dataset source group while using ordinary image detection.

## Workstation composition boundary

Workstation persistence, station policy and browser dispatch now compose through `PlcWorkstationWorkflows`. Internal service callbacks select their domain owner after arguments are evaluated; active-lease validation retains its fixed station binding. Pairing, generation upgrades, expiry settlement, declaration persistence, lease fencing and ACK validation remain in their existing business modules and transactions. Recent dispatch and station projection may write and must not be treated as cached reads. No physical serial operation, uncertain-write replay or new worker is introduced. Full PLC/application lifecycle assembly remains a separate gate.

Lease and diagnostic composition selects the same supplied workstation graph. Diagnostic confirmation and model rebind use its initial bound active-lease member. A disconnect with an in-flight diagnostic keeps the original draining lease, and a late diagnostic receipt clears evidence without manufacturing an ACK or extending expiry. Frame construction and row serialization failures still roll back the station transaction. No server serial port, retry or new runtime topology is introduced.

Retained capture state uses PlcCaptureWorkflows for coordination, expiry and durable receipts. This does not enable legacy capture routes (410), change the no-op start_plc_runtime_workers hook, or start a server serial poller. Browser-only PLC I/O, uncertain-write non-retry and distinct lease epochs remain required.

Pipeline persistence assembly leaves capture 410 routes, browser workstation ownership, PLC plan/ACK contracts, and the no-op server PLC startup unchanged. The capture and workstation state machines retain separate owners.

The pipeline native runtime graph does not enable capture routes, server serial workers or PLC transport factories. Only leased browser dispatch retains physical I/O authority; ordinary pipeline/image tasks do not gain PLC write permissions.

The PipelineQueries assembly retains existing auto-optimization stop-capture capabilities and does not change browser ownership, workstation leases, diagnostic receipts, actual ACK or uncertain-write rules. It starts no legacy PLC polling worker.

Pipeline Agent conversation/action composition preserves the existing supplied pause and pose execution capabilities. It changes no workstation/browser ownership, lease or actual ACK rules, and starts no PLC poller or worker.

The PLC lease composition source-contract smoke now replays the validated outer PipelineStages delta before the existing domain deltas. PLC business code, browser lease/ACK behavior and physical I/O are unchanged; the original assertions remain and unknown outer wiring changes fail replay.

PLC source-oracle checks also validate the outer PipelineTaskWorkflows assembly delta before restoring original coordination and lease constructors. This changes the test location adapter only; actual PLC ownership, at-most-once browser writes and ACK/uncertainty rules remain unchanged.

PipelineRuntimeWorkflows composes native pipeline transitions without creating a PLC executor or changing browser-owned lease, dispatch, ACK or uncertain-write behavior. Legacy PLC shutdown and dormant worker state retain their original lifecycle.

The explicit Codex environment mapping changes no PLC authorization, workstation lease, browser serial I/O or ACK/uncertain-write handling. Its regression uses synthetic accounts and performs no PLC or paid model operation.

The original pipeline runtime ownership clock oracle validates actual composed modules and replays the reviewed root assembly before its unchanged historical clock assertion. This preserves the original state/lock tests after task-list clock ownership moved into PipelineTaskWorkflows. No runtime or PLC behavior changes.

The composition source guard accepts partially replayed roots only when their entire AST matches an immutable reviewed descendant checkpoint. It still validates every actual owner before replay, rejects unknown edits at each checkpoint, and ends at the exact workstation parent. Historical oracle assertions and generic single-delta semantics remain unchanged; this does not approve a missing default Codex environment binding.


Pose composition adds three strict outer source-oracle layers. The unchanged
PLC lease/diagnostic composition regression validates the actual Pose owners
before reversing those layers and inspecting its original PLC binding assertions.
This test adaptation preserves protocol, browser ownership, lease/ACK rules,
uncertain-write non-retry behavior and the original Web shutdown order; it adds
no PLC access or production worker transition.

The default infrastructure builder adds one strict outer source delta before
the existing path/Pose replay. Actual construction modules and unchanged
business sources are verified; the original PLC regressions retain their
assertions. HTTP route order, Web lifecycle positions, browser lease/ACK and
uncertain-write non-retry behavior remain unchanged. Source manifest v272
includes the real infrastructure modules for new tasks only; historical model
snapshots are not rewritten. This change introduces no physical PLC IO.

Provider/real-photo graph assembly does not change workstation ownership, lease/epoch, ACK or uncertainty policy. The feedback bridge's training submission remains separate from browser PLC dispatch. Its native startup and shutdown perform no server serial I/O. Preserve the complete PLC and HTTP contracts when accepting the consolidated backend composition batch.

Canonical application assembly preserves the actual PLC services, HTTP contracts and browser-only physical I/O rules. Each app receives fresh logical PLC runtime/executor state; closing another app cannot close it. No serial ownership, lease, ACK, uncertain-write retry, protocol or camera provenance behavior changes. Keep the complete PLC/release regression and whole-package rollback gates.
