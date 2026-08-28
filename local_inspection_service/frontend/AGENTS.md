# Frontend agent routing

Follow the repository [AGENTS.md](../../AGENTS.md) and inspection-service [AGENTS.md](../AGENTS.md). The frontend owns browser camera state and physical Web Serial I/O; the backend owns authorization, workstation lease/epoch, immutable frame plans, and receipt validation.

For PLC or camera work, read [PLC Web Serial v4](../../docs/plc-web-serial-v4.md) before editing. Preserve one reader, one writer, serialized physical transactions, at-most-once writes, hidden-page pause/resume validation, and fail-closed behavior for uncertain outcomes. Run frontend typecheck/build plus both PLC smoke contracts.
