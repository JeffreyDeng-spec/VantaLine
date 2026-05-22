# Tony Producer-only Batch: Continue Image2 Generation

Owner correction: Tony and Jesse must keep generating images continuously. Review and repair work is no longer Tony's responsibility.

## Role

You are a producer. Generate new images only.

Do not spend time auditing old outputs or doing broad review. If you notice an obvious defect, mention it in progress notes, but continue production unless generation is impossible.

## Assigned Queue

CSV:

`/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/tony_resume_after_repair_next50.csv`

Rows:

`img2-0107` through `img2-0156`

## Input and Output

Input proxy folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations`

Output folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations`

Bottle reference folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection`

## Non-negotiable Generation Rules

- Use Image2 / AI image edit for each final image.
- Do not use scripts to create final images.
- Do not use mechanical compositing/cutout paste/drawing as final output.
- Use exact output filename from the CSV.
- Keep output resolution exactly `1448x1086`.
- Preserve conveyor background/camera framing.
- Preserve manual count, text, QR codes, logos, positions, rotations, scale, and overlap.
- Bottle must visually sit above manuals.
- Bottle must stay fully on the green conveyor.
- Bottle material/shape must come from the Generated Bottle Pose Collection.
- `lying_bar`: generate a lying bottle aligned to the black bar direction and length.
- `upright_dot`: black dot is only the red cap diameter/anchor. Generate the full top-down upright bottle larger than the dot, with red cap diameter matching the dot.
- `no_bottle`: do not add a bottle.

## Throughput

Keep going through all 50 assigned rows.

Report every 10 generated files:

- completed count;
- latest filename;
- any files you could not generate;
- whether any blocker requires Mandy/Book.

Do not switch into review mode. Book owns review and repair.

