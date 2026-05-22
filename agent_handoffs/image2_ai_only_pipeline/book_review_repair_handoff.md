# Book Review + Repair Handoff

Owner correction: Tony and Jesse are producers only. Book owns review, acceptance, and repair.

## Scope

Review all generated images in:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations`

Use queue metadata from:

`/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/image2_ai_only_task_queue.csv`

Bottle reference folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection`

## Review Standard

Each output must pass:

- file exists;
- PNG is readable;
- resolution is exactly `1448x1086`;
- filename exactly matches queue output path;
- object count matches queue row;
- no black proxy remains;
- no obvious background patch around the bottle;
- manual content/text/QR/logo is preserved enough for detection training;
- manual positions/rotations/scale/overlap remain stable;
- bottle is fully on the green conveyor;
- bottle is visually above all manuals;
- bottle material and shape match Generated Bottle Pose Collection;
- `lying_bar`: bottle long axis follows black bar direction and visible length;
- `upright_dot`: black dot is red cap diameter/anchor only; full upright bottle body is visibly larger than dot and centered on it;
- `no_bottle`: no bottle added.

## Repair Method

If an output fails:

1. Mark it in a review report as failed with reason.
2. Rework only that failed image using Image2 / AI image edit.
3. Overwrite the exact same output filename.
4. Do not use scripted compositing as final output.
5. Keep `1448x1086`.
6. Re-check the repaired file against the same review standard.

## Relationship to Tony/Jesse

Do not block Tony/Jesse production unless a systemic prompt/rule issue is causing repeated failures.

If a systemic issue appears, notify Mandy with:

- affected task IDs;
- failure type;
- recommended prompt/rule change;
- whether production can continue while Book repairs.

## Known Current Issues

The current output folder has 134 PNGs. Known risk categories:

- upright-dot images previously too small because the black dot was misread as the whole bottle size;
- several images may use generic bottle shapes instead of the provided bottle reference;
- some prior Image2 attempts may drift manual layout/text.

Book should audit these while Tony/Jesse continue producing new images.

