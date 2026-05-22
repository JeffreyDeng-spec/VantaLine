# AI-only Image2 Regeneration: 1000 Atom Images, Tony 0001-0500

Owner request: regenerate the 1000 randomized atom images so every final image is AI/Image2-generated, not script-generated or copied/composited.

You are not alone in this folder. Jesse handles `0501-1000`. Do not modify Jesse's range. Do not modify or delete any previous output directory.

## Do Not Touch

Preserve this old folder exactly as-is:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_optimized_1000_atom_proxy_combinations`

Do not delete, overwrite, or clean it.

## Input

Proxy sketch input folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations`

Assigned input files:

`0001*.png` through `0500*.png`

Metadata:

- `/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations/labels.csv`
- `/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations/manifest.json`

Bottle reference:

`/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection/overhead_bottle_pose_collection_v1.png`

## Output

New AI-only output folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations`

Save exactly 500 PNGs using the exact same filenames as the input files.

## Hard Requirement: AI-only

Every final output must be produced through Image2 / AI image generation or AI image editing.

Do not satisfy this task by:

- copying proxy PNGs;
- script-compositing bottle cutouts;
- drawing or pasting bottle assets mechanically;
- using a script to fabricate the final photo.

Scripts may only be used for bookkeeping/QA, not final image creation.

## Visual Requirements

For each image:

1. Preserve the intended randomized layout:
   - same object set;
   - same overall manual positions, rotations, scale, and overlap;
   - same background/camera framing.
2. Replace black proxy only when it exists:
   - black bar = lying glass bottle aligned with the bar direction;
   - black dot = upright bottle top-down view;
   - no black proxy residue;
   - clean bottle boundary;
   - no pasted source-background patch.
3. If no black proxy exists:
   - do not add a bottle;
   - still run through AI/Image2 for realistic photo generation/enhancement;
   - preserve the object set.
4. Critical conveyor constraint:
   - bottle must be fully on the green conveyor surface;
   - bottle cannot sit on the metal rail, outside the green belt, or beyond the frame;
   - if the proxy sketch places the bottle partly outside the green conveyor, move the generated bottle minimally inward onto the green conveyor while preserving the closest matching direction.
5. Critical stacking constraint:
   - bottle must be visually above all manuals;
   - never let any paper cover or occlude the bottle.
6. Preserve manual content:
   - do not hallucinate or rewrite text;
   - do not distort QR codes/logos more than normal photo realism;
   - do not add or remove manuals.

Resolution must remain `1448x1086`.

## Reject / Retry Conditions

Reject and retry outputs with:

- any remaining black stick/dot;
- bottle missing or incomplete;
- bottle outside the green conveyor;
- bottle under any paper;
- obvious pasted background around bottle;
- changed object count;
- wrong filename;
- wrong resolution.

## Report Back

When done, report:

- exact PNG count written;
- confirmation that files are AI/Image2-generated;
- files that failed or need manual review;
- any residual quality risk.
