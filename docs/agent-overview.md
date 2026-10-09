Account visibility now composes through `auth/visibility_composition.py`. Keep its public-network and account-projection self-calls on named graph forwarders; do not eagerly capture receiver methods or reorder selected-model/configuration reads. Authentication HTTP registration and complete application factory/lifecycle work remain separate.

Training completion wiring lives in `training/persistence_graph.py`: provide only its narrow typed account/pipeline/candidate inputs and model-spec supplier. Do not route its internal completion callbacks through `server` or merge the existing persistence boundaries. Full Web factory/lifecycle consolidation and final release acceptance remain pending.

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

Service path and output placement policy is owned by `runtime/service_paths.py`; `runtime/path_configuration_composition.py` assembles its directory, persisted-path migration and application-configuration cycle. Composition supplies focused settings, file access and call-time identity/repository interfaces. Internal recursion selects named domain methods while the entry retains compatibility aliases. Complete infrastructure and application assembly remain separate work.

`runtime/infrastructure.py` provides the reusable inert constructor used by the default entry for foundation, artifacts, path/configuration, provider/profile and read-cache owners. Only the application assembler should consume its typed result and distribute narrow handles; business constructors must not receive the complete result. The default passes its earlier artifact owner, needed for root discovery, explicitly; independent construction allocates a fresh artifact owner unless one is supplied. Connecting the remaining Web domains, transport and lifecycle remains required before complete application-factory acceptance.

Account configuration/media/response projections are owned by `auth/account_projections.py`; resource-name normalization and owner-scoped catalog checks are owned by `records/resource_names.py`. Their typed interfaces contain only relevant capabilities, with request identity resolved for each call.

Real-photo detection feedback is introduced behind an owner allowlist in `training/real_photo_*` and `storage/real_photo_feedback.py`. Its data contracts are independent from initial generated-image pretraining; follow [real-photo feedback](real-photo-feedback.md) for staged implementation and commissioning gates.

`training_review/` owns the dedicated Codex screening service, local crop tools and report-only broker. It does not import the Web application or share the label comparison queue. Inspect `docs/real-photo-feedback.md` and its versioned skill before changing screening behavior.
The initial FastAPI allocation and transport middleware assembly live in runtime/http_application.py. Use its explicit environment mapping when composing a new shell; application domains and lifetime are not yet assembled by this focused builder.

The HTTP transport-shell constructor accepts an explicit upload runtime provider for independently composed apps. This isolates only upload admission; complete artifact services and application lifecycle still require per-app composition.

ArtifactRuntimeProvider owns a lazy artifact runtime, configuration signature and lock for one composition. Existing get_runtime still selects one process-default owner; complete app wiring and artifact lifecycle remain separate.

The three pipeline runtime schedulers expose bounded close through their own thread owner. Keep repository cleanup on the native worker thread and retain task/model binding at the existing decorated runner. Do not close the advance or model dependencies while admitted auto-Agent work can still use them.

AutoOptimizationExecution in training/execution_composition.py composes initialization, mask prompts/visuals/verification, sprite publication, label generation/processing, scheduling, sprites/rendering, synthetic batches, dataset and requests. Its narrow external groups retain their original lazy selection; internal calls select the actual component after argument evaluation. Core, settings, shared runtime and separate label/check lifecycles are explicitly supplied. Native label/check entrypoints pin the supplied model resolver and actual task store once after repository scope entry; the public compatibility decorators remain unchanged. No model, prompt, task-state or process topology change is included. Core status selects the same workflow owner for label-start and sprite-pool callbacks. Route/lifecycle assembly and a complete application factory remain pending.

AutoOptimizationWorkflows in training/workflow_composition.py composes the existing Core and Execution owners with the same explicit settings/shared runtime and three separate native lifecycle owners. The two status-to-execution edges select named workflow forwarders; those select execution after argument evaluation. It constructs both inert graphs at the former Core position, with all eager dependencies already defined and the External port imports explicitly moved before their first use. No generic registry, delayed binding slot, new process, algorithm or API change is introduced. Original aliases, public worker decorators, route order and close order remain. This closes only the automatic-optimization graph; capture, pipeline collaborators and complete application assembly still require explicit final integration.

TrainingStateWorkflows in training/state_composition.py composes the existing TrainingRecordStore, TrainingTaskLifecycle and TrainingTaskViews around the supplied TrainingTaskRuntime. Records and lifecycle select the same existing RLock; lifecycle record operations and view load/refresh operations select named methods on this owner after argument evaluation. Repository factories and the two-layer model resolver remain operation-time suppliers; no user, connection or current snapshot is captured. Model freeze precedes invalidation and locking. Visibility still precedes refresh, and retired worker records remain read-only. Authorization, dual canonical/alias tombstones and partial deletion failures retain the original behavior. The entry keeps its public signatures and original component aliases. Replacing those private aliases no longer redirects owned edges; tests replace actual owner capabilities. This composes only training state, not datasets, training execution, submission, pipeline or the complete application factory.

TrainingAccountState in training/account_state_composition.py combines TrainingStateWorkflows and TrainingUserState around one supplied runtime, with operation-time repository/model/identity suppliers and explicit configuration load/save and pipeline synchronization. TrainingExecution in training/native_execution_composition.py owns the original Runner and Submission with the same account records/runtime; the existing Runner model pin remains single. TrainingTaskWorkflows in training/task_composition.py owns jobs, mutations, launch, status, dataset, preview and RunPod transfer services and validates shared account/execution identity. Internal calls use named owners; five HTTP registrars stay at their original positions. The runtime remains shared with background submission, with its original shutdown owner. Launch configuration failure preserves the already-started task; upload metadata failure preserves the published artifact; a failed completion sync retains the original failed-task update and second sync attempt without repeating generation. Neighboring assets, catalogs, background workflows and pipeline services remain explicit collaborators. This is training-task domain composition, not a complete application factory.

ModelConfiguration owns one actual model-profile service, its snapshot scope,
settings projections and HTTP registrar. Construction obtains no repository,
identity or secret. AI/image settings resolve through that owner; agent settings
still resolve first, then merge current defaults and derive enabled from configured.
Default server compatibility exports retain the existing API, while JSON fixtures
replace the explicit owner service. Missing resolution fails explicitly. Source
manifest v251 includes the actual new composition source for new task fingerprints;
historical snapshots are unchanged. This domain owner is a prerequisite for full
application composition, not proof that the complete application factory is finished.

The default `model_profile_service` compatibility name refers to its initially
constructed service; assigning that module alias no longer redirects resolution.
Tests replace `ModelConfiguration.service` explicitly. Independent factories must
supply their own repository and secret capabilities, environment mappings and
legacy-label settings supplier. The default composition retains its existing
process environment, secret store and label feature settings; this change does
not claim those default resources are isolated across complete applications.

ProviderConfiguration in model_providers/configuration_composition.py composes the twelve existing defaults, validation, URL, key identity, secret store, key registry, proxy, local-model and legacy JSON/image/agent configuration services. Internal callbacks select named owner methods at operation time; the default entry supplies external environment, paths, codecs and policy values explicitly. The profile owner uses that same provider configuration for secrets, validation and legacy migration. Construction performs no reads, migration or worker start; profile route registration stays at its original position. Compatibility method names forward to the owned domain, and tests replace its actual capabilities. This closes the configuration graph, not the remaining application-domain assembly or complete application lifecycle.

The model-profile engines route receives an explicit Codex-model supplier. The
default composition reads the existing process environment at request time;
independent registrars can supply separate environments without importing a
process-global environment from the HTTP module. Empty and whitespace values
retain the original truthiness behavior, and the administrator check remains
first. This does not establish independent construction of the full Web app.

The consolidated offline integration now starts from accepted main e1cfee3
(real-photo feedback and independent review worker). DetectionWorkflows receives
narrow analysis/capture feedback callbacks; both original capture gates and
provenance scopes remain. Compatibility aliases select the composed owners.
The real-photo routes, purpose bindings, incremental tables and review worker
remain present. Manifest v253 contains 557 actual sources at this checkpoint;
historical task snapshots are not rewritten. Full factory, combined CI and
release acceptance are separate remaining gates.

`plc/workstation_composition.py` owns the existing repository/station/browser graph through explicit external ports. Ordinary internal edges use named forwarding methods; the active-lease member binds the initial station once. Preserve both selection rules. Construction performs no I/O or capability selection. Capture collaborators, pipeline and complete app lifecycle still require final assembly.

`plc/lease_diagnostic_composition.py` groups lease acquisition/maintenance and diagnostics around the supplied workstation owner. Keep ordinary storage/token edges on named methods and active-lease checks bound once to the initial station. Construction selects no identity, clock, storage or permission capability; no new worker or protocol is added.

Retained PLC capture state composition is in plc/capture_composition.py; coordinate its state and receipt capabilities through named owners. Do not join its generation/owner-epoch protocol to browser workstation leases or enable legacy poll/reconcile workers.

Pipeline persistence, state guards and terminal training synchronization are composed in pipeline/persistence_composition.py. Its TaskStore remains lock-free internally because the caller may already hold the non-reentrant task guard. Pipeline native execution and application-wide lifecycle assembly remain separate work.

Native pipeline auto-agent, advance and recommendation composition is in pipeline/execution_composition.py. Preserve separate lifecycles, the captured resolver provider, single pin inside thread repository scope, identity restoration and producer-first shutdown. A pin failure before runtime.run keeps the old in-flight evidence; do not hide it with automatic retries or registry cleanup.

Pipeline candidate and task read/projection abilities are owned by pipeline/query_composition.py. Treat this graph as capable of protected writes: candidate refresh may save and optimization links may stop capture/save. Private server aliases are compatibility entry points; replace the real owner in tests. No new native worker is owned here.

Pipeline Agent decisions/actions/turns are composed in agent/pipeline_composition.py with PipelineQueries as the explicit projection/normalization collaborator. Preserve Flow try boundaries and private-owner replacement points. An empty pending_advances list queues only; None retains inline fallback. Turns preserve user append, apply, agent append order and earlier side effects on failure without replay.

PipelineStages in `pipeline/stage_composition.py` now composes AI activation, AI-card synchronization, training status, stage advancement, reconciliation and recommendation cache workflows around the actual PipelineQueries and the supplied PipelineRuntimeState. Internal metadata and transition calls select named methods on that owner; reconciliation selects the same runtime advance lock/inflight set used by native execution. The entry retains original component aliases and public function signatures. Its named `advance_pipeline_task` entry is distinct from the `advance` component. Constructors do not select suppliers, launch work or call a model. Preserve save-before-public-projection failures, paused-card state, shallow sharing, cache consumption and cancellation checkpoints. This closes these six stage workflows only; pose/task/HTTP composition, complete application factory, hosted performance gates and production topology activation remain pending.

PipelineTaskWorkflows in `pipeline/task_composition.py` composes the eight task-list, create, update, accessory routing, delete, Agent feedback/chat and manual advance/cancel services. It receives the actual Query, Stage, Execution and Agent owners and rejects mismatched query/persistence/runtime identities before constructing services. Internal calls select named methods; the original eight HTTP registrars execute at their original entry positions, preserving all ten endpoints and route order. Reconciliation still runs and may save before GET visibility filtering; deletion still requests cancellation before record authorization; chat still decides once outside the task guard and rechecks authorization before committing under the guard. Pose feedback remains an explicit external capability and may execute under the existing guard. Execution's own decision/advance inputs remain separate explicit ports; sharing this task graph does not complete those native cross-domain edges or the whole application factory.

For connected pipeline native dependencies, read `pipeline/runtime_composition.py` and its actual graph smoke. Replace the actual owner capability for tests; changing a root compatibility alias does not redirect an owned edge. Task routes still register in original order. Full application/environment and pose assembly, hosted acceptance and production topology activation remain separate completion gates.

When replacing connected pipeline mutation capabilities for tests, use `scripts/pipeline_runtime_test_ports.py`. It preserves frozen mutation instances and per-graph isolation; the eleven synthetic connected tests and original recommendation-runtime regression cover these boundaries.

Codex API environment configuration is an explicit registration input. The source-contract replay first validates the actual Codex API/worker and restores its single reviewed root call before earlier pipeline/PLC inverses. This test adaptation changes no pipeline or PLC business owner.

The composition source guard accepts partially replayed roots only when their entire AST matches an immutable reviewed descendant checkpoint. It still validates every actual owner before replay, rejects unknown edits at each checkpoint, and ends at the exact workstation parent. Historical oracle assertions and generic single-delta semantics remain unchanged; this does not approve a missing default Codex environment binding.


Agent Pose domain assembly uses three inert owners: `AgentStateWorkflows`
(state, tool-call records and render configuration), `PosePlanningWorkflows`
(templates, policy, generation and task plans), and `PoseExecutionWorkflows`
(photo highlight, rendering, artifact publication, call execution and sample
preparation). Internal edges select named owners at call time and preserve
callee/argument evaluation order. Clock/configuration refresh, nested state
identity and partial failures retain their original behavior. Public entry
signatures and route/lifecycle order remain unchanged; no algorithm or prompt
change is included. This closes these domain edges, not complete application
factory assembly. New tasks use manifest v270 with 583 actual source entries;
historical task snapshots and secret references are unchanged.
