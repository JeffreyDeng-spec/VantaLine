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
