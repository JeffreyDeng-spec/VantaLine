# PLC Phase 1 code-only evidence

## Outcome and boundary

This packet implements a disabled-default Mitsubishi FX programming-port ASCII result dispatcher. It is not Modbus RTU. All validation used fake transports and temporary JSON/in-memory PostgreSQL repository doubles. No dependency was installed, no service was deployed or restarted, no production configuration changed, and no real serial port or PLC was opened, scanned, read, or written.

Image dispatch occurs once after the final image result. Video dispatch occurs once after all sampled frames are aggregated. PLC state is appended as `plc_sync`; transport, audit, timeout, or control-plane failures never change the detection `passed` verdict, rule output, detections, or artifact URLs.

## Protocol and checksum decision

Frames are `STX + CMD + address + optional data + ETX + two uppercase checksum characters`; responses are one-byte ACK/NAK. A pyserial-style empty `read(1)` and an explicit `TimeoutError` both map to the timeout class, with a diagnostic source; a non-ACK/NAK control byte maps to `short_response`.

The supplied VB evidence is contradictory: its executable checksum loop excludes ETX, while its comment says CMD through ETX. The setting therefore exposes exactly two modes:

- `exclude_etx_legacy_vb` — default, follows the executable VB loop;
- `include_etx_documented_comment` — follows the comment only and is not claimed as VB-proven.

Both modes remain subject to a separate on-site real-PLC ACK gate.

| Operation | Default legacy-VB/exclude-ETX hex | Documented-comment/include-ETX hex |
| --- | --- | --- |
| D206 = 0 | `02313131394330303030034346` | `02313131394330303030034432` |
| D206 = 1 | `02313131394330303031034430` | `02313131394330303031034433` |
| Y04 OFF | `023830313038033031` | `023830313038033034` |
| Y04 ON | `023730313038033030` | `023730313038033033` |

No D207/D210/D211/D212 handshake, compensation write, whole-group replay, or live test action is present.

## Physical I/O and audit semantics

- `attempting` is persisted before transport open; `sent` appears only after a full-frame `write()` return.
- Open failure has `attempted=false` and no `sent` history.
- Calling the serial `write()` API sets `attempted=true`. Return `0` is a known zero-byte write; a positive in-range integer is known partial/full evidence. `None`, booleans, non-integers, negative values, and values beyond the frame length are never coerced or represented by a sentinel: they retain `write_call_started/outcome_uncertain`, `write_count_known=false`, and `reported_write_count=null`, then fail closed as `write_result_unknown` with no retry or next target. Partial write and full-write/flush failure are also not automatically retried.
- Retry policy is one shared `(terminal code, transport phase)` contract used by both the client loop and reducer finalization. Only NAK/response, timeout/read, short-response/response, and unexpected-response/response may consume the configured retry budget. Write/flush timeout, unknown or invalid result, short write, serial I/O, flush failure, open/dependency failure, and internal/unknown terminal results stop after one operation. A retryable result cannot be finalized with an empty reason until that target's budget is exhausted.
- ACK followed by final audit failure preserves `attempted=true`, ACK targets/frames, and `audit_persist_failed_after_ack`; it never reports “not attempted.”
- D206 ACK followed by Y04 NAK/timeout preserves D206 receipts, `acknowledged_targets`, `failed_target=Y04`, per-attempt operations, and the actual Y04 physical state. No compensation or D206 replay occurs.
- Every physical operation has a stable attempt ID, target, immutable frame binding, byte count, diagnostic source, physical status, outcome, and finish evidence. Failed attempts remain when a later retry ACKs.

The persisted dispatch record is the version authority. One pure versioned reducer consumes the immutable dispatch binding plus a strict ordered typed event stream (`create`, `attempting`, `start_attempt`, `advance_attempt`, `finish_attempt`, `deadline`, `finalize`). Create, every typed mutation, finalization, and persisted duplicate verification all use that same reducer. Each atomic typed mutation first runs the full persisted verifier before deriving its event, closing corrupt/migration and TOCTOU bypasses. Event sequence and monotonic timestamps, strict non-coercing scalar types, target/retry order, attempt identity, frame binding, write-count knowledge, result code/phase/diagnostic/byte semantics, retry-budget exhaustion, finish-after-start, and no-event-after-terminal are validated before CAS. `state_version` must equal the event count. The verifier recomputes and exact-compares every physical/terminal projection, including status/history, attempts/target/bytes, ACK/failed summaries, operations, counters, flags, and worker state; it never accepts a caller-built projection as evidence. Final states cannot regress. Restarted terminal duplicates return the verified terminal record without I/O or version bump; corrupt or migration-required records fail closed on direct, queued, and typed repository paths with no write, version bump, or transport open.

Durable idempotency authority is not pruned by the recent-audit UI window. All dispatch identities and state/event records remain in the protected persisted namespace; only `GET /api/plc/config` limits `recent_dispatches` to the newest 100 for presentation. Exact duplicates and identity conflicts therefore remain authoritative after more than 100 later dispatches, and queued/uncertain records cannot be evicted and recreated as v1.

## Configuration, generation, and persistence ownership

`GET/POST /api/plc/config` uses `system_settings` RBAC. Pydantic rejects coercion and unknown fields. The runtime normalizer independently requires real booleans, integers, finite numeric timeout, and real strings before allowlist/format checks. Persisted string numbers, numeric addresses, booleans in string fields, NaN/Infinity, and malformed/non-object PLC namespaces are invalid, effectively disabled, diagnostic, and no-I/O. Only an absent `plc` key means legal unconfigured/default-disabled; an explicit null/list/string/number/bool is corruption and requires a complete legal replacement.

The protected namespace is `plc`, `plc_control_generation`, and `plc_dispatches`. PLC mutations use one atomic repository contract. Generic `save_config`/`save_app_config` re-read and preserve these keys, so a stale unrelated writer cannot resurrect enabled state or delete generation/audit. JSON uses a reentrant process lock and atomic file replacement. PostgreSQL repository code uses a transaction-scoped advisory lock for protected namespace mutation/CAS and generic-save preservation; independent repository doubles exercise the same contract without connecting to a database.

Generation is the epoch for all normalized physical I/O fields, not only disable. Any effective change to enabled, port/serial parameters, timeout/retries, addresses, checksum mode, or target policy increments generation in the same mutation. Equal normalized saves do not. A dispatch binds one immutable snapshot+generation and rechecks before every retry and next target. Disable/config change after an attempt starts does not kill that low-level I/O, but prevents all later attempts/targets and preserves the completed physical evidence.

For the JSON single-instance runtime, the final epoch/enabled check, typed start event, and in-flight declaration share one `_config_io_lock` linearization section. If configuration commits first, the stale worker performs no I/O. If attempt declaration commits first, the configuration response observes that in-flight attempt; exactly that already-declared attempt may complete, while retries and later targets remain blocked. PostgreSQL activation remains disabled pending the separate durable multi-instance lease/reconciliation phase.

## ASGI worker and deadlines

Final serial work runs in a bounded worker thread; the ASGI event loop remains available for GET config/status and POST disable. Queue wait is bounded at 2 seconds and configured transport combinations are capped at a 60-second dispatch budget; the request wait has an explicit total deadline.

Queue deadline, disable, worker deadline, active attempts, and final cleanup use the same per-dispatch state/audit upsert. A deadline before transport sets a cancel token and remains `attempted=false/not_attempted`; the worker cannot later start I/O. A deadline after attempt start returns an authoritative `attempted=true/outcome_uncertain/worker_continues=true` snapshot; background completion updates the same dispatch ID at a higher CAS version. HTTP snapshots include `state_version`; GET may show the later terminal version. Pure queue timeout and disable-while-queued are persisted, versioned, and no-I/O.

## PostgreSQL activation capability gate

Phase 1 does not implement durable cross-instance attempt-start leases, crash expiry, or reconciliation. Therefore when the active runtime repository is PostgreSQL, effective PLC state is forced disabled while `plc_pg_coordination_available()` is false:

- POST enable returns HTTP 409 `plc_pg_coordination_unavailable`;
- dispatch returns `attempted=false/not_attempted` and performs no transport I/O;
- Settings shows the structured capability blocker.

The proven PG namespace/CAS contract must not be confused with cross-instance physical-attempt sequencing. Activation requires a separate schema/repository/deployment-topology gate implementing durable attempt ID/epoch/target/start/state/version/lease evidence, expiry reconciliation, and DB-authoritative status.

## Validation evidence

| Command | Result |
| --- | --- |
| `python3 local_inspection_service/scripts/smoke_plc_phase1.py` | PASS — both checksum modes/eight goldens; ACK/NAK; empty-read and exception timeout; non-ACK control byte; retry/open failure; default disabled/no-I/O; PASS/FAIL/Y04; idempotence; physical/audit separation; strict API/RBAC; image/video final dispatch |
| `python3 local_inspection_service/scripts/smoke_plc_phase1_hardening.py` | PASS twice — single reducer for create/all typed transitions/finalize/verifier; full-verifier-before-mutation; exhaustive terminal-result and shared `(code, phase)` retry/no-retry actual-server matrix; Optional/known write-count matrix (`None`, zero, partial, full, bool/negative/oversize/string); INTERNAL outcome closure at before-open/during-write/after-full stages; six projection forgeries; event sequence/time/target/result/retry-budget/unfinished/event-after-terminal attacks; legal NAK→retry→ACK and NAK-exhausted→failed; strict bool/int/string persisted schemas; JSON and independent-PG typed/direct/queued no-write/no-bump/no-I/O paths; recent-limit+1 durable duplicate/identity/queued/uncertain retention; deterministic config-first and attempt-first declaration linearization; partial/flush faults; protected namespace/CAS; stale saves; restart/no-replay; generation/disable barriers; event-loop and queue/total deadline snapshots; PG capability 409/no-I/O |
| `python3 local_inspection_service/scripts/smoke_plc_frontend_contract.py` | PASS — server-backed settings, checksum contradiction/ACK gate copy, effective state/capability errors, attempting/status display, async image/video final-only dispatch, no out-of-scope handshake/Modbus/localStorage |
| targeted `python3 -m py_compile ...` | PASS |
| `smoke_phase1_core_cleanup.py` | PASS |
| `smoke_auth_rbac.py` | PASS |
| `smoke_data_analysis.py` | PASS |
| `smoke_phase3a_resources.py` | PASS |
| `smoke_phase3b_detection.py` | PASS |
| `smoke_ai_detection.py` | PASS — 30 checks |
| `smoke_ai_config_provider.py` | PASS |
| `smoke_agent_config.py` | PASS |
| `smoke_runtime_store_selector.py` | PASS |
| `smoke_postgres_runtime_repository.py` | PASS |
| `smoke_endpoint_runtime_store_probe.py` | PASS |
| frontend `npm run typecheck` | PASS |
| frontend `npm run build` | PASS; existing nonblocking chunk-size warning |
| scoped `git diff --check -- <PLC packet paths>` | PASS |

Full regression is not all-green: `python3 local_inspection_service/scripts/verify_task_pipeline.py` passes its first seven checks, then fails in `verify_accessory_long_short_aspect_rule` at the existing training-preview footprint assertion: expected `[57,143]`, actual `[85,213]`. The assertion/function and related rendering metadata have no overlap with the PLC scoped files. Per manager direction it was not modified in task #43. It remains a go-live blocker until its owner restores green or supplies an independently evidenced baseline/waiver; it is not classified as a PLC code-only blocker.

The repository was heavily dirty before task #43, including overlapping changes in `server.py`, storage modules, frontend files, and `requirements.txt`. HEAD-based full-file stats therefore mix unrelated work and are not task-only evidence. No blanket add, commit, reset, or rollback was performed. The actual `data/config.json` and last-good snapshot contain no PLC residue.

## File purposes

- `plc_fx_ascii.py`: strict config, frame/checksum generation, fakeable transport, attempt evidence, retry/result dispatcher.
- `server.py`: protected namespace/CAS/lattice, config API/RBAC, generation/cancel state, bounded worker/deadlines, PG capability gate, image/video integration.
- `storage/postgres_runtime_repository.py`: advisory-transaction protected namespace mutation and generic-save preservation.
- `storage/runtime_records.py`: preserves explicit JSON null so malformed namespace remains diagnosable rather than becoming `{}`.
- frontend API/types, `RulesPage`, detection page, and styles: checksum and capability contracts, settings, warnings, recent-view/idempotency copy, status/diagnostics.
- `smoke_plc_phase1.py`, `smoke_plc_phase1_hardening.py`, `smoke_plc_frontend_contract.py`: focused executable evidence.
- `requirements.txt`: declares `pyserial==3.5`; it was not installed in this task.

## Implementer / Challenger handoff

- Implementer: Tony.
- Accepted: FX ASCII only; checksum ambiguity explicit; strict disabled-default config; final-only worker dispatch; physical/audit separation; partial-success truth; immutable detection/config/frame binding; repository CAS/lattice; stale-writer protection; deterministic cancel/deadline behavior; PG activation fail-closed.
- Rejected: Modbus naming/implementation, browser-only settings, per-frame I/O, D207/D210/D211/D212, compensation/replay, live connection, deploy/restart/install, or pretending local locks prove PG multi-instance safety.
- Main challenges incorporated: ACK/audit separation; sent/open semantics; ETX contradiction; atomic RMW/stale saves; strict persisted values/namespaces; partial-frame/multi-frame evidence; ASGI deadlines; generation epoch and attempt-declaration linearization; restart/CAS; durable idempotency retention independent from presentation limits; identity and recursive evidence monotonicity; removal of raw optional-CAS/create bypasses; strict minimal typed create/transition payloads; full verification inside every atomic mutation; one reducer for event-to-projection truth; exact duplicate verification; shared retry admission/finalize policy; INTERNAL terminal outcome closure; and Optional/known write-count handling without a `-1` sentinel.
- Open activation blockers: real PLC/cable/driver/timing/address/interlock proof; real ACK for the selected checksum mode; the unrelated task-pipeline regression; and durable PostgreSQL cross-instance attempt lease/crash reconciliation plus deployment-topology proof.

Any live enablement requires a new reviewed execution packet, maintenance window, private configuration, machine-safe state, rollback procedure, and explicit operator confirmation.
