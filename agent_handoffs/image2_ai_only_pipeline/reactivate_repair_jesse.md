# Jesse Reactivation: Repair Known Errors + Bottle Shape Audit

Owner request: resume work and fix the current bad outputs.

## Inputs

Audit CSV:

`/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/jesse_shape_material_repair_audit_tasks.csv`

Output folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations`

Bottle reference folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection`

## Required Repairs

1. Finish the previous upright-scale correction.
   - Known Jesse-side blocker: `img2-0164`.
   - The black dot is only the red cap diameter/anchor, not the full bottle size.
   - Rework it so the full upright bottle body is visibly larger than the dot and matches the Generated Bottle Pose Collection proportions.

2. Audit your assigned generated bottle rows for wrong bottle material/shape.
   - Compare the generated bottle visually against the Generated Bottle Pose Collection.
   - If the bottle looks like a generic/invented bottle instead of the provided bottle, rework it.
   - If the bottle shape/material is already correct, leave that file alone and mark it PASS in your report.

## Hard Rules

- Rework means overwrite the exact same output filename.
- Do not create duplicate filenames.
- Do not use scripted compositing as the final output.
- Use Image2 / AI edit per repaired image.
- Preserve manuals, text, QR/logos, positions, rotations, scale, and overlap.
- Bottle must remain on the green conveyor and above all manuals.
- For lying bars: match bar direction and length.
- For upright dots: red cap diameter matches dot diameter; full bottle body is larger than the dot.
- Output must stay `1448x1086`.

## Report

Report:

- files audited;
- files reworked;
- files left unchanged as PASS;
- unresolved blockers;
- first and last modified output filenames.

