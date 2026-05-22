# Image2 AI-only 1000-image Pipeline

Owner goal: regenerate 1000 atom combination images as AI/Image2 outputs, not script-generated composites.

This replaces the earlier two 500-image blanket assignments with a small production pipeline:

1. One manager owns queue, progress, acceptance, and retry decisions.
2. Two available worker agents run the first pilot batch: Tony and Jesse.
3. Every task is tracked in a queue CSV with input path, output path, prompt, status, retry count, result hash, and review status.
4. The first execution is a 20-image pilot, split 10/10.
5. If the pilot passes, production continues in 100-image batches.

## Files

- `image2_ai_only_task_queue.csv`: source of truth for all 1000 tasks.
- `queue_stats.json`: counts by label, missing-count, bottle proxy state, and batch.
- `tony_pilot_20_tasks.csv`: Tony's 10 pilot tasks.
- `jesse_pilot_20_tasks.csv`: Jesse's 10 pilot tasks.
- `worker_protocol.md`: mandatory execution and QA rules for workers.
- `pilot_tony.md`: Tony handoff for the 20-image pilot.
- `pilot_jesse.md`: Jesse handoff for the 20-image pilot.

## Current Worker Capacity

The real Alook execution agents available for this project are Tony and Jesse. So the configured pilot uses 2 workers, not 5. The pipeline is still compatible with adding more workers later by assigning `pending` rows from the queue to new workers in 20-50 image chunks.

## Acceptance Gate

Do not scale to 1000 until the 20 pilot images exist in:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations`

Pilot acceptance requires:

- 20 exact filenames generated.
- 1448x1086 PNG resolution.
- no black proxy residue.
- bottle fully on green conveyor when bottle exists.
- bottle visually above all manuals.
- no bottle added when `bottle_proxy_state=no_bottle`.
- manual count and layout preserved.

