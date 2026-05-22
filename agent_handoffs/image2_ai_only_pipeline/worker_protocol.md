# Worker Protocol: Image2 AI-only Atom Images

You are not working alone in this folder. Do not modify another worker's rows or any previous output folder.

## Hard Rule

The final output image must be produced through Image2 / AI image editing. Do not create the final PNG by script compositing, copy/paste, drawing, mechanical inpainting, or cutout overlay.

Scripts are allowed only for counting, hashing, reading queue rows, and QA checks.

## Input and Output

Input proxy folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations`

Output folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations`

Bottle reference:

`/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection`

The bottle material, shape, and pose must come from the images in this folder. Do not invent a different bottle.

Do not touch old output:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_optimized_1000_atom_proxy_combinations`

## Per-task Rules

For each queue row:

1. Load exactly one input PNG.
2. Use the row's `prompt` and `edit_instruction`.
3. Save exactly one output PNG to the row's `output_path`.
4. Preserve the exact filename and resolution `1448x1086`.
5. QA the single output before moving on.
6. If it fails, retry once with a tighter prompt.
7. If it still fails, stop that task and mark/report `manual_review_needed`; do not silently skip it.

## Visual Rules

- `lying_bar`: black bar means a lying glass bottle aligned to the bar direction.
- `upright_dot`: black dot means the red cap diameter/anchor for an upright top-down bottle, not the full bottle size.
- `no_bottle`: no bottle proxy exists; do not add a bottle.
- Lying bottle length and visual size must match the black bar length and bbox.
- Upright/top-down bottle red cap diameter must match the black dot diameter; the full glass bottle footprint must be clearly larger than the dot, following the Generated Bottle Pose Collection proportions.
- Bottle must stay fully on the green conveyor.
- Bottle must be visually above every manual.
- No black stick/dot residue is allowed.
- Do not add source-background patches around the bottle.
- Preserve manual count, layout, scale, rotation, overlap, text, QR codes, and logos as much as the AI edit allows.

## Progress Rules

For pilot: report after every generated image.

For production batches after pilot: report every 10 images and at batch completion.

If Image2 cannot generate and save even the first assigned image from your runtime, report the exact blocker immediately. Do not keep the issue `in_progress` without output.
