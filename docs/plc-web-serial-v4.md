# PLC Web Serial v4

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

PLC action remains fail-closed unless workstation binding/configuration is enabled, authorization, lease/generation, protocol/bundle consistency, HTTPS/Permissions Policy, and browser support are valid. Configuration or detection success never overrides an invalid physical-action gate.

`profile_verified`/`production_ready` is currently commissioning and UI evidence, not an enforced physical-write gate. Do not describe it as a hard safety gate unless code, tests, and this specification are changed together.
