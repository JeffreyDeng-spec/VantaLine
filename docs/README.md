# VantaLine documentation

**Status: Authoritative**

This is the single index for current project knowledge. Documents marked **Authoritative** describe `main`; **Proposal** documents are unimplemented; **Historical / Do not implement** documents are audit evidence only.

## New maintainer path

1. [New maintainer checklist](new-maintainer-checklist.md)
2. [Architecture](architecture.md)
3. [Contributing](../CONTRIBUTING.md)
4. [Testing](testing.md)

## Current authoritative specifications

- [Agent overview](agent-overview.md) — context and routing for coding agents
- [Architecture](architecture.md) — services, data ownership, and request flows
- [PLC Web Serial v4](plc-web-serial-v4.md) — only current PLC implementation contract
- [Configuration reference](configuration-reference.md) — configuration names, ownership, and secret boundaries
- [Testing](testing.md) — change-area test matrix
- [Release management](release-management.md) — GitHub release policy
- [Production runbook](production-runbook.md) — operations, diagnosis, and rollback
- [PostgreSQL runtime operations](postgresql-runtime.md) — current data-store and migration contract
- [Production baseline provenance](production-baseline-202608.md) — origin of the first reproducible baseline
- [Text inspection v2](text-inspection-v2.md) — account-scoped standards, document safety, VLM idempotency, and staged retirement

## Authoritative subsystem guides

- [Inspection service entry](../local_inspection_service/README.md)
- [RunPod training integration](../local_inspection_service/docs/runpod-yolo-train-worker.md)
- [RunPod worker package](../local_inspection_service/workers/vantaline_yolo_train_worker/README.md)
- [Model artifact policy](../models/README.md)


## Historical documents

[Archive index](archive/README.md) lists superseded PLC phases, migrations, commissioning packets, and implementation evidence. Never implement an archived document without first promoting it through a reviewed proposal that updates this index.

`contract.json` is the machine-readable registry used by CI to protect this structure.
