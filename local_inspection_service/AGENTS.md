# Inspection service agent routing

The root [AGENTS.md](../AGENTS.md) remains mandatory. Before changing this subtree, read [architecture](../docs/architecture.md) and [testing](../docs/testing.md).

- PLC, camera dispatch, workstation lease, or `frontend/src/features/plc/`: also read [PLC Web Serial v4](../docs/plc-web-serial-v4.md).
- Authentication, permission, API, or configuration: also read [configuration reference](../docs/configuration-reference.md).
- Storage or migration: also read [PostgreSQL runtime operations](../docs/postgresql-runtime.md) and the [production runbook](../docs/production-runbook.md).

Do not create a second source of truth in this subtree. Update the mapped repository-level authoritative document when behavior changes.

Text standards compose through text_inspection/standard_composition.TextStandardWorkflows. The inert domain owner holds the supplied TextRecordStore, media, revisions, standard imports/library/edits, document classification and preparation jobs. Internal storage/media/revision callbacks select that owner at operation time; each native job service has its own scoped lifecycle. Three registration methods remain at their original entry positions, preserving intervening routes. This does not complete application assembly or remove the remaining comparison/extraction/history dependencies.

TextComparisonWorkflows in text_inspection/comparison_composition.py composes comparison submission, reviews, history, extraction admission and prepared comparison lifecycles around the actual text standard owner. Record/media/preparation edges select that owner; the entry retains explicit compatibility forwarders. History, extraction and inspection registration stay at their original positions. The extraction resolver has one typed field completed by extraction registration before inspection admission; an unassembled resolver fails explicitly. Remaining Codex/label interfaces and other application domains still need final assembly.

AutoOptimizationCore in training/core_composition.py owns state storage, recommendations, readiness, status and shadow evaluation. Use its actual methods for internal replacements; settings and runtime remain explicit supplied owners. Shadow analysis selects the DetectionWorkflows supplier after argument evaluation. Generation, dataset and training scheduling and their route/lifecycle assembly remain separate work. Preserve native scope cleanup and shared optimization locking.

AutoOptimizationExecution in training/execution_composition.py composes initialization, mask prompts/visuals/verification, sprite publication, label generation/processing, scheduling, sprites/rendering, synthetic batches, dataset and requests. Its narrow external groups retain their original lazy selection; internal calls select the actual component after argument evaluation. Core, settings, shared runtime and separate label/check lifecycles are explicitly supplied. Native label/check entrypoints pin the supplied model resolver and actual task store once after repository scope entry; the public compatibility decorators remain unchanged. No model, prompt, task-state or process topology change is included. Core status still has explicit external label-start and sprite-pool callbacks; closing those edges, route/lifecycle assembly and a complete application factory remain pending.
