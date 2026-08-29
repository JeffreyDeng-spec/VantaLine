# PLC Web Serial v4

**Status: Authoritative — only current PLC implementation contract**

## Ownership and profile

Physical PLC communication runs in a foreground desktop Edge/Chrome page through feature-detected `navigator.serial`; the production server performs zero serial I/O. Configuration is workstation-scoped, survives account logout, and is not a user preference.

The current FX-compatible test profile uses logical D/Y names, 9600 baud, even parity, 7 data bits, 1 stop bit, checksum excluding ETX, a 500 ms ACK timeout, and zero automatic retries. D is decimal; Y is octal and rejects digits 8/9. Derived hexadecimal protocol addresses are read-only diagnostics.

## Connection lifecycle

Connection requires a user gesture, Web Lock, server connecting lease, browser port selection/open, then active station lease. Heartbeat maintains the lease. A model change rebinds the active lease without reopening the serial port. A temporarily hidden page pauses new attempts and validates the lease before resume.

Normal ACK and a clean single-byte NAK may keep the port connected. Port removal, lease loss, bundle/protocol mismatch, timeout, short/malformed/extra response, or uncertain write closes the port and requires manual reconnection.

## Dispatch and evidence

Only dedicated camera detection may create a v4 plan. The plan binds station, lease epoch, configuration generation, model/request identity, logical and resolved addresses, frame digests, and a short execution deadline.

The browser declares the complete attempt before I/O, writes D (`PASS=1`, `FAIL=0`), waits for `ACK=06`, then handles optional Y. D failure suppresses Y. Blank Y produces no Y plan/frame/write/audit. `NAK=15` is rejected only when the input becomes quiet; residual bytes make the operation uncertain.

Receipts are workstation evidence, not proof against browser/OS failure. At-most-once is the promised physical safety property; end-to-end exactly-once is not claimed.

## Production gates

PLC action remains fail-closed unless workstation binding/configuration is enabled, authorization, lease/generation, protocol/bundle consistency, HTTPS/Permissions Policy, and browser support are valid. Configuration or detection success never overrides an invalid physical-action gate.

`profile_verified`/`production_ready` is currently commissioning and UI evidence, not an enforced physical-write gate. Do not describe it as a hard safety gate unless code, tests, and this specification are changed together.
