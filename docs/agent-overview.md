# Agent overview

**Status: Authoritative**

## Mission and current system

VantaLine lets users define inspection tasks, maintain accessory evidence, build/train or select detection models, and inspect camera, image, or video input. Camera results may produce a workstation-scoped PLC output plan.

```text
Edge/Chrome React UI ──HTTPS──> FastAPI ──> PostgreSQL/runtime storage
       │ camera                         │ detection/model workers
       └─ Web Serial v4 ──> local PLC  └─ immutable audit/dispatch plan

GitHub PR → required CI → main → immutable release → production → /api/version
```

The browser owns camera capture and physical serial I/O. FastAPI authenticates, authorizes, generates immutable PLC frames/plans, and records browser evidence. PostgreSQL owns shared records and workstation identity/configuration. Production source is never edited in place.

## Code and ownership map

- `local_inspection_service/server.py`: API composition, authentication/permissions, detection orchestration, PLC station leases/dispatches.
- `local_inspection_service/frontend/src/`: React UI; `features/plc/webSerialClient.ts` is the physical Web Serial state machine.
- `local_inspection_service/model_providers/`: OpenAI-compatible, Gemini, Agnes and Qwen image transports, provider selection/retry orchestration, legacy migration settings, configuration policy, key registry, local secret material, explicit capabilities, shared error types and payload/error parsing without importing the Web application.
- `local_inspection_service/accessories/`: accessory workflows, crop component analysis/selection, object sprite preprocessing, masked sprite geometry, dimension metadata, artifact publication, material alpha, shared cutout runtime, chroma geometry and pose layout/selection/preview policies, and materialized sprite/text asset inventory, and preview sprite decoding/selection/orientation, and asset canvas composition, and preview/document asset loading, and accessory reference evidence, display labels, profile projection, physical dimensions, profile payloads, profile generation, background evidence, and background-library selection.
- `local_inspection_service/agent/`: explicit Agent settings HTTP, invocation, conversation, orchestration state, tool-call records, pose assets/templates/planning/rendering/materialization and pose task and real-photo highlight workflows, pipeline background publication, image helpers and sprite coordination, pipeline decision/action/turn and recommendation services.
- `local_inspection_service/auth/status.py`: permission-aware public status and configuration projections with explicit dependencies.
- `local_inspection_service/storage/`: persistent runtime repositories and PostgreSQL coordination.
- `local_inspection_service/plc_web_serial.py` and `release/plc-protocol.json`: logical-address/frame and release protocol contract.
- `scripts/` and `.github/workflows/`: verification, immutable packaging, installation, rollback, and automation.
- Runtime uploads, outputs, secrets, models, logs, and databases are external mutable state and are not source.

## Invariants agents must preserve

- Current PLC protocol is `plc-web-serial-v4`; server serial opens/writes remain zero.
- One active browser lease/epoch owns a station. A dispatch is declared before physical I/O and is at-most-once.
- ACK may keep a connection reusable. Timeout, malformed/extra response, crash, disconnect, or unknown write outcome is uncertain and is never automatically replayed.
- D must ACK before optional Y. Blank Y means no Y frame or audit operation.
- Only the dedicated camera endpoint can create a PLC plan; image upload/video cannot assert camera provenance.
- Frontend/backend protocol or bundle mismatch disables PLC action while ordinary website functions remain available.
- Database migration is expand-first and must remain compatible with the previous release during rollout.

## Work routing

| Change | Read first | Minimum focused checks |
| --- | --- | --- |
| PLC/Web Serial/camera dispatch | `plc-web-serial-v4.md`, `architecture.md` | PLC smoke, frontend contract, typecheck, release contract |
| API/auth/permissions/config | `architecture.md`, `configuration-reference.md` | targeted backend smoke, permission tests, docs contract |
| PostgreSQL/migrations | data migration runbook, `production-runbook.md` | migration safety and real PostgreSQL schema smoke |
| Frontend behavior | `architecture.md`, `testing.md` | typecheck and production build |
| CI/release/install | `release-management.md`, `production-runbook.md` | source safety, shell syntax, release contract |

## Never do

Do not deploy from a dirty worktree, copy individual files to production, build on the server, bypass PR/CI, commit mutable data/secrets, infer production configuration from examples, or revive archived server-side pyserial/input-polling designs. If repository truth conflicts with runtime truth, stop, collect read-only evidence, and reconcile both through a PR.

PLC backend policy and workflows are organized under `local_inspection_service/plc/`: event/transition/validation policy, browser dispatch and durable evidence, workstation repository/service, and retained legacy dispatch/capture state. Strict HTTP payload models live in `schemas/plc.py`. The entry keeps composition and migration forwarders; physical I/O remains browser-only.

Auto-optimization application workflows now live in `local_inspection_service/training/auto_optimization_*`. Each workflow has its own policy, state or execution boundary and narrow dependencies. Temporary entry forwarders preserve callers while composition cleanup is pending; the existing training/image task process topology is unchanged.

The remaining pipeline link/projection/candidate/metadata/mutation/AI-activation workflows are under `local_inspection_service/pipeline/`. Follow each focused service and its typed ports instead of placing new business logic in application-entry forwarders.

Accessory image workflow code is grouped under `accessories/` with explicit file, record, policy, access and execution interfaces. Image provider configuration and training asset preparation remain in their respective domain packages. The entry composes these boundaries; no new aggregate business context is introduced.

Application-config persistence lives under `config/`; model local configuration and tool dispatch live under `model_providers/`; status request projection remains an auth-domain service. Tests replace explicit capabilities and source guards inspect those actual modules instead of removing requirements.

Service path and output placement policy is owned by `runtime/service_paths.py`; composition supplies focused settings, file access and call-time identity interfaces.

Account configuration/media/response projections are owned by `auth/account_projections.py`; resource-name normalization and owner-scoped catalog checks are owned by `records/resource_names.py`. Their typed interfaces contain only relevant capabilities, with request identity resolved for each call.

The initial FastAPI allocation and transport middleware assembly live in runtime/http_application.py. Use its explicit environment mapping when composing a new shell; application domains and lifetime are not yet assembled by this focused builder.

The HTTP transport-shell constructor accepts an explicit upload runtime provider for independently composed apps. This isolates only upload admission; complete artifact services and application lifecycle still require per-app composition.

ArtifactRuntimeProvider owns a lazy artifact runtime, configuration signature and lock for one composition. Existing get_runtime still selects one process-default owner; complete app wiring and artifact lifecycle remain separate.

The three pipeline runtime schedulers expose bounded close through their own thread owner. Keep repository cleanup on the native worker thread and retain task/model binding at the existing decorated runner. Do not close the advance or model dependencies while admitted auto-Agent work can still use them.

AutoOptimizationExecution in training/execution_composition.py composes initialization, mask prompts/visuals/verification, sprite publication, label generation/processing, scheduling, sprites/rendering, synthetic batches, dataset and requests. Its narrow external groups retain their original lazy selection; internal calls select the actual component after argument evaluation. Core, settings, shared runtime and separate label/check lifecycles are explicitly supplied. Native label/check entrypoints pin the supplied model resolver and actual task store once after repository scope entry; the public compatibility decorators remain unchanged. No model, prompt, task-state or process topology change is included. Core status selects the same workflow owner for label-start and sprite-pool callbacks. Route/lifecycle assembly and a complete application factory remain pending.

AutoOptimizationWorkflows in training/workflow_composition.py composes the existing Core and Execution owners with the same explicit settings/shared runtime and three separate native lifecycle owners. The two status-to-execution edges select named workflow forwarders; those select execution after argument evaluation. It constructs both inert graphs at the former Core position, with all eager dependencies already defined and the External port imports explicitly moved before their first use. No generic registry, delayed binding slot, new process, algorithm or API change is introduced. Original aliases, public worker decorators, route order and close order remain. This closes only the automatic-optimization graph; capture, pipeline collaborators and complete application assembly still require explicit final integration.

TrainingStateWorkflows in training/state_composition.py composes the existing TrainingRecordStore, TrainingTaskLifecycle and TrainingTaskViews around the supplied TrainingTaskRuntime. Records and lifecycle select the same existing RLock; lifecycle record operations and view load/refresh operations select named methods on this owner after argument evaluation. Repository factories and the two-layer model resolver remain operation-time suppliers; no user, connection or current snapshot is captured. Model freeze precedes invalidation and locking. Visibility still precedes refresh, and retired worker records remain read-only. Authorization, dual canonical/alias tombstones and partial deletion failures retain the original behavior. The entry keeps its public signatures and original component aliases. Replacing those private aliases no longer redirects owned edges; tests replace actual owner capabilities. This composes only training state, not datasets, training execution, submission, pipeline or the complete application factory.
